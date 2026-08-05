import { createHash, randomUUID } from 'node:crypto';
import type { ReviewerAdapter, ReviewerAssessment } from './reviewer-adapter.js';
import { validateReviewerAssessment } from './reviewer-adapter.js';
import { ScientificContextBuilder, type ScientificContextBuilderInput } from './scientific-context-builder.js';
import { recordScientificMetric } from './runtime-metrics.js';
import type { ScientificSnapshotRecord } from './scientific-state-store.js';
import { ScientificStateStore } from './scientific-state-store.js';
import type { TutorAdapter, TutorAssessment } from './tutor-adapter.js';
import { validateTutorAssessment } from './tutor-adapter.js';
import { resolveIntent } from './intent-resolver.js';
import { PROPOSED_EDIT_REPLACEMENT_MAX_BYTES } from './types.js';
import type { EditAction, Position, ResolvedIntent } from './types.js';
import type {
	ConceptualReviewOutcome,
	EvidenceReference,
	ProjectEntry,
	ScientificActor,
	ScientificDecision,
	ScientificEvent,
	ScientificEventId,
	ScientificSynthesisCandidate,
	ScientificThread,
	ScientificWorkflowPublicResult,
	ScientificRecoveryDiagnostics,
	MaterializationRecord,
	StructuredConceptualFinding,
	ThreadSynthesis,
} from './scientific-domain.js';

export type ScientificSynthesisRequest = ScientificContextBuilderInput & {
	instruction: string;
};

export type ScientificSynthesisResult =
	| { status: 'reviewed'; candidate: ScientificSynthesisCandidate; reviewOutcome: 'PASS'; eventIds: ScientificEventId[] }
	| { status: 'blocked'; code: string; eventIds: ScientificEventId[]; finding?: StructuredConceptualFinding };

export type ScientificDecisionResult =
	| { status: 'recorded'; eventId: ScientificEventId; decisionId?: string; state: 'ACCEPTED_UNMATERIALIZED' | 'REJECTED' | 'RETRACTED' }
	| { status: 'blocked'; code: string };

export type ScientificDecisionRequest = {
	candidate: ScientificSynthesisCandidate;
	actor: ScientificActor;
};

export type ScientificWorkflowServiceDependencies = {
	store: ScientificStateStore;
	contextBuilder: ScientificContextBuilder;
	tutor?: TutorAdapter;
	reviewer?: ReviewerAdapter;
	newId?: () => string;
	now?: () => Date;
};

const FORBIDDEN_AUTHORITY = /(?:publish|materiali[sz]|lifecycle|document.?edit|\bplan\b|accept(?:ance|ed)?(?:Decision)?)/i;
const PRIVATE_CONTENT = /(?:chain.?of.?thought|hidden.?prompt|raw.?trace|private.?reasoning|role.?transcript|\bprompt\b|\btrace\b|\bthought\b)/i;
const REVIEW_OUTCOMES: Record<ReviewerAssessment['decision'], ConceptualReviewOutcome> = {
	APPROVE: 'PASS',
	APPROVE_WITH_CHANGES: 'REPAIR_REQUIRED',
	BLOCK: 'BLOCK',
	NEEDS_CLARIFICATION: 'NEEDS_CLARIFICATION',
};

const digest = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const clone = <T>(value: T): T => structuredClone(value);
const isBoundedText = (value: unknown, maximum = 2_000): value is string => typeof value === 'string' && value.trim().length > 0 && value.length <= maximum && !PRIVATE_CONTENT.test(value);

function hasForbiddenAuthority(value: unknown): boolean {
	if (!value || typeof value !== 'object') return false;
	for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
		if (FORBIDDEN_AUTHORITY.test(key) || hasForbiddenAuthority(nested)) return true;
	}
	return false;
}

function roleContext(context: Awaited<ReturnType<ScientificContextBuilder['build']>>, instruction: string) {
	return {
		documentSha256: context.documentFragments[0]?.revision.documentSha256 ?? 'scientific-context-only',
		targetEntryId: context.documentFragments[0]?.entryId ?? context.activeThread.threadId,
		instruction,
		fragments: context.documentFragments.map(({ entryId, type, text, textSha256, headingPath }) => ({ entryId, type: type as any, text, textSha256, headingPath })),
		nearbySymbols: {},
		directReferences: context.evidence.map((evidence) => `${evidence.kind}:${evidence.id}`),
		maxBytes: context.limits.maxBytes,
	};
}

function evidenceForFinding(assessment: ReviewerAssessment): EvidenceReference[] {
	const identifiers = [...assessment.unsupportedClaims, ...assessment.referenceRisks, ...assessment.notationRisks]
		.filter((item): item is string => isBoundedText(item, 256))
		.slice(0, 8);
	return identifiers.map((id) => ({ kind: 'conceptual-review', id }));
}

function findingCategory(assessment: ReviewerAssessment): StructuredConceptualFinding['category'] {
	if (assessment.unsupportedClaims.length > 0 || assessment.referenceRisks.length > 0) return 'EVIDENCE';
	if (assessment.notationRisks.length > 0) return 'NOTATION';
	if (assessment.requiredChanges.some((item) => /assumption/i.test(item))) return 'ASSUMPTION';
	if (/scope/i.test(assessment.scopeCompliance)) return 'SCOPE';
	return 'COHERENCE';
}

export class ScientificWorkflowService {
	private readonly newId: () => string;
	private readonly now: () => Date;

	constructor(private readonly dependencies: ScientificWorkflowServiceDependencies) {
		this.newId = dependencies.newId ?? randomUUID;
		this.now = dependencies.now ?? (() => new Date());
	}

	async synthesize(input: ScientificSynthesisRequest): Promise<ScientificSynthesisResult> {
		return this.runSynthesis(input, []);
	}

	async reopen(input: ScientificSynthesisRequest & { priorSynthesis: ThreadSynthesis; modificationCause: string }): Promise<ScientificSynthesisResult> {
		if (!isBoundedText(input.modificationCause) || input.priorSynthesis.threadId !== input.activeThread.threadId) {
			return { status: 'blocked', code: 'SYNTHESIS_REOPEN_INVALID', eventIds: [] };
		}
		const reopenEvent = await this.appendEvent(input.activeThread.threadId, 'SYNTHESIS_REOPENED', { status: 'DRAFT', synthesisId: input.priorSynthesis.synthesisId, synthesisDigest: input.priorSynthesis.digest, modificationCause: input.modificationCause }, [input.priorSynthesis.reviewEventId].filter((id): id is string => !!id));
		if (!reopenEvent) return { status: 'blocked', code: 'SYNTHESIS_REOPEN_PERSISTENCE_FAILED', eventIds: [] };
		const current = await this.dependencies.store.read();
		const activeThread = current?.snapshot.threads.find((thread) => thread.threadId === input.activeThread.threadId);
		if (!activeThread) return { status: 'blocked', code: 'SYNTHESIS_REOPEN_PERSISTENCE_FAILED', eventIds: [reopenEvent.eventId] };
		return this.runSynthesis({ ...input, activeThread }, [reopenEvent.eventId]);
	}

	async modifySynthesis(input: ScientificSynthesisRequest & { priorSynthesis: ThreadSynthesis; modificationCause: string; actor: ScientificActor }): Promise<ScientificSynthesisResult> {
		if (input.actor.kind !== 'USER') return { status: 'blocked', code: 'SCIENTIFIC_DECISION_ACTOR_FORBIDDEN', eventIds: [] };
		return this.reopen(input);
	}

	async acceptDecision(input: ScientificDecisionRequest): Promise<ScientificDecisionResult> {
		if (input.actor.kind !== 'USER') return { status: 'blocked', code: 'SCIENTIFIC_ACCEPTANCE_REQUIRES_USER' };
		return this.recordDecision(input.candidate, 'DECISION_ACCEPTED');
	}

	async rejectDecision(input: ScientificDecisionRequest): Promise<ScientificDecisionResult> {
		if (input.actor.kind !== 'USER') return { status: 'blocked', code: 'SCIENTIFIC_DECISION_ACTOR_FORBIDDEN' };
		return this.recordDecision(input.candidate, 'DECISION_REJECTED');
	}

	async retractDecision(input: { decisionId: string; actor: ScientificActor }): Promise<ScientificDecisionResult> {
		if (input.actor.kind !== 'USER') return { status: 'blocked', code: 'SCIENTIFIC_DECISION_ACTOR_FORBIDDEN' };
		try {
			const current = await this.dependencies.store.read();
			const snapshot = current ? clone(current.snapshot) as ScientificSnapshotRecord : undefined;
			const decision = snapshot?.decisions.find((candidate) => candidate.decisionId === input.decisionId);
			if (!current || !snapshot || !decision || decision.state !== 'ACCEPTED_UNMATERIALIZED') return { status: 'blocked', code: 'SCIENTIFIC_DECISION_RETRACTION_INVALID' };
			const thread = snapshot.threads.find((candidate) => candidate.threadId === decision.threadId);
			if (!thread) return { status: 'blocked', code: 'SCIENTIFIC_DECISION_RETRACTION_INVALID' };
			const event = this.lifecycleEvent(current.events.length + 1, thread.threadId, 'DECISION_RETRACTED', { decisionId: decision.decisionId, status: 'RETRACTED' }, [decision.acceptedEventId]);
			decision.state = 'RETRACTED';
			thread.headEventId = event.eventId;
			thread.status = snapshot.decisions.some((candidate) => candidate.threadId === thread.threadId && candidate.state === 'ACCEPTED_UNMATERIALIZED') ? 'ACCEPTED_UNMATERIALIZED' : 'RETRACTED';
			await this.dependencies.store.commitTransition({ events: [event], snapshot });
			return { status: 'recorded', eventId: event.eventId, decisionId: decision.decisionId, state: 'RETRACTED' };
		} catch {
			return { status: 'blocked', code: 'SCIENTIFIC_DECISION_PERSISTENCE_FAILED' };
		}
	}

	async recoveryDiagnostics(): Promise<ScientificRecoveryDiagnostics> {
		return this.dependencies.store.recoveryDiagnostics();
	}

	async retryMaterialization(record: MaterializationRecord) {
		return this.dependencies.store.retryMaterialization(record);
	}

	projectReentry(entry: ProjectEntry): ScientificWorkflowPublicResult {
		recordScientificMetric('entry');
		if (entry.recovery.required) recordScientificMetric('recovery_required');
		const candidates = entry.pendingCandidates ?? entry.pendingCandidateIds.map((decisionId) => ({ decisionId, threadId: entry.activeThreadId ?? 'unknown', state: 'ACCEPTED_UNMATERIALIZED' as const, eligibility: 'eligible' as const, blockers: [] }));
		return {
			status: entry.recovery.required ? 'recovery_required' : 'ready',
			operation: 'SCIENTIFIC_WORKFLOW',
			routeStage: 'SCIENTIFIC_WORKFLOW',
			entryState: entry.state,
			...(entry.activeThread ? { activeThread: entry.activeThread } : {}),
			relatedThreads: entry.relatedThreads ?? [],
			candidates,
			blockers: entry.blockers ?? (entry.recovery.required && entry.recovery.code ? [{ code: entry.recovery.code, message: 'Scientific state requires recovery.', nextAction: entry.recovery.action }] : []),
			nextAction: entry.nextAction ?? entry.recovery.action ?? null,
			auditStatus: entry.recovery.required ? 'FAIL' : 'PASS',
			selfAuditStatus: 'NOT_RUN',
			metrics: { routeStage: 'SCIENTIFIC_WORKFLOW', bypassedStages: ['LIFECYCLE', 'DIRECT_DOCUMENT', 'DELIBERATE'] },
		};
	}

	private async recordDecision(candidate: ScientificSynthesisCandidate, type: 'DECISION_ACCEPTED' | 'DECISION_REJECTED'): Promise<ScientificDecisionResult> {
		try {
			const current = await this.dependencies.store.read();
			const snapshot = current ? clone(current.snapshot) as ScientificSnapshotRecord : undefined;
			if (!current || !snapshot || !this.isReviewedCandidate(current.events, candidate)) return { status: 'blocked', code: 'SCIENTIFIC_REVIEWED_SYNTHESIS_REQUIRED' };
			const thread = snapshot.threads.find((existing) => existing.threadId === candidate.threadId);
			if (!thread) return { status: 'blocked', code: 'SCIENTIFIC_REVIEWED_SYNTHESIS_REQUIRED' };
			const decisionId = type === 'DECISION_ACCEPTED' ? this.newId() : undefined;
			const event = this.lifecycleEvent(current.events.length + 1, thread.threadId, type, {
				...(decisionId ? { decisionId } : {}),
				synthesisId: candidate.synthesisId,
				synthesisDigest: candidate.digest,
				status: type === 'DECISION_ACCEPTED' ? 'ACCEPTED_UNMATERIALIZED' : 'REJECTED',
			}, [candidate.reviewEventId!]);
			thread.headEventId = event.eventId;
			thread.status = type === 'DECISION_ACCEPTED' ? 'ACCEPTED_UNMATERIALIZED' : 'REJECTED';
			if (decisionId) {
				const decision: ScientificDecision = { decisionId, threadId: thread.threadId, acceptedEventId: event.eventId, acceptedSynthesisDigest: candidate.digest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: [candidate.tutorEventId, candidate.reviewEventId!] };
				snapshot.decisions.push(decision);
				thread.decisionIds.push(decisionId);
			}
			await this.dependencies.store.commitTransition({ events: [event], snapshot });
			return { status: 'recorded', eventId: event.eventId, ...(decisionId ? { decisionId } : {}), state: type === 'DECISION_ACCEPTED' ? 'ACCEPTED_UNMATERIALIZED' : 'REJECTED' };
		} catch {
			return { status: 'blocked', code: 'SCIENTIFIC_DECISION_PERSISTENCE_FAILED' };
		}
	}

	private isReviewedCandidate(events: ScientificEvent[], candidate: ScientificSynthesisCandidate): boolean {
		if (candidate.status !== 'REVIEWED' || !/^[0-9a-f]{64}$/.test(candidate.digest) || !candidate.reviewEventId || !candidate.tutorEventId) return false;
		const tutor = events.find((event) => event.eventId === candidate.tutorEventId);
		const review = events.find((event) => event.eventId === candidate.reviewEventId);
		return tutor?.type === 'TUTOR_ASSESSED'
			&& tutor.threadId === candidate.threadId
			&& tutor.payload.synthesisId === candidate.synthesisId
			&& tutor.payload.synthesisDigest === candidate.digest
			&& review?.type === 'CONCEPTUAL_REVIEW_RECORDED'
			&& review.actor.kind === 'CONCEPTUAL_REVIEWER'
			&& review.threadId === candidate.threadId
			&& review.payload.status === 'PASS'
			&& review.payload.synthesisId === candidate.synthesisId
			&& review.payload.synthesisDigest === candidate.digest
			&& review.causalEventIds.includes(candidate.tutorEventId);
	}

	private lifecycleEvent(sequence: number, threadId: string, type: 'DECISION_ACCEPTED' | 'DECISION_REJECTED' | 'DECISION_RETRACTED', payload: Record<string, unknown>, causalEventIds: ScientificEventId[]): ScientificEvent {
		return { schemaVersion: 1, eventId: this.newId(), sequence, occurredAt: this.now().toISOString(), actor: { kind: 'USER' }, type, threadId, causalEventIds, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
	}

	private async runSynthesis(input: ScientificSynthesisRequest, causalEventIds: ScientificEventId[]): Promise<ScientificSynthesisResult> {
		if (!this.dependencies.tutor) return { status: 'blocked', code: 'TUTOR_UNAVAILABLE', eventIds: causalEventIds };
		if (!this.dependencies.reviewer) return { status: 'blocked', code: 'CONCEPTUAL_REVIEWER_UNAVAILABLE', eventIds: causalEventIds };
		let context: Awaited<ReturnType<ScientificContextBuilder['build']>>;
		try {
			context = await this.dependencies.contextBuilder.build(input);
		} catch {
			return { status: 'blocked', code: 'SCIENTIFIC_CONTEXT_UNAVAILABLE', eventIds: causalEventIds };
		}

		let repairCycles = 0;
		let repairFinding: StructuredConceptualFinding | undefined;
		let instruction = input.instruction;
		const eventIds = causalEventIds.length > 0 ? [...causalEventIds] : [input.activeThread.headEventId];
		while (true) {
			const tutor = await this.assessTutor(instruction, context);
			if (!tutor) return { status: 'blocked', code: 'TUTOR_ASSESSMENT_INVALID', eventIds };
			// Operation kind/operands for a deliberated INSERT or DELETE are captured
			// from the USER's own original instruction (never a repair-cycle rewrite),
			// deterministically parsed by the existing `resolveIntent` -- the tutor only
			// reviews/refutes and supplies content, it never chooses kind or locus.
			const candidate = this.candidate(input.activeThread.threadId, tutor, input.instruction);
			const tutorEvent = await this.appendEvent(input.activeThread.threadId, 'TUTOR_ASSESSED', {
				status: candidate.status,
				summary: candidate.summary,
				synthesisId: candidate.synthesisId,
				synthesisDigest: candidate.digest,
				...(candidate.proposedEdit ? { proposedEdit: candidate.proposedEdit } : {}),
			}, [eventIds.at(-1)!]);
			if (!tutorEvent) return { status: 'blocked', code: 'SCIENTIFIC_ADVISORY_PERSISTENCE_FAILED', eventIds };
			eventIds.push(tutorEvent.eventId);
			const tutorCandidate = { ...candidate, tutorEventId: tutorEvent.eventId };

			const review = await this.assessReviewer(input.instruction, context, tutorCandidate);
			if (!review) return { status: 'blocked', code: 'CONCEPTUAL_REVIEW_INVALID', eventIds };
			const outcome = REVIEW_OUTCOMES[review.decision];
			const reviewerEvent = await this.appendEvent(input.activeThread.threadId, 'CONCEPTUAL_REVIEW_RECORDED', {
				status: outcome,
				synthesisId: tutorCandidate.synthesisId,
				synthesisDigest: tutorCandidate.digest,
				reason: this.reviewSummary(review),
			}, [tutorEvent.eventId]);
			if (!reviewerEvent) return { status: 'blocked', code: 'SCIENTIFIC_REVIEW_PERSISTENCE_FAILED', eventIds };
			eventIds.push(reviewerEvent.eventId);

			if (outcome === 'PASS') {
				return { status: 'reviewed', candidate: { ...tutorCandidate, status: 'REVIEWED', reviewEventId: reviewerEvent.eventId }, reviewOutcome: 'PASS', eventIds };
			}
			if (outcome !== 'REPAIR_REQUIRED') return { status: 'blocked', code: `CONCEPTUAL_REVIEW_${outcome}`, eventIds };
			const finding = this.finding(tutorCandidate, review);
			if (!finding) return { status: 'blocked', code: 'CONCEPTUAL_CRITIQUE_INVALID', eventIds };
			if (repairCycles >= 2) return { status: 'blocked', code: 'REPAIR_LOOP_EXHAUSTED', eventIds, finding };
			const repairEvent = await this.appendEvent(input.activeThread.threadId, 'REPAIR_PROPOSED', {
				status: 'REPAIR_REQUIRED',
				synthesisId: tutorCandidate.synthesisId,
				synthesisDigest: tutorCandidate.digest,
				findingId: finding.findingId,
				issueCategory: finding.category,
				evidenceReferences: finding.evidence.map((item) => `${item.kind}:${item.id}`),
				requiredCorrection: finding.requiredCorrection,
				constraints: finding.constraints,
			}, [reviewerEvent.eventId]);
			if (!repairEvent) return { status: 'blocked', code: 'SCIENTIFIC_REPAIR_PERSISTENCE_FAILED', eventIds, finding };
			eventIds.push(repairEvent.eventId);
			repairCycles += 1;
			repairFinding = finding;
			instruction = `Repair the supplied candidate using this structured conceptual finding: ${JSON.stringify(repairFinding)}`;
			try {
				context = await this.dependencies.contextBuilder.build(input);
			} catch {
				return { status: 'blocked', code: 'SCIENTIFIC_CONTEXT_UNAVAILABLE', eventIds, finding };
			}
		}
	}

	private async assessTutor(instruction: string, context: Awaited<ReturnType<ScientificContextBuilder['build']>>): Promise<TutorAssessment | undefined> {
		try {
			const assessment = await this.dependencies.tutor!.assess({ instruction, context: roleContext(context, instruction) });
			if (hasForbiddenAuthority(assessment) || !isBoundedText(assessment.summary)) return undefined;
			return validateTutorAssessment(assessment, context.documentFragments.map((fragment) => fragment.entryId));
		} catch {
			return undefined;
		}
	}

	private async assessReviewer(instruction: string, context: Awaited<ReturnType<ScientificContextBuilder['build']>>, candidate: ScientificSynthesisCandidate): Promise<ReviewerAssessment | undefined> {
		try {
			const assessment = await this.dependencies.reviewer!.review({ instruction, context: roleContext(context, instruction), plan: { synthesisId: candidate.synthesisId, digest: candidate.digest, summary: candidate.summary, ...(candidate.proposedEdit ? { proposedEdit: candidate.proposedEdit } : {}) } });
			if (hasForbiddenAuthority(assessment)) return undefined;
			return validateReviewerAssessment(assessment);
		} catch {
			return undefined;
		}
	}

	private candidate(threadId: string, assessment: TutorAssessment, rawInstruction: string): ScientificSynthesisCandidate {
		const synthesisId = this.newId();
		const summary = assessment.summary.trim();
		const proposedEdit = this.deriveProposedEdit(assessment, rawInstruction);
		// JSON.stringify drops an `undefined` proposedEdit, so the digest stays
		// byte-identical to the pre-repair summary-only digest when no edit was
		// liftable (additive-safe); when present, the edit is transitively frozen
		// into every downstream acceptance/materialization digest check.
		return { synthesisId, threadId, digest: digest({ synthesisId, threadId, summary, proposedEdit }), status: 'DRAFT', summary, tutorEventId: '', ...(proposedEdit ? { proposedEdit } : {}) };
	}

	/**
	 * Lifts the tutor's own already-emitted structured signal -- `proposedAlternative`
	 * (content/replacement text) targeted at exactly one already-validated
	 * `affectedEntryIds` locus -- into a genuine, reusable `EditAction`, instead of
	 * discarding it down to `summary` alone (closes the V2-PARTIAL gap: the scientific
	 * materialization route can apply a real structured edit instead of only
	 * annotating).
	 *
	 * Operation KIND (CHANGE/replace vs. deliberated ADD/insert vs. deliberated
	 * DELETE/delete) and its operands (position) come from the USER's own original
	 * instruction, deterministically parsed by the EXISTING `resolveIntent` parser --
	 * never invented or guessed by the tutor. The tutor only reviews/refutes the
	 * resulting operation and supplies the content-bearing side (`proposedAlternative`)
	 * for content-bearing kinds (`replace`/`insert`); it never chooses kind, locus, or
	 * position. Bounded to a single already-validated `affectedEntryIds` locus in every
	 * case -- multi-entry decomposition per decision remains an explicit, documented,
	 * unforced fallback (stays summary-only), exactly as before.
	 */
	private deriveProposedEdit(assessment: TutorAssessment, rawInstruction: string): EditAction | undefined {
		const resolved = resolveIntent(rawInstruction);

		// MOVE/COPY (a relocation) is bounded to exactly TWO already-validated loci
		// -- [sourceEntryId, destinationAnchorId], in that fixed order -- instead of
		// the single-locus bound every other kind uses below. Checked first, before
		// the single-locus gate, since it would otherwise always fail that gate.
		if (resolved.intent === 'MOVE' || resolved.intent === 'COPY') return this.deriveMoveCopyEdit(assessment, resolved);

		if (assessment.affectedEntryIds.length !== 1) return undefined;
		const entryId = assessment.affectedEntryIds[0]!;

		if (resolved.intent === 'DELETE') {
			// A deliberated DELETE carries no tutor-supplied content -- ACCEPT (tutor
			// agrees to remove exactly what the user asked) or ACCEPT_WITH_REVISIONS
			// (tutor agrees, with an otherwise-unrelated revision noted in `summary`)
			// both authorize it; REJECT_WITH_REASON/NEEDS_CLARIFICATION/PROPOSE_ALTERNATIVE
			// (tutor suggests doing something else instead of deleting) do not.
			if (assessment.decision !== 'ACCEPT' && assessment.decision !== 'ACCEPT_WITH_REVISIONS') return undefined;
			const reason = assessment.summary.trim();
			if (!isBoundedText(reason)) return undefined;
			const instructionEvidence = rawInstruction.trim().slice(0, 2_000);
			if (!isBoundedText(instructionEvidence)) return undefined;
			return { kind: 'delete', targetEntryId: entryId, instructionEvidence, reason };
		}

		if (resolved.intent === 'INSERT') {
			if (assessment.decision !== 'ACCEPT_WITH_REVISIONS' && assessment.decision !== 'PROPOSE_ALTERNATIVE') return undefined;
			const content = assessment.proposedAlternative?.trim();
			if (!isBoundedText(content, PROPOSED_EDIT_REPLACEMENT_MAX_BYTES)) return undefined;
			// Normalized to exactly `before`/`after` (never `inside_start`/`inside_end`):
			// both the composite engine's zero-width splice and `patch-compiler.ts`'s
			// `insertionPoint` agree on these two anchor-boundary semantics; the latter
			// throws for `inside_start`, so it is never persisted here.
			const position: Position = resolved.requestedPosition === 'before' || resolved.requestedPosition === 'inside_start' ? 'before' : 'after';
			return { kind: 'insert', anchorEntryId: entryId, position, content };
		}

		// Unchanged pre-existing behavior: the well-specified single-locus CHANGE case.
		if (assessment.decision !== 'ACCEPT_WITH_REVISIONS' && assessment.decision !== 'PROPOSE_ALTERNATIVE') return undefined;
		const replacementText = assessment.proposedAlternative?.trim();
		if (!isBoundedText(replacementText, PROPOSED_EDIT_REPLACEMENT_MAX_BYTES)) return undefined;
		return { kind: 'replace', targetEntryId: entryId, replacementText };
	}

	/**
	 * Lifts a deliberated MOVE/COPY (a relocation). Operation kind, source,
	 * destination, position, and `moveMode` all come from the USER's own
	 * original instruction via the EXISTING deterministic `resolveIntent` --
	 * never invented by the tutor. `affectedEntryIds` is bounded to exactly TWO
	 * already-validated loci, in the fixed order [sourceEntryId,
	 * destinationAnchorId]; any other length is a documented, unforced
	 * fallback (stays summary-only), exactly like the single-locus bound above.
	 *
	 * For a LITERAL relocation the tutor authors no content (the composite
	 * engine resolves the source's own frozen bytes at materialization) --
	 * ACCEPT or ACCEPT_WITH_REVISIONS both authorize it, mirroring DELETE's
	 * gate. For an ADAPTIVE relocation (the transition text must be reworded to
	 * fit its new context) the tutor's `proposedAlternative` becomes
	 * `transformedContent` -- REQUIRED and bounded; absent or oversized content
	 * is a block, never a fabrication, mirroring INSERT's gate.
	 */
	private deriveMoveCopyEdit(assessment: TutorAssessment, resolved: ResolvedIntent): EditAction | undefined {
		if (assessment.affectedEntryIds.length !== 2) return undefined;
		const [sourceEntryId, destinationAnchorId] = assessment.affectedEntryIds as [string, string];
		const isMove = resolved.intent === 'MOVE';
		// Normalized to exactly `before`/`after`, same convention as INSERT above:
		// both the composite engine's zero-width splice and `patch-compiler.ts`'s
		// `insertionPoint` only distinguish the anchor's start vs. end boundary.
		const position: Position = resolved.requestedPosition === 'before' || resolved.requestedPosition === 'inside_start' ? 'before' : 'after';
		if (resolved.moveMode === 'ADAPTIVE') {
			if (assessment.decision !== 'ACCEPT_WITH_REVISIONS' && assessment.decision !== 'PROPOSE_ALTERNATIVE') return undefined;
			const transformedContent = assessment.proposedAlternative?.trim();
			if (!isBoundedText(transformedContent, PROPOSED_EDIT_REPLACEMENT_MAX_BYTES)) return undefined;
			return { kind: isMove ? 'move' : 'copy', sourceEntryIds: [sourceEntryId], destinationAnchorId, position, moveMode: 'ADAPTIVE', removeSource: isMove, transformedContent, cleanupLevel: resolved.cleanupLevel };
		}
		if (assessment.decision !== 'ACCEPT' && assessment.decision !== 'ACCEPT_WITH_REVISIONS') return undefined;
		return { kind: isMove ? 'move' : 'copy', sourceEntryIds: [sourceEntryId], destinationAnchorId, position, moveMode: 'LITERAL', removeSource: isMove, cleanupLevel: resolved.cleanupLevel };
	}

	private finding(candidate: ScientificSynthesisCandidate, assessment: ReviewerAssessment): StructuredConceptualFinding | undefined {
		const requiredCorrection = assessment.requiredChanges.find((item): item is string => isBoundedText(item, 500));
		if (!requiredCorrection) return undefined;
		const constraints = [...assessment.unresolvedQuestions, assessment.scopeCompliance]
			.filter((item): item is string => isBoundedText(item, 500))
			.slice(0, 8);
		const evidence = evidenceForFinding(assessment);
		return { findingId: this.newId(), candidateSynthesisId: candidate.synthesisId, candidateSynthesisDigest: candidate.digest, category: findingCategory(assessment), evidence, requiredCorrection, constraints };
	}

	private reviewSummary(assessment: ReviewerAssessment) {
		const summary = assessment.scientificCoherence.trim();
		return isBoundedText(summary, 500) ? summary : assessment.decision;
	}

	private async appendEvent(threadId: string, type: Extract<ScientificEvent['type'], 'TUTOR_ASSESSED' | 'CONCEPTUAL_REVIEW_RECORDED' | 'REPAIR_PROPOSED' | 'SYNTHESIS_REOPENED'>, payload: Record<string, unknown>, causalEventIds: ScientificEventId[]): Promise<ScientificEvent | undefined> {
		try {
			const current = await this.dependencies.store.read();
			if (!current) return undefined;
			const snapshot = clone(current.snapshot) as ScientificSnapshotRecord;
			const thread = snapshot.threads.find((candidate) => candidate.threadId === threadId);
			if (!thread) return undefined;
			const event: ScientificEvent = {
				schemaVersion: 1,
				eventId: this.newId(),
				sequence: current.events.length + 1,
				occurredAt: this.now().toISOString(),
				actor: { kind: type === 'TUTOR_ASSESSED' || type === 'REPAIR_PROPOSED' ? 'TUTOR' : type === 'CONCEPTUAL_REVIEW_RECORDED' ? 'CONCEPTUAL_REVIEWER' : 'USER' },
				type,
				threadId,
				causalEventIds,
				payload,
				evidence: [],
				privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 },
			};
			thread.headEventId = event.eventId;
			thread.status = type === 'REPAIR_PROPOSED'
				? 'REPAIRED'
				: type === 'CONCEPTUAL_REVIEW_RECORDED'
					? 'UNDER_REVIEW'
					: type === 'SYNTHESIS_REOPENED'
						? 'OPEN'
						: thread.status;
			await this.dependencies.store.commitTransition({ events: [event], snapshot });
			return event;
		} catch {
			return undefined;
		}
	}
}
