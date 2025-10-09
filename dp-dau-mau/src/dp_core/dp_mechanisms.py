"""Differential privacy mechanisms used by the pipeline."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class MechanismResult:
    value: float
    noisy_value: float
    mechanism: Literal["laplace", "gaussian"]
    epsilon: float
    delta: float
    confidence_interval: tuple[float, float]
    seed: int


def laplace_mechanism(
    value: float,
    sensitivity: float,
    epsilon: float,
    rng: random.Random,
    seed: int,
    alpha: float = 0.05,
) -> MechanismResult:
    if epsilon <= 0:
        raise ValueError("epsilon must be > 0 for Laplace mechanism.")
    scale = sensitivity / epsilon
    noise = sample_laplace(scale, rng)
    noisy_value = value + noise
    z = -scale * math.log(alpha / 2)
    ci = (noisy_value - z, noisy_value + z)
    return MechanismResult(
        value=value,
        noisy_value=noisy_value,
        mechanism="laplace",
        epsilon=epsilon,
        delta=0.0,
        confidence_interval=ci,
        seed=seed,
    )


def gaussian_mechanism(
    value: float,
    sensitivity: float,
    epsilon: float,
    delta: float,
    rng: random.Random,
    seed: int,
    alpha: float = 0.05,
) -> MechanismResult:
    if epsilon <= 0 or delta <= 0 or delta >= 1:
        raise ValueError("Gaussian mechanism requires epsilon > 0 and 0 < delta < 1.")
    sigma = math.sqrt(2 * math.log(1.25 / delta)) * sensitivity / epsilon
    noise = rng.gauss(0.0, sigma)
    noisy_value = value + noise
    z = 1.959963984540054  # 95% standard normal quantile
    ci = (noisy_value - z * sigma, noisy_value + z * sigma)
    return MechanismResult(
        value=value,
        noisy_value=noisy_value,
        mechanism="gaussian",
        epsilon=epsilon,
        delta=delta,
        confidence_interval=ci,
        seed=seed,
    )


def sample_laplace(scale: float, rng: random.Random) -> float:
    u = rng.random() - 0.5
    return -scale * math.copysign(math.log(1 - 2 * abs(u)), u)
