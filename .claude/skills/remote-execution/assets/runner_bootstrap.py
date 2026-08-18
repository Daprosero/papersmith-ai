#!/usr/bin/env python3
"""Cell 0 of the generated runner notebook — copied byte for byte.

`jobfolder.build_notebook()` copies this file's bytes into the notebook's
first cell with ZERO interpolation. The same bytes serve every job because
every fact this cell needs comes from `run-config.json`, read at runtime,
never baked in at generation time. Eight responsibilities, in order:

1. read `run-config.json`; validate schema/version
2. sparse-clone the pinned commit: `git init`, `remote add`,
   `sparse-checkout set <clonePaths>`, `fetch --depth 1 origin <commit>`,
   `checkout FETCH_HEAD`
3. `sys.path.insert(0, <clone>/src)`
4. import each declared module and assert its `__file__` resolves under
   the clone's own `src` — the "pip-installed copy" refusal: a module
   importable from somewhere ELSE already on `sys.path` would silently
   run against code this job never pinned a commit for
5. detect hardware — `torch` not importable IS "hardware missing"; no
   silent CPU fallback, or this refusal could never actually fire
6. write `bootstrap.json`: commit, config, detected environment
7. any of config / code / hardware missing raises `SystemExit` on the
   spot, so cell 1 never runs against a half-prepared runtime
8. no service name anywhere, ever

Importable and independently testable: every responsibility above is a
plain function, and `bootstrap()` composes them. Nothing runs at import
time — the orchestrating call sits behind `if __name__ == "__main__":`,
the state a notebook cell's own top-level code runs in (a Jupyter
kernel's namespace has `__name__ == "__main__"`), so importing this file
under a different module name never fires it. That is what lets the forge
suite drive `bootstrap()` and every helper directly against fake configs,
in-process — the whole justification `jobfolder.py` gives for shipping
this as a byte-for-byte copy rather than a per-job embedded prose cell.

Every git call goes through `_run_git()`, the single composition point:
`shell=False`, list argv, a PATH-only env allowlist, an explicit timeout,
non-zero exit is a refusal.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class BootstrapError(Exception):
    """A refusal: the run configuration, the declared code, or this
    runtime's hardware is missing or invalid. `bootstrap()` is the only
    place that turns one of these into `SystemExit`.
    """


CONFIG_FILENAME = "run-config.json"
BOOTSTRAP_OUTPUT_FILENAME = "bootstrap.json"
CLONE_DIRNAME = "clone"
SRC_DIRNAME = "src"
RUN_CONFIG_SCHEMA_VERSION = 1
REQUIRED_RUN_CONFIG_FIELDS = ("schemaVersion", "commit", "repo", "clonePaths", "run")

# The whole allowlist a git subprocess's environment is built from — never
# `os.environ` forwarded wholesale, the same restraint every other
# subprocess call in this skill applies to its own child environment.
GIT_ENV_ALLOWLIST = ("PATH",)
GIT_TIMEOUT_SECONDS = 120.0


def _config_path(base_dir: str | Path | None) -> Path:
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    return base / CONFIG_FILENAME


def load_run_config(base_dir: str | Path | None = None) -> dict:
    """Read `run-config.json` beside the notebook (or `base_dir`, for a
    test) and validate its schema/version — responsibility 1.
    """
    path = _config_path(base_dir)
    if not path.is_file():
        raise BootstrapError(
            f"config missing: {path} does not exist; nothing to bootstrap from"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BootstrapError(f"config missing: {path} is not valid JSON: {exc}") from exc
    _validate_run_config(payload)
    return payload


def _validate_run_config(run_config: object) -> None:
    if not isinstance(run_config, dict):
        raise BootstrapError("config missing: run-config.json must decode to a JSON object")
    missing = [f for f in REQUIRED_RUN_CONFIG_FIELDS if f not in run_config]
    if missing:
        raise BootstrapError(
            f"config missing: run-config.json missing required fields: {missing}"
        )
    if run_config.get("schemaVersion") != RUN_CONFIG_SCHEMA_VERSION:
        raise BootstrapError(
            f"config missing: run-config.json declares schemaVersion "
            f"{run_config.get('schemaVersion')!r}; this bootstrap reads only "
            f"{RUN_CONFIG_SCHEMA_VERSION}"
        )
    run_block = run_config.get("run")
    if not isinstance(run_block, dict) or "module" not in run_block:
        raise BootstrapError(
            "config missing: run-config.json's 'run' block must declare a 'module'"
        )


def _run_git(
    args: Sequence[str],
    *,
    cwd: str | Path,
    timeout: float = GIT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess:
    """The single composition point for every git invocation this cell
    makes. `shell=False` with a list argv means a value carrying shell
    metacharacters reaches `argv` as one element and is never evaluated —
    no shell is ever invoked to evaluate it. The environment is built from
    `GIT_ENV_ALLOWLIST` alone, never this process's own `os.environ`
    forwarded wholesale. A non-zero exit or an expired timeout raises
    `BootstrapError` rather than being silently ignored.
    """
    argv = ["git", *args]
    env = {name: os.environ[name] for name in GIT_ENV_ALLOWLIST if name in os.environ}
    try:
        result = subprocess.run(
            argv,
            shell=False,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError(f"git {' '.join(args)} timed out after {timeout}s") from exc
    except OSError as exc:
        raise BootstrapError(f"could not run git: {exc}") from exc
    if result.returncode != 0:
        raise BootstrapError(
            f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result


def clone_repo(run_config: Mapping[str, Any], clone_dir: str | Path) -> Path:
    """Sparse-clone the declared repo at the pinned commit — responsibility
    2 — every step through `_run_git()` alone: `init`, `remote add`,
    `sparse-checkout set <clonePaths>`, `fetch --depth 1 origin <commit>`,
    `checkout FETCH_HEAD`.
    """
    clone_dir = Path(clone_dir)
    clone_dir.mkdir(parents=True, exist_ok=True)
    repo = run_config["repo"]
    commit = run_config["commit"]
    clone_paths = list(run_config["clonePaths"])

    _run_git(["init"], cwd=clone_dir)
    _run_git(["remote", "add", "origin", repo["url"]], cwd=clone_dir)
    _run_git(["sparse-checkout", "set", *clone_paths], cwd=clone_dir)
    _run_git(["fetch", "--depth", "1", "origin", commit], cwd=clone_dir)
    _run_git(["checkout", "FETCH_HEAD"], cwd=clone_dir)
    return clone_dir


def add_clone_to_path(clone_dir: str | Path) -> Path:
    """`sys.path.insert(0, <clone>/src)` — responsibility 3."""
    src_dir = (Path(clone_dir) / SRC_DIRNAME).resolve()
    sys.path.insert(0, str(src_dir))
    return src_dir


def declared_modules(run_config: Mapping[str, Any]) -> list[str]:
    """Every module `run-config.json` names as an entry point: the normal
    `run.module`, plus `run.smoke.module` when present — both get the
    same `__file__`-under-clone proof at bootstrap time, since either one
    could be the module cell 1 actually calls.
    """
    run_block = run_config["run"]
    modules = [run_block["module"]]
    smoke = run_block.get("smoke")
    if isinstance(smoke, dict) and smoke.get("module"):
        modules.append(smoke["module"])
    return modules


def verify_imports_under_clone(
    modules: Sequence[str],
    src_dir: str | Path,
    *,
    import_module: Callable[[str], Any] = importlib.import_module,
) -> dict[str, str]:
    """Import each declared module and assert its `__file__` resolves
    under the clone's own `src` — responsibility 4, the "pip-installed
    copy" refusal. `.resolve()` on both sides: a temp path traversing a
    `/var` -> `/private/var`-style symlink must compare equal either way.
    """
    resolved_src = Path(src_dir).resolve()
    verified: dict[str, str] = {}
    for name in modules:
        try:
            module = import_module(name)
        except ImportError as exc:
            raise BootstrapError(
                f"code missing: declared module {name!r} could not be imported: {exc}"
            ) from exc
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise BootstrapError(
                f"code missing: module {name!r} carries no __file__; its location "
                "cannot be verified"
            )
        resolved_file = Path(module_file).resolve()
        try:
            resolved_file.relative_to(resolved_src)
        except ValueError:
            raise BootstrapError(
                f"code missing: module {name!r} resolved to {resolved_file}, "
                f"outside the clone's own src at {resolved_src} — refusing the "
                "'pip-installed copy' case"
            )
        verified[name] = str(resolved_file)
    return verified


def detect_hardware(
    *, import_module: Callable[[str], Any] = importlib.import_module
) -> dict[str, Any]:
    """Hardware detection — responsibility 5. `torch` not importable IS
    the refusal mapping for "hardware missing": no silent CPU fallback,
    because a silent fallback would mean this refusal branch could never
    actually fire.
    """
    try:
        torch = import_module("torch")
    except ImportError as exc:
        raise BootstrapError(
            "hardware missing: torch is not importable in this runtime"
        ) from exc
    cuda_available = bool(torch.cuda.is_available())
    device = {
        "kind": "cuda" if cuda_available else "cpu",
        "name": torch.cuda.get_device_name(0) if cuda_available else "cpu",
    }
    return {"device": device, "torch": str(torch.__version__)}


def write_bootstrap_output(
    base_dir: str | Path | None,
    *,
    commit: str,
    run_config: Mapping[str, Any],
    environment: Mapping[str, Any],
    imports: Mapping[str, str],
) -> Path:
    """`bootstrap.json` — responsibility 6: the commit, the config, the
    detected environment, and the resolved import locations responsibility
    4 just proved.
    """
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    payload = {
        "commit": commit,
        "config": dict(run_config),
        "environment": dict(environment),
        "imports": dict(imports),
    }
    path = base / BOOTSTRAP_OUTPUT_FILENAME
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return path


def bootstrap(
    base_dir: str | Path | None = None,
    *,
    hardware_import: Callable[[str], Any] = importlib.import_module,
) -> dict[str, Any]:
    """The whole of cell 0, in the fixed order the design pins:
    config -> clone -> `sys.path` -> imports -> hardware -> `bootstrap.json`.

    Any of config / code / hardware missing raises `SystemExit` on the
    spot — responsibility 7 — so cell 1 never runs against a
    half-prepared runtime. `hardware_import` exists only so a test can
    drive `detect_hardware()`'s success path without a real GPU or a real
    `torch` install; the default is the real `importlib.import_module`.
    """
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    try:
        run_config = load_run_config(base)
        clone_dir = clone_repo(run_config, base / CLONE_DIRNAME)
        src_dir = add_clone_to_path(clone_dir)
        modules = declared_modules(run_config)
        imports = verify_imports_under_clone(modules, src_dir)
        environment = detect_hardware(import_module=hardware_import)
        write_bootstrap_output(
            base,
            commit=run_config["commit"],
            run_config=run_config,
            environment=environment,
            imports=imports,
        )
    except BootstrapError as exc:
        raise SystemExit(f"bootstrap refused: {exc}") from exc
    return {"commit": run_config["commit"], "environment": environment, "imports": imports}


if __name__ == "__main__":
    bootstrap()
