# Audit: `proposal-deliberation`, the accepted-operation surface

Subject: `.claude/skills/proposal-deliberation/`. Surface: the set of operations
the CLI host accepts. Slice chosen because it is the one closed set with a
language-independent probe already available in the subject's own code.

Produced by `skill-audit` under its own doctrine, with a shell. Every finding
below carries its own marker; nothing is reported as confirmed that was not
executed. This report **repairs nothing**, and the wall between reporting and
repairing is deliberate: two of the four findings have remedies whose cost the
owner of the subject has to weigh, and one of them cannot be decided at all
without a product decision.

## Move outcomes

- Move: 0: ran
- Move: 1: skipped: no from-zero build declared for this surface
- Move: 2: skipped: not driven from disk in this pass
- Move: 3: skipped: no external boundary crossed in this pass
- Move: 4: skipped: no installed dependency read in this pass
- Move: 5: skipped: no live probe attempted, no consent sought
- Move: 6: skipped: no lock inverted in this pass
- Move: 7: skipped: single-harness count only, not compared before/after
- Move: textual: ran

## Ranked findings

### F1. The surface has no closed roster in any document, anywhere

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Code side: `engine/cli.mjs:320`
- Doctrine side: `SKILL.md:243`
- Detail: the running host enumerates its complete accepted set inside its own
  refusal. Driving it as a subprocess with a nonce, from a directory with no
  project root, returns nine names on stdout with exit `1`. Against that, every
  documented site the recipe declares reports `no-closed-roster`. The table at
  `SKILL.md:243` is headed `## Other engine operations` and closes with "None
  of the four", so it is a complement set and states a deliberate subset. The
  reference states the set in prose at `references/usage.md:264`, and prose is
  what a documented side may not be read out of, because the reader writing the
  comparison has just read that prose and will reproduce it unconsciously. The
  surface test holds it as a JavaScript array at
  `tests/proposal-deliberation-cli-operation-surface.test.mjs:31`.
- Why this is the finding rather than nine findings: with no closed roster, the
  `unregistered` direction is deliberately not computed. Reporting all nine
  accepted operations as undocumented would have invented one finding per
  member and none of them would have been about this subject. Honouring the
  complement claim is what prevents that, and the claim is honoured only
  because the recipe quotes the heading and the quoted heading was found on
  disk.

### F2. The set is restated by hand in three places and derived in none

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Code side: `engine/cli.mjs:298-306`
- Doctrine side: `references/usage.md:264`
- Detail: `roster` reports three restatement sites, each carrying members of
  the executed set written out by hand: `SKILL.md` from line 42,
  `references/usage.md` from line 3 with the full set at `:264-266`, and
  `tests/proposal-deliberation-cli-operation-surface.test.mjs:31`. Every one of
  them currently agrees with the running code. They are still reported.
  Agreement today is not derivation, and this repository's own history records
  a stale operation name that survived precisely because every restatement of
  it agreed with the stale one. The executed set is the deciding evidence here;
  the three written copies are the enumeration, and the enumeration is what is
  wrong by being an enumeration at all.

### F3. A schema description promises an operation its own enum refuses

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Code side: `engine/proposal-workspace.ts:5546`
- Doctrine side: `engine/cli.mjs:298`
- Detail: the `StringEnum` on that line accepts seven operation names. Its
  `description`, on the same line, ends "external-maintenance handoff, or
  persistent scientific-workflow operation" — an operation the enum beside it
  does not list and the host refuses by name. The description is a documented
  claim with nothing behind it. A stale build artifact under
  `node_modules/.cache/jiti/` still holds the wider enum, which dates the
  narrowing: the enum was reduced and the sentence describing it was not. This
  is the cheapest of the four to fix and the easiest to have missed, because
  the claim and the code it contradicts sit on the same physical line.

## Not adjudicable

### F4. A route stage that is enumerated, counted, and unreachable

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: not adjudicable
- Code side: `engine/runtime-metrics.ts:3`
- Doctrine side: `engine/cli.mjs:320`
- Detail: `SCIENTIFIC_WORKFLOW` is a member of `RouteMetricStage`
  (`engine/runtime-metrics.ts:3`) and of `routeStages` (`:14`), so
  `emptyRouteCounts()` at `:16` creates a counter for it on every run. The host
  refuses it as an operation, and that refusal is asserted deliberately at
  `tests/proposal-deliberation-cli-operation-surface.test.mjs:79`. Enumerating
  every `selectedGlobalRoute(...)` call in the live source shows the stages it
  can actually produce, and `SCIENTIFIC_WORKFLOW` is not among them. No engine
  `.ts` file defines a `SCIENTIFIC_WORKFLOW_OPERATION` any more. So the counter
  exists and nothing can ever increment it.
- Why not a defect: the question is not which half is wrong. This half has no
  other half. A stage is not an operation, and a value that is computed and
  deliberately never branched on is not a finding on that ground alone — the
  bar for such a value is documentation, not consumption. What makes this one
  reportable is that nothing documents it either.
- Remedy: build or delete, and both cost something. Deleting the member is a
  handful of lines and forecloses the feature; building the route back is a
  product decision about whether persistent scientific workflow ships. The
  audit does not choose, and this is the structural reason report-then-fix is
  the correct ordering rather than a matter of taste.

## Clean, stated as results

Each entry names the execution that established it and what was observed.
None of them rests on a suite being green.

- **The refusal is complete.** Driving `engine/cli.mjs` as a subprocess with
  `{"operation":"__AUDIT_NONCE__","instruction":"probe"}` returned
  `UNKNOWN_OPERATION: ... is not one of` followed by nine names, on stdout,
  exit `1`. The set the host publishes in its refusal is the set its guard
  actually holds, because `engine/cli.mjs:320` builds the message from
  `HOST_OPERATIONS` and `TOOL_OPERATIONS` themselves rather than from a copy.
- **The probe cannot mutate the subject.** `validateRequest(request);` is the
  first statement of `run()` at `engine/cli.mjs:333`, so the throw precedes all
  project input and output. Observed directly: the scratch directory the probe
  ran in was empty before the run and empty after it, and a content digest over
  every file under the subject was byte-identical before and after a full
  audit.
- **The guard fires on the token being present, not absent.**
  `engine/cli.mjs:319` reads `operation !== undefined && (...)`. Driving the
  host with the key omitted entirely produced no refusal at all. A probe built
  on token-absence would have recovered nothing and reported an empty accepted
  set, which is the shape this audit refuses to emit.
- **The auditor restates nothing it derives.** Every file of `skill-audit` and
  its own test file were searched for each of the nine names, with the needles
  taken from the executed probe rather than from any list. No occurrence.
- **No numeral in the subject's own documentation misstates a list it
  introduces.** `numeralMismatch` is empty for `SKILL.md` and
  `references/usage.md`.

## Unchecked

Named, and not claimed clean. Each is a surface that was never enumerated.

- **Route-metric stages.** The deferred slice, and worth taking next. Read-only
  observation, not executed and therefore not a finding: `GlobalRouteStage` at
  `engine/proposal-workspace.ts:5313` and `RouteMetricStage` at
  `engine/runtime-metrics.ts:3` each hold a member the other does not —
  `CREATE_INITIAL_REVISION` in the first, `SCIENTIFIC_WORKFLOW` in the second —
  while `selectedGlobalRoute` at `engine/proposal-workspace.ts:5405` passes one
  straight into `recordRouteMetric` at `engine/runtime-metrics.ts:30`, which
  increments `routeSelections[stage]`. Nothing in this project typechecks these
  files. That is a candidate, not a finding, and settling it is the point of
  the slice.
- **The error-code roster.** Never enumerated.
- **The public export surface.** Never enumerated.
- **Every other engine module and every other `.mjs` suite.** One pass over
  that surface reproduces an overrun already recorded this week, which is why
  the slicing exists.

## Falsifier

Rename `## Other engine operations` at `SKILL.md:243` to `## Engine operations`.
The recipe quotes that heading verbatim, `roster` checks the quote against disk
before honouring the scope claim, and the claim would stop being honoured — the
site would report `heading-not-found` instead of `no-closed-roster`, and F1's
reasoning about complements would no longer apply to it. That inversion was run:
it fires.

More broadly, F1 through F3 are overturned by a single observation — a
parseable table anywhere in the subject that states the whole accepted set and
claims closure. F4 is overturned by one `selectedGlobalRoute` call that can
produce `SCIENTIFIC_WORKFLOW`, or by any consumer that reads its counter.

## Changed-line forecast

For the fix that would follow. This audit makes none of it.

| Remedy | Changed lines |
| --- | --- |
| One closed `\| Operation \| Use it for \|` table in `SKILL.md` stating all nine | 14 |
| Replace the prose set at `references/usage.md:264-266` with a pointer to that table | 6 |
| Derive `ACCEPTED_OPERATIONS` in the surface test from the host's refusal instead of restating it | 12 |
| Correct the stale clause in the schema description at `engine/proposal-workspace.ts:5546` | 1 |
| F4: no forecast — build-or-delete is a product decision, and its size depends on which | — |
| Total, excluding F4 | 33 |

## Repair units

| Unit | Findings | Changed lines |
| --- | --- | --- |
| Ship the closed operations table and repoint its consumers | F1, F2, F3 | 33 |
| Build or delete the unreachable route-metric stage | F4 | 0 |

## How this report was produced

```
$ python3 .claude/skills/skill-audit/scripts/audit_cli.py roster \
    --subject .claude/skills/proposal-deliberation \
    --probe-spec .claude/skills/skill-audit/references/probes/proposal-deliberation.accepted-operations.json \
    --repo-root .
```

Exit `0`. `comparison: not-run`, `unregistered: []`, `phantom: []`, three
`no-closed-roster` notes each carrying the range searched, three `duplicated`
sites, `numeralMismatch: []`.

Harness figures, reported separately because the two are disjoint and no single
command runs both: `python3 -m unittest discover -s tests` went from 902 before
this change to 973 after it, a rise of 71. `npm test` stayed at 371 pass, 0
fail, on Node v26.4.0 — this change adds no `.mjs`, so a rise there would have
been the surprising result.

Containment was proven by content: a sorted `path -> sha256` listing over
`implementations/Domain_Adaptation` was taken before any file of this change
was written and again at the end, over 46,626 files. Version-control porcelain
was not used and could not have been, because that tree is ignored and porcelain
over it is empty by construction. The `manifest` subcommand that would make this
a one-line proof is deferred to `the-manifest-that-proves-containment`, and this
hand-taken listing is the interim stand-in, named as such rather than passed off
as the same thing.
