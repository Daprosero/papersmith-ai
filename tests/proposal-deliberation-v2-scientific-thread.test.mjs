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
const v2 = await jiti.import(path.join(root, '.claude/skills/proposal-deliberation/engine/exports.ts'));

const entry = { state: 'SCIENTIFIC_ONLY', relatedThreadIds: [], pendingCandidateIds: [], recovery: { required: false }, auditEvidence: [] };
const act = (kind, extras = {}) => ({ status: 'resolved', act: kind, relatedThreadIds: [], ...extras });
const thread = (threadId, status = 'OPEN', extras = {}) => ({
	threadId, version: 1, status, title: `Thread ${threadId}`, summary: 'Bounded summary.',
	createdEventId: `${threadId}-created`, headEventId: `${threadId}-head`, relationIds: [], decisionIds: [], ...extras,
});

function resolver(snapshot, commits = [], failure) {
	let sequence = 0;
	return new v2.ScientificThreadResolver(
		{ read: async () => snapshot },
		{ commit: async (intents) => { if (failure) throw new Error('interrupted'); commits.push(intents); } },
		() => `id-${++sequence}`,
	);
}

test('ScientificThreadResolver creates one bounded user-originated idea thread without document behavior', async () => {
	const commits = [];
	const result = await resolver({ threads: [], relations: [] }, commits).resolve({ entry: { ...entry, state: 'EMPTY_PROJECT' }, act: act('CONSTRUCT_IDEA'), ideaSeed: { title: 'Question', summary: 'Bounded seed.', actor: { kind: 'USER' } } });
	assert.equal(result.status, 'created');
	assert.equal(result.activeThread.threadId, 'id-1');
	assert.deepEqual(commits, [[{ type: 'THREAD_CREATED', eventId: 'id-2', threadId: 'id-1', activeThreadId: 'id-1', causalEventIds: [], relatedThreadIds: [], seed: { title: 'Question', summary: 'Bounded seed.', actor: { kind: 'USER' } } }]]);
});

test('ScientificThreadResolver continues one validated active thread without emitting a selection intent', async () => {
	const active = thread('thread-1');
	const commits = [];
	const result = await resolver({ activeThreadId: active.threadId, threads: [active], relations: [] }, commits).resolve({ entry, act: act('CONSTRUCT_QUESTION') });
	assert.deepEqual(result, { status: 'continued', activeThread: active, intents: [] });
	assert.deepEqual(commits, []);
});

test('ScientificThreadResolver selects an eligible thread and records only allowed transition intents', async () => {
	const active = thread('thread-1', 'OPEN', { relationIds: ['relation-1'] });
	const related = thread('thread-2', 'OPEN', { relationIds: ['relation-1'] });
	const relation = { relationId: 'relation-1', kind: 'RELATED', fromThreadId: active.threadId, toThreadId: related.threadId, createdEventId: 'relation-created' };
	const commits = [];
	const result = await resolver({ threads: [active, related], relations: [relation] }, commits).resolve({ entry, act: act('CONSTRUCT_QUESTION'), requestedActiveThreadId: active.threadId, relatedThreadIds: [related.threadId] });
	assert.equal(result.status, 'selected');
	assert.deepEqual(result.intents.map((intent) => intent.type), ['THREAD_SELECTED', 'THREAD_ACTIVATED', 'THREAD_RELATED']);
	assert.deepEqual(result.intents[1].causalEventIds, [result.intents[0].eventId]);
	assert.deepEqual(result.intents[2].relatedThreadIds, [related.threadId]);
	assert.deepEqual(commits, [result.intents]);
});

test('ScientificThreadResolver clarifies absent or ambiguous ownership and blocks invalid selections without write intents', async () => {
	const one = thread('thread-1');
	const two = thread('thread-2');
	const ambiguousCommits = [];
	const ambiguous = await resolver({ threads: [one, two], relations: [] }, ambiguousCommits).resolve({ entry, act: act('CONSTRUCT_QUESTION') });
	assert.equal(ambiguous.status, 'needs_clarification');
	assert.equal(ambiguous.code, 'THREAD_SELECTION_AMBIGUOUS');
	assert.deepEqual(ambiguousCommits, []);

	const blockedCommits = [];
	const blocked = await resolver({ threads: [thread('blocked', 'BLOCKED')], relations: [] }, blockedCommits).resolve({ entry, act: act('CONSTRUCT_QUESTION'), requestedActiveThreadId: 'blocked' });
	assert.equal(blocked.status, 'blocked');
	assert.equal(blocked.code, 'THREAD_NOT_ELIGIBLE');
	assert.deepEqual(blockedCommits, []);
});

test('ScientificThreadResolver rejects stale threads and non-direct related-thread selection without write intents', async () => {
	const revision = { filename: 'research-concept-r01.md', revision: 'r01', documentSha256: 'a'.repeat(64) };
	const stale = thread('stale', 'OPEN', { revisionEvidence: revision });
	const staleCommits = [];
	const staleResult = await resolver({ threads: [stale], relations: [] }, staleCommits).resolve({ entry, act: act('CONSTRUCT_QUESTION'), requestedActiveThreadId: stale.threadId });
	assert.equal(staleResult.code, 'THREAD_EVIDENCE_STALE');
	assert.deepEqual(staleCommits, []);

	const one = thread('thread-1');
	const two = thread('thread-2');
	const relationCommits = [];
	const relationResult = await resolver({ threads: [one, two], relations: [] }, relationCommits).resolve({ entry, act: act('CONSTRUCT_QUESTION'), requestedActiveThreadId: one.threadId, relatedThreadIds: [two.threadId] });
	assert.equal(relationResult.code, 'THREAD_RELATION_NOT_DIRECT');
	assert.deepEqual(relationCommits, []);
});

test('ScientificThreadResolver reports interrupted transition without a document or role path', async () => {
	const commits = [];
	const result = await resolver({ threads: [], relations: [] }, commits, true).resolve({ entry: { ...entry, state: 'EMPTY_PROJECT' }, act: act('CONSTRUCT_IDEA'), ideaSeed: { title: 'Question', summary: 'Bounded seed.', actor: { kind: 'USER' } } });
	assert.equal(result.status, 'blocked');
	assert.equal(result.code, 'THREAD_TRANSITION_INCOMPLETE');
	assert.deepEqual(commits, []);
});

test('ScientificThreadResolver uses canonical contracts and exposes an in-memory-only transition boundary', async () => {
	const source = await readFile(path.join(root, '.claude/skills/proposal-deliberation/engine/scientific-thread-resolver.ts'), 'utf8');
	assert.match(source, /scientific-domain\.js/);
	assert.match(source, /ReadOnlyScientificThreadStatePort/);
	assert.match(source, /ThreadTransitionIntentPort/);
	assert.doesNotMatch(source, /(?:writeFile|mkdir|rename|proposals\/|publish|receipt|Tutor|Reviewer)/);
});
