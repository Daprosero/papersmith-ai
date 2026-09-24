// Phase 3.1 (change 5): reference integrity becomes profile-driven. What a document
// DECLARES as a numbered/named thing, and what CITES one, are `profile.references.{declares,
// cites}` lookups now -- never a hardwired `\label`/`\tag`/`\eqref`/`(Ec. N)` assumption in
// `candidate-validator.ts`, `reference-index.ts` and `document-index.ts`. The mathematical
// vocabulary ships as `proposal-deliberation/reference-math.ts`, wired through `profile.ts`,
// exactly as the preservation gate's `preservation-math.ts` (change 4).
import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const piRoot = path.resolve('.');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
	'@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
	'@earendil-works/pi-ai/compat': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/compat.js'),
	'@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
	typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const v2 = await jiti.import(path.resolve('skills/_core/deliberation/engine/exports.ts'));
const engine = path.resolve('skills/_core/deliberation/engine');

/**
 * A non-mathematical `declares`/`cites` vocabulary, built by hand for this test only: a
 * report document that declares tables as `[Table T1]` and cites one as `see Table T1`.
 * Proves the check is exercised beyond the math profile's own tests (Acceptance Criteria),
 * without needing a second real profile module -- `checkReferenceIntegrity` takes any
 * `{declares, cites}` pair directly, decoupled from the live `DOMAIN` singleton the whole
 * test run fixes to the mathematical profile.
 */
const tableVocabulary = {
	declares: (source) => [...source.matchAll(/\[Table\s+([A-Za-z0-9]+)\]/g)].map(m => ({ kind: 'table', value: m[1] })),
	cites: (source) => [...source.matchAll(/see Table\s+([A-Za-z0-9]+)/g)].map(m => ({ kind: 'see', value: m[1] })),
};

test('3.1.1 math-profile behavior preserved byte-identical: matched tag and Ec. N citation validate cleanly', async () => {
	const { validateCandidate } = await jiti.import(path.join(engine, 'candidate-validator.ts'));
	const doc = '# 1 Results\n\n$$\nx = 1\n\\tag{1}\n$$\n\nAs shown in (Ec. 1), the result holds.\n';
	const state = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(doc));
	const paragraphs = state.structuralIndex.entries.filter(e => e.type === 'paragraph');
	const editable = paragraphs[paragraphs.length - 1];
	const plan = { planVersion: '2', documentSha256: state.documentSha256, intent: 'MODIFY', instructionHash: 'x', resolvedTargets: [editable.entryId], semanticChange: false, destructiveIntent: false, cleanupLevel: 'NONE', constraints: [], actions: [{ kind: 'replace', targetEntryId: editable.entryId, replacementText: 'As shown in (Ec. 1), the result still holds.' }], expectedEffects: [], unresolvedQuestions: [] };
	const compiled = v2.compilePatches(state, plan);
	const result = await validateCandidate(state, plan, compiled);
	assert.equal(result.ok, true, JSON.stringify(result));
	assert.equal(result.referencesApplicable, true, 'a tag and its citation are both present -- the check has something to measure');
	assert.equal(result.results.declarations, true);
	assert.equal(result.results.references, true);
});

test('3.1.2 a genuine unresolved citation is caught, in a non-mathematical vocabulary shape', async () => {
	const { checkReferenceIntegrity } = await jiti.import(path.join(engine, 'reference-index.ts'));
	const resolved = '[Table T1] shows the baseline results.\n\nAs discussed, see Table T1 for details.\n';
	assert.equal(checkReferenceIntegrity(resolved, tableVocabulary).resolved, true, 'T1 is declared and cited -- resolvable');

	const unresolved = '[Table T1] shows the baseline results.\n\nAs discussed, see Table T2 for details.\n';
	const check = checkReferenceIntegrity(unresolved, tableVocabulary);
	assert.equal(check.resolved, false, 'T2 is cited but never declared');
	assert.ok(check.cited.includes('T2'));
});

test('3.1.3 empty declares/cites is reported not-applicable, distinct from a confirmed-consistent pass', async () => {
	const { checkReferenceIntegrity } = await jiti.import(path.join(engine, 'reference-index.ts'));
	const noReferences = checkReferenceIntegrity('Just prose. Nothing declared, nothing cited.', tableVocabulary);
	assert.equal(noReferences.applicable, false, 'zero declared and zero cited items -- not applicable');

	const genuinePass = checkReferenceIntegrity('[Table T1] shows results.\n\nsee Table T1 above.\n', tableVocabulary);
	assert.equal(genuinePass.applicable, true, 'a declaration and a citation exist -- the check is applicable');
	assert.equal(genuinePass.resolved, true, 'and it genuinely resolves');

	const { validateCandidate } = await jiti.import(path.join(engine, 'candidate-validator.ts'));
	const mathFreeDoc = '# Title\n\nJust prose, no notation at all.\n';
	const mathFreeState = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(mathFreeDoc));
	const target = mathFreeState.structuralIndex.entries.find(e => e.type === 'paragraph');
	const plan = { planVersion: '2', documentSha256: mathFreeState.documentSha256, intent: 'MODIFY', instructionHash: 'x', resolvedTargets: [target.entryId], semanticChange: false, destructiveIntent: false, cleanupLevel: 'NONE', constraints: [], actions: [{ kind: 'replace', targetEntryId: target.entryId, replacementText: 'Different prose, still no notation.' }], expectedEffects: [], unresolvedQuestions: [] };
	const compiled = v2.compilePatches(mathFreeState, plan);
	const mathFreeResult = await validateCandidate(mathFreeState, plan, compiled);
	assert.equal(mathFreeResult.referencesApplicable, false, 'a math-free document declares and cites nothing -- not applicable');
});

test('3.1.4 a duplicate declaration is still caught, generalized to the profile vocabulary', async () => {
	const { checkReferenceIntegrity } = await jiti.import(path.join(engine, 'reference-index.ts'));
	const duplicated = '[Table T1] shows the baseline.\n\n[Table T1] appears a second time.\n';
	const check = checkReferenceIntegrity(duplicated, tableVocabulary);
	assert.equal(check.unique, false, 'the same declared value appears twice');

	const { validateCandidate } = await jiti.import(path.join(engine, 'candidate-validator.ts'));
	const dupTagDoc = '# 1 Results\n\n$$\nx = 1\n\\tag{1}\n$$\n\nAnchor paragraph.\n\n## 2 More\n\n$$\ny = 2\n\\tag{1}\n$$\n';
	const dupState = await v2.rebuildDerivedState('research-concept-r01.md', 'r01', 'ROOT', Buffer.from(dupTagDoc));
	const dupAnchor = dupState.structuralIndex.entries.find(e => e.type === 'paragraph');
	const dupPlan = { planVersion: '2', documentSha256: dupState.documentSha256, intent: 'INSERT', instructionHash: 'x', resolvedTargets: [dupAnchor.entryId], semanticChange: false, destructiveIntent: false, cleanupLevel: 'NONE', constraints: [], actions: [{ kind: 'insert', anchorEntryId: dupAnchor.entryId, position: 'after', content: '\n\nStill anchored.' }], expectedEffects: [], unresolvedQuestions: [] };
	const dupCompiled = v2.compilePatches(dupState, dupPlan);
	const dupResult = await validateCandidate(dupState, dupPlan, dupCompiled);
	assert.equal(dupResult.results.declarations, false, 'two `\\tag{1}` declarations in the same candidate must be reported as non-unique');
	assert.equal(dupResult.ok, false, 'a duplicate tag must block the verdict, same as before this change');
});
