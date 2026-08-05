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
const v2 = await jiti.import(path.join(root, '.claude/skills/proposal-deliberation/engine/exports.ts'));
const workspace = await jiti.import(path.join(root, '.claude/skills/proposal-deliberation/engine/proposal-workspace.ts'));
const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');

function event(sequence, eventId, type, actor, payload, causes = []) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:0${sequence}:00.000Z`, actor: { kind: actor }, type, threadId: 'thread-a', causalEventIds: causes, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}

async function fixture() {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-scientific-recovery-'));
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
	const manifestPath = path.join(projectRoot, '.proposal-deliberation/scientific/manifest.json');
	await writeFile(manifestPath, '{not-json');
	const before = await readFile(manifestPath, 'utf8');
	const diagnostics = await store.recoveryDiagnostics();
	assert.equal(diagnostics.status, 'recovery_required');
	assert.deepEqual(diagnostics.diagnostics, [{ scope: 'SCIENTIFIC_STATE', state: 'RECOVERY_REQUIRED', code: 'SCIENTIFIC_RECORD_INVALID', nextAction: 'reconcile_scientific_state' }]);
	assert.equal(await readFile(manifestPath, 'utf8'), before);
});

test('a committed lifecycle marker recovers through the read-only inventory adapter after a projection fault', async () => {
	const { projectRoot } = await fixture();
	const faulted = new v2.LifecycleService(projectRoot, { afterCommitMarker: () => { throw new Error('injected-after-marker'); } });
	const result = await faulted.registerBaseDocument({ workspaceId: 'workspace-v1', requestId: 'register-base', baseDocumentId: 'base-v1', content: '# Durable base\n' });
	assert.deepEqual({ outcome: result.outcome, code: result.code }, { outcome: 'INCONSISTENT', code: 'LIFECYCLE_INVENTORY_INCONSISTENT' });
	const recovered = await v2.readLifecycleV1Inventory({ projectRoot, workspaceId: 'workspace-v1' });
	assert.deepEqual({ status: recovered.status, lifecycleState: recovered.lifecycleState, baseDocumentId: recovered.baseDocument?.baseDocumentId, activeRevision: recovered.activeRevision }, { status: 'valid', lifecycleState: 'BASE_REGISTERED', baseDocumentId: 'base-v1', activeRevision: undefined });
	await assert.rejects(() => readFile(path.join(projectRoot, 'proposals', 'research-concept-r01.md')));
});

test('lifecycle marker and projection faults preserve recovery evidence without a partial public proposal', async () => {
	const beforeMarker = await fixture();
	const beforeManifestPath = path.join(beforeMarker.projectRoot, '.proposal-deliberation/scientific/manifest.json');
	const beforeManifest = await readFile(beforeManifestPath, 'utf8');
	const interrupted = await new v2.LifecycleService(beforeMarker.projectRoot, { beforeCommitMarker: () => { throw new Error('injected-before-marker'); } }).registerBaseDocument({ workspaceId: 'fault-workspace', requestId: 'register-before-marker', baseDocumentId: 'fault-base', content: '# Interrupted base\n' });
	assert.deepEqual({ outcome: interrupted.outcome, code: interrupted.code }, { outcome: 'INCONSISTENT', code: 'LIFECYCLE_INVENTORY_INCONSISTENT' });
	assert.deepEqual(await v2.readLifecycleV1Inventory({ projectRoot: beforeMarker.projectRoot, workspaceId: 'fault-workspace' }), { status: 'unregistered', code: 'LIFECYCLE_V1_UNREGISTERED', auditEvidence: ['lifecycle-v1:authority-unregistered'] });
	assert.equal(await readFile(beforeManifestPath, 'utf8'), beforeManifest);
	await assert.rejects(() => readFile(path.join(beforeMarker.projectRoot, 'proposals', 'research-concept-r01.md')));

	const afterProjection = await fixture();
	const afterManifestPath = path.join(afterProjection.projectRoot, '.proposal-deliberation/scientific/manifest.json');
	const afterManifest = await readFile(afterManifestPath, 'utf8');
	const committed = await new v2.LifecycleService(afterProjection.projectRoot, { afterInventoryProjection: () => { throw new Error('injected-after-projection'); } }).registerBaseDocument({ workspaceId: 'projection-workspace', requestId: 'register-after-projection', baseDocumentId: 'projection-base', content: '# Committed base\n' });
	assert.deepEqual({ outcome: committed.outcome, code: committed.code }, { outcome: 'INCONSISTENT', code: 'LIFECYCLE_INVENTORY_INCONSISTENT' });
	const rebuilt = await v2.readLifecycleV1Inventory({ projectRoot: afterProjection.projectRoot, workspaceId: 'projection-workspace' });
	assert.deepEqual({ status: rebuilt.status, lifecycleState: rebuilt.lifecycleState, baseDocumentId: rebuilt.baseDocument?.baseDocumentId, activeRevision: rebuilt.activeRevision }, { status: 'valid', lifecycleState: 'BASE_REGISTERED', baseDocumentId: 'projection-base', activeRevision: undefined });
	assert.equal(await readFile(afterManifestPath, 'utf8'), afterManifest);
	await assert.rejects(() => readFile(path.join(afterProjection.projectRoot, 'proposals', 'research-concept-r01.md')));
});

test('a fresh entry resolver rebuilds lifecycle-owned active evidence without selecting or publishing a legacy filename', async () => {
	const { projectRoot } = await fixture();
	const service = new v2.LifecycleService(projectRoot);
	const base = await service.registerBaseDocument({ workspaceId: 'restart-workspace', requestId: 'register-base', baseDocumentId: 'restart-base', content: '# Durable base\n\nUnchanged premise.\n' });
	assert.equal(base.outcome, 'COMMITTED');
	const first = await service.createFromBase({ workspaceId: 'restart-workspace', requestId: 'create-first', operation: 'CREATE_FROM_BASE', revisionId: 'restart-r1', locator: 'research-concept-r99.md', source: { sourceKind: 'BASE_DOCUMENT', sourceId: 'restart-base', sourceContentHash: base.base.contentHash, baseDocumentId: 'restart-base' }, approvedChanges: [] });
	assert.equal(first.outcome, 'COMMITTED');
	const successor = await service.createSuccessor({ workspaceId: 'restart-workspace', requestId: 'create-successor', operation: 'CREATE_SUCCESSOR', revisionId: 'restart-r2', locator: 'research-concept-r01.md', source: { sourceKind: 'REVISION', sourceId: 'restart-r1', sourceContentHash: first.revision.contentHash, baseDocumentId: 'restart-base' }, approvedChanges: [] });
	assert.equal(successor.outcome, 'COMMITTED');
	const entry = await new v2.ProjectEntryResolver(v2.createLifecycleV1RevisionInventoryPort({ projectRoot, workspaceId: 'restart-workspace' }), new v2.ScientificStateStore(projectRoot)).resolve();
	assert.deepEqual({ state: entry.state, baseDocumentId: entry.baseDocument?.baseDocumentId, activeRevisionId: entry.activeRevision?.revisionId, activeHash: entry.activeRevision?.documentSha256 }, { state: 'MATERIALIZATION_PENDING', baseDocumentId: 'restart-base', activeRevisionId: 'restart-r2', activeHash: successor.revision.contentHash });
	const rebuilt = await v2.readLifecycleV1Inventory({ projectRoot, workspaceId: 'restart-workspace' });
	assert.deepEqual({ status: rebuilt.status, lifecycleState: rebuilt.lifecycleState, activeRevisionId: rebuilt.activeRevision?.revisionId, states: rebuilt.revisions.map((revision) => [revision.revisionId, revision.state]) }, { status: 'valid', lifecycleState: 'ACTIVE', activeRevisionId: 'restart-r2', states: [['restart-r1', 'SUPERSEDED'], ['restart-r2', 'ACTIVE']] });
	await assert.rejects(() => readFile(path.join(projectRoot, 'proposals', 'research-concept-r01.md')));
	await assert.rejects(() => readFile(path.join(projectRoot, 'proposals', 'research-concept-r99.md')));
});

test('feature rollback leaves scientific history available to read-only diagnostics without exposing private input', async () => {
	const { projectRoot, store, record } = await fixture();
	await store.recordMaterializationOutcome(record, 'BLOCKED', 'MATERIALIZATION_COMPILATION_FAILED');
	assert.equal(workspace.scientificWorkflowFeatureEnabled({ PROPOSAL_DELIBERATION_SCIENTIFIC_WORKFLOW_ENABLED: 'false' }), false);
	const recordPath = path.join(projectRoot, '.proposal-deliberation/scientific/materializations', `${record.materializationId}.json`);
	const before = await readFile(recordPath, 'utf8');
	v2.resetRuntimeMetrics();
	const diagnostics = await store.recoveryDiagnostics();
	const metrics = v2.getRuntimeMetrics();
	assert.equal(diagnostics.diagnostics[0].code, 'MATERIALIZATION_COMPILATION_FAILED');
	assert.equal(await readFile(recordPath, 'utf8'), before);
	assert.equal(metrics.scientificMetrics.recovery_diagnostic, 1);
	assert.doesNotMatch(JSON.stringify({ diagnostics, metrics }), /private prompt|raw trace|hidden prompt|chain.?of.?thought/i);
});
