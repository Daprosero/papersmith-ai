// Finding M8, decided: `runtime-metrics.ts` used to define `recordScientificMetric` and
// a `scientificMetrics` block of seven counters (entry, blocked, recovery_required,
// materialization_blocked, materialization_recovery_required, materialization_retry,
// recovery_diagnostic), copied into every `getRuntimeMetrics()` snapshot and shipped
// inside `self-audit.ts`'s result as `metrics` -- which both hosts' SKILL.md tell the
// agent to read. `recordScientificMetric` had exactly one occurrence repo-wide (its own
// definition): no production caller, no test, ever. The seven counters therefore
// initialised to 0 and were structurally unable to become anything else.
//
// Decision: removed rather than wired to invented call sites (see the comment on
// `RuntimeMetrics` in `runtime-metrics.ts` for the full reasoning). This test proves the
// removal: the snapshot and the self-audit result both stop carrying the field, and the
// dead function is gone from the module's exports.
import assert from 'node:assert/strict'; import { mkdtemp,mkdir,writeFile } from 'node:fs/promises'; import os from 'node:os'; import path from 'node:path'; import test from 'node:test'; import { pathToFileURL } from 'node:url';
const piRoot=path.resolve('.'); const {createJiti}=await import(pathToFileURL(path.join(piRoot,'node_modules/jiti/lib/jiti.mjs')).href); const jiti=createJiti(import.meta.url,{alias:{'@earendil-works/pi-coding-agent':path.join(piRoot,'dist/index.js'),'@earendil-works/pi-ai/compat':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/compat.js'),'@earendil-works/pi-ai':path.join(piRoot,'node_modules/@earendil-works/pi-ai/dist/index.js'),typebox:path.join(piRoot,'node_modules/typebox/build/index.mjs')}}); const v2=await jiti.import(path.resolve('skills/_core/deliberation/engine/exports.ts'));

async function root(){const value=await mkdtemp(path.join(os.tmpdir(),'pp-v2-scientific-metrics-'));await mkdir(path.join(value,'proposals'),{recursive:true});await writeFile(path.join(value,'proposals/research-concept-r01.md'),'# T\n\nText.\n');await v2.loadDocumentState(value,'research-concept-r01.md');return value;}

test('recordScientificMetric is no longer exported -- it had zero production callers and zero tests', () => {
	assert.equal(v2.recordScientificMetric, undefined);
});

test('getRuntimeMetrics() no longer carries a scientificMetrics field', () => {
	v2.resetRuntimeMetrics();
	const metrics = v2.getRuntimeMetrics();
	assert.equal(Object.prototype.hasOwnProperty.call(metrics, 'scientificMetrics'), false);
	// `recordLifecycleMetric`'s sibling field is the proof this class of field is not
	// what was removed -- only the permanently-zero, uncalled one was.
	assert.equal(Object.prototype.hasOwnProperty.call(metrics, 'lifecycleMetrics'), true);
});

test('self-audit\'s metrics block no longer carries scientificMetrics either', async () => {
	const projectRoot = await root();
	const self = await v2.runProposalDeliberationSelfAudit({ projectRoot });
	assert.equal(Object.prototype.hasOwnProperty.call(self.metrics, 'scientificMetrics'), false);
});
