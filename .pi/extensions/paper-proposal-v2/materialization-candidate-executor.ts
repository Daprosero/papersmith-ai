import { rebuildDerivedState } from './derived-state-builder.js';
import { validateMaterializationPlan } from './materialization-planner.js';
import { compilePatches } from './patch-compiler.js';
import { validateCandidate } from './candidate-validator.js';
import { sha256, type DocumentState } from './types.js';
import type { FrozenDecisionSelection, MaterializationClaimProvenance, MaterializationPlan, MaterializationRecord, RevisionEvidence } from './scientific-domain.js';

export type ExactDocumentCandidate = {
	filename: string;
	revision: string;
	bytes: Buffer;
	digest: string;
};

export type CandidateValidation = {
	operation: MaterializationPlan['operation'];
	planDigest: string;
	payloadVersion: 1;
	inputDocumentSha256?: string;
	candidateDocumentSha256: string;
	patchIds: string[];
	validationResults: Record<string, boolean>;
};

export type CandidateExecutionFailureCode =
	| 'MATERIALIZATION_PLAN_MISSING'
	| 'MATERIALIZATION_PLAN_INVALID'
	| 'MATERIALIZATION_RESERVATION_INVALID'
	| 'MATERIALIZATION_SOURCE_MISSING'
	| 'MATERIALIZATION_SOURCE_STALE'
	| 'MATERIALIZATION_PAYLOAD_PRECONDITION_FAILED'
	| 'MATERIALIZATION_COMPILATION_FAILED'
	| 'MATERIALIZATION_VALIDATION_FAILED';

export type MaterializationCandidateExecutionResult =
	| { status: 'ready'; candidate: ExactDocumentCandidate; provenance: MaterializationClaimProvenance[]; validation: CandidateValidation }
	| { status: 'blocked'; code: CandidateExecutionFailureCode; evidence: { planDigest?: string; materializationId: string } };

function sameSelection(left: FrozenDecisionSelection, right: FrozenDecisionSelection) {
	return JSON.stringify(left) === JSON.stringify(right);
}

function sameRevision(state: DocumentState, expected: RevisionEvidence) {
	return state.filename === expected.filename && state.revision === expected.revision && state.documentSha256 === expected.documentSha256;
}

function blocked(record: MaterializationRecord, code: CandidateExecutionFailureCode, plan?: MaterializationPlan): MaterializationCandidateExecutionResult {
	return { status: 'blocked', code, evidence: { materializationId: record.materializationId, ...(plan ? { planDigest: plan.digest } : {}) } };
}

/** Executes a persisted payload only in memory; it has no workspace, publication, or state-store capability. */
export class MaterializationCandidateExecutor {
	async execute(input: { record: MaterializationRecord; plan?: MaterializationPlan; frozenSelection: FrozenDecisionSelection; source?: DocumentState }): Promise<MaterializationCandidateExecutionResult> {
		const { record } = input;
		const plan = input.plan ?? record.plan;
		if (!plan || !record.plan) return blocked(record, 'MATERIALIZATION_PLAN_MISSING');
		if (input.plan && input.plan.digest !== record.plan.digest) return blocked(record, 'MATERIALIZATION_PLAN_INVALID', plan);
		if (record.state !== 'PREPARED' || !sameSelection(record.frozenSelection, input.frozenSelection) || !validateMaterializationPlan(plan, record)) return blocked(record, 'MATERIALIZATION_RESERVATION_INVALID', plan);
		if (plan.operation === 'CREATE_R01') {
			if (input.source || plan.payload.kind !== 'CREATE_R01') return blocked(record, 'MATERIALIZATION_SOURCE_STALE', plan);
			try {
				const state = await rebuildDerivedState(plan.payload.target.filename, plan.payload.target.revision, 'ROOT', Buffer.from(plan.payload.markdown, 'utf8'));
				const bytes = Buffer.from(plan.payload.markdown, 'utf8');
				const digest = sha256(bytes);
				return {
					status: 'ready',
					candidate: { filename: state.filename, revision: state.revision, bytes, digest },
					provenance: structuredClone(plan.claimProvenance),
					validation: { operation: plan.operation, planDigest: plan.digest, payloadVersion: 1, candidateDocumentSha256: digest, patchIds: [], validationResults: { structural: state.structuralIndex.entries.length > 0, completeMarkdown: bytes.length > 0 } },
				};
			} catch {
				return blocked(record, 'MATERIALIZATION_VALIDATION_FAILED', plan);
			}
		}
		if (plan.payload.kind !== 'CREATE_SUCCESSOR' || !input.source) return blocked(record, 'MATERIALIZATION_SOURCE_MISSING', plan);
		if (!plan.source || !plan.expectedRevisionIdentity || !sameRevision(input.source, plan.source) || !sameRevision(input.source, plan.expectedRevisionIdentity) || !sameRevision(input.source, plan.payload.expectedBase)) return blocked(record, 'MATERIALIZATION_SOURCE_STALE', plan);
		let state = input.source;
		const patchIds: string[] = [];
		for (const patch of plan.payload.patches) {
			const anchor = state.structuralIndex.byId[patch.preconditions.anchorEntryId];
			if (!anchor || state.documentSha256 !== patch.preconditions.baseDocumentSha256 || !sameRevision(state, patch.preconditions.expectedRevision) || anchor.textSha256 !== patch.preconditions.anchorTextSha256) return blocked(record, 'MATERIALIZATION_PAYLOAD_PRECONDITION_FAILED', plan);
			try {
				const compiled = compilePatches(state, patch.plan);
				const validation = await validateCandidate(state, patch.plan, compiled);
				if (!validation.ok) return blocked(record, 'MATERIALIZATION_VALIDATION_FAILED', plan);
				patchIds.push(...compiled.patchIds);
				state = await rebuildDerivedState(state.filename, state.revision, state.lineage, Buffer.from(compiled.candidate, 'utf8'));
			} catch {
				return blocked(record, 'MATERIALIZATION_COMPILATION_FAILED', plan);
			}
		}
		const bytes = Buffer.from(state.documentBytes);
		const digest = sha256(bytes);
		return {
			status: 'ready',
			candidate: { filename: state.filename, revision: state.revision, bytes, digest },
			provenance: structuredClone(plan.claimProvenance),
			validation: { operation: plan.operation, planDigest: plan.digest, payloadVersion: 1, inputDocumentSha256: input.source.documentSha256, candidateDocumentSha256: digest, patchIds, validationResults: { frozenPayload: true, preconditions: true, compiler: true, validator: true } },
		};
	}
}
