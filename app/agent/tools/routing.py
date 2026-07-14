from __future__ import annotations

import json
import logging
from typing import Any
from urllib import error, parse, request

from app.agent.store import AgentStore
from app.agent.tools.base import LoggedTool
from app.agent.tools.maps import _haversine
from app.config import settings

logger = logging.getLogger(__name__)


class RouteOptimizationTool(LoggedTool):
    def __init__(self, store: AgentStore | None = None) -> None:
        super().__init__(store=store)

    def optimize_route(self, origin: dict[str, Any], stops: list[dict[str, Any]]) -> dict[str, Any]:
        return self._run_logged(
            "optimize_route",
            {"origin": origin, "stops": stops},
            lambda: self._optimize(origin, stops),
        )

    def _optimize(self, origin: dict[str, Any], stops: list[dict[str, Any]]) -> dict[str, Any]:
        if not stops:
            return _empty_result()

        locations = [origin, *stops]
        duration_matrix, distance_matrix, traffic_aware = self._build_matrices(locations)

        baseline_order = list(range(1, len(locations)))
        baseline_duration, baseline_distance = _path_cost(duration_matrix, distance_matrix, baseline_order)

        best_order = _two_opt(duration_matrix, _nearest_neighbor(duration_matrix, len(locations)))
        best_duration, best_distance = _path_cost(duration_matrix, distance_matrix, best_order)

        consumption_rate = settings.vehicle_fuel_consumption_l_per_100km
        fuel_liters = best_distance * consumption_rate / 100.0
        baseline_fuel_liters = baseline_distance * consumption_rate / 100.0

        ordered_stops = []
        previous = 0
        for index in best_order:
            ordered_stops.append(
                {
                    **stops[index - 1],
                    "leg_distance_km": round(distance_matrix[previous][index], 2),
                    "leg_duration_minutes": round(duration_matrix[previous][index], 1),
                }
            )
            previous = index

        return {
            "ordered_stops": ordered_stops,
            "total_distance_km": round(best_distance, 2),
            "total_duration_minutes": round(best_duration, 1),
            "estimated_fuel_liters": round(fuel_liters, 2),
            "baseline_distance_km": round(baseline_distance, 2),
            "baseline_duration_minutes": round(baseline_duration, 1),
            "baseline_fuel_liters": round(baseline_fuel_liters, 2),
            "distance_saved_km": round(baseline_distance - best_distance, 2),
            "time_saved_minutes": round(baseline_duration - best_duration, 1),
            "fuel_saved_liters": round(baseline_fuel_liters - fuel_liters, 2),
            "traffic_aware": traffic_aware,
        }

    def _build_matrices(
        self, locations: list[dict[str, Any]]
    ) -> tuple[list[list[float]], list[list[float]], bool]:
        if settings.google_routes_api_key:
            try:
                duration_matrix, distance_matrix = _fetch_traffic_matrices(locations)
                return duration_matrix, distance_matrix, True
            except Exception:
                logger.exception("Google Distance Matrix call failed, falling back to haversine estimate.")
        return (*_haversine_matrices(locations), False)


def _empty_result() -> dict[str, Any]:
    return {
        "ordered_stops": [],
        "total_distance_km": 0.0,
        "total_duration_minutes": 0.0,
        "estimated_fuel_liters": 0.0,
        "baseline_distance_km": 0.0,
        "baseline_duration_minutes": 0.0,
        "baseline_fuel_liters": 0.0,
        "distance_saved_km": 0.0,
        "time_saved_minutes": 0.0,
        "fuel_saved_liters": 0.0,
        "traffic_aware": False,
    }


def _location_query(location: dict[str, Any]) -> str:
    address = location.get("address")
    if address:
        return str(address)
    lat, lng = location.get("lat"), location.get("lng")
    if lat is not None and lng is not None:
        return f"{lat},{lng}"
    raise ValueError(f"Location missing 'address' or 'lat'/'lng': {location!r}")


def _fetch_traffic_matrices(
    locations: list[dict[str, Any]]
) -> tuple[list[list[float]], list[list[float]]]:
    joined = "|".join(_location_query(location) for location in locations)
    query = parse.urlencode(
        {
            "origins": joined,
            "destinations": joined,
            "mode": "driving",
            "departure_time": "now",
            "traffic_model": "best_guess",
            "key": settings.google_routes_api_key,
        }
    )
    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?{query}"
    req = request.Request(url=url, headers={"User-Agent": "Auralys/1.0"}, method="GET")
    try:
        with request.urlopen(req, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError(f"Google Distance Matrix request failed with status {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Google Distance Matrix request failed: {exc.reason}") from exc

    if body.get("status") != "OK":
        raise RuntimeError(f"Google Distance Matrix status: {body.get('status')}")

    n = len(locations)
    duration_matrix = [[0.0] * n for _ in range(n)]
    distance_matrix = [[0.0] * n for _ in range(n)]
    for i, row in enumerate(body.get("rows", [])):
        for j, element in enumerate(row.get("elements", [])):
            if i == j:
                continue
            if element.get("status") != "OK":
                raise RuntimeError(f"Google Distance Matrix element failed for pair ({i},{j}): {element.get('status')}")
            duration_seconds = (element.get("duration_in_traffic") or element["duration"])["value"]
            distance_meters = element["distance"]["value"]
            duration_matrix[i][j] = duration_seconds / 60.0
            distance_matrix[i][j] = distance_meters / 1000.0
    return duration_matrix, distance_matrix


def _haversine_matrices(locations: list[dict[str, Any]]) -> tuple[list[list[float]], list[list[float]]]:
    n = len(locations)
    average_speed_kmh = 30.0
    duration_matrix = [[0.0] * n for _ in range(n)]
    distance_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            distance_km = _haversine(locations[i]["lat"], locations[i]["lng"], locations[j]["lat"], locations[j]["lng"])
            distance_matrix[i][j] = distance_km
            duration_matrix[i][j] = (distance_km / average_speed_kmh) * 60.0
    return duration_matrix, distance_matrix


def _nearest_neighbor(duration_matrix: list[list[float]], n: int) -> list[int]:
    visited = {0}
    order: list[int] = []
    current = 0
    for _ in range(n - 1):
        candidates = [i for i in range(1, n) if i not in visited]
        next_index = min(candidates, key=lambda i: duration_matrix[current][i])
        order.append(next_index)
        visited.add(next_index)
        current = next_index
    return order


def _order_duration(duration_matrix: list[list[float]], order: list[int]) -> float:
    total = 0.0
    previous = 0
    for index in order:
        total += duration_matrix[previous][index]
        previous = index
    return total


def _two_opt(duration_matrix: list[list[float]], order: list[int]) -> list[int]:
    best = list(order)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + list(reversed(best[i : j + 1])) + best[j + 1 :]
                if _order_duration(duration_matrix, candidate) < _order_duration(duration_matrix, best) - 1e-9:
                    best = candidate
                    improved = True
    return best


def _path_cost(
    duration_matrix: list[list[float]],
    distance_matrix: list[list[float]],
    order: list[int],
) -> tuple[float, float]:
    total_duration = 0.0
    total_distance = 0.0
    previous = 0
    for index in order:
        total_duration += duration_matrix[previous][index]
        total_distance += distance_matrix[previous][index]
        previous = index
    return total_duration, total_distance
