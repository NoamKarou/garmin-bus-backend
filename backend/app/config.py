"""Runtime configuration for the Garmin bus backend."""

from __future__ import annotations

import os
from datetime import timedelta

# Open Bus Stride API. No auth, no /api/v1 prefix.
STRIDE_BASE_URL = os.getenv(
    "STRIDE_BASE_URL", "https://open-bus-stride-api.hasadna.org.il"
).rstrip("/")

# HTTP client timeouts (seconds).
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "4.0"))
HTTP_CONNECT_TIMEOUT = float(os.getenv("HTTP_CONNECT_TIMEOUT", "2.0"))

# Upstream query windows.
SCHEDULE_LOOKBACK = timedelta(minutes=30)   # catch delayed buses
SCHEDULE_LOOKAHEAD = timedelta(hours=3)
LIVE_LOOKBACK = timedelta(minutes=10)       # SIRI data is ~1-2 min old
LIVE_LOOKAHEAD = timedelta(minutes=2)       # tolerate feed clock skew

# Output window.
OUTPUT_LOOKBACK = timedelta(seconds=60)
OUTPUT_LOOKAHEAD = timedelta(minutes=120)

# Live ETA sanity bounds.
LIVE_MAX_FUTURE = timedelta(hours=3)
LIVE_MAX_DELAY_VS_SCHEDULE = timedelta(minutes=45)
LIVE_STALE_AFTER = timedelta(minutes=10)
LIVE_AT_STOP_METERS = 100.0
LIVE_NEXT_STOP_SLACK_METERS = 25.0
LIVE_MAX_DISTANCE_TO_NEXT_STOP = 3_000.0
LIVE_MIN_SPEED_MPS = 1.5
LIVE_GROUND_SPEED_KMH = 5.0
LIVE_MAX_TIME_TO_NEXT = timedelta(minutes=20)

# Cache TTLs (seconds).
CACHE_TTL_STOP = 3600
CACHE_TTL_ROUTES = 300
CACHE_TTL_SCHEDULE = 20
CACHE_TTL_TRIP = 600
CACHE_TTL_VEHICLES = 10
CACHE_MAX_ENTRIES = 512

# Request validation.
MAX_LINES = 5
DEFAULT_LIMIT = 3
MAX_LIMIT = 10
