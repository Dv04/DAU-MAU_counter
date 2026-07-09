"""Tests for the append-only binary log storage engine.

The engine is a drop-in replacement for the SQLite ledger as the per-day
activity store, so these tests pin the behaviours the pipeline relies on:
buffered writes are visible to reads (flush-before-read), the user->days
index is correct and survives a reopen, and erasure records round-trip.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from dp_core.storage.log import ActivityEntry, AppendOnlyLog, ErasureEntry
from dp_core.storage.manager import PartitionedLogManager


def _key(s: str) -> bytes:
    return hashlib.sha256(s.encode()).digest()


def test_append_and_read_before_flush_is_visible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        m = PartitionedLogManager(Path(tmp))
        m.append_activity(ActivityEntry("2023-01-01", _key("alice"), _key("alice-root"), "+", "{}"))
        # fetch_day_events must flush the buffered writer first.
        events = list(m.fetch_day_events("2023-01-01"))
        assert events == [("+", _key("alice"))]
        m.close()


def test_days_for_user_index() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        m = PartitionedLogManager(Path(tmp))
        root = _key("bob-root")
        m.append_activity(ActivityEntry("2023-01-01", _key("bob-d1"), root, "+", "{}"))
        m.append_activity(ActivityEntry("2023-01-03", _key("bob-d3"), root, "+", "{}"))
        assert m.days_for_user(root) == ["2023-01-01", "2023-01-03"]
        m.close()


def test_index_rebuilt_on_reopen() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = _key("carol-root")
        m = PartitionedLogManager(Path(tmp))
        m.append_activity(ActivityEntry("2023-02-01", _key("carol"), root, "+", "{}"))
        m.close()

        reopened = PartitionedLogManager(Path(tmp))
        assert list(reopened.fetch_day_events("2023-02-01")) == [("+", _key("carol"))]
        assert reopened.days_for_user(root) == ["2023-02-01"]
        reopened.close()


def test_buffered_batch_write_all_visible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        m = PartitionedLogManager(Path(tmp))
        n = 5000
        with m.buffered_writer() as w:
            for i in range(n):
                w.append_activity(
                    ActivityEntry("2023-03-01", _key(f"u{i}"), _key(f"r{i}"), "+", "{}")
                )
        assert len(list(m.fetch_day_events("2023-03-01"))) == n
        m.close()


def test_erasure_roundtrip_and_processed_marking() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        m = PartitionedLogManager(Path(tmp))
        root = _key("dave-root")
        eid = m.append_erasure(ErasureEntry(None, root, ["2023-01-01", "2023-01-02"], True))
        pending = m.pending_erasures()
        assert len(pending) == 1
        assert pending[0].days == ["2023-01-01", "2023-01-02"]
        m.mark_erasure_processed(pending[0].erasure_id)
        assert m.pending_erasures() == []
        assert isinstance(eid, int)
        m.close()


def test_delete_op_events_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        m = PartitionedLogManager(Path(tmp))
        m.append_activity(ActivityEntry("2023-01-01", _key("x"), _key("xr"), "+", "{}"))
        m.append_activity(ActivityEntry("2023-01-01", _key("x"), _key("xr"), "-", "{}"))
        events = list(m.fetch_day_events("2023-01-01"))
        assert events == [("+", _key("x")), ("-", _key("x"))]
        m.close()


def test_raw_log_replay_mixed_records() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log = AppendOnlyLog(Path(tmp) / "mixed.bin")
        log.append_activity(ActivityEntry("2023-01-01", _key("a"), _key("ar"), "+", '{"m":1}'))
        log.append_erasure(ErasureEntry(None, _key("ar"), ["2023-01-01"], True))
        log.close()

        reader = AppendOnlyLog(Path(tmp) / "mixed.bin")
        records = list(reader.replay())
        reader.close()
        assert isinstance(records[0], ActivityEntry)
        assert records[0].metadata == '{"m":1}'
        assert isinstance(records[1], ErasureEntry)
        assert records[1].days == ["2023-01-01"]
