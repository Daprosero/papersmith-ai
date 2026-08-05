// CREATE_SUCCESSOR + resolvedDecisions coverage for the FULL operation set
// (design `sdd/proposal-deliberation-ambient-model`, SLICE 1b): extends SLICE 1's
// replace-only ambient-supplied path (tests/proposal-deliberation-ambient-model-create-successor.test.mjs)
// to insert/delete/move/copy, reusing the SAME byte-preserving composite
// machinery `scientific-workflow-runtime.ts`'s deliberated-operations
// reduction already uses (`composeSuccessorBlockCandidate`), via
// `ambient-supplied-planner.ts`'s `resolveAmbientCompositeDecisions` and
// `patch-compiler.ts`'s `compileSuccessorCompositeChangeset`. NO model/network
// call is required on this path. No proposal `.md` file is ever committed to
// the repository -- every fixture uses an mkdtemp() temp project root only.
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspaceModule = await jiti.import(path.resolve('.claude/skills/proposal-deliberation/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('.claude/skills/proposal-deliberation/engine/exports.ts'));

async function seed(content) {
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-ambient-composite-'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(root).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content });
	const guard = workspaceModule.createDocumentOperationGuard(root);
	// A fixed, single-reuse operationId works for the other tests in this file
	// (one publish per orchestrator instance) but the MIXED-batch test performs
	// TWO sequential publishes against the SAME orchestrator/adapter -- the
	// guard's per-operation lifecycle rejects a second `begin_document_operation`
	// on an already-finalized id, so this factory must produce a FRESH id per call.
	let counter = 0;
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => `ambient-composite-${++counter}`);
	return { root, adapter };
}

/** NO `semanticPlanner` argument at all: the orchestrator must resolve entirely through `resolvedDecisions`, proving no model/network call is required on this path. */
function orchestratorWithoutPlanner(root, adapter) {
	return new v2.ProposalDeliberationOrchestrator(root, adapter);
}

/** Resolves a locus query into its engine-resolved composite entryId, using the exact same read-only primitives orchestrator.ts itself calls for CREATE_SUCCESSOR. */
async function resolveLocusEntryId(root, filename, query) {
	const state = await v2.loadDocumentState(root, filename);
	const resolution = v2.resolveSuccessorTarget(state, query);
	assert.ok(resolution.candidates.length, `must resolve a candidate for query: ${query}`);
	const gate = v2.ambiguityGate(resolution.candidates);
	assert.ok(gate.candidate, `resolution must not be ambiguous for query: ${query}`);
	return gate.candidate.entryId;
}

test('CREATE_SUCCESSOR + resolvedDecisions: a keyless INSERT decision applies byte-preservingly and publishes', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const content = '## Extra Note\n\nInserted content.\n\n';

	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Agrega una nota tras Alpha.',
		selectedEntryId: 'sección Alpha',
		resolvedDecisions: [{ kind: 'insert', anchorEntryId: alphaEntryId, position: 'after', content }],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	assert.ok(body.includes('Inserted content.'));
	assert.ok(body.includes('Old alpha body.'), 'untouched section body preserved byte-for-byte');
	assert.ok(body.includes('Keep suffix exactly.'), 'untouched suffix preserved byte-for-byte');
	const alphaIndex = body.indexOf('Old alpha body.');
	const insertedIndex = body.indexOf('Inserted content.');
	const tailIndex = body.indexOf('Keep suffix exactly.');
	assert.ok(alphaIndex < insertedIndex && insertedIndex < tailIndex, 'inserted content lands between Alpha and Tail');
});

test('CREATE_SUCCESSOR + resolvedDecisions: a keyless DELETE decision removes a whole section byte-preservingly', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');

	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Elimina la sección Alpha.',
		selectedEntryId: 'sección Alpha',
		resolvedDecisions: [{ kind: 'delete', targetEntryId: alphaEntryId, instructionEvidence: 'Elimina la sección Alpha.', reason: 'obsolete' }],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	assert.equal(body.includes('Old alpha body.'), false, 'the deleted section is gone');
	assert.equal(body.includes('# 2 Alpha'), false, 'the deleted heading is gone');
	assert.ok(body.includes('Keep prefix exactly.'), 'untouched prefix preserved byte-for-byte');
	assert.ok(body.includes('Keep suffix exactly.'), 'untouched suffix preserved byte-for-byte');
});

test('CREATE_SUCCESSOR + resolvedDecisions: a keyless MOVE decision relocates one whole section byte-preservingly (LITERAL)', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Middle\n\nKeep middle exactly.\n\n# 4 Beta\n\nOld beta body.\n\n# 5 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const betaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Beta');

	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Mueve Alpha después de Beta.',
		selectedEntryIds: ['sección Alpha', 'sección Beta'],
		resolvedDecisions: [{ kind: 'move', sourceEntryIds: [alphaEntryId], destinationAnchorId: betaEntryId, position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	const expected = '# 1 Intro\n\nKeep prefix exactly.\n\n# 3 Middle\n\nKeep middle exactly.\n\n# 4 Beta\n\nOld beta body.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 5 Tail\n\nKeep suffix exactly.\n';
	assert.equal(body.replace(/^<!-- proposal-workspace:artifact:v1 -->\n/, ''), expected, 'Alpha relocated after Beta, every untouched byte preserved');
});

test('CREATE_SUCCESSOR + resolvedDecisions: a keyless COPY decision duplicates a section without touching the source', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Beta\n\nOld beta body.\n\n# 4 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const betaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Beta');

	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Copia Alpha después de Beta.',
		selectedEntryIds: ['sección Alpha', 'sección Beta'],
		resolvedDecisions: [{ kind: 'copy', sourceEntryIds: [alphaEntryId], destinationAnchorId: betaEntryId, position: 'after', moveMode: 'LITERAL', removeSource: false, cleanupLevel: 'NONE' }],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	const expected = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Beta\n\nOld beta body.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 4 Tail\n\nKeep suffix exactly.\n';
	assert.equal(body.replace(/^<!-- proposal-workspace:artifact:v1 -->\n/, ''), expected, 'Alpha duplicated after Beta, source untouched');
});

test('CREATE_SUCCESSOR + resolvedDecisions: a MIXED batch (one in-place replace + one relocation move) produces TWO SEPARATE successor versions', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Middle\n\nKeep middle exactly.\n\n# 4 Beta\n\nOld beta body.\n\n# 5 Delta\n\nKeep delta exactly.\n\n# 6 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const betaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Beta');
	const deltaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Delta');
	const alphaReplacement = '# 2 Alpha Revised\n\nNew alpha body.\n\n';

	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Revisa Alpha y mueve Beta después de Delta.',
		selectedEntryIds: ['sección Alpha', 'sección Beta', 'sección Delta'],
		resolvedDecisions: [
			{ kind: 'replace', targetEntryId: alphaEntryId, replacementText: alphaReplacement },
			{ kind: 'move', sourceEntryIds: [betaEntryId], destinationAnchorId: deltaEntryId, position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' },
		],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));

	const result = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(result.status, 'published', JSON.stringify(result));
	assert.equal(result.versions.length, 2, 'a mixed batch produces two grouped, sequential successor versions');
	assert.equal(result.versions[0].published.targetRevision, 'r02');
	assert.equal(result.versions[1].published.targetRevision, 'r03');

	const inPlaceOnly = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	assert.ok(inPlaceOnly.includes('New alpha body.'), 'r02 carries only the in-place replace');
	assert.ok(inPlaceOnly.includes('# 4 Beta'), 'r02 has NOT yet relocated Beta');

	const final = await readFile(path.join(root, 'proposals/research-concept-r03.md'), 'utf8');
	const expected = '# 1 Intro\n\nKeep prefix exactly.\n\n' + alphaReplacement + '# 3 Middle\n\nKeep middle exactly.\n\n# 5 Delta\n\nKeep delta exactly.\n\n# 4 Beta\n\nOld beta body.\n\n# 6 Tail\n\nKeep suffix exactly.\n';
	assert.equal(final.replace(/^<!-- proposal-workspace:artifact:v1 -->\n/, ''), expected, 'r03 carries both the in-place replace (inherited from r02) and the relocation, byte-preserving');
	assert.deepEqual((await readdir(path.join(root, 'proposals'))).sort(), ['research-concept-r01.md', 'research-concept-r02.md', 'research-concept-r03.md']);
});

test('CREATE_SUCCESSOR + resolvedDecisions: the current-turn successor-acceptance consent gate is still required for a non-replace kind', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n# 2 Beta\n\nOld beta.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Elimina Alpha.',
		selectedEntryId: 'sección Alpha',
		resolvedDecisions: [{ kind: 'delete', targetEntryId: alphaEntryId, instructionEvidence: 'Elimina Alpha.', reason: 'obsolete' }],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	const withoutToken = await orchestrator.execute({ ...request, acceptSuccessor: true });
	assert.equal(withoutToken.status, 'blocked');
	assert.equal(withoutToken.reason, 'SUCCESSOR_ACCEPTANCE_REQUIRED');
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published without the acceptance token');
});

test('CREATE_SUCCESSOR + resolvedDecisions: an INSERT decision naming an entry outside the resolved target is rejected, never silently applied', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n# 2 Beta\n\nOld beta.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const betaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Beta');
	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Agrega una nota a Alpha.',
		selectedEntryId: 'sección Alpha',
		// Decision names Beta's entryId even though the resolved locus this turn is Alpha.
		resolvedDecisions: [{ kind: 'insert', anchorEntryId: betaEntryId, position: 'after', content: 'Hijacked content.\n\n' }],
	};
	const result = await orchestrator.execute(request);
	assert.equal(result.status, 'blocked');
	assert.ok(String(result.reason).includes('WRONG_TARGET_ENTRY_ID'), JSON.stringify(result));
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published when the decision names the wrong target');
});

test('CREATE_SUCCESSOR + resolvedDecisions: an ADAPTIVE move without transformedContent is blocked, never fabricated', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n# 2 Beta\n\nOld beta.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const betaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Beta');
	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Mueve Alpha después de Beta, adaptado.',
		selectedEntryIds: ['sección Alpha', 'sección Beta'],
		resolvedDecisions: [{ kind: 'move', sourceEntryIds: [alphaEntryId], destinationAnchorId: betaEntryId, position: 'after', moveMode: 'ADAPTIVE', removeSource: true, cleanupLevel: 'NONE' }],
	};
	const result = await orchestrator.execute(request);
	assert.equal(result.status, 'blocked');
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published without adaptive content');
});

test('CREATE_SUCCESSOR + resolvedDecisions: the existing SLICE-1 replace-only path is untouched by a homogeneous replace batch', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Modifica Alpha.',
		selectedEntryId: 'sección Alpha',
		resolvedDecisions: [{ kind: 'replace', targetEntryId: alphaEntryId, replacementText: '# 1 Alpha Revised\n\nNew alpha.\n' }],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(preview.modelCalls, 1, 'the OLD buildEditPlan-based replace-only path is unchanged by SLICE 1b');
});
