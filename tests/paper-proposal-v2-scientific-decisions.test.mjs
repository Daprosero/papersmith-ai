import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir } from 'node:fs/promises';
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
const v2 = await jiti.import(path.join(root, '.pi/extensions/paper-proposal-v2/exports.ts'));

const tutor = (summary = 'Bounded candidate synthesis.') => ({ decision: 'ACCEPT', summary, mathematicalIssues: [], notationIssues: [], assumptionIssues: [], requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: [] });
const review = () => ({ decision: 'APPROVE', scientificCoherence: 'Coherent within selected scientific context.', scopeCompliance: 'Bounded scope.', unsupportedClaims: [], referenceRisks: [], notationRisks: [], requiredChanges: [], unresolvedQuestions: [], riskLevel: 'LOW' });
const inventory = { read: async () => ({ status: 'valid', activeRevisions: [], withdrawnRevisions: [], auditEvidence: ['revision-inventory:validated'] }) };

async function fixture({ tutorResults = [tutor()], reviewerResults = [review()] } = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-scientific-decisions-'));
	const store = new v2.ScientificStateStore(projectRoot);
	const event = { schemaVersion: 1, eventId: 'thread-created', sequence: 1, occurredAt: '2026-01-01T00:00:00.000Z', actor: { kind: 'USER' }, type: 'THREAD_CREATED', threadId: 'thread-1', causalEventIds: [], payload: { title: 'Bounded question', summary: 'Public thread summary.', activeThreadId: 'thread-1' }, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
	const thread = { threadId: 'thread-1', version: 1, status: 'OPEN', title: 'Bounded question', summary: 'Public thread summary.', createdEventId: 'thread-created', headEventId: 'thread-created', relationIds: [], decisionIds: [] };
	await store.commitTransition({ events: [event], snapshot: { schemaVersion: 1, activeThreadId: 'thread-1', threads: [thread], relations: [], decisions: [] } });
	let id = 0;
	const service = new v2.ScientificWorkflowService({
		store,
		contextBuilder: { build: async (input) => ({ schemaVersion: 1, act: input.act, activeThread: { threadId: input.activeThread.threadId, status: input.activeThread.status, title: input.activeThread.title, summary: input.activeThread.summary }, relatedThreads: [], evidence: [], documentFragments: [], limits: { maxRelatedThreads: 4, maxEvidence: 12, maxDocumentFragments: 4, maxBytes: 16000 }, byteCount: 128, privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } }) },
		tutor: { assess: async () => tutorResults.shift() },
		reviewer: { review: async () => reviewerResults.shift() },
		newId: () => `event-${++id}`,
		now: () => new Date('2026-01-02T00:00:00.000Z'),
	});
	const input = { activeThread: thread, requestedDirectRelationIds: [], act: 'SYNTHESIZE', instruction: 'Synthesize this bounded scientific question.' };
	return { projectRoot, store, service, input };
}

async function reviewed(run) {
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed');
	return result.candidate;
}

test('ScientificWorkflowService accepts only the exact reviewer-passed synthesis as an immutable user decision', async () => {
	const run = await fixture();
	const candidate = await reviewed(run);
	assert.deepEqual(await run.service.acceptDecision({ candidate, actor: { kind: 'SYSTEM' } }), { status: 'blocked', code: 'SCIENTIFIC_ACCEPTANCE_REQUIRES_USER' });
	assert.deepEqual(await run.service.acceptDecision({ candidate: { ...candidate, digest: '0'.repeat(64) }, actor: { kind: 'USER' } }), { status: 'blocked', code: 'SCIENTIFIC_REVIEWED_SYNTHESIS_REQUIRED' });
	assert.deepEqual(await run.service.acceptDecision({ candidate: { ...candidate, reviewEventId: 'missing-review-pass' }, actor: { kind: 'USER' } }), { status: 'blocked', code: 'SCIENTIFIC_REVIEWED_SYNTHESIS_REQUIRED' });
	const accepted = await run.service.acceptDecision({ candidate, actor: { kind: 'USER' } });
	assert.equal(accepted.status, 'recorded');
	assert.equal(accepted.state, 'ACCEPTED_UNMATERIALIZED');
	const state = await run.store.read();
	assert.deepEqual(state.snapshot.decisions, [{ decisionId: accepted.decisionId, threadId: 'thread-1', acceptedEventId: accepted.eventId, acceptedSynthesisDigest: candidate.digest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: [candidate.tutorEventId, candidate.reviewEventId] }]);
	assert.equal(state.snapshot.threads[0].status, 'ACCEPTED_UNMATERIALIZED');
	assert.deepEqual(state.events.map((event) => event.type), ['THREAD_CREATED', 'TUTOR_ASSESSED', 'CONCEPTUAL_REVIEW_RECORDED', 'DECISION_ACCEPTED']);
	assert.deepEqual(await readdir(run.projectRoot), ['.paper-proposal-v2']);
	await assert.rejects(() => readFile(path.join(run.projectRoot, 'proposals', 'research-concept-r01.md')));
});

test('ScientificWorkflowService persists immutable rejection without making a candidate eligible', async () => {
	const run = await fixture();
	const candidate = await reviewed(run);
	assert.deepEqual(await run.service.rejectDecision({ candidate, actor: { kind: 'PLANNER' } }), { status: 'blocked', code: 'SCIENTIFIC_DECISION_ACTOR_FORBIDDEN' });
	const rejected = await run.service.rejectDecision({ candidate, actor: { kind: 'USER' } });
	assert.equal(rejected.status, 'recorded');
	assert.equal(rejected.state, 'REJECTED');
	const state = await run.store.read();
	assert.equal(state.snapshot.decisions.length, 0);
	assert.equal(state.snapshot.threads[0].status, 'REJECTED');
	assert.deepEqual(state.events.slice(-1)[0].payload, { synthesisId: candidate.synthesisId, synthesisDigest: candidate.digest, status: 'REJECTED' });
});

test('ScientificWorkflowService retracts accepted decisions and preserves immutable acceptance history', async () => {
	const run = await fixture({ tutorResults: [tutor('Original synthesis.'), tutor('Modified synthesis.')], reviewerResults: [review(), review()] });
	const candidate = await reviewed(run);
	const accepted = await run.service.acceptDecision({ candidate, actor: { kind: 'USER' } });
	const before = await run.store.read();
	assert.deepEqual(await run.service.retractDecision({ decisionId: accepted.decisionId, actor: { kind: 'DOCUMENT_REVIEWER' } }), { status: 'blocked', code: 'SCIENTIFIC_DECISION_ACTOR_FORBIDDEN' });
	const retracted = await run.service.retractDecision({ decisionId: accepted.decisionId, actor: { kind: 'USER' } });
	assert.equal(retracted.state, 'RETRACTED');
	const afterRetraction = await run.store.read();
	assert.deepEqual(afterRetraction.events.slice(0, before.events.length), before.events);
	assert.equal(afterRetraction.snapshot.decisions[0].state, 'RETRACTED');
	assert.equal(afterRetraction.snapshot.threads[0].status, 'RETRACTED');
	const modified = await run.service.modifySynthesis({ ...run.input, priorSynthesis: candidate, modificationCause: 'Clarify the causal assumption.', actor: { kind: 'USER' } });
	assert.equal(modified.status, 'reviewed');
	assert.equal((await run.store.read()).snapshot.threads[0].status, 'UNDER_REVIEW');
});

test('ProjectEntryResolver and workflow re-entry expose only durable eligible pending candidates', async () => {
	const run = await fixture();
	const candidate = await reviewed(run);
	const accepted = await run.service.acceptDecision({ candidate, actor: { kind: 'USER' } });
	const entry = await new v2.ProjectEntryResolver(inventory, run.store).resolve();
	assert.equal(entry.state, 'MATERIALIZATION_PENDING');
	assert.deepEqual(entry.pendingCandidateIds, [accepted.decisionId]);
	assert.deepEqual(entry.pendingCandidates, [{ decisionId: accepted.decisionId, threadId: 'thread-1', state: 'ACCEPTED_UNMATERIALIZED', eligibility: 'eligible', blockers: [] }]);
	assert.deepEqual(entry.activeThread, { threadId: 'thread-1', status: 'ACCEPTED_UNMATERIALIZED', title: 'Bounded question', summary: 'Public thread summary.' });
	assert.equal(entry.nextAction, 'request_materialization_with_explicit_candidate_ids');
	const publicResult = run.service.projectReentry(entry);
	assert.equal(publicResult.status, 'ready');
	assert.deepEqual(publicResult.candidates, entry.pendingCandidates);
	assert.equal(publicResult.nextAction, entry.nextAction);
	const restartedEntry = await new v2.ProjectEntryResolver(inventory, new v2.ScientificStateStore(run.projectRoot)).resolve();
	assert.deepEqual(restartedEntry.pendingCandidates, entry.pendingCandidates);
	await run.service.retractDecision({ decisionId: accepted.decisionId, actor: { kind: 'USER' } });
	const retractedEntry = await new v2.ProjectEntryResolver(inventory, run.store).resolve();
	assert.equal(retractedEntry.state, 'SCIENTIFIC_ONLY');
	assert.deepEqual(retractedEntry.pendingCandidateIds, []);
	const blocked = run.service.projectReentry({ state: 'INCONSISTENT_PROJECT', relatedThreadIds: [], pendingCandidateIds: [], recovery: { required: true, code: 'SCIENTIFIC_TRANSACTION_INCOMPLETE', action: 'reconcile_scientific_state' }, auditEvidence: [] });
	assert.equal(blocked.status, 'recovery_required');
	assert.deepEqual(blocked.blockers, [{ code: 'SCIENTIFIC_TRANSACTION_INCOMPLETE', message: 'Scientific state requires recovery.', nextAction: 'reconcile_scientific_state' }]);
});

test('Scientific decision lifecycle imports canonical contracts and does not start materialization or publication', async () => {
	const source = await readFile(path.join(root, '.pi/extensions/paper-proposal-v2/scientific-workflow-service.ts'), 'utf8');
	assert.match(source, /scientific-domain\.js/);
	assert.doesNotMatch(source, /(?:ProposalWorkspaceAdapter|publishInitial|publishSuccessor|createInitialProposal|MATERIALIZATION_RESERVED|MATERIALIZATION_COMMITTED|MaterializationCandidateExecutor)/);
});
