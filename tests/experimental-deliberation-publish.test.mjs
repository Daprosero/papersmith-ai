// Can the `experimental-deliberation` skill actually PUBLISH?
//
// Everything upstream of publication was already covered: the profile satisfies the
// core contract, the preservation gate extracts and rules on this domain's atoms, the
// reference vocabulary declares and cites. None of that touches the one thing a
// deliberation skill exists to do -- write the next version of the document -- and a
// defect that let the skill resolve, preview and validate while never once publishing
// sat behind all of it, green.
//
// That defect was `proposal-workspace-adapter.ts` deriving the successor's revision
// label with a hardcoded `/-r(\d+)\.md$/` and re-validating it with `/^r\d{2,}$/`,
// while the revision LETTER is `DOMAIN.artifact.revisionPattern`, which is `"v"` here.
// It is now `parseManagedRevision(...)?.revision` + `strictRevisionLabel(...)`, both
// profile-derived. This file is the guard that was missing: it drives a real
// CREATE_SUCCESSOR cycle, seed -> resolve -> preview -> accept -> published, and reads
// the successor's name and revision label off the result.
//
// A CHILD PROCESS, not a convenience. `package.json`'s `test` script fixes
// `DELIBERATION_DOMAIN_PROFILE` to the MATHEMATICAL profile for the whole suite run,
// and `domain-profile.ts` reads that variable exactly once, at module-import time.
// A second `jiti.import()` in this process would answer for the other domain and this
// file would silently certify `proposal-deliberation` instead -- lineage `-r02.md`,
// every assertion below still green, nothing about `experimental-deliberation` proven.
// So the whole cycle runs in one spawned `node` with the variable repointed, the same
// technique `experimental-deliberation-domain-profile.test.mjs` and
// `proposal-deliberation-required-sources.test.mjs` already established. The acceptance
// token lives only in the registry held by the orchestrator INSTANCE, so preview and
// accept happen inside that one child, against that one orchestrator.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const profilePath = path.join(repoRoot, 'skills/experimental-deliberation/profile.ts');
const piRoot = path.resolve('.');

const LINEAGE = 'domain-shift-baseline-sweep';
const SOURCE_FILENAME = `experiments-${LINEAGE}-v01.md`;
const TARGET_FILENAME = `experiments-${LINEAGE}-v02.md`;

// The seeded v01. Three properties are load-bearing rather than decorative:
//
//  - `## Changes` exists, because this domain DECLARES `artifact.changeHeader`, so the
//    orchestrator appends a second replace action over that block's span and the
//    preview is refused `CHANGE_SUMMARY_REQUIRED` without a `changeSummary` on the
//    request. Its bytes are exactly what `changeHeader.render` produces.
//  - the reported-results table gives the preservation gate real atoms to carry
//    forward, so `preservationApplicable` is true and the pass is not the vacuous
//    pass over an empty atom set.
//  - nothing here asserts an outcome, so this domain's `sourceAuthority` -- the data
//    paper bounding what may be claimed -- finds no conflict to acknowledge. The
//    body cells are empty for the same reason the gate demands: a run fills them.
//  - the dataset and validation-scheme declarations (change "the two declarations a
//    plan owes") live in their OWN section, never inside `## Protocol` -- the stub
//    planner's replace action is scoped to the Protocol section alone, so a
//    declaration placed inside it would be silently dropped by the edit and the
//    successor would fail its own canonical-form check.
const SEED = `# Experiments

## Changes

**What:** Seeded the first version of this plan.

**Why:** A lineage needs a starting point.

## Protocol

Each run trains on the source split and evaluates on the held-out target split.

## Data and validation

**Dataset:** DomainShift-Synth, source/target split as distributed

**Validation scheme:** paired t-test, 5 seeds, 10 repetitions

## Reported results

| Arm | Accuracy |
| --- | --- |
| Source only |  |
| Adapted |  |
`;

const HARNESS = `import path from 'node:path';
import os from 'node:os';
import { mkdir, mkdtemp, readdir } from 'node:fs/promises';
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
const workspaceModule = await jiti.import(path.join(engineDir, 'proposal-workspace.ts'));
const v2 = await jiti.import(path.join(engineDir, 'exports.ts'));
const { DOMAIN } = await jiti.import(path.join(engineDir, 'domain-profile.ts'));

const LINEAGE = ${JSON.stringify(LINEAGE)};
const SEED = ${JSON.stringify(SEED)};

// A temporary project root, and the managed document seeded into THIS domain's own
// directory (\`DOMAIN.artifact.directory\`, never a literal), through the workspace tool
// itself -- so the artifact marker the engine later demands is written by the same
// code that will read it back.
const root = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-publish-'));
await mkdir(path.join(root, DOMAIN.artifact.directory), { recursive: true });
await workspaceModule.createProposalWorkspaceTool(root)
	.execute('seed', { action: 'write', resource: 'proposal', slug: \`\${LINEAGE}-v01\`, content: SEED });

const guard = workspaceModule.createDocumentOperationGuard(root);
const adapter = new v2.ProposalWorkspaceAdapter(
	root,
	guard,
	workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard }),
	() => 'experimental-deliberation-publish');
// A stub planner: this test is about the publication path, not about a model. It edits
// exactly the one resolved locus and returns the full section span, which is what the
// successor composite splice replaces.
const planner = { plan: async (input) => ({
	actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '## Protocol\\n\\nEach run trains on the source split and evaluates on the held-out target split, over three seeds.\\n\\n' }],
	unresolvedQuestions: [],
}) };
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);

const request = {
	operation: 'CREATE_SUCCESSOR',
	editIntent: 'MODIFY',
	sourceFilename: \`experiments-\${LINEAGE}-v01.md\`,
	instruction: 'Modifica la sección Protocol.',
	// Required: this domain declares \`artifact.changeHeader\`.
	changeSummary: { what: 'Fijó tres semillas por corrida.', why: 'Una sola corrida no distingue ruido de efecto.' },
};

const preview = await orchestrator.execute(request);
// Same process, same orchestrator instance: the acceptance token is held in a registry
// that exists only in this memory and is consumed on this turn.
const published = preview.status === 'awaiting_acceptance'
	? await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken })
	: { status: 'not-attempted', reason: 'PREVIEW_DID_NOT_AWAIT_ACCEPTANCE' };

console.log(JSON.stringify({
	profile: {
		revisionPattern: DOMAIN.artifact.revisionPattern,
		directory: DOMAIN.artifact.directory,
		stem: DOMAIN.artifact.stem,
		sidecarRoot: DOMAIN.artifact.sidecarRoot,
		changeHeaderDeclared: Boolean(DOMAIN.artifact.changeHeader),
	},
	preview: {
		status: preview.status,
		reason: preview.reason ?? null,
		question: preview.question ?? null,
		targetFilename: preview.targetFilename ?? null,
		hasAcceptanceToken: typeof preview.acceptanceToken === 'string' && preview.acceptanceToken.length > 0,
		validationResults: preview.validation?.results ?? null,
		preservationApplicable: preview.validation?.preservationApplicable ?? null,
		lostAtomIds: (preview.preservationDelta?.lost ?? []).map((atom) => atom.id),
		sourceAuthorityConflicts: (preview.sourceAuthorityConflicts ?? []).map((conflict) => conflict.id),
	},
	published: {
		status: published.status,
		reason: published.reason ?? null,
		targetFilename: published.published?.targetFilename ?? null,
		targetRevision: published.published?.targetRevision ?? null,
		receiptTargetRevision: published.receipt?.targetRevision ?? null,
		receiptSourceRevision: published.receipt?.sourceRevision ?? null,
	},
	documentsOnDisk: (await readdir(path.join(root, DOMAIN.artifact.directory))).sort(),
	root,
}));
`;

let cached;
/** Runs the whole seed -> preview -> accept cycle once, in one child under this skill's profile. */
async function cycle() {
	if (cached) return cached;
	const scratch = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-publish-harness-'));
	const harnessPath = path.join(scratch, 'harness.mjs');
	await writeFile(harnessPath, HARNESS, 'utf8');
	try {
		const { stdout } = await execFileAsync('node', [harnessPath], {
			env: { ...process.env, DELIBERATION_DOMAIN_PROFILE: profilePath, ENGINE_DIR: engineDir },
			maxBuffer: 32 * 1024 * 1024,
		});
		cached = JSON.parse(stdout.trim().split('\n').pop());
		return cached;
	} finally {
		await rm(scratch, { recursive: true, force: true });
	}
}

// ---------------------------------------------------------------------------
// The guard against certifying the wrong domain
// ---------------------------------------------------------------------------

test('the cycle runs under the experimental profile, not the mathematical one the suite is fixed to', async () => {
	const { profile } = await cycle();
	// If `DELIBERATION_DOMAIN_PROFILE` failed to reach the child, every assertion below
	// would still pass against `proposal-deliberation` -- `research-concept-...-r02.md`
	// is a perfectly good successor -- and prove nothing about this skill. These four
	// values are the ones that differ, so this test is what makes the rest mean anything.
	assert.equal(profile.revisionPattern, 'v', 'the mathematical profile spells its revisions with "r"');
	assert.equal(profile.stem, 'experiments');
	assert.equal(profile.directory, 'experiments');
	assert.equal(profile.sidecarRoot, '.experimental-deliberation');
	assert.equal(profile.changeHeaderDeclared, true, 'this domain declares changeHeader, so changeSummary is required on preview');
});

// ---------------------------------------------------------------------------
// Preview
// ---------------------------------------------------------------------------

test('a seeded v01 previews a successor named experiments-<lineage>-v02.md and awaits acceptance with a token', async () => {
	const { preview } = await cycle();
	assert.equal(preview.status, 'awaiting_acceptance', `preview: ${JSON.stringify(preview)}`);
	assert.equal(preview.targetFilename, TARGET_FILENAME);
	assert.equal(preview.hasAcceptanceToken, true, 'an acceptance token is what the accept turn spends');
});

test('the preview validates cleanly, and its preservation pass is over a real atom set rather than an empty one', async () => {
	const { preview } = await cycle();
	assert.deepEqual(Object.entries(preview.validationResults ?? {}).filter(([, ok]) => !ok), [],
		`every candidate validation must hold: ${JSON.stringify(preview.validationResults)}`);
	assert.equal(preview.preservationApplicable, true,
		'the seed carries report-table atoms, so a pass here is a genuine one, not the vacuous pass over zero atoms');
	assert.deepEqual(preview.lostAtomIds, [], 'the edit touches only the protocol section, so no atom is lost');
	assert.deepEqual(preview.sourceAuthorityConflicts, [],
		'the seed asserts no outcome, so the data paper that bounds this document has nothing to conflict with');
});

// ---------------------------------------------------------------------------
// Accept: the adapter's own revision-label gate
// ---------------------------------------------------------------------------

test('the accept turn derives the successor label from the profile, so the adapter never refuses INVALID_TARGET_REVISION', async () => {
	const { published } = await cycle();
	// This is the exact defect the repair closed. `publishSuccessor` computes the
	// successor's revision label BEFORE it touches the workspace: with the old
	// hardcoded `/-r(\d+)\.md$/`, `experiments-<lineage>-v02.md` matches nothing, the
	// label is undefined and the method throws `INVALID_TARGET_REVISION` before a
	// single byte is written. Whatever else may block downstream, THIS must not.
	assert.notEqual(published.reason, 'INVALID_TARGET_REVISION',
		'the successor label must come from DOMAIN.artifact.revisionPattern ("v"), never a hardcoded "r"');
	assert.equal(published.status !== 'not-attempted', true, `the accept turn must run: ${JSON.stringify(published)}`);
});

// ---------------------------------------------------------------------------
// Publish
// ---------------------------------------------------------------------------

test('the accepted successor publishes as experiments-<lineage>-v02.md at revision v02', async () => {
	const { published, documentsOnDisk } = await cycle();
	assert.equal(published.status, 'published', `the accept turn must publish, not block: ${JSON.stringify(published)}`);
	assert.equal(published.targetFilename, TARGET_FILENAME);
	assert.equal(published.targetRevision, 'v02',
		'the revision label is the profile\'s own spelling; "r02" is the defect this file exists to catch');
	assert.equal(published.receiptTargetRevision, 'v02');
	assert.equal(published.receiptSourceRevision, 'v01');
	assert.deepEqual(documentsOnDisk, [SOURCE_FILENAME, TARGET_FILENAME],
		'the successor stands beside its source in this domain\'s own directory');
});
