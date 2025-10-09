import random

from dp_core.dp_mechanisms import gaussian_mechanism, laplace_mechanism


def test_laplace_mechanism_returns_confidence_interval() -> None:
    rng = random.Random(42)
    result = laplace_mechanism(100.0, sensitivity=1.0, epsilon=0.5, rng=rng, seed=42)
    assert result.mechanism == "laplace"
    assert result.confidence_interval[0] < result.confidence_interval[1]


def test_gaussian_mechanism_respects_delta() -> None:
    rng = random.Random(42)
    result = gaussian_mechanism(200.0, sensitivity=1.0, epsilon=0.7, delta=1e-6, rng=rng, seed=99)
    assert result.delta == 1e-6
    assert result.mechanism == "gaussian"
