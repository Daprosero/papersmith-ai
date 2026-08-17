#!/usr/bin/env python3
"""The CLI front door for forge-owned remote execution: `submit`, for now.

This module is the top of this skill's own dependency chain —
`remote_cli -> packer -> ledger -> adapter` — and it is deliberately the
ONLY module in that chain that names a command-line entry point, parses
`--target`/`--entrypoint`/`--worker` arguments, and decides what counts as
a submittable path in this forge's own repository layout. Everything below
it (`packer.py`, `ledger.py`, `adapter.py`) stays blind to both concerns:
they take paths, ids and dicts as arguments and never ask where an argument
came from or what kind of file it names.

`submit` is the only command implemented here so far. `status`, `poll`,
`fetch` and `reconcile` are later, separate work.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import argparse
import importlib.util
import json
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
    `_currency_verdict`). `packer.plan()` runs before `adapter.submit()` so
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "submit":
        try:
            adapter_cls = ADAPTER.resolve(args.backend)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        try:
            result = cmd_submit(
                target=args.target,
                entrypoint=args.entrypoint,
                worker=args.worker,
                requested=args.requested,
                adapter=adapter_cls(),
            )
        except (RemoteCLIError, PACKER.PackerError, LEDGER.LedgerError) as exc:
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
        except (RemoteCLIError, LEDGER.LedgerError) as exc:
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

        try:
            status_result = cmd_poll(
                submission_id=args.submission_id, adapter=adapter_cls()
            )
        except RemoteCLIError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(
            json.dumps(
                {"state": status_result.state, "detail": status_result.detail},
                sort_keys=True,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
