import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const piRoot = ENGINE_MODULE_ROOT;
const exportsPath = path.join(root, '.claude/skills/_core/deliberation/engine/exports.ts');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(exportsPath);
const sha256 = (value) => createHash('sha256').update(value).digest('hex');

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

function targetOf(source, e) {
	return { status: 'resolved', selector: { entryId: e.entryId, startByte: e.startByte, endByte: e.endByte, textSha256: e.textSha256, documentSha256: source.documentSha256 } };
}

// Mirror the engine's disjoint splice so tests can compute the exact per-block
// candidate hashes the engine will verify.
function spliceDisjoint(sourceBytes, edits) {
	const ordered = [...edits].sort((left, right) => left.startByte - right.startByte);
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

// Build a plan whose per-block candidateSha256 equals the running candidate hash
// after applying blocks[0..k] at their source spans (the per-transition contract).
function planFor(source, specs) {
	const order = specs.map((spec) => spec.id);
	const edits = specs.map((spec) => ({ startByte: spec.entry.startByte, endByte: spec.entry.endByte, replacement: spec.replacement }));
	const blocks = specs.map((spec, index) => ({
		id: spec.id,
		dependsOn: spec.dependsOn ?? [],
		target: targetOf(source, spec.entry),
		candidateSha256: sha256(spliceDisjoint(source.documentBytes, edits.slice(0, index + 1))),
		...(spec.mergeGroupId ? { mergeGroupId: spec.mergeGroupId } : {}),
	}));
	return { plan: { source: sourceIdentity(source), orderedBlockIds: order, blocks, mergeGroups: specs.mergeGroups ?? [] }, edits };
}

function resolverFrom(specs) {
	const byId = new Map(specs.map((spec) => [spec.id, spec.replacement]));
	return ({ block }) => byId.get(block.id);
}

test('barrel exposes the composite successor engine', () => {
	assert.equal(typeof v2.composeSuccessorBlockCandidate, 'function');
});

test('composes disjoint blocks into one candidate, preserving untouched bytes and honoring per-block hashes', async () => {
	const { source, alpha, gamma } = fixture();
	const specs = [
		{ id: 'agg', entry: alpha, replacement: 'Alpha rewritten: se recupera el promedio uniforme como caso base.' },
		{ id: 'loss', entry: gamma, dependsOn: ['agg'], replacement: 'Gamma rewritten with the learned relevance term.' },
	];
	const { plan, edits } = planFor(source, specs);
	const result = await v2.composeSuccessorBlockCandidate(plan, source, resolverFrom(specs));

	assert.equal(result.status, 'composed', JSON.stringify(result));
	const expected = spliceDisjoint(source.documentBytes, edits);
	assert.ok(result.candidateBytes.equals(expected));
	assert.equal(result.manifest.candidateSha256, sha256(expected));
	assert.deepEqual(result.manifest.executionOrder, ['agg', 'loss']);
	// The untouched middle ("Beta section.") and all block boundaries survive byte-for-byte.
	assert.ok(result.candidateBytes.includes(Buffer.from('Beta section.')));
	assert.ok(result.candidateBytes.includes(Buffer.from('se recupera el promedio uniforme')));
	assert.ok(result.manifest.preservedRegions.length >= 1);
	// The source document is never mutated.
	assert.equal(sha256(source.documentBytes), source.documentSha256);
});

test('a wrong per-block candidate hash blocks with BLOCK_CANDIDATE_HASH_MISMATCH and composes nothing', async () => {
	const { source, alpha } = fixture();
	const specs = [{ id: 'agg', entry: alpha, replacement: 'Alpha rewritten.' }];
	const { plan } = planFor(source, specs);
	const corrupted = { ...plan, blocks: [{ ...plan.blocks[0], candidateSha256: sha256('divergent') }] };
	const result = await v2.composeSuccessorBlockCandidate(corrupted, source, resolverFrom(specs));
	assert.equal(result.status, 'blocked');
	assert.deepEqual(result.diagnostics.map((d) => d.code), ['BLOCK_CANDIDATE_HASH_MISMATCH']);
});

test('an unready plan (stale target) blocks with BLOCK_PLAN_NOT_READY before any resolution', async () => {
	const { source, alpha } = fixture();
	const specs = [{ id: 'agg', entry: alpha, replacement: 'Alpha rewritten.' }];
	const { plan } = planFor(source, specs);
	const stale = { ...plan, blocks: [{ ...plan.blocks[0], target: { status: 'resolved', selector: { ...plan.blocks[0].target.selector, textSha256: sha256('stale') } } }] };
	let resolverCalls = 0;
	const result = await v2.composeSuccessorBlockCandidate(stale, source, () => { resolverCalls++; return 'x'; });
	assert.equal(result.status, 'blocked');
	assert.deepEqual(result.diagnostics.map((d) => d.code), ['BLOCK_PLAN_NOT_READY']);
	assert.equal(resolverCalls, 0);
});

test('overlapping targets in a merge group are explicitly deferred, not silently applied', async () => {
	const { source, alpha } = fixture();
	const specs = [
		{ id: 'agg', entry: alpha, replacement: 'Alpha rewritten once.', mergeGroupId: 'g' },
		{ id: 'aggConf', entry: alpha, dependsOn: ['agg'], replacement: 'Alpha rewritten twice.', mergeGroupId: 'g' },
	];
	const { plan } = planFor(source, specs);
	plan.mergeGroups = [{ id: 'g', blockIds: ['agg', 'aggConf'], compatibility: 'OVERLAPPING_TARGETS' }];
	const ready = v2.preflightSuccessorBlockPlan(plan, source);
	assert.equal(ready.status, 'ready');
	const result = await v2.composeSuccessorBlockCandidate(plan, source, resolverFrom(specs));
	assert.equal(result.status, 'blocked');
	assert.deepEqual(result.diagnostics.map((d) => d.code), ['BLOCK_MERGE_GROUP_UNSUPPORTED']);
});

test('an empty replacement blocks with BLOCK_REPLACEMENT_INVALID', async () => {
	const { source, alpha } = fixture();
	const specs = [{ id: 'agg', entry: alpha, replacement: 'Alpha rewritten.' }];
	const { plan } = planFor(source, specs);
	const result = await v2.composeSuccessorBlockCandidate(plan, source, () => '');
	assert.equal(result.status, 'blocked');
	assert.deepEqual(result.diagnostics.map((d) => d.code), ['BLOCK_REPLACEMENT_INVALID']);
});

test('a replacement identical to the source span blocks with COMPOSITE_NO_OP', async () => {
	const { source, alpha } = fixture();
	const specs = [{ id: 'agg', entry: alpha, replacement: 'Alpha section.' }];
	const { plan } = planFor(source, specs);
	const result = await v2.composeSuccessorBlockCandidate(plan, source, resolverFrom(specs));
	assert.equal(result.status, 'blocked');
	assert.deepEqual(result.diagnostics.map((d) => d.code), ['COMPOSITE_NO_OP']);
});
