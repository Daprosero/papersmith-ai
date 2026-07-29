import { createHash } from 'node:crypto';
import { InitialRevisionRenderer } from './initial-revision-renderer.js';
import { SuccessorEditPlanner } from './successor-edit-planner.js';
import type {
	CanonicalProposalMetadata,
	MaterializationClaimProvenance,
	MaterializationPlan,
	MaterializationRecord,
	RevisionEvidence,
	ScientificDecision,
	ScientificEvent,
	ScientificThread,
} from './scientific-domain.js';
import type { ScientificState, ScientificStateStore } from './scientific-state-store.js';
import type { DocumentState, LifecycleRevision, MaterializationResult, WorkspaceLifecycleState } from './types.js';
import { LifecycleService } from './lifecycle-service.js';

export type MaterializationPlannerInput = {
	record: MaterializationRecord;
	state: ScientificState;
	/** A preloaded immutable source state; the planner never reads a workspace. */
	source?: DocumentState;
	/** Required only by the deterministic CREATE_R01 renderer. */
	canonicalMetadata?: CanonicalProposalMetadata;
	maxClaims?: number;
	maxSummaryBytes?: number;
};

export type MaterializationPlannerResult =
	| { status: 'ready'; plan: MaterializationPlan }
	| { status: 'blocked'; code: string };

const SHA256 = /^[0-9a-f]{64}$/;
const DEFAULT_MAX_CLAIMS = 8;
const DEFAULT_MAX_SUMMARY_BYTES = 16_000;

const digest = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const sameEvidence = (left: RevisionEvidence, right: RevisionEvidence) => left.filename === right.filename && left.revision === right.revision && left.documentSha256 === right.documentSha256;
const sourceEvidence = (source: DocumentState): RevisionEvidence => ({ filename: source.filename, revision: source.revision, documentSha256: source.documentSha256 });
const equalJson = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

function isSortedUnique(ids: string[]) {
	return ids.length > 0 && ids.every((id, index) => /^[A-Za-z0-9_-]{1,128}$/.test(id) && (index === 0 || ids[index - 1] < id));
}

function sourceFor(selected: MaterializationRecord['selectedDecisions'], supplied?: DocumentState): { operation: MaterializationPlan['operation']; source?: RevisionEvidence; base?: DocumentState } | undefined {
	const evidence = selected.map((decision) => decision.revisionEvidence);
	if (evidence.every((value) => value === undefined)) return supplied === undefined ? { operation: 'CREATE_R01' } : undefined;
	if (evidence.some((value) => value === undefined) || !supplied) return undefined;
	const expected = evidence[0]!;
	const actual = sourceEvidence(supplied);
	if (!evidence.every((value) => sameEvidence(value!, expected)) || !sameEvidence(actual, expected)) return undefined;
	return { operation: 'CREATE_SUCCESSOR', source: expected, base: supplied };
}

function claimFor(decision: ScientificDecision, thread: ScientificThread, events: ScientificEvent[]): MaterializationClaimProvenance | undefined {
	const accepted = events.find((event) => event.eventId === decision.acceptedEventId);
	if (!accepted || accepted.type !== 'DECISION_ACCEPTED' || accepted.actor.kind !== 'USER' || accepted.threadId !== decision.threadId || accepted.payload.decisionId !== decision.decisionId || accepted.payload.synthesisDigest !== decision.acceptedSynthesisDigest || accepted.payload.status !== 'ACCEPTED_UNMATERIALIZED') return undefined;
	const tutor = decision.sourceEventIds
		.map((eventId) => events.find((event) => event.eventId === eventId))
		.find((event) => event?.type === 'TUTOR_ASSESSED' && event.threadId === decision.threadId && event.payload.synthesisDigest === decision.acceptedSynthesisDigest);
	if (!tutor || typeof tutor.payload.summary !== 'string' || tutor.payload.summary.length === 0 || tutor.payload.summary.length > DEFAULT_MAX_SUMMARY_BYTES) return undefined;
	return {
		claimId: digest({ decisionId: decision.decisionId, acceptedEventId: decision.acceptedEventId, synthesisDigest: decision.acceptedSynthesisDigest }),
		decisionId: decision.decisionId,
		threadId: thread.threadId,
		acceptedEventId: decision.acceptedEventId,
		acceptedSynthesisDigest: decision.acceptedSynthesisDigest,
		summary: tutor.payload.summary,
	};
}

export function materializationPlanDigest(plan: Omit<MaterializationPlan, 'digest'>) {
	return digest(plan);
}

/** Validates only supported frozen payloads; it never upgrades or derives one. */
export function validateMaterializationPlan(plan: unknown, record: Pick<MaterializationRecord, 'materializationId' | 'frozenSelection'>): plan is MaterializationPlan {
	if (!plan || typeof plan !== 'object') return false;
	const candidate = plan as MaterializationPlan;
	if (candidate.schemaVersion !== 1 || candidate.materializationId !== record.materializationId || candidate.selectionKey !== record.frozenSelection.selectionKey || !equalJson(candidate.frozenSelection, record.frozenSelection) || !SHA256.test(candidate.digest) || candidate.digest !== materializationPlanDigest({ ...candidate, digest: undefined } as unknown as Omit<MaterializationPlan, 'digest'>)) return false;
	if (!Array.isArray(candidate.claimProvenance) || candidate.claimProvenance.length !== record.frozenSelection.decisionIds.length || candidate.claimProvenance.some((claim, index) => claim.decisionId !== record.frozenSelection.decisionIds[index] || claim.acceptedEventId !== record.frozenSelection.acceptedEventIds[index] || !claim.summary.trim())) return false;
	if (candidate.operation === 'CREATE_R01') {
		const payload = candidate.payload;
		return payload.kind === 'CREATE_R01' && payload.payloadVersion === 1 && candidate.source === undefined && candidate.expectedRevisionIdentity === undefined
			&& typeof payload.markdown === 'string' && payload.markdown.trim().length > 0
			&& payload.target.filename === 'research-concept-r01.md' && payload.target.revision === 'r01'
			&& payload.canonicalMetadata.schemaVersion === 1 && payload.canonicalMetadata.title.trim().length > 0 && payload.canonicalMetadata.sectionHeading.trim().length > 0;
	}
	if (candidate.operation !== 'CREATE_SUCCESSOR') return false;
	const payload = candidate.payload;
	if (payload.kind !== 'CREATE_SUCCESSOR' || payload.payloadVersion !== 1 || !candidate.source || !candidate.expectedRevisionIdentity || !sameEvidence(candidate.source, candidate.expectedRevisionIdentity) || !sameEvidence(payload.expectedBase, candidate.source) || !Array.isArray(payload.patches) || payload.patches.length === 0) return false;
	return payload.patches.every((patch, index) => patch.order === index + 1
		&& patch.plan.planVersion === '2' && patch.plan.documentSha256 === candidate.source!.documentSha256
		&& patch.preconditions.baseDocumentSha256 === candidate.source!.documentSha256
		&& sameEvidence(patch.preconditions.expectedRevision, candidate.source!)
		&& typeof patch.preconditions.anchorEntryId === 'string' && SHA256.test(patch.preconditions.anchorTextSha256)
		&& patch.plan.actions.length > 0);
}

/** Sole owner of operation selection and atomic persistence of executable frozen payloads. */
export class MaterializationPlanner {
	constructor(private readonly store: Pick<ScientificStateStore, 'persistMaterializationPlan'>) {}

	async plan(input: MaterializationPlannerInput): Promise<MaterializationPlannerResult> {
		const maxClaims = input.maxClaims ?? DEFAULT_MAX_CLAIMS;
		const maxSummaryBytes = input.maxSummaryBytes ?? DEFAULT_MAX_SUMMARY_BYTES;
		const { record, state } = input;
		if (!Number.isInteger(maxClaims) || maxClaims < 1 || !Number.isInteger(maxSummaryBytes) || maxSummaryBytes < 1) return { status: 'blocked', code: 'MATERIALIZATION_PLAN_BUDGET_INVALID' };
		if (record.state !== 'RESOLVING' || record.frozenSelection.policyVersion !== 1 || !isSortedUnique(record.frozenSelection.decisionIds) || record.selectedDecisions.length !== record.frozenSelection.decisionIds.length || record.frozenSelection.acceptedEventIds.length !== record.frozenSelection.decisionIds.length || !SHA256.test(record.frozenSelection.selectionKey)) return { status: 'blocked', code: 'MATERIALIZATION_FROZEN_SELECTION_INVALID' };
		if (record.selectedDecisions.length > maxClaims) return { status: 'blocked', code: 'MATERIALIZATION_PLAN_BUDGET_EXCEEDED' };
		const source = sourceFor(record.selectedDecisions, input.source);
		if (!source) return { status: 'blocked', code: 'MATERIALIZATION_SOURCE_MISMATCH' };
		const decisions = new Map(state.snapshot.decisions.map((decision) => [decision.decisionId, decision]));
		const threads = new Map(state.snapshot.threads.map((thread) => [thread.threadId, thread]));
		const claimProvenance: MaterializationClaimProvenance[] = [];
		for (const [index, reserved] of record.selectedDecisions.entries()) {
			const decision = decisions.get(reserved.decisionId);
			const thread = threads.get(reserved.threadId);
			if (!decision || !thread || decision.state !== 'ACCEPTED_UNMATERIALIZED' || decision.acceptedBy.kind !== 'USER' || decision.threadId !== reserved.threadId || decision.acceptedEventId !== record.frozenSelection.acceptedEventIds[index] || decision.acceptedSynthesisDigest !== reserved.acceptedSynthesisDigest || reserved.decisionId !== record.frozenSelection.decisionIds[index]) return { status: 'blocked', code: 'MATERIALIZATION_DECISION_INELIGIBLE' };
			const claim = claimFor(decision, thread, state.events);
			if (!claim || claim.summary.length > maxSummaryBytes) return { status: 'blocked', code: 'MATERIALIZATION_CLAIM_UNMAPPED' };
			claimProvenance.push(claim);
		}
		try {
			const payload = source.operation === 'CREATE_R01'
				? new InitialRevisionRenderer().render({ acceptedDecisions: claimProvenance, canonicalMetadata: input.canonicalMetadata! })
				: new SuccessorEditPlanner().plan({ base: source.base!, expectedRevision: source.source!, acceptedDecisions: claimProvenance });
			const incomplete = {
				schemaVersion: 1 as const,
				materializationId: record.materializationId,
				selectionKey: record.frozenSelection.selectionKey,
				operation: source.operation,
				frozenSelection: structuredClone(record.frozenSelection),
				...(source.source ? { source: structuredClone(source.source), expectedRevisionIdentity: structuredClone(source.source) } : {}),
				payload,
				claimProvenance: structuredClone(claimProvenance),
			};
			const plan: MaterializationPlan = { ...incomplete, digest: materializationPlanDigest(incomplete) };
			if (!validateMaterializationPlan(plan, record)) return { status: 'blocked', code: 'MATERIALIZATION_PAYLOAD_INVALID' };
			const persisted = await this.store.persistMaterializationPlan(record, plan);
			return persisted.status === 'ready' ? { status: 'ready', plan: persisted.record.plan! } : { status: 'blocked', code: persisted.code };
		} catch (error) {
			return { status: 'blocked', code: error instanceof Error ? error.message : 'MATERIALIZATION_PAYLOAD_INVALID' };
		}
	}
}

export type LifecycleMaterializationPlannerResult =
	| { status:'ready'; result:MaterializationResult; revision:LifecycleRevision; inventory:WorkspaceLifecycleState }
	| { status:'blocked'; code:string };

/** Opt-in boundary: never reads filename-era sources or writes legacy projections. */
export class LifecycleMaterializationPlanner {
	constructor(private readonly input:{projectRoot:string;workspaceId:string;service?:LifecycleService}) {}

	async readInventory(): Promise<WorkspaceLifecycleState> {
		return (this.input.service ?? new LifecycleService(this.input.projectRoot)).rebuildLifecycleInventory(this.input.workspaceId);
	}

	async materialize(request:{requestId:string;revisionId:string;approvedChanges:ReadonlyArray<{from:string;to:string}>;locator?:string}):Promise<LifecycleMaterializationPlannerResult> {
		const service=this.input.service??new LifecycleService(this.input.projectRoot);
		const inventory=await service.rebuildLifecycleInventory(this.input.workspaceId).catch(()=>undefined);
		if(!inventory?.base) return {status:'blocked',code:'BASE_DOCUMENT_NOT_REGISTERED'};
		const active=inventory.revisions.find(revision=>revision.revisionId===inventory.activeRevisionId);
		if(inventory.revisions.length>0&&!active) return {status:'blocked',code:'ACTIVE_REVISION_NOT_FOUND'};
		const result=active
			? await service.createSuccessor({workspaceId:this.input.workspaceId,requestId:request.requestId,operation:'CREATE_SUCCESSOR',revisionId:request.revisionId,source:{sourceKind:'REVISION',sourceId:active.revisionId,sourceContentHash:active.contentHash,baseDocumentId:inventory.base.baseDocumentId},approvedChanges:request.approvedChanges,...(request.locator?{locator:request.locator}:{})})
			: await service.createFromBase({workspaceId:this.input.workspaceId,requestId:request.requestId,operation:'CREATE_FROM_BASE',revisionId:request.revisionId,source:{sourceKind:'BASE_DOCUMENT',sourceId:inventory.base.baseDocumentId,sourceContentHash:inventory.base.contentHash,baseDocumentId:inventory.base.baseDocumentId},approvedChanges:request.approvedChanges,...(request.locator?{locator:request.locator}:{})});
		if(result.outcome!=='COMMITTED'&&result.outcome!=='ALREADY_COMMITTED') return {status:'blocked',code:result.code??'LIFECYCLE_INVENTORY_INCONSISTENT'};
		const rebuilt=await service.rebuildLifecycleInventory(this.input.workspaceId);
		const revision='revision' in result?result.revision:rebuilt.revisions.find(item=>item.revisionId===result.revisionId);
		const materializationResult='result' in result?result.result:result as MaterializationResult;
		if(!revision) return {status:'blocked',code:'LIFECYCLE_INVENTORY_INCONSISTENT'};
		return {status:'ready',result:materializationResult,revision,inventory:rebuilt};
	}
}
