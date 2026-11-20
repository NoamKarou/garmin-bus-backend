from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.errors import UpstreamError
from app.stride import StrideClient

BASE = "https://open-bus-stride-api.hasadna.org.il"
START = datetime(2026, 11, 20, 7, 29, tzinfo=timezone.utc)
END = datetime(2026, 11, 20, 7, 41, tzinfo=timezone.utc)


async def test_vehicle_query_passes_both_time_bounds():
    async with httpx.AsyncClient() as http:
        client = StrideClient(client=http)
        with respx.mock:
            route = respx.get(f"{BASE}/siri_vehicle_locations/list").mock(
                return_value=httpx.Response(200, json=[])
            )
            await client.list_vehicle_locations(7023, START, END)

        request = route.calls.last.request
        params = request.url.params
        assert params["siri_routes__line_ref"] == "7023"
        assert "recorded_at_time_from" in params
        assert "recorded_at_time_to" in params
        assert params["order_by"] == "id desc"


async def test_schedule_query_passes_required_arrival_window():
    async with httpx.AsyncClient() as http:
        client = StrideClient(client=http)
        with respx.mock:
            route = respx.get(f"{BASE}/gtfs_ride_stops/list").mock(
                return_value=httpx.Response(200, json=[])
            )
            await client.list_ride_stops_at_station("4170", "480", START, END)

        params = route.calls.last.request.url.params
        assert params["gtfs_stop__code"] == "4170"
        assert params["gtfs_route__route_short_name"] == "480"
        assert params["arrival_time_from"].endswith("+00:00")
        assert params["arrival_time_to"].endswith("+00:00")
        assert params["order_by"] == "arrival_time"


async def test_retries_once_on_503():
    async with httpx.AsyncClient() as http:
        client = StrideClient(client=http)
        with respx.mock:
            route = respx.get(f"{BASE}/gtfs_stops/list").mock(
                side_effect=[
                    httpx.Response(503),
                    httpx.Response(200, json=[{"code": 4170}]),
                ]
            )
            result = await client._get("gtfs_stops/list", {"code": "4170"})

        assert result == [{"code": 4170}]
        assert route.call_count == 2


async def test_does_not_retry_on_404():
    async with httpx.AsyncClient() as http:
        client = StrideClient(client=http)
        with respx.mock:
            route = respx.get(f"{BASE}/gtfs_stops/list").mock(
                return_value=httpx.Response(404, json={"detail": "nope"})
            )
            with pytest.raises(UpstreamError):
                await client._get("gtfs_stops/list", {"code": "0"})

        assert route.call_count == 1
