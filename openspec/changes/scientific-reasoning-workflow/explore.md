# Exploration: Scientific Reasoning Workflow

## Scope and evidence

This is a read-only implementation audit for `scientific-reasoning-workflow`. No source code, Paper Proposal V2 behavior, proposal content, proposal revisions, manifests, receipts, or tests were modified.

The injected project context reports that the Git root was not recognized and `.codegraph/` was missing; CodeGraph initialization also failed because the directory was not recognized as a CodeGraph project. Therefore this audit used targeted repository reads/searches after loading the injected skills. Engram was unavailable; this exploration is persisted only as the OpenSpec file requested by the parent.

Primary evidence inspected:

- `.pi/extensions/proposal-workspace.ts`
- `.pi/extensions/paper-proposal-v2/{orchestrator,intent-resolver,operation-spec,types,document-state,derived-state-builder,derived-state-store,context-builder,target-resolver,edit-planner,production-runtime,production-planner-adapter,production-tutor-adapter,production-reviewer-adapter,proposal-workspace-adapter,revision-lifecycle-store,revision-lifecycle-transaction,consistency-audit,self-audit,mutation-lock}.ts`
- `.pi/skills/paper-proposal/SKILL.md` and its usage/role contracts
- `proposals/research-concept-r01.md`
- `.paper-proposal-v2/` persisted state and withdrawn-revision artifacts
- focused V2 tests under `tests/`
- `openspec/project-context.md`, `openspec/config.yaml`, and prior V2 exploration artifacts

## Executive finding

The repository already has a conservative, single-entry Paper Proposal V2 workflow with three materially different routes:

1. **Read-only scientific assessment:** `DELIBERATE` invokes the tutor; `REVIEW` invokes the reviewer. Both resolve one bounded document target, return an assessment, and never publish.
2. **Document mutation:** content intents resolve a target, optionally invoke the planner or role chain, compile bounded patches, pass candidate validation and guarded successor publication, then persist derived state and a receipt.
3. **Managed revision lifecycle:** explicit or classified `WITHDRAW_REVISION` and `RESTORE_WITHDRAWN_REVISION` dispatch before document-state loading, target resolution, planning, roles, or model runtime. Lifecycle transactions quarantine/restore exactly three artifacts and require consistency/self-audit success.

The requested direction is feasible as an extension, but the current code has no first-class scientific-workflow state machine, project-entry state detector, scientific-event store, or explicit materialization command. The safest seams are the existing early routing point in `PaperProposalV2Orchestrator.execute`, the read-only `DELIBERATE`/`REVIEW` branches, the existing bounded context/index structures, and a new persistence boundary kept separate from `ProposalWorkspaceAdapter` mutation. The major unresolved product/architecture questions are the scientific state vocabulary, event schema, entry-state policy, materialization authority, and how a new scientific route should coexist with direct V2 requests without changing their current contracts.

## 1. Actual call map: Orchestrator, Planner, Tutor, Reviewer

### Production entry path

```text
paper_proposal_v2_execute
  .pi/extensions/proposal-workspace.ts:proposalWorkspaceExtension
    -> resolveIntent(params.instruction) for public operation classification
    -> ProductionModelRuntime.withContext(ctx, signal, ...)
    -> PaperProposalV2Orchestrator.execute({...params})
    -> projectPaperProposalV2PublicResult(...)
    -> optional runConsistencyAudit + runPaperProposalV2SelfAudit after published result
```

The extension constructs exactly one production orchestrator with one `ProposalWorkspaceAdapter`, one `ProductionModelRuntime`, the production semantic planner, and production tutor/reviewer adapters. It returns a compact public projection, while the internal orchestrator result contains substantially more evidence.

### Orchestrator routing

`PaperProposalV2Orchestrator.execute` in `.pi/extensions/paper-proposal-v2/orchestrator.ts` follows this concrete order:

1. `resolveIntent(request.instruction)`; an explicit `request.operation` overrides the classified intent.
2. If lifecycle intent, validate the managed filename, derive filename/revision/operation identity, and immediately call `RevisionLifecycleTransaction.withdraw` or `.restore`. This route returns before `loadDocumentState`, planner, tutor, reviewer, target resolution, or model calls.
3. Otherwise validate an explicit `sourceFilename` against the managed filename pattern, verify the file exists and begins with `<!-- proposal-workspace:artifact:v1 -->`, or call `latest()` to select the highest managed `rNN` proposal.
4. Call the injected `stateLoader`, normally `loadDocumentState(root, filename)`. A source SHA mismatch supplied by the caller returns `STALE_SOURCE_SHA`.
5. Return `ambiguous` before planning when intent is ambiguous, or when `ambiguityGate(resolveTargets(...))` finds no candidate or comparable candidates.
6. Route `DELIBERATE`/`REVIEW` to read-only role assessment.
7. Route `MOVE`/`COPY` through separate source/destination resolution and `buildMoveCopyPlan`.
8. Resolve and materialize the target for ordinary edit/conceptual routes, build bounded context, then route `CONCEPTUAL_REVISION` through the conditional tutor/planner/reviewer chain.
9. Route remaining intents through `buildEditPlan`; literal `INSERT` can inject `literalContent` without a model.
10. `publish` enforces profile/budget/unresolved-question/no-action gates, acquires `withMutationLock`, compiles patches, validates the candidate, calls the adapter, verifies publication bytes, rebuilds derived state, commits it, and saves a revision receipt.

### Planner route

- `edit-planner.ts:buildEditPlan` treats semantic `MODIFY` as planner-required and invokes `modelCall('planner', ...)` exactly once. The generic contract requires one `replace` action, the resolved target ID, and non-empty replacement text; exact-block MODIFY additionally requires byte-identical replacement text.
- `edit-planner.ts:buildMoveCopyPlan` invokes the planner once only for adaptive MOVE/COPY, and rejects invented source IDs, changed destination/position, multiple actions, or missing transformed content.
- `conceptual-planner.ts:buildConceptualPlan` asks the planner for bounded replace actions, limits the result to 1–3 actions, and returns a conceptual plan with scientific goal/assumptions/effects fields.
- `production-planner-adapter.ts:createProductionSemanticPlanner` is the production boundary. Exact fidelity MODIFY uses a required structured-output tool, allowlisted response/action keys, exactly one replace action, the resolved target ID, and exact replacement bytes. Non-fidelity planner responses are passed through to generic validation.
- `production-runtime.ts:ProductionModelRuntime.structured` is the only provider boundary. It serializes one payload, uses one provider completion, supports required tool output or JSON text, rejects provider/abort/empty/invalid structured responses, and serializes calls through a queue so parallel model calls never exceed one.

### Tutor route

- `tutor-adapter.ts` defines `TutorAssessment` and validates decisions plus `affectedEntryIds` against supplied context fragments.
- `production-tutor-adapter.ts:createProductionTutorAdapter` sends one bounded runtime request. The prompt forbids file access, hash/offset calculation, publication, and plan alteration.
- In `orchestrator.ts`, `DELIBERATE` invokes the tutor once and returns `status: 'deliberated'`, alternatives, risks, unresolved questions, and zero mutations.
- For mathematical `CONCEPTUAL_REVISION`, the tutor is called before the planner. `NEEDS_CLARIFICATION` and `REJECT_WITH_REASON` stop the route before the planner. The effective conceptual budget is at most two model calls.

### Reviewer route

- `reviewer-adapter.ts` defines `ReviewerAssessment` and validates the decision enum.
- `production-reviewer-adapter.ts:createProductionReviewerAdapter` sends one bounded request over the same runtime.
- `REVIEW` invokes only the reviewer and remains read-only.
- Conceptual revision invokes the reviewer only when `reviewerRequired(...)` returns true, based on explicit review language, high tutor risk, or high-risk/multiple-section conceptual language. For mathematical conceptual revisions, the orchestrator blocks `REVIEW_EXCEEDS_MODEL_BUDGET` rather than exceed the two-call limit.
- Reviewer `BLOCK` or `NEEDS_CLARIFICATION` prevents publication.

The Markdown files `.pi/subagents/paper-proposal-tutor.md` and `.pi/subagents/paper-proposal-reviewer.md` are manual/reference contracts. They are not dynamically loaded by the production runtime and do not guarantee invocation or select a model/profile/budget.

## 2. Responsibility matrix and exact extension seams

| Responsibility | Current implementation | Desired scientific-workflow responsibility | Exact seam / boundary | Current gap or constraint |
|---|---|---|---|---|
| User entry | `paper_proposal_v2_execute` in `proposal-workspace.ts` | Preserve direct V2 entry; optionally add a distinct scientific-workflow entry route | Extension registration and request projection; `PaperProposalV2Orchestrator.execute` first lines | No separate scientific entry command or entry-state result exists |
| Intent routing | `intent-resolver.ts:resolveIntent` | Add conservative scientific-act classification without changing direct V2 semantics | Pre-state route in `Orchestrator.execute`; `ResolvedIntent`/`Intent` types | Current vocabulary is content/lifecycle oriented; unknown requests become `AMBIGUOUS` with a generic clarification |
| Project entry detection | `latest()` plus managed filename/marker checks | Detect no-project, managed-project, existing scientific state, and inconsistent states conservatively | Before ordinary `loadDocumentState`; reuse `latestManagedFilename`, marker validation, consistency audit | Current detector only answers “which managed proposal is latest?”; it does not inspect scientific workflow state |
| Scientific deliberation | Tutor/reviewer bounded assessments; `DELIBERATE` and `REVIEW` are read-only | Persist structured scientific acts/decisions without publishing document bytes | New scientific service alongside role adapters; reuse `LocalContext`, `TutorAssessment`, `ReviewerAssessment` | No persistence for tutor/reviewer assessments or deliberation events |
| Planning | `buildEditPlan`, `buildConceptualPlan`, adaptive move/copy planners | Keep scientific reasoning separate from document mutation; produce a materialization proposal, not an implicit edit | Separate scientific planner result before `publish`; existing `EditPlan` remains V2-only | Existing planner outputs are already close to edit actions and can accidentally couple reasoning to mutation |
| Context | `buildContext`, `buildMoveCopyContext`, structural/reference/symbol/concept indexes | Supply bounded evidence to scientific acts and record evidence identity | Reuse `DocumentState`/`LocalContext` and entry IDs/hashes | Context contains document content and is not an auditable scientific-event reference by itself |
| Document mutation | `publish`, `compilePatches`, `validateCandidate`, `ProposalWorkspaceAdapter.publishSuccessor` | Only explicit materialization may enter this route | Keep adapter and guard unchanged; add an explicit handoff to it | Current conceptual path can publish immediately after role/planner approvals; no separate materialization confirmation exists |
| Revision lifecycle | `RevisionLifecycleTransaction` and `revision-lifecycle-store` | Preserve exactly as-is | Early lifecycle dispatch in `Orchestrator.execute`; lifecycle transaction/store | Lifecycle artifacts currently cover proposal/state/receipt only, not scientific state |
| Persistence | `.paper-proposal-v2/state/*.json`, `.paper-proposal-v2/receipts/*.json`, lifecycle quarantine | Persist scientific state/events with stable identities and auditable transitions | New versioned store using existing atomic-write and audit patterns | Existing `RevisionReceipt` records mutation evidence, not scientific reasoning/event history |
| Recovery/audit | `loadDocumentState` rebuild; `runConsistencyAudit`; `runPaperProposalV2SelfAudit`; pending-audit markers | Detect/recover incomplete scientific transitions without exposing chain-of-thought | Extend consistency/audit orchestration only after state schema is defined | Audit currently knows proposal manifests/receipts and lifecycle markers, not scientific state |
| Public response | `projectPaperProposalV2PublicResult` and lifecycle projection | Return state/event summaries and explicit next action while redacting reasoning traces | New projection function, keeping current V2 projection unchanged | Current internal result exposes broad evidence before projection; no scientific event public contract |

## 3. Entry-state detection and defensive/inconsistent-state contracts

### Current entry behavior

- `PaperProposalV2Orchestrator.latest()` scans `root/proposals`, accepts only the managed `research-concept-...-rNN.md` pattern, sorts numerically by revision, and returns the greatest revision.
- An explicit `sourceFilename` is validated for pattern, existence, and the exact marker prefix. Missing/unmanaged sources return blocked results without model calls.
- Without an explicit source, the orchestrator uses the latest managed proposal. If none exists it returns `NO_MANAGED_PROPOSAL`.
- `loadDocumentState` parses lineage/revision from the managed filename, reads the document, rebuilds all derived indexes, then loads a cached state only if its manifest hashes, parser version, filename, document SHA, entry ranges, and entry text hashes validate. Otherwise it persists a fresh `VALID` state and does not invent receipt/publication evidence.
- An expected source SHA supplied by the caller is checked after loading and blocks stale mutations.
- Target selection uses exact composite text first, explicit entry/label/tag next, then scored lexical/symbol/equation resolution. `ambiguityGate` refuses missing or tied/comparable candidates rather than selecting the first match.

### Defensive contracts already present

- Lifecycle intent is classified before destructive content deletion. “Delete/remove r02” is `AMBIGUOUS`; section/content deletion remains `DELETE`; explicit withdrawal/restore bypasses normal state/planning/model routes.
- `discoverManagedRevision` is stricter than ordinary state loading: it blocks base/r01 withdrawal, missing document/state/receipt, unmanaged markers, SHA/filename/revision/source mismatches, missing source revisions, and later dependent revisions.
- Lifecycle files are required to be regular non-symlink files within the canonical project root; operation directories and parents are checked for exact safe directories.
- `runConsistencyAudit` detects missing/invalid committed manifests, SHA mismatches, missing receipts for non-r01 revisions, committed state without receipt, orphan state/receipt files, temporary leftovers, and unsafe/invalid withdrawal markers/artifacts.
- Pending lifecycle audit context is accepted only while the matching lifecycle lock owner and active operation are present, with exact marker, phase, three-artifact inventory, digest, placement, and lease checks.
- `SelfAudit` fails on consistency failure, unreleased locks, duplicate runtime/orchestrator signals, or V1 activity. Editorial status is currently reported separately as `WARN`.
- Mutation publication uses an in-memory source/lineage/filename/SHA lock and blocks concurrent mutation attempts. The workspace/guard additionally enforces one active operation, non-reusable terminal operation IDs, preflight budgets, one-time mutation authorization, and explicit completion/blocking.

### Inconsistency gap relevant to the requested workflow

There is no current state representing “new project,” “scientific state exists,” “materialization pending,” or “scientific state inconsistent.” A missing or corrupt ordinary derived state is automatically rebuilt. That is safe for derived indexes but would be unsafe as an implicit policy for authoritative scientific state/events. The new workflow therefore needs an explicit distinction between rebuildable projections and authoritative scientific records; the existing code does not decide that distinction.

## 4. Semantic-operation and lifecycle routing to preserve

The following behavior is already contractually exercised and should remain untouched by a scientific workflow extension:

- Exact-block semantic MODIFY enters through the complete natural-language instruction and source filename; internal intent resolution finds the target composite and preserves exact replacement bytes.
- Literal INSERT, DELETE, and literal MOVE/COPY do not require a planner; adaptive MOVE/COPY uses one planner call and preserves source/destination identity.
- DELETE expands heading subtrees and rejects broken references or removal of later-used symbols. Semantic cleanup is separately authorized, bounded to at most three ranges, and cannot target equations.
- `DELIBERATE` and `REVIEW` are assessment-only; they return zero mutations and do not publish.
- Conceptual revision keeps conditional tutor/reviewer activation and its two-model-call ceiling; it is not a fixed tutor → planner → reviewer chain for every request.
- Lifecycle operations are not content deletion. Explicit `WITHDRAW_REVISION` generates its own operation ID; restore accepts an operation ID or uniquely identifying filename and clarifies only when filename lookup is ambiguous.
- Publication always uses a single successor path: candidate compilation/validation, `ProposalWorkspaceAdapter.publishSuccessor`, source reread and SHA verification, target reread and SHA verification, guard completion, derived rebuild, committed state, and receipt.
- No new scientific route should accept caller-supplied offsets, hashes, patches, invented entry IDs, or full-document replacement as a shortcut around these boundaries.

## 5. Persistence, atomicity, recovery, and audit mechanisms available

### Proposal-derived state and receipts

- `.pi/extensions/paper-proposal-v2/derived-state-store.ts` stores manifests and indexes at `.paper-proposal-v2/state/<filename>.json` and receipts at `.paper-proposal-v2/receipts/<filename>.json`.
- `atomic(...)` writes a temporary sibling file and renames it into place. `saveDerivedState` refuses to replace a different committed state with incompatible content.
- `validateStoredState` binds the manifest to filename, parser version, document SHA, all index hashes, and every structural entry byte range/text hash. A committed state additionally requires a matching publication receipt.
- `RevisionReceipt` records source/target revisions, document SHAs, operation/intent, resolved entries, patch IDs/count, cleanup level, derived status, model/role counts, validation results, and timing fields. It deliberately does not store model prompts or chain-of-thought.

### Guarded publication

- `proposal-workspace.ts:createDocumentOperationGuard` is an operation-scoped in-memory policy with terminal IDs, one active operation, preflight budget, and one-time mutation authorization.
- `ProposalWorkspaceAdapter.publishSuccessor` validates the effective operation profile and input identity before guard calls; it performs begin → preflight → authorize → `proposal_workspace` `derive_successor` → target/source rereads → hash/byte checks → complete.
- `proposal-workspace.ts:deriveSuccessorProposal` is the filesystem publication boundary. It accepts bounded patches against the exact latest source/SHA, enforces successor naming/lineage/continuity, validates the composed candidate, and atomically creates the immutable successor.
- `withMutationLock` ensures one protected mutation for a source key and releases the lock in `finally`.

### Lifecycle transaction

- `RevisionLifecycleTransaction.withdraw` and `.restore` use a per-revision lifecycle lock, staging directories, verified copies, atomic renames, operation metadata, pending-audit markers, exact artifact placement/SHA checks, and rollback.
- A managed revision’s lifecycle inventory is exactly the public document, derived state, and receipt. Withdrawal retains immutable copies under `.paper-proposal-v2/withdrawn/<operation-id>/`, moves public artifacts to `public-backup`, and finalizes only after `SelfAudit`/consistency pass. Restore recreates public artifacts while retaining quarantine data.
- Failure injection hooks (`createFaultInjectingLifecycleFs`) and explicit rollback checks are already available for move/copy/marker/audit failures.

### What can be reused for scientific state

The atomic JSON writer, SHA-bound manifest pattern, explicit versioning, operation IDs, immutable backup/event identity, lock ownership, pending-audit marker, consistency audit, self-audit, and temporary-root fixtures are usable patterns. However, reuse should not mean placing scientific events into `RevisionReceipt` or silently treating them as derived indexes. A scientific event stream needs a separately defined authoritative schema and transition/recovery policy.

## 6. Existing test runners and relevant fixtures

### Test execution signals

`openspec/project-context.md` and `openspec/config.yaml` did not detect one authoritative runner, and `apply.test_command`/`verify.test_command` are blank. Source/test evidence nevertheless identifies:

- Node built-in tests: `node --test tests/*.test.mjs`.
- Focused V2 tests: `node --test tests/paper-proposal-v2-*.test.mjs`.
- Python standard library tests: `python -m unittest tests/test_extract_pdf.py` is consistent with `tests/test_extract_pdf.py` importing `unittest` and providing `unittest.main()`.
- Prior OpenSpec task evidence records passing historical runs of the focused V2 suite and the complete Node suite, but this exploration did not execute tests.
- There is no project-local `package.json` or reliable project-local TypeScript runner visible from the inspected paths; V2 tests load TypeScript through Jiti and aliases to the installed Pi runtime.

### Relevant Node fixtures and coverage

- `tests/paper-proposal-v2.test.mjs`: deterministic indexes, intent resolution, ambiguity gate, bounded context, patch compilation, effective profiles, and adapter validation.
- `tests/paper-proposal-v2-source-routing.test.mjs`: explicit source routing, composite target resolution, isolation from another proposal-like file, and no fallback to `latest()`.
- `tests/paper-proposal-v2-skill-request-boundary.test.mjs`: exact-block skill-shaped request with only source filename/instruction and exact provider payload behavior.
- `tests/paper-proposal-v2-production-modify.test.mjs`: real production runtime/provider boundary, one-call planner contract, budget preflight, malformed-response diagnostics, no mutation on blocked output, committed state, and receipt.
- `tests/paper-proposal-v2-production-smoke.test.mjs` and `tests/paper-proposal-v2-production-role-metrics.test.mjs`: production tool registration, planner/tutor/reviewer calls, metrics, and read-only deliberate/review behavior.
- `tests/paper-proposal-v2-tutor-reviewer.test.mjs`: role decision validation, affected-entry bounds, budgets, risk-based reviewer activation, and cleanup authorization/range/equation protection.
- `tests/paper-proposal-v2-conceptual-e2e.test.mjs`: tutor-before-editor mathematical path, tutor blocking, high-risk reviewer path, reviewer blocking, and read-only routes.
- `tests/paper-proposal-v2-semantic-modify-e2e.test.mjs`, `...-delete-cleanup-e2e.test.mjs`, `...-move-copy-e2e.test.mjs`: semantic operations, target ambiguity, destructive safety, adaptive planning, and no-publication cases.
- `tests/paper-proposal-v2-derived-state-recovery.test.mjs`: missing/stale/corrupt rebuild, valid state without receipt, committed-state-without-receipt rejection, publication persistence, and no invented operation evidence.
- `tests/paper-proposal-v2-restart-persistence.test.mjs`: fresh-runtime reload, stale-source blocking, and disk persistence.
- `tests/paper-proposal-v2-revision-lifecycle.test.mjs`, `...-pending-audit.test.mjs`, `...-consistency-audit.test.mjs`, and `...-self-audit.test.mjs`: lifecycle classification/dispatch, exact quarantine/restore, fault-injection rollback, pending marker security, audit failures, orphan detection, lock/runtime checks.
- `tests/paper-proposal-v2-concurrency.test.mjs`, `...-parallelism.test.mjs`, and `...-representation.test.mjs`: lock/recovery, configured parallelism, byte/hash representation, and adapter patch transport.
- `tests/proposal-workspace.test.mjs`: extensive workspace sandbox, successor continuity, exact patch, display/equation authorization, atomic publication, stale source, collision, and path-safety coverage.

The dominant fixture pattern is an isolated `mkdtemp` root with `proposals/`, a marker-owned `research-concept-r01.md`, the real guard/workspace/adapter/orchestrator, and either a fake planner or registered faux provider. Lifecycle tests explicitly avoid mutating repository proposal fixtures.

## 7. Feasibility, gaps, and minimum safe change surface

### Feasibility

The requested flow is technically feasible without changing Paper Proposal V2 mutation behavior:

- conservative entry routing can be inserted before ordinary state loading;
- scientific deliberation can reuse bounded `DocumentState`/`LocalContext` and existing tutor/reviewer validation;
- structured scientific state/events can be persisted through a new, separately audited store using the existing atomic JSON and SHA/version conventions;
- explicit materialization can hand off only an approved, user-confirmed bounded action to the unchanged V2 publication path;
- direct V2 and lifecycle routes can remain selected by their existing intent precedence and early lifecycle dispatch.

### Main gaps

1. No defined scientific-act vocabulary or state transition contract exists.
2. No project entry-state detector distinguishes absent, initialized, active, stale, pending materialization, or inconsistent scientific state.
3. No durable scientific event/state store exists; current receipts only describe document mutations.
4. No explicit materialization intent/confirmation boundary exists. Conceptual revision currently may publish in the same execution after role/planner checks.
5. No audit rules define which scientific fields are authoritative, how events are chained, or how interrupted scientific transitions recover.
6. No policy says whether scientific state is per project, per managed revision, per lineage, or per target entry.
7. No public response contract exists for scientific state/event summaries, next actions, or redaction guarantees.
8. Existing runtime metrics count calls and mutations but do not provide durable scientific event identity.

### Minimum safe change surface for later planning

This is not a design decision, but the smallest coherent investigation/implementation boundary appears to be:

- an early scientific-workflow classifier/router adjacent to `resolveIntent` and `Orchestrator.execute`, with an explicit compatibility rule that existing direct V2/lifecycle requests win;
- a scientific state/event module under `.pi/extensions/paper-proposal-v2/` or a clearly separated sibling namespace, with versioned schemas, atomic writes, and no prompts/hidden reasoning/chain-of-thought persistence;
- a read-only scientific deliberation path that consumes bounded context and returns structured outcomes without calling `publish`;
- an explicit materialization boundary that accepts only an approved structured action and then delegates to the existing V2 planner/patch/guard/adapter route rather than writing documents directly;
- consistency/self-audit extensions for the new authoritative state, plus isolated temporary-root tests for entry states, event transitions, interrupted writes, recovery, and direct-V2 non-regression.

### Open questions and risks

- What exact user-visible project entry states are required, and which states must block versus offer recovery?
- What constitutes a “scientific act”: question, hypothesis, assumption, alternative, critique, decision, unresolved issue, or materialization request?
- Is the authoritative unit a project, proposal revision, lineage, document entry, or a combination?
- Which state transitions are allowed without document mutation, and which require explicit user confirmation?
- Should scientific events be append-only, snapshot-plus-events, or another format? How are event IDs, ordering, deduplication, and causal links defined?
- What evidence references are safe to persist: entry IDs, byte hashes, excerpts, or only document/revision hashes? Persisted evidence must not become an accidental chain-of-thought channel.
- How should a scientific state tied to withdrawn/restored revisions behave? Lifecycle currently quarantines exactly three proposal artifacts and knows nothing about additional state.
- Should a scientific state be restored with a withdrawn revision, remain project-level, or be invalidated and require explicit reconciliation?
- How does explicit materialization differ from direct `CONCEPTUAL_REVISION`, and what compatibility behavior is required for existing users of that route?
- Does the desired flow need a new public tool/operation, or can it be represented inside `paper_proposal_v2_execute` without making its current public contract ambiguous?
- Current ordinary derived-state loading rebuilds missing/corrupt projections automatically, while lifecycle validation blocks inconsistent authoritative artifacts. The new workflow must choose which scientific files are rebuildable projections and which must fail closed.
- No runtime tests were executed in this phase; historical test results cited above are repository evidence, not a fresh verification of the current workspace.
