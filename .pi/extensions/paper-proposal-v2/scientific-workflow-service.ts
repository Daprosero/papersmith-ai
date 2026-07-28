import { createHash, randomUUID } from 'node:crypto';
import type { ReviewerAdapter, ReviewerAssessment } from './reviewer-adapter.js';
import { validateReviewerAssessment } from './reviewer-adapter.js';
import { ScientificContextBuilder, type ScientificContextBuilderInput } from './scientific-context-builder.js';
import { createProductionReviewerAdapter } from './production-reviewer-adapter.js';
import { ProductionModelRuntime } from './production-runtime.js';
import { createProductionTutorAdapter } from './production-tutor-adapter.js';
import type { ScientificSnapshotRecord } from './scientific-state-store.js';
import { ScientificStateStore } from './scientific-state-store.js';
import type { TutorAdapter, TutorAssessment } from './tutor-adapter.js';
import { validateTutorAssessment } from './tutor-adapter.js';
import type {
	ConceptualReviewOutcome,
	EvidenceReference,
	ScientificEvent,
	ScientificEventId,
	ScientificSynthesisCandidate,
	ScientificThread,
	StructuredConceptualFinding,
	ThreadSynthesis,
} from './scientific-domain.js';

export type ScientificSynthesisRequest = ScientificContextBuilderInput & {
	instruction: string;
};

export type ScientificSynthesisResult =
	| { status: 'reviewed'; candidate: ScientificSynthesisCandidate; reviewOutcome: 'PASS'; eventIds: ScientificEventId[] }
	| { status: 'blocked'; code: string; eventIds: ScientificEventId[]; finding?: StructuredConceptualFinding };

export type ScientificWorkflowServiceDependencies = {
	store: ScientificStateStore;
	contextBuilder: ScientificContextBuilder;
	tutor?: TutorAdapter;
	reviewer?: ReviewerAdapter;
	newId?: () => string;
	now?: () => Date;
};

/** Reuses the existing production role adapters without granting workflow authority to the runtime. */
export function createProductionScientificRoleAdapters(runtime: ProductionModelRuntime): Pick<ScientificWorkflowServiceDependencies, 'tutor' | 'reviewer'> {
	return { tutor: createProductionTutorAdapter(runtime), reviewer: createProductionReviewerAdapter(runtime) };
}

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
		return this.runSynthesis(input, [reopenEvent.eventId]);
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
			const candidate = this.candidate(input.activeThread.threadId, tutor);
			const tutorEvent = await this.appendEvent(input.activeThread.threadId, 'TUTOR_ASSESSED', {
				status: candidate.status,
				summary: candidate.summary,
				synthesisId: candidate.synthesisId,
				synthesisDigest: candidate.digest,
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
			const assessment = await this.dependencies.reviewer!.review({ instruction, context: roleContext(context, instruction), plan: { synthesisId: candidate.synthesisId, digest: candidate.digest, summary: candidate.summary } });
			if (hasForbiddenAuthority(assessment)) return undefined;
			return validateReviewerAssessment(assessment);
		} catch {
			return undefined;
		}
	}

	private candidate(threadId: string, assessment: TutorAssessment): ScientificSynthesisCandidate {
		const synthesisId = this.newId();
		const summary = assessment.summary.trim();
		return { synthesisId, threadId, digest: digest({ synthesisId, threadId, summary }), status: 'DRAFT', summary, tutorEventId: '' };
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
			thread.status = type === 'REPAIR_PROPOSED' ? 'REPAIRED' : type === 'CONCEPTUAL_REVIEW_RECORDED' ? 'UNDER_REVIEW' : thread.status;
			await this.dependencies.store.commitTransition({ events: [event], snapshot });
			return event;
		} catch {
			return undefined;
		}
	}
}
