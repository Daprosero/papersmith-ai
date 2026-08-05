import { createHash } from 'node:crypto';
import { ScientificStateStore, ScientificStateStoreError } from './scientific-state-store.js';
import type {
	MaterializationCandidateSummary,
	ProjectEntry,
	ProjectEntryBootstrap,
	ProjectEntryState,
	PublicBlocker,
	RevisionEvidence,
	ScientificDecision,
	ScientificEvent,
	ScientificThread,
	ThreadRelation,
	ThreadSummary,
} from './scientific-domain.js';

type ValidRevisionInventory = {
	status: 'valid';
	activeRevisions: RevisionEvidence[];
	withdrawnRevisions: RevisionEvidence[];
	/** Present only when the caller supplied explicit lifecycle-v1 evidence. */
	baseDocument?: { baseDocumentId: string; contentHash: string };
	lifecycleState?: 'EMPTY'|'BASE_REGISTERED'|'ACTIVE'|'WITHDRAWN_ONLY';
	auditEvidence: string[];
};

type InvalidRevisionInventory = {
	status: 'inconsistent';
	code: string;
	auditEvidence: string[];
};

export type RevisionInventoryEvidence = ValidRevisionInventory | InvalidRevisionInventory;

export type ScientificSnapshotEvidence = {
	schemaVersion: 1;
	activeThreadId?: string;
	threads: ScientificThread[];
	relations: ThreadRelation[];
	decisions: ScientificDecision[];
};

export type ScientificTransactionMarker = {
	transitionId: string;
	state: 'PREPARED' | 'COMMITTED';
};

export type PresentScientificStateEvidence = {
	status: 'present';
	manifest: { schemaVersion: 1; snapshotSha256: string; eventsSha256: string };
	snapshot: ScientificSnapshotEvidence;
	events: ScientificEvent[];
	transactionMarkers: ScientificTransactionMarker[];
	auditEvidence: string[];
};

export type ScientificStateEvidence =
	| { status: 'absent'; auditEvidence: string[] }
	| { status: 'inconsistent'; code: string; auditEvidence: string[] }
	| PresentScientificStateEvidence;

export interface ReadOnlyRevisionInventoryPort {
	read(): Promise<RevisionInventoryEvidence>;
}

export interface ReadOnlyScientificStateEvidencePort {
	read(): Promise<ScientificStateEvidence>;
}

export type ProjectEntryResolutionOptions = { bootstrapFromActiveProposal?: boolean };

const sha256 = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const sha = /^[0-9a-f]{64}$/;
const revision = /^r\d{2,}$/;

export function scientificEvidenceDigest(value: unknown) {
	return sha256(value);
}

function failure(code: string, auditEvidence: string[]): ProjectEntry {
	return {
		state: 'INCONSISTENT_PROJECT',
		relatedThreadIds: [],
		pendingCandidateIds: [],
		recovery: { required: true, code, action: 'reconcile_scientific_state' },
		auditEvidence,
	};
}

function validRevisionEvidence(value: RevisionEvidence) {
	return !!value && typeof value.filename === 'string' && typeof value.revision === 'string' && typeof value.documentSha256 === 'string'
		&& (value.filename.length > 0 || typeof value.revisionId === 'string') && (revision.test(value.revision) || typeof value.revisionId === 'string') && sha.test(value.documentSha256);
}

function validateRevisionInventory(evidence: RevisionInventoryEvidence): string | undefined {
	if (evidence.status === 'inconsistent') return evidence.code || 'REVISION_INVENTORY_INCONSISTENT';
	const seen = new Set<string>();
	for (const entry of [...evidence.activeRevisions, ...evidence.withdrawnRevisions]) {
		if (!validRevisionEvidence(entry)) return 'INVALID_REVISION_EVIDENCE';
		if (seen.has(entry.filename)) return 'DUPLICATE_REVISION_EVIDENCE';
		seen.add(entry.filename);
	}
	return undefined;
}

function matchingRevision(left: RevisionEvidence, right: RevisionEvidence) {
	return left.documentSha256 === right.documentSha256 && (left.revisionId&&right.revisionId ? left.revisionId===right.revisionId : left.filename === right.filename && left.revision === right.revision);
}

function validateScientificEvidence(evidence: PresentScientificStateEvidence, activeRevisions: RevisionEvidence[]): string | undefined {
	if (evidence.manifest?.schemaVersion !== 1 || evidence.snapshot?.schemaVersion !== 1) return 'SCIENTIFIC_SCHEMA_INVALID';
	if (!sha.test(evidence.manifest.snapshotSha256) || !sha.test(evidence.manifest.eventsSha256)) return 'SCIENTIFIC_DIGEST_INVALID';
	if (evidence.manifest.snapshotSha256 !== sha256(evidence.snapshot) || evidence.manifest.eventsSha256 !== sha256(evidence.events)) return 'SCIENTIFIC_DIGEST_MISMATCH';
	if (!Array.isArray(evidence.events) || !Array.isArray(evidence.snapshot.threads) || !Array.isArray(evidence.snapshot.relations) || !Array.isArray(evidence.snapshot.decisions)) return 'SCIENTIFIC_RECORDS_INVALID';
	if (evidence.events.length === 0 || evidence.snapshot.threads.length === 0) return 'SCIENTIFIC_AUTHORITATIVE_STATE_PARTIAL';
	if (evidence.transactionMarkers.length > 0) return 'SCIENTIFIC_TRANSACTION_INCOMPLETE';

	const eventIds = new Set<string>();
	const eventSequence = new Map<string, number>();
	for (let index = 0; index < evidence.events.length; index += 1) {
		const event = evidence.events[index];
		if (!event || event.schemaVersion !== 1 || typeof event.eventId !== 'string' || !event.eventId || event.sequence !== index + 1 || eventIds.has(event.eventId)) return 'SCIENTIFIC_EVENT_CONTINUITY_INVALID';
		if (!Number.isFinite(Date.parse(event.occurredAt)) || event.privacy?.contentClass !== 'PUBLIC_SUMMARY_ONLY' || event.privacy?.redactionVersion !== 1) return 'SCIENTIFIC_EVENT_SCHEMA_INVALID';
		eventIds.add(event.eventId);
		eventSequence.set(event.eventId, event.sequence);
	}

	const threads = new Map<string, ScientificThread>();
	for (const thread of evidence.snapshot.threads) {
		if (!thread || thread.version !== 1 || !thread.threadId || threads.has(thread.threadId) || !eventIds.has(thread.createdEventId) || !eventIds.has(thread.headEventId)) return 'SCIENTIFIC_THREAD_REFERENCE_INVALID';
		if (thread.revisionEvidence && (!validRevisionEvidence(thread.revisionEvidence) || !activeRevisions.some((entry) => matchingRevision(entry, thread.revisionEvidence!)))) return 'SCIENTIFIC_REVISION_EVIDENCE_STALE';
		threads.set(thread.threadId, thread);
	}

	for (const event of evidence.events) {
		if (event.threadId && !threads.has(event.threadId)) return 'SCIENTIFIC_EVENT_THREAD_ORPHANED';
		const causes = new Set<string>();
		for (const cause of event.causalEventIds) {
			if (!eventIds.has(cause) || causes.has(cause) || eventSequence.get(cause)! >= event.sequence) return 'SCIENTIFIC_EVENT_CAUSALITY_INVALID';
			causes.add(cause);
		}
	}

	const relations = new Map<string, ThreadRelation>();
	for (const relation of evidence.snapshot.relations) {
		if (!relation || !relation.relationId || relations.has(relation.relationId) || relation.fromThreadId === relation.toThreadId || !threads.has(relation.fromThreadId) || !threads.has(relation.toThreadId) || !eventIds.has(relation.createdEventId)) return 'SCIENTIFIC_GRAPH_REFERENCE_INVALID';
		relations.set(relation.relationId, relation);
	}
	for (const thread of threads.values()) if (thread.relationIds.some((id) => !relations.has(id))) return 'SCIENTIFIC_THREAD_RELATION_ORPHANED';
	for (const relation of relations.values()) if (!threads.get(relation.fromThreadId)!.relationIds.includes(relation.relationId) || !threads.get(relation.toThreadId)!.relationIds.includes(relation.relationId)) return 'SCIENTIFIC_GRAPH_REFERENCE_INVALID';

	const decisions = new Map<string, ScientificDecision>();
	for (const decision of evidence.snapshot.decisions) {
		const acceptance = evidence.events.find((event) => event.eventId === decision.acceptedEventId);
		if (!decision || !decision.decisionId || decisions.has(decision.decisionId) || !threads.has(decision.threadId) || !acceptance || acceptance.type !== 'DECISION_ACCEPTED' || acceptance.actor?.kind !== 'USER') return 'SCIENTIFIC_DECISION_REFERENCE_INVALID';
		if (decision.sourceEventIds.some((id) => !eventIds.has(id))) return 'SCIENTIFIC_DECISION_EVENT_ORPHANED';
		decisions.set(decision.decisionId, decision);
	}
	for (const thread of threads.values()) if (thread.decisionIds.some((id) => !decisions.has(id))) return 'SCIENTIFIC_THREAD_DECISION_ORPHANED';
	if (evidence.snapshot.activeThreadId && !threads.has(evidence.snapshot.activeThreadId)) return 'SCIENTIFIC_ACTIVE_THREAD_ORPHANED';
	return undefined;
}

function bootstrap(activeRevision: RevisionEvidence): ProjectEntryBootstrap {
	return {
		status: 'available',
		source: activeRevision,
		observations: [{ kind: 'verified_active_proposal', id: activeRevision.filename, sha256: activeRevision.documentSha256 }],
		unknownHistory: true,
	};
}

function summary(thread: ScientificThread): ThreadSummary {
	return { threadId: thread.threadId, status: thread.status, title: thread.title, summary: thread.summary };
}

function reentryProjection(snapshot: ScientificSnapshotEvidence): {
	activeThread?: ThreadSummary;
	relatedThreads: ThreadSummary[];
	pendingCandidates: MaterializationCandidateSummary[];
	blockers: PublicBlocker[];
	nextAction: string | null;
} {
	const threads = new Map(snapshot.threads.map((thread) => [thread.threadId, thread]));
	const active = snapshot.activeThreadId ? threads.get(snapshot.activeThreadId) : undefined;
	const relatedThreadIds = active
		? snapshot.relations
			.filter((relation) => relation.fromThreadId === active.threadId || relation.toThreadId === active.threadId)
			.map((relation) => relation.fromThreadId === active.threadId ? relation.toThreadId : relation.fromThreadId)
		: [];
	const pendingCandidates = snapshot.decisions
		.filter((decision) => decision.state === 'ACCEPTED_UNMATERIALIZED')
		.map((decision) => ({ decisionId: decision.decisionId, threadId: decision.threadId, state: decision.state, eligibility: 'eligible' as const, blockers: [] }));
	return {
		...(active ? { activeThread: summary(active) } : {}),
		relatedThreads: relatedThreadIds.map((threadId) => summary(threads.get(threadId)!)),
		pendingCandidates,
		blockers: [],
		nextAction: pendingCandidates.length > 0 ? 'request_materialization_with_explicit_candidate_ids' : null,
	};
}

export class ProjectEntryResolver {
	private readonly scientificState: ReadOnlyScientificStateEvidencePort;

	constructor(
		private readonly revisions: ReadOnlyRevisionInventoryPort,
		scientificState: ReadOnlyScientificStateEvidencePort | ScientificStateStore,
	) {
		this.scientificState = scientificState instanceof ScientificStateStore
			? { read: () => this.readAuthoritativeState(scientificState) }
			: scientificState;
	}

	async resolve(options: ProjectEntryResolutionOptions = {}): Promise<ProjectEntry> {
		const [revisionEvidence, scientificEvidence] = await Promise.all([this.revisions.read(), this.scientificState.read()]);
		const auditEvidence = [...revisionEvidence.auditEvidence, ...scientificEvidence.auditEvidence];
		if (scientificEvidence.status === 'inconsistent') return failure(scientificEvidence.code || 'SCIENTIFIC_AUTHORITATIVE_STATE_INVALID', auditEvidence);
		const revisionFailure = validateRevisionInventory(revisionEvidence);
		if (revisionFailure) return failure(revisionFailure, auditEvidence);
		const activeRevisions = revisionEvidence.activeRevisions;
		const lifecycleProjection = revisionEvidence.status === 'valid' && (revisionEvidence.baseDocument || revisionEvidence.lifecycleState)
			? { ...(revisionEvidence.baseDocument ? { baseDocument: structuredClone(revisionEvidence.baseDocument) } : {}), ...(revisionEvidence.lifecycleState ? { lifecycleState: revisionEvidence.lifecycleState } : {}) }
			: {};
		if (activeRevisions.length > 1) return {
			...lifecycleProjection,
			state: 'MULTIPLE_ACTIVE_REVISIONS',
			relatedThreadIds: [],
			pendingCandidateIds: [],
			recovery: { required: true, code: 'MULTIPLE_ACTIVE_REVISIONS', action: 'select_or_reconcile_active_revision' },
			auditEvidence,
		};
		if (scientificEvidence.status === 'present') {
			const scientificFailure = validateScientificEvidence(scientificEvidence, activeRevisions);
			if (scientificFailure) return failure(scientificFailure, auditEvidence);
			const projection = reentryProjection(scientificEvidence.snapshot);
			const pendingCandidateIds = projection.pendingCandidates.map((candidate) => candidate.decisionId);
			return {
				...lifecycleProjection,
				state: pendingCandidateIds.length
					? 'MATERIALIZATION_PENDING'
					: activeRevisions.length === 0
						? 'SCIENTIFIC_ONLY'
						: 'ACTIVE_SCIENTIFIC_PROJECT',
				activeRevision: activeRevisions[0],
				activeThreadId: scientificEvidence.snapshot.activeThreadId,
				relatedThreadIds: projection.relatedThreads.map((thread) => thread.threadId),
				...projection,
				pendingCandidateIds,
				recovery: { required: false },
				auditEvidence,
			};
		}
		if (activeRevisions.length === 1) {
			return {
				...lifecycleProjection,
				state: 'ACTIVE_PROPOSAL',
				activeRevision: activeRevisions[0],
				relatedThreadIds: [],
				pendingCandidateIds: [],
				recovery: { required: false },
				auditEvidence,
				...(options.bootstrapFromActiveProposal ? { bootstrap: bootstrap(activeRevisions[0]) } : {}),
			};
		}
		if (revisionEvidence.withdrawnRevisions.length > 0) return {
			...lifecycleProjection,
			state: 'WITHDRAWN_ONLY',
			relatedThreadIds: [],
			pendingCandidateIds: [],
			recovery: { required: false },
			auditEvidence,
		};
		return {
			...lifecycleProjection,
			state: 'EMPTY_PROJECT',
			relatedThreadIds: [],
			pendingCandidateIds: [],
			recovery: { required: false },
			auditEvidence,
		};
	}

	private async readAuthoritativeState(store: ScientificStateStore): Promise<ScientificStateEvidence> {
		try {
			const state = await store.read();
			if (!state) return { status: 'absent', auditEvidence: ['scientific-state:authoritative-absent'] };
			return {
				status: 'present',
				manifest: state.manifest,
				snapshot: state.snapshot,
				events: state.events,
				transactionMarkers: [],
				auditEvidence: ['scientific-state:authoritative-validated'],
			};
		} catch (error) {
			const code = error instanceof ScientificStateStoreError ? error.code : error instanceof Error ? error.message : String(error);
			return { status: 'inconsistent', code, auditEvidence: ['scientific-state:authoritative-blocked'] };
		}
	}
}
