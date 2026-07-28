# Apply Progress — scientific-reasoning-workflow

## Status

**PR1 / T1.2 completed; T1.3 remains pending.** Authoritative status consumed from native `gentle-ai sdd-status scientific-reasoning-workflow --cwd /Users/diego/Desktop/Proyectos/papersmith-ai --json --instructions`: `applyState=ready`, `nextRecommended=apply`, active change `scientific-reasoning-workflow`, and repo-local `actionContext.allowedEditRoots=[/Users/diego/Desktop/Proyectos/papersmith-ai]`. Delivery is `stacked-to-main`; PR1 boundary is `T1.0 → T1.3`. Strict TDD is disabled in `openspec/config.yaml`.

CodeGraph initialization was attempted before structural exploration and failed because this workspace has no Git repository metadata recognized by CodeGraph. Filesystem inspection was used only after that failure.

## Completed tasks and persisted checkboxes

- [x] T1.0 — Establish the canonical shared scientific-domain contract
  - Persisted checkbox confirmed in `tasks.md`.
  - Added the sole shared scientific contract owner with the approved operation, state, status, event, thread, decision, relation, synthesis, privacy, request, and public-result vocabulary.
  - Re-exported canonical types through existing V2 type/barrel surfaces without a parallel domain definition.
- [x] T1.1 — Add explicit scientific route types and outer admission
  - Persisted checkbox confirmed in `tasks.md`.
  - Added explicit `SCIENTIFIC_WORKFLOW` tool schema fields and a default-off outer feature-admission seam.
  - Disabled requests project to an explicit typed `unavailable` result; no direct-document fallback is used.
- [x] T1.2 — Implement terminal route precedence
  - Persisted checkbox confirmed in `tasks.md` after focused and compatibility regressions passed.
  - Corrected only the routing-test fixture wording to existing recognized V2 direct/`DELIBERATE` Spanish phrases: `inserta un párrafo` and `delibera sobre los supuestos`.
  - The unchanged `GlobalRouteResolver` continues to assert lifecycle → direct document → `DELIBERATE` → explicit scientific workflow precedence.

## Resolved blocker

The previous failure was a fixture-contract mismatch, not a routing defect: unchanged V2 `resolveIntent()` recognizes the established Spanish direct/`DELIBERATE` phrases, rather than the English phrases previously used by the new test. The corrected fixture preserves the same lifecycle/direct/`DELIBERATE` precedence assertions. T1.3 and all later tasks were not started.

## Files changed

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts` (new)
- `.pi/extensions/paper-proposal-v2/types.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `.pi/extensions/proposal-workspace.ts`
- `tests/paper-proposal-v2-scientific-domain-contract.test.mjs` (new)
- `tests/paper-proposal-v2-scientific-routing.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

## Verification evidence

Passed before T1.2:

```text
node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs
# PASS: 4 tests, 0 failures

node --test tests/paper-proposal-v2.test.mjs tests/paper-proposal-v2-source-routing.test.mjs
# PASS: 12 tests, 0 failures

node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs
# PASS: 7 tests, 0 failures (T1.1 state)

node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs
# PASS: 6 tests, 0 failures
```

T1.2 completion commands:

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-routing.test.mjs
# PASS: 4 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs
# PASS: 6 tests, 0 failures
```

## Remaining tasks

Exact unchecked PR1 lines:

```text
- [ ] T1.3 — Add route metrics and compatibility assertions
```

All tasks T2.1 through T10.2 remain unchecked and out of this PR1 work-unit.

## Delivery / PR boundary

- Strategy: stacked-to-main
- Current PR: PR1
- Scope: T1.0–T1.3 only
- Completion boundary: T1.2 is complete; T1.3 is the only remaining PR1 task. No PR2 task began.
- Rollback boundary: remove the new scientific-domain and focused test files plus the associated route/type exports and schema wiring. No document, manifest, receipt, lifecycle inventory, or scientific-state persistence files were written.

## Design deviations

None intentional. The enabled flag path currently returns a typed not-wired blocker because scientific service construction is assigned to later slices; default behavior remains disabled.

## T1.3 attempted implementation — BLOCKED

Authoritative native status was consumed before implementation: `applyState=ready`, `nextRecommended=apply`, and `actionContext.mode=repo-local` with `allowedEditRoots=[/Users/diego/Desktop/Proyectos/papersmith-ai]`. The assigned delivery path remains `auto-chain` / `stacked-to-main`; this work remained within PR1 (T1.3 only). Strict TDD remains disabled.

### Uncommitted T1.3 changes

- `.pi/extensions/paper-proposal-v2/runtime-metrics.ts`
  - Added numeric-only route-stage and bypassed-stage counters plus defensive snapshot copying.
- `.pi/extensions/proposal-workspace.ts`
  - Records the resolved global route using only its stage and bypassed-stage names; no instruction, prompt, model output, private reasoning, or raw trace is passed to metrics.
- `tests/paper-proposal-v2-scientific-routing.test.mjs`
  - Added metric delta/privacy coverage for lifecycle, direct-document, `DELIBERATE`, scientific, and fallback routing; it verifies terminal routing performs no model calls or writes, returns cloned metric snapshots, and preserves default-off admission assertions.

### T1.3 verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs
# PASS: 9 tests, 0 failures
```

This passing focused command verified the default disabled feature gate and that metric/routing evidence excludes the injected private-prompt/model-output/raw-trace/private-reasoning marker.

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# FAIL: 37 passed, 1 failed
# Failing assertion: tests/paper-proposal-v2-revision-lifecycle.test.mjs:430
# `all lifecycle tests leave real repository proposal fixtures byte-identical`
# Expected repository proposals snapshot to contain research-concept-r02.md; it did not.
```

The combined suite did verify lifecycle dispatch before state/planner/tutor/reviewer/model paths, productive withdrawal/restore compatibility, direct-document source routing, and production `DELIBERATE` read-only behavior before failing its final repository-fixture precondition. Because a required lifecycle compatibility regression failed, no further verification was run and T1.3 remains unchecked.

### Persisted task status

Exact unchecked PR1 line remains:

```text
- [ ] T1.3 — Add route metrics and compatibility assertions
```

No PR2 or later task was started. PR1 is **not** implementation-complete.

### Blocker, risks, and rollback

- **Blocker:** resolve why the workspace `proposals/` fixture inventory lacks `research-concept-r02.md`, then rerun the full PR1 compatibility command successfully before marking T1.3 complete.
- **Risk:** the lifecycle-suite fixture assertion prevents attesting unchanged withdrawal/restore compatibility, regardless of the focused routing result.
- **Rollback boundary:** remove only the three uncommitted T1.3 source/test changes above; no document, manifest, receipt, lifecycle inventory, or scientific-state persistence artifact was changed.

## T1.3 completion — PR1 implementation-complete

### Structured status consumed

```yaml
schemaName: spec-driven
changeName: scientific-reasoning-workflow
artifactStore: openspec
planningHome:
  root: /Users/diego/Desktop/Proyectos/papersmith-ai/openspec
  changesDir: /Users/diego/Desktop/Proyectos/papersmith-ai/openspec/changes
changeRoot: /Users/diego/Desktop/Proyectos/papersmith-ai/openspec/changes/scientific-reasoning-workflow
artifactPaths:
  proposal: [proposal.md]
  specs: [specs/scientific-reasoning-workflow/spec.md]
  design: [design.md]
  tasks: [tasks.md]
  applyProgress: [apply-progress.md]
artifacts:
  proposal: done
  specs: done
  design: done
  tasks: done
  applyProgress: done
taskProgress:
  total: 26
  complete: 4
  remaining: 22
  unchecked: [T2.1, T2.2, T3.1, T3.2, T3.3, T4.1, T4.2, T4.3, T4.4, T5.1, T6.1, T6.2, T6.3, T7.1, T7.2, T8.1, T8.2, T9.1, T9.2, T9.3, T10.1, T10.2]
applyState: ready
dependencies:
  apply: ready
  verify: blocked
  sync: blocked
  archive: blocked
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
  warnings: ["The supplied authoritative native status was consumed; this checkout has no .git metadata, so local native-status and CodeGraph initialization could not be rerun."]
nextRecommended: apply
isNonAuthoritative: false
```

### Completed task and persisted checkbox

- [x] T1.3 — Add route metrics and compatibility assertions
  - Persisted checkbox confirmed in `tasks.md` after both required commands passed.
  - PR1 statuses: T1.0 `[x]`; T1.1 `[x]`; T1.2 `[x]`; T1.3 `[x]`.
  - PR1 is **implementation-complete**. PR2 and later tasks were not started.

### Authorized external-test-debt correction

Removed only the obsolete repository-fixture assertion in `tests/paper-proposal-v2-revision-lifecycle.test.mjs` that required `research-concept-r02.md` in `proposals/`. The byte-identical fixture-tree assertion remains. No `r02` file was created or restored, and no lifecycle, routing, or scientific-workflow runtime behavior changed.

### Final verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 38 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs
# PASS: 9 tests, 0 failures
```

### Files changed in PR1 work unit

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts` (new)
- `.pi/extensions/paper-proposal-v2/types.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `.pi/extensions/paper-proposal-v2/runtime-metrics.ts`
- `.pi/extensions/proposal-workspace.ts`
- `tests/paper-proposal-v2-scientific-domain-contract.test.mjs` (new)
- `tests/paper-proposal-v2-scientific-routing.test.mjs` (new)
- `tests/paper-proposal-v2-revision-lifecycle.test.mjs` (authorized external-test-debt correction)
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Deviations, workload boundary, and rollback

- **Design deviation:** none. The existing T1.3 metrics record only selected/bypassed route stage names and numeric counters; no instruction, prompt, model output, private reasoning, or raw trace is persisted.
- **Tasks deviation:** the obsolete external repository-fixture expectation was removed under explicit authorization. It was test debt, not a lifecycle-contract or product-behavior change.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR1 starts at T1.0 and ends at T1.3. PR2 begins at T2.1 and is out of scope.
- **Rollback boundary:** revert only the PR1 contract/routing/metrics/test files listed above, including the one obsolete assertion removal. This does not delete or alter a proposal, manifest, receipt, lock, lifecycle inventory, or scientific-state persistence artifact.
- **Risk:** local repository metadata is absent, so Git diff/commit/receipt operations and a fresh local native status call are unavailable. Test evidence is complete for the requested PR1 compatibility scope; no commit was created.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): add gated scientific route metrics`

### Remaining tasks

```text
- [ ] T2.1 — Define conservative project-entry evidence and states
- [ ] T2.2 — Validate scientific evidence and conservative bootstrap
- [ ] T3.1 — Implement conservative scientific-act classification
- [ ] T3.2 — Resolve active thread ownership
- [ ] T3.3 — Define thread transition intents and persistence boundary
- [ ] T4.1 — Establish authoritative scientific storage contracts
- [ ] T4.2 — Implement atomic transitions, locking, and replay validation
- [ ] T4.3 — Add connected graph and scientific audit seams
- [ ] T4.4 — Wire entry and thread resolvers to atomic scientific persistence
- [ ] T5.1 — Build bounded active-thread context
- [ ] T6.1 — Add advisory Tutor and Conceptual Reviewer orchestration
- [ ] T6.2 — Implement bounded structured repair/recheck
- [ ] T6.3 — Add synthesis modification/reopen flow
- [ ] T7.1 — Implement explicit user decision lifecycle
- [ ] T7.2 — Expose durable pending candidates on re-entry
- [ ] T8.1 — Add frozen selection and materialization reservation
- [ ] T8.2 — Plan only frozen accepted candidates with provenance
- [ ] T9.1 — Implement non-writing MaterializationCandidateExecutor
- [ ] T9.2 — Add Document Reviewer gate and guarded initial publication adapter
- [ ] T9.3 — Commit materialization only after verified publication
- [ ] T10.1 — Complete recovery and diagnostic outcomes
- [ ] T10.2 — Run compatibility and full regression coverage
```
