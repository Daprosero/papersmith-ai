import assert from 'node:assert/strict';
import * as nativeFs from 'node:fs/promises';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(path.join(root, '.pi/extensions/paper-proposal-v2/exports.ts'));

async function project() { return mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-scientific-resolvers-')); }
const inventory = { read: async () => ({ status: 'valid', activeRevisions: [], withdrawnRevisions: [], auditEvidence: ['revision-inventory:validated'] }) };
const resolvedIdea = { status: 'resolved', act: 'CONSTRUCT_IDEA', relatedThreadIds: [] };
const resolvedQuestion = { status: 'resolved', act: 'CONSTRUCT_QUESTION', relatedThreadIds: [] };
const emptyEntry = { state: 'EMPTY_PROJECT', relatedThreadIds: [], pendingCandidateIds: [], recovery: { required: false }, auditEvidence: [] };

function seedEvent(sequence, eventId, threadId, type = sequence === 1 ? 'THREAD_CREATED' : 'THREAD_SELECTED', causalEventIds = []) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:0${sequence}:00.000Z`, actor: { kind: 'USER' }, type, threadId, causalEventIds, payload: { title: 'Question', summary: 'Bounded summary.' }, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}

test('authoritative store backs entry and thread create/select/activate transitions without document writes', async () => {
	const rootDir = await project();
	const store = new v2.ScientificStateStore(rootDir);
	let id = 0;
	const resolver = new v2.ScientificThreadResolver(store, () => `id-${++id}`);
	const created = await resolver.resolve({ entry: emptyEntry, act: resolvedIdea, ideaSeed: { title: 'Question', summary: 'Bounded seed.', actor: { kind: 'USER' } } });
	assert.equal(created.status, 'created');
	const state = await store.read();
	assert.equal(state.events.length, 1);
	assert.equal(state.snapshot.activeThreadId, 'id-1');
	assert.equal((await new v2.ProjectEntryResolver(inventory, store).resolve()).state, 'SCIENTIFIC_ONLY');
	assert.equal(await nativeFs.access(path.join(rootDir, 'proposals')).then(() => true, () => false), false);

	const selected = await resolver.resolve({ entry: { ...emptyEntry, state: 'SCIENTIFIC_ONLY', activeThreadId: 'id-1' }, act: resolvedQuestion, requestedActiveThreadId: 'id-1' });
	assert.equal(selected.status, 'selected');
	const reopened = await store.read();
	assert.deepEqual(reopened.events.map((event) => event.type), ['THREAD_CREATED']);
});

test('authoritative store commits selection and activation together and fails closed on interruption', async () => {
	const rootDir = await project();
	const store = new v2.ScientificStateStore(rootDir);
	const events = [
		seedEvent(1, 'event-1', 'thread-1'),
		seedEvent(2, 'event-2', 'thread-2', 'THREAD_CREATED', ['event-1']),
		seedEvent(3, 'event-3', 'thread-1', 'THREAD_RELATED', ['event-1', 'event-2']),
	];
	const snapshot = {
		schemaVersion: 1, threads: [
			{ threadId: 'thread-1', version: 1, status: 'OPEN', title: 'First', summary: 'Bounded summary.', createdEventId: 'event-1', headEventId: 'event-3', relationIds: ['relation-1'], decisionIds: [] },
			{ threadId: 'thread-2', version: 1, status: 'OPEN', title: 'Second', summary: 'Bounded summary.', createdEventId: 'event-2', headEventId: 'event-2', relationIds: ['relation-1'], decisionIds: [] },
		], relations: [{ relationId: 'relation-1', kind: 'RELATED', fromThreadId: 'thread-1', toThreadId: 'thread-2', createdEventId: 'event-3' }], decisions: [],
	};
	await store.commitTransition({ transitionId: 'seed-graph', events, snapshot });
	let id = 0;
	const resolver = new v2.ScientificThreadResolver(store, () => `selected-${++id}`);
	const selected = await resolver.resolve({ entry: { ...emptyEntry, state: 'SCIENTIFIC_ONLY' }, act: resolvedQuestion, requestedActiveThreadId: 'thread-1', relatedThreadIds: ['thread-2'] });
	assert.equal(selected.status, 'selected');
	const state = await store.read();
	assert.deepEqual(state.events.slice(-3).map((event) => event.type), ['THREAD_SELECTED', 'THREAD_ACTIVATED', 'THREAD_RELATED']);
	assert.equal(state.snapshot.activeThreadId, 'thread-1');

	const interruptedRoot = await project();
	let writes = 0;
	const fs = { ...nativeFs, async writeFile(...args) { writes += 1; if (writes === 2) throw new Error('INJECTED_EVENT_WRITE_FAILURE'); return nativeFs.writeFile(...args); } };
	const interruptedStore = new v2.ScientificStateStore(interruptedRoot, { fs, newTransitionId: () => 'interrupted' });
	const interrupted = await new v2.ScientificThreadResolver(interruptedStore, () => 'thread-interrupted').resolve({ entry: emptyEntry, act: resolvedIdea, ideaSeed: { title: 'Question', summary: 'Bounded seed.', actor: { kind: 'USER' } } });
	assert.equal(interrupted.status, 'blocked');
	assert.equal(interrupted.code, 'THREAD_TRANSITION_INCOMPLETE');
	const entry = await new v2.ProjectEntryResolver(inventory, interruptedStore).resolve();
	assert.equal(entry.state, 'INCONSISTENT_PROJECT');
	assert.equal(entry.recovery.code, 'SCIENTIFIC_TRANSACTION_INCOMPLETE');
	assert.equal(await nativeFs.access(path.join(interruptedRoot, 'proposals')).then(() => true, () => false), false);
});
