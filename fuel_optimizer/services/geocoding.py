"""OpenRouteService geocoding client (used by CSV import and route API)."""

from __future__ import annotations

from dataclasses import dataclass

import requests
from django.conf import settings

ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"

USA_LAT_MIN = 24.5
USA_LAT_MAX = 49.5
USA_LON_MIN = -125.0
USA_LON_MAX = -66.5


class GeocodingError(Exception):
    """Raised when an address cannot be geocoded."""


@dataclass(frozen=True)
class GeocodeResult:
    latitude: float
    longitude: float
    label: str
    confidence: float | None = None


def build_station_query(*, address: str, city: str, state: str) -> str:
    return f"{address}, {city}, {state}, USA"


def is_within_usa(latitude: float, longitude: float) -> bool:
    return (
        USA_LAT_MIN <= latitude <= USA_LAT_MAX
        and USA_LON_MIN <= longitude <= USA_LON_MAX
    )


def geocode_address(
    text: str,
    *,
    api_key: str | None = None,
    timeout: int = 10,
) -> GeocodeResult:
    key = api_key or settings.ORS_API_KEY
    if not key:
        raise GeocodingError("ORS_API_KEY is not configured")

    try:
        response = requests.get(
            ORS_GEOCODE_URL,
            headers={"Authorization": key},
            params={
                "text": text,
                "boundary.country": "USA",
                "size": 1,
            },
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise GeocodingError("OpenRouteService geocoding request timed out") from exc
    except requests.RequestException as exc:
        raise GeocodingError(f"OpenRouteService geocoding request failed: {exc}") from exc

    if response.status_code == 429:
        raise GeocodingError("OpenRouteService rate limit exceeded")
    if response.status_code >= 500:
        raise GeocodingError(f"OpenRouteService server error: {response.status_code}")
    if not response.ok:
        raise GeocodingError(
            f"Geocoding request failed: {response.status_code} {response.text[:200]}"
        )

    features = response.json().get("features") or []
    if not features:
        raise GeocodingError(f"No geocoding match for: {text}")

    feature = features[0]
    longitude, latitude = feature["geometry"]["coordinates"]
    properties = feature.get("properties") or {}

    if not is_within_usa(latitude, longitude):
        raise GeocodingError(f"Geocoded location outside USA bounds: {text}")

    confidence = properties.get("confidence")
    if confidence is not None:
        confidence = float(confidence)

    return GeocodeResult(
        latitude=latitude,
        longitude=longitude,
        label=properties.get("label", text),
        confidence=confidence,
    )
