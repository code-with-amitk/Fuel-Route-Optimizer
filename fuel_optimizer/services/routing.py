"""OpenRouteService directions client (driving route + GeoJSON geometry)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

from fuel_optimizer.services.geocoding import is_within_usa

"""
HTTP GET https://api.openrouteservice.org/v2/directions/driving-car?
            api_key==<API_KEY>&start=longitude,latitude&end=longitude,latitude

Response:
200 OK GeoJSON
"""
ORS_DIRECTIONS_URL = (
    "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
)
METERS_TO_MILES = 0.000621371


class RoutingError(Exception):
    """Raised when a driving route cannot be fetched."""


@dataclass(frozen=True)
class RouteCoordinate:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class RouteResult:
    geometry: dict[str, Any]
    route_feature: dict[str, Any]
    distance_meters: float
    duration_seconds: float

    @property
    def distance_miles(self) -> float:
        return self.distance_meters * METERS_TO_MILES


def validate_route_coordinates(
    start: RouteCoordinate,
    finish: RouteCoordinate,
) -> None:
    for label, coord in (("start", start), ("finish", finish)):
        if not is_within_usa(coord.latitude, coord.longitude):
            raise RoutingError(
                f"{label} coordinates ({coord.latitude}, {coord.longitude}) "
                "are outside USA bounds"
            )


def get_route(
    start: RouteCoordinate,
    finish: RouteCoordinate,
    *,
    api_key: str | None = None,
    timeout: int = 15,
) -> RouteResult:
    """
    Fetch a full driving route between two USA coordinates in a single ORS call.

    Returns GeoJSON LineString geometry plus distance (meters) and duration (seconds).
    """
    key = api_key or settings.ORS_API_KEY
    if not key:
        raise RoutingError("ORS_API_KEY is not configured")

    validate_route_coordinates(start, finish)

    payload = {
        "coordinates": [
            [start.longitude, start.latitude],
            [finish.longitude, finish.latitude],
        ],
        "instructions": False,
        "geometry": True,
    }

    try:
        response = requests.post(
            ORS_DIRECTIONS_URL,
            headers={
                "Authorization": key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise RoutingError("OpenRouteService directions request timed out") from exc
    except requests.RequestException as exc:
        raise RoutingError(f"OpenRouteService directions request failed: {exc}") from exc

    if response.status_code == 429:
        raise RoutingError("OpenRouteService rate limit exceeded")
    if response.status_code >= 500:
        raise RoutingError(
            f"OpenRouteService server error: {response.status_code}"
        )
    if not response.ok:
        raise RoutingError(
            f"Directions request failed: {response.status_code} {response.text[:200]}"
        )

    features = response.json().get("features") or []
    if not features:
        raise RoutingError("No route returned for the given coordinates")

    feature = features[0]
    geometry = feature.get("geometry") or {}
    if geometry.get("type") != "LineString":
        raise RoutingError("Unexpected route geometry type from OpenRouteService")

    summary = (feature.get("properties") or {}).get("summary") or {}
    distance_meters = summary.get("distance")
    duration_seconds = summary.get("duration")
    if distance_meters is None or duration_seconds is None:
        raise RoutingError("Route response missing distance or duration summary")

    return RouteResult(
        geometry=geometry,
        route_feature=feature,
        distance_meters=float(distance_meters),
        duration_seconds=float(duration_seconds),
    )
