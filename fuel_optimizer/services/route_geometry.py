"""
Polyline distance helpers for route-based fuel optimization.

ORS returns a driving route as a GeoJSON LineString: an ordered list of
[longitude, latitude] points. These helpers turn that polyline into mile
markers along the route and measure how far a fuel station sits from the road.

Used by fuel_optimizer.py to answer:
  - "At what mile marker along the route is this truck stop?"
  - "How far off the highway is it?"
  - "Which DB rows are worth checking for a given route segment?"
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Great-circle distance in miles between two lat/lng points."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    # Haversine formula on a sphere; asin argument is clamped to avoid float drift.
    central_angle = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(central_angle)))


def build_cumulative_distances(coordinates: list[list[float]]) -> list[float]:
    """
    Build cumulative distance in miles along a GeoJSON LineString.

    Returns one value per coordinate: cumulative[i] = miles from the route
    start to coordinates[i]. Index 0 is always 0.0.

    `coordinates` are `[longitude, latitude]` pairs (GeoJSON order).
    """
    if not coordinates:
        return [0.0]

    cumulative = [0.0]
    for index in range(1, len(coordinates)):
        lon1, lat1 = coordinates[index - 1]
        lon2, lat2 = coordinates[index]
        cumulative.append(
            cumulative[-1] + haversine_miles(lat1, lon1, lat2, lon2)
        )
    return cumulative


@dataclass(frozen=True)
class RouteProjection:
    """Where a point lands when dropped onto the nearest spot on the route."""

    distance_along_route_miles: float  # mile marker from route start
    distance_to_route_miles: float     # perpendicular-ish distance off the road
    segment_index: int                 # polyline segment that won the projection


def project_point_to_route(
    latitude: float,
    longitude: float,
    coordinates: list[list[float]],
    cumulative_distances: list[float],
) -> RouteProjection:
    """
    Project a fuel-station location onto the nearest point on the route.

    Each polyline segment is checked; the closest projection wins. That gives
    the station's logical position "along" the trip even if it sits beside I-90.
    """
    if len(coordinates) < 2:
        raise ValueError("Route must contain at least two coordinates")

    best_distance_to_route = float("inf")
    best_along_route = 0.0
    best_segment = 0

    for index in range(len(coordinates) - 1):
        lon1, lat1 = coordinates[index]
        lon2, lat2 = coordinates[index + 1]
        segment_length = cumulative_distances[index + 1] - cumulative_distances[index]

        if segment_length == 0:
            # Degenerate segment: treat as a single point.
            along_route = cumulative_distances[index]
            distance_to_route = haversine_miles(latitude, longitude, lat1, lon1)
        else:
            fraction, proj_lat, proj_lon = _closest_point_on_segment(
                latitude,
                longitude,
                lat1,
                lon1,
                lat2,
                lon2,
            )
            along_route = cumulative_distances[index] + (segment_length * fraction)
            distance_to_route = haversine_miles(
                latitude,
                longitude,
                proj_lat,
                proj_lon,
            )

        if distance_to_route < best_distance_to_route:
            best_distance_to_route = distance_to_route
            best_along_route = along_route
            best_segment = index

    return RouteProjection(
        distance_along_route_miles=best_along_route,
        distance_to_route_miles=best_distance_to_route,
        segment_index=best_segment,
    )


def _closest_point_on_segment(
    point_lat: float,
    point_lon: float,
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> tuple[float, float, float]:
    """
    Closest point on a segment to an arbitrary lat/lng.

    Uses a local flat-plane approximation (longitude scaled by cos(lat)) which
    is accurate enough for corridor matching over typical US route segments.
    Returns (fraction_along_segment, projected_lat, projected_lon) with
    fraction clamped to [0, 1].
    """
    # Scale longitude so east/west distance is comparable to north/south at this latitude.
    lat_scale = math.cos(math.radians((lat1 + lat2 + point_lat) / 3))

    ax, ay = 0.0, 0.0
    bx = (lon2 - lon1) * lat_scale
    by = lat2 - lat1
    px = (point_lon - lon1) * lat_scale
    py = point_lat - lat1

    segment_length_sq = (bx * bx) + (by * by)
    if segment_length_sq == 0:
        return 0.0, lat1, lon1

    # Standard vector projection: t = dot(AP, AB) / |AB|^2
    fraction = max(0.0, min(1.0, ((px * bx) + (py * by)) / segment_length_sq))
    proj_lat = lat1 + (by * fraction)
    proj_lon = lon1 + ((bx * fraction) / lat_scale)
    return fraction, proj_lat, proj_lon


def route_bounding_box(
    coordinates: list[list[float]],
    cumulative_distances: list[float],
    start_mile: float,
    end_mile: float,
    buffer_miles: float,
) -> tuple[float, float, float, float]:
    """
    Lat/lng bounds for a slice of the route, padded by `buffer_miles`.

    Cheap pre-filter before hitting the DB: any station outside this box
    cannot be within the corridor of the [start_mile, end_mile] interval.
    Returns (min_lat, max_lat, min_lon, max_lon).
    """
    min_lat = float("inf")
    max_lat = float("-inf")
    min_lon = float("inf")
    max_lon = float("-inf")

    for index in range(len(coordinates) - 1):
        segment_start = cumulative_distances[index]
        segment_end = cumulative_distances[index + 1]
        if segment_end < start_mile or segment_start > end_mile:
            continue

        lon, lat = coordinates[index]
        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)
        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)

        lon, lat = coordinates[index + 1]
        min_lat = min(min_lat, lat)
        max_lat = max(max_lat, lat)
        min_lon = min(min_lon, lon)
        max_lon = max(max_lon, lon)

    if min_lat == float("inf"):
        min_lat = max_lat = coordinates[0][1]
        min_lon = max_lon = coordinates[0][0]

    # ~69 miles per degree of latitude; longitude degree shrinks by cos(lat).
    lat_buffer = buffer_miles / 69.0
    lon_buffer = buffer_miles / max(
        1.0,
        69.0 * math.cos(math.radians((min_lat + max_lat) / 2)),
    )
    return (
        min_lat - lat_buffer,
        max_lat + lat_buffer,
        min_lon - lon_buffer,
        max_lon + lon_buffer,
    )
