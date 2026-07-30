import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
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
const v2 = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/exports.ts'));

async function project() {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-audit-'));
	await mkdir(path.join(projectRoot, 'proposals'));
	return projectRoot;
}

function event(sequence, eventId, type, threadId, causalEventIds = []) {
	return {
		schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:0${sequence}:00.000Z`, actor: { kind: 'USER' }, type, threadId, causalEventIds,
		payload: { title: 'Question', summary: 'Bounded public summary.', relatedThreadIds: type === 'THREAD_RELATED' ? ['thread-2'] : [] }, evidence: [],
		privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 },
	};
}

function connectedSnapshot(revisionEvidence) {
	return {
		schemaVersion: 1, activeThreadId: 'thread-1',
		threads: [
			{ threadId: 'thread-1', version: 1, status: 'OPEN', title: 'Question', summary: 'Bounded public summary.', createdEventId: 'event-1', headEventId: 'event-3', ...(revisionEvidence ? { revisionEvidence } : {}), relationIds: ['relation-1'], decisionIds: [] },
			{ threadId: 'thread-2', version: 1, status: 'OPEN', title: 'Related question', summary: 'Bounded public summary.', createdEventId: 'event-2', headEventId: 'event-2', relationIds: ['relation-1'], decisionIds: [] },
		],
		relations: [{ relationId: 'relation-1', kind: 'RELATED', fromThreadId: 'thread-1', toThreadId: 'thread-2', createdEventId: 'event-3' }], decisions: [],
	};
}

async function seedConnected(rootDir, revisionEvidence) {
	const store = new v2.ScientificStateStore(rootDir);
	const events = [
		event(1, 'event-1', 'THREAD_CREATED', 'thread-1'),
		event(2, 'event-2', 'THREAD_CREATED', 'thread-2', ['event-1']),
		event(3, 'event-3', 'THREAD_RELATED', 'thread-1', ['event-1', 'event-2']),
	];
	await store.commitTransition({ transitionId: 'connected-graph', events, snapshot: connectedSnapshot(revisionEvidence) });
	return store;
}

test('scientific audit projects absent, validated, and stale revision evidence without mutating lifecycle inventory', async () => {
	const emptyRoot = await project();
	assert.equal((await v2.runScientificConsistencyAudit({ projectRoot: emptyRoot })).status, 'NOT_RUN');
	assert.equal((await v2.runConsistencyAudit({ projectRoot: emptyRoot })).status, 'PASS');

	const rootDir = await project();
	await seedConnected(rootDir);
	const scientific = await v2.runScientificConsistencyAudit({ projectRoot: rootDir });
	assert.equal(scientific.status, 'PASS');
	const combined = await v2.runConsistencyAudit({ projectRoot: rootDir });
	assert.equal(combined.status, 'PASS');
	assert.equal(combined.scientific.status, 'PASS');
	assert.equal((await v2.runPaperProposalSelfAudit({ projectRoot: rootDir })).checks.find((check) => check.id === 'scientific-consistency').status, 'PASS');

	const staleRoot = await project();
	const restoredBytes = 'restored bytes';
	await seedConnected(staleRoot, { filename: 'research-concept-r01.md', revision: 'r01', documentSha256: createHash('sha256').update(restoredBytes).digest('hex') });
	const stale = await v2.runScientificConsistencyAudit({ projectRoot: staleRoot });
	assert.equal(stale.status, 'FAIL');
	assert.ok(stale.failures.includes('SCIENTIFIC_REVISION_EVIDENCE_STALE:thread-1'));
	await writeFile(path.join(staleRoot, 'proposals/research-concept-r01.md'), restoredBytes);
	const restored = await v2.runScientificConsistencyAudit({ projectRoot: staleRoot });
	assert.equal(restored.status, 'PASS');
});

test('scientific storage rejects relationship records that are not explicit graph events', async () => {
	const rootDir = await project();
	const store = new v2.ScientificStateStore(rootDir);
	const events = [event(1, 'event-1', 'THREAD_CREATED', 'thread-1'), event(2, 'event-2', 'THREAD_CREATED', 'thread-2', ['event-1'])];
	const invalid = connectedSnapshot();
	invalid.threads[0].headEventId = 'event-1';
	invalid.relations[0].createdEventId = 'event-2';
	await assert.rejects(() => store.commitTransition({ transitionId: 'invalid-graph', events, snapshot: invalid }), (error) => error?.code === 'SCIENTIFIC_GRAPH_RELATION_EVENT_INVALID');
});
