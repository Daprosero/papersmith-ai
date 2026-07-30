import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
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

const workspace = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/exports.ts'));

test('explicit scientific mode is an explicit global-route discriminant', () => {
	const route = workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Explore an idea.' });
	assert.equal(route.stage, 'SCIENTIFIC_WORKFLOW');
});

test('terminal routes retain lifecycle, direct-document, and CHAT_DELIBERATION precedence', () => {
	assert.equal(workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'withdraw research-concept-r01.md' }).stage, 'LIFECYCLE');
	assert.equal(workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'inserta un párrafo' }).stage, 'DIRECT_DOCUMENT');
	assert.equal(workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'delibera sobre los supuestos' }).stage, 'CHAT_DELIBERATION');
	const scientific = workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Explore an idea.' });
	assert.deepEqual(scientific, { stage: 'SCIENTIFIC_WORKFLOW', bypassedStages: ['LIFECYCLE', 'DIRECT_DOCUMENT', 'CHAT_DELIBERATION', 'DRAFT_MATERIALIZATION', 'MAINTENANCE'] });
});

test('explicit chat mode wins every generic route and established conversations exit only for an explicit edit or maintenance handoff', () => {
	assert.equal(workspace.resolveGlobalRoute({ operation: 'CHAT_DELIBERATION', instruction: 'withdraw research-concept-r01.md' }).stage, 'CHAT_DELIBERATION');
	assert.equal(workspace.resolveGlobalRoute({ operation: 'CHAT_DELIBERATION', instruction: 'inserta una ecuación candidata' }).stage, 'CHAT_DELIBERATION');
	assert.equal(workspace.resolveGlobalRoute({ operation: 'CHAT_DELIBERATION', instruction: 'delibera sobre la infraestructura' }).stage, 'CHAT_DELIBERATION');
	assert.equal(workspace.resolveGlobalRoute({ conversationId: 'chat-session-1', instruction: 'explica las consecuencias de la ecuación candidata' }).stage, 'CHAT_DELIBERATION');
	assert.equal(workspace.resolveGlobalRoute({ conversationId: 'chat-session-1', instruction: 'modifica la ecuación candidata' }).stage, 'DIRECT_DOCUMENT');
	assert.equal(workspace.resolveGlobalRoute({ conversationId: 'chat-session-1', operation: 'MAINTENANCE', instruction: 'run maintenance' }).stage, 'MAINTENANCE');
	assert.deepEqual(workspace.resolveV2ExecutionAuthority('CHAT_DELIBERATION'), { scope: 'CHAT_DELIBERATION', taskDelegation: 'FORBIDDEN', documentAuthority: 'FORBIDDEN', durableState: 'FORBIDDEN', stateIdentifier: 'conversationId', explicitHandoffRequired: false });
	assert.deepEqual(workspace.resolveV2ExecutionAuthority('DIRECT_DOCUMENT'), { scope: 'DOCUMENT_EDIT', taskDelegation: 'LOCAL_ONLY', documentAuthority: 'GUARDED', durableState: 'NOT_APPLICABLE', stateIdentifier: null, explicitHandoffRequired: true });
	assert.deepEqual(workspace.resolveV2ExecutionAuthority('MAINTENANCE'), { scope: 'MAINTENANCE', taskDelegation: 'PERMITTED', documentAuthority: 'FORBIDDEN', durableState: 'NOT_APPLICABLE', stateIdentifier: 'maintenanceTaskId', explicitHandoffRequired: true });
});

test('route-stage and bypass metrics are privacy-safe and terminal routing does not construct scientific components', () => {
	v2.resetRuntimeMetrics();
	const privateMarker = 'private prompt/model output/raw trace/reasoning must never be recorded';
	assert.equal(workspace.resolveGlobalRoute({ operation: 'WITHDRAW_REVISION', instruction: privateMarker }).stage, 'LIFECYCLE');
	assert.equal(workspace.resolveGlobalRoute({ instruction: `inserta un párrafo ${privateMarker}` }).stage, 'DIRECT_DOCUMENT');
	assert.equal(workspace.resolveGlobalRoute({ instruction: `delibera sobre los supuestos ${privateMarker}` }).stage, 'CHAT_DELIBERATION');
	assert.equal(workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: privateMarker }).stage, 'SCIENTIFIC_WORKFLOW');
	assert.equal(workspace.resolveGlobalRoute({ instruction: privateMarker }).stage, 'EXISTING_FALLBACK');

	const metrics = v2.getRuntimeMetrics();
	assert.deepEqual(metrics.routeMetrics, {
		routeSelections: { LIFECYCLE: 1, DIRECT_DOCUMENT: 1, CHAT_DELIBERATION: 1, DRAFT_MATERIALIZATION: 0, MAINTENANCE: 0, SCIENTIFIC_WORKFLOW: 1, EXISTING_FALLBACK: 1 },
		bypassedStageSelections: { LIFECYCLE: 4, DIRECT_DOCUMENT: 3, CHAT_DELIBERATION: 2, DRAFT_MATERIALIZATION: 3, MAINTENANCE: 3, SCIENTIFIC_WORKFLOW: 1, EXISTING_FALLBACK: 0 },
	});
	assert.equal(metrics.totalModelCalls, 0);
	assert.equal(metrics.totalWrites, 0);
	assert.doesNotMatch(JSON.stringify(metrics), /private prompt|model output|raw trace|reasoning|instruction/i);

	metrics.routeMetrics.routeSelections.LIFECYCLE = 99;
	assert.equal(v2.getRuntimeMetrics().routeMetrics.routeSelections.LIFECYCLE, 1);
});

test('scientific workflow remains disabled unless its exact flag is true', () => {
	assert.equal(workspace.scientificWorkflowFeatureEnabled({}), false);
	assert.equal(workspace.scientificWorkflowFeatureEnabled({ PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED: 'false' }), false);
	assert.equal(workspace.scientificWorkflowFeatureEnabled({ PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED: 'true' }), true);
});

test('disabled scientific workflow returns a typed unavailable result without a document fallback', () => {
	const result = workspace.unavailableScientificWorkflowResult();
	assert.deepEqual(result, {
		status: 'unavailable',
		operation: 'SCIENTIFIC_WORKFLOW',
		routeStage: 'SCIENTIFIC_WORKFLOW',
		entryState: null,
		relatedThreads: [],
		candidates: [],
		blockers: [{ code: 'SCIENTIFIC_WORKFLOW_DISABLED', message: 'Persistent scientific workflow is disabled.' }],
		nextAction: 'enable_scientific_workflow',
		auditStatus: 'NOT_RUN',
		selfAuditStatus: 'NOT_RUN',
		metrics: { routeStage: 'SCIENTIFIC_WORKFLOW', bypassedStages: ['LIFECYCLE', 'DIRECT_DOCUMENT', 'CHAT_DELIBERATION', 'DRAFT_MATERIALIZATION'] },
	});
});

test('registered public tool keeps default-off admission exact and delegates enabled scientific requests to the lazy coordinator', async () => {
	const tools = [];
	workspace.default({ registerTool: (tool) => tools.push(tool), on: () => {} });
	const tool = tools.find((candidate) => candidate.name === 'paper_proposal_execute');
	assert.ok(tool);
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
		const disabled = (await tool.execute('scientific-disabled', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'scientific idea' })).details;
		assert.equal(disabled.blockers[0].code, 'SCIENTIFIC_WORKFLOW_DISABLED');
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const enabled = (await tool.execute('scientific-enabled', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'scientific idea' })).details;
		assert.notEqual(enabled.blockers?.[0]?.code, 'SCIENTIFIC_WORKFLOW_NOT_WIRED');
		assert.equal(enabled.operation, 'SCIENTIFIC_WORKFLOW');
		assert.doesNotMatch(JSON.stringify(enabled), /prompt|trace|thought|transcript/i);
	} finally {
		if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
		else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous;
	}
});

test('coordinator uses read-only pre-materialization adapters and fails closed without injected canonical metadata', async () => {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'scientific-runtime-'));
	await mkdir(path.join(projectRoot, 'proposals'));
	try {
		const adapter = new v2.ProposalWorkspaceAdapter(projectRoot, {}, {});
		const runtime = new v2.ScientificWorkflowRuntime(projectRoot, adapter, new v2.ProductionModelRuntime());
		const result = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-a'] });
		assert.equal(result.status, 'blocked');
		assert.equal(result.blockers[0].code, 'CANONICAL_METADATA_UNAVAILABLE');
		assert.equal(result.entryState, 'EMPTY_PROJECT');
		assert.deepEqual(result.relatedThreads, []);
		assert.deepEqual(result.candidates, []);
		assert.equal('events' in result, false);
		assert.equal('paths' in result, false);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});
