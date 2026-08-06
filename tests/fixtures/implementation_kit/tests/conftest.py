"""Deterministic fixtures for the neutral proposal. Fixed seed, no data."""

from __future__ import annotations

import numpy as np
import pytest

SEED = {{SEED}}
TOL = 1e-10


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(SEED)


@pytest.fixture
def collection(rng: np.random.Generator) -> dict:
    """Two finite collections with simplex weights, as Sections 2-3 assume."""
    n, m = 5, 4
    return {
        "left": rng.normal(size=n) * 2.0,
        "right": rng.normal(size=m) * 2.0,
        "alpha": rng.dirichlet(np.ones(n)),
        "beta": rng.dirichlet(np.ones(m)),
        "confidences": rng.uniform(0.1, 1.0, size=4),
    }
