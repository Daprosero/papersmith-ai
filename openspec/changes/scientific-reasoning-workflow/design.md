# Persistent Scientific Reasoning Workflow — Technical Design

## Decision

Add `SCIENTIFIC_WORKFLOW` as an explicit, feature-gated Paper Proposal V2 route backed by an authoritative scientific-state store. Scientific work is persisted as a bounded graph of Scientific Threads and immutable events; it never mutates a proposal document until the user explicitly materializes a frozen accepted decision set.

The route order is fixed: lifecycle, direct document operation, `DELIBERATE`, then `SCIENTIFIC_WORKFLOW`. The first three routes never construct, read, or invoke scientific workflow components. Feature admission is owned only by the outer route entry point. The active thread and its explicitly related direct neighbors are the only default scientific context.

## Ordered control flow

```text
User message
  -> GlobalRouteResolver
       1. explicit lifecycle operation?
          -> current RevisionLifecycleTransaction route -> return
       2. explicit direct document operation?
          -> current V2 document pipeline -> return
       3. DELIBERATE?
          -> current read-only document analysis -> return
       4. explicit SCIENTIFIC_WORKFLOW?
          -> outer feature admission (the only feature-flag read)
          -> ProjectEntryResolver
             -> EMPTY_PROJECT: start from an explicit idea seed
             -> existing state: recover validated state conservatively
          -> ScientificActResolver
          -> ScientificThreadResolver
             -> create from seed | continue active | select existing | clarify/block
          -> ScientificContextBuilder
             -> active thread + explicitly selected direct relations only
          -> Tutor
          -> Conceptual Reviewer
             -> repair required: structured critique -> Tutor -> Reviewer recheck
          -> Thread Synthesis
          -> explicit user decision
             -> REJECT_DECISION: persist rejection, return
             -> MODIFY_SYNTHESIS: reopen active thread, retain history, deliberate again
             -> ACCEPT_DECISION: persist frozen ACCEPTED_UNMATERIALIZED decision, return
          -> no materialization request: continue discussion, no document write
          -> REQUEST_MATERIALIZATION with explicit frozen decisions
             -> stable idempotency/selection control
             -> Materialization Planner
             -> MaterializationCandidateExecutor (non-writing)
             -> deterministic existing-V2 candidate validation seams
             -> existing V2 Document Reviewer
             -> existing guarded V2 publication adapter
             -> verify published bytes, derived state, and receipt
             -> only then mark selected decisions MATERIALIZED
       otherwise
          -> current ambiguous/direct behavior
```

`SCIENTIFIC_WORKFLOW` is selected only through the explicit public operation. Scientific-looking natural language does not activate it. The Global Route Resolver evaluates each stage separately and records the selected stage and bypassed stages in route metrics/audit evidence. Lifecycle, direct-document, and `DELIBERATE` are terminal route stages: they must not instantiate `ProjectEntryResolver`, `ScientificActResolver`, `ScientificThreadResolver`, `ScientificContextBuilder`, Tutor, Conceptual Reviewer, scientific persistence, or materialization components.

## Grounding in the current V2 seams

| Existing seam | Current behavior | Design use |
|---|---|---|
| `.pi/extensions/proposal-workspace.ts:paper_proposal_v2_execute` | Public schema, runtime context, and public-result projection entry point. | Add the explicit scientific request/result schema and `GlobalRouteResolver`; it alone reads the feature flag after the first three route stages have declined. |
| `paper-proposal-v2/orchestrator.ts:PaperProposalV2Orchestrator.execute` | Resolves intent, dispatches lifecycle early, loads a managed document, then handles `DELIBERATE`, review, planning, validation, and publication. | Keep it as the direct-document engine. Do not insert scientific state transitions into `execute()` or `publish()`. |
| `intent-resolver.ts:resolveIntent` | Existing direct/lifecycle classification with defensive ambiguity. | Preserve unchanged for stages 1–3. Scientific classification is a separate resolver used only at stage 4. |
| `context-builder.ts:buildContext` | Bounded local document context. | Reuse only verified document fragments through `ScientificContextBuilder`; never use it to load an entire project history. |
| Tutor/Reviewer adapters and `ProductionModelRuntime` | Validated advisory roles over a serialized runtime. | Reuse adapters with scientific wrappers. Tutor and Conceptual Reviewer remain advisory. The Document Reviewer is a distinct post-candidate role. |
| `compilePatches` and `validateCandidate` | Compile an existing document plan and validate an in-memory candidate before publish. | Reuse as deterministic validation seams after the non-writing Candidate Executor. |
| `ProposalWorkspaceAdapter.publishSuccessor` | Guarded successor publication, source reread/hash verification, and completion. | Remains a publication adapter only; it is not the materialization Executor required by this design. |
| `proposal-workspace.ts:createInitialProposal` and document guard | Guarded `INITIAL_CREATE` support exists for `r01`. | Add a narrow adapter method that invokes this existing guarded path after candidate review. |
| derived state, consistency audit, self-audit, lifecycle transaction | Atomic document state and exact lifecycle inventory/recovery. | Reuse conventions and compose scientific audit; do not add scientific files to lifecycle inventory. |

## Routing and public contract

### Request and result

```ts
type ScientificWorkflowOperation = 'SCIENTIFIC_WORKFLOW';

type ScientificWorkflowRequest = {
  operation: 'SCIENTIFIC_WORKFLOW';
  instruction: string;
  activeThreadId?: string;
  relatedThreadIds?: string[];       // explicit direct neighbors only
  scientificAct?: ScientificActKind; // must agree with the instruction
  candidateIds?: string[];           // frozen decision aliases for materialization
  idempotencyKey?: string;           // retry alias, never an authority
};

type ScientificWorkflowPublicResult = {
  status: 'ready' | 'recorded' | 'needs_clarification' | 'blocked' |
          'materialized' | 'recovery_required' | 'unavailable';
  operation: 'SCIENTIFIC_WORKFLOW';
  routeStage: 'SCIENTIFIC_WORKFLOW';
  entryState: ProjectEntryState;
  activeThread?: ThreadSummary;
  relatedThreads: ThreadSummary[];
  candidates: MaterializationCandidateSummary[];
  eventId?: string;
  decisionId?: string;
  materialization?: MaterializationPublicSummary;
  blockers: PublicBlocker[];
  nextAction: string | null;
  auditStatus: 'PASS' | 'WARN' | 'FAIL' | 'NOT_RUN';
  selfAuditStatus: 'PASS' | 'WARN' | 'FAIL' | 'NOT_RUN';
  metrics: ScientificMetricsDelta;
};
```

The route result records the final selected route stage. Lifecycle/direct/`DELIBERATE` retain their existing response shapes and do not gain scientific fields. Public and persisted scientific summaries are allowlisted, size-bounded, and exclude prompts, private reasoning, raw model responses, hidden traces, and unrestricted transcripts.

### GlobalRouteResolver contract

```ts
interface GlobalRouteResolver {
  resolve(input: PublicV2Request): Promise<
    | { stage: 'LIFECYCLE'; request: ExistingLifecycleRequest }
    | { stage: 'DIRECT_DOCUMENT'; request: ExistingDocumentRequest }
    | { stage: 'DELIBERATE'; request: ExistingDeliberateRequest }
    | { stage: 'SCIENTIFIC_WORKFLOW'; request: ScientificWorkflowRequest }
    | { stage: 'EXISTING_FALLBACK'; request: ExistingDocumentRequest }
  >;
}
```

1. Lifecycle means explicit withdrawal/restore or current lifecycle intent; it dispatches before document loading and before any scientific access.
2. Direct document means an explicit existing direct operation or an instruction that the existing resolver recognizes as a non-ambiguous direct operation, excluding `DELIBERATE` which is stage 3 for traceability.
3. `DELIBERATE` uses the current read-only analysis contract, including its current target resolution and role behavior.
4. Only an explicit `SCIENTIFIC_WORKFLOW` that reached this stage invokes the scientific workflow.

This preserves lifecycle/direct precedence, keeps `DELIBERATE` unchanged, and ensures that an explicit scientific request containing a recognized lifecycle or direct document command follows the existing route rather than silently becoming a scientific act. If the feature is disabled at stage 4, return `unavailable`; never fall back to a document edit.

## Entry, thread, and context resolution

### ProjectEntryResolver

`ProjectEntryResolver` reads but never repairs strict managed-revision inventory and validated scientific authoritative records before any scientific mutation.

```ts
type ProjectEntryState =
  | 'EMPTY_PROJECT' | 'SCIENTIFIC_ONLY' | 'ACTIVE_PROPOSAL'
  | 'ACTIVE_SCIENTIFIC_PROJECT' | 'MATERIALIZATION_PENDING'
  | 'WITHDRAWN_ONLY' | 'INCONSISTENT_PROJECT' | 'MULTIPLE_ACTIVE_REVISIONS';

type ProjectEntry = {
  state: ProjectEntryState;
  activeRevision?: RevisionEvidence;
  activeThreadId?: string;
  relatedThreadIds: string[];
  pendingCandidateIds: string[];
  recovery: { required: boolean; code?: string; action?: string };
  auditEvidence: string[];
};
```

`EMPTY_PROJECT` may accept a user-provided idea seed but must not create `r01`. `ACTIVE_PROPOSAL` may bootstrap only verified observations and unknown history. Invalid schema/digests, non-contiguous events, invalid graph references, duplicate immutable IDs, stale required revision evidence, dangling publication, or transaction inconsistency yields a safe blocked/recovery outcome. Authoritative state is never inferred from document bytes; only a validated projection can be rebuilt from authoritative events.

### Empty-project lifecycle clarification: state, trigger, and guard

This distinction is intentional and must remain independently verifiable:

| Concern | Rule |
|---|---|
| **State** | `EMPTY_PROJECT` means no active managed revision and no authoritative scientific state. After a user accepts an eligible decision, the project has scientific state and the decision is `ACCEPTED_UNMATERIALIZED` (normally exposed as `MATERIALIZATION_PENDING`); it is no longer treated as an empty project for publication purposes. |
| **Trigger** | Deliberative acts—including idea construction, Tutor/Reviewer work, repair, synthesis, `ACCEPT_DECISION`, rejection, retraction, and ordinary continuation—must never create `r01`. Once at least one `ACCEPTED_UNMATERIALIZED` decision exists, an explicit `REQUEST_MATERIALIZATION` with its frozen candidate selection may start initial materialization. |
| **Guard** | The initial-materialization branch must pass the existing frozen-selection, idempotency, Planner → non-writing Candidate Executor → deterministic validation → Document Reviewer approval sequence. Only then may the guarded `publishInitial()` adapter invoke the existing `createInitialProposal()` / `INITIAL_CREATE` flow to generate `r01`. |

Therefore, the no-automatic-creation rule applies during deliberation; it is not a permanent prohibition on initial materialization for a project that began in `EMPTY_PROJECT`.

### ScientificActResolver

```ts
type ScientificActKind =
  | 'CONSTRUCT_IDEA' | 'CONSTRUCT_QUESTION' | 'CONSTRUCT_HYPOTHESIS'
  | 'CONSTRUCT_ASSUMPTION' | 'CONSTRUCT_ALTERNATIVE' | 'RAISE_UNRESOLVED_ISSUE'
  | 'RELATE_THREADS' | 'REQUEST_TUTOR' | 'REQUEST_CONCEPTUAL_REVIEW'
  | 'SYNTHESIZE' | 'MODIFY_SYNTHESIS'
  | 'ACCEPT_DECISION' | 'REJECT_DECISION' | 'RETRACT_DECISION'
  | 'REQUEST_MATERIALIZATION' | 'BOOTSTRAP_FROM_ACTIVE_PROPOSAL'
  | 'PROPOSE_RECONCILIATION' | 'ACCEPT_RECONCILIATION';

type ScientificActResolution =
  | { status: 'resolved'; act: ScientificActKind; requestedThreadId?: string; relatedThreadIds: string[] }
  | { status: 'needs_clarification'; question: string }
  | { status: 'blocked'; code: string };
```

It runs only after valid entry resolution. A caller-supplied act must agree with conservative instruction classification. It never resolves lifecycle/direct instructions as scientific acts.

### ScientificThreadResolver

`ScientificThreadResolver` is mandatory between act resolution and context construction. It converts entry state, resolved act, and user thread selection into one active-thread decision. It owns no document behavior and never silently chooses a thread.

```ts
type ThreadResolutionInput = {
  entry: ProjectEntry;
  act: ScientificActResolution & { status: 'resolved' };
  requestedActiveThreadId?: string;
  relatedThreadIds: string[];
  ideaSeed?: BoundedScientificSeed;
};

type ThreadResolution =
  | { status: 'created'; activeThread: ScientificThread; event: PendingScientificEvent }
  | { status: 'continued'; activeThread: ScientificThread }
  | { status: 'selected'; activeThread: ScientificThread }
  | { status: 'needs_clarification'; code: 'THREAD_SELECTION_AMBIGUOUS' | 'THREAD_REQUIRED'; question: string }
  | { status: 'blocked'; code: ThreadResolutionFailureCode; blockers: PublicBlocker[] };

interface ScientificThreadResolver {
  resolve(input: ThreadResolutionInput): Promise<ThreadResolution>;
}
```

Resolution rules are ordered and deterministic:

1. **Create from seed.** `CONSTRUCT_IDEA` in `EMPTY_PROJECT`, or an explicit create-worthy seed in a valid project, creates a new `OPEN` thread only when the seed is bounded and user-originated. The atomic transition appends `THREAD_CREATED` and the seed event, sets the active-thread projection, and may append explicit relation events only when supplied endpoints validate. It creates neither a document nor a decision.
2. **Continue active.** When no thread ID is supplied and exactly one validated active thread applies to the entry/act, return that thread. The resolver records no selection event merely for continuation.
3. **Select existing.** A supplied `activeThreadId` must identify a validated, eligible existing thread. Persist `THREAD_SELECTED` when the active-thread projection changes; include the causal selection input and any validated direct relation selection. An unknown, retracted/blocked-for-act, or stale-evidence thread is blocked with a recoverable reason.
4. **Ambiguity.** Multiple plausible threads, no active thread for an act that cannot create one, a requested thread outside the project, or a related-thread request that is not a direct graph neighbor returns clarification or block. It never chooses by recency, lexical ordering, document revision, or model suggestion.

The resolver receives entry state and act resolution explicitly, validates all identities against the authoritative snapshot/events, and persists only `THREAD_CREATED`, `THREAD_SELECTED`, `THREAD_ACTIVATED`, and explicit relation changes through `ScientificStateStore`. A failed thread transition leaves no partial event or active-thread projection; recovery reports `THREAD_TRANSITION_INCOMPLETE`. Isolated tests cover create-from-seed, active continuation, explicit selection, no-active/multiple-thread ambiguity, invalid/blocked threads, invalid direct relation selection, interrupted persistence, and the guarantee that resolver failures do not create a document or invoke roles.

### ScientificContextBuilder

```ts
interface ScientificContextBuilder {
  build(input: {
    activeThread: ScientificThread;
    requestedDirectRelationIds: string[];
    act: ScientificActKind;
    verifiedRevision?: RevisionEvidence;
  }): Promise<ScientificRoleContext>;
}
```

The builder includes the active thread, only explicitly selected valid direct-neighbor relations, act-relevant evidence, and optional verified local document fragments. It rejects transitive traversal, implicit related-thread expansion, full-document loading, whole-project replay, and raw role transcripts. Count and byte caps may narrow context but cannot widen it.

## Roles, synthesis, and user decisions

### Mandatory Tutor → Conceptual Reviewer path

Every candidate synthesis—initial synthesis, repaired synthesis, or reopened modified synthesis—must use this exact sequence:

```text
resolved active thread + bounded context
  -> Tutor produces advisory construction/synthesis
  -> persist allowlisted TUTOR_ASSESSED advisory event
  -> Conceptual Reviewer assesses that candidate synthesis
     -> pass: persist CONCEPTUAL_REVIEW_RECORDED; present synthesis to user
     -> repair required: persist structured finding; send it to Tutor
         -> Tutor returns bounded repaired synthesis
         -> persist REPAIR_PROPOSED advisory event
         -> Conceptual Reviewer rechecks repaired synthesis
```

The reviewer finding sent to Tutor is structured: finding ID, candidate synthesis ID/digest, bounded issue category, failed assumptions/evidence references, required correction, and constraints. Tutor receives the same active/direct-neighbor bounded context plus that critique; it cannot alter the thread, accept a decision, create a plan, or publish.

The loop permits at most two repair/recheck cycles per user synthesis request. Each cycle has a new candidate digest and causal links to the prior finding/candidate. A third repair requirement, missing role adapter, invalid role response, invalid critique reference, or context rebuild failure ends in `REPAIR_LOOP_EXHAUSTED` or its specific recoverable block. The workflow returns the retained history and asks the user to revise, select another thread, or retry after remediation. There is no automatic acceptance, automatic repair acceptance, or automatic retry.

Conceptual Reviewer outcomes are `PASS`, `REPAIR_REQUIRED`, `BLOCK`, or `NEEDS_CLARIFICATION`. Only `PASS` exposes a synthesis for an explicit user decision. A repair-required result never bypasses Tutor or recheck; a favorable Tutor result never bypasses conceptual review.

### Thread synthesis and decisions

After a reviewed `PASS`, `Thread Synthesis` records a bounded candidate synthesis event and presents only these explicit user acts:

- `ACCEPT_DECISION`: validates the exact reviewed synthesis digest and causal review pass, appends `DECISION_ACCEPTED`, freezes the decision content/acceptance event, and makes it `ACCEPTED_UNMATERIALIZED`. It does not materialize.
- `REJECT_DECISION`: appends `DECISION_REJECTED`, preserving the candidate and review history. It is never eligible for materialization.
- `MODIFY_SYNTHESIS`: appends `SYNTHESIS_REOPENED` to the active thread, preserves the prior synthesis, review, and user-decision history, and records the modification request/cause. It returns the thread to deliberation and requires a new Tutor → Conceptual Reviewer sequence. It cannot edit a proposal or mutate the old accepted decision. A later acceptance creates a new immutable decision.

`RETRACT_DECISION` preserves a prior acceptance but marks that decision ineligible. The user is the sole scientific acceptance authority: an acceptance event requires `actor.kind: 'USER'`, explicit `ACCEPT_DECISION`, an exact reviewed-synthesis digest, and valid causal links. Tutor, Conceptual Reviewer, Planner, Candidate Executor, Document Reviewer, and publication adapter outputs cannot be accepted scientific decisions.

### Role contracts

| Component | Input | Output | Forbidden authority |
|---|---|---|---|
| Tutor | `ScientificRoleContext`, synthesis seed or structured critique | bounded advisory synthesis/repair | scientific acceptance, document plan, edit, publish |
| Conceptual Reviewer | bounded context and exact Tutor candidate | pass/finding/repair-required assessment | repair acceptance, document review, write, publish |
| MaterializationPlanner | frozen accepted decisions, source evidence, provenance, canonical metadata | validated, versioned, persisted executable `MaterializationPlan` | new scientific claim, decision acceptance, publish, delegation of operation/payload selection |
| CandidateExecutor (`MaterializationCandidateExecutor`) | reserved frozen plan and frozen source | unpublished exact candidate and validation inputs | drafting, summarization, reinterpretation, change selection, agents/context, filesystem write, guard call, receipt/manifest write, V2-index mutation, publish |
| Document Reviewer | exact validated candidate, plan, provenance map | `APPROVE` or non-pass assessment | change plan, scientific acceptance, mutation authorization |
| V2 publication adapter | approved exact candidate/payload | verified V2 publication result | scientific acceptance, materialization identity allocation |

## Authoritative persistence and transitions

### State model

```ts
type ScientificThreadStatus =
  | 'OPEN' | 'UNDER_REVIEW' | 'REPAIRED' | 'ACCEPTED_UNMATERIALIZED'
  | 'REJECTED' | 'RETRACTED' | 'BLOCKED';

type ScientificThread = {
  threadId: string;
  version: 1;
  status: ScientificThreadStatus;
  title: string;
  summary: string; // allowlisted and bounded
  createdEventId: string;
  headEventId: string;
  revisionEvidence?: RevisionEvidence;
  relationIds: string[];
  decisionIds: string[];
};

type AcceptedDecision = {
  decisionId: string;
  threadId: string;
  acceptedEventId: string;
  acceptedSynthesisDigest: string;
  acceptedBy: { kind: 'USER' };
  state: 'ACCEPTED_UNMATERIALIZED' | 'MATERIALIZED' | 'RETRACTED';
  sourceEventIds: string[];
};

type ScientificEvent = {
  schemaVersion: 1;
  eventId: string;
  sequence: number;
  occurredAt: string;
  actor: { kind: 'USER' | 'SYSTEM' | 'TUTOR' | 'CONCEPTUAL_REVIEWER' | 'PLANNER' | 'EXECUTOR' | 'DOCUMENT_REVIEWER' };
  type: ScientificEventType;
  threadId?: string;
  causalEventIds: string[];
  payload: AllowlistedScientificPayload;
  evidence: EvidenceReference[];
  privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY'; redactionVersion: 1 };
};
```

Authoritative files remain separate from document state:

```text
.paper-proposal-v2/scientific/
  manifest.json
  snapshot.json
  events/<sequence>-<event-id>.json
  materializations/index.json
  materializations/<materialization-id>.json
  transactions/<transition-id>.json
  projections/entry-index.json        # rebuildable only
```

Manifest, snapshot, events, materialization index/records, and transaction markers are authoritative. Projections alone are rebuildable. Every authoritative read validates schema, digest bindings, event sequence/causality, immutable IDs, graph endpoints, relation directness, user-only acceptance, decision lifecycle, privacy allowlists, selection claims, candidate/review linkage, and publication evidence.

### Transition matrix

| Event/transition | Preconditions | Persisted effect | Document effect |
|---|---|---|---|
| `THREAD_CREATED` | valid explicit seed | new thread and seed event | none |
| `THREAD_SELECTED` / `THREAD_ACTIVATED` | valid selected thread | active-thread projection/event | none |
| Tutor/Reviewer/repair events | valid bounded context and causal candidate | advisory/finding/repair history | none |
| `SYNTHESIS_REOPENED` | explicit `MODIFY_SYNTHESIS`, prior synthesis | preserve prior history; active thread returns to deliberation | none |
| `DECISION_ACCEPTED` | explicit user act and reviewer-passed exact synthesis | new frozen `ACCEPTED_UNMATERIALIZED` decision | none |
| rejection/retraction | explicit user act | immutable lifecycle event; candidate unavailable | none |
| `MATERIALIZATION_RESERVED` | exact frozen decision selection | stable record and claims | none |
| plan/candidate/review failure | reserved record | record `BLOCKED`; decisions stay `ACCEPTED_UNMATERIALIZED` | none |
| publication failure/ambiguity | approved candidate attempted | record `BLOCKED` or `RECOVERY_REQUIRED`; decisions stay `ACCEPTED_UNMATERIALIZED` | no claimed success |
| `MATERIALIZATION_COMMITTED` | verified bytes, derived state, and receipt | record provenance and change decisions to `MATERIALIZED` | guarded V2 write already verified |

`ScientificStateStore.commitTransition` holds a project scientific lock and uses atomic sibling rename, exclusive immutable event creation, regular-file/no-symlink checks, fsync/error handling, and a recoverable write-ahead marker. A transition validates root/index/head, writes its prepared marker, writes event(s), writes snapshot, updates manifest/index, and commits/removes the marker. Interrupted or invalid authoritative records fail closed; recovery never fabricates a decision, causal link, document revision, receipt, or materialization success.

## Explicit materialization

### Frozen selection and idempotency

Materialization accepts only explicit `candidateIds` resolving to immutable, user-accepted, unretracted `ACCEPTED_UNMATERIALIZED` decisions. It never expands a thread, relation, or project context implicitly.

```ts
type FrozenDecisionSelection = {
  policyVersion: 1;
  decisionIds: string[];          // sorted and unique
  acceptedEventIds: string[];     // same order
  selectionKey: string;           // hash(project identity + canonical pairs)
};

type MaterializationRecordState =
  | 'RESOLVING' | 'PREPARED' | 'PLANNING' | 'EXECUTING_CANDIDATE'
  | 'REVIEWING_DOCUMENT' | 'PUBLISHING' | 'COMMITTED'
  | 'BLOCKED' | 'RECOVERY_REQUIRED';
```

The exact-set `selectionKey` is looked up before eligibility or mutable-head checks. Under the scientific lock, a new set atomically creates a `RESOLVING` record and one decision claim per selected decision. Exact retry returns/resumes the same record; subset, superset, or partial selection overlap returns `MATERIALIZATION_SELECTION_CONFLICT`. Client idempotency keys are secondary aliases only. A retry never allocates a new record, changes the frozen source, or consumes an already-claimed decision into a new selection.

### Planner, executable payload authority, and publication handoff

The materialization sequence is mandatory for both `CREATE_R01` and `CREATE_SUCCESSOR`:

```text
frozen accepted selection
  -> MaterializationPlanner selects operation and freezes executable payload
  -> CandidateExecutor / MaterializationCandidateExecutor (non-writing)
  -> deterministic compiler/validator seams
  -> existing V2 Document Reviewer
  -> guarded V2 publication adapter
  -> reread/hash + derived-state + receipt verification
  -> MATERIALIZATION_COMMITTED / decisions MATERIALIZED
```

`MaterializationPlanner` is the **sole authorized component** that selects `CREATE_R01` or `CREATE_SUCCESSOR`, invokes the matching pure deterministic producer, validates that producer output, and atomically persists the frozen executable `MaterializationPlan` on the reserved materialization record. Operation selection derives only from the validated frozen selection, entry state, and exact source evidence; it is never caller-selected. The Planner receives only frozen accepted decision content, exact source evidence, selected thread provenance, and canonical metadata. It maps every scientific claim to exactly one selected immutable user acceptance event. No other component may draft, summarize, reinterpret, select changes, or replace the persisted payload.

```ts
type MaterializationPlan = {
  schemaVersion: 1;
  materializationId: string;
  selectionKey: string;
  operation: 'CREATE_R01' | 'CREATE_SUCCESSOR';
  source?: VerifiedDocumentState;
  expectedRevisionIdentity?: RevisionEvidence;
  payload: CreateR01PayloadV1 | CreateSuccessorPayloadV1;
  claimProvenance: ClaimProvenanceMap;
  digest: string;
};

type CreateR01PayloadV1 = {
  kind: 'CREATE_R01';
  markdown: string;
  canonicalMetadata: CanonicalProposalMetadata;
};

type CreateSuccessorPayloadV1 = {
  kind: 'CREATE_SUCCESSOR';
  patches: readonly FrozenEditPlan[]; // canonical ordered execution order
};
```

`InitialRevisionRenderer` is the `CREATE_R01` producer. It is pure and deterministic: its complete Markdown output derives only from frozen accepted syntheses/decisions and canonical metadata embedded in the Planner input. It receives no agent, additional context, mutable external state, workspace access, or clock/randomness input.

`SuccessorEditPlanner` is the `CREATE_SUCCESSOR` producer. It is pure and deterministic: from only the frozen base document, expected revision identity, and accepted decisions, it produces a canonical ordered `FrozenEditPlan[]`. Every patch carries stale-revision, wrong-base-identity, and exact-content preconditions, so the exact payload cannot apply to an unintended or changed source.

Payload compatibility is versioned and fail-closed. The Planner validates `schemaVersion`, operation/payload discriminant agreement, canonical ordering, digest, source/revision bindings, provenance completeness, size/budget limits, and all producer preconditions before persisting the plan. Unsupported versions, malformed payloads, mismatched operation/payload pairs, or invalid producer output are `BLOCKED`; every selected decision remains `ACCEPTED_UNMATERIALIZED`. A new payload version requires an explicitly supported producer, validator, and executor compatibility path; it never silently coerces or upgrades a frozen payload.

`CandidateExecutor` is implemented by the named `MaterializationCandidateExecutor` and is deliberately distinct from `ProposalWorkspaceAdapter`.

```ts
interface MaterializationCandidateExecutor {
  execute(input: {
    record: MaterializationRecord;
    plan: MaterializationPlan;
    frozenSelection: FrozenDecisionSelection;
    source?: VerifiedDocumentState;
  }): Promise<
    | { status: 'ready'; candidate: ExactDocumentCandidate; provenance: ClaimProvenanceMap; validation: CandidateValidation }
    | { status: 'blocked'; code: CandidateExecutionFailureCode; evidence: BoundedExecutionEvidence }
  >;
}
```

CandidateExecutor only loads and validates the frozen plan's supported schema version, reservation, source/revision identity, and payload preconditions, then executes the exact payload and returns an unpublished candidate. For successors it applies only the frozen ordered patches through the existing `compilePatches` and `validateCandidate` seams against the frozen source in memory. For `r01`, it validates and uses only the frozen complete Markdown through the existing initial-document structural/compiler/validator seam in memory. It creates an ephemeral exact candidate digest and uses the frozen claim-provenance map. It never drafts, summarizes, reinterprets, selects changes, calls agents or context builders, publishes, writes files, invokes guards, writes receipts/manifests, or modifies V2 indexes. Candidate execution failure sets the record `BLOCKED` and preserves accepted decisions as `ACCEPTED_UNMATERIALIZED`.

The existing Document Reviewer remains mandatory downstream of CandidateExecutor and receives the exact candidate digest, plan digest, source/candidate validation result, and claim-provenance map. `APPROVE` is its sole pass result. `APPROVE_WITH_CHANGES`, `BLOCK`, and `NEEDS_CLARIFICATION` set the record `BLOCKED`, retain the reviewer evidence, and keep all decisions `ACCEPTED_UNMATERIALIZED`; a changed plan/source/candidate invalidates prior approval and needs a fresh explicit retry and review. Any payload, schema-version, reservation, source/revision identity, or base-content precondition inconsistency fails closed before review or publication. No guard preflight, authorization, workspace mutation, document manifest/receipt write, or `proposals/` write occurs before that exact approval.

Only after approval may the existing guarded V2 publication adapter invoke `publishInitial` or `publishSuccessor`; the publication guard remains mandatory downstream of Document Reviewer. The adapter is a **publication adapter**, not the MaterializationCandidateExecutor. It rereads and verifies document bytes/hash, commits derived state, and writes the appropriate receipt. Publication failure before proven commit is `BLOCKED`; ambiguous or partially evidenced publication is `RECOVERY_REQUIRED`. In either case, the selected decisions remain `ACCEPTED_UNMATERIALIZED`. The only transition to `MATERIALIZED` occurs after the adapter result, derived state, and receipt all verify against the frozen record and exact candidate evidence.

### Initial and successor publication

`publishSuccessor` remains unchanged for existing callers. Add a backward-compatible `ProposalWorkspaceAdapter.publishInitial()` that uses the current guarded `INITIAL_CREATE`/`createInitialProposal` path only after exact candidate approval. It must not write directly.

`CREATE_R01` writes a minimal discriminated `InitialPublicationReceipt`; it does not fake an `r01` source or turn document receipts into scientific history. The scientific materialization record retains selected decision/thread provenance and review evidence. Successor receipts may include only document-safe materialization linkage. Existing lifecycle inventory remains exactly document, derived state, and receipt.

## Failure and recovery table

| Code / condition | Materialization record | Accepted decision state | Required behavior |
|---|---|---|---|
| `THREAD_SELECTION_AMBIGUOUS` / `THREAD_REQUIRED` | none | unchanged | clarify; do not invoke roles or write state/document |
| `THREAD_TRANSITION_INCOMPLETE` | recovery required | unchanged | validate marker and resume/diagnose; never guess active thread |
| `TUTOR_UNAVAILABLE`, invalid Tutor output | none or scientific act blocked | unchanged | retain prior history; user retries or changes input |
| `CONCEPTUAL_REPAIR_REQUIRED` | none | unchanged | persist structured finding and send it to Tutor |
| `REPAIR_LOOP_EXHAUSTED` | none | unchanged | stop after two repair/rechecks; return explicit user remediation |
| `SYNTHESIS_REOPENED` | none | old decision unchanged; new result not yet eligible | retain prior synthesis/decision history and repeat Tutor → Reviewer |
| `MATERIALIZATION_SELECTION_CONFLICT` | existing conflicting record | `ACCEPTED_UNMATERIALIZED` | return conflict reference; do not split/merge selection |
| planner failure/budget/source mismatch | `BLOCKED` | `ACCEPTED_UNMATERIALIZED` | preserve frozen record; explicit recovery/retry only |
| candidate executor/compiler/validator failure | `BLOCKED` | `ACCEPTED_UNMATERIALIZED` | no guard, publication, manifest, receipt, or document write |
| document review non-pass | `BLOCKED` | `ACCEPTED_UNMATERIALIZED` | preserve reviewer evidence; changed candidate requires re-review |
| publication call fails before commit | `BLOCKED` | `ACCEPTED_UNMATERIALIZED` | recover/retry same record; no false receipt |
| publication ambiguous or derived/receipt incomplete | `RECOVERY_REQUIRED` | `ACCEPTED_UNMATERIALIZED` | reconcile exact target, guard, derived state, and receipt before retry |
| verified publication | `COMMITTED` | `MATERIALIZED` | record target/revision/receipt provenance exactly once |
| corrupt events/index/manifest or stale required revision | blocked entry or `RECOVERY_REQUIRED` | unchanged | fail closed; no automatic repair/rebinding |

## Lifecycle, audit, feature flag, and rollout

Withdrawal and restore retain current early dispatch and exact three-artifact quarantine inventory. They create no scientific event and do not mutate scientific records. On later scientific entry, revision evidence is compared conservatively. Withdrawn, missing, stale, or contradictory evidence blocks dependent bootstrap/materialization; it is never rebound to a newer revision. A bounded reconciliation proposal is non-mutating; only exact explicit user acceptance can append a reconciliation event.

The outer tool exclusively reads `PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED` after stages 1–3. Scientific internals never read or branch on feature configuration. Disabled scientific requests return explicit `unavailable` and never fall back. Metrics include route-stage selection, entry states, thread resolution outcome, direct-neighbor context bounds, acts, repair loops, decisions, materialization state/outcome, candidate-executor failures, reviewer outcomes, recovery, latency, and role call counts without raw instructions or model output.

Rollout is disabled-by-default, fixture/read-only telemetry, controlled project, then broad enablement. Rollback disables scientific entry/mutation but preserves read-only diagnostic/recovery access and never deletes history or changes published proposals.

## Affected-file plan

| File | Change |
|---|---|
| `.pi/extensions/proposal-workspace.ts` | Add `GlobalRouteResolver`, explicit scientific schema/projection, and outer-only feature admission; preserve first three routes unchanged. |
| `.pi/extensions/paper-proposal-v2/orchestrator.ts` | At most expose a typed direct-route seam; do not add scientific transitions or materialization execution to `publish()`. |
| `.pi/extensions/paper-proposal-v2/types.ts` | Add scientific request, thread, event, decision, synthesis, materialization, candidate-executor, and receipt-link types without changing existing intent semantics. |
| `.pi/extensions/paper-proposal-v2/project-entry-resolver.ts` **new** | Conservative entry inventory and validated state resolution. |
| `.pi/extensions/paper-proposal-v2/scientific-act-resolver.ts` **new** | Isolated scientific act classification. |
| `.pi/extensions/paper-proposal-v2/scientific-thread-resolver.ts` **new** | Create/continue/select/clarify thread ownership and atomic thread events. |
| `.pi/extensions/paper-proposal-v2/scientific-context-builder.ts` **new** | Active plus direct-explicit-neighbor-only context/redaction. |
| `.pi/extensions/paper-proposal-v2/scientific-state-store.ts` **new** | Authoritative graph/event/materialization persistence, transitions, and recovery. |
| `.pi/extensions/paper-proposal-v2/scientific-workflow-service.ts` **new** | Ordered scientific orchestration, mandatory Tutor/Reviewer loop, user decisions, and materialization handoff. |
| `.pi/extensions/paper-proposal-v2/materialization-planner.ts` **new** | Accepted-decision-only materialization plans and provenance mapping. |
| `.pi/extensions/paper-proposal-v2/materialization-candidate-executor.ts` **new** | Non-writing exact candidate execution using compiler/validator seams. |
| `.pi/extensions/paper-proposal-v2/proposal-workspace-adapter.ts` | Add guarded `publishInitial`; keep publication adapter distinct from Candidate Executor and preserve `publishSuccessor`. |
| `.pi/extensions/paper-proposal-v2/scientific-audit.ts` **new** | Scientific consistency/self-audit and recovery diagnostics. |
| `consistency-audit.ts`, `self-audit.ts`, `revision-receipt.ts`, `operation-spec.ts`, `runtime-metrics.ts`, `exports.ts` | Compose scientific audit, narrow receipt/profile extensions, metrics, and exports without altering lifecycle inventory or direct-route profiles. |
| `tests/paper-proposal-v2-scientific-*.test.mjs` **new** | Isolated routing, thread, synthesis, persistence, candidate execution, materialization, privacy, and recovery fixtures. |
| Existing V2 suites | Focused assertions only for public routing, guarded initial publication, and unchanged lifecycle/direct behavior. |

## Test and replay strategy

Use temporary-root Node/Jiti fixtures; this design phase runs no tests.

1. **Routing:** lifecycle first, explicit direct second, `DELIBERATE` third, scientific fourth; prove each of the first three never accesses scientific components/store and preserves current observable results.
2. **Thread resolver:** create-from-seed, continue-active, select-existing, ambiguity, invalid relation/thread, event persistence, interruption, and no-document-write failure cases.
3. **Synthesis loop:** every candidate synthesis invokes Tutor then Conceptual Reviewer; repair-required sends structured critique to Tutor; repaired candidate rechecks; two-cycle bound; no automatic acceptance.
4. **Modify/reopen:** `MODIFY_SYNTHESIS` retains synthesis/decision history, appends reopen event, requires renewed Tutor/Reviewer work, and never changes a proposal.
5. **Isolation/privacy:** all non-materialization acts leave proposal, manifest, receipt, and managed revision bytes unchanged; reject raw prompts/traces/unbounded role content.
6. **Persistence/replay:** fault inject every atomic transition; replay validated events to snapshot; corrupt, duplicate, gapped, dangling, and invalid-claim records fail closed.
7. **Materialization for r01 and successor:** explicit frozen selection, exact-set idempotency before head validation, overlap conflict, sole Planner authority for operation selection and versioned frozen payload persistence, pure deterministic initial/successor producers, CandidateExecutor schema/reservation/base-precondition rejection with no drafting or V2-index mutation, Planner → non-writing Candidate Executor → deterministic validation → Document Reviewer → adapter order, and no writes before review approval.
8. **Failure matrix:** planner failure, candidate-execution/validation failure, document-review block, pre-commit publication failure, ambiguous publication, and incomplete derived/receipt each retain `ACCEPTED_UNMATERIALIZED`; only verified success marks `MATERIALIZED`.
9. **Compatibility:** current lifecycle, direct operations, `DELIBERATE`, manifests, receipts, guard, audit, self-audit, locks, and recovery suites remain green. Lifecycle fixtures prove no scientific inventory access.

## Mandatory-condition traceability

| # | Mandatory condition | Design location | Verification |
|---:|---|---|---|
| 1 | Explicit persistent scientific mode | Routing/public contract | explicit mode test |
| 2 | Conservative entry before mutation | ProjectEntryResolver | all entry-state fixtures |
| 3 | Idea can start before `r01` | Entry/thread creation | empty-project test |
| 4 | Existing scientific state continues without successor | Thread resolution | continuation test |
| 5 | Scientific acts classify conservatively | ScientificActResolver | disagreement/ambiguity test |
| 6 | Lifecycle and direct precedence stay unchanged | GlobalRouteResolver | ordered-route regression |
| 7 | Deliberation/decisions do not write documents | Transition matrix | tree snapshot tests |
| 8 | Tutor is advisory only | Role contracts | authority-negative tests |
| 9 | Reviewer repair loop is bounded and scientific-only | Mandatory Tutor → Reviewer path | repair/recheck tests |
| 10 | Planner runs only for accepted selected materialization | Materialization planner | planner admission tests |
| 11 | Only explicit materialization creates `r01`/successor | Ordered flow | mutation-gate tests |
| 12 | Candidate executor, document review, guarded V2 publication are ordered | Materialization handoff | call-order tests |
| 13 | Accepted-unmaterialized is visible/durable | State model/public result | re-entry tests |
| 14 | Once-only materialization is stable across retry/restart | Frozen selection | replay/idempotency tests |
| 15 | State is versioned, atomic, auditable, privacy-safe | Persistence model | fault/replay/privacy tests |
| 16 | Context is active + explicit direct neighbors only | Context builder | transitive/unrelated exclusion tests |
| 17 | Bootstrap observes but does not invent history | Entry/lifecycle | bootstrap fixture |
| 18 | Corrupt/partial/stale authoritative state fails closed | Entry/recovery table | corruption fixtures |
| 19 | Scientific audit composes without weakening V2 audit | Audit/lifecycle section | audit regression |
| 20 | Outer-only flag ownership and privacy-safe metrics | Routing/rollout | flag ownership/metrics tests |
| 21 | Scientific Thread graph has explicit bounded relations | Thread/state contracts | relation validation tests |
| 22 | Every act has a thread or asks for clarification | Thread resolver | thread ambiguity tests |
| 23 | Materialization explicitly records selected thread/decision provenance | Frozen selection/commit | r01/successor provenance tests |

## Resolved decisions

1. Lifecycle/direct precedence, unchanged `DELIBERATE`, outer-only feature-flag ownership, direct-neighbor-only context, user-only scientific acceptance, minimal initial receipt, and stable exact-set idempotency remain approved.
2. `MaterializationCandidateExecutor` is a non-writing stage before Document Reviewer; `ProposalWorkspaceAdapter` remains the later guarded publication adapter and is not renamed as Executor.
3. `MODIFY_SYNTHESIS` is an explicit user act that reopens a thread without editing history or proposals.
4. Candidate synthesis always follows Tutor then Conceptual Reviewer, with bounded structured repair/recheck.

No unresolved architectural decision remains.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| New route changes V2 behavior | Four separately terminal route stages, precedence tests, flag default off. |
| Thread selection attaches work incorrectly | Dedicated resolver with explicit create/continue/select rules and clarification on ambiguity. |
| Reviewer repair is skipped or becomes automatic acceptance | Mandatory Tutor → Reviewer sequence, structured critique, two-cycle bound, user-only acceptance. |
| Modification erases provenance | Immutable reopen event and new decision identity; historical syntheses/decisions remain. |
| Candidate stage writes before review | Candidate Executor has no write/guard/adapter capability; ordering tests enforce it. |
| Planner/candidate/review/publication failure falsely materializes | `BLOCKED`/`RECOVERY_REQUIRED` retain `ACCEPTED_UNMATERIALIZED`; commit requires verified bytes, derived state, and receipt. |
| Duplicate revision after retry | Durable exact-set selection claim before planning and exact evidence reconciliation. |
| Scientific context grows to project history | Active thread plus explicitly selected direct neighbors; reject transitive expansion. |
| Lifecycle safety regresses | Scientific files excluded from exact lifecycle inventory; references checked only on later scientific entry. |
| Private reasoning leaks | Typed allowlists, bounded summaries, and persistence/public projection rejection tests. |

## Review checklist

- [ ] Global routing is lifecycle → direct document → `DELIBERATE` → `SCIENTIFIC_WORKFLOW`, and the first three cannot enter scientific components.
- [ ] Only the outer entry point reads the flag; disabled scientific mode never falls back.
- [ ] `ScientificThreadResolver` creates from seed, continues active, selects existing, clarifies ambiguity, persists atomic thread events, and has isolated failure tests.
- [ ] Context is active thread plus explicit direct neighbors only.
- [ ] Every candidate synthesis runs Tutor then Conceptual Reviewer; repair-required critiques return to Tutor and recheck within a bounded loop.
- [ ] Acceptance is user-only; `MODIFY_SYNTHESIS` reopens while retaining history and requires renewed deliberation.
- [ ] Non-materialization acts never write documents, manifests, or receipts.
- [ ] Materialization selects frozen accepted decisions explicitly and preserves stable idempotency/provenance.
- [ ] Planner precedes a named non-writing Candidate Executor, deterministic candidate validation, Document Reviewer, then guarded V2 publication adapter.
- [ ] Planner, executor, validation, document-review, and publication failures retain `ACCEPTED_UNMATERIALIZED`; only verified publication marks `MATERIALIZED`.
- [ ] `CREATE_R01` uses guarded initial publication and a minimal receipt; successor uses the existing guarded adapter.
- [ ] Persistence, audit, recovery, metrics, and rollout preserve privacy and lifecycle compatibility.

## Next step

The corrected design is ready for a traceability gate. No task creation or implementation is authorized by this design.
