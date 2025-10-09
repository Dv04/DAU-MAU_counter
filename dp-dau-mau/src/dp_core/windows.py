"""Windowing logic for DAU and MAU computations."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .sketches.base import DistinctSketch, SketchFactory


def parse_day(day: str) -> dt.date:
    return dt.date.fromisoformat(day)


@dataclass(slots=True)
class DaySnapshot:
    sketch: DistinctSketch
    keys: set[bytes]
    dirty: bool = False


@dataclass
class WindowManager:
    sketch_factory: SketchFactory
    hll_rebuild_buffer: int
    snapshots: dict[str, DaySnapshot] = field(default_factory=dict)

    def mark_dirty(self, day: str) -> None:
        if day in self.snapshots:
            self.snapshots[day].dirty = True

    def _build_snapshot(self, day: str, events: Iterable[tuple[str, bytes]]) -> DaySnapshot:
        active: set[bytes] = set()
        for op, key in events:
            if op == "+":
                active.add(key)
            elif op == "-":
                active.discard(key)
        sketch = self.sketch_factory.create()
        for key in active:
            sketch.add(key)
        snapshot = DaySnapshot(sketch=sketch, keys=active, dirty=False)
        self.snapshots[day] = snapshot
        return snapshot

    def get_snapshot(
        self, day: str, events_loader: Callable[[str], Iterable[tuple[str, bytes]]]
    ) -> DaySnapshot:
        snapshot = self.snapshots.get(day)
        if snapshot is None or snapshot.dirty:
            events = events_loader(day)
            snapshot = self._build_snapshot(day, events)
        return snapshot

    def get_dau(
        self, day: str, events_loader: Callable[[str], Iterable[tuple[str, bytes]]]
    ) -> tuple[float, DistinctSketch, set[bytes]]:
        snapshot = self.get_snapshot(day, events_loader)
        return snapshot.sketch.estimate(), snapshot.sketch, snapshot.keys

    def get_mau(
        self,
        end_day: str,
        window_days: int,
        events_loader: Callable[[str], Iterable[tuple[str, bytes]]],
    ) -> tuple[float, DistinctSketch]:
        end = parse_day(end_day)
        start = end - dt.timedelta(days=window_days - 1)
        union = self.sketch_factory.create()
        day = start
        while day <= end:
            day_key = day.isoformat()
            snapshot = self.get_snapshot(day_key, events_loader)
            union.merge(snapshot.sketch)
            day += dt.timedelta(days=1)
        return union.estimate(), union
