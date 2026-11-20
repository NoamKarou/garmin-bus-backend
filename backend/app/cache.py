"""A tiny async TTL cache with single-flight and optional stale-on-error."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any

Value = Any
Factory = Callable[[], Awaitable[Value]]


class TTLCache:
    """Bounded in-memory cache.

    A miss runs the factory once per key at a time. With ``stale_ok_seconds``, a
    failed factory falls back to the last stored value (if it is young enough),
    which keeps a transient upstream outage from turning into an API error.
    """

    def __init__(self, max_entries: int = 512) -> None:
        self._max_entries = max_entries
        # key -> (expires_at, written_at, value)
        self._entries: dict[Hashable, tuple[float, float, Value]] = {}
        self._locks: dict[Hashable, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    def clear(self) -> None:
        self._entries.clear()
        self._locks.clear()

    def _get_fresh(self, key: Hashable, now: float) -> tuple[bool, Value]:
        entry = self._entries.get(key)
        if entry is not None and entry[0] > now:
            return True, entry[2]
        return False, None

    async def get_or_set(
        self,
        key: Hashable,
        ttl: float,
        factory: Factory,
        *,
        stale_ok_seconds: float = 0.0,
    ) -> Value:
        hit, value = self._get_fresh(key, time.monotonic())
        if hit:
            return value

        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock

        async with lock:
            now = time.monotonic()
            hit, value = self._get_fresh(key, now)
            if hit:
                return value

            try:
                value = await factory()
            except Exception:
                entry = self._entries.get(key)
                if (
                    entry is not None
                    and stale_ok_seconds > 0
                    and now - entry[1] <= stale_ok_seconds
                ):
                    return entry[2]
                raise

            written = time.monotonic()
            self._entries[key] = (written + ttl, written, value)
            self._evict_if_needed()
            return value

    def _evict_if_needed(self) -> None:
        if len(self._entries) <= self._max_entries:
            return
        overflow = len(self._entries) - self._max_entries
        for key, _ in sorted(self._entries.items(), key=lambda item: item[1][0])[:overflow]:
            self._entries.pop(key, None)
            self._locks.pop(key, None)
