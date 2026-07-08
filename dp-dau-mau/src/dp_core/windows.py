"""Windowing logic for DAU and MAU computations."""

from __future__ import annotations

import datetime as dt
import struct
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import pyroaring

from .sketches.base import DistinctSketch, SketchFactory


def parse_day(day: str) -> dt.date:
    return dt.date.fromisoformat(day)


@dataclass(slots=True)
class DaySnapshot:
    sketch: DistinctSketch
    exact_count: int
    dirty: bool = False


@dataclass
class WindowManager:
    sketch_factory: SketchFactory
    hll_rebuild_buffer: int
    snapshots: dict[str, DaySnapshot] = field(default_factory=dict)

    def mark_dirty(self, day: str) -> None:
        # Legacy: still useful if we want to force reload
        if day in self.snapshots:
            self.snapshots[day].dirty = True

    def update(self, day: str, op: str, key: bytes) -> None:
        """Eagerly update the in-memory state."""
        if day not in self.snapshots:
            # Initialize empty snapshot if new day
            # We assume SetSketch or RoaringSketch based on factory
            sketch = self.sketch_factory.create()
            # If using Roaring, initialize the bitmap
            if hasattr(sketch, "_bitmap") and isinstance(sketch._bitmap, pyroaring.BitMap):
                 pass # Ready
            self.snapshots[day] = DaySnapshot(sketch=sketch, exact_count=0, dirty=False)
            
        snapshot = self.snapshots[day]
        if snapshot.dirty:
             # If dirty, we can't trust partial updates. 
             # Ideally we flush or reload. 
             # For now, if we are in eager mode, we assume we want to keep it fresh.
             # But if it was marked dirty externally, we might be desynced.
             # Let's assume eager updates are authoritative for the session.
             pass

        # Apply update
        val = struct.unpack("<I", key[:4])[0]
        
        # Optimization: Access bitmap directly if Roaring
        if hasattr(snapshot.sketch, "_bitmap") and isinstance(snapshot.sketch._bitmap, pyroaring.BitMap):
            if op == "+":
                snapshot.sketch._bitmap.add(val)
            elif op == "-":
                snapshot.sketch._bitmap.discard(val)
            snapshot.exact_count = len(snapshot.sketch._bitmap)
        else:
            # Fallback for generic sketches
            if op == "+":
                 snapshot.sketch.add(key)
                 # DistinctSketch doesn't support remove/discard generally!
                 # This assumes Roaring/Exact logic.
                 # If using KMV, removing is hard. 
                 # But we are optimizing for Roaring.
            elif op == "-":
                 # Not supported on base DistinctSketch without rebuild
                 # Mark dirty to force rebuild from log
                 snapshot.dirty = True

    def bulk_update(self, day: str, adds: Iterable[int], removes: Iterable[int]) -> None:
        """Batch update state using SIMD-accelerated bulk operations."""
        if day not in self.snapshots:
            sketch = self.sketch_factory.create()
            # If using Roaring, initialize the bitmap
            if hasattr(sketch, "_bitmap") and isinstance(sketch._bitmap, pyroaring.BitMap):
                 pass 
            self.snapshots[day] = DaySnapshot(sketch=sketch, exact_count=0, dirty=False)
            
        snapshot = self.snapshots[day]
        if snapshot.dirty:
             # See update() comment on dirty state
             pass
             
        # Optimization: Bulk ops on RoaringBitmap
        if hasattr(snapshot.sketch, "_bitmap") and isinstance(snapshot.sketch._bitmap, pyroaring.BitMap):
            if adds:
                snapshot.sketch._bitmap.update(adds)
            if removes:
                snapshot.sketch._bitmap.difference_update(removes)
            snapshot.exact_count = len(snapshot.sketch._bitmap)
        else:
            # Fallback for generic sketches
            for val in adds:
                 snapshot.sketch.add(struct.pack("<I", val))
            # No bulk remove for generic sketches without rebuild
            if removes:
                 snapshot.dirty = True
            
            # Update cache
            snapshot.exact_count = int(snapshot.sketch.estimate())

    def _build_snapshot(self, day: str, events: Iterable[tuple[str, bytes]]) -> DaySnapshot:
        # Use RoaringBitmap for high-performance accumulation
        # Maps 32-byte hash -> u32 (first 4 bytes).
        # Error rate ~0.01% at 1M users due to collisions.
        active = pyroaring.BitMap()
        
        for op, key in events:
            val = struct.unpack("<I", key[:4])[0]
            if op == "+":
                active.add(val)
            elif op == "-":
                active.discard(val)
                
        sketch = self.sketch_factory.create()
        
        # Optimization: Transfer bitmap directly to RoaringSketch
        if hasattr(sketch, "_bitmap") and isinstance(sketch._bitmap, pyroaring.BitMap):
            sketch._bitmap = active
            sketch.compact()
        else:
            # Fallback: Convert u32 back to bytes for other sketches
            for val in active:
                sketch.add(struct.pack("<I", val))
            sketch.compact()
            
        snapshot = DaySnapshot(sketch=sketch, exact_count=len(active), dirty=False)
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
    ) -> tuple[float, DistinctSketch, int]:
        snapshot = self.get_snapshot(day, events_loader)
        return snapshot.sketch.estimate(), snapshot.sketch, snapshot.exact_count

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
            union.union(snapshot.sketch)
            day += dt.timedelta(days=1)
        return union.estimate(), union
