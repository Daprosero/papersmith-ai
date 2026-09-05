# Spec: skill-audit-move6-substitution-probe

> **Stated exception to the 650-word spec cap.** This change's own subject is
> a skill that finds specs and doctrine that overclaim relative to shipped
> code. Dropping a soundness condition or its fail-if-dropped scenario to
> meet a word budget would be exactly that defect, committed while writing
> the spec for the tool that catches it. Four capabilities below, one per
> commit boundary from the proposal (`driver-child-environment` = Change 0,
> `substitution-probe` + `report-shape` = Change a, `probe-recipe-coverage` =
> Change b). `openspec/specs/` does not exist in this repository; this file
> follows the local flat convention (`openspec/changes/<name>/spec.md`), per
> `the-pilot-proves-the-science` precedent already using multiple ordered
> commits inside one change folder.

---

## Capability: driver-child-environment (Change 0 — New)

### Requirement: Unconditional bytecode purge in every constructed child environment

`run_box_step`'s driver-kind child environment and `run_sensitivity_drive`'s
child environment MUST both carry `PYTHONDONTWRITEBYTECODE=1`, injected
through one shared helper, regardless of whether the parent process's
environment holds it and regardless of what the invoking recipe declares.

#### Scenario: Purge holds regardless of parent environment

- GIVEN the parent process's environment has no `PYTHONDONTWRITEBYTECODE`
- WHEN `run_box_step` constructs a driver-kind child environment
- THEN the constructed child environment carries `PYTHONDONTWRITEBYTECODE=1`

#### Scenario: Both sites carry the purge, not one

- GIVEN a recipe drives a `sensitivity` sweep with no `driver` step involved
- WHEN `run_sensitivity_drive` constructs its own child environment
- THEN that child environment also carries `PYTHONDONTWRITEBYTECODE=1`,
  independently of whether `run_box_step` was exercised in the same run

### Requirement: The purge name is never recipe-declarable

`PYTHONDONTWRITEBYTECODE` MUST NOT be added to `DRIVER_ENV_ALLOWLIST`. A
recipe that declares it explicitly in a driver step's `env` list MUST
continue to be refused `Unprobeable`, unchanged from today's behavior — the
purge is unconditional precisely because it is not a user-configurable name.

#### Scenario: An explicit declaration still refuses the step

- GIVEN a `driver` step whose `env` list names `PYTHONDONTWRITEBYTECODE`
- WHEN `run_box_step` validates the declared names against
  `DRIVER_ENV_ALLOWLIST`
- THEN the step is refused `Unprobeable`, and the doctrine paragraph in
  `SKILL.md` states this is deliberate, not an oversight

---

## Capability: substitution-probe (Change a — New)

### Requirement: Presence proven before mutation (condition 1)

The subcommand MUST confirm the guarded fact's literal is present at its
declared `(file, line)` before writing any mutation.

#### Scenario: Absent literal halts before any write

- GIVEN a guarded fact whose literal is not present at the declared line
- WHEN the subcommand attempts to mutate that fact
- THEN it halts `Unprobeable` naming the fact, and no write occurs

### Requirement: Write proven by digest before the drive runs (condition 2)

The subcommand MUST assert `sha256(after-write) != sha256(before-write)`
before invoking the observing run. A write producing identical bytes MUST
halt before any run.

#### Scenario: An edit that did not apply halts before observation

- GIVEN a mutation write that, due to a no-op edit, leaves the file's bytes
  unchanged
- WHEN the subcommand checks the pre/post digest
- THEN it halts `Unprobeable` for that fact and the observing run never
  executes

### Requirement: Bytecode purge holds for every substitution drive (condition 3)

Every observing run this subcommand launches MUST inherit the unconditional
purge from `driver-child-environment` (Change 0); it MUST NOT construct an
independent child environment of its own.

#### Scenario: A same-length mutation still executes fresh source

- GIVEN a guarded fact mutated to a literal of identical byte length
- WHEN the observing run executes against the mutated file
- THEN it runs against the new source, never a cached `.pyc`, because the
  child environment purges bytecode unconditionally

### Requirement: Guarded fact resolves to exactly one match (condition 4)

The subcommand MUST refuse `Unprobeable` a guarded fact whose declared
`(file, line, literal)` matches more than one location, or zero locations,
on the target line.

#### Scenario: Ambiguous match halts rather than guessing

- GIVEN a guarded fact literal that appears twice on its declared line
- WHEN the subcommand resolves the substitution site
- THEN it halts `Unprobeable` naming the ambiguity, and substitutes neither
  occurrence

### Requirement: Restoration confirmed by digest, never `git checkout --` (condition 5)

The subcommand MUST restore each mutated file via its recorded inverse
patch and MUST confirm restoration by sha256 equality against the
pre-mutation digest. It MUST NOT restore via `git checkout --`.

#### Scenario: A digest mismatch halts the sweep

- GIVEN a restore whose resulting bytes do not match the pre-mutation sha256
- WHEN the subcommand checks the digest after applying the inverse patch
- THEN the sweep halts `Unprobeable` and does not mutate the next guarded
  fact

### Requirement: Mutation inverts the asserted effect, not the comparison (condition 6)

The mutation MUST change the guarded fact's literal value. It MUST NOT
invert a comparison operator (for example `==` to `!=`) as a substitute for
changing the value.

#### Scenario: An equality assertion's value changes, its operator does not

- GIVEN a guarded fact expressed as an equality assertion over a literal
- WHEN the subcommand constructs the mutation
- THEN the literal's value changes and the comparison operator is untouched

### Requirement: The observing run matches the guarded fact's declared run (condition 7)

The subcommand MUST execute the exact declared harness and selector for
each guarded fact, and MUST run it separately per disjoint suite when the
repository has more than one.

#### Scenario: The declared suite runs, not a hand-picked subset

- GIVEN a guarded fact declared under the Python `unittest` suite in a
  repository that also has a Node suite
- WHEN the subcommand observes the mutation's effect
- THEN it runs the declared Python suite; a report attributing the
  observation to the Node suite alone is rejected

### Requirement: A green mutation is reported, never silently accepted (condition 8)

Every guarded fact whose mutation leaves its declared run green MUST
produce a finding under `## Not adjudicable` carrying `- Move: 6`,
`- Adjudication: not adjudicable`, and a `- Remedy:` from the existing
delete/update/undecided vocabulary.

#### Scenario: An obsolete-looking guard is reported, not dropped

- GIVEN a guarded fact mutation that leaves its declared run green
- WHEN the subcommand finishes the drive
- THEN the emitted report contains a `## Not adjudicable` finding with that
  fact's Move-6 fields, and the run is never reported as clean

### Requirement: A green mutation states which cause it could not rule out (condition 9)

Every Move-6 not-adjudicable finding's remedy reason MUST name one of
three causes — obsolete guard, equivalent mutant, or degenerate fixture —
or explicitly state that none could be determined. `check-report` MUST
reject a not-adjudicable Move-6 finding whose reason names none of the
three and carries no such statement.

#### Scenario: A reason with no named cause fails validation

- GIVEN a not-adjudicable finding whose `- Remedy: undecided:` reason text
  identifies none of the three causes
- WHEN `check-report` validates the report
- THEN validation fails — stricter than today's check, which accepts any
  non-empty reason string

### Requirement: A red mutation states reachability, never coverage (condition 10)

Every substitution-probe finding, red or not-adjudicable, MUST carry an
explicit statement that the result proves the guarded fact's lock fires
(reachability), never that every consumer of the fact was exercised
(coverage). `check-report` MUST reject a substitution-probe report that
omits this statement.

#### Scenario: A report with no reachability statement fails validation

- GIVEN a report containing a red Move-6 finding and no reachability-versus-
  coverage statement anywhere in the report
- WHEN `check-report` validates the report
- THEN validation fails

### Requirement: The observing run is proven green before any mutation (condition 11)

Added by the design phase, which measured the hole: conditions 1–10 prove the
*bytes* changed and then read the observing run's colour, but nothing required
that run to have been green beforehand. Against an already-red suite every
guarded fact reports `fires`, and the probe announces a roster of working locks
having proven nothing — `green-because-nothing-happened` inverted, and the exact
defect class this subcommand exists to catch.

The subcommand MUST drive the observing run once, unmutated, before the first
substitution, and MUST refuse the whole sweep as `Unprobeable` with
`kind=baseline-not-green` when that run is not green. The baseline result MUST
NOT be reported as a finding — an inability to look is never a verdict about the
subject. The baseline drive MUST go through the same constructed child
environment as every substitution drive, so condition 3 holds for it too.

#### Scenario: A red baseline refuses the sweep instead of reporting locks

- GIVEN a subject whose observing run already fails before any mutation
- AND a recipe declaring two guarded facts
- WHEN the substitution probe runs
- THEN the sweep is refused `Unprobeable` with `kind=baseline-not-green`
- AND no file is mutated
- AND no finding is emitted for either fact

#### Scenario: A green baseline is not counted as a finding

- GIVEN a subject whose observing run is green
- WHEN the substitution probe runs and every declared fact goes red on mutation
- THEN the report carries one finding per guarded fact
- AND carries no finding derived from the baseline drive itself

### Requirement: Guarded facts are sourced only from the recipe's `mutations` block (v1 scope)

The subcommand MUST source every guarded fact from the invoking probe
recipe's own declared `mutations` block. It MUST NOT derive guarded facts
from a subject's own lock roster in v1.

#### Scenario: A recipe with no `mutations` block refuses, not finds zero

- GIVEN a probe recipe with no declared `mutations` block
- WHEN the subcommand is invoked against it
- THEN it refuses `Unprobeable` naming the missing block, rather than
  reporting zero guarded facts

### Requirement: The sweep is capped, and overflow is stated

The subcommand MUST drive at most 8 guarded facts per run, serial, each
restored before the next begins. Facts beyond the cap MUST be named
individually under `## Unchecked`, never silently dropped.

#### Scenario: Ten declared facts yield eight driven and two named

- GIVEN a recipe declaring 10 guarded facts
- WHEN the subcommand runs
- THEN exactly 8 are driven and the remaining 2 are each named under
  `## Unchecked`

### Requirement: Exit-code contract

The subcommand MUST exit `0` for any verdict, a not-adjudicable finding
included, and MUST exit `2` only for an inability to look (missing
`mutations` block, ambiguous match, restore-digest mismatch, or a drive
that writes outside its own box).

#### Scenario: An all-obsolete drive still exits 0

- GIVEN a drive whose every guarded fact mutation leaves the suite green
- WHEN the subcommand exits
- THEN the exit code is `0`; a restore-digest mismatch on any one fact
  instead exits `2`

### Requirement: `SKILL.md`'s Move 6 detail states v1's actual scope

The Move 6 detail section MUST state that v1 sources guarded facts only
from a recipe's `mutations` block (never the subject's own lock roster) and
performs no AST-based delete/update classification. Every v1
not-adjudicable finding MUST carry `- Remedy: undecided: <reason>`, never
`delete` or `update`, until a later change ships that classifier.

#### Scenario: Doctrine does not overclaim v1's capability

- GIVEN `SKILL.md`'s existing Move 6 prose describes AST existence-checking
  deciding delete-versus-update mechanically
- WHEN v1 ships without that classifier
- THEN `SKILL.md` is updated in the same commit to state v1's narrower
  scope, so the doctrine never claims a capability the shipped code lacks

### Requirement: New subcommand and recipe ship with their `SKILL.md` rows

The subcommand's row in "The subcommands" table, its exit-code paragraph,
its self-probe recipe file, and that recipe's row in "The shipped files"
table MUST land in the same commit as the subcommand's code.

#### Scenario: The self-probe finds no `unregistered` gap

- GIVEN the new probe recipe file exists on disk after this change lands
- WHEN the skill's own `roster` self-probe runs against `SKILL.md`'s
  shipped-files table
- THEN the recipe's row is present and `unregistered` does not fire

---

## Capability: report-shape (Change a — Modified)

### Requirement: The shipped example report reflects the new finding shape

`references/example-report.md` MUST include a Move-6 not-adjudicable
finding whose `- Remedy:` reason names one of the three condition-9 causes,
and the report MUST carry the condition-10 reachability-not-coverage
statement, so the shipped example remains valid input to the widened
`check-report`.

#### Scenario: The shipped example still validates after the widening

- GIVEN `check-report` is widened to require the condition-9 cause
  statement and the condition-10 reachability statement
- WHEN `check-report` validates `references/example-report.md`
- THEN validation passes without modification at read time

---

## Capability: probe-recipe-coverage (Change b — Modified)

> Not listed under either "New Capabilities" or "Modified Capabilities" in
> `proposal.md`'s Capabilities section, despite Change b having its own
> scope table and success-criteria line. Named here for spec completeness;
> reported back as a proposal gap.

### Requirement: No new code in this change (NARROWED)

> **Measured false as originally written.** Two requirements inside this same
> capability -- per-step digests and filesystem-versus-roster enumeration --
> cannot be reached through recipe grammar alone, so they move to
> `audit-scope-hardening` where they are implemented as code. What remains
> here is recipe-only, and its forecast holds only for what remains.

The recipe-only part of this change MUST NOT alter `scripts/audit_cli.py`
or any other shipped code. Every finding it reaches MUST be reachable purely through new or
widened `references/probes/*.json` recipes against the shipped subcommand
grammar.

#### Scenario: An unreachable defect is reported as a grammar gap, not coded around

- GIVEN a defect shape that cannot be expressed in the shipped recipe
  grammar
- WHEN this change is scoped
- THEN the change reports that grammar gap as its own finding rather than
  adding code to close it

### Requirement: Duplicated-constant recipe, conditional on a driveable producer

IF a driveable surface's refusal message emits the closed set containing
the thrice-spelled constant, this change MUST ship a `roster` recipe
reaching it via `restatement_of`/`duplicated`. IF no such driveable surface
exists, the change MUST report `no-closed-roster` as the finding, not omit
the attempt.

#### Scenario: No producer yields an honest gap, not silence

- GIVEN the constant lives only in a test helper with no refusal message
  and no producer inside `--subject`
- WHEN the recipe is written against the shipped grammar
- THEN the finding is `no-closed-roster`, reported as a first-class result

### Requirement: Ordering defect reachable via `walkthrough`

This change MUST ship or extend a `walkthrough` recipe naming, in
documented order, the step whose declared expectation is sunk by an
earlier step's own correct-in-isolation check — including the fuller-set
re-check's fourth defect, two separately-documented decisions that combine
to block every launch with a false refusal.

#### Scenario: The sunk step is named as the stall

- GIVEN two separately-documented decisions that are each correct alone
  and, combined, block every launch with a false refusal message
- WHEN the widened `walkthrough` recipe drives the documented flow in order
- THEN the step whose expectation is contradicted is named as the stall,
  and every step after it is `unreached`

### Requirement: Undemanded declaration reachable via `structure`'s from-zero stage

This change MUST ship or extend a `structure` recipe whose from-zero side
proves a declared requirement is never actually demanded of a repository
built from nothing.

#### Scenario: An undemanded declaration surfaces, not agrees silently

- GIVEN a declaration exists in documentation but no from-zero build step
  ever asks for it
- WHEN `structure`'s from-zero comparison runs
- THEN the undemanded declaration surfaces as a finding

### Requirement: A driven step that reports success while producing nothing is a finding (SUPERSEDED)

> **Superseded by `audit-scope-hardening`'s "A driven step is graded on what
> it wrote", which is a strict superset.** Kept so the duplication is visible
> rather than silently deleted; the later requirement is the one to implement,
> and it corrects this one's target: `walkthrough` runs every step with its
> cwd inside the box, so digesting the SUBJECT tree fires on every step of
> every flow. The box is what is digested; a change to the subject is an
> escape, which `walkthrough` gates nowhere today.

Added after a live run: an operator drove a six-step flow, every step
reported success, and the flow was declared complete while three of the
subject's seven notebooks — twenty-two code cells — had never executed. One
step had additionally reported exit `0` after its interpreter failed on a
path, writing no ledger event at all.

When a recipe drives a flow step by step, the audit MUST take a digest of
the subject tree before and after each step, and MUST report any step that
reports success while leaving the tree byte-identical. **A step that
returned is not a step that produced.**

This needs no knowledge of the subject's domain, which is the point: it
reaches "the interpreter never ran" and "the product was never written"
through the same generic observation, without the recipe naming a single
artefact kind.

The digest MUST cover the subject tree, not the step's own declared output
path — a step writing its product somewhere the recipe did not anticipate
is a finding, not an exemption. A step documented as read-only MUST be
declarable as such in the recipe, and an unchanged tree is then the
expected result rather than a finding; a step with no such declaration
defaults to producing.

#### Scenario: A step that returns zero and changes nothing is named

- GIVEN a flow whose second step reports success
- AND the subject tree digest is identical before and after that step
- AND the recipe does not declare that step read-only
- WHEN the audit drives the flow
- THEN that step is reported as having produced nothing
- AND the report states that success was claimed

#### Scenario: A declared read-only step is not a finding

- GIVEN a step the recipe declares read-only
- WHEN it reports success and leaves the tree unchanged
- THEN no finding is emitted for it

### Requirement: Artefacts on disk that the flow's declared roster never names

The defect this skill exists for, aimed at products rather than
subcommands: a flow validates the artefacts its own declarations name, so
an artefact nobody named is never validated and the flow still reports
complete.

When a recipe declares the artefact kind a flow produces, the audit MUST
enumerate that kind across the subject tree, subtract the roster the flow's
own declarations name, and report the remainder. The remainder MUST be
reported whether or not it is empty, so a reader learns what the check
watches rather than meeting it only on failure.

The enumeration MUST come from the filesystem and the roster from the
subject's own declarations — deriving both halves rather than reading
either, as this skill already does for subcommands.

#### Scenario: Unnamed artefacts of a produced kind are reported

- GIVEN a subject tree carrying seven artefacts of the declared kind
- AND the flow's own declarations name four of them
- WHEN the audit runs
- THEN the three unnamed artefacts are reported as unvalidated
- AND the report distinguishes them from artefacts that were named and failed

#### Scenario: A complete roster still states what it covered

- GIVEN every artefact of the declared kind is named by the flow
- WHEN the audit runs
- THEN the report states the enumeration and the roster matched, with counts

---

## Capability: audit-scope-hardening (Change c — Modified)

Seven requirements added after a four-day session in which this repository's
other skill was repaired eleven times. Each attaches to a move or stage that
already ships; only the last introduces a surface the eleven moves do not
cover. Every incident cited is measured, not hypothetical.

### Requirement: The audit measures an enumerator's reach, not only its result (Move 0)

Move 0 enumerates a closed surface from both sides. That is correct and is
not what failed. What failed four times in one session is that **one side was
enumerated more narrowly than the claim the check asserted**, in checks whose
own names and docstrings said they derived:

- an enumerator of refusal codes walked one function-name prefix inside one
  file, so 42 codes raised in helper modules were invisible to it — and the
  roster built from it was reported as complete;
- a check documented as *"enumerated from the signature and not from a
  hand-written list"* iterated one module's namespace and skipped any function
  without a particular parameter, missing nine writers;
- a helper collecting "the notebooks the steps run" collected any string
  literal with that suffix anywhere in the file, so a mutation that replaced
  the call while leaving the literal in place survived it;
- a check asserting "the notebooks the steps name exist" hand-listed four
  names and lagged reality by two.

`roster` MUST report, for any check the subject declares as complete over a
set, whether that check's iteration source is derived or bounded — a literal
collection, a single module's namespace, or a subset filtered before the
assertion. A check whose stated claim is universal and whose enumeration is
bounded MUST be reported with both facts side by side.

**A check that says it derives and enumerates by hand is worse than no check**,
because nobody looks at it again. That is the whole finding.

#### Scenario: A universal claim over a bounded enumeration is reported

- GIVEN a check whose name or docstring states a claim over every member of a
  set
- AND whose iteration source is a literal collection
- WHEN `roster` audits the subject
- THEN both the stated claim and the bounded enumeration are reported together

#### Scenario: A derived enumeration is reported as derived

- GIVEN a check whose iteration source is computed from the subject
- WHEN `roster` audits the subject
- THEN it is reported as derived and is not a finding

### Requirement: A guard is reachable for every member of the set it guards (Move 0)

A guarded vocabulary is a closed set, so it is Move 0's subject. Measured on a
shipped guard: its matcher was a word-boundary pattern, and

- the pattern for a singular term did not match that term's plural, leaving a
  live leak in an asset the skill ships to every new repository;
- the underscore is a word character in that pattern language, so **no**
  word-boundary rule could ever reach an identifier joining the guarded term to
  another word.

For every member of a guarded set, `roster` MUST derive that member's
identifier-boundary variants — plural, underscore-joined, case-joined — and
report any variant the guard's own matcher cannot reach. A guard that cannot
reach a member of the set it guards is the finding.

#### Scenario: An unreachable variant is named

- GIVEN a guarded term whose matcher is a word-boundary pattern
- WHEN the audit derives that term's underscore-joined variant
- THEN the variant is reported as unreachable by that guard

### Requirement: Renaming is not generalising (Move 0)

The same session renamed 853 occurrences of a leaked vocabulary and the
occurrences were still specific to one subject afterwards: the identifiers had
changed and the content had not. A guard satisfied by a rename measures
spelling, not leakage.

Where a guard's subject is content rather than identity, the audit MUST report
that the guard's matcher tests identity — so a reader learns which of the two
was measured. It MUST NOT attempt to adjudicate whether content is specific;
that is a reading, and a check that guessed would spend its credibility on the
wrong ones.

#### Scenario: An identity matcher over a content claim is reported

- GIVEN a guard whose declared subject is content
- AND whose matcher tests identifiers
- WHEN the audit runs
- THEN it reports that identity was measured and content was not

### Requirement: The from-zero drive demands what the subject reads (Stage 2)

Stage 2 drives the subject from ignorance. It measures that the drive runs. It
does not measure whether everything the subject **reads** from its own target
is **demanded** when that target is built from nothing.

Measured: a skill read ten declarations from every repository it drove, and its
scaffolding path demanded none of them. A repository built from zero was
therefore silently missing all ten, and two defects that those declarations
would have caught went undetected until a human compared digests by hand.

During the stage-2 drive the audit MUST record every declaration the subject
reads from its target, subtract those the subject's own from-zero path demands,
and report the remainder — naming, per item, the declaration, where it belongs,
and the consequence of its absence. The remainder MUST be reported whether or
not it is empty.

#### Scenario: A read-but-never-demanded declaration is named

- GIVEN a subject that reads a declaration from its target during the drive
- AND whose scaffolding path never demands it
- WHEN stage 2 completes
- THEN that declaration is reported with its location and its consequence

### Requirement: An artefact is judged by what it shows (Stage 2)

Only a real drive produces artefacts, so this attaches to stage 2 and not to a
static check.

Measured: a flow reported a run complete while three of its seven rendered
artefacts had never executed — twenty-two units of content producing nothing.
Every declared check passed. It was found because a human opened the files.

After the stage-2 drive the audit MUST enumerate the artefacts the drive
produced and report, per artefact, whether it carries content — an executed
artefact whose units produced no output, or a produced file of zero length, is
reported as produced-but-empty. Existence is not the measurement.

#### Scenario: A produced artefact with no content is reported

- GIVEN a drive that produces a rendered artefact whose units carry no output
- WHEN stage 2 reports
- THEN that artefact is reported as produced-but-empty, distinctly from absent

### Requirement: A driven step is graded on what it wrote (Move 8)

`walkthrough` drives a documented flow in order and names the first step whose
expectation breaks. A step that reports success while writing nothing, or while
writing into another step's tree, breaks no stated expectation and is not named.

Both were measured in one session, both reported success, both passed every
check, and both were caught only by a digest comparison written by hand in a
throwaway script.

`walkthrough` MUST take a digest of the subject tree before and after each
driven step and report, per step, whether anything changed and whether the
change fell inside the roots that step declares. A step the recipe declares
read-only is exempt and MUST be declarable as such; a step with no such
declaration defaults to producing.

#### Scenario: A step that returned having written nothing is named

- GIVEN a driven step that reports success
- AND the subject tree digest is unchanged across it
- AND the recipe does not declare that step read-only
- THEN the step is reported as having produced nothing

#### Scenario: A step that wrote outside its declared roots is named

- GIVEN a driven step that declares its output roots
- AND writes only outside them
- THEN the step is reported as having written into a tree it does not own

### Requirement: A reported state names its exit (new surface)

The eleven moves all ask whether the subject is correct. None asks whether the
subject lets its operator out.

Measured on a sibling skill: of 51 reported keys naming a state a human must
act on, 8 had a mechanical exit and none published it; the rest correctly
publish none, because their exit is a human authoring act. Getting out of one
of the eight required reading the skill's own documentation, finding a payload
shape by grepping its test suite, and rebuilding an input by hand.

The audit MUST report, per state the subject names, whether a mechanical exit
exists and whether it is published. A state whose exit is a human judgement
MUST be reported as such and is not a finding — publishing a command for a
judgement would be worse than the silence.

**A published exit that cannot be run is not an exit.** Where the audit
verifies publication, it MUST verify by executing the published act, not by
asserting a field is present.

#### Scenario: An unpublished mechanical exit is a finding

- GIVEN a reported state with a mechanical exit the subject does not publish
- WHEN the audit runs
- THEN it is reported, and the exit it found is named

#### Scenario: A judgement-only state is not a finding

- GIVEN a reported state whose only exit is a human authoring act
- THEN it is reported as such and produces no finding
