import assert from 'node:assert/strict'; import test from 'node:test'; import { readFile } from 'node:fs/promises';
const source = await readFile('.claude/skills/proposal-deliberation/engine/proposal-workspace.ts', 'utf8');
const intents = await readFile('.claude/skills/proposal-deliberation/engine/types.ts', 'utf8');
test('V2 guard exposes only semantic document operations', () => {
	// Concrete, user-facing document operations are surfaced by the host tool.
	for (const operation of ['MODIFY', 'INSERT', 'DELETE', 'MOVE', 'CONCEPTUAL_REVISION', 'REVIEW', 'DELIBERATE'])
		assert.match(source, new RegExp(`['"]${operation}['"]`));
	// AMBIGUOUS is the "no concrete operation" classification, resolved upstream by
	// the intent resolver; it belongs to the engine Intent vocabulary, not to the
	// host operation surface.
	assert.match(intents, /['"]AMBIGUOUS['"]/);
	// Low-level patch mechanics are never surfaced as an operation.
	assert.doesNotMatch(source, /FAST_PATCH/);
});
