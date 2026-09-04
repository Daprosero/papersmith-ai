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
const workspaceModule = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/exports.ts'));
// The name of the one file `derive` accepts belongs to the host-chosen domain
// profile, not to this suite. Read it off the profile so the routing this test
// pins stays the same test under any domain.
const { DOMAIN } = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/domain-profile.ts'));
const deriveBase = DOMAIN.deriveBase;

test('explicit sourceFilename routes exact composite selection only through its managed document state', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-source-routing-'));
 const proposals = path.join(root, 'proposals');
 await mkdir(proposals, { recursive: true });
 const first = '$$\nA_{r01}=1.\n$$';
 const second = '$$\nB_{r01}=2.\n$$';
 const target = `${first}\n\n${second}\n`;
 const replacement = '$$\nC_{r01}=3.\n$$\n';
 const unroutedBase = '# Sediment transport base\n\nUNROUTED_ONLY\n\n$$\nA_{bed}=99.\n$$\n';
 await writeFile(path.join(proposals, deriveBase), unroutedBase);
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
  assert.ok(input.context.fragments.every(fragment => !fragment.text.includes('UNROUTED_ONLY')));
  return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: replacement }], unresolvedQuestions: [] };
 } };
 const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner, {}, stateLoader);
 let latestCalls = 0;
 orchestrator.latest = async () => { latestCalls++; return deriveBase; };
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
 assert.deepEqual(await readFile(path.join(proposals, deriveBase)), Buffer.from(unroutedBase));
 const published = await readFile(path.join(proposals, 'research-concept-r02.md'), 'utf8');
 assert.ok(published.includes(replacement));
 assert.ok(!published.includes('A_{r01}=1.'));
});

test('CREATE_SUCCESSOR authorizes only one composite locus replacement and waits for acceptance (locus inferred from the instruction, no numbered range)', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-composite-successor-'));
 const proposals = path.join(root, 'proposals');
 await mkdir(proposals, { recursive: true });
 const bootstrap = workspaceModule.createProposalWorkspaceTool(root);
 await bootstrap.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# 1 Intro\n\nKeep.\n\n# 2 Framing\n\nOld.\n\n## 2.1 Detail\n\nOld detail.\n\n# 3 End\n\nKeep.\n' });
 const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
 // The heading "2 Framing"'s natural span (its own start through the next
 // same-or-higher-level heading, "3 End") covers the same bytes the retired
 // numbered range "sections 2–2.1" used to cover; the locus is now inferred
 // from the instruction alone, with no sectionRange/editIntent required.
 const range = v2.resolveSuccessorTarget(state, 'Modifica la sección Framing.').candidates[0];
 const child = state.structuralIndex.entries.find(entry => entry.type === 'paragraph' && state.documentBytes.subarray(entry.startByte, entry.endByte).toString().includes('Old detail.')).entryId;
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'composite-successor');
 // editIntent stays optional (no forced numbered-range+editIntent gate); it is
 // supplied explicitly here only to exercise the CONCEPTUAL_REVISION branch's
 // own out-of-target rejection, same as before.
 const request = { operation: 'CREATE_SUCCESSOR', editIntent: 'CONCEPTUAL_REVISION', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Framing.' };
 const childPlanner = { plan: async () => ({ actions: [{ kind: 'replace', targetEntryId: child, replacementText: 'bad' }], unresolvedQuestions: [] }) };
 const rejected = await new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, childPlanner).execute(request);
 assert.equal(rejected.status, 'blocked');
 // Locus-inferred (no numbered range) requests report the out-of-target
 // reason against the composite's own two shell entries, same as the
 // pre-existing no-range semantic path; the numbered-range path used to
 // report the narrower "child" reason against its full descendant-entry set,
 // which no longer exists now that sectionRange is retired.
 assert.equal(rejected.reason, 'SUCCESSOR_OUTSIDE_TARGET_FORBIDDEN');
 const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 2 Reframed\n\nNew bounded content.\n\n' }], unresolvedQuestions: [] }) };
 const preview = await new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner).execute(request);
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
 const result = await new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, { plan: async () => { plannerCalls++; return { actions: [] }; } }).execute({ operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Large.' });
 assert.equal(result.status, 'blocked');
 assert.equal(result.reason, 'SUCCESSOR_CONTEXT_TOO_LARGE');
 assert.equal(plannerCalls, 0);
 assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md']);
});

async function compileSuccessorRange(source, range, replacementText) {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-successor-boundary-'));
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 await writeFile(path.join(root, 'proposals/research-concept-r01.md'), source);
 const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
 const resolution = v2.resolveSectionRange(state, range);
 assert.ok(resolution.candidate, JSON.stringify(resolution));
 v2.materializeCompositeTarget(state, resolution.candidate);
 const plan = {
  planVersion: '2', documentSha256: state.documentSha256, intent: 'CONCEPTUAL_REVISION', instructionHash: 'boundary-test',
  resolvedTargets: [resolution.candidate.entryId], semanticChange: true, destructiveIntent: false, cleanupLevel: 'NONE', constraints: [], expectedEffects: [], unresolvedQuestions: [], successorCompositeTarget: true,
  actions: [{ kind: 'replace', targetEntryId: resolution.candidate.entryId, replacementText }],
 };
 return { state, resolution, compiled: v2.compilePatches(state, plan) };
}

test('CREATE_SUCCESSOR section replacements preserve internal bytes and normalize only composite boundaries', async () => {
 const lfSource = '# 1 Intro\n\nPREFIX-LIST\n- one\n\n$$\nP=1\n$$\n\n```txt\nprefix fence\n```\n\n# 3 Results\n\nOld results.\n\n## 3.1 Analysis\n\nOld analysis.\n\n# 4 Tail\n\nSUFFIX-LIST\n- two\n\n$$\nQ=2\n$$\n\n```txt\nsuffix fence\n```\n';
 const replacement = '\n\n# 3 Revised\n\nInternal paragraph.\n\n## 3.1 Revised\n\nInternal bytes stay\n\n\n';
 const lf = await compileSuccessorRange(lfSource, 'sections 3–3.1', replacement);
 const expectedLf = '# 1 Intro\n\nPREFIX-LIST\n- one\n\n$$\nP=1\n$$\n\n```txt\nprefix fence\n```\n\n# 3 Revised\n\nInternal paragraph.\n\n## 3.1 Revised\n\nInternal bytes stay\n\n# 4 Tail\n\nSUFFIX-LIST\n- two\n\n$$\nQ=2\n$$\n\n```txt\nsuffix fence\n```\n';
 assert.equal(lf.compiled.candidate, expectedLf);
 assert.equal(lf.resolution.candidate.composite.sectionReplacement.newline, '\n');
 assert.ok(lf.compiled.candidate.includes('Internal paragraph.\n\n## 3.1 Revised'));
 assert.ok(lf.compiled.candidate.startsWith('# 1 Intro\n\nPREFIX-LIST'));
 assert.ok(lf.compiled.candidate.endsWith('```txt\nsuffix fence\n```\n'));
 await assert.rejects(compileSuccessorRange(lf.compiled.candidate, 'sections 3–3.1', '# 3 Revised\n\nInternal paragraph.\n\n## 3.1 Revised\n\nInternal bytes stay'), /NO_OP_PLAN/);

 const crlfSource = '# 1 Intro\r\n\r\n# 3 Results\r\n\r\nOld.\r\n\r\n## 3.1 Analysis\r\n\r\nOld detail.\r\n\r\n# 4 Tail\r\n\r\nTail.\r\n';
 const crlf = await compileSuccessorRange(crlfSource, '3–3.1', '\n# 3 Revised\n\nInternal LF remains\n\n## 3.1 Revised\n\n');
 assert.equal(crlf.compiled.candidate, '# 1 Intro\r\n\r\n# 3 Revised\n\nInternal LF remains\n\n## 3.1 Revised\r\n\r\n# 4 Tail\r\n\r\nTail.\r\n');
 assert.equal(crlf.resolution.candidate.composite.sectionReplacement.newline, '\r\n');

 const start = await compileSuccessorRange('# 1 Start\n\nOld.\n\n# 2 Keep\n\nKeep.\n', '1–1', '\n\n# 1 Replaced\n\nNew.\n\n');
 assert.equal(start.compiled.candidate, '# 1 Replaced\n\nNew.\n\n# 2 Keep\n\nKeep.\n');
 const end = await compileSuccessorRange('# 1 Keep\n\nKeep.\n\n# 3 End\n\nOld.\n', '3–3', '\n\n# 3 Replaced\n\nNew.\n\n');
 assert.equal(end.compiled.candidate, '# 1 Keep\n\nKeep.\n\n# 3 Replaced\n\nNew.');
});

test('resolveSectionRange (the pure, still-supported numbered-range resolver, now unused by the orchestrator) still rejects a range containing only headings', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-successor-incomplete-range-'));
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 const workspace = workspaceModule.createProposalWorkspaceTool(root);
 await workspace.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# 3 Empty\n\n# 4 Complete\n\nBody.\n' });
 const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
 assert.equal(v2.resolveSectionRange(state, '3–3').reason, 'SECTION_RANGE_INCOMPLETE_BODY');
});

test('CREATE_SUCCESSOR no longer requires a numbered range or a complete section body: a heading-only section now resolves and previews directly', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-successor-empty-body-'));
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 const workspace = workspaceModule.createProposalWorkspaceTool(root);
 await workspace.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# 3 Empty\n\n# 4 Complete\n\nBody.\n' });
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'empty-body-locus');
 let plannerCalls = 0;
 const planner = { plan: async input => { plannerCalls++; return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 3 Empty\n\nNewly authored body.\n\n' }], unresolvedQuestions: [] }; } };
 const result = await new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner).execute({ operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Empty.' });
 assert.equal(result.status, 'awaiting_acceptance', JSON.stringify(result));
 assert.equal(plannerCalls, 1);
});

test('CREATE_SUCCESSOR publishes r02 for the Results section, locus inferred from the instruction with no numbered range', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-successor-r02-3-3-1-'));
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 const workspace = workspaceModule.createProposalWorkspaceTool(root);
 const source = '# 1 Intro\n\nPrefix remains.\n\n# 3 Results\n\nOld results.\n\n## 3.1 Analysis\n\nOld analysis.\n\n# 4 Tail\n\nSuffix remains.\n';
 await workspace.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: source });
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'r02-3-3-1');
 // Well-formed replacement bytes (the caller's own responsibility now that
 // boundary whitespace is no longer auto-normalized by the compile step).
 const replacement = '# 3 Revised\n\nNew results.\n\n## 3.1 Revised\n\nNew analysis.\n\n';
 const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: replacement }], unresolvedQuestions: [] }) };
 const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
 const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Results.' };
 const preview = await orchestrator.execute(request);
 assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
 const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
 assert.equal(published.status, 'published', JSON.stringify(published));
 assert.equal(await readFile(path.join(root, 'proposals/research-concept-r02.md'), 'utf8'), '<!-- proposal-workspace:artifact:v1 -->\n# 1 Intro\n\nPrefix remains.\n\n# 3 Revised\n\nNew results.\n\n## 3.1 Revised\n\nNew analysis.\n\n# 4 Tail\n\nSuffix remains.\n');
});

test('CREATE_SUCCESSOR does not write r02 when pre-write candidate validation fails', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-successor-validation-failure-'));
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 const workspace = workspaceModule.createProposalWorkspaceTool(root);
 await workspace.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# 3 Results\n\nOld.\n\n## 3.1 Analysis\n\nOld detail.\n\n# 4 Tail\n\nKeep.\n' });
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'validation-failure');
 const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 3 Revised\n\n$$\nunclosed display\n' }], unresolvedQuestions: [] }) };
 const result = await new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner).execute({ operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Results.' });
 assert.equal(result.status, 'blocked');
 assert.equal(result.reason, 'CANDIDATE_VALIDATION_FAILED');
 assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md']);
});

test('explicit CREATE_SUCCESSOR overrides recupera r02 and derives one semantic section without a numbered range', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-semantic-successor-'));
 const proposals = path.join(root, 'proposals');
 await mkdir(proposals, { recursive: true });
 const source = '# 1 Intro\n\nPrefix bytes remain.\n\n# 2 Dynamics\n\n$$\nx_{t+1}=A x_t\n$$\n\nOld dynamics.\n\n# 3 Tail\n\nSuffix bytes remain.\n';
 const workspace = workspaceModule.createProposalWorkspaceTool(root);
 await workspace.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: source });
 const r01Path = path.join(proposals, 'research-concept-r01.md');
 const r01Before = await readFile(r01Path);
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'semantic-successor');
 // Well-formed replacement bytes (no stray leading newline): boundary
 // whitespace is no longer auto-normalized, so the caller supplies it.
 const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 2 Revised dynamics\n\n$$\nx_{t+1}=B x_t\n$$\n\nNew dynamics.\n\n' }], unresolvedQuestions: [] }) };
 const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
 const request = { operation: 'CREATE_SUCCESSOR', editIntent: 'MODIFY', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Dynamics; la ecuación recupera r02.' };
 const preview = await orchestrator.execute(request);
 assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
 assert.equal(preview.operation, 'CREATE_SUCCESSOR');
 assert.equal(preview.plan.resolvedTargets.length, 1);
 assert.equal(preview.compiled.patches.length, 1);
 assert.deepEqual(await readFile(r01Path), r01Before, 'preview preserves source bytes');
 assert.deepEqual(await readdir(proposals), ['research-concept-r01.md'], 'acceptance precedes publication');
 assert.equal(preview.compiled.candidate, '<!-- proposal-workspace:artifact:v1 -->\n# 1 Intro\n\nPrefix bytes remain.\n\n# 2 Revised dynamics\n\n$$\nx_{t+1}=B x_t\n$$\n\nNew dynamics.\n\n# 3 Tail\n\nSuffix bytes remain.\n');
 // The replacement rewrites the dynamics equation, so the old display atom
 // leaves the document: mathematical preservation requires acknowledging it
 // by the id the preview reported, exactly as an intentional removal.
 assert.deepEqual(preview.mathDelta.lost.map(atom => atom.text), ['x_{t+1}=A x_t']);
 const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken, acknowledgedMathRemovals: preview.mathDelta.lost.map(atom => atom.id) });
 assert.equal(published.status, 'published', JSON.stringify(published));
 assert.deepEqual(await readFile(r01Path), r01Before, 'publication preserves r01 bytes');
 assert.ok((await readFile(path.join(proposals, 'research-concept-r02.md'), 'utf8')).includes('New dynamics.'));
});

test('CREATE_SUCCESSOR without a numbered range returns semantic candidates when section selection is ambiguous', async () => {
 const root = await mkdtemp(path.join(os.tmpdir(), 'pp-v2-semantic-successor-ambiguous-'));
 await mkdir(path.join(root, 'proposals'), { recursive: true });
 const workspace = workspaceModule.createProposalWorkspaceTool(root);
 await workspace.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# 1 Model\n\nFirst body.\n\n# 2 Model\n\nSecond body.\n' });
 const guard = workspaceModule.createDocumentOperationGuard(root);
 const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'semantic-successor-ambiguous');
 let plannerCalls = 0;
 const result = await new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, { plan: async () => { plannerCalls++; return { actions: [] }; } }).execute({ operation: 'CREATE_SUCCESSOR', editIntent: 'MODIFY', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Model.' });
 assert.equal(result.status, 'ambiguous', JSON.stringify(result));
 assert.equal(result.candidates.length, 2);
 assert.ok(result.candidates.every(candidate => candidate.type === 'composite'));
 assert.doesNotMatch(result.question, /line|offset/i);
 assert.equal(plannerCalls, 0);
 assert.deepEqual(await readdir(path.join(root, 'proposals')), ['research-concept-r01.md']);
});
