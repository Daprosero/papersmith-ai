// `resolveTargets` used to score an entry's own text, both of its neighbours and
// its heading path against one flat blob, so every word inside an entry scored
// identically for the entry before it, the entry after it, and the ancestor that
// spans it. A GFM table could therefore never be singled out by its own column
// headers: the table, its section and BOTH neighbouring paragraphs — which
// contain none of those words — all tied, and `ambiguityGate` (margin 4) blocked.
//
// Everything here goes through the real `resolveTargets` + `ambiguityGate` path.
// Passing an `entryId` straight in short-circuits the scorer at the direct-match
// branch and proves nothing about it — which is exactly how this stayed hidden.
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
const v2 = await jiti.import(path.resolve('skills/_core/deliberation/engine/exports.ts'));

// One section, an intro paragraph, a fully piped table, an outro paragraph.
// `Modelo`, `Exactitud` and `Cobertura` are the table's column headers and appear
// nowhere else in the document.
const TABLE_IN_CONTEXT_DOC = [
    '# Experimento 3',
    '',
    'Preparacion del banco de pruebas y semillas empleadas.',
    '',
    '| Modelo | Exactitud | Cobertura |',
    '| --- | --- | --- |',
    '| base | 0.81 | 0.72 |',
    '| ajustado | 0.88 | 0.75 |',
    '',
    'Discusion posterior sobre las implicancias observadas.',
    '',
].join('\n');

test('a table is resolved by its own column headers, not tied with its section and its neighbouring paragraphs', async () => {
    const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(TABLE_IN_CONTEXT_DOC));
    const table = state.structuralIndex.entries.find(e => e.type === 'table');
    const section = state.structuralIndex.entries.find(e => e.type === 'section');
    const paragraphs = state.structuralIndex.entries.filter(e => e.type === 'paragraph');
    assert.ok(table, 'fixture premise: the GFM table is its own structural entry');
    assert.ok(section, 'fixture premise: the document has a section entry spanning the table');
    assert.equal(paragraphs.length, 2, 'fixture premise: exactly one paragraph on each side of the table');
    for (const paragraph of paragraphs) {
        const text = v2.entryText(state, paragraph).toLowerCase();
        for (const header of ['modelo', 'exactitud', 'cobertura']) {
            assert.equal(text.includes(header), false, `fixture premise: "${header}" appears only inside the table, never in the paragraph beside it`);
        }
    }

    const candidates = v2.resolveTargets(state, 'Modelo Exactitud Cobertura');
    const scoreOf = id => candidates.find(c => c.entryId === id)?.score ?? 0;
    assert.equal(candidates[0].entryId, table.entryId, 'the entry that actually contains the queried words must rank first');

    // The margin has to clear `ambiguityGate`'s threshold, not merely exist: the
    // gate blocks whenever the top two are within 4 of each other.
    for (const other of [section, ...paragraphs]) {
        assert.ok(
            scoreOf(table.entryId) - scoreOf(other.entryId) > 4,
            `the table must outrank ${other.type} ${other.entryId} by more than the ambiguity margin of 4 (table ${scoreOf(table.entryId)} vs ${scoreOf(other.entryId)})`,
        );
    }

    const gate = v2.ambiguityGate(candidates);
    assert.equal(gate.blocked, false, 'a query naming the table\'s own column headers must not be refused as ambiguous');
    assert.equal(gate.candidate.entryId, table.entryId);
    assert.equal(gate.candidate.type, 'table');
});

// The neighbour signal is deliberately kept, not deleted: a locus is often
// described by what sits beside it. These two paragraphs have byte-identical own
// text, so nothing but their surroundings can tell them apart.
const NEIGHBOUR_CONTEXT_DOC = [
    '# Datos',
    '',
    'Marcador zeta del primer bloque.',
    '',
    'Texto compartido identico entre bloques.',
    '',
    'Marcador omega del segundo bloque.',
    '',
    'Texto compartido identico entre bloques.',
    '',
].join('\n');

test('a term found only in a neighbouring entry still scores, and still breaks a tie between identical entries', async () => {
    const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(NEIGHBOUR_CONTEXT_DOC));
    const shared = state.structuralIndex.entries
        .filter(e => e.type === 'paragraph' && v2.entryText(state, e).trim() === 'Texto compartido identico entre bloques.')
        .sort((a, b) => a.startByte - b.startByte);
    assert.equal(shared.length, 2, 'fixture premise: two paragraphs with byte-identical own text');

    // `zeta` appears only in the paragraph preceding the first of them.
    const candidates = v2.resolveTargets(state, 'compartido zeta');
    const first = candidates.find(c => c.entryId === shared[0].entryId);
    const second = candidates.find(c => c.entryId === shared[1].entryId);
    assert.ok(first && second, 'both identical paragraphs must be listed as candidates');
    assert.ok(first.matchedTerms.includes('zeta'), 'a term carried only by a neighbour must still be recorded as matched evidence');
    assert.equal(second.matchedTerms.includes('zeta'), false, 'the far paragraph has no such neighbour');
    assert.ok(first.score > second.score, `the neighbour term must still lift its entry above an otherwise identical one (${first.score} vs ${second.score})`);

    // And an entry whose OWN text matches nothing at all is still reachable through
    // its neighbours — deleting neighbour text would have filtered it out entirely.
    const marker = state.structuralIndex.entries.find(e => e.type === 'paragraph' && v2.entryText(state, e).includes('omega'));
    const byNeighbour = v2.resolveTargets(state, 'omega').find(c => c.entryId === shared[1].entryId);
    assert.ok(marker, 'fixture premise: the omega marker paragraph exists');
    assert.ok(byNeighbour && byNeighbour.score > 0, 'an entry that matches only through a neighbour must remain a listed candidate');
});
