from dp_core.sketches.hllpp_impl import HllppSketch
from dp_core.sketches.set_impl import SetSketch


def test_set_sketch_counts_unique() -> None:
    sketch = SetSketch()
    sketch.add(b"a")
    sketch.add(b"b")
    sketch.add(b"a")
    assert sketch.estimate() == 2.0


def test_hllpp_sketch_returns_positive_estimate() -> None:
    sketch = HllppSketch()
    for i in range(100):
        sketch.add(f"user-{i}".encode())
    assert sketch.estimate() > 0
