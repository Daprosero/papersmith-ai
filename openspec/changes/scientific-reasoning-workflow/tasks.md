# Tasks: Persistent Scientific Reasoning Workflow

Implement the approved design as ordered vertical slices. Preserve existing Paper Proposal V2 behavior by default; scientific workflow remains disabled unless explicitly enabled. No task may persist private reasoning, hidden prompts, raw model traces, or unrestricted transcripts.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1,250–2,100 authored lines across approximately 16–21 implementation/test files |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 → PR 5 → PR 6 → PR 7 → PR 8 → PR 9 → PR 10 → PR 11 → PR 12 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

## Chained PR Integration Invariant

Every chained PR is a non-negotiable integration boundary. Before that PR can be considered complete, it must:

- compile successfully;
- pass all applicable focused and existing regression tests, or record the exact repository-native manual verification and limitation when no runner is configured;
- keep `PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED` disabled by default;
- introduce no temporary compatibility debt, including duplicate domain models, transitional aliases, shims, TODO migrations, or parallel contract definitions; and
- preserve existing Paper Proposal V2 public behavior, including direct-document operations, `DELIBERATE`, lifecycle operations, manifests, receipts, audits, and recovery outcomes.

The invariant applies to PR1 and every subsequent chained PR. A PR that violates any item is not integration-ready and must not advance the chain.

## Delivery and review gates

- **Dependency rule:** complete each slice's implementation, tests, and acceptance evidence before starting the next slice. PR1 starts with T1.0, the canonical contract unit, and then proceeds through T1.1–T1.3. A later slice may consume only interfaces and persisted contracts verified by earlier slices.
- **Pause gate A:** after Slice 1, review the canonical contract module and repository-wide import ownership, route precedence, feature-flag default-off behavior, and Paper Proposal V2 compatibility before adding scientific state.
- **Pause gate B:** after Slice 4, review authoritative file layout, event atomicity, graph invariants, and recovery semantics before adding role orchestration.
- **Pause gate C:** after Slice 6, review the Tutor → Conceptual Reviewer repair bound and the no-publication invariant before adding decisions/materialization.
- **Pause gate D:** after Slice 9, review the publication boundary, receipt provenance, and idempotency evidence before final regression work.
- **Rollback:** disable `PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED` to stop new scientific entry/mutation without deleting scientific history or changing published documents. Existing lifecycle rollback remains governed by the current lifecycle transaction. Any partial scientific transition or materialization is retained as `BLOCKED` or `RECOVERY_REQUIRED`; recovery must reconcile validated records and never fabricate a decision, revision, receipt, causal link, or publication.
- **Testing capability:** `openspec/config.yaml` reports no detected test runner, lint command, or typecheck command. Use the repository's discovered Node/Jiti fixture conventions and document exact manual verification evidence for each task; do not claim automated execution where none exists.

## 1. Global routing and feature gate

### T1.0 — Establish the canonical shared scientific-domain contract
- [x] T1.0 — Establish the canonical shared scientific-domain contract
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/scientific-domain.ts` (new, sole contract owner), `.pi/extensions/paper-proposal-v2/types.ts`, `exports.ts`, and every approved scientific file listed in `design.md`'s affected-file plan.
- **Depends on:** none.
- **Implement:** create one canonical shared scientific-domain contract module used by the entire workflow. It must own and export at least `ScientificThread`, `ScientificDecision`, `ScientificEvent`, `ThreadRelation`, `ThreadSynthesis`, `ScientificAct`, and `ProjectEntryState`, plus their related identifiers, payloads, and all common scientific statuses/enums: workflow/public statuses, entry states, act kinds, thread statuses, decision statuses, event types, relation kinds, synthesis statuses, materialization states, actor kinds, review outcomes, resolution statuses, audit statuses, and operation discriminants. Use the approved design vocabulary and preserve versioned/allowlisted/privacy-safe shapes. Later tasks MUST import these contracts from `scientific-domain.ts`; they must not redeclare, alias, fork, or independently evolve equivalent scientific types, statuses, or enums in route, resolver, persistence, role, materialization, audit, or projection modules.
- **Tests:** add `tests/paper-proposal-v2-scientific-domain-contract.test.mjs` using the repository's Node/Jiti fixture conventions to verify the required contract exports, allowed status/enum values, version/privacy metadata, and module-load/compile compatibility. Add a static import/ownership assertion covering every later scientific implementation file so a duplicate declaration or non-canonical import fails; run it with the contract test before routing work begins.
- **Acceptance:** (1) `.pi/extensions/paper-proposal-v2/scientific-domain.ts` is the single source definition for every required shared scientific contract and common status/enum; (2) all required symbols named above are importable from that module; (3) downstream scientific files import those symbols rather than defining equivalents; (4) focused contract tests and the repository's available compile/module-load verification pass; (5) no temporary compatibility alias, duplicate model, or migration shim is introduced; and (6) the existing V2 public behavior and default-off flag behavior are unchanged. Rollback is limited to removing this contract unit and its focused tests before dependent scientific slices land.

### T1.1 — Add explicit scientific route types and outer admission
- [x] T1.1 — Add explicit scientific route types and outer admission
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/scientific-domain.ts`, `.pi/extensions/proposal-workspace.ts`, `.pi/extensions/paper-proposal-v2/types.ts`, `operation-spec.ts`, `exports.ts`.
- **Depends on:** T1.0.
- **Implement:** import the canonical scientific contracts from `scientific-domain.ts` and define only route-specific request/result wiring for the `SCIENTIFIC_WORKFLOW` discriminants, public statuses, and entry-state projection. Add the outer-only feature admission seam. Keep the route disabled by default and return `unavailable` when disabled; never reinterpret the request as a direct-document operation.
- **Tests:** extend `tests/paper-proposal-v2-scientific-routing.test.mjs` with explicit imports of the canonical contracts and cases for explicit mode, disabled mode, result shape, and no scientific component access while disabled.
- **Acceptance:** the public contract is explicit and typed; route types consume the canonical module without redeclaring scientific statuses/enums; disabled requests are explicit unavailable outcomes with no document/scientific mutation; existing result types remain source-compatible.
    
### T1.2 — Implement terminal route precedence
- [x] T1.2 — Implement terminal route precedence
- **Files/discovery:** `.pi/extensions/proposal-workspace.ts`, `intent-resolver.ts`, `.pi/extensions/paper-proposal-v2/orchestrator.ts`.
- **Depends on:** T1.1.
- **Implement:** add `GlobalRouteResolver` with terminal ordering lifecycle → direct document → `DELIBERATE` → scientific workflow, preserving existing first-three route behavior and avoiding scientific component construction on those paths.
- **Tests:** extend `tests/paper-proposal-v2-scientific-routing.test.mjs` and focused existing V2 routing suites for lifecycle/direct/`DELIBERATE` precedence, unchanged result shapes, and scientific-store access probes.
- **Acceptance:** recognized lifecycle/direct/`DELIBERATE` requests never enter scientific workflow; explicit scientific requests reach only stage 4; ambiguous requests clarify or retain existing behavior.

### T1.3 — Add route metrics and compatibility assertions
- [x] T1.3 — Add route metrics and compatibility assertions
- **Files/discovery:** `runtime-metrics.ts`, `.pi/extensions/proposal-workspace.ts`, existing V2 operation/lifecycle test suites.
- **Depends on:** T1.2.
- **Implement:** record route-stage selection and bypassed-stage metrics without changing existing public contracts or lifecycle inventory.
- **Tests:** verify metric deltas are privacy-safe and compatibility fixtures show unchanged direct operations, `DELIBERATE`, withdrawal, restore, manifests, receipts, locks, and audits.
- **Acceptance:** metrics contain no prompts/model output; all non-scientific routes have their previous observable contract and no scientific side effects.

## 2. ProjectEntryResolver

### T2.1 — Define conservative project-entry evidence and states
- [x] T2.1 — Define conservative project-entry evidence and states
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` (new), `.pi/extensions/paper-proposal-v2/types.ts`, current revision inventory/derived-state readers.
- **Depends on:** T1.3.
- **Implement:** resolve `EMPTY_PROJECT`, `SCIENTIFIC_ONLY`, `ACTIVE_PROPOSAL`, `ACTIVE_SCIENTIFIC_PROJECT`, `MATERIALIZATION_PENDING`, `WITHDRAWN_ONLY`, `INCONSISTENT_PROJECT`, and `MULTIPLE_ACTIVE_REVISIONS` from validated evidence before mutation. Do not infer or repair authoritative state.
- **Tests:** add `tests/paper-proposal-v2-scientific-entry.test.mjs` covering every state, including no active revision, one active proposal, scientific-only state, pending candidates, withdrawn-only history, and multiple active revisions.
- **Acceptance:** entry resolution is read-only, auditable, deterministic, and never creates `r01`, selects an ambiguous revision, or silently repairs state.

### T2.2 — Validate scientific evidence and conservative bootstrap
- [x] T2.2 — Validate scientific evidence and conservative bootstrap
- **Files/discovery:** `project-entry-resolver.ts`, existing proposal manifest/receipt/audit readers, `.paper-proposal-v2/scientific/` discovery target.
- **Depends on:** T2.1.
- **Implement:** consume a read-only scientific-state evidence port, validate schema/digests, event continuity, graph references, stale revision evidence, orphaned records, and transaction markers; support explicit bootstrap from exactly one verified active proposal as observations plus unknown-history markers only. The durable port implementation is wired in Slice 4.
- **Tests:** add corruption, stale-reference, orphan, conflicting-source, interrupted-transaction, and bootstrap-no-invented-history fixtures.
- **Acceptance:** invalid or ambiguous authoritative state returns `INCONSISTENT_PROJECT` or recovery guidance; bootstrap changes neither document bytes nor revision inventory and records no inferred history.

## 3. ScientificActResolver and ScientificThreadResolver

### T3.1 — Implement conservative scientific-act classification
- [x] T3.1 — Implement conservative scientific-act classification
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/scientific-act-resolver.ts` (new), `types.ts`, global route request projection.
- **Depends on:** T2.1.
- **Implement:** classify the approved act vocabulary, require agreement between caller-supplied act and instruction, preserve direct/lifecycle precedence, and return clarification/block outcomes for ambiguity.
- **Tests:** add `tests/paper-proposal-v2-scientific-act.test.mjs` for all act categories, caller disagreement, missing act ownership, ambiguous requests, and direct/lifecycle lookalikes.
- **Acceptance:** no ambiguous request is attached to a scientific act or thread; every resolved act is explicit and bounded.

### T3.2 — Resolve active thread ownership
- [x] T3.2 — Resolve active thread ownership
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/scientific-thread-resolver.ts` (new), `types.ts`, `scientific-state-store.ts` interface target.
- **Depends on:** T3.1.
- **Implement:** support deterministic create-from-seed, continue-active, explicit selection, direct-neighbor relation validation, and clarification/block outcomes against a read-only state-reader port. Never choose by recency, lexical order, revision identity, or model suggestion.
- **Tests:** add `tests/paper-proposal-v2-scientific-thread.test.mjs` for create, continue, select, multiple-thread ambiguity, invalid/stale/blocked thread, invalid relation, and no-role/no-document-write failure paths.
- **Acceptance:** every scientific act has one validated active thread or a clarification/block result; resolver failures leave no partial scientific event or document mutation.

### T3.3 — Define thread transition intents and persistence boundary
- [x] T3.3 — Define thread transition intents and persistence boundary
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/scientific-thread-resolver.ts`, `.pi/extensions/paper-proposal-v2/types.ts`, `ScientificStateStore` port.
- **Depends on:** T3.2.
- **Implement:** emit only the permitted thread creation, selection, activation, and explicit relation transition intents; preserve stable identities and bounded graph edges without embedding document behavior.
- **Tests:** use an in-memory store double to verify transition intent contents, causal inputs, direct-neighbor constraints, and the guarantee that unresolved/blocked results emit no write intent.
- **Acceptance:** the resolver has a reviewable persistence boundary; successful intents are sufficient for the later atomic store integration, and failed resolution cannot touch `proposals/` or receipts.

## 4. Scientific persistence and thread graph

### T4.1 — Establish authoritative scientific storage contracts
- [x] T4.1 — Establish authoritative scientific storage contracts
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/scientific-state-store.ts` (new), `.pi/extensions/paper-proposal-v2/scientific-domain.ts`, `types.ts`, `.paper-proposal-v2/scientific/manifest.json`, `snapshot.json`, `events/`, `materializations/`, `transactions/`, `projections/`.
- **Depends on:** T1.0 and T1.1.
- **Implement:** import the canonical thread, relation, event, decision, synthesis, act, status, and enum contracts from `scientific-domain.ts`; define only persistence-specific transaction/materialization/projection records that are not shared domain equivalents. Separate authoritative records from rebuildable projections and enforce allowlisted summaries/evidence and privacy metadata. Do not create a second storage-local version of any shared scientific contract.
- **Tests:** add `tests/paper-proposal-v2-scientific-persistence.test.mjs` for canonical-contract imports, schema validation, immutable IDs, privacy rejection, projection distinction, and path/symlink/regular-file safety.
- **Acceptance:** authoritative identities, versions, causal references, graph endpoints, and public-summary limits are explicit; all shared domain values resolve to `scientific-domain.ts`; private reasoning and raw traces are rejected.

### T4.2 — Implement atomic transitions, locking, and replay validation
- [x] T4.2 — Implement atomic transitions, locking, and replay validation
- **Files/discovery:** `scientific-state-store.ts`, existing mutation-lock/recovery conventions, `.paper-proposal-v2/scientific/transactions/`.
- **Depends on:** T4.1.
- **Implement:** implement recoverable write-ahead transitions with exclusive immutable event creation, atomic sibling rename, fsync/error handling, scientific locking, manifest/snapshot/index updates, and fail-closed replay validation.
- **Tests:** fault-inject every persistence boundary; cover duplicate/gapped/non-contiguous events, invalid causality, dangling relations, conflicting heads, partial markers, and restart recovery.
- **Acceptance:** restart exposes only validated committed state or explicit recovery; recovery never invents decisions, relations, revisions, receipts, or publication success.

### T4.3 — Add connected graph and scientific audit seams
- [ ] T4.3 — Add connected graph and scientific audit seams
- **Files/discovery:** `scientific-state-store.ts`, `scientific-audit.ts` (new), `consistency-audit.ts`, `self-audit.ts`.
- **Depends on:** T4.2.
- **Implement:** validate explicit bounded relationships, preserve thread identity across document lifecycle changes, and compose scientific consistency/self-audit without changing the existing three-artifact lifecycle inventory.
- **Tests:** cover relation integrity, withdrawn/restored/stale revision evidence, audit pass/warn/fail projections, and unchanged existing audit outputs.
- **Acceptance:** the graph is not reduced to a linear replay; scientific audit failures fail closed without weakening V2 lifecycle, manifest, receipt, lock, or recovery guarantees.

### T4.4 — Wire entry and thread resolvers to atomic scientific persistence
- [ ] T4.4 — Wire entry and thread resolvers to atomic scientific persistence
- **Files/discovery:** `project-entry-resolver.ts`, `scientific-thread-resolver.ts`, `scientific-state-store.ts`.
- **Depends on:** T3.3 and T4.2.
- **Implement:** replace the earlier read-only/in-memory ports with the validated authoritative store, commit thread transition intents atomically, and expose pending candidates and recovery markers to entry resolution.
- **Tests:** run resolver-to-store integration fixtures for create/select/activate/relation transitions, interrupted commits, replay, and no-document-write guarantees.
- **Acceptance:** entry and thread resolution use authoritative scientific records before mutation; every committed thread transition is atomic and every failed transition is recoverable or blocked without document mutation.

## 5. ScientificContextBuilder

### T5.1 — Build bounded active-thread context
- [ ] T5.1 — Build bounded active-thread context
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/scientific-context-builder.ts` (new), existing `context-builder.ts`, revision/document evidence readers.
- **Depends on:** T4.4.
- **Implement:** include the active thread, only explicitly selected valid direct neighbors, act-relevant evidence, and verified bounded document fragments; enforce count/byte caps and public redaction.
- **Tests:** add `tests/paper-proposal-v2-scientific-context.test.mjs` for unrelated-thread exclusion, transitive traversal rejection, full-document exclusion, cap behavior, evidence identity, and privacy filtering.
- **Acceptance:** Tutor/Reviewer input is selective, bounded, reproducible, and centered on the active thread; cap narrowing never widens context.

## 6. Tutor → Conceptual Reviewer → repair → synthesis loop

### T6.1 — Add advisory Tutor and Conceptual Reviewer orchestration
- [ ] T6.1 — Add advisory Tutor and Conceptual Reviewer orchestration
- **Files/discovery:** `.pi/extensions/paper-proposal-v2/scientific-workflow-service.ts` (new), existing Tutor/Reviewer adapters and `ProductionModelRuntime`, `scientific-context-builder.ts`.
- **Depends on:** T5.1.
- **Implement:** require Tutor first and Conceptual Reviewer second for every candidate synthesis; persist only allowlisted advisory/review events; prohibit both roles from acceptance, planning, editing, lifecycle, or publication authority.
- **Tests:** add `tests/paper-proposal-v2-scientific-synthesis.test.mjs` for call order, advisory authority negatives, valid/invalid role outputs, reviewer outcomes, and no document writes.
- **Acceptance:** no synthesis reaches user decision without conceptual review; favorable Tutor output never bypasses review or accepts a decision.

### T6.2 — Implement bounded structured repair/recheck
- [ ] T6.2 — Implement bounded structured repair/recheck
- **Files/discovery:** `scientific-workflow-service.ts`, `types.ts`, role adapter seams.
- **Depends on:** T6.1.
- **Implement:** persist structured findings, send finding ID/digest/category/evidence/constraints back to Tutor, re-review repaired candidates, and stop after two repair/recheck cycles with `REPAIR_LOOP_EXHAUSTED` or a specific block.
- **Tests:** cover pass, repair-required, repaired pass, second-cycle repair, third-cycle exhaustion, invalid critique linkage, missing adapter, and context rebuild failure.
- **Acceptance:** repair remains scientific-state-only, each candidate has a new digest and causal links, and there is no automatic acceptance or unbounded retry.

### T6.3 — Add synthesis modification/reopen flow
- [ ] T6.3 — Add synthesis modification/reopen flow
- **Files/discovery:** `scientific-workflow-service.ts`, `scientific-state-store.ts`.
- **Depends on:** T6.2.
- **Implement:** record `MODIFY_SYNTHESIS` as an immutable reopen event, preserve prior candidates/reviews/decisions, and require a new Tutor → Reviewer sequence for the revised synthesis.
- **Tests:** verify history preservation, new decision identity, renewed call order, and unchanged proposal/manifest/receipt/revision bytes.
- **Acceptance:** reopening cannot edit prior scientific history or documents and cannot make the prior decision eligible again.

## 7. Decisions and ACCEPTED_UNMATERIALIZED

### T7.1 — Implement explicit user decision lifecycle
- [ ] T7.1 — Implement explicit user decision lifecycle
- **Files/discovery:** `scientific-workflow-service.ts`, `scientific-state-store.ts`, `types.ts`.
- **Depends on:** T6.2.
- **Implement:** require exact reviewed-synthesis digest and user-only `ACCEPT_DECISION`; persist rejection, retraction, and modification transitions while preserving immutable history.
- **Tests:** add `tests/paper-proposal-v2-scientific-decisions.test.mjs` for accept, reject, retract, non-user acceptance attempts, stale digest, missing causal pass, and no-document-write guarantees.
- **Acceptance:** acceptance creates an immutable `ACCEPTED_UNMATERIALIZED` decision; rejection/retraction are not eligible; no decision act creates `r01` or a successor.

### T7.2 — Expose durable pending candidates on re-entry
- [ ] T7.2 — Expose durable pending candidates on re-entry
- **Files/discovery:** `project-entry-resolver.ts`, scientific public-result projection, `scientific-workflow-service.ts`.
- **Depends on:** T7.1.
- **Implement:** report pending candidate IDs, active/related thread summaries, eligibility/blockers, and next action as `MATERIALIZATION_PENDING` without claiming publication.
- **Tests:** re-enter after acceptance, restart, rejection, retraction, and blocked evidence; verify exact candidate/thread/decision identities.
- **Acceptance:** accepted eligible candidates remain visible and queryable across sessions; pending state never masquerades as materialized state.

## 8. Idempotent materialization

### T8.1 — Add frozen selection and materialization reservation
- [ ] T8.1 — Add frozen selection and materialization reservation
- **Files/discovery:** `materialization-planner.ts` (new), `scientific-state-store.ts`, `.paper-proposal-v2/scientific/materializations/`.
- **Depends on:** T7.2.
- **Implement:** accept only explicit sorted unique accepted decision IDs, derive stable exact-set selection keys, reserve claims under the scientific lock before mutable-head checks, and return exact retries or selection conflicts deterministically.
- **Tests:** add `tests/paper-proposal-v2-scientific-materialization.test.mjs` for exact retries, subset/superset/overlap conflicts, rejected/retracted decisions, duplicate IDs, and restart recovery.
- **Acceptance:** one accepted decision cannot be claimed by a second selection; retry never allocates a second materialization record or revision.

### T8.2 — Plan only frozen accepted candidates with provenance
- [ ] T8.2 — Plan only frozen accepted candidates with provenance
- **Files/discovery:** `materialization-planner.ts`, `types.ts`.
- **Depends on:** T8.1.
- **Implement:** map every materialized scientific claim to exactly one selected immutable user acceptance event and produce bounded `CREATE_R01` or `CREATE_SUCCESSOR` plans; reject unsupported, unmapped, stale, or budget-exceeding plans.
- **Tests:** cover provenance completeness, unrelated-thread exclusion, source mismatch, unsupported claim, and planner failure retaining `ACCEPTED_UNMATERIALIZED`.
- **Acceptance:** planner cannot invent claims, accept decisions, include unselected threads, or publish; every plan has frozen source and provenance evidence.

## 9. CandidateExecutor, Document Reviewer, and V2 publication

### T9.1 — Implement non-writing MaterializationCandidateExecutor
- [ ] T9.1 — Implement non-writing MaterializationCandidateExecutor
- **Files/discovery:** `materialization-candidate-executor.ts` (new), existing `compilePatches`, `validateCandidate`, initial-document compiler/validator seams.
- **Depends on:** T8.2.
- **Implement:** generate exact in-memory successor or `r01` candidates, candidate digests, provenance maps, and validation inputs without workspace handles, guard calls, manifest/receipt APIs, or filesystem writes.
- **Tests:** add `tests/paper-proposal-v2-scientific-candidate-executor.test.mjs` for successor and initial candidates, exact digest/provenance, compiler failure, validator failure, and filesystem mutation probes.
- **Acceptance:** executor is non-writing and cannot publish; all failures set materialization `BLOCKED` while preserving `ACCEPTED_UNMATERIALIZED`.

### T9.2 — Add Document Reviewer gate and guarded initial publication adapter
- [ ] T9.2 — Add Document Reviewer gate and guarded initial publication adapter
- **Files/discovery:** `materialization-candidate-executor.ts`, existing V2 Document Reviewer, `proposal-workspace-adapter.ts`, `.pi/extensions/proposal-workspace.ts:createInitialProposal`.
- **Depends on:** T9.1.
- **Implement:** require exact-candidate `APPROVE` before any guard/publication call; add backward-compatible guarded `publishInitial()` using `INITIAL_CREATE`/`createInitialProposal`; leave `publishSuccessor()` unchanged.
- **Tests:** verify reviewer non-pass blocks without writes, changed candidate invalidates approval, call order, guarded `r01` creation, minimal initial receipt, and unchanged successor callers.
- **Acceptance:** no proposal, manifest, receipt, or revision write occurs before exact review approval; initial and successor publication both use existing guarded V2 infrastructure.

### T9.3 — Commit materialization only after verified publication
- [ ] T9.3 — Commit materialization only after verified publication
- **Files/discovery:** `scientific-workflow-service.ts`, `proposal-workspace-adapter.ts`, `revision-receipt.ts`, `scientific-state-store.ts`.
- **Depends on:** T9.2.
- **Implement:** verify published bytes/hash, derived state, and receipt against the frozen record; then append `MATERIALIZATION_COMMITTED`, record revision/receipt/thread provenance, and mark selected decisions `MATERIALIZED` exactly once.
- **Tests:** cover successful `r01` and successor publication, pre-commit failure, ambiguous publication, incomplete derived/receipt evidence, and post-commit replay.
- **Acceptance:** only verified publication transitions decisions to `MATERIALIZED`; all uncertain outcomes remain retryable or recoverable and never claim duplicate publication.

## 10. Recovery, audit, and regression tests

### T10.1 — Complete recovery and diagnostic outcomes
- [ ] T10.1 — Complete recovery and diagnostic outcomes
- **Files/discovery:** `scientific-audit.ts`, `scientific-state-store.ts`, `scientific-workflow-service.ts`, existing recovery markers/audit paths.
- **Depends on:** T4.4 and T9.3.
- **Implement:** expose `BLOCKED`/`RECOVERY_REQUIRED` diagnostics, validated restart/retry actions, scientific metrics, and read-only diagnostic behavior after feature rollback.
- **Tests:** add recovery fixtures for every design failure condition, including corrupt authoritative files, interrupted transitions, publication ambiguity, stale revision evidence, and disabled-mode re-entry.
- **Acceptance:** recovery is fail-closed, auditable, privacy-safe, and never fabricates scientific or document state; rollback preserves history and published documents.

### T10.2 — Run compatibility and full regression coverage
- [ ] T10.2 — Run compatibility and full regression coverage
- **Files/discovery:** `tests/paper-proposal-v2-scientific-*.test.mjs`, existing V2 suites, `.pi/extensions/paper-proposal-v2/` exports and integration seams.
- **Depends on:** T10.1.
- **Implement:** add focused regression assertions for direct-document operations, `DELIBERATE`, lifecycle withdrawal/restore, manifests, receipts, audits, locks, recovery, feature default-off behavior, and privacy boundaries. Use repository-native Node/Jiti fixtures and record manual verification because no test runner is configured.
- **Tests:** execute every available focused fixture and existing V2 suite; where execution is unavailable, record the exact command, limitation, and manual evidence in the verification report.
- **Acceptance:** all existing V2 compatibility expectations remain unchanged; scientific workflow meets the specification scenarios and invariants; no implementation task is marked complete without evidence.

## Mandatory human review pause

**STOP before T1.1. A human must review and approve this task breakdown, the proposed vertical-slice boundaries, the `High` review-workload forecast, the approved stacked-to-main chain strategy, the rollback posture, and the explicit Paper Proposal V2 compatibility preservation. Do not begin implementation until that approval is recorded.**
