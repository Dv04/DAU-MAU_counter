"""Simplified HLL++ implementation for approximate distinct counting."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable

from .base import DistinctSketch


def _rho(w: int, max_bits: int) -> int:
    leading = 1
    while leading <= max_bits and w & 0x8000000000000000 == 0:
        leading += 1
        w <<= 1
    return leading


class HllppSketch(DistinctSketch):
    """Minimal HyperLogLog++ sketch for PoC purposes.

    Deletions are not supported natively; the pipeline rebuilds affected days using cached keys.
    """

    def __init__(self, precision: int = 14, registers: list[int] | None = None) -> None:
        if not 4 <= precision <= 16:
            raise ValueError("precision must be between 4 and 16")
        self.precision = precision
        self.m = 1 << precision
        self.alpha = 0.7213 / (1 + 1.079 / self.m)
        self.registers = registers or [0] * self.m

    def _hash(self, key: bytes) -> int:
        return int(hashlib.sha256(key).hexdigest(), 16)

    def add(self, key: bytes) -> None:
        x = self._hash(key)
        idx = x & (self.m - 1)
        w = x >> self.precision
        rank = _rho(w << (64 - self.precision), 64 - self.precision)
        self.registers[idx] = max(self.registers[idx], rank)

    def merge(self, other: DistinctSketch) -> None:
        if not isinstance(other, HllppSketch):
            raise TypeError("HllppSketch can only merge another HllppSketch.")
        if other.precision != self.precision:
            raise ValueError("Precision mismatch between sketches.")
        self.registers = [max(a, b) for a, b in zip(self.registers, other.registers, strict=False)]

    def estimate(self) -> float:
        indicator_sum = sum(2.0 ** (-r) for r in self.registers)
        raw_estimate = self.alpha * (self.m**2) / indicator_sum
        if raw_estimate <= 2.5 * self.m:
            zeros = self.registers.count(0)
            if zeros:
                return float(self.m * math.log(self.m / zeros))
        if raw_estimate > (1 / 30) * (1 << 32):
            return float(-(1 << 32) * math.log(1 - raw_estimate / (1 << 32)))
        return float(raw_estimate)

    def copy(self) -> HllppSketch:
        return HllppSketch(self.precision, self.registers.copy())

    def difference(self, other: DistinctSketch) -> DistinctSketch:
        raise NotImplementedError(
            "HllppSketch does not support difference; rebuild via cached per-day keys "
            "and respect {{HLL_REBUILD_DAYS_BUFFER}}."
        )

    def rebuild_from_keys(self, keys: Iterable[bytes]) -> None:
        self.registers = [0] * self.m
        for key in keys:
            self.add(key)
