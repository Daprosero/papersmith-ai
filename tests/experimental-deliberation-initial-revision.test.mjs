// Can the `experimental-deliberation` skill actually CREATE its first version -- and is what
// it reports back true of the file it just wrote?
//
// `tests/experimental-deliberation-publish.test.mjs` covers CREATE_SUCCESSOR: a v01 already on
// disk becoming a v02. Nothing covered the step before it, and three separate defects lived
// there, each invisible to the mathematical profile the suite is otherwise fixed to:
//
//   D1  `CREATE_INITIAL_REVISION` ran no content validation at all. `renderFromIdea` injects
//       every declared source's fragment VERBATIM, so a source document carrying a report
//       table that already has numbers in it became v1 unexamined. For a domain whose entire
//       canonical form is "the cells are empty because a run fills them", that is the one
//       thing the gate exists to prevent, and only a later successor whose locus happened to
//       cover that region would ever have noticed.
//   D2  the fragment loader descended exactly one directory level and read
//       `<folder>/<folder>.md`. A managed revision is a FLAT file, so declaring another
//       skill's managed directory as a required source enforced the directory's presence and
//       then delivered nothing out of it -- required, present, and silent.
//   D3  the first revision's label was the literal `'r01'` in seven places, while the file was
//       named by `artifact.revisionLabel(1)`. Under this domain that is `v01`, so a caller
//       reading the response got a revision label that no file on disk carries.
//
// And one more, prose rather than behaviour: the workspace's own JSON-Schema descriptions and
// refusal messages spelled `-rNN`, which is simply false for a domain whose revision prefix is
// `v`.
//
// A CHILD PROCESS, for the reason `experimental-deliberation-publish.test.mjs` sets out at
// length: `package.json`'s `test` script fixes `DELIBERATION_DOMAIN_PROFILE` to the
// MATHEMATICAL profile for the whole run, and `domain-profile.ts` reads it exactly once, at
// import time. Every assertion below would still pass in-process against the other domain --
// a `-r01.md` first revision is a perfectly good one -- and prove nothing. So the whole cycle
// runs in one spawned `node` with the variable repointed.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdir, mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const profilePath = path.join(repoRoot, 'skills/experimental-deliberation/profile.ts');
const piRoot = path.resolve('.');

// This domain declares three sources; two of them are `required: true`.
const DATA_PAPER = 'guidance/data-paper';
const PROPOSALS = 'proposals';

// The data paper, in the NESTED `<folder>/<folder>.md` shape the legacy single guide used and
// the mathematical sibling still depends on. Present here so the flat pass added for D2 is
// proven to be an ADDITION, not a replacement.
const DATA_PAPER_FRAGMENT = 'The dataset splits are fixed by the data paper and are never resampled per run.';

// The latest managed proposal: a FLAT file sitting directly in its own managed directory --
// which is what a managed revision is, and what the loader never picked up.
const PROPOSAL_FILENAME = 'research-concept-cross-site-latent-r03.md';
// Carries this domain's two declarations (change "the two declarations a plan owes") as
// EXTRA lines, appended to the original claim rather than replacing it, so
// `written.includes(PROPOSAL_FRAGMENT)` below still proves the whole fragment -- claim
// and declarations together -- reached v1 verbatim.
const PROPOSAL_FRAGMENT = `The proposal claims one shared latent code carries across acquisition sites.

**Dataset:** DomainShift-Synth, source/target split as distributed

**Validation scheme:** paired t-test, 5 seeds, 10 repetitions`;
// The same claim, WITHOUT either declaration -- mirrors `PROPOSAL_WITH_FILLED_TABLE`'s
// shape below: nothing here is malformed, the composed v1 is simply missing what the
// canonical form now demands, and `CREATE_INITIAL_REVISION` must refuse it exactly as it
// refuses a filled report-table cell.
const PROPOSAL_FRAGMENT_WITHOUT_DECLARATIONS = 'The proposal claims one shared latent code carries across acquisition sites.';

// The same flat proposal, carrying a report table whose body cell is already filled in. Nothing
// about this file is malformed; it is simply a document that reports a number, and an
// experiments document that swallows it whole has published a result nobody measured.
const PROPOSAL_WITH_FILLED_TABLE = `${PROPOSAL_FRAGMENT}

| Arm | Accuracy |
| --- | --- |
| Source only | 0.71 |
`;

const IDEA = 'Un plan experimental para medir la transferencia entre sitios de adquisicion. Cada corrida entrena en el sitio de origen y evalua en el sitio retenido.';

const HARNESS = `import path from 'node:path';
import { readdir, readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const engineDir = process.env.ENGINE_DIR;
const workspace = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));
const { DOMAIN } = await jiti.import(path.join(engineDir, 'domain-profile.ts'));
const projectRoot = process.env.PROJECT_ROOT;

const guard = workspace.createDocumentOperationGuard(projectRoot);
const tools = [];
workspace.createProposalDeliberationExtension({ projectRoot, operationGuard: guard })({ registerTool: (candidate) => tools.push(candidate), on: () => {} });
const tool = tools.find((candidate) => candidate.name === 'proposal_deliberation_execute');
const ctx = { model: { provider: 'anthropic', id: 'unused' }, sessionManager: { getSessionId: () => 'initial-revision-session' }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'unused', headers: {}, env: {} }) } };
const { details } = await tool.execute('initial-revision', { operation: 'CREATE_INITIAL_REVISION', instruction: process.env.IDEA }, undefined, undefined, ctx);

const guarded = workspace.createProposalWorkspaceTool(projectRoot, { operationGuard: guard });
const unguarded = workspace.createProposalWorkspaceTool(projectRoot);

// Real refusals, thrown by the running workspace. The description surface below is only half
// the caller-facing prose; the other half is what a caller is told when it gets the revision
// slug wrong, and that half lives in rejection messages no schema carries.
async function refusal(params) {
	try { await unguarded.execute('prose', params, undefined, undefined, ctx); return null; }
	catch (error) { return String(error?.message ?? error); }
}
const stem = DOMAIN.artifact.stem;
const refusals = [
	// A source that is not a managed revision filename at all.
	await refusal({ action: 'derive_successor', resource: 'proposal', source: 'not-a-managed-name.md', sourceSha256: 'a'.repeat(64), slug: 'cross-site-' + DOMAIN.artifact.revisionLabel(2), patches: [] }),
	// A root source whose target slug skips ahead instead of advancing by exactly one.
	await refusal({ action: 'derive_successor', resource: 'proposal', source: stem + '-' + DOMAIN.artifact.revisionLabel(1) + '.md', sourceSha256: 'a'.repeat(64), slug: DOMAIN.artifact.revisionLabel(9), patches: [] }),
];

// Every caller-visible string surface the workspace publishes, so the revision-label prose can
// be read off the running tools rather than off the source file.
const prose = JSON.stringify([
	guarded.description, guarded.promptGuidelines, JSON.stringify(guarded.parameters),
	unguarded.description, unguarded.promptGuidelines, JSON.stringify(unguarded.parameters),
	...tools.map((candidate) => [candidate.description, candidate.promptGuidelines]),
]);

const managedDirectory = path.join(projectRoot, DOMAIN.artifact.directory);
const onDisk = await readdir(managedDirectory).catch(() => []);
const written = details.targetFilename ? await readFile(path.join(managedDirectory, details.targetFilename), 'utf8') : null;

console.log(JSON.stringify({
	profile: { revisionPattern: DOMAIN.artifact.revisionPattern, stem: DOMAIN.artifact.stem, directory: DOMAIN.artifact.directory, firstLabel: DOMAIN.artifact.revisionLabel(1) },
	details,
	onDisk: onDisk.sort(),
	written,
	prose,
	refusals,
}));
`;

/**
 * One CREATE_INITIAL_REVISION turn, in one fresh child under this skill's own profile.
 * `proposalContent` is what the flat file in the managed proposals directory holds.
 */
async function createInitialRevision(proposalContent) {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-initial-'));
	const scratch = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-initial-harness-'));
	try {
		const nested = path.join(projectRoot, DATA_PAPER, 'acquisition-sites');
		await mkdir(nested, { recursive: true });
		await writeFile(path.join(nested, 'acquisition-sites.md'), DATA_PAPER_FRAGMENT, 'utf8');
		await mkdir(path.join(projectRoot, PROPOSALS), { recursive: true });
		await writeFile(path.join(projectRoot, PROPOSALS, PROPOSAL_FILENAME), proposalContent, 'utf8');
		const harnessPath = path.join(scratch, 'harness.mjs');
		await writeFile(harnessPath, HARNESS, 'utf8');
		const { stdout } = await execFileAsync('node', [harnessPath], {
			env: { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir, PROJECT_ROOT: projectRoot, IDEA },
			maxBuffer: 32 * 1024 * 1024,
		});
		return JSON.parse(stdout.trim().split('\n').pop());
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
		await rm(scratch, { recursive: true, force: true });
	}
}

let cleanRun;
/** The clean fixture: both required sources present, and nothing in either breaking canonical form. */
async function clean() {
	cleanRun ??= await createInitialRevision(`${PROPOSAL_FRAGMENT}\n`);
	return cleanRun;
}

// ---------------------------------------------------------------------------
// The guard against certifying the wrong domain
// ---------------------------------------------------------------------------

test('the creation runs under the experimental profile, not the mathematical one the suite is fixed to', async () => {
	const { profile } = await clean();
	// Without these, every assertion below would pass against the other domain and mean nothing.
	assert.equal(profile.revisionPattern, 'v', 'the mathematical profile spells its revisions with "r"');
	assert.equal(profile.stem, 'experiments');
	assert.equal(profile.directory, 'experiments');
	assert.equal(profile.firstLabel, 'v01');
});

// ---------------------------------------------------------------------------
// D3 -- the reported label is the file's own label
// ---------------------------------------------------------------------------

test('the created first revision reports the label its own filename carries, never the literal r01', async () => {
	const { details, onDisk } = await clean();
	assert.equal(details.status, 'created', JSON.stringify(details));
	assert.equal(details.targetRevision, 'v01',
		'the reported label is artifact.revisionLabel(1); "r01" is the literal this test exists to catch');
	assert.match(details.targetFilename, /^experiments-[a-z0-9-]+-v01\.md$/, details.targetFilename);
	// The claim is not "the label is v01" but "the label matches the file", which is the
	// property that was actually broken: a caller reading the response was told r01 about a
	// file named -v01.md, and no assertion on either half alone catches that.
	assert.equal(details.targetFilename.endsWith(`-${details.targetRevision}.md`), true,
		`reported ${details.targetRevision} for a file named ${details.targetFilename}`);
	assert.equal(details.receiptId, `${details.targetFilename}:${details.targetRevision}`);
	assert.deepEqual(onDisk, [details.targetFilename], 'exactly one managed document, and it is the one reported');
});

// ---------------------------------------------------------------------------
// D2 -- a required source's text actually reaches v1
// ---------------------------------------------------------------------------

test('a flat markdown file sitting directly in a declared source directory reaches the first revision', async () => {
	const { written } = await clean();
	assert.ok(written, 'no document was written');
	assert.ok(written.includes(PROPOSAL_FRAGMENT),
		`the latest proposal is a REQUIRED source precisely so its claims reach the draft, and none of it arrived:\n${written}`);
	assert.ok(written.includes(`${PROPOSALS}/${PROPOSAL_FILENAME}`),
		'the fragment must be attributed to the flat file it came from');
});

test('the nested <folder>/<folder>.md shape still loads beside it', async () => {
	const { written } = await clean();
	// The flat pass is an addition. The mathematical sibling reads its whole guide the nested
	// way, so a fix that traded one shape for the other would be a regression wearing a green
	// suite.
	assert.ok(written.includes(DATA_PAPER_FRAGMENT), `the nested source stopped loading:\n${written}`);
	assert.ok(written.includes(`${DATA_PAPER}/acquisition-sites/acquisition-sites.md`),
		'the nested fragment keeps its full <source>/<folder>/<folder>.md attribution');
});

// ---------------------------------------------------------------------------
// D1 -- the composed v1 is canonical-form checked before it is written
// ---------------------------------------------------------------------------

test('a source fragment carrying a filled report-table cell refuses the first revision instead of publishing it', async () => {
	const { details, onDisk } = await createInitialRevision(PROPOSAL_WITH_FILLED_TABLE);
	assert.equal(details.status, 'blocked', `a fabricated result must never become v1: ${JSON.stringify(details)}`);
	assert.deepEqual(details.blockers?.map((blocker) => blocker.code), ['INITIAL_REVISION_CANONICAL_FORM_VIOLATION'],
		JSON.stringify(details.blockers));
	// The evidence matters as much as the refusal: a caller told only "blocked" cannot repair a
	// source document it was never shown.
	assert.match(details.blockers[0].message, /report-table-fabricated-value/);
	assert.match(details.blockers[0].message, /"0\.71"/);
	assert.equal(details.nextAction, 'repair_canonical_form');
	assert.deepEqual(onDisk, [], 'nothing may be written when the composed candidate is refused');
	assert.equal(details.mutations, 0);
});

// ---------------------------------------------------------------------------
// The two declarations a plan owes -- v1 is checked, not only successors
// ---------------------------------------------------------------------------

test('a proposal declaring neither the dataset nor the validation scheme refuses the first revision instead of publishing it', async () => {
	const { details, onDisk } = await createInitialRevision(`${PROPOSAL_FRAGMENT_WITHOUT_DECLARATIONS}\n`);
	assert.equal(details.status, 'blocked', `a document missing both declarations must never become v1: ${JSON.stringify(details)}`);
	assert.deepEqual(details.blockers?.map((blocker) => blocker.code), ['INITIAL_REVISION_CANONICAL_FORM_VIOLATION'],
		JSON.stringify(details.blockers));
	// Same double evidence discipline as the filled-cell case: both missing declarations
	// must be named, not just the block itself.
	assert.match(details.blockers[0].message, /dataset-declaration-missing/);
	assert.match(details.blockers[0].message, /validation-scheme-declaration-missing/);
	assert.equal(details.nextAction, 'repair_canonical_form');
	assert.deepEqual(onDisk, [], 'nothing may be written when the composed candidate is refused');
	assert.equal(details.mutations, 0);
});

// ---------------------------------------------------------------------------
// D4 -- the revision-label prose is the profile's own
// ---------------------------------------------------------------------------

test('no caller-facing description or refusal message spells a revision label this domain does not use', async () => {
	const { prose, refusals } = await clean();
	assert.equal(/rNN/.test(prose), false, 'a domain whose revision prefix is "v" is never told to choose an -rNN slug');
	assert.ok(prose.includes('vNN'), 'the placeholder must be rendered from the profile, not merely deleted');
	// The description surface alone is not the whole of it: a first pass of this test read only
	// tool descriptions and schemas, and a mutation that put the literal back into two REFUSAL
	// messages survived it green. A refusal is read by exactly the caller that got it wrong.
	const thrown = refusals.filter(Boolean);
	assert.equal(thrown.length, refusals.length, `every probe must actually refuse: ${JSON.stringify(refusals)}`);
	for (const message of thrown) assert.equal(/rNN/.test(message), false, message);
	assert.ok(thrown.some((message) => message.includes('vNN')),
		`no refusal rendered the placeholder at all: ${JSON.stringify(thrown)}`);
});

test('no engine source spells a hardcoded revision-label placeholder outside a comment', async () => {
	// The two surfaces above are the reachable ones. This is the CLASS: `rNN` is a literal that
	// can only ever be right for one domain, and the sites this suite happens to be able to
	// reach are not all of them. Whole-line comments are dropped -- conservatively, so a
	// trailing comment still counts as code -- and what remains is the shipped prose.
	const files = (await readdir(engineDir, { recursive: true, withFileTypes: true }))
		.filter((entry) => entry.isFile() && (entry.name.endsWith('.ts') || entry.name.endsWith('.mjs')))
		.map((entry) => path.join(entry.parentPath ?? entry.path, entry.name));
	assert.ok(files.length > 40, `expected the whole engine, scanned ${files.length}`);
	const leaks = [];
	for (const file of files) {
		const source = await readFile(file, 'utf8');
		source.split('\n').forEach((line, index) => {
			const trimmed = line.trim();
			if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return;
			if (/rNN/.test(line)) leaks.push(`${path.relative(engineDir, file)}:${index + 1}`);
		});
	}
	assert.deepEqual(leaks, [], 'the revision-label placeholder must be rendered from the profile, never spelled');
});
