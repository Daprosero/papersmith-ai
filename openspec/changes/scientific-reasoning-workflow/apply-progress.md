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

## PR1 formal closure — review-receipt limitation

Git authority is recovered: `main` and `origin/main` both point to the initial commit `b8b64dd9e11eae9992ad23e7426414c51b49b318`. `gentle_review inspect` succeeds but finds an empty workspace target with no reviewable paths. An attempted committed-only initial-range review using Git's empty-tree base `4b825dc642cb6eb9a060e54bf8d69288fbee4904` returned `native-start-base-ref-unresolvable`; `lineage_created: false`, and no review mutation occurred.

Therefore, the available native ordinary-review baseRef contract cannot bind a receipt to this root initial commit. No artificial changes were introduced, and no review receipt exists. By explicit user authorization, PR1 is formally complete through existing evidence: T1.0–T1.3 are checked; focused tests passed 9/9; the full V2 suite passed 38/38; there is no design deviation; and one authorized pre-existing lifecycle-test-debt assertion was removed. PR2 remains prohibited pending a new explicit user instruction.

## PR2 / T2.1–T2.2 — BLOCKED on first focused test failure

### Structured status and delivery context consumed

Native `gentle-ai sdd-status scientific-reasoning-workflow --cwd /Users/diego/Desktop/Proyectos/papersmith-ai --json --instructions` was authoritative before implementation:

```yaml
artifactStore: openspec
applyState: ready
nextRecommended: apply
taskProgress: { total: 26, completed: 4, pending: 22 }
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR2 / T2.1–T2.2 only
strictTdd: false
```

The PR2 workload gate is resolved by the supplied `auto-chain` / `stacked-to-main` delivery decision. No T3 or later task was started. CodeGraph initialization completed, but its `explore` subcommand was unavailable; narrow filesystem reads were used after that tool failure.

### Attempted scope and blocker

- Added a read-only `ProjectEntryResolver` boundary backed by injected revision-inventory and scientific-evidence ports, with no durable scientific store, proposal write, lifecycle-inventory mutation, or revision creation path.
- Added the canonical `ProjectEntry` projection and explicit observation-only bootstrap shape to `scientific-domain.ts`; no duplicate scientific statuses or enums were introduced.
- Added focused entry fixtures for entry states, pending candidates, corrupt/stale/orphaned/transaction evidence, and explicit bootstrap.
- **Blocker:** the first required focused command failed. The resolver returned `ACTIVE_SCIENTIFIC_PROJECT` for authoritative scientific state with no active revision, while the specification requires `SCIENTIFIC_ONLY`. Per the assigned stop rule, no corrective edit or further test command was run after this failure.

### Persisted task status

Neither task is complete and neither checkbox was changed:

```text
- [ ] T2.1 — Define conservative project-entry evidence and states
- [ ] T2.2 — Validate scientific evidence and conservative bootstrap
```

### Files changed before the stop

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` (new)
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `tests/paper-proposal-v2-scientific-entry.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs
# FAIL: 9 passed, 1 failed
# Failed: ProjectEntryResolver returns every conservative entry state from validated read-only evidence
# Expected: SCIENTIFIC_ONLY
# Actual: ACTIVE_SCIENTIFIC_PROJECT
```

No V2 regression command was run after the focused failure, as required.

### Remaining work, deviation, and rollback

- Remaining PR2 tasks: the two unchecked lines above.
- Design deviation: unresolved state-classification defect; `SCIENTIFIC_ONLY` must be selected whenever validated scientific state exists without an active managed revision, unless accepted candidates require `MATERIALIZATION_PENDING`.
- Risk/debt: `.codegraph/` is an untracked index generated by the mandatory CodeGraph initialization; it is unrelated to the PR2 work unit and must not be included in a PR.
- Rollback boundary: remove only the four uncompleted PR2 source/test paths listed above. No proposal document, managed revision, manifest, receipt, lifecycle inventory, or scientific authoritative record was modified.
- Conventional commit proposal: none until the focused test passes and both PR2 tasks can be evidenced.

## PR2 / T2.1–T2.2 — completed

### Structured status consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR2 / T2.1–T2.2 only
strictTdd: false
warnings: []
```

### Completed tasks and persisted checkbox evidence

- [x] T2.1 — Define conservative project-entry evidence and states
  - Corrected only `ProjectEntryResolver` classification: validated scientific state without an active managed revision now returns `SCIENTIFIC_ONLY`; a non-pending state returns `ACTIVE_SCIENTIFIC_PROJECT` only when one active managed revision is present.
  - The resolver remains deterministic and read-only: it creates no `r01`, changes no proposal/lifecycle state, and does not repair evidence.
- [x] T2.2 — Validate scientific evidence and conservative bootstrap
  - Confirmed schema/digest, event continuity, graph/reference, stale-revision, orphan, and transaction-marker validation remains fail-closed.
  - Confirmed bootstrap is explicit, observation-only, bound to exactly one verified active proposal, and records unknown history without changing documents or revision inventory.

Both task checkboxes were updated in `tasks.md` only after the focused and compatibility regressions passed.

### Files changed in this PR2 work unit

- `.gitignore` (narrow `.codegraph/` generated-tooling exclusion)
- `.pi/extensions/paper-proposal-v2/scientific-domain.ts` (canonical entry contracts and bootstrap observation shape from the prior stopped attempt)
- `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` (new; one classification correction in this resumption)
- `.pi/extensions/paper-proposal-v2/exports.ts` (entry-resolver export from the prior stopped attempt)
- `tests/paper-proposal-v2-scientific-entry.test.mjs` (new; retained as the authoritative behavior test)
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

`.gitignore` contains the narrow `.codegraph/` entry. No generated CodeGraph contents were added or modified for PR2.

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs
# PASS: 10 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures
```

The second command covers V2 lifecycle, direct-document source routing, and production `DELIBERATE` read-only behavior. No document, proposal, manifest, receipt, lifecycle, or scientific persistence files were created by the resolver tests.

### Deviations, risks, and delivery boundary

- **Design deviation:** none. The correction aligns the resolver with the specified distinction between `SCIENTIFIC_ONLY` and `ACTIVE_SCIENTIFIC_PROJECT`.
- **Risk:** the entry resolver is still an injected read-only evidence boundary; durable scientific-store wiring remains assigned to T4.4 and was not started.
- **PR boundary:** stacked-to-main PR2, T2.1–T2.2 only. T3 and later tasks were not started.
- **Rollback boundary:** remove only the PR2 entry-resolver/domain export/test additions and this resolver classification correction; this removes no proposal, revision, manifest, receipt, lifecycle inventory, or authoritative scientific record.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): add conservative project entry resolution`

### Remaining tasks

```text
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

## PR2 committed-range review limitation

PR2 is committed as `c0cc6d2 feat(paper-proposal-v2): add conservative project entry resolution`; its base is `b8b64dd9e11eae9992ad23e7426414c51b49b318`.

- `gentle_review inspect` succeeded on the clean workspace. Ordinary review start for the committed base range resumed lineage `review-11a054edad08b876` and selected the high-tier 4R review.
- Each selected lens—`review-risk`, `review-resilience`, `review-readability`, and `review-reliability`—rejected the native candidate view before review with the exact error: `candidate view directory is unsafe or writable`.
- No lens findings, finalization, or receipt were produced. No implementation was changed to work around this limitation.
- PR2 must not be formally closed by equivalent evidence until the user explicitly decides after this documented limitation is reported. PR3 remains prohibited.

## PR3 / T3.1–T3.3 — BLOCKED on first focused test failure

### Structured status consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR3 / T3.1–T3.3 only
strictTdd: false
warnings: []
```

### Attempted scope and blocker

- Added the isolated `ScientificActResolver`, canonical scientific act-resolution and thread-transition contracts, and a mandatory `ScientificThreadResolver` with read-only state and in-memory transition-intent ports only.
- Added focused resolver tests for act vocabulary, caller/instruction agreement, lifecycle/direct/`DELIBERATE` precedence, create/continue/select/clarify/block behavior, direct-neighbor validation, and no-document/no-role paths.
- **Blocker:** the first focused command failed in `ScientificActResolver classifies every approved bounded act`. `request materialization` returned `needs_clarification` instead of `REQUEST_MATERIALIZATION` because the current materialization classifier pattern did not match that instruction.
- Per the assigned stop rule, no corrective edit, task-checkbox update, compatibility regression, or T4+ work was performed after that failure.

### Persisted task status

```text
- [ ] T3.1 — Implement conservative scientific-act classification
- [ ] T3.2 — Resolve active thread ownership
- [ ] T3.3 — Define thread transition intents and persistence boundary
```

### Files changed before stop

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/types.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `.pi/extensions/paper-proposal-v2/scientific-act-resolver.ts` (new)
- `.pi/extensions/paper-proposal-v2/scientific-thread-resolver.ts` (new)
- `tests/paper-proposal-v2-scientific-act.test.mjs` (new)
- `tests/paper-proposal-v2-scientific-thread.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-act.test.mjs tests/paper-proposal-v2-scientific-thread.test.mjs
# FAIL: 14 passed, 1 failed
# Failed: ScientificActResolver classifies every approved bounded act
# Expected: REQUEST_MATERIALIZATION for "request materialization"
# Actual: needs_clarification
```

No later test command was run after the failure.

### Deviations, risks, and boundary

- **Design deviation:** unresolved classifier defect; no deliberate design departure was accepted.
- **Risk/debt:** all PR3 edits are unverified as a complete work unit. The transition port is intentionally in-memory/read-only and is not durable persistence; T4.1–T4.4 remain out of scope.
- **PR boundary:** stacked-to-main PR3, T3.1–T3.3 only. T4 and later were not started.
- **Rollback boundary:** remove only the PR3 resolver/domain-export/type/test additions listed above. No proposal, managed revision, manifest, receipt, lifecycle inventory, or durable scientific-state file was changed.
- **Conventional commit proposal:** none until focused and required V2 compatibility tests pass.

## PR3 / T3.1–T3.3 — completed

### Structured status consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR3 / T3.1–T3.3 only
strictTdd: false
warnings: ["CodeGraph MCP was unavailable; narrow known-path reads were used after the required CodeGraph attempt."]
```

### Completed tasks and persisted checkbox evidence

- [x] T3.1 — Implement conservative scientific-act classification
  - Corrected only the `REQUEST_MATERIALIZATION` classifier branch to recognize the explicit English `materialization` noun, while retaining lifecycle, direct-document, and `DELIBERATE` precedence plus conservative ambiguity handling.
- [x] T3.2 — Resolve active thread ownership
  - Verified the read-only/in-memory resolver creates only bounded user-originated idea threads, continues the validated active thread, selects eligible explicit threads, and clarifies or blocks every unresolved/invalid ownership case.
- [x] T3.3 — Define thread transition intents and persistence boundary
  - Verified only thread creation, selection, activation, and direct-relation transition intents are emitted through the in-memory transition port; unresolved or blocked paths emit no write intent.

All three checkboxes were updated in `tasks.md` only after every applicable focused and V2 compatibility command passed.

### Files changed in the PR3 work unit

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/types.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `.pi/extensions/paper-proposal-v2/scientific-act-resolver.ts` (new; final correction is limited to explicit `materialization` classification)
- `.pi/extensions/paper-proposal-v2/scientific-thread-resolver.ts` (new)
- `tests/paper-proposal-v2-scientific-act.test.mjs` (new; unchanged during the correction)
- `tests/paper-proposal-v2-scientific-thread.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-act.test.mjs tests/paper-proposal-v2-scientific-thread.test.mjs
# PASS: 15 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures
```

The regression command covers lifecycle behavior, direct-document source routing, and production `DELIBERATE` read-only behavior. No materialization, proposal, managed revision, manifest, receipt, persistence, context, role, or decision behavior was added.

### Deviations, risks, workload boundary, and rollback

- **Design deviation:** none. The correction makes the existing explicit materialization request classifier recognize the tested vocabulary; it does not relax ambiguity handling or route precedence.
- **Risk:** the scientific thread transition boundary remains intentionally in-memory/read-only until T4.4; no durable scientific persistence is implied by this PR3 work unit.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR3 is T3.1–T3.3 only. T4 and later tasks were not started.
- **Rollback boundary:** remove only the PR3 contract/type/export/resolver/test additions and this classifier correction. No document, proposal, managed revision, manifest, receipt, lifecycle inventory, or durable scientific record is affected.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): add scientific act and thread resolution`

### Remaining tasks

```text
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

## PR4 / T4.1–T4.2 — BLOCKED on first focused test failure

### Structured status consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR4 / T4.1–T4.2 only
strictTdd: false
warnings: ["CodeGraph MCP was unavailable; narrow known-path reads were used only after that failure."]
```

### Attempted scope and blocker

- Added the new storage-only `ScientificStateStore` and focused persistence fixtures. The store imports canonical domain contracts and implements the planned authoritative layout, immutable-event intent, WAL markers, sibling-renamed mutable records, fsync calls, regular-file/no-symlink checks, scientific locking, and fail-closed replay/recovery paths.
- Added only the barrel export required for the isolated storage contract. `ProjectEntryResolver`, `ScientificThreadResolver`, audit seams, materialization behavior, and all T4.3+ work remain untouched.
- **Blocker:** the first focused command failed before any V2 regression command was run. Every store fixture failed with `SCIENTIFIC_PROJECT_ROOT_UNSAFE` from `ScientificStateStore.safeProjectRoot()`. The temporary fixture root resolves through macOS's canonical `/private/var/...` path while its supplied `/var/...` spelling is a valid directory; the strict string-equivalence check rejects that valid root.
- Per the assigned stop rule, no corrective source/test edit, task-checkbox update, V2 regression, commit, or PR5 work was performed after this failure.

### Persisted task status

```text
- [ ] T4.1 — Establish authoritative scientific storage contracts
- [ ] T4.2 — Implement atomic transitions, locking, and replay validation
```

### Files changed before stop

- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts` (new)
- `.pi/extensions/paper-proposal-v2/exports.ts` (storage export only)
- `tests/paper-proposal-v2-scientific-persistence.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs
# FAIL: 5 passed, 5 failed
# First failure: ScientificStateStore persists only versioned authoritative records and rebuilds its projection
# Error: SCIENTIFIC_PROJECT_ROOT_UNSAFE
# Location: .pi/extensions/paper-proposal-v2/scientific-state-store.ts:279
```

No V2 regression command was run after the focused failure.

### Deviations, risks, and rollback

- **Design deviation:** unresolved safe-root validation defect; no accepted deviation.
- **Risk:** T4.1/T4.2 storage behavior is incomplete and must not be wired into entry/thread resolution. The unverified files should not be committed or included in a PR.
- **PR boundary:** stacked-to-main PR4, T4.1–T4.2 only. T4.3, T4.4, and later tasks were not started.
- **Rollback boundary:** remove only the new state-store/test files and the storage export. No project proposal, managed revision, manifest, receipt, lifecycle inventory, audit, entry resolver, or thread resolver was changed.
- **Conventional commit proposal:** none until the focused test passes and both task checkboxes can be evidenced.

## PR4 / T4.1–T4.2 — completed

### Structured status consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: both
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR4 / T4.1–T4.2 only
strictTdd: false
warnings: ["CodeGraph MCP was unavailable; narrow known-path reads were used after the required attempt."]
```

### Completed tasks and persisted checkbox evidence

- [x] T4.1 — Establish authoritative scientific storage contracts
- [x] T4.2 — Implement atomic transitions, locking, and replay validation

Both checkboxes were updated only after the focused persistence and relevant V2 regression commands passed.

### Correction and files changed

- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts`
  - Corrected only `safeProjectRoot()`: both the approved project root and candidate root are canonicalized with `realpath()` before comparison. This accepts the valid macOS `/var/...` temporary-root alias when both canonicalize to `/private/var/...`.
  - The root itself must still be a non-symlink directory. Non-canonicalizable roots, direct root symlinks, and paths that do not canonicalize to the approved root remain rejected; downstream directory/record checks continue to reject symlink traversal outside the canonical root.
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
  - Marked T4.1 and T4.2 `[x]`.
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`
  - Merged this PR4 completion evidence.

The existing PR4 storage module, barrel export, and focused persistence fixture remain the task implementation. No T4.3, T4.4, or later task was changed.

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs
# PASS: 10 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures
```

### Deviations, risks, workload boundary, and rollback

- **Design deviation:** none. The correction normalizes the approved and candidate root identities; it does not widen the allowed-root policy.
- **Risk:** no explicit fixture yet probes an ancestor alias escape beyond the canonical root. The implementation remains fail-closed for a symlinked root, non-canonicalizable root, and unsafe child records/directories; a later persistence-hardening task may add a targeted adversarial fixture without changing this completed PR4 scope.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR4 is T4.1–T4.2 only. T4.3, T4.4, and PR5+ remain out of scope and unchecked.
- **Rollback boundary:** revert the PR4 storage module, its barrel export, focused persistence test, and these task/progress updates. No proposal document, managed revision, manifest, receipt, lifecycle inventory, audit seam, entry resolver, or thread resolver was modified.
- **Conventional commit proposal (not created):** `fix(paper-proposal-v2): canonicalize scientific state roots`

### Remaining tasks

```text
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

## PR5 / T4.3–T4.4 — BLOCKED on first focused test failure

### Structured status consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR5 / T4.3–T4.4 only
strictTdd: false
warnings: ["CodeGraph MCP was unavailable after the required index check; narrow known-path reads were used."]
```

### Attempted scope and blocker

- Added an unverified `scientific-audit.ts` seam and provisional store-backed entry/thread resolver wiring, plus focused audit and resolver-store integration fixtures.
- The first required focused command failed; per the PR5 stop rule, no corrective edit, V2 regression, task-checkbox update, commit, or PR6+ work followed.
- Failure 1: `tests/paper-proposal-v2-scientific-audit.test.mjs` expected `runConsistencyAudit()` to return `PASS` for a temporary root without `proposals/`, but the existing V2 audit returned `FAIL`. This fixture expectation must be reconciled with the established V2 audit contract; do not weaken that contract.
- Failure 2: the canonical contract ownership fixture requires every scientific implementation module, including the new `scientific-audit.ts`, to import `scientific-domain.js`.

### Persisted task status

Neither assigned task is complete; both persisted checkboxes were re-read and remain unchecked:

```text
- [ ] T4.3 — Add connected graph and scientific audit seams
- [ ] T4.4 — Wire entry and thread resolvers to atomic scientific persistence
```

### Files changed before stop

- `.pi/extensions/paper-proposal-v2/scientific-audit.ts` (new; unverified)
- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts` (provisional graph validation and atomic resolver-transition adapter)
- `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` (provisional authoritative-store evidence adapter)
- `.pi/extensions/paper-proposal-v2/scientific-thread-resolver.ts` (provisional authoritative-store constructor path)
- `.pi/extensions/paper-proposal-v2/consistency-audit.ts`
- `.pi/extensions/paper-proposal-v2/self-audit.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `tests/paper-proposal-v2-scientific-audit.test.mjs` (new)
- `tests/paper-proposal-v2-scientific-store-resolvers.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-thread.test.mjs tests/paper-proposal-v2-scientific-audit.test.mjs tests/paper-proposal-v2-scientific-store-resolvers.test.mjs
# FAIL: 25 passed, 2 failed
# tests/paper-proposal-v2-scientific-audit.test.mjs: expected PASS, actual FAIL
# tests/paper-proposal-v2-scientific-domain-contract.test.mjs: scientific-audit.ts must import scientific-domain.js
```

No V2 regression command was run after this first focused failure.

### Deviations, risks, boundary, and rollback

- **Design deviation:** none accepted; the current code is unverified and must not be treated as completion.
- **Risk:** the provisional audit composition and resolver/store wiring may regress existing audit or lifecycle behavior until the focused failures are fixed and relevant V2 regressions pass.
- **PR boundary:** stacked-to-main PR5, T4.3–T4.4 only. T5 and later were not started.
- **Rollback boundary:** revert only the unverified PR5 source/test paths above and this progress entry; no proposal, managed revision, manifest, receipt, lifecycle inventory, or materialization behavior was intentionally changed.
- **Conventional commit proposal:** none until focused tests and relevant V2 regressions pass.

## PR5 / T4.3–T4.4 — completed

### Structured status consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec (session artifact mode: both)
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR5 / T4.3–T4.4 only
strictTdd: false
warnings: ["CodeGraph MCP was unavailable; narrow known-path reads followed the failed CodeGraph request."]
```

### Completed tasks and persisted checkbox evidence

- [x] T4.3 — Add connected graph and scientific audit seams
  - The audit fixture now creates the existing audit's required `proposals/` directory; `runConsistencyAudit()` remains unchanged.
  - `scientific-audit.ts` imports and uses the canonical `ScientificAuditStatus` from `scientific-domain.js`; it does not redefine shared audit-status ownership.
  - Scientific audit composition continues to preserve the three-artifact lifecycle inventory.
- [x] T4.4 — Wire entry and thread resolvers to atomic scientific persistence
  - Verified the existing authoritative-store create/select/activate/relation transition adapters, interrupted-commit recovery, replay, and no-document-write behavior through the resolver-to-store integration fixture.

Both tasks were marked `[x]` in `tasks.md` only after the focused PR5 suite and relevant V2 regression suite passed.

### Files changed in the PR5 work unit

- `.pi/extensions/paper-proposal-v2/scientific-audit.ts`
- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts`
- `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`
- `.pi/extensions/paper-proposal-v2/scientific-thread-resolver.ts`
- `.pi/extensions/paper-proposal-v2/consistency-audit.ts`
- `.pi/extensions/paper-proposal-v2/self-audit.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `tests/paper-proposal-v2-scientific-audit.test.mjs`
- `tests/paper-proposal-v2-scientific-store-resolvers.test.mjs`
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-thread.test.mjs tests/paper-proposal-v2-scientific-audit.test.mjs tests/paper-proposal-v2-scientific-store-resolvers.test.mjs
# PASS: 27 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures
```

### Deviations, risks, workload boundary, and rollback

- **Design deviation:** none. The fixture satisfies the unchanged V2 audit precondition; audit behavior was not broadened or weakened.
- **Risk:** the PR5 additions remain uncommitted and need the normal bounded-review receipt before commit. No PR6/T5 behavior was started.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR5 is T4.3–T4.4 only. PR6 begins at T5.1 and remains out of scope.
- **Rollback boundary:** revert only the PR5 audit/store-resolver integration source and test paths above plus these task/progress updates; no proposal, managed revision, manifest, receipt, or lifecycle inventory behavior is removed.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): compose scientific persistence audits`

### Remaining tasks

```text
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

## PR6 / T5.1 — BLOCKED on first focused test failure

### Structured status and delivery context consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR6 / T5.1 only
strictTdd: false
warnings: ["CodeGraph MCP was unavailable; narrow known-path reads followed the required attempt."]
```

### Attempted scope and blocker

- Added the standalone `ScientificContextBuilder`, importing canonical scientific contracts and exposing only a read-only scientific-state port plus an optional verified-fragment port. It selects the authoritative active thread and explicitly requested direct neighbors, validates context-scoped public evidence, applies count/byte caps, and has no persistence, role, materialization, document-write, or full-document-loader authority.
- Added canonical `ScientificRoleContext`, `ScientificDocumentFragment`, and `ScientificContextLimits` shapes to the sole shared scientific-domain contract owner, a barrel export, and focused T5.1 fixtures.
- **Blocker:** the first required PR6 focused suite failed in the cap-narrowing case with `SCIENTIFIC_CONTEXT_DOCUMENT_NOT_RELEVANT`. The builder caps selected evidence before document-fragment relevance validation. The test's second requested document fragment therefore no longer has a retained evidence reference, although the caller explicitly supplied that validated evidence. This boundary must be reconciled without widening context or permitting unrelated evidence.
- Per the assigned stop-at-first-failure rule, no corrective edit, task-checkbox update, V2 regression command, or `git diff --check` was run after this failure. T6/PR7 and all later work remain untouched.

### Persisted task status

`tasks.md` was re-read after the failure and remains unchanged:

```text
- [ ] T5.1 — Build bounded active-thread context
```

### Files changed before stop

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/scientific-context-builder.ts` (new)
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `tests/paper-proposal-v2-scientific-context.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-thread.test.mjs tests/paper-proposal-v2-scientific-audit.test.mjs tests/paper-proposal-v2-scientific-store-resolvers.test.mjs tests/paper-proposal-v2-scientific-context.test.mjs
# FAIL: 30 passed, 1 failed
# Failed: ScientificContextBuilder enforces narrowing count and byte caps without full-document or transcript expansion
# Error: SCIENTIFIC_CONTEXT_DOCUMENT_NOT_RELEVANT
```

No V2 regression command or `git diff --check` ran because the focused prerequisite failed.

### Deviation, risks, workload boundary, and rollback

- **Design deviation:** none accepted; the T5.1 context cap/relevance ordering defect is unresolved.
- **Risk:** the current builder and focused test are unverified as a work unit and must not be committed. The fix must preserve active-thread plus explicit-direct-neighbor-only selection, reject transitive/implicit expansion and raw role transcripts, and never load a full document or project history.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR6 is T5.1 only. T6/PR7 and later tasks were not started.
- **Rollback boundary:** remove only the four T5.1 source/test/export/domain changes listed above and this progress entry. No proposal, managed revision, manifest, receipt, lifecycle inventory, scientific event, decision, role orchestration, or materialization behavior was changed.
- **Conventional commit proposal:** none until the focused suite, relevant V2 regressions, and `git diff --check` pass.

## PR6 / T5.1 — completed

### Structured status and delivery context consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR6 / T5.1 only
strictTdd: false
warnings: []
```

### Completed task and persisted checkbox evidence

- [x] T5.1 — Build bounded active-thread context
  - The builder now derives document-fragment relevance from the full, validated act-relevant evidence set before any evidence cap.
  - It discards non-relevant requested document fragments, then applies evidence and document caps while preserving the request order of surviving fragments.
  - The change remains read-only: no role, persistence, materialization, document-write, or public-contract behavior was added.
  - The T5.1 checkbox was updated in `tasks.md` only after every command below passed.

### Files changed

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/scientific-context-builder.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `tests/paper-proposal-v2-scientific-context.test.mjs`
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-thread.test.mjs tests/paper-proposal-v2-scientific-audit.test.mjs tests/paper-proposal-v2-scientific-store-resolvers.test.mjs tests/paper-proposal-v2-scientific-context.test.mjs
# PASS: 31 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && git diff --check
# PASS: no output
```

Runtime harness: N/A — T5.1 is an isolated, read-only context-construction boundary with no public execution route wired in this PR.

### Deviations, risks, workload boundary, and rollback

- **Design deviation:** none. The correction follows the design's active/direct-neighbor-only and cap-narrowing rules without widening context.
- **Risk / decision:** non-relevant requested fragments are discarded before caps; selected relevant fragments retain caller order. The fragment port is still bounded by the selected IDs and byte/count limits.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR6 is T5.1 only. T6/PR7 and later tasks were not started.
- **Rollback boundary:** revert only the T5.1 domain/context-builder/export/test additions and these task/progress updates. No proposal, managed revision, manifest, receipt, lifecycle inventory, event, decision, role orchestration, or materialization behavior is affected.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): bound scientific role context`

### Remaining tasks

```text
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
## PR7 / T6.1–T6.3 — completed

### Structured status consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: both
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR7 / T6.1–T6.3 only
strictTdd: false
warnings: ["CodeGraph MCP initialization was unavailable; narrow known-path reads followed the failed MCP request."]
```

### Completed tasks and persisted checkbox evidence

- [x] T6.1 — Added `ScientificWorkflowService`, which invokes the existing Tutor adapter before the existing Conceptual Reviewer adapter for every candidate. Production construction reuses `ProductionModelRuntime` through the existing production adapters. Only allowlisted `TUTOR_ASSESSED` and `CONCEPTUAL_REVIEW_RECORDED` events are persisted; role outputs with planning, publication, document-edit, lifecycle, materialization, or acceptance authority are rejected.
- [x] T6.2 — Added structured `REPAIR_PROPOSED` findings with candidate identity/digest, category, evidence references, correction, and constraints. Each repair returns to Tutor and then rechecks with Reviewer; two repair/recheck cycles are permitted and a third requirement returns `REPAIR_LOOP_EXHAUSTED` without automatic acceptance or retry.
- [x] T6.3 — Added immutable `SYNTHESIS_REOPENED` events. Reopen preserves prior event/snapshot history and forces a new Tutor → Reviewer sequence with a new synthesis identity. It creates no decision lifecycle, materialization, publication, proposal, manifest, receipt, or revision behavior.

All three checkboxes were updated in `tasks.md` only after focused tests, relevant V2 regressions, and `git diff --check` passed.

### Files changed

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts`
- `.pi/extensions/paper-proposal-v2/scientific-workflow-service.ts` (new)
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `tests/paper-proposal-v2-scientific-synthesis.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-thread.test.mjs tests/paper-proposal-v2-scientific-audit.test.mjs tests/paper-proposal-v2-scientific-store-resolvers.test.mjs tests/paper-proposal-v2-scientific-context.test.mjs tests/paper-proposal-v2-scientific-synthesis.test.mjs
# PASS: 36 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && git diff --check
# PASS: no output
```

Runtime harness: N/A — PR7 adds an isolated scientific orchestration service; no public V2 scientific route is wired in this slice.

### Deviations, risks, workload boundary, and rollback

- **Design deviation:** none.
- **Decision:** reviewer `APPROVE_WITH_CHANGES` maps to scientific `REPAIR_REQUIRED`; only `APPROVE` maps to `PASS`. Role approvals never become scientific acceptance.
- **Risk:** the service is intentionally not connected to the public scientific route until later assigned integration work. Its persisted events use the existing authoritative scientific store and retain prior history, but no decision acceptance or materialization lifecycle exists in this PR.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR7 is T6.1–T6.3 only. T7/PR8 and later tasks were not started.
- **Rollback boundary:** revert only the PR7 service, canonical contract/payload allowlist/barrel updates, focused synthesis test, and these task/progress updates. No proposal, managed revision, manifest, receipt, lifecycle inventory, document route, or materialization record is affected.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): orchestrate scientific synthesis review`

### Remaining tasks

```text
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

## PR8 / T7.1–T7.2 — completed

### Structured status and delivery context consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR8 / T7.1–T7.2 only
strictTdd: false
warnings: ["Native status supplied by the parent is authoritative."]
```

### Completed tasks and persisted checkbox evidence

- [x] T7.1 — User-only decision lifecycle: `acceptDecision` admits only the exact persisted Tutor candidate and Conceptual Reviewer `PASS` digest, then appends an immutable `DECISION_ACCEPTED` event and persists an `ACCEPTED_UNMATERIALIZED` decision. Explicit user rejection, retraction, and modification preserve event history; rejected and retracted decisions are ineligible. Non-user, stale-digest, and missing-pass attempts block. No decision path writes a proposal, revision, manifest, or receipt.
- [x] T7.2 — Re-entry now projects durable pending candidate identities, active/direct-related thread summaries, eligibility/blockers, and an explicit materialization request next action. `MATERIALIZATION_PENDING` is returned only for accepted-unmaterialized decisions; restart preserves it, while retraction removes eligibility and corrupt evidence remains recovery-required.

The persisted `tasks.md` checkboxes were updated only after all focused tests, V2 regressions, and `git diff --check` passed.

### Files changed

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts`
- `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`
- `.pi/extensions/paper-proposal-v2/scientific-workflow-service.ts`
- `tests/paper-proposal-v2-scientific-decisions.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-synthesis.test.mjs tests/paper-proposal-v2-scientific-decisions.test.mjs
# PASS: 26 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && git diff --check
# PASS: no output
```

Runtime harness: N/A — PR8 remains an isolated scientific state/service slice; the public scientific route and materialization pipeline are not wired in this work unit.

### Deviations, risks, workload boundary, and rollback

- **Design deviation:** none.
- **Risk / decision:** decision snapshots are projections of immutable lifecycle events. `DECISION_RETRACTED` is required to move an accepted decision to `RETRACTED`; materialization selection, reservation, planning, execution, publication, `r01`, and successor behavior remain unimplemented and out of scope.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR8 is T7.1–T7.2 only. PR9/T8 and later tasks were not started. The authored work unit is 172 tracked additions plus 123 new-test lines before SDD artifacts, under the 400-line review budget.
- **Rollback boundary:** revert only the PR8 domain/state-store/entry-resolver/workflow-service changes, the focused decisions test, and these task/progress updates. No proposal, managed revision, manifest, receipt, lifecycle inventory, materialization record, or publication is affected.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): persist scientific decision lifecycle`

### Remaining tasks

```text
- [ ] T8.1 — Add frozen selection and materialization reservation
- [ ] T8.2 — Plan only frozen accepted candidates with provenance
- [ ] T9.1 — Implement non-writing MaterializationCandidateExecutor
- [ ] T9.2 — Add Document Reviewer gate and guarded initial publication adapter
- [ ] T9.3 — Commit materialization only after verified publication
- [ ] T10.1 — Complete recovery and diagnostic outcomes
- [ ] T10.2 — Run compatibility and full regression coverage
```

## PR8 validation correction — BLOCKED on V2 regression

The subsequent full validation run added the required missing-causal-review-pass assertion to the focused PR8 suite. The focused command passed **26/26**, but the relevant V2 regression command then failed at its first failure; no later command (including `git diff --check`) ran.

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-synthesis.test.mjs tests/paper-proposal-v2-scientific-decisions.test.mjs
# PASS: 26 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# FAIL: 28 passed, 1 failed
# tests/paper-proposal-v2-revision-lifecycle.test.mjs:397
# productive lifecycle negatives block safely while ambiguous revision deletion clarifies and content deletion stays DELETE
# Expected /MANAGED_DOCUMENT_MISSING/; actual MANAGED_STATE_MISSING
```

This failure is in an unchanged lifecycle fixture/observable result, not a PR8 scientific decision path. Per the stop rule, no source correction, additional regression command, or diff check followed. T7.1 and T7.2 were reverted to persisted `- [ ]` because the full validation prerequisite is not satisfied. PR8 is not ready for verify or commit; T8/PR9 and later remain out of scope.

## PR8 validation correction — completed

### Structured status and delivery context consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: both
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR8 / T7.1–T7.2 only
strictTdd: false
warnings: ["CodeGraph MCP was unavailable; narrow known-path reads followed the required index check."]
```

### Completed tasks and checkbox evidence

- [x] T7.1 — Implement explicit user decision lifecycle
- [x] T7.2 — Expose durable pending candidates on re-entry

Both persisted checkboxes were changed only after the lifecycle regression, focused PR8 suite, 29-test V2 regression suite, and `git diff --check` passed. The file was re-read after the update.

### Minimum compatibility correction

`.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts` now validates the requested managed document before derived state or receipt. A missing document therefore returns the existing `MANAGED_DOCUMENT_MISSING` immediately; `MANAGED_STATE_MISSING` is reached only after document existence succeeds. No error code, test, scientific decision semantics, materialization, or PR9 behavior changed.

### Files changed

- `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts`
- `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`
- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts`
- `.pi/extensions/paper-proposal-v2/scientific-workflow-service.ts`
- `tests/paper-proposal-v2-scientific-decisions.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
node --test tests/paper-proposal-v2-revision-lifecycle.test.mjs
# PASS: 18 tests, 0 failures

node --test tests/paper-proposal-v2-scientific-domain-contract.test.mjs tests/paper-proposal-v2-scientific-persistence.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-synthesis.test.mjs tests/paper-proposal-v2-scientific-decisions.test.mjs
# PASS: 26 tests, 0 failures

node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures

git diff --check
# PASS: no output
```

Runtime harness: N/A — PR8 remains an isolated scientific state/service slice; no public route or materialization behavior is wired.

### Deviations, risks, and PR boundary

- **Design deviation:** none.
- **Risk:** the lifecycle correction deliberately serializes three validation reads to make error precedence deterministic; this bounded lifecycle path prioritizes compatibility over parallel I/O.
- **PR boundary:** `auto-chain`, `stacked-to-main`; PR8 ends at T7.1–T7.2. T8/PR9 and later were not started.
- **Rollback boundary:** revert only the PR8 scientific decision files/test and the lifecycle validation-order correction plus these SDD artifacts. No proposal, managed revision, manifest, receipt, lifecycle inventory, materialization record, or publication behavior is affected.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): persist scientific decision lifecycle`

### Remaining tasks

```text
- [ ] T8.1 — Add frozen selection and materialization reservation
- [ ] T8.2 — Plan only frozen accepted candidates with provenance
- [ ] T9.1 — Implement non-writing MaterializationCandidateExecutor
- [ ] T9.2 — Add Document Reviewer gate and guarded initial publication adapter
- [ ] T9.3 — Commit materialization only after verified publication
- [ ] T10.1 — Complete recovery and diagnostic outcomes
- [ ] T10.2 — Run compatibility and full regression coverage
```



## PR9 / T8.1–T8.2 — completed

### Structured status and delivery context consumed

```yaml
schemaName: gentle-ai.sdd-status
schemaVersion: 1
changeName: scientific-reasoning-workflow
artifactStore: openspec
applyState: ready
nextRecommended: apply
actionContext:
  mode: repo-local
  workspaceRoot: /Users/diego/Desktop/Proyectos/papersmith-ai
  allowedEditRoots: [/Users/diego/Desktop/Proyectos/papersmith-ai]
delivery:
  strategy: auto-chain
  chainStrategy: stacked-to-main
  boundary: PR9 / T8.1–T8.2 only
strictTdd: false
warnings: ["Native status supplied by the parent is authoritative.", "CodeGraph MCP was unavailable; known-path reads followed the failed request."]
```

### Completed tasks and persisted checkbox evidence

- [x] T8.1 — Added durable frozen-decision selection and reservation through `ScientificStateStore.reserveMaterialization()`.
  - Only explicit, sorted, unique decision IDs are admitted.
  - The exact decision/acceptance-event set derives a stable project-scoped selection key.
  - Under the scientific lock, exact retries return the original record; subset, superset, and partial-overlap claims return `MATERIALIZATION_SELECTION_CONFLICT` before any new reservation.
  - A reservation writes a validated materialization record and index in the existing recoverable transition boundary and appends `MATERIALIZATION_RESERVED`. Rejected, retracted, unknown, duplicate, and unsorted selections cannot reserve claims.
- [x] T8.2 — Added the non-writing `MaterializationPlanner`.
  - It accepts only a `RESOLVING` frozen record backed by current immutable user acceptance events and accepted-unmaterialized decisions.
  - It emits bounded `CREATE_R01` or `CREATE_SUCCESSOR` plans only, with one exact provenance claim per selected decision and acceptance event.
  - It excludes unselected threads and blocks source mismatch, stale/ineligible decisions, unmapped claims, and invalid/exhausted budgets. It has no candidate execution, review, guard, publication, receipt, manifest, or document-write authority.

The persisted `tasks.md` checkboxes were changed only after the focused PR9 test, V2 regressions, and final `git diff --check` passed. The task artifact was re-read after the update.

### Files changed

- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts`
- `.pi/extensions/paper-proposal-v2/materialization-planner.ts` (new)
- `.pi/extensions/paper-proposal-v2/types.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `tests/paper-proposal-v2-scientific-materialization.test.mjs` (new)
- `openspec/changes/scientific-reasoning-workflow/tasks.md`
- `openspec/changes/scientific-reasoning-workflow/apply-progress.md`

### Verification evidence

```text
cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-scientific-materialization.test.mjs
# PASS: 5 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && node --test tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-source-routing.test.mjs tests/paper-proposal-v2-tutor-reviewer.test.mjs tests/paper-proposal-v2-production-role-metrics.test.mjs
# PASS: 29 tests, 0 failures

cd /Users/diego/Desktop/Proyectos/papersmith-ai && git diff --check
# PASS: no output
```

The first `git diff --check` identified one trailing whitespace character in the new store result union. It was removed mechanically; the final command above passed. Runtime harness: N/A — PR9 is a state/planning-only slice and does not wire the public route, candidate executor, document review, guards, or publication.

### Deviations, risks, workload boundary, and rollback

- **Design deviation:** none. The reservation is durable and exact-set scoped, while planning remains non-writing and cannot reach T9 publication seams.
- **Decision:** the selection key binds canonical decision/acceptance-event pairs to the canonical project root. This gives exact retry identity without treating a client idempotency key as authority.
- **Risk:** materialization record/index consistency is fail-closed. An interrupted reservation remains recoverable through the existing transaction marker rather than allowing another claim. Lifecycle of later record states, candidate execution, document review, guarded publication, `r01`/successor writes, and decision materialization are intentionally unimplemented.
- **Workload / PR boundary:** `auto-chain`, `stacked-to-main`; PR9 is T8.1–T8.2 only. No T9/PR10 task started. The tracked source diff is 161 additions and 3 deletions before the new planner and focused test; the complete PR9 work unit remains within the chained review slice.
- **Rollback boundary:** revert only the PR9 domain/store/planner/barrel/type/test changes plus these SDD artifacts. This removes no proposal, revision, document manifest/receipt, candidate execution, document review, guard call, or publication behavior.
- **Conventional commit proposal (not created):** `feat(paper-proposal-v2): reserve frozen materialization plans`

### Remaining tasks

```text
- [ ] T9.1 — Implement non-writing MaterializationCandidateExecutor
- [ ] T9.2 — Add Document Reviewer gate and guarded initial publication adapter
- [ ] T9.3 — Commit materialization only after verified publication
- [ ] T10.1 — Complete recovery and diagnostic outcomes
- [ ] T10.2 — Run compatibility and full regression coverage
```
