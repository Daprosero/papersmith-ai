// Phase 4.1 (change 8): the change header is its OWN resolved block span,
// gated on `profile.artifact.changeHeader` -- never a sidecar-only field,
// never an invariant exemption. `proposal-deliberation` declares none, so
// most scenarios here spawn a FRESH process with a profile that DOES declare
// one (the same technique `proposal-deliberation-sidecar-root-routing.test.mjs`
// and `proposal-deliberation-required-sources.test.mjs` already established:
// `domain-profile.ts` reads `DELIBERATION_DOMAIN_PROFILE` once per process).
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const piRoot = path.resolve('.');

const MARKER = '<!-- proposal-workspace:artifact:v1 -->\n';

// Declares `artifact.changeHeader` (heading "Changes", a two-field What/Why render) and a
// `preservation.extractAtoms` that recognizes any `\word`-shaped macro token -- self-contained
// domain knowledge, exactly parallel to how `preservation-math.ts` hardcodes its own canonical
// notation, with no engine-level file I/O (see `domain-profile.ts`'s `sourceAuthority` doc
// comment for the same reasoning applied to change 9).
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
		marker: ${JSON.stringify(MARKER)},
		changeHeader: {
			heading: "Changes",
			render: (s) => \`## Changes\\n\\n**What:** \${s.what}\\n\\n**Why:** \${s.why}\\n\\n\`,
		},
	},
	preservation: {
		extractAtoms: (source) => {
			const map = new Map();
			for (const m of source.matchAll(/\\\\[A-Za-z]+/g)) map.set(m[0], { id: m[0], kind: 'macro', text: m[0] });
			return map;
		},
		violations: () => [],
	},
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

function harness(body) {
	return `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspaceModule = await jiti.import(process.env.PROPOSAL_WORKSPACE_MODULE);
const v2 = await jiti.import(process.env.EXPORTS_MODULE);
const { mkdir, writeFile, readFile } = await import('node:fs/promises');
const root = process.env.PROJECT_ROOT;
const proposals = path.join(root, 'proposals');
await mkdir(proposals, { recursive: true });
${body}
`;
}

async function run(t, body, extraProfileSuffix = '') {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-change-header-'));
	const profilePath = path.join(projectRoot, 'profile.ts');
	const harnessPath = path.join(projectRoot, 'harness.mjs');
	await writeFile(profilePath, CUSTOM_PROFILE + extraProfileSuffix, 'utf8');
	await writeFile(harnessPath, harness(body), 'utf8');
	const env = {
		...process.env,
		DELIBERATION_DOMAIN_PROFILE: profilePath,
		PROPOSAL_WORKSPACE_MODULE: path.join(engineDir, 'proposal-workspace.ts'),
		EXPORTS_MODULE: path.join(engineDir, 'exports.ts'),
		PROJECT_ROOT: projectRoot,
	};
	const { stdout } = await execFileAsync('node', [harnessPath], { env });
	return JSON.parse(stdout.trim().split('\n').pop());
}

const HEADER_BLOCK = '## Changes\n\n**What:** Initial revision.\n\n**Why:** First published version.\n';
const TARGET_BLOCK = '## Target Section\n\nOriginal content for the target section.\n';
const SEED_MARKDOWN = `# Test Document\n\n${HEADER_BLOCK}\n${TARGET_BLOCK}`;

test('4.1.1 CREATE_SUCCESSOR omitting changeSummary is refused CHANGE_SUMMARY_REQUIRED, no successor published', async (t) => {
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(SEED_MARKDOWN)});
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'change-header-required');
const planner = { async plan(input) { return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '## Target Section\\n\\nUpdated content.\\n' }], unresolvedQuestions: [] }; } };
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
const result = await orchestrator.execute({ operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Target Section.' });
let r02Exists = true;
try { await readFile(path.join(proposals, 'research-concept-r02.md')); } catch { r02Exists = false; }
console.log(JSON.stringify({ status: result.status, reason: result.reason, r02Exists }));
`);
	assert.equal(result.status, 'blocked');
	assert.equal(result.reason, 'CHANGE_SUMMARY_REQUIRED');
	assert.equal(result.r02Exists, false, 'no successor may be published when changeSummary is required and absent');
});

test('4.1.2/4.1.3 a present changeSummary publishes, the header is its own resolved block span, and blast-radius consumers all recount correctly', async (t) => {
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(SEED_MARKDOWN)});
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'change-header-publish');
const planner = { async plan(input) { return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '## Target Section\\n\\nUpdated content for the target section.\\n' }], unresolvedQuestions: [] }; } };
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
const changeSummary = { what: 'Updated target section.', why: 'Testing change header.' };
const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Target Section.', changeSummary };
const preview = await orchestrator.execute(request);

// Blast radius 4.1.11 (operation-spec.ts): successorTargetCount now accounts for the header as
// an ADDITIONAL resolved target -- by construction, since publish() appended it to
// plan.resolvedTargets BEFORE resolveEffectiveOperationProfile ever ran.
const effectiveProfile = v2.resolveEffectiveOperationProfile({ intent: 'MODIFY', cleanupLevel: 'NONE', successorCompositeTarget: true, successorTargetCount: preview.plan.resolvedTargets.length });

// Blast radius 4.1.12 (growth-threshold.ts): the advisory must NOT count the header as an
// approved section. Recompute the header-EXCLUDED verdict directly from the byte spans
// preview.compiled already resolved for BOTH loci (never a separate, re-materialized state
// load -- composite entries are never persisted back to a derived-state cache) and prove
// growthAdvisory matches it exactly, never the header-INCLUDED byte count.
const headerEntryId = preview.plan.resolvedTargets[preview.plan.resolvedTargets.length - 1];
const targetEntryId = preview.plan.resolvedTargets.find((id) => id !== headerEntryId);
const targetPatch = preview.compiled.patches.find((p) => p.selector.entryId === targetEntryId);
const headerPatch = preview.compiled.patches.find((p) => p.selector.entryId === headerEntryId);
const targetBytes = targetPatch.selector.endByte - targetPatch.selector.startByte;
const headerBytes = headerPatch.selector.endByte - headerPatch.selector.startByte;
const r01Before = await readFile(path.join(proposals, 'research-concept-r01.md'));
const documentBytes = r01Before.length;
const excludeHeaderVerdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 1, approvedBytes: targetBytes, documentBytes });

const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
const r01 = (await readFile(path.join(proposals, 'research-concept-r01.md'))).toString('utf8');
const r02 = (await readFile(path.join(proposals, 'research-concept-r02.md'))).toString('utf8');
console.log(JSON.stringify({
	previewStatus: preview.status,
	previewResolvedTargetsLength: preview.plan.resolvedTargets.length,
	previewGrowthAdvisory: preview.growthAdvisory,
	excludeHeaderVerdict,
	headerBytesPositive: headerBytes > 0,
	effectiveMaxModelCalls: effectiveProfile.maxModelCalls,
	effectiveMaxPatchCount: effectiveProfile.maxPatchCount,
	publishedStatus: published.status,
	compiledPatchesLength: published.compiled.patches.length,
	// Blast radius 4.1.13 (successor-acceptance-registry.ts): compositeTargetIds is the same
	// preview.plan.resolvedTargets array threaded straight into the acceptance token.
	resolvedEntryIdsLength: published.receipt.resolvedEntryIds.length,
	resolvedEntryIdsIncludesHeader: published.receipt.resolvedEntryIds.includes(headerEntryId),
	receiptChangeSummary: published.receipt.changeSummary,
	titlePreserved: r01.startsWith(${JSON.stringify(MARKER)} + '# Test Document') && r02.includes('# Test Document'),
	r02HasNewHeader: r02.includes('**Why:** Testing change header.'),
	r02HasOldHeader: r02.includes('**Why:** First published version.'),
	r02HasNewTarget: r02.includes('Updated content for the target section.'),
}));
`);
	assert.equal(result.previewStatus, 'awaiting_acceptance');
	assert.equal(result.previewResolvedTargetsLength, 2, 'the header is one MORE resolved target alongside the real one');
	assert.equal(result.headerBytesPositive, true, 'sanity: the header locus must actually contribute bytes, or excluding it proves nothing');
	assert.deepEqual(result.previewGrowthAdvisory, result.excludeHeaderVerdict, 'growthAdvisory must be computed WITHOUT the header, never with it');
	assert.equal(result.effectiveMaxModelCalls, 2, 'operation-spec.ts must account for the header as an additional resolved target');
	assert.equal(result.effectiveMaxPatchCount, 2);
	assert.equal(result.publishedStatus, 'published');
	assert.equal(result.compiledPatchesLength, 2);
	assert.equal(result.resolvedEntryIdsLength, 2, 'the receipt resolvedEntryIds must recount with the extra header block');
	assert.equal(result.resolvedEntryIdsIncludesHeader, true);
	assert.deepEqual(result.receiptChangeSummary, { what: 'Updated target section.', why: 'Testing change header.' });
	assert.equal(result.titlePreserved, true, 'the byte-preservation invariant: bytes outside both resolved loci stay identical');
	assert.equal(result.r02HasNewHeader, true, 'the header locus was replaced with the new changeSummary');
	assert.equal(result.r02HasOldHeader, false);
	assert.equal(result.r02HasNewTarget, true);
});

test('4.1.5 a \\command-shaped macro token inside a previous header, once replaced, registers as a lost preservation atom', async (t) => {
	const seedWithMacro = `# Test Document\n\n## Changes\n\n**What:** Initial revision.\n\n**Why:** Uses \\legacyflag notation.\n\n${TARGET_BLOCK}`;
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(seedWithMacro)});
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'change-header-macro-loss');
const planner = { async plan(input) { return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '## Target Section\\n\\nUpdated content.\\n' }], unresolvedQuestions: [] }; } };
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
const changeSummary = { what: 'Updated target section.', why: 'No macro reference this time.' };
const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Target Section.', changeSummary };
const preview = await orchestrator.execute(request);
const lostIds = (preview.preservationDelta?.lost ?? []).map((atom) => atom.id);
const blockedWithoutAck = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
console.log(JSON.stringify({ previewStatus: preview.status, lostIds, blockedWithoutAckStatus: 'unused', blockedReason: blockedWithoutAck.reason }));
`);
	assert.equal(result.previewStatus, 'awaiting_acceptance');
	assert.ok(result.lostIds.includes('\\legacyflag'), `expected \\legacyflag to register as a lost preservation atom, got ${JSON.stringify(result.lostIds)}`);
	assert.equal(result.blockedReason, 'MATH_REMOVALS_NOT_ACKNOWLEDGED', 'an unacknowledged lost header macro must still block accept, exactly like any other lost atom');
});

test('4.1.5b acknowledging the lost header macro completes the publish', async (t) => {
	const seedWithMacro = `# Test Document\n\n## Changes\n\n**What:** Initial revision.\n\n**Why:** Uses \\legacyflag notation.\n\n${TARGET_BLOCK}`;
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(seedWithMacro)});
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'change-header-macro-ack');
const planner = { async plan(input) { return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '## Target Section\\n\\nUpdated content.\\n' }], unresolvedQuestions: [] }; } };
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
const changeSummary = { what: 'Updated target section.', why: 'No macro reference this time.' };
const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Target Section.', changeSummary };
const preview = await orchestrator.execute(request);
const lostIds = (preview.preservationDelta?.lost ?? []).map((atom) => atom.id);
const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken, acknowledgedRemovals: lostIds });
console.log(JSON.stringify({ publishedStatus: published.status, publishedReason: published.reason, publishedValidation: published.validation }));
`);
	assert.equal(result.publishedStatus, 'published', JSON.stringify(result));
});

test('4.1.15 a conceptual-revision CREATE_SUCCESSOR also carries the header block through without breaking the arity guards', async (t) => {
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(SEED_MARKDOWN)});
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'change-header-conceptual');
const planner = { async plan(input) { return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '## Target Section\\n\\nConceptually revised content.\\n' }], unresolvedQuestions: [] }; } };
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
const changeSummary = { what: 'Conceptual revision.', why: 'Testing conceptual-planner.ts arity guards.' };
const request = { operation: 'CREATE_SUCCESSOR', editIntent: 'CONCEPTUAL_REVISION', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Target Section.', changeSummary };
const preview = await orchestrator.execute(request);
const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
console.log(JSON.stringify({ previewStatus: preview.status, previewReason: preview.reason, resolvedTargetsLength: preview.plan?.resolvedTargets?.length, publishedStatus: published.status, publishedReason: published.reason }));
`);
	assert.equal(result.previewStatus, 'awaiting_acceptance', JSON.stringify(result));
	assert.equal(result.resolvedTargetsLength, 2);
	assert.equal(result.publishedStatus, 'published', JSON.stringify(result));
});

test('4.1.4 CREATE_SUCCESSOR without a declared changeHeader never requires changeSummary and never adds a second resolved target', async () => {
	const piRootLocal = piRoot;
	const { createJiti } = await import(pathToFileURL(path.join(piRootLocal, 'node_modules/jiti/lib/jiti.mjs')).href);
	const jiti = createJiti(import.meta.url, { alias: {
		'@earendil-works/pi-coding-agent': path.join(piRootLocal, 'dist/index.js'),
		'@earendil-works/pi-ai': path.join(piRootLocal, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
		typebox: path.join(piRootLocal, 'node_modules/typebox/build/index.mjs'),
	} });
	const workspaceModule = await jiti.import(path.resolve(engineDir, 'proposal-workspace.ts'));
	const v2 = await jiti.import(path.resolve(engineDir, 'exports.ts'));
	const root = await mkdtemp(path.join(os.tmpdir(), 'pp-change-header-undeclared-'));
	const proposals = path.join(root, 'proposals');
	await mkdir(proposals, { recursive: true });
	const bootstrap = workspaceModule.createProposalWorkspaceTool(root);
	await bootstrap.execute('seed', { action: 'write', resource: 'proposal', slug: 'r01', content: '# R01\n\n## Target Section\n\nOriginal content.\n' });
	const guard = workspaceModule.createDocumentOperationGuard(root);
	const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
	const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'change-header-undeclared');
	const planner = { async plan(input) { return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: '## Target Section\n\nUpdated content.\n' }], unresolvedQuestions: [] }; } };
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
	// No changeSummary supplied at all -- must not be required, since this DOMAIN (the default
	// math profile under normal npm test env) declares no `artifact.changeHeader`.
	const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Target Section.' };
	const preview = await orchestrator.execute(request);
	assert.equal(preview.status, 'awaiting_acceptance', JSON.stringify(preview));
	assert.equal(preview.plan.resolvedTargets.length, 1, 'no header locus may be appended when changeHeader is undeclared');
	assert.equal(preview.growthAdvisory, undefined, 'growthAdvisory stays undefined on this path when changeHeader is undeclared, exactly as before this change');
	const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
	assert.equal(published.status, 'published', JSON.stringify(published));
	assert.equal(published.receipt.resolvedEntryIds.length, 1);
	assert.equal('changeSummary' in published.receipt, false, 'the receipt must not carry a changeSummary key when changeHeader is undeclared');
});

// ---------------------------------------------------------------------------
// The ambient-composite path (CREATE_SUCCESSOR + `resolvedDecisions` carrying any
// non-`replace` decision)
//
// Two measured gaps closed together, because they are one mechanism seen from two
// sides. `orchestrator.ts` used to gate the header injection on `!frozenCompiled`,
// and `ambientBatchNeedsComposite` precompiles the WHOLE changeset -- through
// `compileSuccessorCompositeChangeset` -- as soon as one decision in the batch is
// not a `replace`. So `publish()` was handed an already-frozen compilation it could
// no longer add a block span to, and simply skipped the header:
//
//   G1 the published successor carried the PREVIOUS version's `## Changes` block
//      over bytes that were a version newer -- the receipt still recorded the new
//      `changeSummary`, so the history was intact while the DOCUMENT lied.
//   G2 the ambient-composite path never injected the header at all, even with a
//      `changeSummary` present (it was documented as a scope limitation).
//
// The fix appends the header as one MORE disjoint splice part BEFORE the changeset
// is compiled, so it stays its own resolved block span -- never an exemption from
// `COMPOSITE_UNTOUCHED_INVARIANT`, which only ever inspects the gaps BETWEEN spans.
// ---------------------------------------------------------------------------

test('4.1.16 an ambient batch carrying a non-replace decision still rewrites the change header in the published document', async (t) => {
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(SEED_MARKDOWN)});
const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
const gate = v2.ambiguityGate(v2.resolveSuccessorTarget(state, 'sección Target Section').candidates);
const targetEntryId = gate.candidate.entryId;
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
let counter = 0;
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => \`change-header-ambient-insert-\${++counter}\`);
// NO planner at all: the batch is resolved entirely from resolvedDecisions, which is
// what makes this the ambient-composite path rather than the replace-only one.
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter);
const request = {
	operation: 'CREATE_SUCCESSOR',
	sourceFilename: 'research-concept-r01.md',
	instruction: 'Agrega una nota tras Target Section.',
	selectedEntryId: 'sección Target Section',
	changeSummary: { what: 'Added a note after the target section.', why: 'The batch is not replace-only.' },
	resolvedDecisions: [{ kind: 'insert', anchorEntryId: targetEntryId, position: 'after', content: '\\n## Extra Note\\n\\nInserted content.\\n' }],
};
const preview = await orchestrator.execute(request);
const published = preview.status === 'awaiting_acceptance'
	? await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken })
	: { status: 'not-attempted' };
const r02 = published.status === 'published' ? (await readFile(path.join(proposals, 'research-concept-r02.md'))).toString('utf8') : '';
console.log(JSON.stringify({
	previewStatus: preview.status,
	previewReason: preview.reason ?? null,
	publishedStatus: published.status,
	publishedReason: published.reason ?? null,
	r02HasNewHeader: r02.includes('**Why:** The batch is not replace-only.'),
	r02HasStaleHeader: r02.includes('**Why:** First published version.'),
	r02HasInsertedContent: r02.includes('Inserted content.'),
	r02PreservesUntouchedBytes: r02.includes('# Test Document') && r02.includes('Original content for the target section.'),
	receiptChangeSummary: published.receipt?.changeSummary ?? null,
}));
`);
	assert.equal(result.previewStatus, 'awaiting_acceptance', JSON.stringify(result));
	assert.equal(result.publishedStatus, 'published', JSON.stringify(result));
	assert.equal(result.r02HasInsertedContent, true, 'sanity: the non-replace decision must actually have applied, or the header claim below is vacuous');
	assert.equal(result.r02HasNewHeader, true,
		'the successor must carry the header describing ITS OWN change, not the previous version\'s');
	assert.equal(result.r02HasStaleHeader, false,
		'a header describing the PREVIOUS version over newer bytes is the document lying about itself');
	assert.equal(result.r02PreservesUntouchedBytes, true,
		'the header is one more disjoint span, so every byte outside the spliced spans survives untouched');
	assert.deepEqual(result.receiptChangeSummary, { what: 'Added a note after the target section.', why: 'The batch is not replace-only.' },
		'the receipt already recorded the summary before this fix -- it must keep doing so');
});

test('4.1.17 the ambient-composite path counts the header as its own resolved block span across every blast-radius consumer', async (t) => {
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(SEED_MARKDOWN)});
const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
const gate = v2.ambiguityGate(v2.resolveSuccessorTarget(state, 'sección Target Section').candidates);
const targetEntryId = gate.candidate.entryId;
// Resolved from the SAME read-only primitive orchestrator.ts itself uses, so this is
// the expected id rather than one re-derived by a different rule.
const headerCandidate = v2.changeHeaderLocusCandidate(state, 'Changes');
const documentBytes = (await readFile(path.join(proposals, 'research-concept-r01.md'))).length;
const targetSpan = gate.candidate.composite.endByte - gate.candidate.composite.startByte;
const headerSpan = headerCandidate.composite.endByte - headerCandidate.composite.startByte;
// growth-threshold.ts (blast radius): the advisory measures the APPROVED sections the
// author actually chose. The header is engine bookkeeping and must never inflate it.
// This fixture discriminates: the target alone is under the 40% ratio, the target plus
// the header is over it, so a header-counting advisory would warn and this one must not.
const excludeHeaderVerdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 1, approvedBytes: targetSpan, documentBytes });
const includeHeaderVerdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 2, approvedBytes: targetSpan + headerSpan, documentBytes });
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
let counter = 0;
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => \`change-header-ambient-arity-\${++counter}\`);
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter);
const request = {
	operation: 'CREATE_SUCCESSOR',
	sourceFilename: 'research-concept-r01.md',
	instruction: 'Agrega una nota tras Target Section.',
	selectedEntryId: 'sección Target Section',
	changeSummary: { what: 'Added a note after the target section.', why: 'The batch is not replace-only.' },
	resolvedDecisions: [{ kind: 'insert', anchorEntryId: targetEntryId, position: 'after', content: '\\n## Extra Note\\n\\nInserted content.\\n' }],
};
const preview = await orchestrator.execute(request);
const resolvedTargets = preview.plan?.resolvedTargets ?? [];
// operation-spec.ts (blast radius): maxPatchCount for a composite successor IS the
// resolved-target count, and the adapter refuses INVALID_OPERATION_BUDGET when the
// compiled patches outnumber it -- so the header must add exactly one to BOTH.
const effectiveProfile = v2.resolveEffectiveOperationProfile({ intent: 'MODIFY', cleanupLevel: 'NONE', successorCompositeTarget: true, successorTargetCount: resolvedTargets.length });
const published = preview.status === 'awaiting_acceptance'
	? await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken })
	: { status: 'not-attempted' };
console.log(JSON.stringify({
	previewStatus: preview.status,
	previewReason: preview.reason ?? null,
	resolvedTargets,
	expectedTargetEntryId: targetEntryId,
	expectedHeaderEntryId: headerCandidate.entryId,
	compiledPatchCount: preview.compiled?.patches?.length ?? null,
	effectiveMaxPatchCount: effectiveProfile.maxPatchCount,
	growthAdvisory: preview.growthAdvisory ?? null,
	excludeHeaderVerdict,
	includeHeaderVerdict,
	publishedStatus: published.status,
	publishedReason: published.reason ?? null,
	// successor-acceptance-registry.ts + revision-receipt.ts (blast radius): the token's
	// compositeTargetIds is the very same resolvedTargets array, and the receipt's
	// resolvedEntryIds is what a later audit reads the version's loci back from.
	receiptResolvedEntryIds: published.receipt?.resolvedEntryIds ?? null,
}));
`);
	assert.equal(result.previewStatus, 'awaiting_acceptance', JSON.stringify(result));
	assert.deepEqual(result.resolvedTargets, [result.expectedTargetEntryId, result.expectedHeaderEntryId],
		'the header joins the ambient batch as one MORE resolved block span, last, exactly as the replace-only path appends it');
	assert.equal(result.compiledPatchCount, 2, 'the header is compiled as its own patch, never folded into the caller\'s');
	assert.equal(result.effectiveMaxPatchCount, 2, 'operation-spec.ts must recount, or the adapter refuses INVALID_OPERATION_BUDGET');
	assert.notDeepEqual(result.excludeHeaderVerdict, result.includeHeaderVerdict,
		'sanity: this fixture must actually discriminate, or the advisory assertion below proves nothing');
	assert.deepEqual(result.growthAdvisory, result.excludeHeaderVerdict,
		'the growth advisory measures the author\'s approved sections only -- never the engine\'s own header block');
	assert.equal(result.publishedStatus, 'published', JSON.stringify(result));
	assert.deepEqual(result.receiptResolvedEntryIds, [result.expectedTargetEntryId, result.expectedHeaderEntryId],
		'the receipt records both loci this version actually rewrote');
});

test('4.1.18 an ambient batch whose own decision claims the change-header locus is refused SUCCESSOR_TARGET_OVERLAP', async (t) => {
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(SEED_MARKDOWN)});
const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
const gate = v2.ambiguityGate(v2.resolveSuccessorTarget(state, 'sección Changes').candidates);
const headerCandidate = v2.changeHeaderLocusCandidate(state, 'Changes');
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'change-header-ambient-overlap');
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter);
const preview = await orchestrator.execute({
	operation: 'CREATE_SUCCESSOR',
	sourceFilename: 'research-concept-r01.md',
	instruction: 'Elimina la sección Changes.',
	selectedEntryId: 'sección Changes',
	changeSummary: { what: 'Tried to delete the change header.', why: 'The engine must rewrite that same block.' },
	resolvedDecisions: [{ kind: 'delete', targetEntryId: gate.candidate.entryId, instructionEvidence: 'Elimina la sección Changes.', reason: 'obsolete' }],
});
let r02Exists = true;
try { await readFile(path.join(proposals, 'research-concept-r02.md')); } catch { r02Exists = false; }
console.log(JSON.stringify({
	resolvedSameLocus: gate.candidate.entryId === headerCandidate.entryId,
	status: preview.status,
	reason: preview.reason ?? null,
	r02Exists,
}));
`);
	assert.equal(result.resolvedSameLocus, true,
		'sanity: the batch must really claim the header\'s own span, or nothing collides');
	assert.equal(result.status, 'blocked', JSON.stringify(result));
	// Not a special case, and deliberately not an exemption: the header part reaches
	// `compileSuccessorCompositeChangeset`'s own disjointness check and is refused there,
	// exactly as `compileSuccessorCompositeReplacement` refuses the same collision on the
	// replace-only path. Silently dropping the header would publish the stale-header lie.
	assert.equal(result.reason, 'SUCCESSOR_TARGET_OVERLAP', JSON.stringify(result));
	assert.equal(result.r02Exists, false, 'nothing may publish when the header cannot be rewritten');
});

// The relocation-only branch of the same path. `move`/`copy` decisions freeze a
// SEPARATE composite group from the in-place ones, compiled at its own call site, so
// a header joined only to the in-place group would leave exactly this batch shape
// publishing the stale header -- the gap fixed for one branch and left open next door.
const RELOCATION_SEED = `# Test Document\n\n${HEADER_BLOCK}\n## Alpha\n\nAlpha body.\n\n## Beta\n\nBeta body.\n\n## Tail\n\nTail body.\n`;

test('4.1.19 a relocation-only ambient batch rewrites the change header too, and recounts with the moved pair', async (t) => {
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(RELOCATION_SEED)});
const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
const alphaEntryId = v2.ambiguityGate(v2.resolveSuccessorTarget(state, 'sección Alpha').candidates).candidate.entryId;
const betaEntryId = v2.ambiguityGate(v2.resolveSuccessorTarget(state, 'sección Beta').candidates).candidate.entryId;
const headerEntryId = v2.changeHeaderLocusCandidate(state, 'Changes').entryId;
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
let counter = 0;
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => \`change-header-ambient-move-\${++counter}\`);
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter);
const request = {
	operation: 'CREATE_SUCCESSOR',
	sourceFilename: 'research-concept-r01.md',
	instruction: 'Mueve Alpha después de Beta.',
	selectedEntryIds: ['sección Alpha', 'sección Beta'],
	changeSummary: { what: 'Moved Alpha after Beta.', why: 'Relocation-only batches need a header too.' },
	resolvedDecisions: [{ kind: 'move', sourceEntryIds: [alphaEntryId], destinationAnchorId: betaEntryId, position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }],
};
const preview = await orchestrator.execute(request);
const published = preview.status === 'awaiting_acceptance'
	? await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken })
	: { status: 'not-attempted' };
const r02 = published.status === 'published' ? (await readFile(path.join(proposals, 'research-concept-r02.md'))).toString('utf8') : '';
console.log(JSON.stringify({
	previewStatus: preview.status,
	previewReason: preview.reason ?? null,
	resolvedTargets: preview.plan?.resolvedTargets ?? [],
	expected: [alphaEntryId, betaEntryId, headerEntryId],
	compiledPatchCount: preview.compiled?.patches?.length ?? null,
	publishedStatus: published.status,
	publishedReason: published.reason ?? null,
	r02HasNewHeader: r02.includes('**Why:** Relocation-only batches need a header too.'),
	r02HasStaleHeader: r02.includes('**Why:** First published version.'),
	alphaFollowsBeta: r02.indexOf('Beta body.') >= 0 && r02.indexOf('Beta body.') < r02.indexOf('Alpha body.'),
}));
`);
	assert.equal(result.previewStatus, 'awaiting_acceptance', JSON.stringify(result));
	assert.deepEqual(result.resolvedTargets, result.expected,
		'source, destination, then the header -- the relocation group recounts exactly like the in-place one');
	// A `move` contributes TWO parts (insert at the destination, delete at the source) for its
	// two claimed targets, and the header adds the third of each -- so patches and resolved
	// targets stay balanced and `operation-spec.ts`'s maxPatchCount still covers them.
	assert.equal(result.compiledPatchCount, 3);
	assert.equal(result.publishedStatus, 'published', JSON.stringify(result));
	assert.equal(result.alphaFollowsBeta, true, 'sanity: the relocation must actually have applied');
	assert.equal(result.r02HasNewHeader, true, 'a move-only batch rewrites the header exactly as an in-place one does');
	assert.equal(result.r02HasStaleHeader, false);
});

test('4.1.20 a MIXED ambient batch rewrites the header on the version it belongs to, and the second version inherits it', async (t) => {
	const result = await run(t, `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(RELOCATION_SEED)});
const state = await v2.loadDocumentState(root, 'research-concept-r01.md');
const alphaEntryId = v2.ambiguityGate(v2.resolveSuccessorTarget(state, 'sección Alpha').candidates).candidate.entryId;
const betaEntryId = v2.ambiguityGate(v2.resolveSuccessorTarget(state, 'sección Beta').candidates).candidate.entryId;
const tailEntryId = v2.ambiguityGate(v2.resolveSuccessorTarget(state, 'sección Tail').candidates).candidate.entryId;
const headerEntryId = v2.changeHeaderLocusCandidate(state, 'Changes').entryId;
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
// A mixed batch performs TWO sequential publishes against the same adapter, and the
// guard rejects a second begin_document_operation on an already-finalized id.
let counter = 0;
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => \`change-header-ambient-mixed-\${++counter}\`);
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter);
const request = {
	operation: 'CREATE_SUCCESSOR',
	sourceFilename: 'research-concept-r01.md',
	instruction: 'Reescribe Tail y mueve Alpha después de Beta.',
	selectedEntryIds: ['sección Tail', 'sección Alpha', 'sección Beta'],
	changeSummary: { what: 'Rewrote Tail and moved Alpha.', why: 'A mixed batch publishes two versions from one consent.' },
	resolvedDecisions: [
		{ kind: 'replace', targetEntryId: tailEntryId, replacementText: '## Tail\\n\\nRewritten tail body.\\n' },
		{ kind: 'move', sourceEntryIds: [alphaEntryId], destinationAnchorId: betaEntryId, position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' },
	],
};
const preview = await orchestrator.execute(request);
const published = preview.status === 'awaiting_acceptance'
	? await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken })
	: { status: 'not-attempted' };
const read = async (name) => { try { return (await readFile(path.join(proposals, name))).toString('utf8'); } catch { return null; } };
const r02 = await read('research-concept-r02.md');
const r03 = await read('research-concept-r03.md');
console.log(JSON.stringify({
	previewStatus: preview.status,
	previewReason: preview.reason ?? null,
	// The frozen in-place half is Tail's replace plus the header -- the relocation half is
	// deferred and re-resolved after this one publishes.
	resolvedTargets: preview.plan?.resolvedTargets ?? [],
	expectedInPlace: [tailEntryId, headerEntryId],
	publishedStatus: published.status,
	publishedReason: published.reason ?? null,
	versionCount: published.versions?.length ?? null,
	r02HasNewHeader: (r02 ?? '').includes('**Why:** A mixed batch publishes two versions from one consent.'),
	r02HasStaleHeader: (r02 ?? '').includes('**Why:** First published version.'),
	r03HasNewHeader: (r03 ?? '').includes('**Why:** A mixed batch publishes two versions from one consent.'),
	r03HasStaleHeader: (r03 ?? '').includes('**Why:** First published version.'),
	r03AlphaFollowsBeta: r03 !== null && r03.indexOf('Beta body.') < r03.indexOf('Alpha body.'),
	r03HasRewrittenTail: (r03 ?? '').includes('Rewritten tail body.'),
}));
`);
	assert.equal(result.previewStatus, 'awaiting_acceptance', JSON.stringify(result));
	assert.deepEqual(result.resolvedTargets, result.expectedInPlace,
		'the header joins the in-place half, which is the version this batch first publishes');
	assert.equal(result.publishedStatus, 'published', JSON.stringify(result));
	assert.equal(result.versionCount, 2, 'sanity: a mixed batch really does publish two successor versions');
	assert.equal(result.r02HasNewHeader, true);
	assert.equal(result.r02HasStaleHeader, false);
	// The relocation half publishes ON TOP of r02's bytes, which already carry the rewritten
	// header. Re-rendering it there would only rewrite it to the identical text, so the header
	// is deliberately joined once, to the first version -- and the second inherits it.
	assert.equal(result.r03HasNewHeader, true, 'the second version inherits the header the first one rewrote');
	assert.equal(result.r03HasStaleHeader, false);
	assert.equal(result.r03AlphaFollowsBeta, true, 'sanity: the deferred relocation half really applied');
	assert.equal(result.r03HasRewrittenTail, true, 'sanity: the in-place half survived into the second version');
});
