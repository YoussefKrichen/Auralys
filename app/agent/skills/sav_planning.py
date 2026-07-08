from __future__ import annotations

from app.agent.skills.base import Skill
from app.agent.tools.maps import MapsTool
from app.agent.tools.operations_data import OperationsDataTool
from schemas.agent_schema import AgentChatRequest, ProposedAction, SkillResult


class SAVPlanningSkill(Skill):
    def __init__(self, operations_data_tool: OperationsDataTool, maps_tool: MapsTool) -> None:
        self.operations_data_tool = operations_data_tool
        self.maps_tool = maps_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        team_id = int(request.context.get("team_id") or 0)
        origin = request.context.get("current_location") or {"lat": 36.8065, "lng": 10.1815}
        interventions = (
            self.operations_data_tool.get_interventions_by_team(team_id)["interventions"]
            if team_id
            else self.operations_data_tool.get_today_interventions()["interventions"]
        )
        ranked = self.rank_destinations(interventions=interventions, origin=origin)
        if not ranked:
            return SkillResult(
                answer="Aucune intervention exploitable n'a ete trouvee pour le planning SAV.",
                sources=["OPERATIONS_INTERVENTIONS"],
                confidence=0.3,
                justification="Le planning source ne contient pas de destination exploitable.",
            )
        best = ranked[0]
        answer = (
            f"Je recommande d'envoyer l'equipe SAV chez {best['client_name']}. "
            f"Score {best['score']} avec un trajet estime a {best['route_duration_minutes']} minutes."
        )
        return SkillResult(
            answer=answer,
            proposed_actions=[
                ProposedAction(
                    action_type="RECOMMEND_ROUTE",
                    input_json={"team_id": team_id, "client_id": best["client_id"]},
                    output_json={"score": best["score"]},
                ),
                ProposedAction(
                    action_type="UPDATE_SAV_PLANNING",
                    input_json={"team_id": team_id, "recommended_client_id": best["client_id"]},
                    output_json={"route_duration_minutes": best["route_duration_minutes"]},
                ),
            ],
            sources=["OPERATIONS_INTERVENTIONS", "GOOGLE_ROUTES", "CLIENT_PRIORITY"],
            confidence=min(0.95, 0.55 + (best["score"] / 120.0)),
            justification="Classement fonde sur urgence, priorite client, retard et duree de trajet.",
            payload={"ranked_destinations": ranked},
        )

    def rank_destinations(
        self,
        *,
        interventions: list[dict],
        origin: dict[str, float],
    ) -> list[dict]:
        ranked = []
        matrix = self.maps_tool.calculate_route_matrix(
            origin,
            [
                {
                    "destination_id": item["client_id"],
                    "client_name": item["client_name"],
                    "location": item["route_hint"],
                }
                for item in interventions
            ],
        )["routes"]
        route_by_client = {route["destination_id"]: route for route in matrix}
        for intervention in interventions:
            client_id = intervention["client_id"]
            priority = self.operations_data_tool.get_client_priority(client_id)["priority"]
            opening = self.operations_data_tool.get_opening_hours(client_id)
            route = route_by_client[client_id]
            score = compute_sav_score(
                urgency=intervention.get("urgency") or "MEDIUM",
                client_importance=priority,
                route_duration_minutes=route["duration_minutes"],
                intervention_status=intervention.get("status") or "PLANIFIE",
                closing_soon=bool(opening["closing_soon"]),
            )
            ranked.append(
                {
                    **intervention,
                    "client_importance": priority,
                    "closing_soon": opening["closing_soon"],
                    "route_duration_minutes": route["duration_minutes"],
                    "distance_km": route["distance_km"],
                    "score": score,
                }
            )
        ranked.sort(key=lambda item: (item["score"], -item["route_duration_minutes"]), reverse=True)
        return ranked


def compute_sav_score(
    *,
    urgency: str,
    client_importance: str,
    route_duration_minutes: float,
    intervention_status: str,
    closing_soon: bool,
) -> int:
    score = 0
    if urgency == "HIGH":
        score += 40
    if client_importance == "IMPORTANT":
        score += 25
    if route_duration_minutes <= 20:
        score += 20
    elif route_duration_minutes <= 40:
        score += 10
    if intervention_status == "EN_RETARD":
        score += 15
    if closing_soon:
        score += 20
    return score
