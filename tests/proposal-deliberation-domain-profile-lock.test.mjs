import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';

const coreDir = path.resolve('skills/_core/deliberation/engine');
const skillsDir = path.resolve('skills');
const suiteDir = path.resolve('tests');

// The lock no longer reads one hardcoded profile path (Phase 3, change 11, "a
// north a second domain can hold"): it globs every `*/profile.ts` under
// `skills/`, so a domain added later is held to the same rule without
// this file being edited to know about it.
async function discoverProfiles() {
	const entries = await readdir(skillsDir, { withFileTypes: true });
	const profiles = [];
	for (const entry of entries) {
		if (!entry.isDirectory() || entry.name === '_core') continue;
		const profilePath = path.join(skillsDir, entry.name, 'profile.ts');
		const source = await readFile(profilePath, 'utf8').catch(() => null);
		if (source === null) continue;
		const declared = [...source.matchAll(/^\t(?:deriveBase|baseLabel|baseLabelLong|exampleSlug): "([^"]+)",$/gm)].map((m) => m[1]);
		// Exactly ONE leading tab: the top-level `names` field, never a nested one
		// (`sourceAuthority.names` sits at two tabs and names a SOURCE path, not
		// this domain itself).
		const names = [...(source.match(/^\tnames: \[([^\]]*)\],$/m)?.[1] ?? '').matchAll(/"([^"]+)"/g)].map((m) => m[1]);
		const artifactDeclared = [...source.matchAll(/^\t\t(?:directory|stem|sidecarRoot): "([^"]+)",$/gm)].map((m) => m[1]);
		profiles.push({ skillName: entry.name, source, declared, names, artifactDeclared });
	}
	return profiles;
}

/** Same one-tab-indent block extractor the generalized objective-flow test uses
 * (`proposal-deliberation-objective-flow.test.mjs`), duplicated rather than
 * imported: these two files exercise the SAME source text for different
 * purposes, and a shared helper module would be one more file the domain lock
 * itself would then have to scan and clear. */
function extractBlock(source, key) {
	const openMarker = `\n\t${key}: {`;
	const openIdx = source.indexOf(openMarker);
	if (openIdx === -1) return null;
	const blockStart = openIdx + 1;
	const closeIdx = source.indexOf('\n\t},', blockStart);
	if (closeIdx === -1) return null;
	return source.slice(blockStart, closeIdx);
}

function objectiveWords(block) {
	const texts = [];
	for (const re of [/purpose:\s*"([^"]*(?:\\.[^"]*)*)"/g, /establishes:\s*"([^"]*(?:\\.[^"]*)*)"/g, /behindWhen:\s*"([^"]*(?:\\.[^"]*)*)"/g]) {
		texts.push(...[...block.matchAll(re)].map((m) => m[1]));
	}
	const arrivalMatch = block.match(/\n\t+arrival:\s*"([^"]*(?:\\.[^"]*)*)"/);
	if (arrivalMatch) texts.push(arrivalMatch[1]);
	const humanStopsMatch = block.match(/\n\t+humanStops:\s*\[([\s\S]*?)\n\t+\],/);
	if (humanStopsMatch) texts.push(...[...humanStopsMatch[1].matchAll(/"([^"]*(?:\\.[^"]*)*)"/g)].map((m) => m[1]));
	const joined = texts.join(' ');
	return new Set([...joined.matchAll(/[A-Za-z]{5,}/g)].map((m) => m[0].toLowerCase()));
}

async function discoverDocs() {
	const entries = await readdir(skillsDir, { withFileTypes: true });
	const docs = [];
	for (const entry of entries) {
		if (!entry.isDirectory()) continue;
		docs.push(path.join(skillsDir, entry.name, 'SKILL.md'));
		docs.push(path.join(skillsDir, entry.name, 'references', 'usage.md'));
	}
	docs.push(path.resolve('README.md'));
	return docs;
}

async function readCoreFiles() {
	const coreEntries = (await readdir(coreDir, { recursive: true, withFileTypes: true }))
		.filter((e) => e.isFile() && (e.name.endsWith('.ts') || e.name.endsWith('.mjs')))
		.map((e) => path.join(e.parentPath ?? e.path, e.name));
	return Promise.all(coreEntries.map(async (file) => [path.relative(coreDir, file), await readFile(file, 'utf8')]));
}

async function readSuiteFiles() {
	const suiteEntries = (await readdir(suiteDir, { recursive: true, withFileTypes: true }))
		.filter((e) => e.isFile() && e.name.endsWith('.mjs'))
		.map((e) => path.join(e.parentPath ?? e.path, e.name));
	return Promise.all(suiteEntries.map(async (file) => [path.relative(suiteDir, file), await readFile(file, 'utf8')]));
}

const profiles = await discoverProfiles();
const coreSources = await readCoreFiles();
const suiteSources = await readSuiteFiles();

// Every one of a profile's `names` values that is legitimately a MODULE
// NAMESPACE rather than a research subject: it equals the skill's own
// directory name. Derived, never hand-exempted -- a research-subject proper
// noun declared by `proposal-deliberation`'s own profile does not equal that
// profile's directory name, so it stays in scope; `experimental-deliberation`
// (the module namespace) equals its own directory exactly, and 25 occurrences
// across 6 node tests are import paths, tmpdir prefixes and sidecar-root
// assertions, not a domain a fixture spells about a project it has nothing to
// do with.
function selfNamespaceNames(profile) {
	return new Set(profile.names.filter((name) => name === profile.skillName));
}

test('at least two profiles are discovered, or every check below would pass vacuously', () => {
	assert.ok(profiles.length >= 2, `expected at least 2 profiles under skills/*/profile.ts, found ${profiles.length}`);
	for (const profile of profiles) {
		assert.equal(profile.declared.length, 4, `expected 4 declared values in ${profile.skillName}, found ${profile.declared.length}`);
		assert.ok(profile.names.length > 0, `${profile.skillName} declares no domain name, so the lock below would pass vacuously`);
		for (const value of [...profile.declared, ...profile.names]) assert.notEqual(value.trim(), '');
	}
});

test('every declared name really is that domain speaking', () => {
	for (const profile of profiles) {
		const unused = profile.names.filter((n) => !profile.declared.some((v) => v.toLowerCase().includes(n.toLowerCase())) && !profile.source.toLowerCase().includes(n.toLowerCase()));
		assert.deepEqual(unused, [], `${profile.skillName}: a name no profile value contains is not this domain naming itself`);
	}
});

/** A provenance citation -- `sdd/<change-name>` -- naming the change a piece of
 * the engine came out of.
 *
 * These are NOT the engine knowing which domain it serves, which is the one
 * thing the lock below exists to catch. They are references to real recorded
 * changes, and a change's name is fixed the day it is recorded: rewording the
 * citation does not rename the change, it only makes the citation point at
 * nothing. Sixteen of them are in the engine today, all three distinct names
 * belonging to changes that shaped it while it still lived inside one skill.
 *
 * Structural rather than a list of the three, so a citation written tomorrow is
 * exempt for the same reason and nobody has to remember to widen anything.
 *
 * What this does NOT defend against: someone spelling a domain name and dressing
 * it as `sdd/...` to get past the lock. That is a deliberate evasion, and this
 * repository already states that standard for its own seal -- a check like this
 * defends against an unaware edit, never a determined one. The exemption is
 * narrow on purpose: it removes the citation's own text from the scan and
 * nothing else on the line.
 */
function withoutProvenanceCitations(source) {
	return source.replace(/sdd\/[A-Za-z0-9._-]+/g, 'sdd/<cited-change>');
}

/** The declared list of identifiers this engine ANSWERED TO BEFORE.
 *
 * `SUPERSEDED_PARSER_VERSIONS` exists to keep reading state written under an
 * older spelling of the parser version, and it cannot do that job without
 * spelling it. This is the same kind of thing as a provenance citation: a
 * reference to the past, not the engine knowing which domain it serves today.
 * Refusing it would force a choice between a green lock and a readable history,
 * and the history would lose.
 *
 * Deliberately anchored to that one constant rather than to any frozen array:
 * the carve-out has to be small enough that nobody can park a live identifier
 * inside it. Writes always record `PARSER_VERSION`, which is scanned normally,
 * so a domain name reaching stored state still reddens this lock.
 */
function withoutSupersededIdentifiers(source) {
	return source.replace(
		/(SUPERSEDED_PARSER_VERSIONS\s*=\s*Object\.freeze\()\[[^\]]*\]/,
		'$1[/* superseded spellings */]',
	);
}

test('no file in the shared core names any domain', () => {
	assert.ok(coreSources.length > 40, `expected the whole engine, scanned ${coreSources.length}`);
	const leaks = [];
	for (const [rel, rawSource] of coreSources) {
		const source = withoutSupersededIdentifiers(withoutProvenanceCitations(rawSource));
		const lower = source.toLowerCase();
		for (const profile of profiles) {
			for (const value of profile.declared) if (source.includes(value)) leaks.push(`${rel} spells ${JSON.stringify(value)} (${profile.skillName})`);
			// The core scan gets NO self-namespace exemption, unlike the suite scan
			// below: a core file naming a domain by its own module directory is a
			// real coupling leak (measured: `initial-revision-creation.ts` named
			// `experimental-deliberation` by directory before this reword), not an
			// import path a fixture legitimately needs.
			for (const name of profile.names) if (lower.includes(name.toLowerCase())) leaks.push(`${rel} names ${JSON.stringify(name)} (${profile.skillName})`);
		}
	}
	assert.deepEqual([...new Set(leaks)], [], 'the core must read these off the host-chosen profile, never spell them');
});

test('the provenance exemption removes citations and nothing else', () => {
	// Red-first: without both halves asserted, the exemption could be a blanket
	// that silences the whole lock and nothing would say so. The first half proves
	// it exempts; the second proves it still fires on the same name spelled
	// outside a citation, on the SAME line as one.
	const line = 'const x = 1; // (design `sdd/proposal-deliberation-ambient-model`) for proposal-deliberation';
	const cleaned = withoutProvenanceCitations(line);
	assert.ok(!cleaned.includes('sdd/proposal-deliberation-ambient-model'),
		'the citation itself must leave the scanned text');
	assert.ok(cleaned.includes('for proposal-deliberation'),
		'a domain named outside a citation must survive the exemption and still be caught');
	assert.ok(coreSources.some(([, source]) => /sdd\/[A-Za-z0-9._-]+/.test(source)),
		'no citation found in the engine at all -- this exemption would be guarding nothing');
});

test('the superseded-identifier exemption covers that one list and nothing else', () => {
	// Same two halves, same reason: an exemption that cannot be shown to still
	// let the lock fire is indistinguishable from switching the lock off.
	const line = "export const SUPERSEDED_PARSER_VERSIONS = Object.freeze(['proposal-deliberation/2']);\nconst live = 'proposal-deliberation/3';";
	const cleaned = withoutSupersededIdentifiers(line);
	assert.ok(!cleaned.includes("'proposal-deliberation/2'"),
		'the superseded spelling must leave the scanned text');
	assert.ok(cleaned.includes("'proposal-deliberation/3'"),
		'an identifier outside that list must survive the exemption and still be caught');

	const types = coreSources.find(([rel]) => rel === 'types.ts');
	assert.ok(types, 'types.ts not scanned -- this exemption would be guarding nothing');
	assert.match(types[1], /SUPERSEDED_PARSER_VERSIONS\s*=\s*Object\.freeze\(\[/,
		'the constant this exemption is anchored to no longer has that shape');
	assert.ok(types[1].includes("'proposal-deliberation/2'"),
		'the superseded spelling is gone from the list -- state written under it can no longer be read, '
		+ 'and this exemption is now guarding nothing');
});

test('every profile declares its artifact namespace values (directory, stem, sidecarRoot)', () => {
	for (const profile of profiles) {
		assert.equal(profile.artifactDeclared.length, 3, `expected 3 declared artifact values in ${profile.skillName}, found ${profile.artifactDeclared.length}`);
		for (const value of profile.artifactDeclared) assert.notEqual(value.trim(), '');
		assert.ok(profile.artifactDeclared.some((v) => v.startsWith('.')), `${profile.skillName}: sidecarRoot must be declared WITH its leading dot`);
	}
});

test('no file in the shared core spells any domain\'s artifact namespace', () => {
	assert.ok(coreSources.length > 40, `expected the whole engine, scanned ${coreSources.length}`);
	const leaks = [];
	for (const [rel, source] of coreSources) {
		for (const profile of profiles) {
			for (const value of profile.artifactDeclared) if (source.includes(value)) leaks.push(`${rel} spells ${JSON.stringify(value)} (${profile.skillName})`);
		}
	}
	assert.deepEqual([...new Set(leaks)], [], 'core must read the managed directory/stem/sidecar-root off the host-chosen profile, never spell them');
});

test('no test in the node suite names a domain either, except a profile\'s own module namespace', () => {
	assert.ok(suiteSources.length > 30, `expected the whole node suite, scanned ${suiteSources.length}`);
	for (const required of ['proposal-workspace.test.mjs', 'proposal-deliberation-v2-source-routing.test.mjs', 'proposal-deliberation-domain-profile-lock.test.mjs'])
		assert.ok(suiteSources.some(([rel]) => rel === required), `${required} is not in the scanned surface`);
	const leaks = [];
	for (const [rel, source] of suiteSources) {
		const lower = source.toLowerCase();
		for (const profile of profiles) {
			const selfNames = selfNamespaceNames(profile);
			for (const value of profile.declared) if (source.includes(value)) leaks.push(`${rel} spells ${JSON.stringify(value)} (${profile.skillName})`);
			for (const name of profile.names) {
				if (selfNames.has(name)) continue;
				if (lower.includes(name.toLowerCase())) leaks.push(`${rel} names ${JSON.stringify(name)} (${profile.skillName})`);
			}
		}
	}
	assert.deepEqual([...new Set(leaks)], [], 'a fixture must read these off the profile too: a general forge does not shape its tests around one research project');
});

test('no document tells a reader to run the bare core', async () => {
	const docs = await discoverDocs();
	for (const doc of docs) {
		const text = await readFile(doc, 'utf8').catch(() => null);
		if (text === null) continue;
		assert.equal(/_core\/deliberation\/engine\/cli\.mjs/.test(text), false, `${doc} invokes the core directly, which refuses without a profile`);
	}
});

test('the core refuses to serve a domain it was not given', async () => {
	const resolver = await readFile(path.join(coreDir, 'domain-profile.ts'), 'utf8');
	assert.match(resolver, /DELIBERATION_DOMAIN_PROFILE_REQUIRED/, 'no profile must be a refusal, not a default');
	assert.equal(/proposalDeliberationProfile/.test(resolver), false, 'the resolver must carry no domain of its own');
});

// --- C-1: absence (design.md, Decision C) ---------------------------------
//
// The layer that would have caught the original defect regardless of what
// any domain called its stages: the north's TEXT must be reachable only
// through `DOMAIN.objective`, never declared inline in a core file. Also
// asserted, in the same words, by `proposal-deliberation-objective-flow.test.mjs`
// (design.md's own File Changes table places C-1 there, not here -- see this
// change's apply report for the discrepancy against tasks.md's placement).

// --- C-2: extended lock (above) -------------------------------------------
//
// `discoverProfiles`/`selfNamespaceNames` are the extension: every
// `*/profile.ts` is scanned, not one hardcoded path, and the suite scan's
// self-namespace exemption is derived from each profile's own `skillName`
// rather than a hand-written exception list.

// --- C-3: derived subject words --------------------------------------------
//
// A word (>=5 chars) appearing in exactly one profile's `objective` text
// (purpose, every stage's establishes/behindWhen, arrival, humanStops) is
// that domain's subject matter and may not appear in core as a standalone
// word. A word both profiles' norths use is engine vocabulary, never
// flagged. No hand-written denylist: every word below is derived from the
// profiles on disk. Word-boundary matching (not substring): a subject word
// living inside an identifier -- `SAFE_EQUATION_LABEL`, `equationLabel`,
// `display_equation`, `CLEANUP_EQUATION_FORBIDDEN` -- is a structural TYPE
// NAME, not new prose naming a domain's subject, and C-1 above is what
// would have caught this defect regardless of vocabulary; C-3 catches a
// domain word freshly TYPED into a comment or a message, which is a
// different failure and needs a different signal.
function buildDenylist(profileList) {
	const wordSets = new Map();
	for (const profile of profileList) {
		const block = extractBlock(profile.source, 'objective');
		assert.ok(block, `${profile.skillName}/profile.ts declares no objective block for C-3 to read`);
		wordSets.set(profile.skillName, objectiveWords(block));
	}
	const denylist = new Map();
	for (const [skillName, words] of wordSets) {
		const others = new Set();
		for (const [otherName, otherWords] of wordSets) {
			if (otherName === skillName) continue;
			for (const w of otherWords) others.add(w);
		}
		for (const word of words) {
			if (!others.has(word)) denylist.set(word, skillName);
		}
	}
	return denylist;
}

// Pre-existing residue, measured rather than assumed (task 3.6 and its
// generalization -- see apply report): two words end up in the derived
// denylist above while ALSO being deeply pre-existing, load-bearing engine
// vocabulary that predates this change and is out of scope to remove here.
// Both are pinned by EXACT exact occurrence count and sorted file list, so
// either one silently growing (a NEW file starting to spell it, or MORE
// occurrences appearing) is a hard failure below -- visible, and can only
// shrink deliberately, never exempted into silence:
//
//   "equation" -- a core TYPE NAME (`equationLabel`, `SAFE_EQUATION_LABEL`,
//   `display_equation`, `CLEANUP_EQUATION_FORBIDDEN`) and the name of a real
//   EditAction anchor feature (`proposal-workspace.ts`'s "equation anchor"),
//   one of them inside the byte-frozen `patch-compiler.ts`. Measured task
//   0.2 at 126 occurrences / 11 files (`rg -o`, an occurrence count rather
//   than a line count, because the two diverge on multi-match lines) BEFORE
//   Phase 1 deleted `cli.mjs`'s own `OBJECTIVE_FLOW` literal, which itself
//   spelled "equation" twice (`composed.establishes`/`behindWhen`) -- that
//   deletion is this change's own doing, moving the text to a profile, and
//   correctly SHRINKS the residue to the 124/10 files re-measured below.
//
//   "proposal" -- NOT anticipated by design.md, which named only "equation".
//   Measured during apply: `proposal-deliberation`'s own BYTE-IDENTICAL
//   `objective.stages[1].behindWhen` text ends "...approving its own
//   proposal", a sentence this change may not alter (task 1.3). "proposal"
//   is also the engine's own pre-parametrization naming residue -- the
//   `PROPOSAL_DELIBERATION_PROJECT_ROOT`/`PROPOSAL_DELIBERATION_SESSION_ID`
//   environment variables, `proposal-workspace.ts`'s own filename, and
//   dozens of comments -- shared infrastructure naming, not a NEW subject
//   leak. Rewording it across 24 files (some of them tool-facing prompt
//   text and runtime error messages other tests may assert on) would be
//   disproportionate and outside this phase's scope; pinning it the same
//   way "equation" is pinned is the same measured, visible, non-silent
//   treatment design already prescribes for the first residue.
const PINNED_RESIDUE = new Set(['equation', 'proposal']);
const EQUATION_RESIDUE = { substringCount: 124, files: ['cleanup-planner.ts', 'document-index.ts', 'edit-planner.ts', 'lifecycle-service.ts', 'orchestrator.ts', 'patch-compiler.ts', 'proposal-workspace.ts', 'reference-index.ts', 'target-resolver.ts', 'types.ts'] };
// 192 -> 191: `revision-lifecycle-store.ts` stopped declaring the artifact marker as
// its own literal and reads `artifactConfig.marker` like every other core site. The
// literal carried one `proposal` (its own marker bytes), so the count shrank by one.
// Recorded rather than absorbed, in either direction: an unexplained move looks
// exactly like a rename campaign from outside.
// 191 -> 177: fourteen comments in the engine named a domain outright -- the engine
// calling itself "the <domain> engine", and its own contract documented by pointing
// at one sibling's module by directory. Both are the coupling the core-scan lock
// exists to catch, and the second was bad documentation besides: naming ONE consumer
// in a neutral engine's docstring implies that consumer is special, when there are
// two today and could be five. Reworded to what they actually mean ("the deliberation
// engine", "the host-chosen profile's own preservation module"), which is shorter,
// truer, and does not age when a third skill arrives. The remaining residue is the
// engine's own subject noun -- a proposal IS what it deliberates over -- plus six
// live identifiers migrating separately.
const PROPOSAL_RESIDUE = { wordBoundaryCount: 169, files: ['_pi-compat/pi-coding-agent.ts', 'ambient-supplied-planner.ts', 'artifact-naming.ts', 'chat-deliberation.ts', 'cli.mjs', 'conceptual-planner.ts', 'consistency-audit.ts', 'domain-profile.ts', 'draft-materialization.ts', 'edit-planner.ts', 'exports.ts', 'initial-revision-creation.ts', 'orchestrator.ts', 'patch-compiler.ts', 'proposal-workspace-adapter.ts', 'proposal-workspace.ts', 'reference-index.ts', 'revision-lifecycle-store.ts', 'runtime-metrics.ts', 'smoke-runner.ts', 'successor-acceptance-registry.ts', 'types.ts'] };

test('C-3 vacuity guard: the denylist is non-empty, or this check would be vacuous', () => {
	const denylist = buildDenylist(profiles);
	assert.ok(denylist.size > 0, 'no profile pair produced a single-owner subject word -- C-3 would otherwise check nothing');
	// Design's own vacuity self-check (M6c): if two profiles' norths were
	// accidentally IDENTICAL text, every word would be shared and the
	// denylist would be empty. Confirming it is non-empty here is that same
	// self-check, run against the real profiles rather than a synthetic pair.
});

test('C-3: no NEW subject word from one domain\'s north appears in core', () => {
	assert.ok(coreSources.length > 40, `expected the whole engine, scanned ${coreSources.length}`);
	const denylist = buildDenylist(profiles);
	const leaks = [];
	for (const [rel, source] of coreSources) {
		for (const [word, owner] of denylist) {
			if (PINNED_RESIDUE.has(word)) continue;
			if (new RegExp(`\\b${word}\\b`, 'i').test(source)) leaks.push(`${rel} spells ${JSON.stringify(word)} (${owner}'s own north)`);
		}
	}
	assert.deepEqual(leaks, [], 'a core file must never spell a word belonging to only one domain\'s own north');
});

test('the pinned "equation" residue is measured, not assumed, and can only shrink', async () => {
	const leaks = [];
	let total = 0;
	for (const [rel, source] of coreSources) {
		const n = (source.match(/equation/gi) ?? []).length;
		if (n > 0) { total += n; leaks.push(rel); }
	}
	assert.equal(total, EQUATION_RESIDUE.substringCount, `"equation" substring occurrence count drifted from the pinned baseline (task 0.2); update EQUATION_RESIDUE deliberately if this shrink (or grow) is intended`);
	assert.deepEqual(leaks.sort(), EQUATION_RESIDUE.files, '"equation"\'s file list drifted from the pinned baseline');
});

test('the pinned "proposal" residue is measured, not assumed, and can only shrink', async () => {
	const leaks = [];
	let total = 0;
	for (const [rel, source] of coreSources) {
		const n = (source.match(/\bproposal\b/gi) ?? []).length;
		if (n > 0) { total += n; leaks.push(rel); }
	}
	assert.equal(total, PROPOSAL_RESIDUE.wordBoundaryCount, '"proposal" word-boundary occurrence count drifted from the pinned baseline');
	assert.deepEqual(leaks.sort(), PROPOSAL_RESIDUE.files, '"proposal"\'s file list drifted from the pinned baseline');
});
