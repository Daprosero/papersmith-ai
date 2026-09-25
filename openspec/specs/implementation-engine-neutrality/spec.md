# implementation-engine-neutrality Specification

## Purpose

The implementation CLI engine serves no domain of its own. Cut 1 moves the
17,100-line CLI verbatim to `_core/implementation/engine/implementation_engine.py`,
mirroring `_core/deliberation/engine/domain-profile.ts`: it resolves its host
from `IMPLEMENTATION_DOMAIN_PROFILE`, refuses to start without one, and
sources `kit.root` and its published CLI path from the host rather than its
own file location. Governs Cut 1 only — not the 167 domain-specific lines
(Cut 2) or the scalar→pair revision shape (Cut 3).

Four product decisions are deferred to design (whether `kit.root` is a
profile field or launcher-passed; minimal vs. full Cut-1 field set; whether a
Python profile-lock belongs here; whether the `sys.path` site becomes a
profile field). Every requirement below holds under any answer: the host,
never the engine's own file location, supplies the root; an unused field is
not required and is not mutation-provable, so it must not be treated as
satisfying a requirement.

## Requirements

### Requirement: Engine Refuses To Start Without A Domain Profile

The engine MUST fail closed, with a named refusal, when `IMPLEMENTATION_DOMAIN_PROFILE`
is unset, non-absolute, or resolves to a module missing a required field — now including
the ten Cut-2 domain fields and the declared holder leaf (filename plus heading
scaffold), alongside Cut 1's `kit.root`, `cli.path`, `objective`. It
MUST NOT default to any domain, and MUST NOT default to any holder filename
of its own.
(Previously: validated Cut 1's three fields and the ten Cut-2 domain fields,
with no holder leaf.)

#### Scenario: Unset variable refuses
- GIVEN `IMPLEMENTATION_DOMAIN_PROFILE` is unset
- WHEN the engine is imported
- THEN it raises a named refusal before any command runs

#### Scenario: Malformed profile refuses
- GIVEN the variable is relative, or the module omits a required field
- WHEN the engine loads it
- THEN it raises a refusal named for that exact case

#### Scenario: A missing Cut-2 leaf refuses by its own dotted name
- GIVEN a profile carrying Cut 1's three fields but omitting `vocabulary.artifact_noun`
- WHEN the engine loads it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming that leaf

#### Scenario: A missing holder leaf refuses by its own name
- GIVEN a profile carrying every other required field but omitting the
  declared holder leaf
- WHEN the engine loads it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming the
  holder leaf exactly

### Requirement: The Skill Root Resolves From The Host, Never The Engine's Own Location

`SKILL_ROOT` (17 reader sites) MUST resolve from a host-supplied value —
whichever mechanism Cut 1's design settles — and MUST NOT be derived from
`Path(__file__)` inside the moved engine, whose own file now lives under
`_core/implementation`, not under any skill.

#### Scenario: SKILL_ROOT names the skill directory after the move
- GIVEN the engine executes from `_core/implementation/engine/implementation_engine.py`
- WHEN any of the 17 `SKILL_ROOT` readers run
- THEN the resolved value is the skill's own directory

#### Scenario: A wrong root is made observable, not silent
- GIVEN `SKILL_ROOT` is, by mutation, derived from the engine's own `__file__`
- WHEN a reader resolves it
- THEN it resolves to `_core/implementation`, and a test pinning the skill
  directory value goes red

### Requirement: The Core Import Path Resolves From The Engine's Own File

The `sys.path.insert` site locating `_core/implementation` MUST be computed
relative to the moved engine module's own `__file__`, never relative to any
launcher's `__file__`, so the shared core is found identically regardless of
which skill launches it.

#### Scenario: Import succeeds through any launcher
- GIVEN the launcher hands over to the engine
- WHEN the engine computes its own sibling-module path
- THEN the import succeeds without depending on the launcher's directory depth

#### Scenario: A stale relative depth fails loudly
- GIVEN the site were left computed against a launcher's `__file__`
- WHEN the module imports
- THEN it raises `ImportError` immediately — the loud failure mode, distinct
  from `SKILL_ROOT`'s silent one

### Requirement: The Published CLI Path Names The Launcher

`CLI_PATH`, and every value derived from it (`CLI_INVOCATION`, printed or
published commands, `AGREED.md` entries), MUST resolve to the per-skill
launcher's own file, never the engine module's file, regardless of where the
underlying code executes.

#### Scenario: CLI_PATH names the launcher
- GIVEN the launcher hands over to the engine
- WHEN `CLI_PATH` is resolved
- THEN it equals the launcher's own file path, not the engine's

#### Scenario: A wrong CLI_PATH moves the seal
- GIVEN `CLI_PATH` is, by mutation, made to resolve to the engine's file
- WHEN the seal's normalized output is compared to its golden
- THEN every case whose output embeds `CLI_INVOCATION` moves, and comparison
  goes red

### Requirement: Published Commands Are Proven Against The Launcher, Not Assumed

`PublishedCommandsRunVerbatimTests` MUST assert, against the launcher's
literal path, that every printed or published command names a file the
reader was actually given — re-pointed explicitly for this cut, never
inherited unchanged from the pre-move assertion.

#### Scenario: The test asserts the launcher's literal path
- GIVEN the re-pointed test
- WHEN it runs against the moved engine and its launcher
- THEN every published command string contains the launcher's literal path

#### Scenario: The guard is reachable
- GIVEN `CLI_PATH` is mutated to resolve to the engine instead of the launcher
- WHEN the test runs
- THEN it fails, proving the assertion is not vacuous

### Requirement: Zero Behavioural Delta, Proven Against The Existing Seal

Every case captured by `the-seal-before-the-cut` MUST reproduce its stored
digest and exit status byte-identically after the move, run through the
launcher. The committed goldens are not reshaped or reissued by this cut;
they remain the exact contract Cut 1 must satisfy. There is no sanctioned
delta: any digest movement is a defect, and the remedy is reverting the
move, never declaring a new golden.

#### Scenario: Every case reproduces its golden
- GIVEN the 20-subcommand seal corpus and its committed goldens
- WHEN every case is re-run through the launcher after the move
- THEN each normalized digest and exit status is byte-identical to its
  pre-move golden

#### Scenario: A moved digest blocks the change
- GIVEN any case whose digest differs from its golden after the move
- WHEN the seal comparison runs
- THEN the change does not proceed, and the difference is reverted — never
  accepted as a new golden

## ADDED Requirements


### Requirement: Ten Domain-Specific Profile Fields Are The Whole Vocabulary Surface

Each field MUST be a validated resolver leaf, named in
`IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` by its dotted (or indexed) path, and MUST move only its
own named sealed digest(s) when changed. A field satisfying neither MUST NOT exist.

| Field | Read by | Digest(s) moved — MEASURED |
|---|---|---|
| `provenance.claim_key` | 14 provenance sites; kit lock | `probe`, `verify-a`, `verify-b`, `verify-t` |
| `provenance.authored_init_sentence` | `authored_package_init` | **none — zero-mover** |
| `findings.locus_key` | `cmd_admit` field loop, impact | `handoff-e1`, `verify-a`, `verify-b` |
| `findings.remedy_locus_key` | same loop, `cmd_handoff` | `handoff-e1`, `verify-a`, `verify-b` |
| `findings.notation_keys` | `handoff`/report payloads | `handoff-e1`, `verify-a`, `verify-b` |
| `findings.citation_pattern` | `CITATION_RE` | **none — zero-mover** |
| `vocabulary.subject_singular` | refusal builders | `compose` |
| `vocabulary.subject_plural` | refusal builders | **none — zero-mover** |
| `vocabulary.subject_singular_es` | Spanish refusal builders | `handoff-e1` |
| `vocabulary.subject_plural_es` | Spanish refusal builders | `handoff-e1` |
| `vocabulary.subject_collective` | refusal builders | **none — zero-mover** |
| `vocabulary.subject_collective_es` | Spanish refusal builders | **none — zero-mover** |
| `vocabulary.artifact_noun` | `authored_package_init` | **none — zero-mover** |
| `vocabulary.names` | both locks below, nothing else | lock goes red |
| `documents[i].directory` | `proposals_root()`, 5 refusals, validated per index | index 0: `admit-e0`, `close-e0`, `gate-e0`, `offer-e0`, `position-e0` — unchanged from the measured set |
| `documents[i].label` | `undeclared_arms_note` only, validated per index | **none — zero-mover**, any index |
| `documents[i].dataset_marker` | the dataset detector; `cmd_verify`'s `with_data`; `plan`'s conditional document-name key | measured only after real subprocess verification, never forecast — entered here as a passing scenario's exact result, mirroring this table's own correction history below |

**This table was corrected after verification and is now the measured truth, not a
prediction.** Its first version was written from design.md's forecast and diverged
from `MEASURED_MOVERS` in at least six rows. The most consequential: it claimed
`documents.label` moves "the same 5 refusals" as `documents.directory`. It does
not. `DOCUMENTS_LABEL` is read at exactly ONE call site (`undeclared_arms_note`,
inside `ARMS_UNDECLARED_CONSEQUENCE`'s `.format()`), gated on `declaration.get(
"arms")` being falsy AND at least one module declaring `sections` — a condition
**none of the 28 sealed cases hits**.

**Seven of the fifteen pre-existing leaves are zero-movers**, and that is a
recorded state, not a gap to hunt a stronger test for. A zero-mover is still read
— its removal raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming its exact
dotted (or indexed) leaf — it is simply not observable in the sealed stdout of
these particular fixtures. The removal-refusal plus the two neutrality locks are
its whole instrument, and saying so is the honest outcome. `documents[i]
.dataset_marker`'s own zero-mover-or-real-mover status MUST be measured, not
assumed, before this row's third column is treated as final — repeating that
measurement discipline is this table's own established correction pattern, not a
new one invented for this leaf.

Verification established this was **not a harness artifact**. A positive control
ran first: mutating `provenance.claim_key`, a known real mover, reproduced apply's
recorded set byte for byte, proving the profile genuinely reaches the seal's child
process. Only then were three zero-movers re-tested, and all three held.

Under `len(documents) > 1`, each entry is validated and refused by its own
index: removing `documents[1].directory` MUST raise
`IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming `documents[1].directory`
exactly, never the bare `documents.directory`. The identical rule now applies
to `documents[1].dataset_marker`.
(Previously: the table held fifteen leaves, with no `dataset_marker` row; a
`documents[N]` entry could omit any dataset declaration silently, since no
leaf named it as required.)

**This table was corrected after verification and is now the measured truth, not a
prediction.** Its first version was written from design.md's forecast and diverged
from `MEASURED_MOVERS` in at least six rows. The most consequential: it claimed
`documents.label` moves "the same 5 refusals" as `documents.directory`. It does
not. `DOCUMENTS_LABEL` is read at exactly ONE call site (`undeclared_arms_note`,
inside `ARMS_UNDECLARED_CONSEQUENCE`'s `.format()`), gated on `declaration.get(
"arms")` being falsy AND at least one module declaring `sections` — a condition
**none of the 28 sealed cases hits**.

**Seven of the fifteen leaves are zero-movers**, and that is a recorded state, not
a gap to hunt a stronger test for. A zero-mover is still read — its removal raises
`IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming its exact dotted (or indexed) leaf — it is
simply not observable in the sealed stdout of these 28 particular fixtures. The
removal-refusal plus the two neutrality locks are its whole instrument, and saying
so is the honest outcome.

Verification established this was **not a harness artifact**. A positive control
ran first: mutating `provenance.claim_key`, a known real mover, reproduced apply's
recorded set byte for byte, proving the profile genuinely reaches the seal's child
process. Only then were three zero-movers re-tested, and all three held. Without
that control the measurement would have been worthless — an earlier debug pass
under system `python3` instead of `.venv/bin/python` broke `CLI_INVOCATION`
resolution and crashed every subprocess **identically on both sides**, which reads
as "zero movers" for every leaf tried.

Under `len(documents) > 1`, each entry is validated and refused by its own
index: removing `documents[1].directory` MUST raise
`IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming `documents[1].directory`
exactly, never the bare `documents.directory`. Under `len(documents) == 1`,
index 0's behavior — including its digest set — is unchanged from the
measured table above.

(Previously: `documents.directory` and `documents.label` were validated as
single top-level leaves, with no index. They are now per-entry leaves of a
list, validated and refused by their own index; a single-document profile's
index-0 behavior is unchanged.)

#### Scenario: A missing leaf refuses by its own dotted name
- GIVEN a profile omitting `findings.remedy_locus_key`
- WHEN the resolver validates it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming that exact leaf

#### Scenario: Changing one field moves only its named digest
- GIVEN the sealed 28-case corpus
- WHEN `provenance.claim_key` changes and the seal re-runs
- THEN only `probe`, `verify-a`, `verify-b` and `verify-t` move -- the measured set, never `handoff` -- and the other 24 are byte-identical

#### Scenario: A second document's missing leaf refuses by its indexed name
- GIVEN a two-document fixture profile with `documents[1].directory` omitted
- WHEN the resolver validates it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming
  `documents[1].directory`, not `documents.directory`

#### Scenario: A missing `dataset_marker` refuses by its indexed name
- GIVEN a `documents[N]` entry omitting `dataset_marker`
- WHEN the resolver validates the profile
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming
  `documents[N].dataset_marker` exactly, and `documents[N].dataset_marker`
  set to `None` passes with no refusal
### Requirement: The Coarse Provenance Key Stays Shared, Never Profile-Supplied

`"sections"` MUST stay a hardcoded literal in the engine and every kit asset. The
profile MUST NOT expose a coarse-key field. `unreached_modules` MUST cross
`__provenance__["sections"]` against `__benchmark__["arms"][x]["sections"]` using that
literal on both sides.

#### Scenario: The join reads the literal on both sides, unaffected by an unread key
- GIVEN a profile declaring an extra, unread `provenance.drift_unit_key`
- WHEN `unreached_modules` computes the join
- THEN both sides still read the literal `"sections"`, and the join is unaffected

### Requirement: §B1 Fields Excluded For A Recorded Reason Are Not Present

| Field | Reason |
|---|---|
| `provenance.drift_unit_key` | it IS the coarse key; removed by the B2 ruling |
| `provenance.revision_key` | shape (scalar->pair) is Cut 3 |
| `document_reader.drift_units` | no Cut-2 reader |
| `documents.marker` | F6; a fifth spelling worsens the coupling |
| `cli_invocation` | rejected at Cut 1: profile supplies the path only |

#### Scenario: None of the five keys is in the resolver's validated set
- GIVEN the resolver's required-leaf table after Cut 2
- WHEN it is inspected
- THEN none of the five keys above appears in it

### Requirement: The Campaign-Proposal Exclusion List Is Enforced By A Test

A test MUST assert `proposalDigest`, `GATE_PROPOSAL_*`, `_proposal_digest`,
`_verify_gate_proposal`, `_gate_proposal_question`, `_verify_optional_election`,
`cmd_propose`, `_authorization_binding`, `_verify_gate_authorization`,
`_campaign_identity`, `_load_remote_execution_*` remain unrenamed by this cut.

#### Scenario: A rename to any excluded symbol is caught
- GIVEN a hypothetical edit renaming `proposalDigest`
- WHEN the exclusion test runs
- THEN it fails, naming the symbol; unmodified, the test passes

### Requirement: The Kit Template's Provenance Keys Agree With The Profile

Each discovered profile's own kit template MUST have its provenance keys checked
against that same skill's own profile — `KitAgreementLockTests` MUST iterate every
profile `discover_profiles()` finds, the way the domain-profile lock already does,
never a single hardcoded skill path. Each skill's check MUST be independent: one
skill's mismatch MUST be reported without masking another skill's, via `subTest` or
separate test methods per skill.
(Previously: `_profile()` returned a single hardcoded `proposal-implementation`
profile; only that one skill's kit was ever checked, so a second skill's kit template
would diverge from its profile with nothing to catch it.)

#### Scenario: Divergence is caught for the discovered skill it belongs to
- GIVEN the kit template edited to a different `"equations"` equivalent value under
  `experimental-implementation`
- WHEN the lock runs
- THEN it fails, naming that skill and the divergent key; reverted, it passes

#### Scenario: One skill's break does not hide another's
- GIVEN `experimental-implementation`'s kit is broken while `proposal-implementation`'s
  agrees with its own profile
- WHEN the lock runs
- THEN both outcomes are individually visible — the broken skill fails and the
  agreeing skill passes in the same run, neither masked by test-method halting

#### Scenario: A skill declaring no kit template is not silently skipped as a pass
- GIVEN a hypothetical third skill with `impl_profile.py` but no kit template file
- WHEN the lock runs
- THEN it fails naming the missing template, rather than reporting agreement it
  never checked

### Requirement: The Derived-Denylist Lock Becomes Satisfiable, Not A Permanent Skip

With a second implementation profile on disk, the Python mirror of the TS
`buildDenylist` mechanism (a word is a domain's own subject only when no other
profile's north uses it) MUST run as a real, unskipped assertion. It MUST NOT be
implemented as a `skipTest`, and its landing MUST NOT move the pinned Python
`skipped=6` invariant.

#### Scenario: The lock runs for real once two profiles exist
- GIVEN `experimental-implementation` and `proposal-implementation` both declare an
  `OBJECTIVE_FLOW`
- WHEN the derived-denylist lock runs
- THEN it computes a real denylist from each skill's own north against the other's,
  and asserts rather than skips

#### Scenario: skipped=6 does not move
- GIVEN this lock lands as a passing test
- WHEN the full Python suite runs
- THEN `OK (skipped=6)` holds, and `Ran` grows by the new test, not by a new skip

### Requirement: A Namespace Word's Self-Check Is Not The Leak Proof

The existing check that a declared `vocabulary.names` word appears in its own
profile's source text (`test_every_declared_name_really_is_that_domain_speaking`)
MUST NOT be relied on as evidence that the word is leak-free — a namespace word (for
example, the skill's own directory name) trivially satisfies it by appearing in the
file's own path or docstring, without ever having been used as a real domain value.
The whole-engine text scan (`test_the_engine_spells_no_declared_names_word`) remains
the sole mutation-provable leak guard for any declared name, including a namespace
word.

#### Scenario: The self-check passes trivially for a namespace word
- GIVEN `experimental-implementation` declares its own namespace word in
  `vocabulary.names`, present only in its profile file's own path or docstring
- WHEN the self-check runs
- THEN it passes, and that pass is not treated as proof the word never leaks into
  the engine

#### Scenario: The whole-engine scan is what actually catches a leak
- GIVEN that same namespace word is planted anywhere under
  `_core/implementation/engine/`
- WHEN the whole-engine scan runs
- THEN it fails, naming the file and the word; reverting the plant restores green

### Requirement: The Engine Spells No Declared Domain Word

A neutrality lock MUST fail when any `vocabulary.names` word appears anywhere — code,
string, comment, or docstring — under `_core/implementation/engine/`.

#### Scenario: A planted word reddens it, reverting restores green
- GIVEN a `vocabulary.names` word planted anywhere in `engine/`, including a comment
- WHEN the lock runs
- THEN it fails, naming the file and word; reverting the plant restores green

### Requirement: A Python Mirror Discovers Profiles By Globbing, Not Hardcoding

The Python domain-profile lock MUST discover profiles by globbing `*/impl_profile.py`,
mirroring `discoverProfiles` in `tests/proposal-deliberation-domain-profile-lock.test.mjs`.

#### Scenario: A third skill is held without editing the lock
- GIVEN a hypothetical third skill's `impl_profile.py` declaring empty `vocabulary.names`
- WHEN the lock runs
- THEN it fails on that skill with zero edits to the lock file itself

### Requirement: A New Core File Naming A `PRODUCT_DIRS` Member Stays Reachable By `CoreNamesNoDomainTests`

`CoreNamesNoDomainTests` scans `CORE.glob("*.py")` non-recursively and fails
any core-level file whose text names a `PRODUCT_DIRS`/`SOURCE_ROOTS` member.
Any new file this capability adds that names `PRODUCT_DATA` or `"Data"`
MUST live under `_core/implementation/engine/`, which that non-recursive
glob does not reach, or MUST be added to the existing engine module rather
than a new flat `_core/implementation/*.py` file.

#### Scenario: A flat detector file reddens the guard
- GIVEN a hypothetical detector module placed directly under
  `_core/implementation/`, naming `PRODUCT_DATA`
- WHEN `CoreNamesNoDomainTests` runs
- THEN it fails, naming that file

#### Scenario: The same code under `engine/` does not
- GIVEN the identical detector code added to
  `_core/implementation/engine/implementation_engine.py` instead
- WHEN `CoreNamesNoDomainTests` runs
- THEN it passes, unaffected

## Reconciliation note (orchestrator, after design landed)

This spec originally named the engine's destination as the FLAT
`_core/implementation/implementation_engine.py`. That destination is
unreachable, and the correction is recorded here rather than silently applied.

`tests/test_implementation_core.py`'s `CoreNamesNoDomainTests` scans
`CORE.glob("*.py")` — **non-recursive** — and fails any core file whose text
names a member of `PRODUCT_DIRS`/`SOURCE_ROOTS`. The engine **defines**
`PRODUCT_DIRS = ("Notebooks", "Data", "Results", "Models")`, so a flat landing
turns that guard red. Both obvious repairs are worse than the defect: exempting
the engine by name, or weakening the rule, guts a guard covering ~17,100 of
~18,000 core lines.

The destination is therefore the `engine/` **subdirectory**, which the
non-recursive glob does not reach. This is not a new mechanism invented for the
occasion — `.claude/skills/_core/deliberation/engine/` is already exactly this
shape, verified on disk. The precedent this change set out to mirror had already
answered the question.

## Amendment: `objective` joins the Cut-1 profile field set (operator ruling, Phase 8)

This spec was written when the Cut-1 field set was `kit.root` and `cli.path`
only, on the stated principle that **a profile field nothing reads cannot be
mutation-proven, and an unprovable field is the shape of a false guard.**

That principle did not change. What changed is that `objective` now satisfies it.

`tests/test_agents.py` discovers a skill's declared north by walking
`(SKILLS / skill).rglob("*.py")` — a **physical** directory walk under the
skill's own tree. `OBJECTIVE_FLOW` lived inside the engine file, so moving that
file out of the skill took the north with it and `declared_objective(
"proposal-implementation")` began returning `None`. Three `AgentBindingTests`
went red on a file this change never touched.

The 56 lines move verbatim into `impl_profile.py`, which lives inside the
skill's tree, and the engine reads `PROFILE["objective"]`. The resolver
validates it the way `domain-profile.ts` validates its own: `purpose`,
`stages`, `arrival`, `humanStops` present, `stages` non-empty, all three
per-stage keys present — the `artifact: {}` lesson, where a top-level presence
check passes vacuously.

### Why this is required work and not a workaround

The purpose of this seam is a **second skill with its own north**.
`experimental-implementation`'s objective flow is not this one's: different
stages, different arrival. With `OBJECTIVE_FLOW` in the shared engine, the
second skill would inherit the first's north and there would be no way to give
it its own without editing the engine — precisely what the seam exists to
prevent. `objective` had to become a profile field; the block only moved the
date forward.

The other side of this forge already settled it identically: both
`proposal-deliberation/profile.ts` and `experimental-deliberation/profile.ts`
declare `objective` themselves, `_core/deliberation/engine/domain-profile.ts`
hardcodes none, and the archived change is
`2026-09-09-a-north-a-second-domain-can-hold`.

### Proven, not asserted

Mutating one character of `objective.purpose` moves **11 of 28** sealed
digests — every case reaching a refusal payload or the other stamp site —
reproduced case-for-case by verify as a real reverted file edit. The field is
mutation-provable, which is what earns it its place.

`tests/test_agents.py` returned to 16/16 green with **zero edits to that file**
(`git diff --stat` empty), which is the proof the relocation restored discovery
rather than papering over the failure.

### Requirement: No Live Target's Own Name Appears Anywhere In This Forge, In Any Casing

This is a forge of papers, not of one paper. Every file under `.claude/`,
and every test's own commentary, fixture description, or string content not
meant as a neutral placeholder, MUST name no specific live target — neither
a target's package name (already guarded) nor its repository directory
name. This extends the existing engine-text and kit-agreement leak guards
to test commentary specifically, and MUST catch a live target's name
regardless of how that name happens to be cased where it leaks, so a
proper-noun-cased mention in prose is not structurally invisible to a
guard built from normalized words.

**Measured, not hypothetical.** A live target's repository directory name
appears once in `tests/test_proposal_implementation.py`, in a fixture
comment, while the existing vocabulary guards report 28/28 passing and the
same name appears nowhere under `.claude/`. The guard exists and mostly
works; this one instance is where it does not.

#### Scenario: A live target's repository name in a test comment is caught
- GIVEN a test file's comment names a specific live target's repository
  directory, in whatever casing it is naturally written
- WHEN the anti-leak guard runs
- THEN it fails, naming the file and the word

#### Scenario: A neutral placeholder is not mistaken for a leak
- GIVEN a fixture using a generic, invented name that is not any real
  target's own name
- WHEN the guard runs
- THEN it does not object

### Requirement: The Anti-Leak Guard's Word Comparison Does Not Depend On Matching Case

The step that compares a forge document's text against the words a live
target owns MUST NOT silently pass a match merely because the target's own
name is cased differently in the leaking text than in the guard's own
normalized vocabulary (for example, a title-cased repository name in prose
against a lowercased denylist entry). Closing the one measured instance by
hand, without making the comparison case-robust, would leave every future
target's own name free to leak the same way, in the same casing pattern.

#### Scenario: A repository name leaking in a different case than the denylist is caught
- GIVEN a live target's repository directory name appears in forge text in
  a different case than the guard's own derived vocabulary uses
- WHEN the leak check compares them
- THEN the leak is still caught

#### Scenario: The fix closes the class, not the one instance
- GIVEN a hypothetical second live target whose repository directory name
  has never appeared in any forge text before
- WHEN that name is planted, in any casing, into a forge file as a test
- THEN the guard catches it too, with no per-target exemption list required
### Requirement: The Engine's Own Prose Stops Asserting A Literal Holder Filename As Fact

The four docstring assertions of fact that the holder *is* `<Name>/AGREED.md`
(`implementation_engine.py:575`, `:12005`, `:18946`, `:18992`) MUST instead
name the declared holder leaf, not a literal filename, since the holder is
now a per-skill declared value rather than an engine-asserted constant. Every
other prose mention of the literal `AGREED.md` in `implementation_engine.py`
(15 total) and `impl_position.py` (3 total) that reads as the engine's own
naming — rather than quoting a specific skill's own artifact as an example —
MUST receive the same treatment.

#### Scenario: The four fact-asserting docstrings name the declared leaf
- GIVEN the four docstring sites listed above
- WHEN they are read after this capability lands
- THEN none of them asserts a literal filename as the engine's own fact —
  each instead refers to the declared holder leaf

#### Scenario: A literal filename in engine prose is caught for the engine's own claims
- GIVEN a hypothetical reintroduced docstring asserting the holder is a
  specific literal filename as the engine's own default
- WHEN the doctrine-verification check for this capability runs
- THEN it is caught and named, distinguishing it from a comment merely
  illustrating one skill's own declared example value
