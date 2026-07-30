import assert from 'node:assert/strict';
import { cp, mkdir, mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

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

async function importWithDiagnostics(modulePath) {
 try { return await jiti.import(modulePath); }
 catch (error) {
  const cause = error?.cause;
  throw new Error([
   `JITI_IMPORT_FAILED: ${modulePath}`,
   `name: ${error?.name ?? 'UnknownError'}`,
   `message: ${error?.message ?? String(error)}`,
   `stack: ${error?.stack ?? '(missing)'}`,
   `cause: ${cause ? `${cause.name ?? 'UnknownError'}: ${cause.message ?? String(cause)}\n${cause.stack ?? ''}` : '(none)'}`,
  ].join('\n'));
 }
}

async function currentState(stateModule, root) {
 const fs = await import('node:fs/promises');
 const latest = (await fs.readdir(path.join(root, 'proposals')))
  .filter((name) => /^research-concept-r\d+\.md$/.test(name))
  .sort()
  .at(-1);
 return stateModule.loadDocumentState(root, latest);
}

async function entryId(stateModule, root, text) {
 const state = await currentState(stateModule, root);
 const entry = state.structuralIndex.entries.find((candidate) =>
  candidate.type === 'paragraph' && state.documentBytes.subarray(candidate.startByte, candidate.endByte).toString().includes(text));
 assert.ok(entry, `Missing fixture paragraph: ${text}`);
 return entry.entryId;
}

test('runs the production V2 tool through a complete temporary fixture', async () => {
 const fixture = await mkdtemp(path.join(tmpdir(), 'paper-proposal-production-'));
 await mkdir(path.join(fixture, '.pi'), { recursive: true });
 await mkdir(path.join(fixture, 'proposals'), { recursive: true });
 await cp('.claude/skills/paper-proposal/engine', path.join(fixture, '.claude/skills/paper-proposal/engine'), {
  recursive: true,
  filter: (source) => !source.endsWith('.before-v2-barrel-fix'),
 });

 await importWithDiagnostics(path.join(fixture, '.claude/skills/paper-proposal/engine/production-runtime.ts'));
 const aiCompat = await importWithDiagnostics(path.join(fixture, '.claude/skills/paper-proposal/engine/_pi-compat/pi-ai-compat.ts'));
 const calls = { planner: 0, tutor: 0, reviewer: 0 };
 const faux = aiCompat.registerFauxProvider({
  api: 'paper-proposal-faux',
  provider: 'paper-proposal-faux',
  models: [{ id: 'paper-proposal-faux-model', input: ['text'], contextWindow: 32000, maxTokens: 4096 }],
 });
 faux.setResponses(Array.from({ length: 4 }, () => (context) => {
  const payload = JSON.parse(context.messages.at(-1).content.find((part) => part.type === 'text').text);
  if (payload.intent) {
   calls.planner++;
   if (payload.intent.intent === 'CONCEPTUAL_REVISION') {
    return aiCompat.fauxAssistantMessage(aiCompat.fauxToolCall('paper_proposal_conceptual_revision', { actions: [{ kind: 'replace', targetEntryId: payload.target.entryId, replacementText: 'Gamma conceptually revised.' }], unresolvedQuestions: [] }));
   }
   return aiCompat.fauxAssistantMessage(JSON.stringify({ actions: [{ kind: 'replace', targetEntryId: payload.target.entryId, replacementText: 'Alpha semantically revised.' }], expectedEffects: [] }));
  }
  calls.tutor++;
  return aiCompat.fauxAssistantMessage(JSON.stringify({ decision: 'ACCEPT', summary: 'ok', mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: payload.context.fragments.map((fragment) => fragment.entryId) }));
 }));

 const workspaceModule = await importWithDiagnostics(path.join(fixture, '.claude/skills/paper-proposal/engine/proposal-workspace.ts'));
 const seed = workspaceModule.createProposalWorkspaceTool(fixture);
 await seed.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# Proposal\n\nAlpha paragraph.\n\n## Results\n\nGamma paragraph.\n' });
 const stateModule = await importWithDiagnostics(path.join(fixture, '.claude/skills/paper-proposal/engine/document-state.ts'));
 const tools = [];
 const handlers = new Map();
 workspaceModule.default({ registerTool: (tool) => tools.push(tool), on: (name, handler) => handlers.set(name, handler) });
 const tool = tools.find((candidate) => candidate.name === 'paper_proposal_execute');
 assert.equal(tools.filter((candidate) => candidate.name === 'paper_proposal_execute').length, 1);
 assert.ok(tool);
 assert.equal((await handlers.get('input')({ text: '/skill:paper-proposal modify Alpha' })).action, 'continue');
 const ctx = { model: faux.getModel(), sessionManager: { getSessionId: () => 'production-smoke-session' }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'fake', headers: {}, env: {} }) } };
 const execute = async (input) => (await tool.execute('production-smoke', input, undefined, undefined, ctx)).details;

 const modifyRequest = { instruction: 'modifica Alpha paragraph.', selectedEntryId: await entryId(stateModule, fixture, 'Alpha') };
 const modified = await execute(modifyRequest);
 assert.equal(modified.status, 'published');
 assert.equal(calls.planner, 1);
 const beforeInsertModels = calls.planner + calls.tutor + calls.reviewer;
 const inserted = await execute({ instruction: 'inserta una nota literal.', selectedEntryId: await entryId(stateModule, fixture, 'revised'), literalContent: '\n\nLiteral note.\n', position: 'after' });
 assert.equal(inserted.status, 'published');
 assert.equal(calls.planner + calls.tutor + calls.reviewer, beforeInsertModels);
 const conceptual = await execute({ instruction: 'revisión conceptual matemática de Gamma paragraph.', selectedEntryId: await entryId(stateModule, fixture, 'Gamma') });
 assert.equal(conceptual.status, 'published');
 assert.equal(calls.tutor, 1);
 assert.equal(calls.planner, 2);
 const deliberated = await execute({ instruction: 'delibera sobre Gamma paragraph.', selectedEntryId: await entryId(stateModule, fixture, 'Gamma') });
 assert.equal(deliberated.status, 'deliberated');
 assert.equal(deliberated.mutations, 0);
 assert.equal(calls.tutor, 2);
 assert.equal(calls.reviewer, 0);
});
