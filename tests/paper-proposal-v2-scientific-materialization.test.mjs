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
const canonicalMetadata = { schemaVersion: 1, title: 'Scientific reasoning proposal', sectionHeading: 'Accepted scientific decisions' };

function event(sequence, eventId, type, threadId, actor, payload, causalEventIds) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:${String(sequence).padStart(2, '0')}:00.000Z`, actor: { kind: actor }, type, threadId, causalEventIds, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}

async function fixture({ withRevision = false, revisionEvidence = revision } = {}) {
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
		threads.push({ threadId, version: 1, status: 'ACCEPTED_UNMATERIALIZED', title: `Question ${id}`, summary: `Public summary ${id}.`, createdEventId: created, headEventId: accepted, ...(withRevision ? { revisionEvidence } : {}), relationIds: [], decisionIds: [decisionId] });
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
	const planner = new v2.MaterializationPlanner(store);
	const result = await planner.plan({ record: reservation.record, state: await store.read(), canonicalMetadata });
	assert.equal(result.status, 'ready');
	assert.equal(result.plan.operation, 'CREATE_R01');
	assert.deepEqual(result.plan.frozenSelection.decisionIds, ['decision-a']);
	assert.deepEqual(result.plan.claimProvenance.map((claim) => [claim.decisionId, claim.acceptedEventId, claim.threadId]), [['decision-a', 'accepted-a', 'thread-a']]);
	assert.equal(result.plan.claimProvenance[0].summary, 'Bounded accepted synthesis a.');
	assert.equal(result.plan.payload.markdown.includes('Bounded accepted synthesis a.'), true);
	assert.deepEqual(result.plan.payload.target, { filename: 'research-concept-r01.md', revision: 'r01' });
	assert.equal((await store.reserveMaterialization(['decision-a'])).record.plan.digest, result.plan.digest);
	assert.deepEqual(await planner.plan({ record: reservation.record, state: await store.read(), source: revision, canonicalMetadata }), { status: 'blocked', code: 'MATERIALIZATION_SOURCE_MISMATCH' });
});

test('MaterializationPlanner requires exact frozen source and claim provenance for successors', async () => {
	const base = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Existing proposal\n\nStable base.\n'));
	const source = { filename: base.filename, revision: base.revision, documentSha256: base.documentSha256 };
	const { store } = await fixture({ withRevision: true, revisionEvidence: source });
	const reservation = await store.reserveMaterialization(['decision-a']);
	assert.equal(reservation.status, 'reserved');
	const planner = new v2.MaterializationPlanner(store);
	const state = await store.read();
	const planned = await planner.plan({ record: reservation.record, state, source: base, canonicalMetadata });
	assert.equal(planned.status, 'ready');
	assert.equal(planned.plan.operation, 'CREATE_SUCCESSOR');
	assert.deepEqual(planned.plan.expectedRevisionIdentity, source);
	assert.deepEqual(planned.plan.payload.expectedBase, source);
	assert.equal(planned.plan.payload.patches.length, 1);
	assert.deepEqual(planned.plan.payload.patches.map((patch) => patch.order), [1]);
	assert.equal(planned.plan.payload.patches[0].plan.documentSha256, base.documentSha256);
	assert.equal(planned.plan.payload.patches[0].preconditions.anchorTextSha256.length, 64);
	assert.deepEqual(await planner.plan({ record: reservation.record, state, source: await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Changed\n')), canonicalMetadata }), { status: 'blocked', code: 'MATERIALIZATION_SOURCE_MISMATCH' });
	const unmapped = structuredClone(state);
	delete unmapped.events.find((item) => item.eventId === 'tutor-a').payload.summary;
	assert.deepEqual(await planner.plan({ record: reservation.record, state: unmapped, source: base, canonicalMetadata }), { status: 'blocked', code: 'MATERIALIZATION_CLAIM_UNMAPPED' });
	assert.deepEqual(await planner.plan({ record: reservation.record, state, source: base, canonicalMetadata, maxClaims: 0 }), { status: 'blocked', code: 'MATERIALIZATION_PLAN_BUDGET_INVALID' });
});

test('identical frozen inputs produce identical executable payloads before persistence', async () => {
	const source = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Existing proposal\n\nStable base.\n'));
	const evidence = { filename: source.filename, revision: source.revision, documentSha256: source.documentSha256 };
	const first = await fixture({ withRevision: true, revisionEvidence: evidence });
	const second = await fixture({ withRevision: true, revisionEvidence: evidence });
	const firstReservation = await first.store.reserveMaterialization(['decision-a']);
	const secondReservation = await second.store.reserveMaterialization(['decision-a']);
	assert.equal(firstReservation.status, 'reserved');
	assert.equal(secondReservation.status, 'reserved');
	const firstPlan = await new v2.MaterializationPlanner(first.store).plan({ record: firstReservation.record, state: await first.store.read(), source, canonicalMetadata });
	const secondPlan = await new v2.MaterializationPlanner(second.store).plan({ record: secondReservation.record, state: await second.store.read(), source, canonicalMetadata });
	assert.equal(firstPlan.status, 'ready');
	assert.equal(secondPlan.status, 'ready');
	assert.deepEqual(firstPlan.plan.payload, secondPlan.plan.payload);
});

test('materialization modules retain no candidate execution, review, guard, or publication authority', async () => {
	const planner = await readFile(path.join(root, '.pi/extensions/paper-proposal-v2/materialization-planner.ts'), 'utf8');
	assert.match(planner, /scientific-domain\.js/);
	assert.doesNotMatch(planner, /(?:writeFile|mkdir|rename|publish(?:Initial|Successor)?|ProposalWorkspaceAdapter|MaterializationCandidateExecutor|DocumentReviewer|compilePatches|validateCandidate)/);
});

test('unregistered lifecycle-v1 scientific materialization fails closed without legacy publication', async () => {
	const { projectRoot } = await fixture();
	const runtime = new v2.ScientificWorkflowRuntime(projectRoot, {}, {}, { lifecycleV1WorkspaceId: 'unregistered-workspace' });
	const result = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for unregistered base', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-a'] });
	assert.equal(result.status, 'blocked');
	assert.equal(result.blockers[0].code, 'BASE_DOCUMENT_NOT_REGISTERED');
	await assert.rejects(() => readFile(path.join(projectRoot, 'proposals', 'research-concept-r01.md')));
});

test('a fresh lifecycle-v1 runtime blocks a withdrawn-only workspace before reserving another materialization', async () => {
	const { projectRoot } = await fixture();
	const lifecycle = new v2.LifecycleService(projectRoot);
	const registered = await lifecycle.registerBaseDocument({ workspaceId: 'workspace-v1', requestId: 'register-base', baseDocumentId: 'base-v1', content: '# Registered base\n\nUnchanged theorem.\n' });
	assert.equal(registered.outcome, 'COMMITTED');
	const firstRuntime = new v2.ScientificWorkflowRuntime(projectRoot, {}, {}, { lifecycleV1WorkspaceId: 'workspace-v1' });
	const first = await firstRuntime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for approved base revision', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-a'] });
	const successor = await firstRuntime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for approved successor', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-b'] });
	assert.equal(first.status, 'materialized');
	assert.equal(successor.status, 'materialized');
	const withdrawal = await lifecycle.withdrawRevision({ workspaceId: 'workspace-v1', requestId: 'withdraw-successor', revisionId: successor.materialization.targetRevision });
	assert.equal(withdrawal.outcome, 'COMMITTED');
	const recordsPath = path.join(projectRoot, '.paper-proposal-v2', 'scientific', 'materializations');
	const before = await readdir(recordsPath);
	const restarted = new v2.ScientificWorkflowRuntime(projectRoot, {}, {}, { lifecycleV1WorkspaceId: 'workspace-v1' });
	const blocked = await restarted.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for approved withdrawn lifecycle revision', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-c'] });
	assert.deepEqual({ status: blocked.status, code: blocked.blockers?.[0]?.code, nextAction: blocked.nextAction }, { status: 'blocked', code: 'ACTIVE_REVISION_NOT_FOUND', nextAction: 'reconcile_lifecycle_inventory' });
	assert.equal((await lifecycle.rebuildLifecycleInventory('workspace-v1')).lifecycleState, 'WITHDRAWN_ONLY');
	assert.deepEqual(await readdir(recordsPath), before);
	await assert.rejects(() => readFile(path.join(projectRoot, 'proposals', 'research-concept-r03.md')));
});

test('registered lifecycle-v1 scientific materialization publishes only lifecycle-owned base and successor revisions', async () => {
	const { projectRoot } = await fixture();
	const lifecycle = new v2.LifecycleService(projectRoot);
	const base = '# Registered base\n\nUnchanged theorem.\n';
	const registered = await lifecycle.registerBaseDocument({ workspaceId: 'workspace-v1', requestId: 'register-base', baseDocumentId: 'base-v1', content: base });
	assert.equal(registered.outcome, 'COMMITTED');
	const runtime = new v2.ScientificWorkflowRuntime(projectRoot, {}, {}, { lifecycleV1WorkspaceId: 'workspace-v1' });
	const first = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for approved base revision', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-a'] });
	assert.equal(first.status, 'materialized', JSON.stringify(first));
	assert.match(first.materialization.targetFilename, /^lifecycle-v1:/);
	const afterFirst = await lifecycle.rebuildLifecycleInventory('workspace-v1');
	assert.equal(afterFirst.activeRevisionId, first.materialization.targetRevision);
	assert.equal(afterFirst.revisions.length, 1);
	assert.equal(afterFirst.revisions[0].lineage.sourceKind, 'BASE_DOCUMENT');
	assert.equal(afterFirst.revisions[0].content.startsWith(base), true);
	assert.equal(afterFirst.revisions[0].content.includes('Bounded accepted synthesis a.'), true);
	const firstRetry = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for approved base revision', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-a'] });
	assert.equal(firstRetry.status, 'materialized');
	assert.equal(firstRetry.materialization.targetRevision, first.materialization.targetRevision);
	assert.equal((await lifecycle.rebuildLifecycleInventory('workspace-v1')).revisions.length, 1);
	await assert.rejects(() => readFile(path.join(projectRoot, 'proposals', 'research-concept-r01.md')));

	const successor = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for approved successor', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-b'] });
	assert.equal(successor.status, 'materialized');
	const afterSuccessor = await lifecycle.rebuildLifecycleInventory('workspace-v1');
	assert.equal(afterSuccessor.activeRevisionId, successor.materialization.targetRevision);
	assert.equal(afterSuccessor.revisions.length, 2);
	assert.equal(afterSuccessor.revisions.find((revision) => revision.revisionId === first.materialization.targetRevision).state, 'SUPERSEDED');
	const active = afterSuccessor.revisions.find((revision) => revision.revisionId === successor.materialization.targetRevision);
	assert.equal(active.lineage.sourceKind, 'REVISION');
	assert.equal(active.lineage.sourceId, first.materialization.targetRevision);
	assert.equal(active.content.includes('Bounded accepted synthesis a.'), true);
	assert.equal(active.content.includes('Bounded accepted synthesis b.'), true);
});
