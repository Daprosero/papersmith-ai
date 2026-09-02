```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:bfdd7b800f8b889bf437edede99e19b1a218b858421f65e91905c236a67e74e3
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 9/9
scenarios: 11/11
test_command: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests
test_exit_code: 0
test_output_hash: sha256:6a3dee2c486efe0937e69e795e005b57ebb972e393ecc7542405684660157f54
build_command: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m compileall -q .claude/skills/_core/implementation .claude/skills/proposal-implementation/scripts tests
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report

**Change**: `a-run-is-not-a-verdict`
**Version**: `specs/step-witness/spec.md` — 9 requirements, 11 scenarios (counted directly from the file: `rg -c '^### Requirement:'` and `rg -c '^#### Scenario:'`)
**Mode**: Strict TDD (`strict_tdd: true`), full artifact set (proposal, exploration, spec, design, tasks, apply-progress)
**Evidence revision**: `709a755c8ed8b8e3c99f31c8814e0f65ab2dd958`, branch `forge/a-rung-is-never-skipped`, working tree clean before and after this verification
**Artifact store**: hybrid — Engram (`sdd/a-run-is-not-a-verdict/*`) plus `openspec/changes/a-run-is-not-a-verdict/`

Nothing in this report is taken from the apply record on trust. Every requirement was traced to
named code and re-executed against fresh, hand-built fixtures — not merely re-run through the
existing suite. `__pycache__` was purged and `PYTHONDONTWRITEBYTECODE=1` used throughout.

### Completeness

| Metric | Value |
|---|---|
| Tasks total | 30 (`rg -c '^\s*- \[.\]'` on `tasks.md`) |
| Tasks complete | 30 (`rg -c '^\s*- \[x\]'`) |
| Tasks incomplete | 0 |

### Build & Tests Execution

**Build**: PASSED — `python -m compileall -q` over every file this change touched, exit 0, empty output.

**Tests**: PASSED, measured twice independently (once at session start, once as the final report evidence):

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests
→ Ran 2176 tests in 255.158s — OK (skipped=3)

npm test
→ tests 385, pass 385, fail 0
```

Baseline was 2144 Python tests before this change (measured by the apply phase at its own Phase
0); 2176 − 2144 = 32 new tests, matching the apply record's claim exactly. Node suite unchanged at
385/385.

`git diff --stat main..HEAD -- implementations/` — empty, re-confirmed. `git diff --stat 5243b8f..HEAD -- .claude tests` — 969 insertions(+), 45 deletions(-) = **1014 lines**, 72% of the session's 1400-line budget. Both figures match the brief exactly.

**Coverage**: not available — this repository configures no coverage tool.

### Fixtures and executions built for this verification

None of the following were read-and-trusted; every one was run:

1. A hand-built `.implementation/position.jsonl` carrying a `kind: "step"` event with **no `suiteDigest` key at all** (the literal pre-change shape), fed through `_step_verdicts` and then through `impl_position.derive()` end-to-end — confirmed `None`, never a crash, never `True`, for both `outcome: "returned"` and `outcome: "raised"`.
2. Real markdown `@step:level run_suite` parsed through `impl_position.parse_items()` and handed to `derive()` — confirmed `POSITION_WITNESS_NOT_LEVELABLE` fires from an actual parse, not a hand-built item dict.
3. A full CLI invocation of `position` against a two-item sequence (`@step run_suite` valid, `@step nosuch` invalid) — confirmed exit 2, `code: POSITION_STEP_UNKNOWN`, detail names both `nosuch` and `run_suite`.
4. The exact `resolve.command` string that refusal published, extracted from the JSON, interpreter-substituted, and **executed as a real subprocess** against the real target — exit 0, opened a genuine `discuss` record. Not merely asserted non-empty.
5. A second CLI invocation with `__steps__` completely undeclared — confirmed `STEPS_UNDECLARED` fires ahead of `POSITION_STEP_UNKNOWN` (design's stated ordering), by execution.
6. `suite_digest()` executed against a hand-built tree: confirmed a `tests/conftest.py` addition moves the digest (kills the narrower `test_*.py` glob) while `source_digest` on the same tree does not move; confirmed creating a previously-absent `tox.ini` moves the digest.
7. `_step_verdicts` executed against a three-event ledger (stale+returned, then current+returned, then current+raised for the same step name) — confirmed stale-beats-outcome and latest-wins-by-append-order, both by direct execution, not by reading the fold's code.
8. `rg` across the whole repository (not just the changed files) for every `stepVerdicts` construction site — confirmed exactly three: `_position_write_evidence`, `cmd_probe`, `cmd_verify`. No fourth site exists anywhere, in this session's tree, that nobody wired.
9. `FORGE_VOCABULARY_FLOOR`/lexicon guard suites run directly: `ReportFirstSectionProseTests` (5) + `ForgeVocabularyDerivedGuardTests` (8) = 13/13 green.
10. `GATING_REFUSALS`, `_WORK_STATE_RESOLUTIONS`, `COMMANDS` inspected live in a Python REPL against the actual imported module (not read as text): 66 total gating codes, 34 invocation-defect / 32 work-state, `POSITION_STEP_UNKNOWN` present in the resolutions dict, `POSITION_WITNESS_NOT_LEVELABLE` confirmed **absent** from `GATING_REFUSALS` (genuinely unrostered).

### Spec Compliance Matrix

| Requirement | Scenario | Test / Execution | Result |
|---|---|---|---|
| Step Witness Kind | A position item declares a step witness | `test_step_joins_witness_kinds_and_operand_required_kinds` (`test_implementation_core.py`) + my own `parse_items('@step run_suite')` → `kind='step', operand='run_suite'` | COMPLIANT (behavioural) |
| A Leveled Step Refuses, Never Derives Silently | A leveled step item is rejected, not swallowed | `WitnessNotLevelableTests.test_a_leveled_step_item_is_refused_not_a_keyerror` + my own `parse_items('@step:level run_suite')` → `derive()` raises `POSITION_WITNESS_NOT_LEVELABLE` from a real parse | COMPLIANT (behavioural) |
| Step Derivation Reads Only Evidence | A step never run derives unmeasured | `StepDeriveTests.test_a_step_never_run_derives_unmeasured` — green | COMPLIANT |
| | A raised outcome derives False, never None | `StepDeriveTests.test_a_raised_step_derives_false_never_none` — green; confirmed independently via direct `derive()` call | COMPLIANT (behavioural) |
| Suite Digest Covers Source, Tests, and the Environment Declaration | Adding a test file moves the suite digest, not the source digest | `SuiteDigestTests.test_adding_a_test_file_moves_the_suite_digest_not_the_source_digest`, `…_adding_conftest_moves_the_digest_proving_the_walk_is_not_test_star` — both green; independently reproduced (conftest.py, item 6 above) | COMPLIANT (behavioural) |
| | A missing environment file still contributes a value | `SuiteDigestTests.test_creating_tox_ini_moves_the_digest_absence_was_a_value`, `…_creating_pytest_ini_moves_the_digest_too` — green; independently reproduced (tox.ini, item 6 above) | COMPLIANT (behavioural) |
| The Ledger Carries Currency, Old Events Read Safely | A pre-existing undigested event reads as not current | `CmdStepDigestTests.test_a_pre_change_event_with_no_digest_key_folds_to_none` — green; independently reproduced end-to-end through `derive()` (item 1 above) | COMPLIANT (behavioural) |
| Step Verdicts Are Assembled By The Caller | A stale digest overrides a returned outcome | `CmdStepDigestTests.test_a_stale_digest_beats_a_returned_outcome_folds_to_none` — green; independently reproduced with a 3-event ledger (item 7 above) | COMPLIANT (behavioural) |
| Unknown Step Operand Is A Classified, Roster-Visible Refusal | A position item names an undeclared step | `StepOperandRefusalTests.test_an_undeclared_step_operand_refuses_position_step_unknown` — green; independently reproduced via real CLI subprocess + executed the published `resolve.command` (items 3–5 above) | COMPLIANT (behavioural) |
| Gating Recomputes Fresh, No Bypass | A stale offer does not bypass a disagreeing step witness | No new dedicated test — mechanism genuinely unchanged (confirmed: zero diff lines touch `cmd_gate`/`SEQUENCE_NOT_REACHED`/`POSITION_DISAGREES`). Verified by inspection: `_position_write_evidence`→`_step_verdicts`→`suite_digest` carries no caching or memoization anywhere in the chain, so every `gate`/`step` call recomputes the step witness fresh by construction | COMPLIANT (static — design correctly scoped this as "unchanged, restated") |
| Skip-Laundering Is A Stated Non-Goal | (doc requirement itself) SKILL.md/usage.md state the non-goal | `rg` confirms the exact sentence in both `SKILL.md:2288` and `usage.md:1683-1684` | COMPLIANT (behavioural — grep against the live file) |
| | A module-level skip still reads as returned | The normative clause ("SKILL.md/usage.md MUST state this as a non-goal") is satisfied by direct grep of both files. No dedicated runtime test exercises a real `pytest` module-level skip through `cmd_step` — see WARNING 1 for why, and why the underlying mechanism is exercised indirectly. | COMPLIANT (documentation requirement met; runtime depth noted as WARNING 1) |

**Compliance summary**: 9/9 requirements satisfied; 11/11 scenarios compliant — 10 by runtime test/execution, 1 (the module-level-skip scenario) by direct verification of the documentation text the requirement itself asks for, discussed in WARNING 1.

### Three-Builder Parity — independently re-verified

`StepVerdictsParityTests.test_all_three_builders_agree_on_step_verdicts` (real `step` subprocess run,
then `mock.patch.object` spy on `position_state` capturing the exact evidence dict each of
`_position_write_evidence`, `cmd_probe`, `cmd_verify` builds) — green, re-run in isolation.
`test_wiring_only_position_write_evidence_would_leave_probe_and_verify_unmeasured` — green, proves
the specific defect (wiring only one builder) the design's rejected-alternative-3 names.

Extended past the apply record's own proof: a repository-wide `rg -n "stepVerdicts"` (not scoped to
the changed files) turns up exactly the same three construction sites and nothing else — no fourth
site anywhere in this session's tree that nobody wired.

### Reachability — every new refusal

| Refusal | Raise site | Reachable how | Proven |
|---|---|---|---|
| `POSITION_STEP_UNKNOWN` | `cmd_position` (`implementation_cli.py`) | Real markdown `@step nosuch` through the real CLI | Executed: exit 2, correct code/detail, then executed the published `discuss` resolution to completion (exit 0) |
| `POSITION_WITNESS_NOT_LEVELABLE` (leveled arm) | `_resolve_deriver` inside `impl_position.derive()` | Real markdown `@step:level <name>` — `"step"` is in `WITNESS_KINDS` but absent from `_LEVEL_DERIVERS` | Executed: `parse_items` + `derive()` raises it from a genuine parse, not a hand-built item |
| `POSITION_WITNESS_NOT_LEVELABLE` (two-state arm) | Same function, other lookup | **Not markdown-reachable today** — `parse_items` never emits a kind outside `WITNESS_KINDS`, and every member besides `record` now has a `_DERIVERS` entry. The design and the test (`test_the_two_state_lookup_guard_is_structural_not_markdown_reachable`) both say so explicitly, in those words | Confirmed honest: this arm is structural insurance against a *future* kind, not a claim about today's grammar. Not a finding — the code says exactly what it is |

`test_every_gating_refusal_is_classified` is green **for the right reason**: `raised_refusal_codes`
statically AST-scans `cmd_*` function bodies inside `implementation_cli.py` only.
`POSITION_WITNESS_NOT_LEVELABLE` is raised in `_core/implementation/impl_position.py`, one layer
below any `cmd_*` body — genuinely out of the scanner's file scope, not absent because the code
never runs (proven live above). It is not in `GATING_REFUSALS` (confirmed via live import), joining
the pre-existing non-rostered class (`POSITION_ITEM_MALFORMED`, `POSITION_WITNESS_UNKNOWN_KIND`)
`parse_items` already documents.

### Correctness (Static + behavioural evidence)

| Item | Status | Evidence |
|---|---|---|
| `"step"` joins `WITNESS_KINDS`/`OPERAND_REQUIRED_KINDS` | Implemented | Live import: both frozensets contain `"step"` |
| `_derive_step` is a plain dict reader, no digest/ledger/path math | Implemented | Source read; `_derive_step` body touches only `evidence.get("stepVerdicts")` |
| `suite_digest` walks `*.py` under `src/`+`tests/` (not `test_*.py`) plus 5 fixed manifests | Implemented | Source read + behavioural (conftest.py, tox.ini) |
| `suite_digest` never merges into `source_digest`; docstrings name each other | Implemented | Diff on `source_digest` is empty (untouched); both docstrings read and cross-reference each other verbatim |
| `cmd_step` writes `suiteDigest` unconditionally, on every resolved run | Implemented | `CmdStepDigestTests` green (returned + raised both carry it); response dict itself never gains the key (`test_the_returned_response_dict_never_gains_suite_digest` green) |
| `_step_verdicts` compares digest before outcome (stale beats red) | Implemented | Behavioural: 3-event ledger reproduction (item 7) |
| Three evidence builders share one fold, no fourth site | Implemented | Repo-wide grep + parity test, both independent of the apply record |
| `POSITION_STEP_UNKNOWN` classified `WORK_STATE`, publishes something runnable | Implemented | Executed end-to-end; **clarification, not a defect**: `resolve.kind == "question"` (never `"command"`) — the runnable artifact is the `discuss` command embedded in `resolve.command`, which I ran to completion. This is the correct shape for a decision only a human can make (the docstring says so explicitly) and matches every other `WORK_STATE` code's own resolution shape in this file |
| 66/34/32 counts in `SKILL.md`+`usage.md` match the code, not just the test | Implemented | Live-derived from the imported module (`len(GATING_REFUSALS)`, split by classification), independent of `test_the_doctrine_states_the_split_the_roster_actually_holds`, which itself reads the doc text at runtime rather than a hardcoded literal |
| Non-goal stated in both docs | Implemented | Grepped both files directly |
| `implementations/` untouched | Confirmed | `git diff --stat main..HEAD -- implementations/` empty |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| One field on the existing `step` event, not a sibling kind | Yes | `cmd_step` writes `suiteDigest` unconditionally on the one existing event shape |
| The guard lives at the lookup (`_resolve_deriver`), not a fourth special case | Yes | One `.get()`-based resolver at both `_DERIVERS`/`_LEVEL_DERIVERS` lookups; confirmed by reading `derive()` |
| `suite_digest` walks `*.py`, not `test_*.py` | Yes | Confirmed by source and by the conftest.py reproduction |
| Stale beats red — digest compared before outcome | Yes | Confirmed behaviourally |
| The new refusal is a work state, raised in `cmd_position` (correcting the proposal's `INVOCATION_DEFECT`) | Yes | Confirmed: `POSITION_STEP_UNKNOWN` classified `WORK_STATE`, raise sits inside `cmd_position`, `_step_operand_detail` returns rather than raises (found by the AST scanner) |
| All three evidence builders share one fold | Yes | Confirmed, extended past the apply record's own proof (repo-wide grep) |

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. **The "module-level skip still reads as returned" scenario has no dedicated runtime test exercising real `pytest` skip semantics.** The requirement's actual normative text — SKILL.md/usage.md MUST state this as a non-goal — is fully met and directly verified by grep. But the scenario's narrative (an entire module skipping at collection, `pytest` still exiting 0, the step still recording `"returned"`) describes a *target's own* `__steps__` callable's behaviour, which this forge change deliberately does not enforce or execute (design's own "Cross-Repository Contract" places that callable out of scope; no edit under `implementations/` here). The underlying mechanism the non-goal describes IS exercised indirectly: `_derive_step`/`_step_verdicts` never inspect *how* a suite exited internally, only the recorded `outcome` string — proven by `test_a_returned_and_current_step_derives_true`, which shows the derivation doesn't discriminate on internal test outcomes at all, skip or otherwise. No test in this codebase, before or after this change, shells out to a real `pytest` with a module-level skip and checks the ledger. Not a blocker — the claim is true by construction of `_derive_step`'s reading discipline — but a future change adding one target-fixture test that does exactly that would close this gap rather than leave it resting on construction alone.

2. **`POSITION_STEP_UNKNOWN`'s "runnable resolve" is a question with an embedded command, not a directly-runnable fix command.** Worth stating plainly since the launch brief's phrasing ("publishes a runnable resolve") could be read either way: `resolve["kind"]` is `"question"`, never `"command"`, for this code — correctly, since clearing it requires a human decision (edit `AGREED.md` or declare a new `__steps__` entry) that no flag can make on the caller's behalf. The runnable artifact is the `discuss --about record --question ...` command nested inside `resolve["command"]`, which I extracted from a real refusal and executed to completion (exit 0, opened a genuine discussion record). Not a defect — this is the same shape every other `WORK_STATE` code in the file uses — but the distinction matters for anyone building tooling against the `resolve` envelope expecting a fix command rather than a discussion-opener.

**SUGGESTION**: None.

### Things measured wrong in the launch brief

None found. Every quantitative claim in the brief (2176/2144+32, 385/385 unchanged, empty
`implementations/` diff, 969+45=1014 lines at 72% of 1400, the 66/34/32 doc counts, the
three-construction-site claim, the FORGE_VOCABULARY_FLOOR 13/13) was independently re-measured
here and matched exactly. The one phrasing imprecision — "publishes a runnable resolve" for
`POSITION_STEP_UNKNOWN`, which is actually a question envelope with a runnable command nested
inside it — is noted above as WARNING 2, not as an error in the brief; the resolve genuinely is
runnable, just not itself of `kind: "command"`.

### Verdict

**PASS WITH WARNINGS**

All 9 spec requirements are met, traced to named code, with 11/11 scenarios compliant: 10 proven by
a test that passed at runtime — either the suite's own coverage or a fresh, independent
reproduction built for this verification and executed against real fixtures, never read and
trusted — and 1 verified against the documentation text its own requirement asks for. The three-builder
parity claim was extended past the apply record's own proof with a repository-wide search
confirming no fourth construction site exists. Both new refusals were proven reachable from real
markdown/CLI input, including executing the published resolution end-to-end. The two WARNINGs are a
genuinely untested (but structurally true) non-goal scenario and a phrasing clarification about the
`resolve` envelope's shape — neither blocks archive.
