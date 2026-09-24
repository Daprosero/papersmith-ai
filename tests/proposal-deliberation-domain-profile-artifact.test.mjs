// Phase 1.1 (change 1): the domain profile must declare a complete `artifact`
// namespace, and `REQUIRED` alone (top-level key presence) is not enough --
// `domain-profile.ts` only ever did `REQUIRED.filter(key => profile[key] ===
// undefined)`, so `artifact: {}` would have passed vacuously. These tests spawn
// a fresh Node process per profile fixture, because `domain-profile.ts` runs its
// validation at MODULE IMPORT time (top-level await) and Node's ESM loader
// caches a module per URL for the life of a process -- a second `jiti.import()`
// of the same file in the same process would silently reuse the first result
// instead of re-running the check against a different profile.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const domainProfilePath = path.join(engineDir, 'domain-profile.ts');
const piRoot = path.resolve('.');

const BASE_ARTIFACT = {
	directory: 'experiments',
	stem: 'experiment-note',
	revisionPattern: 'r',
	revisionLabelSource: '(ordinal) => `r${String(ordinal).padStart(2, "0")}`',
	sidecarRoot: '.experiments-deliberation',
	marker: '<!-- experiment-note:artifact:v1 -->\\n',
};

function profileSource(artifactFieldsSource) {
	return `export const profile = {
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
${artifactFieldsSource}
	preservation: { extractAtoms: () => new Map(), violations: () => [] },
	references: { declares: () => [], cites: () => [] },
	sources: [{ path: "guidance", required: false }],
	objective: {
		purpose: "test purpose",
		stages: [{ stage: "bound", establishes: "x", behindWhen: "x" }],
		arrival: "test arrival",
		humanStops: ["a person decides"],
	},
};
`;
}

function artifactBlockSource(overrides = {}, omit = []) {
	const fields = { ...BASE_ARTIFACT, ...overrides };
	const lines = [];
	for (const key of ['directory', 'stem', 'revisionPattern', 'sidecarRoot', 'marker']) {
		if (omit.includes(key)) continue;
		lines.push(`\t\t${key}: ${JSON.stringify(fields[key])},`);
	}
	if (!omit.includes('revisionLabel')) lines.push(`\t\trevisionLabel: ${fields.revisionLabelSource},`);
	return `\tartifact: {\n${lines.join('\n')}\n\t},`;
}

async function harnessScript() {
	return `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const module = await jiti.import(process.env.TARGET_MODULE);
console.log('LOADED_OK');
console.log(JSON.stringify(module.DOMAIN.artifact.directory ? { directory: module.DOMAIN.artifact.directory } : {}));
`;
}

async function runWithProfile(artifactFieldsSource) {
	const directory = await mkdtemp(path.join(os.tmpdir(), 'pp-domain-profile-artifact-'));
	const profilePath = path.join(directory, 'profile.ts');
	const harnessPath = path.join(directory, 'harness.mjs');
	await writeFile(profilePath, profileSource(artifactFieldsSource), 'utf8');
	await writeFile(harnessPath, await harnessScript(), 'utf8');
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, TARGET_MODULE: domainProfilePath };
	try {
		const { stdout } = await execFileAsync('node', [harnessPath], { env });
		return { ok: true, stdout };
	} catch (error) {
		return { ok: false, stderr: String(error.stderr ?? error.message ?? '') };
	}
}

test('a profile omitting artifact.marker fails startup naming the missing nested field', async () => {
	const result = await runWithProfile(artifactBlockSource({}, ['marker']));
	assert.equal(result.ok, false, 'expected startup to refuse when artifact.marker is omitted');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /artifact\.marker/, 'the refusal must name the missing NESTED field, not just "artifact"');
});

test('a profile omitting artifact.stem fails startup naming the missing nested field', async () => {
	const result = await runWithProfile(artifactBlockSource({}, ['stem']));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /artifact\.stem/);
});

test('an artifact block with every field present but empty object still fails (REQUIRED alone is not enough)', async () => {
	const result = await runWithProfile('\tartifact: {},');
	assert.equal(result.ok, false, 'REQUIRED only checks top-level `artifact` presence; an empty object must still be refused');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /artifact\./);
});

test('artifact.directory containing a slash refuses with DELIBERATION_DOMAIN_PROFILE_UNSAFE_ARTIFACT_PATH', async () => {
	const result = await runWithProfile(artifactBlockSource({ directory: 'a/b' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_UNSAFE_ARTIFACT_PATH/);
});

test('artifact.sidecarRoot containing ".." refuses with DELIBERATION_DOMAIN_PROFILE_UNSAFE_ARTIFACT_PATH', async () => {
	const result = await runWithProfile(artifactBlockSource({ sidecarRoot: '../escape' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_UNSAFE_ARTIFACT_PATH/);
});

test('artifact.directory failing the safe-segment shape refuses with DELIBERATION_DOMAIN_PROFILE_UNSAFE_ARTIFACT_PATH', async () => {
	const result = await runWithProfile(artifactBlockSource({ directory: 'has spaces' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_UNSAFE_ARTIFACT_PATH/);
});

test('a profile declaring all six artifact fields loads successfully', async () => {
	const result = await runWithProfile(artifactBlockSource());
	assert.equal(result.ok, true, `expected startup to succeed: ${result.stderr ?? ''}`);
	assert.match(result.stdout, /LOADED_OK/);
});

test('a dot-prefixed sidecarRoot (the real proposal-deliberation shape) is accepted', async () => {
	const result = await runWithProfile(artifactBlockSource({ sidecarRoot: '.experiments-deliberation' }));
	assert.equal(result.ok, true, `expected the dot-prefixed sidecarRoot to be accepted: ${result.stderr ?? ''}`);
});
