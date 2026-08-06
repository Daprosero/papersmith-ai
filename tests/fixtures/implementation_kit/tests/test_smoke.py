"""Level 1 - smoke. Does it run at all, on the smallest input?"""

from __future__ import annotations

import importlib

import numpy as np

MODULES = ["{{PKG}}.aggregate", "{{PKG}}.discrepancy"]


def test_package_imports() -> None:
    for module in MODULES:
        assert importlib.import_module(module) is not None


def test_every_module_declares_provenance() -> None:
    for module in MODULES:
        provenance = getattr(importlib.import_module(module), "__provenance__", None)
        assert provenance is not None, f"{module} has no __provenance__"
        assert provenance["revision"] == "research-concept-neutral-r01.md"


def test_runs_on_a_single_value() -> None:
    from {{PKG}}.aggregate import bounded_map, convex_aggregate
    from {{PKG}}.discrepancy import normalized_discrepancy

    value = convex_aggregate(bounded_map(np.zeros(1)), np.ones(1))
    assert 0.0 <= value <= 1.0
    assert normalized_discrepancy(value, value) == 0.0
