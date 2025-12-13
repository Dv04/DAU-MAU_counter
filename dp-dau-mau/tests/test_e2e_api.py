from fastapi.testclient import TestClient

from service.app import create_app


def _client(monkeypatch, overrides: dict[str, str] | None = None) -> TestClient:
    if overrides:
        for key, value in overrides.items():
            monkeypatch.setenv(key, value)
    app = create_app()
    return TestClient(app)


def test_ingest_and_query(monkeypatch) -> None:
    client = _client(monkeypatch)
    headers = {"X-API-Key": "test-key"}
    day = "2025-10-09"
    payload = {"events": [{"user_id": "alice", "op": "+", "day": day}]}
    resp = client.post("/event", headers=headers, json=payload)
    assert resp.status_code == 202

    resp = client.get(f"/dau/{day}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    expected_fields = {
        "estimate",
        "lower_95",
        "upper_95",
        "epsilon_used",
        "delta",
        "mechanism",
        "sketch_impl",
        "budget_remaining",
        "budget",
        "version",
        "exact_value",
    }
    assert expected_fields.issubset(data.keys())


def test_delete_event_reduces_mau(monkeypatch) -> None:
    client = _client(monkeypatch)
    headers = {"X-API-Key": "test-key"}
    day1 = "2025-10-01"
    day2 = "2025-10-02"
    client.post(
        "/event",
        headers=headers,
        json={
            "events": [
                {"user_id": "alice", "op": "+", "day": day1},
                {"user_id": "alice", "op": "+", "day": day2},
                {"user_id": "bob", "op": "+", "day": day2},
            ]
        },
    )
    mau_before = client.get(f"/mau?end={day2}", headers=headers).json()

    client.post(
        "/event",
        headers=headers,
        json={
            "events": [
                {
                    "user_id": "alice",
                    "op": "-",
                    "day": day2,
                    "metadata": {"days": [day1, day2]},
                }
            ]
        },
    )
    mau_after = client.get(f"/mau?end={day2}", headers=headers).json()
    assert mau_after["exact_value"] <= mau_before["exact_value"]


def test_budget_endpoint_tracks_spend(monkeypatch) -> None:
    client = _client(monkeypatch)
    headers = {"X-API-Key": "test-key"}
    day = "2025-10-03"
    client.post(
        "/event",
        headers=headers,
        json={"events": [{"user_id": "carol", "op": "+", "day": day}]},
    )
    before = client.get(f"/budget/dau?day={day}", headers=headers).json()
    client.get(f"/dau/{day}", headers=headers)
    after = client.get(f"/budget/dau?day={day}", headers=headers).json()
    assert after["epsilon_spent"] > before["epsilon_spent"]


def test_missing_api_key_returns_401(monkeypatch) -> None:
    client = _client(monkeypatch)
    day = "2025-10-04"
    resp = client.get(f"/dau/{day}")
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"


def test_malformed_payload_returns_422(monkeypatch) -> None:
    client = _client(monkeypatch)
    headers = {"X-API-Key": "test-key"}
    resp = client.post(
        "/event",
        headers=headers,
        json={"events": [{"user_id": "x", "op": "*", "day": "2025-10-01"}]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid_request"


def test_budget_exhaustion_returns_429(monkeypatch) -> None:
    overrides = {
        "DAU_BUDGET_TOTAL": "0.3",
        "EPSILON_DAU": "0.3",
    }
    client = _client(monkeypatch, overrides)
    headers = {"X-API-Key": "test-key"}
    day = "2025-10-05"
    client.post(
        "/event",
        headers=headers,
        json={"events": [{"user_id": "eve", "op": "+", "day": day}]},
    )
    # First query consumes entire budget
    resp1 = client.get(f"/dau/{day}", headers=headers)
    assert resp1.status_code == 200
    resp2 = client.get(f"/dau/{day}", headers=headers)
    assert resp2.status_code == 429
    error_payload = resp2.json()
    assert error_payload["error"] == "budget_exhausted"
    assert error_payload["metric"] == "dau"
    assert "next_reset" in error_payload
