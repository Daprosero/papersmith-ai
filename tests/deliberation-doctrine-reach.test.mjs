// The north's DOCUMENTED reach, held against its MEASURED reach.
//
// The engine emits `objective` at exactly three sites: `runStatus` and the two
// CLI-level catch handlers. A typed refusal returned as a value from
// `tool.execute` is written straight to stdout by the success path and carries
// none. Both `proposal-deliberation/SKILL.md` and `deliberation-publish.md`
// once claimed a broader reach -- "every refusal carries it" -- and both were
// corrected; nothing read that prose, so nothing would have caught it drifting
// back. This repository has shipped prose that outlived its mechanism often
// enough for that to be the failure class worth a file of its own.
//
// So the counts are MEASURED out of `cli.mjs` and the doctrine is required to
// spell those same counts in words: if a third error path is ever added, the
// measured count becomes 3, the words "both"/"two" stop being accepted, and
// every document making the claim reddens until it is rewritten. The prose
// cannot drift from the code without one of the two moving first.
//
// Scope is DERIVED, never listed: every skill whose `profile.ts` declares an
// `objective`, plus every `.claude/agents/*.md` bound to one of those skills by
// its own `Skill:` path. A new agent bound to a deliberation domain is checked
// the day it is written, without this file being told about it.
import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';

const ENGINE_PATH = path.resolve('skills/_core/deliberation/engine/cli.mjs');
const SKILLS_DIR = path.resolve('skills');
const AGENTS_DIR = path.resolve('.claude/agents');
const engine = await readFile(ENGINE_PATH, 'utf8');

// The measured reach. `EMISSION` counts every site that attaches the north to
// something a reader receives; `ERROR_PATH` counts the subset sitting inside an
// `status: 'error'` payload. Their difference is the STATUS site.
const EMISSION_SITES = [...engine.matchAll(/objective: domainProfileModule\.DOMAIN\.objective/g)].length;
const ERROR_PATH_SITES = [...engine.matchAll(/status: 'error', message: [^}]*objective: domainProfileModule\.DOMAIN\.objective/g)].length;
const STATUS_SITES = EMISSION_SITES - ERROR_PATH_SITES;

const NUMBER_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
// English lets a count of two be written either way, and the doctrine uses
// "both". Every other count has exactly one spelling here on purpose: a doc
// that says "three" while the engine emits at two sites is the drift this file
// exists to catch.
const countWords = (n) => (n === 2 ? ['both', 'two'] : [NUMBER_WORDS[n] ?? String(n)]);

// The claim the correction removed, in the shapes it could come back as.
const FALSE_REACH = [
	/every refusal[^.]{0,80}carr/i,
	/carried by every refusal/i,
	/all refusals[^.]{0,80}carr/i,
	/every refusal, without exception/i,
];

const flatten = (text) => text.replace(/\s+/g, ' ').trim();

async function northDeclaringSkills() {
	const entries = await readdir(SKILLS_DIR, { withFileTypes: true });
	const skills = [];
	for (const entry of entries) {
		if (!entry.isDirectory() || entry.name === '_core') continue;
		const profile = await readFile(path.join(SKILLS_DIR, entry.name, 'profile.ts'), 'utf8').catch(() => null);
		if (profile === null || !/\n\tobjective: \{/.test(profile)) continue;
		skills.push(entry.name);
	}
	return skills;
}

// Every document that speaks for one of those domains: the skill's own doctrine
// and every agent that binds to it. The binding is read from the agent's body
// path, exactly as `test_agents.py::bound_skill` reads it -- never from the
// agent's filename, which names the STRETCH and need not match a skill at all.
async function doctrineDocuments() {
	const skills = await northDeclaringSkills();
	const docs = [];
	for (const skill of skills) {
		const file = path.join(SKILLS_DIR, skill, 'SKILL.md');
		docs.push({ label: `${skill}/SKILL.md`, skill, kind: 'skill', text: await readFile(file, 'utf8') });
	}
	const agents = await readdir(AGENTS_DIR, { withFileTypes: true });
	for (const entry of agents) {
		if (!entry.isFile() || !entry.name.endsWith('.md')) continue;
		const text = await readFile(path.join(AGENTS_DIR, entry.name), 'utf8');
		const bound = text.match(/\.claude\/skills\/([\w-]+)\/SKILL\.md/);
		if (!bound || !skills.includes(bound[1])) continue;
		docs.push({ label: `agents/${entry.name}`, skill: bound[1], kind: 'agent', text });
	}
	return { skills, docs };
}

const { skills, docs } = await doctrineDocuments();

test('the engine emits the north at a countable, non-zero set of sites', () => {
	// If either regex ever stops matching, every assertion below would compare
	// the doctrine against zero and pass for the wrong reason.
	assert.ok(ERROR_PATH_SITES > 0, 'no error path matched -- the count this file spells in words is derived from nothing');
	assert.ok(STATUS_SITES > 0, `the STATUS site did not match: ${EMISSION_SITES} emissions, ${ERROR_PATH_SITES} of them on error paths`);
	assert.equal(EMISSION_SITES, STATUS_SITES + ERROR_PATH_SITES);
});

test('every north-declaring domain has doctrine, and every agent bound to one is in scope', () => {
	assert.ok(skills.length >= 2, `expected at least two north-declaring skills, found ${skills.length}: ${skills.join(', ')}`);
	const agentDocs = docs.filter((doc) => doc.kind === 'agent');
	assert.ok(agentDocs.length >= 1, 'no agent binds to a north-declaring skill -- every per-document check below would be vacuous');
	for (const skill of skills) {
		assert.ok(docs.some((doc) => doc.kind === 'skill' && doc.skill === skill), `${skill} declares a north and has no SKILL.md doctrine`);
	}
});

for (const { label, text } of docs) {
	test(`${label}: states the north's actual reach, and claims no more`, () => {
		const flat = flatten(text);

		// The two halves of the reach, each named.
		assert.match(flat, /`STATUS` reports (?:it|the `objective` block) above the inventory/,
			`${label} does not say STATUS carries the north`);
		const words = countWords(ERROR_PATH_SITES).join('|');
		assert.match(flat, new RegExp(`\\b(?:${words})\\b of [^.]{0,40}CLI-level error paths carry it`),
			`${label} does not spell the engine's measured error-path count (${ERROR_PATH_SITES}) in words`);

		// And the boundary: that those are ALL of it, and what falls outside.
		assert.match(flat, /that is its complete reach/,
			`${label} names the sites without saying they are the whole of it`);
		// Deliberately not `[^.]` here: the thing it is returned FROM is
		// `tool.execute`, whose own dot would end the class.
		assert.match(flat, /typed refusal returned as a value from .{0,30}?does not/,
			`${label} does not exclude a typed refusal returned as a value, which carries no north`);

		// The corrected claim, in the shapes it could return as.
		for (const pattern of FALSE_REACH) {
			assert.doesNotMatch(flat, pattern,
				`${label} claims a broader reach than the engine has: a refusal returned as a value from tool.execute carries no objective`);
		}
	});
}

test('a doctrine that spells the total site count spells the measured one', () => {
	// The tightest tie available: `proposal-deliberation/SKILL.md` says "those
	// three sites". That word is not allowed to be a different number than the
	// engine's own.
	const spellings = [];
	for (const { label, text } of docs) {
		const stated = flatten(text).match(/\b(zero|one|two|three|four|five|six|seven|eight|nine)\b sites/i);
		if (!stated) continue;
		spellings.push(label);
		assert.equal(stated[1].toLowerCase(), NUMBER_WORDS[EMISSION_SITES],
			`${label} says "${stated[1]} sites"; the engine emits the north at ${EMISSION_SITES}`);
	}
	assert.ok(spellings.length >= 1,
		'no doctrine document states how many sites emit the north -- this check compared nothing');
});
