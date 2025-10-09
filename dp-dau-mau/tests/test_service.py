import datetime as dt

from fastapi.testclient import TestClient

from service.app import create_app


def test_service_endpoints_roundtrip() -> None:
    app = create_app()
    client = TestClient(app)
    day = dt.date(2025, 10, 2).isoformat()

    resp = client.post(
        "/event",
        json={
            "event": {
                "user_id": "cli-user",
                "op": "+",
                "day": day,
                "metadata": {"source": "test"},
            }
        },
    )
    assert resp.status_code == 202

    dau = client.get(f"/dau/{day}")
    assert dau.status_code == 200
    payload = dau.json()
    assert "estimate" in payload

    mau = client.get(f"/mau?end={day}")
    assert mau.status_code == 200
