from app.agent.skills.route_optimization import RouteOptimizationSkill
from app.agent.tools.routing import RouteOptimizationTool, _nearest_neighbor, _path_cost, _two_opt
from schemas.agent_schema import AgentChatRequest


def test_nearest_neighbor_then_two_opt_finds_the_shortest_open_path():
    # index 0 is the fixed start (origin); 1, 2, 3 are stops.
    duration_matrix = [
        [0, 10, 1, 10],
        [10, 0, 10, 1],
        [1, 10, 0, 10],
        [10, 1, 10, 0],
    ]

    nearest_neighbor_order = _nearest_neighbor(duration_matrix, len(duration_matrix))
    improved_order = _two_opt(duration_matrix, nearest_neighbor_order)

    distance_matrix = duration_matrix
    improved_duration, _ = _path_cost(duration_matrix, distance_matrix, improved_order)
    naive_duration, _ = _path_cost(duration_matrix, distance_matrix, [1, 2, 3])

    assert improved_duration <= naive_duration
    assert sorted(improved_order) == [1, 2, 3]


def test_route_optimization_tool_falls_back_to_haversine_without_api_key():
    tool = RouteOptimizationTool()
    origin = {"lat": 36.8065, "lng": 10.1815}
    stops = [
        {"client_id": "far", "client_name": "Client loin", "lat": 37.0, "lng": 10.5},
        {"client_id": "near", "client_name": "Client proche", "lat": 36.81, "lng": 10.19},
    ]

    result = tool.optimize_route(origin, stops)

    assert result["traffic_aware"] is False
    assert [stop["client_id"] for stop in result["ordered_stops"]] == ["near", "far"]
    assert result["total_distance_km"] > 0
    assert result["estimated_fuel_liters"] > 0


class _FakeOperationsDataTool:
    def get_today_interventions(self):
        return {
            "interventions": [
                {
                    "client_id": "far",
                    "client_name": "Client loin",
                    "address": None,
                    "route_hint": {"lat": 37.0, "lng": 10.5},
                },
                {
                    "client_id": "near",
                    "client_name": "Client proche",
                    "address": None,
                    "route_hint": {"lat": 36.81, "lng": 10.19},
                },
            ]
        }


def test_route_optimization_skill_orders_stops_and_proposes_planning_update():
    skill = RouteOptimizationSkill(
        operations_data_tool=_FakeOperationsDataTool(),
        routing_tool=RouteOptimizationTool(),
    )
    request = AgentChatRequest(user_id=1, role="sav", message="Optimise ma tournee", context={})

    result = skill.run(request)

    assert "Client proche" in result.answer
    action = result.proposed_actions[0]
    assert action.action_type == "UPDATE_SAV_PLANNING"
    assert action.input_json["ordered_client_ids"] == ["near", "far"]
