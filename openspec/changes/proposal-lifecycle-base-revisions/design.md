# Design: Identity-Based Proposal Lifecycle

Introduce a versioned lifecycle authority beneath Paper Proposal V2. The authority owns the immutable base, stable revision and withdrawal identities, request/result idempotency, and the active pointer. Existing filenames, public proposal files, derived states, receipts, and withdrawal directories become verified locators/projections; they are never lifecycle identity or active-selection authority.

## Decisions

| Topic | Decision |
|---|---|
| First materialization | Replace scientific-plan `CREATE_R01` with semantic `CREATE_FROM_BASE`; it reads the registered base bytes and exact hash, applies only the frozen approved changes, and records `BASE_DOCUMENT(baseDocumentId, contentHash)` lineage. |
| Withdrawal result | Withdrawing an eligible active non-first revision creates a persistent `withdrawalId`, changes that revision to `WITHDRAWN`, clears the active pointer, and commits `WITHDRAWN_ONLY`. No predecessor is promoted. |
| Restoration authority | Restore accepts only a persistent committed `withdrawalId`. A filename is never a restore lookup key or restoration authority. |
| Persistence | A new versioned lifecycle journal is authoritative. Immutable record files plus a final commit marker make a transition visible; public artifacts and existing scientific records are verified projections. |
| Legacy data | No automatic conversion or filename inference. A workspace without valid lifecycle-v1 authority is compatibility-readable only where safe and is fail-closed for semantic mutation until an explicit future migration/registration process. |

## Component design

### New lifecycle authority

Add `lifecycle-state-store.ts` and `lifecycle-service.ts` under `.pi/extensions/paper-proposal-v2/`.

`lifecycle-state-store.ts` provides injected filesystem/clock/ID/hash seams and owns durable records under:

```text
.paper-proposal-v2/lifecycle/v1/
  bases/<baseDocumentId>.json
  contents/<contentHash>
  revisions/<revisionId>.json
  withdrawals/<withdrawalId>.json
  requests/<requestId>.json
  results/<requestId>.json
  transitions/<transitionId>.json
  inventory/<workspaceId>.json
  staging/<transitionId>/
```

Each immutable content record is written and hash-verified before any record refers to it. Base, revision, lineage, withdrawal, request, and result records carry schema version, workspace ID, stable ID, content hash, provenance, and their required semantic state. Locators are optional fields and are maintained in a non-authoritative projection/index.

`lifecycle-service.ts` is the sole state-machine owner. It exposes `registerBaseDocument`, `createFromBase`, `createSuccessor`, `withdrawRevision`, `restoreWithdrawnRevision`, `resolveActiveRevision`, and `rebuildLifecycleInventory`. Its typed return values use the proposal error catalog, not filesystem errors. It validates lineage closure, content hashes, one base, at most one active revision, and withdrawal-to-revision ownership before mutating.

The existing `sha256` implementation remains the initial content-hash implementation, recorded with an explicit hash-algorithm/version field so the record format does not silently depend on filenames or normalization behavior.

### Existing V2 components

| Existing component | Change |
|---|---|
| `types.ts` | Add lifecycle-v1 domain types (`BaseDocument`, `LifecycleRevision`, `WithdrawalRecord`, `LineageReference`, request/result, inventory state) and semantic lifecycle operation/result/error unions. Preserve old filename-based types only as compatibility/projection types. |
| `revision-lifecycle-store.ts` | Replace `latestManagedFilename()` authority and public-file-only inventory with a read-only adapter over `LifecycleService.rebuildLifecycleInventory()`. It may validate locator projections, but it must return all active/superseded/withdrawn evidence and persistent withdrawal IDs from lifecycle records. |
| `revision-lifecycle-transaction.ts` | Retire as the state-machine owner. Reuse its guarded staging, audit, exact-copy, rollback, and mutation-lock techniques behind `LifecycleService` projection publishing. The service, rather than filename parsing, decides eligibility and restore classification. |
| `materialization-planner.ts` | Select `CREATE_FROM_BASE` only when a registered base is the exact source and no first revision exists. Select `CREATE_SUCCESSOR` only from the resolved active revision ID/hash. Frozen decision evidence and approved changes remain the approval boundary. |
| `initial-revision-renderer.ts` | Remove it from lifecycle first materialization. The candidate executor must begin with complete registered base bytes; it may not synthesize a minimal document from metadata/claims. |
| `materialization-candidate-executor.ts` | Add a base-source execution seam that verifies preservation of unmodified base bytes and approved-change boundaries before publication. |
| `materialization-publication-service.ts` / `proposal-workspace-adapter.ts` | Publish a lifecycle-owned candidate only after lifecycle preconditions are reserved. After guarded publication, verify derived state and receipt, then complete the lifecycle request/result transition. Existing workspace filenames remain output locators, not IDs. |
| `scientific-workflow-runtime.ts` / `project-entry-resolver.ts` | Use the rebuilt lifecycle inventory. Deliberation receives base and active evidence read-only; `WITHDRAWN_ONLY` is emitted when history exists with no active revision. Scientific threads retain revision evidence as a projection and must reject stale/withdrawn source evidence for materialization. |
| `orchestrator.ts` / `proposal-workspace.ts` | Keep lifecycle routing before document loading, planning, tutoring, reviewing, and models. Route typed withdrawal/restore to the lifecycle service and route scientific materialization through semantic create-from-base/successor services. |
| `runtime-metrics.ts` | Add bounded lifecycle operation/outcome counters; do not log document content, user instructions, or raw paths. |

## Persistence and reconstruction

A lifecycle transition uses a per-workspace lock and a write-ahead transition record:

1. Rebuild and validate durable lifecycle authority; reject `INCONSISTENT` before mutation.
2. Resolve stable IDs and expected hashes, then reserve the immutable request identity. A matching committed request returns its stored result; a conflicting reuse is rejected.
3. Write immutable content and all proposed records to a transition staging directory; verify hashes, lineage, locator availability, and resulting inventory digest.
4. Publish or move guarded workspace projections only after staging is complete. Existing document guard, derived state, receipt, consistency audit, and self-audit remain required evidence.
5. Atomically rename/finalize the transition commit marker containing the record digest, then write the derived inventory projection. The commit marker is the logical linearization point.
6. Return success only after a fresh reconstruction validates the committed result and unique active pointer.

If a process stops before the marker, rebuild ignores staged records and either restores the verified prior projection or reports `RECOVERY_REQUIRED`; it never treats partially written public files as active. If the marker exists but its projection update is incomplete, reconstruction derives the one committed state from immutable records and either repairs only the projection or returns `LIFECYCLE_INVENTORY_INCONSISTENT`. It never chooses the highest filename.

`REBUILD_LIFECYCLE_INVENTORY` loads base, content, revision, request/result, withdrawal, and transition records before locator data. It verifies hashes and lineage, includes superseded and withdrawn revisions, and deterministically derives `EMPTY`, `BASE_REGISTERED`, `ACTIVE`, or `WITHDRAWN_ONLY`. Duplicate IDs, contradictory markers/states, missing content, orphan withdrawals, invalid hashes, or multiple active revisions produce `LIFECYCLE_INVENTORY_INCONSISTENT` and block all mutation.

## Operation routing and contracts

- `REGISTER_BASE_DOCUMENT` is composition-owned registration for a known complete base source. It does not infer a base from a managed filename. The fixed CREDA source can be registered only by supplying its complete bytes and hash as an explicit base-registration input.
- Scientific materialization calls `CREATE_FROM_BASE` for the first revision and `CREATE_SUCCESSOR` thereafter. The public scientific route remains the approval boundary; direct lifecycle create calls are not exposed as a generic unguarded write API.
- `WITHDRAW_REVISION` resolves a revision ID first. A compatibility `sourceFilename` is only a locator lookup and must resolve uniquely to an active lifecycle revision. The registered base and first materialization return `REVISION_NOT_WITHDRAWABLE` without writing a withdrawal record.
- `RESTORE_WITHDRAWN_REVISION` requires `withdrawalOperationId` as the persistent `withdrawalId`; filenames are classification-only and are never used to locate a withdrawal. Without a valid persistent ID, a known base yields `BASE_DOCUMENT_NOT_RESTORABLE`, a known non-withdrawn revision yields `REVISION_NOT_WITHDRAWN`, and every other reference yields `WITHDRAWAL_IDENTITY_NOT_FOUND`. `WITHDRAWAL_NOT_FOUND` is removed from the semantic public projection.
- `RESOLVE_ACTIVE_REVISION` and deliberation use the rebuilt inventory and return explicit absence in `WITHDRAWN_ONLY`; neither consults filename ordering.

The public result keeps the existing compact lifecycle shape for compatibility but adds stable `revisionId`, `withdrawalId`, `baseDocumentId`, lifecycle state, and correlation/request ID where applicable. It reports semantic error codes as structured codes, with no fallback to generic filename-derived classification.

## Compatibility and fail-closed behavior

The lifecycle-v1 marker is the compatibility boundary. Existing `.paper-proposal-v2/withdrawn` data and public `r01/r02` files may be inspected only to produce diagnostics or to verify a separately migrated record; they do not create stable IDs, active state, or base lineage automatically.

For a workspace without valid v1 authority:

- lifecycle inventory reports an explicit compatibility/inconsistency diagnostic and does not synthesize an active revision;
- semantic create, successor, withdraw, and restore do not mutate legacy files;
- restore requires a persistent withdrawal ID; absent IDs may still classify an obvious registered base, known non-withdrawn revision, or unresolved reference with the required explicit semantic errors, but never search withdrawal records by filename;
- a legacy generic `WITHDRAWAL_NOT_FOUND` can remain only in an isolated deprecated adapter response, never in the semantic contract or new public lifecycle result.

This preserves the proposal's no-migration scope and prevents a rename, missing locator, or highest-numbered public file from becoming silent authority.

## Structured operational evidence

Every attempt records a bounded lifecycle event/transition payload containing: schema version, operation, workspace ID, request/correlation ID, stable entity IDs, source/result hashes, prior and resulting lifecycle states, outcome (`committed`, `already_committed`, `rejected`, `recovery_required`, `inconsistent`), semantic code, and audit/self-audit statuses. Content, prompts, patch text, and absolute paths are excluded.

`runtime-metrics.ts` aggregates operation/outcome counts only. Public responses expose a capped audit-evidence list and correlation IDs sufficient to diagnose recovery without leaking internal file layout.

## Focused test seams

1. **Lifecycle store/service unit tests:** deterministic ID/clock/filesystem fixtures for one-time base registration, immutable hashes, stable IDs independent of locator, exact lineage, request/result idempotency, and conflicting retry rejection.
2. **Materialization tests:** base-to-`CREATE_FROM_BASE` preserves untouched base content and rejects metadata-only input; successor requires resolved active revision ID/hash and atomically supersedes its source.
3. **Inventory/restart tests:** fresh service instances reconstruct active, superseded, withdrawn, and base records; test `WITHDRAWN_ONLY`, multiple-active, orphan withdrawal, hash mismatch, and broken lineage as fail-closed.
4. **Withdrawal/restore tests:** active withdrawal clears the pointer without predecessor promotion; restore succeeds only by persistent withdrawal ID; a filename, including one that formerly matched a withdrawal, cannot restore; base, active/non-withdrawn, and unresolved filename return their specific codes and never `WITHDRAWAL_NOT_FOUND`.
5. **Projection fault tests:** inject failures before/after public projection and commit marker, then verify either the prior state, the committed reconstructed state, or `RECOVERY_REQUIRED`—never a partial success.
6. **Routing and entry tests:** lifecycle requests bypass model/document edit paths; real inventory feeds `ProjectEntryResolver`; read-only deliberation observes base/active or `WITHDRAWN_ONLY` without mutation.

Update the existing lifecycle, scientific-entry, scientific-materialization, and restart-persistence test suites; add one dedicated lifecycle-v1 persistence fixture suite rather than expanding filename-era fixtures indefinitely.

## Rollout and recovery

1. Land lifecycle types, store/service, deterministic reconstruction, and tests behind the v1 record boundary; do not alter existing proposal state.
2. Switch new explicitly registered workspaces and scientific materialization to lifecycle-v1. Verify committed transition/reconstruction evidence in tests before enabling lifecycle mutation routing.
3. Change inventory, project entry, lifecycle public projection, and restore classification to lifecycle-v1 authority. Keep legacy workspaces fail-closed and diagnostic-only until a separately approved migration change exists.
4. On operational failure, preserve immutable records and transition evidence. Recovery rebuilds projections only from a valid committed marker; contradictory evidence remains visible as `INCONSISTENT` and requires explicit repair.

No source, runtime state, proposal documents, or tests are changed by this design phase.
