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
const resolver = new v2.ScientificActResolver();

test('ScientificActResolver classifies every approved bounded act', () => {
	for (const [instruction, act] of [
		['construct an idea', 'CONSTRUCT_IDEA'], ['construct a question', 'CONSTRUCT_QUESTION'],
		['construct a hypothesis', 'CONSTRUCT_HYPOTHESIS'], ['construct an assumption', 'CONSTRUCT_ASSUMPTION'],
		['construct an alternative', 'CONSTRUCT_ALTERNATIVE'], ['raise an unresolved issue', 'RAISE_UNRESOLVED_ISSUE'],
		['relate these threads', 'RELATE_THREADS'], ['ask the tutor for help', 'REQUEST_TUTOR'],
		['request conceptual review', 'REQUEST_CONCEPTUAL_REVIEW'], ['synthesize this result', 'SYNTHESIZE'],
		['modify this synthesis', 'MODIFY_SYNTHESIS'], ['accept this decision', 'ACCEPT_DECISION'],
		['reject this decision', 'REJECT_DECISION'], ['retract this decision', 'RETRACT_DECISION'],
		['request materialization', 'REQUEST_MATERIALIZATION'], ['bootstrap from active proposal', 'BOOTSTRAP_FROM_ACTIVE_PROPOSAL'],
		['propose reconciliation', 'PROPOSE_RECONCILIATION'], ['accept reconciliation', 'ACCEPT_RECONCILIATION'],
	]) {
		const result = resolver.resolve({ instruction, requestedThreadId: 'thread-1', relatedThreadIds: ['thread-2'] });
		assert.deepEqual(result, { status: 'resolved', act, requestedThreadId: 'thread-1', relatedThreadIds: ['thread-2'] }, instruction);
	}
});

test('ScientificActResolver requires caller and instruction agreement and leaves ambiguous requests unresolved', () => {
	assert.equal(resolver.resolve({ instruction: 'construct an idea', scientificAct: 'CONSTRUCT_HYPOTHESIS' }).status, 'needs_clarification');
	assert.equal(resolver.resolve({ instruction: 'consider this carefully' }).status, 'needs_clarification');
	assert.equal(resolver.resolve({ instruction: 'construct a hypothesis and an alternative' }).status, 'needs_clarification');
});

test('ScientificActResolver preserves lifecycle, direct-document, and DELIBERATE precedence', () => {
	assert.deepEqual(resolver.resolve({ instruction: 'withdraw research-concept-r01.md' }), { status: 'blocked', code: 'LIFECYCLE_ROUTE_PRECEDENCE' });
	assert.deepEqual(resolver.resolve({ instruction: 'inserta un párrafo' }), { status: 'blocked', code: 'DIRECT_DOCUMENT_ROUTE_PRECEDENCE' });
	assert.deepEqual(resolver.resolve({ instruction: 'delibera sobre los supuestos' }), { status: 'blocked', code: 'DELIBERATE_ROUTE_PRECEDENCE' });
});

test('ScientificActResolver consumes the canonical domain and has no persistence or document behavior', async () => {
	const source = await readFile(path.join(root, '.claude/skills/paper-proposal/engine/scientific-act-resolver.ts'), 'utf8');
	assert.match(source, /scientific-domain\.js/);
	assert.doesNotMatch(source, /(?:writeFile|mkdir|rename|proposals\/|publish|receipt)/);
});
