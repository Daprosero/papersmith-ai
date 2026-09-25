# implementation-holder-repair Specification

## Purpose

A target's holder may already be poisoned before this change ships — a
`documents=` header group was written into it by one profile and it now
mismatches another profile's declared document count. This capability
governs the D4 forward path for such a target: repair the existing holder,
or give the target its own newly declared holder, and — where the evidence
does not determine which action is correct — stop and surface a named human
decision rather than guessing. It builds on the document-count comparison
`implementation-declared-holder` reuses, extracted here as a shared
predicate.

## Requirements

### Requirement: The Document-Count Comparison Is A Named, Shared Predicate

The `len(DOCUMENTS)`-vs-`documents=` header group count comparison, today
inline only in `cmd_position`'s write-path holder sweep, MUST be extracted
into a named, shared helper function. `cmd_position`'s existing check MUST
call this helper rather than re-deriving the comparison inline, and this
capability's repair-decision path MUST call the same helper.

#### Scenario: The existing check is unaffected by the extraction
- GIVEN a header whose `documents=` group count disagrees with
  `len(DOCUMENTS)`
- WHEN `cmd_position`'s holder sweep runs
- THEN `POSITION_HEADER_DOCUMENT_COUNT_MISMATCH` fires exactly as it does
  today, now via the shared helper

#### Scenario: The repair path uses the same helper, not a re-derived expression
- GIVEN a target whose holder header disagrees with the current skill's
  declared document count
- WHEN the repair-decision path evaluates that target
- THEN it calls the same shared helper `cmd_position` calls, not an
  independently written comparison

### Requirement: A Poisoned Target May Be Repaired Or Given Its Own Declared Holder

For a target whose existing holder mismatches the current skill's declared
document count, the mechanism MUST offer a forward path: repairing the
existing holder's header to match the current skill's declared document
count, or creating this skill's own separate declared holder for the target.
The mechanism MUST NOT leave the target permanently refused with no forward
path when the correct action is determinable from the evidence.

#### Scenario: An unambiguous repair proceeds
- GIVEN a poisoned target where the evidence unambiguously supports repairing
  the existing holder's header
- WHEN the repair path runs
- THEN the header is repaired to match the current skill's declared document
  count, and the target subsequently reads clean

#### Scenario: An unambiguous create-new proceeds
- GIVEN a poisoned target where the evidence unambiguously supports creating
  this skill's own separate declared holder instead of touching the existing
  one
- WHEN the repair path runs
- THEN this skill's declared holder is created, and the existing poisoned
  holder is left untouched

### Requirement: An Ambiguous Repair Case Stops With A Named Human Decision, Writing Nothing

When the evidence does not determine whether repairing the existing holder
or creating a new declared holder is correct, the mechanism MUST stop with a
named refusal code and a question presented to the human, and MUST NOT write
to either the existing holder or a newly created one until the human
decides. This refusal MUST be reachable — proven by mutating the ambiguity
guard away and observing the mechanism guess instead of stopping.

#### Scenario: An ambiguous target stops rather than guessing
- GIVEN a poisoned target where the evidence does not determine repair vs.
  create
- WHEN the repair path runs
- THEN it stops with a named refusal code and a question naming the
  ambiguity, and no file is written

#### Scenario: The stop is reachable by mutation
- GIVEN the ambiguity-detection guard is disabled by mutation
- WHEN the same ambiguous target is evaluated
- THEN the mutated build picks an action instead of stopping, proving the
  guard is what forces the stop

#### Scenario: No silent automatic repair occurs
- GIVEN any poisoned target, ambiguous or not
- WHEN the repair path runs without an explicit human decision already
  recorded for an ambiguous case
- THEN no write happens unless the case was unambiguous or the human
  decision was given

## Known Limitation Carried Forward From Scope (not governed by this capability)

The read-side `documents=`-count comparison in `position_state` (read by
`verify`, `probe`, `discuss`, `gate`, `offer`, `close`, `step`) is out of
scope for this change, per `implementation-document-binding`'s standing
position that a reader MUST NOT refuse for this condition. Consequently, a
target poisoned before this capability ships continues to read as clean
under those six commands and is only caught by `position`'s write-path
sweep, until this capability's repair path is run against it. This window
closes by repair, not by an added read-side refusal, and is documented here
so it is not mistaken for an oversight.
