from __future__ import annotations

from app.agent.skills.base import Skill
from app.agent.tools.operations_data import OperationsDataTool
from schemas.agent_schema import AgentChatRequest, ProposedAction, SkillResult


class CEOReportingSkill(Skill):
    def __init__(self, operations_data_tool: OperationsDataTool) -> None:
        self.operations_data_tool = operations_data_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        interventions = self.operations_data_tool.get_today_interventions()["interventions"]
        reclamations = self.operations_data_tool.get_open_reclamations()["reclamations"]
        risky_clients = [item["client_name"] for item in reclamations if item.get("status") == "EN_RETARD"]
        answer = (
            f"Rapport SAV: {len(interventions)} intervention(s) dans le planning de reference, "
            f"{len(reclamations)} alerte(s) ouverte(s), clients a risque: {', '.join(risky_clients[:3]) or 'aucun'}."
        )
        return SkillResult(
            answer=answer,
            proposed_actions=[
                ProposedAction(
                    action_type="GENERATE_REPORT_DRAFT",
                    input_json={"requested_by_role": request.role},
                    output_json={"interventions": len(interventions), "alerts": len(reclamations)},
                )
            ],
            sources=["OPERATIONS_INTERVENTIONS", "OPERATIONS_ALERTS"],
            confidence=0.8,
            justification="Le rapport compile le planning SAV et les alertes ouvertes.",
            payload={"interventions": interventions, "reclamations": reclamations},
        )
