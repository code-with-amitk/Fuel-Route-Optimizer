"""
Fuel stop selection along a driving route.

Given a route polyline and total distance, this module finds truck stops from
the local FuelStation table and picks refuel points using a greedy strategy:

  1. Look at the next MAX_RANGE_MILES (500) window along the route.
  2. Among stations near the road in that window, pick the cheapest price.
  3. Move forward to that stop and repeat until the destination is in range.

No external API calls — only SQLite + route_geometry helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fuel_optimizer.models import FuelStation
from fuel_optimizer.services.route_geometry import (
    build_cumulative_distances,
    project_point_to_route,
    route_bounding_box,
)

# Vehicle / search tuning (see architecture.md Section 6).
MAX_RANGE_MILES = 500       # max miles between refuels
CORRIDOR_MILES = 25.0       # max distance a station may sit from the polyline
MIN_ADVANCE_MILES = 0.1     # optimizer must move forward each iteration


class FuelOptimizerError(Exception):
    """Raised when fuel stops cannot be planned for a route."""


@dataclass(frozen=True)
class FuelStopPlan:
    """One chosen refuel point tied to its position along the route."""

    station: FuelStation
    distance_from_start_miles: float
    distance_to_route_miles: float


def find_stations_in_corridor(
    coordinates: list[list[float]],
    cumulative_distances: list[float],
    start_mile: float,
    end_mile: float,
    *,
    corridor_miles: float = CORRIDOR_MILES,
) -> list[FuelStopPlan]:
    """
    Return stations near the route between `start_mile` and `end_mile`.

    Two-stage filter:
      1. DB bounding-box query (fast, indexed) — rough cut.
      2. Project each row onto the polyline — keep only stations within
         corridor_miles of the road and whose mile marker lies in the window.
    """
    min_lat, max_lat, min_lon, max_lon = route_bounding_box(
        coordinates,
        cumulative_distances,
        start_mile,
        end_mile,
        corridor_miles,
    )

    candidates: list[FuelStopPlan] = []
    queryset = FuelStation.objects.filter(
        latitude__gte=min_lat,
        latitude__lte=max_lat,
        longitude__gte=min_lon,
        longitude__lte=max_lon,
    )

    for station in queryset:
        projection = project_point_to_route(
            station.latitude,
            station.longitude,
            coordinates,
            cumulative_distances,
        )
        if projection.distance_to_route_miles > corridor_miles:
            continue
        if projection.distance_along_route_miles < start_mile:
            continue
        if projection.distance_along_route_miles > end_mile:
            continue

        candidates.append(
            FuelStopPlan(
                station=station,
                distance_from_start_miles=projection.distance_along_route_miles,
                distance_to_route_miles=projection.distance_to_route_miles,
            )
        )

    return candidates


def select_cheapest_station(candidates: list[FuelStopPlan]) -> FuelStopPlan:
    """Primary key: lowest retail_price; tie-break: closer to route, then earlier mile."""
    return min(
        candidates,
        key=lambda candidate: (
            candidate.station.retail_price,
            candidate.distance_to_route_miles,
            candidate.distance_from_start_miles,
        ),
    )


def optimize_fuel_stops(
    route_geometry: dict[str, Any],
    total_distance_miles: float,
    *,
    max_range_miles: float = MAX_RANGE_MILES,
    corridor_miles: float = CORRIDOR_MILES,
) -> list[FuelStopPlan]:
    """
    Greedy fuel stop planner: within each range window pick the cheapest station.

    Stops when the remaining distance to the destination is within vehicle range
    (no refuel needed for the final leg). Raises FuelOptimizerError if a required
    window has no eligible stations.
    """
    coordinates = route_geometry.get("coordinates") or []
    if len(coordinates) < 2:
        raise FuelOptimizerError("Route geometry must contain at least two points")

    cumulative_distances = build_cumulative_distances(coordinates)
    current_position = 0.0
    fuel_stops: list[FuelStopPlan] = []
    selected_station_ids: set[int] = set()

    while current_position < total_distance_miles:
        remaining = total_distance_miles - current_position
        if remaining <= max_range_miles:
            # Departure tank (or last fill) covers the rest of the trip.
            break

        window_end = current_position + max_range_miles
        candidates = find_stations_in_corridor(
            coordinates,
            cumulative_distances,
            current_position,
            window_end,
            corridor_miles=corridor_miles,
        )
        # Prevent picking the same stop twice or failing to advance along the route.
        candidates = [
            candidate
            for candidate in candidates
            if candidate.station.pk not in selected_station_ids
            and candidate.distance_from_start_miles
            > current_position + MIN_ADVANCE_MILES
        ]
        if not candidates:
            raise FuelOptimizerError(
                f"No fuel stations found within {corridor_miles:.0f} miles of route "
                f"between mile {current_position:.1f} and {window_end:.1f}"
            )

        best = select_cheapest_station(candidates)
        fuel_stops.append(best)
        selected_station_ids.add(best.station.pk)
        current_position = best.distance_from_start_miles

    return fuel_stops
