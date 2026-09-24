// Phase 1.2 (change 2): `artifact-naming.ts` exports a named matcher FAMILY,
// never one canonical regex. Measured (design.md's corrections table), the
// five semantics genuinely diverge:
//   STRICT   -- anchored, lowercase-alnum lineage (or none), minimum 2 digits.
//   LAX      -- the sole gate on `loadDocumentState`; ANY lineage character,
//               a single digit is enough. Genuinely looser than STRICT.
//   INCREMENT-- splits a filename into its stable head and ordinal digits.
//   LOOSE    -- unanchored, case-insensitive; finds a filename inside prose.
//   INITIAL  -- `stem-SEGMENT-r01.md` only; a lineage segment is MANDATORY.
// Collapsing any two of these into one regex is exactly the regression class
// change 2 exists to prevent -- mutation M2b (phase 1.6) proves it directly
// by tightening LAX's `\d+` to `\d{2,}` and watching this exact test go red.
import assert from 'node:assert/strict';
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
const AN = await jiti.import(path.resolve('skills/_core/deliberation/engine/artifact-naming.ts'));
const { loadDocumentState } = await jiti.import(path.resolve('skills/_core/deliberation/engine/document-state.ts'));

// --- STRICT ---------------------------------------------------------------

test('STRICT refuses a one-digit revision ordinal', () => {
	assert.equal(AN.strictManagedRevision('research-concept-r1.md'), false);
});

test('STRICT accepts a two-digit revision ordinal, ROOT lineage', () => {
	assert.equal(AN.strictManagedRevision('research-concept-r02.md'), true);
});

test('STRICT accepts a two-digit revision ordinal with an explicit lineage', () => {
	assert.equal(AN.strictManagedRevision('research-concept-subject-bag-r02.md'), true);
});

test('STRICT refuses an uppercase-lettered lineage (LAX-only territory)', () => {
	assert.equal(AN.strictManagedRevision('research-concept-Subject-r02.md'), false);
});

// --- LAX PARSE (the sole gate on loadDocumentState) -----------------------

test('LAX accepts a one-digit revision ordinal that STRICT refuses', () => {
	const parsed = AN.parseManagedRevision('research-concept-r1.md');
	assert.ok(parsed, 'LAX must accept …-r1.md');
	assert.equal(parsed.lineage, 'ROOT');
	assert.equal(parsed.ordinal, 1);
});

test('LAX accepts ANY lineage character, not just the lowercase-alnum SEGMENT shape', () => {
	const parsed = AN.parseManagedRevision('research-concept-Any_Weird.Chars-r3.md');
	assert.ok(parsed, 'LAX must accept a lineage with characters STRICT would refuse');
	assert.equal(parsed.lineage, 'Any_Weird.Chars');
	assert.equal(parsed.ordinal, 3);
});

test('loadDocumentState accepts a filename LAX allows but STRICT refuses (…-r1.md)', async () => {
	assert.equal(AN.strictManagedRevision('research-concept-r1.md'), false, 'STRICT must still refuse this exact name');
	// loadDocumentState's own INVALID_MANAGED_REVISION guard must be LAX, not STRICT: it should
	// fail on a MISSING file (a filesystem error), never on the identity/name check itself.
	await assert.rejects(
		() => loadDocumentState('/nonexistent-root-for-lax-gate-test', 'research-concept-r1.md'),
		(error) => {
			assert.notEqual(error.message, 'INVALID_MANAGED_REVISION', 'LAX must accept this name; only the missing file may fail');
			return true;
		},
	);
});

test('loadDocumentState still refuses a genuinely malformed name (no revision at all)', async () => {
	await assert.rejects(
		() => loadDocumentState('/nonexistent-root-for-lax-gate-test', 'research-concept-not-a-revision.md'),
		/INVALID_MANAGED_REVISION/,
	);
});

// --- INCREMENT --------------------------------------------------------------

test('INCREMENT splits a managed filename into its stable head and its ordinal digits', () => {
	const parsed = AN.parseRevisionIncrement('research-concept-foo-r06.md');
	assert.ok(parsed);
	assert.equal(parsed.prefix, 'research-concept-foo-r');
	assert.equal(parsed.ordinal, 6);
});

test('INCREMENT bumps the ordinal for a ROOT-lineage filename', () => {
	const parsed = AN.parseRevisionIncrement('research-concept-r09.md');
	assert.ok(parsed);
	const next = `${parsed.prefix}${String(parsed.ordinal + 1).padStart(2, '0')}.md`;
	assert.equal(next, 'research-concept-r10.md');
});

// --- LOOSE SCAN (unanchored, case-insensitive) ------------------------------

test('LOOSE SCAN is unanchored: finds a managed filename inside a sentence', () => {
	const found = AN.scanManagedRevision('please revisa research-concept-foo-r06.md antes de continuar');
	assert.equal(found, 'research-concept-foo-r06.md');
});

test('LOOSE SCAN is case-insensitive', () => {
	const found = AN.scanManagedRevision('RESEARCH-CONCEPT-FOO-R06.MD');
	assert.ok(found, 'expected a case-insensitive match');
	assert.equal(found.toLowerCase(), 'research-concept-foo-r06.md');
});

test('LOOSE SCAN refuses a one-digit ordinal, same digit-count floor as STRICT', () => {
	const found = AN.scanManagedRevision('research-concept-foo-r6.md');
	assert.equal(found, undefined);
});

// --- INITIAL (mandatory lineage) --------------------------------------------

test('INITIAL matches stem-SEGMENT-r01.md', () => {
	assert.equal(AN.isInitialRevision('research-concept-my-idea-r01.md'), true);
});

test('INITIAL refuses the bare-ROOT form (no lineage) even though STRICT accepts it', () => {
	assert.equal(AN.strictManagedRevision('research-concept-r01.md'), true, 'STRICT must accept the bare-ROOT r01 form');
	assert.equal(AN.isInitialRevision('research-concept-r01.md'), false, 'INITIAL requires a mandatory lineage segment');
});

test('INITIAL refuses a non-r01 revision even with a lineage', () => {
	assert.equal(AN.isInitialRevision('research-concept-my-idea-r02.md'), false);
});

// --- Builders ----------------------------------------------------------------

test('managedRevisionFilename renders the ROOT and lineage-qualified forms identically to the old hardcoded shape', () => {
	assert.equal(AN.managedRevisionFilename('ROOT', 6), 'research-concept-r06.md');
	assert.equal(AN.managedRevisionFilename('my-idea', 6), 'research-concept-my-idea-r06.md');
});

test('initialRevisionFilename renders only the lineage-qualified first-revision form', () => {
	assert.equal(AN.initialRevisionFilename('my-idea'), 'research-concept-my-idea-r01.md');
});

test('documentPath/statePath/receiptPath/withdrawnMarkerPath match the pre-migration literal shapes', () => {
	assert.equal(AN.documentPath('x.md'), 'proposals/x.md');
	assert.equal(AN.statePath('x.md'), '.proposal-deliberation/state/x.md.json');
	assert.equal(AN.receiptPath('x.md'), '.proposal-deliberation/receipts/x.md.json');
	assert.equal(AN.withdrawnMarkerPath('op-1'), '.proposal-deliberation/withdrawn/op-1/audit-marker.json');
	assert.deepEqual(AN.publicRelativePaths('x.md'), ['proposals/x.md', '.proposal-deliberation/state/x.md.json', '.proposal-deliberation/receipts/x.md.json']);
});

test('managedRevisionSchemaPattern reproduces the three pre-migration JSON-Schema pattern strings', () => {
	assert.equal(AN.managedRevisionSchemaPattern(), '^research-concept-(?:[a-z0-9]+(?:-[a-z0-9]+)*-)?r\\d{2,}\\.md$');
	assert.equal(AN.managedRevisionSchemaPattern({ requireLineage: true }), '^research-concept-[a-z0-9]+(?:-[a-z0-9]+)*-r\\d{2,}\\.md$');
	assert.equal(AN.managedRevisionSchemaPattern({ directoryPrefix: true }), '^(?:proposals/)?research-concept-(?:[a-z0-9]+(?:-[a-z0-9]+)*-)?r\\d{2,}\\.md$');
});
