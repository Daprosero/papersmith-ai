// The planner-call budget arm of `orchestrator.ts`'s PLANNER_BUDGET_EXCEEDED guard,
// held against an OBSERVED planner-invocation count instead of a derived one.
//
// `publish()` used to read `planned.plannerCalls ?? (planned.plan.semanticChange ? 1 : 0)`.
// No planner-building function ever returned `plannerCalls`, so on every single-target
// path the fallback won -- and the fallback is the SAME expression the allowance is
// derived from (`operation-spec.ts`: `... : (intent==='CONCEPTUAL_REVISION'||semanticChange ? 1 : 0)`).
// The check compared a number to itself. On the multi-target composite path the value
// was worse than tautological: the loop accumulated `planned.plannerCalls ?? 0`, so a
// turn that really invoked the planner once per target reported ZERO planner calls to
// the budget check, to the adapter, and to the caller.
//
// Both tests below count the stub planner's own invocations and require the engine's
// reported number to equal that count. The second one additionally puts the measured
// count OVER the allowance the profile computes for that same turn, so the number the
// guard compares is no longer derivable from the allowance's own inputs.
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
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

const SOURCE = '# 1 Intro\n\nKeep prefix exactly.\n\n# 2 Alpha\n\nOld alpha body.\n\n# 3 Middle\n\nKeep middle exactly.\n\n# 4 Beta\n\nOld beta body.\n\n# 5 Tail\n\nKeep suffix exactly.\n';

async function seed() {
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-planner-measured-'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await workspaceModule.createProposalWorkspaceTool(root).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: SOURCE });
	const guard = workspaceModule.createDocumentOperationGuard(root);
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }), () => 'planner-measured');
	return { root, adapter };
}

// One real planner invocation per resolved target, counted where it actually happens.
function countingPlanner(counter) {
	return { plan: async input => {
		counter.calls++;
		const heading = input.context.fragments[0].text.includes('Alpha') ? '# 2 Alpha Revised' : '# 4 Beta Revised';
		return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: `${heading}\n\nRewritten body.\n\n` }], unresolvedQuestions: [] };
	} };
}

test('a two-target CREATE_SUCCESSOR reports the two planner invocations it actually made', async () => {
	const { root, adapter } = await seed();
	const counter = { calls: 0 };
	const preview = await new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, countingPlanner(counter)).execute({
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Modifica las secciones Alpha y Beta.',
		selectedEntryIds: ['sección Alpha', 'sección Beta'],
	});
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(counter.calls, 2, 'the engine invoked the planner once per resolved target');
	assert.equal(preview.plannerCalls, counter.calls, 'the reported planner count is the observed one, not `semanticChange ? 1 : 0`');
});

test('the planner budget refuses a turn whose measured planner count exceeds its allowance', async () => {
	const { root, adapter } = await seed();
	const counter = { calls: 0 };
	// `deja coherente` resolves cleanupLevel to SEMANTIC (intent-resolver.ts) while
	// `Modifica` keeps the intent MODIFY, so the SAME turn resolves two independent
	// loci -- two real planner calls -- under a profile whose semantic-cleanup branch
	// caps `maxPlannerCalls` at 1 regardless of the target count.
	const result = await new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, countingPlanner(counter)).execute({
		operation: 'CREATE_SUCCESSOR',
		sourceFilename: 'research-concept-r01.md',
		instruction: 'Modifica las secciones Alpha y Beta y deja coherente el texto.',
		selectedEntryIds: ['sección Alpha', 'sección Beta'],
	});
	const allowance = v2.resolveEffectiveOperationProfile({ intent: 'MODIFY', cleanupLevel: 'SEMANTIC', semanticChange: true, successorCompositeTarget: true, successorTargetCount: 2 });
	assert.equal(allowance.maxPlannerCalls, 1, 'the semantic-cleanup branch allows exactly one planner call');
	assert.equal(counter.calls, 2, 'the engine really invoked the planner twice');
	assert.equal(result.status, 'blocked', JSON.stringify(result));
	assert.equal(result.reason, 'PLANNER_BUDGET_EXCEEDED');
	assert.equal(result.plannerCalls, counter.calls, 'the refusal carries the measured count');
	assert.ok(result.plannerCalls > allowance.maxPlannerCalls, 'the guard compared a measured count against a smaller allowance');
	await assert.rejects(readFile(path.join(root, 'proposals/research-concept-r02.md')), { code: 'ENOENT' });
});
