import { randomUUID } from 'node:crypto';
import { ScientificStateStore } from './scientific-state-store.js';
import type {
	BoundedScientificSeed,
	ProjectEntry,
	ScientificActResolution,
	ScientificThread,
	ScientificThreadId,
	ThreadRelation,
	ThreadResolution,
	ThreadTransitionIntent,
} from './scientific-domain.js';

export type ScientificThreadStateSnapshot = {
	activeThreadId?: ScientificThreadId;
	threads: ScientificThread[];
	relations: ThreadRelation[];
};

export interface ReadOnlyScientificThreadStatePort {
	read(): Promise<ScientificThreadStateSnapshot>;
}

export interface ThreadTransitionIntentPort {
	commit(intents: ThreadTransitionIntent[]): Promise<void>;
}

export type ScientificThreadResolverInput = {
	entry: ProjectEntry;
	act: Extract<ScientificActResolution, { status: 'resolved' }>;
	requestedActiveThreadId?: ScientificThreadId;
	relatedThreadIds?: ScientificThreadId[];
	ideaSeed?: BoundedScientificSeed;
};

export type ScientificThreadIdFactory = () => ScientificThreadId;

const usableThreadStatuses = new Set(['OPEN', 'UNDER_REVIEW', 'REPAIRED', 'ACCEPTED_UNMATERIALIZED']);

function blocked(code: string, message: string): ThreadResolution {
	return { status: 'blocked', code, blockers: [{ code, message, nextAction: 'select_or_reconcile_thread' }] };
}

function isBoundedSeed(seed: BoundedScientificSeed | undefined): seed is BoundedScientificSeed {
	return !!seed
		&& seed.actor?.kind === 'USER'
		&& seed.title.trim().length > 0
		&& seed.summary.trim().length > 0
		&& seed.title.length <= 200
		&& seed.summary.length <= 2_000;
}

function sameRevision(left: ScientificThread['revisionEvidence'], right: ProjectEntry['activeRevision']) {
	return !left || (!!right && left.filename === right.filename && left.revision === right.revision && left.documentSha256 === right.documentSha256);
}

export class ScientificThreadResolver {
	private readonly state: ReadOnlyScientificThreadStatePort;
	private readonly transitions: ThreadTransitionIntentPort;
	private readonly createId: ScientificThreadIdFactory;

	constructor(
		state: ReadOnlyScientificThreadStatePort | ScientificStateStore,
		transitionsOrCreateId?: ThreadTransitionIntentPort | ScientificThreadIdFactory,
		createId: ScientificThreadIdFactory = () => randomUUID(),
	) {
		if (state instanceof ScientificStateStore) {
			this.state = { read: () => state.readThreadState() };
			this.transitions = { commit: (intents) => state.commitThreadTransition(intents) };
			this.createId = typeof transitionsOrCreateId === 'function' ? transitionsOrCreateId : createId;
			return;
		}
		if (!transitionsOrCreateId || typeof transitionsOrCreateId === 'function') throw new Error('SCIENTIFIC_TRANSITION_PORT_REQUIRED');
		this.state = state;
		this.transitions = transitionsOrCreateId;
		this.createId = createId;
	}

	async resolve(input: ScientificThreadResolverInput): Promise<ThreadResolution> {
		const snapshot = await this.state.read();
		const threads = new Map(snapshot.threads.map((thread) => [thread.threadId, thread]));
		if (threads.size !== snapshot.threads.length) return blocked('THREAD_STATE_INVALID', 'Scientific thread identities are not unique.');

		const requestedThreadId = input.requestedActiveThreadId ?? input.act.requestedThreadId;
		if (input.requestedActiveThreadId && input.act.requestedThreadId && input.requestedActiveThreadId !== input.act.requestedThreadId) {
			return blocked('THREAD_SELECTION_CONFLICT', 'The requested active thread does not match the act selection.');
		}
		const relatedThreadIds = [...new Set(input.relatedThreadIds ?? input.act.relatedThreadIds)];

		if (input.act.act === 'CONSTRUCT_IDEA' && isBoundedSeed(input.ideaSeed)) {
			return this.create(input, relatedThreadIds);
		}
		if (input.act.act === 'CONSTRUCT_IDEA' && input.ideaSeed) return blocked('THREAD_SEED_INVALID', 'An idea seed must be bounded and user-originated.');

		if (requestedThreadId) {
			const selected = threads.get(requestedThreadId);
			if (!selected) return blocked('THREAD_NOT_FOUND', 'The requested thread is not part of this project.');
			const validation = this.validateThread(selected, input.entry);
			if (validation) return validation;
			const relationError = this.validateDirectRelations(selected.threadId, relatedThreadIds, threads, snapshot.relations);
			if (relationError) return relationError;
			return this.select(selected, snapshot.activeThreadId, relatedThreadIds);
		}

		if (snapshot.activeThreadId) {
			const active = threads.get(snapshot.activeThreadId);
			if (!active) return blocked('THREAD_STATE_STALE', 'The active-thread projection references an unknown thread.');
			const validation = this.validateThread(active, input.entry);
			if (validation) return validation;
			const relationError = this.validateDirectRelations(active.threadId, relatedThreadIds, threads, snapshot.relations);
			if (relationError) return relationError;
			return { status: 'continued', activeThread: active, intents: [] };
		}

		if (threads.size > 1) return { status: 'needs_clarification', code: 'THREAD_SELECTION_AMBIGUOUS', question: 'Select the thread to continue.' };
		return { status: 'needs_clarification', code: 'THREAD_REQUIRED', question: 'Select an active thread or provide a bounded idea seed.' };
	}

	private validateThread(thread: ScientificThread, entry: ProjectEntry): ThreadResolution | undefined {
		if (!usableThreadStatuses.has(thread.status)) return blocked('THREAD_NOT_ELIGIBLE', 'The requested thread is blocked, rejected, or retracted for this act.');
		if (!sameRevision(thread.revisionEvidence, entry.activeRevision)) return blocked('THREAD_EVIDENCE_STALE', 'The requested thread has stale revision evidence.');
		return undefined;
	}

	private validateDirectRelations(
		activeThreadId: ScientificThreadId,
		relatedThreadIds: ScientificThreadId[],
		threads: Map<ScientificThreadId, ScientificThread>,
		relations: ThreadRelation[],
	): ThreadResolution | undefined {
		for (const relatedThreadId of relatedThreadIds) {
			if (relatedThreadId === activeThreadId || !threads.has(relatedThreadId)) return blocked('THREAD_RELATION_INVALID', 'A related thread must be a distinct project thread.');
			const direct = relations.some((relation) =>
				(relation.fromThreadId === activeThreadId && relation.toThreadId === relatedThreadId)
				|| (relation.toThreadId === activeThreadId && relation.fromThreadId === relatedThreadId),
			);
			if (!direct) return blocked('THREAD_RELATION_NOT_DIRECT', 'Related threads must be explicit direct graph neighbors.');
		}
		return undefined;
	}

	private async create(input: ScientificThreadResolverInput, relatedThreadIds: ScientificThreadId[]): Promise<ThreadResolution> {
		if (relatedThreadIds.length > 0) return blocked('THREAD_RELATION_NOT_DIRECT', 'A new thread cannot select unvalidated related threads.');
		const threadId = this.createId();
		const eventId = this.createId();
		const seed = input.ideaSeed!;
		const activeThread: ScientificThread = {
			threadId,
			version: 1,
			status: 'OPEN',
			title: seed.title.trim(),
			summary: seed.summary.trim(),
			createdEventId: eventId,
			headEventId: eventId,
			relationIds: [],
			decisionIds: [],
		};
		const intents: ThreadTransitionIntent[] = [{ type: 'THREAD_CREATED', eventId, threadId, activeThreadId: threadId, causalEventIds: [], relatedThreadIds: [], seed }];
		try {
			await this.transitions.commit(intents);
			return { status: 'created', activeThread, intents };
		} catch {
			return blocked('THREAD_TRANSITION_INCOMPLETE', 'The thread transition could not be recorded.');
		}
	}

	private async select(activeThread: ScientificThread, currentActiveThreadId: ScientificThreadId | undefined, relatedThreadIds: ScientificThreadId[]): Promise<ThreadResolution> {
		if (currentActiveThreadId === activeThread.threadId && relatedThreadIds.length === 0) return { status: 'selected', activeThread, intents: [] };
		const intents: ThreadTransitionIntent[] = [];
		if (currentActiveThreadId !== activeThread.threadId) {
			const selectedEventId = this.createId();
			intents.push({ type: 'THREAD_SELECTED', eventId: selectedEventId, threadId: activeThread.threadId, activeThreadId: activeThread.threadId, causalEventIds: [], relatedThreadIds });
			intents.push({ type: 'THREAD_ACTIVATED', eventId: this.createId(), threadId: activeThread.threadId, activeThreadId: activeThread.threadId, causalEventIds: [selectedEventId], relatedThreadIds });
		}
		for (const relatedThreadId of relatedThreadIds) {
			intents.push({ type: 'THREAD_RELATED', eventId: this.createId(), threadId: activeThread.threadId, activeThreadId: activeThread.threadId, causalEventIds: [], relatedThreadIds: [relatedThreadId] });
		}
		try {
			await this.transitions.commit(intents);
			return { status: 'selected', activeThread, intents };
		} catch {
			return blocked('THREAD_TRANSITION_INCOMPLETE', 'The thread transition could not be recorded.');
		}
	}
}
