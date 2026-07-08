"""Ingestion and release pipeline orchestration."""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
from collections.abc import Iterable
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Literal

from . import config as config_module
from .dp_mechanisms import MechanismResult, gaussian_mechanism, laplace_mechanism
from .hashing import hash_user_id, hash_user_root
from .storage.log import ActivityEntry, ErasureEntry
from .storage.manager import PartitionedLogManager
from .privacy_accountant import BudgetCaps, PrivacyAccountant
from .sketches.base import SketchConfig, SketchFactory
from .sketches.kmv_impl import KMVSketch
from .sketches.roaring_impl import RoaringSketch
from .sketches.set_impl import SetSketch
from .windows import WindowManager


class BudgetExceededError(Exception):
    """Raised when attempting to exceed the allocated privacy budget."""

    def __init__(self, metric: str, day: dt.date, cap: float, spent: float) -> None:
        self.metric = metric
        self.day = day
        self.cap = cap
        self.spent = spent
        self.period = day.strftime("%Y-%m")
        message = (
            f"{metric} budget exhausted for {day.isoformat()} (spent={spent:.4f}, cap={cap:.4f})"
        )
        super().__init__(message)


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
    value = int.from_bytes(digest[:8], "big", signed=False)
    return value & 0x7FFF_FFFF_FFFF_FFFF


class PipelineManager:
    def __init__(
        self,
        config: config_module.AppConfig | None = None,
        log_manager: PartitionedLogManager | None = None,
        accountant: PrivacyAccountant | None = None,
    ) -> None:
        self.config = config or config_module.AppConfig.from_env()
        data_dir = self.config.storage.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_manager = log_manager or PartitionedLogManager(data_dir)
        
        ledgers_dir = data_dir / "ledgers"
        ledgers_dir.mkdir(parents=True, exist_ok=True)
        accountant_path = ledgers_dir / "dp_budget.sqlite"
        self.accountant = accountant or PrivacyAccountant(accountant_path)
        days_per_month = 31

        def _should_autoscale(env_var: str, default_value: float) -> bool:
            raw = os.environ.get(env_var)
            if raw is None:
                return True
            text = str(raw).strip()
            if config_module.PLACEHOLDER_PATTERN.fullmatch(text) is not None:
                return True
            try:
                value = float(text)
            except ValueError:
                return False
            return math.isclose(value, default_value, rel_tol=1e-9, abs_tol=1e-9)

        dau_cap = (
            max(self.config.dp.dau_budget_total, self.config.dp.epsilon_dau * days_per_month)
            if _should_autoscale("DAU_BUDGET_TOTAL", 3.0)
            else self.config.dp.dau_budget_total
        )
        mau_cap = (
            max(self.config.dp.mau_budget_total, self.config.dp.epsilon_mau * days_per_month)
            if _should_autoscale("MAU_BUDGET_TOTAL", 3.5)
            else self.config.dp.mau_budget_total
        )
        self.budgets = BudgetCaps(dau=dau_cap, mau=mau_cap)
        self.events_loader = self.log_manager.fetch_day_events
        self.sketch_factory = self._build_sketch_factory()
        self.window_manager = WindowManager(
            sketch_factory=self.sketch_factory,
            hll_rebuild_buffer=self.config.sketch.hll_rebuild_days_buffer,
        )

    def _build_sketch_factory(self) -> SketchFactory:
        sketch_cfg = SketchConfig(
            k=self.config.sketch.k,
            use_bloom_for_diff=self.config.sketch.use_bloom_for_diff,
            bloom_fp_rate=self.config.sketch.bloom_fp_rate,
        )
        factory = SketchFactory(
            config=sketch_cfg, backends={}, default_impl=self.config.sketch.impl
        )
        factory.register(
            "set",
            lambda cfg: SetSketch(cfg),
            lambda payload, cfg: SetSketch.deserialize(payload, cfg),
        )
        factory.register(
            "roaring",
            lambda cfg: RoaringSketch(cfg),
            lambda payload, cfg: RoaringSketch.deserialize(payload, cfg),
        )
        factory.register(
            "kmv",
            lambda cfg: KMVSketch(cfg),
            lambda payload, cfg: KMVSketch.deserialize(payload, cfg),
        )
        # Note: theta and hllpp backends were removed to simplify codebase
        # Only 'set', 'roaring', and 'kmv' are supported
        if self.config.sketch.impl not in factory.backends:
            raise RuntimeError(
                f"Requested sketch implementation '{self.config.sketch.impl}' is unavailable. "
                f"Available: {list(factory.backends.keys())}"
            )
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
        self.log_manager.append_activity(activity_entry)
        # Eagerly update in-memory state
        self.window_manager.update(day_str, event.op, user_key)

        if event.op == "-":
            days = event.metadata.get("days")
            if not days:
                days = self.log_manager.days_for_user(user_root)
            if day_str not in days:
                days.append(day_str)
            
            # Write tombstone events for each affected historical day
            # This enables retroactive erasure so rebuilding those days removes the user
            tombstone_entries: list[ActivityEntry] = []
            for affected_day_str in set(days):
                affected_day = dt.date.fromisoformat(affected_day_str)
                # Compute the correct user_key for that day's rotation epoch
                day_user_key = hash_user_id(event.user_id, affected_day, self.config)
                tombstone = ActivityEntry(
                    day=affected_day_str,
                    user_key=day_user_key,
                    user_root=user_root,
                    op="-",
                    metadata=json.dumps({"tombstone": True, "source_day": day_str}),
                )
                tombstone_entries.append(tombstone)
            
            # Batch insert all tombstones
            for entry in tombstone_entries:
                self.log_manager.append_activity(entry)
                # Eagerly update affected days in memory
                self.window_manager.update(entry.day, "-", entry.user_key)
            
            # Record erasure entry for auditing
            erasure_entry = ErasureEntry(
                erasure_id=None, user_root=user_root, days=list(set(days)), pending=True
            )
            self.log_manager.append_erasure(erasure_entry)
            # No need to mark dirty if we updated eagerly. 
            # But if older listeners rely on dirty, we might leave it?
            # No, let's trust eager updates.

    def ingest_batch(self, events: Iterable[EventRecord]) -> None:
        """
        Optimized ingestion loop for high throughput.
        Improvements:
        1. Buffered Log Writes (Batch Syscalls)
        2. Pre-calculated Salt (Avoid Hashing Setup)
        3. Inline Struct Unpacking (Avoid Function Calls)
        4. Array Buffering (Memory Efficiency)
        """
        import struct 
        import array
        import hmac
        from hashlib import sha256

        # Pre-calculate salts for likely days (memoization)
        # Assuming most events in batch are roughly contiguous or same day
        salt_cache: dict[str, bytes] = {}
        secret_bytes = self.config.security.hash_salt_secret.encode("utf-8") 
        if self.config.security.hash_salt_secret.startswith("b64:"):
             import base64
             secret_bytes = base64.b64decode(self.config.security.hash_salt_secret[4:])

        root_ctx = hmac.new(secret_bytes, digestmod=sha256)
        
        # State buffers
        adds: dict[str, array.array] = {}
        removes: dict[str, array.array] = {}

        # Buffered Logger
        with self.log_manager.buffered_writer() as log_writer:
            
            for event in events:
                day_str = event.day.isoformat()
                
                # 1. High-Performance Hashing
                # Compute User Root (reused for - op)
                # Optimization: reuse HMAC object? Standard lib doesn't easy copy.
                # Just doing hmac.new is fast enough if secret is pre-bytes.
                
                # Compute User Key (Salted)
                if day_str not in salt_cache:
                    # Salt derivation logic inlined/memoized
                    rotation_days = self.config.security.hash_salt_rotation_days
                    rotation_epoch = event.day.toordinal() // max(rotation_days, 1)
                    salt_msg = f"epoch::{rotation_epoch}".encode()
                    salt_cache[day_str] = hmac.new(secret_bytes, salt_msg, sha256).digest()
                
                day_salt = salt_cache[day_str]
                # hmac.new(key, msg, digest) is most efficient form
                user_key = hmac.new(day_salt, event.user_id.encode("utf-8"), sha256).digest()
                
                # 2. Log Activity (Buffered)
                user_root = b"" # Optimization: Only calculate root if needed (lazy)
                
                # We need `user_root` for ActivityEntry even if op is '+', 
                # because the log spec expects it.
                # Or can we optimize? The spec says 32s. 
                # Let's compute it.
                user_root = hmac.new(secret_bytes, event.user_id.encode("utf-8"), sha256).digest()

                activity = ActivityEntry(
                    day=day_str,
                    user_key=user_key,
                    user_root=user_root,
                    op=event.op,
                    metadata=event.as_json(),
                )
                log_writer.append_activity(activity)
                
                # 3. Buffer Update (Array)
                val = struct.unpack("<I", user_key[:4])[0]
                
                if event.op == "+":
                    if day_str not in adds: adds[day_str] = array.array('I')
                    adds[day_str].append(val)
                else:
                    if day_str not in removes: removes[day_str] = array.array('I')
                    removes[day_str].append(val)
                    
                    # Tombstones (Rare Path)
                    days = event.metadata.get("days")
                    if not days:
                         # Slow path requires Manager lookup
                        days = self.log_manager.days_for_user(user_root)
                    if day_str not in days: days.append(day_str)
                    
                    for affected_day_str in set(days):
                        if affected_day_str == day_str: continue 
                        
                        # Calculate salt for affected day
                        if affected_day_str not in salt_cache:
                             ad = dt.date.fromisoformat(affected_day_str)
                             re = ad.toordinal() // max(rotation_days, 1)
                             sm = f"epoch::{re}".encode()
                             salt_cache[affected_day_str] = hmac.new(secret_bytes, sm, sha256).digest()
                        
                        ad_salt = salt_cache[affected_day_str]
                        d_key = hmac.new(ad_salt, event.user_id.encode("utf-8"), sha256).digest()
                        
                        tombstone = ActivityEntry(
                            day=affected_day_str,
                            user_key=d_key,
                            user_root=user_root,
                            op="-",
                            metadata=json.dumps({"tombstone": True, "source_day": day_str}),
                        )
                        log_writer.append_activity(tombstone)
                        
                        d_val = struct.unpack("<I", d_key[:4])[0]
                        if affected_day_str not in removes: removes[affected_day_str] = array.array('I')
                        removes[affected_day_str].append(d_val)
                    
                    erasure_entry = ErasureEntry(
                        erasure_id=None, user_root=user_root, days=list(set(days)), pending=True
                    )
                    self.log_manager.append_erasure(erasure_entry)

        # 4. Flush bulk updates
        all_days = set(adds.keys()) | set(removes.keys())
        for day in all_days:
            self.window_manager.bulk_update(day, adds.get(day, []), removes.get(day, []))

    def replay_deletions(self) -> None:
        pending = self.log_manager.pending_erasures()
        for erasure in pending:
            for day in erasure.days:
                self.window_manager.mark_dirty(day)
            if erasure.erasure_id is not None:
                self.log_manager.mark_erasure_processed(erasure.erasure_id)

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
            spent = self.accountant.spent_budget(metric, day)
            raise BudgetExceededError(metric, day, cap, spent)
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
        self._log_rdp_release(metric, day, result)
        return result

    def get_daily_release(self, day: dt.date) -> dict[str, Any]:
        self.replay_deletions()
        day_str = day.isoformat()
        estimate, _sketch, exact_count = self.window_manager.get_dau(day_str, self.events_loader)
        base_value = float(exact_count)
        sensitivity = float(min(self.config.dp.w_bound, 1))
        dp_result = self._release("dau", day, base_value, sensitivity)
        budget = self.accountant.budget_snapshot(
            "dau",
            day,
            self.budgets.dau,
            0.0,
            self.config.dp.rdp_orders,
            self.config.dp.advanced_delta,
        )
        return {
            "day": day_str,
            "estimate": dp_result.noisy_value,
            "lower_95": dp_result.confidence_interval[0],
            "upper_95": dp_result.confidence_interval[1],
            "epsilon_used": dp_result.epsilon,
            "delta": dp_result.delta,
            "mechanism": dp_result.mechanism,
            "sketch_impl": self.config.sketch.impl,
            "budget_remaining": budget.epsilon_remaining,
            "budget": budget.as_dict(),
            "exact_value": base_value,
        }

    def get_mau_release(self, end_day: dt.date, window_days: int | None = None) -> dict[str, Any]:
        self.replay_deletions()
        window = window_days or self.config.sketch.mau_window_days
        end_day_str = end_day.isoformat()
        value, _union = self.window_manager.get_mau(end_day_str, window, self.events_loader)
        base_value = float(value)
        # Sensitivity = 1 for user-level DP (each user contributes at most 1 to count)
        # Hardcoded to 1.0 for safety; W_BOUND is reserved for future flippancy-aware mechanisms
        sensitivity = 1.0
        dp_result = self._release("mau", end_day, base_value, sensitivity)
        budget = self.accountant.budget_snapshot(
            "mau",
            end_day,
            self.budgets.mau,
            self.config.dp.delta,
            self.config.dp.rdp_orders,
            self.config.dp.advanced_delta,
        )
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
            "budget_remaining": budget.epsilon_remaining,
            "budget": budget.as_dict(),
            "exact_value": base_value,
        }

    def reset_budget(self, metric: str, month: str) -> None:
        self.accountant.reset_month(metric, month)

    def get_budget_summary(self, metric: str, day: dt.date) -> dict[str, Any]:
        metric = metric.lower()
        if metric not in {"dau", "mau"}:
            raise ValueError("metric must be 'dau' or 'mau'")
        cap = self.budgets.dau if metric == "dau" else self.budgets.mau
        delta = 0.0 if metric == "dau" else self.config.dp.delta
        snapshot = self.accountant.budget_snapshot(
            metric,
            day,
            cap,
            delta,
            self.config.dp.rdp_orders,
            self.config.dp.advanced_delta,
        )
        return snapshot.as_dict()

    def _log_rdp_release(self, metric: str, day: dt.date, result: MechanismResult) -> None:
        orders = getattr(self.config.dp, "rdp_orders", ())
        if not orders:
            return
        rdp_points: dict[float, float] = {}
        if result.mechanism == "gaussian":
            if result.delta <= 0:
                return
            sigma = (
                math.sqrt(2 * math.log(1.25 / result.delta))
                * result.sensitivity
                / max(result.epsilon, 1e-12)
            )
            if sigma <= 0:
                return
            variance = sigma * sigma
            for order in orders:
                if order <= 1:
                    continue
                rdp = (order * (result.sensitivity**2)) / (2 * variance)
                rdp_points[float(order)] = rdp
        else:
            for order in orders:
                if order <= 1:
                    continue
                rdp = (order / (order - 1.0)) * result.epsilon
                rdp_points[float(order)] = rdp
        if rdp_points:
            self.accountant.log_rdp_points(metric, day, rdp_points)
