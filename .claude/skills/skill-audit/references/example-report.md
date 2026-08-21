# Audit: an example subject, one closed surface

This report is shipped as a worked example, so `check-report` has something to
accept in the reference beside the invocation that validates it.

## Ranked findings

### F1. The accepted set is restated by hand and derived nowhere

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Code side: `engine/host.mjs:320`
- Doctrine side: `SKILL.md:243`
- Detail: the running host names its own accepted set in its refusal; the
  table beside it is a complement and states a different one.

## Not adjudicable

### F2. A declared value nothing anywhere reads

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: not adjudicable
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
