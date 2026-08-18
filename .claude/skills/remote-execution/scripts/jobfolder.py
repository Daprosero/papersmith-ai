#!/usr/bin/env python3
"""Generate a forge-owned, service-blind job folder for a target repository.

`generate_job()` is the whole of `generate-job` (driven by `remote_cli.py`,
which loads this module the same sibling way it loads `ledger.py`,
`packer.py` and `adapter.py`). It builds `<target>/tools/<service>/
<job-name>/`: `runner.ipynb`, `run-config.json`, and one adapter-supplied
metadata file — writing the metadata file's bytes and filename opaquely, as
returned by `ADAPTER.resolve_metadata(service)`, without ever learning what
either one means (see `adapter.py`'s own docstring on that registry).

`--target` is resolved first, and every path this module touches —
`resolve_destination()`'s containment check, the `.partial/` build
directory, the final rename — is derived from that resolved value, never
from the raw argument. Generation refuses when the derived destination is
not a directory inside the resolved target, which is what stands between a
crafted `--service`/`--job-name` (`../../etc`, say) and a write outside the
target repository entirely.

`resolve_clone_paths()` (the AST-based, transitive dependency check) and
the two runner assets themselves (`assets/runner_bootstrap.py`,
`assets/runner_invoke.py`) are a separate, later slice — this module
already knows where they live (`ASSETS_DIR` below) and copies whatever
bytes are there byte for byte, but does not yet ship real content for them.
Until that slice lands, `generate_job()` refuses with a clear
`JobFolderError` naming the missing asset, rather than writing a job folder
around empty cells.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Mapping, Sequence


def _load_adapter_seam():
    """Path-import `adapter.py`, one directory up from this file, reusing an
    already-loaded copy under `remote_execution_adapter` when one exists —
    the same `sys.modules`-reuse idiom every other sibling loader in this
    skill uses, for the same reason: a second, separately exec'd copy would
    define a second, distinct `Adapter`/`CredentialHandle` with the same
    name.
    """
    module_name = "remote_execution_adapter"
    if module_name in sys.modules:
        return sys.modules[module_name]
    import importlib.util

    script = Path(__file__).resolve().parent / "adapter.py"
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ADAPTER = _load_adapter_seam()


class JobFolderError(Exception):
    """Generation refused before writing anything a later step couldn't undo."""


TOOLS_DIRNAME = "tools"
RUN_CONFIG_FILENAME = "run-config.json"
RUNNER_FILENAME = "runner.ipynb"
PARTIAL_SUFFIX = ".partial"
STALE_SUFFIX_PREFIX = ".stale-"
RUN_CONFIG_SCHEMA_VERSION = 1

# `scripts/jobfolder.py` -> `scripts/` -> `remote-execution/` -> `assets/`.
# Not yet populated with the real bootstrap/invoke content (a later slice
# ships that); referenced here so every caller — this module's own
# `generate_job()`, `remote_cli.py`'s CLI wiring, and a future test fixture
# alike — points at the exact same two paths.
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_BOOTSTRAP_ASSET = ASSETS_DIR / "runner_bootstrap.py"
DEFAULT_INVOKE_ASSET = ASSETS_DIR / "runner_invoke.py"

REQUIRED_RUN_CONFIG_FIELDS = (
    "schemaVersion", "product", "service", "jobName", "commit", "repo",
    "clonePaths", "run", "runnerTemplate",
)


def resolve_target(target: str | Path) -> Path:
    """Resolve `--target` to an absolute path and refuse anything that is
    not an existing directory — the very first thing `generate_job()` does,
    before any other check.
    """
    resolved = Path(target).resolve()
    if not resolved.is_dir():
        raise JobFolderError(
            f"--target {resolved} does not resolve to an existing directory"
        )
    return resolved


def resolve_destination(target: Path, service: str, job_name: str) -> Path:
    """Derive `<target>/tools/<service>/<job-name>/`, resolved, and refuse
    it outright when the resolved result does not stay under `target` —
    the one check that stands between a crafted `service`/`job_name`
    containing `..` and a write landing outside the target repository.
    """
    destination = (target / TOOLS_DIRNAME / service / job_name).resolve()
    try:
        destination.relative_to(target)
    except ValueError:
        raise JobFolderError(
            f"refusing destination {destination}: it does not stay under "
            f"resolved target {target} at all"
        ) from None
    return destination


def validate_clone_paths(clone_paths: Sequence[str]) -> tuple[str, ...]:
    """Structural validation only — no filesystem, no AST. Empty is
    refused; an absolute path or one containing `..` is refused. This runs
    at generation time here, and is meant to run again on every read (a
    later slice wires the second call site).
    """
    if not clone_paths:
        raise JobFolderError("clonePaths must not be empty")
    validated = []
    for raw in clone_paths:
        candidate = Path(raw)
        if candidate.is_absolute():
            raise JobFolderError(f"refusing absolute clone path {raw!r}")
        if ".." in candidate.parts:
            raise JobFolderError(f"refusing clone path {raw!r}: contains '..'")
        validated.append(candidate.as_posix())
    return tuple(validated)


def validate_run_config(run_config: Mapping[str, object]) -> None:
    """The schema check re-run on every read, not only at generation —
    `generate_job()` calls it on the very config it is about to write, so a
    caller a later slice adds to `jobfolder.read()` needs no second copy of
    this logic.
    """
    if not isinstance(run_config, Mapping):
        raise JobFolderError("run-config.json must decode to a JSON object")
    missing = [field for field in REQUIRED_RUN_CONFIG_FIELDS if field not in run_config]
    if missing:
        raise JobFolderError(f"run-config.json missing required fields: {missing}")
    if run_config.get("schemaVersion") != RUN_CONFIG_SCHEMA_VERSION:
        raise JobFolderError(
            f"run-config.json declares schemaVersion "
            f"{run_config.get('schemaVersion')!r}; this generator writes and "
            f"reads only {RUN_CONFIG_SCHEMA_VERSION}"
        )
    validate_clone_paths(run_config["clonePaths"])
    run_block = run_config["run"]
    if not isinstance(run_block, Mapping) or "module" not in run_block or "function" not in run_block:
        raise JobFolderError(
            "run-config.json's 'run' block must declare a 'module' and a 'function'"
        )


def _asset_sha256(path: Path) -> str:
    if not path.is_file():
        raise JobFolderError(
            f"runner asset {path} does not exist; generation refuses to build "
            "a job folder around a missing cell"
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_run_config(
    *,
    product: str,
    service: str,
    job_name: str,
    commit: str,
    repo_url: str,
    repo_ref: str,
    clone_paths: Sequence[str],
    run_module: str,
    run_function: str,
    run_kwargs: Mapping[str, object] | None,
    smoke_module: str | None,
    smoke_function: str | None,
    smoke_kwargs: Mapping[str, object] | None,
    bootstrap_asset: Path,
    invoke_asset: Path,
) -> dict:
    """Assemble `run-config.json`'s exact shape from target-supplied values.

    `runnerTemplate` records each asset's path and sha256 as inert
    provenance — deliberately not a drift check (see `SKILL.md`): a second
    staleness condition is explicitly out of scope for this skill.
    """
    validated_clone_paths = validate_clone_paths(clone_paths)
    run_block: dict = {
        "module": run_module,
        "function": run_function,
        "kwargs": dict(run_kwargs or {}),
    }
    if smoke_module and smoke_function:
        run_block["smoke"] = {
            "module": smoke_module,
            "function": smoke_function,
            "kwargs": dict(smoke_kwargs or {}),
        }

    run_config = {
        "schemaVersion": RUN_CONFIG_SCHEMA_VERSION,
        "product": product,
        "service": service,
        "jobName": job_name,
        "commit": commit,
        "repo": {"url": repo_url, "ref": repo_ref},
        "clonePaths": list(validated_clone_paths),
        "run": run_block,
        "runnerTemplate": [
            {"path": "assets/runner_bootstrap.py", "sha256": _asset_sha256(bootstrap_asset)},
            {"path": "assets/runner_invoke.py", "sha256": _asset_sha256(invoke_asset)},
        ],
    }
    validate_run_config(run_config)
    return run_config


def _notebook_cell(source_text: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source_text.splitlines(keepends=True),
    }


def build_notebook(bootstrap_asset: Path, invoke_asset: Path) -> dict:
    """Two cells, copied byte for byte from the two runner assets, with
    zero interpolation — the same bytes for every job, which is exactly
    what makes `runner_bootstrap.py`/`runner_invoke.py` unit-testable as
    modules in the forge suite rather than only as embedded, per-job prose.
    """
    if not bootstrap_asset.is_file() or not invoke_asset.is_file():
        raise JobFolderError(
            f"runner assets are missing ({bootstrap_asset}, {invoke_asset}); "
            "generation refuses to build a job folder around a missing cell"
        )
    return {
        "cells": [
            _notebook_cell(bootstrap_asset.read_text(encoding="utf-8")),
            _notebook_cell(invoke_asset.read_text(encoding="utf-8")),
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def generate_job(
    *,
    target: str | Path,
    service: str,
    job_name: str,
    product: str,
    commit: str,
    repo_url: str,
    repo_ref: str,
    clone_paths: Sequence[str],
    run_module: str,
    run_function: str,
    run_kwargs: Mapping[str, object] | None = None,
    smoke_module: str | None = None,
    smoke_function: str | None = None,
    smoke_kwargs: Mapping[str, object] | None = None,
    regenerate: bool = False,
    bootstrap_asset: str | Path | None = None,
    invoke_asset: str | Path | None = None,
) -> Path:
    """Generate one job folder, atomically, refusing to overwrite an
    existing one unless `regenerate=True`.

    Order is fixed: resolve `target` (no other check runs against a raw,
    unresolved path); derive and validate `destination`; build
    `run-config.json` and the notebook fully, in memory, before touching
    disk; only then check for an existing folder or a leftover `.partial/`.
    Everything from that point on writes into `<job>.partial/` first —
    `run-config.json`, `runner.ipynb`, and the adapter-supplied metadata
    file, in that order — and only a fully-written `.partial/` is ever
    renamed into place. A half-written job folder therefore cannot exist:
    either `.partial/` never became `destination` at all, or it did so as
    one atomic rename with everything already inside it.

    Regeneration replaces the existing folder without ever leaving
    `destination` half-old-half-new: the existing folder is renamed aside
    (an atomic rename to a fresh, guaranteed-unused name) before the new
    `.partial/` is renamed into `destination`'s place, and only removed
    once that second rename has actually succeeded. If the second rename
    itself fails, the aside copy is renamed straight back — `destination`
    is either the old job folder or the new one at every instant an
    outside observer could look, never neither and never a mix.
    """
    resolved_target = resolve_target(target)
    destination = resolve_destination(resolved_target, service, job_name)

    resolved_bootstrap = Path(bootstrap_asset) if bootstrap_asset else DEFAULT_BOOTSTRAP_ASSET
    resolved_invoke = Path(invoke_asset) if invoke_asset else DEFAULT_INVOKE_ASSET

    run_config = build_run_config(
        product=product,
        service=service,
        job_name=job_name,
        commit=commit,
        repo_url=repo_url,
        repo_ref=repo_ref,
        clone_paths=clone_paths,
        run_module=run_module,
        run_function=run_function,
        run_kwargs=run_kwargs,
        smoke_module=smoke_module,
        smoke_function=smoke_function,
        smoke_kwargs=smoke_kwargs,
        bootstrap_asset=resolved_bootstrap,
        invoke_asset=resolved_invoke,
    )
    notebook = build_notebook(resolved_bootstrap, resolved_invoke)
    metadata_filename, metadata_text = ADAPTER.resolve_metadata(service)(run_config)

    if destination.is_dir() and not regenerate:
        raise JobFolderError(
            f"{destination} already exists; pass regenerate=True (or "
            "--regenerate) to replace it"
        )

    partial = destination.with_name(destination.name + PARTIAL_SUFFIX)
    if partial.exists():
        raise JobFolderError(
            f"a leftover {partial} exists from a previous failed generation; "
            "it is never read as a job folder — remove it by hand before "
            "retrying"
        )

    partial.mkdir(parents=True)
    try:
        (partial / RUN_CONFIG_FILENAME).write_text(
            json.dumps(run_config, sort_keys=True, indent=2), encoding="utf-8"
        )
        (partial / RUNNER_FILENAME).write_text(
            json.dumps(notebook, indent=1), encoding="utf-8"
        )
        (partial / metadata_filename).write_text(metadata_text, encoding="utf-8")
    except BaseException:
        _rmtree(partial)
        raise

    aside = None
    if destination.is_dir():
        aside = destination.with_name(destination.name + STALE_SUFFIX_PREFIX + uuid.uuid4().hex)
        os.replace(str(destination), str(aside))
    try:
        os.replace(str(partial), str(destination))
    except BaseException:
        if aside is not None:
            os.replace(str(aside), str(destination))
        raise
    if aside is not None:
        _rmtree(aside)

    return destination
