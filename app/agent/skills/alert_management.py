from __future__ import annotations

from app.agent.skills.base import Skill
from app.agent.tools.operations_data import OperationsDataTool
from schemas.agent_schema import AgentChatRequest, ProposedAction, SkillResult


class AlertManagementSkill(Skill):
    def __init__(self, operations_data_tool: OperationsDataTool) -> None:
        self.operations_data_tool = operations_data_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        reclamations = self.operations_data_tool.get_open_reclamations()["reclamations"]
        alerts = []
        for item in reclamations:
            if item.get("age_hours", 0) > 48:
                alerts.append(f"Reclamation depassee 48h pour {item['client_name']}")
            if item.get("status") == "EN_RETARD":
                alerts.append(f"Intervention en retard pour {item['client_name']}")
            stock = self.operations_data_tool.get_client_stock(item["client_id"])
            if stock["status"] == "LOW":
                alerts.append(f"Bouteille bientot vide chez {item['client_name']}")
        if not alerts:
            alerts.append("Aucune alerte prioritaire detectee.")
        return SkillResult(
            answer=" ; ".join(alerts[:4]),
            proposed_actions=[
                ProposedAction(
                    action_type="CREATE_LOW_RISK_ALERT",
                    input_json={"alert_count": len(alerts)},
                    output_json={"top_alert": alerts[0]},
                )
            ],
            sources=["OPERATIONS_ALERTS", "CLIENT_STOCK"],
            confidence=0.78,
            justification="Les alertes proviennent des retards, reclamations ouvertes et niveaux de stock.",
            payload={"alerts": alerts},
        )
