// Growth-threshold advisory unit coverage (paper-proposal-tutor-repair, design
// amendment: multi-section successor + growth advisory).
//
// Pure-function tests only: `evaluateSuccessorGrowthThreshold` /
// `evaluateSuccessorGrowthThresholdFromTargets` never touch the filesystem,
// never mutate anything, and are NEVER wired into the live deliberation flow
// in this batch (that wiring is explicitly deferred to Phase 2, which needs
// in-session accumulated approved-target state). These tests assert exact
// boundary behavior: "more than 4 sections" / "more than 40% of document
// bytes", whichever occurs first, is a WARN; the threshold itself is never a
// WARN (exactly 4 sections, exactly 40% of bytes).
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
const v2 = await jiti.import(path.resolve('.claude/skills/paper-proposal/engine/exports.ts'));

test('barrel exposes the growth-threshold advisory functions', () => {
	assert.equal(typeof v2.evaluateSuccessorGrowthThreshold, 'function');
	assert.equal(typeof v2.evaluateSuccessorGrowthThresholdFromTargets, 'function');
});

test('exactly 4 approved sections does not warn (threshold is "more than 4")', () => {
	const verdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 4, approvedBytes: 10, documentBytes: 1000 });
	assert.equal(verdict.warn, false);
	assert.deepEqual(verdict.reasons, []);
});

test('5 approved sections warns (crosses "more than 4")', () => {
	const verdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 5, approvedBytes: 10, documentBytes: 1000 });
	assert.equal(verdict.warn, true);
	assert.equal(verdict.reasons.length, 1);
	assert.match(verdict.reasons[0], /section count 5 exceeds 4/);
});

test('exactly 40% of document bytes does not warn (threshold is "more than 40%")', () => {
	const verdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 1, approvedBytes: 400, documentBytes: 1000 });
	assert.equal(verdict.warn, false);
	assert.deepEqual(verdict.reasons, []);
});

test('just over 40% of document bytes warns', () => {
	const verdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 1, approvedBytes: 401, documentBytes: 1000 });
	assert.equal(verdict.warn, true);
	assert.equal(verdict.reasons.length, 1);
	assert.match(verdict.reasons[0], /approved bytes 401 exceed 40% of document bytes \(1000\)/);
});

test('just under 40% of document bytes does not warn', () => {
	const verdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 1, approvedBytes: 399, documentBytes: 1000 });
	assert.equal(verdict.warn, false);
});

test('both thresholds crossed at once produces both reasons (non-blocking: still just a warn)', () => {
	const verdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 6, approvedBytes: 900, documentBytes: 1000 });
	assert.equal(verdict.warn, true);
	assert.equal(verdict.reasons.length, 2);
});

test('zero-length document never warns on the byte-ratio branch (avoids division by zero)', () => {
	const verdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 1, approvedBytes: 0, documentBytes: 0 });
	assert.equal(verdict.warn, false);
});

test('the result is a pure, non-blocking advisory: it never throws and carries no side effect', () => {
	assert.doesNotThrow(() => v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 0, approvedBytes: 0, documentBytes: 0 }));
	const verdict = v2.evaluateSuccessorGrowthThreshold({ approvedSectionCount: 0, approvedBytes: 0, documentBytes: 100 });
	assert.equal(verdict.warn, false);
	assert.deepEqual(verdict.reasons, []);
});

test('evaluateSuccessorGrowthThresholdFromTargets measures section count and byte spans directly from resolved TargetCandidate composites', () => {
	const targets = [
		{ composite: { startByte: 0, endByte: 100 } },
		{ composite: { startByte: 200, endByte: 250 } },
	];
	const verdict = v2.evaluateSuccessorGrowthThresholdFromTargets(targets, 1000);
	// 150 approved bytes / 1000 document bytes = 15%; 2 sections: no warn.
	assert.equal(verdict.warn, false);
});

test('evaluateSuccessorGrowthThresholdFromTargets warns once the resolved targets exceed 4 sections', () => {
	const targets = Array.from({ length: 5 }, (_, index) => ({ composite: { startByte: index * 10, endByte: index * 10 + 1 } }));
	const verdict = v2.evaluateSuccessorGrowthThresholdFromTargets(targets, 10000);
	assert.equal(verdict.warn, true);
	assert.match(verdict.reasons.join(' '), /section count 5 exceeds 4/);
});
