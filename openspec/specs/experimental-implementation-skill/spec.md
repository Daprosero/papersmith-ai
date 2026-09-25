# experimental-implementation-skill Specification

## Purpose

The second skill built on the shared `_core/implementation/engine/implementation_engine.py`.
It ships its own domain profile, its own north, and its own two agents — mirroring
`proposal-implementation`'s Cut-1/Cut-2 shape exactly, the way `experimental-deliberation`
mirrors `proposal-deliberation` on the TS side. This capability governs Slice A only:
a **single** declared document. Per-document claim vocabulary, cross-document agreement,
the experiments-successor composer, and `Data/` per product folder are follow-on work
(changes B, C, D) and are explicitly not governed here — no `documents[1]` entry ships
under this capability.

## Requirements

### Requirement: The Skill Declares Its Own Domain Profile

`experimental-implementation/impl_profile.py` MUST exist and validate against the same
resolver tier `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` enforces for any profile, declaring
its own `kit`, `cli`, `objective`, `provenance`, `findings`, `vocabulary`, exactly one
`documents` entry, and its own declared holder leaf (filename plus heading
scaffold). It MUST NOT ship a `profile.ts`.
(Previously: the enumeration named seven sections — `kit`, `cli`, `objective`,
`provenance`, `findings`, `vocabulary`, `documents` — with no holder leaf.)

#### Scenario: The profile resolves and validates
- GIVEN `IMPLEMENTATION_DOMAIN_PROFILE` points at this skill's `impl_profile.py`
- WHEN the shared engine imports it
- THEN every required leaf validates and no refusal is raised

#### Scenario: A missing leaf refuses by its own name
- GIVEN a required leaf omitted from this skill's profile
- WHEN the engine loads it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming that exact leaf

#### Scenario: The declared holder leaf validates as `Experimental_AGREED.md`
- GIVEN this skill's profile declares its holder leaf as
  `Experimental_AGREED.md` with its heading scaffold
- WHEN the engine loads the profile
- THEN the leaf validates and no refusal is raised

#### Scenario: An omitted holder leaf refuses by its own name
- GIVEN this skill's profile with every other required leaf present but the
  holder leaf omitted
- WHEN the engine loads it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming the holder
  leaf exactly

### Requirement: One Skill, One North — No Dual Declaration

A skill declaring `OBJECTIVE_FLOW` in Python and an `objective` in `profile.ts` MUST be
rejected by `declared_objective`, never silently resolved to one source.

#### Scenario: This skill has no profile.ts to collide with
- GIVEN `experimental-implementation` ships only `impl_profile.py`
- WHEN `declared_objective("experimental-implementation")` runs
- THEN it returns the Python `OBJECTIVE_FLOW`, raising nothing

#### Scenario: A planted profile.ts is caught
- GIVEN a `profile.ts` is added beside this skill's `impl_profile.py`, both declaring an objective
- WHEN `declared_objective` runs
- THEN it raises, naming the skill, before either source is picked

### Requirement: The North Belongs To This Skill Alone

`OBJECTIVE_FLOW` MUST be a module-level literal physically inside this skill's own
directory tree, with stages and an arrival distinct from `proposal-implementation`'s —
never the sibling's stages, never its arrival, and never read from the shared engine.

#### Scenario: Discovery finds this skill's own flow
- GIVEN `tests/test_agents.py`'s cross-skill north lock walks this skill's tree
- WHEN it discovers `OBJECTIVE_FLOW`
- THEN the returned stages and arrival differ from `proposal-implementation`'s

#### Scenario: A missing north is refused, not inherited
- GIVEN `OBJECTIVE_FLOW` is removed from this skill's tree
- WHEN the north lock runs
- THEN `declared_objective("experimental-implementation")` returns `None`, and the
  agent-binding tests for this skill fail — the flow is never silently borrowed from
  the sibling or the engine

### Requirement: The Two Agents Carry No Logic And Bind To This Skill's Own Stage

The build- and walk-equivalent agents MUST each be a thin, ~70-line file with no
executable logic beyond loading this skill's `SKILL.md`. The build-equivalent's
`stretch:` frontmatter value MUST name a stage present in this skill's own
`OBJECTIVE_FLOW`, never a stage from any other skill's north.

#### Scenario: A stretch naming a foreign stage is refused
- GIVEN the build-equivalent agent's `stretch:` names a stage that exists only in
  `proposal-implementation`'s `OBJECTIVE_FLOW`
- WHEN `tests/test_agents.py` validates agent bindings
- THEN it fails, naming the unresolvable stretch

#### Scenario: A correctly bound stretch passes
- GIVEN the `stretch:` value names a stage this skill's own `OBJECTIVE_FLOW` declares
- WHEN agent-binding tests run
- THEN they pass

### Requirement: Two Documents Reproduce Document 0's Byte-Identical Guarantee, Each With Its Own Claim Vocabulary

This skill's profile MUST declare exactly two `documents` entries: document 0
(the experiments document, unchanged from Slice A) and document 1 (the
mathematical proposal). Document 0 MUST remain byte-identical in behavior to
its pre-capability form — it declares no per-document vocabulary override, so
it keeps resolving from the top-level `provenance.*`/`findings.*` scalars, the
same resolver tier, the same refusal set, the same digest-moving rules per
changed leaf. Document 1 MUST declare its own per-document claim vocabulary
naming the mathematical proposal's claims as its own kind, never inheriting
document 0's experiments vocabulary by omission passing silently as agreement.
(Previously: this skill declared exactly one `documents` entry for Slice A;
under `len(documents) == 1` its single entry was required to behave like
`proposal-implementation`'s own index-0.)

#### Scenario: Document 0 behaves like index 0, unchanged
- GIVEN this skill's `documents[0]` entry, unchanged from Slice A
- WHEN a leaf under it is omitted
- THEN the refusal names `documents[0]`, not a bare `documents`, and the
  refusal set is unchanged from Slice A

#### Scenario: Document 1 declares and uses its own vocabulary
- GIVEN this skill's `documents[1]` entry declares its own `claim_key`
  naming the mathematical proposal's own claim kind
- WHEN the resolver resolves it and the fold reads it
- THEN document 1's fidelity fold and citation matching use its own
  declared values, never document 0's experiments vocabulary

#### Scenario: This skill's own directory is scanned for leakage the day it appears
- GIVEN `tests/forge_vocabulary.py::shipped_documents()` walks every file
  under `.claude/skills/`
- WHEN this skill's directory (now with two documents) is present
- THEN both documents' declared text is scanned in the same run, with no
  opt-out

### Requirement: A Two-Document Guarantee Is Proven By Reading, Not By Counting

The mechanism that previously guaranteed a single declared document (a
shipped-surface test asserting every discovered profile declares exactly
one `documents` entry) MUST be deleted and replaced by a check proving
each of this skill's declared documents' own claim vocabulary is actually
read and threaded into that document's own fidelity result and citation
matching. A count-only check (asserting `len(documents) == 2` alone) MUST
NOT stand in as evidence that the per-document read happened.

#### Scenario: The replacement lock demonstrates the read, not the count
- GIVEN this skill's two declared documents, each with its own claim
  vocabulary
- WHEN the replacement lock runs
- THEN it demonstrates, via the drift-control fixture, that document 1's
  fidelity status changes when document 1's own text changes while
  document 0 stays clean

#### Scenario: A reverted fold is caught even though the document count is still two
- GIVEN a mutation that reverts the fold's per-document derivation while
  both documents remain declared
- WHEN the replacement lock runs
- THEN it fails, because a documents-count check alone cannot detect the
  reversion

### Requirement: `documents[0]` Declares Its Real Dataset Marker, Landed Last

`experimental-implementation`'s `documents[0]` (the experiments document)
MUST declare a real `dataset_marker` value, added only after
`implementation-data-demandability`'s detector, threading, and `missingDirs`
scenarios are already proven green against a fixture profile the shipped
engine could not otherwise pass. `documents[1]` (the mathematical proposal)
MUST declare `dataset_marker: None` permanently — the mathematical domain
binds to no dataset, and this is a recorded decision, never a silent
omission.

#### Scenario: The real marker lands after the fixture proves the mechanism
- GIVEN the fixture profile's dataset scenarios all pass
- WHEN `documents[0]`'s real `dataset_marker` is declared
- THEN it is this capability's last write to `impl_profile.py`

#### Scenario: `documents[1]` never owes a dataset
- GIVEN `documents[1]`'s `dataset_marker: None` declaration
- WHEN the dataset detector runs for `documents[1]`
- THEN it answers false unconditionally, and `documents[1]`'s `Data/` is
  never demanded

### Requirement: `SKILL.md` States The Dataset-Declared `Data/` Demand, Per Product Folder

`SKILL.md` MUST state that a document declaring a dataset makes `{name}/Data/`
demanded for that product folder, that the demand is presence-only, and that
it is scoped per product folder — never to the repository as a whole —
because a run binds to one method via `--name` and a later paper may move to
a different area entirely.

#### Scenario: The stated demand matches the enforced behavior
- GIVEN `SKILL.md`'s updated text
- WHEN compared against `cmd_verify`'s actual `with_data` derivation and
  `expected_dirs`'s per-`{name}` shape
- THEN the stated demand (presence-only, per product folder) matches what is
  enforced, with no claim the engine does not also do

### Requirement: `SKILL.md` No Longer Lists `compose`/`admit` As Unavailable

`SKILL.md`'s "Which commands are not available yet, and why" section MUST
drop its `compose`/`admit` entry once this domain declares a block locator
and those two commands become sealed cases. The section's remaining entry
(`materialize --stage scaffold`, which reads `assets/kit/`, unrelated to
the locator) MUST remain, since this change does not add a kit.

#### Scenario: The compose/admit entry is gone
- GIVEN this capability landed
- WHEN `SKILL.md`'s "not available yet" section is read
- THEN it no longer names `compose`/`admit`, and the stated reason matches
  what the shipped profile actually declares

#### Scenario: The stated availability matches what runs
- GIVEN `SKILL.md`'s updated text
- WHEN `compose`/`admit` are invoked against this skill's target
- THEN they run, rather than refusing as an unavailable command

### Requirement: `SKILL.md` Carries A Tutor Bullet For The Third, Unchecked Discrepancy Kind

`SKILL.md` MUST document, as guidance for the reading agent rather than as
a mechanical check, the third disagreement kind: an experiment's metric or
protocol does not correspond to what the claim it cites actually asserts.
No check MUST attempt to judge this — it requires reading both documents'
prose, and a check that tried would block correct work as often as it
caught broken work.

#### Scenario: The bullet exists and names no check
- GIVEN `SKILL.md`'s updated text
- WHEN it is read
- THEN it states the third kind as something for the agent to notice
  while reading, and no requirement in any capability of this change
  implements it as a refusal

#### Scenario: A metric/protocol mismatch does not refuse
- GIVEN an experiment whose declared metric does not match its cited
  claim's actual assertion, with the citation itself otherwise resolving
- WHEN the crossing check runs
- THEN it does not refuse for this mismatch — only Kind 1, Kind 2, and the
  no-crossing-declared code refuse

### Requirement: `SKILL.md` Documents Flow B's Existing Path Through To A Test Submission

`SKILL.md` MUST document that this skill reuses `proposal-implementation`'s
existing Flow B — the same gate at its drift step (asking whether the user
made the changes, never inferring it), the same path from a green suite
through to a submission — rather than defining a second, competing flow
for the experiments document. No new flow step MUST be invented here that
duplicates a decision Flow B already asks.

#### Scenario: The documented flow points at the existing one
- GIVEN `SKILL.md`'s updated text
- WHEN it describes the path from implementation to a test submission
- THEN it names Flow B's existing steps and gate, not a new parallel
  sequence

#### Scenario: The drift gate is not duplicated
- GIVEN a code/proposal discrepancy reaches the point where repair
  direction matters
- WHEN the flow is followed
- THEN the same "did the user make this change" gate Flow B's drift step
  already asks is the one exercised — no second gate asks it again
### Requirement: The Skill Ships `references/usage.md` Documenting Its Holder Obligations

`skills/experimental-implementation/references/usage.md` MUST exist and MUST
state this skill's holder obligations — the declared filename, the
create-on-absent behavior, and the write-refusal-into-an-undeclared-holder
behavior — matching the holder obligations already documented in its twin's
`skills/proposal-implementation/references/usage.md`, scoped to the holder
concern only. This directory does not exist for this skill today.

#### Scenario: The file exists where none did before
- GIVEN this skill's directory had no `references/` folder before this
  capability
- WHEN this capability lands
- THEN `skills/experimental-implementation/references/usage.md` exists

#### Scenario: The stated obligations match the shipped holder behavior
- GIVEN this skill's declared holder name and its resolution behavior
- WHEN `references/usage.md`'s holder section is compared against the
  shipped `cmd_settle`/`cmd_position` behavior for this skill
- THEN the stated filename, create-on-absent behavior, and write-refusal
  behavior all match what is actually enforced

#### Scenario: The new document does not exceed its holder scope
- GIVEN `references/usage.md` is written for this capability
- WHEN its content is compared to its twin's full `references/usage.md`
- THEN it documents this skill's holder obligations without mirroring the
  twin's unrelated sections (e.g. kit assets this skill does not ship)
