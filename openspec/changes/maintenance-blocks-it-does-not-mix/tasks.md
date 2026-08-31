# Tasks: maintenance-blocks-it-does-not-mix

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 700–1000 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 Record&Derive → PR2 Wire Refusal → PR3 Crash+Docs |
| Delivery strategy | ask-on-risk (default; none supplied) |
| Chain strategy | pending — orchestrator must ask: feature-branch-chain recommended (rollback per slice, append-only ledger tolerates partial land) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | `ABSENT_FILE_DIGEST`, `current_file_digest`, `open_defects`, `cmd_defect`, both declaration refusals, roster/usage docs | PR1 | `python3 -m unittest discover -s tests -p 'test_proposal_implementation.py' -k Defect` | N/A — pure unit tests, no live forge run needed | revert-only; inert, blocks nothing |
| 2 | `_require_no_open_defect` + 7 ladder insertions + 7 diagnostics + `handoff.openDefects` | PR2 | same, `-k "OpenDefect or Diagnostic"` | `implementation_cli.py step/gate/... --help` smoke per command | revert-only; PR1 stays inert without it |
| 3 | crash arm in `main()`, docs (stop-flow + 2 limits), vocab re-run | PR3 | same, `-k Crash` | trigger a real non-`Refused` exception via monkeypatched `COMMANDS` entry | revert-only |

## Verification (real suites — `openspec/config.yaml`'s configured `test_command` reaches neither Python suite)

```
python3 -m unittest discover -s tests -p 'test_proposal_implementation.py' -v
python3 -m unittest discover -s tests -p 'test_skill_audit.py' -v
npm test
```

RED-before-GREEN instrument (all Phase 2/3 lock tests): **arm/disarm on a real ledger fixture**, not source mutation — ARMED: append a real `defect` event at the file's real current digest → refusal fires; DISARMED: edit the fixture file's bytes (size change) → refusal does not fire. Where source mutation is unavoidable: delete `__pycache__` for the mutated module (or `PYTHONDONTWRITEBYTECODE=1`) and assert the mutation is observable before reading the verdict.

## Coordination Notes

- Sibling `the-skill-materializes-not-the-agent` adds `materialize` and touches the same `write_verbs` literal and worked-invocation test. Whichever change lands second must not assert today's exact set — verify current `write_verbs`/`DOCUMENTED_ELSEWHERE` by name before editing, not by inheriting this artifact's literal.
- Sibling `a-pilot-is-the-whole-flow-validated` also edits `cmd_close`'s ladder (adds `POSITION_UNBACKED` deeper in it); this change only touches the two lines right after `cmd_close`'s existing `resolve_target`/`validate_name` head. Named, not resolved — a maintainer decides landing order.

## Phase 1 (PR1): Record and Derive — inert, blocks nothing

- [x] 1.1 `impl_position.py`: add `ABSENT_FILE_DIGEST = "absent"` (module constant, 6-char non-hex string). Test: assert it fails `^[0-9a-f]{64}$`.
- [x] 1.2 `impl_position.py`: add `current_file_digest(path) -> str` — `digest_bytes(path.read_bytes())` for a regular file, else `ABSENT_FILE_DIGEST`. No `if not exists`/`is_file` branch outside this one function.
- [x] 1.3 `impl_position.py`: add `open_defects(events, forge_root) -> list[dict]` — latest-wins per forge-relative `file`; clearing is the single comparison `current_file_digest(...) != recorded`; missing `fileSha256` key (`.get()` is `None`) → treated OPEN, not cleared. No existence branch.
- [x] 1.4 Review: grep the implemented `open_defects`/`current_file_digest` path for `if not .*\.(exists|is_file)\(` outside `current_file_digest` itself — must find none. This is the exact line shape that reintroduces the bypass.
- [x] 1.5 `implementation_cli.py`: add `cmd_defect` — resolve path (non-strict) → containment under `FORGE_ROOT/.claude/skills` (else `DEFECT_FILE_NOT_FORGE_OWNED`) → `is_file()` (else `DEFECT_FILE_ABSENT`) → digest → `append_event(kind="defect", file=<forge-relative>, fileSha256=<hex>, command="defect", ...)`; `session`/`detail` omitted (never `null`) when absent. Containment checked before existence.
- [x] 1.6 argparse: add `defect` to the `--session`-bearing set, add `--file`/`--detail`; add `defect: cmd_defect` to `COMMANDS`, keeping it a **dict literal** (`dict_literal_keys` parses it by AST).
- [x] 1.7 `SKILL.md`: add `defect` row to the command roster table. `usage.md`: add a worked `implementation_cli.py defect --target ... --name ... --session ... --file ... --detail ...` invocation with flags the real parser accepts. Re-run FORGE_LEXICON rule B + `FORGE_VOCABULARY_FLOOR` rule C against both changed files.
- [x] 1.8 `tests/test_proposal_implementation.py`: add `defect` to `write_verbs` (locate the literal by name first, do not assume today's set — see Coordination Notes); this makes `CommandRosterTests.test_every_command_dispatched_is_accounted_for` and `test_every_command_the_cli_dispatches_has_a_worked_invocation` pass again.
- [x] 1.9 Tests: declare inside tree (event appended, engine-computed hex); outside tree (`DEFECT_FILE_NOT_FORGE_OWNED`, ledger byte-identical); **never-existed path** (`DEFECT_FILE_ABSENT`, ledger byte-identical — the bypass, closed); outside-tree AND nonexistent (`DEFECT_FILE_NOT_FORGE_OWNED` wins, containment first); repeat declaration on unchanged digest appends (+1 event, not refused).
- [x] 1.10 Run Verification suites. RED before: `CommandRosterTests` fails on missing `defect`; GREEN after: full pass.

## Phase 2 (PR2): Wire the Refusal

- [x] 2.1 **`cmd_admit` structural gap** (re-located, not inherited from design's placeholder): `cmd_admit` today calls only `resolve_target(args.target)`, never `validate_name(args.name)`, and its admissibility record lives at `target/tests/admissibility.json` — not `target/<name>/.implementation/`. Its actual first-ladder refusal is `REVISION_UNREADABLE`, raised immediately after `resolve_target`. Add `name = validate_name(args.name)` as new code right after `resolve_target(args.target)`, before `revision_source(...)`, so the defect guard can precede `REVISION_UNREADABLE` (a content check, not argv-shaped — must not outrank the defect check, per the design's own "argv-shaped prerequisites only" rule).
- [x] 2.2 `implementation_cli.py`: add `_require_no_open_defect(target, name)` — reads the ledger, calls `open_defects`, raises `FORGE_DEFECT_OPEN` if non-empty.
- [x] 2.3 Insert `_require_no_open_defect(target, name)` immediately after `resolve_target`+`validate_name`, before `require_clean_worktree`/any target read, in `step`, `gate`, `offer`, `close`, `settle`, `apply`, `admit` (7 sites; `admit` per 2.1).
- [x] 2.4 RED × 7, one scenario per command, each armed so a *different* known refusal wins if the insertion is missing/misplaced (arm/disarm fixture). **Corrected against the source, not inherited from the design's placeholder table**: `offer`'s own docstring states `--answer` is checked BEFORE `resolve_target`/`validate_name` even run ("Both checks sit above resolve_target/revision_source"), so an omitted `--answer` refuses `OFFER_UNANSWERED` identically whether the insertion is present, missing, or misplaced — it cannot distinguish the three, the exact "specified refusal no input could ever trigger" trap the design warns about at every insertion point. Used instead: a valid `--answer` with an unreadable `--revision` (`REVISION_UNREADABLE`), the nearest reachable marker actually past the insertion point. `apply`'s "unreadable" plan is also not a coded refusal today (`FileNotFoundError`, uncaught — Phase 3's concern); used `PLAN_MISMATCH` (an existing, valid, mismatched plan JSON) instead. Final markers: `step`+dirty worktree vs `DIRTY_WORKTREE`; `gate` omit `--authorization` vs `GATE_AUTHORIZATION_REQUIRED` (sharpest — pure-argv, top of ladder); `offer` valid `--answer` + unreadable `--revision` vs `REVISION_UNREADABLE`; `close` unreadable `--revision` vs `REVISION_UNREADABLE`; `settle` `--under` names no heading vs `SETTLE_HEADING_ABSENT`; `apply` a mismatched `--plan` vs `PLAN_MISMATCH`; `admit` its own `REVISION_UNREADABLE` (2.1). Each shows `FORGE_DEFECT_OPEN` armed / other-code disarmed — proven RED (temporarily reverting the 7 insertions) before GREEN (restored), not merely asserted.
- [x] 2.5 Diagnostics stay reachable: `probe`, `verify`, `position`, `plan`, `compose`, `handoff`, `discuss` — 7 scenarios, **each sharing its fixture with a companion assertion that a spend command IS refused on that same fixture** (non-vacuity pairing; without it all 7 pass on a dead arm).
- [x] 2.6 `cmd_handoff`: add `name = validate_name(args.name)`, new key `openDefects: [{file, session, detail, at}]`; `status` field unchanged. Test: open defect → `handoff` reports it and does not refuse.
- [x] 2.7 Auto-append non-self-trip test: `defect` then `step` in the same target → no `DIRTY_WORKTREE` from the defect's own ledger line (`_is_own_bookkeeping` excuses `.implementation/`); a separate non-ledger dirty file still refuses.
- [x] 2.8 `SKILL.md`: update the section naming when the flow stops (`FORGE_DEFECT_OPEN` on the 7 spend/advance commands, not on diagnostics). Re-run vocabulary guard on changed prose. `usage.md` untouched — Phase 1 already carries the `defect` worked invocation, and no command's argv shape changed in Phase 2.
- [x] 2.9 Non-repository guard order test: armed defect + non-repository target → `NOT_A_GIT_REPO`, not `FORGE_DEFECT_OPEN`.
- [x] 2.10 Per-target scope test: defect under target A, spend command against target B → no refusal.
- [x] 2.11 Run Verification suites. RED before: each per-command scenario shows the wrong/no refusal; GREEN after: `FORGE_DEFECT_OPEN` wins in all 7, diagnostics unaffected.

## Phase 3 (PR3): Crash Capture + Docs

- [x] 3.1 `main()`: add `except Exception` after the existing `except Refused` arm — never `except BaseException`. Body wrapped in its own `try: _record_engine_defect(...) except Exception: pass`, ends in bare `raise` (never `finally`).
- [x] 3.2 `_record_engine_defect` / `_crashing_forge_file`: walk `exc.__traceback__.tb_next…`, take the **last** frame under `FORGE_ROOT/.claude/skills`; no qualifying frame → record nothing. `getattr(args, "name"/"target", None)`; either missing → record nothing, re-raise (stated limit for `env`/`name`/`compose`). `getattr(args, "session", None)`; omit key when absent, never write `null`.
- [x] 3.3 RED × 6 (arm/disarm or targeted monkeypatch, delete `__pycache__` if source is touched): non-`Refused` crash records (names raising module + current digest); original exception type/message survives unchanged; `append_event` monkeypatched to raise → original STILL propagates, no second error; **`Refused` records nothing** (highest-consequence — ordering load-bearing since `Refused(Exception)`); `KeyboardInterrupt`/`SystemExit` record nothing; crash in `env` appends nothing, re-raises. Full removal of the `except Exception` arm (git-stash-only-source) turned exactly one of the six tests red — the other five held vacuously true on a mechanism that does not exist, so five further TARGETED mutations (kept, then reverted, one at a time) proved each of the remaining locks: (B) `raise` → `raise RuntimeError("wrapped")` flipped 3 tests (original type/message, failing-recorder, env-limit); (C) removed the inner `try/except Exception: pass` around `_record_engine_defect` → failing-recorder test errors with the injected `OSError` instead of the original `RuntimeError`; (D) swapped `except Exception` ahead of `except Refused` → the Refused-records-nothing test errors, proving ordering load-bearing; (E) `except Exception` → `except BaseException` → both `KeyboardInterrupt`/`SystemExit` subtests fail (ledger gains an event that must never exist).
- [x] 3.4 `SKILL.md`: write both stated limits plainly — (a) this detects and blocks mid-flow forge repair, it does not prevent the edit (no hook, no `permissions.deny` added); (b) per-target scope is a non-goal, not an oversight — a shared forge bug blocks only sessions that declared it. Also document as decided, not a bug: a file deleted *after* a defect is declared against it clears that defect on next check (absence is the strongest digest change). Both limits were already carried in the `defect` roster row (Phase 1/2); this slice adds the missing piece — a new "When the forge itself crashes mid-flow" subsection documenting the `except Exception` auto-record mechanism itself, which no prior slice mentioned — plus the explicit deletion-clears sentence in that same row and in `usage.md`.
- [x] 3.5 Vocabulary guard: **executed** (not reviewed) `ForgeVocabularyDerivedGuardTests.test_rule_b_finds_no_target_vocabulary_in_the_forge` and `ReportFirstSectionProseTests.test_the_whole_forge_borrows_no_repository_s_vocabulary` (`FORGE_VOCABULARY_FLOOR`) against the live tree, including this slice's own new SKILL.md/usage.md prose and `implementation_cli.py` identifiers/comments. Both green, zero hits.
- [x] 3.6 Run Verification suites (full). RED before: no `except Exception` arm — crash tests fail/error uncaught (see 3.3). GREEN after: full pass — `python -m unittest discover -s tests -p 'test_*.py'`: Ran 1869 tests, OK (skipped=2); `npm test`: pass 385, fail 0. `Refused` path unchanged (zero new `defect` events on ordinary refusals, proven by `test_refused_records_nothing_the_ordinary_refusal_path_is_unchanged`).
