"""This corpus's own thin wrapper over `tests/seal/harness.py`'s generic
machinery (design.md D7): `run_case`/`validate_case`/`digest_result`/
`RosterValidationError` are reused UNEDITED (`tests/seal/harness.py` itself
is never modified -- the bar `git diff --exit-code tests/seal/` holds).

What differs is WHICH launcher a case's argv resolves to.
`seal_harness.run_case` builds `full_argv` from `impl.CLI_INVOCATION` --
`impl` there is `tests/seal/harness.py`'s own `implementation_engine`
import, permanently resolved (by that module's own `os.environ.setdefault`)
against the SIBLING's profile. `cli_invocation()` below temporarily
reassigns that one attribute for the duration of a call -- an argv change,
never a monkeypatch of anything a CHILD process reads (design.md D7): the
child this launches is a real, separate subprocess running THIS skill's own
launcher, and nothing inside an already-running child is touched.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

FORGE = Path(__file__).resolve().parents[2]
LAUNCHER = (
    FORGE / "skills" / "experimental-implementation" / "scripts"
    / "implementation_cli.py")

_TESTS_DIR = FORGE / "tests"
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
from seal import harness as seal_harness  # noqa: E402  (path set above)
from seal import corpus as seal_corpus  # noqa: E402  (re-exported below)

#: Re-exported for callers that only need the generic, unedited surface.
run_case = seal_harness.run_case
digest_result = seal_harness.digest_result
validate_case = seal_harness.validate_case
validate_roster = seal_harness.validate_roster
RosterValidationError = seal_harness.RosterValidationError
build_env = seal_harness.build_env
ALLOWED_ENV_KEYS = seal_harness.ALLOWED_ENV_KEYS

_LAUNCHER_INVOCATION = f"{sys.executable} {LAUNCHER}"

#: Captured once, before this module ever reassigns `seal_harness.
#: build_env` -- the wrapper below calls THIS reference, never the module
#: attribute (which becomes the wrapper itself once assigned; calling
#: through the attribute would recurse into itself forever). Mirrors
#: `test_implementation_pair.py`'s own `_build_env_with_profile_override`
#: pattern.
_ORIGINAL_BUILD_ENV = seal_harness.build_env


def _build_env_with_document_one(case: dict, roots) -> dict:
    """`seal_harness.build_env` only ever sets `IMPLEMENTATION_PROPOSALS`
    (document 0's own override) -- Slice C (design.md task 4.6): this
    corpus's own `Roots.proposals_1` is a real, readable revision root for
    `documents[1]`, so a case marked `proposals: true` also gets
    `IMPLEMENTATION_PROPOSALS_1` here, never inside `tests/seal/
    harness.py` itself (that file stays unedited -- `git diff --exit-code
    tests/seal/` holds).

    `the-agreement-nothing-computes` (Slice D): a case marked
    `crossingTarget: true` gets `roots.proposals_1_crossing` instead --
    the crossing axis's own isolated document-1 root (`corpus.py::
    _build_crossing_target`), never the shared `proposals_1` every OTHER
    two-document case's default discovery depends on unmoved."""
    env = _ORIGINAL_BUILD_ENV(case, roots)
    if case.get("proposals"):
        if (case.get("crossingTarget")
                and getattr(roots, "proposals_1_crossing", None) is not None):
            env["IMPLEMENTATION_PROPOSALS_1"] = str(roots.proposals_1_crossing)
        elif getattr(roots, "proposals_1", None) is not None:
            env["IMPLEMENTATION_PROPOSALS_1"] = str(roots.proposals_1)
    return env


@contextlib.contextmanager
def cli_invocation():
    """Wrap `seal_harness.impl.CLI_INVOCATION` for the duration of the
    block -- this skill's own launcher, not the sibling's -- and restore
    the original value on exit, success or failure alike. Also wraps
    `seal_harness.build_env` (design.md task 4.6) to add
    `IMPLEMENTATION_PROPOSALS_1`, the same duration and restoration
    discipline."""
    original_invocation = seal_harness.impl.CLI_INVOCATION
    original_build_env = seal_harness.build_env
    seal_harness.impl.CLI_INVOCATION = _LAUNCHER_INVOCATION
    seal_harness.build_env = _build_env_with_document_one
    try:
        yield
    finally:
        seal_harness.impl.CLI_INVOCATION = original_invocation
        seal_harness.build_env = original_build_env


def run_case_here(case: dict, roots, *, scratch_root):
    """`run_case`, wrapped so this corpus's cases run through THIS skill's
    own launcher for the duration of the one call."""
    with cli_invocation():
        return seal_harness.run_case(case, roots, scratch_root=scratch_root)
