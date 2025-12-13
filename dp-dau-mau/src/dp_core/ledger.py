"""SQLite ledger for activity and erasure tracking."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ActivityEntry:
    day: str
    user_key: bytes
    user_root: bytes
    op: str
    metadata: str


@dataclass(slots=True)
class ErasureEntry:
    erasure_id: int | None
    user_root: bytes
    days: list[str]
    pending: bool


class Ledger:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.row_factory = sqlite3.Row
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                user_key BLOB NOT NULL,
                user_root BLOB NOT NULL,
                op TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS erasure_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_root BLOB NOT NULL,
                days TEXT NOT NULL,
                pending INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT
            );
            """
        )
        self._conn.commit()

    def record_activity(self, entry: ActivityEntry) -> None:
        self._conn.execute(
            """
            INSERT INTO activity_log (day, user_key, user_root, op, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entry.day, entry.user_key, entry.user_root, entry.op, entry.metadata),
        )
        self._conn.commit()

    def record_activity_batch(self, entries: list[ActivityEntry]) -> None:
        """Batch insert activity entries for efficiency (used for tombstones)."""
        if not entries:
            return
        with self._conn:
            self._conn.executemany(
                """INSERT INTO activity_log (day, user_key, user_root, op, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                [(e.day, e.user_key, e.user_root, e.op, e.metadata) for e in entries],
            )

    def record_erasure(self, entry: ErasureEntry) -> int:
        self._conn.execute(
            """
            INSERT INTO erasure_log (user_root, days, pending)
            VALUES (?, ?, ?)
            """,
            (entry.user_root, json.dumps(entry.days), int(entry.pending)),
        )
        self._conn.commit()
        cur = self._conn.execute("SELECT last_insert_rowid()")
        (erasure_id,) = cur.fetchone()
        return int(erasure_id)

    def mark_erasure_processed(self, erasure_id: int) -> None:
        self._conn.execute(
            "UPDATE erasure_log SET pending = 0, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (erasure_id,),
        )
        self._conn.commit()

    def fetch_day_events(self, day: str) -> list[tuple[str, bytes]]:
        cur = self._conn.execute(
            "SELECT op, user_key FROM activity_log WHERE day = ? ORDER BY id ASC", (day,)
        )
        return [(row["op"], row["user_key"]) for row in cur.fetchall()]

    def days_for_user(self, user_root: bytes) -> list[str]:
        cur = self._conn.execute(
            "SELECT DISTINCT day FROM activity_log WHERE user_root = ? ORDER BY day ASC",
            (user_root,),
        )
        return [row["day"] for row in cur.fetchall()]

    def pending_erasures(self) -> list[ErasureEntry]:
        cur = self._conn.execute(
            "SELECT id, user_root, days, pending FROM erasure_log WHERE pending = 1 ORDER BY id ASC"
        )
        results: list[ErasureEntry] = []
        for row in cur.fetchall():
            results.append(
                ErasureEntry(
                    erasure_id=int(row["id"]),
                    user_root=row["user_root"],
                    days=json.loads(row["days"]),
                    pending=bool(row["pending"]),
                )
            )
        return results

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
