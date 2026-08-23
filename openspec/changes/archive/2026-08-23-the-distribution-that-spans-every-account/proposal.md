# Proposal: the-distribution-that-spans-every-account

Domain: `remote-execution` · Store: openspec · Subject: `.claude/skills/remote-execution/`

## Intent

A campaign is many units of work; the accounts are many; each account runs two GPU notebooks at once. **The skill knows the second fact and not the first.** It refuses to oversubscribe one account, correctly and in one place — and plans no spread at all.

| # | Measured today | Evidence |
|---|---|---|
| 1 | The per-account allowance is known, and framed as observed rather than as law | `adapters/kaggle.py:168` — `KAGGLE_WORKER_CAPACITY = 2`, with its own comment naming it a measured property of `kernels push`, "never asserted as a universal per-account or per-service ceiling" |
| 2 | The clamp is honest and kept un-collapsed | `packer.py:175` — `granted = max(0, min(requested, cap) - in_flight)`, reported as four separate numbers so a clamp is never indistinguishable from an unclamped grant that happens to equal it |
| 3 | **Everything is single-worker.** `plan()` takes one `worker_id`; `select()` returns one `Plan` | `packer.py:110-116`, `:187-193` |
| 4 | **Nothing aggregates capacity across workers.** Five accounts at two slots is ten concurrent places, and no code computes ten | no aggregation in `packer.py`, `remote_cli.py`, `ledger.py` |
| 5 | **Nothing assigns work to workers.** `shard_io.read_shards()` is the merge side only — reading results back from disk, never distributing | `scripts/shard_io.py:27` |

Hand the skill twelve units against ten places and **nobody decides which ten go first**. The caller decides, or the invoking agent improvises. That is the exact shape of fork the archived `the-invocation-that-goes-straight-through` existed to remove, reappearing one arity up.

## The boundary, and how it is held

**What makes a unit meaningful is the target's knowledge, not the forge's.** Which seeds belong together, which epochs cannot be cut — that lives in the target repository, which is why its own entrypoint already takes a shard name. **The forge must never learn what a seed is.**

**The assignment itself carries no domain knowledge.** "Distribute N opaque units over M workers, each with its own capacity, respecting what is already in flight, and say honestly what did not fit" is pure arithmetic.

The subtler leak is not vocabulary — it is an **API shaped so that only one kind of unit fits**. Two locks, because the existing vocabulary guard catches only the first:

1. **Vocabulary** — the guard's `MODULE_SCRIPTS` must scan every production script this change touches, including any new one.
2. **Opacity** — the same distribution over units named by structureless opaque strings must produce a structurally identical assignment. A signature that demands a shard shape, an index, or a parseable name fails that lock. Units are an ordered sequence of opaque identifiers; the module never parses one.

## The five decisions, confronted

| # | Question | Decision | Cost accepted |
|---|---|---|---|
| 1 | **Ordering** — fill one account, or round-robin? | **Round-robin, breadth-first, over healthy workers in the accounts CLI's declared order** — the order `select()` already walks and invents nothing new | Ordering only changes the outcome when **units < open places**; at or above capacity every strategy fills every place. Below it, fill-first touches fewer credentials and concentrates risk on one account; round-robin spends more accounts' quota but bounds makespan by the least-loaded account instead of the most-loaded |
| 2 | **The remainder** — twelve units, ten places | **Assign what fits; report the rest as `unplaced`, by identity, not as a count.** The four-numbers precedent applies: `units`, `places`, `assigned`, `unplaced` stay four separate facts | Not a queue and not a refusal. Queuing needs persistence and a scheduler the skill does not have; refusing the whole campaign hands the user a decision, which is the thing being removed. A later call re-places the remainder once slots return |
| 3 | **A worker unhealthy mid-distribution** | **Health is read once, at plan time, through `plan()`'s exact two existing fields** (no `WorkerUnauthorized`; `in_flight_source == "list_active"`). An unconfirmed worker contributes **zero places**, never a guessed two. **No mid-flight redistribution** | Units for a worker that fails during submission come back as `unplaced` on the next distribution — visibly. Silently moving them changes whose quota is spent, and the archived change settled that this is a decision, not a repair |
| 4 | **Does it persist?** | **No.** A distribution is a computation over the ledger plus live counts. The ledger records **submissions** — things that happened at the service | A recorded assignment is a second source of truth that goes stale the instant one job returns, and `fold()` would then have to reconcile it. No ledger schema change, so rollback carries no migration. Cost: nothing remembers an assignment across processes; submission remains the only committing act |
| 5 | **Does it belong in `packer.py`?** | **Yes.** `distribute()` must call `plan()` per worker; a separate module would import the clamp or duplicate it, and this module's whole doctrine is that the clamp lives in exactly one place | The module docstring says "one capacity decision for one worker" and must be re-derived, not appended to. The real seam is unit opacity (above), not a file boundary |

## Scope

### In scope

| Item | Files |
|---|---|
| `packer.distribute()` — aggregate capacity across workers, assign opaque units, report `assigned` + `unplaced` + per-worker skip reasons | `scripts/packer.py` |
| A **read-only** CLI subcommand that prints the distribution as JSON and **submits nothing** | `scripts/remote_cli.py` |
| Re-derived module docstring and `SKILL.md` surface for three shapes: `plan` / `select` / `distribute` | `scripts/packer.py`, `SKILL.md` |
| The opacity lock and the vocabulary guard's coverage of any new production script | `tests/test_remote_execution.py` |

### Out of scope, with reasons

- **Any live launch.** This change is pure planning arithmetic and needs no service call at all. Nothing goes to Kaggle without the user's explicit permission.
- **A batched submit loop, retries, or a queue.** The distribution is computed; the caller submits one by one, exactly as today.
- **`implementations/Domain_Adaptation`** — a separate git repository (`Daprosero/Domain_Adaptation`), read-only from the forge, carrying one uncommitted line the user owns.
- **`openspec/config.yaml`** — it pins the test command to `test_extract_pdf.py` and never runs these suites. A real defect, deliberately left for a real audit to find.
- **The test file's 225 target-vocabulary fixture occurrences, and `MODULE_SCRIPTS` not scanning the test file.** Production scripts are clean and guarded. Both predate this work and must surface from a real audit, not be hand-carried.
- Any other skill.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `remote-execution`: capacity aggregated across workers, assignment of opaque units to workers, and the honest reporting of what did not fit.

## Approach

1. **Arm the opacity lock first**, red against today's code — there is no `distribute` to satisfy it.
2. **Aggregate before assigning.** `distribute()` walks `adapter.workers()` in declared order, calls the existing `plan()` per worker, sums `granted` into `places`, and records a reason for every worker contributing zero — the same reasons vocabulary `select()` already emits.
3. **Assign round-robin over the granted places**, deterministically: identical inputs produce an identical assignment.
4. **Report `unplaced` by identity.** A distribution that drops two units silently must be impossible to confuse with one that had ten.
5. **Expose it read-only** through the CLI, then re-derive the docstring and `SKILL.md` from what the three shapes actually do.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `.claude/skills/remote-execution/scripts/packer.py` | Modified | `distribute()` added; docstring re-derived for three shapes |
| `.claude/skills/remote-execution/scripts/remote_cli.py` | Modified | One read-only subcommand emitting the distribution as JSON |
| `.claude/skills/remote-execution/SKILL.md` | Modified | The distribution surface and the unit-opacity boundary |
| `tests/test_remote_execution.py` | Modified | Opacity lock, aggregation, remainder, unhealthy-worker, determinism |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The API quietly assumes a unit shape and the forge stops being general | **High**, and it is the central risk | The opacity lock: structureless identifiers must distribute identically. Proven reachable-red by inversion |
| A distribution silently drops the remainder and reads as a full plan | Med | `unplaced` reported by identity; the four-numbers precedent extended, never collapsed |
| An unconfirmed worker is counted as two places and the campaign oversubscribes | Med | Zero places for any worker without live `list_active` evidence — refuse to guess, exactly as `plan()` already refuses |
| `packer.py` becomes three loosely related shapes in one module | Low | Docstring re-derived rather than appended; the clamp stays in one place, which is the reason the module exists |
| A green suite hides a lock that stopped locking | Med | Verify by test counts **rising** by the number added, never by a suite staying green |
| The change exceeds the 400-line per-PR guard | Med | ~500 authored lines forecast (arithmetic ~120, CLI ~80, doctrine ~60, tests ~250). Session strategy is `single-pr`; if the guard is enforced, split arithmetic from CLI surface |

## Rollback Plan

`distribute()` and the CLI subcommand are purely additive; `plan()` and `select()` are untouched, so reverting removes a capability without changing any existing behaviour. No on-disk artifact format changes and **no ledger schema change**, so there is no data to migrate. The docstring and `SKILL.md` commit reverts on its own.

## Dependencies

- None. Stdlib-only arithmetic over the existing `adapter` and `ledger` seams. **No live Kaggle access is required to land this change.**

## Success Criteria

- [ ] Five workers at capacity two report **ten** places, computed rather than assumed.
- [ ] Twelve units against ten places assign ten and report **two `unplaced` by identity** — never a count alone, never a silent drop.
- [ ] Units named by structureless opaque strings distribute identically to any other naming; no forge file learns what a unit means.
- [ ] A worker without live capacity evidence contributes zero places and names its own reason; a revoked one is skipped with `WorkerUnauthorized` recorded, not swallowed.
- [ ] Identical inputs produce an identical assignment.
- [ ] No ledger line and no schema field is added.
- [ ] Every new lock is proven reachable-red by inversion, and restored by inverse patch confirmed by sha256.
- [ ] `python3 -m unittest discover -s tests` is green at **1125 + the number of tests added**, counted as a rise.
- [ ] The vocabulary guard stays green and scans every production script this change touches.
- [ ] **Nothing was launched to Kaggle.**

## Proposal question round

This phase could not ask interactively. Five questions whose current assumption is stated above, so it can be corrected now rather than discovered later. Answering, skipping, correcting the framing, or asking for a second round are all fine.

1. **Round-robin over fill-first** — assumed, so a small campaign spreads instead of piling on the first account. Fill-first is defensible if touching fewer credentials matters more than makespan. Which cost is the real one?
2. **`unplaced` rather than a queue** — assumed, because a queue needs persistence the skill does not have. Should an over-subscribed campaign instead refuse outright?
3. **No mid-flight redistribution** — assumed, because moving units changes whose quota is spent. Should a failure during submission auto-redistribute and report afterwards?
4. **A read-only CLI subcommand that submits nothing** — assumed as the first slice. Should the distribution stay a library call with no CLI surface at all until a batched submit exists?
5. **`requested` in a multi-worker world** — `plan()` takes a per-worker `requested`. Does a campaign declare a per-worker request, or only a total unit count that the distribution spreads? Assumed: the campaign hands units, and per-worker `requested` is derived as the worker's own share.
