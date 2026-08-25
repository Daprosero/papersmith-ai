// Base reconciliation: moving a newer revision aside to resume from an older one.
//
// The move itself is the agent's, not the engine's — SKILL.md is explicit that no operation
// moves, backs up or deletes a proposal. That is exactly why it was never covered: nothing
// tests the agent's discipline. What CAN be pinned is the net that catches a botched move,
// and the fact that STATUS is not that net.
//
// The failure mode these tests exist for: moving the .md and forgetting its two sidecars.
// STATUS still answers ok with the new latest, as if the reconciliation were clean. Only the
// consistency audit names the damage. SKILL.md therefore requires auditing after the move,
// and the audit must keep deserving that trust.
import assert from 'node:assert/strict';
import { cp, mkdir, mkdtemp, readFile, rename, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const workspace = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/proposal-workspace.ts'));
const v2 = await jiti.import(path.resolve('.claude/skills/_core/deliberation/engine/exports.ts'));

const sha = (buffer) => createHash('sha256').update(buffer).digest('hex');

/** A lineage of r01..r0N, each with the committed sidecars a published revision carries. */
async function lineage(count) {
	const root = await mkdtemp(path.join(tmpdir(), 'pp-reconciliation-'));
	await mkdir(path.join(root, 'proposals'), { recursive: true });
	const tool = workspace.createProposalWorkspaceTool(root);
	for (let n = 1; n <= count; n++) {
		const slug = `r${String(n).padStart(2, '0')}`;
		await tool.execute('seed', { action: 'write', resource: 'proposal', slug, content: `# Propuesta\n\n## Método\n\nCuerpo de la versión ${n}.\n` });
		const state = await v2.loadDocumentState(root, `research-concept-${slug}.md`);
		await v2.saveDerivedState(root, state, 'VALID');
		// Every revision above r01 is a published successor, so it carries a receipt.
		// Without one the audit reports MISSING_RECEIPT and the fixture stops resembling a real lineage.
		if (n > 1) {
			await v2.saveRevisionReceipt(root, `research-concept-${slug}.md`, {
				sourceRevision: `r${String(n - 1).padStart(2, '0')}`,
				targetRevision: slug,
				sourceFilename: `research-concept-r${String(n - 1).padStart(2, '0')}.md`,
				targetFilename: `research-concept-${slug}.md`,
				intent: 'MODIFY',
				operation: 'CREATE_SUCCESSOR',
				documentShaAfter: state.documentSha256,
			});
		}
	}
	return root;
}

const paths = (root, name) => ({
	md: path.join(root, 'proposals', name),
	state: v2.derivedStatePath(root, name),
	receipt: v2.receiptPath(root, name),
});

/** Moves a revision aside. `withSidecars: false` is the mistake the audit must catch. */
async function moveAside(root, name, { withSidecars }) {
	const destination = path.join(root, 'backup/proposals/2026-01-01T00-00-00Z');
	await mkdir(destination, { recursive: true });
	const from = paths(root, name);
	await rename(from.md, path.join(destination, name));
	if (!withSidecars) return destination;
	await rename(from.state, path.join(destination, `state-${name}.json`)).catch(() => {});
	await rename(from.receipt, path.join(destination, `receipt-${name}.json`)).catch(() => {});
	return destination;
}

test('the lineage resolves its latest and still knows every revision below it', async () => {
	const root = await lineage(3);
	const resolution = await v2.resolveLatestManagedRevision(root);
	assert.equal(resolution.status, 'active', JSON.stringify(resolution));
	assert.equal(resolution.latest.filename, 'research-concept-r03.md');
	assert.deepEqual(
		resolution.candidates.map((candidate) => candidate.filename).sort(),
		['research-concept-r01.md', 'research-concept-r02.md', 'research-concept-r03.md'],
		'an older revision is still a known candidate, which is what makes reconciliation possible',
	);
});

test('a complete move makes the older revision the latest and leaves the audit clean', async () => {
	const root = await lineage(3);
	await moveAside(root, 'research-concept-r03.md', { withSidecars: true });

	const latest = await v2.resolveLatestManagedRevision(root);
	assert.equal(latest.latest.filename, 'research-concept-r02.md', 'the revision below must become the latest');

	const audit = await v2.runConsistencyAudit({ projectRoot: root });
	assert.equal(audit.status, 'PASS', JSON.stringify(audit.failures));
});

test('forgetting the sidecars is invisible to the latest-revision resolution — it answers as if nothing were wrong', async () => {
	const root = await lineage(3);
	await moveAside(root, 'research-concept-r03.md', { withSidecars: false });

	const latest = await v2.resolveLatestManagedRevision(root);
	assert.equal(latest.latest.filename, 'research-concept-r02.md', 'this is exactly why STATUS cannot be the verification step');
});

test('the audit is the net: an orphaned sidecar is named, not shrugged off', async () => {
	const root = await lineage(3);
	await moveAside(root, 'research-concept-r03.md', { withSidecars: false });

	const audit = await v2.runConsistencyAudit({ projectRoot: root });
	assert.equal(audit.status, 'FAIL', 'a revision moved without its sidecars must not audit clean');
	assert.ok(
		audit.failures.some((failure) => failure.startsWith('ORPHAN_STATE')),
		`the orphaned manifest must be named: ${JSON.stringify(audit.failures)}`,
	);
});

test('restoring returns the revision and its sidecars byte-identical', async () => {
	const root = await lineage(3);
	const name = 'research-concept-r03.md';
	const before = paths(root, name);
	const original = {
		md: await readFile(before.md),
		state: await readFile(before.state),
		receipt: await readFile(before.receipt),
	};

	const destination = await moveAside(root, name, { withSidecars: true });
	// All three travel back, exactly as all three travelled out.
	await rename(path.join(destination, name), before.md);
	await rename(path.join(destination, `state-${name}.json`), before.state);
	await rename(path.join(destination, `receipt-${name}.json`), before.receipt);

	assert.equal(sha(await readFile(before.md)), sha(original.md), 'the revision must come back byte-identical');
	assert.equal(sha(await readFile(before.state)), sha(original.state), 'its manifest must come back byte-identical');
	assert.equal(sha(await readFile(before.receipt)), sha(original.receipt), 'its receipt must come back byte-identical');

	const latest = await v2.resolveLatestManagedRevision(root);
	assert.equal(latest.latest.filename, name, 'the restored revision is the latest again');
	const audit = await v2.runConsistencyAudit({ projectRoot: root });
	assert.equal(audit.status, 'PASS', JSON.stringify(audit.failures));
});
