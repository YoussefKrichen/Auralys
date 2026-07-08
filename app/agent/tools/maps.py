from __future__ import annotations

import math
from typing import Any

from app.agent.store import AgentStore
from app.agent.tools.base import LoggedTool


class MapsTool(LoggedTool):
    def __init__(self, store: AgentStore | None = None) -> None:
        super().__init__(store=store)

    def calculate_route(self, origin: dict[str, float], destination: dict[str, float]) -> dict[str, Any]:
        return self._run_logged(
            "calculate_route",
            {"origin": origin, "destination": destination},
            lambda: self._calculate(origin, destination),
        )

    def calculate_route_matrix(
        self,
        origin: dict[str, float],
        destinations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        def _build() -> dict[str, Any]:
            routes = []
            for destination in destinations:
                route = self._calculate(origin, destination["location"])
                routes.append(
                    {
                        "destination_id": destination["destination_id"],
                        "client_name": destination.get("client_name"),
                        **route,
                    }
                )
            return {"routes": routes}

        return self._run_logged(
            "calculate_route_matrix",
            {"origin": origin, "destinations": destinations},
            _build,
        )

    @staticmethod
    def _calculate(origin: dict[str, float], destination: dict[str, float]) -> dict[str, Any]:
        distance_km = _haversine(
            origin["lat"],
            origin["lng"],
            destination["lat"],
            destination["lng"],
        )
        duration_minutes = round((distance_km / 30.0) * 60.0 + 5.0, 1)
        return {
            "distance_km": round(distance_km, 2),
            "duration_minutes": duration_minutes,
        }


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c

