// D1 (this repository's own fix log): `experimental-deliberation`'s `references/usage.md`
// contradicted `SKILL.md` on three load-bearing facts, all three times on the side the code
// disagreed with. Nothing held the reference doc against the code or against SKILL.md, so the
// contradiction shipped and sat there. This file is the guard: it derives facts out of the
// running engine and out of SKILL.md's own headings, and requires usage.md to agree, the same
// way `deliberation-doctrine-reach.test.mjs` requires doctrine to spell a MEASURED site count
// rather than a remembered one.
//
// Three checks:
//   1. Every `../SKILL.md#anchor` usage.md links to must be a heading SKILL.md actually has.
//      This is the mechanical half of D1: the link decayed silently when the heading it pointed
//      at was renamed, and nothing noticed.
//   2. The retired claims themselves ("the accept turn does not publish", "targetRevision is the
//      literal r01", the hardcoded `-r(\d+)` diagnosis) must not reappear in usage.md's prose.
//   3. The worked `CREATE_INITIAL_REVISION` example usage.md shows -- request AND claimed
//      response -- is extracted verbatim out of the doc and actually run against a real fixture.
//      An example nobody runs is how three of these got past everyone; this makes not running it
//      impossible to keep doing unnoticed.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const skillDir = path.join(repoRoot, 'skills/experimental-deliberation');
const cliPath = path.join(skillDir, 'cli.mjs');
const skillMdPath = path.join(skillDir, 'SKILL.md');
const usageMdPath = path.join(skillDir, 'references/usage.md');

const skillMd = await readFile(skillMdPath, 'utf8');
const usageMd = await readFile(usageMdPath, 'utf8');

// ---------------------------------------------------------------------------
// A minimal GitHub-flavored heading slug -- just enough for the headings this
// repository actually writes (no footnotes, no emoji, no non-ASCII beyond
// straight punctuation). Good enough to catch a decayed link; not a general
// Markdown-anchor library.
// ---------------------------------------------------------------------------
function githubSlug(heading) {
	return heading
		.toLowerCase()
		.replace(/[`*_]/g, '')
		.trim()
		.replace(/[^\w\- ]+/g, '')
		.trim()
		.replace(/\s+/g, '-');
}

function headingSlugs(markdown) {
	const slugs = new Set();
	const seen = new Map();
	for (const match of markdown.matchAll(/^#{1,6}\s+(.+)$/gm)) {
		let slug = githubSlug(match[1]);
		const count = seen.get(slug) ?? 0;
		seen.set(slug, count + 1);
		if (count > 0) slug = `${slug}-${count}`;
		slugs.add(slug);
	}
	return slugs;
}

// ---------------------------------------------------------------------------
// 1. The dangling-anchor class of drift: a cross-file link that survives the
//    heading rename it pointed at.
// ---------------------------------------------------------------------------

test('every ../SKILL.md#anchor referenced from usage.md resolves to a real SKILL.md heading', () => {
	const slugs = headingSlugs(skillMd);
	assert.ok(slugs.size > 10, `expected many headings in SKILL.md, found ${slugs.size} -- this check compared against too little`);
	const refs = [...usageMd.matchAll(/\.\.\/SKILL\.md#([a-z0-9-]+)/g)].map((m) => m[1]);
	assert.ok(refs.length > 0, 'usage.md carries no ../SKILL.md#anchor link -- this check compared nothing');
	for (const ref of refs) {
		assert.ok(slugs.has(ref), `../SKILL.md#${ref} matches no heading SKILL.md actually has`);
	}
});

// ---------------------------------------------------------------------------
// 2. The retired claims, in the shapes they could come back as.
// ---------------------------------------------------------------------------

const RETIRED_CLAIMS = [
	/in this domain it does not get there/i,
	/does not publish in this domain/i,
	/known-limit-the-accept-turn-does-not-publish/i,
	/the cause is in the shared core/i,
	/no change inside this skill fixes it/i,
	/literal string `r01`/i,
	/nothing validates v1'?s content/i,
];

test('usage.md does not restate the retired accept-turn or targetRevision claims', () => {
	for (const pattern of RETIRED_CLAIMS) {
		assert.doesNotMatch(usageMd, pattern, `usage.md still carries a retired claim matching ${pattern}`);
	}
});

// ---------------------------------------------------------------------------
// 3. The worked example, driven for real.
// ---------------------------------------------------------------------------

/** Finds the first ```lang fence at or after `fromIndex` in `markdown`. Returns its inner text and the index just past the closing fence. */
function extractFencedBlock(markdown, fromIndex, lang) {
	const fenceRe = new RegExp('```' + lang + '\\n([\\s\\S]*?)\\n```', 'g');
	fenceRe.lastIndex = fromIndex;
	const match = fenceRe.exec(markdown);
	assert.ok(match, `no \`\`\`${lang} fence found in usage.md at or after index ${fromIndex}`);
	return { text: match[1], endIndex: fenceRe.lastIndex };
}

test('the worked CREATE_INITIAL_REVISION example in usage.md, run for real, produces the status, targetRevision and targetFilename the doc claims', async () => {
	const anchor = usageMd.indexOf('## Creating the first managed version');
	assert.ok(anchor >= 0, 'usage.md dropped its "Creating the first managed version" section -- nothing to extract');

	const bash = extractFencedBlock(usageMd, anchor, 'bash');
	const requestMatch = bash.text.match(/cli\.mjs '([\s\S]+)'\s*$/);
	assert.ok(requestMatch, `could not find the cli.mjs request payload in the fenced block:\n${bash.text}`);
	const request = JSON.parse(requestMatch[1]);
	assert.equal(request.operation, 'CREATE_INITIAL_REVISION', 'the worked example is no longer a CREATE_INITIAL_REVISION call');

	const responseBlock = extractFencedBlock(usageMd, bash.endIndex, 'json');
	const documented = JSON.parse(responseBlock.text);

	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-usage-doc-'));
	try {
		await mkdir(path.join(projectRoot, 'guidance/data-paper/pilot'), { recursive: true });
		await writeFile(
			path.join(projectRoot, 'guidance/data-paper/pilot/pilot.md'),
			'# Pilot dataset guidance\nThe dataset supports accuracy claims under domain shift.\n',
			'utf8',
		);
		// A published managed proposal, not just the directory. `proposals` is declared
		// `required: true`, and a required source is required for its CONTENT: an empty
		// directory now refuses `REQUIRED_SOURCE_EMPTY` instead of letting v1 render
		// against nothing. This fixture used to create the bare directory and pass --
		// which meant the worked example in usage.md was certified against an experiments
		// plan with no proposal behind it at all, exactly what this domain's own doctrine
		// says is testing nothing.
		await mkdir(path.join(projectRoot, 'proposals'), { recursive: true });
		await writeFile(
			path.join(projectRoot, 'proposals', 'research-plan-lumen-thesis-r01.md'),
			'# Lumen thesis proposal r01\nThe method is claimed to hold accuracy under domain shift.\n',
			'utf8',
		);

		// `package.json`'s own `test` script pins `DELIBERATION_DOMAIN_PROFILE` to the
		// MATHEMATICAL sibling's profile for the whole run (see
		// `experimental-deliberation-initial-revision.test.mjs`'s header for why); left
		// inherited, that env var would win over `cli.mjs`'s own `??=` default and this
		// test would silently certify the wrong domain. Overriding it here is what makes
		// this a check on `experimental-deliberation`, not a vacuous pass against `v01`
		// happening to equal whatever the other profile emits.
		const profilePath = path.join(skillDir, 'profile.ts');
		const { stdout } = await execFileAsync('node', [cliPath, JSON.stringify(request)], {
			env: { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, PROPOSAL_DELIBERATION_PROJECT_ROOT: projectRoot },
		});
		const actual = JSON.parse(stdout);

		assert.equal(actual.status, documented.status,
			`usage.md's worked example claims status ${JSON.stringify(documented.status)}, but running the exact same request against a real fixture returned ${JSON.stringify(actual.status)}: ${stdout}`);
		if (documented.targetRevision !== undefined) {
			assert.equal(actual.targetRevision, documented.targetRevision,
				`usage.md claims targetRevision ${JSON.stringify(documented.targetRevision)}; the engine actually returned ${JSON.stringify(actual.targetRevision)}`);
		}
		if (documented.targetFilename !== undefined) {
			assert.equal(actual.targetFilename, documented.targetFilename,
				`usage.md claims targetFilename ${JSON.stringify(documented.targetFilename)}; the request's own idea text actually produced ${JSON.stringify(actual.targetFilename)} -- the shown request and the shown response no longer describe the same run`);
		}
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});
