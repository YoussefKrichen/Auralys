from __future__ import annotations

from app.agent.core.orchestrator import AgentOrchestrator
from schemas.agent_schema import AgentChatRequest, AgentIntent, ProposedAction, SkillResult


class _FakeIntentRouter:
    def detect_intent(self, message: str) -> AgentIntent:
        return AgentIntent.GENERAL_QUESTION


class _FakeSessionManager:
    def save_conversation(self, **kwargs) -> int:
        return 101


class _FakeStore:
    def save_action(self, conversation_id: int, action: ProposedAction) -> int:
        return 501


class _FakeMemoryTool:
    pass


class _FakeLLMService:
    def describe_images(self, prompt, images):
        return []

    def answer_details(self, prompt, fallback_context, query="", analysis=None):
        return {
            "answer": "Synthese finale pour l'utilisateur.",
            "response_source": "fallback",
            "model_output": None,
            "llm_error": "disabled",
        }


class _FakeSkill:
    def run(self, request: AgentChatRequest) -> SkillResult:
        return SkillResult(
            answer="Brouillon outil avec fait principal.",
            proposed_actions=[
                ProposedAction(action_type="RECOMMEND_ROUTE"),
                ProposedAction(action_type="UPDATE_SAV_PLANNING"),
            ],
            sources=["RAG_MAINTENANCE", "OPERATIONS_INTERVENTIONS"],
            confidence=0.78,
            justification="Synthese basee sur les outils disponibles.",
            payload={
                "hits": [{"content": "Hit 1"}, {"content": "Hit 2"}],
                "missing_information": ["surface exacte"],
            },
        )


def test_agent_chat_returns_structured_reasoning_metadata():
    skill = _FakeSkill()
    orchestrator = AgentOrchestrator(
        intent_router=_FakeIntentRouter(),
        session_manager=_FakeSessionManager(),
        store=_FakeStore(),
        memory_tool=_FakeMemoryTool(),
        llm_service=_FakeLLMService(),
        client_history_skill=skill,
        sav_planning_skill=skill,
        route_optimization_skill=skill,
        alert_management_skill=skill,
        maintenance_diagnosis_skill=skill,
        ceo_reporting_skill=skill,
        general_question_skill=skill,
        maintenance_fiche_intake_skill=skill,
    )

    response = orchestrator.handle_chat(
        AgentChatRequest(
            user_id=1,
            role="sav",
            message="Quel est le meilleur prochain passage ?",
            context={"team_id": 4},
        )
    )

    assert response.answer == "Synthese finale pour l'utilisateur."
    assert response.reasoning_signals["grounding_status"] == "grounded"
    assert response.reasoning_signals["intent"] == AgentIntent.GENERAL_QUESTION.value
    assert response.reasoning_signals["evidence_hit_count"] == 2
    assert response.reasoning_signals["proposed_action_count"] == 2
    assert response.reasoning_signals["approval_required_count"] == 1
    assert response.reasoning_signals["missing_information"] == ["surface exacte"]
    assert response.reasoning_summary is not None
    assert "approval_required=1" in response.reasoning_summary
    assert "missing_information=surface exacte" in response.reasoning_summary


class _FakeSkillWithCitableHits:
    def run(self, request: AgentChatRequest) -> SkillResult:
        return SkillResult(
            answer="Brouillon avec une fiche identifiable.",
            sources=["RAG_MAINTENANCE"],
            confidence=0.7,
            justification="Cas similaire retrouve.",
            payload={
                "hits": [
                    {
                        "fiche_id": "f1",
                        "content": "Diffuseur en panne",
                        "metadata": {"maintenance_number": "015602", "client": "Red Cattle"},
                    }
                ]
            },
        )


class _FakeLLMServiceCitingFirstSource:
    def describe_images(self, prompt, images):
        return []

    def answer_details(self, prompt, fallback_context, query="", analysis=None):
        assert "[1] client Red Cattle, fiche 015602" in prompt
        return {
            "answer": "Le diffuseur chez Red Cattle est en panne [1].",
            "response_source": "fallback",
            "model_output": None,
            "llm_error": "disabled",
        }


def test_agent_chat_returns_citations_actually_used_by_the_final_answer():
    skill = _FakeSkillWithCitableHits()
    orchestrator = AgentOrchestrator(
        intent_router=_FakeIntentRouter(),
        session_manager=_FakeSessionManager(),
        store=_FakeStore(),
        memory_tool=_FakeMemoryTool(),
        llm_service=_FakeLLMServiceCitingFirstSource(),
        client_history_skill=skill,
        sav_planning_skill=skill,
        route_optimization_skill=skill,
        alert_management_skill=skill,
        maintenance_diagnosis_skill=skill,
        ceo_reporting_skill=skill,
        general_question_skill=skill,
        maintenance_fiche_intake_skill=skill,
    )

    response = orchestrator.handle_chat(
        AgentChatRequest(user_id=1, role="sav", message="Diagnostic diffuseur Red Cattle")
    )

    assert response.answer == "Le diffuseur chez Red Cattle est en panne [1]."
    assert len(response.citations) == 1
    assert response.citations[0].index == 1
    assert response.citations[0].client == "Red Cattle"
    assert response.citations[0].maintenance_number == "015602"
