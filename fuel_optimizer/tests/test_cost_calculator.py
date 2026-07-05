"""
Unit tests for route geometry and cost calculation.

These tests use fixed coordinates and fake station objects — no live ORS calls
and no database (SimpleTestCase).
"""

from decimal import Decimal

from django.test import SimpleTestCase

from fuel_optimizer.services.cost_calculator import calculate_fuel_costs
from fuel_optimizer.services.fuel_optimizer import FuelStopPlan
from fuel_optimizer.services.route_geometry import build_cumulative_distances


class _Station:
    """Minimal stand-in for FuelStation; cost logic only needs retail_price."""

    def __init__(self, retail_price: str):
        self.retail_price = Decimal(retail_price)


class CostCalculatorTests(SimpleTestCase):
    def test_calculate_fuel_costs_for_two_stops(self):
        # Trip: 450 miles total. Stops at mile 100 ($3.00) and mile 400 ($3.50).
        # Leg 1: 100→400 = 300 mi → 30 gal × $3.00 = $90.00
        # Leg 2: 400→450 =  50 mi →  5 gal × $3.50 = $17.50
        stops = [
            FuelStopPlan(_Station("3.00"), 100.0, 1.0),
            FuelStopPlan(_Station("3.50"), 400.0, 1.0),
        ]

        summary = calculate_fuel_costs(stops, total_distance_miles=450.0, mpg=10)

        self.assertEqual(len(summary.legs), 2)
        self.assertEqual(summary.legs[0].leg_distance_miles, 300.0)
        self.assertEqual(summary.legs[0].leg_fuel_cost_usd, Decimal("90.00"))
        self.assertEqual(summary.legs[1].leg_distance_miles, 50.0)
        self.assertEqual(summary.legs[1].leg_fuel_cost_usd, Decimal("17.50"))
        self.assertEqual(summary.total_fuel_cost_usd, Decimal("107.50"))

    def test_no_stops_returns_zero_cost(self):
        # Short trip within 500-mile range: optimizer returns no stops → $0 billed.
        summary = calculate_fuel_costs([], total_distance_miles=120.0)
        self.assertEqual(summary.total_fuel_cost_usd, Decimal("0.00"))


class RouteGeometryTests(SimpleTestCase):
    def test_build_cumulative_distances_on_simple_polyline(self):
        # Three points on the same latitude (due east). Distances should grow monotonically.
        coordinates = [
            [-87.6298, 41.8781],
            [-87.0000, 41.8781],
            [-86.5000, 41.8781],
        ]

        cumulative = build_cumulative_distances(coordinates)

        self.assertEqual(cumulative[0], 0.0)
        self.assertAlmostEqual(cumulative[1], 32.4, delta=1.0)
        self.assertGreater(cumulative[2], cumulative[1])
