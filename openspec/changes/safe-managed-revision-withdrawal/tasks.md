# Implementation Tasks: Safe Managed Revision Withdrawal

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 650–850 authored lines |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PENDING_AUDIT types/context and audit integration; PR 2 → lifecycle operations, transaction, public projection, and temporary-root tests |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

## Scope and work-unit boundary

Plan one bounded feature work unit, with implementation phases kept dependency-ordered. The work unit is limited to:

- `WITHDRAW_REVISION` and `RESTORE_WITHDRAWN_REVISION` public behavior.
- The minimum type/context changes required for the bounded `PENDING_AUDIT` contract.
- `SelfAudit` → `ConsistencyAudit` context propagation and quarantine-aware validation.
- Journaled quarantine/restore with rollback and strict public response projection.
- Tests using isolated temporary roots only.

Do not modify unrelated `DELETE` behavior, proposal content-edit behavior, role contracts, generic proposal infrastructure, or repository proposal fixtures. Do not edit `proposal.md` or the existing specification/design artifacts.

## Apply progress

### Chained slice 1 — bounded PENDING_AUDIT audit context

- [x] Define the strict, non-user-controlled `PendingAuditContext` contract and 30-second maximum lease.
- [x] Propagate the exact context object from SelfAudit to ConsistencyAudit while preserving context-free behavior.
- [x] Require an active operation under a held mutation lock and exact UUID, marker, phase, three-path inventory, placement, and SHA agreement.
- [x] Fail closed for inactive operations, undeclared artifacts, SHA mismatches, expired/mismatched markers, and orphan staging entries.
- [x] Validate finalized committed markers sufficiently for fresh context-free audit completion.
- [x] Cover valid active PENDING_AUDIT, no active operation, undeclared artifact, SHA mismatch, final normal audit, and injected-failure rollback normal audit under isolated temporary roots.
- [x] Correct fresh-context authorization validation: mint an opaque owner only while the exact lifecycle root/filename lock is held, require its operation/root/filename identity in `withActivePendingAuditOperation`, and prove an arbitrary active mutation lock cannot authorize the context.
- [x] Add lifecycle intent/request/result types, full metadata validation, withdrawal/restore transaction logic, public dispatch/projection, and the remaining slice-2 test matrix.

Verification evidence:

- `node --test tests/paper-proposal-v2-pending-audit.test.mjs tests/paper-proposal-v2-self-audit.test.mjs tests/paper-proposal-v2-consistency-audit.test.mjs` → PASS (11 tests, 0 failures).
- `node --test tests/paper-proposal-v2-*.test.mjs` → PASS (87 tests, 0 failures).
- `npx --no-install tsc --noEmit --allowJs false --module nodenext --moduleResolution nodenext --target es2022 .pi/extensions/paper-proposal-v2/types.ts .pi/extensions/paper-proposal-v2/consistency-audit.ts .pi/extensions/paper-proposal-v2/self-audit.ts` → NOT RUN (exit 1: no project-local TypeScript compiler; no dependency was installed). Jiti load/execution is covered by both passing test commands.
- Runtime harness: N/A; this slice exposes an internal filesystem audit seam and all scenarios run under `mkdtemp` roots without public Paper Proposal V2 execution.
- Rollback boundary: revert the new pending-audit types, ConsistencyAudit quarantine/context authorization, SelfAudit context plumbing, and the focused pending-audit test file. No proposal document or lifecycle transaction is involved.

Slice 2 verification evidence:

- `node --test tests/paper-proposal-v2-revision-lifecycle.test.mjs tests/paper-proposal-v2-pending-audit.test.mjs` → PASS (19 tests, 0 failures).
- `node --test tests/paper-proposal-v2-*.test.mjs` → PASS (98 tests, 0 failures; executed before the final path-hardening assertion was added, then superseded by the complete suite below).
- `node --test tests/*.test.mjs` → PASS (190 tests, 0 failures).
- `npx --no-install tsc --noEmit --allowJs false --module nodenext --moduleResolution nodenext --target es2022 ...` → NOT RUN (exit 1: no project-local TypeScript compiler; no dependency was installed). Jiti load and execution are covered by the passing focused and complete Node test suites.
- Runtime harness: lifecycle execution is covered through the registered `paper_proposal_v2_execute` tool in an isolated copied extension root; withdrawal and restoration both succeed with an invalid model context, proving the direct no-runtime branch. No model/planner/tutor/reviewer/subagent metrics or fields are produced.
- Isolation: pre/post SHA-256 inventories for repository `proposals/` and `.paper-proposal-v2/` are byte-identical. All lifecycle fixtures use `mkdtemp` roots and never target the repository `research-concept-r02.md`.
- Authored change estimate: approximately 920 added/deleted lines including focused tests and this evidence (the user approved the planned chained Slice 2 despite the original 400-line forecast).
- Rollback boundary: disable lifecycle dispatch, then revert the lifecycle store/transaction modules, lifecycle type/profile/classifier/orchestrator/public projection seams, quarantine metadata audit seam, focused tests, and this checkbox. Do not remove any completed withdrawal directory because quarantine data is recovery evidence.

## Ordered implementation tasks

### 1. Establish the lifecycle type and audit-context contract

**Files:**

- `.pi/extensions/paper-proposal-v2/types.ts`
- `.pi/extensions/paper-proposal-v2/consistency-audit.ts`
- `.pi/extensions/paper-proposal-v2/self-audit.ts` (or the existing module that exports `runPaperProposalV2SelfAudit`)

**Actions:**

- Add `WITHDRAW_REVISION` and `RESTORE_WITHDRAWN_REVISION` to the intent/request/result types.
- Add bounded request fields for restore operation identity and optional normalized withdrawal reason.
- Define the lifecycle response shape with only the nine public fields specified by the design/spec.
- Define `PendingAuditContext` as non-user-controlled, with strict UUID identity, exact three-artifact inventory, operation phase, expected marker, inventory digest, and ≤30-second lease.
- Extend SelfAudit and ConsistencyAudit signatures with the optional context without changing context-free callers.
- Ensure SelfAudit passes the exact same context object to ConsistencyAudit, without rebuilding or widening it.

**Verification:** Type-check the affected modules and add/prepare unit assertions that object identity and all context fields survive SelfAudit propagation unchanged.

**Rollback boundary:** Revert only the new lifecycle types/signature overloads/context plumbing; existing context-free audit behavior must remain unchanged.

### 2. Add quarantine-aware ConsistencyAudit and SelfAudit behavior

**Files:**

- `.pi/extensions/paper-proposal-v2/consistency-audit.ts`
- `.pi/extensions/paper-proposal-v2/self-audit.ts` (or the existing SelfAudit module)

**Actions:**

- Retain ordinary public document/state/receipt checks.
- Discover and validate withdrawal metadata, immutable artifact inventory, staging directories, public-backup placement, and audit markers.
- Permit temporary withdrawal/restore inconsistency only when every authorization condition is true: active lifecycle lock/operation, exact context-marker agreement, `PENDING_AUDIT`, nonexpired lease, matching phase, declared fixed path, and matching SHA.
- Fail closed—not warn—for missing/unknown/aborted/inactive/expired operations, malformed or mismatched markers, undeclared paths/SHA, incompatible inventory, orphan staging, and pending markers without an active operation.
- Validate committed markers, final placement, metadata, inventory, and recorded PASS outcomes in context-free audits.
- Ensure rollback removes temporary markers/directories so a fresh context-free audit passes.

**Verification:** Add focused audit tests for each authorization failure and for context-free PASS after commit and after rollback.

**Rollback boundary:** Remove only lifecycle quarantine recognition and PENDING_AUDIT authorization; preserve pre-existing audit findings and non-lifecycle audit semantics.

### 3. Implement managed revision discovery and eligibility validation

**Files:**

- `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts` (new)
- `.pi/extensions/paper-proposal-v2/derived-state-store.ts` (only where narrow existing identity/path primitives must be reused or exposed)
- `.pi/extensions/paper-proposal-v2/exports.ts`

**Actions:**

- Add normalized-basename path constructors for the fixed document, state, receipt, withdrawal, staging, marker, and metadata locations.
- Discover the target document/state/receipt without mutation and validate regular marker-owned files.
- Block base/r01, missing artifacts, malformed JSON, filename/revision/SHA mismatches, missing prior source, malformed later receipts, and later dependent revisions.
- Never infer or repair missing identity data; never accept user-controlled path segments beyond validated basenames/UUIDs.
- Provide strict lookup/validation of completed withdrawals for restoration.

**Verification:** Test discovery and block reasons against temporary fixtures before any transaction mutation.

**Rollback boundary:** Delete the new lifecycle store and exports, leaving existing derived-state paths and validation behavior intact.

### 4. Implement journaled withdrawal and exact restoration transactions

**Files:**

- `.pi/extensions/paper-proposal-v2/revision-lifecycle-transaction.ts` (new)
- `.pi/extensions/paper-proposal-v2/revision-lifecycle-store.ts`
- `.pi/extensions/paper-proposal-v2/consistency-audit.ts`
- `.pi/extensions/paper-proposal-v2/self-audit.ts` (integration seam only)

**Actions:**

- Implement lock-protected withdrawal using staged verified copies, atomic metadata writes, final quarantine rename, and public artifact renames into transaction-local `public-backup/` paths.
- Preserve the three immutable restore artifacts and complete `metadata.json`; do not unlink or irreversibly delete withdrawn content.
- Recompute scan-derived latest after public moves.
- Write `PENDING_AUDIT` marker before either audit, construct the exact bounded context only after marker creation, invoke SelfAudit, verify complete PASS results from both audits, then atomically finalize the marker as COMMITTED.
- Implement reverse-order rollback for move, marker, latest, audit, and finalization failures; remove only transaction-created temporary/final quarantine content and verify the pre-operation snapshot is restored.
- Implement restore from operation ID/validated unique lookup using immutable quarantine artifacts, refusing conflicting public destinations and retaining quarantine metadata/copies after success.
- Apply the same marker-first audit and rollback protocol to restoration.
- Add an injectable deterministic filesystem fault hook for Nth move/copy failure and injectable audit failures.

**Verification:** Exercise successful withdrawal/restore and move/audit/marker failure rollback using byte/SHA tree snapshots and latest-view assertions.

**Rollback boundary:** Disable lifecycle transaction dispatch and remove only transaction-created quarantine state; never delete pre-existing proposal artifacts or quarantine data.

### 5. Wire intent classification, orchestrator dispatch, and public projection

**Files:**

- `.pi/extensions/paper-proposal-v2/intent-resolver.ts`
- `.pi/extensions/paper-proposal-v2/operation-spec.ts`
- `.pi/extensions/paper-proposal-v2/role-budget.ts`
- `.pi/extensions/paper-proposal-v2/orchestrator.ts`
- `.pi/extensions/paper-proposal-v2/exports.ts`
- `.pi/extensions/proposal-workspace.ts`

**Actions:**

- Give restore precedence, then classify revision withdrawal before destructive keyword handling; require a managed filename or unambiguous `rNN` referent.
- Preserve `elimina esta sección` and other content-targeted requests as `DELETE`; never add a DELETE fallback for lifecycle matches.
- Add zero-call lifecycle operation profiles.
- Branch explicit filename lifecycle execution before state loading, target resolution, context building, planner/tutor/reviewer selection, or model calls; block ambiguous semantic references deterministically rather than invoking a model.
- Invoke lifecycle execution outside `ProductionModelRuntime.withContext()` while retaining the wrapper for non-lifecycle operations.
- Project exactly the defined lifecycle response fields, including safe blocked values; do not leak patch, receipt, SHA, operation ID, or runtime fields.

**Verification:** Classifier/orchestrator/public-tool tests prove operation registration, precedence, strict projection, and zero runtime/delegated calls for explicit filename withdrawal.

**Rollback boundary:** Remove lifecycle dispatch/projection and restore the prior classifier/public runtime path without changing existing content operations.

### 6. Add isolated temporary-root integration and regression tests

**Files:**

- `tests/paper-proposal-v2-revision-lifecycle.test.mjs` (new)
- Existing classifier/public-tool test files only for narrow regression assertions.

**Actions:**

- Build all fixtures under `mkdtemp(path.join(os.tmpdir(), ...))` with marker-owned r01/r02 (and dependent later-revision) files.
- Add deterministic coverage for:
  1. explicit filename classification;
  2. zero model/planner/tutor/reviewer/subagent/runtime calls;
  3. content deletion remains `DELETE`;
  4. semantic `retira la revisión r02` withdrawal;
  5. base/r01 blocking;
  6. missing/malformed/inconsistent artifact blocking;
  7. later dependent revision blocking;
  8. successful three-artifact quarantine, metadata, coherent latest, strict response, and both PASS audits;
  9. Nth move/copy failure rollback with no partial quarantine/public mutation;
  10. post-mutation ConsistencyAudit/SelfAudit failure rollback;
  11. marker-before-audit ordering and exact context propagation for withdrawal and restore;
  12. each PENDING_AUDIT authorization failure remaining FAIL, not WARN;
  13. fresh context-free audits after commit and every rollback;
  14. exact restoration plus move/audit/marker-finalization failure rollback with quarantine retained.
- Snapshot relative paths and SHA maps before every mutation.
- Assert the repository `proposals/` directory and its bytes are unchanged and never target/withdraw `research-concept-r02.md`.

**Verification:** Run the focused lifecycle test command and the existing Paper Proposal V2 regression suite; record exact commands/results in apply progress. Runtime harness boundary is `N/A` for isolated filesystem tests unless the repository exposes a dedicated runtime scenario.

**Rollback boundary:** Remove only the new lifecycle test file and narrow lifecycle assertions; no repository fixture or real proposal content may be reverted or modified.

## Completion criteria

- All ordered tasks are implemented in the single bounded work unit or explicitly split at the forecasted PR boundary before apply.
- Required public behavior, fail-closed validation, atomic rollback, marker/context audit contract, and exact restoration are covered.
- Focused and regression tests pass; temporary-root and real-fixture immutability assertions pass.
- Apply progress records test commands/results, runtime harness result or `N/A`, rollback boundary, and changed-line count.
