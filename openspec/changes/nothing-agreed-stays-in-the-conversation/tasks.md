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
- [ ] 0.1 Run `verify` on the reference target; record live `audit.localRemediesNotWritten` count in this file and the PR body (D3 obligation).
- [ ] 0.2 Attempt a fixture reaching `cmd_probe`'s `next_step == "piloted"` (`implementation_cli.py:2297`) with all seven downgrade `elif`s false (`declare-first` x2 @2356/2367, `env-first` @2370, `wiring-first` @2372, `poll-first` @2380, `search-first` @2385, `report-first` @2387). GO → Phase 4/Unit 3. NO-GO → delete the probe-piloted requirement from scope, record why, skip Phase 4.

## Phase 1 — Foundation (PR 1)
- [ ] 1.1 RED: test calling `_discuss_command(target, name, about=, question=, answer=None)` on apostrophe text; assert quoted, subprocess-runnable output (symbol absent today).
- [ ] 1.2 GREEN: add `import shlex`; implement `_discuss_command` in `implementation_cli.py`.
- [ ] 1.3 RED: mutation proofs 1–4 (exact-text grouping, last-word ordering x2, doctrine preservation) against `_open_discussions`, using spec's 7-event and clarification fixtures.
- [ ] 1.4 GREEN: implement `_open_discussions(target, name)`.

## Phase 2 — Half 1: close-discussion-gate (PR 1)
- [ ] 2.1 RED baseline: `git stash` `implementation_cli.py` only; run new `close`-refuses test; confirm it fails today; unstash.
- [ ] 2.2 GREEN: wire `_open_discussions` into `cmd_close` as axis 3, after `AGREEMENT_DISAGREES`, before the position refresh; raise `DISCUSSION_UNANSWERED` with one retirement command per open text.
- [ ] 2.3 RED/GREEN: apostrophe retirement command run as subprocess (mutation proof 5), same discipline as `OfferCommandTests.test_expand_contract_command_string_is_runnable_and_writes_nothing`.
- [ ] 2.4 RED: prove `--answer -` (stdin) is the rejected form — assert empty-stdin yields vacuous `status:"open"`, and the printed command never uses it.
- [ ] 2.5 Test: zero-open on the reference ledger (27 events/12 texts); refusal fires before `cmd_position`'s refresh runs, no position bytes rewritten.

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
- [ ] 6.1 `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'` — confirm `Ran 2039+N tests, OK, skipped=3`.
- [ ] 6.2 `npm test` — confirm 385/385 (+ new).
- [ ] 6.3 Run `FORGE_VOCABULARY_FLOOR`/`FORGE_LEXICON` rule B against every changed file — zero violations.
- [ ] 6.4 Run `CoreNamesNoDomainTests` — confirm pass by scope (`_core/implementation/` untouched).
