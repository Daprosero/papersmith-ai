// Phase 4.2 (change 9): `profile.sourceAuthority` names which loaded sources this domain
// treats as a hard bound on claims, and detects a candidate's evidence contradicting one.
// Off by default -- `proposal-deliberation` declares none, so 4.2.1 runs directly under the
// normal npm test env (the math profile). The advisory/refuse scenarios spawn a FRESH process
// with a synthetic profile that DOES declare one, the same technique
// `proposal-deliberation-change-header.test.mjs` already established this slice.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
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

test('4.2.1 proposal-deliberation declares no sourceAuthority: SOURCE_AUTHORITY_CONFLICT is never raised, regardless of candidate content', async () => {
	const piRootLocal = piRoot;
	const { createJiti } = await import(pathToFileURL(path.join(piRootLocal, 'node_modules/jiti/lib/jiti.mjs')).href);
	const jiti = createJiti(import.meta.url, { alias: {
		'@earendil-works/pi-coding-agent': path.join(piRootLocal, 'dist/index.js'),
		'@earendil-works/pi-ai': path.join(piRootLocal, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
		typebox: path.join(piRootLocal, 'node_modules/typebox/build/index.mjs'),
	} });
	const v2 = await jiti.import(path.resolve(engineDir, 'exports.ts'));
	// Deliberately adversarial content: whatever a hypothetical bound-conflict detector might
	// look for (numbers, contradicting claims), proving absence is not just an empty fixture.
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# T\n\nVALUE: 999, exceeds every plausible bound.\n'));
	const target = state.structuralIndex.entries.find((e) => e.type === 'paragraph');
	const plan = { planVersion: '2', documentSha256: state.documentSha256, intent: 'INSERT', instructionHash: 'x', resolvedTargets: [target.entryId], semanticChange: false, destructiveIntent: false, cleanupLevel: 'NONE', constraints: [], actions: [{ kind: 'insert', anchorEntryId: target.entryId, position: 'after', content: '\n\nAdded.\n' }], expectedEffects: [], unresolvedQuestions: [] };
	const compiled = v2.compilePatches(state, plan);
	const result = await v2.validateCandidate(state, plan, compiled);
	assert.deepEqual(result.sourceAuthorityConflicts, []);
});

function customProfile({ severity }) {
	return `import type { DeliberationDomainProfile } from "${path.join(engineDir, 'domain-profile.js')}";
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
	},
	preservation: { extractAtoms: () => new Map(), violations: () => [] },
	references: { declares: () => [], cites: () => [] },
	sources: [{ path: "guidance", required: false }],
	// A pure detector, self-contained domain knowledge (mirrors preservation-math.ts's own
	// hardcoded canonical-form rules, per domain-profile.ts's own doc comment): a "VALUE: N"
	// above 100 in the candidate contradicts the fixed "declared bound is 100" assertion this
	// synthetic domain always holds.
	sourceAuthority: {
		names: ["bound-source"],
		detectConflicts: (candidateText) => {
			const conflicts = [];
			for (const m of candidateText.matchAll(/VALUE:\\s*(\\d+)/g)) {
				if (Number(m[1]) > 100) conflicts.push({ id: \`conflict-\${m[1]}\`, sourceName: "bound-source", claim: "declared bound is 100", evidence: m[0] });
			}
			return conflicts;
		},
		severity: ${JSON.stringify(severity)},
	},
	objective: {
		purpose: "test purpose",
		stages: [{ stage: "bound", establishes: "x", behindWhen: "x" }],
		arrival: "test arrival",
		humanStops: ["a person decides"],
	},
};
`;
}

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
const { mkdir, writeFile } = await import('node:fs/promises');
const root = process.env.PROJECT_ROOT;
const proposals = path.join(root, 'proposals');
await mkdir(proposals, { recursive: true });
${body}
`;
}

async function run(severity, body) {
	const projectRoot = await mkdtemp(path.join(os.tmpdir(), 'pp-source-authority-'));
	const profilePath = path.join(projectRoot, 'profile.ts');
	const harnessPath = path.join(projectRoot, 'harness.mjs');
	await writeFile(profilePath, customProfile({ severity }), 'utf8');
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

const SEED_MARKDOWN = '# Test Document\n\n## Target Section\n\nOriginal content, VALUE: 10.\n';

function seedAndOrchestrator(replacementText) {
	return `
await writeFile(path.join(proposals, 'research-concept-r01.md'), ${JSON.stringify(MARKER)} + ${JSON.stringify(SEED_MARKDOWN)});
const guard = workspaceModule.createDocumentOperationGuard(root);
const workspace = workspaceModule.createProposalWorkspaceTool(root, { operationGuard: guard });
const adapter = new v2.ProposalWorkspaceAdapter(root, guard, workspace, () => 'source-authority-test');
const planner = { async plan(input) { return { actions: [{ kind: 'replace', targetEntryId: input.target.entryId, replacementText: ${JSON.stringify(replacementText)} }], unresolvedQuestions: [] }; } };
const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter, undefined, planner);
const request = { operation: 'CREATE_SUCCESSOR', sourceFilename: 'research-concept-r01.md', instruction: 'Modifica la sección Target Section.' };
`;
}

test('4.2.2 a declared bound source contradiction is detected and surfaced as a preview-time advisory', async () => {
	const result = await run('advisory', `${seedAndOrchestrator('## Target Section\n\nUpdated content, VALUE: 150.\n')}
const preview = await orchestrator.execute(request);
console.log(JSON.stringify({ status: preview.status, sourceAuthorityConflicts: preview.sourceAuthorityConflicts }));
`);
	assert.equal(result.status, 'awaiting_acceptance', 'advisory severity must not block the preview turn');
	assert.equal(result.sourceAuthorityConflicts.length, 1);
	assert.equal(result.sourceAuthorityConflicts[0].sourceName, 'bound-source');
	assert.equal(result.sourceAuthorityConflicts[0].claim, 'declared bound is 100');
	assert.equal(result.sourceAuthorityConflicts[0].evidence, 'VALUE: 150');
});

test('4.2.3 non-contradicting evidence against the same declared bound source raises nothing', async () => {
	const result = await run('advisory', `${seedAndOrchestrator('## Target Section\n\nUpdated content, VALUE: 50.\n')}
const preview = await orchestrator.execute(request);
const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
console.log(JSON.stringify({ status: preview.status, sourceAuthorityConflicts: preview.sourceAuthorityConflicts ?? [], publishedStatus: published.status }));
`);
	assert.equal(result.status, 'awaiting_acceptance');
	assert.deepEqual(result.sourceAuthorityConflicts, []);
	assert.equal(result.publishedStatus, 'published', 'non-contradicting evidence must publish without any acknowledgement');
});

test('4.2.4 acknowledgedSourceConflicts on accept clears the advisory and publishes', async () => {
	const result = await run('advisory', `${seedAndOrchestrator('## Target Section\n\nUpdated content, VALUE: 150.\n')}
const preview = await orchestrator.execute(request);
const blockedWithoutAck = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken });
const conflictIds = preview.sourceAuthorityConflicts.map((c) => c.id);
console.log(JSON.stringify({ previewStatus: preview.status, blockedReason: blockedWithoutAck.reason, conflictIds }));
`);
	assert.equal(result.previewStatus, 'awaiting_acceptance');
	assert.equal(result.blockedReason, 'SOURCE_AUTHORITY_CONFLICT', 'an unacknowledged advisory conflict must still block accept');
	assert.equal(result.conflictIds.length, 1);

	// A SEPARATE fresh acceptance round (the first token above was already consumed by the
	// blocked attempt) that DOES echo the conflict id back must publish.
	const acknowledged = await run('advisory', `${seedAndOrchestrator('## Target Section\n\nUpdated content, VALUE: 150.\n')}
const preview = await orchestrator.execute(request);
const published = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken, acknowledgedSourceConflicts: preview.sourceAuthorityConflicts.map((c) => c.id) });
console.log(JSON.stringify({ publishedStatus: published.status }));
`);
	assert.equal(acknowledged.publishedStatus, 'published');
});

test('4.2.5 severity: refuse hard-blocks publish instead of advising, regardless of acknowledgement', async () => {
	const result = await run('refuse', `${seedAndOrchestrator('## Target Section\n\nUpdated content, VALUE: 150.\n')}
const preview = await orchestrator.execute(request);
const conflictIds = (preview.sourceAuthorityConflicts ?? []).map((c) => c.id);
const acceptAttempt = await orchestrator.execute({ ...request, acceptSuccessor: true, successorAcceptanceToken: preview.acceptanceToken, acknowledgedSourceConflicts: conflictIds });
console.log(JSON.stringify({ previewStatus: preview.status, previewReason: preview.reason, acceptStatus: acceptAttempt.status, acceptReason: acceptAttempt.reason }));
`);
	assert.equal(result.previewStatus, 'blocked', 'a refuse-severity bound must block outright, even at preview time, never offering acceptance');
	assert.equal(result.previewReason, 'SOURCE_AUTHORITY_CONFLICT');
});
