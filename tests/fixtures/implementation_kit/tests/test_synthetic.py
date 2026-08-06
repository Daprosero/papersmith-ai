"""Level 3 - synthetic data. Deterministic, fixed seed, ground truth by construction.

Each expectation is stated before the assertion, so a passing test cannot be
mistaken for a hypothesis fitted after seeing the output.
"""

from __future__ import annotations

import numpy as np

from {{PKG}}.aggregate import bounded_map, convex_aggregate
from {{PKG}}.discrepancy import normalized_discrepancy, weighted_mean


def test_identical_collections_have_no_discrepancy(collection) -> None:
    """Expectation: a collection compared with itself gives exactly zero."""
    value = convex_aggregate(bounded_map(collection["left"]), collection["alpha"])
    assert normalized_discrepancy(value, value) == 0.0


def test_separated_collections_discrepancy_grows(rng) -> None:
    """Expectation: pushing the two collections apart increases the gap."""
    weights = np.full(4, 0.25)
    gaps = []
    for shift in (0.0, 2.0, 6.0, 20.0):
        left = convex_aggregate(bounded_map(np.full(4, -shift)), weights)
        right = convex_aggregate(bounded_map(np.full(4, shift)), weights)
        gaps.append(normalized_discrepancy(left, right))
    assert all(a < b for a, b in zip(gaps, gaps[1:]))


def test_zero_confidence_imposes_nothing(collection) -> None:
    """Expectation: with every confidence at zero the mean is zero."""
    discrepancies = np.linspace(0.0, 0.25, collection["confidences"].size)
    assert weighted_mean(discrepancies, np.zeros_like(collection["confidences"])) == 0.0
