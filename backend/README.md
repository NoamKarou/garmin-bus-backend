# Garmin Bus Backend

A small FastAPI service that answers one question: **when does bus line `<X>`
arrive at station `<Y>`?** It combines the published GTFS schedule with live SIRI
vehicle positions from the free
[Open Bus Stride API](https://open-bus-stride-api.hasadna.org.il/docs).

The Garmin watch app calls this service; it does not talk to Stride directly.

## Requirements

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/)

`backend/.python-version` pins 3.12 for this project. uv installs/manages the
interpreter if needed.

## Quick start

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Then:

```bash
curl "http://127.0.0.1:8000/arrivals?lines=480&station=4170&limit=3"
```

Interactive docs: <http://127.0.0.1:8000/docs>

### Mock mode (offline development)

Set `MOCK_MODE=1` to serve generated in-memory bus data instead of calling
Stride. This needs no network access and works without real bus data:

```bash
MOCK_MODE=1 uv run uvicorn app.main:app --reload --port 8000
```

PowerShell:

```powershell
$env:MOCK_MODE = "1"; uv run uvicorn app.main:app --reload --port 8000
```

In mock mode:

- every line number and stop code is accepted (`/station?station=12345` works);
- a bus arrives at the requested station every 10 minutes, on a 10-minute clock
  grid;
- the first upcoming trip has a simulated SIRI vehicle position, so it returns
  `"live": true`; later arrivals are schedule-only;
- times are generated relative to the current time, so the countdown in the
  watch app ticks down normally;
- `GET /` reports `"mode": "mock"`.

Everything else (validation, errors, response shape, caching) is unchanged, and
the whole arrivals pipeline -- schedule plus live overlay -- runs against the
fake client. Never enable `MOCK_MODE` on a deployed instance.

### Live smoke test

This hits the real Stride API (not the fixtures) and prints the arrivals:

```bash
uv run python scripts/smoke.py --line 480 --station 4170
uv run python scripts/smoke.py --line 22 --station 6214 --limit 4
```

A `LIVE` flag means the ETA came from a recent SIRI vehicle position; `SCHEDULE`
means the GTFS timetable only.

## API

### `GET /arrivals`

| Parameter | Required | Description |
|---|---|---|
| `lines` | yes | Comma-separated public line numbers, 1–5 values (e.g. `480` or `480,74`). |
| `station` | yes | MOT stop code printed on the stop sign (1–10 digits, e.g. `4170`). |
| `limit` | no | Max arrivals per line, 1–10 (default 3). |

Example response:

```json
{
  "station": {
    "code": "4170",
    "name": "ת. מרכזית ירושלים קומה 3/רציפים",
    "city": "ירושלים"
  },
  "queried_at": "2026-11-20T07:53:49.705714Z",
  "queried_at_epoch_sec": 1795161229,
  "arrivals": [
    {
      "line": "480",
      "minutes": 7,
      "arrival_time": "2026-11-20T08:00:00Z",
      "arrival_epoch_sec": 1795161600,
      "live": false
    }
  ]
}
```

- `minutes` is ceil((arrival − queried_at) / 60), clamped at 0.
- `arrival_epoch_sec` / `queried_at_epoch_sec` let the watch recompute `minutes`
  from a cached response without parsing ISO strings, and fit the watch's 32-bit
  `Number`.
- `live: true` only when a recent SIRI vehicle position produced the ETA and
  passed the sanity checks.
- `station.code` is a string so leading zeros survive.

Errors:

- `404` — unknown station, or every requested line is unknown.
- `422` — invalid parameters.
- `502` — Stride is unavailable and there is nothing usable to return.

### `GET /station`

Station name/city for a MOT stop code, without fetching any arrivals. Useful
when the watch only needs to label the configured stop.

| Parameter | Required | Description |
|---|---|---|
| `station` | yes | MOT stop code printed on the stop sign (1–10 digits, e.g. `4170`). |

Example response:

```json
{
  "code": "4170",
  "name": "ת. מרכזית ירושלים קומה 3/רציפים",
  "city": "ירושלים"
}
```

Errors:

- `404` — unknown station.
- `422` — invalid station code.
- `502` — Stride is unavailable.

The station lookup is cached for 1 h, the same entry `/arrivals` uses, so a watch
polling both endpoints hits Stride once per hour per stop.

### `GET /health`

```json
{"status": "ok"}
```

## How it works

1. **Station** — `gtfs_stops` by stop code. The API returns several duplicate
   version rows for the same physical stop; they are de-duplicated.
2. **Schedule** — `gtfs_ride_stops` for the station + line in a
   `[now−30m, now+3h]` arrival window. Rows with `pickup_type == 1` are excluded
   (the bus only drops off there, so you cannot board).
3. **Live overlay** — for every route variant that serves the station:
   - recent `siri_vehicle_locations` for that `line_ref`
     (`[now−10m, now+2m]`; **both** time bounds are required for a fast query);
   - each vehicle's `distance_from_journey_start` is a cumulative route distance
     that matches the GTFS trip's `shape_dist_traveled`;
   - the next stop ahead of the vehicle, and the target stop after it, give the
     remaining time: `recorded_at + remaining/speed + (planned(target) − planned(next))`;
   - the live ETA replaces the closest scheduled arrival on the same route
     variant, and is marked `live`.
4. If any live step fails, the request degrades to schedule-only; it never fails
   because of the live overlay.

Caching: station metadata 1 h, routes 5 min, schedule 20 s, representative trip
timetable 10 min, vehicle locations 10 s. The cache is in-process (run one
uvicorn worker).

## Tests

```bash
uv run pytest -q
```

The tests are deterministic and use captured real Stride responses from
`tests/fixtures/`; no network is required. The live smoke script is separate.

## Docker / deployment

```bash
docker build -t garmin-bus-backend .
docker run --rm -p 8000:8000 garmin-bus-backend
```

The image is based on `python:3.12-slim`, installs from `uv.lock`, and runs
uvicorn on port 8000. Any host that can run a container works (Render, Railway,
Fly, Cloud Run, a VPS…).

Environment variables:

| Variable | Default |
|---|---|
| `STRIDE_BASE_URL` | `https://open-bus-stride-api.hasadna.org.il` |
| `HTTP_TIMEOUT` | `4.0` seconds |
| `HTTP_CONNECT_TIMEOUT` | `2.0` seconds |
| `MOCK_MODE` | unset (set to `1` for offline generated data) |

**HTTPS is required for a physical Garmin watch.** `makeWebRequest` rejects plain
HTTP except to `127.0.0.1` on the phone. Use an HTTPS deployment, or a tunnel
such as `cloudflared tunnel --url http://localhost:8000`, when testing on
hardware.

## Data-source notes

- Stride has no auth and no `/api/v1` prefix.
- Descending sort is `order_by=id%20desc` ("id desc").
- `siri_vehicle_locations` is ~1–2 minutes old; ETAs are anchored to the
  vehicle's `recorded_at_time`, not the request time.
- Do not use Stride's `/stop_arrivals` endpoint: its SIRI→GTFS links are null for
  current data. This service builds the overlay itself.
- A stop code can return ~16 duplicate `gtfs_stops` rows (data versions) with
  identical metadata; schedule rows are not duplicated because they reference a
  canonical stop id.
