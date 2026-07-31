import { createProductionScientificRoleAdapters, ScientificWorkflowService } from './scientific-workflow-service.js';
import { ScientificStateStore } from './scientific-state-store.js';
import { ProjectEntryResolver } from './project-entry-resolver.js';
import { ScientificActResolver } from './scientific-act-resolver.js';
import { ScientificThreadResolver } from './scientific-thread-resolver.js';
import { ScientificContextBuilder } from './scientific-context-builder.js';
import { createReadOnlyDocumentFragmentLoader } from './document-state.js';
import { createLifecycleV1RevisionInventoryPort, readCanonicalManagedRevisionInventory } from './revision-lifecycle-store.js';
import { LifecycleMaterializationPlanner, MaterializationPlanner } from './materialization-planner.js';
import { MaterializationCandidateExecutor } from './materialization-candidate-executor.js';
import { DocumentReviewerGate } from './document-reviewer-gate.js';
import { MaterializationPublicationService } from './materialization-publication-service.js';
import { loadDocumentState } from './document-state.js';
import { rebuildDerivedState } from './derived-state-builder.js';
import { materializeCompositeTarget, resolveSuccessorTarget } from './target-resolver.js';
import { composeSuccessorBlockCandidate, type SuccessorBlockReplacementResolver } from './successor-composite-engine.js';
import type { SuccessorBlock, SuccessorBlockPlan } from './block-plan.js';
import type { ProposalWorkspaceAdapter } from './proposal-workspace-adapter.js';
import { parseProposedEdit, sha256 } from './types.js';
import type { EditAction } from './types.js';
import type { ProductionModelRuntime } from './production-runtime.js';
import type {
	CanonicalProposalMetadata,
	ProjectEntry,
	PublicBlocker,
	ScientificSynthesisCandidate,
	ScientificThread,
	ScientificWorkflowPublicResult,
	ScientificWorkflowRequest,
	ThreadResolution,
} from './scientific-domain.js';
import type { ReviewerAdapter } from './reviewer-adapter.js';
import type { TutorAdapter } from './tutor-adapter.js';

export type ScientificWorkflowRuntimeOptions = {
	/** Canonical proposal metadata is supplied by the composition root; it is never inferred from user text. */
	canonicalMetadata?: CanonicalProposalMetadata;
	/** Composition-owned role ports permit deterministic hosted deployments without exposing role control to callers. */
	roleAdapters?: { tutor: TutorAdapter; reviewer: ReviewerAdapter };
	newId?: () => string;
	now?: () => Date;
	derivedStore?: ConstructorParameters<typeof MaterializationPublicationService>[0]['derivedStore'];
	/** Opt-in only: legacy workspaces are never inferred or migrated into lifecycle-v1. */
	lifecycleV1WorkspaceId?: string;
};

function publicBlocker(code: string, nextAction: string): PublicBlocker {
	return { code, message: 'Scientific workflow cannot continue safely.', nextAction };
}

/**
 * Splices disjoint, ascending source spans in a single pass. Mirrors
 * `successor-composite-engine.ts`'s private `spliceDisjoint` exactly; duplicated
 * locally (rather than exported from that module) to keep the composite
 * engine's public contract minimal, per its own module documentation.
 */
function spliceDisjointForSuccessorLocus(source: Buffer, edits: readonly { startByte: number; endByte: number; replacement: Buffer }[]): Buffer {
	const ordered = [...edits].sort((left, right) => left.startByte - right.startByte);
	const parts: Buffer[] = [];
	let cursor = 0;
	for (const edit of ordered) {
		parts.push(source.subarray(cursor, edit.startByte));
		parts.push(edit.replacement);
		cursor = edit.endByte;
	}
	parts.push(source.subarray(cursor));
	return Buffer.concat(parts);
}

/**
 * The scientific composition root. It composes existing scientific ports while keeping
 * public-tool routing and feature admission outside this module.
 */
export class ScientificWorkflowRuntime {
	private readonly store: ScientificStateStore;
	private readonly entryResolver: ProjectEntryResolver;
	private readonly actResolver = new ScientificActResolver();
	private readonly threadResolver: ScientificThreadResolver;
	private readonly workflow: ScientificWorkflowService;
	// These are deliberately composed here, not in proposal-workspace. Public materialization
	// execution remains covered by T11.2; this coordinator exposes no write capability itself.
	private readonly planner: MaterializationPlanner;
	private readonly candidateExecutor: MaterializationCandidateExecutor;
	private readonly documentReviewer: DocumentReviewerGate;
	private readonly publication: MaterializationPublicationService;
	private readonly lifecyclePublication?: LifecycleMaterializationPlanner;
	/** Secondary client retry aliases are scoped to this public-runtime lifetime; durable exact-set identity remains store-owned. */
	private readonly idempotencySelections = new Map<string, string>();

	constructor(
		private readonly projectRoot: string,
		adapter: ProposalWorkspaceAdapter,
		runtime: ProductionModelRuntime,
		private readonly options: ScientificWorkflowRuntimeOptions = {},
	) {
		this.store = new ScientificStateStore(projectRoot);
		this.entryResolver = new ProjectEntryResolver(options.lifecycleV1WorkspaceId
			? createLifecycleV1RevisionInventoryPort({ projectRoot, workspaceId: options.lifecycleV1WorkspaceId })
			: { read: () => readCanonicalManagedRevisionInventory(projectRoot) }, this.store);
		this.threadResolver = new ScientificThreadResolver(this.store);
		const roles = options.roleAdapters ?? createProductionScientificRoleAdapters(runtime);
		const contextBuilder = new ScientificContextBuilder({ read: async () => {
			const state = await this.store.read();
			if (!state) throw new Error('SCIENTIFIC_STATE_MISSING');
			return { threads: state.snapshot.threads, relations: state.snapshot.relations, events: state.events };
		} }, { documentFragments: createReadOnlyDocumentFragmentLoader(projectRoot) });
		this.workflow = new ScientificWorkflowService({ store: this.store, contextBuilder, ...roles, ...(options.newId ? { newId: options.newId } : {}), ...(options.now ? { now: options.now } : {}) });
		this.planner = new MaterializationPlanner(this.store);
		this.candidateExecutor = new MaterializationCandidateExecutor();
		this.documentReviewer = new DocumentReviewerGate(roles.reviewer);
		this.publication = new MaterializationPublicationService({ projectRoot, store: this.store, executor: this.candidateExecutor, reviewer: this.documentReviewer, adapter, ...(options.derivedStore ? { derivedStore: options.derivedStore } : {}) });
		this.lifecyclePublication = options.lifecycleV1WorkspaceId ? new LifecycleMaterializationPlanner({ projectRoot, workspaceId: options.lifecycleV1WorkspaceId }) : undefined;
	}

	async execute(request: ScientificWorkflowRequest): Promise<ScientificWorkflowPublicResult> {
		const entry = await this.entryResolver.resolve({ bootstrapFromActiveProposal: request.scientificAct === 'BOOTSTRAP_FROM_ACTIVE_PROPOSAL' });
		if (entry.recovery.required) return this.workflow.projectReentry(entry);

		const act = this.actResolver.resolve({
			instruction: request.instruction,
			scientificAct: request.scientificAct,
			requestedThreadId: request.activeThreadId,
			relatedThreadIds: request.relatedThreadIds,
		});
		if (act.status !== 'resolved') return this.withBlock(entry, act.status === 'blocked' ? act.code : 'SCIENTIFIC_ACT_CLARIFICATION_REQUIRED', act.status === 'blocked' ? 'clarify_or_use_existing_route' : 'clarify_scientific_act', act.status);

		if (act.act === 'REQUEST_MATERIALIZATION') return this.materialize(entry, request);

		const thread = await this.threadResolver.resolve({
			entry,
			act,
			requestedActiveThreadId: request.activeThreadId,
			relatedThreadIds: request.relatedThreadIds,
			...(act.act === 'CONSTRUCT_IDEA' ? { ideaSeed: { title: request.instruction.slice(0, 200), summary: request.instruction.slice(0, 2_000), actor: { kind: 'USER' as const } } } : {}),
		});
		if (thread.status === 'blocked') return this.projectThreadResolution(entry, thread);
		if (thread.status === 'needs_clarification') return this.projectThreadResolution(entry, thread);
		const activeThread = thread.activeThread;
		if (act.act === 'MODIFY_SYNTHESIS' || act.act === 'ACCEPT_DECISION') {
			const candidate = await this.reviewedCandidate(activeThread.threadId, request.synthesisId, request.synthesisDigest);
			if (!candidate) return this.withBlock(entry, 'SCIENTIFIC_REVIEWED_SYNTHESIS_REQUIRED', 'supply_exact_reviewed_synthesis', 'blocked');
			if (act.act === 'MODIFY_SYNTHESIS') {
				const modified = await this.workflow.modifySynthesis({ activeThread, requestedDirectRelationIds: request.relatedThreadIds ?? [], act: 'MODIFY_SYNTHESIS', instruction: request.instruction, priorSynthesis: candidate, modificationCause: request.modificationCause ?? '', actor: request.actor ?? { kind: 'USER' } });
				return this.projectSynthesis(entry, activeThread, modified);
			}
			const accepted = await this.workflow.acceptDecision({ candidate, actor: request.actor ?? { kind: 'USER' } });
			return accepted.status === 'recorded'
				? { ...this.workflow.projectReentry({ ...entry, state: 'MATERIALIZATION_PENDING', activeThreadId: activeThread.threadId, activeThread: { threadId: activeThread.threadId, status: 'ACCEPTED_UNMATERIALIZED', title: activeThread.title, summary: activeThread.summary }, relatedThreads: [], pendingCandidateIds: [accepted.decisionId!], pendingCandidates: [{ decisionId: accepted.decisionId!, threadId: activeThread.threadId, state: 'ACCEPTED_UNMATERIALIZED', eligibility: 'eligible', blockers: [] },], nextAction: 'request_materialization_with_explicit_candidate_ids' }), status: 'recorded', eventId: accepted.eventId, decisionId: accepted.decisionId }
				: this.withBlock(entry, accepted.code, 'retry_with_exact_reviewed_synthesis', 'blocked');
		}
		const synthesis = await this.workflow.synthesize({ activeThread, requestedDirectRelationIds: request.relatedThreadIds ?? [], act: act.act, instruction: request.instruction });
		return this.projectSynthesis(entry, activeThread, synthesis);
	}

	private async materialize(entry: ProjectEntry, request: ScientificWorkflowRequest): Promise<ScientificWorkflowPublicResult> {
		if (this.lifecyclePublication) return this.materializeLifecycleV1(entry, request);
		if (!this.options.canonicalMetadata) return this.withBlock(entry, 'CANONICAL_METADATA_UNAVAILABLE', 'supply_canonical_metadata', 'blocked');
		if (!request.candidateIds?.length) return this.withBlock(entry, 'MATERIALIZATION_SELECTION_REQUIRED', 'select_accepted_candidates', 'blocked');
		const requestedSelection = JSON.stringify(request.candidateIds);
		if (request.idempotencyKey) {
			const priorSelection = this.idempotencySelections.get(request.idempotencyKey);
			if (priorSelection && priorSelection !== requestedSelection) return this.withBlock(entry, 'MATERIALIZATION_IDEMPOTENCY_KEY_CONFLICT', 'use_a_new_idempotency_key', 'blocked');
			this.idempotencySelections.set(request.idempotencyKey, requestedSelection);
		}
		const reserved = await this.store.reserveMaterialization(request.candidateIds);
		if (reserved.status === 'blocked') return this.withBlock(entry, reserved.code, 'select_accepted_candidates', 'blocked');
		if (reserved.status === 'conflict') return this.withBlock(entry, reserved.code, 'resolve_materialization_selection_conflict', 'blocked');
		let record = reserved.record;
		if (record.state === 'COMMITTED' && record.commit) return { ...this.workflow.projectReentry(entry), status: 'materialized', materialization: { materializationId: record.materializationId, state: record.state, targetFilename: record.commit.targetFilename, targetRevision: record.commit.targetRevision }, nextAction: null };
		if (record.state === 'RECOVERY_REQUIRED') return this.withBlock(entry, record.outcome?.code ?? 'MATERIALIZATION_RECOVERY_REQUIRED', 'reconcile_materialization_evidence', 'blocked');
		let source;
		const evidence = record.selectedDecisions[0]?.revisionEvidence;
		if (evidence) source = await loadDocumentState(this.projectRoot, evidence.filename);
		if (record.state === 'RESOLVING') {
			const planned = await this.planner.plan({ record, state: await this.store.read()!, ...(source ? { source } : {}), canonicalMetadata: this.options.canonicalMetadata });
			if (planned.status === 'blocked') return this.withBlock(entry, planned.code, 'reconcile_materialization_plan', 'blocked');
			record = (await this.store.reserveMaterialization(request.candidateIds)).record;
		}
		const result = await this.publication.materialize({ record, ...(source ? { source } : {}) });
		if (result.status === 'materialized') return { ...this.workflow.projectReentry(entry), status: 'materialized', materialization: { materializationId: result.record.materializationId, state: result.record.state, targetFilename: result.targetFilename, targetRevision: result.targetRevision }, nextAction: null };
		return this.withBlock(entry, result.code, result.status === 'recovery_required' ? 'reconcile_materialization_evidence' : 'retry_materialization', 'blocked');
	}

	/** The only public lifecycle-v1 publication route. It never invokes filename-era planning, candidate rendering, or workspace publication. */
	private async materializeLifecycleV1(entry: ProjectEntry, request: ScientificWorkflowRequest): Promise<ScientificWorkflowPublicResult> {
		if (!request.candidateIds?.length) return this.withBlock(entry, 'MATERIALIZATION_SELECTION_REQUIRED', 'select_accepted_candidates', 'blocked');
		let authority;
		try { authority = await this.lifecyclePublication!.readInventory(); } catch { return this.withBlock(entry, 'LIFECYCLE_INVENTORY_INCONSISTENT', 'reconcile_lifecycle_inventory', 'blocked'); }
		if (!authority.base) return this.withBlock(entry, 'BASE_DOCUMENT_NOT_REGISTERED', 'register_lifecycle_base', 'blocked');
		const active = authority.revisions.find((revision) => revision.revisionId === authority.activeRevisionId);
		if (authority.revisions.length > 0 && !active) return this.withBlock(entry, 'ACTIVE_REVISION_NOT_FOUND', 'reconcile_lifecycle_inventory', 'blocked');
		const reserved = await this.store.reserveMaterialization(request.candidateIds);
		if (reserved.status === 'blocked') return this.withBlock(entry, reserved.code, 'select_accepted_candidates', 'blocked');
		if (reserved.status === 'conflict') return this.withBlock(entry, reserved.code, 'resolve_materialization_selection_conflict', 'blocked');
		const record = reserved.record;
		if (record.state === 'COMMITTED' && record.commit?.lifecycle) return { ...this.workflow.projectReentry(entry), status: 'materialized', materialization: { materializationId: record.materializationId, state: record.state, targetFilename: record.commit.targetFilename, targetRevision: record.commit.targetRevision }, nextAction: null };
		if (record.state !== 'RESOLVING') return this.withBlock(entry, 'MATERIALIZATION_LIFECYCLE_RETRY_UNSUPPORTED', 'reconcile_materialization_evidence', 'blocked');
		const state = await this.store.read();
		if (!state) return this.withBlock(entry, 'MATERIALIZATION_STATE_MISSING', 'reconcile_scientific_state', 'blocked');
		const claims = record.selectedDecisions.map((selected) => {
			const tutor = state.events.find((event) => event.type === 'TUTOR_ASSESSED' && event.threadId === selected.threadId && event.eventId === selected.sourceEventIds[0]);
			const summary = typeof tutor?.payload.summary === 'string' ? tutor.payload.summary.trim() : undefined;
			if (!summary) return undefined;
			const proposedEdit = parseProposedEdit(tutor?.payload.proposedEdit);
			return { summary, ...(proposedEdit ? { proposedEdit } : {}) };
		});
		if (claims.some((claim) => !claim)) return this.withBlock(entry, 'MATERIALIZATION_CLAIM_UNMAPPED', 'reconcile_materialization_plan', 'blocked');
		const source = active ?? authority.base;
		const approvedChanges = await this.composeLifecycleSuccessorChanges(source.content, claims as { summary: string; proposedEdit?: EditAction }[]);
		const published = await this.lifecyclePublication.materialize({
			requestId: record.materializationId,
			revisionId: `revision-${record.materializationId}`,
			approvedChanges,
		});
		if (published.status === 'blocked') return this.withBlock(entry, published.code, 'reconcile_materialization_evidence', 'blocked');
		const lifecycle = { workspaceId: this.options.lifecycleV1WorkspaceId!, operation: published.result.operation, requestId: published.result.requestId, revisionId: published.revision.revisionId, contentHash: published.revision.contentHash } as const;
		const commit = {
			candidateDigest: published.revision.contentHash,
			planDigest: sha256(JSON.stringify({ schemaVersion: 'lifecycle-v1', requestId: published.result.requestId, operation: published.result.operation, selectionKey: record.frozenSelection.selectionKey })),
			targetFilename: `lifecycle-v1:${published.revision.revisionId}`,
			targetRevision: published.revision.revisionId,
			publishedSha256: published.revision.contentHash,
			receiptSha256: sha256(JSON.stringify(published.result)),
			threadIds: [...new Set(record.selectedDecisions.map((decision) => decision.threadId))].sort(),
			lifecycle,
		};
		const committed = await this.store.commitLifecycleMaterialization(record, commit);
		if (committed.status !== 'ready') return this.withBlock(entry, committed.code, 'reconcile_materialization_evidence', 'blocked');
		return { ...this.workflow.projectReentry(entry), status: 'materialized', materialization: { materializationId: committed.record.materializationId, state: committed.record.state, targetFilename: commit.targetFilename, targetRevision: commit.targetRevision }, nextAction: null };
	}

	/**
	 * Composes the lifecycle-v1 successor's approved changes for `LifecycleService`.
	 *
	 * Resolves EACH accepted decision's locus independently (design: "mixed sets are
	 * per-decision independent" -- never all-or-nothing):
	 *   1. Structural (real, byte-preserving CHANGE): when the decision carries a
	 *      persisted `proposedEdit`, its `targetEntryId` is resolved by an EXPLICIT
	 *      document-index lookup against the CURRENT materialization base -- never
	 *      the synthesis-time document, and never fuzzy summary matching. On drift
	 *      (missing/moved entry) this decision falls through to (2).
	 *   2. Annotate-at-locus (pre-existing fallback): the decision's summary is
	 *      resolved via `resolveSuccessorTarget`, the same heading/section resolver
	 *      used by the interactive orchestrator successor path. Composed as
	 *      `originalText + "> Accepted revision: <summary>"`, exactly as before.
	 *   3. No locus at all: the decision's summary is preserved in the shared
	 *      document-tail "Accepted scientific decisions" block -- never silently
	 *      discarded.
	 *
	 * Overlapping/duplicate loci (from either tier) are never silently applied:
	 * every decision in a colliding pair degrades to tier (3) instead. Every
	 * resolved (tier 1 + tier 2) edit is spliced into ONE successor version through
	 * `composeSuccessorBlockCandidate` -- `successor-composite-engine.ts`'s guarded
	 * byte-preserving path -- so every byte outside the resolved loci is provably
	 * preserved, even when multiple decisions are involved. When NOTHING resolves
	 * (or the guarded compose call itself blocks), this falls back to appending a
	 * single "Accepted scientific decisions" summary block for every decision,
	 * matching the pre-repair shape byte-for-byte for that all-unresolved case.
	 *
	 * Either way, the final content is committed through a single whole-document
	 * `{from,to}` pair, which `LifecycleService`'s byte-safe `applyChanges` (V1)
	 * applies without interpreting `$$`/`$&`/`$<name>` as replacement patterns.
	 */
	private async composeLifecycleSuccessorChanges(sourceContent: string, claims: readonly { summary: string; proposedEdit?: EditAction }[]): Promise<ReadonlyArray<{ from: string; to: string }>> {
		const appendAll = (targets: readonly { summary: string }[]): ReadonlyArray<{ from: string; to: string }> => {
			const addition = `\n\n## Accepted scientific decisions\n\n${targets.map((claim) => `- ${claim.summary}`).join('\n')}\n`;
			return [{ from: sourceContent, to: `${sourceContent}${addition}` }];
		};
		const documentState = await rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(sourceContent, 'utf8'));

		type ResolvedEdit = { index: number; entryId: string; startByte: number; endByte: number; textSha256: string; replacementText: string };
		const resolved: ResolvedEdit[] = [];
		const unresolved: number[] = [];
		for (const [index, claim] of claims.entries()) {
			const structuralTarget = claim.proposedEdit?.kind === 'replace' ? documentState.structuralIndex.byId[claim.proposedEdit.targetEntryId] : undefined;
			if (structuralTarget && structuralTarget.type !== 'document') {
				resolved.push({ index, entryId: structuralTarget.entryId, startByte: structuralTarget.startByte, endByte: structuralTarget.endByte, textSha256: structuralTarget.textSha256, replacementText: (claim.proposedEdit as Extract<EditAction, { kind: 'replace' }>).replacementText });
				continue;
			}
			const candidates = resolveSuccessorTarget(documentState, claim.summary).candidates;
			if (candidates.length === 1) {
				const entry = materializeCompositeTarget(documentState, candidates[0]!)!;
				const originalText = documentState.documentBytes.subarray(entry.startByte, entry.endByte).toString('utf8');
				resolved.push({ index, entryId: entry.entryId, startByte: entry.startByte, endByte: entry.endByte, textSha256: entry.textSha256, replacementText: `${originalText}\n\n> Accepted revision: ${claim.summary.trim()}\n` });
				continue;
			}
			unresolved.push(index);
		}

		// Never silently apply overlapping/duplicate loci: every claim in a
		// colliding pair degrades to the shared tail-block fallback instead of
		// forcing an offset.
		const overlapping = new Set<number>();
		for (const left of resolved) for (const right of resolved) {
			if (left.index === right.index) continue;
			if (left.startByte < right.endByte && right.startByte < left.endByte) { overlapping.add(left.index); overlapping.add(right.index); }
		}
		const applied = resolved.filter((edit) => !overlapping.has(edit.index)).sort((left, right) => left.startByte - right.startByte);
		if (applied.length === 0) return appendAll(claims);

		let appliedSoFar: { startByte: number; endByte: number; replacement: Buffer }[] = [];
		const blocks: SuccessorBlock[] = [];
		const byBlockId = new Map<string, ResolvedEdit>();
		for (const edit of applied) {
			appliedSoFar = [...appliedSoFar, { startByte: edit.startByte, endByte: edit.endByte, replacement: Buffer.from(edit.replacementText, 'utf8') }];
			const blockId = `block-${edit.index}`;
			byBlockId.set(blockId, edit);
			blocks.push({
				id: blockId,
				dependsOn: [],
				target: { status: 'resolved', selector: { entryId: edit.entryId, startByte: edit.startByte, endByte: edit.endByte, textSha256: edit.textSha256, documentSha256: documentState.documentSha256 } },
				candidateSha256: sha256(spliceDisjointForSuccessorLocus(documentState.documentBytes, appliedSoFar)),
			});
		}
		const plan: SuccessorBlockPlan = {
			source: { filename: documentState.filename, revision: documentState.revision, documentSha256: documentState.documentSha256 },
			orderedBlockIds: blocks.map((block) => block.id),
			blocks,
			mergeGroups: [],
		};
		const resolver: SuccessorBlockReplacementResolver = ({ block }) => byBlockId.get(block.id)!.replacementText;
		const composed = await composeSuccessorBlockCandidate(plan, documentState, resolver);
		if (composed.status !== 'composed') return appendAll(claims);

		const fallbackIndexes = new Set([...overlapping, ...unresolved]);
		const fallbackClaims = claims.filter((_, index) => fallbackIndexes.has(index));
		if (fallbackClaims.length === 0) return [{ from: sourceContent, to: composed.candidateBytes.toString('utf8') }];
		const addition = `\n\n## Accepted scientific decisions\n\n${fallbackClaims.map((claim) => `- ${claim.summary}`).join('\n')}\n`;
		return [{ from: sourceContent, to: `${composed.candidateBytes.toString('utf8')}${addition}` }];
	}

	private async reviewedCandidate(threadId: string, synthesisId?: string, synthesisDigest?: string): Promise<ScientificSynthesisCandidate | undefined> {
		if (!synthesisId || !synthesisDigest) return undefined;
		const state = await this.store.read();
		const tutor = state?.events.find((event) => event.type === 'TUTOR_ASSESSED' && event.threadId === threadId && event.payload.synthesisId === synthesisId && event.payload.synthesisDigest === synthesisDigest);
		const review = state?.events.find((event) => event.type === 'CONCEPTUAL_REVIEW_RECORDED' && event.threadId === threadId && event.payload.synthesisId === synthesisId && event.payload.synthesisDigest === synthesisDigest && event.payload.status === 'PASS' && tutor && event.causalEventIds.includes(tutor.eventId));
		return tutor && review && typeof tutor.payload.summary === 'string' ? { synthesisId, threadId, digest: synthesisDigest, status: 'REVIEWED', summary: tutor.payload.summary, tutorEventId: tutor.eventId, reviewEventId: review.eventId } : undefined;
	}

	private projectSynthesis(entry: ProjectEntry, thread: ScientificThread, synthesis: Awaited<ReturnType<ScientificWorkflowService['synthesize']>>): ScientificWorkflowPublicResult {
		if (synthesis.status !== 'reviewed') return this.withBlock(entry, synthesis.code, 'revise_or_retry_scientific_synthesis', 'blocked');
		return { ...this.workflow.projectReentry({ ...entry, state: 'ACTIVE_SCIENTIFIC_PROJECT', activeThreadId: thread.threadId, activeThread: { threadId: thread.threadId, status: thread.status, title: thread.title, summary: thread.summary }, relatedThreads: [], nextAction: 'accept_reject_or_modify_reviewed_synthesis' }), status: 'recorded', eventId: synthesis.candidate.reviewEventId, synthesisId: synthesis.candidate.synthesisId, synthesisDigest: synthesis.candidate.digest };
	}

	private projectThreadResolution(entry: ProjectEntry, resolution: ThreadResolution): ScientificWorkflowPublicResult {
		if (resolution.status === 'blocked') return this.withBlock(entry, resolution.code, resolution.blockers[0]?.nextAction ?? 'select_or_reconcile_thread', 'blocked');
		if (resolution.status === 'needs_clarification') return this.withBlock(entry, resolution.code, 'select_or_create_thread', 'needs_clarification');
		const result = this.workflow.projectReentry({
			...entry,
			state: entry.state === 'EMPTY_PROJECT' ? 'SCIENTIFIC_ONLY' : entry.state,
			activeThreadId: resolution.activeThread.threadId,
			activeThread: { threadId: resolution.activeThread.threadId, status: resolution.activeThread.status, title: resolution.activeThread.title, summary: resolution.activeThread.summary },
			relatedThreads: [],
			nextAction: 'continue_scientific_workflow',
		});
		return {
			...result,
			status: resolution.status === 'created' ? 'recorded' : 'ready',
			...(resolution.intents[0] ? { eventId: resolution.intents[0].eventId } : {}),
		};
	}

	private withBlock(entry: ProjectEntry, code: string, nextAction: string, status: 'blocked' | 'needs_clarification'): ScientificWorkflowPublicResult {
		const result = this.workflow.projectReentry(entry);
		return {
			...result,
			status,
			blockers: [publicBlocker(code, nextAction)],
			nextAction,
		};
	}
}
