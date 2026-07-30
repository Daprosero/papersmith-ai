import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const aiRoot = path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
 '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
 '@earendil-works/pi-ai/compat': path.join(aiRoot, 'compat.js'),
 '@earendil-works/pi-ai': path.join(aiRoot, 'index.js'),
 typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.join(root, '.pi/extensions/proposal-workspace.ts'));
const v2 = await jiti.import(path.join(root, '.pi/extensions/paper-proposal-v2/exports.ts'));
const aiCompat = await jiti.import(path.join(aiRoot, 'compat.js'));

const sourceContent = `# 1 Introduction\n\nPrefix bytes remain untouched.\n\n# 2 Framing\n\nOld framing.\n\n## 2.1 Framing average\n\nOld average.\n\n## 2.2 Setup\n\nOld setup.\n\n## 2.3 Method\n\nOld method.\n\n## 2.4 Consequences\n\nOld consequences.\n\n# 3 Results\n\nOld results.\n\n## 3.1 Analysis\n\nOld analysis.\n\n## 3.2 Validation\n\nOld validation.\n\n## 3.3 Discussion\n\nOld discussion.\n\n# 4 Conclusion\n\nSuffix bytes remain untouched.\n`;

async function fixture() {
 const projectRoot = await mkdtemp(path.join(tmpdir(), 'pp-v2-successor-acceptance-'));
 await mkdir(path.join(projectRoot, 'proposals'));
 const bootstrap = workspace.createProposalWorkspaceTool(projectRoot);
 await bootstrap.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: sourceContent });
 const guardCalls = [];
 const plannerPayloads = [];
 const guard = workspace.createDocumentOperationGuard(projectRoot);
 const guardExecute = guard.execute.bind(guard);
 guard.execute = async (input, signal) => { guardCalls.push(input); return guardExecute(input, signal); };
 const providerId = `paper-proposal-v2-successor-acceptance-${Date.now()}-${Math.random()}`;
 const faux = aiCompat.registerFauxProvider({ api: providerId, provider: providerId, models: [{ id: `${providerId}-model`, input: ['text'], contextWindow: 32000, maxTokens: 4096 }] });
 const state = await v2.loadDocumentState(projectRoot, 'research-concept-r01.md');
 const entry = heading => state.structuralIndex.entries.find(candidate => ['section', 'subsection', 'heading'].includes(candidate.type) && state.documentBytes.subarray(candidate.startByte, candidate.endByte).toString('utf8').includes(heading));
 const childId = entry('## 2.2 Setup').entryId;
 const outsideId = entry('# 4 Conclusion').entryId;
 faux.setResponses(Array.from({ length: 16 }, () => context => {
  const payload = JSON.parse(context.messages.at(-1).content.find(part => part.type === 'text').text);
  if (payload.operation === 'CREATE_SUCCESSOR_REPLACEMENT') {
   plannerPayloads.push(payload);
   const replacementText = /recupera el promedio/i.test(payload.instruction)
    ? '## 2.1 Framing average\n\nEl promedio se recupera.\n\n'
    : '# 2–3.3 Revised\n\nOnly the bounded composite range changes.\n\n';
   return aiCompat.fauxAssistantMessage(aiCompat.fauxToolCall('paper_proposal_v2_successor_replacement', { replacementText, unresolvedQuestions: [] }));
  }
  if (!payload.intent) return aiCompat.fauxAssistantMessage(JSON.stringify({ decision: 'ACCEPT', summary: 'The current managed revision is the correct source.', mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: [] }));
  const targetEntryId = /child action/i.test(payload.instruction) ? childId : /outside action/i.test(payload.instruction) ? outsideId : payload.target.entryId;
  return aiCompat.fauxAssistantMessage(aiCompat.fauxToolCall('paper_proposal_v2_conceptual_revision', { actions: [{ kind: 'replace', targetEntryId, replacementText: '# 2–3.3 Revised\n\nOnly the bounded composite range changes.\n\n' }], unresolvedQuestions: [] }));
 }));
 const tools = [];
 workspace.createPaperProposalV2Extension({ projectRoot, operationGuard: guard })({ registerTool: tool => tools.push(tool), on: () => {} });
 const tool = tools.find(candidate => candidate.name === 'paper_proposal_v2_execute');
 const ctx = { model: faux.getModel(), sessionManager: { getSessionId: () => `acceptance-session-${providerId}` }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'fake', headers: {}, env: {} }) } };
 return {
  projectRoot, guardCalls, plannerPayloads, state,
  execute: async params => (await tool.execute('successor-acceptance', params, undefined, undefined, ctx)).details,
  async dispose() { faux.unregister?.(); await rm(projectRoot, { recursive: true, force: true }); },
 };
}

test('CREATE_SUCCESSOR previews one composite patch and publishes exactly once only after bound current-turn acceptance', async () => {
 const run = await fixture();
 try {
  const r01Path = path.join(run.projectRoot, 'proposals/research-concept-r01.md');
  const before = await readFile(r01Path);
  const chat = await run.execute({ operation: 'CHAT_DELIBERATION', sourceFilename: 'research-concept-r01.md', instruction: 'Assess the current managed proposal before revising it.' });
  assert.equal(chat.status, 'deliberated', JSON.stringify(chat));
  const request = { operation: 'CREATE_SUCCESSOR', editIntent: 'CONCEPTUAL_REVISION', conversationId: chat.conversationId, sectionRange: 'sections 2–3.3', instruction: 'Replace the bounded range with a concise revision.' };
  const preview = await run.execute(request);
  assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
  assert.equal(preview.sourceFilename, 'research-concept-r01.md', 'omitted source resolves from the conversation current document');
  assert.equal(preview.targetFilename, 'research-concept-r02.md');
  assert.equal(preview.patchCount, 1);
  assert.match(preview.acceptanceToken, /^[A-Za-z0-9_-]+$/);
  assert.deepEqual(await readFile(r01Path), before, 'preview cannot mutate the source');
  assert.deepEqual(await readdir(path.join(run.projectRoot, 'proposals')), ['research-concept-r01.md'], 'preview creates no successor');
  assert.deepEqual(run.guardCalls, [], 'preview never reaches workspace publication');

  for (const acceptance of [undefined, 'wrong-token']) {
   const blocked = await run.execute({ ...request, acceptSuccessor: true, ...(acceptance ? { successorAcceptanceToken: acceptance } : {}) });
   assert.equal(blocked.status, 'blocked', JSON.stringify(blocked));
   assert.match(blocked.message, /SUCCESSOR_ACCEPTANCE_(REQUIRED|INVALID)/);
   assert.deepEqual(await readdir(path.join(run.projectRoot, 'proposals')), ['research-concept-r01.md']);
  }

  await writeFile(r01Path, Buffer.concat([before, Buffer.from('\n<!-- source changed -->\n')]));
  const stale = await run.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
  assert.equal(stale.status, 'blocked', JSON.stringify(stale));
  assert.equal(stale.message, 'SUCCESSOR_ACCEPTANCE_STALE_SOURCE');
  assert.deepEqual(await readdir(path.join(run.projectRoot, 'proposals')), ['research-concept-r01.md']);

  const freshPreview = await run.execute(request);
  assert.equal(freshPreview.status, 'awaiting_acceptance', JSON.stringify(freshPreview));
  const published = await run.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: freshPreview.acceptanceToken });
  assert.equal(published.status, 'published', JSON.stringify(published));
  assert.equal(published.targetFilename, 'research-concept-r02.md');
  assert.equal(published.patchCount, 1);
  assert.equal(run.guardCalls.filter(call => call.action === 'authorize_mutation').length, 1);
  const r02 = await readFile(path.join(run.projectRoot, 'proposals/research-concept-r02.md'));
  const range = v2.resolveSectionRange(await v2.loadDocumentState(run.projectRoot, 'research-concept-r01.md'), 'sections 2–3.3').candidate.composite;
  assert.deepEqual(r02.subarray(0, range.startByte), (await readFile(r01Path)).subarray(0, range.startByte));
  assert.deepEqual(r02.subarray(r02.length - ((await readFile(r01Path)).length - range.endByte)), (await readFile(r01Path)).subarray(range.endByte));
  assert.deepEqual(await readFile(r01Path), Buffer.concat([before, Buffer.from('\n<!-- source changed -->\n')]), 'r01 remains immutable');

  const replay = await run.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: freshPreview.acceptanceToken });
  assert.equal(replay.status, 'blocked', JSON.stringify(replay));
  assert.equal(replay.message, 'SUCCESSOR_ACCEPTANCE_INVALID');

  const child = await run.execute({ ...request, instruction: 'Use a child action instead.' });
  assert.equal(child.status, 'awaiting_acceptance', JSON.stringify(child));
  assert.equal(child.patchCount, 1);
  const outside = await run.execute({ ...request, instruction: 'Use an outside action instead.' });
  assert.equal(outside.status, 'awaiting_acceptance', JSON.stringify(outside));
  assert.equal(outside.patchCount, 1);
 } finally { await run.dispose(); }
});

test('CREATE_SUCCESSOR resolves a no-range semantic target to one minimal section and gives the production planner content-only authority', async () => {
 const run = await fixture();
 try {
  const r01Path = path.join(run.projectRoot, 'proposals/research-concept-r01.md');
  const r02Path = path.join(run.projectRoot, 'proposals/research-concept-r02.md');
  const sourceBefore = await readFile(r01Path);
  const originalTarget = '## 2.1 Framing average\n\nOld average.\n\n';
  const replacement = '## 2.1 Framing average\n\nEl promedio se recupera.\n\n';
  const request = {
   operation: 'CREATE_SUCCESSOR',
   editIntent: 'CONCEPTUAL_REVISION',
   sourceFilename: 'research-concept-r01.md',
   instruction: 'Modifica la sección Framing; se recupera el promedio y preserva la conclusión.',
  };
  const preview = await run.execute(request);
  assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
  assert.equal(preview.patchCount, 1);
  assert.equal(preview.plannerCalls, 1);
  assert.deepEqual(run.plannerPayloads.at(-1) && Object.keys(run.plannerPayloads.at(-1)).sort(), ['constraints', 'context', 'documentSha256', 'instruction', 'operation']);
  assert.equal(Object.hasOwn(run.plannerPayloads.at(-1), 'targetEntryId'), false);
  assert.equal(Object.hasOwn(run.plannerPayloads.at(-1), 'sourceFilename'), false);
  assert.equal(Object.hasOwn(run.plannerPayloads.at(-1), 'destination'), false);
  assert.equal(Object.hasOwn(run.plannerPayloads.at(-1), 'publication'), false);
  assert.equal(Object.hasOwn(run.plannerPayloads.at(-1), 'actions'), false);
  assert.equal(run.plannerPayloads.at(-1).context.fragments[0].text, originalTarget, 'nested semantic candidates collapse to the minimal section');
  assert.deepEqual(await readFile(r01Path), sourceBefore, 'preview preserves the byte-identical source');
  await assert.rejects(readFile(r02Path), { code: 'ENOENT' });

  const published = await run.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
  assert.equal(published.status, 'published', JSON.stringify(published));
  assert.equal(published.patchCount, 1);
  assert.deepEqual(await readFile(r01Path), sourceBefore, 'publication preserves the byte-identical source');
  assert.deepEqual(await readFile(r02Path), Buffer.from(sourceBefore.toString('utf8').replace(originalTarget, replacement)), 'only the canonical successor section changes');
 } finally { await run.dispose(); }
});
