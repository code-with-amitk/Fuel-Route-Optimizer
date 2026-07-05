"""Manual verification helpers for ORS geocoding and routing clients."""

from django.core.management.base import BaseCommand

from fuel_optimizer.services.geocoding import geocode_address
from fuel_optimizer.services.routing import RouteCoordinate, get_route


class Command(BaseCommand):
    help = "Smoke-test ORS geocoding and routing clients (Phase 4.4)."

    def handle(self, *args, **options):
        self.stdout.write("Testing geocoding: Chicago, IL")
        chicago = geocode_address("Chicago, IL")
        self.stdout.write(
            f"  -> {chicago.label} ({chicago.latitude}, {chicago.longitude})"
        )

        self.stdout.write("Testing geocoding: Denver, CO")
        denver = geocode_address("Denver, CO")
        self.stdout.write(
            f"  -> {denver.label} ({denver.latitude}, {denver.longitude})"
        )

        self.stdout.write("Testing routing: Chicago -> Denver")
        route = get_route(
            RouteCoordinate(chicago.latitude, chicago.longitude),
            RouteCoordinate(denver.latitude, denver.longitude),
        )
        coordinates = route.geometry.get("coordinates") or []
        self.stdout.write(
            f"  -> {route.distance_miles:.1f} miles, "
            f"{route.duration_seconds:.0f} seconds, "
            f"{len(coordinates)} polyline points"
        )
        self.stdout.write(self.style.SUCCESS("ORS client smoke test passed."))
