"""Thin async client over the Open Bus Stride API."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any

import httpx

from . import config
from .errors import UpstreamError
from .timeutil import stride_dt

logger = logging.getLogger(__name__)


class StrideClient:
    def __init__(
        self,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or config.STRIDE_BASE_URL).rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                config.HTTP_TIMEOUT, connect=config.HTTP_CONNECT_TIMEOUT
            ),
            headers={"User-Agent": "garmin-bus-backend/0.1"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                response = await self._client.get(url, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise UpstreamError(f"Stride request failed: {url}") from exc

            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 0:
                    await asyncio.sleep(0.5 if response.status_code == 429 else 0.25)
                    continue
                raise UpstreamError(
                    f"Stride returned {response.status_code}: {url}",
                    status=response.status_code,
                )

            if response.status_code >= 400:
                raise UpstreamError(
                    f"Stride returned {response.status_code}: {url}",
                    status=response.status_code,
                )

            try:
                return response.json()
            except ValueError as exc:
                raise UpstreamError(f"Stride returned invalid JSON: {url}") from exc

        raise UpstreamError(f"Stride request failed: {url}") from last_error

    async def list_stops(
        self, code: str, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        return await self._get(
            "gtfs_stops/list",
            {
                "code": code,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "order_by": "date desc",
                "limit": 50,
            },
        )

    async def list_routes(
        self, short_name: str, date_from: date, date_to: date
    ) -> list[dict[str, Any]]:
        return await self._get(
            "gtfs_routes/list",
            {
                "route_short_name": short_name,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "limit": 50,
            },
        )

    async def list_ride_stops_at_station(
        self,
        station_code: str,
        line: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        # No service-date filter: the arrival window alone avoids midnight/DST bugs.
        return await self._get(
            "gtfs_ride_stops/list",
            {
                "gtfs_stop__code": station_code,
                "gtfs_route__route_short_name": line,
                "arrival_time_from": stride_dt(start),
                "arrival_time_to": stride_dt(end),
                "order_by": "arrival_time",
                "limit": 100,
            },
        )

    async def list_trip_stops(self, gtfs_ride_id: int) -> list[dict[str, Any]]:
        return await self._get(
            "gtfs_ride_stops/list",
            {
                "gtfs_ride_ids": gtfs_ride_id,
                "order_by": "stop_sequence",
                "limit": 200,
            },
        )

    async def list_vehicle_locations(
        self, line_ref: int, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        # Both time bounds are mandatory for the fast query plan.
        return await self._get(
            "siri_vehicle_locations/list",
            {
                "siri_routes__line_ref": line_ref,
                "recorded_at_time_from": stride_dt(start),
                "recorded_at_time_to": stride_dt(end),
                "order_by": "id desc",
                "limit": 200,
            },
        )
