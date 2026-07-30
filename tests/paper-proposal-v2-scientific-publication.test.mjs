import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { access, mkdtemp, mkdir, readFile } from 'node:fs/promises';
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
const workspaceModule = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/exports.ts'));
const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const metadata = { schemaVersion: 1, title: 'Scientific reasoning proposal', sectionHeading: 'Accepted scientific decisions' };

function event(sequence, eventId, type, threadId, actor, payload, causalEventIds) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:${String(sequence).padStart(2, '0')}:00.000Z`, actor: { kind: actor }, type, threadId, causalEventIds, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}
function assessment(decision = 'APPROVE') {
	return { decision, scientificCoherence: 'Coherent.', scopeCompliance: 'Within scope.', unsupportedClaims: [], referenceRisks: [], notationRisks: [], requiredChanges: [], unresolvedQuestions: [], riskLevel: 'LOW' };
}

async function fixture({ successor = false, reviewerDecision = 'APPROVE', adapter, derivedStore } = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-publication-'));
	await mkdir(path.join(projectRoot, 'proposals'), { recursive: true });
	let source;
	let workspace;
	let guardedAdapter;
	if (successor) {
		const bootstrap = workspaceModule.createProposalWorkspaceTool(projectRoot);
		await bootstrap.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# Existing proposal\n\nStable base.\n' });
		source = await v2.loadDocumentState(projectRoot, 'research-concept-r01.md');
		const guard = workspaceModule.createDocumentOperationGuard(projectRoot);
		workspace = workspaceModule.createProposalWorkspaceTool(projectRoot, { operationGuard: guard });
		guardedAdapter = new v2.ProposalWorkspaceAdapter(projectRoot, guard, workspace, () => 'scientific-successor');
	} else {
		const guard = workspaceModule.createDocumentOperationGuard(projectRoot);
		workspace = workspaceModule.createProposalWorkspaceTool(projectRoot, { operationGuard: guard });
		guardedAdapter = new v2.ProposalWorkspaceAdapter(projectRoot, guard, workspace, () => 'scientific-initial');
	}
	const store = new v2.ScientificStateStore(projectRoot);
	const summary = 'Bounded accepted synthesis.';
	const synthesisDigest = digest({ synthesisId: 'synthesis-a', threadId: 'thread-a', summary });
	const events = [
		event(1, 'created-a', 'THREAD_CREATED', 'thread-a', 'USER', { title: 'Question', summary: 'Public summary.', activeThreadId: 'thread-a' }, []),
		event(2, 'tutor-a', 'TUTOR_ASSESSED', 'thread-a', 'TUTOR', { status: 'DRAFT', summary, synthesisId: 'synthesis-a', synthesisDigest }, ['created-a']),
		event(3, 'review-a', 'CONCEPTUAL_REVIEW_RECORDED', 'thread-a', 'CONCEPTUAL_REVIEWER', { status: 'PASS', synthesisId: 'synthesis-a', synthesisDigest }, ['tutor-a']),
		event(4, 'accepted-a', 'DECISION_ACCEPTED', 'thread-a', 'USER', { decisionId: 'decision-a', synthesisId: 'synthesis-a', synthesisDigest, status: 'ACCEPTED_UNMATERIALIZED' }, ['review-a']),
	];
	const evidence = source && { filename: source.filename, revision: source.revision, documentSha256: source.documentSha256 };
	await store.commitTransition({ events, snapshot: { schemaVersion: 1, activeThreadId: 'thread-a', threads: [{ threadId: 'thread-a', version: 1, status: 'ACCEPTED_UNMATERIALIZED', title: 'Question', summary: 'Public summary.', createdEventId: 'created-a', headEventId: 'accepted-a', ...(evidence ? { revisionEvidence: evidence } : {}), relationIds: [], decisionIds: ['decision-a'] }], relations: [], decisions: [{ decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: synthesisDigest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: ['tutor-a', 'review-a'] }] } });
	const reservation = await store.reserveMaterialization(['decision-a']);
	assert.equal(reservation.status, 'reserved');
	const planned = await new v2.MaterializationPlanner(store).plan({ record: reservation.record, state: await store.read(), ...(source ? { source } : {}), canonicalMetadata: metadata });
	assert.equal(planned.status, 'ready');
	const record = (await store.reserveMaterialization(['decision-a'])).record;
	const calls = [];
	const reviewer = new v2.DocumentReviewerGate({ review: async (input) => { calls.push(input); return assessment(reviewerDecision); } });
	const service = new v2.MaterializationPublicationService({ projectRoot, store, executor: new v2.MaterializationCandidateExecutor(), reviewer, adapter: adapter ?? guardedAdapter, ...(derivedStore ? { derivedStore } : {}) });
	return { projectRoot, store, record, source, service, calls, guardedAdapter };
}

test('Document Reviewer receives the exact frozen candidate and non-pass blocks before guard or proposal writes', async () => {
	const { projectRoot, store, record, service, calls } = await fixture({ reviewerDecision: 'BLOCK' });
	const result = await service.materialize({ record });
	assert.deepEqual(result, { status: 'blocked', code: 'DOCUMENT_REVIEW_BLOCK' });
	assert.equal(calls.length, 1);
	assert.equal(calls[0].plan.candidate.digest, record.plan.digest === calls[0].plan.plan.digest ? calls[0].plan.candidate.digest : 'unreachable');
	await assert.rejects(access(path.join(projectRoot, 'proposals', 'research-concept-r01.md')));
	const state = await store.read();
	assert.equal((await store.reserveMaterialization(['decision-a'])).record.state, 'BLOCKED');
	assert.equal(state.snapshot.decisions[0].state, 'ACCEPTED_UNMATERIALIZED');
});

test('changed candidate invalidates Document Reviewer approval before a guard or write can begin', async () => {
	const { projectRoot, guardedAdapter } = await fixture();
	const original = Buffer.from('# Original\n');
	const changed = Buffer.from('# Changed\n');
	await assert.rejects(guardedAdapter.publishInitial({
		candidate: { filename: 'research-concept-r01.md', revision: 'r01', bytes: changed, digest: createHash('sha256').update(changed).digest('hex') },
		approval: { decision: 'APPROVE', candidateDigest: createHash('sha256').update(original).digest('hex'), planDigest: 'a'.repeat(64) },
	}), /DOCUMENT_REVIEW_APPROVAL_INVALID/);
	await assert.rejects(access(path.join(projectRoot, 'proposals', 'research-concept-r01.md')));
});

test('approved r01 candidate publishes only through INITIAL_CREATE then commits verified derived state, minimal receipt, and provenance', async () => {
	const { projectRoot, store, record, service, calls } = await fixture();
	const result = await service.materialize({ record });
	assert.equal(result.status, 'materialized', JSON.stringify(result));
	assert.equal(result.targetFilename, 'research-concept-r01.md');
	assert.equal(calls.length, 1);
	const bytes = await readFile(path.join(projectRoot, 'proposals', 'research-concept-r01.md'));
	const receipt = JSON.parse(await readFile(path.join(projectRoot, '.paper-proposal/receipts/research-concept-r01.md.json'), 'utf8'));
	assert.equal(receipt.kind, 'INITIAL_PUBLICATION');
	assert.equal(receipt.documentShaAfter, createHash('sha256').update(bytes).digest('hex'));
	const committed = (await store.reserveMaterialization(['decision-a'])).record;
	assert.equal(committed.state, 'COMMITTED');
	assert.equal(committed.commit.targetFilename, 'research-concept-r01.md');
	assert.deepEqual(committed.commit.threadIds, ['thread-a']);
	assert.equal((await store.read()).snapshot.decisions[0].state, 'MATERIALIZED');
});

test('approved successor uses the guarded V2 successor adapter and commits only the reviewed exact bytes', async () => {
	const { projectRoot, store, record, source, service } = await fixture({ successor: true });
	const result = await service.materialize({ record, source });
	assert.equal(result.status, 'materialized', JSON.stringify(result));
	assert.equal(result.targetFilename, 'research-concept-r02.md');
	const bytes = await readFile(path.join(projectRoot, 'proposals', 'research-concept-r02.md'));
	const receipt = JSON.parse(await readFile(path.join(projectRoot, '.paper-proposal/receipts/research-concept-r02.md.json'), 'utf8'));
	assert.equal(receipt.documentShaAfter, createHash('sha256').update(bytes).digest('hex'));
	assert.equal((await store.reserveMaterialization(['decision-a'])).record.state, 'COMMITTED');
});

test('incomplete derived-state or receipt evidence requires recovery after publication and preserves decision eligibility', async () => {
	const adapter = { publishInitial: async ({ candidate }) => {
		const publishedBytes = Buffer.concat([Buffer.from('<!-- proposal-workspace:artifact:v1 -->\n'), candidate.bytes]);
		return { operationId: 'fake-publication', targetFilename: 'research-concept-r01.md', targetRevision: 'r01', publishedSha256: createHash('sha256').update(publishedBytes).digest('hex'), publishedBytes, candidateDigest: candidate.digest, workspaceEvidence: {}, guardEvidence: {} };
	} };
	const derivedStore = { commitDerivedState: async () => undefined, markDerivedState: async () => undefined, saveRevisionReceipt: async () => undefined, loadDerivedState: async () => undefined };
	const { store, record, service } = await fixture({ adapter, derivedStore });
	const result = await service.materialize({ record });
	assert.equal(result.status, 'recovery_required');
	const persisted = (await store.reserveMaterialization(['decision-a'])).record;
	assert.equal(persisted.state, 'RECOVERY_REQUIRED');
	assert.deepEqual(persisted.outcome, {
		code: 'MATERIALIZATION_PUBLICATION_EVIDENCE_INCOMPLETE',
		phaseReached: 'PUBLISHING',
		evidence: ['derived_state:absent'],
		lastValidTransition: 'MATERIALIZATION_DOCUMENT_REVIEWED',
		allowedRecoveryAction: 'reconcile_materialization_evidence',
	});
	assert.equal((await store.read()).snapshot.decisions[0].state, 'ACCEPTED_UNMATERIALIZED');
});

test('recovery-transition persistence failure remains distinct and never claims recovery was recorded', async () => {
	const adapter = { publishInitial: async ({ candidate }) => {
		const publishedBytes = Buffer.concat([Buffer.from('<!-- proposal-workspace:artifact:v1 -->\n'), candidate.bytes]);
		return { operationId: 'fake-publication', targetFilename: 'research-concept-r01.md', targetRevision: 'r01', publishedSha256: createHash('sha256').update(publishedBytes).digest('hex'), publishedBytes, candidateDigest: candidate.digest, workspaceEvidence: {}, guardEvidence: {} };
	} };
	const derivedStore = { commitDerivedState: async () => undefined, markDerivedState: async () => undefined, saveRevisionReceipt: async () => undefined, loadDerivedState: async () => undefined };
	const { store, record, service } = await fixture({ adapter, derivedStore });
	store.recordMaterializationOutcome = async () => ({ status: 'blocked', code: 'INJECTED_RECOVERY_TRANSITION_FAILURE' });
	assert.deepEqual(await service.materialize({ record }), { status: 'recovery_required', code: 'MATERIALIZATION_RECOVERY_TRANSITION_FAILED' });
	assert.equal((await store.reserveMaterialization(['decision-a'])).record.state, 'PUBLISHING');
	assert.equal((await store.read()).snapshot.decisions[0].state, 'ACCEPTED_UNMATERIALIZED');
});

test('pre-commit publication failure stays blocked while ambiguous or incomplete evidence requires recovery and never materializes', async () => {
	for (const [published, expected] of [[false, 'blocked'], [true, 'recovery_required']]) {
		const adapter = { publishInitial: async () => { throw Object.assign(new Error('INJECTED_PUBLICATION_FAILURE'), { published }); } };
		const { store, record, service } = await fixture({ adapter });
		const result = await service.materialize({ record });
		assert.equal(result.status, expected);
		assert.equal((await store.read()).snapshot.decisions[0].state, 'ACCEPTED_UNMATERIALIZED');
	}
});
