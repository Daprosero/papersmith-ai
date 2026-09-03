# Step Witness Specification

## Purpose

A position item MUST name a target's own `__steps__` callable as its witness,
satisfied only by that callable's raise/return outcome, expiring the moment
`src/`, `tests/`, or the environment declaration changes. This closes
assert-forgetting. It does NOT close skip-laundering — stated below as a
non-goal, not an omission.

## Requirements

### Requirement: Step Witness Kind
`"step"` MUST join `WITNESS_KINDS`. `` `@step <name>` `` MUST name a key of
the target's `__steps__`, operand required (same class as
`notebook`/`rehearsal`/`shard`).

#### Scenario: A position item declares a step witness
- GIVEN an item ending `` `@step run_suite` ``
- WHEN the block is parsed
- THEN witness kind is `"step"`, operand `"run_suite"`

### Requirement: A Leveled Step Refuses, Never Derives Silently
No `` `:level` `` entry MUST exist for `"step"` in `_LEVEL_DERIVERS`. An item
written `` `@step:level <name>` `` MUST raise a classified `Refused`, never an
unhandled exception, never a silent `None` forever.

#### Scenario: A leveled step item is rejected, not swallowed
- GIVEN `` `@step:level run_suite` ``
- WHEN derived
- THEN a classified `Refused` names the item and the reason

### Requirement: Step Derivation Reads Only Evidence
`_derive_step(evidence, operand)` MUST be a plain dict reader (matching
`_derive_notebook`/`_derive_rehearsal`/`_derive_shard`), reading only
`evidence["stepVerdicts"][operand]` — no ledger, no path, no digest math.
`returned` + current → `True`. `raised` → `False`. Missing operand, missing
verdict, or stale digest → `None`, never `False`.

#### Scenario: A step never run derives unmeasured
- GIVEN no key for the operand in `stepVerdicts`
- WHEN derived
- THEN result is `(None, ...)`; an `x` mark over it reports `unbacked`

#### Scenario: A raised outcome derives False, never None
- GIVEN `stepVerdicts["run_suite"] is False`
- WHEN derived
- THEN result is `False` — a mutation to `None` MUST fail a test

### Requirement: Suite Digest Covers Source, Tests, and the Environment Declaration
`suite_digest(target)` MUST hash every `.py` under `src/` and `tests/`
(`tests_dir.rglob(...)`, matching `test_function_names`), plus five
Python-ecosystem-standard, target-agnostic paths: `requirements.txt`,
`pyproject.toml`, `setup.cfg`, `tox.ini`, `pytest.ini`. Each of the five MUST
contribute a definite value whether present or absent, via the
`current_file_digest`/`ABSENT_FILE_DIGEST` precedent (one `is_file()` test
producing a value, never a branching skip) — so declaring a file later moves
the digest. `suite_digest` MUST NOT merge into `source_digest`; each carries a
docstring naming the other.

#### Scenario: Adding a test file moves the suite digest, not the source digest
- GIVEN a recorded digest, then a new `tests/test_x.py` is added
- WHEN `suite_digest` is recomputed
- THEN it differs; `source_digest` for the same tree is unchanged

#### Scenario: A missing environment file still contributes a value
- GIVEN no `tox.ini` on disk, then one is created
- WHEN `suite_digest` runs before and after
- THEN the digest changes — absence was a recorded fact, not a skip

### Requirement: The Ledger Carries Currency, Old Events Read Safely
`cmd_step`'s `kind: "step"` event MUST record `suite_digest(target)`; this
reverses "no digest field" only for a bare runner step with no self-stamping
artifact. A pre-change event with no `digest` key MUST NOT raise and MUST
read identically to "digest recorded but stale" — no currency established.
Editing an existing ledger line is never the remedy; running `step` again
appends a fresh event that latest-wins supersedes it with.

#### Scenario: A pre-existing undigested event reads as not current
- GIVEN a `kind: "step"` line with no `digest` key
- WHEN evidence folds it
- THEN the verdict is `None`, never an exception, never `True`

### Requirement: Step Verdicts Are Assembled By The Caller
`_position_write_evidence` MUST fold `kind: "step"` events per step name
(latest wins, ledger order), compare each recorded digest against a fresh
`suite_digest(target)`, and set `evidence["stepVerdicts"][name]` before
`derive()` runs.

#### Scenario: A stale digest overrides a returned outcome
- GIVEN the latest event has `outcome: "returned"` but a mismatched digest
- WHEN evidence is assembled
- THEN `stepVerdicts[name]` is `None`, not `True`

### Requirement: Unknown Step Operand Is A Classified, Roster-Visible Refusal
An item naming a `@step` operand absent from `__steps__` MUST raise a new
refusal, classified in `GATING_REFUSALS`, mirroring `STEP_UNKNOWN`'s detail
(lists the real declared steps). `raise Refused(...)` MUST stay textually
inside a `cmd_*` body (never a top-level helper) — `_skipped_rung_detail`'s
proven shape — so `raised_refusal_codes` finds it.
`test_the_derivation_finds_the_measured_sixty_five` MUST be renamed for its
new count; `test_the_roster_states_the_counts_it_actually_holds` MUST keep
binding `SKILL.md`'s spelled count to `len(COMMANDS)`.

#### Scenario: A position item names an undeclared step
- GIVEN `__steps__` has no `run_suite`, item carries `@step run_suite`
- WHEN graded
- THEN a classified refusal fires naming the real declared steps

### Requirement: Gating Recomputes Fresh, No Bypass
`SEQUENCE_NOT_REACHED`/`POSITION_DISAGREES` MUST be recomputed fresh on every
`gate`/`step` call, independent of any earlier `offer` authorization —
unchanged, restated because this witness depends on it.

#### Scenario: A stale offer does not bypass a disagreeing step witness
- GIVEN an `offer` minted before a step's verdict went stale
- WHEN `gate` runs
- THEN both refusals are evaluated fresh and can still fire

### Requirement: Skip-Laundering Is A Stated Non-Goal
This witness MUST NOT distinguish a fully-executed suite from one that
skipped tests: `pytest` exits 0 on skips, `returned` grades green either way.
Measured on the reference target: six skip sites in `tests/`, one
module-level (`allow_module_level=True`, 15 tests silently absent when a
sibling script is missing), exactly one reachable by a declared agreement
witness. `SKILL.md`/`usage.md` MUST state this as a non-goal, not an implied
guarantee.

#### Scenario: A module-level skip still reads as returned
- GIVEN an entire test module skips at collection
- WHEN the step outcome is `"returned"` with a current digest
- THEN the witness derives `True` — documented as accepted, not hidden

## Out of Scope
Mechanism (B); `source_digest` itself; `_skipped_rung_detail`/
`POSITION_RUNG_SKIPPED`; any edit under `implementations/`.
