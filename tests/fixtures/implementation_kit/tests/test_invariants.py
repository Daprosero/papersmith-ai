"""Level 2 - properties. One test per claim the fixture proposal makes.

Each test name matches an id declared in a module's
`__provenance__["invariants"]`; verification matches them by that exact name.
"""

from __future__ import annotations

import numpy as np

from {{PKG}}.aggregate import bounded_map, convex_aggregate
from {{PKG}}.discrepancy import normalized_discrepancy, weighted_mean

from conftest import TOL


def test_map_is_bounded(rng) -> None:
    """Eq. (2): the map never leaves the unit interval."""
    values = bounded_map(rng.normal(size=64) * 50.0)
    assert (values >= 0.0).all() and (values <= 1.0).all()


def test_aggregate_lies_in_the_unit_interval(collection) -> None:
    """Eq. (4): a convex combination of values in [0,1] stays in [0,1]."""
    value = convex_aggregate(bounded_map(collection["left"]), collection["alpha"])
    assert -TOL <= value <= 1.0 + TOL


def test_aggregate_is_permutation_invariant(collection, rng) -> None:
    """Eq. (4): reordering the pairs leaves the aggregate unchanged."""
    values = bounded_map(collection["left"])
    order = rng.permutation(values.size)
    assert abs(convex_aggregate(values, collection["alpha"])
               - convex_aggregate(values[order], collection["alpha"][order])) < TOL


def test_discrepancy_is_non_negative(collection) -> None:
    """Eq. (5): an absolute value over a positive constant."""
    a = convex_aggregate(bounded_map(collection["left"]), collection["alpha"])
    b = convex_aggregate(bounded_map(collection["right"]), collection["beta"])
    assert normalized_discrepancy(a, b) >= 0.0


def test_weighted_mean_lies_in_the_unit_interval(collection) -> None:
    """Eq. (6): weights are non-negative and the denominator dominates."""
    discrepancies = np.linspace(0.0, 0.25, collection["confidences"].size)
    assert 0.0 <= weighted_mean(discrepancies, collection["confidences"]) <= 1.0
