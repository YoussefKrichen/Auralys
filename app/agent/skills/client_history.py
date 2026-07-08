from __future__ import annotations

from app.agent.core.intent_router import IntentRouter
from app.agent.skills.base import Skill
from app.agent.tools.operations_data import OperationsDataTool
from app.agent.tools.rag import RAGTool
from schemas.agent_schema import AgentChatRequest, ProposedAction, SkillResult


class ClientHistorySkill(Skill):
    def __init__(self, operations_data_tool: OperationsDataTool, rag_tool: RAGTool) -> None:
        self.operations_data_tool = operations_data_tool
        self.rag_tool = rag_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        client_name = request.context.get("client_name") or IntentRouter.extract_client_name(request.message) or request.message
        client = self.operations_data_tool.get_client_by_name(client_name)
        history = self.operations_data_tool.get_client_history(client["client_id"])["history"]
        interventions = self.operations_data_tool.get_client_interventions(client["client_id"])["interventions"]
        reclamations = self.operations_data_tool.get_client_reclamations(client["client_id"])["reclamations"]
        documents = self.rag_tool.search_client_documents(client["client_name"], limit=3)["hits"]
        latest = history[0] if history else None
        confidence = self._compute_confidence(
            history=history,
            documents=documents,
            reclamations=reclamations,
        )
        answer = (
            f"Historique client pour {client['client_name']} : {len(interventions)} intervention(s) connue(s). "
            f"Derniere visite {latest.get('service_date') if latest else 'indisponible'}."
        )
        if reclamations:
            answer += f" Reclamation principale : {reclamations[0].get('issue')}."
        return SkillResult(
            answer=answer,
            proposed_actions=[
                ProposedAction(
                    action_type="SEARCH_CLIENT_HISTORY",
                    input_json={"client_id": client["client_id"]},
                    output_json={"document_count": len(documents)},
                )
            ],
            sources=["OPERATIONS_CLIENT_HISTORY", "RAG_CLIENT_DOCUMENTS"],
            confidence=confidence,
            justification="Historique reconstruit a partir des interventions et des documents client.",
            payload={
                "client": client,
                "history": history[:5],
                "documents": documents,
            },
        )

    @staticmethod
    def _compute_confidence(
        *,
        history: list[dict],
        documents: list[dict],
        reclamations: list[dict],
    ) -> float:
        history_coverage = min(len(history), 5) / 5
        document_coverage = min(len(documents), 3) / 3
        reclamation_signal = 1.0 if reclamations else 0.0

        confidence = (
            0.35
            + (0.35 * history_coverage)
            + (0.20 * document_coverage)
            + (0.10 * reclamation_signal)
        )
        return round(min(confidence, 0.95), 2)
