import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
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
const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const revision = { filename: 'research-concept-r01.md', revision: 'r01', documentSha256: 'a'.repeat(64) };

function event(sequence, eventId, type, threadId, actor, payload, causalEventIds) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:${String(sequence).padStart(2, '0')}:00.000Z`, actor: { kind: actor }, type, threadId, causalEventIds, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}

async function fixture({ withRevision = false } = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-scientific-materialization-'));
	const store = new v2.ScientificStateStore(projectRoot);
	const events = [];
	const threads = [];
	const decisions = [];
	for (const id of ['a', 'b', 'c']) {
		const threadId = `thread-${id}`;
		const decisionId = `decision-${id}`;
		const synthesisId = `synthesis-${id}`;
		const summary = `Bounded accepted synthesis ${id}.`;
		const synthesisDigest = digest({ synthesisId, threadId, summary });
		const created = `created-${id}`;
		const tutor = `tutor-${id}`;
		const review = `review-${id}`;
		const accepted = `accepted-${id}`;
		const base = events.length + 1;
		events.push(
			event(base, created, 'THREAD_CREATED', threadId, 'USER', { title: `Question ${id}`, summary: `Public summary ${id}.`, activeThreadId: threadId }, []),
			event(base + 1, tutor, 'TUTOR_ASSESSED', threadId, 'TUTOR', { status: 'DRAFT', summary, synthesisId, synthesisDigest }, [created]),
			event(base + 2, review, 'CONCEPTUAL_REVIEW_RECORDED', threadId, 'CONCEPTUAL_REVIEWER', { status: 'PASS', synthesisId, synthesisDigest }, [tutor]),
			event(base + 3, accepted, 'DECISION_ACCEPTED', threadId, 'USER', { decisionId, synthesisId, synthesisDigest, status: 'ACCEPTED_UNMATERIALIZED' }, [review]),
		);
		threads.push({ threadId, version: 1, status: 'ACCEPTED_UNMATERIALIZED', title: `Question ${id}`, summary: `Public summary ${id}.`, createdEventId: created, headEventId: accepted, ...(withRevision ? { revisionEvidence: revision } : {}), relationIds: [], decisionIds: [decisionId] });
		decisions.push({ decisionId, threadId, acceptedEventId: accepted, acceptedSynthesisDigest: synthesisDigest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: [tutor, review] });
	}
	await store.commitTransition({ events, snapshot: { schemaVersion: 1, activeThreadId: 'thread-a', threads, relations: [], decisions } });
	return { projectRoot, store };
}

test('reservation freezes only explicit sorted unique accepted decisions and exact retries reuse one durable record', async () => {
	const { projectRoot, store } = await fixture();
	assert.deepEqual(await store.reserveMaterialization(['decision-b', 'decision-a']), { status: 'blocked', code: 'MATERIALIZATION_SELECTION_INVALID' });
	assert.deepEqual(await store.reserveMaterialization(['decision-a', 'decision-a']), { status: 'blocked', code: 'MATERIALIZATION_SELECTION_INVALID' });
	assert.deepEqual(await store.reserveMaterialization(['missing']), { status: 'blocked', code: 'MATERIALIZATION_DECISION_UNKNOWN' });
	const reserved = await store.reserveMaterialization(['decision-a', 'decision-b']);
	assert.equal(reserved.status, 'reserved');
	assert.deepEqual(reserved.record.frozenSelection.decisionIds, ['decision-a', 'decision-b']);
	assert.deepEqual(reserved.record.frozenSelection.acceptedEventIds, ['accepted-a', 'accepted-b']);
	const retry = await new v2.ScientificStateStore(projectRoot).reserveMaterialization(['decision-a', 'decision-b']);
	assert.equal(retry.status, 'existing');
	assert.equal(retry.record.materializationId, reserved.record.materializationId);
	assert.deepEqual(await store.reserveMaterialization(['decision-a']), { status: 'conflict', code: 'MATERIALIZATION_SELECTION_CONFLICT', materializationId: reserved.record.materializationId });
	assert.deepEqual(await store.reserveMaterialization(['decision-a', 'decision-b', 'decision-c']), { status: 'conflict', code: 'MATERIALIZATION_SELECTION_CONFLICT', materializationId: reserved.record.materializationId });
	const state = await store.read();
	assert.equal(state.events.at(-1).type, 'MATERIALIZATION_RESERVED');
	const records = await readdir(path.join(projectRoot, '.paper-proposal-v2/scientific/materializations'));
	assert.equal(records.filter((name) => name.endsWith('.json') && name !== 'index.json').length, 1);
});

test('reservation rejects retracted decisions and fails closed for incomplete durable claims', async () => {
	const { projectRoot, store } = await fixture();
	const current = await store.read();
	const snapshot = structuredClone(current.snapshot);
	snapshot.decisions[0].state = 'RETRACTED';
	const eventId = 'retracted-a';
	snapshot.threads[0].headEventId = eventId;
	snapshot.threads[0].status = 'RETRACTED';
	await store.commitTransition({ events: [event(current.events.length + 1, eventId, 'DECISION_RETRACTED', 'thread-a', 'USER', { decisionId: 'decision-a', status: 'RETRACTED' }, ['accepted-a'])], snapshot });
	assert.deepEqual(await store.reserveMaterialization(['decision-a']), { status: 'blocked', code: 'MATERIALIZATION_DECISION_INELIGIBLE' });
	await assert.rejects(() => readFile(path.join(projectRoot, 'proposals', 'research-concept-r01.md')));
});

test('MaterializationPlanner creates an initial plan from exact frozen provenance without unrelated claims', async () => {
	const { store } = await fixture();
	const reservation = await store.reserveMaterialization(['decision-a']);
	assert.equal(reservation.status, 'reserved');
	const result = new v2.MaterializationPlanner().plan({ record: reservation.record, state: await store.read() });
	assert.equal(result.status, 'ready');
	assert.equal(result.plan.kind, 'CREATE_R01');
	assert.deepEqual(result.plan.frozenSelection.decisionIds, ['decision-a']);
	assert.deepEqual(result.plan.claims.map((claim) => [claim.decisionId, claim.acceptedEventId, claim.threadId]), [['decision-a', 'accepted-a', 'thread-a']]);
	assert.equal(result.plan.claims[0].summary, 'Bounded accepted synthesis a.');
	assert.deepEqual(new v2.MaterializationPlanner().plan({ record: reservation.record, state: await store.read(), source: revision }), { status: 'blocked', code: 'MATERIALIZATION_SOURCE_MISMATCH' });
});

test('MaterializationPlanner requires exact frozen source and claim provenance for successors', async () => {
	const { store } = await fixture({ withRevision: true });
	const reservation = await store.reserveMaterialization(['decision-a']);
	assert.equal(reservation.status, 'reserved');
	const planner = new v2.MaterializationPlanner();
	const state = await store.read();
	const planned = planner.plan({ record: reservation.record, state, source: revision });
	assert.equal(planned.status, 'ready');
	assert.equal(planned.plan.kind, 'CREATE_SUCCESSOR');
	assert.deepEqual(planned.plan.source, revision);
	assert.deepEqual(planner.plan({ record: reservation.record, state, source: { ...revision, documentSha256: 'b'.repeat(64) } }), { status: 'blocked', code: 'MATERIALIZATION_SOURCE_MISMATCH' });
	const unmapped = structuredClone(state);
	delete unmapped.events.find((item) => item.eventId === 'tutor-a').payload.summary;
	assert.deepEqual(planner.plan({ record: reservation.record, state: unmapped, source: revision }), { status: 'blocked', code: 'MATERIALIZATION_CLAIM_UNMAPPED' });
	assert.deepEqual(planner.plan({ record: reservation.record, state, source: revision, maxClaims: 0 }), { status: 'blocked', code: 'MATERIALIZATION_PLAN_BUDGET_INVALID' });
});

test('materialization modules retain no candidate execution, review, guard, or publication authority', async () => {
	const planner = await readFile(path.join(root, '.pi/extensions/paper-proposal-v2/materialization-planner.ts'), 'utf8');
	assert.match(planner, /scientific-domain\.js/);
	assert.doesNotMatch(planner, /(?:writeFile|mkdir|rename|publish(?:Initial|Successor)?|ProposalWorkspaceAdapter|MaterializationCandidateExecutor|DocumentReviewer|compilePatches|validateCandidate)/);
});
