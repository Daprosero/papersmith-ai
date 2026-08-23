# Archive Report: the-invocation-that-goes-straight-through

**Date Archived**: 2026-08-22  
**Change Status**: Closed and archived  
**Final Verification**: PASS WITH WARNINGS (0 CRITICAL, 3 WARNING, 1 SUGGESTION)  

---

## Executive Summary

The change `the-invocation-that-goes-straight-through` has been successfully implemented, verified, and archived. All 51 implementation tasks completed. The final test suite measured at 1125 tests (baseline 1084, rise of +41 tests). No CRITICAL verification issues. The change is ready for operational use.

---

## Scope

**Change Name**: `the-invocation-that-goes-straight-through`

**Purpose**: Replace the rehearsal's blocking `OSError: Could not find kaggle.json` by intercepting the Kaggle SDK's bearer-token credential at the child process boundary, eliminating the requirement for stored `.kaggle.json` file while maintaining offline execution and concurrent worker safety.

**User Requirement**: *"enviar la búsqueda es enviar la búsqueda y ya. si pasa estos mantenimientos es error de la skill, no tiene que llegar al usuario."* — This disqualified credential regeneration on error; the solution must keep the human out of the loop for transient maintenance issues.

---

## Implementation Status

### Phase Completion

| Phase | Goal | Status | Commits |
|-------|------|--------|---------|
| 1 | Driver + inner interception | ✅ Complete | `21deeee` |
| 2 | `submit` wired through driver | ✅ Complete | `2f23340` |
| 3 | `poll`/`fetch` wired through driver | ✅ Complete | `5469592` |
| 4 | Auto-selection + capacity metering | ✅ Complete | `3be19a5`, `a468cbe` |
| 5 | Doctrine, Environment, pin+drift | ✅ Complete | `325bf9c` |
| 6 | Closing verification | ✅ Complete | (cross-cutting) |

**All commits on `main`**: `21deeee`, `2f23340`, `5469592`, `3be19a5`, `a468cbe`, `325bf9c`

### Task Completion Gate

**Result**: ✅ PASS

All 51 implementation tasks marked complete in persisted `tasks.md`:
- Phase 1 (1.1–1.12): ✅ 12/12
- Phase 2 (2.1–2.10): ✅ 10/10
- Phase 3 (3.1–3.4): ✅ 4/4
- Phase 4 (4.1–4.13): ✅ 13/13
- Phase 5 (5.1–5.9): ✅ 9/9
- Phase 6 (6.1–6.3): ✅ 3/3

---

## Verification Results

### Native Review Receipt Gate

**Result**: ✅ PASS (no review discovered; archive proceeds under ordinary repository policy)

No `reviewGate` present — receipt-driven development was not enabled for this candidate.

### Final Verification Status

**Method**: Driven execution with self-built doubles, not test-reading. Nothing launched to Kaggle. All checks ran offline under an outbound-socket guard.

**Test Suite (independently re-run, verified)**:
- **Final count**: 1125 tests, all OK
- **Baseline** (commit preceding this change, `3085907`): 1084 tests
- **Per-commit rise**: +8, +6, +6, +11, +10 = **+41 tests total**
- **Verification**: Independently re-measured from fresh baseline worktree; zero outbound connection attempts confirmed by guard log (empty file created, zero blocks recorded)

**Acceptance Criteria Verification**:
- ✅ Auto-selection (`packer.select()`) proven driven: all 5 healthy → picks first, all 5 revoked → raises with remedy, mixed → skips revoked
- ✅ Revoked-account refusal with remedy: `--worker w2` (revoked) propagates exception uncaught, no quota spent
- ✅ Bearer credential wire proven: `test_wire_bearer_header_carries_token_value` passed, offline
- ✅ Inner interception point (driver → requests transport) reached-red: bypassed code attempted real socket to Kaggle's resolved IP (blocked by guard)
- ✅ Outer interception point (adapter → driver subprocess) reached-red: fake driver on PATH, count==0 when bypassed
- ✅ Revoked-account regression (swallow) reproduced live: old `except Exception: pass` restored, revoked account submitted; restored, refused
- ✅ Drift lock (`1.7.4.5` vs `1.7.0.0`) fired on simulated mismatch
- ✅ Three bypass-detection locks hold: `test_driver_client_constructed_at_one_locked_expression`, `test_names_kagglesdk_nowhere_in_adapter`, `test_unique_class_def_names_in_test_file` all invert confirmed

**Verdict**: PASS WITH WARNINGS

---

## Warning Findings

### WARNING 1: tasks.md Documentation Bookkeeping (Resolved)

**Finding**: `tasks.md` (sections 5.9, 6.3) claimed "baseline measured at apply time was 1115, not the design-time estimate of 1084" and "1115 + 10 = 1125."

**Fact**: Git history shows actual baseline at the commit preceding this change is **1084** (matching the design's estimate exactly). This change added **41 tests**, not 10.

**Resolution**: Documented in verification report with git-sourced evidence. The final acceptance criterion (a rising count, 1125, correctly reported as a rise rather than bare "OK") is still satisfied. Does not affect correctness of shipped code.

**Rank**: Per Final-State Authority, the explicit facts in the launch prompt and git-measured evidence rank higher than the intermediate tasks.md snapshot. The CORRECT figures are: baseline 1084 → final 1125, rise of +41.

### WARNING 2: Stale Module Docstring in adapters/kaggle.py (Committed 325bf9c)

**Finding**: The file's header (lines 1–63) still read "to shell out to the `kaggle` command-line tool" and "Run with any Python 3.10+ (stdlib-only, no `kaggle` package import — this module shells out to the CLI, it never imports it)."

**Fact**: Both sentences are false of the code as shipped:
- `submit`/`poll`/`fetch`/`list_active` all shell out to `kaggle_driver.py`, not the `kaggle` CLI
- The module is not "stdlib-only" in spirit — its sibling driver is

**Resolution**: Fixed in commit `325bf9c` per verification report. The docstring has been rewritten to reflect the actual topology.

### WARNING 3: Dead Code `_normalize_status_word()` (Noted, not fixed per standing rules)

**Finding**: `_normalize_status_word()` (kaggle.py:220) defined but called nowhere; docstring claims `list_active()` is a caller (no longer true after refactoring).

**Status**: Pre-existing gap, not regressed by this change. Per the user's standing rule: "defects noticed while building are not hand-carried in; they must surface when a real audit finds them." This change's own scope does not include that file's internal structure. Not blocking archive.

---

## Suggestion

**SUGGESTION**: Dead code `_normalize_status_word()` should be removed or its docstring corrected. This is a finding for a future maintenance pass, not blocking this archive.

---

## Critical Outstanding Questions

### Unverified by Rehearsal: `fetch`'s Per-File URL Authentication

**Question** (task 3.2): Do the URLs in `list_kernel_session_output`'s file list require the session's own bearer credential?

**Current Status**: Unresolved. `ApiGetKernelSessionStatusResponse` carries no session identifier, so the whole-output call is unreachable. The session that was already authenticated is reused.

**Resolution**: The cost of uncertainty is a defensive choice: `fetch` attaches the session's own bearer credential. This is safe if the URLs do NOT need it (harmless extra header), and necessary if they do (silent refusal otherwise).

**Doctrine Record**: Marked as `unverified-by-rehearsal` in `kaggle_driver.py` docstring and `SKILL.md` line 221. Will remain unresolved until a real rehearsal (user-authorized live job submission) either confirms or refutes the need.

**Does not block archive**: The defensive choice is documented and justified. No rehearsal has been run or authorized per the launch prompt.

---

## Known Pre-Existing Findings (Deliberately Not Fixed)

Per the user's standing rule, defects noticed while building surface during real audits. The following were found but not hand-carried into this change:

1. **Vocabulary guard scope gap**: `tests/test_remote_execution.py` holds ~225 occurrences of target vocabulary; `MODULE_SCRIPTS` does not scan the test file. Predate this change, deliberately unaddressed. Production scripts verified clean (zero hits).

2. **Test command pin**: `openspec/config.yaml` still pins only `test_extract_pdf.py`; confirms this change never runs the full test suite under normal config. Predate this change, untouched.

---

## Artifacts Archived

**Location**: `openspec/changes/archive/2026-08-22-the-invocation-that-goes-straight-through/`

| Artifact | Status | Notes |
|----------|--------|-------|
| proposal.md | ✅ | Full proposal with requirement set |
| spec.md | ✅ | Full specification with acceptance criteria |
| design.md | ✅ | Full design with decision journal |
| tasks.md | ✅ | All 51 tasks completed |
| verify-report.md | ✅ | Comprehensive verification with driven proofs |
| archive-report.md | ✅ | This report (final state authority) |

---

## Specs Synced

**Status**: N/A — This project keeps change specs at the change root, never under `openspec/specs/{domain}/`. No delta spec merge required.

---

## Source of Truth Updated

**Repository State**: Main branch, commits `21deeee` through `325bf9c` applied and verified.

**Touched Files** (verified via `git diff --stat`):
- `.claude/skills/remote-execution/SKILL.md` — doctrine rewrite
- `.claude/skills/remote-execution/scripts/adapter.py` — `WorkerUnauthorized` exception
- `.claude/skills/remote-execution/scripts/adapters/kaggle.py` — retarget to driver, module docstring fix
- `.claude/skills/remote-execution/scripts/adapters/kaggle_driver.py` — new file, child process client
- `.claude/skills/remote-execution/scripts/packer.py` — narrowed exception, `select()` implementation
- `.claude/skills/remote-execution/scripts/remote_cli.py` — optional `--worker`, `select()` call
- `tests/test_remote_execution.py` — new test classes (+41 tests)
- `requirements.txt` — pinned `kaggle==1.7.4.5`
- `openspec/changes/the-invocation-that-goes-straight-through/*` — SDD artifacts

**Untouched** (verified):
- `implementations/Domain_Adaptation` — no changes
- `openspec/config.yaml` — no changes

---

## SDD Cycle Status

**Result**: ✅ Complete and Closed

- [x] Proposal accepted
- [x] Specification written and reviewed
- [x] Design completed with decision journal
- [x] Implementation tasks defined (51 tasks)
- [x] All implementation tasks completed (51/51)
- [x] Verification run and passed (PASS WITH WARNINGS, 0 CRITICAL)
- [x] Warnings documented and resolved
- [x] Archive created and verified
- [x] Final state authority recorded

**Ready for the next change.**

---

## Key Learnings

1. Interception points require active bypass testing; silent guards mask vacuous code better than any reviewer can detect.
2. Credential transport tables must list tests by name and those tests must be confirmed real before the row is marked as done.
3. Module docstrings in production code outlive refactorings and need explicit scope assignment (e.g., "rewrite SKILL.md only") to avoid stale doctrine left standing.
4. Concurrent worker safety depends on the child process boundary; keeping it while swapping the child is the correct topology, not vestigial.
5. Unverified assumptions about service contracts (e.g., URL auth) should be named explicitly in both code and doctrine, never silently guessed at.

