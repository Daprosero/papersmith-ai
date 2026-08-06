"""Randomized configuration sweep shared by the audit and the remedy checks.

One fixed size for every claim: a property surviving SWEEP_SIZE independent
configurations belongs to the formulation, not to a seed.

SWEEP_BASE offsets the block by the run's seed so separate runs audit disjoint
configurations. Without it, agreement between runs would confirm determinism
and nothing else.

`configuration` builds one instance of whatever the proposal's objects are.
Vary what the proposal allows to vary — cardinalities, dispersion, shifts — so
a claim that only holds for one shape shows up as a rate below the full sweep.
"""

from __future__ import annotations

import numpy as np

SWEEP_SIZE = 200
SWEEP_BASE = {{SEED}} * 10000


def configuration(index: int) -> dict:
    """One reproducible configuration of the proposal's objects."""
    rng = np.random.default_rng(SWEEP_BASE + index)  # noqa: F841
    raise NotImplementedError


def sweep(size: int = SWEEP_SIZE):
    for index in range(size):
        yield configuration(index)
