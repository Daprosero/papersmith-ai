// Finding M6: three more shapes `domain-profile.ts`'s `REQUIRED` (top-level key
// presence) let straight through, each measured as a real process before this fix:
//
//   - `sources: []` -- publishes v1, and every `required: true` source check
//     (`proposal-workspace.ts`'s `missingRequiredSources`) is silently gone, because
//     there is nothing to iterate. Indistinguishable from a domain whose sources were
//     never wired at all, so it is refused rather than trusted: both shipped hosts
//     declare at least one real source.
//   - `preservation: {}` -- publishes v1, then dies at first use of the preservation
//     gate with a raw "... is not a function" instead of a clear refusal.
//   - `references: {}` -- same shape, for reference integrity.
//
// These tests spawn a fresh Node process per profile fixture, for the same reason the
// artifact/objective/vocabulary siblings do: `domain-profile.ts` validates at MODULE
// IMPORT time (top-level await), and Node's ESM loader caches a module per URL for the
// life of a process.
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

const VOCABULARY = `\tvocabulary: {
		conceptualTerms: [],
		expertPattern: "x",
		displayNounPattern: "x",
		displayNounStripPattern: "x",
		subjectPattern: "x",
		subjectTerms: [],
		subjectLocusDescription: "x",
		subjectEvidenceLabel: "x",
	},`;
const ARTIFACT = `\tartifact: {
		directory: "experiments",
		stem: "experiment-note",
		revisionPattern: "r",
		revisionLabel: (ordinal) => \`r\${String(ordinal).padStart(2, "0")}\`,
		sidecarRoot: ".experiments-deliberation",
		marker: "<!-- experiment-note:artifact:v1 -->\\n",
	},`;
const OBJECTIVE = `\tobjective: {
		purpose: "test purpose",
		stages: [{ stage: "bound", establishes: "x", behindWhen: "x" }],
		arrival: "test arrival",
		humanStops: ["a person decides"],
	},`;

function profileSource({ preservationSource, referencesSource, sourcesSource }) {
	return `export const profile = {
	deriveBase: "base.md",
	baseLabel: "base",
	baseLabelLong: "base document",
	exampleSlug: "example-slug-r01",
	names: ["TESTDOMAIN"],
	proseReferencePattern: "\\\\(Ec\\\\. ([0-9]+)\\\\)",
${VOCABULARY}
${ARTIFACT}
	preservation: ${preservationSource},
	references: ${referencesSource},
	sources: ${sourcesSource},
${OBJECTIVE}
};
`;
}

const VALID_PRESERVATION = '{ extractAtoms: () => new Map(), violations: () => [] }';
const VALID_REFERENCES = '{ declares: () => [], cites: () => [] }';
const VALID_SOURCES = '[{ path: "guidance", required: false }]';

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
console.log(JSON.stringify({ sources: module.DOMAIN.sources }));
`;
}

async function runWithProfile(overrides) {
	const directory = await mkdtemp(path.join(os.tmpdir(), 'pp-domain-profile-sources-methods-'));
	const profilePath = path.join(directory, 'profile.ts');
	const harnessPath = path.join(directory, 'harness.mjs');
	const fields = { preservationSource: VALID_PRESERVATION, referencesSource: VALID_REFERENCES, sourcesSource: VALID_SOURCES, ...overrides };
	await writeFile(profilePath, profileSource(fields), 'utf8');
	await writeFile(harnessPath, await harnessScript(), 'utf8');
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, TARGET_MODULE: domainProfilePath };
	try {
		const { stdout } = await execFileAsync('node', [harnessPath], { env });
		return { ok: true, stdout };
	} catch (error) {
		return { ok: false, stderr: String(error.stderr ?? error.message ?? '') };
	}
}

test('a fully valid profile (sources/preservation/references all well-formed) loads successfully', async () => {
	const result = await runWithProfile({});
	assert.equal(result.ok, true, `expected startup to succeed: ${result.stderr ?? ''}`);
	assert.match(result.stdout, /LOADED_OK/);
});

test('sources: [] fails startup -- REQUIRED only checks top-level presence, not that any source was declared', async () => {
	const result = await runWithProfile({ sourcesSource: '[]' });
	assert.equal(result.ok, false, 'an empty sources list must be refused: every required-source check would silently never run');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /sources/);
});

test('a sources entry missing "required" fails startup', async () => {
	const result = await runWithProfile({ sourcesSource: '[{ path: "guidance" }]' });
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /sources/);
});

test('a sources entry with an empty path fails startup', async () => {
	const result = await runWithProfile({ sourcesSource: '[{ path: "", required: false }]' });
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /sources/);
});

test('preservation: {} fails startup (REQUIRED alone is not enough -- this is the exact bug M6 measured for preservation)', async () => {
	const result = await runWithProfile({ preservationSource: '{}' });
	assert.equal(result.ok, false, 'an empty preservation object must be refused instead of dying later at "... is not a function"');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /preservation\.(extractAtoms|violations)/);
});

test('preservation missing only "violations" (extractAtoms present) fails startup naming the missing method', async () => {
	const result = await runWithProfile({ preservationSource: '{ extractAtoms: () => new Map() }' });
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /preservation\.violations/);
});

test('references: {} fails startup (REQUIRED alone is not enough -- this is the exact bug M6 measured for references)', async () => {
	const result = await runWithProfile({ referencesSource: '{}' });
	assert.equal(result.ok, false, 'an empty references object must be refused instead of dying later at "... is not a function"');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /references\.(declares|cites)/);
});

test('references missing only "cites" (declares present) fails startup naming the missing method', async () => {
	const result = await runWithProfile({ referencesSource: '{ declares: () => [] }' });
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /references\.cites/);
});
