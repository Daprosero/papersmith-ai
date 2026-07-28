# Technical Design: Safe Managed Revision Withdrawal

## Overview

Add lifecycle operations `WITHDRAW_REVISION` and `RESTORE_WITHDRAWN_REVISION` to Paper Proposal V2. They are distinct from content-edit operations: withdrawal only acts on a managed revision's lifecycle artifacts, never produces a document patch, never calls the semantic runtime for an explicit filename, and never falls back to `DELETE`.

The implementation stays under `.pi/extensions/paper-proposal-v2/` plus the public tool projection in `.pi/extensions/proposal-workspace.ts`. Tests use isolated temporary roots only.

## Existing seams and constraints

- `resolveIntent()` in `intent-resolver.ts` is the current classifier and `PaperProposalV2Orchestrator.execute()` is the single V2 dispatcher.
- The orchestrator currently validates `sourceFilename` before loading document state, and `latest()` derives the published latest view by scanning `proposals/` for managed `rNN` files. There is no independent latest-pointer file.
- A committed revision's public artifacts are:
  - `proposals/<filename>`;
  - `.paper-proposal-v2/state/<filename>.json`, whose embedded `manifest` is the derived-state manifest; and
  - `.paper-proposal-v2/receipts/<filename>.json`.
  There is no separate manifest file today. The transaction must carry the whole state file as the manifest-bearing artifact rather than invent a parallel public manifest.
- `derived-state-store.ts` already owns state/receipt paths and identity validation primitives. `consistency-audit.ts` currently audits public proposals plus those two stores; it must understand quarantined revisions rather than report their intentionally absent public state as orphans.
- The public tool currently runs the orchestrator under `ProductionModelRuntime.withContext()` and projects generic publish results after a second audit pass. Lifecycle operations need a no-runtime direct branch and their own strict response projector.

## Public operation and dispatch design

### Types and profiles

Extend `Intent` with `WITHDRAW_REVISION` and `RESTORE_WITHDRAWN_REVISION`. Add lifecycle request fields to `V2Request`:

- `withdrawalOperationId?: string` for restoring a known quarantine operation;
- `withdrawalReason?: string` (optional user-supplied reason, normalized to a bounded string before writing metadata).

Add both intents to `operationSpec` and `role-budget.ts` with zero model, planner, role-authorization, patch, and content-mutation budgets. Their effective profile is lifecycle-specific, not `DELETE`-derived.

Add lifecycle result types and a single response-field allowlist:

```ts
type RevisionLifecycleResult = {
  status: 'withdrawn' | 'restored' | 'blocked';
  operation: 'WITHDRAW_REVISION' | 'RESTORE_WITHDRAWN_REVISION';
  withdrawnFilename: string | null;
  restoredLatestFilename: string | null;
  artifactCount: number;
  backupLocation: string | null;
  auditStatus: 'PASS' | 'WARN' | 'FAIL' | 'NOT_RUN';
  selfAuditStatus: 'PASS' | 'WARN' | 'FAIL' | 'NOT_RUN';
  warnings: string[];
};
```

The public projector returns exactly these keys for successful lifecycle results (and the same shape with safe nulls/status for a blocked lifecycle request). It does not leak generic patch fields, receipts, SHA values, operation IDs, or runtime metrics.

### Classification precedence

In `resolveIntent()`, classify lifecycle language before the existing destructive-keyword branch:

1. Detect restore language plus either an explicit managed filename or an explicit withdrawal operation ID, yielding `RESTORE_WITHDRAWN_REVISION`.
2. Detect withdrawal/retirement of a managed revision: verbs such as `retira`, `retirar`, `retire`, `withdraw`, `retire revision`, or `remove revision`, coupled with either a managed filename or an unambiguous `rNN` revision reference, yielding `WITHDRAW_REVISION`.
3. Continue into the existing MOVE/COPY/DELETE/etc. rules.

The lifecycle predicate must require a revision-lifecycle referent; `elimina esta sección`, including an existing resolved content target, remains `DELETE`. A withdrawal match never supplies `DELETE` as a secondary candidate or recovery fallback.

For an explicit `sourceFilename`, `execute()` branches immediately after deterministic filename syntax validation and lifecycle-intent classification, before `stateLoader`, target resolution, `buildContext`, planner selection, tutor/reviewer code, or any `modelCall`. The branch returns zero model/planner calls and performs no runtime model work. Semantic `r02` withdrawal may use deterministic filename resolution from the root lineage only; ambiguous references block rather than invoke a model.

In `proposal-workspace.ts`, call the lifecycle branch directly, outside `productionRuntime.withContext()`, when the deterministic pre-classification is a lifecycle operation. Non-lifecycle calls retain the existing runtime wrapper. This ensures explicit filename withdrawal causes no runtime model, planner, tutor, reviewer, or product/subagent call, not merely zero reported metrics.

## Artifact discovery and identity validation

Introduce `revision-lifecycle-store.ts` as the filesystem authority. It exposes `discoverManagedRevision`, `validateWithdrawalEligibility`, `findWithdrawal`, and narrow path constructors. It uses only normalized basenames and existing managed filename regexes; no user-controlled path segment is joined into a filesystem path.

`discoverManagedRevision(root, filename)` reads the document, state JSON, and receipt JSON without modifying them and returns a fixed artifact set:

```text
proposals/<filename>
.paper-proposal-v2/state/<filename>.json
.paper-proposal-v2/receipts/<filename>.json
```

Validation is fail-closed and completes before transaction creation:

1. The document is a regular, marker-owned managed file and its parsed revision is `r02` or later. `r01` and base forms return `BASE_REVISION_WITHDRAWAL_BLOCKED`.
2. State and receipt both exist and parse. State is `COMMITTED`, passes `validateStoredState`, names the exact filename/revision, and its manifest SHA equals the document SHA.
3. Receipt has `targetFilename === filename`, `targetRevision === revision`, `documentShaAfter === documentSha`, `derivedStateStatus === 'COMMITTED'`, and its source revision/filename are internally coherent.
4. The previous revision in the same lineage exists as a marker-owned regular file. For `r02`, that is `r01`; for later revisions it is `r(N-1)`. The previous document's SHA is not inferred from missing data.
5. Scan public managed filenames in the same lineage. Any later revision whose receipt has `sourceRevision === targetRevision` (or whose exact immediate predecessor is the target under the current linear successor contract) blocks with `LATER_DEPENDENT_REVISION_EXISTS`. Conservatively block on unreadable/malformed later receipts rather than assuming independence.
6. Reject any existing withdrawal directory with the requested operation identity unless it is a valid completed transaction being addressed by restore.

No missing state, receipt, manifest fields, source, or SHA is rebuilt, repaired, or inferred during this flow.

## Quarantine layout and transaction

Quarantine is rooted at `.paper-proposal-v2/withdrawn/<operation-id>/`. `operation-id` is generated internally with `randomUUID()` and accepted for restore only after strict UUID/path-segment validation. The final layout is:

```text
.paper-proposal-v2/withdrawn/<operation-id>/
  metadata.json
  artifacts/
    proposals/<filename>
    state/<filename>.json
    receipts/<filename>.json
```

`metadata.json` is written atomically and includes schema version, operation ID, operation timestamp, requested filename, revision, document SHA-256, source revision, source filename, reason, immutable artifact inventory (relative path + SHA-256), and pre-withdrawal/latest filename. It never substitutes for the original state or receipt.

Implement `RevisionLifecycleTransaction` in `revision-lifecycle-transaction.ts`. It receives a root, operation ID, fixed artifact inventory, and injected filesystem/audit dependencies. It serializes a lifecycle operation with `withMutationLock` using a lifecycle-specific key covering root and filename.

Withdrawal protocol:

1. Run complete discovery/identity/dependency validation.
2. Create a sibling staging directory under `.paper-proposal-v2/withdrawn/.staging-<operation-id>` and write verified metadata plus staged copies of all three artifacts. Copy/write uses temp files plus rename; never `unlink`, `rm`, `rm -r`, or a DELETE operation.
3. Verify every staged artifact SHA against the captured inventory and atomically rename staging to the final operation directory. The final quarantine is now a durable recovery copy.
4. Hide each public exclusive artifact by renaming it to a transaction-local `public-backup/` subtree under the final withdrawal directory, retaining its original relative layout. The staged `artifacts/` copy remains the immutable restore source. The implementation records every successful rename in reverse order.
5. Recompute `latest()` from the remaining public managed files. Since latest is scan-derived, no pointer file is changed; the effective latest becomes the highest remaining revision, normally the validated prior source.
6. After every public artifact rename succeeds and before either audit runs, atomically write the operation's `audit-marker.json` with `state: "PENDING_AUDIT"`, operation identity, immutable inventory digest, and the expected public/quarantine artifact placement. Construct the bounded audit context defined below and pass that exact context to `runPaperProposalV2SelfAudit`; SelfAudit must propagate it unchanged to `runConsistencyAudit`.
7. Success requires complete `PASS` results from both audits. Atomically replace `audit-marker.json` with `state: "COMMITTED"` and the two `PASS` outcomes. `WARN`, `FAIL`, thrown errors, incomplete audit objects, or marker-finalization failure are transaction failures.
8. On any failure after step 2, reverse public renames, remove every transaction-created pending/committed audit marker and only transaction-created staging/final quarantine directories through an internal rollback helper (never a user-facing DELETE fallback), then re-check that the public artifact snapshot and latest scan equal the pre-transaction snapshot. Return blocked recovery evidence, never a successful lifecycle response.

The rename sequence is not inherently multi-file atomic, so the transaction's atomicity contract is observable atomicity: all mutations are lock-protected, journaled, and rolled back before the operation returns. Rename remains within the same project root/filesystem; a cross-device rename fails and follows rollback.

## Restore protocol

`RESTORE_WITHDRAWN_REVISION` requires a valid operation ID (or a unique filename-to-withdrawal lookup; otherwise block). It loads and validates `metadata.json` and the immutable `artifacts/` inventory before mutation:

- metadata schema, operation ID, filename, revision, source revision, and SHA are consistent;
- all three artifacts exist, are regular files, and hash exactly to inventory;
- the state and receipt identities agree with metadata and document bytes;
- public destinations do not exist. Existing/conflicting public artifacts block; restore never overwrites them.

A restore transaction stages copies of the immutable artifacts in `.paper-proposal-v2/withdrawn/.restore-staging-<operation-id>`, verifies them, then renames the staged files into their public locations. It retains the original `artifacts/` and `metadata.json` in quarantine after success, satisfying recovery availability.

**Restore ordering is transactionally marker-first:** after every public rename succeeds and before either audit runs, the transaction atomically writes `audit-marker.json` in the operation directory with the operation ID, immutable inventory digest, restored filename/revision/SHA, expected placement, and `state: "PENDING_AUDIT"`. This is an in-flight transaction marker, not a success receipt. The transaction then recomputes the scan-derived latest view and calls `runPaperProposalV2SelfAudit` with the bounded audit context below; SelfAudit propagates it to ConsistencyAudit. Both results must be complete `PASS` results. Only then does it atomically replace the same marker with `state: "COMMITTED"` and the two audit outcomes. Marker finalization is part of the forward transaction: failure to write or replace it triggers rollback and cannot produce success.

If any move, marker write/finalization, publication/latest recomputation, consistency audit, or self audit fails, reverse every newly public rename, remove the transaction-created pending/committed audit marker and restore staging, and verify that the pre-restoration public snapshot/latest scan is restored. The original quarantine inventory and `metadata.json` remain untouched. Re-run both audits after rollback only for diagnostics; do not report restore success unless the forward audit pair passed and the committed marker was atomically written. Thus no partial public restoration, marker, or success receipt remains after a failed restore.

## Audit integration

### Bounded `PENDING_AUDIT` context contract

`runConsistencyAudit` currently accepts only `{ projectRoot }`, and `runPaperProposalV2SelfAudit` currently calls it with only that root. Extend both signatures with an optional, non-user-controlled `auditContext`; lifecycle transaction code is the only producer. SelfAudit MUST pass the same object, without rebuilding, widening, or dropping fields, to ConsistencyAudit:

```ts
type PendingAuditContext = {
  operationType: 'WITHDRAW_REVISION' | 'RESTORE_WITHDRAWN_REVISION';
  operationId: string;                 // strict UUID; equals directory and marker identity
  pendingAudit: true;
  phase: 'WITHDRAW_PUBLIC_ARTIFACTS_MOVED' | 'RESTORE_PUBLIC_ARTIFACTS_MOVED';
  temporarilyMovedArtifacts: Array<{
    publicRelativePath: string;        // one of the three fixed lifecycle paths
    sha256: string;                    // immutable inventory SHA
    expectedLocation: 'quarantine-public-backup' | 'public';
  }>;
  expectedMarker: {
    relativePath: string;              // withdrawn/<operationId>/audit-marker.json
    state: 'PENDING_AUDIT';
    inventoryDigest: string;
    expiresAt: string;                  // marker lease; ISO timestamp
  };
};
```

The transaction constructs this context only after all declared public moves and the atomic pending marker write succeed. It declares exactly the fixed document, state, and receipt inventory, each once; it does not grant directory-, glob-, filename-, or SHA-prefix tolerance. Its phase and every `expectedLocation` must match the operation type: withdrawal declares all three as `quarantine-public-backup`; restoration declares all three as `public`. `expectedMarker` must describe the actual marker bytes at the operation directory, including the same operation ID, inventory digest, and expiry. Set `expiresAt` to no more than 30 seconds after marker creation (`PENDING_AUDIT_LEASE_MS = 30_000`); the audit must compare against its own current clock and must not extend this lease. The context is ephemeral: it is never accepted from a public-tool request, persisted as an authority token, or reused after this audit call returns.

ConsistencyAudit retains all ordinary public document/state/receipt checks, then discovers and validates withdrawal directories, metadata, inventory hashes, and staging directories. It may suppress an otherwise failing public/quarantine pairing or duplicate finding ONLY when all of the following are true: a context is present; `pendingAudit === true`; the operation UUID is active in the current lifecycle transaction; the context and on-disk marker agree exactly; the marker is `PENDING_AUDIT`; the marker is nonexpired; the phase matches the observed placement; and the inconsistent path plus SHA is one of the three declared artifacts. “Active” means the transaction that created the context still owns the matching lifecycle mutation lock and has not completed, rolled back, or aborted. “Nonexpired” means the marker's `createdAt` is within the transaction's bounded audit lease; a missing, invalid, or elapsed lease is a failure, never an implicit renewal. The audit does not use lock ownership, operation ID, marker state, or a valid artifact inventory independently as authorization; all conditions are required.

Accordingly, ConsistencyAudit MUST fail (not warn) for: missing, unknown, aborted, inactive, or expired pending operations; absent, malformed, mismatched, or non-pending expected markers; an undeclared artifact or SHA; an incompatible SHA for a declared path; an orphan temporary/staging directory; a pending marker without its corresponding active operation; or a committed marker whose metadata, immutable inventory, final placement, or recorded `PASS` outcomes are invalid. A normal context-free audit always rejects `PENDING_AUDIT` markers and their temporary inconsistency. It must PASS after a successful final commit because the committed marker records both `PASS` audits and the final public/quarantine placement is valid, and after rollback because the pending marker and all temporary placement have been removed. A `COMMITTED` marker never supplies PENDING tolerance.

`runPaperProposalV2SelfAudit` continues to incorporate ConsistencyAudit; lifecycle code invokes SelfAudit with the bounded context inside the transaction rather than relying on the existing outer tool success-only audit hook. The public tool must not convert a lifecycle result to success after a failed audit.

## File changes

- `.pi/extensions/paper-proposal-v2/types.ts`: lifecycle intents, request/result/metadata types.
- `.pi/extensions/paper-proposal-v2/intent-resolver.ts`: precedence-safe lifecycle classification and deterministic revision extraction.
- `.pi/extensions/paper-proposal-v2/operation-spec.ts` and `role-budget.ts`: zero-call lifecycle profiles.
- `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts` (new): artifact paths, discovery, identity/dependency/quarantine lookup validation.
- `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` (new): injectable journaled staging/rename/rollback transaction and deterministic failure hook.
- `.pi/extensions/paper-proposal-v2/orchestrator.ts`: early lifecycle dispatch before any state/model/planner/role path; `withdrawRevision` and `restoreWithdrawnRevision` delegation.
- `.pi/extensions/paper-proposal-v2/consistency-audit.ts`: public plus quarantine lifecycle audit checks.
- `.pi/extensions/paper-proposal-v2/exports.ts`: export new lifecycle modules.
- `.pi/extensions/proposal-workspace.ts`: lifecycle tool parameters, direct no-runtime execution branch, and strict lifecycle response projection.
- `tests/paper-proposal-v2-revision-lifecycle.test.mjs` (new): isolated integration matrix.
- Existing classifier/public-tool tests: narrow regression assertions for operation registration, projection, and no-runtime invocation.

## Test strategy

All tests create roots with `mkdtemp(path.join(os.tmpdir(), ...))`, construct marker-owned `r01`/`r02` fixtures within that root, and inject adapters/filesystem hooks. Tests must not copy, rename, or write repository `proposals/`; include an assertion that the repository fixture path and its bytes are unchanged, and never target repository `research-concept-r02.md`.

Required cases:

1. explicit filename withdrawal classifies as `WITHDRAW_REVISION`, with spies proving zero runtime/model/planner/tutor/reviewer/subagent calls;
2. `elimina esta sección` with a resolved entry remains `DELETE`;
3. unambiguous semantic `retira la revisión r02` resolves to withdrawal without `DELETE` fallback;
4. r01/base blocks before staging or public mutation;
5. missing state/receipt, SHA/filename/revision mismatch, missing previous source, and malformed artifacts each block with byte-for-byte unchanged snapshots;
6. a later dependent revision blocks;
7. valid r02 withdrawal moves all three exclusive artifacts, writes complete metadata, exposes r01 as latest, and returns only the defined success fields with two `PASS` audits;
8. inject failure on the Nth rename/copy through the transaction filesystem dependency; assert public tree/latest snapshot equality and absence of final/staging quarantine after rollback;
9. inject `ConsistencyAudit` and `SelfAudit` failure after public hiding; assert the same rollback invariants;
10. restore a completed withdrawal and assert exact bytes for document/state/receipt, metadata retention, coherent latest, a `COMMITTED` audit marker with both audit outcomes, and both audit passes;
11. prove marker-before-audit ordering for both withdrawal and restoration: inject the SelfAudit call, assert it receives `operationType`, strict `operationId`, `pendingAudit: true`, exact three-artifact declaration, expected marker, and matching phase; assert SelfAudit passes that same context to ConsistencyAudit and that the inventory-bound `PENDING_AUDIT` marker exists before either audit; then assert atomic finalization only after both audits pass;
12. focused authorization tests: each independently blocks missing/unknown/aborted/expired operation, missing or mismatched marker, undeclared artifact, incompatible declared SHA, orphan staging/temporary directory, and marker without an active operation. Assert none downgrade to `WARN` or receive broad directory tolerance;
13. after successful commit, run a fresh context-free ConsistencyAudit and SelfAudit and assert `PASS`; after every rollback path, run the same context-free audits and assert `PASS` with no pending marker or temporary placement;
14. inject restore move, audit, and marker-finalization failures and assert no partial public artifacts or audit marker remain and the quarantine inventory/metadata remain intact.

Use a deterministic `FaultInjectingFs` test double (for example `{ failAtMove?: number }`) rather than timing, permissions, or platform-specific failures. Snapshot the relative tree and file SHA map before each operation to verify rollback precisely.

## Rollout and compatibility

The feature is additive: existing content `DELETE` behavior and successor publication remain unchanged. No migration is needed because no current quarantine directory exists. Introduce the quarantine audit support in the same change as lifecycle operations so a successful withdrawal is immediately auditable. Keep the generic projector for existing operations and select the lifecycle projector only for lifecycle intents. Roll back the release by disabling lifecycle dispatch; never delete existing quarantine directories.

## Risks

- The current system has no physical latest pointer; design treats latest as the existing scan-derived view. Adding a pointer would be unrelated scope and create another rollback surface.
- Filesystem rename cannot make a multi-file change kernel-atomic. The locked journal, staged verified copy, reverse rollback, and deterministic fault tests provide the required externally atomic behavior.
- The current audit considers every public revision and its receipt; lifecycle-specific audit rules are required to prevent intended withdrawal from appearing as a corrupt public state.
- The current public tool's `withContext()` wrapper would violate the no-runtime-call guarantee even if metrics stay zero; the lifecycle direct branch is therefore mandatory.
