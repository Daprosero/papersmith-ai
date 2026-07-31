// Phase 1 (paper-proposal-tutor-repair): byte-safe splice + composite-engine wiring.
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
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(path.join(root, '.claude/skills/paper-proposal/engine/exports.ts'));

const digest = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');

function event(sequence, eventId, type, threadId, actor, payload, causalEventIds) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:${String(sequence).padStart(2, '0')}:00.000Z`, actor: { kind: actor }, type, threadId, causalEventIds, payload, evidence: [], privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}

async function withTempRoot(run) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-byte-preservation-'));
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

async function materializeSingleDecision({ baseContent, summary, workspaceId = 'workspace-1' }) {
	return withTempRoot(async (projectRoot) => {
		const lifecycle = new v2.LifecycleService(projectRoot);
		const registered = await lifecycle.registerBaseDocument({ workspaceId, requestId: 'register-base', baseDocumentId: 'base-1', content: baseContent });
		assert.equal(registered.outcome, 'COMMITTED');
		const synthesisDigest = digest({ synthesisId: 'synthesis-a', threadId: 'thread-a', summary });
		const store = new v2.ScientificStateStore(projectRoot);
		const events = [
			event(1, 'created-a', 'THREAD_CREATED', 'thread-a', 'USER', { title: 'Energy identity', summary: 'Public summary a.', activeThreadId: 'thread-a' }, []),
			event(2, 'tutor-a', 'TUTOR_ASSESSED', 'thread-a', 'TUTOR', { status: 'DRAFT', summary, synthesisId: 'synthesis-a', synthesisDigest }, ['created-a']),
			event(3, 'review-a', 'CONCEPTUAL_REVIEW_RECORDED', 'thread-a', 'CONCEPTUAL_REVIEWER', { status: 'PASS', synthesisId: 'synthesis-a', synthesisDigest }, ['tutor-a']),
			event(4, 'accepted-a', 'DECISION_ACCEPTED', 'thread-a', 'USER', { decisionId: 'decision-a', synthesisId: 'synthesis-a', synthesisDigest, status: 'ACCEPTED_UNMATERIALIZED' }, ['review-a']),
		];
		const threads = [{ threadId: 'thread-a', version: 1, status: 'ACCEPTED_UNMATERIALIZED', title: 'Energy identity', summary: 'Public summary a.', createdEventId: 'created-a', headEventId: 'accepted-a', relationIds: [], decisionIds: ['decision-a'] }];
		const decisions = [{ decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: synthesisDigest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: ['tutor-a', 'review-a'] }];
		await store.commitTransition({ events, snapshot: { schemaVersion: 1, activeThreadId: 'thread-a', threads, relations: [], decisions } });

		const runtime = new v2.ScientificWorkflowRuntime(projectRoot, {}, { lifecycleV1WorkspaceId: workspaceId });
		const result = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for the accepted energy identity', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-a'] });
		assert.equal(result.status, 'materialized', JSON.stringify(result));
		const inventory = await lifecycle.rebuildLifecycleInventory(workspaceId);
		const active = inventory.revisions.find((revision) => revision.revisionId === result.materialization.targetRevision);
		assert.ok(active, 'materialized revision must exist in the lifecycle inventory');
		return { active, baseContent };
	});
}

test('live chain preserves $$ math delimiters byte-for-byte when applying an approved decision (V1, V6)', async () => {
	const baseContent = '# Energy identity\n\nBaseline informal statement without display math.\n';
	const summary = 'The energy identity should state $$E=mc^2$$ explicitly.';
	const { active } = await materializeSingleDecision({ baseContent, summary });
	assert.equal(active.content.includes('$$E=mc^2$$'), true, '$$ delimiters must never collapse to a single $');
	assert.equal(active.content.includes('$E=mc^2$ '.trim()) && !active.content.includes('$$E=mc^2$$'), false);
});

test('live chain applies the approved decision at its resolved locus, leaving an unrelated later section byte-identical (V2, V3, V4)', async () => {
	const baseContent = '# Energy Identity\n\nBaseline informal statement without display math.\n\n# Momentum Relation\n\nBaseline momentum statement untouched.\n';
	const summary = 'The energy identity should state $$E=mc^2$$ explicitly.';
	const { active } = await materializeSingleDecision({ baseContent, summary });

	// The successor must NOT be merely "old body + appended decisions summary" --
	// the unrelated "Momentum Relation" section must remain byte-identical, in
	// its original position relative to its own untouched content.
	const momentumSection = '# Momentum Relation\n\nBaseline momentum statement untouched.\n';
	assert.equal(active.content.includes(momentumSection), true, 'the untouched section survives byte-for-byte');

	// The new content must land at/adjacent to the "Energy Identity" locus, i.e.
	// strictly BEFORE the untouched "Momentum Relation" heading -- not merely
	// appended after the whole document (which is what the pre-repair append-only
	// route always did, regardless of which section a decision concerned).
	const momentumIndex = active.content.indexOf('# Momentum Relation');
	const decisionIndex = active.content.indexOf('E=mc^2');
	assert.ok(decisionIndex >= 0 && decisionIndex < momentumIndex, 'the approved decision is applied at the Energy Identity locus, before the untouched Momentum Relation section');

	// No longer a whole-document string-append: the corrected successor must NOT
	// simply equal `baseContent + summary-list-appendix` (the Phase 0 baseline shape).
	assert.equal(active.content.endsWith(`- ${summary}\n`), false, 'must not regress to the append-only "## Accepted scientific decisions" tail shape when a locus resolves');

	// Adjacent whitespace/newline formatting of the untouched region is unchanged.
	assert.equal(active.content.slice(active.content.indexOf('# Momentum Relation')), momentumSection);
});
