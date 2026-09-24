// Finding L5: `proseReferenceText` used to be mandatory at the ENGINE level
// (`domain-profile.ts`'s `REQUIRED`) even though no file under `_core/` ever reads it.
// Its one reader anywhere was `proposal-deliberation/preservation-math.ts`, for the
// "ref" atom kind its own preservation gate extracts; `experimental-deliberation` had
// to declare a renderer it never invoked (`preservation-experimental.ts` documents, on
// purpose, that it reads no `DOMAIN` field at all, and has no "ref" atom kind).
//
// Fixed: the field is now optional in `DeliberationDomainProfile`, and
// `preservation-math.ts` -- the one host file that actually needs it -- enforces its
// own requirement locally, lazily, at the one call site that uses it, instead of the
// shared core forcing every domain to supply a renderer most of them will never call.
//
// Spawns a fresh Node process per profile fixture, for the same module-caching reason
// every other domain-profile test here does.
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
const piRoot = path.resolve('.');

function profileSource({ includeProseReferenceText }) {
	return `export const profile = {
	deriveBase: "base.md",
	baseLabel: "base",
	baseLabelLong: "base document",
	exampleSlug: "example-slug-r01",
	names: ["TESTDOMAIN"],
	proseReferencePattern: "\\\\(Ec\\\\. ([0-9]+)\\\\)",
${includeProseReferenceText ? '\tproseReferenceText: (value) => `(Ec. ${value})`,\n' : ''}\tvocabulary: {
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
		stem: "testdoc",
		revisionPattern: "r",
		revisionLabel: (ordinal) => \`r\${String(ordinal).padStart(2, "0")}\`,
		sidecarRoot: ".test-deliberation",
		marker: "<!-- test-doc:artifact:v1 -->\\n",
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

function harnessScript() {
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
console.log(JSON.stringify({ hasProseReferenceText: typeof module.DOMAIN.proseReferenceText === 'function' }));
`;
}

async function runWithProfile(includeProseReferenceText) {
	const directory = await mkdtemp(path.join(os.tmpdir(), 'pp-prose-reference-text-'));
	const profilePath = path.join(directory, 'profile.ts');
	const harnessPath = path.join(directory, 'harness.mjs');
	await writeFile(profilePath, profileSource({ includeProseReferenceText }), 'utf8');
	await writeFile(harnessPath, harnessScript(), 'utf8');
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, TARGET_MODULE: path.join(engineDir, 'domain-profile.ts') };
	try {
		const { stdout } = await execFileAsync('node', [harnessPath], { env });
		return { ok: true, stdout };
	} catch (error) {
		return { ok: false, stderr: String(error.stderr ?? error.message ?? '') };
	}
}

test('a profile omitting proseReferenceText loads successfully -- the engine no longer requires it', async () => {
	const result = await runWithProfile(false);
	assert.equal(result.ok, true, `expected startup to succeed without proseReferenceText: ${result.stderr ?? ''}`);
	assert.match(result.stdout, /LOADED_OK/);
	assert.match(result.stdout, /"hasProseReferenceText":false/);
});

test('a profile declaring proseReferenceText still loads it correctly (no regression for the host that needs it)', async () => {
	const result = await runWithProfile(true);
	assert.equal(result.ok, true, `expected startup to succeed: ${result.stderr ?? ''}`);
	assert.match(result.stdout, /"hasProseReferenceText":true/);
});

// `preservation-math.ts` is the one host file with a real call site. It enforces its OWN
// requirement now that the engine no longer does: calling `extractAtoms` on a document
// carrying a "(Ec. N)" citation, under a profile that omits `proseReferenceText`, must
// fail with a clear, dedicated refusal -- never the raw "DOMAIN.proseReferenceText is not
// a function" a bare optional-field read would produce.
async function extractAtomsUnderProfile(includeProseReferenceText) {
	const directory = await mkdtemp(path.join(os.tmpdir(), 'pp-prose-reference-text-guard-'));
	const profilePath = path.join(directory, 'profile.ts');
	const harnessPath = path.join(directory, 'harness.mjs');
	await writeFile(profilePath, profileSource({ includeProseReferenceText }), 'utf8');
	await writeFile(harnessPath, `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const { extractAtoms } = await jiti.import(path.join(process.env.ENGINE_DIR, '../../../proposal-deliberation/preservation-math.ts'));
try {
	extractAtoms('The result follows (Ec. 3) directly.');
	console.log(JSON.stringify({ threw: false }));
} catch (error) {
	console.log(JSON.stringify({ threw: true, message: error.message }));
}
`, 'utf8');
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir };
	const { stdout } = await execFileAsync('node', [harnessPath], { env });
	return JSON.parse(stdout.trim().split('\n').pop());
}

test('preservation-math.ts extractAtoms refuses clearly when its own profile omits proseReferenceText', async () => {
	const result = await extractAtomsUnderProfile(false);
	assert.equal(result.threw, true, 'a citation atom cannot render its display text without a renderer');
	assert.match(result.message, /PROSE_REFERENCE_TEXT_REQUIRED/, 'must be the dedicated guard, not a raw "is not a function" TypeError');
});

test('preservation-math.ts extractAtoms renders the citation atom correctly when proseReferenceText is declared', async () => {
	const result = await extractAtomsUnderProfile(true);
	assert.equal(result.threw, false, JSON.stringify(result));
});
