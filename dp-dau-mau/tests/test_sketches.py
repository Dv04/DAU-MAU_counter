import math

import pytest

from dp_core.sketches.base import SketchConfig
from dp_core.sketches.kmv_impl import KMVSketch
from dp_core.sketches.set_impl import SetSketch

SKETCH_CFG = SketchConfig(k=256, use_bloom_for_diff=False, bloom_fp_rate=0.01)


def test_set_sketch_exact_difference() -> None:
    sketch_a = SetSketch(SKETCH_CFG)
    sketch_b = SetSketch(SKETCH_CFG)
    sketch_a.add(b"alice")
    sketch_a.add(b"bob")
    sketch_b.add(b"bob")

    diff = sketch_a.a_not_b(sketch_b)
    assert diff.estimate() == 1.0
    assert diff.keys() == {b"alice"}


def test_kmv_union_monotonic() -> None:
    cfg = SketchConfig(k=256, use_bloom_for_diff=False, bloom_fp_rate=0.01)
    sketch_a = KMVSketch(cfg)
    sketch_b = KMVSketch(cfg)
    for i in range(300):
        key = f"user-{i}".encode()
        sketch_a.add(key)
        if i >= 50:
            sketch_b.add(key)
    before = sketch_a.estimate()
    sketch_a.union(sketch_b)
    assert sketch_a.estimate() >= before - 1e-6


def test_kmv_difference_monotonic() -> None:
    cfg = SketchConfig(k=256, use_bloom_for_diff=True, bloom_fp_rate=0.01)
    sketch_a = KMVSketch(cfg)
    sketch_b = KMVSketch(cfg)
    for i in range(400):
        key = f"user-{i}".encode()
        sketch_a.add(key)
        if i % 3 == 0:
            sketch_b.add(key)
    diff = sketch_a.a_not_b(sketch_b)
    assert diff.estimate() <= sketch_a.estimate() + 1e-6


def test_kmv_estimate_within_reasonable_error() -> None:
    cfg = SketchConfig(k=512, use_bloom_for_diff=False, bloom_fp_rate=0.01)
    sketch = KMVSketch(cfg)
    population = 5000
    for i in range(population):
        sketch.add(f"population-{i}".encode())
    estimate = sketch.estimate()
    rel_error = math.fabs(estimate - population) / population
    assert rel_error < 0.25


def test_kmv_serialization_roundtrip() -> None:
    cfg = SketchConfig(k=128, use_bloom_for_diff=False, bloom_fp_rate=0.01)
    sketch = KMVSketch(cfg)
    for i in range(600):
        sketch.add(f"serialize-{i}".encode())
    payload = sketch.serialize()
    restored = KMVSketch.deserialize(payload, cfg)
    assert restored.estimate() == pytest.approx(sketch.estimate(), rel=0.1)
