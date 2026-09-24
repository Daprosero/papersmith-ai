// Finding M6: `domain-profile.ts`'s `REQUIRED` array only ever checked TOP-LEVEL key
// presence (`profile.vocabulary === undefined`), exactly the `artifact: {}` bug this
// file's `-artifact.test.mjs` sibling already covers -- except nobody ever added the
// matching nested check for `vocabulary`. A profile declaring `vocabulary: {}` used to
// start cleanly, publish v1, and only fail later, silently, when an instruction could not
// resolve any locus -- with the caller blamed for a query that was never wrong.
//
// These tests spawn a fresh Node process per profile fixture, for the same reason the
// artifact/objective siblings do: `domain-profile.ts` validates at MODULE IMPORT time
// (top-level await), and Node's ESM loader caches a module per URL for the life of a
// process -- a second `jiti.import()` of the same file in the same process would silently
// reuse the first result instead of re-running the check against a different profile.
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

const BASE_VOCABULARY = {
	conceptualTerms: [],
	expertPattern: 'x',
	displayNounPattern: 'x',
	displayNounStripPattern: 'x',
	subjectPattern: 'x',
	subjectTerms: [],
	subjectLocusDescription: 'x',
	subjectEvidenceLabel: 'x',
};

function profileSource(vocabularyFieldsSource) {
	return `export const profile = {
	deriveBase: "base.md",
	baseLabel: "base",
	baseLabelLong: "base document",
	exampleSlug: "example-slug-r01",
	names: ["TESTDOMAIN"],
	proseReferencePattern: "\\\\(Ec\\\\. ([0-9]+)\\\\)",
${vocabularyFieldsSource}
	artifact: {
		directory: "experiments",
		stem: "experiment-note",
		revisionPattern: "r",
		revisionLabel: (ordinal) => \`r\${String(ordinal).padStart(2, "0")}\`,
		sidecarRoot: ".experiments-deliberation",
		marker: "<!-- experiment-note:artifact:v1 -->\\n",
	},
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

function vocabularyBlockSource(overrides = {}, omit = []) {
	const fields = { ...BASE_VOCABULARY, ...overrides };
	const lines = [];
	for (const key of ['conceptualTerms', 'expertPattern', 'displayNounPattern', 'displayNounStripPattern', 'subjectPattern', 'subjectTerms', 'subjectLocusDescription', 'subjectEvidenceLabel']) {
		if (omit.includes(key)) continue;
		lines.push(`\t\t${key}: ${JSON.stringify(fields[key])},`);
	}
	return `\tvocabulary: {\n${lines.join('\n')}\n\t},`;
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
console.log(JSON.stringify({ expertPattern: module.DOMAIN.vocabulary.expertPattern }));
`;
}

async function runWithProfile(vocabularyFieldsSource) {
	const directory = await mkdtemp(path.join(os.tmpdir(), 'pp-domain-profile-vocabulary-'));
	const profilePath = path.join(directory, 'profile.ts');
	const harnessPath = path.join(directory, 'harness.mjs');
	await writeFile(profilePath, profileSource(vocabularyFieldsSource), 'utf8');
	await writeFile(harnessPath, await harnessScript(), 'utf8');
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, TARGET_MODULE: domainProfilePath };
	try {
		const { stdout } = await execFileAsync('node', [harnessPath], { env });
		return { ok: true, stdout };
	} catch (error) {
		return { ok: false, stderr: String(error.stderr ?? error.message ?? '') };
	}
}

test('a profile omitting vocabulary entirely fails startup naming the missing top-level field', async () => {
	const result = await runWithProfile('');
	assert.equal(result.ok, false, 'expected startup to refuse when vocabulary is omitted');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /\bvocabulary\b/);
});

test('a vocabulary block with every field present but empty object still fails (REQUIRED alone is not enough -- this is the exact bug M6 measured)', async () => {
	const result = await runWithProfile('\tvocabulary: {},');
	assert.equal(result.ok, false, 'REQUIRED only checked top-level `vocabulary` presence; an empty object must still be refused');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /vocabulary\./, 'the refusal must name a NESTED vocabulary field, not just "vocabulary"');
});

for (const key of ['conceptualTerms', 'expertPattern', 'displayNounPattern', 'displayNounStripPattern', 'subjectPattern', 'subjectTerms', 'subjectLocusDescription', 'subjectEvidenceLabel']) {
	test(`a profile omitting vocabulary.${key} fails startup naming the missing nested field`, async () => {
		const result = await runWithProfile(vocabularyBlockSource({}, [key]));
		assert.equal(result.ok, false);
		assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
		assert.match(result.stderr, new RegExp(`vocabulary\\.${key}`));
	});
}

test('a profile declaring all eight vocabulary fields loads successfully', async () => {
	const result = await runWithProfile(vocabularyBlockSource());
	assert.equal(result.ok, true, `expected startup to succeed: ${result.stderr ?? ''}`);
	assert.match(result.stdout, /LOADED_OK/);
});
