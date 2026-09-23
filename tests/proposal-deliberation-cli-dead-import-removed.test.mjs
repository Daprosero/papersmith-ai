// Finding L7: `cli.mjs` imported `pathToFileURL` from `node:url` and never used it for
// anything except keeping the import from reading as unused -- its only other
// occurrence anywhere in the file was `void pathToFileURL;`, the file's own last line.
// Both were dead weight: deleted.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';

const cliPath = path.resolve('skills/_core/deliberation/engine/cli.mjs');

test('cli.mjs no longer imports or references pathToFileURL', async () => {
	const source = await readFile(cliPath, 'utf8');
	assert.doesNotMatch(source, /pathToFileURL/, 'the dead import and its trailing `void pathToFileURL;` must both be gone');
});

test('cli.mjs still ends with a real statement, not a bare void-expression placeholder', async () => {
	const source = await readFile(cliPath, 'utf8');
	const trimmed = source.replace(/\s+$/, '');
	assert.doesNotMatch(trimmed, /void\s+\w+;$/, 'the file must not end in a no-op kept only to silence an unused-import warning');
});
