// Finding L6: two headings the engine wrote unconditionally, undeclared by any profile.
//
//   - `initial-revision-renderer.ts`'s `renderFromIdea` used to hardcode
//     `## Paper Guide Reference` above every loaded read-only source fragment in v1,
//     regardless of domain -- accurate for `proposal-deliberation` (its one source
//     really is a paper guide) and wrong for `experimental-deliberation`, whose
//     declared sources (data paper, latest proposal, area benchmark) are never a paper
//     guide, yet every one of its v1s carried that heading anyway.
//   - `successor-edit-planner.ts`'s `tailBlockContent` used to hardcode
//     `## Accepted scientific decisions` for its claim-provenance document-tail summary
//     block, undeclared by any profile.
//
// Both are now read from `DOMAIN.artifact.sourceReferenceHeading` /
// `.acceptedDecisionsHeading`, optional fields defaulting to the exact prior literals --
// zero migration for a profile that declares neither (both shipped hosts, for the
// second field; `proposal-deliberation`, for the first).
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

function profileSource({ headingsSource = '' }) {
	return `export const profile = {
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
		marker: "<!-- test-doc:artifact:v1 -->\\n",
${headingsSource}
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
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const engineDir = process.env.ENGINE_DIR;
const v2 = await jiti.import(path.join(engineDir, 'exports.ts'));

const composed = new v2.InitialRevisionRenderer().renderFromIdea({
	idea: 'First sentence of the idea. Second sentence of the idea.',
	guideFragments: [{ path: 'guidance/x/x.md', content: 'Fragment body.' }],
});

const base = await v2.rebuildDerivedState('testdoc-sample-r01.md', 'r01', 'sample', Buffer.from('# Intro\\n\\nBody.\\n', 'utf8'));
const expectedRevision = { filename: base.filename, revision: base.revision, documentSha256: base.documentSha256 };
const acceptedDecisions = [
	{ claimId: 'claim-a', decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: 'digest-a', summary: 'A decision summary.' },
];
const plan = new v2.SuccessorEditPlanner().plan({ base, expectedRevision, acceptedDecisions });
const tailContent = plan.patches[0].plan.actions[0].content;

console.log(JSON.stringify({ v1Markdown: composed.markdown, tailContent }));
`;
}

async function run(headingsSource) {
	const directory = await mkdtemp(path.join(os.tmpdir(), 'pp-source-reference-heading-'));
	const profilePath = path.join(directory, 'profile.ts');
	const harnessPath = path.join(directory, 'harness.mjs');
	await writeFile(profilePath, profileSource({ headingsSource }), 'utf8');
	await writeFile(harnessPath, harnessScript(), 'utf8');
	const env = { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir };
	const { stdout } = await execFileAsync('node', [harnessPath], { env });
	return JSON.parse(stdout.trim().split('\n').pop());
}

test('undeclared headings render the exact prior literals (zero migration)', async () => {
	const result = await run('');
	assert.match(result.v1Markdown, /^## Paper Guide Reference$/m, 'default sourceReferenceHeading must be the exact prior literal');
	assert.match(result.tailContent, /^## Accepted scientific decisions$/m, 'default acceptedDecisionsHeading must be the exact prior literal');
});

test('a declared sourceReferenceHeading replaces the hardcoded "Paper Guide Reference" heading in v1', async () => {
	const result = await run('\t\tsourceReferenceHeading: "Reference Sources",');
	assert.match(result.v1Markdown, /^## Reference Sources$/m);
	assert.doesNotMatch(result.v1Markdown, /Paper Guide Reference/);
});

test('a declared acceptedDecisionsHeading replaces the hardcoded "Accepted scientific decisions" heading', async () => {
	const result = await run('\t\tacceptedDecisionsHeading: "Approved Findings",');
	assert.match(result.tailContent, /^## Approved Findings$/m);
	assert.doesNotMatch(result.tailContent, /Accepted scientific decisions/);
});
