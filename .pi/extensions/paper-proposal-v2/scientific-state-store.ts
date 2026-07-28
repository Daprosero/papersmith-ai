import { createHash, randomUUID } from 'node:crypto';
import { constants } from 'node:fs';
import { link, lstat, mkdir, open, readdir, readFile, realpath, rename, rm, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { withMutationLock } from './mutation-lock.js';
import type {
	ScientificDecision,
	ScientificEvent,
	ScientificEventId,
	ScientificThread,
	ScientificThreadId,
	ThreadRelation,
	ThreadTransitionIntent,
} from './scientific-domain.js';

export type ScientificSnapshotRecord = {
	schemaVersion: 1;
	activeThreadId?: ScientificThreadId;
	threads: ScientificThread[];
	relations: ThreadRelation[];
	decisions: ScientificDecision[];
};

export type ScientificManifestRecord = {
	schemaVersion: 1;
	snapshotSha256: string;
	eventsSha256: string;
	eventCount: number;
	headEventId?: ScientificEventId;
};

export type ScientificTransitionMarker = {
	schemaVersion: 1;
	transitionId: string;
	state: 'PREPARED' | 'COMMITTED';
	eventIds: ScientificEventId[];
	snapshotSha256: string;
	manifestSha256: string;
};

export type ScientificEntryProjection = {
	schemaVersion: 1;
	snapshotSha256: string;
	activeThreadId?: ScientificThreadId;
	pendingCandidateIds: string[];
};

export type ScientificState = {
	manifest: ScientificManifestRecord;
	snapshot: ScientificSnapshotRecord;
	events: ScientificEvent[];
	projection: ScientificEntryProjection;
};

export type ScientificTransition = {
	transitionId?: string;
	events: ScientificEvent[];
	snapshot: ScientificSnapshotRecord;
};

export type ScientificRecoveryResult =
	| { status: 'clean' }
	| { status: 'recovered'; transitionId: string }
	| { status: 'recovery_required'; transitionId: string; code: string };

type ScientificFs = {
	link: typeof link;
	lstat: typeof lstat;
	mkdir: typeof mkdir;
	open: typeof open;
	readdir: typeof readdir;
	readFile: typeof readFile;
	realpath: typeof realpath;
	rename: typeof rename;
	rm: typeof rm;
	writeFile: typeof writeFile;
};

export type ScientificStateStoreDependencies = {
	fs?: ScientificFs;
	newTransitionId?: () => string;
};

const defaultFs: ScientificFs = { link, lstat, mkdir, open, readdir, readFile, realpath, rename, rm, writeFile };
const EVENT_FILE = /^(\d+)-([A-Za-z0-9_-]+)\.json$/;
const SHA256 = /^[0-9a-f]{64}$/;
const FORBIDDEN_PRIVATE_KEYS = /(?:chain.?of.?thought|hidden.?prompt|raw.?trace|private.?reasoning|transcript|\bprompt\b|\btrace\b|\bthought\b)/i;
const ALLOWED_PAYLOAD_KEYS = new Set(['title', 'summary', 'status', 'decisionId', 'synthesisDigest', 'relationId', 'relatedThreadIds', 'activeThreadId', 'candidateIds', 'reason', 'code']);
const ALLOWED_EVIDENCE_KINDS = /^[a-z][a-z0-9_-]{0,63}$/;
const THREAD_RELATION_KINDS = new Set(['RELATED', 'SUPPORTS', 'CHALLENGES', 'DEPENDS_ON']);

export class ScientificStateStoreError extends Error {
	constructor(readonly code: string) {
		super(code);
	}
}

const digest = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const fail = (code: string): never => { throw new ScientificStateStoreError(code); };
const errorCode = (error: unknown) => error instanceof ScientificStateStoreError ? error.code : error instanceof Error ? error.message : String(error);
const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

function statePath(root: string) { return join(root, '.paper-proposal-v2', 'scientific'); }
function layout(root: string) {
	const scientific = statePath(root);
	return {
		scientific,
		manifest: join(scientific, 'manifest.json'),
		snapshot: join(scientific, 'snapshot.json'),
		events: join(scientific, 'events'),
		materializations: join(scientific, 'materializations'),
		transactions: join(scientific, 'transactions'),
		projections: join(scientific, 'projections'),
		entryIndex: join(scientific, 'projections', 'entry-index.json'),
	};
}

function assertPlainText(value: unknown, maximum: number, code: string) {
	if (typeof value !== 'string' || value.length === 0 || value.length > maximum || FORBIDDEN_PRIVATE_KEYS.test(value)) fail(code);
}

function assertPublicValue(value: unknown, depth = 0): void {
	if (depth > 3) fail('SCIENTIFIC_PAYLOAD_DEPTH_INVALID');
	if (typeof value === 'string') {
		if (value.length > 2_000 || FORBIDDEN_PRIVATE_KEYS.test(value)) fail('SCIENTIFIC_PRIVACY_VIOLATION');
		return;
	}
	if (typeof value === 'number' || typeof value === 'boolean' || value === null) return;
	if (Array.isArray(value)) {
		if (value.length > 16) fail('SCIENTIFIC_PAYLOAD_LIMIT_INVALID');
		for (const item of value) assertPublicValue(item, depth + 1);
		return;
	}
	if (!isObject(value)) fail('SCIENTIFIC_PAYLOAD_INVALID');
	for (const [key, nested] of Object.entries(value)) {
		if (FORBIDDEN_PRIVATE_KEYS.test(key)) fail('SCIENTIFIC_PRIVACY_VIOLATION');
		assertPublicValue(nested, depth + 1);
	}
}

function validateEvent(event: unknown, expectedSequence: number, knownEventIds: Set<string>) {
	if (!isObject(event) || event.schemaVersion !== 1 || typeof event.eventId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(event.eventId) || knownEventIds.has(event.eventId)) fail('SCIENTIFIC_EVENT_ID_INVALID');
	if (event.sequence !== expectedSequence || typeof event.occurredAt !== 'string' || !Number.isFinite(Date.parse(event.occurredAt))) fail('SCIENTIFIC_EVENT_CONTINUITY_INVALID');
	if (!isObject(event.actor) || typeof event.actor.kind !== 'string') fail('SCIENTIFIC_EVENT_ACTOR_INVALID');
	if (typeof event.type !== 'string' || !isObject(event.payload) || !Array.isArray(event.causalEventIds) || !Array.isArray(event.evidence)) fail('SCIENTIFIC_EVENT_SCHEMA_INVALID');
	if (!isObject(event.privacy) || event.privacy.contentClass !== 'PUBLIC_SUMMARY_ONLY' || event.privacy.redactionVersion !== 1) fail('SCIENTIFIC_PRIVACY_INVALID');
	for (const key of Object.keys(event.payload)) if (!ALLOWED_PAYLOAD_KEYS.has(key)) fail('SCIENTIFIC_PAYLOAD_NOT_ALLOWLISTED');
	assertPublicValue(event.payload);
	const causes = new Set<string>();
	for (const cause of event.causalEventIds) {
		if (typeof cause !== 'string' || !knownEventIds.has(cause) || causes.has(cause)) fail('SCIENTIFIC_EVENT_CAUSALITY_INVALID');
		causes.add(cause);
	}
	for (const evidence of event.evidence) {
		if (!isObject(evidence) || typeof evidence.kind !== 'string' || !ALLOWED_EVIDENCE_KINDS.test(evidence.kind) || typeof evidence.id !== 'string' || evidence.id.length === 0 || evidence.id.length > 256 || (evidence.sha256 !== undefined && (typeof evidence.sha256 !== 'string' || !SHA256.test(evidence.sha256)))) fail('SCIENTIFIC_EVIDENCE_INVALID');
	}
	knownEventIds.add(event.eventId);
}

function validateSnapshot(snapshot: unknown, events: ScientificEvent[]) {
	if (!isObject(snapshot) || snapshot.schemaVersion !== 1 || !Array.isArray(snapshot.threads) || !Array.isArray(snapshot.relations) || !Array.isArray(snapshot.decisions)) fail('SCIENTIFIC_SNAPSHOT_SCHEMA_INVALID');
	const eventsById = new Map(events.map((event) => [event.eventId, event]));
	const threads = new Map<string, ScientificThread>();
	for (const thread of snapshot.threads) {
		if (!isObject(thread) || thread.version !== 1 || typeof thread.threadId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(thread.threadId) || threads.has(thread.threadId)) fail('SCIENTIFIC_THREAD_ID_INVALID');
		assertPlainText(thread.title, 200, 'SCIENTIFIC_THREAD_TITLE_INVALID');
		assertPlainText(thread.summary, 2_000, 'SCIENTIFIC_THREAD_SUMMARY_INVALID');
		if (typeof thread.createdEventId !== 'string' || typeof thread.headEventId !== 'string' || !eventsById.has(thread.createdEventId) || !eventsById.has(thread.headEventId) || !Array.isArray(thread.relationIds) || !Array.isArray(thread.decisionIds)) fail('SCIENTIFIC_THREAD_REFERENCE_INVALID');
		const head = eventsById.get(thread.headEventId)!;
		if (head.threadId !== thread.threadId) fail('SCIENTIFIC_THREAD_HEAD_CONFLICT');
		threads.set(thread.threadId, thread as ScientificThread);
	}
	const relations = new Map<string, ThreadRelation>();
	const relationEdges = new Set<string>();
	for (const relation of snapshot.relations) {
		if (!isObject(relation) || typeof relation.relationId !== 'string' || relations.has(relation.relationId) || !THREAD_RELATION_KINDS.has(relation.kind as string) || typeof relation.fromThreadId !== 'string' || typeof relation.toThreadId !== 'string' || relation.fromThreadId === relation.toThreadId || !threads.has(relation.fromThreadId) || !threads.has(relation.toThreadId) || typeof relation.createdEventId !== 'string' || !eventsById.has(relation.createdEventId)) fail('SCIENTIFIC_GRAPH_REFERENCE_INVALID');
		const created = eventsById.get(relation.createdEventId)!;
		if (created.type !== 'THREAD_RELATED' || (created.threadId !== relation.fromThreadId && created.threadId !== relation.toThreadId)) fail('SCIENTIFIC_GRAPH_RELATION_EVENT_INVALID');
		const edge = [relation.kind, ...[relation.fromThreadId, relation.toThreadId].sort()].join(':');
		if (relationEdges.has(edge)) fail('SCIENTIFIC_GRAPH_RELATION_DUPLICATE');
		relationEdges.add(edge);
		relations.set(relation.relationId, relation as ThreadRelation);
	}
	for (const thread of threads.values()) {
		if (new Set(thread.relationIds).size !== thread.relationIds.length || thread.relationIds.some((id) => !relations.has(id))) fail('SCIENTIFIC_THREAD_RELATION_ORPHANED');
		for (const relationId of thread.relationIds) {
			const relation = relations.get(relationId)!;
			if (relation.fromThreadId !== thread.threadId && relation.toThreadId !== thread.threadId) fail('SCIENTIFIC_GRAPH_REFERENCE_INVALID');
		}
	}
	for (const relation of relations.values()) if (!threads.get(relation.fromThreadId)!.relationIds.includes(relation.relationId) || !threads.get(relation.toThreadId)!.relationIds.includes(relation.relationId)) fail('SCIENTIFIC_GRAPH_REFERENCE_INVALID');
	const decisions = new Map<string, ScientificDecision>();
	for (const decision of snapshot.decisions) {
		if (!isObject(decision) || typeof decision.decisionId !== 'string' || decisions.has(decision.decisionId) || typeof decision.threadId !== 'string' || !threads.has(decision.threadId) || typeof decision.acceptedEventId !== 'string' || !Array.isArray(decision.sourceEventIds)) fail('SCIENTIFIC_DECISION_REFERENCE_INVALID');
		const acceptance = eventsById.get(decision.acceptedEventId);
		if (!acceptance || acceptance.type !== 'DECISION_ACCEPTED' || acceptance.actor.kind !== 'USER' || !decision.sourceEventIds.every((id) => typeof id === 'string' && eventsById.has(id))) fail('SCIENTIFIC_DECISION_REFERENCE_INVALID');
		decisions.set(decision.decisionId, decision as ScientificDecision);
	}
	for (const thread of threads.values()) if (new Set(thread.decisionIds).size !== thread.decisionIds.length || thread.decisionIds.some((id) => !decisions.has(id))) fail('SCIENTIFIC_THREAD_DECISION_ORPHANED');
	if (snapshot.activeThreadId !== undefined && (typeof snapshot.activeThreadId !== 'string' || !threads.has(snapshot.activeThreadId))) fail('SCIENTIFIC_ACTIVE_THREAD_ORPHANED');
}

function deriveProjection(snapshot: ScientificSnapshotRecord): ScientificEntryProjection {
	return {
		schemaVersion: 1,
		snapshotSha256: digest(snapshot),
		...(snapshot.activeThreadId ? { activeThreadId: snapshot.activeThreadId } : {}),
		pendingCandidateIds: snapshot.decisions.filter((decision) => decision.state === 'ACCEPTED_UNMATERIALIZED').map((decision) => decision.decisionId),
	};
}

export class ScientificStateStore {
	private readonly fs: ScientificFs;
	private readonly newTransitionId: () => string;

	constructor(private readonly projectRoot: string, dependencies: ScientificStateStoreDependencies = {}) {
		this.fs = dependencies.fs ?? defaultFs;
		this.newTransitionId = dependencies.newTransitionId ?? randomUUID;
	}

	async read(): Promise<ScientificState | undefined> {
		return this.withLock(async () => this.readValidated(false));
	}

	async commitTransition(input: ScientificTransition): Promise<ScientificState> {
		return this.withLock(() => this.commitTransitionLocked(input));
	}

	private async commitTransitionLocked(input: ScientificTransition): Promise<ScientificState> {
		const root = await this.safeProjectRoot();
		await this.ensureLayout(root);
		const existing = await this.readValidated(false);
		const transitionId = input.transitionId ?? this.newTransitionId();
		if (!/^[A-Za-z0-9_-]{1,128}$/.test(transitionId)) fail('SCIENTIFIC_TRANSITION_ID_INVALID');
		const markerPath = join(layout(root).transactions, `${transitionId}.json`);
		if (await this.exists(markerPath)) fail('SCIENTIFIC_TRANSITION_EXISTS');
		const allEvents = [...(existing?.events ?? []), ...input.events];
		if (input.events.length === 0) fail('SCIENTIFIC_TRANSITION_EMPTY');
		this.validateEvents(allEvents);
		validateSnapshot(input.snapshot, allEvents);
		const manifest: ScientificManifestRecord = {
			schemaVersion: 1,
			snapshotSha256: digest(input.snapshot),
			eventsSha256: digest(allEvents),
			eventCount: allEvents.length,
			...(allEvents.at(-1) ? { headEventId: allEvents.at(-1)!.eventId } : {}),
		};
		const marker: ScientificTransitionMarker = { schemaVersion: 1, transitionId, state: 'PREPARED', eventIds: input.events.map((event) => event.eventId), snapshotSha256: manifest.snapshotSha256, manifestSha256: digest(manifest) };
		await this.writeAtomic(markerPath, marker);
		for (const event of input.events) await this.writeImmutableEvent(join(layout(root).events, `${event.sequence}-${event.eventId}.json`), event);
		await this.writeAtomic(layout(root).snapshot, input.snapshot);
		await this.writeAtomic(layout(root).manifest, manifest);
		const projection = deriveProjection(input.snapshot);
		await this.writeAtomic(layout(root).entryIndex, projection);
		await this.writeAtomic(markerPath, { ...marker, state: 'COMMITTED' });
		await this.removeRegularFile(markerPath);
		return { manifest, snapshot: input.snapshot, events: allEvents, projection };
	}

	async readThreadState(): Promise<{ activeThreadId?: ScientificThreadId; threads: ScientificThread[]; relations: ThreadRelation[] }> {
		const state = await this.read();
		return state
			? { ...(state.snapshot.activeThreadId ? { activeThreadId: state.snapshot.activeThreadId } : {}), threads: state.snapshot.threads, relations: state.snapshot.relations }
			: { threads: [], relations: [] };
	}

	async commitThreadTransition(intents: ThreadTransitionIntent[]): Promise<void> {
		if (intents.length === 0) return;
		return this.withLock(async () => {
		const existing = await this.readValidated(false);
		const snapshot: ScientificSnapshotRecord = existing
			? structuredClone(existing.snapshot)
			: { schemaVersion: 1, threads: [], relations: [], decisions: [] };
		const existingEvents = existing?.events ?? [];
		const threads = new Map(snapshot.threads.map((thread) => [thread.threadId, thread]));
		const relations = new Map(snapshot.relations.map((relation) => [relation.relationId, relation]));
		const events: ScientificEvent[] = [];
		for (const [index, intent] of intents.entries()) {
			if (!/^[A-Za-z0-9_-]{1,128}$/.test(intent.eventId) || existingEvents.some((event) => event.eventId === intent.eventId) || events.some((event) => event.eventId === intent.eventId)) fail('SCIENTIFIC_EVENT_ID_INVALID');
			if (!threads.has(intent.threadId) && intent.type !== 'THREAD_CREATED') fail('SCIENTIFIC_THREAD_REFERENCE_INVALID');
			if (intent.type === 'THREAD_CREATED') {
				if (threads.has(intent.threadId) || !intent.seed || intent.seed.actor.kind !== 'USER') fail('SCIENTIFIC_THREAD_TRANSITION_INVALID');
				const thread: ScientificThread = { threadId: intent.threadId, version: 1, status: 'OPEN', title: intent.seed.title, summary: intent.seed.summary, createdEventId: intent.eventId, headEventId: intent.eventId, relationIds: [], decisionIds: [] };
				threads.set(thread.threadId, thread);
				snapshot.threads.push(thread);
			} else if (intent.type === 'THREAD_RELATED') {
				for (const relatedThreadId of intent.relatedThreadIds) {
					const direct = [...relations.values()].some((relation) => (relation.fromThreadId === intent.threadId && relation.toThreadId === relatedThreadId) || (relation.toThreadId === intent.threadId && relation.fromThreadId === relatedThreadId));
					if (!direct) fail('SCIENTIFIC_THREAD_RELATION_NOT_DIRECT');
				}
			}
			const thread = threads.get(intent.threadId)!;
			const event: ScientificEvent = {
				schemaVersion: 1,
				eventId: intent.eventId,
				sequence: existingEvents.length + index + 1,
				occurredAt: new Date().toISOString(),
				actor: { kind: 'USER' },
				type: intent.type,
				threadId: intent.threadId,
				causalEventIds: intent.causalEventIds,
				payload: intent.type === 'THREAD_CREATED'
					? { title: intent.seed!.title, summary: intent.seed!.summary, activeThreadId: intent.activeThreadId }
					: { activeThreadId: intent.activeThreadId, relatedThreadIds: intent.relatedThreadIds },
				evidence: [],
				privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 },
			};
			thread.headEventId = event.eventId;
			snapshot.activeThreadId = intent.activeThreadId;
			events.push(event);
		}
		await this.commitTransitionLocked({ events, snapshot });
		});
	}

	async recover(): Promise<ScientificRecoveryResult> {
		return this.withLock(async () => {
			const root = await this.safeProjectRoot();
			const paths = layout(root);
			if (!await this.exists(paths.scientific)) return { status: 'clean' };
			await this.ensureLayout(root);
			const markers = await this.readMarkers(paths.transactions);
			if (markers.length === 0) return { status: 'clean' };
			if (markers.length !== 1 || markers[0].state !== 'COMMITTED') return { status: 'recovery_required', transitionId: markers[0]?.transitionId ?? 'unknown', code: 'SCIENTIFIC_TRANSACTION_INCOMPLETE' };
			try {
				const state = await this.readValidated(true);
				if (!state || digest(state.manifest) !== markers[0].manifestSha256 || state.manifest.snapshotSha256 !== markers[0].snapshotSha256) return { status: 'recovery_required', transitionId: markers[0].transitionId, code: 'SCIENTIFIC_TRANSACTION_CONFLICT' };
				await this.removeRegularFile(join(paths.transactions, `${markers[0].transitionId}.json`));
				return { status: 'recovered', transitionId: markers[0].transitionId };
			} catch (error) {
				return { status: 'recovery_required', transitionId: markers[0].transitionId, code: errorCode(error) };
			}
		});
	}

	private async withLock<T>(run: () => Promise<T>): Promise<T> {
		const root = await this.safeProjectRoot();
		return withMutationLock(`scientific-state\0${root}`, run);
	}

	private async safeProjectRoot(): Promise<string> {
		const info = await this.fs.lstat(this.projectRoot).catch(() => fail('SCIENTIFIC_PROJECT_ROOT_MISSING'));
		if (!info.isDirectory() || info.isSymbolicLink()) fail('SCIENTIFIC_PROJECT_ROOT_UNSAFE');
		const approvedRoot = await this.fs.realpath(resolve(this.projectRoot)).catch(() => fail('SCIENTIFIC_PROJECT_ROOT_UNSAFE'));
		const candidateRoot = await this.fs.realpath(this.projectRoot).catch(() => fail('SCIENTIFIC_PROJECT_ROOT_UNSAFE'));
		if (resolve(candidateRoot) !== resolve(approvedRoot)) fail('SCIENTIFIC_PROJECT_ROOT_UNSAFE');
		return candidateRoot;
	}

	private async ensureLayout(root: string) {
		const paths = layout(root);
		for (const directory of [join(root, '.paper-proposal-v2'), paths.scientific, paths.events, paths.materializations, paths.transactions, paths.projections]) {
			if (!await this.exists(directory)) await this.fs.mkdir(directory, { recursive: false });
			await this.assertExactDirectory(directory);
		}
	}

	private async assertExactDirectory(path: string) {
		const info = await this.fs.lstat(path).catch(() => fail('SCIENTIFIC_DIRECTORY_MISSING'));
		if (!info.isDirectory() || info.isSymbolicLink() || resolve(await this.fs.realpath(path)) !== resolve(path)) fail('SCIENTIFIC_DIRECTORY_UNSAFE');
	}

	private async exists(path: string) {
		try { await this.fs.lstat(path); return true; } catch { return false; }
	}

	private async readValidated(ignoreMarkers: boolean): Promise<ScientificState | undefined> {
		const root = await this.safeProjectRoot();
		const paths = layout(root);
		if (!await this.exists(paths.scientific)) return undefined;
		await this.ensureLayout(root);
		const markers = await this.readMarkers(paths.transactions);
		if (!ignoreMarkers && markers.length > 0) fail('SCIENTIFIC_TRANSACTION_INCOMPLETE');
		const required = [paths.manifest, paths.snapshot];
		const present = await Promise.all(required.map((path) => this.exists(path)));
		if (present.some(Boolean) && !present.every(Boolean)) fail('SCIENTIFIC_AUTHORITATIVE_STATE_PARTIAL');
		if (!present.every(Boolean)) {
			const eventNames = await this.fs.readdir(paths.events);
			if (eventNames.length > 0) fail('SCIENTIFIC_AUTHORITATIVE_STATE_PARTIAL');
			return undefined;
		}
		const manifest = await this.readJson<ScientificManifestRecord>(paths.manifest);
		const snapshot = await this.readJson<ScientificSnapshotRecord>(paths.snapshot);
		const eventNames = await this.fs.readdir(paths.events);
		const parsedNames = eventNames.map((name) => ({ name, match: EVENT_FILE.exec(name) })).sort((left, right) => Number(left.match?.[1]) - Number(right.match?.[1]));
		if (parsedNames.some(({ match }) => !match)) fail('SCIENTIFIC_EVENT_FILE_INVALID');
		const events = await Promise.all(parsedNames.map(({ name, match }) => this.readJson<ScientificEvent>(join(paths.events, name)).then((event) => {
			if (`${event.sequence}-${event.eventId}.json` !== name || Number(match![1]) !== event.sequence) fail('SCIENTIFIC_EVENT_FILE_CONFLICT');
			return event;
		})));
		this.validateEvents(events);
		validateSnapshot(snapshot, events);
		if (!isObject(manifest) || manifest.schemaVersion !== 1 || manifest.snapshotSha256 !== digest(snapshot) || manifest.eventsSha256 !== digest(events) || manifest.eventCount !== events.length || manifest.headEventId !== events.at(-1)?.eventId) fail('SCIENTIFIC_MANIFEST_INVALID');
		const projection = deriveProjection(snapshot);
		if (await this.exists(paths.entryIndex)) {
			const info = await this.fs.lstat(paths.entryIndex);
			if (!info.isFile() || info.isSymbolicLink()) fail('SCIENTIFIC_PROJECTION_UNSAFE');
		}
		return { manifest, snapshot, events, projection };
	}

	private validateEvents(events: ScientificEvent[]) {
		const ids = new Set<string>();
		for (let index = 0; index < events.length; index += 1) validateEvent(events[index], index + 1, ids);
	}

	private async readMarkers(directory: string): Promise<ScientificTransitionMarker[]> {
		const names = await this.fs.readdir(directory);
		const markers: ScientificTransitionMarker[] = [];
		for (const name of names) {
			if (!/^[A-Za-z0-9_-]{1,128}\.json$/.test(name)) fail('SCIENTIFIC_TRANSACTION_FILE_INVALID');
			const marker = await this.readJson<ScientificTransitionMarker>(join(directory, name));
			if (!isObject(marker) || marker.schemaVersion !== 1 || marker.transitionId !== basename(name, '.json') || (marker.state !== 'PREPARED' && marker.state !== 'COMMITTED') || !Array.isArray(marker.eventIds) || !SHA256.test(marker.snapshotSha256) || !SHA256.test(marker.manifestSha256)) fail('SCIENTIFIC_TRANSACTION_MARKER_INVALID');
			markers.push(marker);
		}
		return markers;
	}

	private async readJson<T>(path: string): Promise<T> {
		const info = await this.fs.lstat(path).catch(() => fail('SCIENTIFIC_RECORD_MISSING'));
		if (!info.isFile() || info.isSymbolicLink()) fail('SCIENTIFIC_RECORD_UNSAFE');
		try { return JSON.parse(await this.fs.readFile(path, 'utf8')) as T; } catch { return fail('SCIENTIFIC_RECORD_INVALID'); }
	}

	private async writeAtomic(path: string, value: unknown) {
		await this.assertExactDirectory(dirname(path));
		const temporary = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
		try {
			await this.fs.writeFile(temporary, JSON.stringify(value), { flag: 'wx', mode: 0o600 });
			await this.syncFile(temporary);
			await this.fs.rename(temporary, path);
			await this.syncDirectory(dirname(path));
		} catch (error) {
			await this.fs.rm(temporary, { force: true }).catch(() => undefined);
			throw error;
		}
	}

	private async writeImmutableEvent(path: string, event: ScientificEvent) {
		await this.assertExactDirectory(dirname(path));
		if (await this.exists(path)) fail('SCIENTIFIC_EVENT_ALREADY_EXISTS');
		const temporary = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
		try {
			await this.fs.writeFile(temporary, JSON.stringify(event), { flag: 'wx', mode: 0o600 });
			await this.syncFile(temporary);
			await this.fs.link(temporary, path);
			await this.syncDirectory(dirname(path));
			await this.fs.rm(temporary, { force: true });
		} catch (error) {
			await this.fs.rm(temporary, { force: true }).catch(() => undefined);
			if ((error as NodeJS.ErrnoException).code === 'EEXIST') fail('SCIENTIFIC_EVENT_ALREADY_EXISTS');
			throw error;
		}
	}

	private async removeRegularFile(path: string) {
		const info = await this.fs.lstat(path).catch(() => fail('SCIENTIFIC_RECORD_MISSING'));
		if (!info.isFile() || info.isSymbolicLink()) fail('SCIENTIFIC_RECORD_UNSAFE');
		await this.fs.rm(path);
		await this.syncDirectory(dirname(path));
	}

	private async syncFile(path: string) {
		const handle = await this.fs.open(path, constants.O_RDONLY);
		try { await handle.sync(); } finally { await handle.close(); }
	}

	private async syncDirectory(path: string) {
		const handle = await this.fs.open(path, constants.O_RDONLY);
		try { await handle.sync(); } finally { await handle.close(); }
	}
}
