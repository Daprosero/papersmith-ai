import assert from 'node:assert/strict'; import path from 'node:path'; import test from 'node:test'; import { pathToFileURL } from 'node:url'; import { mkdtemp, mkdir } from 'node:fs/promises'; import { tmpdir } from 'node:os'; import { join } from 'node:path';

// D5: a CONCEPTUAL_REVISION turn that reaches CANDIDATE_VALIDATION_FAILED
// consults a tutor before it ever reaches the planner-only budget check, so
// `modelCalls` (tutor + planner) and `plannerCalls` (planner only) MUST
// diverge on this blocked return. A test where the two values are equal
// cannot tell a correct field from a copy-pasted one — see design decision
// A6 and spec requirement "Blocked Publish Returns Assert plannerCalls
// Independently Of modelCalls".

const piRoot = path.resolve('.');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: { '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'), '@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'), '@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'), typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs') } });

const engineDir = 'skills/_core/deliberation/engine';
const { createProposalWorkspaceTool, createDocumentOperationGuard } = await jiti.import(path.resolve(`${engineDir}/proposal-workspace.ts`));
const { ProposalDeliberationOrchestrator } = await jiti.import(path.resolve(`${engineDir}/orchestrator.ts`));
const { ProposalWorkspaceAdapter } = await jiti.import(path.resolve(`${engineDir}/proposal-workspace-adapter.ts`));
const { loadDocumentState } = await jiti.import(path.resolve(`${engineDir}/document-state.ts`));
const { artifact } = await jiti.import(path.resolve(`${engineDir}/artifact-naming.ts`));

test('CANDIDATE_VALIDATION_FAILED reports plannerCalls independently of modelCalls', async () => {
	const root = await mkdtemp(join(tmpdir(), 'pp-blocked-return-'));
	await mkdir(join(root, artifact.directory), { recursive: true });
	const seed = createProposalWorkspaceTool(root);
	await seed.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# Proposal\n\nGamma paragraph.\n' });

	const guard = createDocumentOperationGuard(root);
	const workspace = createProposalWorkspaceTool(root, { operationGuard: guard });
	let operationSequence = 0;
	const adapter = new ProposalWorkspaceAdapter(root, guard, workspace, () => `blocked-return-${++operationSequence}`);

	// Tutor decision inside its vocabulary, LOW risk, `affectedEntryIds` derived
	// from its own input (never a hardcoded id), so this is a genuinely
	// invoked, genuinely valid tutor turn -- not a stub answering vacuously.
	const tutor = { assess: async (input) => ({ decision: 'ACCEPT', summary: 'ok', mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: input.context.fragments.map((f) => f.entryId) }) };

	let gammaEntryId;
	// One `replace` action whose replacement text contains a `#######` line
	// (seven `#`), so `validateCandidate`'s markdown check (`/^#{7,}/m`) fails
	// and the turn lands on CANDIDATE_VALIDATION_FAILED, not on a success path.
	const planner = { plan: async () => ({ actions: [{ kind: 'replace', targetEntryId: gammaEntryId, replacementText: '#######\n\nRevised conceptual text.' }], expectedEffects: [] }) };

	const orchestrator = new ProposalDeliberationOrchestrator(root, adapter, undefined, planner, { tutor });
	const filename = await orchestrator.latest();
	const state = await loadDocumentState(root, filename);
	gammaEntryId = state.structuralIndex.entries.find((entry) => entry.type === 'paragraph' && state.documentBytes.subarray(entry.startByte, entry.endByte).toString().includes('Gamma')).entryId;

	// Matches EXPERT_REQUIRED (`matem|ecuaci|regularización|semi-supervisado|teórico`)
	// and `conceptual` (CONCEPTUAL_REVISION trigger); matches none of
	// `reviewer|revisión independiente|alto riesgo|varias secciones`, so this
	// stays a tutor-only turn and never requires the reviewer role.
	const result = await orchestrator.execute({ instruction: 'revisión conceptual teórico de la ecuación.', selectedEntryId: gammaEntryId });

	assert.equal(result.status, 'blocked');
	assert.equal(result.reason, 'CANDIDATE_VALIDATION_FAILED');
	assert.equal(result.modelCalls, 2);
	assert.equal(result.plannerCalls, 1);
	assert.notEqual(result.plannerCalls, result.modelCalls);
});
