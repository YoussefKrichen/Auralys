from fastapi.testclient import TestClient

from app.api import create_app
from app.auth.session_token import create_session_token
from schemas.agent_schema import AgentChatResponse, AgentIntent


def _auth_headers(role: str = "ceo") -> dict[str, str]:
    token = create_session_token(user_id=1, username="test-user", role=role, display_name="Test User")
    return {"Authorization": f"Bearer {token}"}


class _FakeAgentOrchestrator:
    def handle_chat(self, request):
        return AgentChatResponse(
            conversation_id="12",
            intent=AgentIntent.ASK_NEXT_SAV_DESTINATION,
            answer="Je recommande Pharmacie Victoria.",
            requires_approval=True,
            proposed_actions=[],
            sources=["OPERATIONS_INTERVENTIONS", "GOOGLE_ROUTES"],
            confidence=0.82,
            justification="Classement SAV calcule.",
        )

    def save_feedback(self, **kwargs):
        return {"feedback_id": 1}

    def list_pending_actions(self):
        return [{"id": 99, "action_type": "UPDATE_SAV_PLANNING"}]

    def approve_action(self, action_id, approved_by, review_note=None):
        return {"id": action_id, "status": "APPROVED", "approved_by": approved_by}

    def reject_action(self, action_id, approved_by, review_note=None):
        return {"id": action_id, "status": "REJECTED", "approved_by": approved_by}

    def get_active_memory(self):
        return [{"id": 4, "memory_type": "BUSINESS_RULE"}]


class _FakeContainer:
    def build_agent_orchestrator(self):
        return _FakeAgentOrchestrator()

    def build_history_service(self):
        raise AssertionError("not used in this test")

    def build_review_service(self):
        raise AssertionError("not used in this test")


def test_agent_chat_endpoint_returns_pdf_shape():
    client = TestClient(create_app(_FakeContainer()))

    response = client.post(
        "/agent/chat",
        json={
            "user_id": 1,
            "role": "ceo",
            "message": "Ou doit aller l'equipe SAV maintenant ?",
            "context": {
                "team_id": 3,
                "current_location": {"lat": 36.8065, "lng": 10.1815},
            },
        },
        headers=_auth_headers("ceo"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "ASK_NEXT_SAV_DESTINATION"
    assert payload["requires_approval"] is True
    assert payload["confidence"] == 0.82


def test_agent_chat_endpoint_requires_authentication():
    client = TestClient(create_app(_FakeContainer()))

    response = client.post(
        "/agent/chat",
        json={"user_id": 1, "role": "ceo", "message": "Bonjour"},
    )

    assert response.status_code == 401


def test_ceo_only_route_rejects_sav_role():
    client = TestClient(create_app(_FakeContainer()))

    response = client.get("/agent/actions/pending", headers=_auth_headers("sav"))

    assert response.status_code == 403


def test_ceo_only_route_accepts_ceo_role():
    client = TestClient(create_app(_FakeContainer()))

    response = client.get("/agent/actions/pending", headers=_auth_headers("ceo"))

    assert response.status_code == 200
    assert response.json()["rows"][0]["action_type"] == "UPDATE_SAV_PLANNING"


def test_missing_browser_pages_return_404():
    client = TestClient(create_app(_FakeContainer()))

    response = client.get("/reference-browser")

    assert response.status_code == 404
    assert response.json()["detail"] == "Static page not found: reference_browser.html"
