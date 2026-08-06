"""Audit findings on the neutral fixture proposal, each with its remedy.

Illustrative throughout: these exist so the harness has findings with the shape
of real ones — a loose constant, an overstated guarantee, an objective the
optimizer can game — without carrying anyone's research.

The contract, checked statically by `implementation_cli.py verify`:

- every `id` has a `test_finding_<id>` proving the defect is real over the sweep;
- every `id` has a `test_remedy_<id>` proving the fix resolves it AND preserves
  what was already established;
- `uses` must appear verbatim in the revision, `introduces` is notation the
  remedy would add, `adoption.absent` is text present today whose disappearance
  signals adoption, and `becomes_invariant` names what the remedy turns into
  once the deliberation publishes it;
- a finding whose remedy is local must carry `remedy_block`: the corrected block
  exactly as it should read in the document. Prose describing a correction is
  not a correction. Without it the handoff cannot settle the change inline and
  defers it to a session of its own, which is the honest outcome — writing the
  mathematics is the work, and no tool should guess it from a description.
"""

FINDINGS = [
    {
        "id": "discrepancy_constant_is_unattainable",
        "kind": "loose-constant",
        "equations": ["4", "5"],
        "remedy_equations": ["5"],
        "uses": [r"A_n", r"\kappa", r"\delta"],
        "introduces": [],
        "adoption": {"absent": r"\kappa = 4", "expect": [r"\kappa = 1"]},
        "becomes_invariant": "discrepancy_uses_its_whole_range",
        "status": "theorem",
        "rate": "the full sweep",
        "statement": (
            "Eq. (4) bounds every aggregate in [0,1], so the numerator of Eq. (5) never "
            "exceeds one and the quotient never passes 1/4. Normalizing by 4 leaves three "
            "quarters of the range unreachable by construction — not conservative, dead "
            "range."
        ),
        "remedy": (
            "Normalize by the attainable bound: kappa = 1. The numerator's supremum is one, "
            "reached as the two aggregates separate to the ends of the interval, so the whole "
            "[0,1] range becomes usable and the bound stays sound."
        ),
        "remedy_block": (
            "$$\n"
            "\\delta\n"
            "=\n"
            "\\frac{\\lvert A_n - A_m \\rvert}{\\kappa},\n"
            "\\qquad \\kappa = 1 .\n"
            "\\tag{5}\n"
            "$$"
        ),
    },
    {
        "id": "weighted_mean_guarantee_is_vacuous",
        "kind": "overstated-claim",
        "equations": ["6"],
        "remedy_equations": ["6"],
        "uses": [r"c_j", r"\varepsilon", r"\delta_j"],
        "introduces": [],
        "adoption": {"absent": r"\sum_{j=1}^{m} c_j + \varepsilon",
                     "expect": [r"\frac{1}{m}"]},
        "becomes_invariant": "weighted_mean_scales_with_the_confidence",
        "status": "theorem",
        "rate": "the full sweep",
        "statement": (
            "Section 4 claims the stabilizer keeps the quotient defined when every confidence "
            "is small, implying it then imposes little. It does not: the quotient is invariant "
            "to a uniform rescaling of the c_j for any sum far above epsilon, so it is a mean "
            "whose value ignores the confidence level entirely. The stated behaviour only "
            "appears once the confidence mass reaches a numerical stabilizer."
        ),
        "remedy": (
            "Aggregate with the damped mean instead of the normalized quotient: "
            "M = (1/m) sum_j c_j delta_j. It needs no stabilizer, keeps the relative weighting "
            "among terms, stays in [0,1], and now genuinely scales: halving every confidence "
            "halves the value."
        ),
        "remedy_block": (
            "$$\n"
            "M\n"
            "=\n"
            "\\frac{1}{m} \\sum_{j=1}^{m} c_j \\delta_j .\n"
            "\\tag{6}\n"
            "$$"
        ),
    },
    {
        "id": "confidence_is_an_unconstrained_decision_variable",
        "kind": "ill-posed-objective",
        "equations": ["4", "6"],
        "remedy_equations": ["4", "6"],
        "uses": [r"c_j", r"A_n"],
        "introduces": [r"\operatorname{sg}", r"\lambda"],
        "adoption": {"absent": r"c_j \delta_j", "expect": [r"\operatorname{sg}"]},
        "becomes_invariant": "confidence_carries_no_gradient",
        "status": "tendency",
        "rate": "measured per sweep, never asserted as a law",
        "statement": (
            "The confidences weight the aggregate they are derived from, so lowering them "
            "lowers the value without improving anything the proposal cares about. The damped "
            "mean above sharpens this: once the term genuinely scales with the confidence, "
            "driving it to zero zeroes the whole term."
        ),
        "remedy": (
            "Declare c_j a weight rather than a decision variable, c = sg[...], so no gradient "
            "flows through that channel, and optionally add a penalty with its own lambda to "
            "reward confident values. Both are decisions for the deliberation: the operator and "
            "the coefficient are notation the revision does not define."
        ),
    },
]
