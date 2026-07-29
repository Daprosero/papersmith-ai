import assert from 'node:assert/strict';
import { copyFile, cp, mkdir, mkdtemp, readFile, readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const repositoryRoot = path.resolve('.');
const repositorySourcePath = path.join(repositoryRoot, 'proposals/research-concept-r01.md');
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const aiRoot = path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, {
 alias: {
  '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
  '@earendil-works/pi-ai/compat': path.join(aiRoot, 'compat.js'),
  '@earendil-works/pi-ai': path.join(aiRoot, 'index.js'),
  typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
 },
});
const aiCompat = await jiti.import(path.join(aiRoot, 'compat.js'));
let providerSequence = 0;

async function productionFixture(responses) {
 const root = await mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-production-role-metrics-'));
 await mkdir(path.join(root, '.pi'), { recursive: true });
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 await cp(path.join(repositoryRoot, '.pi/extensions'), path.join(root, '.pi/extensions'), { recursive: true });
 await copyFile(repositorySourcePath, path.join(root, 'proposals/research-concept-r01.md'));
 const workspaceModule = await jiti.import(path.join(root, '.pi/extensions/proposal-workspace.ts'));
 const v2 = await jiti.import(path.join(root, '.pi/extensions/paper-proposal-v2/exports.ts'));
 const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
 const paragraphs = state.structuralIndex.entries.filter((entry) => entry.type === 'paragraph');
 const paragraph = paragraphs.find((entry) => entry.startByte > '<!-- proposal-workspace:artifact:v1 -->\n'.length);
 assert.ok(paragraph, 'temporary production fixture requires a paragraph target after the artifact marker');
 v2.resetRuntimeMetrics();
 const providerId = `paper-proposal-v2-production-role-metrics-${++providerSequence}`;
 const faux = aiCompat.registerFauxProvider({
  api: providerId,
  provider: providerId,
  models: [{ id: `${providerId}-model`, input: ['text'], contextWindow: 32000, maxTokens: 4096 }],
 });
 faux.setResponses(responses);
 const tools = [];
 workspaceModule.default({ registerTool: (tool) => tools.push(tool), on: () => {} });
 const tool = tools.find((candidate) => candidate.name === 'paper_proposal_v2_execute');
 assert.ok(tool, 'registered production paper_proposal_v2_execute tool is required');
 const ctx = {
  model: faux.getModel(),
  sessionManager: { getSessionId: () => `production-role-metrics-session-${providerSequence}` },
  modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'fake', headers: {}, env: {} }) },
 };
 return {
  root,
  v2,
  faux,
  paragraph,
  execute: async (instruction) => (await tool.execute(
   `production-role-metrics-${providerSequence}`,
   { sourceFilename: 'research-concept-r01.md', instruction, selectedEntryId: paragraph.entryId },
   undefined,
   undefined,
   ctx,
  )).details,
 };
}

function payloadFrom(context) {
 return JSON.parse(context.messages.at(-1).content.find((part) => part.type === 'text').text);
}

function tutorResponse(context) {
 const payload = payloadFrom(context);
 return aiCompat.fauxAssistantMessage(JSON.stringify({
  decision: 'ACCEPT',
  summary: 'Read-only tutor assessment.',
  mathematicalIssues: [],
  notationIssues: [],
  assumptionIssues: [],
  requiredRevisions: [],
  unresolvedQuestions: [],
  riskLevel: 'LOW',
  affectedEntryIds: payload.context.fragments.map((fragment) => fragment.entryId),
 }));
}

function reviewerResponse() {
 return aiCompat.fauxAssistantMessage(JSON.stringify({
  decision: 'APPROVE',
  scientificCoherence: 'Coherent within the supplied context.',
  scopeCompliance: 'Bounded and read-only.',
  unsupportedClaims: [],
  referenceRisks: [],
  notationRisks: [],
  requiredChanges: [],
  unresolvedQuestions: [],
  riskLevel: 'LOW',
 }));
}

async function assertReadOnly(run, repositoryBefore) {
 assert.deepEqual(await readFile(path.join(run.root, 'proposals/research-concept-r01.md')), repositoryBefore);
 assert.deepEqual((await readdir(path.join(run.root, 'proposals'))).sort(), ['research-concept-r01.md']);
 assert.deepEqual(await readFile(repositorySourcePath), repositoryBefore);
}

test('production DELIBERATE counts one tutor model call and remains read-only', async () => {
 const repositoryBefore = await readFile(repositorySourcePath);
 const run = await productionFixture([tutorResponse]);
 try {
  const result = await run.execute('delibera sobre este párrafo sin cambiarlo');
  const metrics = run.v2.getRuntimeMetrics();
  assert.equal(result.status, 'deliberated', JSON.stringify(result));
  assert.equal(run.faux.state.callCount, 1);
  assert.equal(result.modelCalls, 1);
  assert.equal(metrics.totalModelCalls, 1);
  assert.equal(metrics.totalRoleCalls, 1);
  assert.equal(metrics.totalTutorCalls, 1);
  assert.equal(metrics.totalReviewerCalls, 0);
  assert.equal(metrics.totalMutations, 0);
  assert.equal(metrics.totalWrites, 0);
  assert.ok(metrics.maxObservedParallelModelCalls <= 1);
  await assertReadOnly(run, repositoryBefore);
 } finally {
  run.faux.unregister?.();
 }
});

test('production REVIEW counts one reviewer model call and remains read-only', async () => {
 const repositoryBefore = await readFile(repositorySourcePath);
 const run = await productionFixture([reviewerResponse]);
 try {
  const result = await run.execute('revisa críticamente este párrafo sin cambiarlo');
  const metrics = run.v2.getRuntimeMetrics();
  assert.equal(result.status, 'deliberated', JSON.stringify(result));
  assert.equal(run.faux.state.callCount, 1);
  assert.equal(result.modelCalls, 1);
  assert.equal(metrics.totalModelCalls, 1);
  assert.equal(metrics.totalRoleCalls, 1);
  assert.equal(metrics.totalReviewerCalls, 1);
  assert.equal(metrics.totalTutorCalls, 0);
  assert.equal(metrics.totalMutations, 0);
  assert.equal(metrics.totalWrites, 0);
  assert.ok(metrics.maxObservedParallelModelCalls <= 1);
  await assertReadOnly(run, repositoryBefore);
 } finally {
  run.faux.unregister?.();
 }
});

test('production semantic planner remains counted exactly once', async () => {
 const repositoryBefore = await readFile(repositorySourcePath);
 const run = await productionFixture([(context) => {
  const payload = payloadFrom(context);
  return aiCompat.fauxAssistantMessage(JSON.stringify({
   actions: [{ kind: 'replace', targetEntryId: payload.target.entryId, replacementText: 'Bounded semantic replacement.' }],
   unresolvedQuestions: [],
  }));
 }]);
 try {
  const result = await run.execute('modifica semánticamente este párrafo');
  const metrics = run.v2.getRuntimeMetrics();
  assert.equal(result.status, 'published', JSON.stringify(result));
  assert.equal(run.faux.state.callCount, 1);
  assert.equal(result.modelCalls, 1);
  assert.equal(result.plannerCalls, 1);
  assert.equal(metrics.totalModelCalls, 1);
  assert.equal(metrics.totalPlannerCalls, 1);
  assert.equal(metrics.totalRoleCalls, 0);
  assert.equal(metrics.totalTutorCalls, 0);
  assert.equal(metrics.totalReviewerCalls, 0);
  assert.equal(metrics.currentModelCalls, 0);
  assert.equal(metrics.currentPlannerCalls, 0);
  assert.deepEqual(await readFile(repositorySourcePath), repositoryBefore);
 } finally {
  run.faux.unregister?.();
 }
});

test('two concurrent production DELIBERATE attempts respect the single-call cap', async () => {
 const repositoryBefore = await readFile(repositorySourcePath);
 const run = await productionFixture([tutorResponse, tutorResponse]);
 try {
  const [first, second] = await Promise.all([
   run.execute('delibera sobre este párrafo sin cambiarlo'),
   run.execute('analiza este párrafo sin cambiarlo'),
  ]);
  const metrics = run.v2.getRuntimeMetrics();
  assert.equal(first.status, 'deliberated', JSON.stringify(first));
  assert.equal(second.status, 'deliberated', JSON.stringify(second));
  assert.equal(run.faux.state.callCount, 2);
  assert.equal(metrics.totalModelCalls, 2);
  assert.equal(metrics.totalRoleCalls, 2);
  assert.equal(metrics.totalTutorCalls, 2);
  assert.equal(metrics.maxObservedParallelModelCalls, 1);
  assert.equal(metrics.currentModelCalls, 0);
  assert.equal(metrics.currentRoleCalls, 0);
  await assertReadOnly(run, repositoryBefore);
 } finally {
  run.faux.unregister?.();
 }
});

test('production provider failure preserves attempted role metrics and releases active counters', async () => {
 const repositoryBefore = await readFile(repositorySourcePath);
 const run = await productionFixture([() => { throw new Error('provider details must not escape'); }]);
 try {
  const result = await run.execute('delibera sobre este párrafo sin cambiarlo');
  const metrics = run.v2.getRuntimeMetrics();
  assert.equal(result.status, 'blocked', JSON.stringify(result));
  assert.equal(result.category, 'model');
  assert.equal(typeof result.message, 'string');
  assert.ok(result.message.trim().length > 0);
  assert.doesNotMatch(result.message, /provider details must not escape/i);
  assert.equal(result.modelCalls, 1);
  assert.equal(result.plannerCalls, 0);
  assert.equal(result.tutorCalls, 1);
  assert.equal(result.reviewerCalls, 0);
  assert.equal(result.mutations, 0);
  assert.equal(Object.hasOwn(result, 'publishedBytes'), false);
  assert.equal(Object.hasOwn(result, 'reason'), false);
  assert.equal(run.faux.state.callCount, 1);
  assert.equal(metrics.totalModelCalls, 1);
  assert.equal(metrics.totalRoleCalls, 1);
  assert.equal(metrics.totalTutorCalls, 1);
  assert.equal(metrics.totalReviewerCalls, 0);
  assert.equal(metrics.currentModelCalls, 0);
  assert.equal(metrics.currentRoleCalls, 0);
  assert.equal(metrics.currentPlannerCalls, 0);
  assert.equal(metrics.totalMutations, 0);
  assert.equal(metrics.totalWrites, 0);
  await assertReadOnly(run, repositoryBefore);
 } finally {
  run.faux.unregister?.();
 }
});
