"""Level 5 - remedies. Each proposed correction, validated at the same rigour.

A remedy is accepted only when the sweep shows both poles: it resolves the
finding, and the declared formulation fails the same criterion. The proposed
replacements live here, never in src/ — establishing that a correction is sound
is not the same as adopting it.
"""

from __future__ import annotations

import numpy as np

from {{PKG}}.aggregate import bounded_map, convex_aggregate
from {{PKG}}.discrepancy import normalized_discrepancy, weighted_mean

from admissibility import require_admissible
from sweep import SWEEP_SIZE, sweep


# --- proposed replacements ------------------------------------------------

def remedy_discrepancy(a: float, b: float) -> float:
    """PROPOSED Eq. (5): normalize by the attainable bound."""
    return abs(a - b) / 1.0


def remedy_weighted_mean(discrepancies: np.ndarray, confidences: np.ndarray) -> float:
    """PROPOSED Eq. (6): damped mean instead of the normalized quotient."""
    if discrepancies.size == 0:
        return 0.0
    return float((confidences @ discrepancies) / discrepancies.size)


def _aggregates(case: dict) -> tuple[float, float]:
    return (convex_aggregate(bounded_map(case["left"]), case["alpha"]),
            convex_aggregate(bounded_map(case["right"]), case["beta"]))


# --- remedies -------------------------------------------------------------

def test_remedy_discrepancy_constant_is_unattainable() -> None:
    """Resolves it: the range becomes usable.

    Control: the declared form stays capped at a quarter over the same sweep,
    so the comparison cannot pass for a measurement that would accept anything.
    """
    require_admissible("discrepancy_constant_is_unattainable")
    bounded = wider = 0
    declared_peak = proposed_peak = 0.0
    for case in sweep():
        a, b = _aggregates(case)
        declared = normalized_discrepancy(a, b)
        proposed = remedy_discrepancy(a, b)
        bounded += 0.0 <= proposed <= 1.0 + 1e-12
        wider += proposed >= declared
        declared_peak = max(declared_peak, declared)
        proposed_peak = max(proposed_peak, proposed)

    assert bounded == SWEEP_SIZE, "the remedy must stay in [0,1]"
    assert wider == SWEEP_SIZE, "the remedy must never shrink the value"
    assert declared_peak < 0.26, f"the control must stay capped, measured {declared_peak}"
    assert proposed_peak > 0.5, f"the point is range usage, measured {proposed_peak}"


def test_remedy_weighted_mean_guarantee_is_vacuous() -> None:
    """Resolves it: the aggregate now scales with the confidence.

    Control: the declared quotient is shown to ignore the same rescaling.
    """
    require_admissible("weighted_mean_guarantee_is_vacuous")
    proportional = vanishes = bounded = 0
    for case in sweep():
        confidences = case["confidences"]
        discrepancies = np.linspace(0.01, 0.24, confidences.size)

        full = remedy_weighted_mean(discrepancies, confidences)
        half = remedy_weighted_mean(discrepancies, 0.5 * confidences)
        none = remedy_weighted_mean(discrepancies, np.zeros_like(confidences))

        bounded += 0.0 <= full <= 1.0
        proportional += abs(half - 0.5 * full) < 1e-12
        vanishes += none == 0.0

        declared_full = weighted_mean(discrepancies, confidences)
        declared_half = weighted_mean(discrepancies, 0.5 * confidences)
        assert abs(declared_full - declared_half) / declared_full < 1e-6, (
            "the finding requires the declared form to be scale invariant")

    assert bounded == SWEEP_SIZE
    assert proportional == SWEEP_SIZE, f"must halve with the confidence, got {proportional}"
    assert vanishes == SWEEP_SIZE, f"must vanish with the confidence, got {vanishes}"


def test_remedy_confidence_is_an_unconstrained_decision_variable() -> None:
    """Resolves it: with the weights frozen the value cannot move through them.

    The premise is checkable — the term reaches the confidences only as weights,
    so two different confidence vectors with the same sum and the same pairing
    give the same value. Control: the declared quotient is exercised alongside.
    """
    require_admissible("confidence_is_an_unconstrained_decision_variable")
    single_channel = exploit_existed = 0
    for case in sweep():
        confidences = case["confidences"]
        discrepancies = np.linspace(0.01, 0.24, confidences.size)

        frozen = remedy_weighted_mean(discrepancies, confidences)
        mirrored = remedy_weighted_mean(discrepancies[::-1], confidences[::-1])
        single_channel += abs(frozen - mirrored) < 1e-12

        exploit_existed += remedy_weighted_mean(discrepancies, 0.1 * confidences) < frozen
        weighted_mean(discrepancies, confidences)  # control: the declared form

    assert single_channel == SWEEP_SIZE, f"got {single_channel}/{SWEEP_SIZE}"
    assert exploit_existed > 0, "the sweep must actually contain the exploit"
