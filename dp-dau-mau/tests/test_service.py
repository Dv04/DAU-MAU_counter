import datetime as dt

from fastapi.testclient import TestClient

from service.app import create_app


def test_service_endpoints_roundtrip() -> None:
    app = create_app()
    client = TestClient(app)
    headers = {"X-API-Key": "test-key"}
    day1 = dt.date(2025, 10, 1)
    day2 = dt.date(2025, 10, 2)

    def post_event(event_payload: dict[str, object]) -> None:
        response = client.post("/event", headers=headers, json={"event": event_payload})
        assert response.status_code == 202

    post_event(
        {"user_id": "alice", "op": "+", "day": day1.isoformat(), "metadata": {"source": "test"}}
    )
    post_event(
        {"user_id": "alice", "op": "+", "day": day2.isoformat(), "metadata": {"source": "test"}}
    )
    post_event(
        {"user_id": "bob", "op": "+", "day": day2.isoformat(), "metadata": {"source": "test"}}
    )

    dau_resp = client.get(f"/dau/{day2.isoformat()}", headers=headers)
    assert dau_resp.status_code == 200
    dau_payload = dau_resp.json()
    assert dau_payload["budget"]["epsilon_spent"] >= 0.0
    assert dau_payload["budget_remaining"] == dau_payload["budget"]["epsilon_remaining"]
    assert (
        dau_payload["budget"]["advanced_delta"] is None
        or dau_payload["budget"]["advanced_delta"] > 0.0
    )
    assert dau_payload["budget"]["release_count"] >= 1

    mau_before = client.get(f"/mau?end={day2.isoformat()}", headers=headers)
    assert mau_before.status_code == 200
    mau_before_json = mau_before.json()

    post_event(
        {
            "user_id": "alice",
            "op": "-",
            "day": day2.isoformat(),
            "metadata": {"days": [day1.isoformat(), day2.isoformat()]},
        }
    )

    mau_after = client.get(f"/mau?end={day2.isoformat()}", headers=headers)
    assert mau_after.status_code == 200
    mau_after_json = mau_after.json()
    assert mau_after_json["exact_value"] <= mau_before_json["exact_value"]
    assert mau_after_json["budget"]["best_rdp_order"] in {None, 2.0, 4.0}

    budget_resp = client.get(f"/budget/dau?day={day2.isoformat()}", headers=headers)
    assert budget_resp.status_code == 200
    budget_payload = budget_resp.json()
    assert budget_payload["metric"] == "dau"
    assert budget_payload["epsilon_spent"] >= dau_payload["budget"]["epsilon_spent"]
    assert budget_payload["advanced_epsilon"] is None or budget_payload["advanced_epsilon"] >= 0.0

    unauth = client.get(f"/dau/{day2.isoformat()}")
    assert unauth.status_code == 401
