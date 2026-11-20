"""Deterministic, offline stand-in for Stride (enable with ``MOCK_MODE=1``).

``MockStrideClient`` implements the same async interface as
:class:`app.stride.StrideClient`, so the whole arrivals pipeline (schedule,
live overlay, caching) runs unchanged -- it just reads generated data instead of
the network. Every line and station code is accepted.

The data is relative to the query window, not frozen in the past, so
``minutes`` counts down like the real thing while developing the watch app:

* a trip arrives at the requested station every 10 minutes;
* one vehicle is in range of the first upcoming trip, producing a ``live: true``
  arrival; later arrivals are schedule-only;
* a stop code shared by several lines is fine -- each line gets its own route.

``ride_id`` values encode the station, route and arrival minute, so
``list_trip_stops`` can rebuild a trip without storing any state.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from . import config

# Shape of a generated trip: the requested station is stop 4 of 8.
STOPS_PER_TRIP = 8
STATION_SEQ = 4
STOP_GAP = timedelta(minutes=3)
STOP_SPACING_M = 1_000.0

# Service pattern and vehicle.
HEADWAY = timedelta(minutes=10)
SPEED_KMH = 25.0
LAT = 32.0853
LON = 34.7818
CITY = "Mock City"

# Bound the generated rows for an unusually wide query window.
MAX_SCHEDULE_ROWS = 500


@dataclass(frozen=True)
class _Departure:
    start: datetime
    arrival: datetime
    ride_id: int


def _line_ref(line: str) -> int:
    return zlib.crc32(f"line:{line}".encode()) & 0x7FFFFFFF or 1


def _station_name(station: str) -> str:
    return f"Mock Station {station}"


def _ride_id(station: str, line: str, arrival: datetime) -> int:
    """Encode station, route and arrival minute into a GTFS-like integer id."""
    epoch_min = int(arrival.timestamp()) // 60
    return (
        (int(station) << 63)
        | (_line_ref(line) << 32)
        | (epoch_min & 0xFFFFFFFF)
    )


def _decode_ride_id(ride_id: int) -> tuple[str, datetime]:
    station = str(ride_id >> 63)
    arrival = datetime.fromtimestamp(
        (ride_id & 0xFFFFFFFF) * 60, tz=timezone.utc
    )
    return station, arrival


def _arrival_grid(start: datetime, end: datetime) -> list[datetime]:
    """Arrivals on a fixed 10-minute grid inside ``[start, end]``."""
    step = int(HEADWAY.total_seconds())
    first = int(start.timestamp())
    first += (-first) % step  # round up to the next grid boundary
    last = int(end.timestamp())
    return [
        datetime.fromtimestamp(t, tz=timezone.utc)
        for t in range(first, last + 1, step)
    ][:MAX_SCHEDULE_ROWS]


class MockStrideClient:
    """In-memory fake of :class:`app.stride.StrideClient`."""

    def __init__(self) -> None:
        # line_ref -> departures seen by the most recent schedule query
        self._departures: dict[int, list[_Departure]] = {}

    async def aclose(self) -> None:
        return None

    async def list_stops(
        self, code: str, date_from: Any, date_to: Any
    ) -> list[dict[str, Any]]:
        return [
            {
                "code": code,
                "name": _station_name(code),
                "city": CITY,
                "lat": LAT,
                "lon": LON,
            }
        ]

    async def list_routes(
        self, short_name: str, date_from: Any, date_to: Any
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": _line_ref(short_name),
                "line_ref": _line_ref(short_name),
                "route_short_name": short_name,
            }
        ]

    async def list_ride_stops_at_station(
        self,
        station_code: str,
        line: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        station = str(station_code)
        line_ref = _line_ref(line)
        rows: list[dict[str, Any]] = []
        departures: list[_Departure] = []

        for arrival in _arrival_grid(start, end):
            trip_start = arrival - (STATION_SEQ - 1) * STOP_GAP
            ride_id = _ride_id(station, line, arrival)
            departures.append(_Departure(trip_start, arrival, ride_id))
            rows.append(
                {
                    "gtfs_ride_id": ride_id,
                    "gtfs_route__line_ref": line_ref,
                    "gtfs_ride__start_time": trip_start.isoformat(),
                    "arrival_time": arrival.isoformat(),
                    "departure_time": arrival.isoformat(),
                    "stop_sequence": STATION_SEQ,
                    "pickup_type": 0,
                    "gtfs_stop__code": int(station),
                    "gtfs_stop__name": _station_name(station),
                    "gtfs_stop__city": CITY,
                }
            )

        # Remember the latest schedule so vehicles can target an upcoming trip.
        self._departures[line_ref] = departures
        return rows

    async def list_trip_stops(
        self, gtfs_ride_id: int
    ) -> list[dict[str, Any]]:
        station, arrival = _decode_ride_id(gtfs_ride_id)
        station_code = int(station)
        rows: list[dict[str, Any]] = []
        for seq in range(1, STOPS_PER_TRIP + 1):
            planned = arrival + (seq - STATION_SEQ) * STOP_GAP
            if seq == STATION_SEQ:
                code = station_code
            else:
                code = 900_000_000 + seq
                if code == station_code:  # never duplicate the target stop
                    code += 100
            rows.append(
                {
                    "gtfs_ride_id": gtfs_ride_id,
                    "stop_sequence": seq,
                    "gtfs_stop__code": code,
                    "arrival_time": planned.isoformat(),
                    "departure_time": planned.isoformat(),
                    "shape_dist_traveled": (seq - 1) * STOP_SPACING_M,
                }
            )
        return rows

    async def list_vehicle_locations(
        self, line_ref: int, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        departures = self._departures.get(line_ref)
        if not departures:
            return []

        # end is now + LIVE_LOOKAHEAD, so this is the request's "now".
        now = end - config.LIVE_LOOKAHEAD
        upcoming = [departure for departure in departures if departure.arrival > now]
        if not upcoming:
            return []
        target = min(upcoming, key=lambda departure: departure.arrival)

        recorded = now - timedelta(seconds=15)
        target_dist = (STATION_SEQ - 1) * STOP_SPACING_M
        speed_mps = SPEED_KMH / 3.6
        remaining_s = max((target.arrival - recorded).total_seconds(), 0.0)

        # Place the vehicle exactly far enough back that the estimated ETA
        # lands on the scheduled arrival.
        distance = max(0.0, target_dist - speed_mps * remaining_s)

        return [
            {
                "siri_ride__id": target.ride_id,
                "siri_ride__scheduled_start_time": target.start.isoformat(),
                "recorded_at_time": recorded.isoformat(),
                "distance_from_journey_start": round(distance, 1),
                "velocity": SPEED_KMH,
                "lat": LAT,
                "lon": LON,
            }
        ]
