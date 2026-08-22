# Audit: an example subject, one closed surface

This report is shipped as a worked example, so `check-report` has something to
accept in the reference beside the invocation that validates it.

## Frozen

- Digest: sha256:f9f163e09a5078c732f596f31c660b4229a97eec1e4fa5de3b6b09eef93ad6e3
- Subject: an example subject, not a real path in this repository
- Exclude: (none)

## Move outcomes

- Move: 0: ran
- Move: 1: skipped: no from-zero build declared for this surface
- Move: 2: skipped: not driven from disk in this pass
- Move: 3: skipped: no external boundary crossed in this pass
- Move: 4: skipped: no installed dependency read in this pass
- Move: 5: skipped: no live probe attempted, no consent sought
- Move: 6: skipped: no lock inverted in this pass
- Move: 7: skipped: single-harness count only, not compared
- Move: 8: skipped: no ordered user-mode flow driven in this pass
- Move: 9: skipped: no supplied reading pair compared in this pass
- Move: textual: ran

## Ranked findings

### F1. The accepted set is restated by hand and derived nowhere

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Digest: sha256:f9f163e09a5078c732f596f31c660b4229a97eec1e4fa5de3b6b09eef93ad6e3
- Code side: `engine/host.mjs:320`
- Doctrine side: `SKILL.md:243`
- Detail: the running host names its own accepted set in its refusal; the
  table beside it is a complement and states a different one.

## Not adjudicable

### F2. A declared value nothing anywhere reads

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: not adjudicable
- Digest: sha256:f9f163e09a5078c732f596f31c660b4229a97eec1e4fa5de3b6b09eef93ad6e3
- Code side: `engine/metrics.ts:3`
- Doctrine side: `engine/host.mjs:319`
- Detail: enumeration found no consumer, so the question is not which half is
  wrong. Build-or-delete, and the choice costs something either way.

## Clean, stated as results

- The refusal path writes nothing - enumerated by driving the host from an
  empty directory, observed that directory empty before the run and after it.

## Unchecked

- The error-code surface - never enumerated, and therefore not claimed clean.

## Falsifier

Rename the heading the recipe quotes and the scope claim stops being honoured,
which would move this surface out of the complement case entirely.

## Changed-line forecast

| Remedy | Changed lines |
| --- | --- |
| One table, one derivation, restatements deleted | 40 |

## Repair units

| Unit | Findings | Changed lines |
| --- | --- | --- |
| One table, one derivation, restatements deleted | F1 | 40 |
| Build or delete the unread declared value | F2 | 0 |
