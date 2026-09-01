# Tasks: Nothing Agreed Stays In The Conversation

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~440 (Half 1) + ~260 (Half 2: collision, verify, probe, rosters, docs) ≈ 700 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Half 1 + shared plumbing) → PR 2 (settle collision + verify remedy) → PR 3 (probe piloted, conditional) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | `_discuss_command`/`_open_discussions` + `close`'s `DISCUSSION_UNANSWERED` gate | PR 1 | `unittest ... -k DiscussionGate` | `close` vs. live reference-target ledger | Revert `cmd_close` axis 3 + helpers; no ledger writes to undo |
| 2 | Settle collision enumeration + verify `toDiscuss` | PR 2 | `-k SettleCollides or -k VerifyToDiscuss` | `settle`/`verify` vs. synthetic collision fixture | Revert message + verify block; Unit 1 unaffected |
| 3 (conditional) | Probe `piloted` `toDiscuss`, only if Phase 0.2 GO | PR 3 | `-k ProbePiloted` | `probe` vs. constructed 7-condition fixture | Drop `toDiscuss` + roster row |

## Phase 0 — Pre-flight measurement (blocking, before any code)
- [x] 0.1 Run `verify` on the reference target; record live `audit.localRemediesNotWritten` count in this file and the PR body (D3 obligation).
      **Measured 2026-09-01**: `implementation_cli.py verify --target implementations/Domain_Adaptation --name MIL-CREDA --revision research-concept-r17.md` → `audit.localRemediesNotWritten: []`, count **0**. Confirms the operator's own measurement; D3's inclusion argument (unbounded volume / unreachable guard, both decided from code shape, not from this count) stands unchanged.
- [x] 0.2 Attempt a fixture reaching `cmd_probe`'s `next_step == "piloted"` (`implementation_cli.py:2297`) with all seven downgrade `elif`s false (`declare-first` x2 @2356/2367, `env-first` @2370, `wiring-first` @2372, `poll-first` @2380, `search-first` @2385, `report-first` @2387). GO → Phase 4/Unit 3. NO-GO → delete the probe-piloted requirement from scope, record why, skip Phase 4.
      **VERDICT: GO — measured live 2026-09-01**, via a direct `impl.cmd_probe(...)` call (not a design-only reachability argument) against a constructed fixture under `implementations/`: declared `__benchmark__` with `arms`, `entry.module` pointing to a pure-Python module (no heavy deps, so `introspect()`'s live subprocess check needs only a working interpreter, not real torch), a full `report` contract (non-empty `components`, `records` covering every `Results/*.json` file, `record` + `conclusionEntry` naming a real callable that produces different text under `INTROSPECT`'s permutation check), a satisfied `search` record, no remote-execution ledger, a `.venv/bin/python` symlinked to the running interpreter, and a `Probe_results.json` below the declared scale. Result: `nextStep: "piloted"`, `report.status: "ok"`, `report.live: "ok"`, `search.recordFound/scaleSatisfied: true`, `remoteExecution.status: "absent"` — all seven `elif`s confirmed non-firing. Phase 4/Unit 3 (PR 3) may proceed in a later PR; out of scope for this PR regardless.

## Phase 1 — Foundation (PR 1)
- [x] 1.1 RED: test calling `_discuss_command(target, name, about=, question=, answer=None)` on apostrophe text; assert quoted, subprocess-runnable output (symbol absent today).
      Confirmed RED via `git stash` on `implementation_cli.py` only (production file), tests kept: `AttributeError: module 'implementation_cli' has no attribute '_discuss_command'` / `'_open_discussions'`.
- [x] 1.2 GREEN: add `import shlex`; implement `_discuss_command` in `implementation_cli.py`.
- [x] 1.3 RED: mutation proofs 1–4 (exact-text grouping, last-word ordering x2, doctrine preservation) against `_open_discussions`, using spec's 7-event and clarification fixtures.
      Mutation proofs 1, 2, 3 individually verified by temporarily swapping the implementation (identity grouping / per-event `status` reading / answered-once) and confirming the corresponding test fails; reverted each time. Mutation 4 (doctrine preservation) shares the identity-grouping defect class already disproven by mutation 1's swap.
- [x] 1.4 GREEN: implement `_open_discussions(target, name)`.

## Phase 2 — Half 1: close-discussion-gate (PR 1)
- [x] 2.1 RED baseline: `git stash` `implementation_cli.py` only; run new `close`-refuses test; confirm it fails today; unstash.
      Confirmed: `test_close_refuses_discussion_unanswered` and `test_close_discussion_refusal_prints_a_runnable_apostrophe_bearing_retirement` both failed (`returncode 0 != 2`, `status: "closed"`) against the stashed production file; all other `CloseCommandTests` (not exercising this axis) stayed green, ruling out a vacuously-passing suite.
- [x] 2.2 GREEN: wire `_open_discussions` into `cmd_close` as axis 3, after `AGREEMENT_DISAGREES`, before the position refresh; raise `DISCUSSION_UNANSWERED` with one retirement command per open text.
- [x] 2.3 RED/GREEN: apostrophe retirement command run as subprocess (mutation proof 5), same discipline as `OfferCommandTests.test_expand_contract_command_string_is_runnable_and_writes_nothing`.
- [x] 2.4 RED: prove `--answer -` (stdin) is the rejected form — assert empty-stdin yields vacuous `status:"open"`, and the printed command never uses it.
- [x] 2.5 Test: zero-open on the reference ledger (27 events/12 texts); refusal fires before `cmd_position`'s refresh runs, no position bytes rewritten.
      Reference-ledger shape reproduced synthetically (multiple distinct answered buckets); refresh non-side-effect proven by byte-identical `AGREED.md` across a refused `close` call.

**PR 1 status**: Phases 0–2 complete. Full gate: `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` and `npm test` (385/385) — see commit message / PR body for the exact run.

## Phase 3 — Half 2a: settle collision + verify remedy (PR 2)
- [ ] 3.1 RED: keep `test_settle_refuses_collides_unnamed` asserting `code` only; add test asserting enumerated colliding texts (not `len(collides)`) in `SETTLE_COLLIDES_UNNAMED` (`cmd_settle` ~7787).
- [ ] 3.2 GREEN: rewrite the message to list every colliding text; append a collision `_discuss_command` (operand + sorted texts, never a count).
- [ ] 3.3 RED/GREEN: apostrophe collision command run as subprocess (mutation proof 6).
- [ ] 3.4 RED/GREEN: `toDiscuss` top-level key on `cmd_verify`'s dict — one command per `localRemediesNotWritten` id (~9697), text from finding id only.
- [ ] 3.5 Test: `prose.staleRevisions`/`unresolvedSymbols`/`agreements.witness.unwitnessed` publish no `discuss` command.
- [ ] 3.6 Re-grep `*.py` for literal `"existing agreement(s)"` post-change; confirm zero remaining assertions of the old wording.

## Phase 4 — Half 2b: probe piloted (PR 3, conditional on 0.2 GO)
- [ ] 4.1 RED: 0.2's fixture reaches `piloted`; assert `toDiscuss` present, question names target/name + declared scale.
- [ ] 4.2 GREEN: add `toDiscuss` top-level key to `cmd_probe`'s piloted branch.
- [ ] 4.3 RED/GREEN: mutation proof 7 — two polls, same declared scale, different achieved counts, byte-identical `--question` text; a build embedding the count MUST fail.

## Phase 5 — Rosters and docs (PR 2, PR 3 if Unit 3 ships)
- [ ] 5.1 `VerifyStatusRosterTests`/`ProbeReportedFactsRosterTests` — add `toDiscuss` rows; confirm both red until docs land.
- [ ] 5.2 `SKILL.md`: non-goal sentence verbatim in both halves' sections + `toDiscuss` row in both roster tables.
- [ ] 5.3 `references/usage.md`: `toDiscuss` under `## Reading verify`; update collision wording example.

## Phase 6 — Full-suite verification (each PR, before merge)
- [x] 6.1 (PR 1) `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` — confirmed `Ran 2051 tests, OK, skipped=3` (2039 baseline + 12 new: 3 `DiscussCommandBuilderTests` + 5 `OpenDiscussionsTests` + 4 `CloseCommandTests`).
- [x] 6.2 (PR 1) `npm test` — confirmed 385/385 (unchanged; this PR touches no TypeScript).
- [x] 6.3 (PR 1) Ran `ForgeVocabularyDerivedGuardTests` (`FORGE_VOCABULARY_FLOOR`/`FORGE_LEXICON` rule B, executed not reasoned about) — 8/8 pass, zero violations.
- [x] 6.4 (PR 1) `CoreNamesNoDomainTests` passes by scope — this PR touches only `.claude/skills/proposal-implementation/scripts/implementation_cli.py` and `tests/`, no `_core/implementation/` change; confirmed included and green in the 6.1 full-suite run.
- [ ] 6.1–6.4 repeat for PR 2 and PR 3 (conditional) before each of those merges.
