import math
import random

import pytest

from dp_core.dp_mechanisms import gaussian_mechanism, laplace_mechanism


def test_laplace_mechanism_returns_confidence_interval() -> None:
    rng = random.Random(42)
    result = laplace_mechanism(100.0, sensitivity=1.0, epsilon=0.5, rng=rng, seed=42)
    assert result.mechanism == "laplace"
    assert result.confidence_interval[0] < result.confidence_interval[1]
    assert result.sensitivity == 1.0


def test_gaussian_mechanism_respects_delta() -> None:
    rng = random.Random(42)
    result = gaussian_mechanism(200.0, sensitivity=1.0, epsilon=0.7, delta=1e-6, rng=rng, seed=99)
    assert result.delta == 1e-6
    assert result.mechanism == "gaussian"
    assert result.sensitivity == 1.0


def test_laplace_rejects_non_positive_epsilon() -> None:
    rng = random.Random(0)
    with pytest.raises(ValueError):
        laplace_mechanism(10.0, sensitivity=1.0, epsilon=0.0, rng=rng, seed=1)


def test_gaussian_parameter_validation() -> None:
    rng = random.Random(0)
    with pytest.raises(ValueError):
        gaussian_mechanism(10.0, sensitivity=1.0, epsilon=-0.1, delta=1e-6, rng=rng, seed=1)
    with pytest.raises(ValueError):
        gaussian_mechanism(10.0, sensitivity=1.0, epsilon=0.5, delta=0.0, rng=rng, seed=1)


def test_laplace_confidence_interval_width_matches_scale() -> None:
    rng = random.Random(123)
    epsilon = 0.8
    sensitivity = 1.5
    result = laplace_mechanism(0.0, sensitivity=sensitivity, epsilon=epsilon, rng=rng, seed=5)
    scale = sensitivity / epsilon
    z = -scale * math.log(0.05 / 2)
    assert math.isclose(
        result.confidence_interval[1] - result.confidence_interval[0], 2 * z, rel_tol=1e-6
    )


def test_gaussian_confidence_interval_width_matches_sigma() -> None:
    rng = random.Random(99)
    epsilon = 0.5
    delta = 1e-5
    sensitivity = 1.0
    result = gaussian_mechanism(
        0.0, sensitivity=sensitivity, epsilon=epsilon, delta=delta, rng=rng, seed=7
    )
    sigma = math.sqrt(2 * math.log(1.25 / delta)) * sensitivity / epsilon
    expected_width = 2 * 1.959963984540054 * sigma
    assert math.isclose(
        result.confidence_interval[1] - result.confidence_interval[0], expected_width, rel_tol=1e-6
    )
