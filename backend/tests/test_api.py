from __future__ import annotations

from fastapi.testclient import TestClient

from app.cache import TTLCache
from app.errors import UpstreamError
from app.main import create_app
from conftest import NOW, FakeStride


def _client(fake) -> TestClient:
    return TestClient(
        create_app(
            stride_client=fake,
            cache=TTLCache(),
            now_provider=lambda: NOW,
        )
    )


def _schedule_row(ride_id, line_ref, start, arrival, code="9999"):
    return {
        "gtfs_ride_id": ride_id,
        "gtfs_route__line_ref": line_ref,
        "gtfs_ride__start_time": start,
        "arrival_time": arrival,
        "departure_time": arrival,
        "stop_sequence": 1,
        "pickup_type": 0,
        "gtfs_stop__name": "Test Station",
        "gtfs_stop__city": "Test City",
        "gtfs_stop__code": int(code),
        "gtfs_stop__lat": 32.0,
        "gtfs_stop__lon": 34.8,
    }


def test_health():
    with _client(FakeStride()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_arrivals_ok(fake):
    with _client(fake) as client:
        response = client.get("/arrivals?lines=480&station=4170&limit=3")

    assert response.status_code == 200
    body = response.json()
    assert body["station"]["code"] == "4170"
    assert body["station"]["name"] == "ת. מרכזית ירושלים קומה 3/רציפים"
    assert len(body["arrivals"]) == 3
    assert [arrival["minutes"] for arrival in body["arrivals"]] == [6, 21, 36]
    assert all(arrival["live"] is False for arrival in body["arrivals"])
    assert body["queried_at_epoch_sec"] > 0
    assert body["arrivals"][0]["arrival_epoch_sec"] > body["queried_at_epoch_sec"]


def test_unknown_station_returns_404(fake):
    fake.stops = {}
    fake.schedule = {}
    with _client(fake) as client:
        response = client.get("/arrivals?lines=480&station=0000")
    assert response.status_code == 404


def test_unknown_line_returns_404(fake):
    fake.routes = {"999": []}
    fake.schedule = {}
    with _client(fake) as client:
        response = client.get("/arrivals?lines=999&station=4170")
    assert response.status_code == 404


def test_empty_arrivals_is_200(fake):
    with _client(fake) as client:
        response = client.get("/arrivals?lines=22&station=1487")
    assert response.status_code == 200
    assert response.json()["arrivals"] == []


def test_bad_station_returns_422(fake):
    with _client(fake) as client:
        response = client.get("/arrivals?lines=480&station=abc")
    assert response.status_code == 422


def test_empty_lines_returns_422(fake):
    with _client(fake) as client:
        response = client.get("/arrivals?lines=,&station=4170")
    assert response.status_code == 422


def test_limit_out_of_range_returns_422(fake):
    with _client(fake) as client:
        response = client.get("/arrivals?lines=480&station=4170&limit=11")
    assert response.status_code == 422


def test_upstream_failure_returns_502(fake):
    fake.schedule[("480", "4170")] = UpstreamError("down")
    with _client(fake) as client:
        response = client.get("/arrivals?lines=480&station=4170")
    assert response.status_code == 502


def test_station_ok(fake):
    with _client(fake) as client:
        response = client.get("/station?station=4170")

    assert response.status_code == 200
    assert response.json() == {
        "code": "4170",
        "name": "ת. מרכזית ירושלים קומה 3/רציפים",
        "city": "ירושלים",
    }
    assert ("stops", ("4170",)) in fake.calls


def test_station_trims_whitespace(fake):
    with _client(fake) as client:
        response = client.get("/station?station=%204170%20")
    assert response.status_code == 200
    assert response.json()["code"] == "4170"


def test_station_not_found_returns_404(fake):
    with _client(fake) as client:
        response = client.get("/station?station=0000")
    assert response.status_code == 404


def test_station_bad_code_returns_422(fake):
    with _client(fake) as client:
        response = client.get("/station?station=abc")
    assert response.status_code == 422


def test_station_upstream_failure_returns_502(fake):
    fake.stops = {"4170": UpstreamError("down")}
    with _client(fake) as client:
        response = client.get("/station?station=4170")
    assert response.status_code == 502


def test_multiple_lines_are_tagged():
    fake = FakeStride(
        stops={
            "9999": [
                {
                    "name": "Test Station",
                    "city": "Test City",
                    "lat": 32.0,
                    "lon": 34.8,
                }
            ]
        },
        routes={"10": [{"id": 1}], "20": [{"id": 2}]},
        schedule={
            ("10", "9999"): [
                _schedule_row(
                    1, 11, "2026-11-20T08:00:00+00:00", "2026-11-20T08:10:00+00:00"
                )
            ],
            ("20", "9999"): [
                _schedule_row(
                    2, 22, "2026-11-20T08:05:00+00:00", "2026-11-20T08:15:00+00:00"
                )
            ],
        },
    )
    with _client(fake) as client:
        response = client.get("/arrivals?lines=10,20&station=9999&limit=3")

    assert response.status_code == 200
    body = response.json()
    assert [arrival["line"] for arrival in body["arrivals"]] == ["10", "20"]
    assert body["arrivals"][0]["minutes"] < body["arrivals"][1]["minutes"]
