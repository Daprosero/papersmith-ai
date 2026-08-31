# Tasks: A Pilot Is The Whole Flow, Validated

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~600-900 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 = Slice A (~150-250 lines); PR 2 = Slice B (~450-700 lines), based on PR 1 |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (design recommends feature-branch-chain) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Slice A: `close`/`unbacked` symmetry via `position_honest` | PR 1 (base: feature/tracker) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_proposal_implementation tests.test_implementation_core -v` | Construction R on scratch target: `position --shards <root>` tick, then `close` | Revert `impl_availability.py` + `cmd_close` commit; `gate`/`offer` untouched |
| 2 | Slice B: witness grammar, `settle --witness`, three-state `verify` | PR 2 (base: PR 1 branch) | same command, full `discover -p 'test_*.py'` | `settle --about <w> --witness test_<id>` then `verify` on scratch target | Revert grammar/parser/settle/verify commit; persisted tokens become inert trailing text |

## Phase 0: Blocking Measurements (spec Group 2 + D4 open question — before either slice)

- [x] 0.1 Measure gate/close asymmetry: on Construction R state (ticked `@shard`, no `--shards` at `gate`), run unmodified `cmd_gate`; record refuse/succeed. Verify: manual scratch-target run, output pasted into PR 1 description. Decides whether Slice A is "close wrong only" or "both wrong, opposite directions." **Executed 2026-08-30**: real subprocess run (position `--sequence` install of a `@shard a` item → `position --shards <dir>` ticks it via real evidence, `derived: true`/`satisfied: true` → unmodified `cmd_gate` (no `--shards` flag exists on it) on the identical state returns exit 2, `{"status":"refused","code":"POSITION_UNBACKED", ...}`; unmodified `cmd_close` on the same state returns exit 0 (succeeds — today's bug). **Framing that survived, per the task's own decision procedure**: gate DOES refuse on a legitimately, evidence-derived-ticked state, which is the prompt's own trigger for "gate false-refuses a legitimately reached rung, and close under-refuses — the fix is different from what the design describes." Root cause: `_derive_shard` returns `satisfied=None` whenever `shardsArrived` is `None`, and `gate`/`close`/`discuss`/`probe` all call `_position_write_evidence(target, name)` with **no** third argument — none of them can ever re-supply shard evidence, so a `@shard` witness, once ticked by `position --shards`, reads `unbacked` at `gate` **permanently**, regardless of how it was ticked. This is pre-existing in `gate` (unrelated to this change) and orthogonal to `POSITION_UNBACKED` reachability at `close`, which remains proven. **STOPPED per explicit instruction** before implementing Phase 1's conditional branch — see apply-progress / session report for the full analysis and the decision the operator needs to make.
- [x] 0.2 (∥ with 0.1) Scan holder markdown for trailing-backtick collision: grep `` `test_[A-Za-z0-9_]+`\s*$ `` over target `.md` agreement lines. Zero hits → keep backtick token (D4). Non-zero → switch to `<!-- witness: test_<id> --> ` fallback for 2.1/2.2. **Executed 2026-08-30**: `rg '`test_[A-Za-z0-9_]+`\s*$' implementations/Domain_Adaptation/MIL-CREDA/AGREED.md` → 0 hits across 114 checklist lines. D4's backtick token form stands for Slice B (not implemented this session).

## Phase 1: Slice A — `close`/`unbacked` symmetry (spec Group 2, PR 1) — BLOCKED, not implemented this session (see 0.1 finding)

- [ ] 1.1 RED `tests/test_proposal_implementation.py`: Construction R (`position --shards` tick, then `close`) asserts refusal naming `POSITION_UNBACKED`. Red today: `close` succeeds (bug, per 0.1).
- [ ] 1.2 GREEN: add `impl_availability.position_honest(*, status, unbacked, disagreements)`; `launch_available` delegates to it first; `cmd_close` calls it directly. Verify: 1.1 green.
- [ ] 1.3 (∥) Fix `cmd_close` docstring: refresh loop writes `" "` for a measured-and-unsatisfied item; "can only ever ADD ticks" is true only because the disagreement check precedes it.
- [ ] 1.4 RED: replace the pinned `count(...) == 2` test with an `ast` walk asserting call-site function sets `{cmd_gate, _offer_launch_action}` (`launch_available`) and `{cmd_gate, cmd_close}` (`position_honest`). Red: `cmd_close` absent from the second set pre-1.2.
- [ ] 1.5 GREEN: confirm 1.4 passes once 1.2 lands; delete the old literal-count assertion.
- [ ] 1.6 (∥) `tests/test_implementation_core.py`: table-driven `position_honest` four-code order unit test.
- [ ] 1.7 Docs: `SKILL.md` close-refusal row + `references/usage.md` refusal set — add `POSITION_UNBACKED`.

DoD: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_proposal_implementation tests.test_implementation_core -v` green; delete `__pycache__` under `.claude/skills/_core/implementation/` before each reachable-red run.

## Phase 2: Slice B — witness persistence (spec Groups 3-4-5, PR 2, gated on 0.2)

- [ ] 2.1 RED: grammar tests — bare line unchanged; witness round-trip; trailing-backtick collision fixture using 0.2's chosen token. Red: `AGREEMENT_LINE` has no witness group.
- [ ] 2.2 GREEN: extend `AGREEMENT_LINE` with the optional trailing witness group; no new `WITNESS_KINDS` member.
- [ ] 2.3 RED: `cmd_settle --witness test_<id>` writes `` - [ ] {text} `{witness}` ``; omitted stays bare.
- [ ] 2.4 GREEN: add `--witness` argparse flag; write logic in `cmd_settle` (sole writer).
- [ ] 2.5 RED: single-write-path `ast` lock — only `cmd_settle` constructs a witness segment.
- [ ] 2.6 GREEN: implement lock.
- [ ] 2.7 RED: `agreements_state` three-state tests (`unwitnessed`/`unmeasured`/`disagrees` per D6); uniform `returned_keys` across every branch incl. `absent`.
- [ ] 2.8 GREEN: `agreements_state` reads witness; state via `tests_dir` presence + `unparsable_tests` + `test_function_names`; one-directional (unticked + existing test ≠ `disagrees`).
- [ ] 2.9 RED: `close` refuses `AGREEMENT_DISAGREES`, naming the item's exact text.
- [ ] 2.10 GREEN: `cmd_close` checks `agreements_state`, raises `AGREEMENT_DISAGREES`.
- [ ] 2.11 RED: `verify` emits `agreements.witness.summary: "N of M witnessed"` on every branch incl. `"0 of 0 witnessed"`; `verify`/`probe` exit 0 on `disagrees`.
- [ ] 2.12 GREEN: `cmd_verify` nests the witness dimension inside the existing `agreements` key; update `returned_keys`/`markdown_table_rows`.
- [ ] 2.13 Docs: `SKILL.md` verify status row + hand-editing doctrine (unsupported, evaluated not rejected); `references/usage.md` three states.

DoD: same suite command as Phase 1, full `discover -p 'test_*.py'`; confirm `implementations/Domain_Adaptation/MIL-CREDA/AGREED.md` byte-identical (`git diff --stat` empty).

## Phase 3: Cross-cutting (spec Cross-cutting)

- [ ] 3.1 RED: `FORGE_VOCABULARY_FLOOR` test — a word merely containing the forbidden substring must not flag.
- [ ] 3.2 GREEN: switch to `\b`-anchored matching in `test_proposal_implementation.py`/`test_skill_audit.py`.
- [ ] 3.3 RED: `FORGE_LEXICON` rule B test asserting it executes against live `src/MIL_CREDA/` basenames, not a hard-coded list.
- [ ] 3.4 GREEN: implement; run in `test_skill_audit.py`.
- [ ] 3.5 Full local verification (never the configured `test_command`, which only discovers `test_extract_pdf.py`): `node --test tests/*.test.mjs && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v`.

## Non-Goals

- No edit to `implementations/Domain_Adaptation/MIL-CREDA/AGREED.md`; retrofit is a separate future pass.
- No new `WITNESS_KINDS` member; no `settle --about test_<id>`.
