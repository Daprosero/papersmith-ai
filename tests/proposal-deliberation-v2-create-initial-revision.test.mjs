import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

// Chain under test: cli.mjs's registered `proposal_deliberation_execute` tool dispatches
// operation:'CREATE_INITIAL_REVISION' -> proposal-workspace.ts's dedicated route
// (independent of PROPOSAL_DELIBERATION_SCIENTIFIC_WORKFLOW_ENABLED and CANONICAL_METADATA_UNAVAILABLE)
// -> InitialRevisionCreationService -> InitialRevisionRenderer.renderFromIdea.
// HARD CONSTRAINT: this file NEVER writes to a real proposals/ directory -- every write goes
// through either an in-memory fake publication port or a mkdtemp() temp project root.

const root = process.cwd();
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const aiRoot = path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(aiRoot, 'index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(path.join(root, '.claude/skills/_core/deliberation/engine/exports.ts'));
const workspace = await jiti.import(path.join(root, '.claude/skills/_core/deliberation/engine/proposal-workspace.ts'));

const MARKER = '<!-- proposal-workspace:artifact:v1 -->\n';

// ---------------------------------------------------------------------------
// Pure rendering: InitialRevisionRenderer.renderFromIdea (no I/O at all)
// ---------------------------------------------------------------------------

test('renderFromIdea composes v1 markdown from the idea alone, deriving title/sectionHeading/slug from the idea text', () => {
	const renderer = new v2.InitialRevisionRenderer();
	const composed = renderer.renderFromIdea({ idea: 'A tutor that refutes weak proofs. It should also cite prior work.' });
	assert.equal(
		composed.markdown,
		'# A tutor that refutes weak proofs.\n\n## It should also cite prior work.\n\nA tutor that refutes weak proofs. It should also cite prior work.\n',
	);
	assert.deepEqual(composed.canonicalMetadata, { schemaVersion: 1, title: 'A tutor that refutes weak proofs.', sectionHeading: 'It should also cite prior work.' });
	assert.equal(composed.slug, 'a-tutor-that-refutes-weak-proofs');
});

test('renderFromIdea includes paper-guide fragments as reference context, and omits the section entirely when there are none', () => {
	const renderer = new v2.InitialRevisionRenderer();
	const withGuide = renderer.renderFromIdea({
		idea: 'Bounded tutor refutation loop for proposal drafting.',
		guideFragments: [{ path: 'guidance/paper-guide/normalized/style.md', content: 'Always define notation before use.' }],
	});
	assert.match(withGuide.markdown, /## Paper Guide Reference\n\n### guidance\/paper-guide\/normalized\/style\.md\n\nAlways define notation before use\.\n/);
	assert.match(withGuide.markdown, /Bounded tutor refutation loop for proposal drafting\./);

	const withoutGuide = renderer.renderFromIdea({ idea: 'Bounded tutor refutation loop for proposal drafting.' });
	assert.doesNotMatch(withoutGuide.markdown, /Paper Guide Reference/);
});

test('renderFromIdea never emits a fixed generic skeleton: two different ideas produce two different titles, headings, and slugs', () => {
	const renderer = new v2.InitialRevisionRenderer();
	const first = renderer.renderFromIdea({ idea: 'Formalizing entropy bounds for adaptive samplers.' });
	const second = renderer.renderFromIdea({ idea: 'A new proof strategy for convergence under noise.' });
	assert.notEqual(first.markdown, second.markdown);
	assert.notEqual(first.canonicalMetadata.title, second.canonicalMetadata.title);
	assert.notEqual(first.slug, second.slug);
});

test('renderFromIdea rejects an empty idea and falls back to safe metadata when sentence splitting yields nothing usable', () => {
	const renderer = new v2.InitialRevisionRenderer();
	assert.throws(() => renderer.renderFromIdea({ idea: '   ' }), /INITIAL_REVISION_IDEA_REQUIRED/);
	const symbolsOnly = renderer.renderFromIdea({ idea: '???' });
	assert.equal(symbolsOnly.slug, 'concept');
});

// ---------------------------------------------------------------------------
// InitialRevisionCreationService with in-memory fake ports (no filesystem at all)
// ---------------------------------------------------------------------------

function fakeExistingProposalPort(exists) {
	return { hasManagedProposal: async () => exists };
}

function fakePublicationPort() {
	const published = [];
	return {
		published,
		port: {
			async publish(candidate) {
				published.push(candidate);
				return { filename: candidate.filename, revision: candidate.revision, documentSha256: `fake-sha-${published.length}`, bytesWritten: Buffer.byteLength(candidate.markdown, 'utf8') };
			},
		},
	};
}

test('creates a managed v1 in memory when no managed proposal exists, and never touches a real filesystem', async () => {
	const fake = fakePublicationPort();
	const service = new v2.InitialRevisionCreationService(fakeExistingProposalPort(false), fake.port);
	const result = await service.execute({ idea: 'Bounded refutation loop for a mathematical tutor.' });
	assert.equal(result.status, 'created');
	assert.match(result.filename, /^research-concept-[a-z0-9-]+-r01\.md$/);
	assert.equal(result.revision, 'r01');
	assert.equal(fake.published.length, 1);
	assert.equal(fake.published[0].filename, result.filename);
	assert.match(fake.published[0].markdown, /Bounded refutation loop for a mathematical tutor\./);
});

test('refuses (does not overwrite or duplicate) when a managed proposal already exists, and never calls publish', async () => {
	const fake = fakePublicationPort();
	const service = new v2.InitialRevisionCreationService(fakeExistingProposalPort(true), fake.port);
	const result = await service.execute({ idea: 'Bounded refutation loop for a mathematical tutor.' });
	assert.deepEqual(result, { status: 'blocked', code: 'MANAGED_PROPOSAL_ALREADY_EXISTS' });
	assert.equal(fake.published.length, 0);
});

test('rejects an empty idea before ever checking for an existing proposal', async () => {
	let checked = false;
	const existingProposal = { hasManagedProposal: async () => { checked = true; return false; } };
	const fake = fakePublicationPort();
	const service = new v2.InitialRevisionCreationService(existingProposal, fake.port);
	const result = await service.execute({ idea: '   ' });
	assert.deepEqual(result, { status: 'blocked', code: 'INITIAL_IDEA_REQUIRED' });
	assert.equal(checked, false);
	assert.equal(fake.published.length, 0);
});

test('threads paper-guide fragments through to the rendered candidate passed to the publication port', async () => {
	const fake = fakePublicationPort();
	const service = new v2.InitialRevisionCreationService(fakeExistingProposalPort(false), fake.port);
	await service.execute({
		idea: 'A concept that reuses the paper guide notation conventions.',
		guideFragments: [{ path: 'guidance/paper-guide/normalized/notation.md', content: 'Use bold for vectors.' }],
	});
	assert.match(fake.published[0].markdown, /Use bold for vectors\./);
});

// ---------------------------------------------------------------------------
// Reachability: the real `proposal_deliberation_execute` tool dispatch (cli.mjs's exact call
// contract), independent of PROPOSAL_DELIBERATION_SCIENTIFIC_WORKFLOW_ENABLED. Uses a mkdtemp()
// temp project root only -- never the real repository `proposals/` directory.
// ---------------------------------------------------------------------------

async function fixture() {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-create-initial-'));
	await mkdir(path.join(projectRoot, 'proposals'), { recursive: true });
	const guard = workspace.createDocumentOperationGuard(projectRoot);
	const tools = [];
	workspace.createProposalDeliberationExtension({ projectRoot, operationGuard: guard })({ registerTool: (candidate) => tools.push(candidate), on: () => {} });
	const tool = tools.find((candidate) => candidate.name === 'proposal_deliberation_execute');
	const ctx = { model: { provider: 'anthropic', id: 'unused' }, sessionManager: { getSessionId: () => 'create-initial-session' }, modelRegistry: { getApiKeyAndHeaders: async () => ({ ok: true, apiKey: 'unused', headers: {}, env: {} }) } };
	return {
		projectRoot,
		execute: async (params) => (await tool.execute('create-initial', params, undefined, undefined, ctx)).details,
		async dispose() { await rm(projectRoot, { recursive: true, force: true }); },
	};
}

test('CREATE_INITIAL_REVISION is reachable via the registered tool and produces a managed r01 when no managed proposal exists, independent of the scientific-workflow flag', async () => {
	const run = await fixture();
	try {
		const result = await run.execute({ operation: 'CREATE_INITIAL_REVISION', instruction: 'A tutor that catches unjustified inference steps in a proof draft.' });
		assert.equal(result.status, 'created', JSON.stringify(result));
		assert.match(result.targetFilename, /^research-concept-[a-z0-9-]+-r01\.md$/);
		assert.equal(result.targetRevision, 'r01');
		assert.equal(result.mutations, 1);
		const written = await readFile(path.join(run.projectRoot, 'proposals', result.targetFilename), 'utf8');
		assert.ok(written.startsWith(MARKER));
		assert.match(written, /A tutor that catches unjustified inference steps in a proof draft\./);
	} finally {
		await run.dispose();
	}
});

// ---------------------------------------------------------------------------
// Re-audit cleanup (issue #2): CREATE_INITIAL_REVISION must write the same derived-state and
// receipt sidecars ordinary materialization writes, so `readCanonicalManagedRevisionInventory`
// (relied on by scientific-workflow admission) treats the fresh r01 as CONSISTENT, not
// `inconsistent` due to `MANAGED_STATE_MISSING`.
// ---------------------------------------------------------------------------

test('CREATE_INITIAL_REVISION writes derived-state and receipt sidecars in the same layout as ordinary materialization, so a fresh r01 yields a CONSISTENT inventory', async () => {
	const run = await fixture();
	try {
		const result = await run.execute({ operation: 'CREATE_INITIAL_REVISION', instruction: 'A tutor that verifies each induction step explicitly.' });
		assert.equal(result.status, 'created', JSON.stringify(result));

		const stateBytes = await readFile(path.join(run.projectRoot, '.proposal-deliberation', 'state', `${result.targetFilename}.json`), 'utf8');
		const state = JSON.parse(stateBytes);
		assert.equal(state.manifest.status, 'COMMITTED');
		assert.equal(state.manifest.documentFilename, result.targetFilename);
		assert.equal(state.manifest.documentSha256, result.targetSha256);
		assert.equal(state.manifest.revision, 'r01');

		const receiptBytes = await readFile(path.join(run.projectRoot, '.proposal-deliberation', 'receipts', `${result.targetFilename}.json`), 'utf8');
		const receipt = JSON.parse(receiptBytes);
		assert.equal(receipt.targetFilename, result.targetFilename);
		assert.equal(receipt.targetRevision, 'r01');
		assert.equal(receipt.documentShaAfter, result.targetSha256);
		assert.equal(receipt.derivedStateStatus, 'COMMITTED');

		const inventory = await v2.readCanonicalManagedRevisionInventory(run.projectRoot);
		assert.equal(inventory.status, 'valid', JSON.stringify(inventory));
		assert.deepEqual(inventory.activeRevisions, [{ filename: result.targetFilename, revision: 'r01', documentSha256: result.targetSha256 }]);
	} finally {
		await run.dispose();
	}
});

test('CREATE_INITIAL_REVISION refuses and does not overwrite when a managed proposal already exists', async () => {
	const run = await fixture();
	try {
		await mkdir(path.join(run.projectRoot, 'proposals'), { recursive: true });
		const existingPath = path.join(run.projectRoot, 'proposals', 'research-concept-r01.md');
		await writeFile(existingPath, `${MARKER}# Existing base\n\nOriginal content.\n`);
		const result = await run.execute({ operation: 'CREATE_INITIAL_REVISION', instruction: 'A second unrelated idea that must not overwrite the first.' });
		assert.equal(result.status, 'blocked', JSON.stringify(result));
		assert.equal(result.blockers[0].code, 'MANAGED_PROPOSAL_ALREADY_EXISTS');
		assert.equal(result.mutations, 0);
		const unchanged = await readFile(existingPath, 'utf8');
		assert.equal(unchanged, `${MARKER}# Existing base\n\nOriginal content.\n`);
	} finally {
		await run.dispose();
	}
});

// ---------------------------------------------------------------------------
// Re-audit cleanup (issue #7): `hasManagedProposal` (the broad pre-check) is not slug-specific, but
// the atomic O_EXCL guard on the target `.md` IS slug-specific -- so two concurrent creates with two
// DIFFERENT ideas (and therefore two different target filenames) could previously both pass the
// pre-check and both succeed. The fix adds a project-wide, slug-independent atomic single-winner
// guard so at most one initial revision can ever be created, regardless of timing.
// ---------------------------------------------------------------------------

test('CREATE_INITIAL_REVISION: two concurrent creates with two different ideas have exactly one winner (single-winner, slug-independent)', async () => {
	const run = await fixture();
	try {
		const [first, second] = await Promise.all([
			run.execute({ operation: 'CREATE_INITIAL_REVISION', instruction: 'Formalizing entropy bounds for adaptive samplers.' }),
			run.execute({ operation: 'CREATE_INITIAL_REVISION', instruction: 'A new proof strategy for convergence under noise.' }),
		]);
		const results = [first, second];
		const created = results.filter((result) => result.status === 'created');
		const blocked = results.filter((result) => result.status === 'blocked');
		assert.equal(created.length, 1, JSON.stringify(results));
		assert.equal(blocked.length, 1, JSON.stringify(results));
		assert.equal(blocked[0].blockers[0].code, 'MANAGED_PROPOSAL_ALREADY_EXISTS');

		const proposalsAfter = await readdir(path.join(run.projectRoot, 'proposals'));
		assert.deepEqual(proposalsAfter, [created[0].targetFilename]);
	} finally {
		await run.dispose();
	}
});

test('CREATE_INITIAL_REVISION is never auto-triggered: an unrelated CHAT_DELIBERATION turn on an empty project does not create a managed proposal', async () => {
	const run = await fixture();
	try {
		const result = await run.execute({ operation: 'CHAT_DELIBERATION', instruction: 'Solo quiero conversar, sin crear nada todavia.' });
		assert.notEqual(result.status, 'created');
		const proposalsAfter = await (await import('node:fs/promises')).readdir(path.join(run.projectRoot, 'proposals'));
		assert.deepEqual(proposalsAfter, []);
	} finally {
		await run.dispose();
	}
});
