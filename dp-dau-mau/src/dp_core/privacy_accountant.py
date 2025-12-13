"""Simple SQLite-backed privacy accountant."""

from __future__ import annotations

import datetime as dt
import math
import sqlite3
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path


def month_key(day: dt.date) -> str:
    return day.strftime("%Y-%m")


@dataclass(slots=True)
class BudgetCaps:
    dau: float
    mau: float


@dataclass(slots=True)
class BudgetSnapshot:
    metric: str
    day: str
    period: str
    epsilon_cap: float
    epsilon_spent: float
    epsilon_remaining: float
    delta: float
    best_rdp_epsilon: float | None = None
    best_rdp_order: float | None = None
    rdp_curve: dict[float, float] = field(default_factory=dict)
    advanced_epsilon: float | None = None
    advanced_delta: float | None = None
    release_count: int = 0
    rdp_orders: tuple[float, ...] = field(default_factory=tuple)
    composition: str = "naive"
    notes: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "day": self.day,
            "period": self.period,
            "epsilon_cap": self.epsilon_cap,
            "epsilon_spent": self.epsilon_spent,
            "epsilon_remaining": self.epsilon_remaining,
            "delta": self.delta,
            "best_rdp_epsilon": self.best_rdp_epsilon,
            "best_rdp_order": self.best_rdp_order,
            "rdp_curve": dict(self.rdp_curve),
            "advanced_epsilon": self.advanced_epsilon,
            "advanced_delta": self.advanced_delta,
            "release_count": self.release_count,
            "rdp_orders": list(self.rdp_orders),
            "policy": {
                "monthly_cap": self.epsilon_cap,
                "composition": self.composition,
                "notes": self.notes,
            },
        }


class PrivacyAccountant:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
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
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rdp_releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric TEXT NOT NULL,
                day TEXT NOT NULL,
                period TEXT NOT NULL,
                alpha REAL NOT NULL,
                epsilon REAL NOT NULL,
                ts INTEGER NOT NULL
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

    def get_spent_epsilon(self, metric: str, day: dt.date) -> float:
        """Public helper exposing cumulative epsilon for the month."""
        return self.spent_budget(metric, day)

    def monthly_release_count(self, metric: str, day: dt.date) -> int:
        period = month_key(day)
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM releases WHERE metric = ? AND period = ?",
            (metric, period),
        )
        (count,) = cur.fetchone()
        return int(count or 0)

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
        self._conn.execute(
            "DELETE FROM rdp_releases WHERE metric = ? AND period = ?",
            (metric, month),
        )
        self._conn.commit()

    def log_rdp_points(self, metric: str, day: dt.date, rdp_points: Mapping[float, float]) -> None:
        """Persist Rényi DP curve points ε(α) for a given release."""
        filtered: list[tuple[float, float]] = []
        for order, value in rdp_points.items():
            if order <= 1:
                raise ValueError("RDP order must be greater than 1.")
            if value < 0:
                raise ValueError("RDP epsilon must be non-negative.")
            filtered.append((float(order), float(value)))
        if not filtered:
            return
        timestamp = int(time.time())
        period = month_key(day)
        entries = [
            (metric, day.isoformat(), period, order, eps, timestamp) for order, eps in filtered
        ]
        self._conn.executemany(
            (
                "INSERT INTO rdp_releases "
                "(metric, day, period, alpha, epsilon, ts) VALUES (?, ?, ?, ?, ?, ?)"
            ),
            entries,
        )
        self._conn.commit()

    def log_rdp(self, metric: str, day: dt.date, order: float, rdp_value: float) -> None:
        """Backward-compatible helper logging a single RDP point."""
        self.log_rdp_points(metric, day, {order: rdp_value})

    def spent_rdp(
        self, metric: str, day: dt.date, orders: Iterable[float] | None = None
    ) -> dict[float, float]:
        period = month_key(day)
        cursor = self._conn.execute(
            """
            SELECT alpha, SUM(epsilon)
            FROM rdp_releases
            WHERE metric = ? AND period = ?
            GROUP BY alpha
            """,
            (metric, period),
        )
        totals = {float(order): float(total or 0.0) for order, total in cursor.fetchall()}
        if orders is not None:
            for order in orders:
                totals.setdefault(float(order), 0.0)
        return totals

    def _rdp_curve_for_day(self, metric: str, day: dt.date) -> dict[float, float]:
        cursor = self._conn.execute(
            """
            SELECT alpha, SUM(epsilon)
            FROM rdp_releases
            WHERE metric = ? AND day = ?
            GROUP BY alpha
            """,
            (metric, day.isoformat()),
        )
        return {float(alpha): float(total or 0.0) for alpha, total in cursor.fetchall()}

    def _fetch_releases(
        self,
        metric: str,
        day: dt.date,
    ) -> list[tuple[float, float]]:
        period = month_key(day)
        cursor = self._conn.execute(
            """
            SELECT epsilon, delta
            FROM releases
            WHERE metric = ? AND period = ?
            ORDER BY id ASC
            """,
            (metric, period),
        )
        return [(float(epsilon), float(delta)) for epsilon, delta in cursor.fetchall()]

    def get_day_epsilon(self, metric: str, day: dt.date, delta: float) -> float:
        """Return composed ε for a specific day, falling back to naive summation."""
        curve = self._rdp_curve_for_day(metric, day)
        best = self.best_epsilon_from_rdp(delta, curve)
        if best is not None:
            return best
        cursor = self._conn.execute(
            "SELECT COALESCE(SUM(epsilon), 0) FROM releases WHERE metric = ? AND day = ?",
            (metric, day.isoformat()),
        )
        (value,) = cursor.fetchone()
        return float(value or 0.0)

    def get_monthly_spent(self, metric: str, month_key_value: str, delta: float) -> float:
        """Return ε spent in a month using RDP when available, else naive composition."""
        try:
            year, month = (int(part) for part in month_key_value.split("-", 1))
        except ValueError:
            raise ValueError("month_key must be in YYYY-MM format") from None
        period_day = dt.date(year, month, 1)
        curve = self.spent_rdp(metric, period_day, None)
        best, _ = self._best_from_curve(delta, curve)
        if best is not None:
            return best
        cursor = self._conn.execute(
            "SELECT COALESCE(SUM(epsilon), 0) FROM releases WHERE metric = ? AND period = ?",
            (metric, month_key_value),
        )
        (value,) = cursor.fetchone()
        return float(value or 0.0)

    def get_remaining_budget(
        self, metric: str, month_key_value: str, cap: float, delta: float
    ) -> float:
        """Return remaining ε budget for the month."""
        spent = self.get_monthly_spent(metric, month_key_value, delta)
        return max(0.0, cap - spent)

    @staticmethod
    def _advanced_epsilon_delta(
        releases: Iterable[tuple[float, float]],
        delta_prime: float,
    ) -> tuple[float | None, float | None]:
        releases_list = list(releases)
        if not releases_list:
            return None, None
        if delta_prime <= 0 or delta_prime >= 1:
            return None, None
        sum_eps_sq = sum(epsilon**2 for epsilon, _ in releases_list)
        sum_exp_terms = sum(epsilon * (math.exp(epsilon) - 1.0) for epsilon, _ in releases_list)
        eps_bound = math.sqrt(2.0 * math.log(1.0 / delta_prime) * sum_eps_sq) + sum_exp_terms
        total_delta = sum(delta for _epsilon, delta in releases_list) + delta_prime
        return eps_bound, total_delta

    @staticmethod
    def _best_from_curve(
        delta: float, rdp_points: Mapping[float, float]
    ) -> tuple[float | None, float | None]:
        if delta <= 0 or delta >= 1:
            return None, None
        log_term = math.log(1.0 / delta)
        best_eps: float | None = None
        best_order: float | None = None
        for order, rdp_value in rdp_points.items():
            if order <= 1:
                continue
            epsilon = float(rdp_value) + log_term / (float(order) - 1.0)
            if best_eps is None or epsilon < best_eps:
                best_eps = epsilon
                best_order = float(order)
        return best_eps, best_order

    @staticmethod
    def best_epsilon_from_rdp(delta: float, rdp_points: Mapping[float, float]) -> float | None:
        """Convert an RDP curve ε_α into (ε, δ) using ε = ε_α + log(1/δ)/(α - 1)."""
        best_eps, _ = PrivacyAccountant._best_from_curve(delta, rdp_points)
        return best_eps

    def best_rdp_epsilon(
        self,
        metric: str,
        day: dt.date,
        delta: float,
        orders: Iterable[float],
    ) -> tuple[float | None, float | None]:
        totals = self.spent_rdp(metric, day, orders)
        best_eps, best_order = self._best_from_curve(delta, totals)
        return best_eps, best_order

    def budget_snapshot(
        self,
        metric: str,
        day: dt.date,
        cap: float,
        delta: float,
        orders: Iterable[float],
        advanced_delta: float,
    ) -> BudgetSnapshot:
        period = month_key(day)
        spent_naive = self.spent_budget(metric, day)
        rdp_totals = self.spent_rdp(metric, day, orders)
        best_eps, best_order = self.best_rdp_epsilon(metric, day, delta, orders)
        using_rdp = delta > 0 and best_eps is not None
        epsilon_spent = best_eps if using_rdp and best_eps is not None else spent_naive
        remaining = max(0.0, cap - epsilon_spent)
        releases = self._fetch_releases(metric, day)
        adv_eps, adv_delta = self._advanced_epsilon_delta(releases, advanced_delta)
        composition = "rdp" if using_rdp else "naive"
        if using_rdp:
            notes = "Composed via Rényi DP ledger across month."
        elif delta <= 0:
            notes = "Delta is zero; falling back to naive ε summation."
        else:
            notes = "No RDP orders configured; falling back to naive ε summation."
        return BudgetSnapshot(
            metric=metric,
            day=day.isoformat(),
            period=period,
            epsilon_cap=cap,
            epsilon_spent=epsilon_spent,
            epsilon_remaining=remaining,
            delta=delta,
            best_rdp_epsilon=best_eps,
            best_rdp_order=best_order,
            rdp_curve=rdp_totals,
            advanced_epsilon=adv_eps,
            advanced_delta=adv_delta,
            release_count=len(releases),
            rdp_orders=tuple(sorted(float(order) for order in rdp_totals.keys())),
            composition=composition,
            notes=notes,
        )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> PrivacyAccountant:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()
