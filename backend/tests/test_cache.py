from __future__ import annotations

import pytest

from app.cache import TTLCache


async def test_returns_stale_value_when_factory_fails():
    cache = TTLCache()
    calls = {"count": 0}

    async def first():
        calls["count"] += 1
        return ["ok"]

    assert await cache.get_or_set(
        "k", ttl=0, factory=first, stale_ok_seconds=60
    ) == ["ok"]

    async def fails():
        raise RuntimeError("upstream down")

    assert await cache.get_or_set(
        "k", ttl=0, factory=fails, stale_ok_seconds=60
    ) == ["ok"]
    assert calls["count"] == 1


async def test_raises_when_stale_fallback_is_disabled():
    cache = TTLCache()

    async def fails():
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        await cache.get_or_set("k", ttl=10, factory=fails)


async def test_fresh_hit_does_not_call_the_factory():
    cache = TTLCache()
    calls = {"count": 0}

    async def factory():
        calls["count"] += 1
        return 42

    assert await cache.get_or_set("k", ttl=10, factory=factory) == 42
    assert await cache.get_or_set("k", ttl=10, factory=factory) == 42
    assert calls["count"] == 1
