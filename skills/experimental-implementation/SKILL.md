---
name: experimental-implementation
description: "Trigger: turn the latest experiments protocol into working Python against a target repository, run its declared measurements, and verify an existing implementation's layout and revision fidelity against both the experiments protocol and the mathematical proposal it answers to. Isolated venv, keyless, fail-closed. The second host on the shared implementation engine (change `the-second-skill-the-seam-was-for`, slice A; change `the-second-document-verified-on-its-own-terms`, slice C) -- two declared documents, each verified on its own claim vocabulary, zero engine bytes."
---

# Experimental Implementation

Turn the current experiments revision (`experiments/experiments-<slug>-vNN.md`)
into Python that runs, in a target repository, and prove it: complete runs whose
own record agrees with what the protocol says.

## Scope: two documents, each verified on its own terms

This skill is the SECOND host built on the shared implementation engine
(`_core/implementation/engine/implementation_engine.py`) -- the same engine
`proposal-implementation` already serves, changed by **zero bytes** to add this
domain. Everything here is a profile
(`skills/experimental-implementation/impl_profile.py`), a byte-identical
launcher copy, this doctrine, two agents, and this skill's own sealed corpus.

**Two declared documents, each with its own claim vocabulary.** `documents[0]`
is `experiments/`, label `experiments` -- the experiments document this skill
originally verified alone (change `the-second-skill-the-seam-was-for`, slice
A). `documents[1]` is `proposals/`, label `proposal` -- the mathematical
proposal this protocol answers to, added by change
`the-second-document-verified-on-its-own-terms` (slice C). Document 0 declares
no per-document overlay and keeps resolving from the top-level scalars below,
byte-identical to slice A; document 1 declares its own complete overlay (all
five leaves: `claim_key`, `locus_key`, `remedy_locus_key`, `notation_keys`,
`citation_pattern`), matching `proposal-implementation`'s own established
`equations` vocabulary for this domain -- never inheriting document 0's
`experiments` vocabulary by omission.

`verify`'s `fidelity.fidelityByDocument` now reports one independent status per
document, each derived from that document's own claim-key module scope: a
module implementing document 0's claims can drift while document 1 stays
clean, and the reverse. A finding may name either or both documents
(`"document": "experiments"`, `"document": ["experiments", "proposal"]`, ...);
each named document's citations are matched against that document's OWN
`citation_pattern`, never a pattern shared across both. Cross-document
agreement (a single verdict combining both documents) and a successor composer
remain follow-on changes (B, D), not built here.

## This domain's own claim vocabulary

Where `proposal-implementation` reads `equations`/`ecuación`/`formulation` at
its own single document, this skill reads its own words for document 0, and
`proposal-implementation`'s own `equations` vocabulary again for document 1
(declared as document 1's own overlay, not inherited):

| Profile leaf | Document 0 (`experiments`) | Document 1 (`proposal`) |
| --- | --- | --- |
| `claim_key` / `locus_key` | `experiments` | `equations` |
| `remedy_locus_key` | `remedy_experiments` | `remedy_equations` |
| `notation_keys.locus` / `.remedyLocus` / `.unknown` | `experiments` / `remedyExperiments` / `unknownExperiments` | `equations` / `remedyEquations` / `unknownEquations` |
| `citation_pattern` | `Exps?`/`Experiment`/`Experimentos?` syntax | `Ecs?`/`Eq`/`Ecuaciones?` syntax |
| `documents[N].directory` / `.label` | `experiments/` / `experiments` | `proposals/` / `proposal` |

The top-level `vocabulary.*` leaves below stay document 0's own -- they are
resolver-tier subject words, not per-document claim vocabulary:

| Profile leaf | This domain's value |
| --- | --- |
| `vocabulary.subject_singular` / `_plural` | `experiment` / `experiments` |
| `vocabulary.subject_singular_es` / `_plural_es` | `experimento` / `experimentos` |
| `vocabulary.subject_collective` / `_collective_es` | `experimentation` / `experimentación` |
| `vocabulary.artifact_noun` | `protocol` |

A module's own `__provenance__` declares a non-empty list under whichever
document's claim key it implements (`"experiments"` for document 0,
`"equations"` for document 1) -- a module may declare both -- and every
invariant listed there needs a matching test under `tests/`, exactly as the
sibling's own doctrine requires for its own claim key.

## `Data/` is demandable, per product folder

`documents[0]`'s own `dataset_marker` leaf (`**Dataset:**`) makes a
declared dataset demandable: when the bound experiments revision carries
a line-leading `**Dataset:** ...` declaration -- the same marker
`experimental-deliberation`'s own preservation rule already enforces on
this domain's documents -- `verify` reports `{Name}/Data` in
`missingDirs` until that folder exists, exactly as it already does for
`Notebooks/`, `Results/` and `Models/`. Presence only: which files
constitute the dataset is out of scope, matching the other three
categories.

The demand is **per product folder, never at the repository root**, for
three reasons:

1. A run binds to **one method** -- `--name` already carries that
   binding, and the data is the data that method's own experiments use.
2. The same repository's data may not apply to a **different method**
   living beside it under the same clone.
3. A later paper may move the repository to a **different area
   entirely**, whose data is not this one's.

A document declaring no dataset (`dataset_marker: None`, as `documents[1]`
-- the mathematical proposal -- always does) changes nothing: `Data/`
stays undemanded for that document, exactly as before this capability
existed.

## The objective flow

**Why this skill was invoked, and where it has to arrive.** Declared here and in
`OBJECTIVE_FLOW`, held equal by a test, and deliberately independent of anything
on disk -- the same property `proposal-implementation`'s own north has, and for
the same reason: a session that hits an error, an interruption or a gap
consults it, locates itself, resolves what blocks, and rejoins.

**Purpose:** carry the declared experiments protocol as far as complete runs
whose own record agrees with what the protocol says -- not a green
verification, not a passing rehearsal.

| Stage | Establishes | Behind you when |
| --- | --- | --- |
| `standing` | A repository set up the way this skill expects, with an interpreter of its own and the protocol's declared steps laid out as runnable commands | `structure` reports no scaffold gaps and the protocol the run answers to is named and readable |
| `binding` | The code that runs says what the bound experiments revision says, every declared step traced to a runnable command | `fidelity` is clean against the bound experiments revision and the target's own suite is green under its own interpreter |
| `instrumentation` | Every measurement the protocol declares has a place to land -- a metric, a record, a check that can fail | every declared measurement resolves to something that can actually be run and read back |
| `rehearsal` | The declared flow runs end to end at a small scale, and the record it leaves agrees with the document a person reads | the rehearsal is complete and its own report is `ok` |
| `full-scale` | Every step routed to where it was decided to run, and executed there at the scale the protocol declares | this is the arrival; it is behind nobody |

**Arrival:** complete runs at the protocol's declared scale, with a record
checkable against the experiments revision.

**Four stops are a person's, not defects to repair:** authorizing that code be
written at all; approving the map from the protocol's declared steps to
runnable commands; publishing the commit a worker would clone; authorizing a
launch, which is hours of somebody's quota.

This north declares no stage nothing measures, and no `entrances` at all --
declaring an entrance nothing produces would be a claim with no producer, the
same reasoning `experimental-deliberation`'s own profile records for itself.

## What this skill delegates, and to whom

Two stretches of this flow are mechanical from end to end, each carried out by
its own agent. What moves is EXECUTION, never doctrine: every rule stays here,
and each agent's first instruction is to load this file.

| Stretch | Delegated to | Begins after | Ends at | Measure this before delegating |
| --- | --- | --- | --- | --- |
| Build | this skill delegates to the `experiments-build` agent | the object-to-map is approved | every declared measurement has a place to land (`instrumentation`) | `verify` -- the protocol's declared steps must already be traced to runnable commands |
| Walk | this skill delegates to the `experiments-walk` agent | each step's placement is decided | the launch the operator must authorize | `verify` -- `undeclaredPlacement` is empty, so every step says where it runs |

Each agent also refuses from inside when it finds itself before its own start --
the backstop, not the rule.

## Where to start: the repository is the memory

Same routing rule as `proposal-implementation`'s own -- **read `src/`, never
remember a prior session.** An implementation already sitting there is the
whole record of what was already asked and answered; a repository with none
has not been through this skill yet.

- **`src/` holds no implementation at all** -> Flow A.
- **`src/` holds one, whatever revision it is bound to** -> Flow B, which
  measures drift against BOTH documents before deciding anything.

## Flow A -- first pass

This domain ships no `assets/kit/` (`materialize --stage scaffold` is
unavailable, above), so a target's scaffold is hand-written, not
materialized. Everything else follows the sibling's own first-pass shape,
narrowed to what this domain actually has:

1. Clone the target repository under `implementations/<repo>/`, then `env`
   to build its own venv from its own interpreter -- never the forge's.
2. **Ask for the name.** Run `name --name "<whatever they typed>"`, confirm
   both forms it returns, then **[GATE]** before writing anything with them.
3. **[GATE] Ask for authorization to implement.** Nothing below writes code
   before this.
4. Present the object-to-module map for **both documents** -- which module
   implements which experiment section, and which implements which
   equation the experiment answers to (`documents[0]`/`documents[1]`,
   above). Wait for approval, then write code, and give each module the
   `__provenance__` claim key it actually implements (`experiments`,
   `equations`, or both).
5. Hand off to the `experiments-build` agent once every declared
   measurement has a place to land (`instrumentation`, the objective flow
   above) -- delegated, not walked by hand.
6. Hand off to the `experiments-walk` agent once every step's placement is
   decided -- the same delegation table above names when each stretch
   begins and ends.

## Flow B -- every later pass

1. Read `src/` and take the newest revision of **each** declared document
   independently -- document 0's own discovery, and document 1's own,
   never one name assumed for both (`each-document-names-its-own-revision`).
2. **Run the suite with the target interpreter, then `verify --revision
   <document 0's newest>`.** Same division as the sibling's own Flow B step
   2: running the suite proves the code *does* what it says; `verify`
   proves it *says* what it should. Neither substitutes for the other.
3. **Differences in fidelity, in EITHER document** -> **[GATE] ask whether
   the user made that document's own change** -- `fidelityByDocument`
   reports each document's status independently (above), so a drift in
   document 1 alone routes the same gate document 0's own drift always
   has, and does not wait for document 0 to also disagree. The gate itself
   is not repeated or reworded here: it is the sibling's own
   ("did the user make this change") asked against whichever document's
   own evidence disagrees.
4. **Suite green and fidelity clean in both documents** -> `agree
   --revision <document 0's newest>` (available once more than one
   document is declared, which this skill's profile always does). Names
   every citation the experiments document makes into the mathematical
   proposal that the proposal does not currently declare, and every claim
   the proposal declares that no experiment cites -- refuses once, naming
   both kinds together, never a verdict on which side should change.
   Resolve each named discrepancy in conversation (`--acknowledge <exact
   id>` clears only the ids echoed back exactly) before continuing.

   - **A third kind `agree` never checks, and never will:** whether an
     experiment's declared metric or protocol actually corresponds to
     what the claim it cites asserts. Reading both documents to judge
     that is exactly the kind of question a check that tried would get
     wrong in both directions -- blocking correct work and passing broken
     work alike. It is guidance for whoever reads `agree`'s output next,
     never a condition `agree` tests: a citation can resolve cleanly by
     `agree`'s own measure while still citing the wrong claim for what it
     actually measures, and only a reader who has read both documents can
     tell.
5. Once `agree` reports no unacknowledged discrepancy, run `handoff
   --revision <document 0's newest>` to size the open findings and hand
   the local ones to the deliberation (`experimental-deliberation`) as
   agenda items. `settleInline` entries substitute through `compose`;
   everything else is a prompt for a session of its own.
6. Once the deliberation publishes a successor revision, this skill's own
   part is done -- what remains is reaching a **test submission**, and
   `remote-execution`'s own commands answer it exactly as they do for the
   sibling: `probe`'s `nextStep` names which one, and
   [the sibling's own remote-execution seam table](../proposal-implementation/SKILL.md#the-remote-execution-seam--which-subcommand-answers-which-reported-state)
   names which subcommand answers which reported state. Nothing here
   re-documents that table or re-asks its own gate; this skill drives the
   same shared scripts (`REMOTE_EXECUTION_CLI_SCRIPT` et al., already
   `FORGE_ROOT`-derived) rather than rebuilding them.

## Entry command

```bash
skills/experimental-implementation/scripts/implementation_cli.py <command> [args...]
```

A concrete, runnable example -- this exact line runs verbatim, unedited, from
the forge's own root (`tests/test_experimental_implementation.py`'s own
published-commands test proves it):

```bash
skills/experimental-implementation/scripts/implementation_cli.py name --name Trial
```

The launcher is a byte-for-byte copy of `proposal-implementation`'s own launcher
(design.md D4): every value inside it is derived from its own location, so the
same 24 bytes, placed under this skill's own `scripts/`, resolve to THIS
skill's own profile without a single domain-specific line. Every argument,
subcommand and exit code is the shared engine's; nothing here re-documents them.

## Which commands are not available yet, and why

This domain ships no `assets/kit/` at all (measured this session: the kit
sibling ships is ~99% general machinery, and copying ~2,000 lines to change the
~20 that are not would be the exact duplication the operator refused for the
CLI, one directory over). Consequence, stated rather than discovered:

- **`materialize --stage scaffold`** and any other stage that copies kit
  destinations reads `assets/kit/`, which this skill does not ship. A target
  scaffolded under this domain needs its object-to-module map approved and
  written by hand, or from a kit a later change adds.

Every other published command runs exactly as `proposal-implementation`'s own
doctrine describes it, against this domain's own profile leaves instead of the
sibling's.

## What this skill has not written down

Same as the sibling, and settled the same way: `.implementation/` is a required
`.gitignore` entry, so neither a launch authorization nor a deliberation record
reaches a clone. **Settled by the operator on 2026-09-14: that is correct and
the ledger is not split.** What the forge needs to do its own work stays home;
the reasoning behind the agreements travels in the paper. Do not re-raise it as
an open gap -- see the sibling's own section for the full wording.

## Non-negotiable isolation

Every run works inside `implementations/<repo>/` and uses that repository's own
`.venv`. Never the forge's virtualenv, never system Python for target code.
`implementations/` is gitignored; the CLI refuses any target outside it, and
refuses to create a venv from a forge interpreter -- exactly as the sibling's
own doctrine states, because this is the shared engine's own behaviour, not a
domain-specific one.
