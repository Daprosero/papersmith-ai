# Tasks: The skill materializes, not the agent

**Size note**: this artifact exceeds the 530-word task-checklist budget by design decision, mirroring the design artifact's own documented 800-word overrun — recovering 42 scenarios, a five-part TDD protocol per lock, and an explicit 1a/1b non-shippable dependency at checklist granularity is the assignment, and folding it back under budget would repeat exactly the compression this change exists to reverse.

**Citation discipline**: every symbol below was located by name in `implementation_cli.py` and `tests/test_proposal_implementation.py` during this phase (`scaffold_gaps`, `cmd_apply`, `cmd_verify`, `COMMANDS`, `build_plan`, `IGNORE_ENTRIES`, `ignore_gaps`, `_is_own_bookkeeping` in `.claude/skills/_core/implementation/impl_guards.py`). Three findings not in the design, all verified against the source directly, none re-litigating the design's chosen shape:

1. `tests/test_proposal_implementation.py::MaterializeIsNotAProductionStepTests` (five methods, ~line 8202) locks the exact opposite of D2/D1 — it asserts `materialize.py`'s stem is **never** a CLI command, is never named in shipped kit assets or the README's flow diagram, and that the engine never imports it. `COMMANDS["materialize"]` collides with that lock by name.
2. `CommandRosterTests.test_every_command_dispatched_is_accounted_for` (~line 11830) asserts **exact set equality** `set(impl.COMMANDS) == DOCUMENTED_ELSEWHERE | write_verbs`, where `write_verbs` is a hardcoded literal `{"position", "discuss", "gate", "offer", "close", "step", "settle"}` — confirmed by reading the method. Adding `materialize` to `COMMANDS` fails this immediately unless `materialize` is added to one of the two sets and, if `write_verbs`, given a non-empty row in SKILL.md's `| Command | What it writes | Refuses on |` table (`command_rows()` requires it).
3. `WorkedInvocationRosterTests.test_every_command_the_cli_dispatches_has_a_worked_invocation` (~line 9693) reads `COMMANDS` via `dict_literal_keys()` (~line 9645), which walks the AST for a module-level `ast.Dict` **literal** assignment — confirmed by reading the helper. `COMMANDS` must stay a plain dict literal; building it programmatically (unpacking, `.update()`, comprehension) makes the helper raise, silently emptying the roster check rather than failing loudly on the new key.

All three are pre-existing tests the design's own chosen shape (`COMMANDS["materialize"]`) breaks by name collision or set-membership, not new guards. They must be retired/rewritten in the same commit that adds the key, not discovered later or deferred to a docs slice. Phase 0 and 1.3 task them explicitly.

**Sequencing note (informational, not a design constraint)**: the sibling change `maintenance-blocks-it-does-not-mix` also touches `CommandRosterTests`/`WorkedInvocationRosterTests`. No task below hardcodes today's exact `write_verbs`/`DOCUMENTED_ELSEWHERE` contents as an assumption — each edit task reads the current literal from source and adds to it, so whichever change lands second is unaffected by the other having already moved these sets.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 950–1250 (command ~150, receipt ~60, verify ~90, docs ~90, `MaterializeIsNotAProductionStepTests` rewrite ~60, `CommandRosterTests`/SKILL.md roster row ~20, tests ~450–650 for 42 scenarios × 5-part RED/GREEN/mutation protocol) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1a → PR 1b → PR 2 → PR 3 (feature-branch-chain; 1a is not independently mergeable) |
| Delivery strategy | ask-on-risk (default; not overridden by this launch) |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

**Why feature-branch-chain, not stacked-to-main**: PR 1a ships `UNRECORDED_SCAFFOLD` detection with no remedy. Per the design's own slice note, merging 1a alone to main strands every existing target (including `implementations/Domain_Adaptation` on this disk) with a refusal and no way out. Stacked-to-main would make 1a a mergeable unit; it is not one. 1a must target the tracker branch; 1b, 2, 3 stack on the previous branch until the tracker itself merges.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1a | `--stage scaffold` writer, receipt, `DESTINATION_CONFLICT` reuse, `STAGE_CANNOT_ANSWER`, anchors, `UNRECORDED_SCAFFOLD`/`SCAFFOLD_DRIFT` detection (no remedy), `MaterializeIsNotAProductionStepTests` rewrite | PR 1a (base: tracker branch) | `python3 -m unittest tests.test_proposal_implementation tests.test_skill_audit` | scratch git repo under `implementations/_ensayo_materialize_scaffold` (git-init → plan → approve → materialize → verify) | `git revert` the PR; receipt file is git-ignored in targets, so no target-side cleanup |
| 1b | `--authored`/`--adopt` modes, `NO_RECEIPT_ENTRY`/`NOT_A_KIT_DESTINATION`, vocabulary suite execution, operator migration of `implementations/Domain_Adaptation` | PR 1b (base: PR 1a branch) | `python3 -m unittest tests.test_proposal_implementation tests.test_skill_audit` | same scratch repo, plus a real `--adopt` run against `implementations/Domain_Adaptation` | `git revert`; adoption is a receipt-only write, reversible without touching target bytes |
| 2 | `--stage objects`, `object_gaps()`, verify enforcement widened to 14 destinations | PR 2 (base: PR 1b branch) | `python3 -m unittest tests.test_proposal_implementation tests.test_skill_audit` | scratch repo through step 8 (object map approved) | `git revert`; additive verify checks |
| 3 | `--stage harness`, `harness_gaps()`, verify reaches all 17, `materialize.py` deletion + fixture rewire, `npm test` regression | PR 3 (base: PR 2 branch, merges tracker → main) | `python3 -m unittest tests.test_proposal_implementation tests.test_skill_audit && npm test` | full scratch flow, `git init` to collectable test tree | `git revert`; `materialize.py` deletion is the one irreversible-in-spirit step — confirm fixtures rewired first |

---

## Phase 0: Existing-lock realignment (lands in the SAME PR/commit as `COMMANDS["materialize"]` — not a preceding gate, not a trailing docs slice)

- [x] 0.1 Read `MaterializeIsNotAProductionStepTests` in full (~lines 8202–8536) and confirm which of its five methods break on `COMMANDS["materialize"]` alone vs. on doctrine-text changes. DoD: written note listing method → breaks-on-what, checked into the PR description, not shipped as prose here.
- [x] 0.2 Rewrite `test_the_only_things_doctrine_tells_the_agent_to_run_are_cli_commands`: drop the `assertNotIn(harness.stem, impl.COMMANDS, ...)` clause (the fact it asserted is now false by design) while keeping the rest of the method (doctrine only tells the agent to run real CLI commands) intact. Before: green under old doctrine. After: green with `materialize` present in `impl.COMMANDS`.
- [x] 0.3 Confirm (do not necessarily edit) `test_no_asset_the_scaffold_ships_names_the_forge_s_own_harness` and `test_no_flow_diagram_draws_the_harness_as_a_step` stay true: kit assets and README diagrams must not gain a mention of `materialize.py`'s name as a side effect of SKILL.md's step-5 prose change. If SKILL.md step 5 now says `Run \`implementation_cli.py materialize --stage scaffold\`` (not `materialize.py`), these stay green untouched.
- [x] 0.4 Confirm `test_the_production_engine_never_reaches_the_harness` stays true after `materialize.py` becomes a thin shim: the shim must import from `implementation_cli`, and `implementation_cli.py` must not import or shell `materialize.py`'s module name. This constrains the shim's implementation shape in Phase 1/3, not just its own test.
- [x] 0.5 Rename the class to state the new fact it holds (e.g. `MaterializeScriptIsNotACommandTests` or similar reflecting: the standalone script stays test-only; the CLI command is the production path) and update its docstring's opening claim accordingly. DoD: `python3 -m unittest tests.test_proposal_implementation -k Materialize` fails today (old class name/assertion), passes after 1.1–1.4 land.
- [x] 0.6 Read `CommandRosterTests.test_every_command_dispatched_is_accounted_for`'s current `write_verbs`/`DOCUMENTED_ELSEWHERE` literals directly from source (do not trust this document's snapshot — another change may have moved them since). Add `materialize` to `write_verbs`: it writes files and refuses on multiple codes, matching the class's own stated criterion ("narrowed to the commands that write"), unlike the 9 `DOCUMENTED_ELSEWHERE` members which predate this change or carry their own roster elsewhere.
- [x] 0.7 Add a `materialize` row to SKILL.md's `| Command | What it writes | Refuses on |` table with non-empty "writes" and "refuses" cells (`command_rows()` asserts both non-empty). DoD: `python3 -m unittest tests.test_proposal_implementation -k CommandRosterTests` fails once `COMMANDS["materialize"]` exists and before 0.6/0.7 land; passes after.
- [x] 0.8 Confirm `COMMANDS` stays a single module-level dict **literal** in `implementation_cli.py` (no unpacking, `.update()`, or comprehension) — `dict_literal_keys()` walks the AST for exactly that shape and raises `AssertionError` rather than failing loudly on a missing key if the shape changes. This constrains 1.3.4's implementation, not just a test.

## Phase 1 — PR 1a: writer, receipt, preflight refusals (not independently shippable)

### 1.1 `--seed` CLI-home decision (blocks 1.2)
- [x] 1.1.1 Confirm `build_plan`/`cmd_plan` carries no seed field (grounded: `build_plan`'s returned dict has `renames/createDirs/moves/referenceUpdates/conflicts/unclassified/scaffoldFiles/reorganization` — no seed key) and `seed` elsewhere in `implementation_cli.py` is only the pip build-backend step. Decide: `--seed` becomes a required flag on `materialize --stage scaffold` (design's fallback) vs. extending `cmd_plan`'s payload to carry a declared seed the operator supplies at plan time. Record the decision and its one-sentence reason in the PR description; this is a real decision, not a rubber stamp of the design's fallback.

### 1.2 RED — writer preflight refusals (before `cmd_materialize` exists)
- [x] 1.2.1 Write `test_materialize_refuses_without_approved_plan` (M1): `materialize --stage scaffold` with no approved plan on a fresh target → expect `PLAN_MISMATCH`/`PLAN_STALE`, no files written, no receipt. **Observe red for the right reason** first: run against pre-change CLI and confirm the failure is "unknown command" or "no refusal raised", not a fixture bug.
- [x] 1.2.2 Write `test_materialize_refuses_without_git_repo` (M2): target dir with no `.git` → `NOT_A_GIT_REPO`, no repo created.
- [x] 1.2.3 Write `test_materialize_refuses_dirty_worktree` (M3, lost scenario): staged-only edit present → `DIRTY_WORKTREE`.
- [x] 1.2.4 Write `test_materialize_refuses_outside_workspace` (M4, lost scenario): target resolves outside `WORKSPACE` → `OUTSIDE_WORKSPACE`.
- [x] 1.2.5 Write `test_materialize_stage_scaffold_refuses_destination_conflict` (M5): a destination in the computed set appears mid-run (simulate via monkeypatched race or pre-seeded conflicting file after set computation) → `DESTINATION_CONFLICT`, whole stage refused, **no receipt written** (fail-closed, no partial receipt).
- [x] 1.2.6 Write `test_materialize_pre_existing_destination_not_in_set_succeeds` (M6 — decides whether D1 is a trap): one of the 11 scaffold files already exists by hand (no receipt); `--stage scaffold` runs and **succeeds**, writing the remaining 10/anchors, leaving the pre-existing file untouched and unrecorded (it becomes `UNRECORDED_SCAFFOLD` material for 1.4, not a conflict here).
- [x] 1.2.7 Write `test_materialize_mid_write_failure_aborts_cleanly` (M7, lost): simulate an I/O failure partway through the copy loop → `APPLY_ABORTED`, `git reset -q --hard` + `git clean -qfd` (no `-x`) run, no receipt entry for any file from that invocation, `.venv/`-equivalent ignored dir survives.
- [x] 1.2.8 Write `test_materialize_stage_cannot_answer_on_unresolved_token` (M8, lost — `STAGE_CANNOT_ANSWER` dropped by the spec entirely): a scaffold template still carrying an unresolved `{{TOKEN}}` after substitution → `ast.parse` fails, refuse `STAGE_CANNOT_ANSWER` naming the file, promoted from `writable_at_scaffold_time`'s current silent skip.

### 1.3 GREEN — implement `cmd_materialize --stage scaffold`
- [x] 1.3.1 Add `cmd_materialize` to `implementation_cli.py`: three-mode dispatch (`--stage`/`--authored`/`--adopt`, exactly one required — refuse on zero or multiple given), `--stage scaffold` branch only in this task. Run over `resolve_target` + `require_clean_worktree`, gate on approved plan per `cmd_apply`'s `PLAN_MISMATCH`/`PLAN_STALE` pattern.
- [x] 1.3.2 Compute the stage's destination set as `[d for d in scaffold_gaps(target, name) if not (target / d).exists()]`; reuse `cmd_apply`'s `DESTINATION_CONFLICT` raise verbatim for a mid-run collision; reuse the abort sequence (`git reset -q --hard`, `git clean -qfd`, `Refused("APPLY_ABORTED", ...)`) for a copy failure.
- [x] 1.3.3 Add the `STAGE_CANNOT_ANSWER` refusal by promoting `writable_at_scaffold_time`'s existing `ast.parse` gate from silent skip.
- [x] 1.3.4 Add `"materialize": cmd_materialize` as a literal key inside the existing `COMMANDS = {...}` dict literal (16 → 17, per 0.8 — no programmatic construction) and the argparse arm in `main()` for `--stage`/`--authored`/`--adopt`/`--plan`/`--seed` (per 1.1's decision). Land this in the same commit as 0.6/0.7 (`CommandRosterTests`) — a commit adding the key without them leaves the suite red with no intermediate shippable state.
- [x] 1.3.5 Add a worked `implementation_cli.py materialize --stage scaffold ...` invocation block to `references/usage.md` (`WorkedInvocationRosterTests.test_every_command_the_cli_dispatches_has_a_worked_invocation` requires every dispatched key to have one). Also add the `--target`/`--name`-equivalent flags `materialize` actually accepts so a parser-acceptance test analogous to `test_the_probe_invocation_uses_flags_the_real_parser_accepts` can run against it.
- [x] 1.3.6 Run 1.2.1–1.2.8, 0.6, 0.7, 1.3.5's roster/invocation tests, and confirm each now passes for the reason stated, not a fixture accident.

### 1.4 RED then GREEN — receipt write and anchors
- [x] 1.4.1 Write `test_receipt_written_last_matches_bytes` (M12): after a successful stage, `<Name>/.implementation/materialization.json`'s `writtenSha256` per entry equals sha256 of the bytes on disk.
- [x] 1.4.2 Write `test_receipt_records_kit_source_and_source_sha256` (M13).
- [x] 1.4.3 Write `test_second_stage_appends_not_truncates` (M14, lost): run `--stage scaffold` then a second stage invocation (simulated) — first stage's entries survive in the receipt, no duplicate, no truncation.
- [x] 1.4.4 Write `test_anchor_rows_merge_not_overwrite` (M10, lost — D4): pre-existing `.gitignore` with unrelated entries → merged, not refused, `kind: "anchor"` entry with no `writtenSha256`, all pre-existing entries preserved; re-running adds nothing new.
- [x] 1.4.5 Implement receipt read/write/replace (atomic, written last) with entry `kind` ∈ `materialized | anchor`; `.gitignore`/`pyproject.toml` merge logic keyed off `ignore_gaps()`/`pytest_anchor_missing()`. Run 1.4.1–1.4.4 to green.
- [x] 1.4.6 Write and green `test_rerun_after_rollback_succeeds` (M11 merged / D5): materialize, `git checkout .` (receipt survives — it is git-ignored per `IGNORE_ENTRIES` carrying `.implementation/`), files gone; re-running `--stage scaffold` succeeds, stale receipt entries for the now-absent paths are replaced, not read as drift.

### 1.5 RED then GREEN — `SCAFFOLD_DRIFT`/`UNRECORDED_SCAFFOLD` detection in `cmd_verify` (11 scaffold destinations only)
- [x] 1.5.1 Write `test_verify_refuses_scaffold_drift_on_hand_edit` (S1) — **mutation choice matters**: the discriminating mutation is "change one byte and restore the file's mtime and size", not "delete the file" (a weaker lock survives delete-only). Clear `__pycache__` for any touched module before re-running to defeat the stale-`.pyc` trap.
- [x] 1.5.2 Write `test_verify_no_drift_on_reverted_edit` (S2, lost — positive case, drift is a byte comparison not an event log): edit then restore original bytes exactly → `verify` does **not** refuse.
- [x] 1.5.3 Write `test_verify_reports_gap_not_drift_on_deleted_recorded_file` (S3, lost / D5): delete a recorded destination → reported through the existing gap channel, never `SCAFFOLD_DRIFT`.
- [x] 1.5.4 Write `test_verify_no_drift_on_edited_anchor` (S4, lost / D4): user edits `.gitignore` after materialize → no drift; the anchor check re-derives presence via `ignore_gaps()`, not a hash.
- [x] 1.5.5 Write `test_verify_names_all_drifting_destinations` (S5, lost): drift on 3 of 11 → all 3 named, not just the first.
- [x] 1.5.6 Write `test_verify_no_drift_when_kit_template_moves` (S6, lost — **must NOT refuse**, explicitly required by the launch brief): change the kit's source template under `assets/kit/`, leave the target's on-disk bytes untouched → not drift; `sourceSha256` divergence reported as an informational field only, target is not stale because the forge moved.
- [x] 1.5.7 Write `test_verify_refuses_unrecorded_destination` (U1): one of the 11 present, no receipt entry → `UNRECORDED_SCAFFOLD` naming the path.
- [x] 1.5.8 Write `test_verify_ignores_non_kit_file_in_same_directory` (U3, lost — **without it the refusal is noise**, explicitly required): `tests/test_my_thing.py` beside the 11 kit destinations → not flagged; only the 11 (this slice) are in domain.
- [x] 1.5.9 Write `test_verify_migration_all_scaffold_destinations_unrecorded` (U2, lost — **the migration case**, explicitly required): all 11 present, zero receipt entries (a target scaffolded before this change existed) → all 11 named, remedy stated once, not 11 times.
- [x] 1.5.10 Implement `SCAFFOLD_DRIFT`/`UNRECORDED_SCAFFOLD` in `cmd_verify`'s `structure` block, scoped to the 11 scaffold destinations for this PR. Run 1.5.1–1.5.9 to green, each via inversion (break the guarded fact on purpose, watch the refusal fire) after first observing red against the pre-guard code.
- [x] 1.5.11 Write and green `test_verify_ok_when_all_scaffold_recorded_and_matching` (V2, lost — the positive case, **required**: "without it the widening can pass by always failing"): all 11 present, recorded, matching → `structure.status == "ok"`.

## Phase 2 — PR 1b: remedies, migration, vocabulary run (completes slice 1)

### 2.1 RED then GREEN — `--authored`
- [x] 2.1.1 Write `test_authored_declares_new_sha_and_clears_drift` (A2): after a step-9-style hand-authored edit (simulated on a scaffold-stage file for this slice, since step-9 destinations arrive in slice 2/3), `--authored <path>` records the new sha256, `kind: "authored"`, later `verify` clean.
- [x] 2.1.2 Write `test_silent_authoring_still_drifts` (A1, merged — confirm, do not just trust the spec): author over without declaring, even after a later plan is approved → still `SCAFFOLD_DRIFT`.
- [x] 2.1.3 Write `test_authored_on_no_receipt_entry_refuses` (A3, lost): `--authored <path>` on a path the receipt does not carry → `NO_RECEIPT_ENTRY` (route to `--adopt` instead).
- [x] 2.1.4 Write `test_second_silent_edit_drifts_again` (A4, lost — **explicitly required, "without it the seal releases once and forever"**): `--authored` releases the seal once; a second undeclared edit after that → drifts again. Release is per-declaration, not permanent.
- [x] 2.1.5 Write `test_authored_succeeds_on_dirty_tree` (A5, lost): `--authored` does not require a clean worktree (precedent: `_is_own_bookkeeping` in `.claude/skills/_core/implementation/impl_guards.py`).
- [x] 2.1.6 Write `test_authored_and_stage_together_refuses` (A6, lost): `--authored` with `--stage` in one invocation → refuse; modes are mutually exclusive.
- [x] 2.1.7 Write `test_authored_on_path_outside_kit_refuses` (part of NOT_A_KIT_DESTINATION domain): `--authored`/`--adopt` on a path outside the 17 (11 for this slice) → `NOT_A_KIT_DESTINATION`.
- [x] 2.1.8 Implement `--authored` mode: no file write, no plan gate, no clean-worktree requirement; re-seal one receipt entry to `kind: "authored"`. Run 2.1.1–2.1.7 to green, inversion-proven.

### 2.2 RED then GREEN — `--adopt`
- [x] 2.2.1 Write `test_adopt_records_current_sha_kind_adopted` (U4): entry `kind: "adopted"`, current sha256, distinguishable from `materialized`/`authored`.
- [x] 2.2.2 Write `test_adopt_on_already_recorded_path_refuses` (U5, lost): `--adopt` on a path with an existing entry → refuse; adoption is not a re-seal (route to `--authored`).
- [x] 2.2.3 Write `test_adopt_outside_kit_refuses` (U6, lost): reuses `NOT_A_KIT_DESTINATION`.
- [x] 2.2.4 Write `test_adopt_on_absent_path_refuses` (U7, lost): `--adopt` on a path with no bytes on disk → refuse; nothing to adopt.
- [x] 2.2.5 Write `test_verify_clean_after_adopt` (U8, merged): after adoption, `verify` no longer refuses that path.
- [x] 2.2.6 Implement `--adopt` mode. Run 2.2.1–2.2.5 to green.

### 2.3 Degraded-guarantee wording (3 required sites, per design)
- [x] 2.3.1 Add the `UNRECORDED_SCAFFOLD` row + `--adopt` remedy paragraph to `references/usage.md`'s refusal table, stating: adoption records who is responsible for the bytes, not that the bytes came from the kit.
- [x] 2.3.2 Add the same statement to `materialize --adopt`'s argparse help text in `main()`.
- [x] 2.3.3 Add the same statement to the JSON output an `adopted` entry produces. DoD: `python3 -m unittest tests.test_proposal_implementation -k Adopt` (or the closest matching filter) exercises all three sites; a grep-based test asserting the phrase appears in all three is acceptable if no existing test covers this.

### 2.4 Vocabulary — run, not argue (explicitly required)
- [x] 2.4.1 Run `python3 -m unittest tests.test_proposal_implementation -k Vocabulary` and `python3 -m unittest tests.test_skill_audit -k Vocabulary` (i.e. `ForgeVocabularyDerivedGuardTests` in `tests/test_proposal_implementation.py` and `VocabularyTests` in `tests/test_skill_audit.py`) **after** every new identifier (`materialize`, `--stage`, `--authored`, `--adopt`, `--seed`, `scaffold`, `objects`, `harness`, `DESTINATION_CONFLICT`, `SCAFFOLD_DRIFT`, `UNRECORDED_SCAFFOLD`, `STAGE_CANNOT_ANSWER`, `NO_RECEIPT_ENTRY`, `NOT_A_KIT_DESTINATION`, receipt field names) is shipped in `.py`/`.md`/`.json`. Record pass/fail in the PR description as the verdict — the design's derivation (denylist = `{creda, mil, schedules, conditional, global, renyi, ceiling, bags, contamination, latent}`) is evidence to check against, not a substitute for running it. Flag any accidental use of the word "global" in new prose before this runs (`global` is on the live denylist).

### 2.5 Operator migration — adopt `implementations/Domain_Adaptation`

**Blocked from this worktree, not skipped by choice.** `implementations/*` is
gitignored (`!implementations/.gitkeep` is the one tracked exception), so
`Domain_Adaptation` and `_ensayo_position` exist only in the main checkout's
untracked working tree, not in this worktree's filesystem at all (confirmed:
`ls implementations/` here shows nothing but `.gitkeep`). The apply launch
brief for this session explicitly restricts edits to this worktree and bars
touching the main checkout beyond reading its interpreter, so the real
operator action below cannot be performed from here without violating that
boundary. The mechanism itself (`--adopt`) is implemented and covered by
`MaterializeAdoptTests` in `tests/test_proposal_implementation.py`, including
the migration case at the unit level
(`MaterializeVerifyScaffoldDriftTests.test_a_target_scaffolded_before_this_change_is_fully_unrecorded`).
Remains for an operator with access to the main checkout.

- [ ] 2.5.1 After 2.1–2.2 land, as a real operator action (not a unit test): run `verify` against `implementations/Domain_Adaptation` on this disk and confirm all 11 scaffold destinations now refuse `UNRECORDED_SCAFFOLD` (the migration case, U2, made concrete).
- [ ] 2.5.2 Run `--adopt` per path against `implementations/Domain_Adaptation`'s 11 scaffold destinations, one at a time, deliberately (no batch/auto-adopt — the design forbids it: auto-adopting would record engine confidence in bytes it never saw). Confirm `verify` reads clean afterward for the scaffold group.
- [ ] 2.5.3 Do the same for `implementations/_ensayo_position` if it carries the same 11 destinations; do not alter its `_`-prefix exclusion from vocabulary rule B while touching it.

## Phase 3 — PR 2: objects stage (slice 2)

- [ ] 3.1 RED: `test_materialize_stage_objects_refuses_before_object_map` (M9, lost): `--stage objects` before the step-8 object map exists → refuses; `{{FUNCTION_NAME}}`/`{{INVARIANT_ID}}`/`{{EXPECTATION}}` tokens have no answer yet (ties to `MaterializeWritesStageOneTests`'s existing finding that these three files do not survive `ast.parse` at scaffold time).
- [ ] 3.2 GREEN: implement `--stage objects` over `src/<Package>/<module>.py`, `tests/test_invariants.py`, `tests/test_synthetic.py`; add `object_gaps()` beside `scaffold_gaps()`.
- [ ] 3.3 RED then GREEN: extend `SCAFFOLD_DRIFT`/`UNRECORDED_SCAFFOLD`/`STAGE_CANNOT_ANSWER`/`NO_RECEIPT_ENTRY`/`NOT_A_KIT_DESTINATION` to the 3 objects destinations (reuse 1.5's/2.1's/2.2's test shapes, new fixture data).
- [ ] 3.4 RED then GREEN: `test_structure_status_names_missing_harness_before_step12` and its objects equivalent (V4, lost — explicitly required, "an enforcer lands before its writer" expressed as a scenario): objects/harness destinations absent before step 8/12 are reached → reported as gaps, must not make the earlier flow (scaffold-only) unrunnable.
- [ ] 3.5 Update SKILL.md step 9 table to a `materialize --stage objects` invocation; `WorkedInvocationRosterTests` requires a real invocation in `references/usage.md` too — add it.

## Phase 4 — PR 3: harness stage, cleanup (slice 3)

- [ ] 4.1 RED then GREEN: `--stage harness` over `src/<Package>_Benchmark/benchmark.py`, `verdict.py`, `<Name>/Notebooks/probe.ipynb`; `harness_gaps()`; verify enforcement for these 3 (reuse 1.5's shapes).
- [ ] 4.2 RED then GREEN: `test_structure_status_ok_across_all_17` (V1/V3 merged, extended to 17): `structure.status` reads `"ok"` only when none of the 17 has drift/unrecorded; a harness destination never materialized → not `"ok"`, names it.
- [ ] 4.3 Update SKILL.md's harness-wiring table to a `materialize --stage harness` invocation; confirm `wiring.py` is untouched (bespoke-authored, out of scope per SKILL.md's own statement).
- [ ] 4.4 Rewire `MaterializeWritesStageOneTests` and any other fixture calling `materialize.py`'s direct entrypoint (`[sys.executable, materialize.py, target, name, seed]`) to go through `cmd_materialize` instead; confirm behavior is identical (same tree, same `ast.parse`-exempt tokens for objects-stage files).
- [ ] 4.5 Delete `materialize.py`; re-run all of Phase 0's realignment tests (`harness()` helper in the renamed class asserts exactly one non-engine script exists in `scripts/` — confirm it still finds exactly one, or that the class's own premise is retired if no second script remains).
- [ ] 4.6 Run full suite: `python3 -m unittest tests.test_proposal_implementation tests.test_skill_audit && npm test`. This is the only phase touching the Node suite; confirm it was not silently skipped by the misconfigured `openspec/config.yaml` `test_command` (lines 19, 21, 25 all pin `test_extract_pdf.py` only and reach none of this work — do not trust it as the definition of done anywhere in this change).

---

## Key Learnings

1. `tests/test_proposal_implementation.py::MaterializeIsNotAProductionStepTests` asserts the exact opposite of D2 and was not in the design's file-change table; it must be rewritten in the same commit that adds `COMMANDS["materialize"]`.
2. `CommandRosterTests.test_every_command_dispatched_is_accounted_for` asserts exact set equality against a hardcoded `write_verbs` literal, and `WorkedInvocationRosterTests` requires `COMMANDS` to stay a parseable dict literal — both verified by reading the methods, both must move in the same commit as the new key, and neither was in the design's file-change table.
3. `build_plan` carries no seed field today, confirming design's `--seed` open question is real, not a formality — grep found `seed` only in an unrelated pip build-backend step.
4. `openspec/config.yaml` pins its test command to `test_extract_pdf.py` in three places (lines 19, 21, 25); every task's DoD must name `python3 -m unittest tests.test_proposal_implementation tests.test_skill_audit` and `npm test` explicitly rather than trusting the configured runner.
5. `scaffold_gaps()`'s 13 rows split into 11 sealed copies and 2 merge anchors (`.gitignore`, `pyproject.toml`); anchors get `kind: "anchor"` receipt entries with no byte seal, checked by re-derived presence, not a hash.
6. Slice 1 cannot ship as one mergeable unit under the 400-line budget without stranding every existing target — PR 1a (writer + detection) and PR 1b (remedies + migration) must chain on a tracker branch, not merge to main independently.
