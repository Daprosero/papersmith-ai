# Archive Report: the-audit-that-runs-what-it-claims

**Date Archived**: 2026-08-21  
**Archive Location**: `openspec/changes/archive/2026-08-21-the-audit-that-runs-what-it-claims/`  
**Status**: **COMPLETE** ✓

## Change Summary

**Change**: `the-audit-that-runs-what-it-claims`  
**Subject**: `skill-audit` (the auditor itself)  
**Store Mode**: openspec  
**Artifact Store**: openspec/changes (specs kept at change root, per project convention)

## Final State Authority

This archive report describes the state of the change AT CLOSE (2026-08-21, 19:02 UTC). Final-state authority is established per `skills/_shared/sdd-archive/SKILL.md`:

1. **Native review authority** — not applicable (review mode is off)
2. **Persisted tasks artifact** — all tasks marked `[x]`, complete
3. **Explicit final-state facts from launch** — verification PASSED (0 CRITICAL / 0 WARNING / 0 SUGGESTION)
4. **Intermediate snapshots** — not consulted for final-state claims

## Artifacts Archived

| Artifact | Location | Status |
|----------|----------|--------|
| proposal.md | `openspec/changes/archive/2026-08-21-the-audit-that-runs-what-it-claims/proposal.md` | ✓ Present (16351 bytes) |
| spec.md | `openspec/changes/archive/2026-08-21-the-audit-that-runs-what-it-claims/spec.md` | ✓ Present (8814 bytes) |
| design.md | `openspec/changes/archive/2026-08-21-the-audit-that-runs-what-it-claims/design.md` | ✓ Present (12791 bytes) |
| tasks.md | `openspec/changes/archive/2026-08-21-the-audit-that-runs-what-it-claims/tasks.md` | ✓ Present (9090 bytes) |

**Note on verify-report**: Verification was performed by `sdd-verify` via direct tool execution (not by reading tests). Per launch context, verify-report.md was not persisted to the change directory; only the PASS result is recorded here.

## Task Completion Gate

**Gate Result**: ✓ PASSED

All implementation tasks in `tasks.md` are marked complete:
- **Slice 1** (Report shape): 1.1–1.13 all `[x]` (13 tasks)
- **Slice 2** (Structure): 2.1–2.17 all `[x]` (17 tasks)
- **Slice 3** (Walkthrough): 3.1–3.14 all `[x]` (14 tasks)
- **Phase 4** (Final cross-slice): 4.1–4.3 all `[x]` (3 tasks)

**Total**: 47 tasks, 47 complete (100%)

## Verification Report

**Final Verification Status**: ✓ **PASS**

Verified by: `sdd-verify` (direct tool execution, not test-read)  
- CRITICAL issues: 0
- WARNING issues: 0
- SUGGESTION issues: 0

**Test Suite Results**:
- Baseline suite: 973 tests OK
- Slice 1 added: +8 tests (delta suite +30)
- Slice 2 added: +15 tests (delta suite +15)
- Slice 3 (measured): +30 tests (final count 1026 total)
- **Final total**: 1026 tests OK

Verification methodology: The verifier constructed independent subjects for:
- `disk-stale`, `builder-broken`, `document-wrong` (structure outcomes)
- Underivable side and occupied box edge cases
- Documented-refusal-as-pass and real stall scenarios (walkthrough)
- Runtime derivation of `move_roster` (injected synthetic move into SKILL.md copy, verified no matching code literal)

**Duplicate class/test-name check**: 124 tests in `tests/test_skill_audit.py` — no duplicate class or `test_` method names (verified via `ast`).

## Deliberate Deferral

**Config-level test-command limitation** (openspec/config.yaml:19,21):  
The project's `test_command` pinning to `test_extract_pdf.py` means `tests/test_skill_audit.py` (124 tests, +53 added by this change) is NOT part of the automated test suite run in future normal SDD phases.

**Why this defect was left unfixed**: Per the user's explicit SDD rule, defects discovered while building the maintenance skill are NOT hand-carried into it. They surface when a real audit finds them, which is also the only evidence the mechanism works. This is the intended first catch for the first real audit run.

**Resolution path**: When `skill-audit` is audited in a future change, the config-level pinning will be discovered and can be addressed as part of that audit's findings.

**Status in archive**: This is a KNOWN and INTENTIONAL deferral, recorded here for future audit reference.

## Deliverables Shipped

The change shipped three things into `skill-audit`'s diagnostic process:

1. **`structure` subcommand**
   - Derives three filesystem sides: declared (from SKILL.md table), on-disk (actual files), from-zero (rebuilt by subject's scaffold command)
   - Arithmetic adjudication: `disk-stale`, `builder-broken`, `document-wrong`, or `three-way-divergence`
   - Exit code 2 for unproabeable sides (missing scaffold, missing root)
   - Enforced by tests covering all outcomes and edge cases

2. **`walkthrough` subcommand**
   - Ordered recipe-driven user-mode flow through the subject
   - Stall detection: names the first gate index where the sequence halts
   - Box lifecycle: single box for whole sequence, optional per-step reset
   - Timeout and stall detection (first observation contradicting expected outcome)
   - Exit code 0 for any verdict, 2 for inability

3. **Enforced report-shape items**
   - `## Move outcomes` — one row per move parsed from SKILL.md (NOT hand-written list), each `ran` or `skipped: <reason>`
   - `## Repair units` — table with unit names, findings, changed lines; every `F<n>` finding covered exactly once
   - Updated `## Handoff` prose to reflect repair-unit grouping
   - `check-report` enforces both shapes (REPORT_SHAPE, verified by ReportSchemaSelfDescriptionTests)

## Spec Sync

**Project Convention**: This project keeps specs at the change root (`openspec/changes/{change-name}/spec.md`) rather than in a centralized `openspec/specs/{domain}/` directory.

**Action Taken**: No merge operation. The spec.md remains in the archived folder and becomes part of the audit trail.

**Main Specs Directory**: `openspec/specs/` did not exist before this change and does not contain a merged spec. This is consistent with the project's spec-at-change-root convention.

## Archive Verification (Mechanical Copy Contract)

**Mechanical Copy Method**: `git mv` (successful)

**Diff -r Output** (source snapshot vs. archived folder):
```
(empty — no differences found)
```

**Verification**: ✓ PASSED
- Archive created successfully via `git mv`
- Pre-move snapshot compared against post-move archive
- Diff -r returned empty (no byte differences)
- All four artifacts present and byte-identical
- Source directory confirmed removed

Per the Mechanical Copy Contract in `skills/_shared/sdd-archive/SKILL.md`, an empty diff is the only passing evidence. Bytes were never routed through model Read/Write operations.

## Prior Change State

**Note**: The prior change `the-skill-that-audits-the-others` is still unarchived. Per launch instructions, it was NOT archived in this run — only noted here for continuity. Its SDD state remains in `openspec/changes/the-skill-that-audits-the-others/`.

## SDD Cycle Completion

**Cycle Status**: ✓ COMPLETE

The change has successfully passed through all SDD phases:
- ✓ **sdd-propose**: Defined scope, four identified gaps, approach to close them
- ✓ **sdd-spec**: Specified behavior for `structure` and `walkthrough`, report shapes
- ✓ **sdd-design**: Designed three work slices (order-free), stall detection, box lifecycle
- ✓ **sdd-tasks**: Planned 47 implementation tasks across three slices and final cross-slice check
- ✓ **sdd-apply**: Completed all 47 tasks (marked `[x]`), landed three commits on `main`
- ✓ **sdd-verify**: Passed verification (0 CRITICAL/WARNING/SUGGESTION), 1026 tests OK
- ✓ **sdd-archive**: Archived to `openspec/changes/archive/2026-08-21-the-audit-that-runs-what-it-claims/`, verified byte-identity

**Ready for**: Next SDD change or ongoing maintenance.

## Observation IDs (Engram Mode)

Not applicable. This change was archived in **openspec mode**. Artifacts are persisted to the filesystem archive only, not to Engram persistent memory.

**Artifact Locations for Reference**:
- Change root: `openspec/changes/archive/2026-08-21-the-audit-that-runs-what-it-claims/`
- Project root: `/Users/diego/Proyectos/papersmith-ai/`
