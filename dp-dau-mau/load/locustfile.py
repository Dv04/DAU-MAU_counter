"""Locust load test exercising ingest and query endpoints."""

from __future__ import annotations

import datetime as dt
import json
import os
import random
from typing import Any

from locust import HttpUser, between, task


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("SERVICE_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


class DPDauUser(HttpUser):
    wait_time = between(0.01, 0.1)

    def on_start(self) -> None:
        self.headers = _headers()
        self.user_ids = [f"load-user-{i}" for i in range(100_000)]
        self.rng = random.Random(int(os.getenv("LOAD_TEST_SEED", "20251013")))
        self.start_day = dt.date.today() - dt.timedelta(days=29)

    def _sample_event(self) -> dict[str, Any]:
        user_id = self.rng.choice(self.user_ids)
        day = self.start_day + dt.timedelta(days=self.rng.randint(0, 29))
        op = "+" if self.rng.random() > 0.1 else "-"
        metadata = {"source": "locust", "batch": self.environment.runner.state}
        if op == "-":
            metadata["days"] = [(day - dt.timedelta(days=i)).isoformat() for i in range(0, 3)]
        return {"user_id": user_id, "op": op, "day": day.isoformat(), "metadata": metadata}

    @task(5)
    def post_event(self) -> None:
        payload = {"events": [self._sample_event()]}
        self.client.post(
            "/event",
            data=json.dumps(payload),
            headers=self.headers,
            name="POST /event",
        )

    @task(2)
    def get_dau(self) -> None:
        day = (self.start_day + dt.timedelta(days=self.rng.randint(0, 29))).isoformat()
        self.client.get(
            f"/dau/{day}",
            headers=self.headers,
            name="GET /dau/{day}",
        )

    @task(1)
    def get_mau(self) -> None:
        day = (self.start_day + dt.timedelta(days=self.rng.randint(0, 29))).isoformat()
        self.client.get(
            f"/mau?end={day}",
            headers=self.headers,
            name="GET /mau",
        )
