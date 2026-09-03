# Named Record Witness Specification

## Purpose

`__records__` makes the leveled `@record` witness addressable to a named record instead of
only the `search` block's own, and states what a target that never declares one gets —
reported, never refused, mirroring `__levels__`'s own `undeclaredLadder` precedent.

## Requirements

### Requirement: `__records__` declaration

A target MAY declare `__records__: dict` as a third top-level literal in
`src/<Package>_Benchmark/__init__.py` (or `config.py`), held apart from `__benchmark__`
exactly as `__levels__`/`__steps__` already are, read the same `ast`-only way (`__init__.py`
first, `config.py` second). Each entry maps a target-chosen name to `{"path": str,
"requiredScale": dict}`. A value of any other shape reads as `{}` (nothing declared) — the
same silent-not-crashing rule `resolve_levels_declaration`/`resolve_steps_declaration`
already apply to a malformed `__levels__`/`__steps__`.

### Requirement: kit ships an empty stub only

`assets/kit/src_benchmark/__init__.py` MUST ship `__records__: dict = {}` plus a commented
example, mirroring `__levels__`/`__steps__` exactly. The kit MUST NOT invent an entry name
or a record vocabulary on any target's behalf — the same restraint that keeps `__levels__`'s
stub `[]`.

### Requirement: from-zero — created or reported, with consequence

Whatever this change reads from a target MUST either be created by the kit (above) or
reported when absent, together with its consequence — the same discipline
`undeclared_ladder_state` already applies to `__levels__`. A target scaffolded from zero
MUST NOT silently lack `__records__` and discover the gap only by tripping a refusal later.

#### Scenario: absent `__records__`, no witness references it

- GIVEN a target with no `__records__` declared and no `@record:level <name>` witness
  anywhere in its position sequence
- WHEN `verify` runs
- THEN it reports a records-undeclared state naming the consequence, and refuses nothing

#### Scenario: absent `__records__`, a witness names one

- GIVEN a target with no `__records__` declared and a position item carrying
  `@record:level <name>`
- WHEN `verify` runs
- THEN the records-undeclared report still fires and `verify` still refuses nothing; the
  witness itself derives `None` (unmeasured) — nothing was declared for it to check

### Requirement: absence is reported, never refused

`verify` MUST report an absent or empty `__records__` as its own top-level key (modeled on
`undeclared_ladder_state`'s placement and shape) and MUST NOT refuse on it. A target with
genuinely no named records is a legitimate resting state — the identical argument
`undeclared_ladder_state`'s own docstring makes for an empty `__levels__`.

### Requirement: `@record:level <name>` grammar

`WITNESS_RE` already parses an optional operand for every kind. `OPERAND_REQUIRED_KINDS`
MUST continue excluding bare `@record` (still operand-less), while a `:level`-marked
`@record:level <name>` carries `name` as its operand. A bare `@record` witness MUST remain
byte-identical in meaning to today.

### Requirement: leveled derivation via existing arithmetic

`@record:level <name>` MUST derive its rung through the existing `_record_scale_level`
function, fed the named entry's own found/current/scale state — never a new arithmetic. A
`name` absent from a declared `__records__` MUST derive `None` (unmeasured), the same way an
unlisted `@notebook` path or `@rehearsal` job derives `None` today; it MUST NOT be treated as
a definite `False`.

### Requirement: existing instances keep working

A position block written before `__records__` existed, and any target that never declares
one, MUST keep deriving `@shard:level`, `@notebook:level` and bare `@record` exactly as
before — those deriver functions are untouched by this change. `@record:level <name>` is new
surface area only: it invalidates nothing already on disk, and no remedy or migration applies
to an existing block.

## Non-Normative: the target's own follow-on

Item 4 (`@shard:level`) and item 5 (`@notebook:level`, which also delegates to
`_record_scale_level` against the `search` block — see the exploration's appendix) share one
defect class: a rung witness that cannot see what its own prose claims to describe. Once
`__records__` exists, the reference target's own change — its own commit, its own session —
rewrites both items' witnesses to `@record:level <name>` and re-derives the block. This
change does not schedule, verify, or gate that work.
