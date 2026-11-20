"""Domain-level errors mapped to HTTP responses in main.py."""

from __future__ import annotations


class BusError(Exception):
    """Base class for expected request failures."""


class StationNotFound(BusError):
    def __init__(self, station: str):
        super().__init__(f"station {station} was not found")
        self.station = station


class LineNotFound(BusError):
    def __init__(self, lines: list[str]):
        super().__init__(f"no known lines among: {', '.join(lines)}")
        self.lines = lines


class UpstreamError(BusError):
    """The Stride API is unavailable or returned an unusable response."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status
