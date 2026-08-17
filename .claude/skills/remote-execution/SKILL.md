---
name: remote-execution
description: "Trigger: durable record of what a repository has submitted to a remote worker, and what came back. This commit lands only the ledger's append path — the append-only log a submission is recorded into, with the write-integrity checks that make a torn or lost line detectable. Packing, the service adapter, and the submit/status/fetch CLI are not part of this skill yet; they land in later, separate commits. Stdlib-only, no venv."
---

# Remote Execution — Ledger

A submission to a remote worker is a fact once it happens, and this skill's
one job right now is to make sure that fact survives being written. Nothing
here yet talks to a service, packs a request, or exposes a command a user
would invoke directly — this is the durable record those later pieces will
write to and read from.

## Current Scope

Only `scripts/ledger.py` exists so far:

- `append(path, event)` — appends one JSON-encoded event as a single line to
  `<target>/<Name>/.remote-execution/ledger.jsonl`. The file is opened
  `O_APPEND`; a line, once written, is never rewritten or deleted.
- `submitted_event(...)`, `returned_event(...)`, `errored_event(...)` — build
  the three event kinds this ledger records, with the field names and
  truncation rules this schema fixes (see below).

Deriving "what is the current state of this entrypoint" — folding the log
into a verdict, telling a fresh result from a stale one — is not implemented
yet. Reading this ledger back today means reading its raw lines.

## Why append, not a status record

A lost append is detectable — the file is simply shorter than expected, or a
line is malformed. A lost in-place mutation of a "current status" record is
not: the write either lands or it silently doesn't, and there is no earlier
version left to compare against. So this ledger only ever grows. Resubmitting
something appends a new `submitted` line; it never erases the one it
supersedes.

## Why an append can be trusted

Four things, held together, and the first two are enforced in code, not by
convention:

- The return value of `os.write()` is checked against the byte count of the
  event about to be written, and a mismatch raises. A write can legitimately
  return short, and a short write is exactly what tears a JSONL line — a
  torn line is a lost submission, which is the one outcome this ledger
  exists to make impossible. This check is the actual defence, not the mere
  existence of an append call.
- Every event is capped at 4096 bytes before it is ever written. The
  fields in this schema — a path, a 64-hex digest, an opaque id, a worker
  name, a timestamp, an already-truncated failure reason — have no business
  producing a line anywhere near that size; exceeding it means something
  that should have been truncated was not. This number is a sanity bound on
  this schema, not `PIPE_BUF`: `PIPE_BUF` governs pipes and FIFOs, not
  regular files, and its value is platform-specific anyway (512 on darwin,
  4096 on Linux) — the wrong number, from the wrong object, and on this
  platform from the wrong operating system.
- `O_APPEND` on a regular, local file makes seek-to-end-and-write atomic as a
  unit with respect to other appenders, so two concurrent writers cannot
  interleave into the same region. `append()` writes through a raw fd
  (`os.open`/`os.write`), never Python's buffered `open(path, "a")`, because a
  buffered file object may split one logical write across syscalls and
  reintroduce exactly the interleaving `O_APPEND` exists to prevent.
- The ledger lives on a local filesystem only. NFS does not honor `O_APPEND`
  atomicity; the ledger is expected to live inside the target's own git
  checkout, which is a local clone.

## Event kinds

| event | fields |
|---|---|
| `submitted` | `ts`, `entrypoint`, `sourceDigest`, `submissionId`, `worker`, `requestedCapacity`, `grantedCapacity` |
| `returned` | `ts`, `submissionId`, `artifactPath`, `observedConcurrency` |
| `errored` | `ts`, `submissionId`, `reason` (truncated to 512 chars) |

`entrypoint` is the field name for the thing executed remotely — not
`notebook`. This schema and the adapter seam a later commit adds both use the
same name for it, and neither carries a format opinion about what it points
to; that policy question belongs to the CLI that submits, not to this
record.

## Environment

**None.** Stdlib-only — no `.venv`, no `setup.sh`, no `requirements.txt`.
Requires Python 3.10+.

## Ledger data location

Code is forge-owned and lives here, inside the skill. Data is target-owned:
`<target>/<Name>/.remote-execution/ledger.jsonl`, inside the target's own git
checkout, alongside the repository whose submissions it records.
