# Archive Report: the-path-that-reaches-a-run

**Change**: the-path-that-reaches-a-run  
**Archived to**: `openspec/changes/archive/2026-08-23-the-path-that-reaches-a-run/`  
**Date**: 2026-08-23  
**Status**: Complete — all tasks done, verification passed, specs merged to main

## Change Scope

This change absorbed and supersedes `the-step-that-closes-the-door-it-opened` (folder removed, recorded here for traceability). Both changes addressed the same causal story — the path to a run (provision → approve → spread → launch → refuse early) — and are archived together as one unified change.

## Artifacts Persisted

### Change Artifacts (Engram topic keys)
- Observation #1014: `sdd/the-path-that-reaches-a-run/proposal`
- Observation #1015: `sdd/the-path-that-reaches-a-run/spec`
- Observation #1016: `sdd/the-path-that-reaches-a-run/design`
- Observation #1017: `sdd/the-path-that-reaches-a-run/tasks`
- Observation #1021: `sdd/the-path-that-reaches-a-run/verify-report`

### Filesystem Artifacts
- **Archived change folder**: `openspec/changes/archive/2026-08-23-the-path-that-reaches-a-run/`
  - proposal.md ✅
  - spec.md ✅
  - design.md ✅
  - tasks.md ✅
  - verify-report.md ✅
  - archive-report.md ✅ (this file)
  
- **Merged specs**: `openspec/specs/spec.md` (new consolidated spec with 4 domains)

## Specification Domains

The spec establishes requirements across four capability domains:

1. **accelerator-contract** (New)
   - Accelerator Declaration: `run-config.json` names kind and architectures (not device models)
   - Pre-Training Comparison and Refusal: arriving capability checked against installed arch list before training
   - Dual-Architecture Torch Coverage: sm_60 and sm_75 coverage as an accepted per-shard cost

2. **launch-authorization** (New)
   - Per-Campaign Consent Gate: `submit` refuses without invocation-carried consent
   - Consent Is Never Persisted: no config keys, env vars, or switches outlive the process

3. **remote-execution** (Modified)
   - Full Healthy-Account Spread Consumption: every healthy account receives the distribution; excluded accounts named with reason
   - `pin-published` Owns Its Time Budget: separate 240s timeout from git transfer time
   - `--entrypoint` Names the Shape It Wanted: reports file-expected, never misdirects to regenerate
   - `status` Refuses Only on Its Own Declared Flags: parser-derived, never hand-written

4. **target-environment-provisioning** (New)
   - Target Manifest Provisioning: forge installs target's declared manifests without hardcoding package names
   - Liveness Requires Executed Evidence: `.venv` alone insufficient; must execute entry-module import
   - Harness Name Resolution from Target Declaration: distinguishes absent from present-under-different-name
   - Probe and Harness Agree on Run Readiness: one gate, one fact (required scale)
   - Guiding Table Completeness: flags column and stale-pin row, derived from parser

## Task Completion

All 8 implementation phases complete with delivery of 9 commits on `main`:

1. ✅ Accelerator declare+gate (9492b13)
2. ✅ Dual-arch torch build (7d39ca7)
3. ✅ Spread consumption (95280d2)
4. ✅ Consent gate rewritten as unconditional invariant (9e3b9f8, includes correction)
5. ✅ env provisioning + liveness (83a30ab)
6. ✅ Harness resolution + gate agreement (5a18e4a)
7. ✅ Three misdirecting refusals (7e7260c)
8. ✅ Guiding table doctrine (abe06a2, 2228749)

Finding 10 (`search_ceilings` KeyError in `implementations/Domain_Adaptation/harness.py:835-840`) is a recorded handoff — no task, target repository, read-only, out of scope.

## Verification

**Verdict**: PASS WITH WARNINGS

Per `verify-report` (Observation #1021):
- Baseline: `python3 -m unittest discover -s tests` → 1269 tests, OK
- Driven verification: all 8 requirement domains behaved exactly as specified under real execution
- Test suite growth: 1160 → 1269 (+109 tests, traced to exact additions in commits)
- Socket guard verification: all 1269 tests re-ran under outbound-socket guard (never site-packages) — 0 blocked outbound attempts
- No CRITICAL findings against the shipped code

### Warnings Recorded

1. **Unproven, correctly recorded**: whether pushing to an existing kernel preserves the accelerator chosen in Kaggle's UI (only a rehearsal settles this; proposal explicitly does not guess)
2. **Factual correction**: the term "CREDA" (bare, not MIL_CREDA) appears 30+ times in `.claude/skills/proposal-deliberation/engine/proposal-workspace.ts` (pre-existing, unrelated skill, never touched by this batch; false cognate with MIL-CREDA)

## State of the Change at Close

### Code Changes (per spec scope)
- `.claude/skills/remote-execution/` — all phases landed with runner accelerator declaration/comparison, consent gate, spread consumption, three refusal-message fixes, guiding table
- `.claude/skills/proposal-implementation/` — all phases landed with env provisioning, harness name resolution, gate agreement, guiding table

### Scope Boundaries (Preserved as-is, Out of Scope)
- `implementations/Domain_Adaptation` — never touched (Finding 10 handoff remains unimplemented)
- `openspec/config.yaml` — never touched (test pinning deliberately left for real audit)
- Other skills — never touched
- Nothing launched to Kaggle — all verification local or against doubles

### Known Open Questions (Resolved in This Batch)
1. ✅ Refuse or warn on accelerator mismatch → **Refuse** (user settled)
2. ✅ Unit of consent — per launch or per campaign → **Per campaign** (user settled)
3. ✅ Dual-architecture torch build now or after rehearsal → **Both halves this batch** (user settled)

### Costs Accepted Knowingly (Visible in Diff)
- Consent gate turns existing `submit` tests red (visible, never folded silently)
- Per-kernel torch install adds minutes per shard × 30 shards (per batch honest cost statement)
- 1200-line review budget (ordered commits, manageable per-commit)
- Entry-module import slows probe (truthful refusal, never a hang)

## Rollback

Each commit independently revertable via `git revert`. Consent gate (commit 4) restores ungated `submit`; env+liveness (commits 5–6) restore deadlock; accelerator gate (commit 1) restores silent CUDA death.

No ledger schema change; additive under schemaVersion 1.
No migration required; pre-change jobs retain backward compatibility.

## Files in Archive

```
openspec/changes/archive/2026-08-23-the-path-that-reaches-a-run/
├── proposal.md           (intent, findings, approach)
├── spec.md              (4 requirement domains)
├── design.md            (14 decisions, contracts, threat matrix)
├── tasks.md             (8 implementation phases, all done)
├── verify-report.md     (verification findings, all passing)
└── archive-report.md    (this file)
```

## Source of Truth

All specifications are now reflected in the following main specs:
- `openspec/specs/spec.md` — consolidated spec with all 4 domains

The change cycle is complete. The change is ready for operational deployment.
