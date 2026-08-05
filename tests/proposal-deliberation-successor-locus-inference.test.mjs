// CREATE_SUCCESSOR locus-inference + byte-preservation coverage (proposal-deliberation-tutor-repair, tasks 1.3/1.4).
//
// Exercises orchestrator.ts's interactive CREATE_SUCCESSOR pipeline directly
// (in-memory ProposalDeliberationOrchestrator over a real temp-dir workspace; no
// proposal .md is authored anywhere in the repository — only ephemeral
// tmpdir fixtures, same pattern as tests/proposal-deliberation-v2-source-routing.test.mjs).
//
// Asserts the corrected V3/V4/V5 behavior:
//  - V5: no numbered sectionRange and no explicit editIntent are required; the
//    edit locus is inferred from the instruction (deliberation), and a stray
//    sectionRange field is ignored rather than honored.
//  - V5: a heading with an empty body is no longer rejected by a
//    "complete section body" gate.
//  - V3/V4: the successor is composed through the byte-preserving composite
//    engine; adjacent bytes (including exact blank-line counts) outside the
//    resolved locus are never reformatted/normalized, unlike the retired
//    whole-range regenerate path.
//  - The user-consent acceptance token handshake (awaiting_acceptance ->
//    acceptSuccessor+token -> published) is preserved unchanged.
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises';
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
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-successor-locus-'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(root).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content });
	const guard = workspaceModule.createDocumentOperationGuard(root);
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'successor-locus');
	return { root, adapter };
}

test('CREATE_SUCCESSOR infers the locus from the instruction with no sectionRange and no editIntent, and preserves adjacent bytes verbatim (no boundary normalization)', async () => {
	const source = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Target\n\nOld body content.\n\n# 3 Tail\n\nKeep suffix exactly.\n';
	const { root, adapter } = await seed(source);
	// Three trailing newlines: the retired whole-range regenerate path would have
	// stripped/rewritten this down to exactly one blank line (`\n\n`) at the
	// boundary; the byte-preserving path must apply it verbatim.
	const replacementText = '# 2 Target Revised\n\nNew body content.\n\n\n';
	const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText }], unresolvedQuestions: [] }) };
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	// No `operation`/`editIntent`/`sectionRange` combination is forced: only an
	// instruction naming the target heading.
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Target.' };
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(preview.patchCount, 1);
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = (await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8')).replace(/^<!-- proposal-workspace:artifact:v1 -->\n/, '');
	const expected = '# 1 Intro\n\nKeep prefix exactly.\n\n' + replacementText + '# 3 Tail\n\nKeep suffix exactly.\n';
	assert.equal(body, expected, 'replacement text is applied verbatim; adjacent bytes are byte-identical, including the exact blank-line count');
});

test('CREATE_SUCCESSOR ignores a stray sectionRange field and resolves the locus from the instruction instead', async () => {
	const source = '# 1 Intro\n\nKeep prefix.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Beta\n\nOld beta body.\n';
	const { root, adapter } = await seed(source);
	const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 2 Alpha Revised\n\nNew alpha body.\n\n' }], unresolvedQuestions: [] }) };
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	// sectionRange, if honored, would target a different span (section 3); the
	// instruction names "Alpha", which must be the actual resolved locus.
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', sectionRange: 'sections 3–3', instruction: 'Modifica la sección Alpha.' };
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	const body = await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8');
	assert.ok(body.includes('New alpha body.'), 'the Alpha section (named in the instruction) was revised');
	assert.ok(body.includes('Old beta body.'), 'the Beta section (named only in the ignored sectionRange) is untouched');
});

test('CREATE_SUCCESSOR without editIntent defaults to a direct in-place replace instead of blocking with CREATE_SUCCESSOR_EDIT_INTENT_REQUIRED', async () => {
	const source = '# 1 Intro\n\nKeep prefix.\n\n# 2 Model\n\nOld model body.\n\n# 3 Tail\n\nKeep suffix.\n';
	const { root, adapter } = await seed(source);
	const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 2 Model Revised\n\nNew model body.\n\n' }], unresolvedQuestions: [] }) };
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Model.' };
	const preview = await orchestrator.execute(request);
	assert.notEqual(preview.reason, 'CREATE_SUCCESSOR_EDIT_INTENT_REQUIRED', JSON.stringify(preview));
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
});

test('CREATE_SUCCESSOR targeting a heading with an empty body is no longer rejected by a section-body-completeness gate', async () => {
	const source = '# 1 Placeholder\n\n# 2 Complete\n\nBody.\n';
	const { root, adapter } = await seed(source);
	const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 1 Placeholder\n\nNewly authored body.\n\n' }], unresolvedQuestions: [] }) };
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Placeholder.' };
	const result = await orchestrator.execute(request);
	assert.notEqual(result.reason, 'SECTION_RANGE_INCOMPLETE_BODY', JSON.stringify(result));
	assert.equal(result.status, 'awaiting_acceptance', JSON.stringify(result));
});

test('CREATE_SUCCESSOR still requires the bound current-turn acceptance token before publishing (consent gate preserved)', async () => {
	const source = '# 1 Intro\n\nKeep prefix.\n\n# 2 Gate\n\nOld gate body.\n\n# 3 Tail\n\nKeep suffix.\n';
	const { root, adapter } = await seed(source);
	const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 2 Gate Revised\n\nNew gate body.\n\n' }], unresolvedQuestions: [] }) };
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Gate.' };
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	const withoutToken = await orchestrator.execute({ ...request, acceptSuccessor: true });
	assert.equal(withoutToken.status, 'blocked');
	assert.equal(withoutToken.reason, 'SUCCESSOR_ACCEPTANCE_REQUIRED');
	assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md'], 'no successor is published without the acceptance token');
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
});
