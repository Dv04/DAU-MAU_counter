from fastapi.testclient import TestClient

from service.app import create_app

REQUIRED_METRIC_KEYS = {
    "day",
    "estimate",
    "lower_95",
    "upper_95",
    "epsilon_used",
    "delta",
    "mechanism",
    "sketch_impl",
    "budget_remaining",
    "version",
    "budget",
}


def _headers(client: TestClient) -> dict[str, str]:
    api_key = client.app.state.config.security.api_key  # type: ignore[attr-defined]
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def test_end_to_end_service_flow(monkeypatch) -> None:
    monkeypatch.setenv("EPSILON_DAU", "10")
    monkeypatch.setenv("EPSILON_MAU", "10")
    monkeypatch.setenv("MAU_WINDOW_DAYS", "3")
    app = create_app()
    client = TestClient(app)
    headers = _headers(client)

    base_events = [
        {"user_id": "alice", "op": "+", "day": "2025-10-01"},
        {"user_id": "alice", "op": "+", "day": "2025-10-01"},  # duplicate plus
        {"user_id": "bob", "op": "+", "day": "2025-10-01"},
        {"user_id": "alice", "op": "+", "day": "2025-10-02"},
        {"user_id": "carol", "op": "+", "day": "2025-10-02"},
        {"user_id": "dave", "op": "+", "day": "2025-10-03"},
        {"user_id": "erin", "op": "+", "day": "2025-10-04"},
    ]
    resp = client.post("/event", json={"events": base_events}, headers=headers)
    assert resp.status_code == 202

    unique_days = ["2025-10-01", "2025-10-02", "2025-10-03", "2025-10-04"]
    dau_estimates: list[float] = []
    for day in unique_days:
        response = client.get(f"/dau/{day}", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert REQUIRED_METRIC_KEYS <= set(payload.keys())
        dau_estimates.append(payload["estimate"])
        if day == "2025-10-01":
            # duplicate '+' should be coalesced to two unique users
            assert payload["exact_value"] == 2

    mau_window = app.state.config.sketch.mau_window_days  # type: ignore[attr-defined]
    end_day = unique_days[-1]
    mau_response = client.get(
        "/mau", params={"end": end_day, "window": mau_window}, headers=headers
    )
    assert mau_response.status_code == 200
    mau_before = mau_response.json()
    assert REQUIRED_METRIC_KEYS <= set(mau_before.keys())
    assert mau_before["estimate"] >= max(dau_estimates[-mau_window:])

    # Apply deletion for alice across two days and ensure MAU drops (noise seed deterministic).
    deletion_payload = {
        "events": [
            {
                "user_id": "alice",
                "op": "-",
                "day": end_day,
                "metadata": {"days": ["2025-10-01", "2025-10-02"]},
            }
        ]
    }
    resp = client.post("/event", json=deletion_payload, headers=headers)
    assert resp.status_code == 202
    # Extra deletion should be idempotent
    resp = client.post("/event", json=deletion_payload, headers=headers)
    assert resp.status_code == 202

    mau_after = client.get(
        "/mau", params={"end": end_day, "window": mau_window}, headers=headers
    ).json()
    assert mau_after["estimate"] <= mau_before["estimate"]

    # Budget endpoint should expose remaining epsilon and composition details.
    budget_resp = client.get(f"/budget/mau?day={end_day}", headers=headers)
    assert budget_resp.status_code == 200
    budget_payload = budget_resp.json()
    assert budget_payload["metric"] == "mau"
    assert budget_payload["day"] == end_day
    assert "epsilon_spent" in budget_payload
    assert "epsilon_remaining" in budget_payload
    assert isinstance(budget_payload["rdp_orders"], list)
    assert budget_payload["policy"]["composition"] in {"rdp", "naive"}
    assert "notes" in budget_payload["policy"]
    assert budget_payload["release_count"] >= 1

    # API key enforcement
    unauthorized = client.get(f"/dau/{end_day}")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"] == "unauthorized"

    # Bad payload should return 400 with structured problem detail.
    bad_payload = client.post("/event", json={"events": []}, headers=headers)
    assert bad_payload.status_code == 400
    problem = bad_payload.json()
    assert problem["error"] == "invalid_request"
    assert "hint" in problem and problem["hint"]

    # Budget GET for DAU should also succeed and include epsilon fields.
    dau_budget = client.get(f"/budget/dau?day={end_day}", headers=headers).json()
    assert dau_budget["metric"] == "dau"
    assert "epsilon_spent" in dau_budget
    assert "budget_remaining" not in dau_budget  # field should not exist on budget response
    assert dau_budget["policy"]["monthly_cap"] == budget_payload["policy"]["monthly_cap"]
