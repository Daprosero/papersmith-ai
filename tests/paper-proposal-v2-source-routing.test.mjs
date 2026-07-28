import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, {
 alias: {
  '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
  '@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
  '@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
  typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
 },
});
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
 assert.deepEqual(
  (await readdir(proposals)).sort(),
  ['matematica_propuesta_CREDA.md', 'research-concept-r01.md'],
 );
 const r01Before = await readFile(r01Path);
 const r01State = await v2.loadDocumentState(root, 'research-concept-r01.md');
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'source-routing');
 const loaded = [];
 const plannerInputs = [];
 const stateLoader = async (loaderRoot, filename) => {
  loaded.push(filename);
  return v2.loadDocumentState(loaderRoot, filename);
 };
 const planner = {
  async plan(input) {
   plannerInputs.push(input);
   assert.equal(input.documentSha256, r01State.documentSha256);
   assert.equal(input.context.documentSha256, r01State.documentSha256);
   assert.equal(input.target.type, 'composite');
   assert.equal(input.target.composite.entryIds.length, 2);
   assert.ok(input.context.fragments.every(fragment => !fragment.text.includes('CREDA_ONLY')));
   return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: replacement }], unresolvedQuestions: [] };
  },
 };
 const orchestrator = new v2.PaperProposalV2Orchestrator(root, adapter, undefined, planner, {}, stateLoader);
 let latestCalls = 0;
 orchestrator.latest = async () => {
  latestCalls++;
  return 'matematica_propuesta_CREDA.md';
 };
 const result = await orchestrator.execute({
  sourceFilename: 'research-concept-r01.md',
  instruction: 'Modifica el bloque seleccionado.',
  selectedEntryId: target,
 });
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
