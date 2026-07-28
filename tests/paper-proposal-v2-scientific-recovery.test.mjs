import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
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
const workspace = await jiti.import(path.join(root, '.pi/extensions/proposal-workspace.ts'));
const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');

function event(sequence, eventId, type, actor, payload, causes = []) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:0${sequence}:00.000Z`, actor: { kind: actor }, type, threadId: 'thread-a', causalEventIds: causes, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}

async function fixture() {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-v2-scientific-recovery-'));
	await mkdir(path.join(projectRoot, 'proposals'));
	const store = new v2.ScientificStateStore(projectRoot);
	const summary = 'Bounded accepted synthesis.';
	const synthesisDigest = digest({ synthesisId: 'synthesis-a', threadId: 'thread-a', summary });
	await store.commitTransition({
		events: [
			event(1, 'created-a', 'THREAD_CREATED', 'USER', { title: 'Question', summary, activeThreadId: 'thread-a' }),
			event(2, 'tutor-a', 'TUTOR_ASSESSED', 'TUTOR', { status: 'DRAFT', summary, synthesisId: 'synthesis-a', synthesisDigest }, ['created-a']),
			event(3, 'review-a', 'CONCEPTUAL_REVIEW_RECORDED', 'CONCEPTUAL_REVIEWER', { status: 'PASS', synthesisId: 'synthesis-a', synthesisDigest }, ['tutor-a']),
			event(4, 'accepted-a', 'DECISION_ACCEPTED', 'USER', { decisionId: 'decision-a', synthesisId: 'synthesis-a', synthesisDigest, status: 'ACCEPTED_UNMATERIALIZED' }, ['review-a']),
		],
		snapshot: { schemaVersion: 1, activeThreadId: 'thread-a', threads: [{ threadId: 'thread-a', version: 1, status: 'ACCEPTED_UNMATERIALIZED', title: 'Question', summary, createdEventId: 'created-a', headEventId: 'accepted-a', relationIds: [], decisionIds: ['decision-a'] }], relations: [], decisions: [{ decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: synthesisDigest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: ['tutor-a', 'review-a'] }] },
	});
	const reservation = await store.reserveMaterialization(['decision-a']);
	assert.equal(reservation.status, 'reserved');
	const planned = await new v2.MaterializationPlanner(store).plan({ record: reservation.record, state: await store.read(), canonicalMetadata: { schemaVersion: 1, title: 'Scientific recovery', sectionHeading: 'Accepted decisions' } });
	assert.equal(planned.status, 'ready');
	return { projectRoot, store, record: (await store.reserveMaterialization(['decision-a'])).record };
}

test('recovery diagnostics expose only bounded fail-closed state and retry validates the frozen record', async () => {
	const { store, record } = await fixture();
	const blocked = await store.recordMaterializationOutcome(record, 'BLOCKED', 'MATERIALIZATION_VALIDATION_FAILED');
	assert.equal(blocked.status, 'ready');
	assert.deepEqual(await store.recoveryDiagnostics(), { status: 'ready', diagnostics: [{ scope: 'MATERIALIZATION', state: 'BLOCKED', code: 'MATERIALIZATION_VALIDATION_FAILED', phaseReached: 'PREPARED', evidence: [], lastValidTransition: 'MATERIALIZATION_PLANNED', nextAction: 'retry_materialization', materializationId: record.materializationId }] });
	const retried = await store.retryMaterialization(blocked.record);
	assert.equal(retried.status, 'ready');
	assert.equal(retried.record.state, 'PREPARED');
	assert.equal((await store.read()).snapshot.decisions[0].state, 'ACCEPTED_UNMATERIALIZED');
});

test('recovery-required evidence cannot be retried and corrupt authoritative files remain diagnostic-only', async () => {
	const { projectRoot, store, record } = await fixture();
	const recovery = await store.recordMaterializationOutcome(record, 'RECOVERY_REQUIRED', 'MATERIALIZATION_PUBLICATION_EVIDENCE_INCOMPLETE');
	assert.equal(recovery.status, 'ready');
	assert.deepEqual(await store.recoveryDiagnostics(), { status: 'recovery_required', diagnostics: [{ scope: 'MATERIALIZATION', state: 'RECOVERY_REQUIRED', code: 'MATERIALIZATION_PUBLICATION_EVIDENCE_INCOMPLETE', phaseReached: 'PREPARED', evidence: [], lastValidTransition: 'MATERIALIZATION_PLANNED', nextAction: 'reconcile_materialization_evidence', materializationId: record.materializationId }] });
	assert.deepEqual(await store.retryMaterialization(recovery.record), { status: 'blocked', code: 'MATERIALIZATION_RETRY_NOT_ALLOWED' });
	const manifestPath = path.join(projectRoot, '.paper-proposal-v2/scientific/manifest.json');
	await writeFile(manifestPath, '{not-json');
	const before = await readFile(manifestPath, 'utf8');
	const diagnostics = await store.recoveryDiagnostics();
	assert.equal(diagnostics.status, 'recovery_required');
	assert.deepEqual(diagnostics.diagnostics, [{ scope: 'SCIENTIFIC_STATE', state: 'RECOVERY_REQUIRED', code: 'SCIENTIFIC_RECORD_INVALID', nextAction: 'reconcile_scientific_state' }]);
	assert.equal(await readFile(manifestPath, 'utf8'), before);
});

test('feature rollback leaves scientific history available to read-only diagnostics without exposing private input', async () => {
	const { projectRoot, store, record } = await fixture();
	await store.recordMaterializationOutcome(record, 'BLOCKED', 'MATERIALIZATION_COMPILATION_FAILED');
	assert.equal(workspace.scientificWorkflowFeatureEnabled({ PAPER_PROPOSAL_V2_SCIENTIFIC_WORKFLOW_ENABLED: 'false' }), false);
	const recordPath = path.join(projectRoot, '.paper-proposal-v2/scientific/materializations', `${record.materializationId}.json`);
	const before = await readFile(recordPath, 'utf8');
	v2.resetRuntimeMetrics();
	const diagnostics = await store.recoveryDiagnostics();
	const metrics = v2.getRuntimeMetrics();
	assert.equal(diagnostics.diagnostics[0].code, 'MATERIALIZATION_COMPILATION_FAILED');
	assert.equal(await readFile(recordPath, 'utf8'), before);
	assert.equal(metrics.scientificMetrics.recovery_diagnostic, 1);
	assert.doesNotMatch(JSON.stringify({ diagnostics, metrics }), /private prompt|raw trace|hidden prompt|chain.?of.?thought/i);
});
