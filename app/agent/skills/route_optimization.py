from __future__ import annotations

from app.agent.skills.base import Skill
from app.agent.tools.operations_data import OperationsDataTool
from app.agent.tools.routing import RouteOptimizationTool
from schemas.agent_schema import AgentChatRequest, ProposedAction, SkillResult

DEFAULT_ORIGIN = {
    "address": "AROM AIR, La Soukra, Ariana, Tunisia",
    "lat": 36.8065,
    "lng": 10.1815,
}


class RouteOptimizationSkill(Skill):
    def __init__(self, operations_data_tool: OperationsDataTool, routing_tool: RouteOptimizationTool) -> None:
        self.operations_data_tool = operations_data_tool
        self.routing_tool = routing_tool

    def run(self, request: AgentChatRequest) -> SkillResult:
        team_id = int(request.context.get("team_id") or 0)
        origin = request.context.get("current_location") or DEFAULT_ORIGIN
        planning = request.context.get("planning")
        interventions = (
            planning
            if planning
            else (
                self.operations_data_tool.get_interventions_by_team(team_id)["interventions"]
                if team_id
                else self.operations_data_tool.get_today_interventions()["interventions"]
            )
        )
        stops = self._to_stops(interventions)
        if not stops:
            return SkillResult(
                answer="Aucune visite planifiee n'a ete trouvee pour optimiser la tournee.",
                sources=["OPERATIONS_INTERVENTIONS"],
                confidence=0.3,
                justification="Le planning source ne contient aucune destination exploitable.",
            )

        result = self.routing_tool.optimize_route(origin, stops)
        answer = self._build_answer(result)
        return SkillResult(
            answer=answer,
            proposed_actions=[
                ProposedAction(
                    action_type="UPDATE_SAV_PLANNING",
                    input_json={
                        "team_id": team_id,
                        "ordered_client_ids": [stop["client_id"] for stop in result["ordered_stops"]],
                    },
                    output_json={
                        "total_duration_minutes": result["total_duration_minutes"],
                        "total_distance_km": result["total_distance_km"],
                        "estimated_fuel_liters": result["estimated_fuel_liters"],
                    },
                ),
            ],
            sources=["OPERATIONS_INTERVENTIONS", "GOOGLE_ROUTES_TRAFFIC", "FUEL_ESTIMATE"],
            confidence=0.85 if result["traffic_aware"] else 0.6,
            justification=(
                "Ordre calcule par optimisation de tournee (plus proche voisin + amelioration 2-opt) "
                "sur la duree de trajet avec trafic, afin de reduire le temps perdu et la consommation de carburant."
            ),
            payload={"route_optimization": result},
        )

    @staticmethod
    def _to_stops(interventions: list[dict]) -> list[dict]:
        stops = []
        for item in interventions:
            route_hint = item.get("route_hint") or {}
            stops.append(
                {
                    "client_id": item["client_id"],
                    "client_name": item["client_name"],
                    "address": item.get("address"),
                    "lat": route_hint.get("lat"),
                    "lng": route_hint.get("lng"),
                }
            )
        return stops

    @staticmethod
    def _build_answer(result: dict) -> str:
        order_names = ", ".join(stop["client_name"] for stop in result["ordered_stops"])
        traffic_note = (
            "en tenant compte du trafic en temps reel"
            if result["traffic_aware"]
            else "sur la base de distances estimees (trafic en temps reel indisponible)"
        )
        return (
            f"Voici l'ordre de tournee optimise {traffic_note} : {order_names}. "
            f"Duree totale estimee : {result['total_duration_minutes']} min, "
            f"distance totale : {result['total_distance_km']} km, "
            f"carburant estime : {result['estimated_fuel_liters']} L. "
            f"Gain par rapport a l'ordre initial : {result['time_saved_minutes']} min "
            f"et {result['fuel_saved_liters']} L de carburant."
        )
