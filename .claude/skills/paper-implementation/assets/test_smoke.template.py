"""Level 1 — smoke. Does the implementation run at all, on the smallest input?

Smoke never asserts mathematics. It asserts that the code is reachable, the
package imports, and every public entry point returns something of the right
shape. Mathematical claims belong in test_invariants.py.
"""

from __future__ import annotations

import importlib

import numpy as np

SEED = 20260804

MODULES = [
    "{{NAME}}.{{MODULE}}",
]


def test_package_imports() -> None:
    for module in MODULES:
        assert importlib.import_module(module) is not None


def test_runs_on_minimal_input() -> None:
    rng = np.random.default_rng(SEED)
    x = rng.normal(size=(4, 2))
    from {{NAME}}.{{MODULE}} import {{FUNCTION_NAME}}

    out = {{FUNCTION_NAME}}(x)
    assert out is not None
