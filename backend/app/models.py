"""HTTP response models for the watch-facing API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StationOut(BaseModel):
    code: str
    name: str | None = None
    city: str | None = None


class ArrivalOut(BaseModel):
    line: str
    minutes: int
    arrival_time: datetime
    arrival_epoch_sec: int
    live: bool


class ArrivalsResponse(BaseModel):
    station: StationOut
    queried_at: datetime
    queried_at_epoch_sec: int
    arrivals: list[ArrivalOut]
