"""RoaringBitmap-based sketch implementation.

PROVENANCE NOTE (added for the popets-strengtheners branch, 2026-07-08):
This file is a byte-for-byte snapshot (only the relative import below was
changed to an absolute one so it can be loaded standalone from experiments/)
of src/dp_core/sketches/roaring_impl.py as it exists, UNTRACKED, in the
working tree of the main DAU-MAU_counter checkout. It has never been
committed to any branch of this repository and is NOT registered in
PipelineManager._build_sketch_factory (src/dp_core/pipeline.py), which wires
up only "set" and "kmv". The paper text (paper/paper.tex) repeatedly
describes the evaluation as using "Roaring Bitmaps" as the exact backend
(e.g. Definition~\\ref{def:history-indep} discussion, Section on
implementation, throughput numbers such as 115k events/sec and 52s
ingestion for 1M users) -- none of that is backed by code that is actually
committed or covered by the 33 passing tests. We include this snapshot here
ONLY so Strengthener 1 can empirically test the orphaned implementation
that the paper's prose refers to, and we report its status honestly in
STRENGTHENERS_RESULTS.md. It is not part of the shipped package and this
file should not be imported by application code.
"""

from __future__ import annotations

import struct
from collections.abc import Iterable

import pyroaring

from dp_core.sketches.base import DistinctSketch, SketchConfig


class RoaringSketch(DistinctSketch):
    """Exact sketch using Roaring Bitmaps (u32 generation from hash)."""

    def __init__(self, config: SketchConfig, keys: Iterable[bytes] | None = None) -> None:
        self._config = config
        self._bitmap = pyroaring.BitMap()
        if keys:
            for k in keys:
                self.add(k)

    def add(self, key: bytes) -> None:
        # Take first 4 bytes as u32
        # Note: This has collision risk for 1M users (approx 0.01% error)
        val = struct.unpack("<I", key[:4])[0]
        self._bitmap.add(val)

    def discard(self, key: bytes) -> None:
        val = struct.unpack("<I", key[:4])[0]
        self._bitmap.discard(val)

    def union(self, other: DistinctSketch) -> None:
        if not isinstance(other, RoaringSketch):
            raise TypeError("RoaringSketch union requires another RoaringSketch.")
        self._bitmap |= other._bitmap

    def a_not_b(self, other: DistinctSketch) -> RoaringSketch:
        if not isinstance(other, RoaringSketch):
            raise TypeError("RoaringSketch a_not_b requires another RoaringSketch.")
        new_sketch = RoaringSketch(self._config)
        new_sketch._bitmap = self._bitmap - other._bitmap
        return new_sketch

    def estimate(self) -> float:
        return float(len(self._bitmap))

    def copy(self) -> RoaringSketch:
        new_sketch = RoaringSketch(self._config)
        new_sketch._bitmap = self._bitmap.copy()
        return new_sketch

    def compact(self) -> None:
        self._bitmap.run_optimize()

    def serialize(self) -> bytes:
        return self._bitmap.serialize()

    @classmethod
    def deserialize(cls, payload: bytes, config: SketchConfig) -> RoaringSketch:
        sketch = cls(config)
        sketch._bitmap = pyroaring.BitMap.deserialize(payload)
        return sketch

    def keys_as_ints(self) -> list[int]:
        return list(self._bitmap)
