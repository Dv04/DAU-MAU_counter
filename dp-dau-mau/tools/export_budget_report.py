"""Generate a JSON snapshot of privacy budget state for CI observability."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from service.app import create_app  # noqa: E402


def _ingest_sample_traffic(
    client: TestClient,
    *,
    days: int,
    daily_users: int,
    seed: int,
    headers: dict[str, str],
) -> list[dt.date]:
    rng = random.Random(seed)
    today = dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    sampled_days: list[dt.date] = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        sampled_days.append(day)
        user_ids = [f"ci-user-{offset}-{i}" for i in range(daily_users)]
        events = [
            {
                "user_id": user,
                "op": "+",
                "day": day.isoformat(),
                "metadata": {"source": "ci-sample"},
            }
            for user in user_ids
        ]
        if rng.random() < 0.3 and user_ids:
            deleted_user = rng.choice(user_ids)
            events.append(
                {
                    "user_id": deleted_user,
                    "op": "-",
                    "day": day.isoformat(),
                    "metadata": {"source": "ci-sample", "days": [day.isoformat()]},
                }
            )
        if events:
            response = client.post("/event", json={"events": events}, headers=headers)
            response.raise_for_status()
        client.get(f"/dau/{day.isoformat()}", headers=headers).raise_for_status()
        client.get("/mau", params={"end": day.isoformat()}, headers=headers).raise_for_status()
    return sampled_days


def _collect_budget_snapshots(
    client: TestClient,
    *,
    metrics: Sequence[str],
    day: dt.date,
    headers: dict[str, str],
) -> dict[str, object]:
    snapshot: dict[str, object] = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    params = {"day": day.isoformat()}
    for metric in metrics:
        response = client.get(f"/budget/{metric}", params=params, headers=headers)
        response.raise_for_status()
        snapshot[metric] = response.json()
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Export DP budget snapshot for CI artifacts.")
    parser.add_argument(
        "--out", type=Path, default=None, help="Output JSON path under {{DATA_DIR}}."
    )
    parser.add_argument(
        "--metrics",
        nargs="+",
        default=("dau", "mau"),
        help="Metrics to include in the snapshot.",
    )
    parser.add_argument(
        "--sample-days", type=int, default=3, help="Synthetic days to ingest before exporting."
    )
    parser.add_argument(
        "--daily-users", type=int, default=100, help="Synthetic users per sampled day."
    )
    parser.add_argument(
        "--seed", type=int, default=20251013, help="Random seed for synthetic workload."
    )
    args = parser.parse_args()

    app = create_app()
    api_key = app.state.config.security.api_key  # type: ignore[attr-defined]
    headers = {"X-API-Key": api_key} if api_key else {}

    with TestClient(app) as client:
        sampled_days = _ingest_sample_traffic(
            client,
            days=max(0, args.sample_days),
            daily_users=max(1, args.daily_users),
            seed=args.seed,
            headers=headers,
        )
        target_day = sampled_days[-1] if sampled_days else dt.date.today()
        snapshot = _collect_budget_snapshots(
            client, metrics=args.metrics, day=target_day, headers=headers
        )

    out_path = args.out
    if out_path is None:
        data_dir = app.state.config.storage.data_dir  # type: ignore[attr-defined]
        out_path = data_dir / "reports" / "budget-snapshot.json"
    else:
        out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
