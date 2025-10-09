"""Ingestion and release pipeline orchestration."""

from __future__ import annotations

import datetime as dt
import json
import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Literal

from . import config as config_module
from .dp_mechanisms import MechanismResult, gaussian_mechanism, laplace_mechanism
from .hashing import hash_user_id, hash_user_root
from .ledger import ActivityEntry, ErasureEntry, Ledger
from .privacy_accountant import BudgetCaps, PrivacyAccountant
from .sketches.base import SketchFactory
from .sketches.hllpp_impl import HllppSketch
from .sketches.set_impl import SetSketch
from .sketches.theta_impl import ThetaSketch, ThetaSketchUnavailable
from .windows import WindowManager


class BudgetExceeded(Exception):
    """Raised when attempting to exceed the allocated privacy budget."""


@dataclass(slots=True)
class EventRecord:
    user_id: str
    op: Literal["+", "-"]
    day: dt.date
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> str:
        return json.dumps(self.metadata or {})


def _seed_for(metric: str, day: dt.date, default_seed: int) -> int:
    digest = sha256(f"{metric}:{day.isoformat()}:{default_seed}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


class PipelineManager:
    def __init__(
        self,
        config: config_module.AppConfig | None = None,
        ledger: Ledger | None = None,
        accountant: PrivacyAccountant | None = None,
    ) -> None:
        self.config = config or config_module.AppConfig.from_env()
        ledgers_dir = self.config.storage.data_dir / "ledgers"
        ledgers_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = ledgers_dir / "ledger.sqlite"
        self.ledger = ledger or Ledger(ledger_path)
        accountant_path = ledgers_dir / "dp_budget.sqlite"
        self.accountant = accountant or PrivacyAccountant(accountant_path)
        self.budgets = BudgetCaps(
            dau=self.config.dp.dau_budget_total,
            mau=self.config.dp.mau_budget_total,
        )
        self.events_loader = self.ledger.fetch_day_events
        self.sketch_factory = self._build_sketch_factory()
        self.window_manager = WindowManager(
            sketch_factory=self.sketch_factory,
            hll_rebuild_buffer=self.config.sketch.hll_rebuild_days_buffer,
        )

    def _build_sketch_factory(self) -> SketchFactory:
        builders: dict[str, callable] = {
            "set": SetSketch,
        }
        builders["hllpp"] = lambda: HllppSketch()
        try:
            builders["theta"] = ThetaSketch
        except ThetaSketchUnavailable:
            pass
        factory = SketchFactory(builders=builders, default_impl="set")
        if self.config.sketch.impl not in factory.builders:
            raise RuntimeError(
                f"Requested sketch implementation '{self.config.sketch.impl}' is unavailable."
            )
        factory.default_impl = self.config.sketch.impl
        return factory

    def ingest_event(self, event: EventRecord) -> None:
        if event.op not in {"+", "-"}:
            raise ValueError("Event op must be '+' or '-'.")
        day_str = event.day.isoformat()
        user_key = hash_user_id(event.user_id, event.day, self.config)
        user_root = hash_user_root(event.user_id, self.config)

        activity_entry = ActivityEntry(
            day=day_str,
            user_key=user_key,
            user_root=user_root,
            op=event.op,
            metadata=event.as_json(),
        )
        self.ledger.record_activity(activity_entry)
        self.window_manager.mark_dirty(day_str)

        if event.op == "-":
            days = event.metadata.get("days")
            if not days:
                days = self.ledger.days_for_user(user_root)
            if day_str not in days:
                days.append(day_str)
            erasure_entry = ErasureEntry(
                erasure_id=None, user_root=user_root, days=days, pending=True
            )
            self.ledger.record_erasure(erasure_entry)
            for affected_day in set(days):
                self.window_manager.mark_dirty(affected_day)

    def ingest_batch(self, events: Iterable[EventRecord]) -> None:
        for event in events:
            self.ingest_event(event)

    def replay_deletions(self) -> None:
        pending = self.ledger.pending_erasures()
        for erasure in pending:
            for day in erasure.days:
                self.window_manager.mark_dirty(day)
            if erasure.erasure_id is not None:
                self.ledger.mark_erasure_processed(erasure.erasure_id)

    def _release(
        self,
        metric: Literal["dau", "mau"],
        day: dt.date,
        base_value: float,
        sensitivity: float,
    ) -> MechanismResult:
        epsilon = self.config.dp.epsilon_dau if metric == "dau" else self.config.dp.epsilon_mau
        delta = self.config.dp.delta if metric == "mau" else 0.0
        cap = self.budgets.dau if metric == "dau" else self.budgets.mau
        if not self.accountant.can_release(metric, epsilon, day, cap):
            raise BudgetExceeded(f"{metric} budget exhausted for {day.isoformat()}")
        seed = _seed_for(metric, day, self.config.dp.default_seed)
        rng = random.Random(seed)
        if delta > 0:
            result = gaussian_mechanism(
                value=base_value,
                sensitivity=sensitivity,
                epsilon=epsilon,
                delta=delta,
                rng=rng,
                seed=seed,
            )
        else:
            result = laplace_mechanism(
                value=base_value,
                sensitivity=sensitivity,
                epsilon=epsilon,
                rng=rng,
                seed=seed,
            )
        self.accountant.record_release(
            metric=metric,
            day=day,
            epsilon=epsilon,
            delta=delta,
            mechanism=result.mechanism,
            seed=seed,
        )
        return result

    def get_daily_release(self, day: dt.date) -> dict[str, Any]:
        self.replay_deletions()
        day_str = day.isoformat()
        estimate, _sketch, keys = self.window_manager.get_dau(day_str, self.events_loader)
        base_value = float(len(keys))
        sensitivity = float(min(self.config.dp.w_bound, 1))
        dp_result = self._release("dau", day, base_value, sensitivity)
        budget_remaining = self.accountant.remaining_budget("dau", day, self.budgets.dau)
        return {
            "day": day_str,
            "estimate": dp_result.noisy_value,
            "lower_95": dp_result.confidence_interval[0],
            "upper_95": dp_result.confidence_interval[1],
            "epsilon_used": dp_result.epsilon,
            "delta": dp_result.delta,
            "mechanism": dp_result.mechanism,
            "sketch_impl": self.config.sketch.impl,
            "budget_remaining": budget_remaining,
            "exact_value": base_value,
        }

    def get_mau_release(self, end_day: dt.date, window_days: int | None = None) -> dict[str, Any]:
        self.replay_deletions()
        window = window_days or self.config.sketch.mau_window_days
        end_day_str = end_day.isoformat()
        value, _union = self.window_manager.get_mau(end_day_str, window, self.events_loader)
        base_value = float(value)
        sensitivity = float(self.config.dp.w_bound)
        dp_result = self._release("mau", end_day, base_value, sensitivity)
        budget_remaining = self.accountant.remaining_budget("mau", end_day, self.budgets.mau)
        return {
            "day": end_day_str,
            "window_days": window,
            "estimate": dp_result.noisy_value,
            "lower_95": dp_result.confidence_interval[0],
            "upper_95": dp_result.confidence_interval[1],
            "epsilon_used": dp_result.epsilon,
            "delta": dp_result.delta,
            "mechanism": dp_result.mechanism,
            "sketch_impl": self.config.sketch.impl,
            "budget_remaining": budget_remaining,
            "exact_value": base_value,
        }

    def reset_budget(self, metric: str, month: str) -> None:
        self.accountant.reset_month(metric, month)
