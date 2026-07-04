"""Load fuel stations from CSV, geocode offline, and bulk-insert into the database."""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from fuel_optimizer.models import FuelStation
from fuel_optimizer.services.geocoding import (
    GeocodingError,
    build_station_query,
    geocode_address,
)

CSV_COLUMNS = {
    "opis_id": "OPIS Truckstop ID",
    "name": "Truckstop Name",
    "address": "Address",
    "city": "City",
    "state": "State",
    "rack_id": "Rack ID",
    "retail_price": "Retail Price",
}


@dataclass
class StationRow:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    rack_id: int | None
    retail_price: Decimal


class Command(BaseCommand):
    help = "Import fuel prices from CSV, geocode stations once, and store in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            default=str(settings.BASE_DIR / "fuel-prices-for-be-assessment.csv"),
            help="Path to fuel prices CSV file.",
        )
        parser.add_argument(
            "--cache",
            default=str(settings.BASE_DIR / ".geocode_cache.json"),
            help="JSON file cache for geocode results (speeds up re-runs).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing FuelStation rows before importing.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and deduplicate only; do not geocode or write to DB.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process only the first N unique stations (for testing).",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.1,
            help="Seconds to sleep between live geocode API calls.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Insert to the database after this many geocoded stations.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv"])
        cache_path = Path(options["cache"])

        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        stations = self._parse_and_deduplicate(csv_path)
        self.stdout.write(
            f"Parsed {options['csv']}: {len(stations)} unique stations after deduplication."
        )

        if options["limit"]:
            stations = stations[: options["limit"]]
            self.stdout.write(f"Limited to first {len(stations)} stations.")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run complete; no geocoding or DB writes."))
            return

        if options["clear"]:
            deleted, _ = FuelStation.objects.all().delete()
            self.stdout.write(f"Cleared {deleted} existing FuelStation rows.")

        cache = self._load_cache(cache_path)
        geocoded_batch: list[FuelStation] = []
        geocode_failures = 0
        cache_hits = 0
        api_calls = 0
        inserted = 0
        batch_size = options["batch_size"]

        for index, station in enumerate(stations, start=1):
            cache_key = build_station_query(
                address=station.address,
                city=station.city,
                state=station.state,
            )

            if cache_key in cache:
                lat, lng, confidence = cache[cache_key]
                cache_hits += 1
            else:
                result = self._geocode_station(station, cache_key, cache)
                if result is None:
                    geocode_failures += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"[{index}/{len(stations)}] Geocode failed for "
                            f"{station.name} ({station.city}, {station.state})"
                        )
                    )
                    continue

                lat, lng, confidence = result
                api_calls += 1

                if options["delay"]:
                    time.sleep(options["delay"])

                if api_calls % 50 == 0:
                    self._save_cache(cache_path, cache)
                    self.stdout.write(f"Geocoded {api_calls} stations via API so far...")

            geocoded_batch.append(
                FuelStation(
                    opis_id=station.opis_id,
                    name=station.name,
                    address=station.address,
                    city=station.city,
                    state=station.state,
                    rack_id=station.rack_id,
                    retail_price=station.retail_price,
                    latitude=lat,
                    longitude=lng,
                    geocode_confidence=confidence,
                )
            )

            if len(geocoded_batch) >= batch_size:
                inserted += self._bulk_insert(geocoded_batch, batch_size)
                geocoded_batch.clear()
                self.stdout.write(
                    f"Progress: {index}/{len(stations)} processed, {inserted} inserted."
                )

        if geocoded_batch:
            inserted += self._bulk_insert(geocoded_batch, batch_size)

        self._save_cache(cache_path, cache)

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {inserted} stations inserted, "
                f"{cache_hits} cache hits, {api_calls} API calls, "
                f"{geocode_failures} geocode failures."
            )
        )
        self.stdout.write(f"Database total: {FuelStation.objects.count()} FuelStation rows.")

    def _geocode_station(
        self,
        station: StationRow,
        cache_key: str,
        cache: dict[str, list],
    ) -> tuple[float, float, float | None] | None:
        fallback_key = f"{station.city}, {station.state}, USA"
        for query in (cache_key, fallback_key):
            if query in cache:
                cached = cache[query]
                cache[cache_key] = cached
                return cached[0], cached[1], cached[2]

            try:
                result = geocode_address(query)
            except GeocodingError:
                continue

            coords = [result.latitude, result.longitude, result.confidence]
            cache[cache_key] = coords
            if query != cache_key:
                cache[query] = coords
            return result.latitude, result.longitude, result.confidence

        return None

    def _parse_and_deduplicate(self, csv_path: Path) -> list[StationRow]:
        deduped: dict[tuple[int, str], StationRow] = {}

        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    station = StationRow(
                        opis_id=int(row[CSV_COLUMNS["opis_id"]].strip()),
                        name=row[CSV_COLUMNS["name"]].strip(),
                        address=row[CSV_COLUMNS["address"]].strip(),
                        city=row[CSV_COLUMNS["city"]].strip(),
                        state=row[CSV_COLUMNS["state"]].strip().upper(),
                        rack_id=self._parse_optional_int(row[CSV_COLUMNS["rack_id"]]),
                        retail_price=Decimal(row[CSV_COLUMNS["retail_price"]].strip()),
                    )
                except (KeyError, InvalidOperation, ValueError) as exc:
                    raise CommandError(f"Invalid CSV row: {row!r} ({exc})") from exc

                key = (station.opis_id, station.address)
                existing = deduped.get(key)
                if existing is None or station.retail_price < existing.retail_price:
                    deduped[key] = station

        return list(deduped.values())

    @staticmethod
    def _parse_optional_int(value: str) -> int | None:
        value = (value or "").strip()
        if not value:
            return None
        return int(value)

    @staticmethod
    def _load_cache(cache_path: Path) -> dict[str, list]:
        if not cache_path.exists():
            return {}
        with cache_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _save_cache(cache_path: Path, cache: dict[str, list]) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle)

    @staticmethod
    def _bulk_insert(rows: list[FuelStation], batch_size: int) -> int:
        if not rows:
            return 0

        inserted = 0
        with transaction.atomic():
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                FuelStation.objects.bulk_create(
                    batch,
                    ignore_conflicts=True,
                    batch_size=batch_size,
                )
                inserted += len(batch)
        return inserted
