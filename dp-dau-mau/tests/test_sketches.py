import math
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dp_core.sketches.base import SketchConfig
from dp_core.sketches.kmv_impl import KMVSketch
from dp_core.sketches.roaring_impl import RoaringSketch
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


# --- RoaringSketch --------------------------------------------------------
#
# RoaringSketch is, like SetSketch, an *exact* backend (unlike KMV, which is
# probabilistic) -- so its tests hold it to the same exactness bar as
# SetSketch: exact cardinality, exact difference, and exact,
# history-independent removal (add-then-remove must be indistinguishable
# from never having added the removed element).


def test_roaring_sketch_exact_difference() -> None:
    sketch_a = RoaringSketch(SKETCH_CFG)
    sketch_b = RoaringSketch(SKETCH_CFG)
    sketch_a.add(b"alice")
    sketch_a.add(b"bob")
    sketch_b.add(b"bob")

    diff = sketch_a.a_not_b(sketch_b)
    assert diff.estimate() == 1.0


def test_roaring_union_exact() -> None:
    sketch_a = RoaringSketch(SKETCH_CFG)
    sketch_b = RoaringSketch(SKETCH_CFG)
    for i in range(500):
        key = f"user-{i}".encode()
        sketch_a.add(key)
        if i >= 200:
            sketch_b.add(key)
    sketch_a.union(sketch_b)
    assert sketch_a.estimate() == 500.0


def test_roaring_estimate_is_exact() -> None:
    sketch = RoaringSketch(SKETCH_CFG)
    population = 5000
    for i in range(population):
        sketch.add(f"population-{i}".encode())
    # No fuzz factor: unlike KMV, Roaring must match the true cardinality
    # exactly.
    assert sketch.estimate() == float(population)


def test_roaring_duplicate_adds_do_not_inflate_cardinality() -> None:
    sketch = RoaringSketch(SKETCH_CFG)
    for _ in range(10):
        sketch.add(b"same-user")
    assert sketch.estimate() == 1.0


def test_roaring_serialization_roundtrip() -> None:
    cfg = SketchConfig(k=128, use_bloom_for_diff=False, bloom_fp_rate=0.01)
    sketch = RoaringSketch(cfg)
    for i in range(600):
        sketch.add(f"serialize-{i}".encode())
    payload = sketch.serialize()
    restored = RoaringSketch.deserialize(payload, cfg)
    # Exact roundtrip, not approximate.
    assert restored.estimate() == sketch.estimate()
    assert sorted(restored.keys_as_ints()) == sorted(sketch.keys_as_ints())


def test_roaring_copy_is_independent() -> None:
    sketch = RoaringSketch(SKETCH_CFG)
    sketch.add(b"alice")
    clone = sketch.copy()
    clone.add(b"bob")
    assert sketch.estimate() == 1.0
    assert clone.estimate() == 2.0


def test_roaring_discard_removes_exactly_one_user() -> None:
    sketch = RoaringSketch(SKETCH_CFG)
    for name in (b"alice", b"bob", b"carol"):
        sketch.add(name)
    sketch.discard(b"bob")

    expected = RoaringSketch(SKETCH_CFG)
    for name in (b"alice", b"carol"):
        expected.add(name)

    assert sketch.estimate() == 2.0
    assert sorted(sketch.keys_as_ints()) == sorted(expected.keys_as_ints())


def test_roaring_discard_of_absent_key_is_a_noop() -> None:
    sketch = RoaringSketch(SKETCH_CFG)
    sketch.add(b"alice")
    sketch.discard(b"never-added")
    assert sketch.estimate() == 1.0


def test_roaring_history_independence_add_then_remove() -> None:
    """add(D) + discard(u) must be byte-identical to building fresh from D\\{u}.

    This is the exact property the paper claims for the Roaring backend:
    the sketch state after an erasure is indistinguishable from a state
    that never contained the erased user (history independence), not just
    "the count went down by one".
    """
    full_population = [f"user-{i}".encode() for i in range(300)]
    erased_user = full_population[137]

    built_then_erased = RoaringSketch(SKETCH_CFG)
    for key in full_population:
        built_then_erased.add(key)
    built_then_erased.discard(erased_user)

    built_fresh_without_user = RoaringSketch(SKETCH_CFG)
    for key in full_population:
        if key != erased_user:
            built_fresh_without_user.add(key)

    assert built_then_erased.estimate() == built_fresh_without_user.estimate()
    assert sorted(built_then_erased.keys_as_ints()) == sorted(
        built_fresh_without_user.keys_as_ints()
    )
    assert built_then_erased.serialize() == built_fresh_without_user.serialize()


@given(
    population_size=st.integers(min_value=1, max_value=200),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
@settings(max_examples=100)
def test_roaring_history_independence_property(population_size: int, seed: int) -> None:
    """Property test: for any population and any subset erased, add-then-
    discard state == build-fresh-from-remaining-set state, 100% of the time
    (Roaring is exact -- this must never be approximately true).
    """
    rng = random.Random(seed)
    population = [f"pop-{i}".encode() for i in range(population_size)]
    erased = {key for key in population if rng.random() < 0.3}

    built_then_erased = RoaringSketch(SKETCH_CFG)
    for key in population:
        built_then_erased.add(key)
    for key in erased:
        built_then_erased.discard(key)

    remaining = [key for key in population if key not in erased]
    built_fresh = RoaringSketch(SKETCH_CFG)
    for key in remaining:
        built_fresh.add(key)

    assert built_then_erased.estimate() == built_fresh.estimate() == float(len(remaining))
    assert sorted(built_then_erased.keys_as_ints()) == sorted(built_fresh.keys_as_ints())
    assert built_then_erased.serialize() == built_fresh.serialize()
