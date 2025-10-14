"""Deterministic set-based sketch implementation."""

from __future__ import annotations

import pickle
from collections.abc import Iterable

from .base import DistinctSketch, SketchConfig


class SetSketch(DistinctSketch):
    """Exact set sketch; suitable for tests and small workloads only."""

    def __init__(self, config: SketchConfig, keys: Iterable[bytes] | None = None) -> None:
        self._config = config
        self._keys = set(keys or [])

    def add(self, key: bytes) -> None:
        self._keys.add(key)

    def union(self, other: DistinctSketch) -> None:
        if not isinstance(other, SetSketch):
            raise TypeError("SetSketch union requires another SetSketch.")
        self._keys.update(other._keys)

    def a_not_b(self, other: DistinctSketch) -> "SetSketch":
        if not isinstance(other, SetSketch):
            raise TypeError("SetSketch a_not_b requires another SetSketch.")
        return SetSketch(self._config, self._keys.difference(other._keys))

    def estimate(self) -> float:
        return float(len(self._keys))

    def copy(self) -> "SetSketch":
        return SetSketch(self._config, self._keys)

    def compact(self) -> None:
        # No-op: set already compact in memory.
        return None

    def serialize(self) -> bytes:
        return pickle.dumps(tuple(self._keys))

    @classmethod
    def deserialize(cls, payload: bytes, config: SketchConfig) -> "SetSketch":
        keys = pickle.loads(payload)
        return cls(config, keys)

    def keys(self) -> set[bytes]:
        """Testing helper exposing the underlying keys."""
        return set(self._keys)
