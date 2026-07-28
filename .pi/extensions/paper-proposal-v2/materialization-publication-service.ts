import { readFile } from 'node:fs/promises';
import { createRevisionReceipt, type InitialPublicationReceipt, type PublicationReceipt } from './revision-receipt.js';
import { derivedStatePath, loadDerivedState, markDerivedState, receiptPath, saveRevisionReceipt, commitDerivedState } from './derived-state-store.js';
import { rebuildDerivedState } from './derived-state-builder.js';
import { MaterializationCandidateExecutor, type ExactDocumentCandidate } from './materialization-candidate-executor.js';
import { DocumentReviewerGate } from './document-reviewer-gate.js';
import { ProposalWorkspaceAdapter } from './proposal-workspace-adapter.js';
import { resolveEffectiveOperationProfile } from './operation-spec.js';
import { sha256, type DocumentState } from './types.js';
import type { MaterializationRecord } from './scientific-domain.js';
import { ScientificStateStore } from './scientific-state-store.js';

type DerivedStore = Pick<typeof import('./derived-state-store.js'), 'commitDerivedState' | 'markDerivedState' | 'saveRevisionReceipt' | 'loadDerivedState'>;
export type MaterializationPublicationResult =
	| { status: 'materialized'; record: MaterializationRecord; targetFilename: string; targetRevision: string }
	| { status: 'blocked'; code: string }
	| { status: 'recovery_required'; code: string };

function publicationFailure(error: unknown): { code: string; published: boolean } {
	const value = error as { message?: unknown; published?: unknown };
	return { code: typeof value?.message === 'string' ? value.message : 'MATERIALIZATION_PUBLICATION_FAILED', published: value?.published === true };
}

/** Coordinates review, guarded publication, V2 evidence, and the final scientific commit. */
export class MaterializationPublicationService {
	constructor(private readonly dependencies: {
		projectRoot: string;
		store: ScientificStateStore;
		executor: MaterializationCandidateExecutor;
		reviewer: DocumentReviewerGate;
		adapter: ProposalWorkspaceAdapter;
		derivedStore?: DerivedStore;
	}) {}

	async materialize(input: { record: MaterializationRecord; source?: DocumentState }): Promise<MaterializationPublicationResult> {
		const execution = await this.dependencies.executor.execute({ record: input.record, frozenSelection: input.record.frozenSelection, ...(input.source ? { source: input.source } : {}) });
		if (execution.status === 'blocked') return this.outcome(input.record, 'BLOCKED', execution.code);
		const plan = input.record.plan;
		if (!plan || execution.validation.planDigest !== plan.digest) return this.outcome(input.record, 'BLOCKED', 'MATERIALIZATION_PLAN_INVALID');

		let review;
		try {
			review = await this.dependencies.reviewer.review({ candidate: execution.candidate, plan, provenance: execution.provenance, validation: execution.validation });
		} catch (error) {
			return this.outcome(input.record, 'BLOCKED', error instanceof Error ? error.message : 'DOCUMENT_REVIEW_FAILED');
		}
		const reviewEvidence = review.status === 'approved'
			? review.approval
			: { candidateDigest: execution.candidate.digest, planDigest: plan.digest, decision: review.decision };
		const reviewed = await this.dependencies.store.recordDocumentReview(input.record, reviewEvidence);
		if (review.status !== 'approved') return { status: 'blocked', code: `DOCUMENT_REVIEW_${review.decision}` };
		if (reviewed.status !== 'ready') return { status: 'blocked', code: reviewed.code };

		let published: Awaited<ReturnType<ProposalWorkspaceAdapter['publishInitial']>> | Awaited<ReturnType<ProposalWorkspaceAdapter['publishApprovedSuccessor']>>;
		try {
			if (plan.operation === 'CREATE_R01') {
				published = await this.dependencies.adapter.publishInitial({ candidate: execution.candidate, approval: review.approval });
			} else {
				if (!input.source || !execution.candidate.patches?.length || plan.payload.kind !== 'CREATE_SUCCESSOR') return this.outcome(reviewed.record, 'BLOCKED', 'MATERIALIZATION_SUCCESSOR_PUBLICATION_INPUT_INVALID');
				const frozen = plan.payload.patches[0]!.plan;
				published = await this.dependencies.adapter.publishApprovedSuccessor({
					candidate: execution.candidate,
					approval: review.approval,
					intent: frozen.intent,
					cleanupLevel: frozen.cleanupLevel,
					effectiveOperationProfile: resolveEffectiveOperationProfile({ intent: frozen.intent, cleanupLevel: frozen.cleanupLevel, semanticChange: frozen.semanticChange }),
					sourceFilename: input.source.filename,
					sourceSha256: input.source.documentSha256,
					patches: execution.candidate.patches,
					modelCalls: 0,
					plannerCalls: 0,
					roleAuthorizations: 0,
					validationResults: execution.validation.validationResults,
				});
			}
		} catch (error) {
			const failure = publicationFailure(error);
			return this.outcome(reviewed.record, failure.published ? 'RECOVERY_REQUIRED' : 'BLOCKED', failure.code);
		}

		return this.verifyAndCommit(reviewed.record, plan, execution.candidate, published);
	}

	private async verifyAndCommit(record: MaterializationRecord, plan: NonNullable<MaterializationRecord['plan']>, candidate: ExactDocumentCandidate, published: Awaited<ReturnType<ProposalWorkspaceAdapter['publishInitial']>> | Awaited<ReturnType<ProposalWorkspaceAdapter['publishApprovedSuccessor']>>): Promise<MaterializationPublicationResult> {
		const initial = plan.operation === 'CREATE_R01';
		const candidateMatches = initial
			? published.candidateDigest === candidate.digest && published.publishedBytes.subarray(-candidate.bytes.length).equals(candidate.bytes)
			: published.publishedBytes.equals(candidate.bytes);
		if (!candidateMatches || sha256(published.publishedBytes) !== published.publishedSha256) return this.outcome(record, 'RECOVERY_REQUIRED', 'MATERIALIZATION_PUBLISHED_BYTES_MISMATCH');
		try {
			const derived = await rebuildDerivedState(published.targetFilename, published.targetRevision, initial ? 'ROOT' : plan.source!.filename, published.publishedBytes);
			if (derived.documentSha256 !== published.publishedSha256) return this.outcome(record, 'RECOVERY_REQUIRED', 'MATERIALIZATION_DERIVED_STATE_MISMATCH');
			const store = this.dependencies.derivedStore ?? { commitDerivedState, markDerivedState, saveRevisionReceipt, loadDerivedState };
			await store.commitDerivedState(this.dependencies.projectRoot, derived);
			const receipt: PublicationReceipt = initial
				? createRevisionReceipt({ kind: 'INITIAL_PUBLICATION', targetRevision: 'r01', targetFilename: 'research-concept-r01.md', documentShaAfter: published.publishedSha256, derivedStateStatus: 'COMMITTED', materializationId: record.materializationId, selectionKey: record.frozenSelection.selectionKey, planDigest: plan.digest, candidateDigest: candidate.digest } satisfies InitialPublicationReceipt)
				: createRevisionReceipt({ sourceRevision: plan.source!.revision, targetRevision: published.targetRevision, sourceFilename: plan.source!.filename, targetFilename: published.targetFilename, intent: plan.payload.kind === 'CREATE_SUCCESSOR' ? plan.payload.patches[0]!.plan.intent : 'INSERT', operation: plan.payload.kind === 'CREATE_SUCCESSOR' ? plan.payload.patches[0]!.plan.intent : 'INSERT', instructionHash: plan.payload.kind === 'CREATE_SUCCESSOR' ? plan.payload.patches[0]!.plan.instructionHash : plan.digest, documentShaBefore: plan.source!.documentSha256, documentShaAfter: published.publishedSha256, resolvedEntryIds: plan.payload.kind === 'CREATE_SUCCESSOR' ? plan.payload.patches.flatMap((patch) => patch.plan.resolvedTargets) : [], patchIds: candidate.patches?.map((patch) => patch.id) ?? [], patchCount: candidate.patches?.length ?? 0, cleanupLevel: plan.payload.kind === 'CREATE_SUCCESSOR' ? plan.payload.patches[0]!.plan.cleanupLevel : 'NONE', derivedStateStatus: 'COMMITTED', modelCalls: 0, roleAuthorizations: 0, inputTokens: 0, outputTokens: 0, elapsedMs: 0, parallelTasks: 1, validationResults: { publishedBytes: true, derivedState: true, receipt: true } });
			await store.saveRevisionReceipt(this.dependencies.projectRoot, published.targetFilename, receipt);
			const verifiedDerived = await store.loadDerivedState(this.dependencies.projectRoot, published.targetFilename, published.publishedSha256, derived.parserVersion, published.publishedBytes);
			const receiptBytes = await readFile(receiptPath(this.dependencies.projectRoot, published.targetFilename));
			if (!verifiedDerived || sha256(receiptBytes) !== sha256(Buffer.from(JSON.stringify(receipt)))) return this.outcome(record, 'RECOVERY_REQUIRED', 'MATERIALIZATION_PUBLICATION_EVIDENCE_INCOMPLETE');
			const committed = await this.dependencies.store.commitMaterialization(record, { candidateDigest: candidate.digest, planDigest: plan.digest, targetFilename: published.targetFilename, targetRevision: published.targetRevision, publishedSha256: published.publishedSha256, receiptSha256: sha256(receiptBytes), threadIds: [...new Set(record.selectedDecisions.map((decision) => decision.threadId))].sort() });
			return committed.status === 'ready' ? { status: 'materialized', record: committed.record, targetFilename: published.targetFilename, targetRevision: published.targetRevision } : { status: 'recovery_required', code: committed.code };
		} catch (error) {
			try { await (this.dependencies.derivedStore ?? { markDerivedState }).markDerivedState(this.dependencies.projectRoot, published.targetFilename, 'FAILED', error instanceof Error ? error.message : String(error)); } catch {}
			return this.outcome(record, 'RECOVERY_REQUIRED', error instanceof Error ? error.message : 'MATERIALIZATION_PUBLICATION_EVIDENCE_FAILED');
		}
	}

	private async outcome(record: MaterializationRecord, state: 'BLOCKED' | 'RECOVERY_REQUIRED', code: string): Promise<MaterializationPublicationResult> {
		const outcome = await this.dependencies.store.recordMaterializationOutcome(record, state, code);
		return state === 'RECOVERY_REQUIRED' ? { status: 'recovery_required', code: outcome.status === 'ready' ? code : outcome.code } : { status: 'blocked', code: outcome.status === 'ready' ? code : outcome.code };
	}
}
