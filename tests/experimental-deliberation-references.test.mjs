// This domain's reference-integrity vocabulary: an experiment DECLARES an
// identifier, and a claim reference CITES one. Both directions of the mapping
// become detectable from that pair -- a claim citing an experiment nobody
// declares is an unresolved citation, and an experiment nobody cites is a
// declared value absent from the cited set.
//
// A fresh process, because `reference-experimental.ts` reads this domain's own
// prose-citation pattern off the loaded profile, and the whole suite run is fixed
// to a different one by `package.json`'s `test` script.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = process.cwd();
const engineDir = path.join(repoRoot, 'skills/_core/deliberation/engine');
const skillDir = path.join(repoRoot, 'skills/experimental-deliberation');
const profilePath = path.join(skillDir, 'profile.ts');
const piRoot = path.resolve('.');

// One experiment declaring `E1`, one claim citing it in prose, and one claim
// citing it through the explicit marker. Everything resolves.
const RESOLVED = `# Experiments

## Claim C1

The adapted model needs no target labels. Tested by (Exp. E1).

## Experiment [exp:E1]

Sustains claim C1 [tests:E1].
`;

// A claim naming an experiment that this document never declares: the claim has
// no experiment behind it.
const CLAIM_WITHOUT_EXPERIMENT = `# Experiments

## Claim C1

The adapted model needs no target labels. Tested by (Exp. E9).

## Experiment [exp:E1]

Sustains claim C1.
`;

// An experiment nobody cites: it maps to no claim.
const EXPERIMENT_WITHOUT_CLAIM = `# Experiments

## Experiment [exp:E1]

Measures accuracy on the held-out split.
`;

const DUPLICATE = `# Experiments

## Experiment [exp:E1]

First.

## Experiment [exp:E1]

Second.
`;

const NEITHER = '# Experiments\n\nTraining runs use a learning rate of 3e-4 over 5 seeds.\n';

// `the-agreement-nothing-computes` (Slice D, design.md M6, tasks.md 2.11):
// the new cross-document `[claims:N]` form, which resolves against the
// mathematical proposal's own declared claims -- an entirely different
// engine (`_core/implementation/`), never this deliberation core's own
// `cites()`. This document carries the form and nothing this domain's own
// `cites()` recognizes at all, so `cites()` must answer `[]` for it --
// the guard against a later agent adding `[claims:N]` to `cites()` "for
// completeness" (which would make every crossing an unresolved reference
// in ITS OWN document, per `checkReferenceIntegrity`'s `known =
// declaredValues(source)` reading the SAME document's declarations).
const CLAIMS_CROSSING_ONLY = '# Experiments\n\nSustains claim [claims:39].\n';

const HARNESS = `import path from 'node:path';
import { pathToFileURL } from 'node:url';
const piRoot = ${JSON.stringify(piRoot)};
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
    '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
    '@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
    typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const engineDir = process.env.ENGINE_DIR;
const references = await jiti.import(process.env.REFERENCES_MODULE);
const { checkReferenceIntegrity } = await jiti.import(path.join(engineDir, 'reference-index.ts'));
const documents = JSON.parse(process.env.DOCUMENTS);
const report = {};
for (const [name, source] of Object.entries(documents)) {
    report[name] = {
        declares: references.declares(source),
        cites: references.cites(source),
        integrity: checkReferenceIntegrity(source, references),
    };
}
console.log(JSON.stringify(report));
`;

let cached;
async function loaded() {
    if (cached) return cached;
    const directory = await mkdtemp(path.join(os.tmpdir(), 'experimental-deliberation-references-'));
    const harnessPath = path.join(directory, 'harness.mjs');
    await writeFile(harnessPath, HARNESS, 'utf8');
    const env = {
        ...process.env,
        DELIBERATION_DOMAIN_PROFILE: profilePath,
        ENGINE_DIR: engineDir,
        REFERENCES_MODULE: path.join(skillDir, 'reference-experimental.ts'),
        DOCUMENTS: JSON.stringify({
            RESOLVED, CLAIM_WITHOUT_EXPERIMENT, EXPERIMENT_WITHOUT_CLAIM, DUPLICATE, NEITHER,
            CLAIMS_CROSSING_ONLY,
        }),
    };
    const { stdout } = await execFileAsync('node', [harnessPath], { env });
    cached = JSON.parse(stdout.trim().split('\n').pop());
    return cached;
}

test('an experiment declares its identifier', async () => {
    const { RESOLVED: result } = await loaded();
    assert.deepEqual(result.declares, [{ kind: 'tag', value: 'E1' }]);
});

test('a claim cites an experiment in prose and through the explicit marker', async () => {
    const { RESOLVED: result } = await loaded();
    assert.deepEqual(result.cites.map((entry) => entry.value), ['E1', 'E1']);
    assert.deepEqual([...new Set(result.cites.map((entry) => entry.kind))].sort(), ['prose', 'ref']);
});

test('every citation resolving to a declared experiment is reference-integral', async () => {
    const { RESOLVED: result } = await loaded();
    assert.equal(result.integrity.resolved, true);
    assert.equal(result.integrity.unique, true);
    assert.equal(result.integrity.applicable, true);
});

test('a claim with no experiment behind it is an unresolved citation', async () => {
    const { CLAIM_WITHOUT_EXPERIMENT: result } = await loaded();
    assert.deepEqual(result.integrity.declared, ['E1']);
    assert.ok(result.integrity.cited.includes('E9'));
    assert.equal(result.integrity.resolved, false, 'the core fails candidate validation on an unresolved citation');
});

test('an experiment mapping to no claim is a declared value absent from the cited set', async () => {
    const { EXPERIMENT_WITHOUT_CLAIM: result } = await loaded();
    assert.deepEqual(result.integrity.declared, ['E1']);
    assert.deepEqual(result.integrity.cited, []);
    assert.equal(result.integrity.applicable, true, 'a declared experiment nobody cites is still something to check');
    const orphans = result.integrity.declared.filter((value) => !result.integrity.cited.includes(value));
    assert.deepEqual(orphans, ['E1']);
});

test('two experiments declaring the same identifier are not unique', async () => {
    const { DUPLICATE: result } = await loaded();
    assert.deepEqual(result.integrity.declared, ['E1', 'E1']);
    assert.equal(result.integrity.unique, false);
});

test('a document declaring and citing nothing reports not applicable, never a vacuous pass', async () => {
    const { NEITHER: result } = await loaded();
    assert.deepEqual(result.declares, []);
    assert.deepEqual(result.cites, []);
    assert.equal(result.integrity.applicable, false);
});

test('the cross-document [claims:N] form is not a citation this domain resolves', async () => {
    // M6 (design.md): a negative control, asserted against the CURRENT,
    // unedited reference-experimental.ts -- not a RED test waiting for a
    // GREEN. `[claims:N]` resolves against the mathematical proposal
    // through `_core/implementation/`'s own crossing_state, an entirely
    // different engine; this deliberation core's own `cites()` must never
    // recognize it.
    const { CLAIMS_CROSSING_ONLY: result } = await loaded();
    assert.deepEqual(result.cites, []);
});
