import { ENGINE_MODULE_ROOT } from './_engine-module-root.mjs';
// Characterization tests (Phase 0 of proposal-deliberation-tutor-repair), updated for
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
// wiring changes (see the proposal-deliberation-tutor-repair apply-progress for the
// scoping rationale) and remains unmodified.
//
// Chain under test: cli.mjs's registered `proposal_deliberation_execute` tool calls
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


