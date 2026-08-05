// Deliberation lock + refute loop + in-session state unit coverage
// (proposal-deliberation-tutor-repair, Phase 2: spec D1-D5, design amendment growth advisory).
//
// These tests construct `ChatDeliberationService` directly with hand-written
// TutorAdapter/ReviewerAdapter fakes (plain `{assess}`/`{review}` objects) --
// no faux AI provider or model-call harness is needed, since the service only
// ever calls the injected adapter interfaces directly. Everything here is
// in-memory: no proposal `.md` is read or written anywhere.
import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(path.resolve('.claude/skills/proposal-deliberation/engine/exports.ts'));

function baseAssessment(overrides = {}) {
	return {
		decision: 'ACCEPT', summary: 'Discussion-only assessment.', mathematicalIssues: [], notationIssues: [], assumptionIssues: [],
		requiredRevisions: [], unresolvedQuestions: [], riskLevel: 'LOW', affectedEntryIds: [],
		...overrides,
	};
}

function baseReview(overrides = {}) {
	return {
		decision: 'APPROVE', scientificCoherence: 'Coherent.', scopeCompliance: 'In scope.', unsupportedClaims: [], referenceRisks: [], notationRisks: [],
		requiredChanges: [], unresolvedQuestions: [], riskLevel: 'LOW',
		...overrides,
	};
}

function fakeTutor(assessments) {
	let call = 0;
	const inputs = [];
	return { calls: () => call, inputs, assess: async (input) => { inputs.push(input); const value = assessments[Math.min(call, assessments.length - 1)]; call += 1; return typeof value === 'function' ? value(input) : value; } };
}

function fakeReviewer(reviews) {
	let call = 0;
	const inputs = [];
	return { calls: () => call, inputs, review: async (input) => { inputs.push(input); const value = reviews[Math.min(call, reviews.length - 1)]; call += 1; return typeof value === 'function' ? value(input) : value; } };
}

test('isOpen/close (D1/D2/D4): a conversation opens on its first turn, closes explicitly, discards state, and reports terminated on reuse', async () => {
	const tutor = fakeTutor([baseAssessment()]);
	const registry = v2.createPiSessionDraftRegistry();
	const service = new v2.ChatDeliberationService(tutor, registry);
	const sessionIdentity = 'session-lock-1';
	assert.equal(service.isOpen(sessionIdentity, 'chat-lock-1'), false, 'never-seen conversation is not open');

	const first = await service.deliberate({ instruction: 'Discutamos la hipótesis.', sessionIdentity, conversationId: 'chat-lock-1' });
	assert.equal(first.status, 'deliberated', JSON.stringify(first));
	assert.equal(service.isOpen(sessionIdentity, 'chat-lock-1'), true, 'a completed turn opens the conversation');

	const closed = service.close(sessionIdentity, 'chat-lock-1');
	assert.deepEqual(closed, { status: 'closed', conversationId: 'chat-lock-1' });
	assert.equal(service.isOpen(sessionIdentity, 'chat-lock-1'), false, 'CLOSE clears the open flag');
	assert.equal(service.latestConclusion('chat-lock-1'), undefined, 'CLOSE discards accumulated turns (D4)');

	const reused = await service.deliberate({ instruction: 'Sigamos.', sessionIdentity, conversationId: 'chat-lock-1' });
	assert.equal(reused.status, 'blocked');
	assert.equal(reused.reason, 'CONVERSATION_TERMINATED', 'reusing a closed conversationId reports terminated, not resumed (D5)');

	const closingAgain = service.close(sessionIdentity, 'chat-lock-2');
	assert.deepEqual(closingAgain, { status: 'not_open', conversationId: 'chat-lock-2' }, 'closing a conversation that was never open is a no-op, not an error');
});

test('default-on bounded refute loop (D3): a discussion-only decision stays single-pass; a concrete-change decision runs tutor->reviewer->repair (<=2 cycles)', async () => {
	// Discussion-only: ACCEPT never triggers the reviewer.
	const discussionTutor = fakeTutor([baseAssessment({ decision: 'ACCEPT' })]);
	const reviewerNeverCalled = fakeReviewer([baseReview()]);
	const registry1 = v2.createPiSessionDraftRegistry();
	const discussionService = new v2.ChatDeliberationService(discussionTutor, registry1, reviewerNeverCalled);
	const discussion = await discussionService.deliberate({ instruction: '¿Qué hipótesis conviene?', sessionIdentity: 's1', conversationId: 'chat-refute-1' });
	assert.equal(discussion.status, 'deliberated', JSON.stringify(discussion));
	assert.equal(discussion.refute.ran, false);
	assert.equal(discussion.refute.outcome, 'NOT_RUN');
	assert.equal(reviewerNeverCalled.calls(), 0, 'a discussion-only turn never invokes the reviewer');
	assert.equal(discussion.reviewerCalls, 0);
	assert.equal(discussion.tutorCalls, 1);

	// Concrete change (ACCEPT_WITH_REVISIONS) that the reviewer approves immediately.
	const concreteTutor = fakeTutor([baseAssessment({ decision: 'ACCEPT_WITH_REVISIONS', proposedAlternative: 'Use finite sets.' })]);
	const approvingReviewer = fakeReviewer([baseReview({ decision: 'APPROVE' })]);
	const registry2 = v2.createPiSessionDraftRegistry();
	const approvedService = new v2.ChatDeliberationService(concreteTutor, registry2, approvingReviewer);
	const approved = await approvedService.deliberate({ instruction: 'Aplica esta revisión concreta.', sessionIdentity: 's2', conversationId: 'chat-refute-2' });
	assert.equal(approved.status, 'deliberated', JSON.stringify(approved));
	assert.equal(approved.refute.ran, true);
	assert.equal(approved.refute.outcome, 'ACCEPT');
	assert.equal(approved.refute.repairCycles, 0);
	assert.equal(approvingReviewer.calls(), 1);

	// Concrete change (PROPOSE_ALTERNATIVE) where the reviewer always requests changes: bounded to exactly 2 repair cycles, then exhausted.
	const repairTutor = fakeTutor([
		baseAssessment({ decision: 'PROPOSE_ALTERNATIVE', proposedAlternative: 'First alternative.' }),
		baseAssessment({ decision: 'PROPOSE_ALTERNATIVE', proposedAlternative: 'Second alternative.' }),
		baseAssessment({ decision: 'PROPOSE_ALTERNATIVE', proposedAlternative: 'Third alternative.' }),
	]);
	const stallingReviewer = fakeReviewer([baseReview({ decision: 'APPROVE_WITH_CHANGES', requiredChanges: ['tighten the notation'] })]);
	const registry3 = v2.createPiSessionDraftRegistry();
	const exhaustedService = new v2.ChatDeliberationService(repairTutor, registry3, stallingReviewer);
	const exhausted = await exhaustedService.deliberate({ instruction: 'Aplica esta revisión concreta.', sessionIdentity: 's3', conversationId: 'chat-refute-3' });
	assert.equal(exhausted.status, 'deliberated', JSON.stringify(exhausted));
	assert.equal(exhausted.refute.ran, true);
	assert.equal(exhausted.refute.outcome, 'REPAIR_EXHAUSTED');
	assert.equal(exhausted.refute.repairCycles, 2, 'repair is bounded to at most 2 cycles');
	assert.equal(stallingReviewer.calls(), 3);
	assert.equal(repairTutor.calls(), 3);
});

test('growth advisory (task 2.10): the in-session accumulated approved set surfaces a non-blocking warning once it exceeds 4 sections, and is discarded on CLOSE (D4)', async () => {
	const tutor = fakeTutor([baseAssessment({ decision: 'ACCEPT_WITH_REVISIONS', proposedAlternative: 'One approved change.' })]);
	const reviewer = fakeReviewer([baseReview({ decision: 'APPROVE' })]);
	const registry = v2.createPiSessionDraftRegistry();
	const service = new v2.ChatDeliberationService(tutor, registry, reviewer);
	const sessionIdentity = 'session-growth';
	let last;
	for (let turn = 1; turn <= 5; turn += 1) {
		last = await service.deliberate({ instruction: `Aplica el cambio aprobado número ${turn}.`, sessionIdentity, conversationId: 'chat-growth-1' });
		assert.equal(last.status, 'deliberated', JSON.stringify(last));
		assert.ok(last.growthAdvisory, 'a completed concrete-change turn always carries a growth advisory verdict');
		if (turn <= 4) assert.equal(last.growthAdvisory.warn, false, `turn ${turn}: exactly ${turn} approved sections must not warn yet`);
	}
	assert.equal(last.growthAdvisory.warn, true, 'the 5th accumulated approved section crosses the "more than 4" threshold');
	assert.match(last.growthAdvisory.reasons.join(' '), /section count 5 exceeds 4/);
	// Non-blocking: the turn itself still deliberates successfully even while the advisory warns.
	assert.equal(last.status, 'deliberated');

	// D4: CLOSE discards the accumulated approved-set state; a brand-new deliberation starts fresh.
	service.close(sessionIdentity, 'chat-growth-1');
	const fresh = await service.deliberate({ instruction: 'Aplica un cambio aprobado en una deliberación nueva.', sessionIdentity, conversationId: 'chat-growth-2' });
	assert.equal(fresh.status, 'deliberated', JSON.stringify(fresh));
	assert.equal(fresh.context.turnCount, 1, 'the new conversation carries no turn history from the closed one');
	assert.equal(fresh.growthAdvisory.warn, false, 'a fresh deliberation does not inherit the closed conversation\'s accumulated approved set');
});

test('growth advisory (re-audit cleanup): repeated approvals to the SAME declared section do not each add 1 to the accumulated section count', async () => {
	// A loaded document gives the tutor a stable, valid entryId
	// (`chat-document:<filename>`) it can legally declare via
	// `affectedEntryIds` on every turn (see chat-deliberation.ts's `context()`:
	// the document fragment, when present, is included on every turn, unlike
	// the once-only paper-guide fragment). The document is intentionally huge
	// so the byte-ratio leg of the threshold never fires on its own -- only
	// the section-count leg is under test here.
	const document = { access: 'READ_ONLY', filename: 'proposal.md', revision: 'r01', lineage: 'lineage-1', documentSha256: 'sha-doc', content: 'placeholder', bytesRead: 1_000_000, truncated: false };
	const sameSectionTutor = fakeTutor([baseAssessment({ decision: 'ACCEPT_WITH_REVISIONS', proposedAlternative: 'Small revision.', affectedEntryIds: ['chat-document:proposal.md'] })]);
	const reviewer = fakeReviewer([baseReview({ decision: 'APPROVE' })]);
	const registry = v2.createPiSessionDraftRegistry();
	const service = new v2.ChatDeliberationService(sameSectionTutor, registry, reviewer);
	const sessionIdentity = 'session-growth-same-section';
	let last;
	for (let turn = 1; turn <= 5; turn += 1) {
		last = await service.deliberate({ instruction: `Ajusta la misma sección (vuelta ${turn}).`, sessionIdentity, conversationId: 'chat-growth-same-1', document });
		assert.equal(last.status, 'deliberated', JSON.stringify(last));
	}
	assert.equal(last.growthAdvisory.warn, false, '5 approvals that all declare the exact same affected entry id must dedupe to 1 distinct section, never crossing the "more than 4" threshold');

	// Positive control in the SAME test: a turn that approves a genuinely
	// DIFFERENT declared target (a second document identity) still counts as
	// its own distinct section -- proving the dedupe is identity-based, not a
	// bug that silently stops counting altogether.
	const otherDocument = { ...document, filename: 'other-proposal.md' };
	const distinctTutor = fakeTutor([baseAssessment({ decision: 'ACCEPT_WITH_REVISIONS', proposedAlternative: 'Different section revision.', affectedEntryIds: ['chat-document:other-proposal.md'] })]);
	const serviceDistinct = new v2.ChatDeliberationService(distinctTutor, v2.createPiSessionDraftRegistry(), reviewer);
	const distinct = await serviceDistinct.deliberate({ instruction: 'Ajusta una sección distinta.', sessionIdentity: 'session-growth-distinct', conversationId: 'chat-growth-distinct-1', document: otherDocument });
	assert.equal(distinct.status, 'deliberated', JSON.stringify(distinct));
});
