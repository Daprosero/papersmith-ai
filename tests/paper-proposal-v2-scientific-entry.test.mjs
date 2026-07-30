import assert from 'node:assert/strict';
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

const v2 = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/exports.ts'));
const revision = { filename: 'research-concept-r01.md', revision: 'r01', documentSha256: 'a'.repeat(64) };
const withdrawnRevision = { filename: 'research-concept-r02.md', revision: 'r02', documentSha256: 'b'.repeat(64) };

function inventory({ activeRevisions = [], withdrawnRevisions = [], status = 'valid', code = 'REVISION_INVENTORY_INCONSISTENT' } = {}) {
	return status === 'valid'
		? { status, activeRevisions, withdrawnRevisions, auditEvidence: ['revision-inventory:validated'] }
		: { status, code, auditEvidence: ['revision-inventory:blocked'] };
}

function scientific({ revisionEvidence, pending = false, transactionMarkers = [], mutate, status = 'present' } = {}) {
	if (status === 'absent') return { status, auditEvidence: ['scientific-state:absent'] };
	const thread = {
		threadId: 'thread-1', version: 1, status: pending ? 'ACCEPTED_UNMATERIALIZED' : 'OPEN', title: 'Question', summary: 'Bounded summary.',
		createdEventId: 'event-1', headEventId: pending ? 'event-2' : 'event-1', ...(revisionEvidence ? { revisionEvidence } : {}), relationIds: [], decisionIds: pending ? ['decision-1'] : [],
	};
	const events = [{
		schemaVersion: 1, eventId: 'event-1', sequence: 1, occurredAt: '2026-01-01T00:00:00.000Z', actor: { kind: 'USER' }, type: 'THREAD_CREATED', threadId: 'thread-1', causalEventIds: [], payload: {}, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 },
	}];
	const decisions = [];
	if (pending) {
		events.push({ schemaVersion: 1, eventId: 'event-2', sequence: 2, occurredAt: '2026-01-01T00:01:00.000Z', actor: { kind: 'USER' }, type: 'DECISION_ACCEPTED', threadId: 'thread-1', causalEventIds: ['event-1'], payload: {}, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } });
		decisions.push({ decisionId: 'decision-1', threadId: 'thread-1', acceptedEventId: 'event-2', acceptedSynthesisDigest: 'c'.repeat(64), acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: ['event-1', 'event-2'] });
	}
	const snapshot = { schemaVersion: 1, activeThreadId: 'thread-1', threads: [thread], relations: [], decisions };
	const value = {
		status, manifest: { schemaVersion: 1, snapshotSha256: v2.scientificEvidenceDigest(snapshot), eventsSha256: v2.scientificEvidenceDigest(events) }, snapshot, events, transactionMarkers, auditEvidence: ['scientific-state:validated'],
	};
	mutate?.(value);
	return value;
}

function resolver(revisions, state) {
	return new v2.ProjectEntryResolver({ read: async () => revisions }, { read: async () => state });
}

test('ProjectEntryResolver returns every conservative entry state from validated read-only evidence', async () => {
	assert.equal((await resolver(inventory(), scientific({ status: 'absent' })).resolve()).state, 'EMPTY_PROJECT');
	assert.equal((await resolver(inventory(), scientific()).resolve()).state, 'SCIENTIFIC_ONLY');
	assert.equal((await resolver(inventory({ activeRevisions: [revision] }), scientific({ status: 'absent' })).resolve()).state, 'ACTIVE_PROPOSAL');
	assert.equal((await resolver(inventory({ activeRevisions: [revision] }), scientific({ revisionEvidence: revision })).resolve()).state, 'ACTIVE_SCIENTIFIC_PROJECT');
	assert.equal((await resolver(inventory(), scientific({ pending: true })).resolve()).state, 'MATERIALIZATION_PENDING');
	assert.equal((await resolver(inventory({ withdrawnRevisions: [withdrawnRevision] }), scientific({ status: 'absent' })).resolve()).state, 'WITHDRAWN_ONLY');
	const multiple = await resolver(inventory({ activeRevisions: [revision, withdrawnRevision] }), scientific({ status: 'absent' })).resolve();
	assert.equal(multiple.state, 'MULTIPLE_ACTIVE_REVISIONS');
	assert.equal(multiple.recovery.required, true);
	assert.equal(multiple.recovery.code, 'MULTIPLE_ACTIVE_REVISIONS');
});

test('ProjectEntryResolver returns pending candidates and never changes port evidence', async () => {
	const revisions = inventory({ activeRevisions: [revision] });
	const state = scientific({ revisionEvidence: revision, pending: true });
	const before = JSON.stringify({ revisions, state });
	const entry = await resolver(revisions, state).resolve();
	assert.equal(entry.state, 'MATERIALIZATION_PENDING');
	assert.deepEqual(entry.pendingCandidateIds, ['decision-1']);
	assert.equal(entry.activeRevision.filename, revision.filename);
	assert.equal(JSON.stringify({ revisions, state }), before);
});

test('invalid authoritative scientific evidence fails closed with recovery guidance', async () => {
	for (const [name, mutate, code] of [
		['digest mismatch', (value) => { value.manifest.eventsSha256 = '0'.repeat(64); }, 'SCIENTIFIC_DIGEST_MISMATCH'],
		['orphaned event thread', (value) => { value.events[0].threadId = 'missing-thread'; value.manifest.eventsSha256 = v2.scientificEvidenceDigest(value.events); }, 'SCIENTIFIC_EVENT_THREAD_ORPHANED'],
		['orphaned relation', (value) => { value.snapshot.threads[0].relationIds = ['relation-1']; value.manifest.snapshotSha256 = v2.scientificEvidenceDigest(value.snapshot); }, 'SCIENTIFIC_THREAD_RELATION_ORPHANED'],
		['interrupted transaction', undefined, 'SCIENTIFIC_TRANSACTION_INCOMPLETE'],
	]) {
		const state = scientific({ revisionEvidence: revision, transactionMarkers: name === 'interrupted transaction' ? [{ transitionId: 'tx-1', state: 'PREPARED' }] : [], mutate });
		const entry = await resolver(inventory({ activeRevisions: [revision] }), state).resolve();
		assert.equal(entry.state, 'INCONSISTENT_PROJECT', name);
		assert.equal(entry.recovery.required, true, name);
		assert.equal(entry.recovery.code, code, name);
	}
});

test('stale revision evidence, partial records, and invalid revision inventory never infer a safe entry', async () => {
	const stale = await resolver(inventory({ activeRevisions: [revision] }), scientific({ revisionEvidence: { ...revision, documentSha256: 'd'.repeat(64) } })).resolve();
	assert.equal(stale.recovery.code, 'SCIENTIFIC_REVISION_EVIDENCE_STALE');

	const partial = await resolver(inventory(), scientific({ mutate: (value) => { value.snapshot.threads = []; value.manifest.snapshotSha256 = v2.scientificEvidenceDigest(value.snapshot); } })).resolve();
	assert.equal(partial.recovery.code, 'SCIENTIFIC_AUTHORITATIVE_STATE_PARTIAL');

	const invalidInventory = await resolver(inventory({ status: 'inconsistent', code: 'MANIFEST_RECEIPT_AUDIT_FAILED' }), scientific({ status: 'absent' })).resolve();
	assert.equal(invalidInventory.recovery.code, 'MANIFEST_RECEIPT_AUDIT_FAILED');
});

test('bootstrap is explicit, observation-only, and limited to one verified active proposal', async () => {
	const revisions = inventory({ activeRevisions: [revision] });
	const state = scientific({ status: 'absent' });
	const ordinary = await resolver(revisions, state).resolve();
	assert.equal(ordinary.bootstrap, undefined);
	const bootstrapped = await resolver(revisions, state).resolve({ bootstrapFromActiveProposal: true });
	assert.equal(bootstrapped.state, 'ACTIVE_PROPOSAL');
	assert.deepEqual(bootstrapped.bootstrap, {
		status: 'available', source: revision,
		observations: [{ kind: 'verified_active_proposal', id: revision.filename, sha256: revision.documentSha256 }], unknownHistory: true,
	});
	assert.deepEqual(await resolver(inventory({ activeRevisions: [revision, withdrawnRevision] }), state).resolve({ bootstrapFromActiveProposal: true }), {
		state: 'MULTIPLE_ACTIVE_REVISIONS', relatedThreadIds: [], pendingCandidateIds: [],
		recovery: { required: true, code: 'MULTIPLE_ACTIVE_REVISIONS', action: 'select_or_reconcile_active_revision' }, auditEvidence: ['revision-inventory:validated', 'scientific-state:absent'],
	});
});

test('entry resolver remains read-only and imports canonical scientific contracts', async () => {
	const source = await (await import('node:fs/promises')).readFile(path.join(root, '.claude/skills/paper-proposal/engine/project-entry-resolver.ts'), 'utf8');
	assert.match(source, /scientific-domain\.js/);
	assert.doesNotMatch(source, /(?:writeFile|mkdir|rename|rm\()/);
	assert.doesNotMatch(source, /type\s+(?:ScientificThread|ScientificDecision|ScientificEvent|ThreadRelation|ProjectEntryState)\s*=/);
});

test('ProjectEntryResolver exposes registered lifecycle evidence read-only and preserves withdrawn-only absence', async () => {
 const base = { baseDocumentId: 'base-1', contentHash: 'c'.repeat(64) };
 const active = { filename: 'ignored-locator.md', revision: 'r01', documentSha256: 'a'.repeat(64), revisionId: 'revision-1', baseDocumentId: 'base-1', lineage: { sourceKind: 'BASE_DOCUMENT', sourceId: 'base-1', sourceContentHash: 'c'.repeat(64) } };
 const lifecycle = { ...inventory({ activeRevisions: [active] }), baseDocument: base, lifecycleState: 'ACTIVE' };
 const before = JSON.stringify(lifecycle);
 const entry = await resolver(lifecycle, scientific({ status: 'absent' })).resolve();
 assert.deepEqual({ state: entry.state, baseDocument: entry.baseDocument, lifecycleState: entry.lifecycleState, activeRevisionId: entry.activeRevision.revisionId }, { state: 'ACTIVE_PROPOSAL', baseDocument: base, lifecycleState: 'ACTIVE', activeRevisionId: 'revision-1' });
 assert.equal(JSON.stringify(lifecycle), before);
 const withdrawn = await resolver({ ...inventory({ withdrawnRevisions: [withdrawnRevision] }), baseDocument: base, lifecycleState: 'WITHDRAWN_ONLY' }, scientific({ status: 'absent' })).resolve();
 assert.deepEqual({ state: withdrawn.state, lifecycleState: withdrawn.lifecycleState, activeRevision: withdrawn.activeRevision }, { state: 'WITHDRAWN_ONLY', lifecycleState: 'WITHDRAWN_ONLY', activeRevision: undefined });
});
