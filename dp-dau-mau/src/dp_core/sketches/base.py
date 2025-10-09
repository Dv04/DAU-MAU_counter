"""Abstract sketch interface and factory utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class DistinctSketch(Protocol):
    """Common interface for distinct-count sketches."""

    def add(self, key: bytes) -> None: ...

    def merge(self, other: "DistinctSketch") -> None: ...

    def estimate(self) -> float: ...

    def copy(self) -> "DistinctSketch": ...

    def difference(self, other: "DistinctSketch") -> "DistinctSketch": ...


SketchBuilder = Callable[[], DistinctSketch]


@dataclass(slots=True)
class SketchFactory:
    """Factory that produces sketches based on configuration."""

    builders: dict[str, SketchBuilder]
    default_impl: str = "set"

    def register(self, name: str, builder: SketchBuilder) -> None:
        self.builders[name] = builder

    def create(self, name: str | None = None) -> DistinctSketch:
        impl_name = name or self.default_impl
        if impl_name not in self.builders:
            raise KeyError(f"Unknown sketch implementation: {impl_name}")
        return self.builders[impl_name]()
