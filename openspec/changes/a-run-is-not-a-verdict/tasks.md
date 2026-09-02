# Tasks: A Run Is Not A Verdict

Design supersedes proposal/spec on all five corrected points; this checklist
follows the design. `strict_tdd: true` — every lock RED before GREEN, run with
`PYTHONDONTWRITEBYTECODE=1` and `__pycache__` purged. No task writes under
`implementations/`.

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1050–1120 (own tally, corroborates design's ~1120) |
| 400-line budget risk | High *(against the session's 1400: ~80% consumed, ~280–350 headroom)* |
| Chained PRs recommended | No |
| Suggested split | single PR — `size-exception` |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

**Why no split despite High risk**: verified — a witness kind (Phase 1) without
its digest (Phases 2–4) is a verdict that never expires; a refusal (Phase 5)
without its roster classification fails `test_every_gating_refusal_is_classified`
on its own. No phase boundary here is an independently mergeable, non-broken
state. `ask-on-risk` + High risk means the owner decides before `sdd-apply`:
accept `size-exception` for one PR, or direct a different split against the
atomicity risk above.

### Suggested Work Units (sequential, one PR)

| Unit | Goal | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|
| 0 | Measure both baselines | `.venv/bin/python -m unittest discover -s tests` / `npm test` | N/A — measurement only | N/A, no code change |
| 1 | `step` kind + leveled guard | `unittest tests.test_implementation_core -k Derive or Operand or Levelable` | N/A — pure core, no subprocess | Revert `impl_position.py` + its test edits |
| 2 | `suite_digest` | `unittest tests.test_proposal_implementation -k SuiteDigest` | N/A — filesystem-only hashing | Revert new function + its tests |
| 3 | `cmd_step` digest field | `unittest tests.test_proposal_implementation -k CmdStep` | `implementation_cli.py step` against a fixture target | Revert event field + docstring |
| 4 | Evidence parity (3 builders) | `unittest tests.test_proposal_implementation -k StepVerdicts or Parity` | `implementation_cli.py gate/probe/verify` against a fixture target | Revert `_step_verdicts` + 3 call sites |
| 5 | `POSITION_STEP_UNKNOWN` refusal | `unittest tests.test_proposal_implementation -k GatingRefusalRoster or StepOperand` | `implementation_cli.py position` against a fixture target with a bad `@step` operand | Revert helper + raise + roster entries |
| 6 | Docs | `unittest tests.test_proposal_implementation -k RosterDoctrine or CountsItActuallyHolds` | N/A — doc-bound tests only | Revert `SKILL.md`/`usage.md` hunks |
| 7 | Full verification | full suites + `FORGE_VOCABULARY_FLOOR` | Both suites, `git status` | N/A, verification only |

## Phase 0: Baselines — non-negotiable, first

- [x] 0.1 Run `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_*.py'` on `forge/a-rung-is-never-skipped @ 5243b8f`; record the exact `OK`/`skipped=N` line in this file before any RED.
- [x] 0.2 Run `npm test`; record the exact pass count here before any RED.
- [x] 0.3 `git status` — confirm clean, nothing under `implementations/` pending.

**Baselines measured this session:**
- Python: `Ran 2144 tests in 259.754s` — `OK (skipped=3)`. Matches expected count exactly.
- Node: `tests 385`, `pass 385`, `fail 0`, `cancelled 0`, `skipped 0`. Matches expected count exactly.
- `git status --porcelain=v1` before any RED: only `?? openspec/changes/a-run-is-not-a-verdict/` (planning artifacts, untracked, not under `implementations/`). Nothing under `implementations/` pending. Confirmed again after the Python suite run (the run prints `materialized Method into .../implementations/_materialize_*` paths to stdout but those are outside this repository tree — `git status` after the run is unchanged).

## Phase 1: Core witness kind — `impl_position.py`

- [x] 1.1 RED: assert `"step" in WITNESS_KINDS` and `"step" in OPERAND_REQUIRED_KINDS` — fails today (absent from both frozensets).
- [x] 1.2 GREEN: add `"step"` to `WITNESS_KINDS` (line 81) and `OPERAND_REQUIRED_KINDS` (line 99); update `OperandRequiredKindsTests.test_record_is_excluded_the_rest_are_required` (`tests/test_implementation_core.py:876-881`) frozenset literal to `{"notebook", "rehearsal", "shard", "step"}`.
- [x] 1.3 RED: `_derive_step` dict-reader — missing key → `None`; `stepVerdicts[op] is False` → `False`. Mutation: flip the `False`-branch return to `None` — proves the lock catches exactly that flip, not a generic falsy-value bug.
- [x] 1.4 GREEN: implement `_derive_step(evidence, operand)` reading only `evidence["stepVerdicts"][operand]`; register in `_DERIVERS["step"]` (~line 529); no `_LEVEL_DERIVERS["step"]` entry.
- [x] 1.5 RED: `@step:level` item through `derive()` → `Refused("POSITION_WITNESS_NOT_LEVELABLE", ...)`, not `KeyError`. Mutation: revert the `.get()` guard to bare `_LEVEL_DERIVERS[kind]` — test fails with uncaught `KeyError`.
- [x] 1.6 GREEN: replace both `_DERIVERS[kind]` (line 747) and `_LEVEL_DERIVERS[kind]` (line 753) lookups in `derive()` with one shared `.get()`-based resolver raising `Refused("POSITION_WITNESS_NOT_LEVELABLE", ...)` naming the item and the kinds that do carry a rung.
- [x] 1.7 Add a contract test stating the two-state arm's guard is reachable only from a direct `derive()` call (hand-built item dict), never from real markdown — `parse_items` never emits a two-state item with an unregistered kind, so this is structural insurance, not a markdown-reachable path. State this in the test docstring.

**Phase 1 evidence**: `StepDeriveTests`/`WitnessNotLevelableTests`/`OperandRequiredKindsTests` in `tests/test_implementation_core.py`, 9 tests, all RED-then-GREEN with mutation proofs recorded in apply-progress. Full `test_implementation_core.py` re-run: 94/94 OK, no regressions.

## Phase 2: Suite digest — `implementation_cli.py`

- [x] 2.1 RED: adding `tests/test_x.py` moves `suite_digest`, `source_digest` unchanged; adding `tests/conftest.py` moves `suite_digest` (proves the walk is `rglob("*.py")`, not `test_*.py`); creating `tox.ini` moves the digest (absence was a value). Mutation: swap the walk to `rglob("test_*.py")` under `tests/` — only the conftest-scenario test catches it; a generic "any test file" lock would survive.
- [x] 2.2 GREEN: implement `suite_digest(target)` beside `source_digest` (after ~line 4707) — `rglob("*.py")` under `src/` and `tests/`, skip `__pycache__`; plus `requirements.txt`, `pyproject.toml`, `setup.cfg`, `tox.ini`, `pytest.ini` each folded through `current_file_digest`/`ABSENT_FILE_DIGEST` (no branching skip). Docstring names `source_digest` and states why they don't merge.

**Phase 2 evidence**: `SuiteDigestTests` in `tests/test_proposal_implementation.py`, 8 tests, RED-then-GREEN. Mutation proof recorded in apply-progress: swapping the `tests/` walk to `rglob("test_*.py")` failed only `test_adding_conftest_moves_the_digest_proving_the_walk_is_not_test_star`; the weaker "any test file" lock survived unchanged, confirming the conftest scenario is the strength-proving mutation, not the generic one.

## Phase 3: Ledger currency — `cmd_step`

- [x] 3.1 RED: `cmd_step`'s ledger event carries a `suiteDigest` field, written unconditionally regardless of outcome. **Deviation from the literal brief, recorded**: the brief's "folds `None`/always-`True` stub" language describes the fold/currency-comparison lock, which structurally belongs to `_step_verdicts` and is proven in Phase 4 (`test_a_stale_step_derives_unmeasured_not_false` at the core layer, plus Phase 4's own stale-beats-red mutation) — `cmd_step` itself never reads back or compares a digest, only writes one. Phase 3's own RED/GREEN instead locks that the WRITE happens, unconditionally: `CmdStepDigestTests` (2 e2e tests via the real CLI) — missing key on both `returned` and `raised` outcomes before GREEN.
- [x] 3.2 GREEN: add `event["suiteDigest"] = suite_digest(target)` unconditionally to the event dict in `cmd_step`; rewrote the "No digest field" docstring paragraph to scope its reasoning to self-stamping steps (a bare runner has no other record of what it ran against). Also updated the one pre-existing test that pinned the old "no digest key at all" behavior (`test_a_passing_step_is_recorded_with_exit_zero_and_no_digest_field` → renamed `..._and_a_digest_field`, its literal absence-assertion replaced) — its assertion is a description of code behavior this change deliberately reverses, not a record of something that happened, so updating it is in scope (skill's "never edit a record to make it pass" rule governs artifacts asserting an event occurred, not test expectations of code shape).
- [x] 3.3 Confirmed via a lock I added (no pre-existing `returned_keys(CLI, "cmd_step")` test existed under that exact name — measured, not assumed): `test_the_returned_response_dict_never_gains_suite_digest` asserts `"suiteDigest" not in returned_keys(CLI, "cmd_step")`. Green both before and after Phase 3's GREEN (the response dict was never touched).

**Phase 3 evidence**: `CmdStepDigestTests` (3 tests) in `tests/test_proposal_implementation.py`, plus 1 renamed/updated test in `StepCommandTests`. Mutation proof: gating `event["suiteDigest"]` on `outcome == "returned"` failed only `test_a_raised_step_event_also_carries_a_suite_digest`; the "returned" happy-path lock survived unchanged — the weaker lock that would have missed this bug.

## Phase 4: Evidence assembly — three builders agree

- [x] 4.1 RED: parity test — one ledger fixture, `_position_write_evidence`'s, `cmd_probe`'s inline dict's, and `cmd_verify`'s inline dict's `stepVerdicts` must be byte-identical. Mutation: wire only `_position_write_evidence` — the parity test fails even though all 8 of its own callers would individually pass.
- [x] 4.2 RED: stale-beats-red — latest event `outcome: "returned"` but mismatched digest → `None`, not `True`; latest event `outcome: "raised"` but mismatched digest → `None`, not `False`. Mutation: reorder the fold to check outcome before digest — the stale-red case flips to `False` and the test fails.
- [x] 4.3 GREEN: implement `_step_verdicts(target, name)` — folds `kind: "step"` events latest-wins per step name; digest comparison decided before outcome; short-circuits to `{}` when no `kind: "step"` event exists (never calls `suite_digest` for a target that never ran `step`).
- [x] 4.4 GREEN: wire `evidence["stepVerdicts"] = _step_verdicts(target, name)` into `_position_write_evidence` (one edit, all 8 callers fixed at once), into `cmd_probe`'s inline evidence dict, and into `cmd_verify`'s inline evidence dict.

**Phase 4 evidence — parity proven, not asserted**: `StepVerdictsTests` (8 pure-fold unit tests) + `StepVerdictsParityTests` (2 e2e tests spying on the exact `evidence` dict each of the three builders hands to `position_state`, via `mock.patch.object(impl, "position_state", side_effect=spy)` wrapping the real function) in `tests/test_proposal_implementation.py`. `test_all_three_builders_agree_on_step_verdicts` computed `_position_write_evidence(box, "Method")["stepVerdicts"]`, captured `cmd_probe`'s and `cmd_verify`'s own inline `stepVerdicts` via the spy, and asserted `json.dumps(..., sort_keys=True)` equality pairwise across all three against one real ledger fixture (a `step` run through the actual CLI subprocess) — result: `{"run_suite": True}` for all three, GREEN. Mutation proof (task 4.1): dropping the `stepVerdicts` wiring from `cmd_probe`'s and `cmd_verify`'s inline dicts (leaving only `_position_write_evidence` wired) failed the parity test with `KeyError: 'stepVerdicts'`; a weaker check — calling `_position_write_evidence(root, "Method")` in isolation and confirming it reports `stepVerdicts` — still passed under the same mutation, confirming only the cross-builder parity test catches the exact defect the design's "All three evidence builders share one fold" decision names. Mutation proof (task 4.2): reordering the fold to check `outcome == "raised"` before the digest comparison failed only `test_a_stale_digest_beats_a_raised_outcome_folds_to_none` (`False` instead of `None`); the adjacent `test_a_stale_digest_beats_a_returned_outcome_folds_to_none` (a weaker, one-directional lock) survived unchanged.

## Phase 5: Unknown-operand refusal — `cmd_position`

- [x] 5.1 RED: `@step nosuch` where `__steps__` has no `nosuch`, through `cmd_position` → `Refused("POSITION_STEP_UNKNOWN", ...)` naming the real declared steps. Confirmed today's (pre-change) behavior: silently derives `unmeasured`, no refusal, exit 0. Reachable: `parse_items` validates witness *kind* only, never the operand string, confirmed by reading `parse_items` (impl_position.py:380-384) — it checks `kind not in WITNESS_KINDS` only.
- [x] 5.2 GREEN: `_step_operand_detail(items, steps) -> str | None` (mirrors `_skipped_rung_detail`'s shape) returns a detail or `None`; `raise Refused("POSITION_STEP_UNKNOWN", detail)` stays textually inside `cmd_position`'s body (after `_skipped_rung_detail`'s own raise, before `derive()`) so `raised_refusal_codes` finds it. Second arm: `@step` items when `__steps__` is empty reuse `STEPS_UNDECLARED` verbatim (same code, same message text `cmd_step` already raises), checked inline in `cmd_position`, not inside the helper — no new code needed since `STEPS_UNDECLARED` was already classified `WORK_STATE`.
- [x] 5.3 GREEN: classified `"POSITION_STEP_UNKNOWN": WORK_STATE` in `GATING_REFUSALS`; added `_resolve_position_step_unknown` to `_WORK_STATE_RESOLUTIONS` (mirrors `_resolve_position_rung_skipped`'s shape: re-derives `resolve_steps_declaration(target, name)` fresh at resolution time from `args.target`/`args.name`), detail lists the target's real declared steps.
- [x] 5.4 Renamed `test_the_derivation_finds_the_measured_sixty_five` → `..._sixty_six`, bumped `65` → `66`. `test_every_gating_refusal_is_classified` and `test_every_work_state_publishes_something_runnable` pass unmodified.
- [x] 5.5 Confirmed (unedited) `test_the_roster_states_the_counts_it_actually_holds` still passes — binds `len(impl.COMMANDS)`; no subcommand added.

**Phase 5 evidence**: `StepOperandRefusalTests` (3 e2e tests) in `tests/test_proposal_implementation.py`. Mutation proof: `_step_operand_detail` checking only `step_items[:1]` (first `@step` item, dropping the rest) survived the single-item RED-derived test but was caught by a strengthened two-item test (`@step run_suite` valid first, `@step nosuch` invalid second) — only the full-scan implementation reports the second item's unknown operand. `GatingRefusalRosterTests`: `test_the_derivation_finds_the_measured_sixty_six` (66), `test_every_gating_refusal_is_classified`, `test_every_work_state_publishes_something_runnable`, and `test_the_roster_states_the_counts_it_actually_holds` (unmoved) all green — 12/12 across both classes.

## Phase 6: Docs

- [x] 6.1 `SKILL.md`: `Sixty-five`→`Sixty-six`; invocation-defect count `(34 codes)` unchanged (`POSITION_STEP_UNKNOWN` is `WORK_STATE`); work-state count `31`→`32`; `position` row's `Refuses on` list gained `STEPS_UNDECLARED`/`POSITION_STEP_UNKNOWN`; `step` row's "No digest field" claim rewritten to describe `suiteDigest`. Bound by `test_the_doctrine_states_the_split_the_roster_actually_holds`, green.
- [x] 6.2 `references/usage.md`: `Thirty-one codes`→`Thirty-two codes` (`Thirty-four codes` unchanged); `step` section rewritten identically to SKILL.md's paragraph. Same test binds it, green.
- [x] 6.3 Added `"step"` to the witness-kind grammar mentions in both docs (`discuss`'s `--about notebook/rehearsal/shard` list gained `step`, matching `OPERAND_REQUIRED_KINDS` generically reading the frozenset); stated the skip-laundering non-goal in `SKILL.md` and `usage.md`, same substance as `specs/step-witness/spec.md`'s "Skip-Laundering Is A Stated Non-Goal" requirement (`pytest` exits 0 on skips, `returned` grades green over a skipped suite exactly as a notebook report already does).

## Phase 7: Full verification

- [x] 7.1 Ran `ForgeVocabularyDerivedGuardTests` + the class holding `test_the_whole_forge_borrows_no_repository_s_vocabulary`/`test_the_guard_scans_the_scripts_this_forge_ships` (13 tests, covering `FORGE_VOCABULARY_FLOOR` + the derived lexicon rule over every guarded surface, including every file this change touched) — 13/13 green, zero violations.
- [x] 7.2 Re-ran both full suites: Python `Ran 2176 tests in 256.628s` — `OK (skipped=3)` (2144 baseline + exactly 32 new tests this change added: 8+8+3+10+3 across the five phases — no other count moved). Node `tests 385 / pass 385 / fail 0` — unchanged, byte-identical to baseline (no Node code touched).
- [x] 7.3 `git status --porcelain=v1` — six modified files, all under `.claude/skills/` or `tests/`, zero changes under `implementations/`. `?? openspec/changes/a-run-is-not-a-verdict/` remains untracked planning artifacts.

**Unplanned fix, found and fixed during 7.2 (not in the original task brief)**: the first full-suite run surfaced 15 real failures. 14 were a genuine regression in Phase 1's `_resolve_deriver`: the `derive()` call sites evaluated `item["ordinal"]` eagerly as an argument on every call (not lazily, only when the guard fires), which crashed any caller building a witness item without an `"ordinal"` key — `cmd_discuss`'s synthetic probe item (`--about <kind> <operand>`, built before any sequence item exists) is exactly that shape. Fixed by passing the whole `item` dict into `_resolve_deriver` and reading `item.get("ordinal", "?")` only inside the branch that actually raises. The 15th was `test_no_reader_anywhere_selects_kind_equals_step`, an existing invariant ("nothing anywhere selects on kind == 'step'") that Phase 4's `_step_verdicts` was always going to violate on purpose — corrected to assert the narrower, still-true claim: `remote_cli.py`/`impl_position.py` still select nothing on `"step"`, and `implementation_cli.py` carries exactly one such reader, pinned by AST to sit inside `_step_verdicts` itself. All fixes proven by re-running the full suite to 2176/2176 green.

Total changed lines: `git diff --stat -- .claude tests` → **969 insertions(+), 45 deletions(-) = 1014 lines**, against the 1400 budget (~72%, ~386 headroom). Under the design's ~1120 and the tasks' own ~1050-1120 forecast.

## Citations verified against source this phase

`WITNESS_KINDS`/`OPERAND_REQUIRED_KINDS` (impl_position.py:81,99), `_DERIVERS`/`_LEVEL_DERIVERS` lookups in `derive()` (impl_position.py:747,753), `_position_write_evidence` (implementation_cli.py:6434, called from 8 sites: 6813, 7345, 8253, 9012, 9524, 9694, 9795, 9917), `cmd_probe`/`cmd_verify` inline evidence dicts (~2456, ~10347 — do NOT call `_position_write_evidence`), `cmd_step`'s event dict (9945-9951) and response dict (9955-9961), `test_function_names` globs `test_*.py` / `unparsable_tests` globs `*.py` (5173, 5188 — confirms `conftest.py` gap), `source_digest` walks `src/` only (4654), `current_file_digest`/`ABSENT_FILE_DIGEST` (impl_position.py:862-879), `_skipped_rung_detail` shape (6340), `parse_items` validates kind only (344), `OperandRequiredKindsTests` pins the exact frozenset (test_implementation_core.py:876), roster tests (test_proposal_implementation.py:14801, 21814, 21875).

**position_state's 10 evidence-construction sites, reconciled**: 8 calls to `_position_write_evidence` (one shared function — wiring it once fixes all 8) + `cmd_probe`'s and `cmd_verify`'s own inline dicts (2 separate code paths, each needs its own edit) = 10 total sites feeding either `position_state` (9 of them) or `derive()` directly (`cmd_position`, which calls `_position_write_evidence` then `derive()` without going through `position_state` at all). Phase 4's parity test is what proves all three code paths (not all ten call sites) agree.
