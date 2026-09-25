# Delta for experimental-implementation-skill

## MODIFIED Requirements

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

## ADDED Requirements

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
