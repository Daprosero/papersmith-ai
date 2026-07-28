import { createHash } from 'node:crypto';
import type {
	MaterializationClaimProvenance,
	MaterializationPlan,
	MaterializationRecord,
	RevisionEvidence,
	ScientificDecision,
	ScientificEvent,
	ScientificThread,
} from './scientific-domain.js';
import type { ScientificState } from './scientific-state-store.js';

export type MaterializationPlannerInput = {
	record: MaterializationRecord;
	state: ScientificState;
	/** Verified document evidence is required only for a successor plan. */
	source?: RevisionEvidence;
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

function isSortedUnique(ids: string[]) {
	return ids.length > 0 && ids.every((id, index) => /^[A-Za-z0-9_-]{1,128}$/.test(id) && (index === 0 || ids[index - 1] < id));
}

function sourceFor(selected: MaterializationRecord['selectedDecisions'], supplied?: RevisionEvidence): { kind: MaterializationPlan['kind']; source?: RevisionEvidence } | undefined {
	const evidence = selected.map((decision) => decision.revisionEvidence);
	if (evidence.every((value) => value === undefined)) return supplied === undefined ? { kind: 'CREATE_R01' } : undefined;
	if (evidence.some((value) => value === undefined)) return undefined;
	const expected = evidence[0]!;
	if (!evidence.every((value) => sameEvidence(value!, expected)) || !supplied || !sameEvidence(supplied, expected)) return undefined;
	return { kind: 'CREATE_SUCCESSOR', source: expected };
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

/** Converts a durable reservation into a bounded, non-writing document plan. */
export class MaterializationPlanner {
	plan(input: MaterializationPlannerInput): MaterializationPlannerResult {
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
		const claims: MaterializationClaimProvenance[] = [];
		for (const [index, reserved] of record.selectedDecisions.entries()) {
			const decision = decisions.get(reserved.decisionId);
			const thread = threads.get(reserved.threadId);
			if (!decision || !thread || decision.state !== 'ACCEPTED_UNMATERIALIZED' || decision.acceptedBy.kind !== 'USER' || decision.threadId !== reserved.threadId || decision.acceptedEventId !== record.frozenSelection.acceptedEventIds[index] || decision.acceptedSynthesisDigest !== reserved.acceptedSynthesisDigest || reserved.decisionId !== record.frozenSelection.decisionIds[index]) return { status: 'blocked', code: 'MATERIALIZATION_DECISION_INELIGIBLE' };
			const claim = claimFor(decision, thread, state.events);
			if (!claim || claim.summary.length > maxSummaryBytes) return { status: 'blocked', code: 'MATERIALIZATION_CLAIM_UNMAPPED' };
			claims.push(claim);
		}
		return {
			status: 'ready',
			plan: {
				planVersion: 1,
				kind: source.kind,
				materializationId: record.materializationId,
				frozenSelection: structuredClone(record.frozenSelection),
				...(source.source ? { source: structuredClone(source.source) } : {}),
				claims,
			},
		};
	}
}
