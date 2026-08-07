import type { EditAction, EditPlan } from './types.js';

/**
 * The vocabulary of a managed revision: what a revision is, what it was published from,
 * and the frozen payload that produced it. Everything here is reachable from the ordinary
 * publication path (CREATE_INITIAL_REVISION and CREATE_SUCCESSOR) and stays reachable
 * whether or not a durable deliberation record exists alongside it.
 */

/** Opaque identifiers minted by whatever recorded the decision a revision claims to carry. */
export type ScientificThreadId = string;
export type ScientificDecisionId = string;
export type ScientificEventId = string;

export type RevisionEvidence = {
	filename: string;
	revision: string;
	/** Stable lifecycle-v1 identity when this is explicit authority rather than a legacy projection. */
	revisionId?: string;
	baseDocumentId?: string;
	lineage?: { sourceKind: 'BASE_DOCUMENT'|'REVISION'; sourceId: string; sourceContentHash: string };
	documentSha256: string;
};

export type MaterializationPlanKind = 'CREATE_R01' | 'CREATE_SUCCESSOR';

export type FrozenDecisionSelection = {
	policyVersion: 1;
	decisionIds: ScientificDecisionId[];
	acceptedEventIds: ScientificEventId[];
	selectionKey: string;
};

export type MaterializationClaimProvenance = {
	claimId: string;
	decisionId: ScientificDecisionId;
	threadId: ScientificThreadId;
	acceptedEventId: ScientificEventId;
	acceptedSynthesisDigest: string;
	summary: string;
	/** Present only when the accepted decision carries a real, single-locus structured edit (see `parseProposedEdit`). Absent decisions fall back to the pre-existing summary annotation. */
	proposedEdit?: EditAction;
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
