// The experimental domain's preservation gate: which atoms an experiments
// document declares (lost ones must be acknowledged by id before a successor
// publishes), and the canonical-form rules that block outright because they are
// never intentional.
//
// Loaded IN PROCESS rather than through a spawned child, and that is a property
// of the module under test rather than a convenience: `preservation-experimental.ts`
// imports only `types.js` (for `sha256`), never `domain-profile.js`, so nothing
// here touches the single `DELIBERATION_DOMAIN_PROFILE` the whole suite run is
// fixed to. The sibling file `experimental-deliberation-domain-profile.test.mjs`
// spawns a child for the parts that DO need this skill's profile installed.
import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const repoRoot = process.cwd();
const piRoot = path.resolve('.');
const { createJiti } = await import(pathToFileURL(path.join(piRoot, 'node_modules/jiti/lib/jiti.mjs')).href);
const jiti = createJiti(import.meta.url, { alias: {
    '@earendil-works/pi-coding-agent': path.join(piRoot, 'dist/index.js'),
    '@earendil-works/pi-ai': path.join(piRoot, 'node_modules/@earendil-works/pi-ai/dist/index.js'),
    typebox: path.join(piRoot, 'node_modules/typebox/build/index.mjs'),
} });
const { extractAtoms, violations } = await jiti.import(
    path.join(repoRoot, 'skills/experimental-deliberation/preservation-experimental.ts'));

const kinds = (source) => [...extractAtoms(source).values()].map((atom) => atom.kind).sort();
const rules = (source) => violations(source).map((entry) => entry.rule).sort();

// The seven rule ids this change adds -- used ONLY by `otherRules`/`otherViolations`,
// the filter that keeps a PRE-EXISTING rule-specific fixture's assertion honest
// once every document in this file that omits `**Dataset:**`/`**Validation
// scheme:**` also owes the two new missing-declaration violations. NEVER used by
// a test that exists to prove one of these seven rules fires -- reaching for it
// there would hide exactly the regression those tests exist to catch.
const NEW_DECLARATION_RULES = new Set([
    'dataset-declaration-missing', 'dataset-declaration-repeated',
    'validation-scheme-declaration-missing', 'validation-scheme-declaration-repeated',
    'validation-scheme-without-test', 'validation-scheme-without-seeds', 'validation-scheme-without-repetitions',
]);
const otherViolations = (source) => violations(source).filter((entry) => !NEW_DECLARATION_RULES.has(entry.rule));
const otherRules = (source) => otherViolations(source).map((entry) => entry.rule).sort();

// A document carrying one of every atom kind and violating nothing. The protocol
// paragraph deliberately carries three numbers (a learning rate, a seed count and a
// year) OUTSIDE any table, because the fabricated-value rule below must not see them.
// Carries both of this change's declarations too, so the genuine-pass assertion
// below stays UNFILTERED and end-to-end -- the one fixture in this file proven
// against every rule at once, old and new.
const RICH = `# Experiments

## Protocol

Training runs use a learning rate of 3e-4 over 5 seeds, reported on the 2018 split.

**Dataset:** ImageNet-R, 2021 split (train/test as distributed)

**Validation scheme:** paired t-test, 5 seeds, 10 repetitions per condition

- **Success criterion:** the adapted model matches the source-only baseline on the held-out split.

## Baselines

| Baseline | Repository | Venue |
| --- | --- | --- |
| Alpha-Net | https://example.org/alpha-net [pending-verification] | ICML 2015 |
| Beta-Net | https://example.org/beta-net [pending-verification] | NeurIPS 2019 |

## Reported results

| Arm | Accuracy | F1 |
| --- | --- | --- |
| Source only |  |  |
| Adapted |  |  |

![Accuracy against the number of labelled examples](figures/accuracy-vs-labels.png)
`;

// The same protocol prose with every experimental structure removed: no table, no
// figure, no declared criterion, no cited URL, no dataset, no validation scheme.
// Nothing for the pre-existing atom-based gate to check -- but the two new
// declaration rules DO fire on it, which is exactly what the dedicated test below
// proves.
const PLAIN = `# Experiments

## Protocol

Training runs use a learning rate of 3e-4 over 5 seeds, reported on the 2018 split.
`;

// A minimal experiments document declaring exactly the given dataset/validation-scheme
// lines (either may be omitted), used by every scenario below that needs one or
// both declarations in isolation, without RICH's unrelated structure.
const DATASET_LINE = (value) => `**Dataset:** ${value}`;
const SCHEME_LINE = (value) => `**Validation scheme:** ${value}`;
const DOC = (...lines) => `# Experiments\n\n${lines.join('\n\n')}\n`;

// ---------------------------------------------------------------------------
// Atoms
// ---------------------------------------------------------------------------

test('every atom kind is extracted from a document that genuinely contains it', () => {
    assert.deepEqual(kinds(RICH), [
        'baseline', 'baseline',
        'dataset',
        'figure',
        'report-table', 'report-table',
        'success-criterion',
        'url', 'url',
    ]);
});

test('a report-table atom is keyed on the header row, so losing the skeleton is a loss', () => {
    const atoms = [...extractAtoms(RICH).values()].filter((atom) => atom.kind === 'report-table');
    assert.deepEqual(atoms.map((atom) => atom.text).sort(), [
        '| Arm | Accuracy | F1 |',
        '| Baseline | Repository | Venue |',
    ]);
});

test('a baseline atom names the model in the first cell of a baselines table body row', () => {
    const atoms = [...extractAtoms(RICH).values()].filter((atom) => atom.kind === 'baseline');
    assert.deepEqual(atoms.map((atom) => atom.text).sort(), ['Alpha-Net', 'Beta-Net']);
});

test('a success-criterion atom carries the criterion text, not the label', () => {
    const atoms = [...extractAtoms(RICH).values()].filter((atom) => atom.kind === 'success-criterion');
    assert.equal(atoms.length, 1);
    assert.equal(atoms[0].text, 'the adapted model matches the source-only baseline on the held-out split.');
});

test('a url atom is keyed on the URL itself, and the verification marker is not part of it', () => {
    const atoms = [...extractAtoms(RICH).values()].filter((atom) => atom.kind === 'url');
    assert.deepEqual(atoms.map((atom) => atom.text).sort(), [
        'https://example.org/alpha-net',
        'https://example.org/beta-net',
    ]);
    assert.deepEqual(atoms.map((atom) => atom.id).sort(), [
        'url:https://example.org/alpha-net',
        'url:https://example.org/beta-net',
    ]);
});

test('a URL ending a sentence is cited without the sentence punctuation', () => {
    const source = '# Experiments\n\nSee https://example.org/alpha-net.\n';
    assert.deepEqual([...extractAtoms(source).values()].map((atom) => atom.id), ['url:https://example.org/alpha-net']);
    // The stripped period stays in the trailing text, where it correctly fails the tag
    // rule: an untagged URL is untagged whether or not a sentence ended on it. This
    // minimal fixture declares neither of this change's labels, so `otherRules` is the
    // pre-existing-rule-specific filter (see its own definition above).
    assert.deepEqual(otherRules(source), ['url-without-verification-marker']);
});

test('a figure placeholder standing alone on its line is an atom; an inline image reference is not', () => {
    const inline = '# Experiments\n\nSee ![a chart](figures/chart.png) in the appendix.\n';
    assert.deepEqual(kinds(inline), []);
    assert.deepEqual(kinds('# Experiments\n\n![a chart](figures/chart.png)\n'), ['figure']);
});

test('atoms are presence-based: repeating an atom does not multiply it', () => {
    const twice = `${PLAIN}\n![a chart](figures/chart.png)\n\n![a chart](figures/chart.png)\n`;
    assert.deepEqual(kinds(twice), ['figure']);
});

// ---------------------------------------------------------------------------
// applicable:false vs a genuine pass
// ---------------------------------------------------------------------------

test('a document with none of these atom kinds declares no atoms, which the core reports as not applicable', () => {
    assert.equal(extractAtoms(PLAIN).size, 0, 'core computes preservationApplicable as `atoms(before).size > 0`');
    // `PLAIN` has no atoms at all, but it DOES now carry two hard-block violations
    // of its own (neither declaration is present) -- proven, unfiltered, by the
    // dedicated test below. `otherRules` here isolates the claim this test makes:
    // no atom-adjacent, PRE-EXISTING rule fires on it either.
    assert.deepEqual(otherRules(PLAIN), []);
});

test('a document declaring neither label yields exactly the two missing-declaration violations, unfiltered', () => {
    assert.deepEqual(rules(PLAIN), ['dataset-declaration-missing', 'validation-scheme-declaration-missing']);
});

test('a document that HAS atoms and breaks no rule is a genuine pass, distinct from the vacuous one', () => {
    assert.ok(extractAtoms(RICH).size > 0, 'a pass over an empty atom set is the vacuous pass this gate exists to avoid');
    // Deliberately UNFILTERED: RICH carries both of this change's declarations,
    // correctly formed, so the genuine end-to-end pass is proven against every
    // rule this module enforces at once, old and new -- never routed through
    // `otherRules`/`otherViolations`, which exist only to shield a PRE-EXISTING
    // rule-specific fixture that was never meant to also carry these labels.
    assert.deepEqual(violations(RICH), []);
});

// ---------------------------------------------------------------------------
// Canonical form: no fabricated value in a report table's body
// ---------------------------------------------------------------------------

const REPORT_TABLE = (rows) => `# Experiments

## Reported results

| Arm | Accuracy | F1 |
| --- | --- | --- |
${rows}
`;

test('an empty report-table body cell is not a violation', () => {
    assert.deepEqual(otherViolations(REPORT_TABLE('| Source only |  |  |')), []);
});

test('a number in a report-table body cell is a violation naming the row line', () => {
    const found = otherViolations(REPORT_TABLE('| Source only | 0.91 |  |'));
    assert.deepEqual(found.map((entry) => entry.rule), ['report-table-fabricated-value']);
    assert.equal(found[0].line, 7, 'the violation must point at the offending body row');
    assert.match(found[0].detail, /0\.91/);
});

test('a number in a report-table row LABEL (column one) is not a violation', () => {
    assert.deepEqual(otherViolations(REPORT_TABLE('| Adapted (k=3) |  |  |')), []);
});

test('a number in prose outside any table is never a fabricated value', () => {
    assert.deepEqual(otherViolations(PLAIN), []);
});

test('a number in a baselines table body is legitimate: it is a reference table, not a report table', () => {
    const baselines = `# Experiments

| Baseline | Repository | Venue |
| --- | --- | --- |
| Alpha-Net | https://example.org/alpha-net [pending-verification] | ICML 2015 |
`;
    assert.deepEqual(otherViolations(baselines), []);
});

// ---------------------------------------------------------------------------
// Canonical form: a baseline carries a repository URL and a venue/year
// ---------------------------------------------------------------------------

const BASELINES = (header, row) => `# Experiments

| ${header} |
| ${header.split('|').map(() => '---').join(' | ')} |
| ${row} |
`;

test('a baseline row with a repository URL and a venue year is not a violation', () => {
    assert.deepEqual(
        otherRules(BASELINES('Baseline | Repository | Venue', 'Alpha-Net | https://example.org/alpha-net [pending-verification] | ICML 2015')),
        []);
});

test('a baseline named without a repository URL is a violation', () => {
    assert.deepEqual(
        otherRules(BASELINES('Baseline | Venue', 'Alpha-Net | ICML 2015')),
        ['baseline-missing-repository-url']);
});

test('a baseline named without a venue year is a violation', () => {
    assert.deepEqual(
        otherRules(BASELINES('Baseline | Repository', 'Alpha-Net | https://example.org/alpha-net [pending-verification]')),
        ['baseline-missing-venue-year']);
});

test('a verified-on date does not stand in for a missing venue year', () => {
    assert.deepEqual(
        otherRules(BASELINES('Baseline | Repository', 'Alpha-Net | https://example.org/alpha-net [verified: 2026-09-08]')),
        ['baseline-missing-venue-year'],
        'the verification marker carries a year of its own and must be stripped before the venue check');
});

test('an empty first cell is not a baseline, so an empty spacer row raises nothing', () => {
    assert.deepEqual(otherRules(BASELINES('Baseline | Repository | Venue', ' |  | ')), []);
});

// ---------------------------------------------------------------------------
// Canonical form: every external URL carries a verification marker
// ---------------------------------------------------------------------------

test('a bare URL is a violation: nothing in the bytes says a search ever reached it', () => {
    const found = otherViolations('# Experiments\n\nSee https://example.org/alpha-net for the reference implementation.\n');
    assert.deepEqual(found.map((entry) => entry.rule), ['url-without-verification-marker']);
    assert.equal(found[0].line, 3);
});

test('a URL marked pending verification is accepted', () => {
    assert.deepEqual(otherViolations('# Experiments\n\nSee https://example.org/alpha-net [pending-verification] for it.\n'), []);
});

test('a URL marked verified with a run date is accepted', () => {
    assert.deepEqual(otherViolations('# Experiments\n\nSee https://example.org/alpha-net [verified: 2026-09-08] for it.\n'), []);
});

test('a Markdown link carries its tag after the closing paren', () => {
    // Citing a repository as a Markdown link is the ordinary way to write one, so the
    // tag rule has to reach past the link syntax the URL is wrapped in.
    assert.deepEqual(otherViolations('# Experiments\n\nSee [the repository](https://example.org/alpha-net) [pending-verification].\n'), []);
});

test('a marker that is not one of the two spellings does not satisfy the rule', () => {
    assert.deepEqual(
        otherRules('# Experiments\n\nSee https://example.org/alpha-net [checked] for it.\n'),
        ['url-without-verification-marker']);
});

test('a verified marker without a full date does not satisfy the rule', () => {
    assert.deepEqual(
        otherRules('# Experiments\n\nSee https://example.org/alpha-net [verified: 2026] for it.\n'),
        ['url-without-verification-marker']);
});

test('a marker written before the URL does not vouch for it', () => {
    assert.deepEqual(
        otherRules('# Experiments\n\n[pending-verification] was written before https://example.org/alpha-net here.\n'),
        ['url-without-verification-marker']);
});

test('a marker further along the same line does not vouch for an earlier URL', () => {
    // One tagged URL must not cover an untagged neighbour: the tag has to be the next
    // thing after the URL it speaks for, not merely present somewhere on the line.
    const found = otherViolations('# Experiments\n\nSee https://example.org/alpha-net and https://example.org/beta-net [pending-verification] here.\n');
    assert.deepEqual(found.map((entry) => entry.rule), ['url-without-verification-marker']);
    assert.match(found[0].detail, /alpha-net/, 'the untagged URL is the first one, not the tagged neighbour');
});

test('a URL inside a dataset line is caught by the existing url rule, not a new one', () => {
    const source = DOC(DATASET_LINE('see https://example.org/data-card for the split'), SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions'));
    const found = violations(source);
    assert.deepEqual(found.map((entry) => entry.rule), ['url-without-verification-marker']);
});

// ---------------------------------------------------------------------------
// Shape
// ---------------------------------------------------------------------------

test('violations are returned in line order', () => {
    const source = `# Experiments

See https://example.org/one and https://example.org/two.

| Arm | Accuracy |
| --- | --- |
| Adapted | 0.42 |
`;
    const found = otherViolations(source);
    assert.deepEqual(found.map((entry) => entry.line), [3, 3, 7]);
    assert.deepEqual(found.map((entry) => entry.rule), [
        'url-without-verification-marker',
        'url-without-verification-marker',
        'report-table-fabricated-value',
    ]);
});

// ---------------------------------------------------------------------------
// The dataset declaration (D1-D3, ruling 6)
// ---------------------------------------------------------------------------

test('a single dataset line is accepted', () => {
    assert.deepEqual(rules(DOC(DATASET_LINE('CIFAR-10, standard train/test split'), SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions'))), []);
});

test('a missing dataset line is refused', () => {
    const found = violations(DOC(SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions')));
    assert.ok(found.some((entry) => entry.rule === 'dataset-declaration-missing'));
    const entry = found.find((e) => e.rule === 'dataset-declaration-missing');
    assert.equal(entry.line, 1);
});

test('two dataset lines are refused, not silently reduced to the first', () => {
    // A suite testing only zero and one dataset lines would survive a mutation that
    // widened the cardinality check from `> 1` to `> 2` -- this is the third case.
    const found = rules(DOC(DATASET_LINE('CIFAR-10'), DATASET_LINE('ImageNet'), SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions')));
    assert.deepEqual(found, ['dataset-declaration-repeated']);
});

test('a bare `Dataset:` line without bold does not satisfy the rule', () => {
    const source = DOC('Dataset: CIFAR-10', SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions'));
    assert.deepEqual(rules(source), ['dataset-declaration-missing'], 'an unbolded label declares nothing, so it reads as absent');
});

test('a missing declaration reports line 1 and sorts first', () => {
    const source = `# Experiments

See https://example.org/x for detail.

**Validation scheme:** paired t-test, 5 seeds, 10 repetitions
`;
    const found = violations(source);
    assert.equal(found[0].rule, 'dataset-declaration-missing');
    assert.equal(found[0].line, 1);
});

test('a dataset line reducible to a placeholder is refused, exactly like an empty one (ruling 6)', () => {
    assert.deepEqual(
        rules(DOC(DATASET_LINE('TBD'), SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions'))),
        ['dataset-declaration-missing']);
});

test('a dataset atom is extracted from a compliant document', () => {
    const atoms = [...extractAtoms(DOC(DATASET_LINE('ImageNet-R, 2021 split'))).values()];
    assert.deepEqual(atoms.map((atom) => ({ kind: atom.kind, text: atom.text })), [{ kind: 'dataset', text: 'ImageNet-R, 2021 split' }]);
});

test('the atom id is `dataset:<name>`, echoable by a caller', () => {
    const atoms = [...extractAtoms(DOC(DATASET_LINE('CIFAR-10 (train/test split as distributed)'))).values()];
    assert.deepEqual(atoms.map((atom) => atom.id), ['dataset:cifar-10 (train/test split as distributed)']);
});

test('a genuinely different dataset text keys a different atom id (a swap is a loss)', () => {
    const before = [...extractAtoms(DOC(DATASET_LINE('Office-Home'))).values()].map((atom) => atom.id);
    const after = [...extractAtoms(DOC(DATASET_LINE('DomainNet'))).values()].map((atom) => atom.id);
    assert.notDeepEqual(before, after);
});

test('rewording the dataset line by whitespace alone keys the same atom id (not a loss)', () => {
    const before = [...extractAtoms(DOC(DATASET_LINE('ImageNet-R, 2021 split'))).values()].map((atom) => atom.id);
    const after = [...extractAtoms(DOC(DATASET_LINE('ImageNet-R,   2021   split'))).values()].map((atom) => atom.id);
    assert.deepEqual(before, after);
});

test('the same dataset re-verified on a later date keeps its atom id', () => {
    const before = [...extractAtoms(DOC(DATASET_LINE('see https://example.org/data-card [pending-verification]'))).values()].map((atom) => atom.id);
    const after = [...extractAtoms(DOC(DATASET_LINE('see https://example.org/data-card [verified: 2026-09-09]'))).values()].map((atom) => atom.id);
    assert.deepEqual(before, after, 're-verifying must not change the id, or a real re-check would read as a dataset swap');
});

test('the validation scheme declares no atom of its own', () => {
    assert.deepEqual(kinds(DOC(SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions'))), [], 'ruled: the validation scheme is a hard block only');
});

// ---------------------------------------------------------------------------
// The validation-scheme declaration (D2, D4, ruling 7)
// ---------------------------------------------------------------------------

test('a complete validation scheme is accepted', () => {
    assert.deepEqual(rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions per condition'))), []);
});

test('a novel, legitimate test name is accepted without a vocabulary update', () => {
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('Friedman test with Nemenyi post-hoc, 3 seeds, 20 repetitions'))),
        []);
});

test('a missing validation-scheme line is refused', () => {
    const found = violations(DOC(DATASET_LINE('CIFAR-10')));
    assert.ok(found.some((entry) => entry.rule === 'validation-scheme-declaration-missing'));
});

test('two validation-scheme lines are refused', () => {
    const found = rules(DOC(
        DATASET_LINE('CIFAR-10'),
        SCHEME_LINE('paired t-test, 5 seeds, 10 repetitions'),
        SCHEME_LINE('Wilcoxon test, 5 seeds, 10 repetitions'),
    ));
    assert.deepEqual(found, ['validation-scheme-declaration-repeated']);
});

test('one line naming more than one test satisfies the cardinality rule', () => {
    // The cardinality rule counts declaration LINES, not test names.
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('paired t-test and Wilcoxon signed-rank, 5 seeds, 10 repetitions'))),
        []);
});

test('a denylisted placeholder is refused even though the line is non-empty', () => {
    assert.deepEqual(rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('TBD'))), ['validation-scheme-without-test']);
});

test('a non-test output named alone is refused', () => {
    assert.deepEqual(rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('p-value'))), ['validation-scheme-without-test']);
});

test('TBD over 5 seeds, 3 repetitions is refused as naming no test', () => {
    // Both clauses are fully accounted for by the placeholder and the seeds/reps
    // vocabulary; nothing survives to be read as a test name.
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('TBD over 5 seeds, 3 repetitions'))),
        ['validation-scheme-without-test']);
});

test('a scheme naming a real test *and* a p-value publishes', () => {
    // The denylist decides REDUCIBILITY, never vocabulary hygiene: a line is refused
    // only when nothing survives it, not merely because a denylisted term appears.
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('Wilcoxon signed-rank test, p-value < 0.05, over 10 seeds with 3 repetitions'))),
        []);
});

test('seeds and repetitions without a named test are refused', () => {
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('5 seeds, 10 repetitions'))),
        ['validation-scheme-without-test']);
});

test('a named test without seeds or repetitions is refused', () => {
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('paired t-test'))),
        ['validation-scheme-without-seeds']);
});

test('a seeds clause must carry its own digit, not one borrowed from a neighbouring clause', () => {
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('paired t-test with fixed seeds, 3 repetitions'))),
        ['validation-scheme-without-seeds']);
});

test('naming seeds without a repetitions clause is refused', () => {
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('t-test over 5 seeds'))),
        ['validation-scheme-without-repetitions']);
});

test('a second, unrelated digit elsewhere in the value does not stand in for a repetitions clause', () => {
    // A check that merely counted digits anywhere in the value -- rather than
    // requiring a repetitions KEYWORD paired with its own digit -- would wrongly
    // accept this: `5` (the seeds count) and `2024` (a publication year) are two
    // digits, but neither is a repetitions count.
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('paired t-test, 5 seeds, published in 2024'))),
        ['validation-scheme-without-repetitions']);
});

test('a seeds synonym with its own digit is accepted, not only the literal word "seeds" (ruling 7)', () => {
    assert.deepEqual(
        rules(DOC(DATASET_LINE('CIFAR-10'), SCHEME_LINE('paired t-test, 10 random initialisations, 3 repetitions'))),
        []);
});

// ---------------------------------------------------------------------------
// D7 identity: the untouched parts of this module are untouched (design D7 §2)
// ---------------------------------------------------------------------------

// One document engineered to fire all four PRE-EXISTING violation ids at once
// (an untagged URL, a baseline with neither a repository nor a venue year, a
// fabricated report-table value) while its two declarations are both well
// formed -- so the only violations produced are the four this test names, and
// none of this change's seven new ones leak in to make a renamed/dropped id
// invisible among a pile of unrelated noise.
const D7_IDENTITY_DOC = `# Experiments

## Protocol

See https://example.org/untagged for the reference.

- **Success criterion:** the adapted model matches the baseline.

## Baselines

| Baseline | Repository |
| --- | --- |
| Alpha-Net |  |

## Reported results

| Arm | Accuracy |
| --- | --- |
| Adapted | 0.5 |

![a chart](figures/chart.png)

**Dataset:** CIFAR-10

**Validation scheme:** paired t-test, 5 seeds, 10 repetitions
`;

test('D7 identity: the four pre-existing violation ids are still produced, by their own unrenamed names', () => {
    const PRE_EXISTING_RULES = [
        'baseline-missing-repository-url', 'baseline-missing-venue-year',
        'report-table-fabricated-value', 'url-without-verification-marker',
    ];
    const produced = new Set(violations(D7_IDENTITY_DOC).map((entry) => entry.rule));
    for (const rule of PRE_EXISTING_RULES)
        assert.ok(produced.has(rule), `pre-existing rule id ${JSON.stringify(rule)} is no longer produced -- renamed or dropped`);
});

test('D7 identity: the five pre-existing atom kinds are still produced, by their own unrenamed names', () => {
    const PRE_EXISTING_KINDS = ['baseline', 'figure', 'report-table', 'success-criterion', 'url'];
    const produced = new Set([...extractAtoms(D7_IDENTITY_DOC).values()].map((atom) => atom.kind));
    for (const kind of PRE_EXISTING_KINDS)
        assert.ok(produced.has(kind), `pre-existing atom kind ${JSON.stringify(kind)} is no longer produced -- renamed or dropped`);
});
