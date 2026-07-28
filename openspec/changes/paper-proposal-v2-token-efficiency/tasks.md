# Tasks: Paper Proposal V2 Token Efficiency

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 280–420 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR, with measurement scaffolding isolated as a removable slice |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

## Scope Guard

This TASKS phase writes planning artifacts only. It does not modify production code, tests, configuration, proposal documents, or measurement fixtures. The implementation must preserve internal publication evidence and all existing verification, receipt, audit, SelfAudit, recovery, and exact-block guarantees.

## Ordered implementation tasks

### 1. Inventory and freeze the public result contract

- **Production targets:** `.pi/extensions/proposal-workspace.ts`; `paper-proposal-v2/orchestrator.ts`.
- **Test target:** `paper-proposal-v2/orchestrator.public-envelope.test.ts`.
- **Work:** Trace the currently serialized success and error results, identify callers that consume broad fields, and define explicit compact success/error types. Keep receipt, manifest/publication outcome, consistency-audit status, SelfAudit status, recovery state, next-action guidance, operation, and status. Exclude managed bytes, compiled candidate bytes, derived document state, workspace read details, planner context, and verification internals from normal public serialization.
- **Verification:** Contract tests assert stable success/error keys and assert excluded internal structures are absent from serialized output. Existing compatibility consumers are either updated explicitly or recorded as blocked before implementation.
- **Acceptance mapping:** Proposal scope 1; business rules 1, 4, and 5; success criteria 1 and 2.
- **Rollback boundary:** Revert only the public adapter/type mapping; retain the internal execution and verification result unchanged.

### 2. Separate internal evidence from the compact public response

- **Production targets:** `paper-proposal-v2/orchestrator.ts`; `paper-proposal-v2/proposal-workspace-adapter.ts`; `.pi/extensions/proposal-workspace.ts`.
- **Test target:** `paper-proposal-v2/orchestrator.public-envelope.test.ts`.
- **Work:** Preserve `publishedBytes` and workspace evidence through candidate/publication equality, source reread/hash checks, guard completion, derived-state rebuild, receipt creation, consistency audit, SelfAudit, and recovery handling. Redact only at the final public boundary, including typed validation, publication, recovery, audit, model, and budget-block errors.
- **Verification:** Instrumented tests prove internal bytes remain available until every dependent check completes, while the returned JSON contains only the compact envelope. Failed or incomplete SelfAudit never maps to apparent success.
- **Acceptance mapping:** Proposal scope 1 and non-goals; success criteria 1 and 2; rollback requirement.
- **Rollback boundary:** Restore the previous response-shaping adapter without removing internal evidence retention.

### 3. Define the exact-MODIFY fidelity payload

- **Production targets:** `paper-proposal-v2/intent-resolver.ts`; `paper-proposal-v2/context-builder.ts`; `paper-proposal-v2/edit-planner.ts`; `paper-proposal-v2/production-planner-adapter.ts`; `paper-proposal-v2/production-runtime.ts`.
- **Test target:** `paper-proposal-v2/exact-modify-planner-payload.test.ts`.
- **Work:** Add a fidelity-specific planner input for exact-block semantic `MODIFY`. Include target identity, replacement text, document identity, required local correctness context, and the single replace-action constraint. Ensure target and replacement blocks occur exactly once each in the payload and remove duplicated instruction/fidelity/composite representations without changing unrelated operation payloads.
- **Verification:** Serialized payload tests count target and replacement occurrences, assert no session-history field/source is consulted, require one replace action, and retain byte-for-byte matching and non-broadening behavior.
- **Acceptance mapping:** Proposal scope 2 and 3; business rule 3; success criteria 3, 4, and 7.
- **Rollback boundary:** Disable the fidelity payload builder and restore the prior exact-MODIFY payload construction; unrelated operations remain untouched.

### 4. Narrow exact-MODIFY local context without weakening resolution

- **Production targets:** `paper-proposal-v2/context-builder.ts`; `paper-proposal-v2/production-planner-adapter.ts`.
- **Test target:** `paper-proposal-v2/exact-modify-context.test.ts`.
- **Work:** Define the bounded local context required for exact-block fidelity operations, retaining target identity, document SHA, and correctness-critical context while excluding unnecessary neighboring/fragments data. Do not use session history as fallback or implicit context.
- **Verification:** Boundary fixtures show deterministic context construction, target resolution still succeeds, and context remains local and within the documented bound. Existing non-MODIFY context behavior is unchanged.
- **Acceptance mapping:** Proposal scope 3; risks on planner correctness and session-history independence; success criteria 3 and 7.
- **Rollback boundary:** Revert only fidelity-context narrowing and retain the compact public envelope independently.

### 5. Add deterministic MODIFY budget configuration and pre-invocation blocking

- **Production targets:** `paper-proposal-v2/production-planner-adapter.ts`; `paper-proposal-v2/production-runtime.ts`; the repository's existing runtime configuration module discovered by the implementation phase.
- **Test target:** `paper-proposal-v2/modify-budget.test.ts`.
- **Work:** Add a documented MODIFY input budget with one explicit accounting unit and deterministic accounting function. Validate configuration and safe default deterministically. Account for the complete planner input before model invocation; return a typed budget-block result when over limit; expose only effective-budget/accounting metadata in compact metadata. Never use model clarification or session history to bypass a block.
- **Verification:** Tests cover invalid configuration, below-limit, exact-boundary, and over-limit requests. Over-limit requests make zero model calls; allowed exact-MODIFY requests make at most one.
- **Acceptance mapping:** Proposal scope 3; business rules 3, 4, and 6; success criteria 4 and 5.
- **Rollback boundary:** Raise or disable the threshold only through documented configuration, without bypassing accounting or invoking an over-budget request.

### 6. Add P0 measurement and non-regression evidence

- **Production/measurement targets:** `paper-proposal-v2/measurement/modify-token-efficiency.ts` (temporary, removable); `.pi/extensions/proposal-workspace.ts` only if the measurement hook requires an explicit diagnostic boundary.
- **Test targets:** `paper-proposal-v2/token-efficiency.measurement.test.ts`; `paper-proposal-v2/non-regression.test.ts`.
- **Work:** Capture baseline/post-change response size or token footprint, exact-MODIFY planner input size and occurrence counts, model invocation count, budget-block behavior, envelope shape, and measurable latency. Keep instrumentation out of proposal documents and production semantics, clearly mark it removable, and record instrumentation-on/off comparison evidence.
- **Verification:** Measurement fixtures demonstrate intended public/input reduction and negative evidence for no-call budget blocks and no session-history dependency. Non-regression coverage verifies publication equality, source/hash checks, guards, receipts, derived-state rebuild, consistency audit, SelfAudit, recovery, exact-block semantics, and unaffected operations.
- **Acceptance mapping:** Proposal scope 4; non-goals; success criteria 6 and 7; measurement-distortion mitigation.
- **Rollback boundary:** Remove the temporary measurement module and its test-only hooks without changing proposal content or correctness behavior.

### 7. Document compatibility, configuration, and operational rollback

- **Production/documentation targets:** the existing runtime configuration documentation target discovered during implementation; `openspec/changes/paper-proposal-v2-token-efficiency/spec.md` and `design.md` only if the planning workflow later authorizes updates.
- **Test target:** `paper-proposal-v2/public-envelope.compatibility.test.ts`.
- **Work:** Record the compact envelope compatibility decision, migration of affected callers, budget unit/default/validation rules, effective metadata, and release rollback procedure. Do not silently remove fields or change managed proposal documents.
- **Verification:** Compatibility tests cover callers that previously inspected broad result fields; configuration documentation matches the accounting implementation and rollback can restore the prior adapter path without losing readable receipts.
- **Acceptance mapping:** Proposal scope 1 and business risks; business rule 6; rollback and success criteria.
- **Rollback boundary:** Revert documentation and compatibility adapter changes independently from planner and measurement work.

## Completion criteria

- All seven tasks have implementation evidence and focused tests at the listed targets.
- Compact success and error envelopes are stable and do not serialize broad internal evidence.
- Internal evidence survives every required publication, audit, SelfAudit, receipt, derived-state, and recovery check.
- Exact-MODIFY payloads deduplicate target/replacement content, use bounded local context, and do not consult session history.
- Over-budget exact-MODIFY requests are typed pre-invocation blocks with zero model calls; permitted requests use at most one call.
- P0 measurements and non-regression evidence demonstrate the intended reduction without changing proposal document content.
- No production modification is performed during this TASKS phase; the artifact produced here is only `openspec/changes/paper-proposal-v2-token-efficiency/tasks.md`.

## Phase note

The requested read scope excluded the design artifact, so these tasks are grounded only in the approved proposal and exploration findings. The implementation phase should reconcile the listed expected test/configuration paths with the repository's established locations before editing.