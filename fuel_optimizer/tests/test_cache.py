"""Tests for ORS geocode/route caching and API call accounting."""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from fuel_optimizer.models import FuelStation
from fuel_optimizer.services.geocoding import GeocodeResult
from fuel_optimizer.services.ors_cache import cached_geocode_address, cached_get_route
from fuel_optimizer.services.route_service import plan_fuel_route
from fuel_optimizer.services.routing import RouteCoordinate, RouteResult


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-ors-cache",
        }
    }
)
class OrsCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("fuel_optimizer.services.ors_cache.geocode_address")
    def test_geocode_cache_hit_skips_second_api_call(self, mock_geocode):
        mock_geocode.return_value = GeocodeResult(41.88, -87.66, "Chicago, IL, USA")

        cached_geocode_address("Chicago, IL")
        cached_geocode_address("Chicago, IL")

        mock_geocode.assert_called_once()

    @patch("fuel_optimizer.services.ors_cache.get_route")
    def test_route_cache_hit_skips_second_api_call(self, mock_get_route):
        geometry = {
            "type": "LineString",
            "coordinates": [[-87.63, 41.88], [-87.50, 41.88]],
        }
        mock_get_route.return_value = RouteResult(
            geometry=geometry,
            route_feature={"type": "Feature", "geometry": geometry, "properties": {}},
            distance_meters=8046.7,
            duration_seconds=900.0,
        )
        start = RouteCoordinate(41.8781, -87.6298)
        finish = RouteCoordinate(41.8781, -87.5000)

        cached_get_route(start, finish)
        cached_get_route(start, finish)

        mock_get_route.assert_called_once()


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-plan-cache",
        }
    }
)
class OrsApiCallCountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.route_geometry = {
            "type": "LineString",
            "coordinates": [
                [-87.6298, 41.8781],
                [-87.2000, 41.8781],
                [-86.7000, 41.8781],
            ],
        }
        FuelStation.objects.create(
            opis_id=201,
            name="MID ROUTE CHEAP",
            address="I-90",
            city="Toledo",
            state="OH",
            rack_id=201,
            retail_price=Decimal("2.750000"),
            latitude=41.8781,
            longitude=-86.0000,
        )

    @patch("fuel_optimizer.services.ors_cache.get_route")
    @patch("fuel_optimizer.services.ors_cache.geocode_address")
    def test_uncached_address_request_makes_three_ors_calls(self, mock_geocode, mock_get_route):
        mock_geocode.side_effect = [
            GeocodeResult(41.87897, -87.66063, "Chicago, IL, USA"),
            GeocodeResult(43.0389, -87.9065, "Milwaukee, WI, USA"),
        ]
        mock_get_route.return_value = RouteResult(
            geometry=self.route_geometry,
            route_feature={"type": "Feature", "geometry": self.route_geometry, "properties": {}},
            distance_meters=160934.0,
            duration_seconds=3600.0,
        )

        result = plan_fuel_route("Chicago, IL", "Milwaukee, WI")

        self.assertEqual(result["summary"]["ors_api_calls"], 3)
        self.assertEqual(mock_geocode.call_count, 2)
        mock_get_route.assert_called_once()

    @patch("fuel_optimizer.services.ors_cache.get_route")
    @patch("fuel_optimizer.services.ors_cache.geocode_address")
    def test_full_cache_hit_makes_zero_ors_calls(self, mock_geocode, mock_get_route):
        mock_geocode.side_effect = [
            GeocodeResult(41.87897, -87.66063, "Chicago, IL, USA"),
            GeocodeResult(43.0389, -87.9065, "Milwaukee, WI, USA"),
        ]
        mock_get_route.return_value = RouteResult(
            geometry=self.route_geometry,
            route_feature={"type": "Feature", "geometry": self.route_geometry, "properties": {}},
            distance_meters=160934.0,
            duration_seconds=3600.0,
        )

        plan_fuel_route("Chicago, IL", "Milwaukee, WI")
        result = plan_fuel_route("Chicago, IL", "Milwaukee, WI")

        self.assertEqual(result["summary"]["ors_api_calls"], 0)
        self.assertEqual(mock_geocode.call_count, 2)
        mock_get_route.assert_called_once()

    @patch("fuel_optimizer.services.ors_cache.get_route")
    def test_coordinate_only_request_makes_one_ors_call(self, mock_get_route):
        mock_get_route.return_value = RouteResult(
            geometry=self.route_geometry,
            route_feature={"type": "Feature", "geometry": self.route_geometry, "properties": {}},
            distance_meters=8046.7,
            duration_seconds=900.0,
        )

        result = plan_fuel_route(
            {"lat": 41.8781, "lng": -87.6298},
            {"lat": 41.8781, "lng": -87.5000},
        )

        self.assertEqual(result["summary"]["ors_api_calls"], 1)
        mock_get_route.assert_called_once()
