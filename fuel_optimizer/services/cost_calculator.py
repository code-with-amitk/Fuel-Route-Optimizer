"""
Fuel cost calculations for route legs.

After optimize_fuel_stops() picks where to refuel, this module turns those
choices into dollars spent.

Pricing model (documented in architecture.md Section 6):
  - Driver fills the tank at each chosen stop.
  - Each leg is billed at the price of the stop where that leg *begins*.
  - The drive from trip start to the first stop uses the departure tank and is
    not charged here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from fuel_optimizer.services.fuel_optimizer import FuelStopPlan

MPG = 10
MONEY_PRECISION = Decimal("0.01")


@dataclass(frozen=True)
class FuelLegCost:
    """Fuel spend for one leg that starts at a chosen stop."""

    start_mile: float
    end_mile: float
    leg_distance_miles: float
    retail_price: Decimal
    leg_fuel_cost_usd: Decimal


@dataclass(frozen=True)
class FuelCostSummary:
    legs: tuple[FuelLegCost, ...]
    total_fuel_cost_usd: Decimal


def calculate_fuel_costs(
    fuel_stops: list[FuelStopPlan],
    total_distance_miles: float,
    *,
    mpg: int = MPG,
) -> FuelCostSummary:
    """
    Calculate fuel spend for each leg beginning at a fuel stop.

    Example with two stops at miles 100 and 400 on a 450-mile trip:
      - Leg 1: miles 100→400, priced at stop 1
      - Leg 2: miles 400→450, priced at stop 2
    """
    if mpg <= 0:
        raise ValueError("mpg must be positive")

    if not fuel_stops:
        return FuelCostSummary(legs=tuple(), total_fuel_cost_usd=Decimal("0.00"))

    legs: list[FuelLegCost] = []
    total_cost = Decimal("0")

    for index, stop in enumerate(fuel_stops):
        start_mile = stop.distance_from_start_miles
        # Leg ends at the next stop, or at the destination if this is the last stop.
        end_mile = (
            fuel_stops[index + 1].distance_from_start_miles
            if index + 1 < len(fuel_stops)
            else total_distance_miles
        )
        leg_distance = max(0.0, end_mile - start_mile)
        gallons = Decimal(str(leg_distance)) / Decimal(mpg)
        leg_cost = _money(gallons * stop.station.retail_price)

        legs.append(
            FuelLegCost(
                start_mile=start_mile,
                end_mile=end_mile,
                leg_distance_miles=leg_distance,
                retail_price=stop.station.retail_price,
                leg_fuel_cost_usd=leg_cost,
            )
        )
        total_cost += leg_cost

    return FuelCostSummary(legs=tuple(legs), total_fuel_cost_usd=_money(total_cost))


def _money(value: Decimal) -> Decimal:
    """Round to cents for API-friendly currency values."""
    return value.quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)
