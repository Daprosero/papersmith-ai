# Spec Delta: the-audit-that-escalates-what-it-cannot-decide

Change: `the-audit-that-escalates-what-it-cannot-decide` · Modifies capability: `skill-audit`
(`.claude/skills/skill-audit/`, `tests/test_skill_audit.py`) · Store: openspec.

Baseline: `openspec/changes/archive/2026-08-21-the-audit-that-runs-what-it-claims/spec.md`.
MODIFIES the moves-table requirement (new numbered move). ADDS frozen-subject digesting, a
totality-checked escalation partition and routing, `reading-diff`, `Found by` /
`Disputed severity`, setup-vs-gate steps, and `## Stage outcomes`. Out: `manifest`/`counts`
(still `the-manifest-that-proves-containment`); enforcing independence between drives (last
requirement below states why, instead).

## MODIFIED Requirements

### Requirement: The moves table MUST be complete, typed, and never sized by an underived numeral

Doctrine MUST carry one parseable table, one row per numbered move — now 0 through 9 — plus
one row for the textual move. Row 9 MUST name `reading-diff`: comparing two supplied readings
of one prose surface by mechanical diff. `check-report`'s move-coverage check MUST derive the
required roster from `SKILL.md`'s own table, never a literal list inside the tool.
(Previously: table sized 0-8; no row comparing two readings.)

#### Scenario: A move loses its row
- GIVEN move 9's row is deleted from the table
- WHEN `check-report` validates a report claiming full move coverage
- THEN it SHALL fail and SHALL name move 9 as missing

#### Scenario: The required roster is derived, not hardcoded
- GIVEN a tenth numbered move added with no matching literal in `audit_cli.py`
- WHEN `check-report` runs against a report omitting that move
- THEN it SHALL require a row for it, proving the requirement came from `SKILL.md`

## ADDED Requirements

### Requirement: Every subcommand payload MUST carry a frozen digest of the subject, and a mismatched finding MUST be rejected

Every subcommand MUST emit `tree_digest` of the subject in its payload. A report MUST carry
`## Frozen` naming that digest; `check-report` MUST reject any finding whose digest disagrees.

#### Scenario: A finding's digest disagrees with `## Frozen`
- GIVEN a report where `## Frozen` names digest A and one finding carries digest B
- WHEN `check-report` validates it
- THEN it SHALL reject the report and SHALL name the mismatching finding

### Requirement: A walkthrough step MUST declare `kind: "setup" | "gate"`, defaulting to `"gate"`, and a failing setup step MUST report `setup-failed`, never `stalled`

`walkthrough` MUST read a per-step `kind`. A setup step asserts nothing about the subject and
MUST NOT be counted among gates that passed. A setup step that fails MUST exit `2` as
`setup-failed`.

#### Scenario: A passing setup step is not a passed gate
- GIVEN a recipe whose step 0 is `kind: "setup"` and it succeeds
- WHEN `walkthrough` runs
- THEN step 0 SHALL NOT be counted among gates that passed

#### Scenario: A failing setup step names itself, not the subject
- GIVEN a recipe whose `kind: "setup"` step fails
- WHEN `walkthrough` runs
- THEN it SHALL exit `2` as `setup-failed`, never `stalled`

### Requirement: Every emitted note kind MUST be classified by a totality-checked partition, and an escalatable kind MUST route to a zero-model probe before any reader is reached

A named constant MUST partition every `"kind":` literal emitted in `audit_cli.py` into exactly
one of: escalatable (prose exists, could not be derived), consequence (produced by an
escalatable note, never independently escalated), deterministic exclusion (no prose to re-read).
A totality lock MUST scan actual emission sites and fail on an unclassified kind. Each
escalatable kind MUST carry an `escalation` hint naming the zero-model probe able to decide it;
a surface reaches two-reader comparison only after no such probe applies — the model proposes
a reading, the tool disposes by driving execution.

#### Scenario: A new note kind is added unclassified
- GIVEN a new `"kind":` literal absent from the partition constant
- WHEN the totality lock runs
- THEN it SHALL fail, naming the unclassified kind

#### Scenario: A documented-flag surface is rerouted, not read
- GIVEN a `no-closed-roster` note over a prose-stated flag list
- WHEN escalation routing runs
- THEN each documented flag SHALL be driven as a `walkthrough` gate before any reader is invoked

#### Scenario: A consequence kind is not independently escalated
- GIVEN a `comparison-not-run` note produced solely because its originating surface was already escalatable
- WHEN the escalatable list is built
- THEN `comparison-not-run` SHALL NOT appear in it as a second, independent entry

### Requirement: `reading-diff` MUST compare two supplied readings and MUST NEVER set `closed_seen`

`reading-diff` MUST be a subcommand that never calls `doctrine_side`, comparing exactly two
supplied readings of one prose surface and reporting agreement or divergence. `comparison`
MUST remain `not-run` for a surface compared this way, permanently — agreement between two
readers proves the prose has one reading, never that it is closed.

#### Scenario: Two readers agree
- GIVEN two supplied readings of one surface that state the same set
- WHEN `reading-diff` runs
- THEN it SHALL report agreement and `comparison` SHALL remain `not-run` for that surface

#### Scenario: A supplied reading is planted into `closed_seen`
- GIVEN a call from `reading-diff` into `doctrine_side` is planted
- WHEN the AST lock scans `audit_cli.py`
- THEN it SHALL fail, proving the call reachable-red

### Requirement: A finding MUST carry `- Found by: both | one | not-compared` with no default, and `## Disputed severity` MUST record disagreement verbatim without any severity vocabulary

Each finding MUST carry `- Found by:` alongside the existing evidence marker. When drives
disagree on how serious a finding is, the report MUST carry `## Disputed severity` recording
both positions verbatim with their sources. No `Severity`, `CRITICAL`, `WARNING`, or
`SUGGESTION` vocabulary MUST appear anywhere in the skill.

#### Scenario: A finding omits `Found by`
- GIVEN a finding with no `- Found by:` line
- WHEN `check-report` validates the report
- THEN it SHALL reject the report

#### Scenario: Severity vocabulary is introduced
- GIVEN a finding carrying a `- Severity:` field
- WHEN the vocabulary guard scans the skill directory
- THEN it SHALL fail

### Requirement: `## Stage outcomes` MUST report each of the five stages as `ran` or `skipped: <reason>`, roster derived from a stages table, and a `ran` row MUST demand its artifact

`check-report` MUST require one row per stage, roster derived by parsing `SKILL.md`'s stages
table, never hardcoded. A `ran` stage MUST demand the artifact its row names; a `skipped` row
demands nothing. A zero-model audit (stages 0-1 `ran`, 2-4 all `skipped`) MUST remain valid.

#### Scenario: A stage is declared `ran` without its artifact
- GIVEN stage 2 declared `ran` with no `## Reading diff` section
- WHEN `check-report` validates the report
- THEN it SHALL reject the report and SHALL name stage 2's missing artifact

#### Scenario: A zero-model audit is valid
- GIVEN a report with stages 0-1 `ran` and stages 2-4 all `skipped: <reason>`
- WHEN `check-report` validates it
- THEN it SHALL accept the report

### Requirement: Doctrine MUST state, in its own words, that the shape enforces artifact presence and structure but never enforces independence between drives

The stages table's row for stages 2-4 MUST state explicitly that isolation, blindness, and
no-contact between drives are unfalsifiable from inside a tool that only calls
`subprocess.run()`, and that a stage row is an operator's declaration carrying no lock —
exactly as the moves table's textual row states it has no lock.

#### Scenario: The limit is stated where the stages are
- GIVEN the stages table in `SKILL.md`
- WHEN its row for stages 2-4 is read
- THEN it SHALL state that independence between drives is unfalsifiable and is not enforced
