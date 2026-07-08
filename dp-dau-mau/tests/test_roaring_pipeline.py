"""End-to-end pipeline tests for the Roaring Bitmap sketch backend.

Mirrors tests/test_correctness_fixes.py (which pins SKETCH_IMPL=set as
"ground truth") but runs the same event sequences through SKETCH_IMPL=roaring
and asserts identical exact_value results. Roaring is claimed by the paper
to be an *exact* backend, so at the pipeline level it must reproduce the
same exact counts as the "set" backend -- not merely a close estimate.
"""

from __future__ import annotations

import datetime as dt
import tempfile

import pytest


@pytest.fixture
def roaring_data_dir(monkeypatch: pytest.MonkeyPatch) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("SKETCH_IMPL", "roaring")
        monkeypatch.setenv("HASH_SALT_ROTATION_DAYS", "30")
        monkeypatch.setenv("MAU_WINDOW_DAYS", "30")
        monkeypatch.setenv("DAU_BUDGET_TOTAL", "100.0")
        monkeypatch.setenv("MAU_BUDGET_TOTAL", "100.0")
        yield tmpdir


def test_roaring_pipeline_accepts_sketch_impl(roaring_data_dir: str) -> None:
    """SKETCH_IMPL=roaring must be a valid, selectable backend."""
    from dp_core.config import AppConfig
    from dp_core.pipeline import PipelineManager

    config = AppConfig.from_env()
    assert config.sketch.impl == "roaring"
    pipeline = PipelineManager(config=config)
    assert "roaring" in pipeline.sketch_factory.backends


def test_roaring_mau_counts_user_once_across_days(roaring_data_dir: str) -> None:
    from dp_core.config import AppConfig
    from dp_core.pipeline import EventRecord, PipelineManager

    config = AppConfig.from_env()
    pipeline = PipelineManager(config=config)

    day1 = dt.date(2025, 10, 1)
    day2 = dt.date(2025, 10, 2)

    pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day1))
    pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day2))

    mau_result = pipeline.get_mau_release(day2, window_days=2)
    assert mau_result["exact_value"] == 1, (
        f"Roaring backend: expected MAU exact_value=1, got {mau_result['exact_value']}"
    )


def test_roaring_mau_counts_distinct_users(roaring_data_dir: str) -> None:
    from dp_core.config import AppConfig
    from dp_core.pipeline import EventRecord, PipelineManager

    config = AppConfig.from_env()
    pipeline = PipelineManager(config=config)

    day1 = dt.date(2025, 10, 1)
    day2 = dt.date(2025, 10, 2)

    pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day1))
    pipeline.ingest_event(EventRecord(user_id="bob", op="+", day=day2))

    mau_result = pipeline.get_mau_release(day2, window_days=2)
    assert mau_result["exact_value"] == 2


def test_roaring_deletion_removes_user_from_previous_day_dau(roaring_data_dir: str) -> None:
    from dp_core.config import AppConfig
    from dp_core.pipeline import EventRecord, PipelineManager

    config = AppConfig.from_env()
    pipeline = PipelineManager(config=config)

    day1 = dt.date(2025, 10, 1)
    day2 = dt.date(2025, 10, 2)

    pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day1))
    pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day2))

    dau_before = pipeline.get_daily_release(day1)
    assert dau_before["exact_value"] == 1

    pipeline.ingest_event(
        EventRecord(
            user_id="alice",
            op="-",
            day=day2,
            metadata={"days": [day1.isoformat(), day2.isoformat()]},
        )
    )

    pipeline.window_manager.snapshots.clear()
    dau_after = pipeline.get_daily_release(day1)
    assert dau_after["exact_value"] == 0, (
        f"Roaring backend: expected DAU=0 after deletion, got {dau_after['exact_value']}"
    )


def test_roaring_deletion_removes_user_from_mau_union(roaring_data_dir: str) -> None:
    from dp_core.config import AppConfig
    from dp_core.pipeline import EventRecord, PipelineManager

    config = AppConfig.from_env()
    pipeline = PipelineManager(config=config)

    day1 = dt.date(2025, 10, 1)
    day2 = dt.date(2025, 10, 2)

    pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day1))
    pipeline.ingest_event(EventRecord(user_id="bob", op="+", day=day2))

    mau_before = pipeline.get_mau_release(day2, window_days=2)
    assert mau_before["exact_value"] == 2

    pipeline.ingest_event(
        EventRecord(
            user_id="alice",
            op="-",
            day=day2,
            metadata={"days": [day1.isoformat()]},
        )
    )

    pipeline.window_manager.snapshots.clear()
    mau_after = pipeline.get_mau_release(day2, window_days=2)
    assert mau_after["exact_value"] == 1, (
        f"Roaring backend: expected MAU=1 after deletion, got {mau_after['exact_value']}"
    )


def test_roaring_matches_set_backend_exactly_under_random_events() -> None:
    """Cross-backend equivalence: same event stream through 'set' and
    'roaring' must produce identical exact_value DAU/MAU results, since
    both backends are claimed exact (unlike KMV, which is approximate).
    """
    import os
    import random

    from dp_core.config import AppConfig
    from dp_core.pipeline import EventRecord, PipelineManager

    rng = random.Random(20260708)
    users = [f"user-{i}" for i in range(40)]
    base_day = dt.date(2025, 10, 1)
    events = []
    for _ in range(150):
        op = rng.choice(["+", "-"])
        user = rng.choice(users)
        offset = rng.randint(0, 9)
        events.append((op, user, offset))

    def run_with_impl(impl: str) -> tuple[int, int]:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_env = {
                k: os.environ.get(k)
                for k in (
                    "DATA_DIR",
                    "SKETCH_IMPL",
                    "HASH_SALT_ROTATION_DAYS",
                    "MAU_WINDOW_DAYS",
                    "DAU_BUDGET_TOTAL",
                    "MAU_BUDGET_TOTAL",
                )
            }
            try:
                os.environ["DATA_DIR"] = tmpdir
                os.environ["SKETCH_IMPL"] = impl
                os.environ["HASH_SALT_ROTATION_DAYS"] = "30"
                os.environ["MAU_WINDOW_DAYS"] = "30"
                os.environ["DAU_BUDGET_TOTAL"] = "1000.0"
                os.environ["MAU_BUDGET_TOTAL"] = "1000.0"
                config = AppConfig.from_env()
                pipeline = PipelineManager(config=config)
                for op, user, offset in events:
                    day = base_day + dt.timedelta(days=offset)
                    pipeline.ingest_event(EventRecord(user_id=user, op=op, day=day, metadata={}))
                pipeline.window_manager.snapshots.clear()
                end_day = base_day + dt.timedelta(days=9)
                mau = pipeline.get_mau_release(end_day, window_days=10)
                dau_last_day = pipeline.get_daily_release(end_day)
                return mau["exact_value"], dau_last_day["exact_value"]
            finally:
                for k, v in old_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    set_mau, set_dau = run_with_impl("set")
    roaring_mau, roaring_dau = run_with_impl("roaring")

    assert roaring_mau == set_mau, (
        f"Roaring MAU exact_value ({roaring_mau}) must match set backend ({set_mau})"
    )
    assert roaring_dau == set_dau, (
        f"Roaring DAU exact_value ({roaring_dau}) must match set backend ({set_dau})"
    )
