"""Deterministic fixtures. Fixed seed, no data, no network.

The seed is chosen per run so that levels 2 and 3 vary between runs while
staying reproducible within one.
"""

from __future__ import annotations

import numpy as np
import pytest

SEED = {{SEED}}
TOL = 1e-10


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(SEED)
