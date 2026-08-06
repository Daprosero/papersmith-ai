"""Randomized configuration sweep shared by the audit and remedy checks.

One fixed size for every claim: a property surviving SWEEP_SIZE independent
configurations belongs to the formulation, not to a seed. SWEEP_BASE offsets the
block by the scenario seed so separate runs audit disjoint configurations —
without it, agreement between runs would confirm determinism and nothing else.
"""

from __future__ import annotations

import numpy as np

SWEEP_SIZE = 200
SWEEP_BASE = {{SEED}} * 10000


def configuration(index: int) -> dict:
    """One reproducible configuration of the fixture's objects."""
    rng = np.random.default_rng(SWEEP_BASE + index)
    n = int(rng.integers(2, 9))
    m = int(rng.integers(2, 9))
    left = rng.normal(size=n) * float(rng.uniform(0.2, 4.0))
    right = rng.normal(size=m) * float(rng.uniform(0.2, 4.0))
    alpha = rng.dirichlet(np.ones(n))
    beta = rng.dirichlet(np.ones(m))
    return {"index": index, "n": n, "m": m,
            "left": left, "right": right, "alpha": alpha, "beta": beta,
            "confidences": rng.uniform(0.05, 1.0, size=int(rng.integers(2, 7)))}


def sweep(size: int = SWEEP_SIZE):
    for index in range(size):
        yield configuration(index)
