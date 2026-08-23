# Spec Delta: the-distribution-that-spans-every-account

Change: `the-distribution-that-spans-every-account` · Modifies capability: `remote-execution`
(`.claude/skills/remote-execution/scripts/packer.py`, `.claude/skills/remote-execution/scripts/remote_cli.py`,
`.claude/skills/remote-execution/SKILL.md`, `tests/test_remote_execution.py`) · Store: openspec.

Baseline: `packer.plan()` clamps one worker's request to its cap (`packer.py:110-116`); `packer.select()`
returns one `Plan` for a caller naming none (`:187-193`). Both are single-worker and untouched by this
delta. Nothing today aggregates capacity across workers, and nothing assigns opaque units to workers —
`shard_io.read_shards()` is the merge side only. This delta is purely additive: `distribute()` is new,
calls `plan()` per worker, and adds one read-only CLI subcommand.

---

## Group 1 — Opacity: a unit is an opaque identifier, never parsed

### ADDED Requirement: `distribute()` MUST accept units as an ordered sequence of opaque identifiers and MUST NOT parse, shape-check, or branch on their contents

The forge MUST NOT learn what a unit means. Its signature MUST accept any ordered sequence of strings,
with no shard shape, index, or naming convention required, and the resulting assignment MUST be
structurally identical no matter what the strings look like.

#### Scenario: Structureless identifiers distribute identically to shaped ones
- GIVEN two equal-length unit lists — one of plain integers-as-strings, one of structureless opaque tokens
- WHEN `distribute()` runs against identical worker state for both
- THEN the per-worker assignment counts SHALL be identical between the two runs

#### Scenario: A signature demanding a shard shape fails the lock
- GIVEN a hypothetical `distribute()` requiring units to carry a parseable shard name or index
- WHEN the opacity lock runs against it
- THEN it SHALL fail, naming the offending parameter or parsing call

---

## Group 2 — Aggregation and round-robin assignment

### ADDED Requirement: `distribute()` MUST aggregate `granted` capacity across every worker, in the adapter's declared order, before assigning anything

`distribute()` MUST walk `adapter.workers()`, call `plan()` once per worker, and sum `granted` into
`places`. A worker contributing zero places MUST be named with its own reason, reusing the reasons
`select()` already emits.

#### Scenario: Five workers at capacity two report ten places
- GIVEN five healthy workers, each `cap=2` and `in_flight=0`
- WHEN `distribute()` runs
- THEN `places` SHALL equal 10, computed from five separate `plan()` calls

### ADDED Requirement: Units MUST be assigned round-robin, breadth-first, over granted places, and identical inputs MUST produce an identical assignment

Ordering MUST follow the adapter's declared worker order; `distribute()` MUST invent no ordering of its
own.

#### Scenario: A small campaign spreads instead of piling on one account
- GIVEN three units and five workers each with one open place
- WHEN `distribute()` runs
- THEN the three units SHALL land on three distinct workers, one each

#### Scenario: Determinism holds across repeated calls
- GIVEN identical units, workers, and ledger state
- WHEN `distribute()` is called twice
- THEN both assignments SHALL be identical, worker for worker

---

## Group 3 — The remainder, reported by identity, never a count

### ADDED Requirement: `distribute()` MUST report `units`, `places`, `assigned`, and `unplaced` as four separate facts, with `unplaced` naming identities, not a count

An over-subscribed campaign MUST assign what fits and report the rest as `unplaced`, listing the exact
unit identities that did not fit.

#### Scenario: Twelve units against ten places
- GIVEN five healthy workers at capacity two (ten places) and twelve units
- WHEN `distribute()` runs
- THEN exactly ten units SHALL be assigned and `unplaced` SHALL list the exact two remaining identities

#### Scenario: A drop is never mistaken for a full plan
- GIVEN a distribution with two unplaced units
- WHEN the result is inspected
- THEN `unplaced` SHALL be non-empty and its length SHALL equal `units - assigned`

---

## Group 4 — Health at plan time; no mid-flight redistribution; no persistence

### ADDED Requirement: A worker without live capacity evidence MUST contribute zero places; a revoked worker MUST be skipped with its exception named, never swallowed

Health MUST be read once, at plan time, through `plan()`'s existing `in_flight_source` field — no second,
separate health probe. `distribute()` MUST NOT redistribute a worker's units after submission begins.

#### Scenario: An unconfirmed worker contributes zero places
- GIVEN a worker whose `plan()` call returns `in_flight_source == "ledger"`, not `"list_active"`
- WHEN `distribute()` runs
- THEN that worker SHALL contribute zero places and SHALL be named with its own reason

#### Scenario: A revoked worker is skipped, not swallowed
- GIVEN a worker whose `plan()` call raises `WorkerUnauthorized`
- WHEN `distribute()` runs
- THEN that worker SHALL be recorded as skipped, naming `WorkerUnauthorized` as the reason
- AND no exception SHALL propagate out of `distribute()` itself

#### Scenario: No mid-flight redistribution after a submission failure
- GIVEN a computed distribution whose one worker's submission later fails
- WHEN the campaign inspects the result
- THEN `distribute()` SHALL NOT have reassigned that worker's units to another worker
- AND those units become visible as `unplaced` only on a later `distribute()` call

### ADDED Requirement: `distribute()` MUST NOT persist an assignment or add any ledger schema field

A distribution MUST stay a pure computation over the ledger's fold and live worker state.

#### Scenario: No ledger write occurs
- GIVEN a call to `distribute()`
- WHEN it returns
- THEN no line SHALL have been appended to any ledger file

---

## Group 5 — A read-only CLI surface, submitting nothing

### ADDED Requirement: `remote_cli.py` MUST expose one read-only subcommand that prints the distribution as JSON and submits nothing

The subcommand MUST call `distribute()` and print its result; it MUST NOT call `adapter.submit()` or
write to any ledger.

#### Scenario: The subcommand submits nothing
- GIVEN the new subcommand invoked against a target with pending units
- WHEN it runs
- THEN it SHALL print a JSON distribution to stdout
- AND no `adapter.submit()` call SHALL occur

---

## Cross-cutting requirements

### ADDED Requirement: The vocabulary guard's `MODULE_SCRIPTS` MUST scan every production script this change touches

`packer.py` and `remote_cli.py`, already covered, MUST remain covered; any new production script this
change adds MUST be added to `MODULE_SCRIPTS`.

#### Scenario: Both edited files remain covered
- GIVEN this change edits `packer.py` and `remote_cli.py` and adds no new production script
- WHEN `MODULE_SCRIPTS` is inspected
- THEN both files SHALL remain present in it

### ADDED Requirement: Every new lock, including the opacity lock, MUST be proven reachable-red by inversion and restored by inverse patch

Greenness on first run is never sufficient evidence a lock runs.

#### Scenario: The opacity lock is proven reachable
- GIVEN the opacity lock passing against `distribute()`
- WHEN a hypothetical shape-demanding signature is substituted for it
- THEN the lock SHALL fail
- AND restoring the inverse patch SHALL return it to green with no other file altered

---

## Explicit non-goals

| Non-goal | Reason |
|---|---|
| Any live launch to Kaggle | Pure planning arithmetic; no service call is needed |
| A batched submit loop, retries, or a queue | The caller still submits one by one, exactly as today |
| `implementations/Domain_Adaptation` | Separate git repository, read-only from the forge |
| `openspec/config.yaml`'s stale test pin | Known defect, deliberately left for a real audit |
| The test file's 225 vocabulary fixture occurrences and `MODULE_SCRIPTS` not scanning the test file | Predates this work; must surface from an audit, not be hand-carried |

## Acceptance

`python3 -m unittest discover -s tests` green at 1125 plus the number of tests added, counted as a rise.
Five workers at capacity two report ten places. Twelve units against ten places assign ten and report
two `unplaced` by identity. Opaque identifiers distribute identically regardless of naming. A worker
without live evidence contributes zero places; a revoked one is skipped with `WorkerUnauthorized` named.
No ledger line or schema field is added. Every new lock is reachable-red by inversion, restored by
inverse patch confirmed by sha256. Nothing is launched to Kaggle.
