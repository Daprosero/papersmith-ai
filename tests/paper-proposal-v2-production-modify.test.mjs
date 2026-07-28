import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { copyFile, cp, mkdir, mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const repositoryRoot = path.resolve('.');
const repositorySourcePath = path.join(repositoryRoot, 'proposals/research-concept-r01.md');
const repositorySuccessorPath = path.join(repositoryRoot, 'proposals/research-concept-r02.md');
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
const v2Module = await jiti.import(path.join(repositoryRoot, '.pi/extensions/paper-proposal-v2/exports.ts'));

const firstEquation = `$$
\\sum_{c=1}^C y_{i,c}^s=1,\\qquad i\\in\\{1,\\ldots,N_s\\}.
$$`;
const secondEquation = `$$
y_{i,c}^s\\in\\{0,1\\},\\qquad y_{i,c}^sy_{i,c'}^s=0\\quad\\text{para }c\\ne c',\\qquad c,c'\\in\\{1,\\ldots,C\\}.
$$`;
const providedTargetBlock = `${firstEquation}\n\n${secondEquation}`;
const sourceTargetBlock = `${firstEquation}\n${secondEquation}`;
const replacementBlock = `$$
\\sum_{c=1}^C y_{i,c}^s=1,
$$

$$
y_{i,c}^s\\neq y_{i,c'}^s,
\\qquad
c,c'\\in C,
\\qquad
y_{i,c}^s,y_{i,c'}^s\\in\\mathbf y_i^s,
$$`;
const instruction = `En la propuesta administrada research-concept-r01.md, reemplaza exactamente este bloque:\n\n${providedTargetBlock}\n\npor este bloque:\n\n${replacementBlock}\n\nNo modifiques ningún otro byte del documento.`;

const sha256 = (value) => createHash('sha256').update(value).digest('hex');
let providerSequence = 0;

async function assertMissing(filename) {
 await assert.rejects(readFile(filename), { code: 'ENOENT' });
}

async function assertRepositoryUnchanged(expectedBytes) {
 assert.deepEqual(await readFile(repositorySourcePath), expectedBytes);
 assert.equal(sha256(await readFile(repositorySourcePath)), sha256(expectedBytes));
 await assertMissing(repositorySuccessorPath);
}

async function executeThroughProductionTool(responseFactory, options = {}) {
 const repositorySourceBefore = await readFile(repositorySourcePath);
 await assertMissing(repositorySuccessorPath);
 const root = await mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-production-modify-'));
 await mkdir(path.join(root, '.pi'), { recursive: true });
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 await cp(path.join(repositoryRoot, '.pi/extensions'), path.join(root, '.pi/extensions'), {
  recursive: true,
  filter: (source) => !source.endsWith('.before-v2-barrel-fix'),
 });
 await copyFile(repositorySourcePath, path.join(root, 'proposals/research-concept-r01.md'));
 await assertMissing(path.join(root, 'proposals/research-concept-r02.md'));

 const workspaceModule = await jiti.import(path.join(root, '.pi/extensions/proposal-workspace.ts'));
 const v2 = await jiti.import(path.join(root, '.pi/extensions/paper-proposal-v2/exports.ts'));
 v2.resetRuntimeMetrics();
 const payloads = [];
 const providerContexts = [];
 const providerId = `paper-proposal-v2-production-modify-${++providerSequence}`;
 const faux = aiCompat.registerFauxProvider({
  api: providerId,
  provider: providerId,
  models: [{ id: `${providerId}-model`, input: ['text'], contextWindow: 32000, maxTokens: 4096 }],
 });
 faux.setResponses([(context) => {
  const payload = JSON.parse(context.messages.at(-1).content.find((part) => part.type === 'text').text);
  payloads.push(payload);
  providerContexts.push(context);
  const plannerResponse = responseFactory(payload);
  try {
   return aiCompat.fauxAssistantMessage(aiCompat.fauxToolCall('paper_proposal_v2_fidelity_modify', JSON.parse(plannerResponse)));
  } catch {
   return aiCompat.fauxAssistantMessage(plannerResponse);
  }
 }]);

 const tools = [];
 const previousBudget = process.env.PAPER_PROPOSAL_V2_MODIFY_INPUT_BUDGET_BYTES;
 if (options.modifyInputBudget !== undefined) process.env.PAPER_PROPOSAL_V2_MODIFY_INPUT_BUDGET_BYTES = String(options.modifyInputBudget);
 try {
  workspaceModule.default({ registerTool: (tool) => tools.push(tool), on: () => {} });
 } finally {
  if (previousBudget === undefined) delete process.env.PAPER_PROPOSAL_V2_MODIFY_INPUT_BUDGET_BYTES;
  else process.env.PAPER_PROPOSAL_V2_MODIFY_INPUT_BUDGET_BYTES = previousBudget;
 }
 const tool = tools.find((candidate) => candidate.name === 'paper_proposal_v2_execute');
 assert.ok(tool, 'registered production paper_proposal_v2_execute tool is required');
 assert.equal(tools.filter((candidate) => candidate.name === 'paper_proposal_v2_execute').length, 1);
 const request = { sourceFilename: 'research-concept-r01.md', instruction };
 const ctx = {
  model: faux.getModel(),
  modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'fake', headers: {}, env: {} }) },
 };
 let response;
 let providerCalls;
 try {
  response = await tool.execute(`production-modify-${providerSequence}`, structuredClone(request), undefined, undefined, ctx);
  providerCalls = faux.state.callCount;
 } finally {
  faux.unregister?.();
 }
 return {
  root,
  sourcePath: path.join(root, 'proposals/research-concept-r01.md'),
  successorPath: path.join(root, 'proposals/research-concept-r02.md'),
  repositorySourceBefore,
  sourceBefore: repositorySourceBefore,
  request,
  payloads,
  providerContexts,
  providerCalls,
  response,
  result: response.details,
  metrics: v2.getRuntimeMetrics(),
 };
}

test('production tool publishes the P0 replacement from a byte-identical temporary real proposal copy', async () => {
 const run = await executeThroughProductionTool((payload) => JSON.stringify({
  actions: [{
   kind: 'replace',
   targetEntryId: payload.targetEntryId,
   replacementText: payload.replacementBlock,
  }],
  unresolvedQuestions: [],
 }));
 const { result, metrics } = run;
 assert.deepEqual(Object.keys(run.request).sort(), ['instruction', 'sourceFilename']);
 assert.equal(run.request.instruction, instruction);
 assert.deepEqual(await readFile(run.sourcePath), run.sourceBefore);
 assert.equal(sha256(run.sourceBefore), 'bec1edd3cfde073efde4d0053bd8e4375e4af51021ad02b422bf36ea9c1fa55c');
 assert.equal(run.payloads.length, 1);
 assert.equal(run.providerCalls, 1);
 assert.equal(run.payloads[0].operation, 'MODIFY');
 assert.equal(run.payloads[0].targetBlock, providedTargetBlock);
 assert.equal(run.payloads[0].replacementBlock, replacementBlock);
 const providerInput = run.providerContexts[0].systemPrompt + run.providerContexts[0].messages[0].content[0].text + JSON.stringify(run.providerContexts[0].tools);
 const occurrences = (value) => providerInput.split(JSON.stringify(value).slice(1, -1)).length - 1;
 assert.equal(occurrences(providedTargetBlock), 1);
 assert.equal(occurrences(replacementBlock), 1);
 assert.doesNotMatch(providerInput, /sessionHistory|conversationHistory|messagesHistory/);
 assert.ok(Buffer.byteLength(providerInput) < 5000);

 const serialized = JSON.stringify(result);
 assert.equal(result.status, 'published', serialized);
 assert.deepEqual(JSON.parse(run.response.content[0].text), result);
 for (const key of ['operation','sourceFilename','targetFilename','targetSha256','patchCount','modelCalls','plannerCalls','tutorCalls','reviewerCalls','receiptId','manifestStatus','auditStatus','warnings']) assert.ok(key in result, key);
 for (const key of ['publishedBytes','documentBytes','candidate','compiledCandidate','compiled','derived','plan','context','validation','workspaceEvidence','plannerInputBudget']) assert.doesNotMatch(serialized, new RegExp(`"${key}"`));
 assert.ok(Buffer.byteLength(serialized) < 2000);
 assert.equal(result.operation, 'MODIFY');
 assert.equal(result.modelCalls, 1);
 assert.equal(result.plannerCalls, 1);
 assert.equal(result.tutorCalls, 0);
 assert.equal(result.reviewerCalls, 0);
 assert.equal(result.mutations, 1);
 assert.equal(result.patchCount, 1);
 assert.equal(result.manifestStatus, 'COMMITTED');
 assert.equal(result.auditStatus, 'PASS');
 assert.equal(result.selfAuditStatus, 'PASS');
 assert.equal(metrics.totalModelCalls, 1);
 assert.equal(metrics.totalPlannerCalls, 1);
 assert.equal(metrics.totalRoleCalls, 0);
 assert.equal(metrics.totalMutations, 1);

 const after = await readFile(run.successorPath);
 const expected = Buffer.from(run.sourceBefore.toString().replace(sourceTargetBlock, () => replacementBlock));
 assert.deepEqual(after, expected);
 const startByte = run.sourceBefore.indexOf(sourceTargetBlock);
 const endByte = startByte + Buffer.byteLength(sourceTargetBlock);
 assert.deepEqual(run.sourceBefore.subarray(0, startByte), after.subarray(0, startByte));
 assert.deepEqual(run.sourceBefore.subarray(endByte), after.subarray(startByte + Buffer.byteLength(replacementBlock)));
 const receipt = JSON.parse(await readFile(path.join(run.root, '.paper-proposal-v2/receipts/research-concept-r02.md.json'), 'utf8'));
 const state = JSON.parse(await readFile(path.join(run.root, '.paper-proposal-v2/state/research-concept-r02.md.json'), 'utf8'));
 assert.equal(receipt.patchCount, 1);
 assert.equal(receipt.derivedStateStatus, 'COMMITTED');
 assert.equal(state.manifest.status, 'COMMITTED');
 assert.equal(sha256(run.sourceBefore), receipt.documentShaBefore);
 assert.equal(sha256(after), receipt.documentShaAfter);
 assert.equal(sha256(after), result.targetSha256);
 await assertRepositoryUnchanged(run.repositorySourceBefore);
});

test('production tool preserves one valid action when clarification is required and does not publish', async () => {
 const run = await executeThroughProductionTool((payload) => JSON.stringify({
  actions: [{
   kind: 'replace',
   targetEntryId: payload.targetEntryId,
   replacementText: payload.replacementBlock,
  }],
  unresolvedQuestions: ['Confirm whether C denotes the class-index set.'],
 }));
 assert.equal(run.providerCalls, 1);
 assert.equal(run.payloads.length, 1);
 assert.equal(run.result.status, 'needs-clarification', JSON.stringify(run.result));
 assert.equal(run.result.modelCalls, 1);
 assert.equal(run.result.plannerCalls, 1);
 assert.equal(run.result.mutations, 0);
 assert.equal(run.result.category, 'validation');
 assert.equal(run.result.message, 'Confirm whether C denotes the class-index set.');
 assert.equal(run.result.patchCount, 0);
 assert.doesNotMatch(JSON.stringify(run.result), /"plan"|"context"|"plannerDiagnostic"/);
 assert.equal(run.metrics.totalModelCalls, 1);
 assert.equal(run.metrics.totalPlannerCalls, 1);
 assert.equal(run.metrics.totalRoleCalls, 0);
 assert.equal(run.metrics.totalMutations, 0);
 assert.deepEqual(await readFile(run.sourcePath), run.sourceBefore);
 await assertMissing(run.successorPath);
 await assertRepositoryUnchanged(run.repositorySourceBefore);
});

test('MODIFY UTF-8 budget accounting is deterministic at and above the boundary', () => {
 const output = { name: 'budget_test', description: 'é', schema: { type: 'object' } };
 const payload = { text: 'λ' };
 const bytes = v2Module.measureStructuredInputUtf8Bytes('é', payload, output);
 assert.equal(bytes, Buffer.byteLength('é') + Buffer.byteLength(JSON.stringify(payload)) + Buffer.byteLength(JSON.stringify([{ name: output.name, description: output.description, parameters: output.schema }])));
 assert.equal(new v2Module.ProductionModelRuntime({ modifyInputBudget: bytes }).preflightFidelityModify('é', payload, output).effectiveBytes, bytes);
 assert.throws(() => new v2Module.ProductionModelRuntime({ modifyInputBudget: bytes - 1 }).preflightFidelityModify('é', payload, output), { code: 'MODIFY_INPUT_BUDGET_EXCEEDED' });
 for (const invalid of [0, -1, 1.5, 'nope']) assert.throws(() => new v2Module.ProductionModelRuntime({ modifyInputBudget: invalid }), /INVALID_MODIFY_INPUT_BUDGET/);
});

test('production tool budget-blocks exact MODIFY before planner, model, mutation, or publication', async () => {
 const run = await executeThroughProductionTool(() => { throw new Error('provider must not be called'); }, { modifyInputBudget: 1 });
 assert.equal(run.result.status, 'budget_block', JSON.stringify(run.result));
 assert.equal(run.result.category, 'budget_block');
 assert.equal(run.result.modelCalls, 0);
 assert.equal(run.result.plannerCalls, 0);
 assert.equal(run.result.mutations, 0);
 assert.equal(run.providerCalls, 0);
 assert.equal(run.payloads.length, 0);
 assert.equal(run.metrics.totalModelCalls, 0);
 assert.equal(run.metrics.totalPlannerCalls, 0);
 assert.equal(run.metrics.totalWrites, 0);
 assert.equal(run.result.budget.unit, 'utf8_bytes');
 assert.equal(run.result.budget.budgetBytes, 1);
 assert.ok(run.result.budget.effectiveBytes > 1);
 assert.deepEqual(await readFile(run.sourcePath), run.sourceBefore);
 await assertMissing(run.successorPath);
 await assertRepositoryUnchanged(run.repositorySourceBefore);
});

const invalidResponses = [
 {
  name: 'zero actions',
  diagnostic: { code: 'INVALID_ACTION_COUNT', stage: 'adapter', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: [], receivedActionCount: 0 },
  response: () => JSON.stringify({ actions: [], unresolvedQuestions: [] }),
 },
 {
  name: 'two actions',
  diagnostic: { code: 'INVALID_ACTION_COUNT', stage: 'adapter', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: [], receivedActionCount: 2 },
  response: (payload) => JSON.stringify({
   actions: [
    { kind: 'replace', targetEntryId: payload.targetEntryId, replacementText: payload.replacementBlock },
    { kind: 'replace', targetEntryId: payload.targetEntryId, replacementText: payload.replacementBlock },
   ],
   unresolvedQuestions: [],
  }),
 },
 {
  name: 'wrong action kind',
  diagnostic: { code: 'WRONG_ACTION_KIND', stage: 'adapter', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: [], receivedActionCount: 1 },
  response: (payload) => JSON.stringify({
   actions: [{ kind: 'insert', targetEntryId: payload.targetEntryId, replacementText: payload.replacementBlock }],
   unresolvedQuestions: [],
  }),
 },
 {
  name: 'wrong target',
  diagnostic: { code: 'WRONG_TARGET_ENTRY_ID', stage: 'adapter', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: [], receivedActionCount: 1 },
  response: (payload) => JSON.stringify({
   actions: [{ kind: 'replace', targetEntryId: 'invented-entry', replacementText: payload.replacementBlock }],
   unresolvedQuestions: [],
  }),
 },
 {
  name: 'altered replacement',
  diagnostic: { code: 'ALTERED_REPLACEMENT_TEXT', stage: 'adapter', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: [], receivedActionCount: 1 },
  response: (payload) => JSON.stringify({
   actions: [{ kind: 'replace', targetEntryId: payload.targetEntryId, replacementText: `${payload.replacementBlock}\n` }],
   unresolvedQuestions: [],
  }),
 },
 {
  name: 'unknown action field',
  diagnostic: { code: 'UNEXPECTED_ACTION_FIELD', stage: 'adapter', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: ['type'], receivedActionCount: 1 },
  response: (payload) => JSON.stringify({
   actions: [{ kind: 'replace', type: 'replace', targetEntryId: payload.targetEntryId, replacementText: payload.replacementBlock }],
   unresolvedQuestions: [],
  }),
 },
 {
  name: 'invalid JSON',
  diagnostic: { code: 'MODEL_RESPONSE_ERROR', stage: 'runtime', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: [], receivedActionCount: 0 },
  response: () => '{"actions":',
 },
 {
  name: 'free text',
  diagnostic: { code: 'MODEL_RESPONSE_ERROR', stage: 'runtime', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: [], receivedActionCount: 0 },
  response: () => 'Confirmed. Replace the equations as requested.',
 },
 {
  name: 'empty response',
  diagnostic: { code: 'MODEL_RESPONSE_ERROR', stage: 'runtime', expectedFields: ['kind', 'targetEntryId', 'replacementText'], unexpectedFields: [], receivedActionCount: 0 },
  response: () => '',
 },
];

for (const invalid of invalidResponses) {
 test(`production tool blocks ${invalid.name} with a safe diagnostic after one real provider invocation`, async () => {
  const run = await executeThroughProductionTool(invalid.response);
  assert.equal(run.payloads.length, 1);
  assert.equal(run.providerCalls, 1);
  assert.equal(run.result.status, 'blocked', JSON.stringify(run.result));
  assert.equal(run.result.category, 'model');
  assert.equal(run.result.message, 'PRODUCTION_PLANNER_RESPONSE_REJECTED');
  assert.doesNotMatch(JSON.stringify(run.result), /plannerDiagnostic|expectedFields|unexpectedFields|receivedActionCount/);
  assert.equal(run.result.modelCalls, 1);
  assert.equal(run.result.plannerCalls, 1);
  assert.equal(run.result.mutations, 0);
  assert.equal(run.metrics.totalModelCalls, 1);
  assert.equal(run.metrics.totalPlannerCalls, 1);
  assert.equal(run.metrics.totalRoleCalls, 0);
  assert.equal(run.metrics.totalTutorCalls, 0);
  assert.equal(run.metrics.totalReviewerCalls, 0);
  assert.equal(run.metrics.totalMutations, 0);
  assert.equal(run.metrics.totalWrites, 0);
  assert.deepEqual(await readFile(run.sourcePath), run.sourceBefore);
  assert.equal(sha256(await readFile(run.sourcePath)), sha256(run.sourceBefore));
  await assertMissing(run.successorPath);
  await assertRepositoryUnchanged(run.repositorySourceBefore);
 });
}
