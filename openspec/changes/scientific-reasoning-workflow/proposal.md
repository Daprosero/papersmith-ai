# Proposal: Persistent Scientific Reasoning Workflow

## Status

Proposed for specification. This phase defines product intent and requirements only. **No implementation, specification, design, task breakdown, or application behavior changes occur in this phase.**

## Problem statement

Paper Proposal V2 currently supports bounded deliberation, conceptual revision, review, and document publication, but it does not provide a persistent scientific workspace in which an idea can be explored, challenged, repaired, accepted, rejected, or retracted before becoming a document revision. The current routes also do not expose conservative project-entry states or durable, auditable scientific state.

This creates three product risks:

- scientific decisions can be confused with document edits;
- users cannot reliably continue a line of reasoning across sessions or revisions;
- materialization can become an accidental side effect of deliberation rather than an explicit product decision.

The change is worth pursuing because scientific reasoning needs durable state and reviewable decisions while the existing V2 document lifecycle must remain predictable and safe.

## Intent and product outcome

Introduce an explicit persistent scientific workflow mode in the Paper Proposal V2 public contract. In this mode, users can construct and deliberate on scientific concepts without publishing or editing proposal documents. Accepted deltas can later be materialized explicitly through the existing V2 document pipeline.

After this change:

1. A user entering a project can see a conservative state such as idea-only, document-only, active scientific state, materialization pending, or inconsistent state.
2. A project with no revision can begin from an idea and accumulate scientific state before `r01` exists.
3. A project with an active revision can continue from its scientific state without automatically creating a successor.
4. Scientific acts produce structured state and deliberative history, not document mutations.
5. An accepted decision remains visibly accepted-but-unmaterialized until the user explicitly requests materialization.
6. Materialization is bounded, auditable, and once-only for a given accepted decision.
7. Existing direct-document operations, lifecycle operations, manifests, receipts, audits, recovery behavior, and the existing `DELIBERATE` contract remain compatible.

## Scientific Thread abstraction

The persistent unit of scientific reasoning is a **Scientific Thread**: a durable unit of reasoning around one problem or decision. The term is intentionally retained because the repository evidence does not establish a stronger domain convention that would justify renaming it.

Project scientific state is a connected set or graph of Scientific Threads, not a linear event sequence. A thread groups related questions, hypotheses, assumptions, alternatives, unresolved issues, critiques, repairs, syntheses, and decisions. Threads may be explicitly related when reasoning crosses from one problem or decision to another; relatedness must not imply that the entire project history is relevant to every act.

One thread is active for a scientific act. Tutor and Conceptual Reviewer work primarily from the active thread and explicitly related threads, with bounded evidence selected for the act. Selective context recovery follows the same rule: it recovers the active thread and only the explicitly related portions needed to continue safely, rather than replaying or supplying full project history.

Accepted, eligible, unmaterialized threads and/or deltas are first-class materialization candidates. Materialization must identify the accepted candidates it uses, record the thread identities represented in the materialized result, and preserve the graph and its history after publication. The exact identity, relation, projection, and persistence schema belongs to specification and design.

## Scope

### 1. Explicit workflow mode and entry states

The public V2 contract will define the persistent scientific workflow as an explicit mode, distinct from ordinary direct-document operations and from the existing `DELIBERATE` operation. Every scientific act belongs to an active Scientific Thread; entry and continuation must expose enough thread identity and relationship state for the user to understand what reasoning is being continued without implying a linear project history.

The mode will expose conservative project-entry states. The exact public enum and response shape belong in the specification, but the proposal requires the system to distinguish at least:

- no managed revision with no scientific state: an idea may initialize scientific work;
- scientific state with no managed revision: scientific work exists before `r01`;
- an active managed revision with no scientific state: an existing document is available for conservative bootstrap;
- active scientific state associated with a revision or project lineage, including its active Scientific Thread and explicitly related threads;
- accepted materialization pending, including accepted eligible threads and/or deltas awaiting explicit materialization;
- inconsistent or unrecoverable authoritative scientific state.

Entry detection must not infer missing history, silently create a revision, or silently repair authoritative scientific records. Uncertainty and inconsistency must produce a safe state with an explicit recovery or reconciliation action.

### 2. Scientific-act classification

Scientific mode will classify user actions into structured acts rather than treating every request as a document instruction. Each classified act must be associated with an active Scientific Thread or remain unresolved until thread ownership is clarified. The initial vocabulary must cover, at minimum:

- idea/question construction;
- hypothesis, assumption, alternative, or unresolved-issue construction;
- critique and conceptual review;
- repair proposal and repair acceptance;
- decision acceptance, rejection, and retraction;
- explicit materialization request.

Classification must be conservative. Ambiguous requests must remain unresolved or request clarification. Existing direct-document and lifecycle intent precedence is unchanged: those routes retain precedence and are never reinterpreted as scientific acts.

### 3. Separation of scientific state from document state

Deliberation, critique, repair, acceptance, rejection, and retraction update only authoritative scientific state and deliberative history. They must never write under `proposals/`, create a revision, or alter a document manifest or document receipt.

The scientific record must be structured and auditable. It may contain Scientific Thread identities and explicit thread relationships, decisions, status transitions, bounded rationale summaries, actor/source identity, timestamps, causal references, revision/document identity references, and selected evidence references. It must not contain private reasoning, chain-of-thought, hidden prompts, or raw internal model traces.

Scientific Threads, their relationships, current thread state, and scientific events must be distinguishable from rebuildable document-derived indexes. The project state is a connected thread graph rather than a linear event sequence; event history may explain transitions, but must not force unrelated threads into one context or materialization unit. Existing document receipts remain records of document mutation; they are not repurposed as scientific reasoning history.

### 4. Tutor, Reviewer, and Planner responsibilities

- **Tutor:** supports conceptual construction and scientific deliberation using the active Scientific Thread plus explicitly related threads. It has no publication, document-edit, patch, revision-creation, or lifecycle authority.
- **Conceptual Reviewer:** evaluates coherence, unsupported claims, scope, assumptions, evidence references, and notation at the scientific-state level, primarily within the active thread and explicitly related threads. When it identifies a problem, the workflow supports a bounded repair loop: review finding → proposed repair → subsequent review or acceptance. The loop updates only scientific state and deliberative history.
- **Planner:** is limited to converting accepted, eligible scientific thread/delta selections into a bounded materialization action. It must not turn ordinary deliberation into an edit plan or publish as a side effect.
- **Existing document infrastructure:** once materialization is explicitly authorized, the existing Planner, Executor, document Reviewer, guarded publication path, manifests, receipts, and publication infrastructure are reused rather than bypassed.

### 5. Accepted decisions and materialization

The workflow must represent an accepted scientific decision that has not yet been materialized. This is a first-class state, not an implicit or transient condition.

Only `REQUEST_MATERIALIZATION`, or an unequivocal document order issued inside scientific mode, may initiate creation of `r01` or a successor revision. The system must not materialize merely because a Tutor or Reviewer approves an idea, because a repair is accepted, or because a scientific state is complete.

Materialization requirements:

- it identifies one or more accepted, eligible Scientific Threads and/or deltas, and does not implicitly include unrelated project threads;
- it records the selected thread identities, decision identities, and the source state/revision identity used;
- it hands off to the existing bounded V2 publication path;
- it is once-only for a given accepted decision: a repeated request must return the existing outcome or a safe recovery status and must not create a duplicate revision;
- a failure before a committed publication must remain retryable or recoverable without duplicating a revision;
- after successful publication, the scientific record records the resulting revision, materialization receipt reference, and the materialized thread identities without replacing the thread graph or scientific history.

With no existing revision, materialization may create `r01` from the accepted scientific state. With an active revision, it may create a successor only when explicitly requested and only from an eligible accepted delta; scientific continuation itself never creates a successor.

### 6. Selective context and summaries

Tutor and Reviewer inputs must use selective, bounded context appropriate to the scientific act. Context must be centered on the active Scientific Thread and may include only explicitly related threads and relevant evidence. It may reference relevant entries, structural/reference/symbol/concept indexes, document and revision hashes, and concise summaries. Full documents and unrelated project history must not be included by default.

Persisted evidence references must be sufficient for audit and later re-evaluation without becoming an accidental private-reasoning channel. The public result should expose concise active-thread and related-thread state summaries, thread/event identities, decisions, blockers, and next actions—not hidden reasoning or unbounded model output.

### 7. Conservative bootstrap from existing active proposals

When an active managed proposal exists but no scientific state exists, scientific mode may offer bootstrap from that proposal. Bootstrap must:

- use the current active managed proposal and its verified identity as bounded source evidence;
- preserve the distinction between observed document content and newly constructed scientific decisions;
- avoid inventing prior scientific history, intent, acceptance, rejection, or rationale;
- avoid creating a successor or changing the document;
- require the explicit scientific-mode entry action and report what was observed and what remains unknown.

If multiple active or conflicting sources make the starting state ambiguous, the workflow must block or request clarification rather than choose silently.

### 8. Persistence, versioning, recovery, and atomicity

Scientific Thread state, thread relationships, and events require explicit versioning, stable identities, atomic persistence, and recovery semantics compatible with the existing V2 safety model. The specification must define which thread and event records are authoritative, which projections are rebuildable, how graph relationships, event ordering, and deduplication work without reducing the project to a linear event sequence, and how interrupted transitions are detected.

The workflow must support:

- atomic state/event transitions or an equivalent recoverable transaction boundary;
- immutable event identity and auditable transition history;
- schema/version validation before use;
- fail-closed behavior for corrupt, conflicting, partial, or orphaned authoritative records;
- safe restart and recovery guidance after interruption;
- no invented publication, revision, or scientific decisions during recovery;
- consistency and self-audit coverage for scientific artifacts in addition to existing V2 artifacts.

Scientific Threads and state associated with withdrawn or restored revisions must be handled explicitly by the specification. Thread identity and graph relationships must never be silently attached to a different revision or silently discarded.

### 9. Metrics and rollout control

The workflow will expose operational and product metrics without persisting private reasoning. Metrics should cover scientific-mode entries, active and related thread selection, thread creation/relationship outcomes, act classifications, clarification/block rates, critique and repair outcomes, accepted/rejected/retracted decisions, accepted-but-unmaterialized threads/deltas, materialization attempts and outcomes, materialized thread identities, duplicate/idempotent requests, recovery and inconsistency events, context bounds, latency, and Tutor/Reviewer/Planner call counts.

An optional feature flag will gate scientific mode. When disabled, existing V2 behavior and public contracts remain unchanged; the system must not fall back by reinterpreting a scientific request as a direct document edit. Rollout and rollback must be reversible without deleting scientific history.

### 10. Compatibility with existing V2 behavior

The proposal must preserve:

- existing V2 operations and their public results;
- the existing `DELIBERATE` operation, which remains a bounded, assessment-only, non-persistent document deliberation route unless its current contract explicitly says otherwise. It is not the new persistent scientific workflow;
- direct-document route precedence and semantics;
- lifecycle precedence and semantics for withdrawal and restore;
- proposal manifests, document receipts, derived-state validation, consistency audits, self-audits, mutation locks, recovery markers, and defensive inconsistent-state behavior;
- the rule that no scientific route accepts caller-supplied offsets, hashes, patches, invented entry IDs, or full-document replacement as a shortcut around V2 boundaries;
- the rule that Scientific Thread identity and explicit thread relationships are authoritative scientific concepts, not substitutes for document revision identity or a reason to change direct-document routing.

## Functional requirements

1. The public V2 contract identifies persistent scientific workflow mode explicitly.
2. Scientific-mode entry detection returns a conservative, auditable state before any scientific mutation or document mutation.
3. The mode can initialize from an idea when no managed revision exists and must not require or create `r01` prematurely.
4. The mode can continue from existing scientific state with an active revision without automatically creating a successor.
5. Scientific-act classification is bounded, explicit, and clarification-seeking when ambiguous.
6. Direct-document and lifecycle operations are resolved with their current precedence and are never reclassified as scientific acts.
7. Deliberation, critique, repair, acceptance, rejection, and retraction write only scientific state/history and never write `proposals/` or create revisions.
8. Tutor output is advisory conceptual construction only and cannot authorize publication or document edits.
9. Reviewer findings can initiate a bounded conceptual repair loop that remains scientific-state-only until materialization is explicitly requested.
10. Planner invocation for scientific work is limited to an accepted delta selected for materialization.
11. `REQUEST_MATERIALIZATION` and unequivocal in-mode document orders are the only scientific entry points allowed to initiate `r01` or successor creation.
12. Materialization reuses the existing V2 Planner, Executor, document Reviewer, guarded publication, manifest, receipt, audit, and recovery infrastructure.
13. Accepted-but-unmaterialized decisions are visible, queryable, and remain eligible or blocked according to explicit state rules.
14. Materialization is idempotent/once-only per accepted decision and cannot duplicate a revision after retry or restart.
15. Scientific state/events are versioned, structured, auditable, atomically persisted, and free of private reasoning and hidden model traces.
16. Context supplied to scientific roles is selective and bounded, with evidence identity sufficient for audit.
17. Bootstrap from an active proposal is conservative and does not infer unobserved scientific history.
18. Corrupt, partial, conflicting, stale, or orphaned scientific artifacts fail closed or enter explicit recovery without inventing state.
19. Scientific artifacts participate in consistency/self-audit and recovery without corrupting existing V2 manifests or receipts.
20. Metrics and feature-flag behavior are observable, privacy-safe, and compatible with reversible rollout.
21. Scientific state is organized as persistent Scientific Threads around problems or decisions, with explicit relationships forming a connected project graph rather than a required linear event sequence.
22. Every scientific act has an active Scientific Thread or remains unresolved pending clarification; Tutor, Conceptual Reviewer, and selective context recovery use that thread plus explicitly related threads by default.
23. Accepted, eligible, unmaterialized Scientific Threads and/or deltas are visible and queryable as materialization candidates, and materialization records the thread identities it materializes.
24. Persistence, recovery, audit, and public summaries preserve thread identities and graph relationships without persisting chain-of-thought, hidden prompts, or raw internal model traces.

## Invariants

- No scientific act other than explicit materialization authorization may mutate document bytes, `proposals/`, managed revision files, document manifests, or document receipts.
- Existing direct-document and lifecycle routes retain precedence.
- Existing `DELIBERATE` remains contractually unchanged and is not silently upgraded to persistent scientific workflow behavior.
- Tutor and conceptual Reviewer have no publication or edit authority.
- Planner does not materialize unaccepted scientific deltas.
- An accepted scientific decision may remain unmaterialized, and its state is auditable.
- A given accepted decision cannot create more than one committed materialization outcome.
- Scientific history is not private reasoning storage.
- Recovery never invents a revision, receipt, decision, or causal link.
- Missing or corrupt authoritative scientific records are not silently rebuilt from guesses.
- Existing V2 lifecycle, manifest, receipt, audit, lock, and recovery guarantees remain valid.
- Scientific mode never accepts low-level caller-supplied mutation mechanics as an authority shortcut.
- A Scientific Thread is a unit of reasoning around one problem or decision; project scientific state is a connected graph/set of threads, not a linear event sequence.
- Thread relationships are explicit and bounded; an act does not inherit unrelated project history merely because it belongs to the same project.
- Tutor, Conceptual Reviewer, and selective context recovery operate primarily on the active thread and explicitly related threads.
- Materialization selects accepted, eligible, unmaterialized threads and/or deltas explicitly and records the thread identities represented in the committed materialization.
- Thread identity and graph state survive materialization; publication does not replace or erase scientific history.

## Non-goals

- Replacing or redesigning Paper Proposal V2 document mutation, publication, or lifecycle infrastructure.
- Changing the semantics of `DELIBERATE`, `REVIEW`, `CONCEPTUAL_REVISION`, or existing direct-document operations in this proposal phase.
- Automatic publication after Tutor, Reviewer, or acceptance outcomes.
- Automatic creation of `r01` or successors during scientific entry, bootstrap, deliberation, critique, repair, acceptance, rejection, or retraction.
- Persisting chain-of-thought, hidden prompts, private model traces, or unrestricted transcripts.
- Inferring historical scientific intent from an existing proposal.
- Defining provider/model selection or treating manual role files as runtime guarantees.
- Designing the final file layout, thread/event payload schema, graph representation, API field names beyond the required public mode and materialization boundary, or test implementation details; those belong to design/specification work.
- Introducing unrelated document authoring, collaboration, or publication workflows.

## Acceptance outcomes

The proposal is successful when the later implementation can demonstrate that:

1. Users can enter scientific mode safely from an idea, an existing active proposal, or an existing scientific state.
2. Entry state clearly communicates whether a revision exists, whether scientific work exists, whether an accepted delta awaits materialization, and whether recovery is required.
3. Scientific acts produce durable, structured, auditable state without changing proposal documents.
4. Tutor-guided construction and Reviewer-guided repair are useful without granting either role edit or publication authority.
5. Accepted decisions remain explicit until materialization is requested.
6. Materialization creates `r01` or a successor only through the existing V2 publication path and cannot duplicate its outcome.
7. Existing V2 operations, `DELIBERATE`, lifecycle behavior, manifests, receipts, audits, recovery, and defensive failure behavior pass unchanged compatibility expectations.
8. Scientific records remain privacy-safe and recoverable across restart, interruption, revision lifecycle changes, and feature-flag rollback.
9. Metrics make adoption, safety blocks, repair effectiveness, materialization conversion, and recovery burden observable without exposing private reasoning.
10. A project can resume from an active Scientific Thread, recover only explicitly related context, and preserve the connected thread graph across sessions without treating the project as a linear event replay.
11. Materialization identifies the accepted, eligible, unmaterialized thread/delta set it uses and records the resulting materialized thread identities while preserving the scientific graph and audit history.

## Risks and rollback

| Risk | Mitigation | Rollback posture |
|---|---|---|
| Scientific classification accidentally changes a direct V2 request | Preserve existing intent/lifecycle precedence; require explicit mode; fail closed on ambiguity | Disable the feature flag; direct V2 routes continue unchanged |
| Deliberation accidentally publishes or edits a document | Separate scientific state persistence from publication and hard-gate materialization | Stop scientific writes; preserve history; use existing V2 lifecycle only for already-created managed revisions |
| Duplicate revision after retry or restart | Stable decision/materialization identity, atomic transition, and idempotent replay | Return the recorded outcome or recovery state; never delete history to retry |
| Bootstrap invents scientific history | Record only verified observations and explicit user acts | Discard only an uncommitted bootstrap attempt, never erase authoritative events |
| Scientific state diverges from withdrawn/restored revisions | Bind references to revision/document identity and require explicit reconciliation | Block affected acts/materialization until reconciled |
| Corrupt or partial state is treated as recoverable when it is authoritative | Version and audit authoritative records separately from projections; fail closed | Preserve artifacts for diagnosis and use explicit recovery tooling |
| Persisted summaries expose private reasoning | Schema allowlists for public summaries/evidence and rejection of hidden traces | Disable the mode if privacy validation fails; retain only compliant records |
| New workflow increases operational complexity or support burden | Optional feature flag, explicit states, explicit thread boundaries, metrics, and bounded context | Disable new entry while retaining read-only diagnostic/recovery capability as specified |
| Thread graph is treated as a linear history or context expands to the whole project | Make the active-thread/explicit-related-thread rule and graph invariants explicit; bound recovery and role context | Disable scientific continuation/materialization if thread scope cannot be established; preserve authoritative history |
| Materialization omits a related accepted thread or records no thread provenance | Require explicit eligible-thread/delta selection and committed materialization thread identities | Return a safe blocked/recovery outcome; do not publish an unverifiable materialization |

Rollback must not silently reinterpret existing requests, delete scientific history, or mutate already-published documents. Any managed revision rollback remains governed by existing lifecycle rules.

## Proposal-to-spec handoff

The specification phase should turn this proposal into testable contracts by resolving:

1. the exact public mode, entry-state, scientific-act, decision, and materialization status vocabulary;
2. the authoritative state/event model, identity, ordering, causal-link, deduplication, and projection rules;
3. the Scientific Thread lifecycle and graph transition matrix for construction, thread relation, critique, repair, synthesis, acceptance, rejection, retraction, bootstrap, inconsistency, and recovery;
4. the exact boundary between unchanged `DELIBERATE` and persistent scientific mode;
5. the materialization eligibility, active-thread/related-thread selection, confirmation, once-only/idempotency, retry, thread-provenance, and post-publication rules;
6. the selective-context and privacy/redaction contract, including active-thread context recovery and explicit related-thread boundaries;
7. the interaction of Scientific Thread identity and relationships with active, withdrawn, restored, stale, and inconsistent revisions;
8. the public metrics and feature-flag behavior;
9. acceptance tests for no-publication guarantees, compatibility, atomicity, recovery, auditability, and defensive inconsistent-state handling.

No implementation is authorized by this proposal alone. The next phase is specification, followed by technical design only after the specification is approved.