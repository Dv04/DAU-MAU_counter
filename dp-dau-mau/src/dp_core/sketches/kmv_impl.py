"""KMV bottom-k sketch implementation with approximate set difference."""

from __future__ import annotations

import bisect
import hashlib
import math
import struct
from array import array
from collections.abc import Iterable
from dataclasses import dataclass

from .base import DistinctSketch, SketchConfig

MAX_HASH = (1 << 64) - 1
PERSON = b"dpdau-kmv"


def _hash_key(key: bytes) -> int:
    digest = hashlib.blake2b(key, digest_size=8, person=PERSON).digest()
    return int.from_bytes(digest, "big", signed=False)


class _PlainMembership:
    __slots__ = ("_set",)

    def __init__(self, hashes: Iterable[int]) -> None:
        self._set = set(hashes)

    def contains(self, value: int) -> bool:
        return value in self._set


@dataclass(slots=True)
class _BloomMembership:
    m: int
    k: int
    bits: bytearray

    @classmethod
    def build(cls, values: Iterable[int], fp_rate: float) -> _BloomMembership:
        vals = list(values)
        n = max(len(vals), 1)
        fp = min(max(fp_rate, 1e-6), 1 - 1e-6)
        m = int(math.ceil(-(n * math.log(fp)) / (math.log(2) ** 2)))
        m = max(m, 8)
        k = max(1, int(round((m / n) * math.log(2))))
        bits = bytearray((m + 7) // 8)
        inst = cls(m=m, k=k, bits=bits)
        for value in vals:
            inst._add(value)
        return inst

    def _hash(self, value: int, seed: int) -> int:
        data = value.to_bytes(8, "big") + seed.to_bytes(2, "big")
        digest = hashlib.blake2b(data, digest_size=8, person=b"kmv-bloom").digest()
        return int.from_bytes(digest, "big", signed=False) % self.m

    def _add(self, value: int) -> None:
        for i in range(self.k):
            idx = self._hash(value, i)
            self.bits[idx // 8] |= 1 << (idx % 8)

    def contains(self, value: int) -> bool:
        for i in range(self.k):
            idx = self._hash(value, i)
            if not (self.bits[idx // 8] & (1 << (idx % 8))):
                return False
        return True


class KMVSketch(DistinctSketch):
    """Approximate distinct counter using bottom-k sampling."""

    def __init__(
        self,
        config: SketchConfig,
        hashes: Iterable[int] | None = None,
    ) -> None:
        self._config = config
        unique = sorted(set(hashes or []))
        self._hashes = unique[: self._config.k]
        self._hash_set = set(self._hashes)

    def _normalize(self, value: int) -> float:
        return value / MAX_HASH if value else 0.0

    def _threshold(self) -> float:
        if len(self._hashes) < self._config.k:
            return 1.0
        return self._normalize(self._hashes[-1])

    def add(self, key: bytes) -> None:
        hashed = _hash_key(key)
        if hashed in self._hash_set:
            return
        if len(self._hashes) < self._config.k:
            bisect.insort(self._hashes, hashed)
            self._hash_set.add(hashed)
            return
        largest = self._hashes[-1]
        if hashed >= largest:
            return
        bisect.insort(self._hashes, hashed)
        self._hash_set.add(hashed)
        # trim to k smallest
        while len(self._hashes) > self._config.k:
            removed = self._hashes.pop()
            self._hash_set.discard(removed)

    def union(self, other: DistinctSketch) -> None:
        if not isinstance(other, KMVSketch):
            raise TypeError("KMVSketch union requires another KMVSketch.")
        merged = sorted(set(self._hashes).union(other._hashes))
        self._hashes = merged[: self._config.k]
        self._hash_set = set(self._hashes)

    def _membership(self) -> object:
        if not self._hashes:
            return _PlainMembership([])
        if self._config.use_bloom_for_diff:
            return _BloomMembership.build(self._hashes, self._config.bloom_fp_rate)
        return _PlainMembership(self._hashes)

    def a_not_b(self, other: DistinctSketch) -> KMVSketch:
        if not isinstance(other, KMVSketch):
            raise TypeError("KMVSketch a_not_b requires another KMVSketch.")
        membership = other._membership()
        kept: list[int] = []
        for hashed in self._hashes:
            contains = membership.contains(hashed) if hasattr(membership, "contains") else False
            if not contains:
                kept.append(hashed)
                if len(kept) == self._config.k:
                    break
        return KMVSketch(self._config, kept)

    def estimate(self) -> float:
        if not self._hashes:
            return 0.0
        if len(self._hashes) < self._config.k:
            return float(len(self._hashes))
        tau = self._threshold()
        if tau <= 0:
            return float(len(self._hashes))
        return float((self._config.k - 1) / tau)

    def copy(self) -> KMVSketch:
        return KMVSketch(self._config, self._hashes)

    def compact(self) -> None:
        # ensure internal cache is trimmed
        if len(self._hashes) > self._config.k:
            self._hashes = self._hashes[: self._config.k]
            self._hash_set = set(self._hashes)

    def serialize(self) -> bytes:
        arr = array("Q", self._hashes)
        header = struct.pack("!II", self._config.k, len(self._hashes))
        return header + arr.tobytes()

    @classmethod
    def deserialize(cls, payload: bytes, config: SketchConfig) -> KMVSketch:
        if len(payload) < 8:
            raise ValueError("Invalid KMV sketch payload.")
        k, count = struct.unpack("!II", payload[:8])
        if k != config.k:
            # proceed but honour runtime configuration
            count = min(count, config.k)
        arr = array("Q")
        arr.frombytes(payload[8 : 8 + count * 8])
        hashes = list(arr)[: config.k]
        return cls(config, hashes)
