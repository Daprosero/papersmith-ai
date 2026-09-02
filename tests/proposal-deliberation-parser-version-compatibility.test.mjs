import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
// Derived state committed under a superseded parser identifier must still validate.
//
// The parser version exists to invalidate stored state when PARSING changes. Renaming the
// skill from `paper-proposal` to `proposal-deliberation` changed the identifier without
// changing a single line of parsing code, so every revision published before that rename
// was rejected as an invalid committed manifest even though its bytes and indexes were
// correct. These tests pin both halves: the superseded identifier is accepted, and an
// identifier that was never this parser is not.
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = ENGINE_MODULE_ROOT;
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/exports.ts'));

const CONTENT = '# Propuesta\n\n## Método\n\nUn cuerpo estable para el índice.\n';

/** Publishes r01 normally, then rewrites ONLY the parserVersion its committed state carries. */
async function projectWithStoredParserVersion(storedVersion, status = 'COMMITTED') {
	const root = await mkdtemp(path.join(tmpdir(), 'pp-parser-version-'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await workspace.createProposalWorkspaceTool(root).execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: CONTENT });
	const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
	await v2.saveDerivedState(root, state, status);
	const statePath = v2.derivedStatePath(root, 'research-concept-r01.md');
	const stored = JSON.parse(await (await import('node:fs/promises')).readFile(statePath, 'utf8'));
	stored.manifest.parserVersion = storedVersion;
	await writeFile(statePath, JSON.stringify(stored));
	return { root, state, stored };
}

test('validateStoredState accepts derived state committed under the superseded parser identifier', async () => {
	assert.ok(v2.SUPERSEDED_PARSER_VERSIONS.includes('paper-proposal/1'), 'the pre-rename identifier must be declared superseded');
	const { state, stored } = await projectWithStoredParserVersion('paper-proposal/1');
	assert.equal(
		v2.validateStoredState(stored, 'research-concept-r01.md', state.documentSha256, v2.PARSER_VERSION),
		true,
		'state produced by byte-identical parsing code must not be invalidated by the rename alone',
	);
});

test('validateStoredState still accepts the current parser identifier', async () => {
	const { state, stored } = await projectWithStoredParserVersion(v2.PARSER_VERSION);
	assert.equal(v2.validateStoredState(stored, 'research-concept-r01.md', state.documentSha256, v2.PARSER_VERSION), true);
});

test('validateStoredState rejects an identifier this parser never answered to', async () => {
	const { state, stored } = await projectWithStoredParserVersion('some-other-engine/9');
	assert.equal(
		v2.validateStoredState(stored, 'research-concept-r01.md', state.documentSha256, v2.PARSER_VERSION),
		false,
		'widening the accepted set must not degrade into accepting anything',
	);
});

test('a superseded identifier never excuses a document whose bytes have changed', async () => {
	const { stored } = await projectWithStoredParserVersion('paper-proposal/1');
	assert.equal(
		v2.validateStoredState(stored, 'research-concept-r01.md', 'f'.repeat(64), v2.PARSER_VERSION),
		false,
		'the document hash is a separate guard and must still fail closed',
	);
});

test('the consistency audit reports no invalid committed manifest for pre-rename state', async () => {
	const { root } = await projectWithStoredParserVersion('paper-proposal/1');
	const audit = await v2.runConsistencyAudit({ projectRoot: root });
	assert.deepEqual(
		audit.failures.filter((failure) => failure.startsWith('INVALID_COMMITTED_MANIFEST')),
		[],
		JSON.stringify(audit.failures),
	);
});
