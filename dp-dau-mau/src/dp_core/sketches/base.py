"""Abstract sketch interface and factory utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SketchConfig:
    """Runtime configuration shared by sketch implementations."""

    k: int
    use_bloom_for_diff: bool
    bloom_fp_rate: float


class DistinctSketch(ABC):
    """Common interface for distinct-count sketches."""

    @abstractmethod
    def add(self, key: bytes) -> None: ...

    @abstractmethod
    def union(self, other: "DistinctSketch") -> None: ...

    @abstractmethod
    def a_not_b(self, other: "DistinctSketch") -> "DistinctSketch": ...

    @abstractmethod
    def estimate(self) -> float: ...

    @abstractmethod
    def copy(self) -> "DistinctSketch": ...

    @abstractmethod
    def compact(self) -> None: ...

    @abstractmethod
    def serialize(self) -> bytes: ...

    @classmethod
    @abstractmethod
    def deserialize(cls, payload: bytes, config: SketchConfig) -> "DistinctSketch": ...


SketchBuilder = Callable[[SketchConfig], DistinctSketch]
SketchDeserializer = Callable[[bytes, SketchConfig], DistinctSketch]


@dataclass(slots=True)
class SketchBackend:
    build: SketchBuilder
    deserialize: SketchDeserializer


@dataclass(slots=True)
class SketchFactory:
    """Factory that produces sketches based on configuration."""

    config: SketchConfig
    backends: dict[str, SketchBackend]
    default_impl: str = "kmv"

    def register(
        self,
        name: str,
        builder: SketchBuilder,
        deserializer: SketchDeserializer,
    ) -> None:
        self.backends[name] = SketchBackend(build=builder, deserialize=deserializer)

    def _resolve(self, name: str | None) -> SketchBackend:
        impl_name = name or self.default_impl
        if impl_name not in self.backends:
            raise KeyError(f"Unknown sketch implementation: {impl_name}")
        return self.backends[impl_name]

    def create(self, name: str | None = None) -> DistinctSketch:
        backend = self._resolve(name)
        return backend.build(self.config)

    def deserialize(self, payload: bytes, name: str | None = None) -> DistinctSketch:
        backend = self._resolve(name)
        return backend.deserialize(payload, self.config)
