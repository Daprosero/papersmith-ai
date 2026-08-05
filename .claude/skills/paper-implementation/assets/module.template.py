"""{{ONE_LINE_STATEMENT_OF_THE_MATHEMATICAL_OBJECT}}.

Every module under src/{{NAME}}/ declares `__provenance__`. It is read
statically by `implementation_cli.py verify` — the module is never imported to obtain
it — and it is the only thing that makes revision drift detectable.

Rules:
- `revision` is the exact managed filename this code was written against.
- `sections` and `equations` point at the passage that justifies the code.
- every id in `invariants` MUST have a matching `test_<id>` under tests/.
  A declared invariant with no test fails verification.
"""

from __future__ import annotations

import numpy as np

__provenance__ = {
    "revision": "research-concept-rNN.md",
    "sections": ["3"],
    "equations": ["14", "15"],
    "invariants": ["{{INVARIANT_ID}}"],
}


def {{FUNCTION_NAME}}(x: np.ndarray) -> np.ndarray:
    """Implement Eq. (14). State assumptions the proposal makes explicit."""
    raise NotImplementedError
