---
name: remote-execution
description: "Trigger: durable record of what a repository has submitted to a remote worker, what came back, and how much to submit at once. This skill ships the append-only ledger (write path and the fold that derives per-entrypoint state), the backend-agnostic adapter seam (ABC + frozen shapes + registry), the packer's capacity clamp, the full `remote_cli` front door (`submit` with its path guard, `status`, `poll`, `fetch` with quarantine, `reconcile`), and one concrete backend: `adapters/kaggle.py` — the ONLY file in this entire skill allowed to name a service. It shells out to the `kaggle` CLI (never imports the `kaggle` package), derives worker identity solely from kaggle-accounts' own sanctioned `list --json` command, and accepts credentials only as a `CredentialHandle(worker_id, config_dir)` carrying a path, never a value — its single sink is `KAGGLE_CONFIG_DIR` on a child process's environment. Stdlib-only, no venv."
---

# Remote Execution

A submission to a remote worker is a fact once it happens, and this skill's
job is to make sure that fact survives being written, to derive current
state from the record rather than store it separately, and to decide how
much work a worker is asked to take on at once without either side of that
decision asserting the other's fact. Nothing here yet talks to a real
service — that is a concrete adapter, still to come — but the CLI a user
would invoke directly (`submit`, `status`, `poll`, `fetch`, `reconcile`) is
in place today, exercised against a `FakeAdapter` only.

## Current Scope

Three modules exist so far, each service-blind and stdlib-only:

- `scripts/ledger.py` — `append(path, event)` appends one JSON-encoded event
  as a single line to `<target>/<Name>/.remote-execution/ledger.jsonl`. The
  file is opened `O_APPEND`; a line, once written, is never rewritten or
  deleted (see below for why an append can be trusted at all).
  `fold(lines, live_digest)` derives current per-entrypoint state from that
  log — `pending | returned | errored`, whether a pending submission is
  `staleInFlight`, and which `returned` results are `fromStaleSubmission` —
  the currency rule that tells a fresh result from a stale one.
  `submitted_event(...)`, `returned_event(...)`, `errored_event(...)` build
  the three event kinds this ledger records, with the field names and
  truncation rules this schema fixes (see below).
- `scripts/adapter.py` — the `Adapter` ABC every backend-specific module
  must satisfy in full, the frozen data shapes that cross the seam
  (`Worker`, `Job`, `Submission`, `Status`, `Fetched`), and a name-to-class
  registry a caller can select a backend by without importing it directly.
  No concrete backend implements this ABC yet; this skill's own test suite
  stands a `FakeAdapter` in for one.
- `scripts/packer.py` — `plan(...)` clamps a repository's declared
  per-worker request to the cap the adapter states through `workers()`,
  deducting what is already committed (from the ledger's fold, refined by
  `list_active()` when the adapter answers). The clamp is never a silent
  minimum: `plan()` returns `requested`, `cap`, `inFlight` and `granted` as
  four separate numbers, plus `inFlightSource` recording whether `inFlight`
  came from the live service or fell back to the ledger.
- `scripts/remote_cli.py` — the CLI front door, five commands.
  - `submit` guards the entrypoint, computes a fresh `source_digest()`,
    calls `packer.plan()`, hands the job to a registered adapter's
    `submit()`, and appends the resulting `submitted` event to the ledger —
    in that order. `guard_entrypoint()` is the ONLY place in this whole
    skill that holds an opinion about what KIND of file may run remotely:
    `Path.resolve()` first, then refuse anything whose resolved path does
    not stay under `<target>/<Name>/Notebooks/` and end `.ipynb`.
    Everything below the guard (`Job.entrypoint`, the ledger's `entrypoint`
    field, the fold's indices) stays deliberately blind to that question;
    widening this one guard, not reworking any of those, is how a future
    non-notebook workload becomes admissible.
  - `status` folds the ledger and reports per-entrypoint state, what is
    `staleInFlight`, what is quarantined, and `unreadableLines`. It accepts
    no `adapter` parameter at all — a structural fact, not a convention —
    so it reports and never resolves anything.
  - `poll` asks the adapter for one submission's status and refuses a
    `Status.state` outside the seam's own five-value vocabulary itself,
    rather than trusting every adapter to have gone through
    `ADAPTER.Status.__post_init__`'s own validation.
  - `fetch` materializes into `<dest>.partial/` and renames into place only
    on `Fetched.complete == True`; only a completed rename appends a
    `returned` event, so a crash mid-fetch leaves the submission `pending`
    — retryable, never a false `returned`. `LEDGER.currency_verdict()` (the
    same rule `fold()` itself uses) is evaluated before the rename: a
    `fromStaleSubmission` result overrides the caller's requested `dest`
    entirely and is fetched into
    `<target>/<Name>/.remote-execution/quarantine/<submissionId>/` instead
    — structurally outside `Results/shards/`, so it is parked and
    auditable, never merged. Every `returned` event also carries
    `observedConcurrency`: `LedgerState.pending_for(worker)` read from the
    ledger state at the top of the call, so a service throttling below the
    packer's own grant becomes a visible, different number instead of an
    assumed one.
  - `reconcile` compares `adapter.list_active(worker)` against the ledger's
    own pending set for that worker, in both directions, and only ever
    reports the difference. An id the service has that the ledger lacks is
    `orphanRemote` — reported, never auto-cancelled and never auto-adopted,
    because adopting would fabricate a `submitted` line with no digest, and
    the digest is the entire basis a later result is judged current by. A
    `pending` ledger submission the service no longer lists is
    `orphanLocal` — reported, and `--resolve` (human-invoked only, default
    `False`) is the one path that appends `errored(reason="not-found-at-service")`
    for it.
  - `name_for(target, entrypoint)` derives `<Name>` from a resolved path the
    same way `guard_entrypoint()` does, factored out so `fetch`'s quarantine
    path and `reconcile`'s ledger selection reuse the one derivation instead
    of each growing a second copy that could quietly disagree with `submit`'s.
- `scripts/adapters/kaggle.py` — the ONE file below the adapter seam allowed
  to name a service. `workers()` reports usernames from kaggle-accounts' own
  sanctioned `list --json` command (run as a subprocess; this module never
  opens kaggle-accounts' own credential file itself, directly or otherwise),
  each stamped with this service's own documented per-worker allowance
  (`KAGGLE_WORKER_CAPACITY`, a module constant, explicitly not a universal
  one). `submit`/`poll`/`fetch`/`cancel`/`list_active` shell out to the
  `kaggle` CLI — `shell=False`, list argv, an env built from an allowlist
  (`PATH` plus, when a credential is involved, `KAGGLE_CONFIG_DIR`), and an
  explicit timeout on every call; a non-zero exit or an expired timeout is a
  refusal (`KaggleAdapterError`), never a fabricated `Status`, `Submission`
  or `Fetched`. `poll()` translates Kaggle's own raw status text into the
  seam's five-value vocabulary and never passes it through; the raw text
  goes in `Status.detail` only. `CredentialHandle(worker_id, config_dir)` is
  the only credential type this adapter accepts, exposes no read method, and
  has exactly one sink in the whole file: `env["KAGGLE_CONFIG_DIR"] =
  str(handle.config_dir)`. `REQUESTED_ACCELERATOR = "T4"` is declared here —
  a request, not a receipt; what a submission actually ran on is a fact the
  service states at poll/fetch time, never assumed from this constant.
  `cancel()` refuses explicitly: Kaggle's own CLI documents no
  single-kernel cancel operation, and this adapter does not guess at an
  unofficial one.

Every `remote_cli` command a user would invoke (`submit`, `status`, `poll`,
`fetch`, `reconcile`) exists today. `submit`/`poll`/`fetch`/`reconcile` are
exercised in this skill's own test suite against both a `FakeAdapter` and
`adapters/kaggle.py` (the latter only ever against a fake `kaggle`
executable — no test in this suite reaches the network or a real account).

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
`notebook`. This schema and the adapter seam (`scripts/adapter.py`) both use
the same name for it, and neither carries a format opinion about what it
points to; that policy question belongs to the CLI that submits, not to
this record.

## Environment

**None.** Stdlib-only — no `.venv`, no `setup.sh`, no `requirements.txt`.
Requires Python 3.10+.

## Ledger data location

Code is forge-owned and lives here, inside the skill. Data is target-owned:
`<target>/<Name>/.remote-execution/ledger.jsonl`, inside the target's own git
checkout, alongside the repository whose submissions it records.

## Quarantine location

`<target>/<Name>/.remote-execution/quarantine/<submissionId>/` — a
`fromStaleSubmission` result's fetch destination, structurally outside
`Results/shards/`. This is what makes the non-merging structural rather than
procedural: the tree a shard reader enumerates never contains this path, so
there is nothing a filter could forget to apply.
