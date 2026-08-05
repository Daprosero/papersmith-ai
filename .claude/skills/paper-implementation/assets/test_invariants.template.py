"""Level 2 — properties and invariants. The bridge between proposal and code.

One test per mathematical claim the proposal makes. The test name MUST be
`test_<invariant_id>` where `<invariant_id>` is the id declared in the module's
`__provenance__["invariants"]`; verification matches them by that exact name.

Each test carries, in its docstring, the passage it enforces. A test whose
claim cannot be traced back to the proposal does not belong here.
"""

from __future__ import annotations

import numpy as np

SEED = 20260804
TOL = 1e-10


def test_{{INVARIANT_ID}}() -> None:
    """<revision> § 3, Eq. (14): the Gram matrix is positive semi-definite."""
    from {{NAME}}.{{MODULE}} import {{FUNCTION_NAME}}

    rng = np.random.default_rng(SEED)
    x = rng.normal(size=(16, 3))
    gram = {{FUNCTION_NAME}}(x)

    assert np.allclose(gram, gram.T, atol=TOL), "kernel must be symmetric"
    eigenvalues = np.linalg.eigvalsh(gram)
    assert eigenvalues.min() >= -TOL, f"kernel is not PSD: min eigenvalue {eigenvalues.min()}"
