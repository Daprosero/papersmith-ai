# Step Witness Specification

## Purpose

Formally states why `@step` cannot carry a rung. Behavior is unchanged by this change; the
reasoning becomes doctrine, written down and bound by a test.

## Requirements

### Requirement: `@step` stays two-state

A `@step:level <name>` witness MUST continue to derive as not-levelable:
`_resolve_deriver` MUST keep refusing `POSITION_WITNESS_NOT_LEVELABLE` for kind `"step"`
against `_LEVEL_DERIVERS`, because `_derive_step` reads `run_step`'s `raised`/`returned`
outcome, which is identical whether the callable ran at pilot scale or full scale — it
measures completion, never production.

#### Scenario: a leveled step witness refuses

- GIVEN a position item written as `` `@step:level verification` ``
- WHEN its witness is resolved
- THEN it refuses `POSITION_WITNESS_NOT_LEVELABLE`, unchanged from before this change

### Requirement: the doctrine is written and bound by a test

`proposal-implementation/SKILL.md` MUST state the doctrine: "The smoke proves the pipe. The
pilot proves the science." — with the reasoning that a rehearsal's readiness measurement (the
service accepted the submission, the kernel ran, the shard came down carrying the agreed
fields) is a different fact from a pilot's production (the whole flow ran and what it
produced satisfies what was agreed). Passing one MUST NOT be read as passing the other. A
test MUST assert this text is present in `SKILL.md`.

#### Scenario: doctrine text exists

- GIVEN `SKILL.md` after this change
- WHEN a test reads it
- THEN the doctrine paragraph is present verbatim
