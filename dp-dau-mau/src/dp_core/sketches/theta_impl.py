"""Theta sketch implementation with optional dependency."""

from __future__ import annotations

from .base import DistinctSketch, SketchConfig

try:
    from datasketches import CompactThetaSketch, ThetaANotB, UpdateThetaSketch
except ImportError:  # pragma: no cover - optional dependency
    CompactThetaSketch = None  # type: ignore[assignment]
    ThetaANotB = None  # type: ignore[assignment]
    UpdateThetaSketch = None  # type: ignore[assignment]


class ThetaSketchUnavailableError(RuntimeError):
    """Raised when the datasketches dependency is missing."""


class ThetaSketch(DistinctSketch):
    """Wrapper around Apache DataSketches Theta implementation."""

    def __init__(
        self,
        config: SketchConfig,
        sketch: UpdateThetaSketch | None = None,
    ) -> None:
        if UpdateThetaSketch is None:
            raise ThetaSketchUnavailableError(
                "datasketches package not installed. Set {{SKETCH_IMPL}} to 'kmv' or 'set' "
                "or install the dependency."
            )
        self._config = config
        self._sketch: UpdateThetaSketch = sketch or UpdateThetaSketch()

    def add(self, key: bytes) -> None:
        self._sketch.update(bytes(key))

    def union(self, other: DistinctSketch) -> None:
        if not isinstance(other, ThetaSketch):
            raise TypeError("ThetaSketch union requires another ThetaSketch.")
        self._sketch.merge(other._sketch)

    def a_not_b(self, other: DistinctSketch) -> "ThetaSketch":
        if ThetaANotB is None:
            raise ThetaSketchUnavailableError("datasketches ThetaANotB unavailable.")
        if not isinstance(other, ThetaSketch):
            raise TypeError("ThetaSketch a_not_b requires another ThetaSketch.")
        result = ThetaANotB()
        result.set_a(self._sketch.compact())
        result.set_b(other._sketch.compact())
        return ThetaSketch(self._config, result.get_result().to_update_theta_sketch())

    def estimate(self) -> float:
        return float(self._sketch.get_estimate())

    def copy(self) -> "ThetaSketch":
        new_sketch = UpdateThetaSketch()
        new_sketch.merge(self._sketch)
        return ThetaSketch(self._config, new_sketch)

    def compact(self) -> None:
        compacted = self._sketch.compact()
        refreshed = UpdateThetaSketch()
        refreshed.merge(compacted)
        self._sketch = refreshed

    def serialize(self) -> bytes:
        compacted = self._sketch.compact()
        if hasattr(compacted, "serialize"):
            return compacted.serialize()  # type: ignore[no-any-return]
        if hasattr(compacted, "to_bytearray"):
            return bytes(compacted.to_bytearray())  # type: ignore[no-any-return]
        raise ThetaSketchUnavailableError("datasketches serialization API unavailable.")

    @classmethod
    def deserialize(cls, payload: bytes, config: SketchConfig) -> "ThetaSketch":
        if UpdateThetaSketch is None:
            raise ThetaSketchUnavailableError(
                "datasketches package not installed."
            )
        if hasattr(UpdateThetaSketch, "heapify"):
            compact = UpdateThetaSketch.heapify(payload)  # type: ignore[attr-defined]
        elif CompactThetaSketch is not None and hasattr(CompactThetaSketch, "deserialize"):
            compact = CompactThetaSketch.deserialize(payload)  # type: ignore[attr-defined]
        else:
            raise ThetaSketchUnavailableError(
                "datasketches version does not support heapify/deserialize APIs."
            )
        new_sketch = UpdateThetaSketch()
        new_sketch.merge(compact)
        return cls(config, new_sketch)
