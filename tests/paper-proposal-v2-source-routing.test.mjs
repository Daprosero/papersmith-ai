import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
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
const workspaceModule = await jiti.import(path.resolve('.pi/extensions/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('.pi/extensions/paper-proposal-v2/exports.ts'));

test('explicit sourceFilename routes exact composite selection only through its managed document state', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-source-routing-'));
 const proposals = path.join(root, 'proposals');
 await mkdir(proposals, { recursive: true });
 const first = '$$\nA_{r01}=1.\n$$';
 const second = '$$\nB_{r01}=2.\n$$';
 const target = `${first}\n\n${second}\n`;
 const replacement = '$$\nC_{r01}=3.\n$$\n';
 const creDa = '# CREDA default\n\nCREDA_ONLY\n\n$$\nA_{creda}=99.\n$$\n';
 await writeFile(path.join(proposals, 'matematica_propuesta_CREDA.md'), creDa);
 const bootstrap = workspaceModule.createProposalWorkspaceTool(root);
 await bootstrap.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: `# R01\n\nR01_ONLY\n\n${target}\n` });
 const r01Path = path.join(proposals, 'research-concept-r01.md');
 const r01Before = await readFile(r01Path);
 const r01State = await v2.loadDocumentState(root, 'research-concept-r01.md');
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'source-routing');
 const loaded = [];
 const plannerInputs = [];
 const stateLoader = async (loaderRoot, filename) => { loaded.push(filename); return v2.loadDocumentState(loaderRoot, filename); };
 const planner = { async plan(input) {
  plannerInputs.push(input);
  assert.equal(input.documentSha256, r01State.documentSha256);
  assert.equal(input.context.documentSha256, r01State.documentSha256);
  assert.equal(input.target.type, 'composite');
  assert.equal(input.target.composite.entryIds.length, 2);
  assert.ok(input.context.fragments.every(fragment => !fragment.text.includes('CREDA_ONLY')));
  return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: replacement }], unresolvedQuestions: [] };
 } };
 const orchestrator = new v2.PaperProposalV2Orchestrator(root, adapter, undefined, planner, {}, stateLoader);
 let latestCalls = 0;
 orchestrator.latest = async () => { latestCalls++; return 'matematica_propuesta_CREDA.md'; };
 const result = await orchestrator.execute({ sourceFilename: 'research-concept-r01.md', instruction: 'Modifica el bloque seleccionado.', selectedEntryId: target });
 assert.equal(result.status, 'published', JSON.stringify(result));
 assert.equal(result.plannerCalls, 1);
 assert.equal(latestCalls, 0);
 assert.deepEqual(loaded, ['research-concept-r01.md']);
 assert.equal(plannerInputs.length, 1);
 assert.equal(result.receipt.sourceFilename, 'research-concept-r01.md');
 assert.equal(result.receipt.documentShaBefore, r01State.documentSha256);
 assert.equal(result.plan.resolvedTargets.length, 1);
 assert.equal(result.compiled.patches.length, 1);
 assert.equal(result.published.patchCount, 1);
 assert.deepEqual(await readFile(r01Path), r01Before);
 assert.deepEqual(await readFile(path.join(proposals, 'matematica_propuesta_CREDA.md')), Buffer.from(creDa));
 const published = await readFile(path.join(proposals, 'research-concept-r02.md'), 'utf8');
 assert.ok(published.includes(replacement));
 assert.ok(!published.includes('A_{r01}=1.'));
});

test('CREATE_SUCCESSOR authorizes only one composite range replacement and waits for acceptance', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-composite-successor-'));
 const proposals = path.join(root, 'proposals');
 await mkdir(proposals, { recursive: true });
 const bootstrap = workspaceModule.createProposalWorkspaceTool(root);
 await bootstrap.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# 1 Intro\n\nKeep.\n\n# 2 Framing\n\nOld.\n\n## 2.1 Detail\n\nOld detail.\n\n# 3 End\n\nKeep.\n' });
 const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
 const range = v2.resolveSectionRange(state, 'sections 2–2.1').candidate;
 const child = state.structuralIndex.entries.find(entry => entry.type === 'paragraph' && state.documentBytes.subarray(entry.startByte, entry.endByte).toString().includes('Old detail.')).entryId;
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'composite-successor');
 const request = { operation: 'CREATE_SUCCESSOR', editIntent: 'CONCEPTUAL_REVISION', sourceFilename: 'research-concept-r01.md', sectionRange: 'sections 2–2.1', instruction: 'Revise the bounded range.' };
 const childPlanner = { plan: async () => ({ actions: [{ kind: 'replace', targetEntryId: child, replacementText: 'bad' }], unresolvedQuestions: [] }) };
 const rejected = await new v2.PaperProposalV2Orchestrator(root, adapter, undefined, childPlanner).execute(request);
 assert.equal(rejected.status, 'blocked');
 assert.equal(rejected.reason, 'SUCCESSOR_CHILD_TARGET_FORBIDDEN');
 const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 2 Reframed\n\nNew bounded content.\n\n' }], unresolvedQuestions: [] }) };
 const preview = await new v2.PaperProposalV2Orchestrator(root, adapter, undefined, planner).execute(request);
 assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
 assert.equal(preview.compiled.patches.length, 1);
 assert.equal(preview.context.fragments.length, 1);
 assert.equal(preview.context.fragments[0].entryId, range.entryId);
 assert.equal(preview.plan.successorCompositeTarget, true);
});

test('CREATE_SUCCESSOR rejects an oversized composite context before planning or publication', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-successor-context-cap-'));
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 const bootstrap = workspaceModule.createProposalWorkspaceTool(root);
 await bootstrap.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: `# 1 Intro\n\nKeep.\n\n# 2 Large\n\n${'x'.repeat(32_001)}\n\n# 3 End\n\nKeep.\n` });
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'context-cap');
 let plannerCalls = 0;
 const result = await new v2.PaperProposalV2Orchestrator(root, adapter, undefined, { plan: async () => { plannerCalls++; return { actions: [] }; } }).execute({ operation: 'CREATE_SUCCESSOR', editIntent: 'CONCEPTUAL_REVISION', sourceFilename: 'research-concept-r01.md', sectionRange: 'sections 2–2', instruction: 'Revise the bounded range.' });
 assert.equal(result.status, 'blocked');
 assert.equal(result.reason, 'SUCCESSOR_CONTEXT_TOO_LARGE');
 assert.equal(plannerCalls, 0);
 assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md']);
});
