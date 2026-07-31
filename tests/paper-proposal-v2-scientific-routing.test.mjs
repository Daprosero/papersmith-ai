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

test('mode-first lock (D1/D2): an open deliberation keeps a keyword-inferred edit/lifecycle follow-up in chat; explicit exits remain honored', () => {
	// Baseline (unaffected by openDeliberation): a bare conversationId + edit verb still leaks to
	// DIRECT_DOCUMENT when the conversation is NOT open -- this is the existing, still-correct fallback.
	assert.equal(workspace.resolveGlobalRoute({ conversationId: 'chat-session-1', instruction: 'modifica la ecuación candidata' }).stage, 'DIRECT_DOCUMENT');
	// D1 fix: the SAME follow-up, while the conversation IS open, stays in chat instead of leaking.
	const locked = workspace.resolveGlobalRoute({ conversationId: 'chat-session-1', instruction: 'modifica la ecuación candidata', openDeliberation: true });
	assert.equal(locked.stage, 'CHAT_DELIBERATION');
	assert.deepEqual(locked.bypassedStages, ['LIFECYCLE', 'DIRECT_DOCUMENT', 'DRAFT_MATERIALIZATION', 'MAINTENANCE', 'SCIENTIFIC_WORKFLOW']);
	// A keyword-inferred lifecycle follow-up (no explicit operation) is locked out the same way.
	assert.equal(workspace.resolveGlobalRoute({ conversationId: 'chat-session-1', instruction: 'restaura la revisión r01', openDeliberation: true }).stage, 'CHAT_DELIBERATION');
	// An explicit lifecycle operation always remains honored, even while open.
	assert.equal(workspace.resolveGlobalRoute({ operation: 'WITHDRAW_REVISION', conversationId: 'chat-session-1', instruction: 'withdraw research-concept-r01.md', openDeliberation: true }).stage, 'LIFECYCLE');
	// Explicit CREATE_SUCCESSOR and MAINTENANCE remain honored escapes while open.
	assert.equal(workspace.resolveGlobalRoute({ operation: 'CREATE_SUCCESSOR', conversationId: 'chat-session-1', instruction: 'modifica la ecuación candidata', openDeliberation: true }).stage, 'DIRECT_DOCUMENT');
	assert.equal(workspace.resolveGlobalRoute({ operation: 'MAINTENANCE', conversationId: 'chat-session-1', instruction: 'run maintenance', openDeliberation: true }).stage, 'MAINTENANCE');
	// Explicit CLOSE_DELIBERATION always routes to the CHAT_DELIBERATION-scoped dispatch, honored while open.
	assert.equal(workspace.resolveGlobalRoute({ operation: 'CLOSE_DELIBERATION', conversationId: 'chat-session-1', instruction: 'irrelevant', openDeliberation: true }).stage, 'CHAT_DELIBERATION');
	// A natural-language CLOSE (task 2.3) is itself the exit action and is honored even while open.
	assert.equal(workspace.resolveGlobalRoute({ conversationId: 'chat-session-1', instruction: 'cierra la deliberación', openDeliberation: true }).stage, 'CHAT_DELIBERATION');
	assert.equal(workspace.resolveGlobalRoute({ conversationId: 'chat-session-1', instruction: 'close the deliberation' }).stage, 'CHAT_DELIBERATION');
	// Re-audit cleanup (issue #5): an explicit typed SCIENTIFIC_WORKFLOW operation is honored while open,
	// exactly like every other explicit typed operation above (WITHDRAW_REVISION, CREATE_SUCCESSOR,
	// MAINTENANCE, CLOSE_DELIBERATION) -- it must never be trapped into CHAT_DELIBERATION by the
	// mode-first gate just because a keyword-inferred instruction would have been.
	assert.equal(workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', conversationId: 'chat-session-1', instruction: 'Explore an idea.', openDeliberation: true }).stage, 'SCIENTIFIC_WORKFLOW');
});

test('re-audit cleanup (issue #5): explicit SCIENTIFIC_WORKFLOW operation ordering is consistent with the other explicit typed operations', () => {
	// Symmetric with the other explicit-operation checks (WITHDRAW_REVISION/RESTORE_WITHDRAWN_REVISION,
	// CREATE_SUCCESSOR, MAINTENANCE, CREATE_INITIAL_REVISION, CLOSE_DELIBERATION): all of them are honored
	// before the openDeliberation gate. Trapping SCIENTIFIC_WORKFLOW alone into chat during an open
	// deliberation was an unintentional asymmetry, not a documented product decision -- so it is now
	// resolved before the gate exactly like its siblings, and its bypassedStages/route metadata are
	// unchanged for the non-open case.
	const open = workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', conversationId: 'chat-session-1', instruction: 'Explore an idea.', openDeliberation: true });
	assert.deepEqual(open, { stage: 'SCIENTIFIC_WORKFLOW', bypassedStages: ['LIFECYCLE', 'DIRECT_DOCUMENT', 'CHAT_DELIBERATION', 'DRAFT_MATERIALIZATION', 'MAINTENANCE'] });
	// Unaffected: the non-open baseline route and its bypassedStages remain exactly as before.
	const closed = workspace.resolveGlobalRoute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Explore an idea.' });
	assert.deepEqual(closed, { stage: 'SCIENTIFIC_WORKFLOW', bypassedStages: ['LIFECYCLE', 'DIRECT_DOCUMENT', 'CHAT_DELIBERATION', 'DRAFT_MATERIALIZATION', 'MAINTENANCE'] });
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
