"""Deterministic set-based sketch implementation."""

from __future__ import annotations

from typing import Iterable

from .base import DistinctSketch


class SetSketch(DistinctSketch):
    """Reference implementation using an in-memory set of hashes."""

    def __init__(self, keys: Iterable[bytes] | None = None) -> None:
        self._keys = set(keys or [])

    def add(self, key: bytes) -> None:
        self._keys.add(key)

    def merge(self, other: DistinctSketch) -> None:
        if isinstance(other, SetSketch):
            self._keys.update(other._keys)
        else:
            raise TypeError("SetSketch can only merge another SetSketch.")

    def estimate(self) -> float:
        return float(len(self._keys))

    def copy(self) -> "SetSketch":
        return SetSketch(self._keys)

    def difference(self, other: DistinctSketch) -> "SetSketch":
        if not isinstance(other, SetSketch):
            raise TypeError("SetSketch difference requires another SetSketch.")
        return SetSketch(self._keys.difference(other._keys))

    def keys(self) -> set[bytes]:
        return set(self._keys)
