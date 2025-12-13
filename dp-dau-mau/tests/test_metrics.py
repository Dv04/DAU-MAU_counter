from fastapi.testclient import TestClient

from service.app import create_app


def test_metrics_endpoint_aggregates_requests() -> None:
    app = create_app()
    client = TestClient(app)
    headers = {"X-API-Key": "test-key"}
    client.post(
        "/event",
        headers=headers,
        json={"events": [{"user_id": "metric", "op": "+", "day": "2025-10-08"}]},
    )
    client.get("/dau/2025-10-08", headers=headers)
    response = client.get("/metrics")
    assert response.headers["content-type"].startswith("text/plain")
    metrics = response.text
    assert "app_requests_total" in metrics
    assert "app_requests_5xx_total" in metrics
    assert "app_request_latency_seconds_bucket" in metrics
