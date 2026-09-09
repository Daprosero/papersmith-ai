// The north: why this skill was invoked and where it has to arrive.
//
// It lives in the ENGINE rather than in a domain profile, and that is derived
// rather than chosen: a profile says what a domain is called and which notation
// it uses, and would say the same north whichever domain asked. The engine has
// exactly one purpose, so the purpose is the engine's.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';

const ENGINE = path.resolve('.claude/skills/_core/deliberation/engine/cli.mjs');
const SKILL = path.resolve('.claude/skills/proposal-deliberation/SKILL.md');
const engine = await readFile(ENGINE, 'utf8');
const skill = await readFile(SKILL, 'utf8');

const STAGES = ['bound', 'deliberated', 'composed', 'published'];

test('every error path carries the north', () => {
	// A blocked session is exactly the one that has lost the purpose. Both of
	// the engine's two output paths are pinned, so a third added later has to
	// be a decision rather than a drift.
	const paths = [...engine.matchAll(/status: 'error', message: [^}]*}/g)].map((m) => m[0]);
	assert.equal(paths.length, 2, 'the engine has two error paths; that count is what this pins');
	for (const emitted of paths) {
		assert.match(emitted, /objective: OBJECTIVE_FLOW/, 'an error reaches a reader without the north');
	}
});

test('STATUS reports it above the inventory', () => {
	assert.match(engine, /operation: 'STATUS',\n\t\t\/\/[\s\S]{0,600}?objective: OBJECTIVE_FLOW,/);
});

test('it is declared, ordered, and every stage says how it closes', () => {
	for (const stage of STAGES) {
		assert.match(engine, new RegExp(`stage: '${stage}'`), `the engine is silent about ${stage}`);
	}
	// Order matters: a flow whose stages could be read in any order is not a flow.
	const order = STAGES.map((stage) => engine.indexOf(`stage: '${stage}'`));
	assert.deepEqual(order, [...order].sort((a, b) => a - b), 'the stages are declared out of order');
});

test('the deliberated stage refuses to claim it can be measured', () => {
	// The honest gap. Nothing measures "it was deliberated", and if this
	// pretended to, an agent could open a question, answer it itself, and close
	// the stage on its own word -- a failure this project has already seen.
	const block = engine.slice(engine.indexOf("stage: 'deliberated'"));
	const closes = block.slice(0, block.indexOf('},'));
	assert.match(closes, /THE USER SAID SO/, 'the stage that cannot be measured must say so');
	assert.match(closes, /Nothing here measures it/);
});

test('the entrance from a handoff still owes the arrival', () => {
	// A finding that gets discussed, agreed, and never published is how this
	// pair of skills loses work.
	assert.match(engine, /arrivesAt: 'composed'/);
	assert.match(engine, /agreement is not arrival/);
});

test('the doctrine states the same stages, in the same order', () => {
	// Scoped to the section's own table: these words appear all over a long
	// document, and a whole-file search would stay green through a renamed row.
	const start = skill.indexOf('## The objective flow');
	assert.ok(start >= 0, 'the doctrine has no objective-flow section');
	const table = skill.slice(start, skill.indexOf('**Arrival:**', start));
	const rows = table.split('\n').filter((line) => line.startsWith('| `')).map((line) => line.split('`')[1]);
	assert.deepEqual(rows, STAGES);
});
