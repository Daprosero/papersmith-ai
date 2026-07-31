// Ambient-supplied planner unit coverage (design `sdd/paper-proposal-ambient-model`,
// SLICE 1). `createAmbientSuppliedPlanner` is a thin echo-and-VALIDATE
// `SemanticEditPlanner`: it makes no model/network call, but it MUST carry the
// exact planner OUTPUT validation `production-planner-adapter.ts` enforced on a
// real model response (WRONG_TARGET_ENTRY_ID, ALTERED_REPLACEMENT_TEXT,
// malformed action shape, unexpected keys, wrong action count) -- the ambient
// model can still err. No proposal `.md` file is created; every fixture below
// is an in-memory `SemanticPlannerInput` only.
import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const piRoot = '/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent';
const exportsPath = path.join(root, '.claude/skills/paper-proposal/engine/exports.ts');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(exportsPath);

function fakeTarget(entryId) {
	return { entryId, type: 'section', headingPath: [], matchedTerms: [], matchedLabels: [], matchedTags: [], matchedSymbols: [], score: 1, confidence: 1, shortPreview: '', evidence: [] };
}

function baseInput(overrides = {}) {
	return {
		intent: { intent: 'MODIFY', targetDescription: 'x', semanticChange: true, constraints: [], fidelity: {}, scope: 'SECTION', evidence: ['edit it'], destructiveIntent: false, cleanupAuthorized: false, moveMode: 'LITERAL', removeSource: false, cleanupLevel: 'NONE', modelBudget: 1, confidence: 1, pendingQuestions: [], unresolvedQuestions: [] },
		instruction: 'edit it',
		target: fakeTarget('alpha-section'),
		context: { documentSha256: 'a'.repeat(64), targetEntryId: 'alpha-section', instruction: 'edit it', fragments: [], nearbySymbols: {}, directReferences: [], successorCompositeTarget: true },
		constraints: [],
		fidelity: {},
		documentSha256: 'a'.repeat(64),
		...overrides,
	};
}

test('ambient-supplied planner: echoes the ONE resolved-target replace decision, no model call', async () => {
	const planner = v2.createAmbientSuppliedPlanner([{ kind: 'replace', targetEntryId: 'alpha-section', replacementText: 'New alpha body.' }]);
	const result = await planner.plan(baseInput());
	assert.deepEqual(result, { actions: [{ kind: 'replace', targetEntryId: 'alpha-section', replacementText: 'New alpha body.' }], unresolvedQuestions: [] });
});

test('ambient-supplied planner: multi-section reuse -- the SAME planner instance resolves a DIFFERENT decision per target entryId', async () => {
	const planner = v2.createAmbientSuppliedPlanner([
		{ kind: 'replace', targetEntryId: 'alpha-section', replacementText: 'New alpha.' },
		{ kind: 'replace', targetEntryId: 'beta-section', replacementText: 'New beta.' },
	]);
	const alpha = await planner.plan(baseInput({ target: fakeTarget('alpha-section') }));
	const beta = await planner.plan(baseInput({ target: fakeTarget('beta-section') }));
	assert.equal(alpha.actions[0].replacementText, 'New alpha.');
	assert.equal(beta.actions[0].replacementText, 'New beta.');
});

test('ambient-supplied planner: rejects WRONG_TARGET_ENTRY_ID when the only supplied decision names a DIFFERENT entry than the engine resolved', async () => {
	const planner = v2.createAmbientSuppliedPlanner([{ kind: 'replace', targetEntryId: 'wrong-section', replacementText: 'New body.' }]);
	await assert.rejects(
		() => planner.plan(baseInput({ target: fakeTarget('alpha-section') })),
		(error) => {
			assert.equal(error.code, 'PRODUCTION_PLANNER_RESPONSE_REJECTED');
			assert.equal(error.diagnostic.code, 'WRONG_TARGET_ENTRY_ID');
			return true;
		},
	);
});

test('ambient-supplied planner: rejects ALTERED_REPLACEMENT_TEXT when the request carries an exact fidelity block and the decision diverges from it', async () => {
	const planner = v2.createAmbientSuppliedPlanner([{ kind: 'replace', targetEntryId: 'alpha-section', replacementText: 'Drifted text, not the authorized block.' }]);
	const input = baseInput({ fidelity: { targetBlock: 'Old alpha body.', replacementBlock: 'Exact authorized replacement.' } });
	await assert.rejects(
		() => planner.plan(input),
		(error) => {
			assert.equal(error.diagnostic.code, 'ALTERED_REPLACEMENT_TEXT');
			return true;
		},
	);
});

test('ambient-supplied planner: accepts a decision matching the exact fidelity replacementBlock byte-for-byte', async () => {
	const planner = v2.createAmbientSuppliedPlanner([{ kind: 'replace', targetEntryId: 'alpha-section', replacementText: 'Exact authorized replacement.' }]);
	const input = baseInput({ fidelity: { targetBlock: 'Old alpha body.', replacementBlock: 'Exact authorized replacement.' } });
	const result = await planner.plan(input);
	assert.equal(result.actions[0].replacementText, 'Exact authorized replacement.');
});

test('ambient-supplied planner: rejects a malformed decision shape (missing replacementText)', async () => {
	const planner = v2.createAmbientSuppliedPlanner([{ kind: 'replace', targetEntryId: 'alpha-section' }]);
	await assert.rejects(
		() => planner.plan(baseInput()),
		(error) => {
			assert.equal(error.diagnostic.code, 'MALFORMED_DECISION_SHAPE');
			return true;
		},
	);
});

test('ambient-supplied planner: rejects a decision carrying an unexpected extra field', async () => {
	const planner = v2.createAmbientSuppliedPlanner([{ kind: 'replace', targetEntryId: 'alpha-section', replacementText: 'New body.', extraField: 'not authorized' }]);
	await assert.rejects(
		() => planner.plan(baseInput()),
		(error) => {
			assert.equal(error.diagnostic.code, 'UNEXPECTED_DECISION_FIELD');
			return true;
		},
	);
});

test('ambient-supplied planner: rejects WRONG_ACTION_KIND for an insert/delete/move decision -- CREATE_SUCCESSOR is replace-only downstream (edit-planner.ts), so this fails closed at the planner boundary instead of leaking an INVALID_SEMANTIC_EDIT_PLAN deep in the engine', async () => {
	const insertPlanner = v2.createAmbientSuppliedPlanner([{ kind: 'insert', anchorEntryId: 'alpha-section', position: 'after', content: 'New content.' }]);
	await assert.rejects(() => insertPlanner.plan(baseInput()), (error) => { assert.equal(error.diagnostic.code, 'WRONG_ACTION_KIND'); return true; });

	const deletePlanner = v2.createAmbientSuppliedPlanner([{ kind: 'delete', targetEntryId: 'alpha-section', instructionEvidence: 'elimina', reason: 'obsolete' }]);
	await assert.rejects(() => deletePlanner.plan(baseInput()), (error) => { assert.equal(error.diagnostic.code, 'WRONG_ACTION_KIND'); return true; });

	const movePlanner = v2.createAmbientSuppliedPlanner([{ kind: 'move', sourceEntryIds: ['alpha-section'], destinationAnchorId: 'beta-section', position: 'after', moveMode: 'LITERAL', removeSource: true, cleanupLevel: 'NONE' }]);
	await assert.rejects(() => movePlanner.plan(baseInput()), (error) => { assert.equal(error.diagnostic.code, 'WRONG_ACTION_KIND'); return true; });
});

test('ambient-supplied planner: rejects wrong action count (two decisions both naming the SAME resolved target, ambiguous which applies)', async () => {
	const planner = v2.createAmbientSuppliedPlanner([
		{ kind: 'replace', targetEntryId: 'alpha-section', replacementText: 'First.' },
		{ kind: 'replace', targetEntryId: 'alpha-section', replacementText: 'Second.' },
	]);
	await assert.rejects(
		() => planner.plan(baseInput()),
		(error) => {
			assert.equal(error.diagnostic.code, 'AMBIGUOUS_MATCHING_DECISIONS');
			return true;
		},
	);
});

test('ambient-supplied planner: rejects NO_MATCHING_DECISION when no supplied decision names any entry at all', async () => {
	const planner = v2.createAmbientSuppliedPlanner([]);
	await assert.rejects(
		() => planner.plan(baseInput()),
		(error) => {
			assert.equal(error.diagnostic.code, 'NO_MATCHING_DECISION');
			return true;
		},
	);
});
