// Phase 2.2 (change 4): the preservation gate -- extract atoms that must not vanish
// silently, report loss on preview, refuse accept until each loss is acknowledged --
// becomes domain-neutral. `math-integrity.ts` becomes `preservation.ts`; its
// `atoms`/`delta`/`violations` machinery sources its extractor and rule set from
// `profile.preservation.{extractAtoms, violations}` instead of hardcoding mathematics.
// The mathematical implementation ships as `proposal-deliberation/preservation-math.ts`.
//
// `mathDelta` and `acknowledgedMathRemovals` remain PERMANENT accepted aliases for
// `preservationDelta`/`acknowledgedRemovals`, in both directions, so the mathematical
// SKILL.md never needs an edit.
import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { mkdtemp } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const piRoot = path.resolve('.');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspaceModule = await jiti.import(path.resolve('skills/_core/deliberation/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('skills/_core/deliberation/engine/exports.ts'));
const engine = path.resolve('skills/_core/deliberation/engine');

/** Builds a CREATE_SUCCESSOR preview that drops the r01 dynamics display equation. */
async function previewDroppedEquation() {
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-preservation-gate-'));
	const proposals = path.join(root, 'proposals');
	await mkdir(proposals, { recursive: true });
	const source = '# 1 Intro\n\nPrefix bytes remain.\n\n# 2 Dynamics\n\n$$\nx_{t+1}=A x_t\n$$\n\nOld dynamics.\n\n# 3 Tail\n\nSuffix bytes remain.\n';
	const workspace = workspaceModule.createProposalWorkspaceTool(root);
	await workspace.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: source });
	const guard = workspaceModule.createDocumentOperationGuard(root);
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'preservation-gate');
	const planner = { plan: async input => ({ actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '# 2 Revised dynamics\n\nNew dynamics, no equation.\n\n' }], unresolvedQuestions: [] }) };
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	const request = { operation: 'CREATE_SUCCESSOR', editIntent: 'MODIFY', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Dynamics.' };
	const preview = await orchestrator.execute(request);
	return { root, orchestrator, request, preview };
}

// 2.2.1 -- the missing characterization test: this exact scenario is run FIRST, against
// the CURRENT, pre-refactor orchestrator, and must PASS today. It is the baseline change
// 4's refactor must not break (re-confirmed unchanged by 2.2.10, after the refactor).
test('2.2.1 CREATE_SUCCESSOR with a genuinely lost atom and no acknowledgement is refused with MATH_REMOVALS_NOT_ACKNOWLEDGED', async () => {
	const { orchestrator, request, preview } = await previewDroppedEquation();
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.ok(preview.mathDelta.lost.length > 0, 'the fixture must genuinely drop a mathematical atom');
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'blocked', JSON.stringify(published));
	assert.equal(published.reason, 'MATH_REMOVALS_NOT_ACKNOWLEDGED');
	assert.ok(published.unacknowledged.length > 0);
});

test('2.2.2 profile.preservation.{extractAtoms,violations} wired to preservation-math.ts reproduces byte-identical atoms/deltas/violations for the mathematical profile', async () => {
	const { DOMAIN } = await jiti.import(path.join(engine, 'domain-profile.ts'));
	const preservationMath = await jiti.import(path.resolve('skills/proposal-deliberation/preservation-math.ts'));
	const source = '## S\n\n$$\nx = 1 \\tag{1}\n$$\n';
	const viaProfile = [...DOMAIN.preservation.extractAtoms(source).values()];
	const direct = [...preservationMath.extractAtoms(source).values()];
	assert.deepEqual(viaProfile, direct, 'the profile must wire exactly preservation-math.ts, not a divergent copy');
	assert.ok(viaProfile.length > 0, 'the fixture must contain recognizable atoms');
	const { atoms, delta, violations } = await jiti.import(path.join(engine, 'preservation.ts'));
	assert.deepEqual([...atoms(source).values()], direct);
	assert.deepEqual(delta(source, '## S\n\nGone.\n').lost.map(a => a.id), direct.map(a => a.id));
	assert.deepEqual(violations(source), preservationMath.violations(source));
});

test('2.2.3 empty extraction (zero atoms) is reported not-applicable, a distinct shape from a genuine pass with atoms confirmed intact', async () => {
	const { validateCandidate } = await jiti.import(path.join(engine, 'candidate-validator.ts'));
	const mathFreeDoc = '# Title\n\nJust prose, no notation at all.\n';
	const mathFreeState = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(mathFreeDoc));
	const target = mathFreeState.structuralIndex.entries.find(e => e.type === 'paragraph');
	const plan = { planVersion: '2', documentSha256: mathFreeState.documentSha256, intent: 'MODIFY', instructionHash: 'x', resolvedTargets: [target.entryId], semanticChange: false, destructiveIntent: false, cleanupLevel: 'NONE', constraints: [], actions: [{ kind: 'replace', targetEntryId: target.entryId, replacementText: 'Different prose, still no notation.' }], expectedEffects: [], unresolvedQuestions: [] };
	const compiled = v2.compilePatches(mathFreeState, plan);
	const noAtomsValidation = await validateCandidate(mathFreeState, plan, compiled);
	assert.equal(noAtomsValidation.preservationApplicable, false, 'zero atoms extracted from a math-free document must report not-applicable');

	const mathDoc = '# 2 Dynamics\n\n$$\nx_{t+1}=A x_t\n$$\n\nOld dynamics.\n';
	const mathState = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(mathDoc));
	const prose = mathState.structuralIndex.entries.find(e => e.type === 'paragraph');
	const mathPlan = { planVersion: '2', documentSha256: mathState.documentSha256, intent: 'MODIFY', instructionHash: 'x', resolvedTargets: [prose.entryId], semanticChange: false, destructiveIntent: false, cleanupLevel: 'NONE', constraints: [], actions: [{ kind: 'replace', targetEntryId: prose.entryId, replacementText: 'New dynamics, equation untouched.' }], expectedEffects: [], unresolvedQuestions: [] };
	const mathCompiled = v2.compilePatches(mathState, mathPlan);
	const genuinePass = await validateCandidate(mathState, mathPlan, mathCompiled);
	assert.equal(genuinePass.preservationApplicable, true, 'atoms exist in this document -- the check is applicable');
	assert.equal(genuinePass.preservationDelta.lost.length, 0, 'the equation was untouched, so nothing was lost');
});

test('2.2.4 legacy input alias acknowledgedMathRemovals is treated identically to acknowledgedRemovals', async () => {
	const legacy = await previewDroppedEquation();
	const legacyPublished = await legacy.orchestrator.execute({ ...legacy.request, acceptSuccessor: true, successorAcceptanceToken: legacy.preview.acceptanceToken, acknowledgedMathRemovals: legacy.preview.mathDelta.lost.map(a => a.id) });
	assert.equal(legacyPublished.status, 'published', JSON.stringify(legacyPublished));

	const modern = await previewDroppedEquation();
	const modernPublished = await modern.orchestrator.execute({ ...modern.request, acceptSuccessor: true, successorAcceptanceToken: modern.preview.acceptanceToken, acknowledgedRemovals: modern.preview.mathDelta.lost.map(a => a.id) });
	assert.equal(modernPublished.status, 'published', JSON.stringify(modernPublished));
});

test('2.2.5 a preview response includes both mathDelta and preservationDelta, populated identically', async () => {
	const { preview } = await previewDroppedEquation();
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.ok(preview.preservationDelta, 'the preview must carry the new field name');
	assert.deepEqual(preview.preservationDelta, preview.mathDelta, 'both fields must be populated identically');
});

// 2.2.10 -- re-run 2.2.1's exact scenario after the refactor and confirm it is
// byte-identical in behaviour: gate behaviour survives the rename.
test('2.2.10 the 2.2.1 characterization still passes unchanged after the preservation-gate refactor', async () => {
	const { orchestrator, request, preview } = await previewDroppedEquation();
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.ok(preview.mathDelta.lost.length > 0);
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'blocked', JSON.stringify(published));
	assert.equal(published.reason, 'MATH_REMOVALS_NOT_ACKNOWLEDGED');
});
