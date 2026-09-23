# Diagram Obligation Specification (delta)

## ADDED Requirements

### Requirement: Figure-Prose Semantic Audit

A diagram's manifest `components` MUST be checked against the prose of the
section that describes it, and the `components_from` fact's resolved list MUST
be checked against both the manifest and that prose. The audit's subject is the
**manifest**, never every `\node{}` string. Its verdict MUST be one of
`pass` | `fail` | `unmeasured`, and a warning MUST NOT change the verdict.

#### Scenario: A phantom component fails

- GIVEN a manifest component the section prose never names
- WHEN the audit runs
- THEN `verdict` is `fail` and the component is named in `unmatched_nodes`

#### Scenario: A missing pipeline stage fails

- GIVEN a `components_from` fact whose list names a step absent from both the
  manifest and the prose
- WHEN the audit runs
- THEN the step is named in `missing_pipeline_steps`

#### Scenario: A clean pair passes with every list empty

- GIVEN a figure, manifest, contract and prose that agree
- WHEN the audit runs
- THEN `verdict` is `pass` with empty `unmatched_nodes`,
  `missing_pipeline_steps` and `label_mismatches`

#### Scenario: Acronym drift warns rather than fails

- GIVEN a component whose only content is an acronym the prose spells out
- WHEN the audit runs
- THEN the token is named in `label_mismatches` and in `warnings`, and the
  verdict is not `fail`

#### Scenario: An uncheckable pair is unmeasured, never pass

- GIVEN a contract declaring no `components_from`, or a call with no block bound
- WHEN the audit runs
- THEN the verdict is `unmeasured` naming its reason, never `pass`

#### Scenario: A content finding is not a CLI refusal

- GIVEN a manifest naming a component the contract excludes
- WHEN `figure audit` runs
- THEN the call exits 0 with `status: ok` and `verdict: fail`, and the refusal
  code appears as a finding rather than as the process exit

### Requirement: The Audit Is Read Without Its Module

`verify`'s `figure-semantics` check MUST read only an already-computed report
dict on the evidence object. `paper_verify.py`'s import allowlist MUST NOT be
widened to admit the auditor or a JSON parser, and no `Path`-typed evidence
field may be read by a check.

#### Scenario: No figure declares nothing rather than passing

- GIVEN a paper with no diagram at all
- WHEN `verify` runs
- THEN `figure-semantics` reports `unmeasured`, reason `NO_FIGURE_DECLARED`
