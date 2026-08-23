# Design: the-distribution-that-spans-every-account

## Technical Approach

One pure function in `packer.py`, one read-only CLI command, one extracted triage helper. `distribute()` aggregates by calling `plan()` per worker (the clamp stays in one place), assigns positionally, and inspects nothing about a unit beyond "non-empty `str`". Nothing persists; nothing is submitted.

## Interfaces

```python
def distribute(*, adapter, units: Sequence[str], ledger_lines, live_digest) -> Distribution

@dataclass(frozen=True)
class Assignment:  plan: Plan;  units: tuple[str, ...]   # the whole Plan, never a collapsed granted
@dataclass(frozen=True)
class Skip:        worker: str; reason: str              # triage's exact reason, unprefixed
@dataclass(frozen=True)
class Distribution:
    units: tuple[str, ...]        # exactly as handed in
    places: int                   # sum of granted over assignments
    assignments: tuple[Assignment, ...]   # workers granting >=1, declared order
    unplaced: tuple[str, ...]     # BY IDENTITY, input order
    skipped: tuple[Skip, ...]     # workers granting 0, declared order
```

No `requested` parameter: every worker is asked `requested=len(units)` and `plan()` clamps it. **Rejected**: pre-slicing `len(units)//len(workers)` — three units over five workers gives each a share of 0 and distributes nothing. No `complete` boolean: a boolean is the collapse this module refuses; `unplaced` is the fact. Two invariants hold and are asserted: every unit appears exactly once across `assignments`+`unplaced` (conservation — nothing can vanish), and `{assignments}∪{skipped}` equals `adapter.workers()` exactly (no account disappears silently).

## Architecture Decisions

| # | Choice | Alternative rejected | Rationale |
|---|---|---|---|
| 1 | Zero healthy workers is a **result** (`places=0`, all units unplaced, every reason in `skipped`) | Raise, like `select()` | `select()` must raise — it owes one `Plan` and has none. `distribute()` has an honest total answer, richer than an exception string. **But** `adapter.workers()` empty still raises, reusing `select()`'s existing first refusal. |
| 2 | Duplicate identifiers → `PackerError` naming each repeat and its positions | Dedup silently; place both | `unplaced` is reported by identity; duplicates destroy identity as a key and make conservation unstateable. Placing both double-submits the same work under two accounts. |
| 3 | Empty `units` → honest result, `places` still computed | Refuse | It is the "how many places do I have" query; refusing forces a caller to invent a unit. |
| 4 | Surplus workers stay in `assignments` with `units=()` | Move them to `skipped` | "Had room, didn't need it" is not "had no room". |
| 5 | `select()`/`distribute()` share a private `_triage(worker) -> (Plan\|None, reason\|None)`, not a body | Express `select()` as `distribute(units=(x,))[0]` | Each `plan()` dials `list_active()`; `select()` short-circuits at the first healthy account, `distribute()` probes all — the rewrite turns a one-account probe into an N-account probe on a live service. The helper is the anti-drift device: the health rule and its three reason strings live in one place. |
| 6 | Repeatable `--unit`, never `--units a,b,c` | Comma-separated list | A separator imposes structure on identifiers: a unit containing a comma would be split. The opacity leak, reappearing at the CLI. |

## Round-robin, exactly

`order` = workers with `granted >= 1`, in `adapter.workers()` declared order. Place sequence: for `r = 0,1,2,…`, append every `w` with `granted(w) > r`; stop when a round appends nothing. Unit `i` goes to `place_sequence[i]`; units past the end are `unplaced` in input order. "A round" over ragged rows is simply that a worker drops out once its own places are spent.

Worked: `w1`(2), `w2`(1), `w3`(2) over `u_a..u_f` → sequence `w1,w2,w3,w1,w3` → `w1=(u_a,u_d)`, `w2=(u_b,)`, `w3=(u_c,u_e)`, `unplaced=(u_f,)`, `places=5`, `units=6`.

Deterministic because all three inputs are ordered sequences never re-sorted (declared worker order, caller's unit order, positional zip) and no dict/set iteration participates. The test pins the **explicit expected tuple**, not merely repeat-equality — a stable-but-wrong order repeats too.

## Health is read once, and cannot drift to a guess

`distribute()` reads health only through `plan()`'s two existing fields, on one pass, and **never reads `Worker.capacity` itself** — its only route to a number is `plan().granted`. `WorkerUnauthorized` never yields a `Plan` at all. The dangerous case is `in_flight_source != "list_active"`: the `Plan` exists and carries a positive `granted`. `_triage()` returns `(None, reason)` there, and `places` sums only triage-returned Plans. Three guards against the later swallow: (a) `inspect.getsource(PACKER.distribute)` names no `.capacity`; (b) five workers of cap 2 with three unreachable reports `places == 4`, never 10, and inverting the `in_flight_source` check makes it 10 — the mutation proof; (c) each unconfirmed worker is named in `skipped` by identity, so a defaulting edit must also delete rows the test names.

## The opacity lock, written so it cannot pass vacuously

Distribute the same fixture twice under two alphabets of equal length: **A** structured-but-domain-free and deliberately **not in sorted order**; **B** structureless opaque hex tokens whose sorted order differs from A's positional order. Assert that applying the bijection `A[i] → B[i]` to result A yields result B exactly (per-worker tuples and `unplaced`, in order). The test asserts properties of **its own fixtures** first — `A != B` elementwise, disjoint sets, `list(A) != sorted(A)`, and B's sort permutation ≠ A's — so a later "simplification" of the alphabets cannot make it trivially true. Inversion: inserting `units = sorted(units)` into `distribute()` must turn it red; if it cannot, the lock never locked. A second family passes identifiers containing a space, a comma, a slash and 200 chars, and asserts byte-identical round-trip through the CLI's JSON.

## `distribute` (CLI) — read-only

`--target`, `--entrypoint` (product/digest resolution, exactly as `status`), `--backend`, repeatable `--unit`, `--credential-dir`. Stdout: one `sort_keys=True` JSON object carrying **four separate facts** — `units` (count), `places`, `assigned` (count), `unplaced` (identities) — plus `assignments` (each row the full four numbers, `inFlightSource`, and its unit identities) and `skipped`. Exit `0` when at least one place exists, including a partial distribution: a visible remainder is a success, not a failure. Exit `1` on refusal (stderr, as every other command) **and** when `places == 0` with units handed — the JSON still prints, but the CLI refuses to say "fine". **Rejected**: a new exit code `3`; this CLI's vocabulary is two-valued and this change adds no third value.

"Submits nothing" cannot use the `cmd_status`/`cmd_readiness` no-`adapter`-parameter precedent — health is live, so an adapter must be in scope. Say so plainly and lock it three other ways: (1) drive `main(["distribute", …])` with the existing `MultiWorkerFakeAdapter(forbid_submit=True)`, whose `submit()` raises; (2) snapshot every path under `<target>` as `(relpath, sha256)` before and after and assert the mapping is byte-identical with no path added or removed — this catches any write, not only the ledger append we thought to check; (3) `inspect.getsource(REMOTE_CLI.cmd_distribute)` names neither `append` nor `submit`.

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/remote-execution/scripts/packer.py` | Modify | `Distribution`/`Assignment`/`Skip`, `distribute()`, `_triage()`; `select()` refactored onto `_triage()`; module docstring and `Plan`'s "one capacity decision for one worker" line **re-derived** for three arities |
| `.claude/skills/remote-execution/scripts/remote_cli.py` | Modify | `cmd_distribute()`, its subparser, its `main()` branch |
| `.claude/skills/remote-execution/SKILL.md` | Modify | The `packer.py` bullet re-derived for `plan`/`select`/`distribute`; the unit-opacity boundary stated |
| `tests/test_remote_execution.py` | Modify | New locks; `MultiWorkerFakeAdapter` extended **in place** with optional `active: dict[str, list[str]]` (default `{}`) for ragged in-flight fixtures |

`plan()`'s body, `Plan`'s fields, `ledger.py`, `adapter.py` and every event schema are untouched.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Aggregation (5×2 → 10, computed); ragged round-robin exact tuple; remainder by identity; conservation; total worker accounting; duplicates/empty/surplus/zero-healthy; determinism | `MultiWorkerFakeAdapter`, no service call |
| Doctrine | Opacity (both families); `.capacity` absent from `distribute`'s source; `select()`/`distribute()` reason-string parity; `MODULE_SCRIPTS` unchanged coverage (no new production script is added, so no new entry is due — assert that explicitly rather than assume it) | Source and signature inspection, the file's existing precedent |
| CLI | `main(["distribute", …])` end-to-end JSON, exit 0 / partial-0 / places-0-exit-1, `forbid_submit`, tree-hash no-write snapshot | Runtime harness |
| Suite integrity | `ast` guard: every top-level `ClassDef` name **and** every method name in the test file is unique | Top-level class names are duplicate-free today (59, verified); a duplicate **method** surfacing is an audit finding to report, never hand-fixed here |

Every lock proven reachable-red by inversion, restored by inverse patch confirmed by `sha256`. Verified by test count **rising** by the number added from 1125, never by the suite staying green.

## Threat Matrix

`N/A`, all five rows. The command classifies no file kind (it never calls `guard_entrypoint()`, following `status`) and touches no VCS or PR surface. The one adjacent process boundary — `--backend`'s `_load_backend_module()` side-load — is reused **unchanged**, already guarded by `_BACKEND_NAME_RE` plus an independent `relative_to()` containment check.

## Migration / Rollout

None. No ledger schema or on-disk format change; `plan()` and `select()`'s observable behaviour is unchanged. Reverting removes a capability and the `_triage()` extraction — both mechanical.

## Open Questions

- [ ] None blocking. The five proposal questions are answered and encoded above.
