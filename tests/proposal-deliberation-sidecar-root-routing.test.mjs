// Phase 1.4 (change 3): the managed directory and the three sidecar kinds
// (state, receipts, withdrawn) must route through `profile.artifact.directory`
// / `profile.artifact.sidecarRoot`, never the literal `proposals/` and
// `.proposal-deliberation/`. This spawns a FRESH process with a profile
// declaring a DIFFERENT sidecarRoot (`.other-deliberation`) -- the same
// reason `proposal-deliberation-domain-profile-artifact.test.mjs` spawns
// fresh processes: `domain-profile.ts` reads `DELIBERATION_DOMAIN_PROFILE` at
// module-import time, once per process.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, readdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const piRoot = path.resolve('.');

const CUSTOM_PROFILE = `import type { DeliberationDomainProfile } from "${path.join(engineDir, 'domain-profile.js')}";
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

const HARNESS = `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const initialRevision = await jiti.import(process.env.INITIAL_REVISION_MODULE);
const service = new initialRevision.InitialRevisionCreationService(
	{ hasManagedProposal: async () => false },
	initialRevision.createFilesystemInitialRevisionPublicationPort(process.env.PROJECT_ROOT),
);
const result = await service.execute({ idea: 'A test idea for sidecar routing. It exists so the sidecar has somewhere to land.' });
console.log(JSON.stringify(result));
`;

test('a profile declaring sidecarRoot: ".other-deliberation" writes state/receipts sidecars there, never under .proposal-deliberation/', async () => {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-sidecar-routing-'));
	const profilePath = path.join(projectRoot, 'profile.ts');
	const harnessPath = path.join(projectRoot, 'harness.mjs');
	await writeFile(profilePath, CUSTOM_PROFILE, 'utf8');
	await writeFile(harnessPath, HARNESS, 'utf8');
	const env = {
		...process.env,
		DELIBERATION_DOMAIN_PROFILE: profilePath,
		INITIAL_REVISION_MODULE: path.join(engineDir, 'initial-revision-creation.ts'),
		PROJECT_ROOT: projectRoot,
	};
	const { stdout } = await execFileAsync('node', [harnessPath], { env });
	const result = JSON.parse(stdout.trim().split('\n').pop());
	assert.equal(result.status, 'created', `expected creation to succeed: ${JSON.stringify(result)}`);

	let otherEntries;
	try {
		otherEntries = await readdir(path.join(projectRoot, '.other-deliberation'), { recursive: true });
	} catch (error) {
		assert.fail(`expected .other-deliberation/ to exist: ${error.message}`);
	}
	assert.ok(otherEntries.some((entry) => entry.includes('state')), 'expected a state/ sidecar under .other-deliberation/');
	assert.ok(otherEntries.some((entry) => entry.includes('receipts')), 'expected a receipts/ sidecar under .other-deliberation/');

	await assert.rejects(
		() => readdir(path.join(projectRoot, '.proposal-deliberation')),
		/ENOENT/,
		'.proposal-deliberation/ must never be created when the profile declares a different sidecarRoot',
	);
});

const WITHDRAWAL_HARNESS = `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const revisionLifecycleStore = await jiti.import(process.env.REVISION_LIFECYCLE_STORE_MODULE);
console.log(JSON.stringify({
	withdrawalRoot: revisionLifecycleStore.withdrawalRootPath(process.env.PROJECT_ROOT),
	markerPath: revisionLifecycleStore.withdrawalMarkerPath(process.env.PROJECT_ROOT, '11111111-1111-4111-8111-111111111111'),
}));
`;

test('withdrawal sidecar paths route through the profile-declared sidecarRoot too', async () => {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-sidecar-withdrawal-routing-'));
	const profilePath = path.join(projectRoot, 'profile.ts');
	const harnessPath = path.join(projectRoot, 'withdrawal-harness.mjs');
	await writeFile(profilePath, CUSTOM_PROFILE, 'utf8');
	await writeFile(harnessPath, WITHDRAWAL_HARNESS, 'utf8');
	const env = {
		...process.env,
		DELIBERATION_DOMAIN_PROFILE: profilePath,
		REVISION_LIFECYCLE_STORE_MODULE: path.join(engineDir, 'revision-lifecycle-store.ts'),
		PROJECT_ROOT: projectRoot,
	};
	const { stdout } = await execFileAsync('node', [harnessPath], { env });
	const result = JSON.parse(stdout.trim().split('\n').pop());
	assert.equal(result.withdrawalRoot, path.join(projectRoot, '.other-deliberation', 'withdrawn'));
	assert.equal(result.markerPath, path.join(projectRoot, '.other-deliberation', 'withdrawn', '11111111-1111-4111-8111-111111111111', 'audit-marker.json'));
	assert.ok(!result.withdrawalRoot.includes('.proposal-deliberation'), 'the withdrawal root must never carry the literal .proposal-deliberation sidecar name');
});
