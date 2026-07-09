"""Per-day partitioned append-only log manager.

Presents the same surface the pipeline previously used from the SQLite
`ledger.Ledger` (append_activity / fetch_day_events / days_for_user /
append_erasure / pending_erasures / mark_erasure_processed) but stores each
day's events in its own binary append-only log file under
``<data_dir>/days/<day>.bin`` and erasures in ``<data_dir>/erasures.bin``.

Correctness note: writers are buffered, so any read path
(``fetch_day_events``) flushes that day's open writer first, ensuring a
query observes every event ingested so far in-process.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from .log import ActivityEntry, AppendOnlyLog, ErasureEntry


class PartitionedLogManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.daily_logs_dir = self.base_dir / "days"
        self.daily_logs_dir.mkdir(parents=True, exist_ok=True)
        self.erasure_log_path = self.base_dir / "erasures.bin"
        self._erasure_log = AppendOnlyLog(self.erasure_log_path)
        self._open_logs: dict[str, AppendOnlyLog] = {}
        self._user_days: dict[bytes, set[str]] = {}
        self._processed_erasures: set[int] = set()
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        for log_file in self.daily_logs_dir.glob("*.bin"):
            day_str = log_file.stem
            reader = AppendOnlyLog(log_file)
            for entry in reader.replay():
                if isinstance(entry, ActivityEntry):
                    self._user_days.setdefault(entry.user_root, set()).add(day_str)
            reader.close()

    def _get_day_log(self, day: str) -> AppendOnlyLog:
        log = self._open_logs.get(day)
        if log is None:
            log = AppendOnlyLog(self.daily_logs_dir / f"{day}.bin")
            self._open_logs[day] = log
        return log

    def _index_activity(self, entry: ActivityEntry) -> None:
        self._user_days.setdefault(entry.user_root, set()).add(entry.day)

    def append_activity(self, entry: ActivityEntry) -> None:
        self._get_day_log(entry.day).append_activity(entry)
        self._index_activity(entry)

    def record_activity_batch(self, entries: list[ActivityEntry]) -> None:
        for entry in entries:
            self.append_activity(entry)

    def append_erasure(self, entry: ErasureEntry) -> int:
        return self._erasure_log.append_erasure(entry)

    def fetch_day_events(self, day: str) -> Iterator[tuple[str, bytes]]:
        # Flush any buffered writes for this day so the read sees them.
        open_log = self._open_logs.get(day)
        if open_log is not None:
            open_log.flush()
        log_path = self.daily_logs_dir / f"{day}.bin"
        if not log_path.exists():
            return
        reader = AppendOnlyLog(log_path)
        try:
            for entry in reader.replay():
                if isinstance(entry, ActivityEntry):
                    yield (entry.op, entry.user_key)
        finally:
            reader.close()

    def days_for_user(self, user_root: bytes) -> list[str]:
        return sorted(self._user_days.get(user_root, set()))

    def pending_erasures(self) -> list[ErasureEntry]:
        self._erasure_log.flush()
        return [
            e
            for e in self._erasure_log.replay()
            if isinstance(e, ErasureEntry) and e.erasure_id not in self._processed_erasures
        ]

    def mark_erasure_processed(self, erasure_id: int) -> None:
        self._processed_erasures.add(erasure_id)

    def flush_all(self) -> None:
        for log in self._open_logs.values():
            log.flush()
        self._erasure_log.flush()

    def close(self) -> None:
        for log in self._open_logs.values():
            log.close()
        self._open_logs.clear()
        self._erasure_log.close()

    def buffered_writer(self) -> PartitionedBufferedWriter:
        return PartitionedBufferedWriter(self)


class PartitionedBufferedWriter:
    """Batch-ingest helper: buffers writes per day and keeps the manager's
    user->days index current so in-batch deletion lookups still work."""

    def __init__(self, manager: PartitionedLogManager) -> None:
        self._manager = manager
        self._writers: dict[str, object] = {}

    def __enter__(self) -> PartitionedBufferedWriter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        for writer in self._writers.values():
            writer.flush()  # type: ignore[attr-defined]
        self._writers.clear()

    def append_activity(self, entry: ActivityEntry) -> None:
        writer = self._writers.get(entry.day)
        if writer is None:
            writer = self._manager._get_day_log(entry.day).buffered_writer()
            self._writers[entry.day] = writer
        writer.append_activity(entry)  # type: ignore[attr-defined]
        self._manager._index_activity(entry)
