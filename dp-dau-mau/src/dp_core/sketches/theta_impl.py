"""Theta sketch implementation with optional dependency."""

from __future__ import annotations

from .base import DistinctSketch

try:
    from datasketches import ThetaANotB, UpdateThetaSketch
except ImportError:  # pragma: no cover - optional dependency
    ThetaANotB = None  # type: ignore[assignment]
    UpdateThetaSketch = None  # type: ignore[assignment]


class ThetaSketchUnavailable(RuntimeError):
    """Raised when the datasketches dependency is missing."""


class ThetaSketch(DistinctSketch):
    """Wrapper around Apache DataSketches Theta implementation."""

    def __init__(self, sketch: UpdateThetaSketch | None = None) -> None:
        if UpdateThetaSketch is None:
            raise ThetaSketchUnavailable(
                "datasketches package not installed. Set {{SKETCH_IMPL}} to 'set' or install the dependency."
            )
        self._sketch: UpdateThetaSketch = sketch or UpdateThetaSketch()

    def add(self, key: bytes) -> None:
        self._sketch.update(bytes(key))

    def merge(self, other: DistinctSketch) -> None:
        if not isinstance(other, ThetaSketch):
            raise TypeError("ThetaSketch can only merge another ThetaSketch.")
        self._sketch.merge(other._sketch)

    def estimate(self) -> float:
        return float(self._sketch.get_estimate())

    def copy(self) -> ThetaSketch:
        new_sketch = UpdateThetaSketch()
        new_sketch.merge(self._sketch)
        return ThetaSketch(new_sketch)

    def difference(self, other: DistinctSketch) -> ThetaSketch:
        if ThetaANotB is None:
            raise ThetaSketchUnavailable("datasketches ThetaANotB unavailable.")
        if not isinstance(other, ThetaSketch):
            raise TypeError("ThetaSketch difference requires another ThetaSketch.")
        result = ThetaANotB()
        result.set_a(self._sketch.compact())
        result.set_b(other._sketch.compact())
        return ThetaSketch(result.get_result().to_update_theta_sketch())
