// paper-proposal-tutor-repair (deliberated-operations, SLICE 1): deliberated
// ADD (insert) and DELETE applied byte-preservingly in the SAME successor
// version as an ordinary CHANGE (replace), all in-place and disjoint, per
// design `sdd/paper-proposal-tutor-repair/design-deliberated-operations`.
//
// Covers, bottom-up:
//   A. composite-engine + block-plan primitives: zero-width insert splice,
//      empty-replacement delete splice, guard rejections, target staleness.
//   B. capture: `ScientificWorkflowService.candidate()`/`deriveProposedEdit`
//      lifts a deliberated INSERT/DELETE from the USER's own instruction
//      (via `resolveIntent`), never from the tutor's own guess.
//   C. coexistence: a CHANGE + an ADD + a DELETE at distinct loci splice into
//      ONE successor version through the live lifecycle-v1 materialization
//      route; true overlaps and drift fall back safely.
//   D. SuccessorEditPlanner (secondary/filename-era route): the same three
//      kinds compile through the existing generic `compilePatches` path.
//
// No real proposal `.md` file is ever created or modified; every fixture is
// in-memory DocumentState/temp-directory only.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
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
const v2 = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/exports.ts'));

const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const EMPTY_SHA256 = sha256(Buffer.alloc(0));

// --- Section A: composite-engine + block-plan primitives -----------------------------

const TEXT = 'Alpha section.\n\nBeta section.\n\nGamma section.\n';

function span(text) {
	const start = TEXT.indexOf(text);
	return { startByte: start, endByte: start + Buffer.byteLength(text) };
}
function entry(id, text) {
	const { startByte, endByte } = span(text);
	return { entryId: id, type: 'section', startByte, endByte, textSha256: sha256(Buffer.from(text)) };
}
function fixture() {
	const documentBytes = Buffer.from(TEXT);
	const alpha = entry('alpha-section', 'Alpha section.');
	const beta = entry('beta-section', 'Beta section.');
	const gamma = entry('gamma-section', 'Gamma section.');
	const source = {
		filename: 'research-concept-r01.md',
		revision: 'r01',
		documentBytes,
		documentSha256: sha256(documentBytes),
		structuralIndex: { entries: [alpha, beta, gamma], byId: { [alpha.entryId]: alpha, [beta.entryId]: beta, [gamma.entryId]: gamma } },
	};
	return { source, alpha, beta, gamma };
}
function sourceIdentity(source) {
	return { filename: source.filename, revision: source.revision, documentSha256: source.documentSha256 };
}
function spliceDisjoint(sourceBytes, edits) {
	const ordered = [...edits].sort((left, right) => left.startByte - right.startByte || left.endByte - right.endByte);
	const parts = [];
	let cursor = 0;
	for (const edit of ordered) {
		parts.push(sourceBytes.subarray(cursor, edit.startByte));
		parts.push(Buffer.from(edit.replacement, 'utf8'));
		cursor = edit.endByte;
	}
	parts.push(sourceBytes.subarray(cursor));
	return Buffer.concat(parts);
}

function insertBlockPlan(source, anchor, position, content, id = 'ins-1') {
	const point = position === 'before' ? anchor.startByte : anchor.endByte;
	const target = { status: 'resolved', selector: { entryId: anchor.entryId, startByte: point, endByte: point, textSha256: EMPTY_SHA256, documentSha256: source.documentSha256 } };
	const edits = [{ startByte: point, endByte: point, replacement: content }];
	const block = { id, dependsOn: [], target, candidateSha256: sha256(spliceDisjoint(source.documentBytes, edits)), op: 'insert' };
	return { plan: { source: sourceIdentity(source), orderedBlockIds: [id], blocks: [block], mergeGroups: [] }, resolver: () => content };
}

function deleteBlockPlan(source, target, id = 'del-1') {
	const selector = { entryId: target.entryId, startByte: target.startByte, endByte: target.endByte, textSha256: target.textSha256, documentSha256: source.documentSha256 };
	const edits = [{ startByte: target.startByte, endByte: target.endByte, replacement: '' }];
	const block = { id, dependsOn: [], target: { status: 'resolved', selector }, candidateSha256: sha256(spliceDisjoint(source.documentBytes, edits)), op: 'delete' };
	return { plan: { source: sourceIdentity(source), orderedBlockIds: [id], blocks: [block], mergeGroups: [] }, resolver: () => '' };
}

test('composite engine: a zero-width insert block splices content at the anchor boundary, every other byte untouched', async () => {
	const { source, alpha, beta } = fixture();
	const { plan, resolver } = insertBlockPlan(source, alpha, 'after', '\n\nInserted section.\n');
	const result = await v2.composeSuccessorBlockCandidate(plan, source, resolver);
	assert.equal(result.status, 'composed', JSON.stringify(result));
	assert.ok(result.candidateBytes.includes(Buffer.from('Inserted section.')));
	assert.ok(result.candidateBytes.includes(Buffer.from('Alpha section.')), 'the anchor entry itself is untouched, not replaced');
	assert.ok(result.candidateBytes.includes(Buffer.from('Beta section.')));
	assert.ok(result.candidateBytes.includes(Buffer.from('Gamma section.')));
	// Byte count only grows by the inserted content -- nothing else moved or changed.
	assert.equal(result.candidateBytes.length, source.documentBytes.length + Buffer.byteLength('\n\nInserted section.\n'));
	void beta;
});

test('composite engine: an insert block with empty content is rejected (BLOCK_REPLACEMENT_INVALID), never a silent no-op insert', async () => {
	const { source, alpha } = fixture();
	const { plan } = insertBlockPlan(source, alpha, 'after', 'placeholder');
	const result = await v2.composeSuccessorBlockCandidate(plan, source, () => '');
	assert.equal(result.status, 'blocked');
	assert.deepEqual(result.diagnostics.map((d) => d.code), ['BLOCK_REPLACEMENT_INVALID']);
});

test('composite engine: a delete block (empty replacement over a non-empty span) removes exactly that span, every other byte byte-identical', async () => {
	const { source, alpha, beta, gamma } = fixture();
	const { plan, resolver } = deleteBlockPlan(source, beta);
	const result = await v2.composeSuccessorBlockCandidate(plan, source, resolver);
	assert.equal(result.status, 'composed', JSON.stringify(result));
	assert.equal(result.candidateBytes.includes(Buffer.from('Beta section.')), false, 'the deleted span itself is gone');
	assert.ok(result.candidateBytes.includes(Buffer.from('Alpha section.')));
	assert.ok(result.candidateBytes.includes(Buffer.from('Gamma section.')));
	assert.equal(result.candidateBytes.length, source.documentBytes.length - (beta.endByte - beta.startByte));
	void alpha; void gamma;
});

test('composite engine: a delete block declaring NON-empty replacement text is rejected (BLOCK_REPLACEMENT_INVALID) -- it would silently behave like a hidden replace', async () => {
	const { source, beta } = fixture();
	const { plan } = deleteBlockPlan(source, beta);
	const result = await v2.composeSuccessorBlockCandidate(plan, source, () => 'sneaky replacement');
	assert.equal(result.status, 'blocked');
	assert.deepEqual(result.diagnostics.map((d) => d.code), ['BLOCK_REPLACEMENT_INVALID']);
});

test('composite engine: a CHANGE (replace) + an ADD (insert) + a DELETE at three distinct loci splice into ONE candidate, every untouched byte preserved', async () => {
	const { source, alpha, beta, gamma } = fixture();
	const changeEdit = { startByte: alpha.startByte, endByte: alpha.endByte, replacement: Buffer.from('Alpha rewritten.') };
	const insertPoint = beta.endByte;
	const insertEdit = { startByte: insertPoint, endByte: insertPoint, replacement: Buffer.from('\n\nInserted after beta.') };
	const deleteEdit = { startByte: gamma.startByte, endByte: gamma.endByte, replacement: Buffer.alloc(0) };
	const allEdits = [changeEdit, insertEdit, deleteEdit];
	function candidateHashThrough(count) {
		return sha256(spliceDisjoint(source.documentBytes, allEdits.slice(0, count).sort((a, b) => a.startByte - b.startByte).length === count ? allEdits.slice(0, count) : allEdits.slice(0, count)));
	}
	const blocks = [
		{ id: 'change', dependsOn: [], target: { status: 'resolved', selector: { entryId: alpha.entryId, startByte: alpha.startByte, endByte: alpha.endByte, textSha256: alpha.textSha256, documentSha256: source.documentSha256 } }, candidateSha256: sha256(spliceDisjoint(source.documentBytes, [changeEdit])), op: 'replace' },
		{ id: 'add', dependsOn: ['change'], target: { status: 'resolved', selector: { entryId: beta.entryId, startByte: insertPoint, endByte: insertPoint, textSha256: EMPTY_SHA256, documentSha256: source.documentSha256 } }, candidateSha256: sha256(spliceDisjoint(source.documentBytes, [changeEdit, insertEdit])), op: 'insert' },
		{ id: 'remove', dependsOn: ['add'], target: { status: 'resolved', selector: { entryId: gamma.entryId, startByte: gamma.startByte, endByte: gamma.endByte, textSha256: gamma.textSha256, documentSha256: source.documentSha256 } }, candidateSha256: sha256(spliceDisjoint(source.documentBytes, [changeEdit, insertEdit, deleteEdit])), op: 'delete' },
	];
	const plan = { source: sourceIdentity(source), orderedBlockIds: ['change', 'add', 'remove'], blocks, mergeGroups: [] };
	const byId = { change: 'Alpha rewritten.', add: '\n\nInserted after beta.', remove: '' };
	const result = await v2.composeSuccessorBlockCandidate(plan, source, ({ block }) => byId[block.id]);
	assert.equal(result.status, 'composed', JSON.stringify(result));
	const text = result.candidateBytes.toString('utf8');
	assert.ok(text.includes('Alpha rewritten.'));
	assert.equal(text.includes('Alpha section.'), false);
	assert.ok(text.includes('Beta section.'), 'beta itself untouched -- only an insert splice happened at its boundary');
	assert.ok(text.includes('Inserted after beta.'));
	assert.equal(text.includes('Gamma section.'), false, 'gamma is deleted');
	void candidateHashThrough;
});

test('block-plan: a zero-width insert target at a fresh anchor boundary preflights ready; a drifted anchor makes it BLOCK_TARGET_STALE', async () => {
	const { source, alpha } = fixture();
	const point = alpha.endByte;
	const fresh = { status: 'resolved', selector: { entryId: alpha.entryId, startByte: point, endByte: point, textSha256: EMPTY_SHA256, documentSha256: source.documentSha256 } };
	const readyPlan = { source: sourceIdentity(source), orderedBlockIds: ['ins'], blocks: [{ id: 'ins', dependsOn: [], target: fresh, candidateSha256: sha256(Buffer.from('x')), op: 'insert' }], mergeGroups: [] };
	assert.equal(v2.preflightSuccessorBlockPlan(readyPlan, source).status, 'ready');

	const drifted = { status: 'resolved', selector: { entryId: alpha.entryId, startByte: point + 1, endByte: point + 1, textSha256: EMPTY_SHA256, documentSha256: source.documentSha256 } };
	const stalePlan = { ...readyPlan, blocks: [{ ...readyPlan.blocks[0], target: drifted }] };
	const stale = v2.preflightSuccessorBlockPlan(stalePlan, source);
	assert.equal(stale.status, 'blocked');
	assert.deepEqual(stale.diagnostics.map((d) => d.code), ['BLOCK_TARGET_STALE']);
});

test('types: parseProposedEdit recognizes bounded insert/delete shapes and rejects malformed ones', () => {
	const insert = v2.parseProposedEdit({ kind: 'insert', anchorEntryId: 'paragraph:a', position: 'after', content: 'New content.' });
	assert.deepEqual(insert, { kind: 'insert', anchorEntryId: 'paragraph:a', position: 'after', content: 'New content.' });
	assert.equal(v2.parseProposedEdit({ kind: 'insert', anchorEntryId: 'paragraph:a', position: 'after', content: '' }), undefined, 'empty insert content is rejected');
	assert.equal(v2.parseProposedEdit({ kind: 'insert', anchorEntryId: 'paragraph:a', position: 'sideways', content: 'x' }), undefined, 'invalid position is rejected');

	const del = v2.parseProposedEdit({ kind: 'delete', targetEntryId: 'paragraph:a', instructionEvidence: 'elimina este parrafo', reason: 'Obsolete claim.' });
	assert.deepEqual(del, { kind: 'delete', targetEntryId: 'paragraph:a', instructionEvidence: 'elimina este parrafo', reason: 'Obsolete claim.' });
	assert.equal(v2.parseProposedEdit({ kind: 'delete', targetEntryId: 'paragraph:a', instructionEvidence: '', reason: 'x' }), undefined, 'empty instructionEvidence is rejected');
	// SLICE 2 update (documented, not weakened): move/copy are now recognized --
	// see tests/paper-proposal-deliberated-move-copy.test.mjs for full coverage.
	// This assertion moved from "rejected" to "recognized" to reflect that.
	assert.deepEqual(
		v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['a'], destinationAnchorId: 'b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }),
		{ kind: 'move', sourceEntryIds: ['a'], destinationAnchorId: 'b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' },
	);
});

// --- Section B: capture -- deriveProposedEdit via ScientificWorkflowService.candidate() --

function event(sequence, eventId, type, threadId, actor, payload, causalEventIds) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:${String(sequence).padStart(2, '0')}:00.000Z`, actor: { kind: actor }, type, threadId, causalEventIds, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}
const tutorAssessment = (overrides = {}) => ({
	decision: 'ACCEPT_WITH_REVISIONS',
	summary: 'Bounded accepted synthesis.',
	mathematicalIssues: [], notationIssues: [], assumptionIssues: [],
	requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW',
	affectedEntryIds: [],
	...overrides,
});
const reviewerAssessment = (overrides = {}) => ({
	decision: 'APPROVE', scientificCoherence: 'Coherent.', scopeCompliance: 'Within scope.',
	unsupportedClaims: [], referenceRisks: [], notationRisks: [], requiredChanges: [], unresolvedQuestions: [], riskLevel: 'LOW',
	...overrides,
});

async function serviceFixture({ tutorResults, reviewerResults = [reviewerAssessment()], documentFragments = [], instruction = 'Synthesize this bounded scientific question.' } = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-deliberated-'));
	const store = new v2.ScientificStateStore(projectRoot);
	const initialEvent = event(1, 'thread-created', 'THREAD_CREATED', 'thread-1', 'USER', { title: 'Bounded question', summary: 'Public thread summary.', activeThreadId: 'thread-1' }, []);
	const thread = { threadId: 'thread-1', version: 1, status: 'OPEN', title: 'Bounded question', summary: 'Public thread summary.', createdEventId: 'thread-created', headEventId: 'thread-created', relationIds: [], decisionIds: [] };
	await store.commitTransition({ events: [initialEvent], snapshot: { schemaVersion: 1, activeThreadId: 'thread-1', threads: [thread], relations: [], decisions: [] } });
	let id = 0;
	const service = new v2.ScientificWorkflowService({
		store,
		contextBuilder: { build: async (input) => ({ schemaVersion: 1, act: input.act, activeThread: { threadId: input.activeThread.threadId, status: input.activeThread.status, title: input.activeThread.title, summary: input.activeThread.summary }, relatedThreads: [], evidence: [], documentFragments, limits: { maxRelatedThreads: 4, maxEvidence: 12, maxDocumentFragments: 4, maxBytes: 64_000 }, byteCount: 128, privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } }) },
		tutor: { assess: async () => tutorResults.shift() },
		reviewer: { review: async () => reviewerResults.shift() },
		newId: () => `event-${++id}`,
		now: () => new Date('2026-01-02T00:00:00.000Z'),
	});
	const input = { activeThread: thread, requestedDirectRelationIds: [], act: 'SYNTHESIZE', instruction };
	return { projectRoot, store, service, input, thread };
}

const fragment = (entryId, text = 'Original text.') => ({ entryId, type: 'paragraph', text, textSha256: 'a'.repeat(64), headingPath: [], revision: { filename: 'lifecycle-v1:x', revision: 'working', documentSha256: 'b'.repeat(64) } });

test('capture: a user instruction parsed as INSERT ("agrega/inserta") lifts a real kind:"insert" EditAction, content from the tutor, never guessed by the tutor', async () => {
	const run = await serviceFixture({
		instruction: 'Agrega una nueva oración después de este párrafo explicando el supuesto.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT_WITH_REVISIONS', affectedEntryIds: ['paragraph:anchor-1'], proposedAlternative: 'La nueva oración explicando el supuesto.' })],
		documentFragments: [fragment('paragraph:anchor-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	assert.deepEqual(result.candidate.proposedEdit, { kind: 'insert', anchorEntryId: 'paragraph:anchor-1', position: 'after', content: 'La nueva oración explicando el supuesto.' });
});

test('capture: a user instruction parsed as DELETE ("elimina/borra") lifts a real kind:"delete" EditAction with no tutor-authored content', async () => {
	const run = await serviceFixture({
		instruction: 'Elimina este párrafo, ya no es relevante para el argumento.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT', affectedEntryIds: ['paragraph:target-1'], summary: 'Removes an obsolete claim; safe to delete.' })],
		documentFragments: [fragment('paragraph:target-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	assert.equal(result.candidate.proposedEdit.kind, 'delete');
	assert.equal(result.candidate.proposedEdit.targetEntryId, 'paragraph:target-1');
	assert.equal(result.candidate.proposedEdit.reason, 'Removes an obsolete claim; safe to delete.');
	assert.ok(result.candidate.proposedEdit.instructionEvidence.length > 0);
});

test('capture: a DELETE instruction the tutor REJECTs or asks to clarify never becomes a delete proposedEdit (tutor can refute, never author, the operation)', async () => {
	const rejected = await serviceFixture({
		instruction: 'Elimina este párrafo completo.',
		tutorResults: [tutorAssessment({ decision: 'REJECT_WITH_REASON', affectedEntryIds: ['paragraph:target-1'], summary: 'This paragraph is load-bearing; deletion would break the argument.' })],
		documentFragments: [fragment('paragraph:target-1')],
		reviewerResults: [reviewerAssessment({ decision: 'BLOCK' })],
	});
	const result = await rejected.service.synthesize(rejected.input);
	assert.equal(result.status, 'blocked');
});

test('capture: a plain CHANGE instruction (not INSERT/DELETE) still produces the pre-existing kind:"replace" EditAction, unchanged', async () => {
	const run = await serviceFixture({
		instruction: 'Cambia este párrafo para que sea más preciso.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT_WITH_REVISIONS', affectedEntryIds: ['paragraph:target-1'], proposedAlternative: 'A more precise statement of the claim.' })],
		documentFragments: [fragment('paragraph:target-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	assert.deepEqual(result.candidate.proposedEdit, { kind: 'replace', targetEntryId: 'paragraph:target-1', replacementText: 'A more precise statement of the claim.' });
});

// --- Section C: coexistence -- CHANGE + ADD + DELETE at distinct loci, ONE version ------

async function withTempRoot(run) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-deliberated-live-'));
	try {
		return await run(projectRoot);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
}
function decisionEvents({ id, threadId, summary, proposedEdit, sequenceStart }) {
	const synthesisDigest = digest({ synthesisId: `synthesis-${id}`, threadId, summary, proposedEdit });
	const tutorPayload = { status: 'DRAFT', summary, synthesisId: `synthesis-${id}`, synthesisDigest, ...(proposedEdit ? { proposedEdit } : {}) };
	return {
		synthesisDigest,
		events: [
			event(sequenceStart, `tutor-${id}`, 'TUTOR_ASSESSED', threadId, 'TUTOR', tutorPayload, [`created-${id}`]),
			event(sequenceStart + 1, `review-${id}`, 'CONCEPTUAL_REVIEW_RECORDED', threadId, 'CONCEPTUAL_REVIEWER', { status: 'PASS', synthesisId: `synthesis-${id}`, synthesisDigest }, [`tutor-${id}`]),
			event(sequenceStart + 2, `accepted-${id}`, 'DECISION_ACCEPTED', threadId, 'USER', { decisionId: `decision-${id}`, synthesisId: `synthesis-${id}`, synthesisDigest, status: 'ACCEPTED_UNMATERIALIZED' }, [`review-${id}`]),
		],
	};
}
async function materialize({ baseContent, decisions, workspaceId = 'workspace-1' }) {
	return withTempRoot(async (projectRoot) => {
		const lifecycle = new v2.LifecycleService(projectRoot);
		const registered = await lifecycle.registerBaseDocument({ workspaceId, requestId: 'register-base', baseDocumentId: 'base-1', content: baseContent });
		assert.equal(registered.outcome, 'COMMITTED');
		const store = new v2.ScientificStateStore(projectRoot);
		const threads = [];
		const allDecisions = [];
		let allEvents = [];
		let sequence = 1;
		for (const d of decisions) {
			allEvents.push(event(sequence, `created-${d.id}`, 'THREAD_CREATED', `thread-${d.id}`, 'USER', { title: `Question ${d.id}`, summary: `Public summary ${d.id}.`, activeThreadId: `thread-${d.id}` }, []));
			sequence += 1;
			const built = decisionEvents({ id: d.id, threadId: `thread-${d.id}`, summary: d.summary, proposedEdit: d.proposedEdit, sequenceStart: sequence });
			allEvents = allEvents.concat(built.events);
			sequence += 3;
			threads.push({ threadId: `thread-${d.id}`, version: 1, status: 'ACCEPTED_UNMATERIALIZED', title: `Question ${d.id}`, summary: `Public summary ${d.id}.`, createdEventId: `created-${d.id}`, headEventId: `accepted-${d.id}`, relationIds: [], decisionIds: [`decision-${d.id}`] });
			allDecisions.push({ decisionId: `decision-${d.id}`, threadId: `thread-${d.id}`, acceptedEventId: `accepted-${d.id}`, acceptedSynthesisDigest: built.synthesisDigest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: [`tutor-${d.id}`, `review-${d.id}`] });
		}
		await store.commitTransition({ events: allEvents, snapshot: { schemaVersion: 1, activeThreadId: threads[0].threadId, threads, relations: [], decisions: allDecisions } });

		const runtime = new v2.ScientificWorkflowRuntime(projectRoot, {}, {}, { lifecycleV1WorkspaceId: workspaceId });
		const result = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: decisions.map((d) => `decision-${d.id}`) });
		assert.equal(result.status, 'materialized', JSON.stringify(result));
		const inventory = await lifecycle.rebuildLifecycleInventory(workspaceId);
		const active = inventory.revisions.find((revision) => revision.revisionId === result.materialization.targetRevision);
		assert.ok(active, 'materialized revision must exist in the lifecycle inventory');
		return { active, baseContent, projectRoot };
	});
}

test('coexistence: a CHANGE + an ADD + a DELETE at three distinct loci splice into ONE materialized version, byte-preserving', async () => {
	const baseContent = '# Energy Identity\n\nBaseline informal statement without display math.\n\n# Momentum Relation\n\nBaseline momentum statement, to be removed.\n\n# Notation\n\nStable notation paragraph, never touched.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const energyParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Baseline informal'));
	const momentumParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Baseline momentum'));
	const notationParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Stable notation'));
	assert.ok(energyParagraph && momentumParagraph && notationParagraph);

	const { active } = await materialize({
		baseContent,
		// Ordered so `decision-<id>` is already lexicographically sorted (a required
		// invariant of `reserveMaterialization`'s frozen selection) -- unrelated to
		// splice order, which is independently determined by each locus's byte offset.
		decisions: [
			{ id: 'add', summary: 'Add a clarifying remark after the notation paragraph.', proposedEdit: { kind: 'insert', anchorEntryId: notationParagraph.entryId, position: 'after', content: '\n\nClarifying remark: symbols follow standard conventions.\n' } },
			{ id: 'change', summary: 'Energy identity revision.', proposedEdit: { kind: 'replace', targetEntryId: energyParagraph.entryId, replacementText: 'The energy identity is E=mc^2.' } },
			{ id: 'delete', summary: 'Remove the obsolete momentum paragraph.', proposedEdit: { kind: 'delete', targetEntryId: momentumParagraph.entryId, instructionEvidence: 'elimina este parrafo', reason: 'Superseded by a later section.' } },
		],
	});

	assert.equal(active.content.includes('The energy identity is E=mc^2.'), true, 'the CHANGE is applied');
	assert.equal(active.content.includes('Baseline informal statement without display math.'), false);
	assert.equal(active.content.includes('Clarifying remark: symbols follow standard conventions.'), true, 'the ADD is applied');
	assert.equal(active.content.includes('Stable notation paragraph, never touched.'), true, 'the ADD anchor entry itself is untouched');
	assert.equal(active.content.includes('Baseline momentum statement, to be removed.'), false, 'the DELETE removed its span');
	assert.equal(active.content.includes('# Momentum Relation'), true, 'only the paragraph was deleted -- the surrounding heading survives');
	assert.doesNotMatch(active.content, /> Accepted revision:/, 'all three decisions are applied as real structured edits, never annotations');
	assert.doesNotMatch(active.content, /## Accepted scientific decisions/, 'no claim was pushed to the summary tail block -- all three fully resolved structurally');
});

test('coexistence: a boundary-adjacent insert/delete pair (insert placed immediately before the same paragraph the delete removes) is NOT an overlap -- both apply structurally, disjointly', async () => {
	const baseContent = '# Section\n\nA single paragraph that both an insert and a delete target.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const paragraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph');
	assert.ok(paragraph);

	const { active } = await materialize({
		baseContent,
		decisions: [
			{ id: 'delete', summary: 'Delete the paragraph.', proposedEdit: { kind: 'delete', targetEntryId: paragraph.entryId, instructionEvidence: 'elimina', reason: 'Obsolete.' } },
			{ id: 'insert', summary: 'Insert before the same paragraph, which the delete also targets.', proposedEdit: { kind: 'insert', anchorEntryId: paragraph.entryId, position: 'before', content: 'Would-be inserted text.' } },
		],
	});

	// A zero-width insert exactly at the delete's own span START is boundary-
	// adjacent, not strictly inside it -- per the composite engine's own overlap
	// rule (mirrors `BLOCK_TARGET_OVERLAP`'s semantics), so both apply: the
	// paragraph is removed and the insert lands at its frozen boundary. Nothing
	// is silently corrupted, duplicated, or force-applied at the wrong offset --
	// see the dedicated tie-break fix in `spliceDisjoint`/`spliceDisjointForSuccessorLocus`.
	assert.equal(active.content.includes('Would-be inserted text.'), true);
	assert.equal(active.content.includes('A single paragraph that both an insert and a delete target.'), false);
	assert.doesNotMatch(active.content, /## Accepted scientific decisions/, 'boundary-adjacent, not overlapping -- both resolve structurally');
});

test('coexistence: a TRUE overlap (replace and delete both targeting the exact same entry span) is never silently applied -- both degrade to the summary tail block', async () => {
	const baseContent = '# Section\n\nA single paragraph targeted by two colliding decisions.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const paragraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph');
	assert.ok(paragraph);

	const { active } = await materialize({
		baseContent,
		decisions: [
			{ id: 'change', summary: 'Replace the paragraph.', proposedEdit: { kind: 'replace', targetEntryId: paragraph.entryId, replacementText: 'Replacement text.' } },
			{ id: 'delete', summary: 'Delete the same paragraph.', proposedEdit: { kind: 'delete', targetEntryId: paragraph.entryId, instructionEvidence: 'elimina', reason: 'Obsolete.' } },
		],
	});

	assert.equal(active.content.includes('Replacement text.'), false, 'the colliding replace is never silently applied');
	assert.equal(active.content.includes('A single paragraph targeted by two colliding decisions.'), true, 'the colliding delete is never silently applied either -- the original span survives as an untouched prefix');
	assert.match(active.content, /## Accepted scientific decisions/, 'both colliding decisions degrade to the shared tail block');
	assert.equal(active.content.includes('Replace the paragraph.'), true, 'neither decision is silently lost');
	assert.equal(active.content.includes('Delete the same paragraph.'), true, 'neither decision is silently lost');
});

test('coexistence: an insert whose anchorEntryId has drifted falls back to annotation/tail-block, never a forced offset', async () => {
	const baseContent = '# Stable Section\n\nCompletely stable content, never touched by any heading-keyword match.\n';
	const summary = 'This summary intentionally shares no words with any heading in the base document xyzxyz.';
	const { active } = await materialize({
		baseContent,
		decisions: [{ id: 'a', summary, proposedEdit: { kind: 'insert', anchorEntryId: 'paragraph:this-entry-id-does-not-exist', position: 'after', content: 'Would-be inserted text, must never be silently applied at the wrong offset.' } }],
	});
	assert.equal(active.content.includes('Would-be inserted text, must never be silently applied at the wrong offset.'), false);
	assert.equal(active.content.startsWith(baseContent), true, 'the original base content is preserved as an untouched prefix when the only decision falls back');
	assert.equal(active.content.includes(summary), true, 'the decision itself is never silently lost');
});

test('coexistence: a delete whose targetEntryId has drifted falls back to annotation/tail-block, never a forced offset', async () => {
	const baseContent = '# Stable Section\n\nCompletely stable content, never touched by any heading-keyword match.\n';
	const summary = 'This other summary also intentionally shares no words with any heading xyzxyz.';
	const { active } = await materialize({
		baseContent,
		decisions: [{ id: 'a', summary, proposedEdit: { kind: 'delete', targetEntryId: 'paragraph:this-entry-id-does-not-exist', instructionEvidence: 'elimina', reason: 'Obsolete.' } }],
	});
	assert.equal(active.content.startsWith(baseContent), true, 'the original base content is preserved as an untouched prefix when the only decision falls back');
	assert.equal(active.content.includes(summary), true, 'the decision itself is never silently lost');
});

test('coexistence: an old-style summary-only decision (no proposedEdit) still annotates exactly as before, even alongside this batch\'s new kinds', async () => {
	const baseContent = '# Energy identity\n\nBaseline informal statement without display math.\n';
	const summary = 'The energy identity should state E=mc^2 explicitly.';
	const { active } = await materialize({ baseContent, decisions: [{ id: 'a', summary }] });
	assert.match(active.content, /> Accepted revision: /, 'summary-only decisions still fall back to the pre-existing locus-scoped annotation');
	assert.equal(active.content.includes(summary), true);
});

// --- Section D: SuccessorEditPlanner (secondary/filename-era route) -------------------

test('SuccessorEditPlanner emits a real "insert" action for a structural insert claim, and marks destructiveIntent for a structural delete claim', async () => {
	const base = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Introduction\n\nOriginal introduction text.\n\n# Method\n\nOriginal method text.\n'));
	const introParagraph = base.structuralIndex.entries.find((e) => e.type === 'paragraph' && e.headingPath?.includes?.('Introduction'));
	const methodParagraph = base.structuralIndex.entries.find((e) => e.type === 'paragraph' && e.headingPath?.includes?.('Method'));
	assert.ok(introParagraph && methodParagraph);
	const expectedRevision = { filename: base.filename, revision: base.revision, documentSha256: base.documentSha256 };

	const insertOnly = new v2.SuccessorEditPlanner().plan({
		base, expectedRevision,
		acceptedDecisions: [{ claimId: 'claim-a', decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: 'digest-a', summary: 'Add a remark after the introduction.', proposedEdit: { kind: 'insert', anchorEntryId: introParagraph.entryId, position: 'after', content: '\n\nA clarifying remark.\n' } }],
	});
	assert.deepEqual(insertOnly.patches[0].plan.actions, [{ kind: 'insert', anchorEntryId: introParagraph.entryId, position: 'after', content: '\n\nA clarifying remark.\n' }]);
	assert.equal(insertOnly.patches[0].plan.destructiveIntent, false);

	const deleteOnly = new v2.SuccessorEditPlanner().plan({
		base, expectedRevision,
		acceptedDecisions: [{ claimId: 'claim-b', decisionId: 'decision-b', threadId: 'thread-b', acceptedEventId: 'accepted-b', acceptedSynthesisDigest: 'digest-b', summary: 'Delete the obsolete method paragraph.', proposedEdit: { kind: 'delete', targetEntryId: methodParagraph.entryId, instructionEvidence: 'elimina', reason: 'Obsolete.' } }],
	});
	assert.deepEqual(deleteOnly.patches[0].plan.actions, [{ kind: 'delete', targetEntryId: methodParagraph.entryId, instructionEvidence: 'elimina', reason: 'Obsolete.' }]);
	assert.equal(deleteOnly.patches[0].plan.destructiveIntent, true, 'a structural delete action requires destructiveIntent so patch-compiler authorizes it');
});
