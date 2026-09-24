// Phase 1.1 (change 11, "a north a second domain can hold"): the domain profile
// must declare a complete `objective` namespace -- the north's own shape -- and
// `REQUIRED` alone (top-level key presence) is not enough, exactly the bug
// `artifact: {}` already taught this file (see
// `proposal-deliberation-domain-profile-artifact.test.mjs`). These tests spawn a
// fresh Node process per profile fixture for the same reason that file does:
// `domain-profile.ts` validates at MODULE IMPORT time (top-level await), and
// Node's ESM loader caches a module per URL for the life of a process.
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

const BASE_STAGES_SOURCE = `[
		{ stage: "bound", establishes: "which entry is targeted", behindWhen: "the target resolved" },
		{ stage: "closed", establishes: "the work is done", behindWhen: "it was published" },
	]`;

function profileSource(objectiveFieldsSource) {
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
${objectiveFieldsSource}
};
`;
}

function objectiveBlockSource(overrides = {}, omit = []) {
	const fields = {
		purpose: 'test purpose',
		stagesSource: BASE_STAGES_SOURCE,
		arrival: 'test arrival',
		humanStopsSource: '["a person decides"]',
		...overrides,
	};
	const lines = [];
	if (!omit.includes('purpose')) lines.push(`\t\tpurpose: ${JSON.stringify(fields.purpose)},`);
	if (!omit.includes('stages')) lines.push(`\t\tstages: ${fields.stagesSource},`);
	if (!omit.includes('arrival')) lines.push(`\t\tarrival: ${JSON.stringify(fields.arrival)},`);
	if (!omit.includes('humanStops')) lines.push(`\t\thumanStops: ${fields.humanStopsSource},`);
	return `\tobjective: {\n${lines.join('\n')}\n\t},`;
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
console.log(JSON.stringify({ arrival: module.DOMAIN.objective.arrival }));
`;
}

async function runWithProfile(objectiveFieldsSource) {
	const directory = await mkdtemp(path.join(os.tmpdir(), 'pp-domain-profile-objective-'));
	const profilePath = path.join(directory, 'profile.ts');
	const harnessPath = path.join(directory, 'harness.mjs');
	await writeFile(profilePath, profileSource(objectiveFieldsSource), 'utf8');
	await writeFile(harnessPath, await harnessScript(), 'utf8');
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, TARGET_MODULE: domainProfilePath };
	try {
		const { stdout } = await execFileAsync('node', [harnessPath], { env });
		return { ok: true, stdout };
	} catch (error) {
		return { ok: false, stderr: String(error.stderr ?? error.message ?? '') };
	}
}

test('a profile omitting objective entirely fails startup naming the missing top-level field', async () => {
	const result = await runWithProfile('');
	assert.equal(result.ok, false, 'expected startup to refuse when objective is omitted');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /\bobjective\b/, 'the refusal must name the missing top-level field');
});

test('an objective block with every field present but empty object still fails (REQUIRED alone is not enough)', async () => {
	const result = await runWithProfile('\tobjective: {},');
	assert.equal(result.ok, false, 'REQUIRED only checks top-level `objective` presence; an empty object must still be refused');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\./);
});

test('a profile omitting objective.arrival fails startup naming the missing nested field', async () => {
	const result = await runWithProfile(objectiveBlockSource({}, ['arrival']));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.arrival/);
});

test('a profile omitting objective.purpose fails startup naming the missing nested field', async () => {
	const result = await runWithProfile(objectiveBlockSource({}, ['purpose']));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.purpose/);
});

test('a profile omitting objective.humanStops fails startup naming the missing nested field', async () => {
	const result = await runWithProfile(objectiveBlockSource({}, ['humanStops']));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.humanStops/);
});

test('objective.stages present but empty still fails (a weaker top-level-only check would miss this)', async () => {
	const result = await runWithProfile(objectiveBlockSource({ stagesSource: '[]' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.stages/);
});

test('a stage missing behindWhen fails, naming objective.stages', async () => {
	const result = await runWithProfile(objectiveBlockSource({ stagesSource: '[{ stage: "bound", establishes: "x" }]' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.stages/);
});

// Finding M6: this exact guard used to test `=== undefined` only, which is the shape
// the guard's own comment says it exists to prevent ("a stage this domain declares by
// name would silently establish nothing and close on no condition at all") and NOT the
// harm: `""` is not `undefined`, so it passed. Measured, then fixed to reject an empty
// string the same way an omitted field is rejected.
test('a stage with establishes: "" fails, naming objective.stages (an empty string is not `undefined` and used to slip through)', async () => {
	const result = await runWithProfile(objectiveBlockSource({ stagesSource: '[{ stage: "bound", establishes: "", behindWhen: "x" }]' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.stages/);
});

test('a stage with behindWhen: "" fails, naming objective.stages', async () => {
	const result = await runWithProfile(objectiveBlockSource({ stagesSource: '[{ stage: "bound", establishes: "x", behindWhen: "" }]' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.stages/);
});

test('objective.humanStops: [] fails startup -- asserting that NOTHING is a person\'s decision is not a north', async () => {
	const result = await runWithProfile(objectiveBlockSource({ humanStopsSource: '[]' }));
	assert.equal(result.ok, false, 'humanStops presence alone (OBJECTIVE_REQUIRED) does not rule out an empty array');
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.humanStops/);
});

test('objective.arrival: "" fails startup -- an empty string is not `undefined` and used to slip through', async () => {
	const result = await runWithProfile(objectiveBlockSource({ arrival: '' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.arrival/);
});

test('objective.purpose: "" fails startup', async () => {
	const result = await runWithProfile(objectiveBlockSource({ purpose: '' }));
	assert.equal(result.ok, false);
	assert.match(result.stderr, /DELIBERATION_DOMAIN_PROFILE_INCOMPLETE/);
	assert.match(result.stderr, /objective\.purpose/);
});

test('a complete objective block loads successfully', async () => {
	const result = await runWithProfile(objectiveBlockSource());
	assert.equal(result.ok, true, `expected startup to succeed: ${result.stderr ?? ''}`);
	assert.match(result.stdout, /LOADED_OK/);
	assert.match(result.stdout, /"arrival":"test arrival"/);
});
