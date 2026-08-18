#!/usr/bin/env python3
"""Cell 1 of the generated runner notebook — copied byte for byte.

Resolves `run.module` / `run.function` / `run.kwargs` from
`run-config.json` (or the `smoke` variant, when `run_config["mode"] ==
"smoke"`) through `importlib`, and calls it. Cell 0
(`runner_bootstrap.py`) has already sparse-cloned the pinned commit and
put its `src/` on `sys.path` before this cell ever runs — `SystemExit`
there means this cell never runs at all — so the module named here
resolves from that same clone, never from anywhere this cell reaches on
its own initiative.

Importable and independently testable the same way `runner_bootstrap.py`
is: nothing runs at import time, and the orchestrating call sits behind
`if __name__ == "__main__":`, letting the forge suite drive
`select_block()`, `resolve_callable()` and `invoke()` directly against
fake `run-config.json` payloads.

No service name occurs anywhere in this file, and none may be added
later either.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping


class InvokeError(Exception):
    """A refusal: the selected `run`/`smoke` block, its declared module,
    or its declared function could not be resolved.
    """


CONFIG_FILENAME = "run-config.json"


def select_block(run_config: Mapping[str, Any]) -> Mapping[str, Any]:
    """The normal `run` block, or its `smoke` variant when
    `run_config["mode"] == "smoke"` — T11 sets that mode; this is the
    branch it selects.
    """
    run_block = run_config.get("run", {})
    if run_config.get("mode") == "smoke":
        smoke = run_block.get("smoke")
        if not smoke:
            raise InvokeError(
                "run_config declares mode 'smoke' but its 'run' block "
                "carries no 'smoke' entry"
            )
        return smoke
    return run_block


def resolve_callable(
    block: Mapping[str, Any],
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> Callable[..., Any]:
    """Resolve `block["module"]`/`block["function"]` through `importlib`,
    refusing a missing module, a missing attribute, or a non-callable
    attribute — never guessing at any of the three.
    """
    module_name = block.get("module")
    function_name = block.get("function")
    if not module_name or not function_name:
        raise InvokeError(
            f"block {dict(block)!r} is missing a 'module' or a 'function'"
        )
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise InvokeError(f"could not import {module_name!r}: {exc}") from exc
    try:
        func = getattr(module, function_name)
    except AttributeError as exc:
        raise InvokeError(
            f"{module_name!r} has no attribute {function_name!r}"
        ) from exc
    if not callable(func):
        raise InvokeError(f"{module_name}.{function_name} is not callable")
    return func


def invoke(
    run_config: Mapping[str, Any],
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> Any:
    """The whole of cell 1: select the block, resolve the callable, call
    it with its declared kwargs, and return whatever it returns.
    """
    block = select_block(run_config)
    func = resolve_callable(block, import_module=import_module)
    kwargs = dict(block.get("kwargs") or {})
    return func(**kwargs)


def _load_run_config(base_dir: str | Path | None = None) -> dict:
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    path = base / CONFIG_FILENAME
    if not path.is_file():
        raise InvokeError(f"{path} does not exist")
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    invoke(_load_run_config())
