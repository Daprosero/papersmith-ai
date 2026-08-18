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

`resolve_clone_paths()` is the AST-based, transitive dependency check:
declared `clonePaths` are cross-checked against what the declared entry
modules (`run.module`, plus `run.smoke.module` when present) actually
import, transitively, before a job folder is ever written. A real import
missing from `clonePaths` (`computedNotDeclared`) always refuses
generation; an import this walk cannot resolve with confidence (a
non-literal `importlib.import_module(...)` call, any `__import__(...)`
call, a `sys.path` mutation, an unparsable file, or an import that looks
like this repository's own code but does not resolve to a file on disk)
also refuses, unless `--accept-unresolved` is passed — which records the
uncertainty in `run-config.json`'s `unresolvedImports` instead of silently
guessing. See `resolve_clone_paths()`'s own docstring for the full rule.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import ast
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
# Holds the two runner assets' real, byte-for-byte-copied content;
# referenced here so every caller — this module's own `generate_job()`,
# `remote_cli.py`'s CLI wiring, and each test fixture alike — points at the
# exact same two paths.
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


def validate_clone_paths(
    clone_paths: Sequence[str], target: Path | None = None
) -> tuple[str, ...]:
    """Structural validation — empty is refused; an absolute path or one
    containing `..` is refused. When `target` is given, each path is also
    resolved against it and refused if that resolution escapes `target` —
    the symlink-escape case a purely textual check cannot see (a clone path
    whose name is safe in text but whose real, resolved location leaves the
    target directory through a symlink).

    This is the SAME validator every caller uses — `build_run_config()` at
    generation time (structural only, no `target` yet resolved), and
    `resolve_clone_paths()` again once `target` is known — never a second,
    parallel validator for the symlink case.
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
        if target is not None:
            # `.resolve()` on both sides: macOS resolves `/var` through
            # `/private/var`, so an unresolved `target` (e.g. straight out
            # of `tempfile.TemporaryDirectory()`) would otherwise never
            # compare equal to a fully-resolved clone path candidate.
            resolved_target = target.resolve()
            resolved = (resolved_target / candidate).resolve()
            try:
                resolved.relative_to(resolved_target)
            except ValueError:
                raise JobFolderError(
                    f"refusing clone path {raw!r}: resolves to {resolved}, "
                    f"outside target {resolved_target} (symlink escape)"
                ) from None
        validated.append(candidate.as_posix())
    return tuple(validated)


def _module_to_relpath(dotted: str, source: Path) -> Path | None:
    """Resolve a dotted module name to the `.py` file it names under
    `source` (`<target>/src`) — a package's `__init__.py` when the dotted
    name is itself a package, else a plain module file. `None` when neither
    exists.
    """
    parts = dotted.split(".")
    package_init = source.joinpath(*parts) / "__init__.py"
    plain_module = source.joinpath(*parts[:-1], parts[-1] + ".py")
    if package_init.is_file():
        return package_init
    if plain_module.is_file():
        return plain_module
    return None


def _classify_import(
    dotted: str, source: Path, *, is_entry: bool
) -> tuple[str, str | None, Path | None]:
    """Classify one dotted import name against `source` (`<target>/src`).

    `("internal", clone_path, file)` — this repository's own code;
    `clone_path` is the granularity-rule top-level clone path (`src/A` for
    a package, `src/A.py` for a true top-level module) it belongs under,
    and `file` feeds the transitive walk.

    `("unresolved", None, None)` — looks like this repository's own code
    (an entry module, or a top-level segment that exists under `source`)
    but the dotted path itself does not resolve to a file on disk.

    `("external", None, None)` — filtered: the top-level segment names
    nothing under `source` at all, so this is not this repository's own
    code and never becomes a clone path or an uncertainty. An entry module
    is deliberately never given this exemption — its own absence on disk
    is exactly the "resolves to nothing" uncertainty, not something to
    skip quietly, since an entry module is by definition meant to be this
    repository's own code.
    """
    top = dotted.split(".", 1)[0]
    top_dir = source / top
    top_file = source / f"{top}.py"
    looks_internal = top_dir.is_dir() or top_file.is_file()
    if not looks_internal:
        return ("unresolved" if is_entry else "external"), None, None
    clone_path = f"src/{top}" if top_dir.is_dir() else f"src/{top}.py"
    file = _module_to_relpath(dotted, source)
    if file is None:
        return "unresolved", None, None
    return "internal", clone_path, file


def _is_dunder_import_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
    )


def _is_import_module_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "import_module":
        return True
    return isinstance(func, ast.Name) and func.id == "import_module"


def _literal_import_module_argument(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def _is_sys_path_target(expr: ast.AST) -> bool:
    return (
        isinstance(expr, ast.Attribute)
        and expr.attr == "path"
        and isinstance(expr.value, ast.Name)
        and expr.value.id == "sys"
    )


def _is_sys_path_mutation(node: ast.AST) -> bool:
    """`sys.path.append/insert/extend/remove/pop(...)`, `sys.path = ...`,
    `sys.path[...] = ...`, or `sys.path += ...` — any mutation of
    `sys.path`, which can change what a later import in the same file
    resolves to and makes this walk's own resolution uncertain.
    """
    if isinstance(node, ast.Call):
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr in ("append", "insert", "extend", "remove", "pop")
            and _is_sys_path_target(func.value)
        )
    if isinstance(node, ast.Assign):
        return any(_is_sys_path_target(t) for t in node.targets)
    if isinstance(node, ast.AugAssign):
        return _is_sys_path_target(node.target)
    return False


def resolve_clone_paths(
    target: Path,
    entry_modules: Sequence[str],
    declared_clone_paths: Sequence[str],
) -> dict:
    """Cross-check declared `clonePaths` against what the declared entry
    modules actually import, transitively, before generation ever writes a
    job folder.

    Reuses `implementation_cli.py`'s `prior_work_state()` idiom exactly for
    the walk itself (`ast.parse` + `ast.walk` over `ast.Import`/
    `ast.ImportFrom`, inspecting only `node.module` for `ImportFrom` and
    `alias.name` for `Import`, with no relative-import resolution and no
    per-name submodule disambiguation) — just walked transitively, over
    every module an entry module reaches, instead of over one fixed file
    set.

    The granularity rule (design #744 section 3): a resolved import maps
    to its top-level package directory under `src/`, never to a single
    file — `src/A/B/C.py` => clone path `src/A`; a true top-level module
    `src/A.py` => clone path `src/A.py`. An import that is not this
    repository's own code (its top-level segment names nothing under
    `<target>/src` at all) is filtered and never becomes a clone path.

    Returns `{"declared", "computed", "computedNotDeclared", "unresolved"}`:
    `declared` is `declared_clone_paths` re-validated through the SAME
    `validate_clone_paths()` `generate_job()` already uses (structural,
    plus the symlink-escape check now that `target` is known) — never a
    second validator. `computedNotDeclared` names every real import missing
    from `clonePaths`; a non-empty result is always a refusal, never a
    warning. `unresolved` names every uncertain case this walk hit: a
    non-literal `importlib.import_module(...)` call, any `__import__(...)`
    call, a `sys.path` mutation, an unparsable file, or an import that
    looks like this repository's own code but does not resolve to a file
    on disk. A non-empty `unresolved` refuses generation unless the caller
    passes `--accept-unresolved`, which records it in `run-config.json`'s
    `unresolvedImports` instead of guessing.
    """
    resolved_target = target.resolve()
    source = resolved_target / "src"
    declared = validate_clone_paths(declared_clone_paths, resolved_target)

    computed: set[str] = set()
    unresolved: list[str] = []
    visited: set[Path] = set()
    queued: set[str] = set(entry_modules)
    queue: list[tuple[str, bool]] = [(name, True) for name in entry_modules]

    def enqueue(name: str) -> None:
        if name not in queued:
            queued.add(name)
            queue.append((name, False))

    while queue:
        dotted, is_entry = queue.pop(0)
        kind, clone_path, file = _classify_import(dotted, source, is_entry=is_entry)
        if kind == "external":
            continue
        if kind == "unresolved":
            unresolved.append(
                f"import {dotted!r} resolves to nothing on disk under {source}"
            )
            continue
        computed.add(clone_path)
        if file in visited:
            continue
        visited.add(file)

        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            unresolved.append(f"{file}: unreadable ({exc})")
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            unresolved.append(f"{file}: unparsable ({exc})")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                enqueue(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    enqueue(alias.name)
            elif _is_dunder_import_call(node):
                unresolved.append(f"{file}: __import__(...) call is uncertain")
            elif _is_import_module_call(node):
                literal = _literal_import_module_argument(node)
                if literal is not None:
                    enqueue(literal)
                else:
                    unresolved.append(
                        f"{file}: non-literal importlib.import_module(...) call is uncertain"
                    )
            elif _is_sys_path_mutation(node):
                unresolved.append(f"{file}: sys.path mutation is uncertain")

    return {
        "declared": list(declared),
        "computed": sorted(computed),
        "computedNotDeclared": sorted(computed - set(declared)),
        "unresolved": unresolved,
    }


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
    unresolved_imports: Sequence[str] | None = None,
) -> dict:
    """Assemble `run-config.json`'s exact shape from target-supplied values.

    `runnerTemplate` records each asset's path and sha256 as inert
    provenance — deliberately not a drift check (see `SKILL.md`): a second
    staleness condition is explicitly out of scope for this skill.

    `unresolved_imports`, when non-empty, is recorded verbatim as
    `unresolvedImports` — the `--accept-unresolved` escape hatch turning a
    silence into a recorded, reportable decision (design #744 section 3).
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
    if unresolved_imports:
        run_config["unresolvedImports"] = list(unresolved_imports)
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
    accept_unresolved: bool = False,
) -> Path:
    """Generate one job folder, atomically, refusing to overwrite an
    existing one unless `regenerate=True`.

    Order is fixed: resolve `target` (no other check runs against a raw,
    unresolved path); derive and validate `destination`; resolve and
    cross-check `clone_paths` against what the declared entry modules
    actually import (`resolve_clone_paths()`), refusing before anything
    else is built if that check fails; build `run-config.json` and the
    notebook fully, in memory, before touching disk; only then check for an
    existing folder or a leftover `.partial/`. Everything from that point
    on writes into `<job>.partial/` first — `run-config.json`,
    `runner.ipynb`, and the adapter-supplied metadata file, in that order —
    and only a fully-written `.partial/` is ever renamed into place. A
    half-written job folder therefore cannot exist: either `.partial/`
    never became `destination` at all, or it did so as one atomic rename
    with everything already inside it.

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

    entry_modules = [run_module]
    if smoke_module and smoke_function:
        entry_modules.append(smoke_module)
    clone_resolution = resolve_clone_paths(resolved_target, entry_modules, clone_paths)
    if clone_resolution["computedNotDeclared"]:
        raise JobFolderError(
            "generation refuses: these imports resolve to clone paths not "
            "declared in --clone-path: "
            f"{clone_resolution['computedNotDeclared']}"
        )
    if clone_resolution["unresolved"] and not accept_unresolved:
        raise JobFolderError(
            "generation refuses: uncertain imports found (pass "
            "--accept-unresolved to record and proceed instead of refusing): "
            f"{clone_resolution['unresolved']}"
        )

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
        unresolved_imports=clone_resolution["unresolved"] if accept_unresolved else None,
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
