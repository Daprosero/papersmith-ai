// proposal-deliberation-tutor-repair (deliberated-operations, SLICE 2): deliberated
// MOVE and COPY applied byte-preservingly, and the SEPARATE-VERSION grouping
// rule -- accepted in-place edits (change/insert/delete) materialize into ONE
// version, accepted relocations (move/copy) materialize into a SEPARATE
// version, produced in sequence within the same open deliberation -- per
// design `sdd/proposal-deliberation-tutor-repair/design-deliberated-operations` and
// locked decisions (obs #551).
//
// Covers, bottom-up:
//   A. types + block-plan primitives: parseProposedEdit recognizes bounded
//      move/copy shapes and rejects malformed ones; two zero-width inserts at
//      the identical offset need explicit dependsOn ordering or are rejected
//      as ambiguous (deferred from SLICE 1).
//   B. capture: `ScientificWorkflowService.candidate()`/`deriveProposedEdit`
//      lifts a deliberated MOVE/COPY from the USER's own instruction (via
//      `resolveIntent`), never invented by the tutor; ADAPTIVE content comes
//      from the tutor and is never fabricated when absent.
//   C. materialization: a MOVE relocates a section byte-preserving into a
//      SEPARATE successor version from a coexisting in-place CHANGE; a COPY
//      duplicates without removing the source; self/cycle/drift all fall
//      back safely, never forced or lost.
//   (Section D -- production-tutor-adapter.ts's TUTOR_PROMPT documenting
//   move/copy -- was removed in design `sdd/proposal-deliberation-ambient-model`
//   SLICE 2 along with the production adapter itself.)
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
const v2 = await jiti.import(path.join(root, '.claude/skills/proposal-deliberation/engine/exports.ts'));

const sha256 = (value) => createHash('sha256').update(value).digest('hex');
const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const EMPTY_SHA256 = sha256(Buffer.alloc(0));

// --- Section A: types + block-plan primitives --------------------------------------

test('types: parseProposedEdit recognizes bounded move/copy shapes and rejects malformed ones', () => {
	const literalMove = v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' });
	assert.deepEqual(literalMove, { kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' });

	const literalCopy = v2.parseProposedEdit({ kind: 'copy', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'before', moveMode: 'LITERAL', removeSource: false, cleanupLevel: 'NONE' });
	assert.deepEqual(literalCopy, { kind: 'copy', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'before', moveMode: 'LITERAL', removeSource: false, cleanupLevel: 'NONE' });

	const adaptiveMove = v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'ADAPTIVE', removeSource: true, cleanupLevel: 'NONE', transformedContent: 'Reworded transition text.' });
	assert.deepEqual(adaptiveMove, { kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'ADAPTIVE', removeSource: true, cleanupLevel: 'NONE', transformedContent: 'Reworded transition text.' });

	// Never fabricate: an ADAPTIVE relocation MUST carry transformedContent -- absent, it is rejected outright (not silently treated as LITERAL).
	assert.equal(v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'ADAPTIVE', removeSource: true, cleanupLevel: 'NONE' }), undefined, 'ADAPTIVE without transformedContent is rejected');
	// removeSource must agree with kind -- a mismatched combination is malformed, not silently trusted.
	assert.equal(v2.parseProposedEdit({ kind: 'copy', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }), undefined, 'copy with removeSource:true is rejected');
	assert.equal(v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'LITERAL', removeSource: false, cleanupLevel: 'NONE' }), undefined, 'move with removeSource:false is rejected');
	// Bounded to exactly one source entry for this slice.
	assert.equal(v2.parseProposedEdit({ kind: 'move', sourceEntryIds: [], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }), undefined, 'empty sourceEntryIds is rejected');
	assert.equal(v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['paragraph:a', 'paragraph:c'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }), undefined, 'multi-entry sourceEntryIds is rejected (deferred fallback)');
	assert.equal(v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'sideways', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }), undefined, 'invalid position is rejected');
	assert.equal(v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'SOMETHING_ELSE', removeSource: true, cleanupLevel: 'NONE' }), undefined, 'invalid moveMode is rejected');
	assert.equal(v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['paragraph:a'], destinationAnchorId: 'paragraph:b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'BOGUS' }), undefined, 'invalid cleanupLevel is rejected');
});

test('block-plan: two zero-width insert blocks at the IDENTICAL offset require explicit dependsOn ordering, else rejected as ambiguous (BLOCK_INSERT_ORDER_AMBIGUOUS)', () => {
	const documentBytes = Buffer.from('Alpha section.\n\nBeta section.\n');
	const point = documentBytes.indexOf('\n\nBeta');
	const alphaEntry = { entryId: 'anchor', type: 'section', startByte: 0, endByte: point, textSha256: sha256(documentBytes.subarray(0, point)) };
	const source = { filename: 'lifecycle-v1:x', revision: 'working', documentBytes, documentSha256: sha256(documentBytes), structuralIndex: { entries: [alphaEntry], byId: { [alphaEntry.entryId]: alphaEntry } } };
	const target = { status: 'resolved', selector: { entryId: 'anchor', startByte: point, endByte: point, textSha256: EMPTY_SHA256, documentSha256: source.documentSha256 } };
	const blockA = { id: 'insert-a', dependsOn: [], target, candidateSha256: sha256(Buffer.from('irrelevant-a')), op: 'insert' };
	const blockB = { id: 'insert-b', dependsOn: [], target, candidateSha256: sha256(Buffer.from('irrelevant-b')), op: 'insert' };
	const sourceIdentity = { filename: source.filename, revision: source.revision, documentSha256: source.documentSha256 };

	const withoutOrder = v2.preflightSuccessorBlockPlan({ source: sourceIdentity, orderedBlockIds: ['insert-a', 'insert-b'], blocks: [blockA, blockB], mergeGroups: [] }, source);
	assert.equal(withoutOrder.status, 'blocked');
	assert.deepEqual(withoutOrder.diagnostics.map((d) => d.code), ['BLOCK_INSERT_ORDER_AMBIGUOUS']);

	const withOrder = v2.preflightSuccessorBlockPlan({ source: sourceIdentity, orderedBlockIds: ['insert-a', 'insert-b'], blocks: [blockA, { ...blockB, dependsOn: ['insert-a'] }], mergeGroups: [] }, source);
	assert.equal(withOrder.status, 'ready', JSON.stringify(withOrder));
});

// --- Section B: capture -- deriveProposedEdit via ScientificWorkflowService.candidate() --

function event(sequence, eventId, type, threadId, actor, payload, causalEventIds) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:${String(sequence).padStart(2, '0')}:00.000Z`, actor: { kind: actor }, type, threadId, causalEventIds, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}
const tutorAssessment = (overrides = {}) => ({
	decision: 'ACCEPT',
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
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-deliberated-mc-'));
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

test('capture: a user instruction parsed as MOVE ("mueve...antes de") lifts a real kind:"move" LITERAL EditAction, no tutor-authored content, source/destination in the exact order the tutor supplied', async () => {
	const run = await serviceFixture({
		instruction: 'Mueve este párrafo antes de la sección de conclusión.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT', affectedEntryIds: ['paragraph:source-1', 'paragraph:dest-1'], summary: 'Relocation improves the argument flow.' })],
		documentFragments: [fragment('paragraph:source-1'), fragment('paragraph:dest-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	assert.deepEqual(result.candidate.proposedEdit, { kind: 'move', sourceEntryIds: ['paragraph:source-1'], destinationAnchorId: 'paragraph:dest-1', position: 'before', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' });
});

test('capture: a user instruction parsed as COPY ("copia...después de") lifts a real kind:"copy" LITERAL EditAction with removeSource:false', async () => {
	const run = await serviceFixture({
		instruction: 'Copia este párrafo después de la introducción, conservando el original.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT_WITH_REVISIONS', affectedEntryIds: ['paragraph:source-1', 'paragraph:dest-1'], summary: 'Duplicating this content is useful for both sections.' })],
		documentFragments: [fragment('paragraph:source-1'), fragment('paragraph:dest-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	assert.deepEqual(result.candidate.proposedEdit, { kind: 'copy', sourceEntryIds: ['paragraph:source-1'], destinationAnchorId: 'paragraph:dest-1', position: 'after', moveMode: 'LITERAL', removeSource: false, cleanupLevel: 'NONE' });
});

test('capture: an ADAPTIVE move ("adapta la transición") lifts transformedContent from the tutor\'s proposedAlternative', async () => {
	const run = await serviceFixture({
		instruction: 'Mueve este párrafo después de la sección de resultados y adapta la transición.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT_WITH_REVISIONS', affectedEntryIds: ['paragraph:source-1', 'paragraph:dest-1'], proposedAlternative: 'Reworded so the transition fits its new context.' })],
		documentFragments: [fragment('paragraph:source-1'), fragment('paragraph:dest-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	// Note: the same phrase "adapta la transición" that signals ADAPTIVE mode is
	// ALSO one of `resolveIntent`'s pre-existing SEMANTIC cleanup-level keywords
	// (unrelated to this slice) -- so cleanupLevel is 'SEMANTIC' here, carried
	// through from `resolved.cleanupLevel` unchanged, not invented by this slice.
	assert.deepEqual(result.candidate.proposedEdit, { kind: 'move', sourceEntryIds: ['paragraph:source-1'], destinationAnchorId: 'paragraph:dest-1', position: 'after', moveMode: 'ADAPTIVE', removeSource: true, cleanupLevel: 'SEMANTIC', transformedContent: 'Reworded so the transition fits its new context.' });
});

test('capture: an ADAPTIVE move with a >2000-byte reworded body survives persistence -- the raised cap covers transformedContent, not only replacementText/content', async () => {
	const largeBody = 'Reworded transition sentence. '.repeat(100); // 3000 bytes: within the 2000<n<=20000 window
	assert.ok(largeBody.length > 2_000 && largeBody.length <= 20_000, 'fixture body must exercise the 2000<n<=20000 window');
	const run = await serviceFixture({
		instruction: 'Mueve este párrafo después de la sección de resultados y adapta la transición.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT_WITH_REVISIONS', affectedEntryIds: ['paragraph:source-1', 'paragraph:dest-1'], proposedAlternative: largeBody })],
		documentFragments: [fragment('paragraph:source-1'), fragment('paragraph:dest-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	// The fix under test: the >2000-byte body must SURVIVE persistence (not be
	// dropped to undefined by the 2000-byte privacy guard). Content is stored
	// trimmed, so assert survival + size rather than exact bytes.
	assert.ok(result.candidate.proposedEdit, 'a >2000-byte ADAPTIVE body must not be dropped by the persistence privacy guard');
	assert.equal(result.candidate.proposedEdit.kind, 'move');
	assert.ok(result.candidate.proposedEdit.transformedContent.length > 2_000, 'the reworded body over 2000 bytes must persist intact, not be truncated/dropped');
	assert.ok(result.candidate.proposedEdit.transformedContent.startsWith('Reworded transition sentence.'));
});

test('capture: an ADAPTIVE move whose tutor never supplies proposedAlternative never fabricates content -- no proposedEdit at all, never a guessed LITERAL fallback', async () => {
	const run = await serviceFixture({
		instruction: 'Mueve este párrafo después de la sección de resultados y adapta la transición.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT_WITH_REVISIONS', affectedEntryIds: ['paragraph:source-1', 'paragraph:dest-1'] })],
		documentFragments: [fragment('paragraph:source-1'), fragment('paragraph:dest-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	assert.equal(result.candidate.proposedEdit, undefined, 'blocked rather than fabricated -- the decision still reviews, just carries no structured edit');
});

test('capture: a MOVE/COPY instruction whose tutor supplies the wrong number of affectedEntryIds (not exactly [source, destination]) never becomes a move/copy proposedEdit', async () => {
	const run = await serviceFixture({
		instruction: 'Mueve este párrafo antes de la sección de conclusión.',
		tutorResults: [tutorAssessment({ decision: 'ACCEPT', affectedEntryIds: ['paragraph:source-1'] })],
		documentFragments: [fragment('paragraph:source-1')],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	assert.equal(result.candidate.proposedEdit, undefined);
});

// --- Section C: materialization -- SEPARATE-VERSION grouping + relocation resolution ----

async function withTempRoot(run) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-deliberated-mc-live-'));
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
/** Materializes a batch of decisions and returns the full lifecycle inventory plus the runtime's own result. */
async function materializeBatch({ baseContent, decisions, workspaceId = 'workspace-1' }) {
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

		const runtime = new v2.ScientificWorkflowRuntime(projectRoot, {}, { lifecycleV1WorkspaceId: workspaceId });
		const result = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: decisions.map((d) => `decision-${d.id}`) });
		const inventory = await lifecycle.rebuildLifecycleInventory(workspaceId);
		return { result, inventory, baseContent, projectRoot };
	});
}

test('materialization: an accepted CHANGE and an accepted MOVE in ONE materialize() call produce TWO distinct successor versions -- never spliced into the same version', async () => {
	const baseContent = '# Alpha\n\nAlpha original content.\n\n# Beta\n\nBeta content to relocate.\n\n# Gamma\n\nGamma content, the new home.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const alphaParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Alpha original'));
	const betaParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Beta content'));
	const gammaParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Gamma content'));
	assert.ok(alphaParagraph && betaParagraph && gammaParagraph);

	const { result, inventory } = await materializeBatch({
		baseContent,
		decisions: [
			{ id: 'change', summary: 'Alpha revision.', proposedEdit: { kind: 'replace', targetEntryId: alphaParagraph.entryId, replacementText: 'Alpha revised content.' } },
			{ id: 'move', summary: 'Relocate Beta content next to Gamma.', proposedEdit: { kind: 'move', sourceEntryIds: [betaParagraph.entryId], destinationAnchorId: gammaParagraph.entryId, position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' } },
		],
	});
	assert.equal(result.status, 'materialized', JSON.stringify(result));

	// Exactly TWO new revisions were produced from the base, chained in sequence.
	assert.equal(inventory.revisions.length, 2, JSON.stringify(inventory.revisions.map((r) => r.revisionId)));
	const revisionOne = inventory.revisions.find((r) => r.lineage.sourceKind === 'BASE_DOCUMENT');
	const revisionTwo = inventory.revisions.find((r) => r.lineage.sourceKind === 'REVISION');
	assert.ok(revisionOne && revisionTwo, 'one revision must chain from the base, the other from the first revision');
	assert.equal(revisionTwo.lineage.sourceId, revisionOne.revisionId, 'the relocation version is built ON TOP of the in-place version, not the raw base');
	assert.equal(result.materialization.targetRevision, revisionTwo.revisionId, 'the reported materialized version is the final one in the chain');

	// Version 1 (in-place): the CHANGE applied, Beta/Gamma untouched -- the relocation has NOT happened yet.
	assert.equal(revisionOne.content.includes('Alpha revised content.'), true);
	assert.equal(revisionOne.content.includes('Beta content to relocate.'), true, 'version 1 has not relocated Beta yet');
	assert.ok(revisionOne.content.indexOf('Beta content to relocate.') < revisionOne.content.indexOf('Gamma content, the new home.'), 'version 1: Beta is still before Gamma');

	// Version 2 (relocation, on top of version 1): the CHANGE survives, Beta has moved after Gamma.
	assert.equal(revisionTwo.content.includes('Alpha revised content.'), true, 'the in-place CHANGE from version 1 is carried forward');
	assert.equal(revisionTwo.content.includes('Beta content to relocate.'), true, 'the relocated content itself is preserved byte-for-byte (LITERAL)');
	assert.ok(revisionTwo.content.indexOf('Gamma content, the new home.') < revisionTwo.content.indexOf('Beta content to relocate.'), 'version 2: Beta now appears AFTER Gamma');
	// The original Beta heading/location no longer immediately precedes Gamma's heading.
	assert.doesNotMatch(revisionTwo.content, /Beta content to relocate\.\n\n# Gamma/, 'Beta is no longer in its original position, immediately before Gamma');
});

test('materialization: a lone accepted COPY duplicates the source at the destination without removing it, in ONE version', async () => {
	const baseContent = '# Notation\n\nStandard notation paragraph.\n\n# Appendix\n\nAppendix intro.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const notationParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Standard notation'));
	const appendixParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Appendix intro'));
	assert.ok(notationParagraph && appendixParagraph);

	const { result, inventory } = await materializeBatch({
		baseContent,
		decisions: [{ id: 'copy', summary: 'Repeat the notation paragraph in the appendix.', proposedEdit: { kind: 'copy', sourceEntryIds: [notationParagraph.entryId], destinationAnchorId: appendixParagraph.entryId, position: 'after', moveMode: 'LITERAL', removeSource: false, cleanupLevel: 'NONE' } }],
	});
	assert.equal(result.status, 'materialized', JSON.stringify(result));
	assert.equal(inventory.revisions.length, 1, 'a homogeneous single-decision batch still produces exactly ONE version');
	const revision = inventory.revisions[0];
	const occurrences = revision.content.split('Standard notation paragraph.').length - 1;
	assert.equal(occurrences, 2, 'the source survives AND the copy is inserted -- content appears twice');
	assert.equal(revision.content.includes('Appendix intro.'), true, 'the destination anchor itself is untouched');
});

test('materialization: MOVE source === destination falls back to annotation, never a forced no-op', async () => {
	const baseContent = '# Section\n\nA lone paragraph, self-targeted.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const paragraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph');
	assert.ok(paragraph);
	const summary = 'Move this paragraph next to itself (degenerate request).';

	const { result, inventory } = await materializeBatch({
		baseContent,
		decisions: [{ id: 'move', summary, proposedEdit: { kind: 'move', sourceEntryIds: [paragraph.entryId], destinationAnchorId: paragraph.entryId, position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' } }],
	});
	assert.equal(result.status, 'materialized', JSON.stringify(result));
	const revision = inventory.revisions[0];
	assert.equal(revision.content.startsWith(baseContent), true, 'original content preserved as an untouched prefix -- the move never silently applied');
	assert.equal(revision.content.includes(summary), true, 'the decision itself is never silently lost');
});

test('materialization: MOVE destination nested inside its own source (HIERARCHY_CYCLE) falls back to annotation, never a forced offset', async () => {
	// A single-heading document: the `section`-type entry's own raw span covers
	// its heading through the end of the document (there is no next heading to
	// stop at), so it structurally CONTAINS its own body paragraph entry --
	// exactly the HIERARCHY_CYCLE shape (moving the section to "after" a point
	// that is itself inside the section's own span).
	const baseContent = '# Outer Section\n\nBody paragraph fully inside this section, the moved subtree itself.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const outerSection = probe.structuralIndex.entries.find((e) => e.type === 'section');
	const innerParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph');
	assert.ok(outerSection && innerParagraph);
	assert.ok(innerParagraph.startByte >= outerSection.startByte && innerParagraph.endByte <= outerSection.endByte, 'fixture precondition: the inner paragraph is nested inside the outer section');
	const summary = 'Move the outer section to just after its own body paragraph (a cycle).';

	const { result, inventory } = await materializeBatch({
		baseContent,
		decisions: [{ id: 'move', summary, proposedEdit: { kind: 'move', sourceEntryIds: [outerSection.entryId], destinationAnchorId: innerParagraph.entryId, position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' } }],
	});
	assert.equal(result.status, 'materialized', JSON.stringify(result));
	const revision = inventory.revisions[0];
	assert.equal(revision.content.startsWith(baseContent), true, 'the cyclic move is never silently applied -- original content preserved as an untouched prefix');
	assert.equal(revision.content.includes(summary), true, 'the decision itself is never silently lost');
});

test('materialization: a MOVE whose sourceEntryId has drifted falls back to annotation, never a forced offset', async () => {
	const baseContent = '# Stable Section\n\nCompletely stable content, never touched by any heading-keyword match.\n';
	const summary = 'This summary intentionally shares no words with any heading in the base document xyzxyz.';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const paragraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph');
	assert.ok(paragraph);

	const { result, inventory } = await materializeBatch({
		baseContent,
		decisions: [{ id: 'move', summary, proposedEdit: { kind: 'move', sourceEntryIds: ['paragraph:this-entry-id-does-not-exist'], destinationAnchorId: paragraph.entryId, position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' } }],
	});
	assert.equal(result.status, 'materialized', JSON.stringify(result));
	const revision = inventory.revisions[0];
	assert.equal(revision.content.startsWith(baseContent), true, 'the original base content is preserved as an untouched prefix when the only decision falls back');
	assert.equal(revision.content.includes(summary), true, 'the decision itself is never silently lost');
});

test('materialization: an ADAPTIVE move persisted without transformedContent fails validation and safely falls back to annotation -- never fabricated content', async () => {
	const baseContent = '# Stable Section\n\nCompletely stable content, never touched by any heading-keyword match.\n\n# Destination\n\nDestination anchor paragraph xyzxyz.\n';
	const summary = 'This summary also intentionally shares no words with any heading xyzxyz.';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const source = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Completely stable'));
	const destination = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Destination anchor'));
	assert.ok(source && destination);

	const { result, inventory } = await materializeBatch({
		baseContent,
		// Malformed on purpose: moveMode ADAPTIVE with no transformedContent -- this
		// shape can never be produced by `deriveProposedEdit` (capture already
		// blocks it), but a persisted event must still fail closed if it ever
		// arrived malformed. `parseProposedEdit` rejects it outright, so the
		// decision degrades to the pre-existing summary-annotation fallback.
		decisions: [{ id: 'move', summary, proposedEdit: { kind: 'move', sourceEntryIds: [source.entryId], destinationAnchorId: destination.entryId, position: 'after', moveMode: 'ADAPTIVE', removeSource: true, cleanupLevel: 'NONE' } }],
	});
	assert.equal(result.status, 'materialized', JSON.stringify(result));
	const revision = inventory.revisions[0];
	assert.equal(revision.content.includes('Completely stable content, never touched by any heading-keyword match.'), true, 'source content untouched -- no relocation was silently applied');
	assert.equal(revision.content.includes(summary), true, 'the decision itself is never silently lost');
});

// Section D (production-tutor-adapter.ts's TUTOR_PROMPT documents move/copy) was
// REMOVED (design `sdd/proposal-deliberation-ambient-model`, SLICE 2): production-tutor-adapter.ts
// and its real-API transport no longer exist -- the tutor role prompt migrates to
// SKILL.md (ambient conditioning) in a later slice, not a production adapter constant.
