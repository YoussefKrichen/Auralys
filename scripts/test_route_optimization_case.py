"""Cas de test manuel pour l'agent d'optimisation de tournee (ASK_ROUTE_OPTIMIZATION).

Usage: python scripts/test_route_optimization_case.py
"""
from app.agent.skills.route_optimization import RouteOptimizationSkill
from app.agent.tools.routing import RouteOptimizationTool
from schemas.agent_schema import AgentChatRequest


class _NoOpOperationsDataTool:
    def get_today_interventions(self):
        return {"interventions": []}

    def get_interventions_by_team(self, team_id):
        return {"interventions": []}


def main() -> None:
    skill = RouteOptimizationSkill(
        operations_data_tool=_NoOpOperationsDataTool(),
        routing_tool=RouteOptimizationTool(),
    )

    request = AgentChatRequest(
        user_id=1,
        role="sav",
        message="Optimise la tournee de l'equipe SAV pour eviter les embouteillages",
        context={
            "current_location": {
                "address": "AROM AIR, La Soukra, Ariana, Tunisia",
                "lat": 36.8665,
                "lng": 10.2405,
            },
            "planning": [
                {
                    "client_id": "jardin-carthage",
                    "client_name": "Jardin Carthage",
                    "address": "Jardin Carthage, Tunis, Tunisia",
                    "route_hint": {"lat": 36.8520, "lng": 10.3230},
                },
                {
                    "client_id": "ennasr",
                    "client_name": "Ennasr",
                    "address": "Ennasr, Tunis, Tunisia",
                    "route_hint": {"lat": 36.8390, "lng": 10.1720},
                },
                {
                    "client_id": "menzah8",
                    "client_name": "Menzah 8",
                    "address": "Menzah8, Tunis, Tunisia",
                    "route_hint": {"lat": 36.8390, "lng": 10.1650},
                },
                {
                    "client_id": "borj-louzir",
                    "client_name": "Borj Louzir",
                    "address": "Borj Louzir, Tunis, Tunisia",
                    "route_hint": {"lat": 36.8580, "lng": 10.1850},
                },
                {
                    "client_id": "omrane",
                    "client_name": "Omrane",
                    "address": "Omrane, Tunis, Tunisia",
                    "route_hint": {"lat": 36.8230, "lng": 10.1550},
                },
            ],
        },
    )

    result = skill.run(request)
    print("REPONSE:\n", result.answer)
    print("\nACTION PROPOSEE:", result.proposed_actions[0].input_json)
    print("\nDETAIL:", result.payload["route_optimization"])


if __name__ == "__main__":
    main()
