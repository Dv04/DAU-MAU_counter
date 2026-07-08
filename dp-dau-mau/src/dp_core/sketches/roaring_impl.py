"""RoaringBitmap-based sketch implementation."""

from __future__ import annotations

import pickle
import struct
from collections.abc import Iterable

import pyroaring

from .base import DistinctSketch, SketchConfig


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
