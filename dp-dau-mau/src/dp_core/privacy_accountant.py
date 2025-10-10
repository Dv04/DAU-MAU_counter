"""Simple SQLite-backed privacy accountant."""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass
from pathlib import Path


def month_key(day: dt.date) -> str:
    return day.strftime("%Y-%m")


@dataclass(slots=True)
class BudgetCaps:
    dau: float
    mau: float


class PrivacyAccountant:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric TEXT NOT NULL,
                day TEXT NOT NULL,
                period TEXT NOT NULL,
                epsilon REAL NOT NULL,
                delta REAL NOT NULL,
                mechanism TEXT NOT NULL,
                seed INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.commit()

    def can_release(self, metric: str, epsilon: float, day: dt.date, cap: float) -> bool:
        spent = self.spent_budget(metric, day)
        return spent + epsilon <= cap + 1e-9

    def spent_budget(self, metric: str, day: dt.date) -> float:
        period = month_key(day)
        cur = self._conn.execute(
            "SELECT COALESCE(SUM(epsilon), 0) FROM releases WHERE metric = ? AND period = ?",
            (metric, period),
        )
        (value,) = cur.fetchone()
        return float(value)

    def remaining_budget(self, metric: str, day: dt.date, cap: float) -> float:
        return max(0.0, cap - self.spent_budget(metric, day))

    def record_release(
        self,
        metric: str,
        day: dt.date,
        epsilon: float,
        delta: float,
        mechanism: str,
        seed: int,
    ) -> None:
        self._conn.execute(
            (
                "INSERT INTO releases "
                "(metric, day, period, epsilon, delta, mechanism, seed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            (metric, day.isoformat(), month_key(day), epsilon, delta, mechanism, seed),
        )
        self._conn.commit()

    def reset_month(self, metric: str, month: str) -> None:
        self._conn.execute(
            "DELETE FROM releases WHERE metric = ? AND period = ?",
            (metric, month),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> PrivacyAccountant:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
