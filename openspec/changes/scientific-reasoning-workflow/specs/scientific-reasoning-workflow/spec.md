# Scientific Reasoning Workflow Specification

## Purpose

Provide an explicit, persistent scientific reasoning workflow in Paper Proposal V2. The workflow SHALL preserve existing document and lifecycle behavior while allowing scientific work to be continued, audited, and explicitly materialized only when authorized.

## Requirements

### Requirement: Explicit scientific workflow routing

The public V2 contract MUST expose an explicit `SCIENTIFIC_WORKFLOW` mode. A request MUST enter persistent scientific workflow only when it explicitly selects that mode and no existing lifecycle or direct-document route has precedence. Existing lifecycle operations, direct-document operations, and their current results MUST retain their current precedence and semantics. A request that is ambiguous between a scientific act and an existing V2 route MUST be clarified or handled by the existing route; it MUST NOT be silently reinterpreted as a scientific act.

`DELIBERATE` MUST remain the existing bounded, assessment-only, non-persistent document deliberation operation. It MUST NOT create, update, query as, or resume a Scientific Thread. Direct V2 document operations, including `CONCEPTUAL_REVISION`, MUST remain distinct from scientific workflow materialization.

#### Scenario: Explicit scientific entry after route resolution

- GIVEN a request explicitly selects `SCIENTIFIC_WORKFLOW` and does not resolve to a lifecycle or direct-document operation
- WHEN V2 resolves the request
- THEN it SHALL enter the persistent scientific workflow
- AND it SHALL return a scientific-mode result rather than a document-operation result.

#### Scenario: Lifecycle route retains precedence

- GIVEN a request identifies a managed revision lifecycle action and also contains scientific terminology
- WHEN V2 resolves the request
- THEN it SHALL execute or clarify the lifecycle route under the existing lifecycle contract
- AND it MUST NOT create or mutate scientific state as a side effect.

#### Scenario: Existing DELIBERATE remains non-persistent

- GIVEN a user invokes `DELIBERATE` without selecting `SCIENTIFIC_WORKFLOW`
- WHEN V2 completes the assessment
- THEN it SHALL return the existing assessment-only outcome with zero document mutations
- AND it MUST NOT create a Scientific Thread, scientific event, or materialization candidate.

### Requirement: Conservative project entry resolution

The scientific workflow MUST resolve and return a conservative, auditable project-entry state before any scientific or document mutation. The public vocabulary MUST include `EMPTY_PROJECT`, `SCIENTIFIC_ONLY`, `ACTIVE_PROPOSAL`, `ACTIVE_SCIENTIFIC_PROJECT`, `MATERIALIZATION_PENDING`, `WITHDRAWN_ONLY`, `INCONSISTENT_PROJECT`, and `MULTIPLE_ACTIVE_REVISIONS`.

`EMPTY_PROJECT` SHALL mean no active managed revision and no authoritative scientific state. `SCIENTIFIC_ONLY` SHALL mean authoritative scientific state exists without an active managed revision. `ACTIVE_PROPOSAL` SHALL mean exactly one active managed revision exists without authoritative scientific state. `ACTIVE_SCIENTIFIC_PROJECT` SHALL mean authoritative scientific state exists and no accepted eligible materialization is pending. `MATERIALIZATION_PENDING` SHALL mean one or more accepted eligible unmaterialized decisions or threads exist. `WITHDRAWN_ONLY` SHALL mean managed history is withdrawn with no active managed revision. `INCONSISTENT_PROJECT` SHALL mean authoritative state cannot be safely validated or reconciled. `MULTIPLE_ACTIVE_REVISIONS` SHALL mean more than one active managed revision is detected.

The entry result MUST identify observed revision, scientific-state, active-thread, accepted-candidate, and recovery/reconciliation information that is applicable to the state. It MUST NOT infer missing history, silently repair authoritative records, or silently create a revision.

#### Scenario: Empty project begins with an idea

- GIVEN no active managed revision and no authoritative scientific state exist
- WHEN a user explicitly enters scientific workflow
- THEN the resolver SHALL return `EMPTY_PROJECT`
- AND the workflow MAY accept an explicit idea-construction act
- AND it MUST NOT create `r01`.

#### Scenario: Ambiguous revision sources block entry

- GIVEN more than one active managed revision is detected
- WHEN a user explicitly enters scientific workflow
- THEN the resolver SHALL return `MULTIPLE_ACTIVE_REVISIONS`
- AND it SHALL request clarification or reconciliation
- AND it MUST NOT select a revision or bootstrap state silently.

#### Scenario: Invalid authoritative state fails closed

- GIVEN scientific authoritative records are corrupt, partial, conflicting, stale in a safety-relevant way, or orphaned
- WHEN scientific entry is resolved
- THEN the resolver SHALL return `INCONSISTENT_PROJECT` with recovery or reconciliation guidance
- AND it MUST NOT reconstruct authoritative decisions, causal links, or thread relationships from guesses.

### Requirement: Scientific Threads and connected project state

A Scientific Thread MUST be a persistent unit of reasoning around one problem or decision. Each thread MUST have a stable identity, lifecycle state, auditable history, and explicit relationships to other threads when applicable. Project scientific state MUST represent a connected graph or set of Scientific Threads; it MUST NOT require a linear project-history replay or imply that every thread is relevant to every other thread.

Every scientific act MUST identify one active thread or remain unresolved pending clarification. Relationships MUST be explicit and bounded. Materialization and context selection MUST preserve thread identity and relationships rather than replacing them with a document revision identity.

#### Scenario: Related but bounded reasoning

- GIVEN a project has an active thread and a separate explicitly related thread
- WHEN a scientific act is performed on the active thread
- THEN the workflow SHALL retain both thread identities and their explicit relationship
- AND it MUST NOT treat unrelated project threads as act context merely because they share the project.

#### Scenario: Missing thread ownership is clarified

- GIVEN a scientific request could apply to multiple threads and no active-thread selection resolves the ambiguity
- WHEN the workflow classifies the request
- THEN it SHALL return an unresolved or clarification outcome
- AND it MUST NOT attach the act to an arbitrary thread.

### Requirement: Scientific-act and decision lifecycle

Scientific workflow MUST classify and persist structured acts for, at minimum: idea or question construction; hypothesis, assumption, alternative, or unresolved-issue construction; critique and conceptual review; repair proposal and repair acceptance; synthesis; decision acceptance, rejection, and retraction; and explicit materialization request.

The workflow MUST maintain an auditable lifecycle for thread synthesis and decisions. A decision MAY be accepted only through an explicit acceptance act. A retraction MUST preserve the prior decision and its history while making its current status retracted. A rejected or retracted decision MUST NOT remain eligible for materialization unless a subsequent explicit lifecycle transition makes an eligible decision available.

#### Scenario: Reviewer-guided repair remains a scientific lifecycle

- GIVEN a conceptual review records a finding for the active thread
- WHEN a user proposes and accepts a bounded repair
- THEN the workflow SHALL record the review, repair proposal, and repair acceptance as scientific history
- AND it MUST NOT publish or edit a proposal document.

#### Scenario: Accepted synthesis is pending, not published

- GIVEN a thread synthesis is explicitly accepted and is eligible for publication
- WHEN no materialization request is made
- THEN the decision SHALL remain accepted-but-unmaterialized
- AND no managed revision SHALL be created or changed.

### Requirement: Selective scientific role context

Tutor and Conceptual Reviewer MUST operate primarily on the active Scientific Thread plus only explicitly related threads and relevant evidence selected for the act. Selective context recovery MUST follow the same bounded rule. The roles MUST NOT receive full documents or unrelated project history by default.

Tutor and Conceptual Reviewer outputs SHALL be advisory scientific input only. Neither role SHALL have authority to publish, edit document bytes, create a revision, alter lifecycle state, or authorize materialization. A scientific Planner MAY prepare a bounded materialization action only for explicitly selected accepted eligible candidates; it MUST NOT convert ordinary deliberation into a document edit or publication.

#### Scenario: Bounded Tutor context

- GIVEN an active thread has one explicitly related thread and other unrelated threads
- WHEN Tutor is invoked for a scientific act
- THEN its supplied context SHALL be limited to the active thread, the explicitly related thread when relevant, and act-relevant evidence
- AND it MUST NOT include unrelated thread history by default.

#### Scenario: Role approval does not publish

- GIVEN Tutor or Conceptual Reviewer returns a favorable assessment
- WHEN the user has not explicitly requested materialization
- THEN the workflow MAY persist the assessment or subsequent scientific act
- AND it MUST NOT create, modify, or publish a managed proposal revision.

### Requirement: Deliberative write isolation

Every deliberative scientific path, including construction, critique, review, repair, synthesis, acceptance, rejection, retraction, clarification, and context recovery, MUST write only scientific state and scientific history when it writes at all. These paths MUST NOT write under `proposals/`, create or alter a managed revision, alter a document manifest, or alter a document receipt.

Only a successful explicitly authorized materialization may enter the existing document publication path. Existing document receipts MUST remain records of document mutation and MUST NOT be repurposed as scientific reasoning history.

#### Scenario: Scientific acceptance performs no document write

- GIVEN a user accepts a scientific decision
- WHEN the acceptance transition completes
- THEN scientific state and audit history MAY change
- AND `proposals/`, managed revision bytes, document manifests, and document receipts MUST remain unchanged.

### Requirement: Accepted materialization candidates

Accepted, eligible, unmaterialized decisions, threads, and deltas MUST be first-class, visible, and queryable materialization candidates. The workflow MUST expose their identities, eligibility or blocking status, and concise next actions. Candidate status MUST remain durable across sessions and MUST NOT be inferred merely from a favorable Tutor or Reviewer assessment.

#### Scenario: Pending candidates are visible on re-entry

- GIVEN an accepted eligible thread or delta has not been materialized
- WHEN the user re-enters scientific workflow
- THEN the resolver SHALL return `MATERIALIZATION_PENDING`
- AND the result SHALL identify the pending candidate without claiming that it was published.

### Requirement: Explicit, provenance-preserving materialization

Only `REQUEST_MATERIALIZATION`, or an unequivocal document order issued inside explicitly selected scientific workflow, MAY initiate `r01` or a successor revision from scientific state. Materialization MUST require explicit selection of one or more accepted eligible threads and/or deltas. It MUST NOT implicitly include unrelated threads.

A materialization attempt MUST record the selected thread and decision identities, the source scientific state, and applicable source document or revision identity. It MUST hand off to the existing V2 Planner, Executor, document Reviewer, guarded publication, manifest, receipt, audit, and recovery path; it MUST NOT bypass those contracts. On successful publication, scientific state MUST record the resulting revision and materialization receipt reference while preserving the thread graph and scientific history.

#### Scenario: First revision is explicitly materialized

- GIVEN `SCIENTIFIC_ONLY` state has an accepted eligible candidate
- WHEN the user explicitly requests materialization and selects that candidate
- THEN the workflow MAY create `r01` only through the existing guarded V2 publication path
- AND the committed materialization record SHALL identify the selected thread and decision identities.

#### Scenario: Unrelated thread is excluded

- GIVEN two accepted threads exist and only one is selected for materialization
- WHEN materialization is requested
- THEN the workflow SHALL use and record only the selected eligible candidate set
- AND it MUST NOT silently include the unselected thread.

### Requirement: Once-only materialization and recovery

A given accepted decision MUST produce at most one committed materialization outcome. Repeated requests for the same accepted decision MUST return the recorded outcome or an explicit safe recovery status; they MUST NOT create a duplicate revision. A failure before committed publication MUST remain retryable or recoverable without duplicating a revision or inventing a receipt.

#### Scenario: Repeated request is idempotent

- GIVEN a materialization for an accepted decision has committed successfully
- WHEN the same materialization is requested again, including after restart
- THEN the workflow SHALL return the existing committed outcome or its reference
- AND it MUST NOT create another successor revision.

#### Scenario: Interrupted materialization is recoverable

- GIVEN a materialization is interrupted before its publication outcome is committed
- WHEN the workflow is resumed
- THEN it SHALL provide a retry or recovery action based on validated recorded state
- AND it MUST NOT claim a revision, receipt, or completed materialization that is not evidenced.

### Requirement: Conservative bootstrap and revision lifecycle compatibility

From `ACTIVE_PROPOSAL`, scientific workflow MAY offer bootstrap only after explicit scientific-mode entry. Bootstrap MUST use verified active-proposal identity as bounded observed evidence, distinguish observations from newly created scientific decisions, report unknown prior history, and MUST NOT change the document or create a successor.

Withdrawal and restore MUST retain their existing precedence and semantics. Scientific thread identity and relationships associated with withdrawn, restored, stale, or missing revisions MUST NOT be silently discarded, reassigned to another revision, or treated as reconciled without explicit validated reconciliation. Affected scientific acts or materialization MUST block or request recovery when their required revision evidence is unavailable or inconsistent.

#### Scenario: Bootstrap does not invent history

- GIVEN exactly one active managed proposal exists and no scientific state exists
- WHEN a user explicitly enters scientific workflow and requests bootstrap
- THEN the workflow MAY record verified observations from that proposal
- AND it MUST NOT infer prior decisions, acceptance, rejection, rationale, or scientific history.

#### Scenario: Withdrawn evidence blocks unsafe materialization

- GIVEN a selected materialization candidate depends on a withdrawn or inconsistent revision reference
- WHEN materialization is requested
- THEN the workflow SHALL return a blocked or reconciliation outcome
- AND it MUST NOT attach the thread to another revision or publish from unvalidated evidence.

### Requirement: Authoritative persistence, audit, and privacy

Scientific authoritative records MUST be structured, versioned, atomically persisted or protected by an equivalent recoverable transaction boundary, and validated before use. They MUST preserve stable thread, event, decision, relationship, and materialization identities; immutable event history; auditable transition order and causal references; and deduplication sufficient to enforce once-only materialization. Rebuildable projections MUST be distinguishable from authoritative records.

The workflow MUST fail closed for corrupt, conflicting, partial, or orphaned authoritative records and MUST provide safe restart or recovery guidance after interruption. Consistency audit and self-audit MUST cover scientific artifacts without corrupting or weakening existing V2 audits, manifests, receipts, locks, and recovery markers. Recovery MUST NOT invent a scientific decision, causal link, revision, receipt, or publication.

Persisted scientific records and public summaries MUST contain only approved structured summaries and evidence references. They MUST NOT contain chain-of-thought, hidden prompts, private reasoning, raw internal model traces, or unrestricted transcripts.

#### Scenario: Atomic scientific transition survives interruption

- GIVEN a scientific transition is interrupted during persistence
- WHEN the project is next opened
- THEN the workflow SHALL expose only a validated committed transition or an explicit recovery state
- AND it MUST NOT expose a partially committed decision as accepted.

#### Scenario: Privacy-safe audit record

- GIVEN a scientific act is persisted and later audited
- WHEN its public summary and audit references are returned
- THEN they SHALL identify the relevant thread, event, decision, and bounded evidence as applicable
- AND they MUST NOT expose hidden prompts, private reasoning, or raw model traces.

### Requirement: Feature gating, metrics, and compatibility regressions

Scientific workflow MAY be controlled by a feature flag. When the flag is disabled, existing V2 public behavior and contracts MUST remain unchanged. A scientific-mode request while disabled MUST return an explicit unavailable outcome; it MUST NOT fall back by reinterpreting the request as a direct document edit. Enabling, disabling, or rolling back the feature MUST NOT delete scientific history or alter published documents.

The workflow MUST expose privacy-safe operational metrics for scientific-mode entries; entry states; active and related-thread selection; thread creation and relationships; act classifications; clarification and block outcomes; critique and repair outcomes; accepted, rejected, retracted, and pending decisions; materialization attempts, outcomes, selected/materialized thread identities, and idempotent duplicates; recovery and inconsistency events; context bounds; latency; and Tutor, Reviewer, and Planner call counts.

Compatibility verification MUST demonstrate that existing V2 operations, `DELIBERATE`, direct-document routing, withdrawal/restore lifecycle routing, manifests, receipts, audits, recovery, locks, and defensive inconsistent-state behavior remain unchanged outside explicitly selected scientific workflow.

#### Scenario: Disabled feature does not alter document routing

- GIVEN scientific workflow is disabled
- WHEN a user explicitly requests scientific workflow
- THEN V2 SHALL return an explicit unavailable result
- AND it MUST NOT execute a direct-document operation or mutate a proposal.

#### Scenario: Existing direct document request remains unchanged

- GIVEN a request invokes an existing direct-document operation without selecting scientific workflow
- WHEN V2 resolves and executes it
- THEN it SHALL follow the pre-existing direct-document route and result contract
- AND it MUST NOT create scientific state solely because the request contains scientific language.

## Next Step

Technical design follows only after this specification is approved.
