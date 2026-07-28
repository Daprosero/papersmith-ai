import assert from 'node:assert/strict';
import * as nativeFs from 'node:fs/promises';
import { mkdtemp, readFile, symlink, writeFile } from 'node:fs/promises';
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

async function project() { return mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-scientific-store-')); }

function event(sequence, eventId, overrides = {}) {
	return {
		schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:0${sequence}:00.000Z`, actor: { kind: 'USER' },
		type: sequence === 1 ? 'THREAD_CREATED' : 'THREAD_SELECTED', threadId: 'thread-1', causalEventIds: sequence === 1 ? [] : ['event-1'],
		payload: { title: 'Question', summary: 'Bounded public summary.' }, evidence: [{ kind: 'user_input', id: `input-${sequence}` }],
		privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 }, ...overrides,
	};
}

function snapshot(headEventId = 'event-1', extras = {}) {
	return {
		schemaVersion: 1, activeThreadId: 'thread-1',
		threads: [{ threadId: 'thread-1', version: 1, status: 'OPEN', title: 'Question', summary: 'Bounded public summary.', createdEventId: 'event-1', headEventId, relationIds: [], decisionIds: [] }],
		relations: [], decisions: [], ...extras,
	};
}

async function seed(store) {
	return store.commitTransition({ transitionId: 'transition-1', events: [event(1, 'event-1')], snapshot: snapshot() });
}

async function expectCode(run, code) {
	await assert.rejects(run, (error) => error?.code === code || error?.message === code);
}

test('ScientificStateStore persists only versioned authoritative records and rebuilds its projection', async () => {
	const rootDir = await project();
	const store = new v2.ScientificStateStore(rootDir);
	const committed = await seed(store);
	assert.equal(committed.manifest.schemaVersion, 1);
	assert.equal(committed.events[0].eventId, 'event-1');
	assert.deepEqual(committed.projection.pendingCandidateIds, []);
	const scientific = path.join(rootDir, '.paper-proposal-v2/scientific');
	const projectionPath = path.join(scientific, 'projections/entry-index.json');
	await writeFile(projectionPath, '{"not":"authoritative"}');
	const reopened = await store.read();
	assert.equal(reopened.snapshot.activeThreadId, 'thread-1');
	assert.equal(reopened.projection.snapshotSha256, committed.manifest.snapshotSha256);
	assert.equal(JSON.parse(await readFile(path.join(scientific, 'manifest.json'), 'utf8')).eventCount, 1);
	assert.ok(await nativeFs.stat(path.join(scientific, 'events/1-event-1.json')));
});

test('ScientificStateStore rejects non-allowlisted, private, malformed, and duplicate authoritative records', async () => {
	const rootDir = await project();
	const store = new v2.ScientificStateStore(rootDir);
	await expectCode(() => store.commitTransition({ transitionId: 'private', events: [event(1, 'event-1', { payload: { prompt: 'hidden prompt' } })], snapshot: snapshot() }), 'SCIENTIFIC_PAYLOAD_NOT_ALLOWLISTED');
	await expectCode(() => store.commitTransition({ transitionId: 'causal', events: [event(1, 'event-1', { causalEventIds: ['event-1'] })], snapshot: snapshot() }), 'SCIENTIFIC_EVENT_CAUSALITY_INVALID');
	await seed(store);
	await expectCode(() => store.commitTransition({ transitionId: 'duplicate', events: [event(2, 'event-1')], snapshot: snapshot('event-1') }), 'SCIENTIFIC_EVENT_ID_INVALID');
	await expectCode(() => store.commitTransition({ transitionId: 'gap', events: [event(3, 'event-3')], snapshot: snapshot('event-3') }), 'SCIENTIFIC_EVENT_CONTINUITY_INVALID');
	await expectCode(() => store.commitTransition({ transitionId: 'dangling', events: [event(2, 'event-2')], snapshot: snapshot('event-2', { relations: [{ relationId: 'relation-1', kind: 'RELATED', fromThreadId: 'thread-1', toThreadId: 'missing', createdEventId: 'event-2' }] }) }), 'SCIENTIFIC_GRAPH_REFERENCE_INVALID');
});

test('ScientificStateStore rejects unsafe symlinks and does not follow them as records', async () => {
	const rootDir = await project();
	const store = new v2.ScientificStateStore(rootDir);
	await seed(store);
	const manifest = path.join(rootDir, '.paper-proposal-v2/scientific/manifest.json');
	const replacement = path.join(rootDir, 'replacement.json');
	await writeFile(replacement, await readFile(manifest));
	await nativeFs.rm(manifest);
	await symlink(replacement, manifest);
	await expectCode(() => store.read(), 'SCIENTIFIC_RECORD_UNSAFE');
});

test('ScientificStateStore keeps an interrupted transition fail-closed and recovery never invents state', async () => {
	const rootDir = await project();
	let writes = 0;
	const fs = {
		...nativeFs,
		async writeFile(...args) {
			writes += 1;
			if (writes === 2) throw new Error('INJECTED_EVENT_WRITE_FAILURE');
			return nativeFs.writeFile(...args);
		},
	};
	const store = new v2.ScientificStateStore(rootDir, { fs, newTransitionId: () => 'interrupted' });
	await assert.rejects(() => seed(store), /INJECTED_EVENT_WRITE_FAILURE/);
	await expectCode(() => store.read(), 'SCIENTIFIC_TRANSACTION_INCOMPLETE');
	assert.deepEqual(await store.recover(), { status: 'recovery_required', transitionId: 'transition-1', code: 'SCIENTIFIC_TRANSACTION_INCOMPLETE' });
	assert.equal(await nativeFs.stat(path.join(rootDir, '.paper-proposal-v2/scientific/transactions/transition-1.json')).then(() => true), true);
});

test('ScientificStateStore validates replay and can clean only a fully committed marker', async () => {
	const rootDir = await project();
	const store = new v2.ScientificStateStore(rootDir);
	const committed = await seed(store);
	const markerPath = path.join(rootDir, '.paper-proposal-v2/scientific/transactions/replay.json');
	await writeFile(markerPath, JSON.stringify({ schemaVersion: 1, transitionId: 'replay', state: 'COMMITTED', eventIds: ['event-1'], snapshotSha256: committed.manifest.snapshotSha256, manifestSha256: v2.scientificEvidenceDigest(committed.manifest) }));
	assert.deepEqual(await store.recover(), { status: 'recovered', transitionId: 'replay' });
	assert.equal(await nativeFs.access(markerPath).then(() => true, () => false), false);
	const eventsPath = path.join(rootDir, '.paper-proposal-v2/scientific/events/1-event-1.json');
	const invalid = JSON.parse(await readFile(eventsPath, 'utf8'));
	invalid.sequence = 9;
	await writeFile(eventsPath, JSON.stringify(invalid));
	await expectCode(() => store.read(), 'SCIENTIFIC_EVENT_FILE_CONFLICT');
});

test('scientific persistence imports canonical contracts and keeps storage-only records local', async () => {
	const source = await readFile(path.join(root, '.pi/extensions/paper-proposal-v2/scientific-state-store.ts'), 'utf8');
	assert.match(source, /scientific-domain\.js/);
	assert.match(source, /ScientificManifestRecord/);
	assert.match(source, /ScientificEntryProjection/);
	assert.doesNotMatch(source, /type\s+(?:ScientificThread|ScientificDecision|ScientificEvent|ThreadRelation|ThreadSynthesis|ScientificAct|ProjectEntryState)\s*=/);
});
