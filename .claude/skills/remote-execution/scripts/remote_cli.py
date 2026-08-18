#!/usr/bin/env python3
"""The CLI front door for forge-owned remote execution.

This module is the top of this skill's own dependency chain —
`remote_cli -> packer -> ledger -> adapter` — and it is deliberately the
ONLY module in that chain that names a command-line entry point, parses
`--target`/`--entrypoint`/`--worker` arguments, and decides what counts as
a submittable path in this forge's own repository layout. Everything below
it (`packer.py`, `ledger.py`, `adapter.py`) stays blind to both concerns:
they take paths, ids and dicts as arguments and never ask where an argument
came from or what kind of file it names.

`submit`, `status`, `poll`, `fetch` and `reconcile` are the five commands.
`status` reports the fold and calls no adapter at all — it never resolves
anything, only renders what the ledger already says. `poll` and `fetch`
call the adapter; `fetch` is the only command that ever writes an artifact
to disk, and it does so through a materialize-then-rename sequence so a
crash never leaves a false `returned` event behind (see `cmd_fetch`).
`reconcile` compares the ledger against `adapter.list_active()` in both
directions and reports the difference; it never auto-adopts a remote orphan
and never auto-resolves a local one — `--resolve` is the one human-invoked
exception, and even then it only ever appends `errored`, never `returned`
or `submitted`.

`submit`, `poll`, `fetch` and `reconcile` construct their adapter with a
credential PROVIDER, never a value and never a pre-built mapping this
module would have to assemble itself: `credentials.provider()` returns a
callable an adapter calls lazily, by worker id, the first time it actually
needs one. `--credential-dir` is an override only, for tests and
already-materialized directories — the default is lazy materialization,
and no target configuration file is ever consulted for a credential path.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Callable


def _load_sibling(module_name: str, filename: str):
    """Path-import a sibling module from this same directory, reusing an
    already-loaded copy under `module_name` when one exists.

    Same technique and same correctness reason as `packer.py`'s own
    `_load_sibling`: this skill's scripts are not a package, so a
    cross-module dependency goes by file path, and checking `sys.modules`
    first is what keeps `isinstance` checks against `ADAPTER.Adapter`
    working when this module and `packer.py` both load `adapter.py` — a
    second, separately exec'd copy would define a second, distinct
    `Adapter` class with the same name.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]
    script = Path(__file__).resolve().parent / filename
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


LEDGER = _load_sibling("remote_execution_ledger", "ledger.py")
ADAPTER = _load_sibling("remote_execution_adapter", "adapter.py")
PACKER = _load_sibling("remote_execution_packer", "packer.py")

# Loaded AFTER adapter.py above, for the same sys.modules-reuse reason
# documented next to PACKER's own load above: `credentials.py`'s own
# `ADAPTER.CredentialHandle` has to be the exact same class every other
# module in this chain already loaded, not a second, separately exec'd
# copy of the same name.
CREDENTIALS = _load_sibling("remote_execution_credentials", "credentials.py")


def _load_source_digest() -> Callable[[Path, str], str]:
    """Path-import `source_digest()` from proposal-implementation's digest kit.

    A `submitted` event's `sourceDigest` has to be the SAME hash
    proposal-implementation's own admissibility and verify machinery already
    treats as canonical for a given source tree — a second, independently
    written hash here would be safe only until the day the two quietly
    drifted apart, at which point every submission this CLI records would
    carry a digest nothing else in the repository recognizes as current.

    `assets/kit/nb/report_digest.py` is the file this reaches for, not
    `implementation_cli.py`: it is the lightweight, stdlib-only half of the
    pair proposal-implementation's own test suite already holds to
    byte-for-byte parity with the CLI's copy (`ReportDigestJoinTests` in
    `tests/test_proposal_implementation.py`), and loading it costs nothing
    but `hashlib` and `pathlib` — not the whole argparse-driven
    proposal-implementation CLI, which this module never touches. This IS a
    dependency reaching outside this skill's own
    `remote_cli -> packer -> ledger -> adapter` chain, and this function is
    the one place in the whole skill that reaches for it — `fold()`'s own
    docstring (`ledger.py`) already anticipates exactly this: it says the
    real `source_digest()` "lives in proposal-implementation's own module"
    and must be supplied by a caller that already knows how to compute one.
    This function is that caller, called only when `submit` actually needs
    a digest, never at import time.
    """
    module_name = "remote_execution_source_digest_kit"
    if module_name in sys.modules:
        return sys.modules[module_name].source_digest
    script = (
        Path(__file__).resolve().parents[2]
        / "proposal-implementation"
        / "assets"
        / "kit"
        / "nb"
        / "report_digest.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise RemoteCLIError(
            f"the source-digest kit is not where this expects it: {script}. "
            "If it moved, this loader is the one place that has to follow it."
        )
    module = importlib.util.module_from_spec(spec)
    # Registered only once it has actually run. Publishing the module before
    # executing it is the usual shape, and it is wrong here: a failed exec
    # would leave an empty module under this name, and every later call would
    # take the cache branch above and raise AttributeError on a module that
    # never loaded — reporting a missing attribute instead of the real fault,
    # for the rest of the process. Registering after means a failure is
    # retryable and always reports itself.
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module.source_digest


class RemoteCLIError(Exception):
    """Something this CLI's own validation refused before doing any work."""


class PathGuardError(RemoteCLIError):
    """An entrypoint failed this forge's own file-kind policy for what may run remotely."""


NOTEBOOKS_DIRNAME = "Notebooks"
NOTEBOOK_SUFFIX = ".ipynb"
LEDGER_DIRNAME = ".remote-execution"
LEDGER_FILENAME = "ledger.jsonl"
QUARANTINE_DIRNAME = "quarantine"
PARTIAL_SUFFIX = ".partial"


def name_for(target: Path, entrypoint: str | Path) -> str:
    """Derive `<Name>` from a path known to live under `target` — the same
    structural technique `guard_entrypoint()` uses for a submitted
    notebook (resolve first, then read the first path component past
    `target`), factored out so `fetch`'s quarantine path and `reconcile`'s
    ledger selection call the SAME derivation rather than each growing its
    own copy that could quietly disagree with `submit`'s about which
    product a given path belongs to.

    This forge's real target hosts two products (`CREDA`, `MIL-CREDA`);
    nothing in this skill is allowed to assume which one a caller means —
    `<Name>` is always read off a path, never typed in as a bare string.
    """
    resolved = Path(entrypoint).resolve()
    try:
        relative = resolved.relative_to(target)
    except ValueError:
        raise RemoteCLIError(
            f"cannot derive <Name>: {resolved} does not stay under target "
            f"{target} at all"
        ) from None
    if not relative.parts:
        raise RemoteCLIError(
            f"cannot derive <Name>: {resolved} equals target {target} itself"
        )
    return relative.parts[0]


def guard_entrypoint(target: Path, entrypoint: Path) -> Path:
    """Refuse anything that is not a notebook living under this product's
    `Notebooks/` tree.

    THIS function is the single place in the entire remote-execution skill
    that holds an opinion about what KIND of file may run remotely.
    Everything below it is deliberately blind to that question:
    `adapter.Job.entrypoint` is typed as a bare path with no extension or
    directory-containment check (see `adapter.py`'s own docstring on that
    field), the ledger's `submitted`/`returned`/`errored` events store
    `entrypoint` as an opaque string, and the fold indexes by that same
    string without ever asking what it points to. That narrowing is
    deliberate, not an oversight left for later: a future workload that is
    a plain script, not a notebook, becomes admissible by widening the two
    checks below — and ONLY the two checks below. Nowhere else in this
    skill needs to change: not `Job`, not the ledger's event schema, not
    the fold's indices, not any downstream consumer that reads `entrypoint`
    today. Reworking all of those for a second file kind is exactly the
    refactor this one guard exists to make unnecessary.

    This forge's own layout rule, not a universal one, and not something a
    second deployment of this skill against a differently-shaped repository
    should assume holds:
    - the entrypoint's resolved path must stay under
      `<target>/<Name>/Notebooks/`, for whatever `<Name>` it resolves under
      — this function does not know or care which one
    - the resolved path must end `.ipynb`
    - anything else is refused, with a message naming both the path that
      was refused and which of the two rules it failed

    `Path.resolve()` runs FIRST, and both checks below run only against the
    RESOLVED path — never the literal argument this function received.
    This order is load-bearing, not cosmetic: a symlink sitting inside
    `<Name>/Notebooks/` can point anywhere else on disk, and a check made
    against the literal path would see only the symlink's own in-bounds
    location, never where it actually leads. Checking containment before
    resolving is the exact hole a documentation-like escape (this skill's
    own threat matrix) would walk straight through; resolving first and
    checking the resolved target is what closes it.
    """
    resolved = Path(entrypoint).resolve()

    try:
        relative = resolved.relative_to(target)
    except ValueError:
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not stay "
            f"under target {target} at all"
        ) from None

    parts = relative.parts
    if len(parts) < 3 or parts[1] != NOTEBOOKS_DIRNAME:
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not stay "
            f"under <target>/<Name>/{NOTEBOOKS_DIRNAME}/"
        )

    if resolved.suffix != NOTEBOOK_SUFFIX:
        raise PathGuardError(
            f"refusing {entrypoint}: resolved path {resolved} does not end "
            f"in {NOTEBOOK_SUFFIX}"
        )

    return resolved


def cmd_submit(
    *,
    target: str | Path,
    entrypoint: str | Path,
    worker: str,
    requested: int,
    adapter: "ADAPTER.Adapter",
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """Guard, plan, submit, and record — the whole submit path, in this order.

    `target` is resolved to an absolute path as the very first thing this
    function does, before any other check and before any filesystem write —
    every data path this call touches (the guard's containment check, the
    ledger's location) is derived from that resolved value and never from
    the raw argument. A relative `--target` therefore never gets a chance to
    be interpreted against the wrong working directory later in the call,
    because by the time anything else runs, there is no relative path left
    to misinterpret.

    Order past that point is fixed by design, not incidental:
    `guard_entrypoint()` runs first because nothing after it — not the
    digest, not the plan, not the adapter call — should ever run against a
    path this forge's layout rule refuses. `source_digest()` is called
    FRESH here, at submit time, and its result is never reused from a
    notebook's own post-hoc marker or from any earlier call in this
    process — that freshness is the one thing that later lets the ledger's
    fold tell a current result from a stale one (see `ledger.py`'s
    `currency_verdict`). `packer.plan()` runs before `adapter.submit()` so
    a submission is never attempted with no capacity clamp computed behind
    it. `ledger.append()` runs LAST, only after the adapter has already
    returned a real submission id — appending before that would risk
    recording a submission that was never actually made.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    resolved_entrypoint = guard_entrypoint(target, Path(entrypoint))
    name = resolved_entrypoint.relative_to(target).parts[0]
    relative_entrypoint = resolved_entrypoint.relative_to(target / name)

    digest_fn = source_digest or _load_source_digest()
    digest = digest_fn(target, name)

    ledger_path = target / name / LEDGER_DIRNAME / LEDGER_FILENAME
    ledger_lines: list[str] = []
    if ledger_path.exists():
        ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()

    plan = PACKER.plan(
        adapter=adapter,
        worker_id=worker,
        requested=requested,
        ledger_lines=ledger_lines,
        live_digest=digest,
    )

    job = ADAPTER.Job(entrypoint=resolved_entrypoint, inputs=(), worker=worker)
    submission = adapter.submit(job)

    event = LEDGER.submitted_event(
        entrypoint=str(relative_entrypoint),
        source_digest=digest,
        submission_id=submission.id,
        worker=worker,
        requested_capacity=requested,
        granted_capacity=plan.granted,
    )
    LEDGER.append(ledger_path, event)

    return {
        "plan": plan,
        "submission": submission,
        "event": event,
        "ledgerPath": ledger_path,
    }


def cmd_status(
    *,
    target: str | Path,
    entrypoint: str | Path,
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """The fold, rendered for a human: per-entrypoint state, what is
    pending, what is `staleInFlight`, what is quarantined, and how many
    lines could not be read at all.

    This function accepts no `adapter` parameter at all — not merely
    "does not call one" but structurally cannot, since none is in scope to
    call. `status` reports what the ledger already says; it never resolves
    anything, and the signature itself is what makes that true rather than
    a rule this function's body would otherwise have to be trusted to
    follow.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    name = name_for(target, entrypoint)
    ledger_path = target / name / LEDGER_DIRNAME / LEDGER_FILENAME
    ledger_lines: list[str] = []
    if ledger_path.exists():
        ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()

    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, name)
    state = LEDGER.fold(ledger_lines, live_digest=live)

    return {
        "ledgerPath": ledger_path,
        "entrypoints": {
            entry_name: {
                "state": entry.state,
                "staleInFlight": entry.stale_in_flight,
            }
            for entry_name, entry in state.entrypoints.items()
        },
        "staleInFlight": state.stale_in_flight,
        "quarantined": state.from_stale_submission,
        "unreadableLines": state.unreadable_lines,
    }


def cmd_poll(*, submission_id: str, adapter: "ADAPTER.Adapter") -> "ADAPTER.Status":
    """Ask the adapter for one submission's status, in the seam's own
    five-value vocabulary — never the backend's raw text.

    `ADAPTER.Status.__post_init__` already refuses an out-of-vocabulary
    `state` for a genuine `Status` built the ordinary way, but that
    validation runs only at construction time, inside the adapter, and this
    function has no way to confirm every adapter actually goes through it —
    a misbehaving adapter could hand back any object carrying a `.state`
    attribute the ordinary constructor never touched. The check below is
    this seam's OWN refusal, made again at the one place a bad value would
    otherwise reach a caller: a state outside `ADAPTER.STATES` is the
    adapter's fault, and it is refused here, not translated, not guessed
    at, and never passed through.
    """
    status = adapter.poll(submission_id)
    state = getattr(status, "state", None)
    if state not in ADAPTER.STATES:
        raise RemoteCLIError(
            f"adapter.poll() returned state {state!r}, outside this seam's "
            f"own vocabulary {ADAPTER.STATES}; that is the adapter's fault, "
            "not something this CLI passes through"
        )
    return status


def cmd_fetch(
    *,
    target: str | Path,
    entrypoint: str | Path,
    submission_id: str,
    dest: str | Path,
    adapter: "ADAPTER.Adapter",
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """Materialize one submission's result, quarantining it structurally
    when it is not judged current — never discarding it, and never merging
    it either.

    Ordering is fixed, and every step past the first exists to protect the
    one fact that matters most: a `returned` event must never be recorded
    unless the artifact it names is actually, completely, on disk.

    1. `LEDGER.currency_verdict()` — the SAME rule `fold()` itself uses for
       an already-recorded `returned` event — is evaluated here BEFORE one
       exists, against the ledger state read at the top of this call. A
       `current` verdict uses the caller's own `dest`; anything else
       (`fromStaleSubmission`) overrides `dest` entirely and reroutes to
       `<target>/<Name>/.remote-execution/quarantine/<submissionId>/` — a
       location structurally outside `Results/shards/`, the only tree a
       shard reader ever enumerates. This is a placement decision made
       once, not a filter a merge step could forget to apply later: the
       artifact is never even offered a path a merge could reach.
    2. `observed_concurrency` is read from the SAME pre-fetch ledger state,
       via `LedgerState.pending_for()` — the count of this worker's pending
       submissions at the instant just before this one is about to be
       recorded as done, including itself. A grant the packer allowed for
       N concurrent jobs, honored by the service for fewer than N, shows up
       here as a smaller number than N — visible, not assumed.
    3. `adapter.fetch()` is handed `<dest-or-quarantine>.partial/`, never
       the final path directly. This is the ONE call in this whole function
       that can fail partway through after having already written SOME
       bytes to disk — a network drop, a killed process, a raised
       exception from inside the adapter itself. Nothing before this line
       has touched the filesystem at all, and nothing after it runs unless
       this call returns normally.
    4. `Fetched.complete` is checked before anything else happens. `False`
       means the backend itself considers the result unfinished — this
       function returns without renaming and without appending anything,
       leaving the ledger's own state exactly as `pending` as it already
       was, which is what makes a retry safe. Only `complete=True` reaches
       the rename.
    5. `os.replace()` — an atomic rename on the same filesystem — moves the
       `.partial/` directory into its final name. This is the one line
       that turns "an artifact happens to exist on disk" into "the
       artifact is at the path this call promises callers", and it runs
       before the ledger is touched.
    6. `LEDGER.append()` runs LAST, only after the rename above has
       already succeeded. If the process is killed at any point before
       this line, the submission reads back as `pending` on the next fold
       — retryable, never a false `returned` — because nothing before this
       line ever wrote to the ledger.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    name = name_for(target, entrypoint)
    ledger_path = target / name / LEDGER_DIRNAME / LEDGER_FILENAME
    ledger_lines: list[str] = []
    if ledger_path.exists():
        ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()

    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, name)
    state = LEDGER.fold(ledger_lines, live_digest=live)

    submission = state.by_id.get(submission_id)
    if submission is None:
        raise RemoteCLIError(
            f"no submitted event on record for submission {submission_id!r}"
        )

    verdict = LEDGER.currency_verdict(submission, state.latest, live)
    if verdict == "current":
        final_dest = Path(dest).resolve()
    else:
        final_dest = target / name / LEDGER_DIRNAME / QUARANTINE_DIRNAME / submission_id

    observed_concurrency = state.pending_for(submission["worker"])

    partial_dest = final_dest.with_name(final_dest.name + PARTIAL_SUFFIX)
    fetched = adapter.fetch(submission_id, partial_dest)

    if not fetched.complete:
        # Not renamed, not recorded: the ledger's own state stays exactly
        # `pending`, which is the one state a retry can safely start from.
        return {
            "verdict": verdict,
            "complete": False,
            "path": partial_dest,
            "event": None,
        }

    final_dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(str(partial_dest), str(final_dest))

    event = LEDGER.returned_event(
        submission_id=submission_id,
        artifact_path=str(final_dest),
        observed_concurrency=observed_concurrency,
    )
    LEDGER.append(ledger_path, event)

    return {
        "verdict": verdict,
        "complete": True,
        "path": final_dest,
        "event": event,
    }


def cmd_reconcile(
    *,
    target: str | Path,
    entrypoint: str | Path,
    worker: str,
    adapter: "ADAPTER.Adapter",
    resolve: bool = False,
    source_digest: Callable[[Path, str], str] | None = None,
) -> dict:
    """Compare the ledger's pending submissions for `worker` against what
    `adapter.list_active(worker)` reports right now, in both directions,
    and report the difference. Never resolves either side on its own
    initiative.

    An id `list_active()` reports that this ledger has no `submitted` event
    for at all is `orphanRemote`. It is reported ONLY — never cancelled
    (this function never calls `adapter.cancel()`, the same restraint
    `fold()`'s own `staleInFlight` handling already applies to a source
    that moved out from under a pending submission) and NEVER auto-adopted
    by fabricating a `submitted` line for it. Adoption would have to invent
    a `sourceDigest` this function has no way to know, and `sourceDigest`
    is the entire basis the fold's currency rule later judges a result by
    — a fabricated one would turn every future currency verdict for that id
    into a guess wearing the shape of a fact. Reporting the orphan and
    leaving the ledger untouched is the guarantee-preserving choice;
    adoption is the guarantee-destroying one.

    A `pending` submission the ledger still expects that `list_active()` no
    longer lists is `orphanLocal`. It is always reported, regardless of
    `resolve`. Only when `resolve=True` — reserved for a human explicitly
    passing `--resolve`, never set by any automated caller in this skill —
    does this function append one `errored` event per orphan, with
    `reason="not-found-at-service"`, through the exact same
    `LEDGER.append()` path every other terminal event goes through.
    `resolve=False`, the default, appends nothing at all: an orphan-remote
    id is reported without a single ledger write, on every call.
    """
    target = Path(target).resolve()
    if not target.is_dir():
        raise RemoteCLIError(
            f"--target {target} does not resolve to an existing directory"
        )

    name = name_for(target, entrypoint)
    ledger_path = target / name / LEDGER_DIRNAME / LEDGER_FILENAME
    ledger_lines: list[str] = []
    if ledger_path.exists():
        ledger_lines = ledger_path.read_text(encoding="utf-8").splitlines()

    digest_fn = source_digest or _load_source_digest()
    live = digest_fn(target, name)
    state = LEDGER.fold(ledger_lines, live_digest=live)

    remote_active = set(adapter.list_active(worker))
    local_pending = {
        submission["submissionId"]
        for submission in state.latest.values()
        if submission.get("worker") == worker
        and state.entrypoints[submission["entrypoint"]].state == "pending"
    }

    orphan_remote = tuple(sorted(remote_active - local_pending))
    orphan_local = tuple(sorted(local_pending - remote_active))

    resolved_events: list[dict] = []
    if resolve:
        for submission_id in orphan_local:
            event = LEDGER.errored_event(
                submission_id=submission_id, reason="not-found-at-service"
            )
            LEDGER.append(ledger_path, event)
            resolved_events.append(event)

    return {
        "orphanRemote": orphan_remote,
        "orphanLocal": orphan_local,
        "resolved": tuple(resolved_events),
    }


def _construct_adapter(
    adapter_cls: type["ADAPTER.Adapter"],
    credentials_provider: Callable[[str], "ADAPTER.CredentialHandle"],
) -> "ADAPTER.Adapter":
    """Construct a registered adapter, handing it a credential provider only
    when its own constructor is written to accept one.

    The `Adapter` ABC constrains exactly six operations and nothing about
    `__init__` — a second adapter genuinely may take no arguments at all
    (this skill's own test doubles do exactly that), and that has to keep
    working, unmodified, for the seam's own "zero ledger/packer changes"
    guarantee to mean anything at the CLI's own construction site too.
    Introspecting the signature here, rather than trying `credentials=` and
    falling back on a bare `TypeError`, is what keeps a GENUINE defect
    inside a compliant adapter's own `__init__` from being swallowed as
    "this adapter must not want credentials".
    """
    try:
        parameters = inspect.signature(adapter_cls).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_credentials = "credentials" in parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )
    if accepts_credentials:
        return adapter_cls(credentials=credentials_provider)
    return adapter_cls()


def _accounts_cli_for(adapter_cls: type["ADAPTER.Adapter"]) -> Path | None:
    """Read a resolved backend's own credential-materializing CLI location
    off its class, without this module ever naming which backend that is.

    `credentials.py` is the only producer of a `CredentialHandle`, but it
    holds no opinion about WHERE a given backend's own materialize command
    lives — that knowledge is confined to the one file per backend allowed
    to name a service at all, one level below this seam, through that
    module's own `CREDENTIAL_CLI` class attribute. `CREDENTIAL_CLI` is an
    ordinary class attribute, not one of the `Adapter` ABC's six
    operations, so an adapter that never declares one (this skill's own
    test doubles included) is read as `None` here — `credentials.provider()`
    only refuses if it is actually asked to materialize with neither this
    nor `--credential-dir` supplied.
    """
    return getattr(adapter_cls, "CREDENTIAL_CLI", None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remote_cli",
        description="Forge-owned remote execution CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit = subparsers.add_parser(
        "submit", help="submit one notebook to a registered backend's worker"
    )
    submit.add_argument("--target", required=True, type=Path)
    submit.add_argument("--entrypoint", required=True, type=Path)
    submit.add_argument("--worker", required=True)
    submit.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    submit.add_argument("--requested", type=int, default=1)
    submit.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )

    status = subparsers.add_parser(
        "status", help="report the fold for one product's ledger; resolves nothing"
    )
    status.add_argument("--target", required=True, type=Path)
    status.add_argument("--entrypoint", required=True, type=Path)

    poll = subparsers.add_parser(
        "poll", help="ask the adapter for one submission's status"
    )
    poll.add_argument("--submission-id", required=True)
    poll.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    poll.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )

    fetch = subparsers.add_parser(
        "fetch",
        help="materialize one submission's result, quarantining it when it is not current",
    )
    fetch.add_argument("--target", required=True, type=Path)
    fetch.add_argument("--entrypoint", required=True, type=Path)
    fetch.add_argument("--submission-id", required=True)
    fetch.add_argument("--dest", required=True, type=Path)
    fetch.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    fetch.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )

    reconcile = subparsers.add_parser(
        "reconcile",
        help="compare the ledger against the adapter's list_active() in both directions",
    )
    reconcile.add_argument("--target", required=True, type=Path)
    reconcile.add_argument("--entrypoint", required=True, type=Path)
    reconcile.add_argument("--worker", required=True)
    reconcile.add_argument(
        "--backend",
        required=True,
        help="the name a concrete adapter was registered under via adapter.register()",
    )
    reconcile.add_argument(
        "--resolve",
        action="store_true",
        help="human-invoked only: append errored(reason=not-found-at-service) for each orphanLocal id",
    )
    reconcile.add_argument(
        "--credential-dir", type=Path, default=None,
        help="override: use this directory instead of lazily materializing one by worker id",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "submit":
        try:
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_submit(
                target=args.target,
                entrypoint=args.entrypoint,
                worker=args.worker,
                requested=args.requested,
                adapter=_construct_adapter(adapter_cls, provider),
            )
        except (RemoteCLIError, PACKER.PackerError, LEDGER.LedgerError,
                ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(
            json.dumps(
                {
                    "submissionId": result["submission"].id,
                    "worker": result["submission"].worker,
                    "granted": result["plan"].granted,
                    "ledgerPath": str(result["ledgerPath"]),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "status":
        try:
            result = cmd_status(target=args.target, entrypoint=args.entrypoint)
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(json.dumps({**result, "ledgerPath": str(result["ledgerPath"])}, sort_keys=True))
        return 0

    if args.command == "poll":
        try:
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            status_result = cmd_poll(
                submission_id=args.submission_id, adapter=_construct_adapter(adapter_cls, provider)
            )
        except (RemoteCLIError, ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(
            json.dumps(
                {"state": status_result.state, "detail": status_result.detail},
                sort_keys=True,
            )
        )
        return 0

    if args.command == "fetch":
        try:
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_fetch(
                target=args.target,
                entrypoint=args.entrypoint,
                submission_id=args.submission_id,
                dest=args.dest,
                adapter=_construct_adapter(adapter_cls, provider),
            )
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(
            json.dumps(
                {
                    "verdict": result["verdict"],
                    "complete": result["complete"],
                    "path": str(result["path"]),
                    "event": result["event"],
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "reconcile":
        try:
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        provider = CREDENTIALS.provider(
            accounts_cli=_accounts_cli_for(adapter_cls), override=args.credential_dir
        )
        try:
            result = cmd_reconcile(
                target=args.target,
                entrypoint=args.entrypoint,
                worker=args.worker,
                adapter=_construct_adapter(adapter_cls, provider),
                resolve=args.resolve,
            )
        except (RemoteCLIError, LEDGER.LedgerError, ADAPTER.AdapterError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(json.dumps(result, sort_keys=True))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
