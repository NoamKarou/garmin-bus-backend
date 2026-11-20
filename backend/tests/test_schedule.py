from __future__ import annotations

from datetime import timedelta

import pytest

from app.arrivals import get_arrivals
from app.cache import TTLCache
from app.errors import LineNotFound, StationNotFound, UpstreamError


async def test_schedule_only_returns_planned_arrivals(fake, now):
    fake.vehicles = {}
    response = await get_arrivals(fake, TTLCache(), ["480"], "4170", 3, now)

    assert response.station.code == "4170"
    assert response.station.name
    assert [a.minutes for a in response.arrivals] == [6, 21, 36]
    assert all(a.live is False for a in response.arrivals)
    assert response.arrivals[0].arrival_time == now + timedelta(minutes=6)


async def test_pickup_type_one_is_excluded(fake, now):
    # Every line-22 arrival at stop 1487 is drop-off only.
    response = await get_arrivals(fake, TTLCache(), ["22"], "1487", 3, now)

    assert response.arrivals == []


async def test_unknown_station_raises(fake, now):
    fake.stops = {}
    fake.schedule = {}

    with pytest.raises(StationNotFound):
        await get_arrivals(fake, TTLCache(), ["480"], "0000", 3, now)


async def test_unknown_line_raises(fake, now):
    fake.routes = {"999": []}
    fake.schedule = {}

    with pytest.raises(LineNotFound):
        await get_arrivals(fake, TTLCache(), ["999"], "4170", 3, now)


async def test_schedule_query_failure_raises_upstream(fake, now):
    fake.schedule[("480", "4170")] = UpstreamError("down")

    with pytest.raises(UpstreamError):
        await get_arrivals(fake, TTLCache(), ["480"], "4170", 3, now)


async def test_minutes_and_epoch_are_consistent(fake, now):
    response = await get_arrivals(fake, TTLCache(), ["480"], "4170", 3, now)

    for arrival in response.arrivals:
        assert arrival.arrival_epoch_sec == int(arrival.arrival_time.timestamp())
        delta = arrival.arrival_time - response.queried_at
        assert arrival.minutes == max(0, -(-int(delta.total_seconds()) // 60))

    assert response.queried_at_epoch_sec == int(now.timestamp())
