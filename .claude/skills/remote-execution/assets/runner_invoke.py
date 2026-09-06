#!/usr/bin/env python3
"""Cell 1 of the generated runner notebook — copied byte for byte.

Runs whichever of the two shapes the selected block declares.

- A CALLABLE block (`module` / `function` / `kwargs`) resolves through
  `importlib` and is called.
- A NOTEBOOK block (`notebook`) is read out of the clone, executed in a
  kernel with the clone's `src` on its `PYTHONPATH`, and written back
  executed into the runner's own working directory, which is what makes
  its outputs part of what a fetch returns.

Both stay reachable, deliberately. The notebook shape exists so that what
a worker runs can be the notebook a pilot validated, rather than a second
implementation of it whose agreement nothing checks. The callable shape
stays because a worker asked to settle one question is legitimately a
function call, and some entries cannot be named by a `module`/`function`
contract at all. `block_kind()` decides between them and refuses a block
that declares neither or both — never a default, because on this side of
the wire every default costs the same quota as the right answer.

The `smoke` variant is selected the same way for both shapes, when
`run_config["mode"] == "smoke"`. Cell 0
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
import os
from pathlib import Path
from typing import Any, Callable, Mapping


class InvokeError(Exception):
    """A refusal: the selected `run`/`smoke` block, its declared module,
    or its declared function could not be resolved.
    """


CONFIG_FILENAME = "run-config.json"

# `runner_bootstrap.py` clones into `<base>/clone`, and this cell has to
# find the same directory to reach a declared notebook inside it. The two
# assets have no import between them — they are two cells of one notebook,
# each copied byte for byte — so this constant MIRRORS that one rather
# than importing it, exactly the way each file already holds its own
# subprocess-environment allowlist. A forge test binds the two spellings
# together; a divergence is a defect the suite catches, never a runtime
# surprise.
CLONE_DIRNAME = "clone"

# What an executed notebook is written back as, beside `run-config.json`
# and `bootstrap.json` in the runner's own working directory. A prefix and
# not an in-place overwrite: the clone is the pinned input and stays the
# pinned input, and the fetched artifact then carries both the notebook
# that was sent and the outputs it produced.
EXECUTED_NOTEBOOK_PREFIX = "executed-"

DEFAULT_KERNEL_NAME = "python3"

SRC_DIRNAME = "src"


def kernel_python_path(clone_root: str | Path, existing: str | None) -> str:
    """`PYTHONPATH` for the kernel a notebook executes in — the clone's own
    `src`, ahead of whatever was already there.

    Cell 0's `sys.path.insert(0, <clone>/src)` puts the pinned code on the
    path of the RUNNER process, and a notebook executes in a SEPARATE
    kernel process that inherits none of it. Without this, a notebook
    whose first cell imports the target's own package dies with
    `ModuleNotFoundError` on a worker whose clone is sitting right there
    — the pinned code delivered, and unreachable.

    Prepended rather than replacing: an existing `PYTHONPATH` belongs to
    the worker's own image and this has no business discarding it. The
    clone goes first for the same reason cell 0 inserts at position 0 —
    a copy of the same package installed elsewhere must never win against
    the commit this job pinned.
    """
    clone_src = str((Path(clone_root) / SRC_DIRNAME).resolve())
    if existing:
        return clone_src + os.pathsep + existing
    return clone_src


def block_kind(block: Mapping[str, Any]) -> str:
    """Which of the two shapes a selected block declares — `"callable"`
    (a `module`/`function` pair) or `"notebook"` (a `notebook` path) —
    refusing anything that is neither and anything that is both.

    The mirror of `jobfolder.run_block_kind()`, held here on its own for
    the reason every guard in these two assets is: this cell runs against
    whatever `run-config.json` the kernel was actually handed, not against
    the one a generator validated. A block that declares neither shape is
    refused rather than defaulted, and a block that declares both is
    refused rather than resolved by precedence — a silent precedence rule
    would decide, on the worker, which of two disagreeing declarations the
    operator paid for.
    """
    if not isinstance(block, Mapping):
        raise InvokeError(f"selected block {block!r} is not an object")
    notebook = block.get("notebook")
    module = block.get("module")
    function = block.get("function")
    if notebook is not None and (module is not None or function is not None):
        raise InvokeError(
            f"selected block declares BOTH a notebook ({notebook!r}) and a "
            f"module/function pair ({module!r}/{function!r}); a block "
            "declares exactly one of the two"
        )
    if notebook is not None:
        if not isinstance(notebook, str) or not notebook.strip():
            raise InvokeError(
                f"selected block declares notebook {notebook!r}: a notebook "
                "path must be a non-empty string"
            )
        return "notebook"
    if module and function:
        return "callable"
    raise InvokeError(
        f"selected block {dict(block)!r} declares neither a "
        "'module'/'function' pair nor a 'notebook'"
    )


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


def _default_notebook_client(notebook: Any, *, kernel_name: str, cwd: Path) -> Any:
    """The real executor, built only when a notebook run actually reaches
    it — never at import time, so the forge suite can drive every other
    function in this file on a machine that has no kernel at all.

    `nbclient` is what executes; `resources.metadata.path` is the working
    directory it starts the kernel in. That directory is the RUNNER's own
    working directory and deliberately not the notebook's location inside
    the clone: a notebook writing a relative path is writing an output,
    and an output written inside the clone is an output the fetch never
    sees. The clone is the pinned input; the working directory is what
    comes back.
    """
    from nbclient import NotebookClient

    return NotebookClient(
        notebook,
        kernel_name=kernel_name,
        resources={"metadata": {"path": str(cwd)}},
    )


def execute_notebook(
    block: Mapping[str, Any],
    base_dir: str | Path | None = None,
    *,
    client_factory: Callable[..., Any] = _default_notebook_client,
) -> dict:
    """Execute the declared notebook — the notebook half of cell 1.

    The notebook is read from the CLONE (`<base>/clone/<notebook>`, the
    pinned bytes cell 0 fetched), executed with the kernel it names, and
    written back — outputs and all — to `<base>/executed-<name>.ipynb`,
    the runner's own working directory. That destination is the whole of
    "the outputs come back": the fetch materializes the files the worker
    left in its working directory, which is already how `bootstrap.json`
    returns, so an executed notebook written there needs nothing added
    anywhere else in this skill to arrive.

    Three things this refuses rather than works around:

    - a notebook path that escapes the clone, or is not a file inside it
      (cell 0 already proves this for a declared notebook, and this cell
      proves it again because it is the cell that opens the file);
    - a missing `nbformat`/`nbclient` — an `ImportError` becomes an
      `InvokeError` naming `environment.install` as the remedy, the same
      remedy cell 0's own executor gate names;
    - an execution that raises — the partially-executed notebook is
      written to the same destination BEFORE the failure is re-raised, so
      the fetched artifact carries the traceback in the cell that
      produced it instead of nothing at all.

    `client_factory` exists only so the forge suite can drive this
    function without a kernel; the default is the real one.
    """
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    name = block["notebook"]
    clone_root = (base / CLONE_DIRNAME).resolve()
    notebook_path = (clone_root / name).resolve()
    try:
        notebook_path.relative_to(clone_root)
    except ValueError:
        raise InvokeError(
            f"declared notebook {name!r} resolves to {notebook_path}, outside "
            f"the clone at {clone_root}"
        ) from None
    if not notebook_path.is_file():
        raise InvokeError(
            f"declared notebook {name!r} is not at {notebook_path}; the "
            "sparse checkout delivered nothing for it"
        )
    try:
        import nbformat
    except ImportError as exc:
        raise InvokeError(
            "cannot execute a notebook: 'nbformat' is not importable in this "
            "runtime. Declare it in run-config.json's environment.install "
            f"(--environment-requirement): {exc}"
        ) from exc

    notebook = nbformat.read(str(notebook_path), as_version=4)
    kernelspec = (notebook.get("metadata") or {}).get("kernelspec") or {}
    kernel_name = str(kernelspec.get("name") or DEFAULT_KERNEL_NAME)
    executed_path = base / f"{EXECUTED_NOTEBOOK_PREFIX}{notebook_path.name}"

    try:
        client = client_factory(notebook, kernel_name=kernel_name, cwd=base)
    except ImportError as exc:
        raise InvokeError(
            "cannot execute a notebook: 'nbclient' is not importable in this "
            "runtime. Declare it in run-config.json's environment.install "
            f"(--environment-requirement): {exc}"
        ) from exc

    saved_python_path = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = kernel_python_path(clone_root, saved_python_path)
    try:
        client.execute()
    finally:
        if saved_python_path is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = saved_python_path
        # Written on the failure path too, and that is the point: a
        # notebook that died halfway is the only record of WHERE it died,
        # and losing it means paying the quota again to find out.
        nbformat.write(notebook, str(executed_path))

    return {
        "notebook": name,
        "kernel": kernel_name,
        "executed": str(executed_path),
        "cells": len(notebook.get("cells") or []),
    }


def invoke(
    run_config: Mapping[str, Any],
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
    base_dir: str | Path | None = None,
    client_factory: Callable[..., Any] = _default_notebook_client,
) -> Any:
    """The whole of cell 1: select the block, decide which of the two
    shapes it declares, and run that one.

    A callable block resolves through `importlib` and is called with its
    declared kwargs, exactly as it always was. A notebook block is
    executed from the clone and written back executed. `block_kind()`
    decides, and it refuses a block that is neither or both — this
    function has no default branch, because the only default available
    costs the same quota as the right answer.
    """
    block = select_block(run_config)
    if block_kind(block) == "notebook":
        return execute_notebook(block, base_dir, client_factory=client_factory)
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
