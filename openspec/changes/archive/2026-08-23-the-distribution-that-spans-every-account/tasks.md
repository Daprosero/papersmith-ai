# Tasks: the-distribution-that-spans-every-account

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~490 (arithmetic ~120, CLI ~80, doctrine/docs ~60, tests ~230) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Unit 1: arithmetic core (`packer.py` + its tests) → Unit 2: CLI surface (`remote_cli.py` + docs + its tests) |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | `distribute()`/`_triage()`/`Distribution`/`Assignment`/`Skip` in `packer.py`, all arithmetic/doctrine tests | PR 1 (or slice 1 of size-exception) | `python3 -m unittest tests.test_remote_execution -v 2>&1 \| grep -i distribut` | N/A — pure planning arithmetic; `MultiWorkerFakeAdapter` is the substitute for a live service, no Kaggle call needed | Revert `distribute()`, `_triage()`, the three dataclasses, and their tests; `plan()`/`select()` observable behavior unchanged |
| 2 | `cmd_distribute()` CLI surface, `SKILL.md`/docstring re-derivation, CLI + opacity-round-trip tests | PR 2 (or slice 2) | `python3 -m unittest tests.test_remote_execution -v 2>&1 \| grep -i "Distribute.*Cli\|NoWrite"` | `python3 remote_cli.py distribute --target <tmp> --entrypoint <tmp>/.../*.ipynb --backend fake --unit u1 --unit u2 --credential-dir <tmp>` against `MultiWorkerFakeAdapter(forbid_submit=True)` — N/A for a live backend | Revert `cmd_distribute`, its subparser/`main()` branch, and doc edits; `packer.py` untouched |

Count-rise baseline: **1125**. Each phase below names its expected post-commit count.

## Phase 1: Test Harness Prep + Parity Lock (before extraction)

- [x] 1.1 Extend `MultiWorkerFakeAdapter.__init__` (`tests/test_remote_execution.py:5065`) IN PLACE with `active: dict[str, list[str]] = {}`; `list_active()` returns `self._active.get(worker, [])` for a healthy worker. Never a second class of the same name.
- [x] 1.2 Write `test_active_kwarg_produces_ragged_granted_capacity` proving the extension yields differing `granted` per worker via `plan()`. RUN, confirm pass.
- [x] 1.3 Write `test_select_reason_strings_are_pinned` asserting `select()`'s exact strings `"live capacity evidence unavailable"` and `"no capacity granted right now"` for the three fixtures (healthy/unconfirmed/no-capacity), against TODAY's `select()` — BEFORE any `_triage()` extraction, so the parity lock is proven against real behavior, not the refactor's own new code. RUN, confirm green.
- [x] Commit 1 — expected count: **1127**

## Phase 2: Opacity Lock, Armed Red First

- [x] 2.1 Write `test_opacity_lock_fixtures_are_nonvacuous`: alphabet A (structured, domain-free, unsorted) and B (opaque hex, differing sort permutation) assert `A != B` elementwise, disjoint sets, `list(A) != sorted(A)`, differing sort permutations.
- [x] 2.2 Write `test_opacity_lock_bijection_holds_between_alphabets` calling `PACKER.distribute` (does not exist yet — RED). RUN, paste the failure.
- [x] Commit 2 — expected count: **1129**

## Phase 3: Aggregation Core

- [x] 3.1 In `packer.py`, add `Assignment`, `Skip`, `Distribution` frozen dataclasses exactly per design (`Assignment.plan: Plan`, no `complete` field).
- [x] 3.2 Extract `_triage(worker) -> (Plan | None, reason | None)` from `select()`'s per-worker health branch, reusing the two exact reason strings from 1.3; refactor `select()` to call it. RUN Phase 1's parity lock, confirm still green.
- [x] 3.3 Implement `distribute(*, adapter, units, ledger_lines, live_digest)`: walk `adapter.workers()`, call `plan(requested=len(units))` per worker via `_triage()`, sum `granted` into `places`; empty `adapter.workers()` reuses `select()`'s existing raise.
- [x] 3.4 Write `test_five_workers_at_capacity_two_report_ten_places`. RUN Phase 2's opacity test, confirm now green.
- [x] Commit 3 — expected count: **1130**

## Phase 4: Round-Robin Assignment

- [x] 4.1 Implement ragged round-robin: `order` = workers with `granted >= 1`; for `r=0,1,2,…` append every `w` with `granted(w) > r`; stop when a round adds nothing; unit `i` → `place_sequence[i]`.
- [x] 4.2 Write `test_round_robin_worked_example_pins_explicit_tuple`: `w1(2),w2(1),w3(2)` over six units → explicit `w1,w2,w3,w1,w3`, one unplaced. Pin the literal tuple, not repeat-equality.
- [x] 4.3 Write `test_round_robin_is_deterministic_across_repeated_calls`: call `distribute()` twice, assert against the SAME explicit expected tuple from 4.2, not merely `result1 == result2`.
- [x] 4.4 Write `test_small_campaign_spreads_instead_of_piling_on_one_account`: 3 units, 5 workers at 1 open place each → 3 distinct workers, one each. Doubles as the counterexample against pre-slicing `len(units)//len(workers)` (would floor to 0 here).
- [x] Commit 4 — expected count: **1133**

## Phase 5: Remainder and Invariants

- [x] 5.1 Write `test_twelve_units_against_ten_places_reports_two_unplaced_by_identity`: five workers cap 2, twelve units → 10 assigned, `unplaced` names the exact two identities.
- [x] 5.2 Write `test_conservation_every_unit_appears_exactly_once`: assert `assignments`-union + `unplaced` covers `units` exactly once each.
- [x] 5.3 Write `test_worker_accounting_assignments_and_skipped_cover_all_workers`: `{assignments} ∪ {skipped}` equals `adapter.workers()` exactly.
- [x] Commit 5 — expected count: **1136**

## Phase 6: Health Guards (mutation-proofed)

- [x] 6.1 Write `test_unconfirmed_worker_contributes_zero_places`: `in_flight_source != "list_active"` → worker granted 0, named in `skipped` with its own reason.
- [x] 6.2 Write `test_revoked_worker_skipped_not_swallowed`: `WorkerUnauthorized` → recorded in `skipped` naming it; no exception propagates out of `distribute()`.
- [x] 6.3 Write `test_three_unreachable_workers_yield_four_places_not_ten`: 5 workers cap 2, 3 unreachable → `places == 4`. Then MANUALLY invert the `in_flight_source` check in `distribute()`, re-run, confirm `places == 10` (mutation proof), restore by inverse patch, confirm `sha256` of `packer.py` matches pre-inversion.
- [x] 6.4 Write `test_distribute_source_never_reads_capacity_directly`: `inspect.getsource(PACKER.distribute)` contains no `.capacity`.
- [x] Commit 6 — expected count: **1140**

## Phase 7: No Mid-Flight Redistribution, No Persistence

- [x] 7.1 Write `test_no_mid_flight_redistribution_after_submission_failure`: first `distribute()` call leaves a unit unplaced (worker at capacity); second call with updated ledger state (freed capacity) is the only way that unit gets placed — never within the first call.
- [x] 7.2 Write `test_distribute_writes_no_ledger_line`: snapshot the ledger file bytes before/after a `distribute()` call, assert byte-identical.
- [x] Commit 7 — expected count: **1142**

## Phase 8: Edge Inputs

- [x] 8.1 Write `test_duplicate_unit_identifiers_refuse_by_name_and_position`: `PackerError` naming each repeated identifier and its positions.
- [x] 8.2 Write `test_empty_units_is_an_honest_result_with_places_computed`.
- [x] 8.3 Write `test_surplus_workers_stay_in_assignments_with_empty_units`.
- [x] 8.4 Write `test_zero_healthy_workers_is_a_result_not_a_raise`: `places=0`, all units in `unplaced`, every worker in `skipped`.
- [x] 8.5 Write `test_zero_workers_at_all_still_raises`: reuses `select()`'s existing first refusal message.
- [x] Commit 8 — expected count: **1147**

## Phase 9: Doctrine Guards

- [x] 9.1 Write `test_module_scripts_still_covers_packer_and_remote_cli`: explicit assertion that `MODULE_SCRIPTS` (`tests/test_remote_execution.py:10332`) still lists both files; no new production script is added by this change.
- [x] 9.2 Write `test_no_duplicate_class_or_test_method_names_in_suite`: `ast`-based scan of `tests/test_remote_execution.py` for duplicate top-level `ClassDef` names AND duplicate `test_` method names across the whole file. Report any duplicate method found as an audit finding — do not hand-fix it here.
- [x] Commit 9 — expected count: **1149**

## Phase 10: Read-Only CLI Surface

- [x] 10.1 In `remote_cli.py`, add `cmd_distribute(*, target, entrypoint, adapter, units, source_digest=None)`: resolves target/entrypoint exactly as `cmd_status` (`product_for()`, main ledger path, digest seam); `--backend`/`--credential-dir` are threaded through `main()`'s own adapter-construction wiring, the same shape every other adapter-taking command (`submit`/`poll`/`fetch`/`reconcile`) already uses — `cmd_status` alone accepts no adapter, and that precedent stays unavailable here since health is live, exactly as the design says. Calls `PACKER.distribute()`, prints one `sort_keys=True` JSON object (`units`, `places`, `assigned`, `unplaced`, `assignments` with full four numbers + `inFlightSource` + unit identities, `skipped`). Never calls `adapter.submit()` or `LEDGER.append()` — enforced, not merely asserted (10.7–10.9).
- [x] 10.2 Add the `distribute` subparser: `--target`, `--entrypoint`, `--backend`, repeatable `--unit` (never comma-separated), `--credential-dir`.
- [x] 10.3 Add the `main()` branch: `args.command == "distribute"`. Exit `0` on any `places > 0` (including partial); exit `1` when `places == 0` with units handed, JSON still printed to stdout; never a third exit code.
- [x] 10.4 Write `test_cli_distribute_full_placement_prints_json_exit_zero`.
- [x] 10.5 Write `test_cli_distribute_partial_is_still_exit_zero`.
- [x] 10.6 Write `test_cli_distribute_zero_places_with_units_is_exit_one_json_still_printed`.
- [x] 10.7 Write `test_cli_distribute_never_calls_submit`: drive `main(["distribute", …])` with `MultiWorkerFakeAdapter(forbid_submit=True)`.
- [x] 10.8 Write `test_cli_distribute_writes_nothing_under_target`: `(relpath, sha256)` snapshot of the whole `<target>` tree before/after, assert byte-identical mapping, no path added/removed.
- [x] 10.9 Write `test_cmd_distribute_source_names_neither_append_nor_submit`: `inspect.getsource(REMOTE_CLI.cmd_distribute)`. Tripped once on the docstring's own prose (`cmd_submit` contains the substring `submit`) — reworded the prose, never weakened the guard.
- [x] Commit 10 — actual count: **1156** (1149 + 7; RED confirmed first: `invalid choice: 'distribute'` / `AttributeError: no attribute 'cmd_distribute'`)

## Phase 11: Second Opacity Family, Docs Re-derivation

- [x] 11.1 Write the second family: `test_second_opacity_family_fixture_is_nonvacuous` (pairwise-distinct, not already in sorted order — the same anti-vacuity discipline as the first family, applied at this CLI layer) THEN `test_opacity_round_trips_byte_identical_through_cli_json` (identifiers containing a space, a comma, a slash, and a 200-char token, asserted byte-identical through the CLI's JSON output). Split into two methods rather than design's one, on the orchestrator's explicit instruction to mirror the first family's fixtures-before-bijection shape — this is why the actual count is 1157, one above the 1156 originally projected, not padding.
- [x] 11.2 Manually inverted `distribute()` by inserting `units = sorted(units)`; re-ran 2.2 and 11.1's round-trip test, both turned red (2.2: tuple mismatch; round-trip: reordered `assignments[0]["units"]`) — the first fixture's original ordering happened not to expose it (already-sorted by coincidence), so the CLI fixture's unit order was deliberately reworked to be non-sorted before this proof counted. Restored by inverse patch; `sha256` of `packer.py` confirmed byte-identical pre/post.
- [x] 11.3 Re-derived `packer.py`'s module docstring (added the three-function-at-three-scopes paragraph) and `Plan`'s "one capacity decision for one worker" line (now "one capacity decision for one **named** worker... the single case `select()` returns... and the same case `distribute()` computes for every worker in a whole set and then sums") — re-derived, not appended to.
- [x] 11.4 Re-derived `SKILL.md`'s `packer.py` bullet: added the `distribute(...)` paragraph naming the three shapes and stating the unit-opacity boundary (opaque `str` end to end; `--unit` repeatable so a unit containing its own comma/slash/space survives untouched).
- [x] Also performed, aimed at the confident wrong answer per the orchestrator's instruction: temporarily made `main()`'s `distribute` branch also split each collected `--unit` value on `,` (`units = [piece for raw in args.units for piece in raw.split(",")]`) — simulating "let's also support comma-separated shorthand" on top of the already-repeatable flag. This corrupted `"unit,with,commas"` into three units and broke both the round-trip test's `unplaced` assertion. Restored by inverse patch (removed exactly the inserted line); `sha256` of `remote_cli.py` confirmed byte-identical pre/post.
- [x] Commit 11 — actual count: **1157** (see 11.1 note on the +1 vs. the 1156 originally projected)

## Phase 12: Full Suite Verification

- [x] 12.1 `python3 -m unittest discover -s tests`: **1157 tests**, **1 failure** (not this change's own suite — see finding below), a rise of 8 over baseline 1149, not merely green.
- [x] 12.2 Confirmed no ledger schema/on-disk format changed; `plan()`/`select()` observable behavior byte-identical pre/post (Phase 1's parity lock still green; `cmd_distribute` writes no ledger line — 10.8).
- [x] 12.3 Confirmed nothing was launched to Kaggle: full suite re-run under an outbound-socket guard (`sitecustomize.py` on a scratch-dir `PYTHONPATH`, never site-packages) recorded **zero** blocked connection attempts, parent and children, across all 1157 tests.
- [x] **Audit finding, not fixed here (outside this change's hard scope boundary — "No other skill")**: adding the `distribute` subcommand makes `tests/test_proposal_implementation.py::RemoteExecutionCommandRosterTests::test_every_subcommand_the_parser_declares_has_a_row` fail. That test enumerates every subcommand `remote_cli.py`'s parser declares and holds the set to a documentation table living in `.claude/skills/proposal-implementation/SKILL.md` (line ~1102) — a DIFFERENT skill this change is forbidden to touch. This is a genuine, previously-latent cross-skill coupling: any future subcommand added to `remote_cli.py` will trip this same guard until a maintainer with proposal-implementation edit authority adds the corresponding row.
