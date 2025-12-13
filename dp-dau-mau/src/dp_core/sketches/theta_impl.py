"""Theta sketch implementation with optional dependency."""

from __future__ import annotations

from .base import DistinctSketch, SketchConfig

try:  # Prefer the class-based API (datasketches <4.x)
    from datasketches import CompactThetaSketch, ThetaANotB, ThetaUnion, UpdateThetaSketch
except ImportError:  # pragma: no cover - optional dependency
    CompactThetaSketch = None  # type: ignore[assignment]
    ThetaANotB = None  # type: ignore[assignment]
    ThetaUnion = None  # type: ignore[assignment]
    UpdateThetaSketch = None  # type: ignore[assignment]
    try:
        import datasketches as _ds  # type: ignore
    except ImportError:  # pragma: no cover
        _ds = None
    if _ds is not None:  # datasketches 4.x exposes factory functions instead of classes
        UpdateThetaSketch = getattr(_ds, "update_theta_sketch", None)
        CompactThetaSketch = getattr(_ds, "compact_theta_sketch", None)
        ThetaANotB = getattr(_ds, "theta_a_not_b", None)
        ThetaUnion = getattr(_ds, "theta_union", None)


class ThetaSketchUnavailableError(RuntimeError):
    """Raised when the datasketches dependency is missing."""


def _new_update_sketch() -> object:
    """Return a fresh UpdateThetaSketch, supporting both class and factory APIs."""
    if UpdateThetaSketch is None:
        raise ThetaSketchUnavailableError(
            "datasketches package not installed. Set {{SKETCH_IMPL}} to 'kmv' or 'set' "
            "or install the dependency."
        )
    # datasketches<4: UpdateThetaSketch is a class; >=4: it is a factory function
    try:
        return UpdateThetaSketch()  # type: ignore[call-arg]
    except TypeError as exc:  # pragma: no cover - defensive
        raise ThetaSketchUnavailableError(
            "datasketches Theta update sketch could not be constructed."
        ) from exc


def _to_theta_value(key: bytes) -> int:
    """Map arbitrary bytes to an int acceptable by datasketches update().

    Newer datasketches (5.x) only accepts int/float/str; we hash-bytes to a 64-bit int.
    """
    return int.from_bytes(key, "big", signed=False) & ((1 << 63) - 1)


def _as_compact(sketch: object) -> object:
    """Convert an update sketch to a compact sketch when possible."""
    if hasattr(sketch, "compact"):
        return sketch.compact()  # type: ignore[attr-defined]
    if CompactThetaSketch is not None and isinstance(sketch, CompactThetaSketch):
        return sketch
    raise ThetaSketchUnavailableError("Theta sketch cannot be compacted with current backend.")


class ThetaSketch(DistinctSketch):
    """Wrapper around Apache DataSketches Theta implementation."""

    def __init__(
        self,
        config: SketchConfig,
        sketch: object | None = None,
    ) -> None:
        self._config = config
        self._sketch: object = sketch or _new_update_sketch()

    def add(self, key: bytes) -> None:
        if not hasattr(self._sketch, "update"):
            raise ThetaSketchUnavailableError("Theta sketch is compact; cannot add more items.")
        self._sketch.update(_to_theta_value(key))

    def union(self, other: DistinctSketch) -> None:
        if not isinstance(other, ThetaSketch):
            raise TypeError("ThetaSketch union requires another ThetaSketch.")
        if ThetaUnion is not None:
            union = ThetaUnion()
            union.update(_as_compact(self._sketch))
            union.update(_as_compact(other._sketch))
            self._sketch = union.get_result()
            return
        if hasattr(self._sketch, "merge"):
            self._sketch.merge(other._sketch)  # type: ignore[attr-defined]
            return
        raise ThetaSketchUnavailableError("Theta union unavailable in current datasketches build.")

    def a_not_b(self, other: DistinctSketch) -> ThetaSketch:
        if ThetaANotB is None:
            raise ThetaSketchUnavailableError("datasketches ThetaANotB unavailable.")
        if not isinstance(other, ThetaSketch):
            raise TypeError("ThetaSketch a_not_b requires another ThetaSketch.")
        a_compact = _as_compact(self._sketch)
        b_compact = _as_compact(other._sketch)
        if hasattr(ThetaANotB, "compute"):
            a_not_b = ThetaANotB()
            result = a_not_b.compute(a_compact, b_compact)
            return ThetaSketch(self._config, result)
        if hasattr(ThetaANotB, "set_a"):
            a_not_b = ThetaANotB()
            a_not_b.set_a(a_compact)  # type: ignore[attr-defined]
            a_not_b.set_b(b_compact)  # type: ignore[attr-defined]
            result = a_not_b.get_result()
            return ThetaSketch(self._config, result)
        raise ThetaSketchUnavailableError("Theta A-not-B API not supported by this version.")

    def estimate(self) -> float:
        return float(self._sketch.get_estimate())

    def copy(self) -> ThetaSketch:
        compact = _as_compact(self._sketch)
        return ThetaSketch(self._config, compact)

    def compact(self) -> None:
        self._sketch = _as_compact(self._sketch)

    def serialize(self) -> bytes:
        compacted = _as_compact(self._sketch)
        if hasattr(compacted, "serialize"):
            return compacted.serialize()  # type: ignore[no-any-return]
        if hasattr(compacted, "to_bytearray"):
            return bytes(compacted.to_bytearray())  # type: ignore[no-any-return]
        raise ThetaSketchUnavailableError("datasketches serialization API unavailable.")

    @classmethod
    def deserialize(cls, payload: bytes, config: SketchConfig) -> ThetaSketch:
        if CompactThetaSketch is not None and hasattr(CompactThetaSketch, "deserialize"):
            compact = CompactThetaSketch.deserialize(payload)  # type: ignore[attr-defined]
            return cls(config, compact)
        raise ThetaSketchUnavailableError(
            "datasketches version does not support Theta deserialization APIs."
        )
