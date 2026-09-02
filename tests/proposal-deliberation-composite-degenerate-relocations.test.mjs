import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
// Degenerate and drifted relocations on the LIVE composite path.
//
// These promises were previously exercised only through the durable scientific
// workflow, which drove the same `successor-edit-planner.ts` / `orchestrator.ts`
// machinery from a second entry point. That subsystem is gone; the machinery is
// not. Each test below pins one refusal that would otherwise be unguarded:
// a relocation must never be applied at a forced offset, and a degenerate
// relocation must never be silently accepted as a no-op.
//
// Driver: CREATE_SUCCESSOR + resolvedDecisions, the same keyless composite path
// tests/proposal-deliberation-ambient-model-composite-successor.test.mjs uses.
// No model or network call. Every fixture lives in an mkdtemp() project root.
import assert from 'node:assert/strict';
import { mkdir, mkdtemp } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = ENGINE_MODULE_ROOT;
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspaceModule = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/exports.ts'));

const SOURCE = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n## 2.1 Alpha Child\n\nNested body.\n\n# 3 Tail\n\nKeep suffix exactly.\n';

async function seed(content) {
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-degenerate-'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(root).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content });
	const guard = workspaceModule.createDocumentOperationGuard(root);
	let counter = 0;
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => `degenerate-${++counter}`);
	return { root, adapter, orchestrator: new v2.ProposalDeliberationOrchestrator(root, adapter) };
}

async function resolveLocusEntryId(root, filename, query) {
	const state = await v2.loadDocumentState(root, filename);
	const resolution = v2.resolveSuccessorTarget(state, query);
	assert.ok(resolution.candidates.length, `must resolve a candidate for query: ${query}`);
	const gate = v2.ambiguityGate(resolution.candidates);
	assert.ok(gate.candidate, `resolution must not be ambiguous for query: ${query}`);
	return gate.candidate.entryId;
}

function request(resolvedDecisions, instruction) {
	return {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction,
		selectedEntryId: 'sección Alpha',
		resolvedDecisions,
	};
}

/** A refusal is anything that is not a publishable preview: the successor must never reach acceptance. */
function assertRefused(result, label) {
	assert.notEqual(result.status, 'published', `${label}: must never publish`);
	assert.notEqual(result.status, 'awaiting_acceptance', `${label}: must never reach acceptance, got ${JSON.stringify(result)}`);
}

test('composite MOVE whose source is its own destination is refused, never accepted as a forced no-op', async () => {
	const { root, orchestrator } = await seed(SOURCE);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const result = await orchestrator.execute(request(
		[{ kind: 'move', sourceEntryId: alphaEntryId, destinationEntryId: alphaEntryId, position: 'after', removeSource: true }],
		'Mueve Alpha después de Alpha.',
	));
	assertRefused(result, 'source === destination');
});

// NOT PORTED: "destination nested inside its own source" (HIERARCHY_CYCLE).
// The removed subsystem addressed a section and its subsection as distinct
// entries, so a move could name a destination inside its own source. On the
// composite path a section and its whole subtree resolve to ONE entry -- both
// 'sección Alpha' and 'Alpha Child' resolve to the same composite entryId --
// so the cycle is not expressible here rather than merely unguarded. A test
// asserting a refusal would pass for the wrong reason: it would be indistinct
// from the drifted-source case below.

test('composite MOVE naming a source that does not exist in the resolved document is refused, never applied at a forced offset', async () => {
	const { root, orchestrator } = await seed(SOURCE);
	const tailEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Tail');
	const result = await orchestrator.execute(request(
		[{ kind: 'move', sourceEntryId: 'entry-that-drifted-away', destinationEntryId: tailEntryId, position: 'after', removeSource: true }],
		'Mueve una sección que ya no está donde se creía.',
	));
	assertRefused(result, 'drifted source');
});

test('composite INSERT anchored to an entry that does not exist is refused, never appended at a forced offset', async () => {
	const { root, orchestrator } = await seed(SOURCE);
	const result = await orchestrator.execute(request(
		[{ kind: 'insert', anchorEntryId: 'anchor-that-drifted-away', position: 'after', content: '## Extra\n\nInserted.\n\n' }],
		'Agrega una nota tras una sección que ya no está.',
	));
	assertRefused(result, 'drifted insert anchor');
});

test('composite DELETE targeting an entry that does not exist is refused, never applied to a neighbouring span', async () => {
	const { root, orchestrator } = await seed(SOURCE);
	const result = await orchestrator.execute(request(
		[{ kind: 'delete', targetEntryId: 'target-that-drifted-away' }],
		'Elimina una sección que ya no está.',
	));
	assertRefused(result, 'drifted delete target');
});
