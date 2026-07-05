"""Orchestrate geocoding, routing, fuel optimization, and cost calculation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fuel_optimizer.services.cost_calculator import MPG, calculate_fuel_costs
from fuel_optimizer.services.fuel_optimizer import (
    MAX_RANGE_MILES,
    FuelOptimizerError,
    optimize_fuel_stops,
)
from fuel_optimizer.services.geocoding import GeocodeResult, GeocodingError, geocode_address
from fuel_optimizer.services.routing import RouteCoordinate, RouteResult, RoutingError, get_route


class RouteServiceError(Exception):
    """Domain error with an HTTP status code for the API layer."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ResolvedLocation:
    latitude: float
    longitude: float
    label: str


def resolve_location(value: str | dict[str, Any], *, field_name: str) -> ResolvedLocation:
    """Resolve an address string or {lat, lng} dict to coordinates."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise RouteServiceError(f"{field_name} address cannot be empty", 400)
        try:
            result = geocode_address(text)
        except GeocodingError as exc:
            raise _map_geocoding_error(exc) from exc
        return ResolvedLocation(result.latitude, result.longitude, result.label)

    if isinstance(value, dict):
        lat = value.get("lat")
        lng = value.get("lng")
        if lat is None or lng is None:
            raise RouteServiceError(
                f"{field_name} must include both lat and lng when using coordinates",
                400,
            )
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (TypeError, ValueError) as exc:
            raise RouteServiceError(f"{field_name} lat/lng must be numbers", 400) from exc

        label = value.get("label") or f"{lat_f}, {lng_f}"
        coordinate = RouteCoordinate(lat_f, lng_f)
        try:
            from fuel_optimizer.services.routing import validate_route_coordinates

            validate_route_coordinates(coordinate, coordinate)
        except RoutingError as exc:
            raise RouteServiceError(str(exc), 400) from exc
        return ResolvedLocation(lat_f, lng_f, label)

    raise RouteServiceError(
        f"{field_name} must be an address string or an object with lat and lng",
        400,
    )


def plan_fuel_route(
    start: str | dict[str, Any],
    finish: str | dict[str, Any],
) -> dict[str, Any]:
    """
    Full pipeline: resolve locations → ORS route → fuel stops → costs → JSON payload.
    """
    start_location = resolve_location(start, field_name="start")
    finish_location = resolve_location(finish, field_name="finish")

    try:
        route = get_route(
            RouteCoordinate(start_location.latitude, start_location.longitude),
            RouteCoordinate(finish_location.latitude, finish_location.longitude),
        )
    except RoutingError as exc:
        raise _map_routing_error(exc) from exc

    try:
        fuel_stop_plans = optimize_fuel_stops(
            route.geometry,
            total_distance_miles=route.distance_miles,
        )
    except FuelOptimizerError as exc:
        raise RouteServiceError(str(exc), 400) from exc

    cost_summary = calculate_fuel_costs(
        fuel_stop_plans,
        total_distance_miles=route.distance_miles,
    )

    fuel_stops = []
    for index, plan in enumerate(fuel_stop_plans):
        leg_cost = cost_summary.legs[index].leg_fuel_cost_usd if index < len(cost_summary.legs) else Decimal("0.00")
        station = plan.station
        fuel_stops.append(
            {
                "name": station.name,
                "address": station.address,
                "city": station.city,
                "state": station.state,
                "retail_price": float(station.retail_price),
                "coordinates": {
                    "lat": station.latitude,
                    "lng": station.longitude,
                },
                "distance_from_start_miles": round(plan.distance_from_start_miles, 1),
                "leg_fuel_cost_usd": float(leg_cost),
            }
        )

    return {
        "start": {
            "lat": start_location.latitude,
            "lng": start_location.longitude,
            "label": start_location.label,
        },
        "finish": {
            "lat": finish_location.latitude,
            "lng": finish_location.longitude,
            "label": finish_location.label,
        },
        "route": {
            "type": "Feature",
            "geometry": route.geometry,
            "properties": {
                "distance_miles": round(route.distance_miles, 1),
                "duration_seconds": round(route.duration_seconds),
            },
        },
        "fuel_stops": fuel_stops,
        "summary": {
            "total_distance_miles": round(route.distance_miles, 1),
            "total_fuel_cost_usd": float(cost_summary.total_fuel_cost_usd),
            "fuel_stops_count": len(fuel_stops),
            "mpg": MPG,
            "max_range_miles": MAX_RANGE_MILES,
        },
    }


def _map_geocoding_error(exc: GeocodingError) -> RouteServiceError:
    message = str(exc)
    if "No geocoding match" in message:
        return RouteServiceError(message, 404)
    if "outside USA" in message:
        return RouteServiceError(message, 400)
    if "rate limit" in message:
        return RouteServiceError(message, 503)
    if any(token in message for token in ("server error", "timed out", "request failed")):
        return RouteServiceError(message, 502)
    return RouteServiceError(message, 400)


def _map_routing_error(exc: RoutingError) -> RouteServiceError:
    message = str(exc)
    if "rate limit" in message:
        return RouteServiceError(message, 503)
    if any(token in message for token in ("server error", "timed out", "request failed")):
        return RouteServiceError(message, 502)
    return RouteServiceError(message, 502)
