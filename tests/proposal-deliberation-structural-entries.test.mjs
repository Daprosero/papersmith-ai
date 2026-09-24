// Phase 2.1 (change 6): `table` and `figure_placeholder` become first-class leaf
// entries. This is a RETYPING, not an addition -- `entryId` is `${type}:${sha256(...)}`,
// so a GFM table that used to fold into `paragraph` now carries a different id, and
// `target-resolver.ts`'s `leaf()` list must learn both new type names in the same
// change or a retyped table silently drops out of composite member selection.
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = path.resolve('.');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(path.resolve('skills/_core/deliberation/engine/exports.ts'));

// 2.1.1: the exact structural-index snapshot for a table/figure-free document, captured
// against the pre-change engine. Any drift here for a document with no tables or figures
// is a regression in the additive guarantee, not an intended change.
const NO_TABLES_DOC = '# Title\n\nIntro one-hot text.\n\n$$\nx = 1\n\\label{eq:onehot}\n\\tag{1}\n$$\n\n## Results\n\nTarget paragraph.\n';
const NO_TABLES_SNAPSHOT = [
	{ type: 'section', entryId: 'section:417cb9671b650232149e8043' },
	{ type: 'document', entryId: 'document:4d019014e32e4b451ca93e45' },
	{ type: 'paragraph', entryId: 'paragraph:129c640f63f5252b132938a1' },
	{ type: 'display_equation', entryId: 'display_equation:a946a5ccfc53e388a535e96c' },
	{ type: 'subsection', entryId: 'subsection:672031da6c2d953c21b7aace' },
	{ type: 'paragraph', entryId: 'paragraph:eebf7fb200f26909a56c63c8' },
];

test('2.1.1 buildStructuralIndex is byte-identical for a document with no tables or figures', async () => {
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(NO_TABLES_DOC));
	const actual = state.structuralIndex.entries.map(e => ({ type: e.type, entryId: e.entryId }));
	assert.deepEqual(actual, NO_TABLES_SNAPSHOT, 'the additive guarantee: nothing about a table-free document may change');
});

const TABLE_DOC = '# Results\n\nIntro line.\n\n| Metric | Value |\n| --- | --- |\n| Accuracy | 0.91 |\n\nTail line.\n';
const TABLE_MARKDOWN = '| Metric | Value |\n| --- | --- |\n| Accuracy | 0.91 |';

test('2.1.2 a GFM table is recognized as its own leaf entry, not folded into paragraph', async () => {
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(TABLE_DOC));
	const table = state.structuralIndex.entries.find(e => e.type === 'table');
	assert.ok(table, 'buildStructuralIndex must emit a `table` entry for the GFM table');
	assert.equal(v2.entryText(state, table), TABLE_MARKDOWN, 'the table entry byte span is exactly the table, no more, no less');
	assert.deepEqual(table.headingPath, ['Results']);
	assert.equal(
		state.structuralIndex.entries.some(e => e.type === 'paragraph' && v2.entryText(state, e) === TABLE_MARKDOWN),
		false,
		'the table bytes must not ALSO be claimed by a paragraph entry',
	);
	// RESOLVE_TARGET by the table's own id returns exactly the table, never the enclosing
	// section -- proving it is independently addressable, not absorbed.
	const [resolved] = v2.resolveTargets(state, table.entryId);
	assert.equal(resolved.entryId, table.entryId);
	assert.equal(resolved.type, 'table');
});

const FIGURE_DOC = '# Figures\n\nIntro line.\n\n![Figure 1: Training curves](figures/fig1.png)\n\nTail line.\n';
const FIGURE_MARKDOWN = '![Figure 1: Training curves](figures/fig1.png)';

test('2.1.3 a declared figure placeholder is recognized as its own leaf entry, not folded into paragraph', async () => {
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(FIGURE_DOC));
	const figure = state.structuralIndex.entries.find(e => e.type === 'figure_placeholder');
	assert.ok(figure, 'buildStructuralIndex must emit a `figure_placeholder` entry for the declared image reference');
	assert.equal(v2.entryText(state, figure), FIGURE_MARKDOWN);
	assert.equal(
		state.structuralIndex.entries.some(e => e.type === 'paragraph' && v2.entryText(state, e) === FIGURE_MARKDOWN),
		false,
		'the figure bytes must not ALSO be claimed by a paragraph entry',
	);
	const [resolved] = v2.resolveTargets(state, figure.entryId);
	assert.equal(resolved.entryId, figure.entryId);
	assert.equal(resolved.type, 'figure_placeholder');
});

const TWO_TABLES_DOC = '# Results\n\n| Metric | Value |\n| --- | --- |\n| Accuracy | 0.91 |\n\n| Metric | Value |\n| --- | --- |\n| Loss | 0.12 |\n';

test('2.1.4 two tables under one heading and an under-specified query still refuse correctly, now listing both tables by identity', async () => {
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(TWO_TABLES_DOC));
	const tables = state.structuralIndex.entries.filter(e => e.type === 'table');
	assert.equal(tables.length, 2, 'the fixture declares exactly two tables');
	assert.notEqual(tables[0].entryId, tables[1].entryId, 'each table carries its own identity');
	// A query that matches both tables equally (their shared header row) is under-specified.
	const candidates = v2.resolveTargets(state, 'Metric Value');
	assert.ok(candidates.some(c => c.entryId === tables[0].entryId), 'the first table must be a listed candidate');
	assert.ok(candidates.some(c => c.entryId === tables[1].entryId), 'the second table must be a listed candidate');
	const gate = v2.ambiguityGate(candidates);
	assert.equal(gate.blocked, true, 'the ambiguity gate must still refuse an under-specified query');
});

test('2.1.9 a literal composite selection spanning a table still resolves, the table counted as a member (composite materialization does not drop table bytes)', async () => {
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(TABLE_DOC));
	const table = state.structuralIndex.entries.find(e => e.type === 'table');
	const introParagraph = state.structuralIndex.entries.find(e => e.type === 'paragraph' && e.startByte < table.startByte);
	assert.ok(introParagraph, 'fixture must have a leaf entry before the table');
	const selection = state.documentBytes.subarray(introParagraph.startByte, table.endByte).toString('utf8');
	const [candidate] = v2.resolveTargets(state, selection);
	assert.ok(candidate, 'a literal selection spanning a table must resolve to a composite candidate');
	assert.equal(candidate.type, 'composite');
	assert.ok(candidate.composite.entryIds.includes(table.entryId), 'the table entry must be counted as a member, not silently dropped');
	assert.equal(candidate.composite.exactProvidedText, selection, 'the composite bytes are exactly the selected span, table included');
	// materializeCompositeTarget must accept this candidate and reproduce the exact same span.
	const materialized = v2.materializeCompositeTarget(state, candidate);
	assert.equal(materialized.startByte, candidate.composite.startByte);
	assert.equal(materialized.endByte, candidate.composite.endByte);
});

// Extra coverage (not a numbered task, but explicitly required): change 6 bumps
// PARSER_VERSION and deliberately does NOT supersede the old one, because retyping a
// table changes its entryId -- this is not a same-parse-output rename. Prove both
// halves of that mechanism: (a) a document committed under a now-unaccepted PRIOR
// parser version is silently invalidated and rebuilt, never thrown on; (b) a COMMITTED
// state that re-serializes differently under the SAME parser version -- the mistake of
// forgetting to bump the version after a real parsing change -- is refused outright.
test('2.1.6 a stale committed derived state under a prior, non-superseded parser version is invalidated and rebuilt, not thrown on', async () => {
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-structural-entries-parser-version-'));
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(NO_TABLES_DOC));
	await v2.commitDerivedState(root, state);
	await v2.saveRevisionReceipt(root, 'research-concept-r01.md', {
		targetFilename: 'research-concept-r01.md',
		targetRevision: state.revision,
		documentShaAfter: state.documentSha256,
		derivedStateStatus: 'COMMITTED',
	});
	const statePath = v2.derivedStatePath(root, 'research-concept-r01.md');
	const stored = JSON.parse(await readFile(statePath, 'utf8'));
	assert.notEqual(v2.PARSER_VERSION, 'proposal-deliberation/1', 'this test\'s premise requires PARSER_VERSION to have moved past /1');
	stored.manifest.parserVersion = 'proposal-deliberation/1';
	await writeFile(statePath, JSON.stringify(stored));
	await assert.doesNotReject(
		v2.commitDerivedState(root, state),
		'a stale, unaccepted prior parser version must not be compared against -- it is simply not recognized, and the cache is rebuilt',
	);
});

test('2.1.6b a COMMITTED state that re-serializes differently under the SAME parser version throws INCOMPATIBLE_COMMITTED_STATE', async () => {
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-structural-entries-incompatible-'));
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(NO_TABLES_DOC));
	await v2.commitDerivedState(root, state);
	await v2.saveRevisionReceipt(root, 'research-concept-r01.md', {
		targetFilename: 'research-concept-r01.md',
		targetRevision: state.revision,
		documentShaAfter: state.documentSha256,
		derivedStateStatus: 'COMMITTED',
	});
	// Same filename, same documentSha256, same parserVersion -- but a structural index that
	// re-serializes differently, simulating a parsing change that forgot to bump the version.
	const mutated = {
		...state,
		structuralIndex: {
			...state.structuralIndex,
			entries: [...state.structuralIndex.entries, { ...state.structuralIndex.entries[0], entryId: 'paragraph:deadbeefdeadbeefdeadbeef' }],
		},
	};
	await assert.rejects(v2.commitDerivedState(root, mutated), /INCOMPATIBLE_COMMITTED_STATE/);
});
