"""Shared per-case execution: argv resolution, constructed env, one real
subprocess run, one normalize-and-digest. `seal_capture.py` calls this twice
per case and refuses to write anything on disagreement; the comparison
suite in `test_implementation_seal.py` calls it once per case and compares
against the stored golden. Two entry points, one mechanism (design.md).

Real subprocess, never in-process `impl.main(argv)` (design.md D2): a seal
blind to the process boundary is blind to Cut 1's own single silent failure
mode, `CLI_PATH` resolving to the wrong file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_FORGE = Path(__file__).resolve().parents[2]
#: The engine source (meaning 2): `impl.CLI_INVOCATION`/`impl.FORGE_ROOT`
#: below are engine attributes the launcher deliberately does not carry
#: (design.md D1), so this harness reaches the engine directly -- never
#: the launcher, which is what `impl.CLI_INVOCATION` itself names as the
#: invoked path (meaning 1), read back out of the engine's own profile-
#: derived `CLI_PATH`. Import route only; argv still derives from
#: `impl.CLI_INVOCATION`, unedited.
_ENGINE_DIR = (_FORGE / "skills" / "_core" / "implementation"
              / "engine")
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from domain_profile import seeded_profile  # noqa: E402  (tests/ on path)

with seeded_profile(_FORGE / "skills" / "proposal-implementation"
                    / "impl_profile.py"):
    import implementation_engine as impl  # noqa: E402  (path set above)

from . import corpus as seal_corpus
from . import normalize as seal_normalize

#: A timeout is a hard failure, never routed to `unsealed.json` (threat
#: matrix: Timeouts / hangs).
TIMEOUT_SECONDS = 120

#: The constructed env allow-list (design.md D2, task 3.5). The child env is
#: an explicit dict, NEVER `os.environ` inherited wholesale — an operator's
#: stray `IMPLEMENTATION_*` must not be able to reshape a digest.
ALLOWED_ENV_KEYS = frozenset({
    "PATH", "HOME", "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "LC_ALL",
    "TZ", "NO_COLOR", "COLUMNS", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
    # The pinned identity the corpus itself commits under -- allow-listed so
    # `build_env` can hand it to the child without tripping its own assert
    # (the `apply` case's `git commit` must not vary by operator machine).
    "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME", "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_EMAIL", "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE",
    "IMPLEMENTATION_PROPOSALS",
    # Cut 3 (`a-revision-is-two-documents`, design.md M5): the bare
    # `IMPLEMENTATION_PROPOSALS` keeps overriding document 0 only -- one
    # variable cannot name two roots. A second document's directory is
    # overridden by this key instead, allow-listed here so a later class
    # (or this corpus's own pair cases) can pass it without tripping
    # `build_env`'s own allow-list assert. No generic `_0` alias exists for
    # the bare variable (M5): that would be a second spelling for a
    # variable every existing fixture already uses.
    "IMPLEMENTATION_PROPOSALS_1",
})

#: Real shell-injection primitives, never characters legitimate case content
#: needs (`compose`'s `--entry-text` carries literal `$$`/`\n` for a LaTeX
#: display block, `settle`'s `--under` carries `#`) — `shell=False` makes
#: every character harmless to actually run, so this is belt-and-braces
#: against a case authored as if a shell would parse it.
_SHELL_METACHARACTERS = (";", "|", "&", "`")


class RosterValidationError(ValueError):
    """A case in `cases.json` is mis-specified — refused before any
    subprocess ever runs."""


def validate_case(case: dict) -> None:
    """Threat-matrix guard (design.md Threat Matrix, tasks 4.1/4.3).

    Refuses a case whose argv contains a shell-injection primitive, and
    refuses a case whose `--target` is not the `<TARGET>` placeholder this
    harness resolves into a fresh scratch copy — never a literal path a case
    author could point outside the scratch root.
    """
    argv = case["argv"]
    for token in argv:
        if any(marker in token for marker in _SHELL_METACHARACTERS) or "$(" in token:
            raise RosterValidationError(
                f"{case['id']}: argv token {token!r} contains a shell-injection "
                "primitive; every case runs with shell=False, but a case "
                "authored as if a shell would parse it is mis-specified.")
    if "--target" in argv:
        value = argv[argv.index("--target") + 1]
        if value != "<TARGET>":
            raise RosterValidationError(
                f"{case['id']}: --target must be the <TARGET> placeholder "
                f"this harness resolves into a fresh scratch copy, got "
                f"{value!r} — a literal path could point outside the "
                "scratch root.")


def validate_roster(cases: list) -> None:
    for case in cases:
        validate_case(case)


def build_env(case: dict, roots: "seal_corpus.Roots") -> dict:
    """The child env: `PATH`/`HOME` passed through, everything else pinned,
    `IMPLEMENTATION_PROPOSALS` only when the case says so (design.md D2)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "NO_COLOR": "1",
        "COLUMNS": "80",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        # The corpus commits under a pinned identity; a child `git commit`
        # must too. Measured live: with only the empty git config above, the
        # `apply` case's own `git commit` fell back to operator auto-detection
        # and baked `carlos@archlinux.(none)` (or CI's `runner@...`) into the
        # sealed bytes -- an environment-dependent digest that passed locally
        # and failed on every other machine.
        "GIT_AUTHOR_NAME": seal_corpus._GIT_IDENTITY_NAME,
        "GIT_COMMITTER_NAME": seal_corpus._GIT_IDENTITY_NAME,
        "GIT_AUTHOR_EMAIL": seal_corpus._GIT_IDENTITY_EMAIL,
        "GIT_COMMITTER_EMAIL": seal_corpus._GIT_IDENTITY_EMAIL,
        "GIT_AUTHOR_DATE": seal_corpus._GIT_AUTHOR_DATE,
        "GIT_COMMITTER_DATE": seal_corpus._GIT_AUTHOR_DATE,
    }
    if case.get("proposals"):
        env["IMPLEMENTATION_PROPOSALS"] = str(roots.proposals)
    extra = set(env) - ALLOWED_ENV_KEYS
    assert not extra, f"env builder emitted a key outside the allow-list: {sorted(extra)}"
    return env


def _fixture_path(case: dict, roots: "seal_corpus.Roots"):
    fixture = case.get("fixture")
    if fixture is None:
        return None
    return {"A": roots.fixture_a, "B": roots.fixture_b, "T": roots.fixture_t}[fixture]


def resolve_argv(case: dict, target_dir, roots: "seal_corpus.Roots", plan_path) -> list:
    """Substitute `<TARGET>`/`<PROPOSALS>`/`<FORGE>`/`<PLAN>` — the same
    placeholders N2 produces (design.md Interfaces), so the roster stays
    readable and path-free."""
    substitutions = {
        "<TARGET>": str(target_dir) if target_dir is not None else None,
        "<PROPOSALS>": str(roots.proposals),
        "<FORGE>": str(impl.FORGE_ROOT),
        "<PLAN>": str(plan_path) if plan_path is not None else None,
    }
    resolved = []
    for token in case["argv"]:
        for placeholder, value in substitutions.items():
            if placeholder in token:
                if value is None:
                    raise RosterValidationError(
                        f"{case['id']}: {placeholder} used but not available "
                        "for this case")
                token = token.replace(placeholder, value)
        resolved.append(token)
    return resolved


@dataclasses.dataclass(frozen=True)
class CaseResult:
    stdout_text: str
    exit_status: int


def run_case(case: dict, roots: "seal_corpus.Roots", *, scratch_root) -> CaseResult:
    """Copy the case's fixture into a fresh scratch dir (if it has one),
    materialize a `plan.json` sibling when the argv needs `<PLAN>`, build
    argv + env, run the CLI as a real subprocess, normalize the decoded
    stdout. Every writing command's `--target` and every `plan.json` this
    writes live under `scratch_root` — never outside it, never inside the
    committed corpus fixtures themselves."""
    case_dir = Path(tempfile.mkdtemp(dir=str(scratch_root), prefix=case["id"] + "-"))
    target_dir = None
    fixture_src = _fixture_path(case, roots)
    if fixture_src is not None:
        target_dir = case_dir / "target"
        shutil.copytree(fixture_src, target_dir)

    plan_path = None
    if any("<PLAN>" in token for token in case["argv"]):
        plan_path = case_dir / "plan.json"
        plan = dict(roots.plan_template)
        plan["target"] = str(target_dir)
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

    argv = resolve_argv(case, target_dir, roots, plan_path)
    full_argv = shlex.split(impl.CLI_INVOCATION) + [case["command"]] + argv
    env = build_env(case, roots)

    proc = subprocess.run(full_argv, cwd=str(impl.FORGE_ROOT), env=env,
                          capture_output=True, timeout=TIMEOUT_SECONDS)

    normalize_roots = seal_normalize.Roots(
        target=target_dir if target_dir is not None else Path("/__no_target__"),
        corpus=roots.root, forge=impl.FORGE_ROOT, proposals=roots.proposals)
    text = proc.stdout.decode("utf-8", errors="strict")
    normalized = seal_normalize.normalize(text, normalize_roots)
    return CaseResult(stdout_text=normalized, exit_status=proc.returncode)


def digest_result(result: CaseResult) -> dict:
    encoded = result.stdout_text.encode("utf-8")
    return {"sha256": hashlib.sha256(encoded).hexdigest(), "bytes": len(encoded),
           "exit": result.exit_status}
