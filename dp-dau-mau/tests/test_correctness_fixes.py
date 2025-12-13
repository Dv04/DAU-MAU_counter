"""Regression tests for critical correctness fixes.

Tests for:
1. MAU counts unique users (not user-days) within rotation epoch
2. Deletions retroactively remove users from historical days
3. Hash stability within epochs
"""

from __future__ import annotations

import datetime as dt
import os
import tempfile

import pytest


@pytest.fixture
def temp_data_dir(monkeypatch: pytest.MonkeyPatch) -> str:
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("DATA_DIR", tmpdir)
        monkeypatch.setenv("SKETCH_IMPL", "set")  # Use exact counting
        monkeypatch.setenv("HASH_SALT_ROTATION_DAYS", "30")
        monkeypatch.setenv("MAU_WINDOW_DAYS", "30")
        monkeypatch.setenv("DAU_BUDGET_TOTAL", "100.0")  # Large budget for testing
        monkeypatch.setenv("MAU_BUDGET_TOTAL", "100.0")
        yield tmpdir


class TestMAUUniqueness:
    """Test that MAU counts unique users, not user-days."""

    def test_mau_counts_user_once_across_days(self, temp_data_dir: str) -> None:
        """Verify same user active on multiple days counts as 1 in MAU."""
        from dp_core.config import AppConfig
        from dp_core.pipeline import EventRecord, PipelineManager

        config = AppConfig.from_env()
        pipeline = PipelineManager(config=config)

        day1 = dt.date(2025, 10, 1)
        day2 = dt.date(2025, 10, 2)

        # Same user active on two days
        pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day1))
        pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day2))

        # MAU over 2-day window should count alice ONCE (not twice)
        mau_result = pipeline.get_mau_release(day2, window_days=2)
        
        # With set sketch, exact_value should be 1
        assert mau_result["exact_value"] == 1, (
            f"Expected MAU exact_value=1 (unique user), got {mau_result['exact_value']}"
        )

    def test_mau_counts_distinct_users(self, temp_data_dir: str) -> None:
        """Verify different users are counted correctly."""
        from dp_core.config import AppConfig
        from dp_core.pipeline import EventRecord, PipelineManager

        config = AppConfig.from_env()
        pipeline = PipelineManager(config=config)

        day1 = dt.date(2025, 10, 1)
        day2 = dt.date(2025, 10, 2)

        # Two different users
        pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day1))
        pipeline.ingest_event(EventRecord(user_id="bob", op="+", day=day2))

        # MAU should count both users
        mau_result = pipeline.get_mau_release(day2, window_days=2)
        
        assert mau_result["exact_value"] == 2, (
            f"Expected MAU exact_value=2 (two users), got {mau_result['exact_value']}"
        )


class TestHashStability:
    """Test that hashes are stable within rotation epoch."""

    def test_hash_user_id_stable_within_epoch(self, temp_data_dir: str) -> None:
        """Same user hashes to same key for days in same rotation epoch."""
        from dp_core.config import AppConfig
        from dp_core.hashing import hash_user_id

        config = AppConfig.from_env()

        # Two consecutive days in same 30-day epoch
        day1 = dt.date(2025, 10, 1)
        day2 = dt.date(2025, 10, 2)

        hash1 = hash_user_id("alice", day1, config)
        hash2 = hash_user_id("alice", day2, config)

        assert hash1 == hash2, (
            "Same user should hash to same key within rotation epoch"
        )

    def test_hash_different_across_epoch_boundary(self, temp_data_dir: str) -> None:
        """Same user hashes to different key when epoch changes."""
        from dp_core.config import AppConfig
        from dp_core.hashing import hash_user_id

        # Use short rotation for test
        os.environ["HASH_SALT_ROTATION_DAYS"] = "1"  # Daily rotation
        config = AppConfig.from_env()

        day1 = dt.date(2025, 10, 1)
        day2 = dt.date(2025, 10, 2)  # Different epoch with 1-day rotation

        hash1 = hash_user_id("alice", day1, config)
        hash2 = hash_user_id("alice", day2, config)

        assert hash1 != hash2, (
            "Same user should hash to different key across epoch boundary"
        )


class TestRetroactiveDeletion:
    """Test that deletions remove users from historical days."""

    def test_deletion_removes_user_from_previous_day_dau(self, temp_data_dir: str) -> None:
        """Verify deletion with metadata.days removes user from those days."""
        from dp_core.config import AppConfig
        from dp_core.pipeline import EventRecord, PipelineManager

        config = AppConfig.from_env()
        pipeline = PipelineManager(config=config)

        day1 = dt.date(2025, 10, 1)
        day2 = dt.date(2025, 10, 2)

        # Alice active on day1 and day2
        pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day1))
        pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day2))

        # Verify DAU(day1) = 1 before deletion
        dau_before = pipeline.get_daily_release(day1)
        assert dau_before["exact_value"] == 1

        # Delete alice for day1 and day2
        pipeline.ingest_event(
            EventRecord(
                user_id="alice",
                op="-",
                day=day2,
                metadata={"days": [day1.isoformat(), day2.isoformat()]},
            )
        )

        # After deletion and rebuild, DAU(day1) should be 0
        pipeline.window_manager.snapshots.clear()  # Force rebuild
        dau_after = pipeline.get_daily_release(day1)
        assert dau_after["exact_value"] == 0, (
            f"Expected DAU=0 after deletion, got {dau_after['exact_value']}"
        )

    def test_deletion_removes_user_from_mau_union(self, temp_data_dir: str) -> None:
        """Verify deletion removes user from MAU calculation."""
        from dp_core.config import AppConfig
        from dp_core.pipeline import EventRecord, PipelineManager

        config = AppConfig.from_env()
        pipeline = PipelineManager(config=config)

        day1 = dt.date(2025, 10, 1)
        day2 = dt.date(2025, 10, 2)

        # Alice and Bob active
        pipeline.ingest_event(EventRecord(user_id="alice", op="+", day=day1))
        pipeline.ingest_event(EventRecord(user_id="bob", op="+", day=day2))

        # Verify MAU = 2 before deletion
        mau_before = pipeline.get_mau_release(day2, window_days=2)
        assert mau_before["exact_value"] == 2

        # Delete alice
        pipeline.ingest_event(
            EventRecord(
                user_id="alice",
                op="-",
                day=day2,
                metadata={"days": [day1.isoformat()]},
            )
        )

        # After deletion, MAU should be 1 (only bob)
        pipeline.window_manager.snapshots.clear()  # Force rebuild
        mau_after = pipeline.get_mau_release(day2, window_days=2)
        assert mau_after["exact_value"] == 1, (
            f"Expected MAU=1 after deletion, got {mau_after['exact_value']}"
        )
