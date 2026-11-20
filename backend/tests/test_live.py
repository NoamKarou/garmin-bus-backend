from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from app.arrivals import TripStop, _estimate_eta, _latest_vehicles, get_arrivals
from app.cache import TTLCache
from app.timeutil import parse_dt

UTC = timezone.utc


def _latest(rows, ride_id: int) -> dict:
    return max(
        (row for row in rows if row["siri_ride__id"] == ride_id),
        key=lambda row: row["recorded_at_time"],
    )


def _as_trip(rows: list[dict]) -> list[TripStop]:
    stops = []
    for row in rows:
        dist = row.get("shape_dist_traveled")
        stops.append(
            TripStop(
                seq=row["stop_sequence"],
                code=row["gtfs_stop__code"],
                planned=parse_dt(row["arrival_time"]),
                dist=float(dist) if dist is not None else 0.0,
                lat=row.get("gtfs_stop__lat"),
                lon=row.get("gtfs_stop__lon"),
            )
        )
    stops.sort(key=lambda stop: stop.seq)
    return stops


async def test_live_vehicle_waiting_at_origin(fake, now):
    response = await get_arrivals(fake, TTLCache(), ["22"], "5895", 3, now)

    first = response.arrivals[0]
    assert first.live is True
    assert first.arrival_time == datetime(2026, 11, 20, 7, 49, 26, tzinfo=UTC)
    assert first.minutes == 11
    assert response.arrivals[1].live is False


async def test_live_moving_vehicles(fake, now):
    response = await get_arrivals(fake, TTLCache(), ["22"], "1484", 3, now)

    assert [a.live for a in response.arrivals] == [True, True, False]
    assert response.arrivals[0].arrival_time == datetime(
        2026, 11, 20, 7, 40, 16, tzinfo=UTC
    )
    assert response.arrivals[1].arrival_time == datetime(
        2026, 11, 20, 7, 58, 56, tzinfo=UTC
    )


async def test_vehicle_that_passed_the_stop_is_ignored(fake, now, vehicles_5499):
    fake.vehicles = {
        5499: [row for row in vehicles_5499 if row["siri_ride__id"] == 154431092]
    }

    response = await get_arrivals(fake, TTLCache(), ["22"], "5895", 3, now)

    assert all(not arrival.live for arrival in response.arrivals)


async def test_stale_vehicle_is_ignored(fake, now, vehicles_5499):
    vehicle = copy.deepcopy(_latest(vehicles_5499, 154433200))
    vehicle["recorded_at_time"] = "2026-11-20T07:20:00+00:00"
    fake.vehicles = {5499: [vehicle]}

    response = await get_arrivals(fake, TTLCache(), ["22"], "5895", 3, now)

    assert all(not arrival.live for arrival in response.arrivals)


async def test_invalid_distance_is_ignored(fake, now, vehicles_5499):
    vehicle = copy.deepcopy(_latest(vehicles_5499, 154433200))
    vehicle["distance_from_journey_start"] = -1
    fake.vehicles = {5499: [vehicle]}

    response = await get_arrivals(fake, TTLCache(), ["22"], "5895", 3, now)

    assert all(not arrival.live for arrival in response.arrivals)


def test_latest_vehicles_dedupes_per_ride(vehicles_5499, now):
    latest = _latest_vehicles(vehicles_5499, now)

    assert len(latest) == 4
    assert len({row["siri_ride__id"] for row in latest}) == 4


def test_truncated_siri_stop_list_regression(trip_480, vehicles_7023, now):
    """The bus is far past its last SIRI-monitored stop; progress must come
    from distance_from_journey_start, not siri_ride_stop_id."""
    vehicle = _latest(vehicles_7023, 154428359)
    eta = _estimate_eta(_as_trip(trip_480), vehicle, 27997, now)

    assert eta is not None
    assert datetime(2026, 11, 20, 7, 45, tzinfo=UTC) < eta < datetime(
        2026, 11, 20, 7, 47, tzinfo=UTC
    )


def test_estimate_returns_none_when_target_is_behind(trip_480, vehicles_7023, now):
    vehicle = _latest(vehicles_7023, 154428359)
    # Stop 4170 is the origin; the bus is 51 km past it.
    assert _estimate_eta(_as_trip(trip_480), vehicle, 4170, now) is None


def test_estimate_returns_none_for_missing_distance(trip_480, vehicles_7023, now):
    vehicle = copy.deepcopy(_latest(vehicles_7023, 154428359))
    vehicle["distance_from_journey_start"] = None
    assert _estimate_eta(_as_trip(trip_480), vehicle, 27997, now) is None
