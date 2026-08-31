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

## Phase 1: Slice A — `close`/`unbacked` symmetry (spec Group 2, PR 1) — implemented 2026-08-30, revised design

**Design revision (operator-approved, 2026-08-30, ahead of this apply session).** 0.1's own finding under-stated the defect: `gate` was not merely "asymmetric with `close`" — a target that legitimately ticks a `@shard` item via `position --shards` reads it back as `unmeasured` at `gate`/`close`/`discuss`/`probe` **permanently**, because none of those four carries a `--shards` flag of its own to re-supply the evidence, and `POSITION_UNBACKED`'s own text ("witnesses were never measured") is **false** for that state — the witness WAS measured, by `position`, from evidence still on disk. Cloning `gate`'s ladder into `close` unmodified (the original Phase 1 plan) would have propagated that false refusal into a second command. The approved fix, implemented as part of this phase rather than as a separate blocked item:

1. A new OPTIONAL declared key, `distribution.shardsRoot` (sibling to `currentWhen`, identical idiom — described in a kit comment, never prefilled, never guessed by the forge) names where a split campaign's returned shards land.
2. `_position_write_evidence` (factored further into `_resolve_shard_evidence`, shared with `cmd_probe`) resolves that declaration when the caller passed no explicit `--shards`, so `position`, `gate`, `close`, `discuss` and `probe` all see the same evidence; an explicit `--shards` still overrides. `verify` keeps its own `--shards` explicit-only, deliberately (a report over a named directory, not a gate the declaration should widen).
3. A ticked `@shard` item whose location nobody declared no longer reads `POSITION_UNBACKED` (false: "measured and found silent"). It reads the new `POSITION_SHARDS_UNDECLARED` (true: "never told where to look"), fired by `impl_availability.position_honest` only when `shards_declared=False` AND the unbacked item's witness kind is `shard`; any other unbacked item, of any kind, still reads `POSITION_UNBACKED` and is checked first (the more general honesty problem is never masked by the narrower one).

- [x] 1.1 RED `tests/test_proposal_implementation.py`: Construction R (`position --shards` tick, then `close`) asserts refusal naming `POSITION_UNBACKED`. Red today: `close` succeeds (bug, per 0.1). **Landed as `test_a_declared_shards_root_ends_the_permanent_false_refusal`** (`OfferCommandTests`) — ticks via real `position --shards`, declares `distribution.shardsRoot`, then asserts `gate` no longer refuses on any position-related code (reaches `GATE_AUTHORIZATION_UNKNOWN` instead) and `close` succeeds (`status: "closed"`). Reachable-red confirmed by `git stash` of only the two production files: pre-fix, this construction refuses `POSITION_UNBACKED` exactly as 0.1 found.
- [x] 1.2 GREEN: add `impl_availability.position_honest(*, status, unbacked, disagreements, shards_declared)`; `launch_available` delegates to it first; `cmd_close` calls it directly. Signature gained `shards_declared` (no default, same no-default doctrine as `disagreements`) beyond the original design, to carry the revision above. Verify: 1.1 green.
- [x] 1.3 (∥) Fix `cmd_close` docstring: refresh loop writes `" "` for a measured-and-unsatisfied item; "can only ever ADD ticks" is true only because the disagreement check precedes it.
- [x] 1.4 RED: replace the pinned `count(...) == 2` test with an `ast` walk. **Landed as three tests** rather than one combined assertion: `test_gate_and_offer_call_the_identical_shared_availability_symbol` asserts `launch_available`'s CLI call-site set is exactly `{cmd_gate, _offer_launch_action}`; `test_close_calls_the_shared_honesty_rule_directly` asserts `position_honest`'s CLI call-site set is exactly `{cmd_close}` (not `{cmd_gate, cmd_close}` as D3's prose suggested — `cmd_gate` reaches `position_honest` only *indirectly*, through `launch_available`, so no literal `impl_availability.position_honest(` call node exists inside `cmd_gate` for an AST walk of the CLI file to find); `test_launch_available_itself_calls_position_honest_first` asserts the indirect half structurally, over `impl_availability.py`'s own AST. Red confirmed pre-1.2 by `git stash` of both production files: `cmd_close` absent from `position_honest`'s set, `launch_available` never calls `position_honest` at all.
- [x] 1.5 GREEN: confirm 1.4 passes once 1.2 lands; delete the old literal-count assertion.
- [x] 1.6 (∥) `tests/test_implementation_core.py`: table-driven `position_honest` unit test — **five** outcomes in ladder order (`POSITION_ABSENT`/`POSITION_STALE`/`POSITION_UNBACKED`/`POSITION_SHARDS_UNDECLARED`/`POSITION_DISAGREES`, plus the honest-true case), not the four the pre-revision design named, plus a status-outranks-everything test and a no-default `TypeError` test for `shards_declared`.
- [x] 1.7 Docs: `SKILL.md` close-refusal row + `references/usage.md` refusal set — add `POSITION_UNBACKED` **and** `POSITION_SHARDS_UNDECLARED`; `SKILL.md`'s `--shards`/`currentWhen` paragraph gained a new paragraph documenting `shardsRoot`; `main()`'s own `--shards` argparse comment and `impl_position._derive_shard`'s docstring corrected (both previously stated `gate`/`close`/`discuss`/`probe`/`probe` read no shard evidence at all — no longer true once a target declares `shardsRoot`).

**One pre-existing test broken by the revision, fixed in place (not blocked-around):** `UnbackedPositionSurfaceTests` (`tests/test_proposal_implementation.py`) built its entire fixture set around a ticked `@shard` witness with no declaration at all — exactly the case this revision gives a new, more honest code. `test_gate_refuses_a_launch_authorized_over_an_unbacked_tick` renamed to `test_gate_refuses_a_launch_authorized_over_an_undeclared_shard_tick`, asserting `POSITION_SHARDS_UNDECLARED`; `test_the_doctrine_names_the_refusal` extended to check both codes are documented. The seven `OfferCommandTests` refusal-code cross-join test's own `POSITION_UNBACKED` fixture was switched from a `@shard` witness to a `@notebook` witness (a real, general unbacked cause the shard revision has nothing to say about), and a new `POSITION_SHARDS_UNDECLARED` subtest added beside it — the class docstring/method name now say "seven", not "six".

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
