import assert from 'node:assert/strict';
import { cp, mkdir, mkdtemp, readFile } from 'node:fs/promises';
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
 try {
  return await jiti.import(modulePath);
 } catch (error) {
  throw new Error(`JITI_IMPORT_FAILED: ${modulePath}\n${error?.stack ?? error}`);
 }
}

function requestFromSkillContract(skill, sourceFilename, instruction) {
 assert.match(skill, /with exactly `sourceFilename` and the complete original user `instruction`/);
 assert.match(skill, /Omit `selectedEntryId`, `literalContent`, every literal-mode field/);
 assert.match(skill, /internal IntentResolver derives those semantics/);
 assert.match(skill, /only after real structural document resolution returns that entry ID/);
 return { sourceFilename, instruction };
}

test('exact-block semantic MODIFY crosses the skill boundary with only sourceFilename and instruction', async () => {
 const target = `$$
\\sum_{c=1}^C y_{i,c}^s=1,\\qquad i\\in\\{1,\\ldots,N_s\\}.
$$

$$
y_{i,c}^s\\in\\{0,1\\},\\qquad y_{i,c}^sy_{i,c'}^s=0\\quad\\text{para }c\\ne c',
\\qquad c,c'\\in\\{1,\\ldots,C\\}.
$$`;
 const replacement = `$$
\\sum_{c=1}^C y_{i,c}^s=1,
$$

$$
y_{i,c}^s\\neq y_{i,c'}^s,
\\qquad
c,c'\\in C,
\\qquad
y_{i,c}^s,y_{i,c'}^s\\in\\mathbf y_i^s,
$$`;
 const instruction = `En la propuesta administrada research-concept-r01.md, reemplaza exactamente este bloque:\n\n${target}\n\npor este bloque:\n\n${replacement}\n\nNo modifiques ningún otro byte del documento.`;
 const sourceFilename = 'research-concept-r01.md';
 const fixture = await mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-skill-boundary-'));
 await mkdir(path.join(fixture, '.pi'), { recursive: true });
 await mkdir(path.join(fixture, 'proposals'), { recursive: true });
 await cp('.pi/extensions', path.join(fixture, '.pi/extensions'), {
  recursive: true,
  filter: (source) => !source.endsWith('.before-v2-barrel-fix'),
 });

 await importWithDiagnostics(path.join(fixture, '.pi/extensions/paper-proposal-v2/production-runtime.ts'));
 const aiCompat = await importWithDiagnostics(path.join(aiRoot, 'compat.js'));
 const plannerPayloads = [];
 const faux = aiCompat.registerFauxProvider({
  api: 'paper-proposal-v2-skill-boundary-faux',
  provider: 'paper-proposal-v2-skill-boundary-faux',
  models: [{ id: 'paper-proposal-v2-skill-boundary-model', input: ['text'], contextWindow: 32000, maxTokens: 4096 }],
 });
 faux.setResponses([(context) => {
  const payload = JSON.parse(context.messages.at(-1).content.find((part) => part.type === 'text').text);
  plannerPayloads.push(payload);
  return aiCompat.fauxAssistantMessage(aiCompat.fauxToolCall('paper_proposal_v2_fidelity_modify', {
   actions: [{ kind: 'replace', targetEntryId: payload.targetEntryId, replacementText: payload.replacementBlock }],
   unresolvedQuestions: [],
  }));
 }]);

 const workspaceModule = await importWithDiagnostics(path.join(fixture, '.pi/extensions/proposal-workspace.ts'));
 const seed = workspaceModule.createProposalWorkspaceTool(fixture);
 await seed.execute('seed', {
  action: 'write',
  resource: 'proposal',
  slug: 'r01',
  content: `# Representative Proposal\n\nBefore.\n\n${target}\n\nAfter.\n`,
 });
 const sourcePath = path.join(fixture, 'proposals', sourceFilename);
 const sourceBefore = await readFile(sourcePath, 'utf8');
 const tools = [];
 const handlers = new Map();
 workspaceModule.default({
  registerTool: (tool) => tools.push(tool),
  on: (name, handler) => handlers.set(name, handler),
 });
 const tool = tools.find((candidate) => candidate.name === 'paper_proposal_v2_execute');
 assert.ok(tool, 'registered production paper_proposal_v2_execute tool is required');

 const skill = await readFile('.pi/skills/paper-proposal/SKILL.md', 'utf8');
 assert.equal((await handlers.get('input')({ text: `/skill:paper-proposal\n${instruction}` })).action, 'continue');
 const skillRequest = requestFromSkillContract(skill, sourceFilename, instruction);
 let actualArgs;
 const ctx = {
  model: faux.getModel(),
  modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'fake', headers: {}, env: {} }) },
 };
 const response = await tool.execute('skill-request-boundary', (() => {
  actualArgs = structuredClone(skillRequest);
  return skillRequest;
 })(), undefined, undefined, ctx);
 const result = response.details;

 assert.deepEqual(actualArgs, { sourceFilename, instruction });
 assert.deepEqual(Object.keys(actualArgs).sort(), ['instruction', 'sourceFilename']);
 assert.equal(actualArgs.instruction, instruction);
 assert.ok(actualArgs.instruction.includes(target), 'instruction must preserve the exact original LaTeX block');
 assert.ok(actualArgs.instruction.includes(replacement), 'instruction must preserve the exact replacement LaTeX block');
 assert.equal(Object.hasOwn(actualArgs, 'selectedEntryId'), false);
 assert.equal(Object.hasOwn(actualArgs, 'literalContent'), false);

 assert.equal(plannerPayloads.length, 1);
 assert.equal(plannerPayloads[0].operation, 'MODIFY');
 assert.equal(plannerPayloads[0].targetBlock, target);
 assert.equal(plannerPayloads[0].replacementBlock, replacement);
 assert.equal(result.status, 'published', JSON.stringify(result));
 assert.equal(result.operation, 'MODIFY');
 assert.equal(result.plannerCalls, 1);
 assert.equal(result.patchCount, 1);
 assert.equal(result.sourceFilename, sourceFilename);
 assert.equal(result.targetFilename, 'research-concept-r02.md');
 assert.doesNotMatch(JSON.stringify(result), /publishedBytes|compiledCandidate|"compiled"|"derived"|"plan"|"context"/);
 assert.equal(await readFile(sourcePath, 'utf8'), sourceBefore);
 assert.equal(
  await readFile(path.join(fixture, 'proposals/research-concept-r02.md'), 'utf8'),
  sourceBefore.replace(target, () => replacement),
 );
});
