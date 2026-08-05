import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, readdir } from 'node:fs/promises';
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
const v2 = await jiti.import(path.join(root, '.claude/skills/proposal-deliberation/engine/exports.ts'));
const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const metadata = { schemaVersion: 1, title: 'Scientific reasoning proposal', sectionHeading: 'Accepted scientific decisions' };

function event(sequence, eventId, type, threadId, actor, payload, causalEventIds) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:${String(sequence).padStart(2, '0')}:00.000Z`, actor: { kind: actor }, type, threadId, causalEventIds, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}

async function fixture({ source } = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-scientific-candidate-'));
	const store = new v2.ScientificStateStore(projectRoot);
	const summary = 'Bounded accepted synthesis.';
	const synthesisDigest = digest({ synthesisId: 'synthesis-a', threadId: 'thread-a', summary });
	const events = [
		event(1, 'created-a', 'THREAD_CREATED', 'thread-a', 'USER', { title: 'Question', summary: 'Public summary.', activeThreadId: 'thread-a' }, []),
		event(2, 'tutor-a', 'TUTOR_ASSESSED', 'thread-a', 'TUTOR', { status: 'DRAFT', summary, synthesisId: 'synthesis-a', synthesisDigest }, ['created-a']),
		event(3, 'review-a', 'CONCEPTUAL_REVIEW_RECORDED', 'thread-a', 'CONCEPTUAL_REVIEWER', { status: 'PASS', synthesisId: 'synthesis-a', synthesisDigest }, ['tutor-a']),
		event(4, 'accepted-a', 'DECISION_ACCEPTED', 'thread-a', 'USER', { decisionId: 'decision-a', synthesisId: 'synthesis-a', synthesisDigest, status: 'ACCEPTED_UNMATERIALIZED' }, ['review-a']),
	];
	const revisionEvidence = source && { filename: source.filename, revision: source.revision, documentSha256: source.documentSha256 };
	await store.commitTransition({ events, snapshot: {
		schemaVersion: 1,
		activeThreadId: 'thread-a',
		threads: [{ threadId: 'thread-a', version: 1, status: 'ACCEPTED_UNMATERIALIZED', title: 'Question', summary: 'Public summary.', createdEventId: 'created-a', headEventId: 'accepted-a', ...(revisionEvidence ? { revisionEvidence } : {}), relationIds: [], decisionIds: ['decision-a'] }],
		relations: [],
		decisions: [{ decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: synthesisDigest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: ['tutor-a', 'review-a'] }],
	} });
	const reservation = await store.reserveMaterialization(['decision-a']);
	assert.equal(reservation.status, 'reserved');
	const planned = await new v2.MaterializationPlanner(store).plan({ record: reservation.record, state: await store.read(), ...(source ? { source } : {}), canonicalMetadata: metadata });
	assert.equal(planned.status, 'ready');
	const persisted = await store.reserveMaterialization(['decision-a']);
	assert.equal(persisted.status, 'existing');
	return { projectRoot, source, record: persisted.record };
}

function clonedRecordWithPlan(record, mutate) {
	const next = structuredClone(record);
	mutate(next.plan);
	const { digest: ignored, ...incomplete } = next.plan;
	next.plan.digest = v2.materializationPlanDigest(incomplete);
	return next;
}

test('CandidateExecutor returns the exact frozen r01 bytes, digest, provenance, and validation inputs without writes', async () => {
	const { projectRoot, record } = await fixture();
	const before = await readdir(projectRoot);
	const result = await new v2.MaterializationCandidateExecutor().execute({ record, frozenSelection: record.frozenSelection });
	const after = await readdir(projectRoot);
	assert.equal(result.status, 'ready');
	assert.deepEqual(after, before);
	assert.equal(result.candidate.bytes.toString('utf8'), record.plan.payload.markdown);
	assert.equal(result.candidate.digest, createHash('sha256').update(result.candidate.bytes).digest('hex'));
	assert.deepEqual(result.provenance, record.plan.claimProvenance);
	assert.equal(result.validation.validationResults.completeMarkdown, true);
});

test('CandidateExecutor applies only ordered frozen successor patches and fails closed for a stale base', async () => {
	const source = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Existing proposal\n\nStable base.\n'));
	const { record } = await fixture({ source });
	const executor = new v2.MaterializationCandidateExecutor();
	const ready = await executor.execute({ record, frozenSelection: record.frozenSelection, source });
	assert.equal(ready.status, 'ready');
	assert.equal(ready.candidate.bytes.toString('utf8').includes('Bounded accepted synthesis.'), true);
	assert.deepEqual(ready.validation.patchIds, ['patch-1']);
	assert.equal(source.documentBytes.toString('utf8'), '# Existing proposal\n\nStable base.\n');
	const stale = await v2.rebuildDerivedState(source.filename, source.revision, source.lineage, Buffer.from('# Existing proposal\n\nChanged base.\n'));
	assert.deepEqual(await executor.execute({ record, frozenSelection: record.frozenSelection, source: stale }), { status: 'blocked', code: 'MATERIALIZATION_SOURCE_STALE', evidence: { materializationId: record.materializationId, planDigest: record.plan.digest } });
});

test('CandidateExecutor rejects missing, invalid, compiler-failing, and validator-failing frozen payloads without deriving content', async () => {
	const source = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Existing proposal\n\nStable base.\n'));
	const { record } = await fixture({ source });
	const executor = new v2.MaterializationCandidateExecutor();
	const missing = structuredClone(record);
	delete missing.plan;
	assert.equal((await executor.execute({ record: missing, frozenSelection: missing.frozenSelection, source })).code, 'MATERIALIZATION_PLAN_MISSING');
	const compilerFailure = clonedRecordWithPlan(record, (plan) => { plan.payload.patches[0].plan.actions[0].anchorEntryId = 'missing-anchor'; });
	assert.equal((await executor.execute({ record: compilerFailure, frozenSelection: compilerFailure.frozenSelection, source })).code, 'MATERIALIZATION_COMPILATION_FAILED');
	const validatorFailure = clonedRecordWithPlan(record, (plan) => { plan.payload.patches[0].plan.actions[0].content = '\n\n####### invalid heading\n'; });
	assert.equal((await executor.execute({ record: validatorFailure, frozenSelection: validatorFailure.frozenSelection, source })).code, 'MATERIALIZATION_VALIDATION_FAILED');
});

test('CandidateExecutor has no drafting, agent, context, workspace-write, guard, index, review, or publication authority', async () => {
	const source = await (await import('node:fs/promises')).readFile(path.join(root, '.claude/skills/proposal-deliberation/engine/materialization-candidate-executor.ts'), 'utf8');
	assert.doesNotMatch(source, /(?:writeFile|mkdir|rename|publish(?:Initial|Successor)?|ProposalWorkspaceAdapter|DocumentReviewer|createInitialProposal|loadDocumentState|ScientificStateStore|Tutor|Reviewer|ContextBuilder|guard)/);
});
