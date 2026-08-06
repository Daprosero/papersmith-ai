"""Level 4 - audit. Evidence that each declared finding is a real defect."""

from __future__ import annotations

import numpy as np

from {{PKG}}.aggregate import bounded_map, convex_aggregate
from {{PKG}}.discrepancy import normalized_discrepancy, weighted_mean

from findings import FINDINGS
from sweep import SWEEP_SIZE, sweep


def _aggregates(case: dict) -> tuple[float, float]:
    return (convex_aggregate(bounded_map(case["left"]), case["alpha"]),
            convex_aggregate(bounded_map(case["right"]), case["beta"]))


def test_every_finding_declares_a_remedy() -> None:
    """A finding without a proposed correction is a complaint, not a finding."""
    for finding in FINDINGS:
        assert finding["remedy"].strip(), f"{finding['id']} has no remedy"
        assert finding["remedy_equations"], f"{finding['id']} does not say what it changes"
        assert finding["becomes_invariant"], f"{finding['id']} names no invariant to become"
        assert finding["adoption"]["absent"], f"{finding['id']} has no adoption marker"
        assert finding["status"] in {"theorem", "tendency"}
        assert finding["kind"] in {
            "ill-formed", "underspecified", "missing-complement", "overstated-claim",
            "ill-posed-objective", "loose-constant",
        }


def test_finding_discrepancy_constant_is_unattainable() -> None:
    """Normalizing by 4 leaves three quarters of the range unreachable."""
    peak = 0.0
    within = 0
    for case in sweep():
        a, b = _aggregates(case)
        value = normalized_discrepancy(a, b)
        peak = max(peak, value)
        within += 0.0 <= value <= 0.25 + 1e-12
    assert within == SWEEP_SIZE, "the numerator cannot exceed one"
    assert peak < 0.25 + 1e-12, f"the quotient never passes a quarter, measured {peak}"


def test_finding_weighted_mean_guarantee_is_vacuous() -> None:
    """Eq. (6) ignores the confidence scale for any mass above the stabilizer."""
    invariant = 0
    for case in sweep():
        confidences = case["confidences"]
        discrepancies = np.linspace(0.01, 0.24, confidences.size)
        full = weighted_mean(discrepancies, confidences)
        tiny = weighted_mean(discrepancies, 1e-3 * confidences)
        invariant += abs(full - tiny) / max(full, 1e-12) < 1e-3
    assert invariant == SWEEP_SIZE, f"measured {invariant}/{SWEEP_SIZE}"


def test_finding_confidence_is_an_unconstrained_decision_variable() -> None:
    """Lowering the confidences lowers the damped value, improving nothing.

    A tendency by declaration, so the test pins the shape of the evidence and
    never asserts a law: the endpoint holds broadly, and the value is bounded
    at every level in between.
    """
    endpoint = bounded = 0
    for case in sweep():
        confidences = case["confidences"]
        discrepancies = np.linspace(0.01, 0.24, confidences.size)
        damped = [float((scale * confidences) @ discrepancies) / confidences.size
                  for scale in (1.0, 0.5, 0.1, 0.01)]
        endpoint += damped[0] > damped[-1]
        bounded += all(0.0 <= value <= 1.0 for value in damped)
    assert bounded == SWEEP_SIZE
    assert endpoint > 0.9 * SWEEP_SIZE, "the tendency should be strong"
