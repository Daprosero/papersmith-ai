import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { promisify } from 'node:util';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const piRoot = ENGINE_MODULE_ROOT;
const execFileAsync = promisify(execFile);
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

async function fixture() {
	const documentBytes = Buffer.from('First.\nSecond.\n');
	const first = { entryId: 'first-section', type: 'section', startByte: 0, endByte: 6, textSha256: sha256(documentBytes.subarray(0, 6)) };
	const second = { entryId: 'second-section', type: 'section', startByte: 7, endByte: 14, textSha256: sha256(documentBytes.subarray(7, 14)) };
	const source = {
		filename: 'research-concept-r01.md',
		revision: 'r01',
		documentBytes,
		documentSha256: sha256(documentBytes),
		structuralIndex: { entries: [first, second], byId: { [first.entryId]: first, [second.entryId]: second } },
	};
	return { source, first, second };
}

function sourceIdentity(source) {
	return { filename: source.filename, revision: source.revision, documentSha256: source.documentSha256 };
}

function target(source, entry) {
	return { status: 'resolved', selector: { entryId: entry.entryId, startByte: entry.startByte, endByte: entry.endByte, textSha256: entry.textSha256, documentSha256: source.documentSha256 } };
}

function candidate(text) {
	return sha256(text);
}

function plan(source, blocks, orderedBlockIds = blocks.map((block) => block.id), mergeGroups = []) {
	return { source: sourceIdentity(source), orderedBlockIds, blocks, mergeGroups };
}

function block(id, source, entry, overrides = {}) {
	return { id, dependsOn: [], target: target(source, entry), candidateSha256: candidate(id), ...overrides };
}

test('public exports barrel exposes block-plan preflight', () => {
	assert.equal(typeof v2.preflightSuccessorBlockPlan, 'function');
});

test('preflight accepts disjoint blocks and returns the declared canonical order', async () => {
	const { source, first, second } = await fixture();
	const result = v2.preflightSuccessorBlockPlan(plan(source, [block('first', source, first), block('second', source, second, { dependsOn: ['first'] })]), source);
	assert.deepEqual(result, { status: 'ready', executionOrder: ['first', 'second'], diagnostics: [] });
});

test('preflight rejects invalid IDs, dependency order errors, cycles, and unknown dependencies', async () => {
	const { source, first, second } = await fixture();
	for (const input of [
		plan(source, [block('bad id', source, first)]),
		plan(source, [block('first', source, first, { dependsOn: ['second'] }), block('second', source, second)], ['first', 'second']),
		plan(source, [block('first', source, first, { dependsOn: ['second'] }), block('second', source, second, { dependsOn: ['first'] })]),
		plan(source, [block('first', source, first, { dependsOn: ['missing'] })]),
	]) {
		const result = v2.preflightSuccessorBlockPlan(input, source);
		assert.equal(result.status, 'blocked');
	}
	const cycle = v2.preflightSuccessorBlockPlan(plan(source, [block('first', source, first, { dependsOn: ['second'] }), block('second', source, second, { dependsOn: ['first'] })]), source);
	assert.deepEqual(cycle.diagnostics.map((diagnostic) => diagnostic.code), ['BLOCK_DEPENDENCY_CYCLE', 'BLOCK_DEPENDENCY_CYCLE', 'BLOCK_DEPENDENCY_ORDER']);
});

test('preflight rejects unresolved and ambiguous targets', async () => {
	const { source, first } = await fixture();
	for (const targetStatus of [
		{ status: 'unresolved', query: 'missing section' },
		{ status: 'ambiguous', candidateEntryIds: [first.entryId, 'another-entry'] },
	]) {
		const result = v2.preflightSuccessorBlockPlan(plan(source, [block('first', source, first, { target: targetStatus })]), source);
		assert.deepEqual(result, { status: 'blocked', diagnostics: [{ code: targetStatus.status === 'unresolved' ? 'BLOCK_TARGET_UNRESOLVED' : 'BLOCK_TARGET_AMBIGUOUS', blockId: 'first' }] });
	}
});

test('preflight blocks malformed and untyped target statuses without throwing', async () => {
	const { source, first } = await fixture();
	for (const malformedTarget of [undefined, null, { status: null }, { status: 'unsupported' }, { status: 'resolved' }]) {
		const result = v2.preflightSuccessorBlockPlan(plan(source, [block('first', source, first, { target: malformedTarget })]), source);
		assert.deepEqual(result, { status: 'blocked', diagnostics: [{ code: 'BLOCK_TARGET_INVALID', blockId: 'first' }] });
	}
});

test('preflight rejects overlapping spans unless an explicit compatible merge group covers both blocks', async () => {
	const { source, first } = await fixture();
	const left = block('left', source, first);
	const right = block('right', source, first);
	const rejected = v2.preflightSuccessorBlockPlan(plan(source, [left, right]), source);
	assert.deepEqual(rejected, { status: 'blocked', diagnostics: [{ code: 'BLOCK_TARGET_OVERLAP', blockId: 'right', relatedBlockId: 'left' }] });
	const accepted = v2.preflightSuccessorBlockPlan(plan(source, [{ ...left, mergeGroupId: 'same-target' }, { ...right, mergeGroupId: 'same-target' }], ['left', 'right'], [{ id: 'same-target', blockIds: ['left', 'right'], compatibility: 'OVERLAPPING_TARGETS' }]), source);
	assert.deepEqual(accepted, { status: 'ready', executionOrder: ['left', 'right'], diagnostics: [] });
});

test('preflight reports malformed merge groups and invalid candidate hashes', async () => {
	const { source, first, second } = await fixture();
	const input = plan(source, [
		block('first', source, first, { candidateSha256: 'invalid' }),
		block('second', source, second, { mergeGroupId: 'invalid-group' }),
	], undefined, [{ id: 'invalid-group', blockIds: ['first', 'first'], compatibility: 'NOT_COMPATIBLE' }]);
	assert.deepEqual(v2.preflightSuccessorBlockPlan(input, source), {
		status: 'blocked',
		diagnostics: [
			{ code: 'BLOCK_CANDIDATE_HASH_INVALID', blockId: 'first' },
			{ code: 'BLOCK_MERGE_GROUP_INVALID' },
			{ code: 'BLOCK_MERGE_GROUP_INVALID', blockId: 'second' },
		],
	});
});

test('preflight rejects stale frozen source identity and stale structural target hashes', async () => {
	const { source, first } = await fixture();
	const staleSource = plan(source, [block('first', source, first)]);
	staleSource.source.documentSha256 = candidate('stale source');
	assert.deepEqual(v2.preflightSuccessorBlockPlan(staleSource, source), { status: 'blocked', diagnostics: [{ code: 'BLOCK_SOURCE_STALE' }] });
	const staleTarget = plan(source, [block('first', source, first, { target: { status: 'resolved', selector: { ...target(source, first).selector, textSha256: candidate('stale target') } } })]);
	assert.deepEqual(v2.preflightSuccessorBlockPlan(staleTarget, source), { status: 'blocked', diagnostics: [{ code: 'BLOCK_TARGET_STALE', blockId: 'first' }] });
});

test('preflight rejects source-byte mutations outside selected targets', async () => {
	const { source, first } = await fixture();
	const mutatedBytes = Buffer.from(source.documentBytes);
	mutatedBytes.write('Changed', mutatedBytes.indexOf('Second.'));
	const mutatedSource = { ...source, documentBytes: mutatedBytes };
	assert.deepEqual(v2.preflightSuccessorBlockPlan(plan(source, [block('first', source, first)]), mutatedSource), { status: 'blocked', diagnostics: [{ code: 'BLOCK_SOURCE_STALE' }] });
});

test('preflight diagnostics and execution order are deterministic', async () => {
	const { source, first, second } = await fixture();
	const blocks = [block('second', source, second, { dependsOn: ['missing'] }), block('first', source, first, { dependsOn: ['missing'] })];
	const input = plan(source, blocks, ['first', 'second']);
	const reversed = plan(source, [...blocks].reverse(), ['first', 'second']);
	assert.deepEqual(v2.preflightSuccessorBlockPlan(input, source), v2.preflightSuccessorBlockPlan(reversed, source));
	assert.deepEqual(v2.preflightSuccessorBlockPlan(input, source).diagnostics, [
		{ code: 'BLOCK_DEPENDENCY_UNKNOWN', blockId: 'first', dependencyId: 'missing' },
		{ code: 'BLOCK_DEPENDENCY_UNKNOWN', blockId: 'second', dependencyId: 'missing' },
	]);
});

test('preflight diagnostic ordering is locale-independent', async () => {
	const script = `
		import { createHash } from 'node:crypto';
		import path from 'node:path';
		import { pathToFileURL } from 'node:url';
		const piRoot = process.env.PROPOSAL_DELIBERATION_PI_ROOT;
		const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
		const jiti = createJiti(import.meta.url, { alias: {
			'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
			'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
			'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
			typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
		} });
		const v2 = await jiti.import(process.env.PROPOSAL_DELIBERATION_EXPORTS);
		const documentBytes = Buffer.from('frozen source');
		const sha256 = (value) => createHash('sha256').update(value).digest('hex');
		const source = { filename: 'source.md', revision: 'r01', documentBytes, documentSha256: sha256(documentBytes), structuralIndex: { byId: {} } };
		const plan = { source: { filename: source.filename, revision: source.revision, documentSha256: source.documentSha256 }, orderedBlockIds: ['a', 'B'], blocks: [
			{ id: 'a', dependsOn: [], target: { status: 'unresolved' }, candidateSha256: 'a'.repeat(64) },
			{ id: 'B', dependsOn: [], target: { status: 'unresolved' }, candidateSha256: 'b'.repeat(64) },
		], mergeGroups: [] };
		console.log(JSON.stringify(v2.preflightSuccessorBlockPlan(plan, source).diagnostics));
	`;
	const diagnosticsForLocale = async (locale) => {
		const { stdout } = await execFileAsync(process.execPath, ['--input-type=module', '--eval', script], {
			env: { ...process.env, LANG: locale, LC_ALL: locale, PROPOSAL_DELIBERATION_PI_ROOT: piRoot, PROPOSAL_DELIBERATION_EXPORTS: exportsPath },
		});
		return JSON.parse(stdout);
	};
	const expected = [
		{ code: 'BLOCK_TARGET_UNRESOLVED', blockId: 'B' },
		{ code: 'BLOCK_TARGET_UNRESOLVED', blockId: 'a' },
	];
	assert.deepEqual(await diagnosticsForLocale('en_US.UTF-8'), expected);
	assert.deepEqual(await diagnosticsForLocale('tr_TR.UTF-8'), expected);
});
