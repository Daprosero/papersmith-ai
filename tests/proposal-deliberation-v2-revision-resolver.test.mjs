import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const repositoryRoot = path.resolve('.');
const piRoot = ENGINE_MODULE_ROOT;
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, {
	alias: {
		'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
		'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
		'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
		typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
	},
});
const v2 = await jiti.import(path.join(repositoryRoot, '.claude/skills/_core/deliberation/engine/exports.ts'));

const marker = '<!-- proposal-workspace:artifact:v1 -->\n';

async function writeJson(filename, value) {
	await mkdir(path.dirname(filename), { recursive: true });
	await writeFile(filename, JSON.stringify(value));
}

/** Writes one managed, marker-owned, COMMITTED revision so `readCanonicalManagedRevisionInventory`'s
 * heavier validation (state identity + COMMITTED status) accepts it, independent of any lineage chain. */
async function writeCommittedRevision(root, filename, body) {
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	await writeFile(path.join(root, 'proposals', filename), marker + body);
	const state = await v2.loadDocumentState(root, filename);
	const stored = JSON.parse(await readFile(v2.derivedStatePath(root, filename), 'utf8'));
	stored.manifest.status = 'COMMITTED';
	await writeJson(v2.derivedStatePath(root, filename), stored);
	return state;
}

async function tempProjectRoot() {
	return mkdtemp(path.join(os.tmpdir(), 'proposal-deliberation-revision-resolver-'));
}

test('resolveLatestManagedRevision picks the single highest revisionNumber when unambiguous', async () => {
	const root = await tempProjectRoot();
	await writeCommittedRevision(root, 'research-concept-r01.md', '# Base\n\nBase text.\n');
	await writeCommittedRevision(root, 'research-concept-r02.md', '# Revision\n\nRevised text.\n');
	const resolution = await v2.resolveLatestManagedRevision(root);
	assert.equal(resolution.status, 'active');
	assert.equal(resolution.latest.filename, 'research-concept-r02.md');
	assert.equal(resolution.latest.revisionNumber, 2);
});

test('resolveLatestManagedRevision reports empty for a proposals directory with no managed files', async () => {
	const root = await tempProjectRoot();
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	const resolution = await v2.resolveLatestManagedRevision(root);
	assert.deepEqual(resolution, { status: 'empty' });
});

test('resolveLatestManagedRevision surfaces MULTIPLE_ACTIVE_REVISIONS instead of silently picking one when two lineages tie at the highest revisionNumber', async () => {
	const root = await tempProjectRoot();
	await writeCommittedRevision(root, 'research-concept-r01.md', '# Concept A\n\nFirst idea.\n');
	await writeCommittedRevision(root, 'research-concept-idea-b-r01.md', '# Concept B\n\nSecond idea.\n');
	const resolution = await v2.resolveLatestManagedRevision(root);
	assert.equal(resolution.status, 'multiple');
	assert.equal(resolution.code, 'MULTIPLE_ACTIVE_REVISIONS');
	assert.deepEqual(resolution.candidates.map((c) => c.filename).sort(), ['research-concept-idea-b-r01.md', 'research-concept-r01.md']);
});

test('latestManagedFilename agrees with resolveLatestManagedRevision in an unambiguous case (shared tie-break, one resolver)', async () => {
	const root = await tempProjectRoot();
	await writeCommittedRevision(root, 'research-concept-r01.md', '# Base\n\nBase text.\n');
	await writeCommittedRevision(root, 'research-concept-r02.md', '# Revision\n\nRevised text.\n');
	const resolution = await v2.resolveLatestManagedRevision(root);
	assert.equal(await v2.latestManagedFilename(root), resolution.latest.filename);
});

test('readCanonicalManagedRevisionInventory surfaces every tied candidate as an active revision instead of suppressing to one (I4)', async () => {
	const root = await tempProjectRoot();
	await writeCommittedRevision(root, 'research-concept-r01.md', '# Concept A\n\nFirst idea.\n');
	await writeCommittedRevision(root, 'research-concept-idea-b-r01.md', '# Concept B\n\nSecond idea.\n');
	const inventory = await v2.readCanonicalManagedRevisionInventory(root);
	assert.equal(inventory.status, 'valid');
	assert.equal(inventory.activeRevisions.length, 2, 'both tied candidates surface, not just one');
	assert.deepEqual(inventory.activeRevisions.map((r) => r.filename).sort(), ['research-concept-idea-b-r01.md', 'research-concept-r01.md']);
});


test('ProposalDeliberationOrchestrator.execute() surfaces MULTIPLE_ACTIVE_REVISIONS instead of NO_MANAGED_PROPOSAL when the managed proposal base is ambiguous', async () => {
	const root = await tempProjectRoot();
	await writeCommittedRevision(root, 'research-concept-r01.md', '# Concept A\n\nFirst idea.\n');
	await writeCommittedRevision(root, 'research-concept-idea-b-r01.md', '# Concept B\n\nSecond idea.\n');
	const adapter = new v2.ProposalWorkspaceAdapter(root, { execute: async () => ({ decision: 'allowed' }) }, { execute: async () => ({}) });
	const orchestrator = new v2.ProposalDeliberationOrchestrator(root, adapter);
	const result = await orchestrator.execute({ instruction: 'delibera sobre la definición de bolsas.' });
	assert.equal(result.status, 'blocked');
	assert.equal(result.reason, 'MULTIPLE_ACTIVE_REVISIONS');
	assert.deepEqual(result.candidates.sort(), ['research-concept-idea-b-r01.md', 'research-concept-r01.md']);
});

test('draft-materialization default managed-document inventory agrees with the unified resolver (no more mtime-based tie-break)', async () => {
	const root = await tempProjectRoot();
	await writeCommittedRevision(root, 'research-concept-r01.md', '# Base\n\nBase text.\n');
	await writeCommittedRevision(root, 'research-concept-r02.md', '# Revision\n\nRevised text.\n');
	const guard = { execute: async () => ({ decision: 'allowed', authorization: 'granted' }) };
	const service = new v2.DraftMaterializationService(root, guard, { draftDirectory: 'working-drafts' });
	const result = await service.execute({
		conversationId: 'chat-resolver-default',
		materializationPayload: { source: 'CHAT_DELIBERATION', conversationId: 'chat-resolver-default', content: 'Bounded content.' },
		request: { operation: 'INITIAL_CREATE', authorized: false },
	});
	assert.equal(result.status, 'draft_path_proposed', JSON.stringify(result));
	assert.equal(result.primaryDocumentPath, 'proposals/research-concept-r02.md');
});
