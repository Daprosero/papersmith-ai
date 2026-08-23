#!/usr/bin/env python3
"""Cell 0 of the generated runner notebook — copied byte for byte.

`jobfolder.build_notebook()` copies this file's bytes into the notebook's
first cell with ZERO interpolation. The same bytes serve every job because
every fact this cell needs comes from `run-config.json`, read at runtime,
never baked in at generation time. Ten responsibilities, in order:

1. read `run-config.json`; validate schema/version
2. sparse-clone the pinned commit: `git init`, `remote add`,
   `sparse-checkout set <clonePaths>`, `fetch --depth 1 origin <commit>`,
   `checkout FETCH_HEAD`
3. `sys.path.insert(0, <clone>/src)`
4. install the declared build: `sys.executable -m pip install`, list
   argv, against `run-config.json`'s additive `environment.install`
   (Decision 3). This runs BEFORE responsibility 5, never after —
   responsibility 5 imports the declared modules, and those modules
   import the tensor library this step installs; installing after that
   point would be too late. An older, undeclared config carries no
   `environment.install` block and this step is a no-op. Honest cost:
   this installs on every kernel that runs a job, adding minutes to each
   one — a campaign of thirty shards pays that cost thirty times.
   Determinism (the arriving capability verified against what was
   actually installed, never assumed) was chosen over the cheaper
   deferral of trusting a pre-baked image
5. import each declared module and assert its `__file__` resolves under
   the clone's own `src` — the "pip-installed copy" refusal: a module
   importable from somewhere ELSE already on `sys.path` would silently
   run against code this job never pinned a commit for
6. detect hardware — `torch` not importable IS "hardware missing"; no
   silent CPU fallback, or this refusal could never actually fire
7. write `bootstrap.json`: commit, config, detected environment
8. any of config / code / hardware missing raises `SystemExit` on the
   spot, so cell 1 never runs against a half-prepared runtime
9. the accelerator gate: the arriving capability must appear in the
   installed arch list, and any declared `accelerator.architectures`
   must be covered by that same installed list. This runs AFTER
   responsibility 7, never before — a refusal whose evidence was never
   written is unreadable no matter how early it fires, so `bootstrap.json`
   already carries the arriving device, the torch build and the arch
   list the verdict was computed from by the time this refuses
10. no service name anywhere, ever

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


class AcceleratorError(BootstrapError):
    """Responsibility 8's refusal: the arriving accelerator cannot run
    this build's kernels, or the declared architectures are not covered
    by the torch build actually installed. A subclass of
    `BootstrapError` so `bootstrap()`'s existing `except BootstrapError`
    converts it to `SystemExit` the same way as every other refusal —
    no second exception-handling path to keep in step.
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


# The whole allowlist a pip subprocess's environment is built from —
# never `os.environ` forwarded wholesale, the same restraint
# `GIT_ENV_ALLOWLIST` above already applies to its own child environment.
# A separate constant, deliberately: this cell's pip invocation and its
# git invocations are different subprocess families, and each holds this
# discipline on its own rather than sharing one name that could drift for
# the wrong reason.
PIP_ENV_ALLOWLIST = ("PATH",)
PIP_INSTALL_TIMEOUT_SECONDS = 600.0


def _validate_requirement_specifier(spec: str) -> str:
    """A requirement specifier is data, never a flag. `pip install` reads
    each positional argv element as either a package specifier or, when
    it begins with `-`, an option of its own — a declared specifier
    shaped like `--index-url https://evil.invalid` would occupy the same
    argv position as a real package name and silently redirect the whole
    install to an attacker-controlled index. Refusing any specifier
    beginning with `-` is what keeps a declared `requirements` list
    unable to smuggle a flag this way. Nothing else about the string is
    inspected: shell metacharacters elsewhere in a specifier reach pip's
    argv as inert data, the same `shell=False`, list-argv guarantee
    `_run_git()` already gives every value this cell passes to git.
    """
    if not isinstance(spec, str) or not spec or spec.startswith("-"):
        raise BootstrapError(
            f"environment.install refuses requirement specifier {spec!r}: "
            "a specifier beginning with '-' would be read by pip as an "
            "option, not a package to install"
        )
    return spec


def _run_pip(args: Sequence[str], *, timeout: float = PIP_INSTALL_TIMEOUT_SECONDS) -> None:
    """The single composition point for the one pip invocation this cell
    makes — the same discipline `_run_git()` already holds: `shell=False`
    with a list argv, so a value carrying shell metacharacters reaches
    argv as one element and is never evaluated by a shell; the
    environment built from `PIP_ENV_ALLOWLIST` alone, never this
    process's own `os.environ` forwarded wholesale; an explicit timeout;
    a non-zero exit is a refusal, never silently ignored.
    """
    argv = [sys.executable, "-m", "pip", *args]
    env = {name: os.environ[name] for name in PIP_ENV_ALLOWLIST if name in os.environ}
    try:
        result = subprocess.run(
            argv,
            shell=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BootstrapError(
            f"environment install timed out after {timeout}s running pip "
            f"{' '.join(args)}"
        ) from exc
    except OSError as exc:
        raise BootstrapError(f"could not run pip: {exc}") from exc
    if result.returncode != 0:
        raise BootstrapError(
            f"pip {' '.join(args)} exited {result.returncode}: "
            f"{result.stderr.strip()}"
        )


def install_environment(run_config: Mapping[str, Any]) -> None:
    """Responsibility 4: install the dual-architecture torch build (or
    whatever else the target declares) BEFORE responsibility 5 imports
    the target's own modules — those imports pull in the tensor library
    this step installs, so installing after that point would be too
    late.

    Reads `run-config.json`'s additive `environment.install:
    {requirements[], indexUrl}` (Decision 3). Additive: an older config
    with no `environment` block, or no `install` block within it,
    installs nothing at all — this is a no-op, exactly as this cell
    behaved before the field existed. This module names only those two
    fields and never a package: it does not know which tensor-library
    build a target needs, only that the target declared one.

    Every requirement specifier is validated by
    `_validate_requirement_specifier()` before any argv is built, and the
    whole install runs through `_run_pip()`, the single composition point
    matching `_run_git()`'s own discipline: `sys.executable -m pip
    install`, with `--index-url <indexUrl>` first when declared, then
    each requirement its own argv element — never one opaque command
    string.
    """
    environment = run_config.get("environment")
    install = environment.get("install") if isinstance(environment, Mapping) else None
    if not isinstance(install, Mapping):
        return
    requirements = [
        _validate_requirement_specifier(spec)
        for spec in (install.get("requirements") or [])
    ]
    if not requirements:
        raise BootstrapError(
            "config missing: environment.install declares no requirements "
            "to install"
        )
    index_url = install.get("indexUrl")
    args = ["install"]
    if index_url:
        args += ["--index-url", str(index_url)]
    args += requirements
    _run_pip(args)


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
    under the clone's own `src` — responsibility 5, the "pip-installed
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


def _capability_to_arch(capability: tuple[int, int]) -> str:
    """`torch.cuda.get_device_capability()`'s `(major, minor)` pair,
    formatted the same way `torch.cuda.get_arch_list()` names its own
    entries (`sm_60`, `sm_75`, ...) — the one shared vocabulary the
    accelerator gate compares against.
    """
    major, minor = capability
    return f"sm_{major}{minor}"


def detect_hardware(
    *, import_module: Callable[[str], Any] = importlib.import_module
) -> dict[str, Any]:
    """Hardware detection — responsibility 6. `torch` not importable IS
    the refusal mapping for "hardware missing": no silent CPU fallback,
    because a silent fallback would mean this refusal branch could never
    actually fire.

    Beside `device` and `torch`, this also captures `archList` — the
    architectures THIS INSTALLED torch build actually ships kernels for
    (`torch.cuda.get_arch_list()`) — and `capability`, the arriving
    device's own capability formatted the same way. Both are what
    responsibility 9's accelerator gate compares; neither requires the
    declared `accelerator` block to exist, since the arch list a build
    installs is a fact about that build, not about what any job declared.
    A runtime with no CUDA device carries nothing to compare: `archList`
    is `[]` and `capability` is `None`.
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
    if cuda_available:
        arch_list = list(torch.cuda.get_arch_list())
        capability = _capability_to_arch(torch.cuda.get_device_capability(0))
    else:
        arch_list = []
        capability = None
    return {
        "device": device,
        "torch": str(torch.__version__),
        "archList": arch_list,
        "capability": capability,
    }


def write_bootstrap_output(
    base_dir: str | Path | None,
    *,
    commit: str,
    run_config: Mapping[str, Any],
    environment: Mapping[str, Any],
    imports: Mapping[str, str],
) -> Path:
    """`bootstrap.json` — responsibility 7: the commit, the config, the
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


def check_accelerator(run_config: Mapping[str, Any], environment: Mapping[str, Any]) -> None:
    """The accelerator gate — responsibility 9, run only AFTER
    `write_bootstrap_output()` (see `bootstrap()` below). Two assertions:

    1. the arriving `capability` must appear in the INSTALLED `archList`
       — the physics check: can this build run on this card at all. It
       needs no declaration and runs whenever a capability was detected
       (a CPU-only runtime has none, and nothing to refuse here).
    2. the declared `accelerator.architectures`, when `run-config.json`
       declares an `accelerator` block, must be covered by that same
       installed `archList` — this is how the dual-architecture torch
       build gets VERIFIED rather than assumed. An older, undeclared
       config carries no `accelerator` block and this assertion is
       skipped entirely: additive, `schemaVersion` stays 1.
    """
    capability = environment.get("capability")
    arch_list = list(environment.get("archList") or [])
    if capability is not None and capability not in arch_list:
        raise AcceleratorError(
            f"accelerator mismatch: this runtime's capability {capability!r} "
            f"is not in the installed torch build's arch list {arch_list!r}; "
            "training would fail with no kernel image for this device"
        )
    accelerator = run_config.get("accelerator")
    if isinstance(accelerator, Mapping):
        declared = list(accelerator.get("architectures") or [])
        uncovered = [arch for arch in declared if arch not in arch_list]
        if uncovered:
            raise AcceleratorError(
                f"accelerator mismatch: declared architectures {uncovered} "
                f"are not covered by the installed torch build's arch list "
                f"{arch_list!r}; the dual-architecture build was assumed, "
                "never verified"
            )


def bootstrap(
    base_dir: str | Path | None = None,
    *,
    hardware_import: Callable[[str], Any] = importlib.import_module,
) -> dict[str, Any]:
    """The whole of cell 0, in the fixed order the design pins:
    config -> clone -> `sys.path` -> install -> imports -> hardware ->
    `bootstrap.json` -> the accelerator gate.

    Any of config / code / hardware missing raises `SystemExit` on the
    spot — responsibility 8 — so cell 1 never runs against a
    half-prepared runtime. `hardware_import` exists only so a test can
    drive `detect_hardware()`'s success path without a real GPU or a real
    `torch` install; the default is the real `importlib.import_module`.

    `check_accelerator()` runs LAST inside this `try`, strictly after
    `write_bootstrap_output()` — never before. Cell 1 already cannot run
    after this cell's own `SystemExit`, so "before training" is
    structural regardless of ordering; what ordering decides is whether
    the refusal's own evidence (the arriving device, the torch build, the
    installed arch list the verdict was computed from) is still readable
    on disk once it fires. It always is, because it was written first.
    """
    base = Path(base_dir) if base_dir is not None else Path.cwd()
    try:
        run_config = load_run_config(base)
        clone_dir = clone_repo(run_config, base / CLONE_DIRNAME)
        src_dir = add_clone_to_path(clone_dir)
        install_environment(run_config)
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
        check_accelerator(run_config, environment)
    except BootstrapError as exc:
        raise SystemExit(f"bootstrap refused: {exc}") from exc
    return {"commit": run_config["commit"], "environment": environment, "imports": imports}


if __name__ == "__main__":
    bootstrap()
