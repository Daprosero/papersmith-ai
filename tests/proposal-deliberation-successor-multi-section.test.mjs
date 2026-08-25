// Multi-section CREATE_SUCCESSOR coverage (proposal-deliberation-tutor-repair, design
// amendment: multi-section successor + growth advisory).
//
// Extends tests/proposal-deliberation-successor-locus-inference.test.mjs (tasks 1.3/1.4,
// ONE heading span per successor) to lift that over-conservative limit: when
// `request.selectedEntryIds` names SEVERAL independent, disjoint locus queries in
// one turn, ALL of them must be spliced into the SAME successor via the
// byte-preserving composite engine (`composeSuccessorBlockCandidate`, which
// already supports disjoint multi-block composition). Exercises
// orchestrator.ts's interactive CREATE_SUCCESSOR pipeline directly (in-memory
// `ProposalDeliberationOrchestrator` over a real temp-dir workspace; no proposal .md is
// authored anywhere in the repository -- only ephemeral tmpdir fixtures).
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
const workspaceModule = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/exports.ts'));

async function seed(content) {
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-successor-multi-'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(root).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content });
	const guard = workspaceModule.createDocumentOperationGuard(root);
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'successor-multi');
	return { root, adapter };
}

// A per-target replacement planner: returns whichever replacement text was
// registered for the exact `entryId` the orchestrator resolved for that turn's
// planner call (one call per resolved target, matching the single-target
// contract exactly -- just invoked once per independent locus).
function plannerFor(byEntryText) {
	return { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: byEntryText(input.context.fragments[0].text) }], unresolvedQuestions: [] }) };
}

test('CREATE_SUCCESSOR splices TWO independent, disjoint sections into ONE successor, preserving every untouched byte', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Middle\n\nKeep middle exactly.\n\n# 4 Beta\n\nOld beta body.\n\n# 5 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	const alphaReplacement = '# 2 Alpha Revised\n\nNew alpha body.\n\n';
	const betaReplacement = '# 4 Beta Revised\n\nNew beta body.\n\n';
	const planner = plannerFor(text => (text.includes('Alpha') ? alphaReplacement : betaReplacement));
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica las secciones Alpha y Beta.', selectedEntryIds: ['sección Alpha', 'sección Beta'] };
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(preview.patchCount, 2, 'exactly one patch per independent resolved section');
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = (await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8')).replace(/^<!-- proposal-workspace:artifact:v1 -->\n/, '');
	const expected = '# 1 Intro\n\nKeep prefix exactly.\n\n' + alphaReplacement + '# 3 Middle\n\nKeep middle exactly.\n\n' + betaReplacement + '# 5 Tail\n\nKeep suffix exactly.\n';
	assert.equal(body, expected, 'both independent sections are revised in place and every untouched byte (including the middle section and blank-line counts) is byte-identical');
});

test('CREATE_SUCCESSOR splices THREE independent sections into one successor (not limited to one heading span)', async () => {
	const source = '# 1 One\n\nBody one.\n\n# 2 Two\n\nBody two.\n\n# 3 Three\n\nBody three.\n\n# 4 Four\n\nBody four.\n';
	const { root, adapter } = await seed(source);
	const replacements = { One: '# 1 One Revised\n\nNew one.\n\n', Two: '# 2 Two Revised\n\nNew two.\n\n', Three: '# 3 Three Revised\n\nNew three.\n\n' };
	const planner = plannerFor(text => Object.entries(replacements).find(([name]) => text.includes(name))[1]);
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica One, Two y Three.', selectedEntryIds: ['sección One', 'sección Two', 'sección Three'] };
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(preview.patchCount, 3);
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	assert.ok(body.includes('New one.'));
	assert.ok(body.includes('New two.'));
	assert.ok(body.includes('New three.'));
	assert.ok(body.includes('Body four.'), 'the untouched fourth section survives byte-for-byte');
});

test('CREATE_SUCCESSOR still requires the bound current-turn acceptance token before publishing a multi-section successor', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n# 2 Beta\n\nOld beta.\n';
	const { root, adapter } = await seed(source);
	const planner = plannerFor(text => (text.includes('Alpha') ? '# 1 Alpha Revised\n\nNew alpha.\n\n' : '# 2 Beta Revised\n\nNew beta.\n\n'));
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica Alpha y Beta.', selectedEntryIds: ['sección Alpha', 'sección Beta'] };
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	const withoutToken = await orchestrator.execute({ ...request, acceptSuccessor: true });
	assert.equal(withoutToken.status, 'blocked');
	assert.equal(withoutToken.reason, 'SUCCESSOR_ACCEPTANCE_REQUIRED');
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published without the acceptance token');
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
});

test('CREATE_SUCCESSOR rejects duplicate targets naming the same section twice', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n# 2 Beta\n\nOld beta.\n';
	const { root, adapter } = await seed(source);
	const planner = plannerFor(() => '# 1 Alpha Revised\n\nNew alpha.\n\n');
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica Alpha dos veces.', selectedEntryIds: ['sección Alpha', 'sección Alpha'] };
	const result = await orchestrator.execute(request);
	assert.equal(result.status, 'blocked');
	assert.equal(result.reason, 'SUCCESSOR_DUPLICATE_TARGET');
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published when targets are duplicated');
});

test('published successor receipt instructionHash reflects the full multi-target set, not only the last resolved target (re-audit cleanup)', async () => {
	const source = '# 1 Alpha\n\nOld alpha.\n\n# 2 Beta\n\nOld beta.\n\n# 3 Gamma\n\nOld gamma.\n';
	const replacements = { Alpha: '# 1 Alpha Revised\n\nNew alpha.\n\n', Beta: '# 2 Beta Revised\n\nNew beta.\n\n', Gamma: '# 3 Gamma Revised\n\nNew gamma.\n\n' };
	const planner = plannerFor(text => Object.entries(replacements).find(([name]) => text.includes(name))[1]);

	const { root: rootAB, adapter: adapterAB } = await seed(source);
	const orchestratorAB = new v2.ProposalDeliberationOrchestrator(rootAB, adapterAB, undefined, planner);
	// SAME shared instruction text used for both runs below -- the request-level
	// instruction alone never varies per target (there is only ever one
	// `intent.evidence[0]` per multi-target call), so a correct combined hash
	// must additionally depend on which targets were actually resolved.
	const requestAB = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica las secciones seleccionadas.', selectedEntryIds: ['sección Alpha', 'sección Beta'] };
	const previewAB = await orchestratorAB.execute(requestAB);
	assert.equal(previewAB.status, 'awaiting_acceptance', JSON.stringify(previewAB));
	const publishedAB = await orchestratorAB.execute({ ...requestAB, acceptSuccessor: true, successorAcceptanceToken: previewAB.acceptanceToken });
	assert.equal(publishedAB.status, 'published', JSON.stringify(publishedAB));

	const { root: rootAG, adapter: adapterAG } = await seed(source);
	const orchestratorAG = new v2.ProposalDeliberationOrchestrator(rootAG, adapterAG, undefined, planner);
	// Only the SECOND target differs (Beta -> Gamma); the shared instruction text is identical.
	const requestAG = { ...requestAB, selectedEntryIds: ['sección Alpha', 'sección Gamma'] };
	const previewAG = await orchestratorAG.execute(requestAG);
	assert.equal(previewAG.status, 'awaiting_acceptance', JSON.stringify(previewAG));
	const publishedAG = await orchestratorAG.execute({ ...requestAG, acceptSuccessor: true, successorAcceptanceToken: previewAG.acceptanceToken });
	assert.equal(publishedAG.status, 'published', JSON.stringify(publishedAG));

	assert.notEqual(
		publishedAB.receipt.instructionHash,
		publishedAG.receipt.instructionHash,
		'the combined instructionHash must reflect every resolved target, not only the last one built in the per-target loop -- ' +
		'with the old "inherit from the last target only" behavior both receipts would be identical here, since the shared instruction text never changes',
	);
});

test('combineSuccessorInstructionHashes (re-audit cleanup): pure function is deterministic and sensitive to any single target or instruction hash changing', () => {
	const a = v2.combineSuccessorInstructionHashes([{ entryId: 'alpha', instructionHash: 'hash-a' }, { entryId: 'beta', instructionHash: 'hash-b' }]);
	const sameInputs = v2.combineSuccessorInstructionHashes([{ entryId: 'alpha', instructionHash: 'hash-a' }, { entryId: 'beta', instructionHash: 'hash-b' }]);
	assert.equal(a, sameInputs, 'deterministic for identical ordered inputs');

	const differentSecondTarget = v2.combineSuccessorInstructionHashes([{ entryId: 'alpha', instructionHash: 'hash-a' }, { entryId: 'gamma', instructionHash: 'hash-b' }]);
	assert.notEqual(a, differentSecondTarget, 'changing one target entryId changes the combined hash');

	const differentSecondInstructionHash = v2.combineSuccessorInstructionHashes([{ entryId: 'alpha', instructionHash: 'hash-a' }, { entryId: 'beta', instructionHash: 'hash-c' }]);
	assert.notEqual(a, differentSecondInstructionHash, 'changing one target\'s own instructionHash changes the combined hash');

	const reordered = v2.combineSuccessorInstructionHashes([{ entryId: 'beta', instructionHash: 'hash-b' }, { entryId: 'alpha', instructionHash: 'hash-a' }]);
	assert.notEqual(a, reordered, 'target order is part of the combined provenance');
});

test('CREATE_SUCCESSOR rejects overlapping targets (a parent heading and its own child subsection)', async () => {
	const source = '# 1 Parent\n\nIntro paragraph.\n\n## 1.1 Child\n\nChild body.\n\n# 2 Tail\n\nKeep suffix.\n';
	const { root, adapter } = await seed(source);
	const planner = plannerFor(() => '# 1 Parent Revised\n\nNew body.\n\n');
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	// "Parent" resolves to the whole `# 1 Parent` section (spanning its child
	// `## 1.1 Child` subsection); "Child" resolves to a span nested entirely
	// inside it -- the two byte ranges overlap.
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica Parent y Child.', selectedEntryIds: ['sección Parent', 'sección Child'] };
	const result = await orchestrator.execute(request);
	assert.equal(result.status, 'blocked');
	assert.equal(result.reason, 'SUCCESSOR_TARGET_OVERLAP');
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published when targets overlap');
});
