"""Roaring-bitmap-based exact sketch implementation.

Backs the paper's "Roaring Bitmaps (exact compressed sets)" evaluation
backend. Keys of any length (in production, 32-byte SHA-256 HMAC digests
from ``hashing.hash_user_id``) are hashed with a personalized BLAKE2b to an
8-byte digest -- the same approach ``kmv_impl._hash_key`` uses -- and stored
as 64-bit unsigned integers in a ``pyroaring.BitMap64`` (CRoaring C++
bindings).

Why 64-bit and not 32-bit: an earlier draft of this backend truncated keys
to the first 4 bytes (32 bits) before inserting them into a 32-bit
``pyroaring.BitMap``. At the paper's target scale of 1M users, the birthday
bound on a 32-bit space (2^32 slots) gives an expected number of colliding
pairs of approximately::

    n^2 / (2 * 2^32) = (1e6)^2 / (2 * 4.295e9) ~= 116

i.e. roughly a hundred pairs of distinct users silently merging into one
bitmap slot -- a real, measurable exactness violation for a backend the
paper describes as "exact". Hashing to a 64-bit space instead makes the
same calculation ``n^2 / (2 * 2^64) ~= 2.7e-8`` -- negligible for any scale
this paper evaluates -- so cardinality and history-independence hold
exactly in practice.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

import pyroaring

from .base import DistinctSketch, SketchConfig

_PERSON = b"dpdau-roar"


def _hash_key(key: bytes) -> int:
    digest = hashlib.blake2b(key, digest_size=8, person=_PERSON).digest()
    return int.from_bytes(digest, "big", signed=False)


class RoaringSketch(DistinctSketch):
    """Exact sketch backed by a 64-bit Roaring bitmap."""

    def __init__(self, config: SketchConfig, keys: Iterable[bytes] | None = None) -> None:
        self._config = config
        self._bitmap = pyroaring.BitMap64()
        if keys:
            for key in keys:
                self.add(key)

    def add(self, key: bytes) -> None:
        self._bitmap.add(_hash_key(key))

    def discard(self, key: bytes) -> None:
        """Remove a key if present. Exact and idempotent (no-op if absent).

        Not part of the abstract ``DistinctSketch`` interface -- the
        pipeline achieves erasure by rebuilding each dirty day's sketch
        from the replayed activity log (see ``windows.WindowManager``)
        rather than by incremental deletion. ``discard`` is provided so the
        backend can also be exercised/tested directly for exact,
        history-independent removal.
        """
        self._bitmap.discard(_hash_key(key))

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
        sketch._bitmap = pyroaring.BitMap64.deserialize(payload)
        return sketch

    def keys_as_ints(self) -> list[int]:
        """Testing helper exposing the underlying 64-bit values."""
        return list(self._bitmap)

    def __len__(self) -> int:
        return len(self._bitmap)
