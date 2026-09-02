import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
// Phase 1 (proposal-deliberation-tutor-repair): byte-safe splice + composite-engine wiring.
//
// These tests assert the CORRECTED behavior of the live, CLI-reachable
// successor-generation chain -- replacing the Phase 0 characterization
// baseline (which documented the $$ corruption / append-only bugs). Every
// fixture uses in-memory DocumentState builders or a temp directory; no real
// proposal `.md` file is ever created or modified.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const piRoot = ENGINE_MODULE_ROOT;
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(path.join(root, '.claude/skills/_core/deliberation/engine/exports.ts'));

const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');


async function withTempRoot(run) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'proposal-deliberation-byte-preservation-'));
	try {
		return await run(projectRoot);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
}

// --- Unit level: LifecycleService.applyChanges (V1) -----------------------------------

test('LifecycleService applies an approved change without interpreting "$$" as a String.replace pattern', async () => {
	await withTempRoot(async (projectRoot) => {
		const lifecycle = new v2.LifecycleService(projectRoot);
		const baseContent = '# Energy identity\n\nInformal statement.\n';
		const base = await lifecycle.registerBaseDocument({ workspaceId: 'workspace-1', requestId: 'register-base', baseDocumentId: 'base-1', content: baseContent });
		assert.equal(base.outcome, 'COMMITTED');
		const revision = await lifecycle.createFromBase({
			workspaceId: 'workspace-1', requestId: 'create-1', operation: 'CREATE_FROM_BASE', revisionId: 'revision-1',
			source: { sourceKind: 'BASE_DOCUMENT', sourceId: 'base-1', sourceContentHash: base.base.contentHash, baseDocumentId: 'base-1' },
			// `to` intentionally contains "$$" -- a String.replace-based implementation
			// would silently collapse this to a single "$" because "$$" is a special
			// replacement-pattern escape in String.prototype.replace.
			approvedChanges: [{ from: 'Informal statement.', to: 'The identity is $$E=mc^2$$ exactly.' }],
		});
		assert.equal(revision.outcome, 'COMMITTED');
		assert.equal(revision.revision.content, '# Energy identity\n\nThe identity is $$E=mc^2$$ exactly.\n');
		assert.equal(revision.revision.content.includes('$$E=mc^2$$'), true, '$$ delimiters must survive byte-for-byte');
		assert.equal(revision.revision.content.includes('$E=mc^2$'.replace('$$', '$')), true);
	});
});

test('LifecycleService only substitutes the located "from" occurrence; an identical later occurrence stays untouched', async () => {
	await withTempRoot(async (projectRoot) => {
		const lifecycle = new v2.LifecycleService(projectRoot);
		// "Shared line." appears twice, byte-for-byte identical, in two different sections.
		const baseContent = '# Section A\n\nShared line.\n\n# Section B\n\nShared line.\n';
		const base = await lifecycle.registerBaseDocument({ workspaceId: 'workspace-1', requestId: 'register-base', baseDocumentId: 'base-1', content: baseContent });
		assert.equal(base.outcome, 'COMMITTED');
		const revision = await lifecycle.createFromBase({
			workspaceId: 'workspace-1', requestId: 'create-1', operation: 'CREATE_FROM_BASE', revisionId: 'revision-1',
			source: { sourceKind: 'BASE_DOCUMENT', sourceId: 'base-1', sourceContentHash: base.base.contentHash, baseDocumentId: 'base-1' },
			approvedChanges: [{ from: 'Shared line.', to: 'Revised line.' }],
		});
		assert.equal(revision.outcome, 'COMMITTED');
		assert.equal(revision.revision.content, '# Section A\n\nRevised line.\n\n# Section B\n\nShared line.\n', 'only the first located occurrence changes; the later identical occurrence is untouched');
		assert.equal((revision.revision.content.match(/Shared line\./g) ?? []).length, 1, 'the untouched occurrence survives byte-for-byte');
	});
});

// --- Live CLI-reachable chain: ScientificWorkflowRuntime -> materializeLifecycleV1 -----



