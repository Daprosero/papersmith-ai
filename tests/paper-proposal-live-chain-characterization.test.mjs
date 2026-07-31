// Characterization tests (Phase 0 of paper-proposal-tutor-repair), updated for
// Phase 1's byte-safe splice + composite-engine wiring.
//
// These tests originally locked in the pre-repair observable behavior of the
// live, CLI-reachable successor-generation chain (including its $$-corruption
// and append-only bugs) so Phase 1 could be verified against a known
// baseline. Phase 1 changed that behavior (lifecycle-service.ts's applyChanges
// is now a byte-safe splice, and scientific-workflow-runtime.ts's
// materializeLifecycleV1 now composes successors through
// successor-composite-engine.ts when a locus resolves), so the second test
// below now asserts the CORRECTED behavior instead of the original bug. The
// first test (SuccessorEditPlanner, the legacy non-lifecycle-v1 route) still
// documents its append-only baseline: that route is out of scope for Phase 1
// wiring changes (see the paper-proposal-tutor-repair apply-progress for the
// scoping rationale) and remains unmodified.
//
// Chain under test: cli.mjs's registered `paper_proposal_execute` tool calls
// `ScientificWorkflowRuntime.execute(...)` for SCIENTIFIC_WORKFLOW operations;
// when a lifecycle-v1 workspace is configured, materialization flows through
// `ScientificWorkflowRuntime.materializeLifecycleV1` -> `LifecycleMaterializationPlanner`
// -> `LifecycleService.createFromBase/createSuccessor` (lifecycle-service.ts).
// The legacy (non-lifecycle-v1) materialization path flows through
// `MaterializationPlanner` -> `SuccessorEditPlanner` (successor-edit-planner.ts).
// No real proposal `.md` file is ever created or modified by these tests --
// every fixture uses a temp directory and in-memory state.
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

function event(sequence, eventId, type, threadId, actor, payload, causalEventIds, evidence = []) {
	return { schemaVersion: 1, eventId, sequence, occurredAt: `2026-01-01T00:${String(sequence).padStart(2, '0')}:00.000Z`, actor: { kind: actor }, type, threadId, causalEventIds, payload, evidence, privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } };
}

test('SuccessorEditPlanner only appends a decisions block after the document -- it never applies an approved edit at its locus (baseline bug, V2)', async () => {
	const base = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Introduction\n\nOriginal introduction text.\n\n# Method\n\nOriginal method text.\n'));
	const expectedRevision = { filename: base.filename, revision: base.revision, documentSha256: base.documentSha256 };
	const acceptedDecisions = [
		{ claimId: 'claim-a', decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: 'digest-a', summary: 'Replace the method section with a formal derivation.' },
	];
	const plan = new v2.SuccessorEditPlanner().plan({ base, expectedRevision, acceptedDecisions });
	assert.equal(plan.kind, 'CREATE_SUCCESSOR');
	assert.equal(plan.patches.length, 1);
	const [patch] = plan.patches;
	assert.equal(patch.plan.intent, 'INSERT');
	assert.deepEqual(patch.plan.actions.map((action) => action.kind), ['insert']);
	assert.equal(patch.plan.actions[0].position, 'after');
	assert.match(patch.plan.actions[0].content, /^\n\n## Accepted scientific decisions/);
	// The approved decision text is only ever appended after the anchor entry; the
	// existing "Original method text." span it was supposed to revise is untouched
	// by any replace/delete action in the plan -- proving the current planner
	// never applies an approved edit in place (V2 violation, baseline behavior).
	assert.doesNotMatch(patch.plan.actions[0].content, /Original method text/);
	assert.equal(patch.plan.actions[0].content.includes('Replace the method section with a formal derivation.'), true);
});

test('lifecycle-v1 materialization preserves $$ math delimiters and applies the decision at its resolved locus (Phase 1 repair, V1 + V2 + V6)', async () => {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-live-chain-'));
	try {
		const baseContent = '# Energy identity\n\nBaseline informal statement without display math.\n';
		const lifecycle = new v2.LifecycleService(projectRoot);
		const registered = await lifecycle.registerBaseDocument({ workspaceId: 'workspace-1', requestId: 'register-base', baseDocumentId: 'base-1', content: baseContent });
		assert.equal(registered.outcome, 'COMMITTED');

		const summary = 'The governing identity is $$E=mc^2$$ and it subsumes the earlier approximation.';
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

		// Exercises the exact call contract cli.mjs's registered paper_proposal_execute
		// tool uses for SCIENTIFIC_WORKFLOW operations (getScientificWorkflowRuntime().execute(...)).
		const runtime = new v2.ScientificWorkflowRuntime(projectRoot, {}, { lifecycleV1WorkspaceId: 'workspace-1' });
		const result = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization for the accepted energy identity', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: ['decision-a'] });
		assert.equal(result.status, 'materialized', JSON.stringify(result));

		const inventory = await lifecycle.rebuildLifecycleInventory('workspace-1');
		const active = inventory.revisions.find((revision) => revision.revisionId === result.materialization.targetRevision);
		assert.ok(active, 'materialized revision must exist in the lifecycle inventory');

		// Phase 1 repair (V1/V6): the byte-safe splice in lifecycle-service.ts's
		// applyChanges() never interprets "$$" as a String.replace special
		// replacement-pattern escape, so approved display-math delimiters survive
		// byte-for-byte.
		assert.equal(active.content.includes('$$E=mc^2$$'), true, 'display-math delimiters must survive byte-for-byte');
		assert.equal(active.content.includes('$E=mc^2$'.replace('$$', '$')) && !active.content.includes('$$E=mc^2$$'), false, 'the corrupted single-dollar form must never appear');

		// Phase 1 repair (V2): the sole managed section resolves as the decision's
		// locus via resolveSuccessorTarget/composeSuccessorBlockCandidate, so the
		// decision is composed there (not via a naive whole-document string
		// append). The original base content is still the untouched prefix here
		// because, with exactly one section, that section's span covers the
		// entire document -- the composite engine's untouched-byte invariant
		// still holds, it is simply vacuous outside the single resolved span.
		assert.equal(active.content.startsWith(baseContent), true, 'the base content remains an untouched prefix up to the resolved locus');
		assert.equal(active.content.endsWith(`- ${summary}\n`), false, 'must not regress to the append-only "## Accepted scientific decisions" tail shape');
		assert.match(active.content, /> Accepted revision: /, 'the decision is composed via the byte-preserving locus-aware path, not a blind tail append');
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

test('scientific context stays bounded to a single latest revision and a fixed maxDocumentFragments ceiling per turn (regression guard -- Preserved requirement)', async () => {
	const loadCalls = [];
	const documentFragments = {
		async load({ revision, entryIds, maxFragments, maxBytes }) {
			loadCalls.push({ revision, entryIds, maxFragments, maxBytes });
			return { revision, fragments: entryIds.map((entryId) => ({ entryId, type: 'paragraph', text: `${entryId} body.`, textSha256: v2.sha256(`${entryId} body.`), headingPath: ['Section', entryId] })) };
		},
	};
	const activeThread = { threadId: 'thread-a', version: 1, status: 'ACTIVE_SCIENTIFIC_PROJECT', title: 'Question', summary: 'Public summary.', createdEventId: 'created-a', headEventId: 'created-a' };
	const entryIds = ['entry-1', 'entry-2', 'entry-3', 'entry-4', 'entry-5', 'entry-6'];
	const evidence = entryIds.map((entryId) => ({ kind: 'document-fragment', id: entryId }));
	const events = [event(1, 'created-a', 'THREAD_CREATED', 'thread-a', 'USER', { title: 'Question', summary: 'Public summary.', activeThreadId: 'thread-a' }, [], evidence)];
	const builder = new v2.ScientificContextBuilder({ read: async () => ({ threads: [activeThread], relations: [], events }) }, { documentFragments });

	const revisionOne = { filename: 'research-concept-r01.md', revision: 'r01', documentSha256: '1'.repeat(64) };
	const contextOne = await builder.build({ activeThread, requestedDirectRelationIds: [], act: 'CONSTRUCT_IDEA', verifiedRevision: revisionOne, actEvidence: evidence, documentEntryIds: entryIds });
	assert.deepEqual(contextOne.limits, { maxRelatedThreads: 4, maxEvidence: 12, maxDocumentFragments: 4, maxBytes: 16_000 });
	assert.equal(contextOne.documentFragments.length, 4, 'per-turn document context is bounded to maxDocumentFragments even when more evidence is relevant');
	assert.deepEqual(contextOne.documentFragments.map((fragment) => fragment.entryId), ['entry-1', 'entry-2', 'entry-3', 'entry-4']);

	const revisionTwo = { filename: 'research-concept-r02.md', revision: 'r02', documentSha256: '2'.repeat(64) };
	const contextTwo = await builder.build({ activeThread, requestedDirectRelationIds: [], act: 'CONSTRUCT_IDEA', verifiedRevision: revisionTwo, actEvidence: evidence, documentEntryIds: entryIds });

	assert.equal(loadCalls.length, 2, 'one bounded load per turn -- turns are never batched together');
	assert.deepEqual(loadCalls.map((call) => call.revision), [revisionOne, revisionTwo], 'each turn loads only its own single latest revision, never a list of historical revisions');
	assert.deepEqual(loadCalls.map((call) => call.maxFragments), [4, 4]);
	assert.equal(contextTwo.documentFragments.length, 4);
	assert.equal(contextTwo.documentFragments[0].entryId, 'entry-1');
	assert.deepEqual(contextOne.documentFragments[0].revision, revisionOne);
	assert.deepEqual(contextTwo.documentFragments[0].revision, revisionTwo);
});
