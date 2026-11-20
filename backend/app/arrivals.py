"""Orchestration: station resolution, GTFS schedule, and the SIRI live overlay."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from . import config
from .cache import TTLCache
from .errors import LineNotFound, StationNotFound, UpstreamError
from .geo import haversine_m
from .models import ArrivalOut, ArrivalsResponse, StationOut
from .stride import StrideClient
from .timeutil import (
    epoch_sec,
    local_today,
    minutes_until,
    parse_dt,
    utc_now,
)

logger = logging.getLogger(__name__)


@dataclass
class StationInfo:
    code: str
    name: str | None = None
    city: str | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass
class ScheduleRow:
    line: str
    line_ref: int
    gtfs_ride_id: int
    start_time: datetime
    planned: datetime
    stop_sequence: int | None
    live: bool = False
    effective: datetime | None = None


@dataclass(frozen=True)
class TripStop:
    seq: int
    code: int
    planned: datetime
    dist: float
    lat: float | None
    lon: float | None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _resolve_station(
    client: StrideClient,
    cache: TTLCache,
    station: str,
    today,
) -> StationInfo | None:
    rows = await cache.get_or_set(
        ("stops", station, today.isoformat()),
        config.CACHE_TTL_STOP,
        lambda: client.list_stops(station, today - timedelta(days=30), today),
        stale_ok_seconds=86_400,
    )
    if not rows:
        return None
    # The same physical stop has many version rows with identical metadata.
    latest = rows[0]
    return StationInfo(
        code=str(station),
        name=latest.get("name"),
        city=latest.get("city"),
        lat=_as_float(latest.get("lat")),
        lon=_as_float(latest.get("lon")),
    )


async def get_station(
    client: StrideClient,
    cache: TTLCache,
    station_code: str,
    now: datetime | None = None,
) -> StationInfo:
    """Station metadata (name, city) for a MOT stop code."""
    now = now or utc_now()
    station = await _resolve_station(
        client, cache, station_code, local_today(now)
    )
    if station is None:
        raise StationNotFound(station_code)
    return station


async def _line_exists(
    client: StrideClient, cache: TTLCache, line: str, today
) -> bool:
    rows = await cache.get_or_set(
        ("routes", line, today.isoformat()),
        config.CACHE_TTL_ROUTES,
        lambda: client.list_routes(line, today, today),
        stale_ok_seconds=86_400,
    )
    return bool(rows)


async def _fetch_schedule(
    client: StrideClient,
    cache: TTLCache,
    line: str,
    station: str,
    start: datetime,
    end: datetime,
    today,
) -> list[dict[str, Any]]:
    return await cache.get_or_set(
        ("schedule", line, station, today.isoformat()),
        config.CACHE_TTL_SCHEDULE,
        lambda: client.list_ride_stops_at_station(station, line, start, end),
        stale_ok_seconds=600,
    )


def _build_schedule_rows(
    line: str, rows: list[dict[str, Any]]
) -> list[ScheduleRow]:
    out: list[ScheduleRow] = []
    seen: set[tuple[int, int | None]] = set()
    for row in rows:
        if _as_int(row.get("pickup_type")) == 1:
            continue  # drop-off only: passengers cannot board
        ride_id = _as_int(row.get("gtfs_ride_id"))
        line_ref = _as_int(row.get("gtfs_route__line_ref"))
        planned = parse_dt(row.get("arrival_time")) or parse_dt(
            row.get("departure_time")
        )
        if ride_id is None or line_ref is None or planned is None:
            continue
        stop_sequence = _as_int(row.get("stop_sequence"))
        key = (ride_id, stop_sequence)
        if key in seen:
            continue
        seen.add(key)
        start_time = parse_dt(row.get("gtfs_ride__start_time")) or planned
        out.append(
            ScheduleRow(
                line=line,
                line_ref=line_ref,
                gtfs_ride_id=ride_id,
                start_time=start_time,
                planned=planned,
                stop_sequence=stop_sequence,
            )
        )
    return out


async def _trip_stops(
    client: StrideClient, cache: TTLCache, ride_id: int
) -> list[TripStop]:
    rows = await cache.get_or_set(
        ("trip", ride_id),
        config.CACHE_TTL_TRIP,
        lambda: client.list_trip_stops(ride_id),
        stale_ok_seconds=3600,
    )
    stops: list[TripStop] = []
    for row in rows:
        seq = _as_int(row.get("stop_sequence"))
        code = _as_int(row.get("gtfs_stop__code"))
        planned = (
            parse_dt(row.get("arrival_time"))
            or parse_dt(row.get("departure_time"))
            or parse_dt(row.get("gtfs_ride__start_time"))
        )
        if seq is None or code is None or planned is None:
            continue
        dist = _as_float(row.get("shape_dist_traveled"))
        stops.append(
            TripStop(
                seq=seq,
                code=code,
                planned=planned,
                dist=dist if dist is not None else 0.0,
                lat=_as_float(row.get("gtfs_stop__lat")),
                lon=_as_float(row.get("gtfs_stop__lon")),
            )
        )
    stops.sort(key=lambda s: s.seq)
    return stops


def _trip_has_distances(trip: list[TripStop]) -> bool:
    return len(trip) >= 2 and sum(1 for s in trip if s.dist > 0) >= 1


def _station_from_schedule(
    station_code: str, schedule_by_line: dict[str, list[dict[str, Any]]]
) -> StationInfo:
    counts: Counter[tuple[str | None, str | None]] = Counter()
    for rows in schedule_by_line.values():
        for row in rows:
            counts[(row.get("gtfs_stop__name"), row.get("gtfs_stop__city"))] += 1
    if not counts:
        return StationInfo(code=station_code)
    (name, city), _ = counts.most_common(1)[0]
    return StationInfo(code=station_code, name=name, city=city)


def _refine_station(
    station: StationInfo,
    all_rows: list[dict[str, Any]],
) -> StationInfo:
    """Prefer the name/city of the schedule rows when a code is shared."""
    counts: Counter[tuple[str | None, str | None]] = Counter()
    for row in all_rows:
        counts[(row.get("gtfs_stop__name"), row.get("gtfs_stop__city"))] += 1
    if not counts:
        return station
    (name, city), count = counts.most_common(1)[0]
    if not name or count < 2:
        return station
    if (station.name, station.city) == (name, city):
        return station
    return StationInfo(
        code=station.code,
        name=name,
        city=city,
        lat=station.lat,
        lon=station.lon,
    )


def _latest_vehicles(
    rows: list[dict[str, Any]], now: datetime
) -> list[dict[str, Any]]:
    latest: dict[int, tuple[datetime, dict[str, Any]]] = {}
    stale_before = now - config.LIVE_STALE_AFTER
    for row in rows:
        ride_id = _as_int(row.get("siri_ride__id"))
        recorded = parse_dt(row.get("recorded_at_time"))
        if ride_id is None or recorded is None or recorded < stale_before:
            continue
        previous = latest.get(ride_id)
        if previous is None or recorded > previous[0]:
            latest[ride_id] = (recorded, row)
    return [row for _, row in latest.values()]


def _match_schedule_row(
    rows: list[ScheduleRow], vehicle: dict[str, Any]
) -> ScheduleRow:
    representative = min(rows, key=lambda row: row.start_time)
    scheduled = parse_dt(vehicle.get("siri_ride__scheduled_start_time"))
    if scheduled is None:
        return representative
    best = min(
        rows,
        key=lambda row: abs((row.start_time - scheduled).total_seconds()),
    )
    if abs((best.start_time - scheduled).total_seconds()) <= 30 * 60:
        return best
    return representative


def _clamp_eta(
    eta: datetime, now: datetime, planned_target: datetime
) -> datetime | None:
    if eta < now - timedelta(seconds=30):
        return None
    if eta < now + timedelta(seconds=30):
        eta = now + timedelta(seconds=30)
    if eta > now + config.LIVE_MAX_FUTURE:
        return None
    if eta > planned_target + config.LIVE_MAX_DELAY_VS_SCHEDULE:
        return None
    return eta


def _estimate_eta(
    trip: list[TripStop],
    vehicle: dict[str, Any],
    station_code: int,
    now: datetime,
) -> datetime | None:
    vdist = _as_float(vehicle.get("distance_from_journey_start"))
    recorded = parse_dt(vehicle.get("recorded_at_time"))
    if vdist is None or vdist < 0 or recorded is None:
        return None
    if recorded < now - config.LIVE_STALE_AFTER:
        return None

    targets = [stop for stop in trip if stop.code == station_code]
    if not targets:
        return None

    # Is the bus already at the target?
    at_target = min(targets, key=lambda stop: abs(stop.dist - vdist))
    if abs(at_target.dist - vdist) <= config.LIVE_AT_STOP_METERS:
        return _clamp_eta(recorded + timedelta(seconds=30), now, at_target.planned)

    slack = config.LIVE_NEXT_STOP_SLACK_METERS
    ahead = [stop for stop in trip if stop.dist > vdist + slack]
    if not ahead:
        return None
    next_stop = ahead[0]

    target = next((stop for stop in targets if stop.dist > vdist + slack), None)
    if target is None:
        return None  # the target is behind the bus

    vlat = _as_float(vehicle.get("lat"))
    vlon = _as_float(vehicle.get("lon"))
    if (
        vlat is not None
        and vlon is not None
        and next_stop.lat is not None
        and next_stop.lon is not None
    ):
        straight = haversine_m(vlat, vlon, next_stop.lat, next_stop.lon)
        remaining_route = max(next_stop.dist - vdist, 0.0)
        if straight > remaining_route * 1.5 + config.LIVE_MAX_DISTANCE_TO_NEXT_STOP:
            return None  # vehicle is not plausibly on this route

    velocity_kmh = _as_float(vehicle.get("velocity")) or 0.0
    if velocity_kmh >= config.LIVE_GROUND_SPEED_KMH:
        speed_mps = max(velocity_kmh / 3.6, config.LIVE_MIN_SPEED_MPS)
        time_to_next = timedelta(seconds=max(next_stop.dist - vdist, 0.0) / speed_mps)
    else:
        # Stopped/dwelling: trust the timetable for the next hop.
        time_to_next = next_stop.planned - recorded
        if time_to_next < timedelta(seconds=60):
            time_to_next = timedelta(seconds=60)

    if time_to_next > config.LIVE_MAX_TIME_TO_NEXT:
        time_to_next = config.LIVE_MAX_TIME_TO_NEXT
    if time_to_next < timedelta(0):
        time_to_next = timedelta(0)

    segment = target.planned - next_stop.planned
    eta = recorded + time_to_next + segment
    return _clamp_eta(eta, now, target.planned)


async def _overlay_ref(
    client: StrideClient,
    cache: TTLCache,
    line_ref: int,
    rows: list[ScheduleRow],
    station_code: int,
    now: datetime,
) -> list[tuple[datetime, dict[str, Any], int]]:
    vehicle_rows = await cache.get_or_set(
        ("vehicles", line_ref),
        config.CACHE_TTL_VEHICLES,
        lambda: client.list_vehicle_locations(
            line_ref,
            now - config.LIVE_LOOKBACK,
            now + config.LIVE_LOOKAHEAD,
        ),
    )
    vehicles = _latest_vehicles(vehicle_rows, now)
    if not vehicles:
        return []

    trips: dict[int, list[TripStop]] = {}
    attachments: list[tuple[datetime, dict[str, Any], int]] = []
    for vehicle in vehicles:
        matched = _match_schedule_row(rows, vehicle)
        trip = trips.get(matched.gtfs_ride_id)
        if trip is None:
            try:
                trip = await _trip_stops(client, cache, matched.gtfs_ride_id)
            except UpstreamError as exc:
                logger.warning("trip %s unavailable: %s", matched.gtfs_ride_id, exc)
                continue
            trips[matched.gtfs_ride_id] = trip
        if not _trip_has_distances(trip):
            continue
        eta = _estimate_eta(trip, vehicle, station_code, now)
        if eta is not None:
            attachments.append((eta, vehicle, line_ref))
    return attachments


async def get_arrivals(
    client: StrideClient,
    cache: TTLCache,
    lines: list[str],
    station_code: str,
    limit: int = config.DEFAULT_LIMIT,
    now: datetime | None = None,
) -> ArrivalsResponse:
    now = now or utc_now()
    today = local_today(now)
    window_start = now - config.SCHEDULE_LOOKBACK
    window_end = now + config.SCHEDULE_LOOKAHEAD

    station_task = asyncio.create_task(
        _resolve_station(client, cache, station_code, today)
    )
    route_tasks = {
        line: asyncio.create_task(_line_exists(client, cache, line, today))
        for line in lines
    }
    schedule_tasks = {
        line: asyncio.create_task(
            _fetch_schedule(
                client, cache, line, station_code, window_start, window_end, today
            )
        )
        for line in lines
    }

    station_error: UpstreamError | None = None
    try:
        station = await station_task
    except UpstreamError as exc:
        station = None
        station_error = exc

    schedule_by_line: dict[str, list[dict[str, Any]]] = {}
    schedule_errors: list[UpstreamError] = []
    for line, task in schedule_tasks.items():
        try:
            schedule_by_line[line] = await task
        except UpstreamError as exc:
            schedule_errors.append(exc)
            schedule_by_line[line] = []

    line_status: dict[str, bool | None] = {}
    line_errors: list[UpstreamError] = []
    for line, task in route_tasks.items():
        try:
            line_status[line] = await task
        except UpstreamError as exc:
            line_errors.append(exc)
            line_status[line] = None

    any_schedule = any(schedule_by_line.values())

    # Every schedule query failed upstream: this is a 502, not an empty day.
    if not any_schedule and schedule_errors and len(schedule_errors) == len(lines):
        raise schedule_errors[0]

    if station is None:
        if any_schedule:
            station = _station_from_schedule(station_code, schedule_by_line)
        elif station_error is not None:
            raise station_error
        else:
            raise StationNotFound(station_code)

    known_lines = [line for line in lines if line_status.get(line)]
    if not known_lines and not any_schedule:
        if line_errors and len(line_errors) == len(lines):
            raise line_errors[0]
        raise LineNotFound(lines)

    schedule_rows: list[ScheduleRow] = []
    all_rows: list[dict[str, Any]] = []
    for line in lines:
        rows = schedule_by_line.get(line, [])
        all_rows.extend(rows)
        schedule_rows.extend(_build_schedule_rows(line, rows))

    station = _refine_station(station, all_rows)

    # --- live overlay -----------------------------------------------------
    by_ref: dict[int, list[ScheduleRow]] = defaultdict(list)
    for row in schedule_rows:
        by_ref[row.line_ref].append(row)

    if by_ref:
        station_numeric = _as_int(station_code)
        if station_numeric is not None:
            async def overlay(
                ref: int, ref_rows: list[ScheduleRow]
            ) -> list[tuple[datetime, dict[str, Any], int]]:
                try:
                    return await _overlay_ref(
                        client, cache, ref, ref_rows, station_numeric, now
                    )
                except Exception as exc:  # live data must never break the response
                    logger.warning("live overlay failed for line_ref %s: %s", ref, exc)
                    return []

            results = await asyncio.gather(
                *(overlay(ref, ref_rows) for ref, ref_rows in by_ref.items())
            )
            attachments = [item for result in results for item in result]
        else:
            attachments = []

        used: set[int] = set()
        for eta, vehicle, ref in sorted(attachments, key=lambda item: item[0]):
            candidates = [
                row
                for row in by_ref.get(ref, [])
                if id(row) not in used
            ]
            if not candidates:
                continue
            best = min(
                candidates,
                key=lambda row: abs((row.planned - eta).total_seconds()),
            )
            if abs((best.planned - eta).total_seconds()) > 30 * 60:
                continue
            used.add(id(best))
            best.live = True
            best.effective = eta

    # --- output -----------------------------------------------------------
    response_arrivals: list[ArrivalOut] = []
    for line in lines:
        line_rows = [row for row in schedule_rows if row.line == line]
        for row in line_rows:
            row.effective = row.effective or row.planned
        line_rows = [
            row
            for row in line_rows
            if now - config.OUTPUT_LOOKBACK
            <= (row.effective or row.planned)
            <= now + config.OUTPUT_LOOKAHEAD
        ]
        line_rows.sort(key=lambda row: row.effective or row.planned)
        for row in line_rows[:limit]:
            effective = (row.effective or row.planned).replace(microsecond=0)
            response_arrivals.append(
                ArrivalOut(
                    line=row.line,
                    minutes=minutes_until(effective, now),
                    arrival_time=effective,
                    arrival_epoch_sec=epoch_sec(effective),
                    live=row.live,
                )
            )

    response_arrivals.sort(key=lambda arrival: arrival.arrival_time)

    return ArrivalsResponse(
        station=StationOut(
            code=station.code, name=station.name, city=station.city
        ),
        queried_at=now,
        queried_at_epoch_sec=epoch_sec(now),
        arrivals=response_arrivals,
    )
