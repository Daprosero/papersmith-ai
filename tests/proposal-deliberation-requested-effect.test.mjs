// Phase 4.3 (change 10): `intent-resolver.ts` must not contain the `'sparse'`/`'dispers'`
// string literal as an unconditional core-level term. The equivalent inference is opt-in via
// `profile.vocabulary.requestedEffect`; `proposal-deliberation` opts in with the exact same
// terms/label (see profile.ts), so this is a scope decision documented there, not a silent drop.
//
// Named separately from `proposal-deliberation-domain-vocabulary.test.mjs` (an unrelated,
// pre-existing suite pinning `DOMAIN.vocabulary.subjectTerms`/`expertPattern`/display-noun
// reading) so as not to collide with it.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const piRoot = path.resolve('.');

test('4.3.1 intent-resolver.ts contains neither the sparse nor the dispers string literal as a core-level unconditional term', async () => {
	const source = await readFile(path.join(engineDir, 'intent-resolver.ts'), 'utf8');
	// The literal forms this change removes: a bare quoted 'sparse'/'dispers' argument to the
	// core has(...) matcher, unconditional on any profile field. `DOMAIN.vocabulary.requestedEffect`
	// itself is fine to name (it is the opt-in mechanism, not the literal); what must be gone is
	// the core spelling the two words itself.
	assert.ok(!/['"]sparse['"]/.test(source), 'intent-resolver.ts must not spell the literal "sparse" itself');
	assert.ok(!/['"]dispers['"]/.test(source), 'intent-resolver.ts must not spell the literal "dispers" itself');
});

test('4.3.2 the mathematical profile keeps identical requestedEffect resolution for matching content, having opted in', async () => {
	const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
	const jiti = createJiti(import.meta.url, { alias: {
		'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
		'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
		typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
	} });
	const v2 = await jiti.import(path.resolve(engineDir, 'exports.ts'));
	// Exercised under the normal npm test env (the math profile), which now opts in via
	// `profile.ts`'s `vocabulary.requestedEffect`. Pre-change behavior: any instruction containing
	// "sparse" or "dispers" (plain substring, matching `has(...)`'s own style) resolved
	// `requestedEffect: 'representación sparse'`.
	const sparse = v2.resolveIntent('Cambia la ecuación por una representación sparse.');
	const dispersa = v2.resolveIntent('Cambia la ecuación por una representación dispersa.');
	const neither = v2.resolveIntent('Cambia la ecuación por otra forma cualquiera.');
	assert.equal(sparse.requestedEffect, 'representación sparse');
	assert.equal(dispersa.requestedEffect, 'representación sparse');
	assert.equal(neither.requestedEffect, undefined);
});

test('4.3.4 a profile opting out entirely (no vocabulary.requestedEffect declared) simply never sets requestedEffect via this mechanism', async () => {
	const projectRoot = await (await import('node:fs/promises')).mkdtemp(path.join((await import('node:os')).default.tmpdir(), 'pp-requested-effect-'));
	const profilePath = path.join(projectRoot, 'profile.ts');
	const harnessPath = path.join(projectRoot, 'harness.mjs');
	const customProfile = `import type { DeliberationDomainProfile } from "${path.join(engineDir, 'domain-profile.js')}";
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
		sidecarRoot: ".other-deliberation",
		marker: "<!-- proposal-workspace:artifact:v1 -->\\n",
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
	const harness = `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(process.env.EXPORTS_MODULE);
const resolved = v2.resolveIntent('Cambia la ecuación por una representación sparse.');
console.log(JSON.stringify({ requestedEffect: resolved.requestedEffect }));
`;
	await (await import('node:fs/promises')).writeFile(profilePath, customProfile, 'utf8');
	await (await import('node:fs/promises')).writeFile(harnessPath, harness, 'utf8');
	const { execFile } = await import('node:child_process');
	const { promisify } = await import('node:util');
	const execFileAsync = promisify(execFile);
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, EXPORTS_MODULE: path.join(engineDir, 'exports.ts') };
	const { stdout } = await execFileAsync('node', [harnessPath], { env });
	const result = JSON.parse(stdout.trim().split('\n').pop());
	assert.equal(result.requestedEffect, undefined, 'requestedEffect is simply absent when the profile declares no vocabulary.requestedEffect -- acceptable, nothing downstream reads it except the conceptual plan scientificGoal fallback');
});
