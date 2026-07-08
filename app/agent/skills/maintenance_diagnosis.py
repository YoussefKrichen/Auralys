from __future__ import annotations

from app.agent.core.intent_router import IntentRouter
from app.agent.skills.base import Skill
from app.agent.tools.operations_data import OperationsDataTool
from app.agent.tools.rag import RAGTool
from schemas.agent_schema import AgentChatRequest, ProposedAction, SkillResult


class MaintenanceDiagnosisSkill(Skill):
    def __init__(self, operations_data_tool: OperationsDataTool, rag_tool: RAGTool) -> None:
        self.operations_data_tool = operations_data_tool
        self.rag_tool = rag_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        client_name = request.context.get("client_name") or IntentRouter.extract_client_name(request.message)
        client = self.operations_data_tool.get_client_by_name(client_name) if client_name else None
        similar_cases = self.rag_tool.search_similar_cases(request.message, limit=3)["hits"]
        diffusers = self.operations_data_tool.get_client_diffusers(client["client_id"])["diffusers"] if client else []
        last_intervention = self.operations_data_tool.get_last_intervention(client["client_id"])["intervention"] if client else None
        if similar_cases:
            top = similar_cases[0]
            answer = f"Cas similaire trouve : {top['content'][:220].strip()}"
        else:
            answer = "Aucun cas similaire convaincant n'a ete retrouve dans les fiches de maintenance."
        if last_intervention and last_intervention.get("recommendation"):
            answer += f" Derniere recommandation connue : {last_intervention['recommendation']}."
        return SkillResult(
            answer=answer,
            proposed_actions=[
                ProposedAction(
                    action_type="SUMMARIZE_MAINTENANCE",
                    input_json={"client_id": client["client_id"] if client else None},
                    output_json={"similar_case_count": len(similar_cases), "diffuser_count": len(diffusers)},
                )
            ],
            sources=["RAG_SIMILAR_CASES", "OPERATIONS_LAST_INTERVENTION"],
            confidence=0.74 if similar_cases else 0.42,
            justification="Le diagnostic s'appuie sur des cas similaires et sur la derniere intervention connue.",
            payload={"similar_cases": similar_cases, "diffusers": diffusers},
        )
