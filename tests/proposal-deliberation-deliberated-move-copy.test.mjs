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
const v2 = await jiti.import(path.join(root, '.claude/skills/_core/deliberation/engine/exports.ts'));

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


const fragment = (entryId, text = 'Original text.') => ({ entryId, type: 'paragraph', text, textSha256: 'a'.repeat(64), headingPath: [], revision: { filename: 'lifecycle-v1:x', revision: 'working', documentSha256: 'b'.repeat(64) } });







// --- Section C: materialization -- SEPARATE-VERSION grouping + relocation resolution ----

async function withTempRoot(run) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-deliberated-mc-live-'));
	try {
		return await run(projectRoot);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
}
/** Materializes a batch of decisions and returns the full lifecycle inventory plus the runtime's own result. */







// Section D (production-tutor-adapter.ts's TUTOR_PROMPT documents move/copy) was
// REMOVED (design `sdd/proposal-deliberation-ambient-model`, SLICE 2): production-tutor-adapter.ts
// and its real-API transport no longer exist -- the tutor role prompt migrates to
// SKILL.md (ambient conditioning) in a later slice, not a production adapter constant.
