"""FastAPI entrypoint for the Garmin bus backend."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .arrivals import get_arrivals, get_station
from .cache import TTLCache
from .errors import LineNotFound, StationNotFound, UpstreamError
from .mock import MockStrideClient
from .models import ArrivalsResponse, StationOut
from .stride import StrideClient
from .timeutil import utc_now

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _parse_lines(raw: str) -> list[str]:
    parsed: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        line = part.strip()
        if not line or line in seen or len(line) > 12:
            continue
        seen.add(line)
        parsed.append(line)
        if len(parsed) >= config.MAX_LINES:
            break
    return parsed


def _station_code(raw: str) -> str:
    """Validate a MOT stop code from a query parameter."""
    station_code = raw.strip()
    if not station_code.isdigit() or not (1 <= len(station_code) <= 10):
        raise HTTPException(
            status_code=422,
            detail="station must be a 1-10 digit MOT stop code",
        )
    return station_code


def _get_stride(request: Request) -> StrideClient:
    return request.app.state.stride


def _get_cache(request: Request) -> TTLCache:
    return request.app.state.cache


def _get_now(request: Request) -> Callable[[], datetime]:
    return request.app.state.now_provider


def create_app(
    stride_client: StrideClient | MockStrideClient | None = None,
    cache: TTLCache | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "stride", None) is None:
            if config.MOCK_MODE:
                logger.warning(
                    "MOCK_MODE is enabled: serving generated bus data, "
                    "not calling Stride"
                )
                app.state.stride = MockStrideClient()
            else:
                app.state.stride = StrideClient()
            app.state.owns_stride = True
        else:
            app.state.owns_stride = False
        if getattr(app.state, "cache", None) is None:
            app.state.cache = TTLCache(config.CACHE_MAX_ENTRIES)
        yield
        if app.state.owns_stride:
            await app.state.stride.aclose()

    app = FastAPI(
        title="Garmin Bus Backend",
        version="0.1.0",
        description=(
            "Arrival times for a bus line at a station, using the Open Bus "
            "Stride API (SIRI live + GTFS schedule)."
        ),
        lifespan=lifespan,
    )
    app.state.stride = stride_client
    app.state.cache = cache
    app.state.now_provider = now_provider or utc_now

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": "garmin-bus-backend",
            "mode": "mock" if config.MOCK_MODE else "live",
            "docs": "/docs",
            "example": "/arrivals?lines=480&station=4170&limit=3",
            "station": "/station?station=4170",
        }

    @app.get("/arrivals", response_model=ArrivalsResponse)
    async def arrivals(
        lines: str = Query(..., description="Comma-separated line numbers"),
        station: str = Query(..., description="MOT stop code"),
        limit: int = Query(
            config.DEFAULT_LIMIT, ge=1, le=config.MAX_LIMIT
        ),
        stride: StrideClient = Depends(_get_stride),
        cache: TTLCache = Depends(_get_cache),
        now_provider: Callable[[], datetime] = Depends(_get_now),
    ) -> ArrivalsResponse:
        parsed_lines = _parse_lines(lines)
        if not parsed_lines:
            raise HTTPException(
                status_code=422, detail="lines must contain at least one line number"
            )

        station_code = _station_code(station)

        try:
            return await get_arrivals(
                stride, cache, parsed_lines, station_code, limit, now=now_provider()
            )
        except (StationNotFound, LineNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except UpstreamError as exc:
            logger.warning("upstream failure: %s", exc)
            raise HTTPException(
                status_code=502, detail="upstream bus data is unavailable"
            ) from exc

    @app.get("/station", response_model=StationOut)
    async def station_metadata(
        station: str = Query(..., description="MOT stop code"),
        stride: StrideClient = Depends(_get_stride),
        cache: TTLCache = Depends(_get_cache),
        now_provider: Callable[[], datetime] = Depends(_get_now),
    ) -> StationOut:
        station_code = _station_code(station)

        try:
            info = await get_station(
                stride, cache, station_code, now=now_provider()
            )
        except StationNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except UpstreamError as exc:
            logger.warning("upstream failure: %s", exc)
            raise HTTPException(
                status_code=502, detail="upstream bus data is unavailable"
            ) from exc

        return StationOut(code=info.code, name=info.name, city=info.city)

    return app


app = create_app()
