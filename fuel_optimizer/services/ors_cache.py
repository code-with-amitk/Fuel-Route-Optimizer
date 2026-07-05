"""Django cache layer for OpenRouteService geocode and routing responses."""

from __future__ import annotations

import hashlib
from typing import Any

from django.conf import settings
from django.core.cache import cache

from fuel_optimizer.services.geocoding import GeocodeResult, geocode_address
from fuel_optimizer.services.routing import RouteCoordinate, RouteResult, get_route

DEFAULT_CACHE_TTL = 60 * 60 * 24  # 24 hours


def cache_ttl_seconds() -> int:
    return int(getattr(settings, "ORS_CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL))


def geocode_cache_key(text: str) -> str:
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()
    return f"ors:geocode:{digest}"


def route_cache_key(start: RouteCoordinate, finish: RouteCoordinate) -> str:
    return (
        "ors:route:"
        f"{start.latitude:.4f},{start.longitude:.4f}:"
        f"{finish.latitude:.4f},{finish.longitude:.4f}"
    )


def _serialize_geocode(result: GeocodeResult) -> dict[str, Any]:
    return {
        "latitude": result.latitude,
        "longitude": result.longitude,
        "label": result.label,
        "confidence": result.confidence,
    }


def _deserialize_geocode(data: dict[str, Any]) -> GeocodeResult:
    return GeocodeResult(
        latitude=data["latitude"],
        longitude=data["longitude"],
        label=data["label"],
        confidence=data.get("confidence"),
    )


def _serialize_route(result: RouteResult) -> dict[str, Any]:
    return {
        "geometry": result.geometry,
        "route_feature": result.route_feature,
        "distance_meters": result.distance_meters,
        "duration_seconds": result.duration_seconds,
    }


def _deserialize_route(data: dict[str, Any]) -> RouteResult:
    return RouteResult(
        geometry=data["geometry"],
        route_feature=data["route_feature"],
        distance_meters=data["distance_meters"],
        duration_seconds=data["duration_seconds"],
    )


def cached_geocode_address(text: str, **kwargs) -> tuple[GeocodeResult, bool]:
    """Return geocode result and whether it came from cache."""
    key = geocode_cache_key(text)
    cached = cache.get(key)
    if cached is not None:
        return _deserialize_geocode(cached), True

    result = geocode_address(text, **kwargs)
    cache.set(key, _serialize_geocode(result), cache_ttl_seconds())
    return result, False


def cached_get_route(
    start: RouteCoordinate,
    finish: RouteCoordinate,
    **kwargs,
) -> tuple[RouteResult, bool]:
    """Return route result and whether it came from cache."""
    key = route_cache_key(start, finish)
    cached = cache.get(key)
    if cached is not None:
        return _deserialize_route(cached), True

    result = get_route(start, finish, **kwargs)
    cache.set(key, _serialize_route(result), cache_ttl_seconds())
    return result, False
