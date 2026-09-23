// Phase 3.2 (change 7): a domain layer may depend on read-only reference sources loaded once
// before the first revision renders. `profile.sources: readonly { path, required }[]` replaces
// the single hardcoded `GUIDE_DIRECTORY` path; a missing `required: true` source now refuses
// `CREATE_INITIAL_REVISION` with `REQUIRED_SOURCE_MISSING` instead of silently returning `[]`.
// `proposal-deliberation` declares its guide as NOT required, so an absent
// `guidance/paper-guide` still renders v1 silently -- exactly today's behavior.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const piRoot = path.resolve('.');
const aiRoot = path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(aiRoot, 'index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));

// ---------------------------------------------------------------------------
// 3.2.1 / 3.2.3 -- exercised against the DEFAULT (math) profile the whole test run already
// runs under (`DELIBERATION_DOMAIN_PROFILE` set by package.json's `test` script), which
// declares exactly one source, `guidance/paper-guide`, `required: false`.
// ---------------------------------------------------------------------------

async function defaultProfileFixture() {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-required-sources-'));
	await mkdir(path.join(projectRoot, 'proposals'), { recursive: true });
	const guard = workspace.createDocumentOperationGuard(projectRoot);
	const tools = [];
	workspace.createProposalDeliberationExtension({ projectRoot, operationGuard: guard })({ registerTool: (candidate) => tools.push(candidate), on: () => {} });
	const tool = tools.find((candidate) => candidate.name === 'proposal_deliberation_execute');
	const ctx = { model: { provider: 'anthropic', id: 'unused' }, sessionManager: { getSessionId: () => 'required-sources-session' }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'unused', headers: {}, env: {} }) } };
	return {
		projectRoot,
		execute: async (params) => (await tool.execute('required-sources', params, undefined, undefined, ctx)).details,
		async dispose() { await rm(projectRoot, { recursive: true, force: true }); },
	};
}

test('3.2.1 a declared, present source loads its fragments exactly as today', async () => {
	const run = await defaultProfileFixture();
	try {
		const guideFolder = path.join(run.projectRoot, 'guidance/paper-guide/style');
		await mkdir(guideFolder, { recursive: true });
		await writeFile(path.join(guideFolder, 'style.md'), 'Always define notation before use.', 'utf8');
		const result = await run.execute({ operation: 'CREATE_INITIAL_REVISION', instruction: 'A tutor that catches unjustified inference steps in a proof draft. It names the step it doubts.' });
		assert.equal(result.status, 'created', JSON.stringify(result));
		const written = await readFile(path.join(run.projectRoot, 'proposals', result.targetFilename), 'utf8');
		assert.match(written, /Paper Guide Reference/);
		assert.match(written, /Always define notation before use\./);
	} finally {
		await run.dispose();
	}
});

test('3.2.3 an absent, not-required source (proposal-deliberation\'s guide) preserves today\'s silence', async () => {
	const run = await defaultProfileFixture();
	try {
		// No guidance/ directory at all -- the default profile's one declared source, `required: false`.
		const result = await run.execute({ operation: 'CREATE_INITIAL_REVISION', instruction: 'A tutor that verifies each induction step explicitly. It refuses to advance past one it cannot check.' });
		assert.equal(result.status, 'created', JSON.stringify(result));
		const written = await readFile(path.join(run.projectRoot, 'proposals', result.targetFilename), 'utf8');
		assert.doesNotMatch(written, /Paper Guide Reference/, 'no fragments were injected');
	} finally {
		await run.dispose();
	}
});

// ---------------------------------------------------------------------------
// 3.2.2 / 3.2.4 -- need a profile declaring a `required: true` source, so a FRESH process is
// spawned with a custom profile file, the same technique
// `proposal-deliberation-sidecar-root-routing.test.mjs` uses: `domain-profile.ts` reads
// `DELIBERATION_DOMAIN_PROFILE` once, at module-import time, per process.
// ---------------------------------------------------------------------------

function customProfileSource(sourcesFieldSource) {
	return `import type { DeliberationDomainProfile } from "${path.join(engineDir, 'domain-profile.js')}";
export const profile: DeliberationDomainProfile = {
	deriveBase: "base.md",
	baseLabel: "base",
	baseLabelLong: "base document",
	exampleSlug: "example-slug-r01",
	names: ["TESTDOMAIN"],
	proseReferencePattern: "\\\\(Ec\\\\. ([0-9]+)\\\\)",
	proseReferenceText: (value) => \`(Ec. \${value})\`,
	vocabulary: {
		conceptualTerms: [],
		expertPattern: "x",
		displayNounPattern: "x",
		displayNounStripPattern: "x",
		subjectPattern: "x",
		subjectTerms: [],
		subjectLocusDescription: "x",
		subjectEvidenceLabel: "x",
	},
	artifact: {
		directory: "proposals",
		stem: "research-concept",
		revisionPattern: "r",
		revisionLabel: (ordinal) => \`r\${String(ordinal).padStart(2, "0")}\`,
		sidecarRoot: ".proposal-deliberation",
		marker: "<!-- proposal-workspace:artifact:v1 -->\\n",
	},
	preservation: { extractAtoms: () => new Map(), violations: () => [] },
	references: { declares: () => [], cites: () => [] },
${sourcesFieldSource}
	objective: {
		purpose: "test purpose",
		stages: [{ stage: "bound", establishes: "x", behindWhen: "x" }],
		arrival: "test arrival",
		humanStops: ["a person decides"],
	},
};
`;
}

const HARNESS = `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(process.env.WORKSPACE_MODULE);
const projectRoot = process.env.PROJECT_ROOT;
const guard = workspace.createDocumentOperationGuard(projectRoot);
const tools = [];
workspace.createProposalDeliberationExtension({ projectRoot, operationGuard: guard })({ registerTool: (candidate) => tools.push(candidate), on: () => {} });
const tool = tools.find((candidate) => candidate.name === 'proposal_deliberation_execute');
const ctx = { model: { provider: 'anthropic', id: 'unused' }, sessionManager: { getSessionId: () => 'required-sources-fresh-session' }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'unused', headers: {}, env: {} }) } };
const result = await tool.execute('required-sources-fresh', { operation: 'CREATE_INITIAL_REVISION', instruction: process.env.IDEA }, undefined, undefined, ctx);
console.log(JSON.stringify(result.details));
`;

async function runFreshProfile(sourcesFieldSource, { createGuidance = [], createEmpty = [], createFlat = [] } = {}) {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-required-sources-fresh-'));
	await mkdir(path.join(projectRoot, 'proposals'), { recursive: true });
	for (const relativeDir of createGuidance) {
		await mkdir(path.join(projectRoot, relativeDir), { recursive: true });
		await writeFile(path.join(projectRoot, relativeDir, `${path.basename(relativeDir)}.md`), 'Fragment content.', 'utf8');
	}
	// A directory and nothing else -- exactly what `mkdir <declared path>` alone produces.
	// The presence check cannot tell this apart from a populated source; the content check can.
	for (const relativeDir of createEmpty) {
		await mkdir(path.join(projectRoot, relativeDir), { recursive: true });
	}
	// Flat Markdown sitting DIRECTLY in the source directory -- the other shape the loader
	// walks, and the one a managed revision actually has. Exercised so the content check is
	// proven against both shapes rather than only the nested `<folder>/<folder>.md` one.
	for (const relativeDir of createFlat) {
		await mkdir(path.join(projectRoot, relativeDir), { recursive: true });
		await writeFile(path.join(projectRoot, relativeDir, 'flat-document-r01.md'), 'Flat fragment content.', 'utf8');
	}
	const profilePath = path.join(projectRoot, 'profile.ts');
	const harnessPath = path.join(projectRoot, 'harness.mjs');
	await writeFile(profilePath, customProfileSource(sourcesFieldSource), 'utf8');
	await writeFile(harnessPath, HARNESS, 'utf8');
	const env = {
		...process.env,
		DELIBERATION_DOMAIN_PROFILE: profilePath,
		WORKSPACE_MODULE: path.join(engineDir, 'proposal-workspace.ts'),
		PROJECT_ROOT: projectRoot,
		// Two sentences: `INITIAL_IDEA_SINGLE_SENTENCE` refuses one, and until the content
		// check existed no test in this file ever reached that gate -- every case here
		// blocked earlier, on a required source. The source checks run first, so the cases
		// that assert `blocked` are unaffected by this.
		IDEA: 'A required-sources test idea for CREATE_INITIAL_REVISION. It states what the plan must establish before it runs.',
	};
	const { stdout } = await execFileAsync('node', [harnessPath], { env });
	const result = JSON.parse(stdout.trim().split('\n').pop());
	return { projectRoot, result };
}

test('3.2.2 a missing required: true source refuses CREATE_INITIAL_REVISION with REQUIRED_SOURCE_MISSING; no v1 is created', async () => {
	const { projectRoot, result } = await runFreshProfile('\tsources: [{ path: "required-guide", required: true }],');
	try {
		assert.equal(result.status, 'blocked', JSON.stringify(result));
		assert.ok(result.blockers?.some((b) => b.code === 'REQUIRED_SOURCE_MISSING'), JSON.stringify(result));
		const proposalsEntries = await readdir(path.join(projectRoot, 'proposals'));
		assert.deepEqual(proposalsEntries, [], 'no v1 document must be created when a required source is missing');
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

test('3.2.4 two sources, one required (absent) and one not required (present): CREATE_INITIAL_REVISION fails with REQUIRED_SOURCE_MISSING regardless of the second', async () => {
	const { projectRoot, result } = await runFreshProfile(
		'\tsources: [{ path: "required-guide", required: true }, { path: "optional-guide", required: false }],',
		{ createGuidance: ['optional-guide/fragment'] },
	);
	try {
		assert.equal(result.status, 'blocked', JSON.stringify(result));
		assert.ok(result.blockers?.some((b) => b.code === 'REQUIRED_SOURCE_MISSING'), JSON.stringify(result));
		const proposalsEntries = await readdir(path.join(projectRoot, 'proposals'));
		assert.deepEqual(proposalsEntries, [], 'the present-but-optional source must not rescue a missing required one');
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

// ---------------------------------------------------------------------------
// A required source is required for its CONTENT, not for its name.
//
// The presence check above is an `lstat`: `mkdir <declared path>` satisfied it, and v1 then
// rendered against a source holding nothing. These four tests are the content check, and the
// last two exist so the first two cannot pass by the gate simply always blocking.
// ---------------------------------------------------------------------------

test('a required: true source that exists but holds nothing refuses REQUIRED_SOURCE_EMPTY; no v1 is created', async () => {
	const { projectRoot, result } = await runFreshProfile(
		'\tsources: [{ path: "required-guide", required: true }],',
		{ createEmpty: ['required-guide'] },
	);
	try {
		assert.equal(result.status, 'blocked', JSON.stringify(result));
		assert.ok(result.blockers?.some((b) => b.code === 'REQUIRED_SOURCE_EMPTY'), JSON.stringify(result));
		assert.ok(!result.blockers?.some((b) => b.code === 'REQUIRED_SOURCE_MISSING'),
			'the directory IS present -- reporting it missing would send the reader to create what already exists');
		const empty = result.blockers.find((b) => b.code === 'REQUIRED_SOURCE_EMPTY');
		assert.match(empty.message, /required-guide/, 'the refusal names the source that is unanswered');
		assert.match(empty.message, /<name>\.md|directly inside it/,
			'the refusal names how to answer it, not only that it is unanswered');
		const proposalsEntries = await readdir(path.join(projectRoot, 'proposals'));
		assert.deepEqual(proposalsEntries, [], 'no v1 document must be created when a required source holds nothing');
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

test('an optional source that exists but holds nothing stays legal and stays silent', async () => {
	const { projectRoot, result } = await runFreshProfile(
		'\tsources: [{ path: "required-guide", required: true }, { path: "optional-guide", required: false }],',
		{ createGuidance: ['required-guide/fragment'], createEmpty: ['optional-guide'] },
	);
	try {
		assert.equal(result.status, 'created', JSON.stringify(result));
		assert.ok(!(result.blockers ?? []).some((b) => b.code === 'REQUIRED_SOURCE_EMPTY'),
			'emptiness only blocks where the declaration says required');
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

test('a required source answered by the nested <folder>/<folder>.md shape proceeds', async () => {
	const { projectRoot, result } = await runFreshProfile(
		'\tsources: [{ path: "required-guide", required: true }],',
		{ createGuidance: ['required-guide/fragment'] },
	);
	try {
		assert.equal(result.status, 'created', JSON.stringify(result));
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

test('a required source answered by flat Markdown directly inside it proceeds', async () => {
	const { projectRoot, result } = await runFreshProfile(
		'\tsources: [{ path: "required-guide", required: true }],',
		{ createFlat: ['required-guide'] },
	);
	try {
		assert.equal(result.status, 'created', JSON.stringify(result));
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});
