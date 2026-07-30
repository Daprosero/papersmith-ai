import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/exports.ts'));

const metadata = { schemaVersion: 1, title: 'Public scientific proposal', sectionHeading: 'Accepted scientific decisions' };
const tutor = () => ({ decision: 'ACCEPT', summary: 'Bounded public scientific synthesis.', mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: [] });
const reviewer = () => ({ decision: 'APPROVE', scientificCoherence: 'Coherent.', scopeCompliance: 'Bounded.', unsupportedClaims: [], referenceRisks: [], notationRisks: [], requiredChanges: [], unresolvedQuestions: [], riskLevel: 'LOW' });

async function fixture({ incompleteEvidence = false, lifecycleV1WorkspaceId } = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-public-'));
	await mkdir(path.join(projectRoot, 'proposals'));
	if (lifecycleV1WorkspaceId) {
		const service = new v2.LifecycleService(projectRoot);
		const base = await service.registerBaseDocument({ workspaceId: lifecycleV1WorkspaceId, requestId: 'register-public-base', baseDocumentId: 'public-base', content: 'Public lifecycle base\n' });
		assert.equal(base.outcome, 'COMMITTED');
		const first = await service.createFromBase({ workspaceId: lifecycleV1WorkspaceId, requestId: 'create-public-r01', operation: 'CREATE_FROM_BASE', revisionId: 'revision-1', locator: 'research-concept-r01.md', source: { sourceKind: 'BASE_DOCUMENT', sourceId: 'public-base', sourceContentHash: base.base.contentHash, baseDocumentId: 'public-base' }, approvedChanges: [] });
		assert.equal(first.outcome, 'COMMITTED');
		const successor = await service.createSuccessor({ workspaceId: lifecycleV1WorkspaceId, requestId: 'create-public-r02', operation: 'CREATE_SUCCESSOR', revisionId: 'revision-2', locator: 'research-concept-r02.md', source: { sourceKind: 'REVISION', sourceId: 'revision-1', sourceContentHash: first.revision.contentHash, baseDocumentId: 'public-base' }, approvedChanges: [] });
		assert.equal(successor.outcome, 'COMMITTED');
	}
	const calls = [];
	let id = 0;
	const extension = workspace.createPaperProposalExtension({
		projectRoot,
		scientificWorkflow: {
			canonicalMetadata: metadata,
			newId: () => `public-${++id}`,
			now: () => new Date('2026-01-01T00:00:00.000Z'),
			roleAdapters: {
				tutor: { assess: async () => { calls.push('Tutor'); return tutor(); } },
				reviewer: { review: async () => { calls.push('Reviewer'); return reviewer(); } },
			},
			...(lifecycleV1WorkspaceId ? { lifecycleV1WorkspaceId } : {}),
			...(incompleteEvidence ? { derivedStore: { commitDerivedState: async () => undefined, markDerivedState: async () => undefined, saveRevisionReceipt: async () => undefined, loadDerivedState: async () => undefined } } : {}),
		},
	});
	const tools = [];
	extension({ registerTool: (tool) => tools.push(tool), on: () => {} });
	const tool = tools.find((candidate) => candidate.name === 'paper_proposal_execute');
	assert.ok(tool, 'registered public tool');
	return { projectRoot, calls, tool, async dispose() { await rm(projectRoot, { recursive: true, force: true }); } };
}

async function invoke(tool, callId, params) {
	const ctx = { model: undefined, sessionManager: { getSessionId: () => 'scientific-public-e2e-session' }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: false, error: 'MODEL_NOT_CONFIGURED' }) } };
	const result = await tool.execute(callId, params, undefined, undefined, ctx);
	return result.details;
}

async function deliberation(run) {
	return invoke(run.tool, 'construct', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Construct an idea about bounded causal inference.', scientificAct: 'CONSTRUCT_IDEA' });
}

async function accepted(run) {
	const initial = await deliberation(run);
	assert.equal(initial.status, 'recorded');
	return invoke(run.tool, 'accept', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Accept this decision.', scientificAct: 'ACCEPT_DECISION', activeThreadId: initial.activeThread.threadId, synthesisId: initial.synthesisId, synthesisDigest: initial.synthesisDigest });
}

async function scientificPaths(projectRoot) {
	try { return (await readdir(path.join(projectRoot, '.paper-proposal/scientific'), { recursive: true })).sort(); } catch { return []; }
}

test('disabled gate returns exact SCIENTIFIC_WORKFLOW_DISABLED without dependency invocation or persistence', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
		const result = await invoke(run.tool, 'disabled', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Construct an idea.', scientificAct: 'CONSTRUCT_IDEA' });
		assert.equal(result.blockers[0].code, 'SCIENTIFIC_WORKFLOW_DISABLED');
		assert.deepEqual(run.calls, []);
		assert.deepEqual(await readdir(run.projectRoot), ['proposals']);
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('public scientific projection rejects private, infrastructure, path, stack, full-document, and unpublished-candidate input without persistence', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	const markers = ['SECRET_PUBLIC_CONFORMANCE_MARKER', '/absolute/private/path', 'Error: stack-frame', 'FULL_DOCUMENT_CONTENT_MARKER', 'ADAPTER_DETAIL_MARKER', 'UNPUBLISHED_CANDIDATE_PAYLOAD_MARKER'];
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const result = await invoke(run.tool, 'unsafe-public-input', { operation: 'SCIENTIFIC_WORKFLOW', instruction: `Construct an idea ${markers.join(' ')}`, scientificAct: 'CONSTRUCT_IDEA' });
		assert.equal(result.status, 'blocked');
		assert.equal(result.blockers[0].code, 'THREAD_SEED_INVALID');
		for (const marker of markers) assert.doesNotMatch(JSON.stringify(result), new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
		assert.deepEqual(await readdir(run.projectRoot), ['proposals']);
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('initial public deliberation routes through Tutor then Reviewer and persists scientific state only', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const result = await deliberation(run);
		assert.equal(result.routeStage, 'SCIENTIFIC_WORKFLOW');
		assert.equal(result.status, 'recorded');
		assert.deepEqual(run.calls, ['Tutor', 'Reviewer']);
		assert.ok(result.synthesisId && /^[0-9a-f]{64}$/.test(result.synthesisDigest));
		assert.deepEqual(await readdir(path.join(run.projectRoot, 'proposals')), []);
		assert.deepEqual(await readdir(path.join(run.projectRoot, '.paper-proposal')), ['scientific']);
		assert.ok(JSON.stringify(result).length < 4096);
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('public MODIFY_SYNTHESIS requires authoritative identity, digest, USER actor semantics, and cause before renewed review', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const initial = await deliberation(run);
		const invalid = await invoke(run.tool, 'modify-invalid', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Modify the synthesis.', scientificAct: 'MODIFY_SYNTHESIS', activeThreadId: initial.activeThread.threadId, synthesisId: 'missing', synthesisDigest: initial.synthesisDigest, modificationCause: 'Clarify.' });
		assert.equal(invalid.blockers[0].code, 'SCIENTIFIC_REVIEWED_SYNTHESIS_REQUIRED');
		const wrongDigest = await invoke(run.tool, 'modify-wrong-digest', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Modify the synthesis.', scientificAct: 'MODIFY_SYNTHESIS', activeThreadId: initial.activeThread.threadId, synthesisId: initial.synthesisId, synthesisDigest: '0'.repeat(64), modificationCause: 'Clarify.' });
		assert.equal(wrongDigest.blockers[0].code, 'SCIENTIFIC_REVIEWED_SYNTHESIS_REQUIRED');
		const missingCause = await invoke(run.tool, 'modify-missing-cause', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Modify the synthesis.', scientificAct: 'MODIFY_SYNTHESIS', activeThreadId: initial.activeThread.threadId, synthesisId: initial.synthesisId, synthesisDigest: initial.synthesisDigest });
		assert.equal(missingCause.blockers[0].code, 'SYNTHESIS_REOPEN_INVALID');
		const forbiddenActor = await invoke(run.tool, 'modify-forbidden-actor', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Modify the synthesis.', scientificAct: 'MODIFY_SYNTHESIS', activeThreadId: initial.activeThread.threadId, synthesisId: initial.synthesisId, synthesisDigest: initial.synthesisDigest, modificationCause: 'Clarify.', actor: { kind: 'TUTOR' } });
		assert.equal(forbiddenActor.blockers[0].code, 'SCIENTIFIC_DECISION_ACTOR_FORBIDDEN');
		const modified = await invoke(run.tool, 'modify', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Modify the synthesis.', scientificAct: 'MODIFY_SYNTHESIS', activeThreadId: initial.activeThread.threadId, synthesisId: initial.synthesisId, synthesisDigest: initial.synthesisDigest, modificationCause: 'Clarify the causal assumption.' });
		assert.equal(modified.status, 'recorded', JSON.stringify(modified));
		assert.notEqual(modified.synthesisId, initial.synthesisId);
		assert.deepEqual(run.calls, ['Tutor', 'Reviewer', 'Tutor', 'Reviewer']);
		assert.deepEqual(await readdir(path.join(run.projectRoot, 'proposals')), []);
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('public ACCEPT_DECISION validates the reviewed causal chain and persists accepted-unmaterialized only', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const initial = await deliberation(run);
		const invalid = await invoke(run.tool, 'accept-invalid', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Accept this decision.', scientificAct: 'ACCEPT_DECISION', activeThreadId: initial.activeThread.threadId, synthesisId: initial.synthesisId, synthesisDigest: '0'.repeat(64) });
		assert.equal(invalid.blockers[0].code, 'SCIENTIFIC_REVIEWED_SYNTHESIS_REQUIRED');
		const result = await invoke(run.tool, 'accept', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Accept this decision.', scientificAct: 'ACCEPT_DECISION', activeThreadId: initial.activeThread.threadId, synthesisId: initial.synthesisId, synthesisDigest: initial.synthesisDigest });
		assert.equal(result.status, 'recorded');
		assert.ok(result.decisionId);
		assert.equal(result.entryState, 'MATERIALIZATION_PENDING');
		assert.deepEqual(await readdir(path.join(run.projectRoot, 'proposals')), []);
		assert.deepEqual(run.calls, ['Tutor', 'Reviewer']);
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('public REQUEST_MATERIALIZATION exercises the frozen plan, review, guarded publication, and public outcome', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const decision = await accepted(run);
		const result = await invoke(run.tool, 'materialize', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Request materialization.', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: [decision.decisionId], idempotencyKey: 'public-materialization-1' });
		assert.equal(result.status, 'materialized', JSON.stringify(result));
		assert.equal(result.materialization.targetFilename, 'research-concept-r01.md');
		assert.deepEqual(run.calls, ['Tutor', 'Reviewer', 'Reviewer']);
		assert.ok(await readFile(path.join(run.projectRoot, 'proposals', 'research-concept-r01.md')));
		assert.ok(await readFile(path.join(run.projectRoot, '.paper-proposal/receipts/research-concept-r01.md.json')));
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('exact public idempotent replay returns one materialization and incompatible selection-key reuse fails closed', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const decision = await accepted(run);
		const request = { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Request materialization.', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: [decision.decisionId], idempotencyKey: 'public-materialization-1' };
		const first = await invoke(run.tool, 'materialize-first', request);
		const replay = await invoke(run.tool, 'materialize-replay', request);
		assert.equal(first.status, 'materialized');
		assert.equal(replay.status, 'materialized');
		assert.equal(replay.materialization.materializationId, first.materialization.materializationId);
		assert.deepEqual(await readdir(path.join(run.projectRoot, 'proposals')), ['research-concept-r01.md']);
		const incompatible = await invoke(run.tool, 'materialize-incompatible', { ...request, candidateIds: ['unknown-decision'] });
		assert.equal(incompatible.status, 'blocked');
		assert.equal(incompatible.blockers[0].code, 'MATERIALIZATION_IDEMPOTENCY_KEY_CONFLICT');
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('controlled incomplete public publication evidence persists recovery and public re-entry never silently retries', async () => {
	const run = await fixture({ incompleteEvidence: true });
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const decision = await accepted(run);
		const failed = await invoke(run.tool, 'materialize-incomplete', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Request materialization.', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: [decision.decisionId] });
		assert.equal(failed.status, 'blocked');
		assert.match(failed.blockers[0].code, /MATERIALIZATION_PUBLICATION_EVIDENCE_INCOMPLETE/);
		const reentry = await invoke(run.tool, 'reentry', { operation: 'SCIENTIFIC_WORKFLOW', instruction: 'Construct another idea.', scientificAct: 'CONSTRUCT_IDEA' });
		assert.equal(reentry.status, 'recovery_required');
		assert.equal(run.calls.filter((call) => call === 'Tutor').length, 1);
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('public lifecycle-v1 withdrawal and restore expose typed bounded transition evidence without legacy publication', async () => {
	const run = await fixture({ lifecycleV1WorkspaceId: 'public-lifecycle-e2e' });
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		const withdrawn = await invoke(run.tool, 'public-lifecycle-withdraw', { operation: 'WITHDRAW_REVISION', instruction: 'withdraw research-concept-r02.md', sourceFilename: 'research-concept-r02.md', idempotencyKey: 'public-lifecycle-withdraw' });
		assert.deepEqual({ status: withdrawn.status, semanticCode: withdrawn.semanticCode ?? null, lifecycleState: withdrawn.lifecycleState, revisionId: withdrawn.revisionId, activeRevisionId: withdrawn.activeRevisionId }, { status: 'withdrawn', semanticCode: null, lifecycleState: 'WITHDRAWN_ONLY', revisionId: 'revision-2', activeRevisionId: null });
		assert.deepEqual(withdrawn.transitionEvidence, { operation: 'WITHDRAW_REVISION', requestId: 'public-lifecycle-withdraw', outcome: 'committed', lifecycleState: 'WITHDRAWN_ONLY', activeRevisionId: null, revisionId: 'revision-2', withdrawalId: withdrawn.withdrawalId });
		assert.match(withdrawn.withdrawalId, /^[0-9a-f-]{36}$/);
		assert.doesNotMatch(JSON.stringify(withdrawn.transitionEvidence), /research-concept|public-lifecycle-e2e|contents\/|withdraw research/i);

		const rejected = await invoke(run.tool, 'public-lifecycle-rejected', { operation: 'RESTORE_WITHDRAWN_REVISION', instruction: 'restore a filename', sourceFilename: 'research-concept-r02.md', idempotencyKey: 'public-lifecycle-rejected' });
		assert.deepEqual({ status: rejected.status, semanticCode: rejected.semanticCode, lifecycleState: rejected.lifecycleState, transitionEvidence: rejected.transitionEvidence }, { status: 'blocked', semanticCode: 'WITHDRAWAL_IDENTITY_NOT_FOUND', lifecycleState: null, transitionEvidence: { operation: 'RESTORE_WITHDRAWN_REVISION', requestId: 'public-lifecycle-rejected', outcome: 'rejected', semanticCode: 'WITHDRAWAL_IDENTITY_NOT_FOUND' } });

		const restored = await invoke(run.tool, 'public-lifecycle-restore', { operation: 'RESTORE_WITHDRAWN_REVISION', instruction: 'restore the withdrawn revision', withdrawalOperationId: withdrawn.withdrawalId, idempotencyKey: 'public-lifecycle-restore' });
		assert.deepEqual({ status: restored.status, lifecycleState: restored.lifecycleState, revisionId: restored.revisionId, activeRevisionId: restored.activeRevisionId }, { status: 'restored', lifecycleState: 'ACTIVE', revisionId: 'revision-2', activeRevisionId: 'revision-2' });
		assert.deepEqual(restored.transitionEvidence, { operation: 'RESTORE_WITHDRAWN_REVISION', requestId: 'public-lifecycle-restore', outcome: 'committed', lifecycleState: 'ACTIVE', activeRevisionId: 'revision-2', revisionId: 'revision-2', withdrawalId: withdrawn.withdrawalId });
		assert.deepEqual(await readdir(path.join(run.projectRoot, 'proposals')), []);
		assert.equal(await scientificPaths(run.projectRoot).then((paths) => paths.filter((entry) => entry.includes('materializations')).length), 0);
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});

test('lifecycle, direct-document, and DELIBERATE public routes preserve their V2 results without scientific runtime construction', async () => {
	const run = await fixture();
	const previous = process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED;
	try {
		process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = 'true';
		for (const [callId, request] of [['lifecycle', { operation: 'WITHDRAW_REVISION', instruction: 'withdraw research-concept-r01.md', sourceFilename: 'research-concept-r01.md' }], ['direct', { instruction: 'inserta un párrafo' }], ['deliberate', { instruction: 'delibera sobre los supuestos' }]]) {
			const result = await invoke(run.tool, callId, request);
			assert.notEqual(result.operation, 'SCIENTIFIC_WORKFLOW');
		}
		
		assert.deepEqual(run.calls, []);
		assert.deepEqual(await scientificPaths(run.projectRoot), []);
	} finally { if (previous === undefined) delete process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED; else process.env.PAPER_PROPOSAL_SCIENTIFIC_WORKFLOW_ENABLED = previous; await run.dispose(); }
});
