// paper-proposal-tutor-repair (V2-scientific structured edits): closes the
// V2-PARTIAL gap. The scientific materialization route previously reduced
// every accepted decision to a `summary` string and only ever annotated
// ("> Accepted revision: <summary>") instead of applying a real structured
// edit. This suite proves the tutor's own already-emitted structured signal
// (`proposedAlternative` + `affectedEntryIds`) is now lifted into a genuine
// `EditAction`, frozen into the acceptance digest, persisted on the immutable
// TUTOR_ASSESSED event, and applied byte-preservingly at materialization --
// including MULTIPLE decisions spliced into ONE successor version -- while
// every additive-optional fallback (no proposedEdit, drift, oversized) still
// safely annotates exactly as before.
//
// No real proposal `.md` file is ever created or modified by this suite;
// every fixture uses a temp directory + the lifecycle-v1 in-memory-style
// scientific state store, or hand-built DocumentState/claim fixtures.
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

// --- Section A: candidate() lifts the tutor's structured signal -----------------------

const tutorAssessment = (overrides = {}) => ({
	decision: 'ACCEPT_WITH_REVISIONS',
	summary: 'Bounded accepted synthesis.',
	mathematicalIssues: [], notationIssues: [], assumptionIssues: [],
	requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW',
	affectedEntryIds: [],
	...overrides,
});
const reviewerAssessment = (overrides = {}) => ({
	decision: 'APPROVE', scientificCoherence: 'Coherent.', scopeCompliance: 'Within scope.',
	unsupportedClaims: [], referenceRisks: [], notationRisks: [], requiredChanges: [], unresolvedQuestions: [], riskLevel: 'LOW',
	...overrides,
});

async function serviceFixture({ tutorResults, reviewerResults = [reviewerAssessment()], documentFragments = [] } = {}) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-structured-'));
	const store = new v2.ScientificStateStore(projectRoot);
	const initialEvent = event(1, 'thread-created', 'THREAD_CREATED', 'thread-1', 'USER', { title: 'Bounded question', summary: 'Public thread summary.', activeThreadId: 'thread-1' }, []);
	const thread = { threadId: 'thread-1', version: 1, status: 'OPEN', title: 'Bounded question', summary: 'Public thread summary.', createdEventId: 'thread-created', headEventId: 'thread-created', relationIds: [], decisionIds: [] };
	await store.commitTransition({ events: [initialEvent], snapshot: { schemaVersion: 1, activeThreadId: 'thread-1', threads: [thread], relations: [], decisions: [] } });
	let id = 0;
	const service = new v2.ScientificWorkflowService({
		store,
		contextBuilder: { build: async (input) => ({ schemaVersion: 1, act: input.act, activeThread: { threadId: input.activeThread.threadId, status: input.activeThread.status, title: input.activeThread.title, summary: input.activeThread.summary }, relatedThreads: [], evidence: [], documentFragments, limits: { maxRelatedThreads: 4, maxEvidence: 12, maxDocumentFragments: 4, maxBytes: 64_000 }, byteCount: 128, privacy: { contentClass: 'PUBLIC_SUMMARY_ONLY', redactionVersion: 1 } }) },
		tutor: { assess: async () => tutorResults.shift() },
		reviewer: { review: async () => reviewerResults.shift() },
		newId: () => `event-${++id}`,
		now: () => new Date('2026-01-02T00:00:00.000Z'),
	});
	const input = { activeThread: thread, requestedDirectRelationIds: [], act: 'SYNTHESIZE', instruction: 'Synthesize this bounded scientific question.' };
	return { projectRoot, store, service, input, thread };
}

test('candidate() lifts a single-locus ACCEPT_WITH_REVISIONS proposedAlternative into a real EditAction, frozen into the digest and persisted on TUTOR_ASSESSED', async () => {
	const fragment = { entryId: 'paragraph:target-1', type: 'paragraph', text: 'Original claim text.', textSha256: 'a'.repeat(64), headingPath: [], revision: { filename: 'lifecycle-v1:x', revision: 'working', documentSha256: 'b'.repeat(64) } };
	const run = await serviceFixture({
		tutorResults: [tutorAssessment({ decision: 'ACCEPT_WITH_REVISIONS', affectedEntryIds: ['paragraph:target-1'], proposedAlternative: 'The corrected claim text.' })],
		documentFragments: [fragment],
	});
	const result = await run.service.synthesize(run.input);
	assert.equal(result.status, 'reviewed', JSON.stringify(result));
	assert.deepEqual(result.candidate.proposedEdit, { kind: 'replace', targetEntryId: 'paragraph:target-1', replacementText: 'The corrected claim text.' });

	// F3: proposedEdit is folded into the acceptance digest -- it must differ from
	// the summary-only digest that would have been computed without it.
	const summaryOnlyDigest = digest({ synthesisId: result.candidate.synthesisId, threadId: 'thread-1', summary: result.candidate.summary });
	assert.notEqual(result.candidate.digest, summaryOnlyDigest);

	// Persisted ONLY on the immutable TUTOR_ASSESSED event payload (no snapshot mutation).
	const state = await run.store.read();
	const tutorEvent = state.events.find((e) => e.type === 'TUTOR_ASSESSED');
	assert.deepEqual(tutorEvent.payload.proposedEdit, { kind: 'replace', targetEntryId: 'paragraph:target-1', replacementText: 'The corrected claim text.' });
	assert.equal(state.snapshot.decisions.length, 0, 'no decision recorded yet -- ScientificDecision snapshot shape is untouched by this synthesis alone');
});

test('candidate() stays summary-only (no proposedEdit) for ACCEPT, multi-entry, or empty/oversized alternatives -- regression guard', async () => {
	const fragments = [
		{ entryId: 'paragraph:a', type: 'paragraph', text: 'A.', textSha256: 'a'.repeat(64), headingPath: [], revision: { filename: 'x', revision: 'r', documentSha256: 'b'.repeat(64) } },
		{ entryId: 'paragraph:b', type: 'paragraph', text: 'B.', textSha256: 'a'.repeat(64), headingPath: [], revision: { filename: 'x', revision: 'r', documentSha256: 'b'.repeat(64) } },
	];
	// (1) decision === 'ACCEPT' (not in the accepted-with-edit set), even with a proposedAlternative + one affected entry.
	const acceptOnly = await serviceFixture({ tutorResults: [tutorAssessment({ decision: 'ACCEPT', affectedEntryIds: ['paragraph:a'], proposedAlternative: 'Should not be lifted.' })], documentFragments: fragments });
	const acceptResult = await acceptOnly.service.synthesize(acceptOnly.input);
	assert.equal(acceptResult.status, 'reviewed');
	assert.equal('proposedEdit' in acceptResult.candidate, false);

	// (2) multi-entry (bounded to single-locus).
	const multiEntry = await serviceFixture({ tutorResults: [tutorAssessment({ decision: 'PROPOSE_ALTERNATIVE', affectedEntryIds: ['paragraph:a', 'paragraph:b'], proposedAlternative: 'Ambiguous target.' })], documentFragments: fragments });
	const multiResult = await multiEntry.service.synthesize(multiEntry.input);
	assert.equal(multiResult.status, 'reviewed');
	assert.equal('proposedEdit' in multiResult.candidate, false);

	// (3) empty alternative.
	const empty = await serviceFixture({ tutorResults: [tutorAssessment({ decision: 'PROPOSE_ALTERNATIVE', affectedEntryIds: ['paragraph:a'], proposedAlternative: '   ' })], documentFragments: fragments });
	const emptyResult = await empty.service.synthesize(empty.input);
	assert.equal(emptyResult.status, 'reviewed');
	assert.equal('proposedEdit' in emptyResult.candidate, false);

	// (4) oversized alternative (> the raised 20,000-byte proposedEdit cap).
	const oversized = await serviceFixture({ tutorResults: [tutorAssessment({ decision: 'PROPOSE_ALTERNATIVE', affectedEntryIds: ['paragraph:a'], proposedAlternative: 'x'.repeat(20_001) })], documentFragments: fragments });
	const oversizedResult = await oversized.service.synthesize(oversized.input);
	assert.equal(oversizedResult.status, 'reviewed');
	assert.equal('proposedEdit' in oversizedResult.candidate, false);
});

test('an old-style TUTOR_ASSESSED event with no proposedEdit key still validates (additive-optional backward compat)', async () => {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-structured-legacy-'));
	try {
		const store = new v2.ScientificStateStore(projectRoot);
		const synthesisDigest = digest({ synthesisId: 'synthesis-legacy', threadId: 'thread-1', summary: 'Legacy summary only.' });
		const events = [
			event(1, 'created-a', 'THREAD_CREATED', 'thread-1', 'USER', { title: 'Q', summary: 'Public summary.', activeThreadId: 'thread-1' }, []),
			event(2, 'tutor-a', 'TUTOR_ASSESSED', 'thread-1', 'TUTOR', { status: 'DRAFT', summary: 'Legacy summary only.', synthesisId: 'synthesis-legacy', synthesisDigest }, ['created-a']),
		];
		await store.commitTransition({ events, snapshot: { schemaVersion: 1, activeThreadId: 'thread-1', threads: [{ threadId: 'thread-1', version: 1, status: 'OPEN', title: 'Q', summary: 'Public summary.', createdEventId: 'created-a', headEventId: 'tutor-a', relationIds: [], decisionIds: [] }], relations: [], decisions: [] } });
		const state = await store.read();
		assert.equal(state.events.length, 2);
		assert.equal('proposedEdit' in state.events[1].payload, false);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

// --- Section B: scientific-state-store.ts's raised proposedEdit byte cap --------------

async function assertCommits(projectRoot, payload, shouldSucceed) {
	const store = new v2.ScientificStateStore(projectRoot);
	const synthesisDigest = digest({ synthesisId: 'synthesis-cap', threadId: 'thread-1', summary: payload.summary });
	const events = [
		event(1, 'created-a', 'THREAD_CREATED', 'thread-1', 'USER', { title: 'Q', summary: 'Public summary.', activeThreadId: 'thread-1' }, []),
		event(2, 'tutor-a', 'TUTOR_ASSESSED', 'thread-1', 'TUTOR', { status: 'DRAFT', synthesisId: 'synthesis-cap', synthesisDigest, ...payload }, ['created-a']),
	];
	const commit = store.commitTransition({ events, snapshot: { schemaVersion: 1, activeThreadId: 'thread-1', threads: [{ threadId: 'thread-1', version: 1, status: 'OPEN', title: 'Q', summary: 'Public summary.', createdEventId: 'created-a', headEventId: 'tutor-a', relationIds: [], decisionIds: [] }], relations: [], decisions: [] } });
	if (shouldSucceed) {
		await commit;
		assert.ok(true);
	} else {
		await assert.rejects(commit);
	}
}

test('proposedEdit.replacementText accepts up to ~20,000 bytes (raised cap) while every other public string stays bounded at 2,000', async () => {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-structured-cap-'));
	try {
		// (1) 15,000 bytes: over the OLD 2,000-byte cap, under the NEW 20,000-byte cap -- must succeed.
		await assertCommits(projectRoot, { summary: 'Bounded summary.', proposedEdit: { kind: 'replace', targetEntryId: 'paragraph:x', replacementText: 'x'.repeat(15_000) } }, true);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

test('proposedEdit.replacementText is still bounded (not unlimited) at ~20,000 bytes', async () => {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-structured-cap-over-'));
	try {
		await assertCommits(projectRoot, { summary: 'Bounded summary.', proposedEdit: { kind: 'replace', targetEntryId: 'paragraph:x', replacementText: 'x'.repeat(20_001) } }, false);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
});

test('the raised cap never weakens the 2,000-byte guard for any OTHER public payload string, including other fields nested inside proposedEdit', async () => {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-structured-cap-other-'));
	try {
		// A top-level field other than proposedEdit.replacementText: still bounded at 2,000.
		await assertCommits(projectRoot, { summary: 'y'.repeat(2_500) }, false);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
	const projectRoot2 = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-structured-cap-other2-'));
	try {
		// A DIFFERENT field nested inside proposedEdit (rationale, not replacementText/content): still bounded at 2,000.
		await assertCommits(projectRoot2, { summary: 'Bounded summary.', proposedEdit: { kind: 'replace', targetEntryId: 'paragraph:x', replacementText: 'Short.', rationale: 'z'.repeat(2_500) } }, false);
	} finally {
		await rm(projectRoot2, { recursive: true, force: true });
	}
});

// --- Section C: live lifecycle-v1 materialization applies real structured edits --------

async function withTempRoot(run) {
	const projectRoot = await mkdtemp(path.join(tmpdir(), 'paper-proposal-scientific-structured-live-'));
	try {
		return await run(projectRoot);
	} finally {
		await rm(projectRoot, { recursive: true, force: true });
	}
}

function decisionEvents({ id, threadId, summary, proposedEdit, sequenceStart }) {
	const synthesisDigest = digest({ synthesisId: `synthesis-${id}`, threadId, summary, proposedEdit });
	const tutorPayload = { status: 'DRAFT', summary, synthesisId: `synthesis-${id}`, synthesisDigest, ...(proposedEdit ? { proposedEdit } : {}) };
	return {
		synthesisDigest,
		events: [
			event(sequenceStart, `tutor-${id}`, 'TUTOR_ASSESSED', threadId, 'TUTOR', tutorPayload, [`created-${id}`]),
			event(sequenceStart + 1, `review-${id}`, 'CONCEPTUAL_REVIEW_RECORDED', threadId, 'CONCEPTUAL_REVIEWER', { status: 'PASS', synthesisId: `synthesis-${id}`, synthesisDigest }, [`tutor-${id}`]),
			event(sequenceStart + 2, `accepted-${id}`, 'DECISION_ACCEPTED', threadId, 'USER', { decisionId: `decision-${id}`, synthesisId: `synthesis-${id}`, synthesisDigest, status: 'ACCEPTED_UNMATERIALIZED' }, [`review-${id}`]),
		],
	};
}

async function materialize({ baseContent, decisions, workspaceId = 'workspace-1' }) {
	return withTempRoot(async (projectRoot) => {
		const lifecycle = new v2.LifecycleService(projectRoot);
		const registered = await lifecycle.registerBaseDocument({ workspaceId, requestId: 'register-base', baseDocumentId: 'base-1', content: baseContent });
		assert.equal(registered.outcome, 'COMMITTED');
		const store = new v2.ScientificStateStore(projectRoot);
		const threads = [];
		const allDecisions = [];
		let allEvents = [];
		let sequence = 1;
		for (const d of decisions) {
			allEvents.push(event(sequence, `created-${d.id}`, 'THREAD_CREATED', `thread-${d.id}`, 'USER', { title: `Question ${d.id}`, summary: `Public summary ${d.id}.`, activeThreadId: `thread-${d.id}` }, []));
			sequence += 1;
			const built = decisionEvents({ id: d.id, threadId: `thread-${d.id}`, summary: d.summary, proposedEdit: d.proposedEdit, sequenceStart: sequence });
			allEvents = allEvents.concat(built.events);
			sequence += 3;
			threads.push({ threadId: `thread-${d.id}`, version: 1, status: 'ACCEPTED_UNMATERIALIZED', title: `Question ${d.id}`, summary: `Public summary ${d.id}.`, createdEventId: `created-${d.id}`, headEventId: `accepted-${d.id}`, relationIds: [], decisionIds: [`decision-${d.id}`] });
			allDecisions.push({ decisionId: `decision-${d.id}`, threadId: `thread-${d.id}`, acceptedEventId: `accepted-${d.id}`, acceptedSynthesisDigest: built.synthesisDigest, acceptedBy: { kind: 'USER' }, state: 'ACCEPTED_UNMATERIALIZED', sourceEventIds: [`tutor-${d.id}`, `review-${d.id}`] });
		}
		await store.commitTransition({ events: allEvents, snapshot: { schemaVersion: 1, activeThreadId: threads[0].threadId, threads, relations: [], decisions: allDecisions } });

		const runtime = new v2.ScientificWorkflowRuntime(projectRoot, {}, { lifecycleV1WorkspaceId: workspaceId });
		const result = await runtime.execute({ operation: 'SCIENTIFIC_WORKFLOW', instruction: 'request materialization', scientificAct: 'REQUEST_MATERIALIZATION', candidateIds: decisions.map((d) => `decision-${d.id}`) });
		assert.equal(result.status, 'materialized', JSON.stringify(result));
		const inventory = await lifecycle.rebuildLifecycleInventory(workspaceId);
		const active = inventory.revisions.find((revision) => revision.revisionId === result.materialization.targetRevision);
		assert.ok(active, 'materialized revision must exist in the lifecycle inventory');
		return { active, baseContent, projectRoot };
	});
}

test('a single structured CHANGE applies in place, byte-preserving: replacement lands verbatim at its locus, unrelated content untouched', async () => {
	const baseContent = '# Energy Identity\n\nBaseline informal statement without display math.\n\n# Momentum Relation\n\nBaseline momentum statement untouched.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const energyParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Baseline informal'));
	assert.ok(energyParagraph, 'fixture assumption: an addressable paragraph entry exists for the Energy Identity section');

	const { active } = await materialize({
		baseContent,
		decisions: [{ id: 'a', summary: 'State the energy identity explicitly as E=mc^2.', proposedEdit: { kind: 'replace', targetEntryId: energyParagraph.entryId, replacementText: 'The energy identity is E=mc^2, stated explicitly.' } }],
	});

	assert.equal(active.content.includes('The energy identity is E=mc^2, stated explicitly.'), true, 'the real replacement text is applied, not an annotation of the original text');
	assert.equal(active.content.includes('Baseline informal statement without display math.'), false, 'the original paragraph text is replaced, not preserved alongside an annotation');
	assert.equal(active.content.includes('# Momentum Relation\n\nBaseline momentum statement untouched.\n'), true, 'the unrelated Momentum Relation section survives byte-for-byte, untouched');
	assert.doesNotMatch(active.content, /> Accepted revision:/, 'a real structured CHANGE is applied directly -- it must never fall back to the annotation shape');
});

test('MULTIPLE decisions, each with its own distinct proposedEdit locus, splice into ONE successor version (disjoint splice), all untouched bytes byte-preserved', async () => {
	const baseContent = '# Energy Identity\n\nBaseline informal statement without display math.\n\n# Momentum Relation\n\nBaseline momentum statement untouched.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const energyParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Baseline informal'));
	const momentumParagraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph' && baseContent.slice(e.startByte, e.endByte).startsWith('Baseline momentum'));
	assert.ok(energyParagraph && momentumParagraph);

	const { active } = await materialize({
		baseContent,
		decisions: [
			{ id: 'a', summary: 'Energy identity revision.', proposedEdit: { kind: 'replace', targetEntryId: energyParagraph.entryId, replacementText: 'The energy identity is E=mc^2.' } },
			{ id: 'b', summary: 'Momentum relation revision.', proposedEdit: { kind: 'replace', targetEntryId: momentumParagraph.entryId, replacementText: 'The momentum relation is p=mv.' } },
		],
	});

	// Both accepted decisions land in the SAME materialized revision -- one version, not two.
	assert.equal(active.content.includes('The energy identity is E=mc^2.'), true);
	assert.equal(active.content.includes('The momentum relation is p=mv.'), true);
	// The headings themselves (untouched regions between/around the two edited spans) survive byte-for-byte.
	assert.equal(active.content.includes('# Energy Identity\n\n'), true);
	assert.equal(active.content.includes('# Momentum Relation\n\n'), true);
	assert.doesNotMatch(active.content, /> Accepted revision:/, 'both decisions are applied as real structured edits, never annotations');
	assert.doesNotMatch(active.content, /## Accepted scientific decisions/, 'no claim was pushed to the summary tail block -- both fully resolved structurally');
});

test('a large (>2,000 byte) replacement is applied after the cap raise, still byte-preserving', async () => {
	const baseContent = '# Derivation\n\nShort placeholder derivation text.\n';
	const probe = await v2.rebuildDerivedState('lifecycle-v1:successor-locus', 'working', 'lifecycle-v1', Buffer.from(baseContent, 'utf8'));
	const paragraph = probe.structuralIndex.entries.find((e) => e.type === 'paragraph');
	assert.ok(paragraph);
	const largeReplacement = `${'The derivation proceeds as follows. '.repeat(150)}Q.E.D.`;
	assert.ok(largeReplacement.length > 2_000 && largeReplacement.length < 20_000);

	const { active } = await materialize({
		baseContent,
		decisions: [{ id: 'a', summary: 'Expand the derivation.', proposedEdit: { kind: 'replace', targetEntryId: paragraph.entryId, replacementText: largeReplacement } }],
	});
	assert.equal(active.content.includes(largeReplacement), true, 'the full large replacement text is applied verbatim, not truncated');
	assert.equal(active.content.startsWith('# Derivation\n\n'), true, 'the untouched heading prefix is byte-preserved');
});

test('an old-style summary-only decision (no proposedEdit at all) still annotates exactly as before (regression)', async () => {
	const baseContent = '# Energy identity\n\nBaseline informal statement without display math.\n';
	const summary = 'The energy identity should state E=mc^2 explicitly.';
	const { active } = await materialize({ baseContent, decisions: [{ id: 'a', summary }] });
	assert.match(active.content, /> Accepted revision: /, 'summary-only decisions still fall back to the pre-existing locus-scoped annotation');
	assert.equal(active.content.includes(summary), true);
});

test('a proposedEdit whose targetEntryId has drifted (absent from the current materialization base) falls back to annotation/tail-block -- it never forces an offset or crashes', async () => {
	const baseContent = '# Stable Section\n\nCompletely stable content, never touched by any heading-keyword match.\n';
	const summary = 'This summary intentionally shares no words with any heading in the base document xyzxyz.';
	const { active } = await materialize({
		baseContent,
		decisions: [{ id: 'a', summary, proposedEdit: { kind: 'replace', targetEntryId: 'paragraph:this-entry-id-does-not-exist-in-the-base', replacementText: 'Would-be replacement, must never be silently applied at the wrong offset.' } }],
	});
	// Drift: the structural locus is unresolvable, and (by construction) the summary
	// also matches no heading, so this decision is preserved -- as a fallback block --
	// rather than silently discarded or force-applied at a wrong offset.
	assert.equal(active.content.includes('Would-be replacement, must never be silently applied at the wrong offset.'), false, 'a drifted proposedEdit must never be force-applied at an unresolved offset');
	assert.equal(active.content.startsWith(baseContent), true, 'the original base content is preserved as an untouched prefix when the only decision falls back');
	assert.equal(active.content.includes(summary), true, 'the decision itself is never silently lost -- it is preserved in the fallback block');
});

// --- Section D: SuccessorEditPlanner (secondary/filename-era route) -------------------

test('SuccessorEditPlanner emits a real "replace" action at the resolved locus when a claim carries a structural proposedEdit (instead of only an "insert" annotation)', async () => {
	const base = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Introduction\n\nOriginal introduction text.\n\n# Method\n\nOriginal method text.\n'));
	const methodParagraph = base.structuralIndex.entries.find((e) => e.type === 'paragraph' && e.headingPath?.includes?.('Method'));
	assert.ok(methodParagraph, 'fixture assumption: an addressable Method paragraph entry exists');
	const expectedRevision = { filename: base.filename, revision: base.revision, documentSha256: base.documentSha256 };
	const acceptedDecisions = [
		{ claimId: 'claim-a', decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: 'digest-a', summary: 'Replace the method section with a formal derivation.', proposedEdit: { kind: 'replace', targetEntryId: methodParagraph.entryId, replacementText: 'The method proceeds via formal derivation.' } },
	];
	const plan = new v2.SuccessorEditPlanner().plan({ base, expectedRevision, acceptedDecisions });
	assert.equal(plan.kind, 'CREATE_SUCCESSOR');
	const [patch] = plan.patches;
	assert.deepEqual(patch.plan.actions, [{ kind: 'replace', targetEntryId: methodParagraph.entryId, replacementText: 'The method proceeds via formal derivation.' }]);
	assert.deepEqual(patch.plan.resolvedTargets, [methodParagraph.entryId]);
});

test('SuccessorEditPlanner with no proposedEdit on any claim keeps the exact pre-existing append-only behavior (backward compat)', async () => {
	const base = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from('# Introduction\n\nOriginal introduction text.\n\n# Method\n\nOriginal method text.\n'));
	const expectedRevision = { filename: base.filename, revision: base.revision, documentSha256: base.documentSha256 };
	const acceptedDecisions = [
		{ claimId: 'claim-a', decisionId: 'decision-a', threadId: 'thread-a', acceptedEventId: 'accepted-a', acceptedSynthesisDigest: 'digest-a', summary: 'Replace the method section with a formal derivation.' },
	];
	const plan = new v2.SuccessorEditPlanner().plan({ base, expectedRevision, acceptedDecisions });
	const [patch] = plan.patches;
	assert.deepEqual(patch.plan.actions.map((action) => action.kind), ['insert']);
	assert.match(patch.plan.actions[0].content, /^\n\n## Accepted scientific decisions/);
});
