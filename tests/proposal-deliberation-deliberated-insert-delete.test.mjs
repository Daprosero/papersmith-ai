// proposal-deliberation-tutor-repair (deliberated-operations, SLICE 1): deliberated
// ADD (insert) and DELETE applied byte-preservingly in the SAME successor
// version as an ordinary CHANGE (replace), all in-place and disjoint, per
// design `sdd/proposal-deliberation-tutor-repair/design-deliberated-operations`.
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
const v2 = await jiti.import(path.join(root, '.claude/skills/_core/deliberation/engine/exports.ts'));

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
	// see tests/proposal-deliberation-deliberated-move-copy.test.mjs for full coverage.
	// This assertion moved from "rejected" to "recognized" to reflect that.
	assert.deepEqual(
		v2.parseProposedEdit({ kind: 'move', sourceEntryIds: ['a'], destinationAnchorId: 'b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }),
		{ kind: 'move', sourceEntryIds: ['a'], destinationAnchorId: 'b', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' },
	);
});

// --- Section B: capture -- deriveProposedEdit via ScientificWorkflowService.candidate() --

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


const fragment = (entryId, text = 'Original text.') => ({ entryId, type: 'paragraph', text, textSha256: 'a'.repeat(64), headingPath: [], revision: { filename: 'lifecycle-v1:x', revision: 'working', documentSha256: 'b'.repeat(64) } });





// --- Section C: coexistence -- CHANGE + ADD + DELETE at distinct loci, ONE version ------

async function withTempRoot(run) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-deliberated-live-'));
	try {
		return await run(projectRoot);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
}







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
