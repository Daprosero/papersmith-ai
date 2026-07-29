# Apply Progress — Proposal Lifecycle Base Revisions

## Slice 1 — Lifecycle-v1 authority and durable reconstruction

**Status:** completed for the assigned Slice 1 boundary. Lifecycle-v1 remains internal and unrouted; Slice 2/3 integration was not started.

### Completed persisted tasks

- 16 implementation-owned Slice 1/guardrail checkboxes are visibly marked `- [x]` in `tasks.md`.
- Added versioned lifecycle domain types and a standalone `LifecycleStateStore` / `LifecycleService`.
- Durable authority lives only under `.paper-proposal-v2/lifecycle/v1/` with immutable content, base, revision, withdrawal, request, result, transition-marker, inventory, and staging records.
- Implemented stable-ID/state transitions: base registration, create-from-base, successor creation, withdrawal, restore, active resolution, and deterministic reconstruction.
- Added request/result replay, per-workspace in-process serialization, marker-based reconstruction, locator conflict checks, and fail-closed validation for contradictory durable evidence.
- Added lifecycle-v1 TDD coverage for state transitions, idempotency, interruption points, fresh-process reconstruction, identity-vs-locator behavior, and inconsistency cases.

### Files changed

- `.pi/extensions/paper-proposal-v2/types.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` (new)
- `.pi/extensions/paper-proposal-v2/lifecycle-service.ts` (new)
- `tests/paper-proposal-v2-lifecycle-v1.test.mjs` (new)
- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`

### Verification evidence

- RED: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` failed with `TypeError: v2.LifecycleService is not a constructor` before production implementation.
- RED: durable request-record test failed with `ENOENT` before request persistence was added.
- RED: orphan withdrawal and cross-workspace durable-record tests failed before fail-closed validation was added.
- RED: post-projection interruption test failed before the projection fault seam was added.
- GREEN/TRIANGULATE: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` — 10 passing.
- Focused compatibility: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-lifecycle.test.mjs tests/paper-proposal-v2-revision-lifecycle.test.mjs` — 29 passing.
- `git diff --check -- <Slice 1 changed paths>` — passed.
- The configured full Node regression command was deliberately not run because this slice was explicitly limited to focused tests; it remains unchecked for the later verification boundary.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Slice 1 durable authority | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | Unit | New files; focused legacy lifecycle suite subsequently passed | Missing `LifecycleService` | 10 passing focused tests | Base, successor, withdrawal/restore, retry, locator, and fresh-process cases | Centralized state/error and record validation helpers |
| Slice 1 reconstruction | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | Unit | New files; focused legacy lifecycle suite subsequently passed | Orphan/cross-workspace evidence initially reconstructed | 10 passing focused tests | Marker-before/after projection, duplicate active, missing content, lineage, and hash cases | Commit-marker evidence and inventory checks centralized |

### Deviations from design

- No routing, public projection publishing, legacy adapter changes, metrics, or scientific-entry integration were made; those belong to Slices 2 and 3.
- The lock is intentionally internal to the isolated authority and does not alter existing legacy runtime locking.
- Existing `.paper-proposal-v2/withdrawn/`, proposal files, derived-state files, receipts, and scientific documents were not read as lifecycle-v1 authority and were not mutated.

### Workload / PR boundary

- Delivery path consumed: user-selected three reviewable slices; this is **Slice 1 only** (lifecycle-v1 authority and durable reconstruction).
- No commit or PR was created.

### Structured status consumed

```json
{
  "changeName": "proposal-lifecycle-base-revisions",
  "artifactStore": "openspec",
  "applyState": "ready",
  "dependencies": {"apply": "ready", "verify": "blocked", "archive": "blocked"},
  "actionContext": {
    "mode": "repo-local",
    "workspaceRoot": "/Users/diego/Desktop/Proyectos/papersmith-ai",
    "allowedEditRoots": ["/Users/diego/Desktop/Proyectos/papersmith-ai"]
  },
  "nextRecommended": "apply",
  "warnings": ["Full regression deliberately deferred by assigned Slice 1 focused-test constraint."]
}
```

### Remaining tasks (exact unchecked task lines)

- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Run the configured Node regression command `node --test tests/*.test.mjs`; record any compatibility failures without weakening lifecycle-v1 invariants.
- [ ] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.
- [ ] Change `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts` from filename/latest-file authority to a read-only adapter over `LifecycleService.rebuildLifecycleInventory()`, returning stable IDs, hashes, lineage, all lifecycle states, withdrawal IDs, and explicit inconsistency/absence.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-planner.ts` to select `CREATE_FROM_BASE` only for an exact registered base with no first revision and `CREATE_SUCCESSOR` only for the resolved active revision ID/hash; preserve frozen decision and approved-change provenance.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that first materialization preserves the full base, applies only approved changes, records `BASE_DOCUMENT` lineage, and retries the same request without duplicate revisions or active pointers.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [ ] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.

- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.
- [ ] Add failing tests in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` for active withdrawal clearing the pointer, `WITHDRAWN_ONLY`, no predecessor promotion, durable recovery content, restore by persistent `withdrawalId`, restored historical withdrawal state, and no new revision on restore.
- [ ] Add failing classification coverage for base → `BASE_DOCUMENT_NOT_RESTORABLE`, existing non-withdrawn revision → `REVISION_NOT_WITHDRAWN`, unresolved/generic filename → `WITHDRAWAL_IDENTITY_NOT_FOUND`, and absence of semantic `WITHDRAWAL_NOT_FOUND`.
- [ ] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [ ] Add failing tests for structured lifecycle operational events and bounded metrics in `tests/paper-proposal-v2-scientific-routing.test.mjs` or a dedicated `tests/paper-proposal-v2-lifecycle-observability.test.mjs`; assert content, prompts, patches, and absolute paths are absent.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Update `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` and `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts` to rebuild inventory on fresh entry/restart, retain withdrawn and superseded history, and block materialization from stale/withdrawn evidence.
- [ ] Extend `.pi/extensions/paper-proposal-v2/runtime-metrics.ts` with bounded lifecycle operation/outcome counters and correlation IDs; persist structured transition evidence through `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` without raw content, prompts, patch text, or absolute paths.
- [ ] Keep `.paper-proposal-v2/withdrawn/`, legacy `proposals/research-concept-r*.md`, derived state, and receipts read-only. Add an explicit compatibility/inconsistency diagnostic path that never infers v1 identity, lineage, active state, or withdrawal authority and blocks semantic mutation until explicit registration/migration exists.
- [ ] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Verify legacy fixtures are byte-identical before and after read-only inspection and fail-closed semantic mutation; assert no migration files or synthetic lifecycle records are created.
- [ ] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.
- [ ] Centralize public lifecycle classification and compatibility mapping in `.pi/extensions/paper-proposal-v2/types.ts` plus the lifecycle adapter boundary; keep deprecated `WITHDRAWAL_NOT_FOUND` isolated from semantic v1 results.
- [ ] Bound and normalize operational evidence in `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` and `.pi/extensions/paper-proposal-v2/runtime-metrics.ts`; ensure logs are deterministic enough for recovery diagnosis but contain no sensitive payloads or raw filesystem layout.
- [ ] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.
- [ ] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [ ] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.
- [ ] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.

## Slice 2 continuation — lifecycle-owned scientific publication

**Status:** partial Slice 2 continuation complete; final verify is **not ready** because Slice 2 routing/adapter tasks and all Slice 3 tasks remain unchecked.

### Completed persisted tasks

- Marked the configured Node-regression execution task complete: it was executed twice during this continuation; its sole failure is pre-existing/unrelated to this integration (see verification).
- Marked lifecycle materialization planning complete: `LifecycleMaterializationPlanner` reads only explicit lifecycle-v1 authority and selects `CREATE_FROM_BASE` from the registered base or `CREATE_SUCCESSOR` from the resolved active revision.
- Marked first-materialization triangulation complete: a registered public scientific workflow preserves full base bytes, applies only frozen accepted summaries, records `BASE_DOCUMENT` lineage, and exact retry creates no second revision/active pointer.

### Files changed in this continuation

- `.pi/extensions/paper-proposal-v2/materialization-planner.ts`
- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `.pi/extensions/paper-proposal-v2/scientific-state-store.ts`
- `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`
- `tests/paper-proposal-v2-scientific-materialization.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

### Implementation evidence

- The explicit `lifecycleV1WorkspaceId` runtime route is the sole lifecycle-v1 public materialization path. It never invokes legacy `CREATE_R01`, candidate rendering, guarded workspace publication, or filename parsing.
- An unregistered lifecycle-v1 workspace returns `BASE_DOCUMENT_NOT_REGISTERED` without creating `proposals/research-concept-r01.md` or synthetic lifecycle records.
- A registered workspace materializes the full durable base plus only frozen accepted-decision summaries through `CREATE_FROM_BASE`; successors use the active revision ID/hash through `CREATE_SUCCESSOR`, supersede exactly the previous active revision, and retain base lineage.
- Lifecycle-v1 request/result/active state commits in `LifecycleService`; after that commit, the scientific projection records the same lifecycle identity and marks frozen decisions materialized. Legacy/unregistered paths remain unchanged.

### Verification evidence

- Safety net: `node --test tests/paper-proposal-v2-scientific-materialization.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs` — 14 passing before edits.
- RED: `node --test tests/paper-proposal-v2-scientific-materialization.test.mjs` — new registered-v1 test failed (`needs_clarification`, expected `materialized`) before public lifecycle routing.
- GREEN/TRIANGULATE: `node --test tests/paper-proposal-v2-scientific-materialization.test.mjs` — 8 passing.
- Focused integration: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs` — 34 passing.
- Full Node: `node --test tests/*.test.mjs` — 313 passing, 1 failing. Failure: pre-existing `tests/document-operation-guard.test.mjs` expects `"AMBIGUOUS"` in `.pi/extensions/proposal-workspace.ts`; that unrelated file was already modified before this continuation and was not changed here.
- Python: `python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` — 15 passing.
- `git diff --check` — passed.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Public lifecycle-v1 publication | `tests/paper-proposal-v2-scientific-materialization.test.mjs` | Integration | 14 focused tests passing | Registered route returned `needs_clarification` | 7 passing after lifecycle-only route | Unregistered fail-closed, first retry idempotency, and successor lineage cases; 8 passing | Isolated v1 routing from legacy planner/publication and centralized v1 scientific commit validation |

### Deviations from design

- Lifecycle-v1 publication is a durable lifecycle-owned result (`lifecycle-v1:<revisionId>`), not a legacy public proposal filename. This is necessary to avoid legacy artifact mutation and `CREATE_R01` bypass.
- Scientific projection commits immediately after the lifecycle transaction; the lifecycle request/result/revision/active transition remains atomic at its authority boundary.
- Did not alter legacy proposal files, `.paper-proposal-v2/withdrawn/`, derived state, receipts, scientific documents, or unrelated user changes.

### Workload / PR boundary

- Delivery path: user-selected three reviewable slices; this continuation remains **Slice 2 — public lifecycle-v1 materialization/publication integration**.
- No commit or PR was created.

### Structured status consumed

```json
{
  "changeName": "proposal-lifecycle-base-revisions",
  "artifactStore": "openspec",
  "applyState": "ready",
  "dependencies": {"apply": "ready", "verify": "blocked", "archive": "blocked"},
  "actionContext": {
    "mode": "repo-local",
    "workspaceRoot": "/Users/diego/Desktop/Proyectos/papersmith-ai",
    "allowedEditRoots": ["/Users/diego/Desktop/Proyectos/papersmith-ai"]
  },
  "nextRecommended": "apply",
  "warnings": ["Full Node suite has one unrelated pre-existing guard-contract failure."]
}
```

### Remaining tasks (exact unchecked task lines)

- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [ ] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.
- [ ] Change `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts` from filename/latest-file authority to a read-only adapter over `LifecycleService.rebuildLifecycleInventory()`, returning stable IDs, hashes, lineage, all lifecycle states, withdrawal IDs, and explicit inconsistency/absence.
- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.
- [ ] Add failing tests in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` for active withdrawal clearing the pointer, `WITHDRAWN_ONLY`, no predecessor promotion, durable recovery content, restore by persistent `withdrawalId`, restored historical withdrawal state, and no new revision on restore.
- [ ] Add failing classification coverage for base → `BASE_DOCUMENT_NOT_RESTORABLE`, existing non-withdrawn revision → `REVISION_NOT_WITHDRAWN`, unresolved/generic filename → `WITHDRAWAL_IDENTITY_NOT_FOUND`, and absence of semantic `WITHDRAWAL_NOT_FOUND`.
- [ ] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [ ] Add failing tests for structured lifecycle operational events and bounded metrics in `tests/paper-proposal-v2-scientific-routing.test.mjs` or a dedicated `tests/paper-proposal-v2-lifecycle-observability.test.mjs`; assert content, prompts, patches, and absolute paths are absent.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Update `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` and `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts` to rebuild inventory on fresh entry/restart, retain withdrawn and superseded history, and block materialization from stale/withdrawn evidence.
- [ ] Extend `.pi/extensions/paper-proposal-v2/runtime-metrics.ts` with bounded lifecycle operation/outcome counters and correlation IDs; persist structured transition evidence through `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` without raw content, prompts, patch text, or absolute paths.
- [ ] Keep `.paper-proposal-v2/withdrawn/`, legacy `proposals/research-concept-r*.md`, derived state, and receipts read-only. Add an explicit compatibility/inconsistency diagnostic path that never infers v1 identity, lineage, active state, or withdrawal authority and blocks semantic mutation until explicit registration/migration exists.
- [ ] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Verify legacy fixtures are byte-identical before and after read-only inspection and fail-closed semantic mutation; assert no migration files or synthetic lifecycle records are created.
- [ ] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.
- [ ] Centralize public lifecycle classification and compatibility mapping in `.pi/extensions/paper-proposal-v2/types.ts` plus the lifecycle adapter boundary; keep deprecated `WITHDRAWAL_NOT_FOUND` isolated from semantic v1 results.
- [ ] Bound and normalize operational evidence in `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` and `.pi/extensions/paper-proposal-v2/runtime-metrics.ts`; ensure logs are deterministic enough for recovery diagnosis but contain no sensitive payloads or raw filesystem layout.
- [ ] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.
- [ ] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [ ] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.
- [ ] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.

## Slice 2 — Read-only lifecycle-v1 exposure (partial)

**Status:** partial. Completed the explicit lifecycle-v1 read-only adapter and project-entry/runtime consumption. The required lifecycle-owned materialization/publication routing is intentionally still unchecked; it cannot safely reuse the filename-era `CREATE_R01` renderer or publish to legacy proposal artifacts.

### Completed persisted tasks

- Added `readLifecycleV1Inventory()` and `createLifecycleV1RevisionInventoryPort()`; both reconstruct only explicit v1 records and never consult legacy filenames or withdrawal paths.
- `ProjectEntryResolver` now exposes a registered base ID/hash and lifecycle state without mutation, including explicit `WITHDRAWN_ONLY` absence.
- `ScientificWorkflowRuntime` selects the lifecycle-v1 read port only when `lifecycleV1WorkspaceId` is supplied. Existing legacy workspaces retain their read-only compatibility port and are not migrated.
- Updated persisted Slice 2 checkboxes for entry coverage, read-only runtime consumption, and its focused command.

### Files changed in this batch

- `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts`
- `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`
- `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`
- `.pi/extensions/paper-proposal-v2/scientific-domain.ts`
- `tests/paper-proposal-v2-lifecycle-v1.test.mjs`
- `tests/paper-proposal-v2-scientific-entry.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`

### Verification evidence

- RED: explicit v1 inventory test failed because `readLifecycleV1Inventory` did not exist.
- RED: project-entry base/lifecycle projection test failed before the resolver projected explicit lifecycle evidence.
- GREEN/TRIANGULATE: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs` — 32 passing.
- `git diff --check` — passed.
- Full Node/Python suite deliberately deferred per the Slice 2 focused-test constraint.

### TDD Cycle Evidence

| Task | Test file | Layer | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|
| Read-only v1 inventory | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | Unit | Missing adapter | Passed | Explicit base, active identity, and no-write snapshot | Isolated adapter boundary |
| Entry/runtime exposure | `tests/paper-proposal-v2-scientific-entry.test.mjs` | Unit | Missing base/lifecycle projection | Passed | Active and withdrawn-only evidence | Opt-in runtime port preserves legacy compatibility |

### Deviation / remaining Slice 2 boundary

The legacy scientific materialization pipeline still synthesizes `CREATE_R01` from claims and publishes legacy proposal artifacts. Replacing it requires lifecycle-owned request reservation and a base-byte candidate executor; implementing it partially would violate the requested no-legacy-mutation and full-base-byte constraints. The unchecked Slice 2 planner, executor, publication, adapter, and routing tasks remain the required next work.

### Structured status consumed

```json
{"changeName":"proposal-lifecycle-base-revisions","artifactStore":"openspec","applyState":"ready","taskProgress":{"completed":20,"pending":33},"actionContext":{"mode":"repo-local","allowedEditRoots":["/Users/diego/Desktop/Proyectos/papersmith-ai"]},"nextRecommended":"apply"}
```

### Slice 2 correction — lifecycle-owned materialization bridge

- Added `LifecycleMaterializationPlanner` in `materialization-planner.ts`.
- It accepts only an explicit lifecycle workspace, reconstructs durable authority, blocks an unregistered workspace with `BASE_DOCUMENT_NOT_REGISTERED`, creates the first revision only from registered full base bytes plus supplied approved replacements, and creates successors only from the resolved active revision ID/hash.
- The bridge persists stable base lineage and supersedes the source via `LifecycleService`; it neither reads nor writes legacy proposal documents or filename-era runtime state.
- Strict-TDD RED: the bridge test failed because the class did not exist. GREEN/TRIANGULATE: the focused command passed with 33 tests.
- Persisted Slice 2 RED coverage checkbox is marked complete. Lifecycle-owned publication/routing tasks remain unchecked because no safe adapter yet maps frozen scientific decision evidence to approved byte replacements and commits the corresponding scientific/publication evidence.

## Slice 3 continuation — public lifecycle-v1 withdrawal and restoration

**Status:** partial; lifecycle-v1 public router added, but legacy public-tool composition, restart/recovery adapters, metrics, and remaining lifecycle tasks still require implementation.

### Completed persisted tasks

- Added RED/GREEN coverage for public lifecycle-v1 withdrawal/restore behavior and specific restore classifications.
- Added `LifecycleV1PublicRouter`, which addresses only explicit `workspaceId` lifecycle authority, never scans legacy files, clears the active pointer through `LifecycleService`, and restores only with a persisted `withdrawalId`.
- Updated Slice 3 RED task checkboxes immediately after the focused suite passed.

### Files changed

- `.pi/extensions/paper-proposal-v2/lifecycle-v1-public-router.ts` (new)
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `tests/paper-proposal-v2-lifecycle-v1.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

### Verification / TDD evidence

| Task | Test file | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|
| Public v1 withdrawal/restore | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | 30 focused tests passing | `LifecycleV1PublicRouter is not a constructor` | 13 lifecycle-v1 tests passing | Covers `WITHDRAWN_ONLY`, no predecessor promotion, base/non-withdrawn/filename classification, and restore by durable ID | Router returns only bounded semantic data |

- `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` — 13 passing.
- Earlier focused lifecycle/recovery/routing safety net — 30 passing.

### Remaining risks

- This router is not yet composed into the existing `paper_proposal_v2_execute` legacy lifecycle path. That composition must preserve the no-migration boundary and is still unchecked.
- Full Node suite remains known to have the unrelated pre-existing `document-operation-guard` failure; no unrelated files were changed.
- Native final verify is not ready; 28 task checkboxes remain unchecked.

## Slice 3 continuation — public composition and bounded lifecycle diagnostics

**Status:** partial. The existing public `paper_proposal_v2_execute` route now selects lifecycle-v1 only when an explicit `scientificWorkflow.lifecycleV1WorkspaceId` is configured. No legacy lifecycle file, proposal artifact, scientific document, derived state, or receipt is read or mutated by that path.

### Completed persisted tasks

- Marked the two completed Slice 3 observability checkboxes in `tasks.md` as `- [x]`.
- Composed `LifecycleV1PublicRouter` into the existing public lifecycle route for explicitly configured lifecycle-v1 workspaces.
- Public withdrawal resolves only the active lifecycle-v1 revision locator, reaches `WITHDRAWN_ONLY`, and reports the persistent `withdrawalId`.
- Public restore accepts `withdrawalOperationId` only as the durable `withdrawalId`; a filename reference is rejected as `WITHDRAWAL_IDENTITY_NOT_FOUND`.
- Added bounded lifecycle outcome counters and correlation `requestId` to the public lifecycle-v1 result. Transition evidence remains bounded to IDs, state changes, operation, and relative record paths; the focused test proves it excludes base content, prompts, and absolute temporary roots.

### Files changed in this continuation

- `.pi/extensions/proposal-workspace.ts`
- `.pi/extensions/paper-proposal-v2/runtime-metrics.ts`
- `tests/paper-proposal-v2-lifecycle-v1.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

### Verification evidence

- Safety net: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs` — 21 passing before this continuation's RED test.
- RED: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` — 13 passing, 1 failing; the public route returned legacy `blocked` rather than lifecycle-v1 `WITHDRAWN_ONLY` because it was not composed.
- GREEN: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` — 14 passing after public lifecycle-v1 composition.
- TRIANGULATE: added a filename-only restore rejection alongside successful withdrawal and withdrawal-ID restore; recorded exact committed/rejected bounded metrics.
- Focused integration: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs` — 37 passing.
- `git diff --check` — passed.
- Full suites were intentionally not rerun; they remain the verify-phase responsibility.

### Pre-existing Node guard failure evidence

`node --test tests/document-operation-guard.test.mjs` still fails before any change in this continuation: it expects `"AMBIGUOUS"` in `.pi/extensions/proposal-workspace.ts`. `git show HEAD:.pi/extensions/proposal-workspace.ts` contains that token, while the already-modified worktree source did not at the start of this continuation. The test file itself is unchanged. This establishes that the failure is caused by a pre-existing uncommitted guard-contract change, not lifecycle-v1 composition; it is not hidden or attributed to lifecycle work.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Public lifecycle-v1 composition and diagnostics | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | Integration | 21 focused passing | Public route returned legacy `blocked` | 14 lifecycle-v1 passing | Withdrawal, filename-only restore rejection, withdrawal-ID restore, and bounded metrics | None needed; isolated projection helper retained the legacy route unchanged |

### Deviations from design

- The explicit lifecycle-v1 public projection reports `auditStatus` and `selfAuditStatus` as `NOT_RUN`; it intentionally does not invoke legacy filesystem audit/receipt machinery because lifecycle-v1 owns no legacy public artifact.
- The remaining restart/recovery, legacy compatibility diagnostics, and legacy transaction adapter work is not complete and remains unchecked.

### Workload / PR boundary

- Delivery path: existing three-slice chain; this work remains the assigned **Slice 3** boundary.
- No commit or PR was created.

### Structured status consumed

```json
{
  "changeName": "proposal-lifecycle-base-revisions",
  "artifactStore": "openspec",
  "applyState": "ready",
  "dependencies": {"apply": "ready", "verify": "blocked", "archive": "blocked"},
  "actionContext": {
    "mode": "repo-local",
    "workspaceRoot": "/Users/diego/Desktop/Proyectos/papersmith-ai",
    "allowedEditRoots": ["/Users/diego/Desktop/Proyectos/papersmith-ai"]
  },
  "nextRecommended": "apply",
  "warnings": ["Strict TDD active.", "Full suite intentionally deferred to verify.", "document-operation-guard failure is pre-existing worktree drift."]
}
```

### Remaining tasks (exact unchecked task lines)

- [ ] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Update `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` and `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts` to rebuild inventory on fresh entry/restart, retain withdrawn and superseded history, and block materialization from stale/withdrawn evidence.
- [ ] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Keep `.paper-proposal-v2/withdrawn/`, legacy `proposals/research-concept-r*.md`, derived state, and receipts read-only. Add an explicit compatibility/inconsistency diagnostic path that never infers v1 identity, lineage, active state, or withdrawal authority and blocks semantic mutation until explicit registration/migration exists.
- [ ] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Verify legacy fixtures are byte-identical before and after read-only inspection and fail-closed semantic mutation; assert no migration files or synthetic lifecycle records are created.
- [ ] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.
- [ ] Centralize public lifecycle classification and compatibility mapping in `.pi/extensions/paper-proposal-v2/types.ts` plus the lifecycle adapter boundary; keep deprecated `WITHDRAWAL_NOT_FOUND` isolated from semantic v1 results.
- [ ] Bound and normalize operational evidence in `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` and `.pi/extensions/paper-proposal-v2/runtime-metrics.ts`; ensure logs are deterministic enough for recovery diagnosis but contain no sensitive payloads or raw filesystem layout.
- [ ] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.
- [ ] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [ ] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.
- [ ] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.
- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Change `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts` from filename/latest-file authority to a read-only adapter over `LifecycleService.rebuildLifecycleInventory()`, returning stable IDs, hashes, lineage, all lifecycle states, withdrawal IDs, and explicit inconsistency/absence.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [ ] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.
- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.

## Apply resumption gate — blocked before code changes

**Status:** blocked by the persisted Review Workload Forecast. `tasks.md` still declares `Decision needed before apply: Yes`, `Chained PRs recommended: Yes`, `Chain strategy: pending`, and `400-line budget risk: High`. The resume request identifies technical priorities but does not provide one of the required resolved delivery paths (`auto-chain` / a chosen chained-or-stacked mode, or explicit `size:exception` / `exception-ok`). No code or task checkbox was changed.

### Inputs and current-state assessment

- Read proposal, specification, design, tasks, prior apply progress, strict-TDD configuration, current diff, and lifecycle-v1 focused tests.
- `tasks.md` is internally current at **27 checked / 26 unchecked**; the prior prose claiming 28 unchecked is stale.
- The existing working tree already contains lifecycle-v1 public-router composition in `.pi/extensions/proposal-workspace.ts`, read-only lifecycle inventory adapters, lifecycle-v1 materialization routing, and bounded lifecycle counters. The remaining checklist requires evidence and/or integrations beyond those existing partial changes.
- CodeGraph MCP was unavailable (`MCP not initialized`), so targeted filesystem reads were used as the fallback.

### Strict-TDD / verification

No RED/GREEN cycle or integration was started because the delivery gate blocks implementation before code changes. Consequently, no focused or full test command was run in this resumption attempt.

Existing baseline evidence remains: `node --test tests/document-operation-guard.test.mjs` fails because the pre-existing modified `.pi/extensions/proposal-workspace.ts` removed the test's expected `AMBIGUOUS` token; `git show HEAD:.pi/extensions/proposal-workspace.ts` contains it and the test file is unchanged. This is **pre-existing worktree drift**, not an introduced lifecycle-v1 failure. No new failures were introduced because no source or test files changed.

### Structured status consumed

```json
{
  "changeName": "proposal-lifecycle-base-revisions",
  "artifactStore": "openspec",
  "applyState": "ready",
  "dependencies": {"apply": "ready", "verify": "blocked", "archive": "blocked"},
  "actionContext": {
    "mode": "repo-local",
    "workspaceRoot": "/Users/diego/Desktop/Proyectos/papersmith-ai",
    "allowedEditRoots": ["/Users/diego/Desktop/Proyectos/papersmith-ai"]
  },
  "nextRecommended": "apply",
  "warnings": ["Strict TDD active.", "Review Workload Forecast requires a resolved delivery path before apply."]
}
```

### Required decision before resuming

Provide `auto-chain` with a chain strategy (`stacked-to-main` or `feature-branch-chain`) and the assigned PR/work-unit boundary, or explicitly approve `size:exception` / `exception-ok`. The next apply batch must be limited to that boundary.

## Slice 3 continuation — legacy compatibility diagnostic and non-mutating inventory recovery

**Status:** partial Slice 3 implementation complete. Explicit lifecycle-v1 public composition, recovery rebuild, and bounded metrics were already present; this batch fixed the remaining legacy-adapter hole: a read-only check of an unregistered legacy workspace had been creating an empty lifecycle-v1 directory and exposing it as ordinary `EMPTY` state.

### Completed persisted tasks

- Marked the existing read-only lifecycle-v1 adapter task complete after source/test reconciliation.
- Marked explicit compatibility diagnostics, byte-identical legacy fixture protection, public classification mapping, and bounded operational-evidence refactor tasks complete.
- Added `LIFECYCLE_V1_UNREGISTERED` as the explicit compatibility diagnostic. It is emitted by direct lifecycle-v1 reads and public lifecycle mutation routes for an explicitly configured workspace without durable v1 authority.
- Made lifecycle inventory reconstruction read-only: it no longer creates the lifecycle-v1 directory layout. Layout creation remains confined to committing lifecycle transitions.
- Kept the scientific entry port compatible with existing fail-closed materialization behavior: an unregistered lifecycle workspace is observed as an empty read-only port, then materialization returns `BASE_DOCUMENT_NOT_REGISTERED` without legacy publication or synthetic lifecycle records.

### Files modified in this continuation

- `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts`
- `.pi/extensions/paper-proposal-v2/lifecycle-service.ts`
- `.pi/extensions/paper-proposal-v2/lifecycle-v1-public-router.ts`
- `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts`
- `.pi/extensions/paper-proposal-v2/types.ts`
- `tests/paper-proposal-v2-lifecycle-v1.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

No scientific documents, legacy lifecycle state/records, generated lifecycle records for legacy fixtures, migrations, commits, or PRs were created or modified.

### Verification evidence

- Safety net before edits: lifecycle/recovery/pending-audit/routing/entry focused command — **39 passing**.
- RED: new legacy compatibility test failed because `readLifecycleV1Inventory()` returned a normal `EMPTY` result and created `.paper-proposal-v2/lifecycle/v1/`.
- GREEN: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` — **15 passing** after adding unregistered diagnostic and non-mutating reconstruction.
- TRIANGULATE: added public-tool composition coverage; the same suite — **16 passing**. It proves an explicitly configured legacy workspace returns `LIFECYCLE_V1_UNREGISTERED`, increments only the bounded rejection counter, and leaves legacy bytes and lifecycle-v1 paths absent.
- Focused integration: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-recovery.test.mjs tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs` — **49 passing**.
- Full Node: `node --test tests/*.test.mjs` — **317 passing, 1 failing**. `tests/document-operation-guard.test.mjs` remains the known pre-existing worktree failure: the unchanged test expects `"AMBIGUOUS"`; `git show HEAD:.pi/extensions/proposal-workspace.ts` contains it while the already-modified worktree source does not. Lifecycle files do not cause this failure.
- Python: `python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` — **15 passing**.
- `git diff --check` for tracked paths modified in this continuation — passed.

### Public E2E proof

`paper_proposal_v2_execute` was exercised through the registered public tool in both configured states: a registered v1 workspace withdraws/restores by persistent withdrawal ID without legacy files; an explicitly configured legacy workspace rejects withdrawal with `LIFECYCLE_V1_UNREGISTERED`, does not create lifecycle-v1 state, and preserves the legacy proposal bytes. This is public-tool integration proof, not final verify completion.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Legacy diagnostic/read-only inventory | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | Integration | 39 focused passing | New legacy read returned `valid/EMPTY` and created the v1 layout | 15 lifecycle tests passing | Added public composition/no-write/metric case; 16 passing | Moved layout creation exclusively to commit paths and centralized absence classification |

### Deviations from design

- `LIFECYCLE_V1_UNREGISTERED` is an explicit compatibility diagnostic, not a replacement semantic error for base registration. The scientific read port remains empty/read-only so its established materialization boundary can return `BASE_DOCUMENT_NOT_REGISTERED`; direct lifecycle mutation stays blocked by the compatibility diagnostic.
- No legacy filename is used to derive lifecycle identity, active state, lineage, or withdrawal authority.

### Workload / PR boundary

- Delivery path consumed: user-selected three reviewable slices; this remains **Slice 3**. No commit or PR was created.

### Structured status consumed

```json
{
  "changeName": "proposal-lifecycle-base-revisions",
  "artifactStore": "openspec",
  "applyState": "ready",
  "dependencies": {"apply": "ready", "verify": "blocked", "archive": "blocked"},
  "actionContext": {"mode": "repo-local", "workspaceRoot": "/Users/diego/Desktop/Proyectos/papersmith-ai", "allowedEditRoots": ["/Users/diego/Desktop/Proyectos/papersmith-ai"]},
  "nextRecommended": "apply",
  "warnings": ["Strict TDD active.", "CodeGraph MCP was unavailable; targeted filesystem fallback used.", "Full Node suite has one pre-existing document-operation-guard worktree failure."]
}
```

### Remaining tasks (exact unchecked task lines)

- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [ ] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.
- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.
- [ ] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Update `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` and `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts` to rebuild inventory on fresh entry/restart, retain withdrawn and superseded history, and block materialization from stale/withdrawn evidence.
- [ ] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.
- [ ] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.
- [ ] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [ ] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.
- [ ] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.

## Slice 3 continuation — restart-safe withdrawn-only materialization boundary

**Status:** partial Slice 3 continuation complete. The lifecycle-v1 scientific runtime now reconstructs lifecycle authority before it reserves a scientific materialization. A fresh runtime cannot create a new scientific reservation or derive a successor when the durable workspace is `WITHDRAWN_ONLY`.

### Completed persisted task

- Marked the Slice 3 project-entry/runtime restart integration task `- [x]`: fresh runtime entry rebuilds the lifecycle inventory and blocks materialization from withdrawn evidence with typed `ACTIVE_REVISION_NOT_FOUND`.

### Files modified in this continuation

- `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`
- `tests/paper-proposal-v2-scientific-materialization.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

No scientific documents, legacy files/state, lifecycle records for legacy fixtures, migrations, commits, or PRs were changed.

### Verification evidence

- Safety net: lifecycle/recovery/pending-audit/routing/entry/materialization focused command — **49 passing** before this batch.
- RED: a fresh runtime over `WITHDRAWN_ONLY` returned `ACTIVE_REVISION_ALREADY_EXISTS` and created a new scientific materialization reservation, rather than reporting missing active lifecycle authority.
- GREEN: `node --test tests/paper-proposal-v2-scientific-materialization.test.mjs` — **9 passing** after lifecycle authority is read before reservation.
- TRIANGULATE/focused integration: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-recovery.test.mjs tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs` — **50 passing**.
- The new public-runtime test proves first materialization, successor creation, active withdrawal, fresh-runtime restart, typed blocked outcome (`ACTIVE_REVISION_NOT_FOUND`), preserved `WITHDRAWN_ONLY`, unchanged materialization records, and no legacy publication.
- `git diff --check` for this batch — passed.
- Final verification was deliberately not run.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Restart-safe v1 materialization | `tests/paper-proposal-v2-scientific-materialization.test.mjs` | Integration | 49 focused passing | Fresh withdrawn-only runtime reserved work and returned `ACTIVE_REVISION_ALREADY_EXISTS` | 9 materialization tests passing | Full focused lifecycle/recovery/routing/entry/materialization command: 50 passing | Lifecycle authority check now precedes scientific reservation; no duplicate read after reservation |

### Public routing / failure separation

- The focused suite retains public route precedence and typed lifecycle public composition coverage: lifecycle requests win over scientific routing, registered v1 withdrawal/restore uses persistent IDs, and unregistered v1 workspaces return `LIFECYCLE_V1_UNREGISTERED` without legacy writes.
- No introduced failures. The known unrelated `tests/document-operation-guard.test.mjs` failure was not re-run in this batch; prior evidence remains pre-existing worktree drift (`AMBIGUOUS` exists in `HEAD` but not the already-modified `.pi/extensions/proposal-workspace.ts`).

### Workload / PR boundary

- Delivery path consumed: user-selected three reviewable slices; this remains Slice 3. No commit or PR was created.

### Structured status consumed

```json
{
  "changeName": "proposal-lifecycle-base-revisions",
  "artifactStore": "openspec",
  "applyState": "ready",
  "taskProgress": {"completed": 33, "pending": 20},
  "actionContext": {"mode": "repo-local", "workspaceRoot": "/Users/diego/Desktop/Proyectos/papersmith-ai", "allowedEditRoots": ["/Users/diego/Desktop/Proyectos/papersmith-ai"]},
  "nextRecommended": "apply",
  "warnings": ["Strict TDD active.", "CodeGraph MCP was unavailable; targeted filesystem fallback used.", "Final verify intentionally not run."]
}
```

### Remaining tasks (exact unchecked task lines)

- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [ ] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.
- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.
- [ ] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.
- [ ] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.
- [ ] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [ ] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.
- [ ] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.

## Slice 3 continuation — workspace-scoped authority diagnostics and committed-marker recovery

**Status:** partial Slice 3 continuation complete. Lifecycle-v1 authority detection is now scoped to the requested workspace. A valid lifecycle for one workspace no longer masks another workspace's missing-v1 diagnostic or allows its public router to downgrade that condition into filename-era classification.

### Newly completed implementation evidence

- Added workspace-scoped `hasLifecycleAuthority(workspaceId)` through the state-store/service/adapter/router chain.
- A lifecycle-v1 read for a workspace with no durable records now returns `LIFECYCLE_V1_UNREGISTERED` even when another workspace in the same project has valid authority.
- The public lifecycle router returns the same typed diagnostic for that unregistered workspace and leaves the registered workspace's durable inventory byte-for-byte equivalent.
- Added scientific-recovery coverage for a post-commit-marker projection fault: the initiating operation returns fail-closed `LIFECYCLE_INVENTORY_INCONSISTENT`; a fresh read-only lifecycle adapter reconstructs the committed `BASE_REGISTERED` authority without publishing a legacy proposal file.

### Persisted task reconciliation

No checkbox was newly marked complete in this batch. The two matching checklist items remain unchecked because their stated scope is broader than the demonstrated work:

- `Extend tests/paper-proposal-v2-pending-audit.test.mjs and tests/paper-proposal-v2-scientific-recovery.test.mjs ...`: recovery now has lifecycle marker/restart proof, but the legacy `PENDING_AUDIT` path remains a separate guarded legacy-publication mechanism. Lifecycle-v1 intentionally does not create legacy public artifacts or pending-audit records, so checking the combined task would be false.
- `Verify restart reconstruction ... in tests/...lifecycle-v1... and tests/...scientific-recovery... for active, superseded, withdrawn, WITHDRAWN_ONLY, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch`: lifecycle-v1 coverage proves those inventory variants; scientific-recovery now proves the committed-marker/base projection path only. The cross-suite exhaustive matrix is still outstanding.

### Intentional legacy-path dispositions (requirements remain traceable)

- `InitialRevisionRenderer`, `MaterializationCandidateExecutor`, `MaterializationPublicationService`, `ProposalWorkspaceAdapter`, and `revision-lifecycle-transaction` checklist items remain unchecked. Their filename/publication machinery is intentionally bypassed by the explicit lifecycle-v1 route (`LifecycleMaterializationPlanner` and `LifecycleService`) to prevent legacy document/state mutation. The lifecycle-v1 alternative is covered by public-tool and runtime tests; the legacy tasks cannot be checked until any required guarded projection is separately designed without weakening the no-migration boundary.
- The broad `orchestrator.ts` / legacy `proposal-workspace.ts` tasks remain unchecked: public lifecycle-v1 withdrawal/restore composition is present, but completing the legacy pipeline conversion would be a separate compatibility integration, not a safe inference from current v1 routing.

### Files modified in this continuation

- `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts`
- `.pi/extensions/paper-proposal-v2/lifecycle-service.ts`
- `.pi/extensions/paper-proposal-v2/lifecycle-v1-public-router.ts`
- `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts`
- `tests/paper-proposal-v2-lifecycle-v1.test.mjs`
- `tests/paper-proposal-v2-scientific-recovery.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

No scientific documents, legacy durable state, legacy withdrawal records, migrations, commits, or PRs were modified.

### Verification evidence

- Safety net: focused lifecycle/recovery/pending-audit/routing/entry/materialization command — **50 passing**.
- RED: a project with workspace-1 lifecycle authority returned ordinary `EMPTY` rather than `LIFECYCLE_V1_UNREGISTERED` for workspace-2.
- GREEN: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` — **17 passing**.
- TRIANGULATE: `node --test tests/paper-proposal-v2-scientific-recovery.test.mjs` — **4 passing**; injected post-marker fault reconstructs committed base evidence through the read-only adapter.
- Focused integration: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-recovery.test.mjs tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs` — **52 passing**.
- `git diff --check` — passed.
- Final verify/full suite deliberately not run.

### Public E2E / failure classification

Focused public-tool coverage proves lifecycle routing precedence, persistent withdrawal-ID restore, and workspace-scoped `LIFECYCLE_V1_UNREGISTERED` rejection without legacy writes. No introduced failures occurred. The known `tests/document-operation-guard.test.mjs` failure was not run in this batch; its prior classification remains pre-existing worktree drift.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Workspace-scoped authority diagnostic | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | Integration | 50 focused passing | Other-workspace authority suppressed the unregistered diagnostic | 17 lifecycle tests passing | Public router and registered-workspace byte-equivalence assertions | Threaded workspace identity through store/service/read/router seam |
| Committed-marker recovery adapter | `tests/paper-proposal-v2-scientific-recovery.test.mjs` | Integration | Existing recovery suite passing | Existing marker-fault behavior used as recovery seam | 4 recovery tests passing | Fresh read-only adapter reconstructs committed base without public legacy file | No production refactor needed |

### Structured status consumed

```json
{"changeName":"proposal-lifecycle-base-revisions","artifactStore":"openspec","applyState":"ready","taskProgress":{"completed":33,"pending":20},"actionContext":{"mode":"repo-local","allowedEditRoots":["/Users/diego/Desktop/Proyectos/papersmith-ai"]},"nextRecommended":"apply","warnings":["Strict TDD active.","CodeGraph MCP unavailable; targeted filesystem fallback used.","Final verify intentionally not run."]}
```

### Remaining tasks (exact unchecked task lines)

- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [ ] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.
- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.
- [ ] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.
- [ ] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.
- [ ] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [ ] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.
- [ ] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.

## Slice 3 continuation — normalized public transition evidence and acceptance trace

**Status:** partial Slice 3 continuation complete. The public lifecycle-v1 response now exposes one normalized, bounded transition-evidence object for both committed and rejected withdrawal/restore requests. It contains only operation, request/correlation ID, outcome, semantic classification, lifecycle state, and stable entity IDs; it excludes content, prompts, patches, locators, and filesystem paths.

### Newly completed implementation evidence

- `projectLifecycleV1PublicResult()` now normalizes committed and rejected lifecycle-v1 outcomes into a bounded `transitionEvidence` projection.
- Public withdrawal evidence exposes `WITHDRAWN_ONLY`, no active pointer, revision and withdrawal IDs; rejected restore exposes the explicit semantic code; restored evidence exposes the reactivated identity.
- The existing public-tool route is now covered for both success and rejection evidence without legacy files.

### Acceptance-criterion trace to lifecycle-v1 evidence

| Lifecycle spec acceptance criterion | Lifecycle-v1 implementation | Focused evidence |
|---|---|---|
| One immutable, readable base with stable identity/hash | `LifecycleService.registerBaseDocument` + immutable content store | lifecycle-v1 registration/replay tests |
| Read-only base/active inspection | `readLifecycleV1Inventory` + `createLifecycleV1RevisionInventoryPort` | entry/read-only/no-write tests |
| Full-base first materialization and base lineage | `LifecycleMaterializationPlanner` + `createFromBase` | scientific-materialization first-revision test |
| Exact active successor and single active state | `createSuccessor` validates ID/hash and supersedes source | lifecycle-v1 + scientific-materialization successor tests |
| Identity/state active resolution, fail closed | `rebuildLifecycleInventory` / `resolveActiveRevision` | locator, duplicate-active, broken-lineage tests |
| Withdrawal yields `WITHDRAWN_ONLY` without promotion | `withdrawRevision` + public router | withdrawal/restart/public-tool tests |
| Persistent-ID-only restore with explicit errors | `restoreWithdrawnRevision` + public projection | base/non-withdrawn/unresolved/public-tool tests |
| Fresh reconstruction or inconsistency | durable marker reconstruction + read adapter | marker fault, missing content, orphan, cross-workspace tests |
| Locator independence/conflict rejection | lifecycle records treat locator as optional projection | locator/conflict tests |
| Idempotency and no partial successful transition | request/result records + marker linearization | retry and pre/post-marker interruption tests |

### Persisted task reconciliation

No checkbox was newly marked in this batch. The normalized public evidence completes behavior already represented by the checked public-classification and bounded-evidence tasks. Remaining unchecked tasks are not silently retired:

- Legacy renderer, publication, adapter, transaction, and generic orchestrator conversion tasks remain **deferred compatibility work**, not lifecycle-v1 requirements. Their filename-era publication mechanism cannot be used by the v1 path without violating no-legacy-mutation; a future guarded projection design would be needed if public document artifacts are required.
- Public lifecycle-v1 successor rejection coverage is still incomplete for every requested source class (base, stale hash, superseded, withdrawn, unresolved, and filename-only) at the public scientific runtime boundary; direct lifecycle service coverage exists but does not justify checking the broader materialization task.
- The combined pending-audit/recovery and cross-suite restart matrices remain partial as previously documented. They are achievable but require targeted tests across legacy audit compatibility and v1 fault seams; they are not claimed complete.

### Files modified in this continuation

- `.pi/extensions/proposal-workspace.ts`
- `tests/paper-proposal-v2-lifecycle-v1.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

No scientific documents, legacy durable state, legacy withdrawal records, migrations, commits, or PRs were modified.

### Verification evidence

- Safety net: focused lifecycle/recovery/pending-audit/routing/entry/materialization command — **52 passing**.
- RED: public lifecycle-v1 responses omitted normalized transition evidence.
- GREEN: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` — **17 passing**.
- TRIANGULATE: committed withdrawal, rejected restore, and committed restore evidence are asserted separately and checked for sensitive payload/path exclusion.
- Focused integration: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-recovery.test.mjs tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs` — **52 passing**.
- `git diff --check` — passed. Final verify/full suite deliberately not run.

### Apply-completion assessment

Apply **cannot** become complete yet: 20 task checkboxes remain and final verification is blocked. The lifecycle specification's core v1 acceptance criteria now have direct implementation/test traces above, but apply still needs the missing public-scientific source-rejection matrix, explicit read-only routing coverage, full restart/audit matrix, and final requirements/test verification. Deferred legacy-publication tasks are not impossible; they require a separately safe projection design and must not be satisfied by reviving filename authority.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Public normalized transition evidence | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | Public integration | 52 focused passing | `transitionEvidence` was absent | 17 lifecycle tests passing | Withdrawn/rejected/restored projections plus payload-exclusion assertion | One local projection helper; no router/storage behavior change |

### Structured status consumed

```json
{"changeName":"proposal-lifecycle-base-revisions","artifactStore":"openspec","applyState":"ready","taskProgress":{"completed":33,"pending":20},"actionContext":{"mode":"repo-local","allowedEditRoots":["/Users/diego/Desktop/Proyectos/papersmith-ai"]},"nextRecommended":"apply","warnings":["Strict TDD active.","Final verify intentionally not run."]}
```

### Remaining tasks (exact unchecked task lines)

- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [ ] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.
- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.
- [ ] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.
- [ ] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.
- [ ] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [ ] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.
- [ ] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.

## Slice 3 continuation — public lifecycle-v1 E2E evidence

**Status:** partial Slice 3 continuation complete. This batch validated the existing normalized lifecycle-v1 public projection through the registered `paper_proposal_v2_execute` tool; it did not alter lifecycle production code, legacy artifacts, or scientific documents.

### Completed persisted tasks

- No task checkbox was newly completed. The 20 remaining task lines are broader than this E2E batch, so marking any of them would be inaccurate.
- The already-implemented public lifecycle-v1 route now has dedicated public E2E coverage for committed withdrawal, typed filename-only restore rejection, committed restore, and normalized bounded transition evidence.

### Files changed in this continuation

- `tests/paper-proposal-v2-scientific-public-e2e.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

No proposal documents, `.paper-proposal-v2/withdrawn/`, legacy proposal files, derived state, receipts, migrations, commits, or PRs were changed.

### Public E2E evidence

- A temporary explicitly registered lifecycle-v1 workspace is initialized with a base, first revision, and active successor only through `LifecycleService`.
- The registered public tool withdraws `revision-2`, returns `WITHDRAWN_ONLY`, a null active pointer, a persistent `withdrawalId`, and bounded `transitionEvidence`.
- A filename-only restore returns `status: blocked`, `semanticCode: WITHDRAWAL_IDENTITY_NOT_FOUND`, and rejected bounded evidence.
- Restore by the returned persistent withdrawal ID returns `ACTIVE` with `revision-2` as the sole active revision.
- Assertions prove transition evidence excludes locator strings, user instruction text, temporary-root fragments, and content-store paths; no legacy proposal or scientific materialization artifact is published.

### Verification and failure split

- Safety net before edits: focused lifecycle/public/recovery/routing/entry/materialization command — **61 passing**.
- RED: `node --test tests/paper-proposal-v2-scientific-public-e2e.test.mjs` — **9 passing, 1 failing** because the public E2E fixture did not yet configure and bootstrap explicit lifecycle-v1 authority; the route correctly remained legacy-blocked.
- GREEN: after extending only the temporary E2E fixture, `node --test tests/paper-proposal-v2-scientific-public-e2e.test.mjs` — **10 passing**.
- TRIANGULATE/REFACTOR: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-public-e2e.test.mjs tests/paper-proposal-v2-scientific-recovery.test.mjs tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs` — **62 passing**; `git diff --check` — passed.
- Full Node: `node --test tests/*.test.mjs` — **321 passing, 1 failing**. The sole failure is the known pre-existing `tests/document-operation-guard.test.mjs` assertion: unchanged test expects `"AMBIGUOUS"`, which exists in `HEAD:.pi/extensions/proposal-workspace.ts` but not in the already-modified worktree file. It is separate worktree drift, not a lifecycle-v1 regression.
- Python: `python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` — **15 passing**.

### TDD Cycle Evidence

| Task | Test file | Layer | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|
| Public lifecycle-v1 transition contract | `tests/paper-proposal-v2-scientific-public-e2e.test.mjs` | Public E2E | Fixture lacked explicit v1 authority; expected typed withdrawal result was blocked | Temporary fixture registers only v1 durable authority; 10 E2E tests pass | Withdrawal, filename-only rejection, restore-by-ID, payload exclusion, and no legacy publication; 62 focused tests pass | Fixture setup is opt-in; no production refactor needed |

### Acceptance trace reconciliation

The prior normalized-transition acceptance trace remains valid and this E2E test adds the public-route proof for withdrawal/restore semantic classification and bounded durable evidence. Core lifecycle-v1 acceptance criteria remain traceable through the checked authority/read/materialization/observability tasks and their focused suites. The unchecked cross-suite source-rejection, pending-audit, legacy compatibility, and final-verification work remains intentionally unclaimed.

### Deviations from design

- The E2E fixture uses the explicit lifecycle-v1 authority boundary and does not attempt to revive filename-era rendering, guarded legacy publication, or record migration.
- No production source changed because the existing public projection satisfied the newly added E2E contract.

### Workload / PR boundary

- Delivery path: already-approved three-slice plan; this is a bounded **Slice 3 public-E2E evidence** batch.
- No commit, PR, or review transaction was created.

### Structured status consumed

```json
{"changeName":"proposal-lifecycle-base-revisions","artifactStore":"openspec","applyState":"ready","taskProgress":{"completed":33,"pending":20},"dependencies":{"apply":"ready","verify":"blocked","archive":"blocked"},"actionContext":{"mode":"repo-local","workspaceRoot":"/Users/diego/Desktop/Proyectos/papersmith-ai","allowedEditRoots":["/Users/diego/Desktop/Proyectos/papersmith-ai"]},"nextRecommended":"apply","warnings":["Strict TDD active.","CodeGraph MCP unavailable; targeted filesystem fallback used.","Full Node suite has one pre-existing document-operation-guard worktree failure."]}
```

### Remaining tasks (exact unchecked task lines)

- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [ ] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.
- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.
- [ ] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.
- [ ] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.
- [ ] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [ ] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.
- [ ] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.

## Slice 3 continuation — lifecycle source rejection and restart/audit compatibility

**Status:** partial Slice 3 implementation/evidence batch complete. Final verify remains blocked; this does not complete the change.

### Completed persisted task

- Marked the recovery/pending-audit fault-coverage task complete in `tasks.md` after adding marker, projection, restart, and no-write compatibility proof.

### Lifecycle-owned behavior completed

- `LifecycleMaterializationPlanner` now returns `ACTIVE_REVISION_NOT_FOUND` for a lifecycle with historical revisions but no active revision (`WITHDRAWN_ONLY`); it never falls through to a misleading first-materialization attempt.
- Successor creation coverage proves base, superseded, stale-hash, withdrawn, and filename-only source evidence are rejected without changing durable lifecycle inventory.
- Fresh entry rebuilds lifecycle-owned base/active/superseded evidence from durable records rather than locators and publishes no legacy proposal file.
- A lifecycle-v1 diagnostic against an active legacy `PENDING_AUDIT` fixture leaves the marker, metadata, and quarantine bytes unchanged, creates no lifecycle-v1 authority, and preserves the existing audit pass.
- Before-marker interruption remains unregistered/diagnostic-only; after-projection interruption reconstructs the committed base through a fresh read-only inventory. Neither path creates a partial legacy proposal or changes scientific recovery evidence.

### Files changed in this continuation

- `.pi/extensions/paper-proposal-v2/materialization-planner.ts`
- `tests/paper-proposal-v2-lifecycle-v1.test.mjs`
- `tests/paper-proposal-v2-scientific-recovery.test.mjs`
- `tests/paper-proposal-v2-pending-audit.test.mjs`
- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

### Verification evidence

- Safety net: focused lifecycle/public/recovery/pending-audit/routing/entry/materialization suite — **62 passing** before this batch.
- RED: the new withdrawn-lifecycle planner test failed with `ACTIVE_REVISION_ALREADY_EXISTS`; expected `ACTIVE_REVISION_NOT_FOUND`.
- GREEN: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs` — **18 passing** after the lifecycle-owned guard.
- TRIANGULATE: added stale, superseded, withdrawn, base, and filename-only source-rejection cases — lifecycle suite **19 passing**.
- Recovery: `node --test tests/paper-proposal-v2-scientific-recovery.test.mjs` — **6 passing**.
- Pending audit: `node --test tests/paper-proposal-v2-pending-audit.test.mjs` — **8 passing**.
- Focused integration: `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-public-e2e.test.mjs tests/paper-proposal-v2-scientific-recovery.test.mjs tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs` — **67 passing**.
- `git diff --check` — passed.
- Full Node/Python regression was not rerun in this apply batch. Previous evidence remains **321 Node passing / 1 pre-existing `document-operation-guard` worktree failure** and **15 Python passing**. The pre-existing failure is unchanged: its test expects `AMBIGUOUS`, present in `HEAD:.pi/extensions/proposal-workspace.ts` but absent from the pre-existing modified worktree file.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Withdrawn lifecycle materialization guard | `tests/paper-proposal-v2-lifecycle-v1.test.mjs` | Integration | 62 focused passing | Expected `ACTIVE_REVISION_NOT_FOUND`, received `ACTIVE_REVISION_ALREADY_EXISTS` | 18 lifecycle tests passing | Stale/superseded/withdrawn/base/filename source matrix; 19 passing | One explicit lifecycle-state guard; no legacy path touched |
| Restart and marker recovery | `tests/paper-proposal-v2-scientific-recovery.test.mjs` | Integration | Existing recovery suite passing | Existing marker seams extended as triangulation of the prior fault behavior | 6 recovery tests passing | Before-marker, after-marker/projection, fresh-entry and no-publication cases | None required |
| Pending-audit compatibility diagnostics | `tests/paper-proposal-v2-pending-audit.test.mjs` | Integration | Existing pending-audit suite passing | Existing read-only diagnostic seam extended as triangulation | 8 pending-audit tests passing | Byte-identical metadata/marker/quarantine plus successful active audit | None required |

### Traceability disposition

The remaining filename-era renderer, publication, workspace-adapter, and legacy transaction checklist lines stay unchecked. Lifecycle-v1 routes avoid those modules deliberately because routing lifecycle materialization through filename-derived rendering or legacy proposal publication would violate the no-migration/no-write contract. This batch implements and proves the lifecycle-owned alternatives; it does not falsely claim legacy-path conversion.

### Remaining tasks

There are 19 unchecked tasks in `tasks.md`, including the legacy projection/adapter conversion lines, the broader public scientific source-rejection/routing matrix, the exhaustive cross-suite restart matrix, smoke compatibility, and final requirements/full-regression verification. Verify is not ready.

### Workload / PR boundary

- Delivery path: already-approved three-slice chain; this remains the assigned **Slice 3** boundary.
- No migrations, commits, PRs, scientific-document changes, or legacy durable-state mutation.

### Structured status consumed

```json
{
  "changeName": "proposal-lifecycle-base-revisions",
  "artifactStore": "openspec",
  "applyState": "ready",
  "taskProgress": {"completed": 33, "pending": 20},
  "dependencies": {"apply": "ready", "verify": "blocked", "archive": "blocked"},
  "actionContext": {"mode": "repo-local", "workspaceRoot": "/Users/diego/Desktop/Proyectos/papersmith-ai", "allowedEditRoots": ["/Users/diego/Desktop/Proyectos/papersmith-ai"]},
  "nextRecommended": "apply",
  "warnings": ["Strict TDD active.", "CodeGraph MCP unavailable; targeted filesystem fallback used.", "Known full Node guard failure is pre-existing worktree drift."]
}
```

## Slice 3 completion reconciliation — lifecycle-v1 scope

**Status:** no further safe lifecycle-owned production task remains in the approved Slice 3 scope. This reconciliation checked ten evidence/traceability tasks after re-running the focused and configured suites; final verify is **not** complete and remains blocked by nine unchecked tasks.

### Completed persisted tasks

The following are now visibly marked `- [x]` in `tasks.md`:

- materialization/routing source-rejection coverage;
- successor lineage/source-rejection triangulation;
- read-only entry/routing no-write proof;
- typed lifecycle projections at entry/runtime boundaries;
- fresh-instance restart/recovery matrix;
- configured full-regression execution (with the recorded pre-existing Node failure);
- stable identity/state fixture updates;
- complete spec acceptance-criterion trace;
- no-migration/no-filename-authority confirmation; and
- the explicit no-data-loss decision check (no such decision is required).

### Filename-era task dispositions

- `InitialRevisionRenderer` / `MaterializationCandidateExecutor` (lines 79 and 92): intentionally bypassed. `LifecycleMaterializationPlanner` + `LifecycleService` materialize complete registered base or active-revision bytes and preserve exact lineage. Reusing the legacy `CREATE_R01` renderer would synthesize filename-era output and violate the approved guardrail.
- `MaterializationPublicationService` / `ProposalWorkspaceAdapter` (line 80): intentionally bypassed. Lifecycle-v1 commits request/result/revision transitions inside the v1 authority and records a lifecycle-owned scientific projection. Publishing a legacy proposal filename, derived state, or receipt would mutate durable legacy state.
- Legacy `orchestrator.ts` / proposed v1 `proposal-workspace.ts` conversion (lines 81 and 112): only the actual public composition root (`.pi/extensions/proposal-workspace.ts`) routes explicit lifecycle-v1 withdrawal/restore before model/document paths. The legacy orchestrator continues serving legacy lifecycle semantics; forcing it through v1 would infer authority from filenames or migrate legacy state. Persistent-ID restore and explicit base/non-withdrawn/unresolved classification are already provided by `LifecycleV1PublicRouter` on the v1 path.
- `revision-lifecycle-transaction.ts` (line 111): remains the guarded legacy-publication transaction. Routing it through `LifecycleService` would make v1 withdraw/restore move `.paper-proposal-v2/withdrawn/`, proposal files, derived state, and receipts—the exact durable legacy state that lifecycle-v1 is approved to leave read-only.

### Files changed in this reconciliation

- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

No scientific document, legacy proposal artifact, legacy withdrawal record, derived state, receipt, migration, or lifecycle-v1 production module changed in this reconciliation.

### Verification evidence

- Focused lifecycle/public/recovery/pending-audit/routing/entry/materialization command: **67 passing, 0 failing**.
- Configured Node command: **326 passing, 1 failing**; only `tests/document-operation-guard.test.mjs` fails. It expects `AMBIGUOUS`, which is in `HEAD:.pi/extensions/proposal-workspace.ts` but absent from the pre-existing modified worktree file; the test is unchanged. This is pre-existing worktree drift, not a lifecycle-v1 failure.
- Configured Python command: **15 passing**.
- `git diff --check`: passed.
- Public E2E status: covered by `tests/paper-proposal-v2-scientific-public-e2e.test.mjs` in the 67-test focused command; it exercises withdrawal, filename-only restore rejection, restore by persistent withdrawal ID, bounded evidence, and no legacy publication.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Slice 3 reconciliation | Existing focused suites | Integration / public E2E | 67 passing | No production behavior changed in this reconciliation | 67 passing | Full configured regression plus public E2E | No refactor required |

### Remaining tasks (exact unchecked lines)

- [ ] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase.
- [ ] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone.
- [ ] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing.
- [ ] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts.
- [ ] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification.
- [ ] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes.
- [ ] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative.
- [ ] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact.

### Workload / PR boundary

- Delivery path consumed: approved **Slice 3** only; no commit, PR, review transaction, verification phase, or delivery decision was created.
- `Review Workload Forecast` remains high/chained, but the parent supplied the approved Slice 3 boundary.

### Structured status consumed

```json
{
  "changeName":"proposal-lifecycle-base-revisions",
  "artifactStore":"openspec",
  "applyState":"ready",
  "taskProgress":{"completed":44,"pending":9},
  "dependencies":{"apply":"ready","verify":"blocked","archive":"blocked"},
  "actionContext":{"mode":"repo-local","workspaceRoot":"/Users/diego/Desktop/Proyectos/papersmith-ai","allowedEditRoots":["/Users/diego/Desktop/Proyectos/papersmith-ai"]},
  "nextRecommended":"apply",
  "warnings":["Strict TDD active.","CodeGraph MCP unavailable; targeted filesystem fallback used.","Full Node has one pre-existing document-operation-guard worktree failure."]
}
```

## Final nine-task reconciliation — lifecycle-v1 boundary

**Status:** #14 / Implement lifecycle correction is complete. All nine formerly unchecked task lines are reconciled: three are satisfied by current evidence, and six are explicitly `N/A — superseded by approved lifecycle-v1 architecture`. No genuine lifecycle-v1 functional requirement remains. #15 / Verify lifecycle correction was not performed.

### Per-task disposition and exact evidence

| Task | Disposition | Evidence / approved replacement |
|---|---|---|
| Task-completion guardrail | Satisfied | This batch changed only `tasks.md` and this progress artifact; no production source, scientific document, legacy runtime state, commit, PR, or review transaction changed. |
| `initial-revision-renderer.ts` / `materialization-candidate-executor.ts` first-materialization conversion | N/A — superseded by approved lifecycle-v1 architecture | `LifecycleMaterializationPlanner` invokes `LifecycleService.createFromBase` using durable complete base bytes and exact hash. The legacy renderer emits `CREATE_R01` from metadata/claims, so literal reuse would violate the no-legacy-write/no-migration boundary. |
| `materialization-publication-service.ts` / `proposal-workspace-adapter.ts` publication conversion | N/A — superseded by approved lifecycle-v1 architecture | `LifecycleService` durably owns request/result/revision transitions and locator-conflict validation; `ScientificWorkflowRuntime.materializeLifecycleV1()` commits only lifecycle-owned scientific projection evidence. Legacy publication writes public proposal files, derived state, and receipts. |
| Legacy `orchestrator.ts` / proposed v1 workspace routing conversion | N/A — superseded by approved lifecycle-v1 architecture | `.pi/extensions/proposal-workspace.ts` composes `LifecycleV1PublicRouter` before legacy orchestrator/model execution for explicit v1 workspaces; `ScientificWorkflowRuntime` delegates v1 materialization directly to `LifecycleService`. |
| `InitialRevisionRenderer` isolation | N/A — superseded by approved lifecycle-v1 architecture | `ScientificWorkflowRuntime.materializeLifecycleV1()` documents and enforces that it never invokes filename-era planning, candidate rendering, or workspace publication. |
| `revision-lifecycle-transaction.ts` conversion | N/A — superseded by approved lifecycle-v1 architecture | `LifecycleV1PublicRouter` delegates eligibility/classification to `LifecycleService`. The legacy transaction remains isolated because it moves `.paper-proposal-v2/withdrawn/`, public proposals, derived state, and receipts. |
| Legacy orchestration restore classification conversion | N/A — superseded by approved lifecycle-v1 architecture | The v1 public root passes only `withdrawalOperationId` as a durable withdrawal ID to `LifecycleV1PublicRouter` / `LifecycleService`; it yields `BASE_DOCUMENT_NOT_RESTORABLE`, `REVISION_NOT_WITHDRAWN`, or `WITHDRAWAL_IDENTITY_NOT_FOUND` without filename authority. |
| Pending-audit and smoke compatibility | Satisfied | `node --test tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-production-smoke.test.mjs` passed 9/9, including byte-identical legacy diagnostic/no-authority and completed-marker audit behavior. |
| Configured full regression | Satisfied for apply evidence | Node: 326 passed, 1 failed. The only failure is pre-existing `tests/document-operation-guard.test.mjs`: it expects `AMBIGUOUS`, which exists in `HEAD:.pi/extensions/proposal-workspace.ts` but was absent from the already-modified worktree file; test source is unchanged. Python: 15 passed. Evidence attachment to `verify-report.md` belongs to #15 and was not performed. |

### Completed persisted task updates

- All 53 task lines are visibly `- [x]` in `tasks.md`.
- The six literal legacy integration lines preserve their original wording and carry an explicit `N/A — superseded by approved lifecycle-v1 architecture` disposition.
- The three evidence/guardrail lines carry explicit satisfied dispositions.

### Files changed

- `openspec/changes/proposal-lifecycle-base-revisions/tasks.md`
- `openspec/changes/proposal-lifecycle-base-revisions/apply-progress.md`

### Verification evidence

- Focused safety evidence: `node --test tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-production-smoke.test.mjs` — 9 passed, 0 failed.
- Configured Node command: `node --test tests/*.test.mjs` — 326 passed, 1 pre-existing unrelated failure (`document-operation-guard`).
- Configured Python command: `python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` — 15 passed.
- `git diff --check` had passed before artifact edits; no production paths were edited in this reconciliation.

### TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| Final reconciliation evidence | Existing focused/full suites | Integration | 9 focused passing | No production behavior change; no RED applicable | Focused compatibility evidence passed | Full Node/Python execution captured the known pre-existing guard failure and 15 Python passes | No refactor required |

### Deviations from design

None. Literal implementation of the six legacy adapter/publication tasks is forbidden by the approved lifecycle-v1 no-legacy-write/no-migration boundary; the lifecycle-v1 components named above provide the required behavior without changing legacy state.

### Remaining tasks

None for implementation. Native status requires an explicit bounded review/start(target) before independent #15 verification; no review transaction was opened in this subtask. After that required review, #15 must independently assess the recorded Node failure and attach final evidence to `verify-report.md`.

### Workload / PR boundary

- Delivery path: parent-approved final reconciliation for the existing Slice 3 lifecycle-v1 boundary.
- No commit, PR, review transaction, scientific-document change, migration, or persistent legacy-state change.

### Structured status consumed and expected transition

```json
{
  "consumed": {
    "changeName": "proposal-lifecycle-base-revisions",
    "artifactStore": "openspec",
    "applyState": "ready",
    "taskProgress": {"completed": 44, "pending": 9},
    "dependencies": {"apply": "ready", "verify": "blocked", "archive": "blocked"},
    "actionContext": {"mode": "repo-local", "workspaceRoot": "/Users/diego/Desktop/Proyectos/papersmith-ai", "allowedEditRoots": ["/Users/diego/Desktop/Proyectos/papersmith-ai"]},
    "nextRecommended": "apply"
  },
  "actualAfterPersistence": {
    "taskProgress": {"completed": 53, "pending": 0},
    "applyState": "all_done",
    "dependencies": {"apply": "all_done", "verify": "blocked", "archive": "blocked"},
    "nextRecommended": "review",
    "blockedReasons": ["explicit bounded review/start(target) is required after apply before independent final verification: bounded review transaction is missing"]
  },
  "warnings": ["Strict TDD active.", "CodeGraph MCP was unavailable; targeted filesystem fallback used.", "Node full suite retains one pre-existing document-operation-guard worktree failure."]
}
```
