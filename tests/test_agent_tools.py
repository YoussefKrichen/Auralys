from app.agent.tools.maps import MapsTool
from app.agent.tools.operations_data import OperationsDataTool


def test_maps_tool_calculates_positive_route():
    tool = MapsTool()

    route = tool.calculate_route(
        {"lat": 36.8065, "lng": 10.1815},
        {"lat": 36.85, "lng": 10.22},
    )

    assert route["distance_km"] > 0
    assert route["duration_minutes"] > 0


def test_operations_data_tool_can_find_known_fixture_client():
    tool = OperationsDataTool()

    client = tool.get_client_by_name("Pharmacie Victoria")

    assert "Pharmacie Victoria" in client["client_name"]
    assert client["client_id"].startswith("pharmacie-victoria")
