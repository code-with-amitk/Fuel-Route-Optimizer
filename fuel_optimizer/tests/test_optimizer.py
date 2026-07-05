"""
Unit tests for the fuel stop optimizer.

Uses a synthetic east-west polyline (fixed GeoJSON coordinates) and real
FuelStation rows in a test database. No live ORS calls.

Tests override max_range_miles in some cases so a ~140-mile sample route
behaves like a long trip without needing a 500-mile test fixture.
"""

from decimal import Decimal

from django.test import TestCase

from fuel_optimizer.models import FuelStation
from fuel_optimizer.services.cost_calculator import calculate_fuel_costs
from fuel_optimizer.services.fuel_optimizer import (
    FuelOptimizerError,
    find_stations_in_corridor,
    optimize_fuel_stops,
    select_cheapest_station,
)
from fuel_optimizer.services.route_geometry import build_cumulative_distances


class FuelOptimizerTests(TestCase):
    def setUp(self):
        # Flat eastbound route near Chicago — easy to reason about mile markers.
        self.route_geometry = {
            "type": "LineString",
            "coordinates": [
                [-87.6298, 41.8781],
                [-87.2000, 41.8781],
                [-86.7000, 41.8781],
                [-86.2000, 41.8781],
            ],
        }
        self.cumulative = build_cumulative_distances(self.route_geometry["coordinates"])
        self.total_distance_miles = self.cumulative[-1]

        self.expensive = FuelStation.objects.create(
            opis_id=1,
            name="EXPENSIVE STOP",
            address="I-90 East",
            city="Chicago",
            state="IL",
            rack_id=1,
            retail_price=Decimal("4.500000"),
            latitude=41.8781,
            longitude=-87.4000,
        )
        self.cheap = FuelStation.objects.create(
            opis_id=2,
            name="CHEAP STOP",
            address="I-90 East",
            city="Gary",
            state="IN",
            rack_id=2,
            retail_price=Decimal("3.000000"),
            latitude=41.8781,
            longitude=-87.0000,
        )

    def test_select_cheapest_station_breaks_price_ties_by_distance(self):
        from fuel_optimizer.services.fuel_optimizer import FuelStopPlan

        # Same price → prefer the station closer to the route (smaller 3rd sort key).
        nearer = FuelStopPlan(self.cheap, 120.0, 1.0)
        farther = FuelStopPlan(
            FuelStation(
                opis_id=3,
                name="CHEAP FAR",
                address="Far",
                city="Gary",
                state="IN",
                rack_id=3,
                retail_price=Decimal("3.000000"),
                latitude=41.8781,
                longitude=-86.9000,
            ),
            130.0,
            5.0,
        )

        selected = select_cheapest_station([farther, nearer])
        self.assertEqual(selected.station.name, "CHEAP STOP")

    def test_find_stations_in_corridor_returns_projected_candidates(self):
        candidates = find_stations_in_corridor(
            self.route_geometry["coordinates"],
            self.cumulative,
            start_mile=0.0,
            end_mile=self.total_distance_miles,
        )

        names = {candidate.station.name for candidate in candidates}
        self.assertIn("CHEAP STOP", names)
        self.assertIn("EXPENSIVE STOP", names)

    def test_optimize_fuel_stops_skips_stop_when_trip_within_range(self):
        # 5-mile trip is well under 500-mile range → no refuel stops needed.
        short_route = {
            "type": "LineString",
            "coordinates": [
                [-87.6298, 41.8781],
                [-87.5000, 41.8781],
            ],
        }

        stops = optimize_fuel_stops(short_route, total_distance_miles=5.0)

        self.assertEqual(stops, [])

    def test_optimize_fuel_stops_picks_cheapest_in_range(self):
        long_route = {
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
        total_distance = build_cumulative_distances(long_route["coordinates"])[-1]

        FuelStation.objects.create(
            opis_id=3,
            name="MID ROUTE CHEAP",
            address="I-90",
            city="Toledo",
            state="OH",
            rack_id=3,
            retail_price=Decimal("2.750000"),
            latitude=41.8781,
            longitude=-86.0000,
        )
        FuelStation.objects.create(
            opis_id=5,
            name="LATER CHEAP",
            address="I-90",
            city="South Bend",
            state="IN",
            rack_id=5,
            retail_price=Decimal("2.900000"),
            latitude=41.8781,
            longitude=-86.3500,
        )

        # max_range_miles=130 forces one refuel on this ~140 mi route; MID ROUTE
        # CHEAP ($2.75) should beat LATER CHEAP ($2.90) and setUp stations.
        stops = optimize_fuel_stops(
            long_route,
            total_distance_miles=total_distance,
            max_range_miles=130.0,
        )

        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0].station.name, "MID ROUTE CHEAP")

    def test_optimize_and_cost_summary_integration(self):
        long_route = {
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
        total_distance = build_cumulative_distances(long_route["coordinates"])[-1]

        FuelStation.objects.create(
            opis_id=4,
            name="MID ROUTE CHEAP",
            address="I-90",
            city="Toledo",
            state="OH",
            rack_id=4,
            retail_price=Decimal("2.750000"),
            latitude=41.8781,
            longitude=-86.0000,
        )

        stops = optimize_fuel_stops(
            long_route,
            total_distance_miles=total_distance,
            max_range_miles=130.0,
        )
        summary = calculate_fuel_costs(stops, total_distance_miles=total_distance)

        self.assertGreater(summary.total_fuel_cost_usd, Decimal("0.00"))
        self.assertEqual(len(summary.legs), len(stops))

    def test_optimize_raises_when_no_stations_available(self):
        # Remote route with no FuelStation rows in DB → planner must fail clearly.
        FuelStation.objects.all().delete()
        route = {
            "type": "LineString",
            "coordinates": [
                [-100.0, 35.0],
                [-99.0, 35.0],
                [-98.0, 35.0],
            ],
        }
        total_distance = build_cumulative_distances(route["coordinates"])[-1]

        with self.assertRaises(FuelOptimizerError):
            optimize_fuel_stops(
                route,
                total_distance_miles=total_distance,
                max_range_miles=50.0,
            )
