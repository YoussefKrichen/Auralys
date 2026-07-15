from __future__ import annotations

from app.agent.skills.client_history import ClientHistorySkill
from schemas.agent_schema import AgentChatRequest


class _FakeOperationsDataToolClientNotFound:
    def get_client_by_name(self, name: str) -> dict:
        raise ValueError(f"Client not found for lookup: {name}")


class _FakeRAGTool:
    def search_client_documents(self, client_name: str, limit: int = 5) -> dict:
        return {"hits": []}


def test_client_history_skill_handles_unknown_client_gracefully():
    skill = ClientHistorySkill(
        operations_data_tool=_FakeOperationsDataToolClientNotFound(),
        rag_tool=_FakeRAGTool(),
    )
    request = AgentChatRequest(user_id=1, role="sav", message="Historique du client Plac Art")

    result = skill.run(request)

    assert not result.proposed_actions
    assert result.confidence < 0.5
    assert "trouve" in result.answer.lower() or "trouv" in result.answer.lower()
