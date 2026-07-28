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
const review = (decision = 'APPROVE', changes = []) => ({ decision, scientificCoherence: 'Coherent within selected scientific context.', scopeCompliance: 'Bounded scope.', unsupportedClaims: [], referenceRisks: [], notationRisks: [], requiredChanges: changes, unresolvedQuestions: [], riskLevel: 'LOW' });

async function fixture({ tutorResults = [tutor()], reviewerResults = [review()], contextFails = false } = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-scientific-synthesis-'));
	const store = new v2.ScientificStateStore(projectRoot);
	const initialEvent = { schemaVersion: 1, eventId: 'thread-created', sequence: 1, occurredAt: '2026-01-01T00:00:00.000Z', actor: { kind: 'USER' }, type: 'THREAD_CREATED', threadId: 'thread-1', causalEventIds: [], payload: { title: 'Bounded question', summary: 'Public thread summary.', activeThreadId: 'thread-1' }, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
	const thread = { threadId: 'thread-1', version: 1, status: 'OPEN', title: 'Bounded question', summary: 'Public thread summary.', createdEventId: 'thread-created', headEventId: 'thread-created', relationIds: [], decisionIds: [] };
	await store.commitTransition({ events: [initialEvent], snapshot: { schemaVersion: 1, activeThreadId: 'thread-1', threads: [thread], relations: [], decisions: [] } });
	const calls = [];
	let id = 0;
	const service = new v2.ScientificWorkflowService({
		store,
		contextBuilder: { build: async (input) => {
			calls.push('context');
			if (contextFails) throw new Error('context unavailable');
			return { schemaVersion: 1, act: input.act, activeThread: { threadId: input.activeThread.threadId, status: input.activeThread.status, title: input.activeThread.title, summary: input.activeThread.summary }, relatedThreads: [], evidence: [], documentFragments: [], limits: { maxRelatedThreads: 4, maxEvidence: 12, maxDocumentFragments: 4, maxBytes: 16000 }, byteCount: 128, privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
		} },
		tutor: { assess: async (input) => { calls.push(['tutor', input.instruction]); return tutorResults.shift(); } },
		reviewer: { review: async (input) => { calls.push(['reviewer', input.plan.digest]); return reviewerResults.shift(); } },
		newId: () => `event-${++id}`,
		now: () => new Date('2026-01-02T00:00:00.000Z'),
	});
	const input = { activeThread: thread, requestedDirectRelationIds: [], act: 'SYNTHESIZE', instruction: 'Synthesize this bounded scientific question.' };
	return { projectRoot, store, service, input, calls, thread };
}

test('ScientificWorkflowService runs Tutor then Conceptual Reviewer, persists only advisory events, and grants neither role authority', async () => {
	const run = await fixture();
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed');
	assert.deepEqual(run.calls.filter((call) => Array.isArray(call)).map(([role]) => role), ['tutor', 'reviewer']);
	const state = await run.store.read();
	assert.deepEqual(state.events.map((event) => event.type), ['THREAD_CREATED', 'TUTOR_ASSESSED', 'CONCEPTUAL_REVIEW_RECORDED']);
	assert.equal(state.snapshot.decisions.length, 0);
	assert.equal(state.events.some((event) => /publish|materiali[sz]|plan/i.test(JSON.stringify(event.payload))), false);
	assert.deepEqual(await readdir(run.projectRoot), ['.paper-proposal-v2']);
	await assert.rejects(() => readFile(path.join(run.projectRoot, 'proposals', 'research-concept-r01.md')));
});

test('ScientificWorkflowService rejects invalid or authority-bearing role output without accepting a decision', async () => {
	const run = await fixture({ tutorResults: [{ ...tutor(), publish: true }] });
	const result = await run.service.synthesize(run.input);
	assert.deepEqual(result, { status: 'blocked', code: 'TUTOR_ASSESSMENT_INVALID', eventIds: ['thread-created'] });
	assert.deepEqual((await run.store.read()).events.map((event) => event.type), ['THREAD_CREATED']);
	const unavailable = new v2.ScientificWorkflowService({ store: run.store, contextBuilder: { build: async () => { throw new Error('must not build without adapters'); } } });
	assert.deepEqual(await unavailable.synthesize(run.input), { status: 'blocked', code: 'TUTOR_UNAVAILABLE', eventIds: [] });
	const badCritique = await fixture({ reviewerResults: [review('APPROVE_WITH_CHANGES')] });
	assert.equal((await badCritique.service.synthesize(badCritique.input)).code, 'CONCEPTUAL_CRITIQUE_INVALID');
	const missingContext = await fixture({ contextFails: true });
	assert.deepEqual(await missingContext.service.synthesize(missingContext.input), { status: 'blocked', code: 'SCIENTIFIC_CONTEXT_UNAVAILABLE', eventIds: [] });
});

test('ScientificWorkflowService repairs structured findings through Tutor and rechecks them with a two-cycle bound', async () => {
	const repaired = await fixture({ tutorResults: [tutor('Initial candidate.'), tutor('Repaired candidate.')], reviewerResults: [review('APPROVE_WITH_CHANGES', ['Correct the unsupported assumption.']), review()] });
	const pass = await repaired.service.synthesize(repaired.input);
	assert.equal(pass.status, 'reviewed');
	assert.deepEqual(repaired.calls.filter((call) => Array.isArray(call)).map(([role]) => role), ['tutor', 'reviewer', 'tutor', 'reviewer']);
	assert.match(repaired.calls.filter((call) => Array.isArray(call) && call[0] === 'tutor')[1][1], /findingId|candidateSynthesisDigest|requiredCorrection/);
	const types = (await repaired.store.read()).events.map((event) => event.type);
	assert.deepEqual(types, ['THREAD_CREATED', 'TUTOR_ASSESSED', 'CONCEPTUAL_REVIEW_RECORDED', 'REPAIR_PROPOSED', 'TUTOR_ASSESSED', 'CONCEPTUAL_REVIEW_RECORDED']);
	const exhausted = await fixture({ tutorResults: [tutor('One'), tutor('Two'), tutor('Three')], reviewerResults: [review('APPROVE_WITH_CHANGES', ['Repair one.']), review('APPROVE_WITH_CHANGES', ['Repair two.']), review('APPROVE_WITH_CHANGES', ['Repair three.'])] });
	const stop = await exhausted.service.synthesize(exhausted.input);
	assert.equal(stop.status, 'blocked');
	assert.equal(stop.code, 'REPAIR_LOOP_EXHAUSTED');
	assert.equal(exhausted.calls.filter((call) => Array.isArray(call) && call[0] === 'tutor').length, 3);
	assert.equal((await exhausted.store.read()).snapshot.decisions.length, 0);
});

test('ScientificWorkflowService reopens immutable synthesis history and requires a fresh Tutor then Reviewer sequence', async () => {
	const run = await fixture({ tutorResults: [tutor('Original candidate.'), tutor('Modified candidate.')], reviewerResults: [review(), review()] });
	const original = await run.service.synthesize(run.input);
	assert.equal(original.status, 'reviewed');
	const before = await run.store.read();
	const reopened = await run.service.reopen({ ...run.input, priorSynthesis: original.candidate, modificationCause: 'Clarify the causal assumption.' });
	assert.equal(reopened.status, 'reviewed');
	assert.notEqual(reopened.candidate.synthesisId, original.candidate.synthesisId);
	const after = await run.store.read();
	assert.deepEqual(after.events.slice(0, before.events.length), before.events);
	assert.deepEqual(after.events.slice(-3).map((event) => event.type), ['SYNTHESIS_REOPENED', 'TUTOR_ASSESSED', 'CONCEPTUAL_REVIEW_RECORDED']);
	assert.deepEqual(after.snapshot.decisions, []);
	assert.deepEqual(run.calls.filter((call) => Array.isArray(call)).map(([role]) => role), ['tutor', 'reviewer', 'tutor', 'reviewer']);
});

test('Scientific synthesis orchestration imports canonical contracts and has no document, lifecycle, or materialization authority', async () => {
	const source = await readFile(path.join(root, '.pi/extensions/paper-proposal-v2/scientific-workflow-service.ts'), 'utf8');
	assert.match(source, /scientific-domain\.js/);
	assert.match(source, /ProductionModelRuntime/);
	assert.doesNotMatch(source, /(?:writeFile|ProposalWorkspaceAdapter|publishInitial|publishSuccessor|createInitialProposal|MATERIALIZATION_COMMITTED)/);
});
