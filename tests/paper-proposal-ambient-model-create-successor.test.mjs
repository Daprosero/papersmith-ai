// CREATE_SUCCESSOR + resolvedDecisions coverage (design `sdd/paper-proposal-ambient-model`,
// SLICE 1: ADD the ambient-supplied path; the existing model-backed CREATE_SUCCESSOR
// path is untouched and stays covered by tests/paper-proposal-successor-multi-section.test.mjs).
//
// Exercises orchestrator.ts's real CREATE_SUCCESSOR pipeline (in-memory
// `PaperProposalOrchestrator` over a real temp-dir workspace) with `resolvedDecisions`
// instead of a `semanticPlanner`: NO model/planner is passed to the orchestrator at
// all, proving the ambient-supplied-planner is what resolves the edit, with zero
// model/network call. No proposal `.md` file is ever created in the repository --
// every fixture uses an mkdtemp() temp project root only.
//
// A real ambient caller learns a locus's resolved composite entryId via the
// engine's own existing read-only resolution (`resolveSuccessorTarget` +
// `ambiguityGate`, the SAME primitives orchestrator.ts itself calls) before
// supplying `resolvedDecisions` -- so this file resolves the entryId the exact
// same way, instead of guessing or reimplementing the composite-id format.
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
const workspaceModule = await jiti.import(path.resolve('.claude/skills/paper-proposal/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('.claude/skills/paper-proposal/engine/exports.ts'));

async function seed(content) {
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-ambient-successor-'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(root).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content });
	const guard = workspaceModule.createDocumentOperationGuard(root);
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'ambient-successor');
	return { root, adapter };
}

/** NO `semanticPlanner` argument at all: the orchestrator must resolve entirely through `resolvedDecisions`, proving no model/network call is required on this path. */
function orchestratorWithoutPlanner(root, adapter) {
	return new v2.PaperProposalOrchestrator(root, adapter);
}

/** Resolves a locus query into its engine-resolved composite entryId, using the exact same read-only primitives orchestrator.ts itself calls for CREATE_SUCCESSOR (never a reimplementation of the composite-id format). */
async function resolveLocusEntryId(root, filename, query) {
	const state = await v2.loadDocumentState(root, filename);
	const resolution = v2.resolveSuccessorTarget(state, query);
	assert.ok(resolution.candidates.length, `must resolve a candidate for query: ${query}`);
	const gate = v2.ambiguityGate(resolution.candidates);
	assert.ok(gate.candidate, `resolution must not be ambiguous for query: ${query}`);
	return gate.candidate.entryId;
}

test('CREATE_SUCCESSOR + resolvedDecisions: single-section change applies byte-preservingly and publishes, with NO semanticPlanner/model wired at all', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const replacement = '# 2 Alpha Revised\n\nNew alpha body.\n\n';

	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Modifica la sección Alpha.',
		selectedEntryId: 'sección Alpha',
		resolvedDecisions: [{ kind: 'replace', targetEntryId: alphaEntryId, replacementText: replacement }],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(preview.modelCalls, 1, 'buildEditPlan generically counts one planner invocation regardless of whether it was ambient or model-backed');
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	assert.ok(body.includes('New alpha body.'));
	assert.ok(body.includes('Keep prefix exactly.'), 'untouched prefix preserved byte-for-byte');
	assert.ok(body.includes('Keep suffix exactly.'), 'untouched suffix preserved byte-for-byte');
	assert.equal(body.includes('Old alpha body.'), false);
});

test('CREATE_SUCCESSOR + resolvedDecisions: multi-section batch (TWO independent decisions) splices into ONE successor, byte-preserving, and exposes a non-blocking growthAdvisory', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Middle\n\nKeep middle exactly.\n\n# 4 Beta\n\nOld beta body.\n\n# 5 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const alphaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Alpha');
	const betaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Beta');
	const alphaReplacement = '# 2 Alpha Revised\n\nNew alpha body.\n\n';
	const betaReplacement = '# 4 Beta Revised\n\nNew beta body.\n\n';

	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Modifica Alpha y Beta.',
		selectedEntryIds: ['sección Alpha', 'sección Beta'],
		resolvedDecisions: [
			{ kind: 'replace', targetEntryId: alphaEntryId, replacementText: alphaReplacement },
			{ kind: 'replace', targetEntryId: betaEntryId, replacementText: betaReplacement },
		],
	};
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(preview.patchCount, 2);
	assert.ok(preview.growthAdvisory, 'growth advisory must be exposed on the resolvedDecisions path');
	assert.equal(typeof preview.growthAdvisory.warn, 'boolean');
	assert.equal(preview.growthAdvisory.warn, false, 'two small sections stay well under the advisory threshold');

	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	const expected = '# 1 Intro\n\nKeep prefix exactly.\n\n' + alphaReplacement + '# 3 Middle\n\nKeep middle exactly.\n\n' + betaReplacement + '# 5 Tail\n\nKeep suffix exactly.\n';
	assert.equal(body.replace(/^<!-- proposal-workspace:artifact:v1 -->\n/, ''), expected, 'both independent sections revised in place, every untouched byte preserved');
});

test('CREATE_SUCCESSOR + resolvedDecisions: the current-turn successor-acceptance consent gate is still required -- a resolvedDecisions call cannot publish without a valid acceptanceToken', async () => {
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
	const withoutToken = await orchestrator.execute({ ...request, acceptSuccessor: true });
	assert.equal(withoutToken.status, 'blocked');
	assert.equal(withoutToken.reason, 'SUCCESSOR_ACCEPTANCE_REQUIRED');
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published without the acceptance token');
});

test('CREATE_SUCCESSOR + resolvedDecisions: a decision naming an entry outside the resolved target is rejected, never silently applied to the wrong section', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n# 2 Beta\n\nOld beta.\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const betaEntryId = await resolveLocusEntryId(root, 'research-concept-r01.md', 'sección Beta');
	const request = {
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Modifica Alpha.',
		selectedEntryId: 'sección Alpha',
		// Decision names Beta's entryId even though the resolved locus this turn is Alpha.
		resolvedDecisions: [{ kind: 'replace', targetEntryId: betaEntryId, replacementText: 'Hijacked replacement.' }],
	};
	const result = await orchestrator.execute(request);
	assert.equal(result.status, 'blocked');
	// The ambient-supplied-planner rejects this with WRONG_TARGET_ENTRY_ID at its own
	// boundary (see tests/paper-proposal-ambient-supplied-planner.test.mjs), which
	// edit-planner.ts's pre-existing `plannerInvocationDiagnostic` fail-closed path
	// converts into an empty-actions plan; orchestrator.ts's OWN pre-existing
	// successor action-count/kind check (STAY, unmodified by this slice) then blocks
	// BEFORE publish() ever observes the plannerDiagnostic -- the exact same
	// downstream reason a rejected MODEL response would have produced on this path.
	assert.equal(result.reason, 'SUCCESSOR_OUTSIDE_TARGET_FORBIDDEN');
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published when the decision names the wrong target');
});

test('CREATE_SUCCESSOR + resolvedDecisions: the existing model-backed path is untouched -- a request WITHOUT resolvedDecisions still requires a semanticPlanner', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n';
	const { root, adapter } = await seed(source);
	const orchestrator = orchestratorWithoutPlanner(root, adapter);
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica Alpha.', selectedEntryId: 'sección Alpha' };
	const result = await orchestrator.execute(request);
	assert.equal(result.status, 'blocked');
	assert.equal(result.reason, 'SEMANTIC_EDIT_PLANNER_REQUIRED');
});
