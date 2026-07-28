import type { EditPlan } from './types.js';

export const SCIENTIFIC_WORKFLOW_OPERATION = 'SCIENTIFIC_WORKFLOW' as const;

export type ScientificWorkflowOperation = typeof SCIENTIFIC_WORKFLOW_OPERATION;
export type ScientificWorkflowPublicStatus =
	| 'ready'
	| 'recorded'
	| 'needs_clarification'
	| 'blocked'
	| 'materialized'
	| 'recovery_required'
	| 'unavailable';
export type ProjectEntryState =
	| 'EMPTY_PROJECT'
	| 'SCIENTIFIC_ONLY'
	| 'ACTIVE_PROPOSAL'
	| 'ACTIVE_SCIENTIFIC_PROJECT'
	| 'MATERIALIZATION_PENDING'
	| 'WITHDRAWN_ONLY'
	| 'INCONSISTENT_PROJECT'
	| 'MULTIPLE_ACTIVE_REVISIONS';
export type ScientificActKind =
	| 'CONSTRUCT_IDEA'
	| 'CONSTRUCT_QUESTION'
	| 'CONSTRUCT_HYPOTHESIS'
	| 'CONSTRUCT_ASSUMPTION'
	| 'CONSTRUCT_ALTERNATIVE'
	| 'RAISE_UNRESOLVED_ISSUE'
	| 'RELATE_THREADS'
	| 'REQUEST_TUTOR'
	| 'REQUEST_CONCEPTUAL_REVIEW'
	| 'SYNTHESIZE'
	| 'MODIFY_SYNTHESIS'
	| 'ACCEPT_DECISION'
	| 'REJECT_DECISION'
	| 'RETRACT_DECISION'
	| 'REQUEST_MATERIALIZATION'
	| 'BOOTSTRAP_FROM_ACTIVE_PROPOSAL'
	| 'PROPOSE_RECONCILIATION'
	| 'ACCEPT_RECONCILIATION';
export type ScientificThreadStatus =
	| 'OPEN'
	| 'UNDER_REVIEW'
	| 'REPAIRED'
	| 'ACCEPTED_UNMATERIALIZED'
	| 'REJECTED'
	| 'RETRACTED'
	| 'BLOCKED';
export type ScientificDecisionStatus = 'ACCEPTED_UNMATERIALIZED' | 'MATERIALIZED' | 'RETRACTED';
export type ScientificEventType =
	| 'THREAD_CREATED'
	| 'THREAD_SELECTED'
	| 'THREAD_ACTIVATED'
	| 'THREAD_RELATED'
	| 'TUTOR_ASSESSED'
	| 'CONCEPTUAL_REVIEW_RECORDED'
	| 'REPAIR_PROPOSED'
	| 'SYNTHESIS_REOPENED'
	| 'DECISION_ACCEPTED'
	| 'DECISION_REJECTED'
	| 'DECISION_RETRACTED'
	| 'MATERIALIZATION_RESERVED'
	| 'MATERIALIZATION_PLANNED'
	| 'MATERIALIZATION_COMMITTED';
export type ThreadRelationKind = 'RELATED' | 'SUPPORTS' | 'CHALLENGES' | 'DEPENDS_ON';
export type ThreadSynthesisStatus = 'DRAFT' | 'REVIEWED' | 'REPAIR_REQUIRED' | 'ACCEPTED' | 'REJECTED' | 'RETRACTED';
export type MaterializationState =
	| 'RESOLVING'
	| 'PREPARED'
	| 'PLANNING'
	| 'EXECUTING_CANDIDATE'
	| 'REVIEWING_DOCUMENT'
	| 'PUBLISHING'
	| 'COMMITTED'
	| 'BLOCKED'
	| 'RECOVERY_REQUIRED';
export type MaterializationPlanKind = 'CREATE_R01' | 'CREATE_SUCCESSOR';
export type ScientificActorKind =
	| 'USER'
	| 'SYSTEM'
	| 'TUTOR'
	| 'CONCEPTUAL_REVIEWER'
	| 'PLANNER'
	| 'EXECUTOR'
	| 'DOCUMENT_REVIEWER';
export type ConceptualReviewOutcome = 'PASS' | 'REPAIR_REQUIRED' | 'BLOCK' | 'NEEDS_CLARIFICATION';
export type ScientificResolutionStatus = 'resolved' | 'needs_clarification' | 'blocked';
export type ScientificAuditStatus = 'PASS' | 'WARN' | 'FAIL' | 'NOT_RUN';

export type ScientificThreadId = string;
export type ScientificDecisionId = string;
export type ScientificEventId = string;
export type ThreadRelationId = string;
export type ThreadSynthesisId = string;

export type RevisionEvidence = {
	filename: string;
	revision: string;
	documentSha256: string;
};
export type EvidenceReference = { kind: string; id: string; sha256?: string };
export type PublicBlocker = { code: string; message: string; nextAction?: string };
export type ScientificPrivacy = { contentClass: 'PUBLIC_SUMMARY_ONLY'; redactionVersion: 1 };
export type ProjectEntryRecovery = { required: boolean; code?: string; action?: string };
export type ProjectEntryBootstrap = {
	status: 'available';
	source: RevisionEvidence;
	observations: EvidenceReference[];
	unknownHistory: true;
};
export type ProjectEntry = {
	state: ProjectEntryState;
	activeRevision?: RevisionEvidence;
	activeThreadId?: ScientificThreadId;
	relatedThreadIds: ScientificThreadId[];
	pendingCandidateIds: ScientificDecisionId[];
	/** Present for validated pending entries; legacy resolver consumers may continue using IDs. */
	activeThread?: ThreadSummary;
	relatedThreads?: ThreadSummary[];
	pendingCandidates?: MaterializationCandidateSummary[];
	blockers?: PublicBlocker[];
	nextAction?: string | null;
	recovery: ProjectEntryRecovery;
	auditEvidence: string[];
	bootstrap?: ProjectEntryBootstrap;
};
export type ScientificActor = { kind: ScientificActorKind };

export type ThreadRelation = {
	relationId: ThreadRelationId;
	kind: ThreadRelationKind;
	fromThreadId: ScientificThreadId;
	toThreadId: ScientificThreadId;
	createdEventId: ScientificEventId;
};
export type ScientificThread = {
	threadId: ScientificThreadId;
	version: 1;
	status: ScientificThreadStatus;
	title: string;
	summary: string;
	createdEventId: ScientificEventId;
	headEventId: ScientificEventId;
	revisionEvidence?: RevisionEvidence;
	relationIds: ThreadRelationId[];
	decisionIds: ScientificDecisionId[];
};
export type ScientificDecision = {
	decisionId: ScientificDecisionId;
	threadId: ScientificThreadId;
	acceptedEventId: ScientificEventId;
	acceptedSynthesisDigest: string;
	acceptedBy: { kind: 'USER' };
	state: ScientificDecisionStatus;
	sourceEventIds: ScientificEventId[];
};
export type FrozenDecisionSelection = {
	policyVersion: 1;
	decisionIds: ScientificDecisionId[];
	acceptedEventIds: ScientificEventId[];
	selectionKey: string;
};
export type MaterializationReservedDecision = Pick<ScientificDecision, 'decisionId' | 'threadId' | 'acceptedEventId' | 'acceptedSynthesisDigest' | 'sourceEventIds'> & {
	revisionEvidence?: RevisionEvidence;
};
export type MaterializationRecord = {
	schemaVersion: 1;
	materializationId: string;
	state: MaterializationState;
	frozenSelection: FrozenDecisionSelection;
	selectedDecisions: MaterializationReservedDecision[];
	/** Absent only for reservations persisted before executable payload support. */
	plan?: MaterializationPlan;
};
export type MaterializationClaimProvenance = {
	claimId: string;
	decisionId: ScientificDecisionId;
	threadId: ScientificThreadId;
	acceptedEventId: ScientificEventId;
	acceptedSynthesisDigest: string;
	summary: string;
};
export type CanonicalProposalMetadata = {
	schemaVersion: 1;
	title: string;
	sectionHeading: string;
};
export type FrozenPatchPreconditions = {
	expectedRevision: RevisionEvidence;
	baseDocumentSha256: string;
	anchorEntryId: string;
	anchorTextSha256: string;
};
export type FrozenEditPlan = {
	order: number;
	plan: EditPlan;
	preconditions: FrozenPatchPreconditions;
};
export type CreateR01PayloadV1 = {
	kind: 'CREATE_R01';
	payloadVersion: 1;
	markdown: string;
	target: { filename: 'research-concept-r01.md'; revision: 'r01' };
	canonicalMetadata: CanonicalProposalMetadata;
};
export type CreateSuccessorPayloadV1 = {
	kind: 'CREATE_SUCCESSOR';
	payloadVersion: 1;
	expectedBase: RevisionEvidence;
	patches: readonly FrozenEditPlan[];
};
export type MaterializationPlan = {
	schemaVersion: 1;
	materializationId: string;
	selectionKey: string;
	operation: MaterializationPlanKind;
	frozenSelection: FrozenDecisionSelection;
	source?: RevisionEvidence;
	expectedRevisionIdentity?: RevisionEvidence;
	payload: CreateR01PayloadV1 | CreateSuccessorPayloadV1;
	claimProvenance: MaterializationClaimProvenance[];
	digest: string;
};
export type ThreadSynthesis = {
	synthesisId: ThreadSynthesisId;
	threadId: ScientificThreadId;
	digest: string;
	status: ThreadSynthesisStatus;
	summary: string;
	reviewEventId?: ScientificEventId;
};
export type ScientificSynthesisCandidate = ThreadSynthesis & {
	tutorEventId: ScientificEventId;
};
export type StructuredConceptualFinding = {
	findingId: string;
	candidateSynthesisId: ThreadSynthesisId;
	candidateSynthesisDigest: string;
	category: 'COHERENCE' | 'SCOPE' | 'EVIDENCE' | 'NOTATION' | 'ASSUMPTION';
	evidence: EvidenceReference[];
	requiredCorrection: string;
	constraints: string[];
};
export type ScientificAct = {
	kind: ScientificActKind;
	threadId?: ScientificThreadId;
	relatedThreadIds: ScientificThreadId[];
};
export type ScientificActResolution =
	| { status: 'resolved'; act: ScientificActKind; requestedThreadId?: ScientificThreadId; relatedThreadIds: ScientificThreadId[] }
	| { status: 'needs_clarification'; question: string }
	| { status: 'blocked'; code: string };
export type BoundedScientificSeed = {
	title: string;
	summary: string;
	actor: { kind: 'USER' };
};
export type ThreadTransitionIntent = {
	type: Extract<ScientificEventType, 'THREAD_CREATED' | 'THREAD_SELECTED' | 'THREAD_ACTIVATED' | 'THREAD_RELATED'>;
	eventId: ScientificEventId;
	threadId: ScientificThreadId;
	activeThreadId: ScientificThreadId;
	causalEventIds: ScientificEventId[];
	relatedThreadIds: ScientificThreadId[];
	seed?: BoundedScientificSeed;
};
export type ThreadResolution =
	| { status: 'created'; activeThread: ScientificThread; intents: ThreadTransitionIntent[] }
	| { status: 'continued'; activeThread: ScientificThread; intents: [] }
	| { status: 'selected'; activeThread: ScientificThread; intents: ThreadTransitionIntent[] }
	| { status: 'needs_clarification'; code: 'THREAD_SELECTION_AMBIGUOUS' | 'THREAD_REQUIRED'; question: string }
	| { status: 'blocked'; code: string; blockers: PublicBlocker[] };
export type ScientificEvent = {
	schemaVersion: 1;
	eventId: ScientificEventId;
	sequence: number;
	occurredAt: string;
	actor: ScientificActor;
	type: ScientificEventType;
	threadId?: ScientificThreadId;
	causalEventIds: ScientificEventId[];
	payload: Record<string, unknown>;
	evidence: EvidenceReference[];
	privacy: ScientificPrivacy;
};

export type ScientificWorkflowRequest = {
	operation: ScientificWorkflowOperation;
	instruction: string;
	activeThreadId?: ScientificThreadId;
	relatedThreadIds?: ScientificThreadId[];
	scientificAct?: ScientificActKind;
	candidateIds?: ScientificDecisionId[];
	idempotencyKey?: string;
};
export type ThreadSummary = Pick<ScientificThread, 'threadId' | 'status' | 'title' | 'summary'>;
export type ScientificContextLimits = {
	maxRelatedThreads: number;
	maxEvidence: number;
	maxDocumentFragments: number;
	maxBytes: number;
};
export type ScientificDocumentFragment = {
	entryId: string;
	type: string;
	text: string;
	textSha256: string;
	headingPath: string[];
	revision: RevisionEvidence;
};
export type ScientificRoleContext = {
	schemaVersion: 1;
	act: ScientificActKind;
	activeThread: ThreadSummary;
	relatedThreads: ThreadSummary[];
	evidence: EvidenceReference[];
	documentFragments: ScientificDocumentFragment[];
	limits: ScientificContextLimits;
	byteCount: number;
	privacy: ScientificPrivacy;
};
export type MaterializationCandidateSummary = {
	decisionId: ScientificDecisionId;
	threadId: ScientificThreadId;
	state: ScientificDecisionStatus;
	eligibility: 'eligible' | 'blocked';
	blockers: PublicBlocker[];
};
export type ScientificMetricsDelta = {
	routeStage: ScientificWorkflowOperation;
	bypassedStages: Array<'LIFECYCLE' | 'DIRECT_DOCUMENT' | 'DELIBERATE'>;
};
export type ScientificWorkflowPublicResult = {
	status: ScientificWorkflowPublicStatus;
	operation: ScientificWorkflowOperation;
	routeStage: ScientificWorkflowOperation;
	entryState: ProjectEntryState | null;
	activeThread?: ThreadSummary;
	relatedThreads: ThreadSummary[];
	candidates: MaterializationCandidateSummary[];
	eventId?: ScientificEventId;
	decisionId?: ScientificDecisionId;
	blockers: PublicBlocker[];
	nextAction: string | null;
	auditStatus: ScientificAuditStatus;
	selfAuditStatus: ScientificAuditStatus;
	metrics: ScientificMetricsDelta;
};
