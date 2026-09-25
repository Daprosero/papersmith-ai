# implementation-declared-holder Specification

## Purpose

The checklist holder that `agreements_state`/`_chosen_holder`/`cmd_settle` read and
write is chosen today by a `*.md` glob plus an item-holding test — never by a
name either skill owns. `proposal-implementation` and `experimental-implementation`
share one engine and one product folder shape (`product = target / name`), so two
skills invoked against the same target land in the same undeclared holder, and a
`documents=` header group written by one profile permanently poisons that holder
for the other. This capability closes the collision structurally: each skill
declares its own holder filename and the heading scaffold a freshly created
holder is born with, as an 8th required `PROFILE` leaf. The engine hardcodes
no filename, defaults to none, and stops asserting one as fact. The existing
by-shape scan is preserved verbatim as the read-only fallback that protects an
adopted target's own arbitrarily-named checklist; only the write path changes
owner.

## Requirements

### Requirement: The Declared Holder Is A Required PROFILE Leaf

Each skill's `PROFILE` MUST declare its own holder filename as a required leaf,
validated by `impl_domain_profile.py`'s existing required-leaf tier. Omitting
this leaf MUST raise `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE`, naming that
exact leaf. The engine MUST NOT supply a default or fallback filename of its
own for this leaf.

#### Scenario: A profile declaring the leaf validates
- GIVEN `proposal-implementation`'s `PROFILE` declares its holder leaf as
  `AGREED.md`
- WHEN the engine loads the profile
- THEN the leaf validates and no refusal is raised

#### Scenario: An omitted leaf refuses by its own name
- GIVEN a profile with every other required leaf present but the holder leaf
  omitted
- WHEN the engine loads it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming the holder
  leaf exactly

### Requirement: The Declared Holder Leaf Carries A Heading Scaffold

The holder leaf MUST include the heading(s) a freshly created holder is born
with, alongside the filename. Omitting the heading scaffold while declaring
the filename MUST be treated as an incomplete leaf under the same refusal.

#### Scenario: The scaffold validates alongside the filename
- GIVEN a profile declaring both the holder filename and its heading scaffold
- WHEN the engine loads the profile
- THEN both validate together and no refusal is raised

#### Scenario: A filename without a heading scaffold refuses
- GIVEN a profile declaring the holder filename but omitting its heading
  scaffold
- WHEN the engine loads it
- THEN it raises `IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE` naming the missing
  heading-scaffold leaf

### Requirement: Declared Name Present Resolves Both Reads And Writes

When a file matching the declared holder filename exists on disk under the
product folder, it MUST be the holder used for both reading and writing,
regardless of whether any other item-holding `*.md` file is also present.

#### Scenario: The declared file is used even beside another candidate
- GIVEN both the declared holder filename and an unrelated item-holding
  `*.md` file exist in the product folder
- WHEN the engine resolves the holder for a read or a write
- THEN it resolves to the declared file, never the other candidate

### Requirement: Read Falls Back To The By-Shape Scan When The Declared Name Is Absent

When no file matching the declared holder filename exists, reading MUST fall
back to the existing by-shape scan (`AGREEMENTS_GLOB` plus the item-holding
test), exactly as it resolves today. A target adopted with its own
arbitrarily-named checklist MUST still be found and read.

#### Scenario: An arbitrarily named existing checklist is still read
- GIVEN a product folder with no file matching the declared holder filename,
  but an item-holding `TASKS.md`
- WHEN the engine resolves the holder for a read
- THEN it resolves to `TASKS.md` and the read succeeds

### Requirement: Write Refuses Into A Holder Not Found By The Declared Name, Naming Both Exits

When the declared holder filename is absent but the by-shape scan finds another
item-holding candidate, a write MUST refuse with a named code rather than
writing into that candidate. The refusal message MUST name both available
exits: creating the skill's own declared holder, or renaming the existing
file to the declared name. This refusal MUST be reachable — proven by
mutating the guard away and observing the write proceed incorrectly.

#### Scenario: A write into an undeclared candidate refuses
- GIVEN no file matches the declared holder filename, and an item-holding
  `TASKS.md` is present
- WHEN a write (e.g. `settle` or `position`) is attempted
- THEN it refuses with a named code, and does not write into `TASKS.md`

#### Scenario: The refusal names both exits
- GIVEN the same refusal fires
- WHEN its message is inspected
- THEN it names both exits: create this skill's own declared holder, or
  rename `TASKS.md` to the declared name

#### Scenario: The guard is reachable by mutation
- GIVEN the write-refusal guard is disabled by mutation
- WHEN the same write is attempted against the undeclared candidate
- THEN the mutated build writes into the undeclared candidate, proving the
  guard — restored — is what prevents it

### Requirement: Create-On-Absent When No Candidate Exists

When neither the declared holder filename nor any other item-holding `*.md`
file exists in the product folder, the skill MUST create its declared
holder, with its declared heading scaffold, and with zero checklist items.

#### Scenario: A first write into an empty product folder creates the declared holder
- GIVEN a product folder with no `*.md` file at all
- WHEN a write is attempted
- THEN the declared holder file is created with its declared heading(s), and
  it holds no checklist items

#### Scenario: Creation never invents an agreement
- GIVEN the same creation
- WHEN the created holder's content is inspected
- THEN it contains only the declared heading scaffold — no checklist item is
  present

### Requirement: Declared-Name Identity Is Independent Of The Item-Holding Test

A holder identified by its declared name MUST be reported as present by
every consumer that reads `agreements_state`'s `holders` list, regardless of
whether it currently holds any checklist item. `_chosen_holder` and
`cmd_settle` MUST resolve a freshly created, item-less declared holder
without raising an absence refusal.

#### Scenario: A freshly created holder appears in `holders`
- GIVEN the declared holder was just created with zero checklist items
- WHEN `agreements_state` is computed
- THEN the declared holder appears in the `holders` list

#### Scenario: `_chosen_holder` resolves the freshly created holder
- GIVEN the same freshly created, item-less declared holder
- WHEN `_chosen_holder` runs
- THEN it resolves to the declared holder and raises no absence refusal

#### Scenario: `cmd_settle` writes into the freshly created holder
- GIVEN the same freshly created, item-less declared holder
- WHEN `cmd_settle` is invoked
- THEN it writes into the declared holder rather than raising
  `SETTLE_HOLDER_ABSENT`

### Requirement: The Never-Invents-A-File Doctrine Is Narrowed To The Read Path, Not Retired

Every restatement of "never invents a file" (`agreements_state`'s root
doctrine, `_chosen_holder`'s and `cmd_settle`'s absence-refusal docstrings,
the two interactive-question restatements, the fixture comment in
`tests/test_implementation_pair.py`) and every by-shape comment
(`position_state`, `cmd_position`'s sweep comment and docstring) MUST be
verified against the shipped bytes and updated so that none asserts, as
current behavior, that the write path never invents a file. Each MUST
instead state — verbatim or in substance — that the engine still invents no
*filename* (the skill declares it), and that the by-shape scan remains the
read-only fallback.

#### Scenario: No doctrine restatement contradicts shipped behavior
- GIVEN the shipped create-on-absent and write-refusal behavior
- WHEN each of the doctrine restatement sites listed above is read
- THEN none of them asserts that a write into an absent holder is refused
  unconditionally — each instead describes the read-only by-shape fallback
  and the declared-name write rule

#### Scenario: The read-only concern is preserved verbatim
- GIVEN a target adopted with its own arbitrarily-named checklist
- WHEN that target is read under this capability
- THEN it is found and reported exactly as the by-shape doctrine originally
  promised

### Requirement: `SETTLE_HEADING_ABSENT` Still Fires For A Heading The Declaration Does Not Carry

The existing `SETTLE_HEADING_ABSENT` refusal MUST remain unamended: after a
holder is created with its declared heading scaffold, a write targeting any
heading not present in that scaffold MUST still refuse
`SETTLE_HEADING_ABSENT`, with the same question it asks today.

#### Scenario: A write under an undeclared heading still refuses
- GIVEN a declared holder created with its declared heading scaffold
- WHEN a write targets a heading absent from that scaffold
- THEN `SETTLE_HEADING_ABSENT` fires, naming the same question as before this
  capability

#### Scenario: The refusal is reachable by mutation
- GIVEN `SETTLE_HEADING_ABSENT`'s guard is disabled by mutation
- WHEN the same write is attempted
- THEN the mutated build writes under the undeclared heading, proving the
  guard is what prevents it

### Requirement: The Engine Uses No Default Or Fallback Holder Filename Of Its Own

No site in `implementation_engine.py` or `impl_position.py` MUST resolve the
holder filename to a hardcoded literal as a default or fallback value. Every
resolution MUST originate from the declared `PROFILE` leaf or the by-shape
scan; a grep for a literal holder filename used as a Python default value or
fallback expression MUST return no result.

#### Scenario: No hardcoded default is used at resolution time
- GIVEN both skills' declared holder names differ (`AGREED.md` and
  `Experimental_AGREED.md`)
- WHEN either skill's engine invocation resolves its holder
- THEN it resolves to that skill's own declared name, never to a value the
  engine supplied on its own

### Requirement: The Pinned Reachable-Refusal-Code Count Is Re-Measured By Running The Derivation

`test_the_derivation_finds_the_measured_one_hundred_and_thirteen`
(`tests/test_proposal_implementation.py:32285-32309`) MUST be re-run after
every refusal code this capability adds or retires, and its pinned expected
count MUST be updated to whatever the derivation actually prints. The new
count MUST NOT be predicted, estimated, or copied from the proposal's
forecast — it MUST be the observed output of running the derivation against
the shipped code.

#### Scenario: The pinned count matches a fresh run of the derivation
- GIVEN this capability's refusal codes are all shipped
- WHEN `reachable_refusal_codes`'s derivation is run against the shipped
  engine
- THEN the test's pinned expected count equals that run's actual output

#### Scenario: An unreconciled prediction is rejected
- GIVEN the pinned count was updated to a number taken from the proposal's
  forecast rather than from running the derivation
- WHEN the derivation is actually run and disagrees with that number
- THEN the test fails, and the correct action is updating the pin to the
  measured number, never adjusting the derivation to match the guess
