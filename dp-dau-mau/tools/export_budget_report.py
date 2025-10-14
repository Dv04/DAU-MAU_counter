"""Generate a JSON snapshot of privacy budget state for CI observability."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dp_core.pipeline import EventRecord, PipelineManager  # noqa: E402


def _ingest_sample_traffic(
    pipeline: PipelineManager,
    *,
    days: int,
    daily_users: int,
    seed: int,
) -> list[dt.date]:
    rng = random.Random(seed)
    today = dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    sampled_days: list[dt.date] = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        sampled_days.append(day)
        user_ids = [f"ci-user-{offset}-{i}" for i in range(daily_users)]
        for user in user_ids:
            pipeline.ingest_event(
                EventRecord(
                    user_id=user,
                    op="+",
                    day=day,
                    metadata={"source": "ci-sample"},
                )
            )
        # trigger one delete to exercise replay logic
        if rng.random() < 0.3:
            deleted_user = rng.choice(user_ids)
            pipeline.ingest_event(
                EventRecord(
                    user_id=deleted_user,
                    op="-",
                    day=day,
                    metadata={"days": [day.isoformat()]},
                )
            )
        pipeline.get_daily_release(day)
        pipeline.get_mau_release(day)
    return sampled_days


def _collect_budget_snapshots(
    pipeline: PipelineManager,
    *,
    metrics: Sequence[str],
    day: dt.date,
) -> dict[str, object]:
    snapshot: dict[str, object] = {"generated_at": dt.datetime.utcnow().isoformat() + "Z"}
    for metric in metrics:
        snapshot[metric] = pipeline.get_budget_summary(metric, day)
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

    pipeline = PipelineManager()
    sampled_days = _ingest_sample_traffic(
        pipeline,
        days=max(0, args.sample_days),
        daily_users=max(1, args.daily_users),
        seed=args.seed,
    )
    target_day = sampled_days[-1] if sampled_days else dt.date.today()
    snapshot = _collect_budget_snapshots(pipeline, metrics=args.metrics, day=target_day)

    out_path = args.out
    if out_path is None:
        out_dir = Path(tempfile.mkdtemp(prefix="dpdau-budget-"))
        out_path = out_dir / "budget-snapshot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
