import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
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

const revision = { filename: 'research-concept-r01.md', revision: 'r01', documentSha256: 'a'.repeat(64) };
const thread = (threadId, relationIds = [], extras = {}) => ({
	threadId, version: 1, status: 'OPEN', title: `Thread ${threadId}`, summary: `Public summary for ${threadId}.`,
	createdEventId: `${threadId}-created`, headEventId: `${threadId}-head`, relationIds, decisionIds: [], ...extras,
});
const evidence = (id) => ({ kind: 'document-fragment', id, sha256: 'b'.repeat(64) });
const event = (eventId, threadId, items = []) => ({
	schemaVersion: 1, eventId, sequence: 1, occurredAt: '2026-01-01T00:00:00.000Z', actor: { kind: 'USER' }, type: 'THREAD_CREATED', threadId,
	causalEventIds: [], payload: { title: 'Public title', summary: 'Public summary.' }, evidence: items,
	privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 },
});
const fragment = (entryId, text = 'Bounded public document fragment.') => ({ entryId, type: 'paragraph', text, textSha256: v2.sha256(text), headingPath: ['Method'] });

function builder(snapshot, options = {}) {
	return new v2.ScientificContextBuilder({ read: async () => snapshot }, options);
}

test('ScientificContextBuilder uses the active thread, explicit direct neighbor, relevant evidence, and verified bounded fragment only', async () => {
	const active = thread('active', ['active-related']);
	const related = thread('related', ['active-related']);
	const unrelated = thread('unrelated');
	const activeEvidence = evidence('entry-active');
	const relatedEvidence = evidence('entry-related');
	const unrelatedEvidence = evidence('entry-unrelated');
	const requested = [];
	const context = await builder({
		threads: [active, related, unrelated],
		relations: [{ relationId: 'active-related', kind: 'RELATED', fromThreadId: 'active', toThreadId: 'related', createdEventId: 'related-event' }],
		events: [event('active-event', 'active', [activeEvidence]), event('related-event', 'related', [relatedEvidence]), event('unrelated-event', 'unrelated', [unrelatedEvidence])],
	}, { documentFragments: { load: async (input) => {
		requested.push(input);
		return { revision, fragments: [fragment('entry-active')] };
	} } }).build({
		activeThread: active,
		requestedDirectRelationIds: ['related'],
		act: 'REQUEST_TUTOR',
		actEvidence: [activeEvidence],
		verifiedRevision: revision,
		documentEntryIds: ['entry-active'],
	});
	assert.equal(context.activeThread.threadId, 'active');
	assert.deepEqual(context.relatedThreads.map((item) => item.threadId), ['related']);
	assert.deepEqual(context.evidence, [activeEvidence]);
	assert.deepEqual(context.documentFragments.map((item) => item.entryId), ['entry-active']);
	assert.equal(context.documentFragments[0].revision.documentSha256, revision.documentSha256);
	assert.equal(context.privacy.contentClass, 'PUBLIC_SUMMARY_ONLY');
	assert.equal(requested.length, 1);
	assert.deepEqual(requested[0].entryIds, ['entry-active']);
	assert.equal(requested[0].maxFragments <= 4, true);
	assert.equal(context.byteCount <= context.limits.maxBytes, true);
	await assert.rejects(() => builder({ threads: [active, related, unrelated], relations: [{ relationId: 'active-related', kind: 'RELATED', fromThreadId: 'active', toThreadId: 'related', createdEventId: 'related-event' }], events: [event('unrelated-event', 'unrelated', [unrelatedEvidence])] }).build({ activeThread: active, requestedDirectRelationIds: ['related'], act: 'REQUEST_TUTOR', actEvidence: [unrelatedEvidence] }), { code: 'SCIENTIFIC_CONTEXT_EVIDENCE_NOT_RELEVANT' });
});

test('ScientificContextBuilder rejects transitive and implicit relation expansion', async () => {
	const active = thread('active', ['active-direct']);
	const direct = thread('direct', ['active-direct', 'direct-transitive']);
	const transitive = thread('transitive', ['direct-transitive']);
	const state = {
		threads: [active, direct, transitive],
		relations: [
			{ relationId: 'active-direct', kind: 'RELATED', fromThreadId: 'active', toThreadId: 'direct', createdEventId: 'direct-event' },
			{ relationId: 'direct-transitive', kind: 'RELATED', fromThreadId: 'direct', toThreadId: 'transitive', createdEventId: 'transitive-event' },
		],
		events: [],
	};
	const withoutSelection = await builder(state).build({ activeThread: active, requestedDirectRelationIds: [], act: 'CONSTRUCT_QUESTION' });
	assert.deepEqual(withoutSelection.relatedThreads, []);
	await assert.rejects(() => builder(state).build({ activeThread: active, requestedDirectRelationIds: ['transitive'], act: 'CONSTRUCT_QUESTION' }), { code: 'SCIENTIFIC_CONTEXT_RELATION_NOT_DIRECT' });
});

test('ScientificContextBuilder enforces narrowing count and byte caps without full-document or transcript expansion', async () => {
	const active = thread('active', ['one', 'two']);
	const one = thread('one', ['one']);
	const two = thread('two', ['two']);
	const oneEvidence = evidence('entry-one');
	const twoEvidence = evidence('entry-two');
	const loads = [];
	const context = await builder({
		threads: [active, one, two],
		relations: [
			{ relationId: 'one', kind: 'RELATED', fromThreadId: 'active', toThreadId: 'one', createdEventId: 'one-event' },
			{ relationId: 'two', kind: 'RELATED', fromThreadId: 'active', toThreadId: 'two', createdEventId: 'two-event' },
		],
		events: [event('active-event', 'active', [oneEvidence, twoEvidence])],
	}, {
		limits: { maxRelatedThreads: 1, maxEvidence: 1, maxDocumentFragments: 1 },
		documentFragments: { load: async (input) => { loads.push(input); return { revision, fragments: [fragment('entry-one'), fragment('entry-two')] }; } },
	}).build({
		activeThread: active,
		requestedDirectRelationIds: ['one', 'two'],
		act: 'REQUEST_TUTOR',
		actEvidence: [oneEvidence, twoEvidence],
		verifiedRevision: revision,
		documentEntryIds: ['entry-one', 'entry-two'],
	});
	assert.deepEqual(context.relatedThreads.map((item) => item.threadId), ['one']);
	assert.deepEqual(context.evidence, [oneEvidence]);
	assert.deepEqual(context.documentFragments.map((item) => item.entryId), ['entry-one']);
	assert.deepEqual(loads[0].entryIds, ['entry-one']);
	assert.equal(context.documentFragments.some((item) => /raw role transcript/i.test(item.text)), false);
	assert.equal(context.byteCount <= context.limits.maxBytes, true);
	const privateActive = thread('private', [], { summary: 'Hidden prompt with raw role transcript.' });
	await assert.rejects(() => builder({ threads: [privateActive], relations: [], events: [] }).build({ activeThread: privateActive, requestedDirectRelationIds: [], act: 'CONSTRUCT_QUESTION' }), { code: 'SCIENTIFIC_CONTEXT_PRIVATE_CONTENT' });
});

test('ScientificContextBuilder uses canonical contracts and has no role, persistence, or full-document loader authority', async () => {
	const source = await readFile(path.join(root, '.claude/skills/paper-proposal/engine/scientific-context-builder.ts'), 'utf8');
	assert.match(source, /scientific-domain\.js/);
	assert.match(source, /VerifiedDocumentFragmentPort/);
	assert.doesNotMatch(source, /(?:writeFile|mkdir|rename|proposals\/|publish|Materialization|Tutor|Reviewer|loadDocumentState)/);
});
