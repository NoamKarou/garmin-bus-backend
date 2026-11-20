"""Live smoke test: query the real Stride API and print arrivals.

Usage (from backend/):
    uv run python scripts/smoke.py --line 480 --station 4170
    uv run python scripts/smoke.py --lines 480,74 --station 4170
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.arrivals import get_arrivals  # noqa: E402
from app.cache import TTLCache  # noqa: E402
from app.stride import StrideClient  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    raw_lines = args.lines or args.line
    lines = [line.strip() for line in raw_lines.split(",") if line.strip()]

    client = StrideClient()
    try:
        response = await get_arrivals(
            client, TTLCache(), lines, args.station, args.limit
        )
    finally:
        await client.aclose()

    station = response.station
    print(f"Station: {station.code} {station.name or ''} {station.city or ''}".rstrip())
    print(f"Queried: {response.queried_at.isoformat()}")
    if not response.arrivals:
        print("No upcoming arrivals.")
        return 1

    for arrival in response.arrivals:
        flag = "LIVE" if arrival.live else "SCHEDULE"
        print(
            f"  {arrival.line:>4}  {arrival.minutes:>3} min  "
            f"{arrival.arrival_time.astimezone().strftime('%H:%M:%S')}  {flag}"
        )
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--line", default="480")
    parser.add_argument("--lines", default=None, help="comma-separated lines")
    parser.add_argument("--station", default="4170")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
