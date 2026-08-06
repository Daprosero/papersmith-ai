"""Normalized discrepancy and the confidence-weighted mean of the fixture."""

from __future__ import annotations

import numpy as np

__provenance__ = {
    "revision": "neutral-concept-r01.md",
    "sections": ["3", "4"],
    "equations": ["5", "6"],
    "invariants": [
        "discrepancy_is_non_negative",
        "weighted_mean_lies_in_the_unit_interval",
    ],
}

KAPPA = 4.0
EPSILON = 1e-8


def normalized_discrepancy(a: float, b: float, kappa: float = KAPPA) -> float:
    """Eq. (5): the gap between two aggregates, normalized by a constant."""
    return abs(a - b) / kappa


def weighted_mean(discrepancies: np.ndarray, confidences: np.ndarray,
                  epsilon: float = EPSILON) -> float:
    """Eq. (6): confidence-weighted mean with a numerical stabilizer."""
    return float((confidences @ discrepancies) / (confidences.sum() + epsilon))
