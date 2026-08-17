#!/usr/bin/env python3
"""Append-only ledger for forge-owned remote execution.

A submission to a remote worker is a fact once it happens, and facts are not
edited — only added to. This module owns exactly one operation on that
premise: appending one JSON-encoded event to `<target>/<Name>/.remote-execution/
ledger.jsonl`, one line per event, opened `O_APPEND`, never rewritten and
never deleted. Deriving "what is the current state of this entrypoint" from
that log — the fold, and the currency rule that tells a fresh result from a
stale one — is a later module's job; this one only has to make sure that
every fact that goes in survives being written.

Ledger CODE is forge-owned. Ledger DATA lives inside the target's own git
checkout, because it is a per-repository record of what that repository
submitted, not something the forge should hold on anyone's behalf.

Why an append is trustworthy at all rests on four things held together, and
only two of them are this module's job:

- `O_APPEND` on a regular, local file makes seek-to-end-and-write atomic as a
  unit with respect to other appenders, so two concurrent writers cannot
  interleave into the same region. That guarantee is unconditional; it does
  not depend on any buffer-size constant, `PIPE_BUF` included.
- The return value of `os.write()` is checked against the byte count, and a
  mismatch raises. A write CAN legitimately return short, and a short write
  is exactly what tears a JSONL line. This check is the actual defence
  against that, not the append call's mere existence.
- No `io` buffering: `open(path, "a")` may split one logical write across
  syscalls, which would reintroduce the interleaving `O_APPEND` exists to
  prevent. `append()` here always goes through `os.open`/`os.write` on a raw
  fd, one `os.write()` per event.
- Local filesystem only — NFS does not honor `O_APPEND` atomicity. That is a
  precondition stated in `SKILL.md`, not something this module can enforce.

Run with any Python 3.10+ (stdlib-only):
    python3 -m unittest tests.test_remote_execution
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Mapping

# A ledger event has no business being large: the fields are a path, a
# 64-hex digest, an opaque id, a worker name and a timestamp — ~300 B
# observed — plus an errored.reason already truncated below. Exceeding this
# means a field that should have been truncated was not, so raising is the
# correct response.
#
# This is a sanity bound on OUR OWN schema, and deliberately NOT `PIPE_BUF`.
# `PIPE_BUF` governs atomicity of writes to pipes and FIFOs, and says nothing
# about regular files — which is what this ledger is. Its value is also
# platform-specific: 512 on darwin (`os.pathconf('/tmp', 'PC_PIPE_BUF')`),
# 4096 on Linux. Re-deriving this cap from it would be a number borrowed
# from the wrong object, and on this platform, from the wrong operating
# system.
MAX_EVENT_BYTES = 4096

# Unlike every other field in this schema, `errored.reason` has no natural
# size limit at the call site — an exception's full text, a service's raw
# error body. It is truncated here, at construction, so a runaway reason can
# never be what pushes an otherwise routine failure record over the
# line-level cap above.
MAX_REASON_CHARS = 512


class LedgerError(Exception):
    """An append could not be trusted to have landed as a whole event."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def submitted_event(
    *,
    entrypoint: str | Path,
    source_digest: str,
    submission_id: str,
    worker: str,
    requested_capacity: int,
    granted_capacity: int,
    ts: str | None = None,
) -> dict:
    """Build a `submitted` event.

    `entrypoint` — not `notebook` — is the field name for the thing executed
    remotely. The dataclass and adapter seam that will carry this same value
    around (a later task) name it the same way: this schema and that seam
    agree on one vocabulary for "the thing that runs", and neither one
    smuggles in a format opinion about it.
    """
    return {
        "kind": "submitted",
        "ts": ts or _now(),
        "entrypoint": str(entrypoint),
        "sourceDigest": source_digest,
        "submissionId": submission_id,
        "worker": worker,
        "requestedCapacity": requested_capacity,
        "grantedCapacity": granted_capacity,
    }


def returned_event(
    *,
    submission_id: str,
    artifact_path: str | Path,
    observed_concurrency: int,
    ts: str | None = None,
) -> dict:
    """Build a `returned` event."""
    return {
        "kind": "returned",
        "ts": ts or _now(),
        "submissionId": submission_id,
        "artifactPath": str(artifact_path),
        "observedConcurrency": observed_concurrency,
    }


def errored_event(*, submission_id: str, reason: str, ts: str | None = None) -> dict:
    """Build an `errored` event, with `reason` truncated to 512 chars."""
    return {
        "kind": "errored",
        "ts": ts or _now(),
        "submissionId": submission_id,
        "reason": reason[:MAX_REASON_CHARS],
    }


def append(path: str | Path, event: Mapping[str, object]) -> None:
    """Append one event as a single JSON line, or raise without recording it.

    Serialization and the size check both happen before any filesystem call,
    so a rejected event never creates the ledger file or its parent
    directory. Once the write is attempted, a short write is the one failure
    this function cannot undo: the partial bytes it already put on disk stay
    there. The caller must treat the event as unrecorded and must not retry
    blindly onto the same fd — the tail left behind is a corrupted line, and
    handling that is the next fold's job (a later module), not a repair
    attempted here.
    """
    line = json.dumps(event, sort_keys=True) + "\n"
    payload = line.encode("utf-8")

    if len(payload) > MAX_EVENT_BYTES:
        raise LedgerError(
            f"event is {len(payload)} bytes, over the {MAX_EVENT_BYTES}-byte "
            "sanity cap for this schema; a field that should have been "
            "truncated was not"
        )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        written = os.write(fd, payload)
    finally:
        os.close(fd)

    if written != len(payload):
        # A large write CAN legitimately return short, and a short write is
        # exactly what tears a JSONL line. A torn line is a lost submission,
        # which is the one outcome this ledger exists to make impossible, so
        # this fails loudly rather than trusting os.write() to have done the
        # whole job silently.
        raise LedgerError(
            f"short write on append: wrote {written} of {len(payload)} "
            f"bytes to {path}; treat this event as unrecorded"
        )
