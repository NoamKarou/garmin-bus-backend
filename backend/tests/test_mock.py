from __future__ import annotations

from fastapi.testclient import TestClient

from app import config
from app.cache import TTLCache
from app.main import create_app
from app.mock import MockStrideClient
from conftest import NOW


def _client() -> TestClient:
    return TestClient(
        create_app(
            stride_client=MockStrideClient(),
            cache=TTLCache(),
            now_provider=lambda: NOW,
        )
    )


def test_mock_arrivals_are_upcoming_and_partly_live():
    with _client() as client:
        response = client.get("/arrivals?lines=480&station=4170&limit=3")

    assert response.status_code == 200
    body = response.json()
    assert body["station"] == {
        "code": "4170",
        "name": "Mock Station 4170",
        "city": "Mock City",
    }

    arrivals = body["arrivals"]
    assert len(arrivals) == 3
    assert [arrival["line"] for arrival in arrivals] == ["480"] * 3
    assert [arrival["minutes"] for arrival in arrivals] == [1, 11, 21]

    # The first trip has a vehicle in range; the rest are schedule-only.
    assert arrivals[0]["live"] is True
    assert all(arrival["live"] is False for arrival in arrivals[1:])
    assert body["queried_at_epoch_sec"] > 0
    assert all(
        arrival["arrival_epoch_sec"] >= body["queried_at_epoch_sec"]
        for arrival in arrivals
    )


def test_mock_accepts_any_station_and_line():
    with _client() as client:
        station = client.get("/station?station=12345")
        arrivals = client.get("/arrivals?lines=999&station=12345")

    assert station.status_code == 200
    assert station.json() == {
        "code": "12345",
        "name": "Mock Station 12345",
        "city": "Mock City",
    }
    assert arrivals.status_code == 200
    assert arrivals.json()["station"]["code"] == "12345"


def test_mock_multiple_lines_are_independent():
    with _client() as client:
        response = client.get("/arrivals?lines=480,74&station=4170&limit=2")

    assert response.status_code == 200
    arrivals = response.json()["arrivals"]
    assert {arrival["line"] for arrival in arrivals} == {"480", "74"}
    assert len(arrivals) == 4
    assert any(arrival["live"] for arrival in arrivals)


def test_mock_still_validates_parameters():
    with _client() as client:
        response = client.get("/arrivals?lines=480&station=abc")
    assert response.status_code == 422


def test_mock_mode_env_var_selects_mock_client(monkeypatch):
    monkeypatch.setattr(config, "MOCK_MODE", True)
    application = create_app(cache=TTLCache(), now_provider=lambda: NOW)

    with TestClient(application) as client:
        assert isinstance(application.state.stride, MockStrideClient)
        assert client.get("/").json()["mode"] == "mock"
        response = client.get("/arrivals?lines=480&station=4170")

    assert response.status_code == 200
    assert response.json()["arrivals"][0]["live"] is True
