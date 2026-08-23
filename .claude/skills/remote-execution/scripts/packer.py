#!/usr/bin/env python3
"""The capacity clamp: what a repository asks for, clamped to what a worker allows.

The settled rule this module exists to enforce, and enforce in exactly one
place: the adapter states the cap, the repository states the request, and
this module — never either of those two — does the clamping. Neither side
is trusted to know the other's fact. How many jobs a worker will run at
once is a fact about the service, so it is read here only through
`adapter.workers()`, never accepted as a parameter from a caller and never
hardcoded. How many the repository WANTS to use of that is the repository's
own declared intent, handed in as `requested` by whoever calls `plan()` —
this module never guesses it and never defaults it.

`plan()` reports `requested`, `cap`, `inFlight` and `granted` as four
separate numbers on purpose. A clamp collapsed down to `granted` alone is
indistinguishable from an unclamped grant that merely happens to equal the
same number — a caller asking for five and receiving two because the
service caps at two looks identical, from `granted` alone, to a caller
asking for exactly two and receiving it. Those are different facts to know
before spending an afternoon waiting on a service, and this module keeps
them different by never collapsing them into one number in the first place.

Depends only on `adapter.py`'s ABC (`plan()` requires a real `Adapter`
instance, checked structurally, not merely documented) and `ledger.py`'s
`fold()` (to learn what is already in flight before granting more). Names
no backend and holds no service-specific knowledge; nothing below this
module's own two dependencies is ever imported.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


def _load_sibling(module_name: str, filename: str):
    """Path-import a sibling module from this same directory, reusing an
    already-loaded copy under `module_name` when one exists.

    This skill's scripts are not a package — there is no `__init__.py`, on
    purpose, so the skill stays runnable with a bare `python3` and no
    install step — so a cross-module dependency inside it goes by file
    path, the same technique `tests/test_remote_execution.py` already uses
    for every module in this skill.

    The reuse check is not an optimization; it is a correctness requirement.
    `ledger.py`'s `LedgerState` and `adapter.py`'s `Worker`/`Adapter` are
    dataclasses and an ABC. Two separately exec'd copies of the same source
    file produce two DISTINCT class objects with the same name — an
    `isinstance` check made against one copy would silently fail against an
    instance built by the other, even though the source is byte-identical.
    Checking `sys.modules` first, and only loading fresh when nothing is
    there yet, is what keeps this module and whatever already loaded its
    dependencies talking about the same classes.
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


class PackerError(Exception):
    """A plan could not be computed from what the adapter and ledger state."""


@dataclass(frozen=True)
class Plan:
    """One capacity decision for one worker, with the clamp kept visible.

    Every field here is a distinct fact; none is derivable from another
    without also knowing at least one more:

    - `requested` — what the repository's own config declared it wants.
    - `cap` — what `adapter.workers()` states this worker allows, read
      fresh at plan time, never cached across calls and never hardcoded.
    - `in_flight` — how much of that cap is already committed, per
      `in_flight_source` below.
    - `granted` — `max(0, min(requested, cap) - in_flight)`. Never negative:
      a worker already at or over its cap grants zero, not a negative
      number that would otherwise have to be clamped again downstream.
    - `in_flight_source` — `"list_active"` when the adapter answered and
      that live count was used, `"ledger"` when it did not (or raised) and
      the ledger's own fold supplied the count instead. This is what keeps
      a live-refined `in_flight` from being reported with the same
      confidence as a fallback estimate that merely carries the same value.
    """

    worker: str
    requested: int
    cap: int
    in_flight: int
    granted: int
    in_flight_source: str


def plan(
    *,
    adapter: "ADAPTER.Adapter",
    worker_id: str,
    requested: int,
    ledger_lines: Iterable[str],
    live_digest: str | Callable[[], str],
) -> Plan:
    """Clamp `requested` concurrent jobs on `worker_id` to what the adapter
    and the ledger together say is actually available right now.

    `adapter` must be a real `Adapter` instance — checked structurally here,
    the same discipline `adapter.py`'s own ABC uses to refuse an incomplete
    subclass, rather than trusting a caller to have passed the right shape
    of object. `cap` is discovered through `adapter.workers()` and no other
    route: this module accepts no `cap` or `capacity` parameter from its
    caller, because the cap is not this module's fact, or the caller's, to
    assert — it is the adapter's alone.

    `in_flight` starts as `fold(ledger_lines, live_digest).pending_for(worker_id)`
    — every entrypoint whose latest submission to this worker has neither
    returned nor errored yet. `adapter.list_active(worker_id)` then refines
    that count when the adapter answers, because the ledger only ever
    reflects what THIS repository last recorded submitting, while
    `list_active()` reflects what the service itself currently considers
    active. When `list_active()` raises — the service unreachable, refusing,
    or timing out — this function falls back to the ledger-derived count
    rather than propagating the failure, but it says so through
    `Plan.in_flight_source` rather than reporting a bare number with no
    indication of where it came from.
    """
    if not isinstance(adapter, ADAPTER.Adapter):
        raise PackerError(
            f"{adapter!r} is not an Adapter instance; capacity is discovered "
            "through the adapter seam only, never accepted some other way"
        )

    workers_by_id = {worker.id: worker for worker in adapter.workers()}
    if worker_id not in workers_by_id:
        raise PackerError(f"adapter reports no worker named {worker_id!r}")
    cap = workers_by_id[worker_id].capacity

    state = LEDGER.fold(ledger_lines, live_digest)
    in_flight = state.pending_for(worker_id)
    in_flight_source = "ledger"

    try:
        in_flight = len(adapter.list_active(worker_id))
        in_flight_source = "list_active"
    except ADAPTER.WorkerUnauthorized:
        # NOT swallowed: a revoked or otherwise unauthorized credential is
        # a decision-bearing fact, never a mere "service unreachable" one.
        # Folding it into the ledger fallback below would make a revoked
        # account report exactly like a healthy one whose live count
        # merely could not be confirmed — the one confusion this
        # exception exists to make structurally impossible. Every OTHER
        # exception below still degrades to the ledger, unchanged.
        raise
    except Exception:
        # Unreachable, refusing, or timed out: the ledger-derived count
        # computed above is already in `in_flight` and stays there. This is
        # a refusal to trust a number the service could not actually
        # confirm, not a fabricated "it must still be running" guess.
        pass

    granted = max(0, min(requested, cap) - in_flight)

    return Plan(
        worker=worker_id,
        requested=requested,
        cap=cap,
        in_flight=in_flight,
        granted=granted,
        in_flight_source=in_flight_source,
    )


def select(
    *,
    adapter: "ADAPTER.Adapter",
    requested: int,
    ledger_lines: Iterable[str],
    live_digest: str | Callable[[], str],
) -> Plan:
    """Choose a worker with no caller-supplied name, walking
    `adapter.workers()` in the DECLARED order (the accounts CLI's own
    stable order — this module invents no ordering of its own) and
    returning the first one whose health can be established and that has
    at least one slot to grant.

    A worker counts as HEALTHY for this purpose only when BOTH of these
    hold, distinguished by the exact two fields `plan()` already reports
    rather than by a second, separate health probe this function would
    otherwise have to invent:

    - `plan()` did not raise `ADAPTER.WorkerUnauthorized` — the backend's
      own distinct signal that this worker's credential is refused, never
      swallowed here or in `plan()` itself.
    - `plan().in_flight_source == "list_active"` — the adapter's live
      capacity read genuinely succeeded for this worker. A `plan()` that
      fell back to `"ledger"` answers a real question for a caller who
      already committed to one named worker, but it answers a WEAKER one
      than automatic selection is allowed to accept: `plan()` cannot tell
      "unreachable right now" apart from "revoked" on its own, and
      counting an unconfirmed worker healthy here would let a merely
      slow or flaky service look exactly like a genuinely healthy one —
      the same confusion `WorkerUnauthorized` exists to prevent, on the
      other side of the same fact.

    A healthy worker with `granted < 1` (every slot already spent) is
    skipped too, but for a different, unremarkable reason: it has nothing
    to grant right now, not that it is unwell.

    No worker healthy and grantable is an honest terminal state, never a
    silent pass and never an arbitrary pick: the refusal names every
    worker this call actually tried and the reason each one was skipped,
    plus the remedy — restore at least one account's credential, or wait
    for the service to become reachable, before retrying with no
    `--worker` named at all.
    """
    if not isinstance(adapter, ADAPTER.Adapter):
        raise PackerError(
            f"{adapter!r} is not an Adapter instance; capacity is discovered "
            "through the adapter seam only, never accepted some other way"
        )

    workers = adapter.workers()
    if not workers:
        raise PackerError(
            "adapter reports no workers at all; automatic selection has "
            "nothing to choose among"
        )

    reasons: list[str] = []
    for worker in workers:
        try:
            candidate = plan(
                adapter=adapter,
                worker_id=worker.id,
                requested=requested,
                ledger_lines=ledger_lines,
                live_digest=live_digest,
            )
        except ADAPTER.WorkerUnauthorized as exc:
            reasons.append(f"{worker.id}: unauthorized ({exc})")
            continue

        if candidate.in_flight_source != "list_active":
            reasons.append(
                f"{worker.id}: live capacity evidence unavailable (service "
                "unreachable or refusing) — not counted healthy"
            )
            continue

        if candidate.granted < 1:
            reasons.append(
                f"{worker.id}: no capacity granted right now "
                f"(cap={candidate.cap}, in_flight={candidate.in_flight})"
            )
            continue

        return candidate

    raise PackerError(
        "automatic selection found no healthy worker with capacity among "
        f"{[worker.id for worker in workers]}; restore at least one "
        "account's credential, or wait for the service to become "
        f"reachable, before retrying with no --worker named: {'; '.join(reasons)}"
    )
