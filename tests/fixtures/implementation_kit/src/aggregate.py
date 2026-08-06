"""Bounded map and convex aggregate of the neutral fixture proposal."""

from __future__ import annotations

import numpy as np

__provenance__ = {
    "revision": "neutral-concept-r01.md",
    "sections": ["1", "2"],
    "equations": ["1", "2", "3", "4"],
    "invariants": [
        "map_is_bounded",
        "aggregate_lies_in_the_unit_interval",
        "aggregate_is_permutation_invariant",
    ],
}


def bounded_map(x: np.ndarray) -> np.ndarray:
    """Eq. (1)/(2): send a point to the unit interval."""
    return 1.0 / (1.0 + np.exp(-x))


def convex_aggregate(values: np.ndarray, weights: np.ndarray) -> float:
    """Eq. (4): convex combination of values under simplex weights."""
    if abs(float(weights.sum()) - 1.0) > 1e-9 or (weights < 0).any():
        raise ValueError("weights must lie on the simplex (Eq. 3)")
    return float(weights @ values)
