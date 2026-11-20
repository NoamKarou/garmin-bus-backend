from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 20, 7, 39, 0, tzinfo=timezone.utc)


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def stops_from_trip(rows: list[dict[str, Any]], code: int) -> list[dict[str, Any]]:
    for row in rows:
        if row.get("gtfs_stop__code") == code:
            return [
                {
                    "id": row.get("gtfs_stop_id"),
                    "date": row.get("gtfs_stop__date"),
                    "code": code,
                    "lat": row.get("gtfs_stop__lat"),
                    "lon": row.get("gtfs_stop__lon"),
                    "name": row.get("gtfs_stop__name"),
                    "city": row.get("gtfs_stop__city"),
                }
            ]
    return []


class FakeStride:
    """In-memory stand-in for StrideClient, backed by captured fixtures."""

    def __init__(
        self,
        *,
        stops: dict[str, Any] | None = None,
        routes: dict[str, Any] | None = None,
        schedule: dict[tuple[str, str], Any] | None = None,
        trips: dict[int, Any] | None = None,
        vehicles: dict[int, Any] | None = None,
    ) -> None:
        self.stops = stops or {}
        self.routes = routes or {}
        self.schedule = schedule or {}
        self.trips = trips or {}
        self.vehicles = vehicles or {}
        self.calls: list[tuple[str, tuple]] = []

    @staticmethod
    def _value(mapping: dict, key: Any) -> Any:
        value = mapping.get(key, [])
        if isinstance(value, Exception):
            raise value
        return value

    async def list_stops(self, code, date_from, date_to):
        self.calls.append(("stops", (str(code),)))
        return self._value(self.stops, str(code))

    async def list_routes(self, short_name, date_from, date_to):
        self.calls.append(("routes", (short_name,)))
        return self._value(self.routes, short_name)

    async def list_ride_stops_at_station(self, station_code, line, start, end):
        self.calls.append(("schedule", (line, str(station_code))))
        return self._value(self.schedule, (line, str(station_code)))

    async def list_trip_stops(self, gtfs_ride_id):
        self.calls.append(("trip", (gtfs_ride_id,)))
        return self._value(self.trips, gtfs_ride_id)

    async def list_vehicle_locations(self, line_ref, start, end):
        self.calls.append(("vehicles", (line_ref,)))
        return self._value(self.vehicles, line_ref)


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def fake() -> FakeStride:
    return standard_fake()


@pytest.fixture
def vehicles_5499() -> list[dict[str, Any]]:
    return load("siri_vehicle_locations_5499.json")


@pytest.fixture
def vehicles_7023() -> list[dict[str, Any]]:
    return load("siri_vehicle_locations_7023.json")


@pytest.fixture
def trip_480() -> list[dict[str, Any]]:
    return load("gtfs_ride_stops_163800994.json")


@pytest.fixture
def trip_22_0700() -> list[dict[str, Any]]:
    return load("gtfs_ride_stops_163797003.json")


@pytest.fixture
def trip_22_0720() -> list[dict[str, Any]]:
    return load("gtfs_ride_stops_163764140.json")


@pytest.fixture
def trip_22_0740() -> list[dict[str, Any]]:
    return load("gtfs_ride_stops_163764141.json")


def standard_fake() -> FakeStride:
    trip_480 = load("gtfs_ride_stops_163800994.json")
    trip_22_0700 = load("gtfs_ride_stops_163797003.json")
    trip_22_0720 = load("gtfs_ride_stops_163764140.json")
    trip_22_0740 = load("gtfs_ride_stops_163764141.json")
    return FakeStride(
        stops={
            "4170": load("gtfs_stops_4170.json"),
            "5895": stops_from_trip(trip_22_0700, 5895),
            "1484": stops_from_trip(trip_22_0700, 1484),
            "1487": stops_from_trip(trip_22_0700, 1487),
        },
        routes={
            "480": load("gtfs_routes_480.json"),
            "22": [{"id": 1, "line_ref": 5499, "route_short_name": "22"}],
        },
        schedule={
            ("480", "4170"): load("gtfs_ride_stops_480_4170.json"),
            ("480", "27997"): load("gtfs_ride_stops_480_27997.json"),
            ("22", "5895"): load("gtfs_ride_stops_22_5895.json"),
            ("22", "1484"): load("gtfs_ride_stops_22_1484.json"),
            ("22", "1487"): load("gtfs_ride_stops_22_1487.json"),
        },
        trips={
            163800994: trip_480,
            163797003: trip_22_0700,
            163764140: trip_22_0720,
            163764141: trip_22_0740,
        },
        vehicles={
            5499: load("siri_vehicle_locations_5499.json"),
            7023: load("siri_vehicle_locations_7023.json"),
        },
    )
