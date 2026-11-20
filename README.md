# Garmin Bus

A Garmin Connect IQ watch app that shows when a chosen bus line arrives at a
chosen station, backed by a small FastAPI service that reads the free
[Open Bus Stride API](https://open-bus-stride-api.hasadna.org.il/docs).

The watch shows the arrival **green** when a live SIRI vehicle position is
available, and **grey** when only the scheduled GTFS time is known.

## Repository layout

```
backend/    FastAPI service: GTFS schedule + SIRI live ETA
frontend/   Connect IQ watch app (Monkey C), targets Venu 3 / Vivoactive
```

## Quick start

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

```bash
curl "http://127.0.0.1:8000/arrivals?lines=480&station=4170&limit=3"
```

See [backend/README.md](backend/README.md) for the API, tests, Docker, and
deployment.

### Watch app

The Connect IQ SDK is required to build. See
[frontend/README.md](frontend/README.md). The short version:

1. Install the Connect IQ SDK + VS Code extension and generate a developer key.
2. Set the backend URL in `frontend/resources/settings/properties.xml`.
3. Build for `venu3` (or your device) and run it in the simulator or sideload it.

App settings (line number and station code) are edited in the Garmin Connect
mobile app once the app is installed through the store/private beta. The backend
URL is a build-time property because Connect IQ's text settings cannot reliably
type `.`, `:` and `/`.

## Configuration model

- **Line** — the public line number (e.g. `480`), configured on the watch.
- **Station** — the MOT stop code printed on the physical stop sign (e.g. `4170`).
- **Backend URL** — an HTTPS URL reachable by the phone paired to the watch.

## Important constraints

- A physical watch requires **HTTPS** for network requests; plain HTTP only works
  to `127.0.0.1` on the phone. For local testing use the simulator or an HTTPS
  tunnel (`cloudflared tunnel --url http://localhost:8000`).
- The backend is stateless; the cache is in-process, so run one uvicorn worker.
- Live data is about 1–2 minutes old. When it is unavailable or unreliable, the
  app shows the scheduled time in grey instead of guessing.
