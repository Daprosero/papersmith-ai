#!/usr/bin/env python3
"""The remote-execution adapter seam.

This module defines the ABC every backend-specific adapter must satisfy in
full, the frozen data shapes that cross the seam in either direction, and a
small name-to-class registry so a caller can select a backend by a string
without importing it directly.

Nothing here knows what any backend is called or how it talks over the
network. That knowledge is confined to exactly one file per backend, living
below this seam. This module is the boundary that makes swapping one such
file for another a no-op for everything above it: the ledger, the packer,
and the CLI depend on this interface only, never on a concrete adapter class.

A second backend, if one is ever added, would expose exactly four places
this seam could otherwise leak its details through. Each shape below states,
next to the field it concerns, the rule that keeps it from doing so:

- `Submission.id` — opaque outside the adapter that issued it.
- `Status.state` — the seam's own vocabulary, never a backend's raw text.
- `Job.inputs` — opaque strings the adapter interprets; the packer never
  resolves them.
- `Worker.capacity` — concurrent jobs per worker, not a backend's own
  metering unit.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Worker:
    """One execution slot a backend exposes, and the cap it states for it.

    `capacity` means concurrent jobs this worker may run at once — never a
    quota, a byte budget, or a time budget. A backend that meters capacity
    some other way converts that into "how many jobs at once" inside its own
    adapter; this shape carries only the converted number, never the
    backend's own unit.
    """

    id: str
    capacity: int


@dataclass(frozen=True)
class Job:
    """One unit of work handed to `Adapter.submit()`.

    `entrypoint` is a path and nothing more. This dataclass carries no
    opinion about what kind of file it points to — no extension check, no
    directory-containment rule. That is deliberate: this repository's rule
    that a submitted entrypoint must end `.ipynb` and live under
    `<Name>/Notebooks/` is real and stays enforced, but it is *the
    submitting CLI's path guard's* policy, held in exactly one place. A
    future workload that is not a notebook becomes admissible by widening
    that one guard — not by reworking this dataclass, the ledger's event
    schema, the fold's indices, or any other consumer that would otherwise
    need to change alongside a field rename.

    `inputs` are opaque strings this dataclass does not interpret. What one
    backend's adapter expects there (a dataset identifier, say) and what
    another expects (a local path, say) is that adapter's business alone;
    nothing above this seam — the packer included — ever resolves or
    inspects an input string itself.
    """

    entrypoint: Path
    inputs: tuple[str, ...]
    worker: str


@dataclass(frozen=True)
class Submission:
    """A backend's receipt for one `submit()` call.

    `id` is OPAQUE to everything above this seam. The ledger and the packer
    are permitted exactly two operations on it: equality, and use as a dict
    key. Neither is permitted to split it, parse it, or pattern-match any
    part of it — an id's internal shape is a fact about the backend that
    issued it, and code that came to depend on that shape would break the
    moment a second backend issued ids shaped differently.
    """

    id: str
    worker: str


# The seam's own five-value vocabulary for `Status.state` — not any
# backend's. A backend's raw status text (a queue position, an internal
# code) never belongs here; it goes in `Status.detail` instead. Translating
# a backend's own vocabulary into this one is the adapter's job, every time.
STATES = ("queued", "running", "complete", "failed", "unknown")


@dataclass(frozen=True)
class Status:
    """A poll result, expressed in the seam's vocabulary, never the backend's.

    `state` is validated against `STATES` at construction — enforced, not
    merely documented, for the same reason the ABC below refuses an
    incomplete subclass rather than trusting a comment to be read. `detail`
    is where a backend's own raw status text belongs; anything that would
    tempt a caller to start pattern-matching backend-specific strings out of
    `state` itself goes there instead.
    """

    state: str
    detail: str

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(
                f"{self.state!r} is not one of this seam's states {STATES}; "
                "a backend's own status text belongs in `detail`, not here"
            )


@dataclass(frozen=True)
class Fetched:
    """The result of one `fetch()` call."""

    path: Path
    complete: bool
    files: tuple[str, ...]


class AdapterError(Exception):
    """A backend refused, timed out, or answered with something unusable.

    The seam's own error type, and the fifth thing that crosses this boundary
    besides the four data shapes above. Every concrete adapter raises a
    subclass of this and nothing else.

    Without it the seam has a hole exactly where it is supposed to be sealed.
    A caller has to catch a backend's failures somehow, and if the only type
    available is the concrete adapter's own, then catching it means importing
    it — so the CLI would have to name every backend it might be run against,
    which is the one thing this whole file exists to prevent. The alternative,
    catching bare `Exception`, is worse: it swallows the genuine defects a
    traceback is for.

    So the failure this closes is not a crash but a leak: a common base is
    what lets code above the seam handle a backend it has never heard of.
    """


class Adapter(ABC):
    """The seam every backend-specific adapter must satisfy in full.

    Ledger and packer code depends on this interface only — never on a
    concrete adapter class. Leaving even one of the six operations
    unimplemented in a subclass must make that subclass itself
    uninstantiable; that is what `ABC` and `@abstractmethod` are doing here,
    together, and it is a structural guarantee, not a convention a future
    subclass could quietly ignore.
    """

    @abstractmethod
    def workers(self) -> list[Worker]:
        """Report the workers this backend currently exposes, and each cap."""

    @abstractmethod
    def submit(self, job: Job) -> Submission:
        """Hand one job to the backend, returning its opaque submission receipt."""

    @abstractmethod
    def poll(self, submission_id: str) -> Status:
        """Report a submission's state, translated into the seam's vocabulary."""

    @abstractmethod
    def fetch(self, submission_id: str, into: Path) -> Fetched:
        """Materialize a submission's result under `into`, complete or not."""

    @abstractmethod
    def cancel(self, submission_id: str) -> None:
        """Ask the backend to stop a submission. Never called by this seam itself."""

    @abstractmethod
    def list_active(self, worker: str) -> list[str]:
        """Report the submission ids the backend still considers active for `worker`."""


_REGISTRY: dict[str, type[Adapter]] = {}


def register(name: str, adapter_cls: type[Adapter]) -> None:
    """Register a concrete adapter class under a name a caller can select by.

    This is the one place a backend-specific module and this seam-only
    module meet, and the meeting happens by the backend module calling IN to
    this function — this module never imports OUT to any backend module.
    That direction is what keeps this file free of any backend's name, no
    matter how many backends the registry eventually holds.
    """
    if not (isinstance(adapter_cls, type) and issubclass(adapter_cls, Adapter)):
        raise TypeError(f"{adapter_cls!r} does not subclass Adapter")
    _REGISTRY[name] = adapter_cls


def resolve(name: str) -> type[Adapter]:
    """Look up a previously registered adapter class by name."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"no adapter registered under {name!r}") from None
