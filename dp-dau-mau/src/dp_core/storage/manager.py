from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .log import AppendOnlyLog, ActivityEntry, ErasureEntry, TYPE_ACTIVITY

class PartitionedLogManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.daily_logs_dir = base_dir / "days"
        self.daily_logs_dir.mkdir(parents=True, exist_ok=True)
        self.erasure_log_path = base_dir / "erasures.bin"
        self._erasure_log = AppendOnlyLog(self.erasure_log_path)
        self._open_logs: dict[str, AppendOnlyLog] = {}
        
        # In-Memory Indices
        self._user_days: dict[bytes, set[str]] = {}
        self._processed_erasures: set[int] = set()
        
        # Build index on startup
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        # Scan all day logs to build user->days mapping
        # This is fast sequential read
        for log_file in self.daily_logs_dir.glob("*.bin"):
            day_str = log_file.stem
            log = AppendOnlyLog(log_file)
            for entry in log.replay():
                if isinstance(entry, ActivityEntry):
                    if entry.user_root not in self._user_days:
                        self._user_days[entry.user_root] = set()
                    self._user_days[entry.user_root].add(day_str)
            log.close()

    def _get_day_log(self, day: str) -> AppendOnlyLog:
        if day not in self._open_logs:
            path = self.daily_logs_dir / f"{day}.bin"
            self._open_logs[day] = AppendOnlyLog(path)
        return self._open_logs[day]

    def append_activity(self, entry: ActivityEntry) -> None:
        # Update Log
        log = self._get_day_log(entry.day)
        log.append_activity(entry)
        
        # Update Index
        if entry.user_root not in self._user_days:
            self._user_days[entry.user_root] = set()
        self._user_days[entry.user_root].add(entry.day)

    def append_erasure(self, entry: ErasureEntry) -> int:
        return self._erasure_log.append_erasure(entry)
        
    def fetch_day_events(self, day: str) -> Iterator[tuple[str, bytes]]:
        """Optimized fetch: Read only the specific day file."""
        log_path = self.daily_logs_dir / f"{day}.bin"
        if not log_path.exists():
            return
            
        reader = AppendOnlyLog(log_path)
        for entry in reader.replay():
            if isinstance(entry, ActivityEntry):
                yield (entry.op, entry.user_key)
        reader.close()

    def days_for_user(self, user_root: bytes) -> list[str]:
        return list(self._user_days.get(user_root, set()))

    def pending_erasures(self) -> list[ErasureEntry]:
        # Return only unprocessed erasures
        all_erasures = [e for e in self._erasure_log.replay() if isinstance(e, ErasureEntry)]
        return [e for e in all_erasures if e.erasure_id not in self._processed_erasures]

    def mark_erasure_processed(self, erasure_id: int) -> None:
        self._processed_erasures.add(erasure_id)

    def close(self) -> None:
        for log in self._open_logs.values():
            log.close()
        self._erasure_log.close()
        self._open_logs.clear()
        
    def transaction(self):
         return _FlushContext(self)

    def flush_all(self):
        for log in self._open_logs.values():
            log.flush()
        self._erasure_log.flush()

    def buffered_writer(self) -> PartitionedBufferedWriter:
        return PartitionedBufferedWriter(self)

class PartitionedBufferedWriter:
    """Buffers writes across multiple daily logs."""
    def __init__(self, manager: PartitionedLogManager):
        self.manager = manager
        self.writers: dict[str, Any] = {}
        self.contexts: dict[str, Any] = {}
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        for ctx in self.contexts.values():
            # Pass exception details if needed, or None
            ctx.__exit__(exc_type, exc_val, exc_tb)
            
    def append_activity(self, entry: ActivityEntry) -> None:
        if entry.day not in self.writers:
            log = self.manager._get_day_log(entry.day)
            ctx = log.buffered_writer()
            self.writers[entry.day] = ctx.__enter__()
            self.contexts[entry.day] = ctx
        self.writers[entry.day].append_activity(entry)

class _FlushContext:
    def __init__(self, manager: PartitionedLogManager):
        self.manager = manager
        
    def __enter__(self): 
        pass
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.manager.flush_all()
