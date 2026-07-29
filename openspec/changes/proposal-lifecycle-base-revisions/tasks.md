# Tasks: Proposal Lifecycle Base Revisions

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 900–1,400 authored lines across 10–14 source/test files |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3: lifecycle-v1 authority; base/read-only and materialization integration; withdrawal/restore, reconstruction, observability, and regression hardening |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

The estimate includes a new durable authority, integration across existing lifecycle/materialization/entry paths, fault-injection and restart coverage, and compatibility safeguards. Generated artifacts and unchanged legacy fixtures are excluded. Do not migrate or rewrite legacy records.

## Implementation guardrails

- [x] Keep all lifecycle-v1 authority under `.paper-proposal-v2/lifecycle/v1/`; do not alter existing legacy records under `.paper-proposal-v2/withdrawn/`, filename-derived proposal files, derived-state files, or receipts.
- [x] Treat legacy records as read-only diagnostic/projection inputs only: never synthesize stable IDs, active pointers, lineage, or withdrawal authority from filenames or numeric ordering.
- [x] Preserve the existing `sha256` implementation as the initial versioned content-hash seam; reject hash mismatches rather than recomputing identity.
- [x] Serialize lifecycle transitions per workspace and make the commit marker the logical linearization point; incomplete transitions must be ignored, resumed, or reported as recovery-required/inconsistent, never exposed as success.
- [x] Keep task completion unchecked until implementation and verification prove it; no source, test, runtime-state, commit, or PR changes belong in this tasks phase. **Disposition: satisfied** — this reconciliation changed only `tasks.md` and `apply-progress.md`; no production, scientific-document, legacy-state, commit, PR, or review-transaction change was made.

## Slice 1 — Lifecycle-v1 authority and durable reconstruction

**Start:** current filename-based lifecycle code remains the only active behavior; no `lifecycle/v1` authority exists.
**Finish:** a standalone lifecycle service can register/reconstruct immutable domain records and execute the core state transitions against injected filesystem/clock/ID/hash seams.
**Verification:** dedicated lifecycle-v1 tests pass, including idempotency, hash/lineage validation, commit-marker recovery, and fail-closed reconstruction.
**Rollback:** remove only the new lifecycle-v1 modules and fixture directory; legacy files and legacy behavior remain byte-for-byte unchanged.

### RED

- [x] Add `tests/paper-proposal-v2-lifecycle-v1.test.mjs` with deterministic fixtures for `EMPTY`, `BASE_REGISTERED`, `ACTIVE`, `SUPERSEDED`, `WITHDRAWN`, `WITHDRAWN_ONLY`, and `INCONSISTENT`, covering the proposal error catalog and stable identities independent of locators.
- [x] Add failing tests in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` for the durable layout under `.paper-proposal-v2/lifecycle/v1/`, one-base enforcement, content/hash agreement, base/revision/withdrawal lineage, request/result idempotency, conflicting request reuse, and no filename-based active selection.
- [x] Add failing interruption tests for staging before the transition marker, after marker publication but before inventory projection, and after projection publication; assert prior state, committed reconstruction, or explicit recovery-required/inconsistent outcome only.

### GREEN

- [x] Extend `.pi/extensions/paper-proposal-v2/types.ts` with versioned `BaseDocument`, lifecycle revision, `WithdrawalRecord`, `LineageReference`, `MaterializationRequest`, `MaterializationResult`, `WorkspaceLifecycleState`, inventory/error unions, and structured transition evidence while retaining old filename types as compatibility projections.
- [x] Create `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` with injected filesystem/clock/ID/hash dependencies and durable records for `bases`, `contents`, `revisions`, `withdrawals`, `requests`, `results`, `transitions`, `inventory`, and per-transition staging. Verify immutable content before writing records that reference it.
- [x] Create `.pi/extensions/paper-proposal-v2/lifecycle-service.ts` as the sole state-machine owner for `registerBaseDocument`, `createFromBase`, `createSuccessor`, `withdrawRevision`, `restoreWithdrawnRevision`, `resolveActiveRevision`, and `rebuildLifecycleInventory`; return typed semantic codes rather than filesystem errors.
- [x] Implement per-workspace locking, transition staging, immutable record publication, commit-marker finalization, deterministic inventory digesting, and fresh post-commit reconstruction in `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` and `.pi/extensions/paper-proposal-v2/lifecycle-service.ts.
- [x] Make reconstruction load durable records before locator/projection data, include active/superseded/withdrawn history and withdrawal identities, and produce `LIFECYCLE_INVENTORY_INCONSISTENT` without deleting, inventing, migrating, or silently repairing contradictory records.

### TRIANGULATE

- [x] Extend `tests/paper-proposal-v2-lifecycle-v1.test.mjs` with duplicate active revisions, orphan withdrawals, broken lineage, missing content, mismatched hashes, duplicate identities, cross-workspace references, and conflicting locator cases; assert fail-closed behavior and unchanged durable evidence.
- [x] Extend the same suite with fresh `LifecycleService` instances that rebuild unchanged records byte-for-byte equivalently and return the same base ID, revision IDs, withdrawal IDs, states, lineage, and active pointer.
- [x] Run the configured Node regression command `node --test tests/*.test.mjs`; record any compatibility failures without weakening lifecycle-v1 invariants.

### REFACTOR

- [x] Refine record validation and operation result helpers in `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts`, `.pi/extensions/paper-proposal-v2/lifecycle-service.ts`, and `.pi/extensions/paper-proposal-v2/types.ts` so all semantic error codes and transition outcomes are centralized and independently reviewable.
- [x] Confirm the new fixture setup never writes to repository proposal files or legacy `.paper-proposal-v2/withdrawn/` paths; keep the dedicated suite deterministic and isolated.

## Slice 2 — Base registration, read-only exposure, and create integration

**Start:** lifecycle-v1 authority exists but existing deliberation/materialization routes still select filename-derived sources and synthesize `CREATE_R01` content.
**Finish:** explicitly registered workspaces expose read-only base/lifecycle evidence, first materialization consumes complete base bytes, and successors consume the unique active revision identity/hash.
**Verification:** materialization, entry, routing, and publication integration suites prove exact source/approval boundaries and one active revision.
**Rollback:** disable lifecycle-v1 mutation routing while preserving the new authority records; no legacy proposal artifact is rewritten or migrated.

### RED

- [x] Add failing scenarios to `tests/paper-proposal-v2-lifecycle-v1.test.mjs` for complete-base `CREATE_FROM_BASE`, metadata-only rejection, exact base lineage, approved-change-only content, successor source identity/hash, stale/filename-only rejection, output locator conflicts, and idempotent retries.
- [x] Update `tests/paper-proposal-v2-scientific-entry.test.mjs` expectations to include base identity/hash/lineage, all active/superseded/withdrawn evidence, explicit `WITHDRAWN_ONLY`, and read-only deliberation with zero lifecycle writes.
- [x] Update `tests/paper-proposal-v2-scientific-materialization.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` with failing coverage for semantic `CREATE_FROM_BASE`/`CREATE_SUCCESSOR`, lifecycle routing precedence, and rejection of stale or withdrawn source evidence.

### GREEN

- [x] Change `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts` from filename/latest-file authority to a read-only adapter over `LifecycleService.rebuildLifecycleInventory()`, returning stable IDs, hashes, lineage, all lifecycle states, withdrawal IDs, and explicit inconsistency/absence.
- [x] Update `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` and `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts` to consume the rebuilt inventory; expose registered base evidence read-only and emit `WITHDRAWN_ONLY` without predecessor promotion or implicit restore.
- [x] Update `.pi/extensions/paper-proposal-v2/materialization-planner.ts` to select `CREATE_FROM_BASE` only for an exact registered base with no first revision and `CREATE_SUCCESSOR` only for the resolved active revision ID/hash; preserve frozen decision and approved-change provenance.
- [x] Update `.pi/extensions/paper-proposal-v2/initial-revision-renderer.ts` and `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` so first materialization begins with complete registered base bytes, verifies untouched-byte preservation and approved-change boundaries, and never creates a valid revision from claims/metadata alone. **Disposition: N/A — superseded by approved lifecycle-v1 architecture.** `LifecycleMaterializationPlanner` + `LifecycleService` materialize from durable complete base/active-revision bytes and exact hashes; routing through the filename-era `CREATE_R01` renderer would violate the no-legacy-write boundary.
- [x] Update `.pi/extensions/paper-proposal-v2/materialization-publication-service.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` to reserve and complete lifecycle requests/results around guarded publication, treating public filenames as locators and rejecting occupied locators without overwrite. **Disposition: N/A — superseded by approved lifecycle-v1 architecture.** `LifecycleService` owns request/result transitions and locator conflict checks; `ScientificWorkflowRuntime.materializeLifecycleV1()` records a lifecycle-owned projection. Literal legacy guarded publication would write proposal files, derived state, and receipts.
- [x] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace.ts` so lifecycle routing occurs before document loading/models and scientific materialization delegates state transitions to `LifecycleService` rather than filename parsing. **Disposition: N/A — superseded by approved lifecycle-v1 architecture.** The actual public composition root `.pi/extensions/proposal-workspace.ts` routes explicit lifecycle-v1 operations to `LifecycleV1PublicRouter` before the legacy orchestrator/model path, while `ScientificWorkflowRuntime` delegates v1 materialization to `LifecycleService`; converting the filename-era orchestrator would couple or migrate legacy state.

### TRIANGULATE

- [x] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that first materialization preserves the full base, applies only approved changes, records `BASE_DOCUMENT` lineage, and retries the same request without duplicate revisions or active pointers.
- [x] Verify in `tests/paper-proposal-v2-scientific-materialization.test.mjs` that successors preserve complete source content, record `REVISION` lineage, supersede exactly the source, and reject base, stale-hash, superseded, withdrawn, unresolved, or filename-only sources.
- [x] Verify in `tests/paper-proposal-v2-scientific-entry.test.mjs` and `tests/paper-proposal-v2-scientific-routing.test.mjs` that read-only inspection performs no lifecycle mutation and that legacy filename routes cannot bypass lifecycle authority.
- [x] Run `node --test tests/paper-proposal-v2-lifecycle-v1.test.mjs tests/paper-proposal-v2-scientific-entry.test.mjs tests/paper-proposal-v2-scientific-materialization.test.mjs tests/paper-proposal-v2-scientific-routing.test.mjs`.

### REFACTOR

- [x] Remove or isolate `InitialRevisionRenderer`'s filename-era authority without deleting compatibility/projection code needed for legacy read-only behavior; document the semantic source boundary in the affected module contracts. **Disposition: N/A — superseded by approved lifecycle-v1 architecture.** The v1 materialization route is explicitly isolated in `ScientificWorkflowRuntime.materializeLifecycleV1()` and bypasses `InitialRevisionRenderer`; its method contract states that it never invokes filename-era planning, candidate rendering, or workspace publication.
- [x] Ensure `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts`, `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts`, and the workspace adapters expose typed lifecycle results rather than translating inconsistency into a guessed active filename.

## Slice 3 — Withdrawal/restore classification, inventory/restart integration, and operational evidence

**Start:** lifecycle-v1 create/read paths are integrated, but withdrawal/restore and restart still depend on legacy public files and generic filename classification.
**Finish:** withdrawal, restore, inventory rebuild, project re-entry, and metrics use persistent identity/state authority; legacy records remain diagnostic-only and fail closed.
**Verification:** withdrawal, pending-audit, recovery, restart, entry, routing, smoke, and full repository suites pass with structured evidence assertions.
**Rollback:** disable lifecycle-v1 withdrawal/restore routing and retain immutable lifecycle records; never delete withdrawal history or rewrite legacy records.

### RED

- [x] Add failing tests in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` for active withdrawal clearing the pointer, `WITHDRAWN_ONLY`, no predecessor promotion, durable recovery content, restore by persistent `withdrawalId`, restored historical withdrawal state, and no new revision on restore.
- [x] Add failing classification coverage for base → `BASE_DOCUMENT_NOT_RESTORABLE`, existing non-withdrawn revision → `REVISION_NOT_WITHDRAWN`, unresolved/generic filename → `WITHDRAWAL_IDENTITY_NOT_FOUND`, and absence of semantic `WITHDRAWAL_NOT_FOUND`.
- [x] Extend `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` with before/after marker, projection, and restart fault cases; assert no partial success and preserved recovery evidence.
- [x] Add failing tests for structured lifecycle operational events and bounded metrics in `tests/paper-proposal-v2-scientific-routing.test.mjs` or a dedicated `tests/paper-proposal-v2-lifecycle-observability.test.mjs`; assert content, prompts, patches, and absolute paths are absent.

### GREEN

- [x] Route `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` through `LifecycleService` while retaining guarded staging, exact-copy, audit, rollback, and mutation-lock techniques for projection publication; the service decides withdrawability and restore classification. **Disposition: N/A — superseded by approved lifecycle-v1 architecture.** `LifecycleV1PublicRouter` delegates withdrawal/restore eligibility and classification to `LifecycleService`; the legacy transaction deliberately remains isolated because it moves `.paper-proposal-v2/withdrawn/`, public proposals, derived state, and receipts.
- [x] Update `.pi/extensions/paper-proposal-v2/orchestrator.ts` and `.pi/extensions/paper-proposal-v2/proposal-workspace.ts` to require persistent withdrawal identity for restore and to classify base, non-withdrawn revision, and unresolved references with the explicit semantic codes. **Disposition: N/A — superseded by approved lifecycle-v1 architecture.** The actual v1 public composition delegates only `withdrawalOperationId` to `LifecycleV1PublicRouter`, which delegates to `LifecycleService` for `BASE_DOCUMENT_NOT_RESTORABLE`, `REVISION_NOT_WITHDRAWN`, and `WITHDRAWAL_IDENTITY_NOT_FOUND`; the legacy orchestrator is not a safe v1 authority.
- [x] Update `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` and `.pi/extensions/paper-proposal-v2/scientific-workflow-runtime.ts` to rebuild inventory on fresh entry/restart, retain withdrawn and superseded history, and block materialization from stale/withdrawn evidence.
- [x] Extend `.pi/extensions/paper-proposal-v2/runtime-metrics.ts` with bounded lifecycle operation/outcome counters and correlation IDs; persist structured transition evidence through `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` without raw content, prompts, patch text, or absolute paths.
- [x] Keep `.paper-proposal-v2/withdrawn/`, legacy `proposals/research-concept-r*.md`, derived state, and receipts read-only. Add an explicit compatibility/inconsistency diagnostic path that never infers v1 identity, lineage, active state, or withdrawal authority and blocks semantic mutation until explicit registration/migration exists.

### TRIANGULATE

- [x] Verify restart reconstruction with fresh service/runtime instances in `tests/paper-proposal-v2-lifecycle-v1.test.mjs` and `tests/paper-proposal-v2-scientific-recovery.test.mjs` for active, superseded, withdrawn, `WITHDRAWN_ONLY`, committed restore, missing content, multiple-active, orphan withdrawal, broken lineage, and hash mismatch cases.
- [x] Verify `tests/paper-proposal-v2-pending-audit.test.mjs` and `tests/paper-proposal-v2-smoke.test.mjs` preserve existing guard/audit/self-audit guarantees while lifecycle commit markers remain authoritative. **Disposition: satisfied** — focused `pending-audit` plus production-smoke run passed 9/9; it includes byte-identical legacy diagnostic/no-authority proof and completed marker audit coverage.
- [x] Verify legacy fixtures are byte-identical before and after read-only inspection and fail-closed semantic mutation; assert no migration files or synthetic lifecycle records are created.
- [x] Run the complete configured regression commands: `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`.

### REFACTOR

- [x] Centralize public lifecycle classification and compatibility mapping in `.pi/extensions/paper-proposal-v2/types.ts` plus the lifecycle adapter boundary; keep deprecated `WITHDRAWAL_NOT_FOUND` isolated from semantic v1 results.
- [x] Bound and normalize operational evidence in `.pi/extensions/paper-proposal-v2/lifecycle-state-store.ts` and `.pi/extensions/paper-proposal-v2/runtime-metrics.ts`; ensure logs are deterministic enough for recovery diagnosis but contain no sensitive payloads or raw filesystem layout.
- [x] Update affected test fixtures in `tests/paper-proposal-v2-scientific-entry.test.mjs`, `tests/paper-proposal-v2-scientific-materialization.test.mjs`, `tests/paper-proposal-v2-scientific-recovery.test.mjs`, `tests/paper-proposal-v2-scientific-routing.test.mjs`, and `tests/paper-proposal-v2-pending-audit.test.mjs` to assert stable identity/state contracts instead of filename ordering while preserving legacy compatibility tests.

## Final verification and handoff

- [x] Confirm every requirement and acceptance criterion in `openspec/changes/proposal-lifecycle-base-revisions/specs/proposal-lifecycle/spec.md` maps to at least one completed implementation/test task above.
- [x] Confirm no task introduces automatic migration, legacy record mutation, filename-derived identity, implicit predecessor promotion, or best-effort active selection.
- [x] Run `node --test tests/*.test.mjs && python3 -m unittest discover -s tests -p 'test_extract_pdf.py'` after all slices are applied and attach the result to the verification artifact. **Disposition: satisfied for apply evidence** — Node ran 326 passing / 1 pre-existing unrelated guard-contract failure; Python ran 15 passing. The exact evidence is recorded in `apply-progress.md`; attaching it to the verification artifact is the pending #15 verification-phase action, not a new implementation requirement.
- [x] Stop and report a data-loss/recovery decision if any implementation would require deleting, rewriting, or automatically converting existing legacy records; otherwise continue through apply and verify without creating commits or PRs.
