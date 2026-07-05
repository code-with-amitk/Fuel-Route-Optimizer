"""Hit the local route API with common scenarios (Phase 6.6 manual HTTP client)."""

import json

import requests
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Call POST /api/v1/route/ with sample payloads against the running dev server."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default="http://127.0.0.1:8000",
            help="Server base URL (dev server must be running).",
        )

    def handle(self, *args, **options):
        base_url = options["base_url"].rstrip("/")
        endpoint = f"{base_url}/api/v1/route/"

        scenarios = [
            (
                "Short trip — coordinates (no geocode calls)",
                {
                    "start": {"lat": 41.8781, "lng": -87.6298},
                    "finish": {"lat": 41.8781, "lng": -87.5000},
                },
            ),
            (
                "Address-based trip",
                {"start": "Chicago, IL", "finish": "Milwaukee, WI"},
            ),
            (
                "Invalid — missing finish",
                {"start": "Chicago, IL"},
            ),
        ]

        for title, payload in scenarios:
            self.stdout.write(f"\n=== {title} ===")
            try:
                response = requests.post(endpoint, json=payload, timeout=60)
            except requests.RequestException as exc:
                self.stderr.write(self.style.ERROR(f"Request failed: {exc}"))
                continue

            self.stdout.write(f"Status: {response.status_code}")
            try:
                body = response.json()
            except json.JSONDecodeError:
                self.stdout.write(response.text[:500])
                continue

            if response.ok:
                summary = body.get("summary", {})
                self.stdout.write(
                    f"Distance: {summary.get('total_distance_miles')} mi | "
                    f"Fuel stops: {summary.get('fuel_stops_count')} | "
                    f"Cost: ${summary.get('total_fuel_cost_usd')}"
                )
            else:
                self.stdout.write(json.dumps(body, indent=2))

        self.stdout.write(self.style.SUCCESS("\nRoute API client scenarios complete."))
