// Finding M7: `patch-compiler.ts` used to declare its own hardcoded
// `Buffer.from('<!-- proposal-workspace:artifact:v1 -->\n')` instead of reading
// `DOMAIN.artifact.marker` (via `artifact-naming.ts`, like every other core site except
// `revision-lifecycle-store.ts`, kept hardcoded on purpose for a Python cross-language
// guard). Nothing bites either shipped host, because both declare byte-identical
// markers -- this only bites a domain whose marker differs from the literal, which is
// exactly why it is "born broken in silence" rather than caught by either host's own
// test suite.
//
// `compileSuccessorSectionReplacement` (private; reached only through `compilePatches`
// with `successorCompositeTarget: true`) treats a section's own leading marker specially
// (`protectedMarker`): when the byte-range immediately before the replaced entry is
// EXACTLY the artifact marker, it is preserved untouched and no extra blank-line joiner
// is spliced between it and the replacement. With the marker hardcoded to the DEFAULT
// literal, a domain whose profile declares a DIFFERENT marker never satisfies
// `prefix.equals(ARTIFACT_MARKER)`, so the marker's own trailing newline gets trimmed
// like ordinary prose and a spurious extra blank line appears between the marker and
// the first replaced section -- a real, observable byte difference, not a cosmetic one.
//
// This test spawns a fresh Node process with a custom-marker profile (module caching
// per `DELIBERATION_DOMAIN_PROFILE`, same reason every other domain-profile test here
// spawns fresh processes) and drives `compilePatches` directly against a hand-built
// composite target -- the same low-level entry point
// `proposal-deliberation-v2-source-routing.test.mjs`'s `compileSuccessorRange` helper
// uses, and the ONLY way this branch is reached at all: the real orchestrator always
// routes a `successorCompositeTarget` plan through `compileSuccessorCompositeReplacement`
// instead (see `orchestrator.ts`'s `publish`), never through `compilePatches`'s own
// successor branch.
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

const CUSTOM_MARKER = '<!-- test-marker:artifact:v9 -->\n';

const PROFILE_SOURCE = `export const profile = {
	deriveBase: "base.md",
	baseLabel: "base",
	baseLabelLong: "base document",
	exampleSlug: "example-slug-r01",
	names: ["TESTDOMAIN"],
	proseReferencePattern: "\\\\(Ec\\\\. ([0-9]+)\\\\)",
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
		stem: "testdoc",
		revisionPattern: "r",
		revisionLabel: (ordinal) => \`r\${String(ordinal).padStart(2, "0")}\`,
		sidecarRoot: ".test-deliberation",
		marker: ${JSON.stringify(CUSTOM_MARKER)},
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

function harnessScript() {
	return `import path from 'node:path';
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
const { DOMAIN } = await jiti.import(path.join(engineDir, 'domain-profile.ts'));
const v2 = await jiti.import(path.join(engineDir, 'exports.ts'));

const marker = DOMAIN.artifact.marker;
const source = \`\${marker}# 1 Section\\n\\nOld body.\\n\\n# 2 Tail\\n\\nKeep.\\n\`;
const state = await v2.rebuildDerivedState('testdoc-sample-r01.md', 'r01', 'sample', Buffer.from(source, 'utf8'));
const resolution = v2.resolveSectionRange(state, '1–1');
if (!resolution.candidate) throw new Error('RESOLUTION_FAILED: ' + JSON.stringify(resolution));
v2.materializeCompositeTarget(state, resolution.candidate);
const replacementText = '# 1 Revised\\n\\nNew body.\\n\\n';
const plan = {
	planVersion: '2', documentSha256: state.documentSha256, intent: 'CONCEPTUAL_REVISION', instructionHash: 'marker-test',
	resolvedTargets: [resolution.candidate.entryId], semanticChange: true, destructiveIntent: false, cleanupLevel: 'NONE', constraints: [], expectedEffects: [], unresolvedQuestions: [], successorCompositeTarget: true,
	actions: [{ kind: 'replace', targetEntryId: resolution.candidate.entryId, replacementText }],
};
const compiled = v2.compilePatches(state, plan);
console.log(JSON.stringify({ candidate: compiled.candidate, marker }));
`;
}

async function compile() {
	const directory = await mkdtemp(path.join(os.tmpdir(), 'pp-patch-compiler-marker-'));
	const profilePath = path.join(directory, 'profile.ts');
	const harnessPath = path.join(directory, 'harness.mjs');
	await writeFile(profilePath, PROFILE_SOURCE, 'utf8');
	await writeFile(harnessPath, harnessScript(), 'utf8');
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir };
	const { stdout } = await execFileAsync('node', [harnessPath], { env });
	return JSON.parse(stdout.trim().split('\n').pop());
}

test('compileSuccessorSectionReplacement preserves a custom artifact marker exactly, with no spurious blank line, when the replaced section sits immediately after it', async () => {
	const result = await compile();
	const expected = `${CUSTOM_MARKER}# 1 Revised\n\nNew body.\n\n# 2 Tail\n\nKeep.\n`;
	assert.equal(result.marker, CUSTOM_MARKER);
	assert.equal(result.candidate, expected,
		'the marker must be recognized as `protectedMarker` and preserved with its own single trailing newline -- a hardcoded default-marker comparison would insert a spurious extra blank line here instead');
});
