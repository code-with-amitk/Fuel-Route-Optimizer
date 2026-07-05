"""API integration tests for POST /api/v1/route/ (mocked ORS, no live external calls)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from fuel_optimizer.models import FuelStation
from fuel_optimizer.services.geocoding import GeocodeResult
from fuel_optimizer.services.routing import RouteResult


class RouteAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.route_geometry = {
            "type": "LineString",
            "coordinates": [
                [-87.6298, 41.8781],
                [-87.2000, 41.8781],
                [-86.7000, 41.8781],
                [-86.2000, 41.8781],
                [-85.0000, 41.8781],
                [-84.0000, 41.8781],
            ],
        }
        FuelStation.objects.create(
            opis_id=101,
            name="MID ROUTE CHEAP",
            address="I-90",
            city="Toledo",
            state="OH",
            rack_id=101,
            retail_price=Decimal("2.750000"),
            latitude=41.8781,
            longitude=-86.0000,
        )

    @patch("fuel_optimizer.services.route_service.get_route")
    @patch("fuel_optimizer.services.route_service.geocode_address")
    def test_post_route_with_addresses(self, mock_geocode, mock_get_route):
        mock_geocode.side_effect = [
            GeocodeResult(41.87897, -87.66063, "Chicago, IL, USA"),
            GeocodeResult(39.740959, -104.985798, "Denver, CO, USA"),
        ]
        mock_get_route.return_value = RouteResult(
            geometry=self.route_geometry,
            route_feature={"type": "Feature", "geometry": self.route_geometry, "properties": {}},
            distance_meters=160934.0,
            duration_seconds=36000.0,
        )

        response = self.client.post(
            "/api/v1/route/",
            {"start": "Chicago, IL", "finish": "Denver, CO"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("route", response.data)
        self.assertIn("fuel_stops", response.data)
        self.assertIn("summary", response.data)
        self.assertEqual(response.data["start"]["label"], "Chicago, IL, USA")
        self.assertEqual(response.data["summary"]["mpg"], 10)
        self.assertEqual(response.data["summary"]["max_range_miles"], 500)

    @patch("fuel_optimizer.services.route_service.get_route")
    def test_post_route_with_coordinates_skips_geocoding(self, mock_get_route):
        mock_get_route.return_value = RouteResult(
            geometry=self.route_geometry,
            route_feature={"type": "Feature", "geometry": self.route_geometry, "properties": {}},
            distance_meters=8046.7,
            duration_seconds=900.0,
        )

        response = self.client.post(
            "/api/v1/route/",
            {
                "start": {"lat": 41.8781, "lng": -87.6298},
                "finish": {"lat": 41.8781, "lng": -87.5000},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        mock_get_route.assert_called_once()

    def test_missing_fields_return_400(self):
        response = self.client.post("/api/v1/route/", {"start": "Chicago, IL"}, format="json")
        self.assertEqual(response.status_code, 400)

    @patch("fuel_optimizer.services.route_service.geocode_address")
    def test_geocode_miss_returns_404(self, mock_geocode):
        from fuel_optimizer.services.geocoding import GeocodingError

        mock_geocode.side_effect = GeocodingError("No geocoding match for: Nowhere, XX")

        response = self.client.post(
            "/api/v1/route/",
            {"start": "Nowhere, XX", "finish": "Chicago, IL"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    @patch("fuel_optimizer.services.route_service.get_route")
    @patch("fuel_optimizer.services.route_service.geocode_address")
    def test_routing_failure_returns_502(self, mock_geocode, mock_get_route):
        from fuel_optimizer.services.routing import RoutingError

        mock_geocode.side_effect = [
            GeocodeResult(41.87897, -87.66063, "Chicago, IL, USA"),
            GeocodeResult(39.740959, -104.985798, "Denver, CO, USA"),
        ]
        mock_get_route.side_effect = RoutingError("OpenRouteService server error: 503")

        response = self.client.post(
            "/api/v1/route/",
            {"start": "Chicago, IL", "finish": "Denver, CO"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)

    @patch("fuel_optimizer.services.route_service.get_route")
    def test_get_route_with_query_params(self, mock_get_route):
        mock_get_route.return_value = RouteResult(
            geometry=self.route_geometry,
            route_feature={"type": "Feature", "geometry": self.route_geometry, "properties": {}},
            distance_meters=8046.7,
            duration_seconds=900.0,
        )

        response = self.client.get(
            "/api/v1/route/",
            {
                "start": '{"lat": 41.8781, "lng": -87.6298}',
                "finish": '{"lat": 41.8781, "lng": -87.5000}',
            },
        )

        self.assertEqual(response.status_code, 200)
