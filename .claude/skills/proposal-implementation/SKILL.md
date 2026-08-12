---
name: proposal-implementation
description: "Trigger: turn the latest managed mathematical proposal into working Python, scaffold or reorganize a target repository, or verify an existing implementation's layout and revision fidelity. Isolated venv, keyless, fail-closed."
---

# Proposal Implementation

Turn the current managed revision (`research-concept-rNN.md`) into Python that
runs, in a target repository, and then prove it: smoke, invariants, synthetic
data. Text is not the deliverable — code with a traceable link back to the
mathematics is.

## Non-negotiable isolation

Every run works inside `implementations/<repo>/` and uses **that repository's own
`.venv`**. Never the forge's virtualenv, never system Python for target code.
`implementations/` is gitignored; the CLI refuses any target outside it, and refuses to
create a venv from a forge interpreter.

## Activation Contract

Activate when the user asks to implement, code, scaffold, reorganize or verify
the implementation of the managed proposal. Do not activate for edits to the
proposal itself — that is `proposal-deliberation`.

## Hard Rules

- Bind to the revision `proposal-deliberation`'s `STATUS` reports as `latest`. Never
  guess the base and never read `proposals/` by hand.
- Never write implementation code before the user approves the mapping from
  mathematical object to module.
- Dirty target worktree → stop and report. Never mutate an unclean repository.
- Migration is `git mv` in its own separate commit, before any new code.
- Never flatten an organized subtree. A product folder with the right shape and
  the wrong name is one rename, not one move per file.
- A migration is not finished until the references move with it. Moves break
  paths exactly as renames do. Present `referenceUpdates` alongside the moves
  and never apply one without the other.
- Rewrite only what is unambiguous; report the rest. A path the skill cannot
  remap safely belongs in `staleReferences`, not in a guessed substitution.
- Clone with `GIT_LFS_SKIP_SMUDGE=1` **and** persist the skip in the clone's
  local config. Pointers are enough to reorganize; the env var only covers the
  clone, so any later checkout or reset re-downloads gigabytes and burns the
  LFS quota.
- Every test of the implementation lives in the target repository and nowhere
  else. The forge's own `tests/` cover the forge's tooling — the deliberation
  engine, the ingestion helpers — and never the materialized proposal. Deleting
  the target deletes its tests, and the next implementation starts without any:
  that is the intended consequence, not an accident.
- `tests/*.py` is the source of truth and is fail-closed. The notebook is the
  executed report, never the only place a claim is checked.
- A green result means something only when red was reachable. Two ways it is
  not: an assertion that cannot fail — never compare an expression with itself,
  in an assert or in the counter feeding one, and never assert a constant — and
  a remedy test that measures its own proposal without ever exercising the
  declared formulation it corrects. `verify` reports them as
  `trivialAssertions` and `remediesWithoutControl`.
- Every remedy test carries both poles: the remedy satisfies the criterion AND
  the declared formulation fails it. One pole alone cannot distinguish an
  improvement from a measurement that would have passed anything.
- When probing a guard adversarially, assert that the fixture actually changed
  before believing the result. A negative test whose mutation silently failed
  reports success while testing nothing.
- Check that a thing works, not that it is there. A notebook that exists but was
  never run is a claim, not a report; `verify` reads its `execution_count` and
  its error outputs and says `stale`, `errored` or `executed`.
- `verify` reads; it never executes a test. It proves the code *says* what it
  should — the revision it is bound to, an invariant declared for every claim, a
  matching test for every invariant, no assertion that cannot fail. Only running
  the suite proves the code *does* it. Never treat a clean `verify` as a green
  repository, and never compare, benchmark or publish from one that was not run.
- Every module under `src/<Name>/` declares `__provenance__`; every id in its
  `invariants` has a matching `test_<id>`. No provenance, no merge.
- Never fabricate mathematics. A test whose claim is not traceable to the
  proposal does not belong in the suite.
- **Never assert an absence you did not go looking for.** "There is no bootstrap",
  "that cannot be obtained", "the prior work has no data layer" are claims about the
  whole repository, and a reading that stopped at one file cannot support any of them.
  Before saying something is missing, look where it would live — and if the answer
  still is nothing, say where you looked, so the user can point at the place you did
  not. A plausible reason invented to explain what you failed to find is worse than
  saying you did not find it: it sounds like a finding and gets acted on like one.
- Audit the mathematics, not the code. A finding is an ill-formed term, a claim
  stated more strongly than the construction supports, a missing complement, or
  a constant that does not hold up.
- No finding without a remedy, and no remedy without validation. Both are
  measured over the same randomized sweep of 200 configurations.
- Classify every finding. `theorem` demands the full sweep; `tendency` must
  declare its measured rate and must never be asserted as a law.
- Rule on admissibility BEFORE measuring efficacy, never after. Run `admit`
  first: every equation a remedy cites must exist in the revision, and every
  symbol it relies on must be declared in `uses` and present there. Measuring a
  remedy that fails this produces numbers that read as evidence and lend the
  sweep's rigour to something that should never have reached the bench. The
  remedy suite refuses to run without the ruling.
- Notation the remedy would add goes in `introduces`. A non-empty `introduces`
  is admissible but makes the audit `needs-deliberation` — never `ok`. Adding
  notation is the deliberation's decision, not this skill's.
- Remedies live in `tests/`, never in `src/`. Establishing that a correction is
  sound is not the same as adopting it.
- This skill proposes; `proposal-deliberation` decides and publishes. Never
  write to `proposals/`. `handoff` hands the open findings over sized by their
  reach into the document: a remedy touching one equation, adding no notation
  and cited nowhere else settles inline; anything wider comes back as a prompt
  for a session of its own, because a change with implications deserves
  unhurried deliberation rather than a decision taken in passing.
- A remedy settles inline only if the finding declares `remedy_block`: the
  corrected equation written out, with the same `\tag{n}`. Prose is not a
  correction. Without it the reach may be local but the handoff still defers —
  writing the mathematics is the work, and nothing here paraphrases a
  description into a document. `verify` lists these under
  `audit.localRemediesNotWritten` so the omission is a decision, not a silence.
- To settle one inline, drive `proposal-deliberation` with the item's
  `deliberation` payload: `RESOLVE_TARGET` with its `selectedEntryId` returns
  the entry's `text`; pipe that text into `implementation_cli.py compose
  --finding <id> --entry-text -`; send the returned `replacementText` as a
  `replace` decision to `CREATE_SUCCESSOR`. Composition substitutes inside the
  entry rather than handing back the bare block, because an entry usually holds
  more than the one equation and replacing it wholesale would delete the rest.
- Adoption is read from the published revision, never assumed. The reliable
  signal is that the text the remedy replaces is gone; if nothing recognizable
  took its place the state is `changed-unrecognized` and a human confirms.
- An adopted remedy stops being a proposal and becomes the formulation, so it
  moves: its remedy test retires, its claim lands in the invariant suite as
  `test_<becomes_invariant>`, and the module implementing it declares that
  invariant. Until it does, `audit` stays `incomplete` — leaving it in the
  remedy suite would keep reporting a defect the revision no longer has, and
  would keep its claim outside the contract every other claim is held to.
- Comparison against a baseline happens only after the implementation is faithful
  and only through `probe`, never improvised mid-implementation. It reports
  `nextStep` and that order is binding: an implementation computing with numpy
  cannot be trained at all, so the PyTorch conversion is settled before a
  comparison is discussed. See [Conversion, then benchmark](#conversion-then-benchmark).
- A result is never reported as more than the bounds it was obtained under, and a
  winner is never declared from two bare means. Both settings — the fast unit-free
  sweep and the trained run over real material — carry those bounds beside their
  numbers and grant a verdict only past the combined standard error.
- **And below a declared floor of repetitions, no verdict at all.** With one
  repetition the dispersion is zero and the threshold is zero, so the rule that
  exists to suppress noise declares a winner on every row instead. Stamp the reason
  and print the table; never suppress it, because the pilot has to run the same code
  the campaign will.
- The benchmark lives in its own package beside the method's, never inside it. A
  harness declares no `__provenance__` because it implements no equation, and
  stamping one on it to satisfy the check empties the check.
- Two arms differ in what they compute **and in everything they touch**. Shared
  mutable state — running statistics, caches, how much of the generator each
  consumes — is a difference nobody declared, and a rung that ignores it credits a
  term with what the exposure did.
- **Never credit a mechanism without trying to take the credit away.** When a
  difference is attributed to something, switch that something off and re-run. Two
  runs settle what an argument cannot, and they happen before the claim is written
  down, not after somebody doubts it.
- A run below the scale the protocol declares is a **pilot**, and its numbers are
  never quoted as results — not in the report, not in the summary, not in
  conversation. Only an explicit authorization releases the full run: not a clean
  verification, not a green pilot, not the agent's own conclusion that it is ready.
  Green is not permission.
- **The checklist is made of the agreements, not of the plan of work.** Every design
  decision reached in conversation becomes an item that gets ticked off. A checklist
  derived from how the agent intends to build can be completed in full while an
  agreement never reaches the code, and nothing anywhere will say so — the omission
  arrives as a silence, and silences are not read.
- **A decision already agreed is never re-decided while implementing.** When the work
  runs into something that makes it awkward — a dependency that is not installed, a
  thing easier to print than to draw, an interface that does not fit — that is not a
  detail to resolve in passing. Say it plainly: this was agreed, this is what blocks
  it, this is what I would put in its place, this is what the substitution costs. Then
  wait. A change mentioned inside a progress report reads as housekeeping and gets
  nodded through, and afterwards nobody decided it.
- **And when something agreed turns out to be missing, find out when it went missing
  before explaining why.** A reconstruction that sounds coherent is worse than "I have
  not checked yet": it lands as a finding and gets acted on like one. The rule against
  asserting an absence nobody looked for applies to the session's own history exactly
  as it applies to a repository.
- **When a rule joins two ends — something writes, something reads — the check has to
  cross the join.** Testing each side against a fixture you wrote yourself verifies
  both halves and never the connection, which is the only thing the rule was about.
  The fixture always passes: the same hand wrote it and reads it. Run the thing, then
  ask the tool what it sees.
- **Revision drift is sized by reach, not only located.** Some changes are local — an
  equation gains a stabilizer, a constant moves — and the implementation adjusts.
  Others change what the experiment *is*: what is predicted, over which statistical
  unit, what counts as correct. Those do not oblige an adjustment, they oblige a new
  protocol, and every result, checkpoint and dimension stops meaning anything rather
  than merely going stale. Never adjust the code and re-run without ruling on which of
  the two it is; a table of the old metric computed over the new formulation is
  arithmetically correct and answers a question that no longer exists.
- **Saved models are verified like everything else.** They carry the revision they
  were trained under in their manifest, so it gets read. A checkpoint from an earlier
  revision is named as such and never analysed silently beside current ones.

## Target layout

```
<repo>/
├── <Name>/                    Notebooks/  Data/ (only if data exists)  Results/  Models/
├── src/<Package>/             the implementation (.py), one module per mathematical object
├── src/<Package>_Benchmark/   the harness: configuration, material, wiring, verdict
├── tests/                     smoke, invariants, synthetic, findings + audit + remedies
└── pyproject.toml             isolation marker: anchors pytest/ruff to this repo
```

`<Name>` is chosen by the user. `<Package>` is its importable form: a hyphen is
legal in a directory but not in a Python identifier, so `Example-Method/` pairs with
`src/Example_Method/`. Never scaffold `src/<Name>/` when the two differ — nothing
could import it. Pre-existing code moves to its own package under `src/`, never
into `src/<Package>/`. `pyproject.toml` must carry
`[tool.pytest.ini_options]` with `pythonpath = ["src"]`: without it the suite
cannot import the package offline, and an existing file that lacks the table
counts as a gap, not as compliance.

**The benchmark is a sibling package, never a subfolder of the method's.** Two rules
already in force decide this between them, and there is exactly one place left that
satisfies both: `verify` recurses into `src/<Package>/` demanding `__provenance__`
from every module, and it counts any tracked `.py` outside `src/` and `tests/` as a
stray module. So a harness beside the notebooks breaks the structure at the first
commit, and a harness inside the method's package breaks the fidelity — unless
somebody stamps a provenance on it, which is worse than either: provenance says
"this module implements these equations", a harness implements none, and falsifying
it hollows out the one check that keeps the code tied to the mathematics.

Nothing in the benchmark package is part of the formulation. Deleting it leaves the
method intact, which is the property the name is promising.

## Decision Gates

| Situation | Action |
| --- | --- |
| No repository yet | Ask: create new, or clone an existing URL |
| Repository empty | Scaffold the layout directly; no migration commit |
| Layout already compliant, code present | Verification mode only |
| Layout drift | `plan` → present the map → user approves → `apply` |
| Product folder right shape, wrong name | `plan` proposes one rename; subtrees stay intact |
| Plan reports `referenceUpdates` | Show them; `apply` rewrites them in the same commit |
| `verify` reports `staleReferences` | A path points nowhere: report before writing any code |
| Plan reports `unclassified` or `conflicts` | Ask where those files belong; never guess |
| `verify` reports structure drift | Report it as its own finding, ask before fixing |
| `verify` reports stale modules | Report revision drift separately; ask before rewriting |
| Target outside `implementations/`, or dirty tree | Refuse and report the guard |

## Where to start: the repository is the memory

**Every invocation begins the same way — look at `src/` before asking anything.**
Nothing about a previous session is stored anywhere; the repository itself is the
record. An implementation sitting in `src/` is the evidence that this skill already
ran here, which means the layout question was already put to the user and answered.
Whether they accepted or declined it is not worth recovering: either way it is
settled, and asking again treats a decision as if it had never been made.

That state is *read*, never *remembered*. Nothing is carried forward except facts
about the repository as it is now, so nothing can drift out of date and nothing a
past session concluded can bias this one.

Route on **existence, not on fidelity**. Whether the implementation still matches the
latest revision is a measurement, and `verify` is what makes it — asking it here
would send a repository whose code is bound to `r14` while `latest` is `r16` through a
full first pass, re-implementing from scratch something that only needs bringing up to
date. Drift is Flow B's fourth step, not a reason to start over.

- **`src/` holds no implementation at all** → first pass. Run
  [Flow A](#flow-a--first-pass).
- **`src/` holds one, whatever revision it is bound to** → run
  [Flow B](#flow-b--every-later-pass), which measures the drift and handles it.

## Flow A — first pass

1. `node .claude/skills/proposal-deliberation/engine/cli.mjs '{ "operation": "STATUS" }'` → take `latest`.
2. **Ask for the repository URL** and clone it:
   `GIT_LFS_SKIP_SMUDGE=1 git clone <url> implementations/<repo>` (or `git init`), pin the
   LFS skip in the clone's local config (see `references/usage.md`), then `env`.
3. Install dev dependencies with the printed target `pip`, never the forge's.
4. **Is there prior work, and does its layout already comply?** Run `plan`. If
   `status` is `compliant`, go to step 6. Otherwise present every rename, move and
   reference update with its reason, and read `reorganization`:
   `decisionCount` is what the user actually reads: every move, every rename, every
   reference rewrite. `carriedFiles` is reported alongside it and is worth saying out
   loud — "this renames one folder and sweeps thirty-seven files with it" — but it is
   not what decides the branch. Renaming a folder of two hundred files is one line to
   read and one command to undo; counting those files would measure blast radius and
   call it reviewability, forcing a separate session for a trivial change.
   - **`scale: "reviewable"`** → **[GATE]** ask whether to reorganize. On approval,
     `apply` lands renames, moves and reference updates in one commit. On refusal,
     continue without touching the layout — that refusal needs no record, because
     the next session reads the tree, not a note about it.
   - **`scale: "large"`** → **do not apply it, even if the user says yes.** A list
     this long is approved without being read, and an unread approval is not one.
     Say so, and hand the user a self-contained prompt that performs exactly this
     reorganization in a separate session. Then continue without it.
5. Fill scaffold gaps from `assets/` (pyproject, `__init__.py`, smoke test, notebook).
6. **Ask for the name.** Run `name --name "<whatever they typed>"` and show both
   forms it returns — the `<Name>/` directory and the `src/<Package>/` package —
   then **[GATE]** confirm before writing anything with them.
7. **[GATE] Ask for authorization to implement.** Nothing below writes code until
   this is given.
8. Present the object → module map. Wait for approval. Only then write code.
9. Write one module per object with `__provenance__`, plus its invariant tests.
10. Audit: sweep 200 configurations, declare each finding in `tests/findings.py`
    with its kind, status, measured rate and proposed remedy.
11. `admit --revision <latest>`: rule on admissibility before anything is
    measured. Only admitted remedies proceed.
12. Validate every admitted remedy over the same sweep: it must resolve its
    finding and preserve the properties already established.
13. **Report the findings and say what they cost to establish.** For each one:
    what is wrong, what the remedy is, and that it was **detected over 200
    configurations and confirmed over the same 200**. A remedy presented without
    that number reads as an opinion; it is a measurement, and the user is entitled
    to know it before authorizing anything.
14. **[GATE] Ask for authorization to apply the corrections to the proposal and to
    the code.** On approval this session drives the deliberation engine itself:
    `handoff` sizes each finding, `RESOLVE_TARGET` locates the entry, `compose`
    builds the replacement, and `CREATE_SUCCESSOR` publishes the next revision.
    See `references/usage.md`. Publishing advances the user's real lineage, so it
    happens only behind this gate.
15. Run the suite with the target interpreter, then execute the notebook.
16. **Final check.** `verify --revision <latest>` → report `structure`, `fidelity`,
    `audit` and `validation`.
    - **Not faithful** → correct the code and re-enter from step 15. **At most
      three passes.** If the third still is not faithful, stop and hand the user
      the decision, with what the three attempts established. A loop with no bound
      does not fail — it keeps trying, and nobody notices.
    - **Faithful** → **do not stop here.** Continue into Flow B step 3: the
      repository is now in exactly the state a later invocation would find, so it
      gets the same answer. Ending here would make the reply depend on how the user
      arrived rather than on what the repository holds, and would leave them to
      re-invoke just to be told what comes next. `probe` is read-only and instant;
      what it reports is a question, not work, and the gate is where they stop.

## How a gate is asked

**Speak the language the user is speaking.** The repository, the code, the commits and
every file written stay in English; the conversation does not. A skill that answers a
Spanish session in English has changed the subject.

**And speak plainly.** Command names, JSON fields and status codes are this skill's
plumbing, not the user's. Say what was found and what it means; name a command only
when the user has to run it themselves.

**The subject is the plan of work, not the mathematics and not the code.** When
proposing how something will be built or measured, what the user is judging is the
sequence and the friction: what gets built, in what order, what has to meet what, and
where the two sides do not fit. Not equations, not identifiers.

They wrote the code once and can no longer recite it; they deliberate the mathematics
elsewhere and do not need it restated here. A draft carrying either is asking them to
decode before they can judge, and every symbol it spends is a place they stop to
recall instead.

**Do not open with a status report.** When the verification came back clean, that is a
precondition, not news: one sentence saying the implementation matches the latest
revision and the suite passes, and move on. Listing what was checked, how many tests
ran and which fields came back green spends the reader's attention before the proposal
starts. A report is owed when something is *wrong* — then it is the whole message.

So narrate the work:

- **What will be built and in what order.** Plainly, as steps.
- **Where the two sides do not line up, and how that is resolved.** This is the part
  worth their attention: prior work and new work were built for different shapes, and
  making them meet always costs something. Say what does not fit, **propose the way
  through**, and say what that way gives up.

  A friction named without a proposed resolution is the problem handed back. The user
  cannot argue with a question — they argue with a proposal, and rejecting one is how
  they steer. Ending on "how would you like to handle this?" after correctly finding
  the hardest part is the same evasion as a menu, one level deeper: it does the
  diagnosis and stops before the prescription.
- **The experiment itself, stated as a protocol.** This is what the user is actually
  agreeing to, and it is where a draft most often goes vague. The standard is two
  things: someone else could run it and get the same thing, and the user can disagree
  with a *specific* choice rather than with a mood.

  What that takes depends entirely on the experiment, and the repository has already
  been read by the time a draft exists, so write it from what is there. Whatever the
  inputs are, say which ones and where they come from. Whatever has to be built or
  configured to run it, say which and at what size, and why that size. Whatever the
  comparison needs that the material does not already contain, say how it is
  constructed. However many times it runs, say how many and what changes between runs.
  Numbers, not adjectives.

  **Give the material its roles, and keep them disjoint.** Wherever something is fitted
  to the material, at least two roles exist — what it is fitted on and what it is
  judged on — and they must not overlap: judging on what was fitted measures how well
  it absorbed that material, and it flatters each side by a different amount, most of
  all the side that absorbs best. If anything at all is chosen by looking at outcomes,
  that choosing needs a third role of its own, or the judgement is reading a decision
  it already made. Say the proportions, say how the division is drawn, and say what
  every role is used for. **Do not carve a role you will not use** — it costs material
  and buys nothing.

  **And choose those proportions, do not inherit them.** A conventional division copied
  because it is conventional is not a decision, and it meets the letter of this rule
  while deciding nothing. The share that goes to judging follows from what the
  measurement has to resolve — the next paragraph — and the two are one thought: work
  out the difference worth detecting, work out how many units that takes, give the
  judging role at least those, and let what remains fund the rest. If the material
  cannot fund every role at that size, that is the finding, and it is said before
  anything runs rather than discovered after a scale has already been proposed.

  Say how each role is composed, not only how large it is. Whatever has to be present
  in every one of them for the comparison to be defined must be present in every one
  of them; a division drawn without regard for that produces a failure that reads as a
  defect of the method and is a defect of the division.

  **Say what the measurement can resolve, before running it.** Count the units the
  verdict will rest on and state the difference that many can separate from noise. A
  protocol whose verdict rests on too few will answer "indistinguishable" whatever
  happens, and the user pays the whole run to learn nothing. That arithmetic is
  cheaper than the run, so it happens first, and it is what decides the scale rather
  than a number that felt reasonable.

- **What is held identical across both sides.** A comparison means something only when
  one thing differs. Name everything the two share and the single thing they do not —
  whatever those turn out to be for this experiment. Without it the measurement is of
  whatever else drifted, and no result can be attributed to the difference it claims
  to be about.

  **Free choices count as part of what differs.** Any knob left open — a coefficient, a
  threshold, a stopping point — is a choice, and if one side's is tuned while the
  other's is guessed or left at whatever its author defaulted to, then the sides differ
  in two things and the claim that only one changed is false. Either both are chosen
  the same way, on the same material, by the same rule, or both are fixed at a declared
  value and the report says so. Tuning one side is the easiest way to produce a result
  that survives every other check and means nothing.

- **What it depends on that might not hold** — data that has to be present, something
  that has to download, something assumed about their setup.

Mathematics enters only when a constraint forces a decision, and then as one plain
sentence about what is required, never as an equation. A file or a function is named
only when the user will open it themselves.

**Generic in the source, concrete in the proposal.** That this skill knows nothing
about any particular field is a property of its code — no dataset, no architecture, no
method hardcoded anywhere. It is not a property of the conversation. By the time a
draft is written the repository has been read: what the prior work trains on, how it
loads it, what shape each side expects. Use it.

So the recipe is specific — in whatever terms this experiment is made of. How many
repetitions and why that many. Every proportion, ratio and threshold, named. Anything
the comparison needs that the material does not already provide, and how it gets
built. Numbers the user can disagree with, not adjectives they can only nod at.

A proposal that stays abstract to remain general has confused generality with
vagueness: generality means the *skill* works for any paper, not that its *plan* works
for none. The skill carries no assumption about what an experiment is made of; the
draft carries every detail of this one.

Two kinds of gate, and treating them alike is the mistake to avoid.

### What happens to an agreement after it is made

A gate produces agreements, and agreements are the thing this flow loses. They are
reached in conversation, they live in nobody's file, and by the time the code is
being written the only record of them is a memory that re-decides freely.

**Write them down as the checklist.** Not the steps of the build — those are the
agent's own plan, and it can finish every one of them while an agreed thing quietly
never happens. The items are what was settled: this figure, that instrument, this
proportion, that ordering. Then an agreement that never reached the code shows up as
an unticked item instead of as nothing at all.

**And when implementation collides with one, that is a gate, not a detail.** The
collision is real and worth reporting — a package missing, a rendering that is far
easier as text than as a picture, an interface that will not take the shape agreed.
What is not allowed is resolving it alone and mentioning it on the way past. Name the
agreement, name what blocks it, name the replacement and what it gives up, and wait
for a yes.

The substitution is usually the more defensible engineering choice, and that is
exactly why it slips through: it looks like tidiness rather than a decision. It was
still the user's to make.

### Decisions — offer the options

A decision has a knowable set of outcomes: reorganize or not, convert or not, run or
not. Ask it as a choice, using the runtime's interactive question UI when there is
one. An open "do you want me to reorganize?" leaves the user guessing what the
alternatives are and what each costs. The third outcome is usually the interesting
one:

| gate | the options that must be visible |
|---|---|
| reorganize | apply it · leave the layout alone · **too large: take it to its own session** |
| the name | use `<Name>`/`<Package>` as normalized · type a different one |
| implement | go ahead · stop here |
| corrections to the proposal | publish them · leave the findings open · review them one by one first |
| convert to PyTorch | convert implementation and tests · not now |
| run the benchmark | run it · not now (it downloads a dataset and uses the machine) |

- **Never offer an option the flow cannot honour.** A reorganization above the limit
  is not offered as "apply it": that answer would be refused after the user chose it.
- **State each option's cost before it is chosen**, not after. Publishing advances the
  real lineage; the benchmark occupies the machine; declining the layout leaves drift
  every later run will report. A choice made without its consequence is not a
  decision, and the authorization it produces is not one either.

### Design — a conversation, and one question at the end of it

The wiring and the object→module map are **not** decisions, and they are not
questionnaires either. They are things to work out together, and the skill already
holds what it takes to open the conversation: the provenance of each module, the
baseline's own code, what it trains on and how it loads it.

**No options, no menu, no "how do you want to handle this".** Offering approaches to
choose between returns the work to the user while holding the context that would have
answered it, and a menu is that same evasion wearing a structure. This is the
deliberation tutor's posture at a smaller scale: propose, say what you are unsure of,
listen, argue back when the answer does not hold, and keep going until it settles.

**Tell it, do not report it.** Narrate what you found and what you would do with it —
not which commands you ran, not what the JSON came back with, not a list of fields.
The user does not need the mechanics to judge the idea; the mechanics are this
skill's problem. Say what the repository turned out to contain, what that suggests,
and what still worries you.

What the conversation carries:

- **The proposal**, concrete enough to argue with. Vague is not humble: a draft too
  soft to be wrong cannot be corrected either.
- **Where each part came from** — read, inferred, or assumed. The three are not
  equally trustworthy and the user is entitled to know which is which.
- **Your own doubts, raised by you.** Not "let me know if this is right", but the
  specific thing you could not settle from the repository and why it matters. A
  proposal that hides its soft spot is asking for approval, not for review.

**Only ask when the conversation has converged.** You decide when your doubts are
answered and the design is reasonable, and you say what changed your mind. Then, one
question and only one: implement this? Not before — asking earlier turns a
deliberation into a form, which is what this section exists to prevent.

**"Correct something else first" is not a request for a menu.** When the user pushes
back without naming the piece, do not answer with a list of the parts in play for
them to pick from: that is the questionnaire returning in another shape, and it asks
them to do the locating. Go back to the part you were least sure of, say why it is
still bothering you, and open there. If you genuinely cannot tell which piece they
mean, ask that — one question, in their words, not a numbered inventory of your own
design decisions.

## Flow B — every later pass

1. Read `src/` and take `latest` from `STATUS`.
2. **Run the suite with the target interpreter, then `verify --revision <latest>`.**
   Both, and in that order — they answer different questions and neither substitutes
   for the other.

   `verify` **reads**: it checks the layout, that every module still declares the
   revision it was written against, that every invariant it names has a matching
   test, that no assertion is one that cannot fail, and that the notebook was
   actually executed. What it cannot tell you is whether any of those tests pass.
   Running the suite is what proves the code *does* what it says; `verify` proves it
   *says* what it should.

   Skipping the run is how a repository reaches a benchmark while an invariant is
   broken: every provenance intact, every id matched, `fidelity` clean, and a claim
   failing underneath. That gap is widest right after a change of backend, which
   rewrites how every number is computed while leaving every declaration untouched.
3. **Suite green and no differences** → report both, then run `probe --revision <latest>`
   before asking anything and follow its `nextStep`. See
   [Conversion, then benchmark](#conversion-then-benchmark). On `nothing-to-compare`
   or `already-benchmarked`, **ask the user what they want to do next** and invent
   no work.

   **`piloted` is its own state and never reads as finished.** A record whose scale
   sits below the one the protocol declares is neither absent nor done. Report it
   precisely — how many repetitions and how long it ran, what the protocol asks for,
   what the full run costs from the measured time, and what the configuration declares
   but has never exercised — and then leave the question open. Not a menu: the pilot
   exists to be the place where somebody looks, adds a test, moves a proportion, and
   runs it short again, and a list of three buttons closes exactly the door it was
   built to hold open. The decision to release the full run appears only after the user
   says there is nothing left to change.
4. **A failing test** → that is the finding, before any question about fidelity. Report
   which claim broke and stop; a red suite is not a state to compare from.
5. **Differences in fidelity** → **[GATE] ask whether the user made those changes.**

   Read `drift` before saying anything: it crosses the sections that actually differ
   between the revision a module declares and the current one with the sections that
   module declares. A module bound to an older revision whose own sections never moved
   needs re-binding, not rewriting — bookkeeping, not mathematics — and saying "nine
   modules are stale" when one equation changed tells the reader there is work and
   nothing about where. `benchmark` answers the same question for the bench: which
   arms a changed section reaches, so the experiment is re-run because something it
   depends on moved rather than because a string did.
   - **They did** → the code is ahead of the proposal. Remind them to update the
     mathematics and hand them the prompt that does it. Do not edit their code to
     match an older proposal.
   - **They did not** → the code has drifted. Correct it and re-run the validations,
     bounded by the same three passes as Flow A step 16.
## Conversion, then benchmark

Run `probe --revision <latest>` and follow its `nextStep`. The order it reports is
not a preference.

**A baseline is asked about first.** Without one there is nothing to compare, and
then the backend is nobody's business: numpy is where the mathematics is proved —
no autograd, no device, no optimizer to mask a wrong formula — and for a proposal
nobody is going to train, that is where it belongs and where it can stay. Demanding a
conversion there would ask for work with no purpose and make a finished
implementation read as unfinished.

**With a baseline, the conversion comes before the comparison**, because an
implementation computing with numpy cannot be trained at all. Proposing a benchmark
first would ask the user to approve a run that cannot happen.

The verification before all of this does not care which backend it finds. It is a
static reading — the revision each module is bound to, an invariant for every claim,
a test for every invariant, no assertion that cannot fail — and the suite is run with
whatever interpreter the target has. Both work the same whether the implementation
computes with arrays or with tensors, because which one is right depends on the stage
the proposal is at, not on this skill's preference.

### `nextStep: "convert"` — port the implementation to PyTorch

`backend` reports which files still compute with numpy. **[GATE]** ask, then convert
the modules under `src/<Package>/` **and their tests together**. `mixed` is the state
to avoid, not a milestone: modules that train while the tests still assert over numpy
give a passing suite that measures something the trained model never touched.

The mathematics does not change — this is a change of backend, not of method — so
`verify --revision <latest>` must still report `fidelity` clean afterwards, and every
invariant test must still hold. Re-run the audit: a remedy established over the numpy
sweep has not been established over the converted one.

### `nextStep: "benchmark"` — propose the wiring, then train both and measure

Only reachable once `backend.trainable` is true and a baseline exists.

`probe` returns a `wiring` draft assembled from each module's `__provenance__` and
from the baseline's own code — the modules with their sections and equations, the
baseline package, what it trains on and how it loads it.

That is raw material for you, not output for the user. **Open a conversation with it**
— see [Design — a conversation](#design--a-conversation-and-one-question-at-the-end-of-it).
Say what you found in their repository and what you would wire to what: which modules
carry the trainable terms, where the backbone's features enter, what the head predicts
over. Mark what you read, what you inferred and what you assumed, and raise whatever
you could not settle. Then work it out with them.

The harness knows how to train and measure; it cannot know what makes *this* method
trainable, and that is the one part worth the user's attention. Handing them the three
questions unanswered wastes the context this skill is already holding.

The draft's `offer` is `fromBaseline` and nothing else: the backbones, task names,
trained weights, **data entry points** and notebooks the prior work actually uses,
read from its own code. That environment is where its published results were
obtained, so it is the one a comparison means something in.

The entry points matter more than the names. A task name says what was measured; a
loader says how to measure it again, and the wiring needs the second. Notebooks
outside the proposal are read too — that is usually where the prior experiments
actually ran.

**Read `acquisition` before saying anything is unavailable.** A package can resolve a
directory it never creates; what creates it usually lives in a notebook, and a reading
that stopped at the package would conclude the material is unobtainable while the
thing that obtains it sits one file away. `acquisition` reports what was found about
how each side gets hold of what it trains on — a download, a clone, an archive, a
mounted directory. Material that is absent until something runs is not material that
cannot be had, and treating the two alike discards most of a user's experimental
ground for no reason.

**Read `foundNothingFor` before concluding anything.** The reading is a heuristic over
English word-stems and structure, so it misses a plausible variant and misses a
repository named in another language entirely. Where it reports finding nothing for a
kind, `readBy` says how it looked: put that to the user and ask them to point, rather
than telling them their baseline has no data layer. An empty list is a miss, and
presenting it as an absence would be the flow concluding something it never
established.

Nothing is suggested from a list. This is a forge for papers, not for one field: it
cannot know which models or datasets are reasonable for mathematics it has not read,
and offering a catalogue of well-known benchmarks would push both implementations
into a setting neither has been measured in. If the baseline's own environment is too
heavy to screen with, say so and let the user name a lighter one.

Write the completed wiring as `src/<Package>_Benchmark/wiring.py`, exposing
`build_new`, `build_baseline` and **`build_data`**. `build_baseline` may be `None`
when the prior work cannot run under the common reduction as it stands: that is a
`not applicable` with its reason, and the baseline is never edited to make a
comparison possible.

The harness owns training and measuring and nothing else: it names no dataset and no
architecture, because a catalogue there would dictate the experiment — the wiring
would be forced to pick whichever well-known set the baseline happens to touch, and
the reported common environment would be an intersection with that list rather than
the environment the prior results came from. `build_data` belongs to the wiring for
the same reason the builders do.

Copy `benchmark.py`, `verdict.py` and `probe.ipynb` from `assets/kit/nb/` — the two
modules into `src/<Package>_Benchmark/`, the notebook into `<Name>/Notebooks/` — fill
in the reduction, and execute the notebook. Python that lives beside a notebook is a
stray module the moment it is committed; see [Target layout](#target-layout). Without
`wiring.py` the harness refuses and says what is missing. It trains each
implementation over every seed, measures accuracy, wall time, peak memory and
parameter count, and writes `<Name>/Results/Probe_results.json`.

**[GATE]** ask before running: it is quick by design, but it is still the user's
machine, and it downloads a dataset.

Execute the notebook with the target repository's own interpreter, as with the suite.
`benchmark.py` refuses under any other and says which one to use — for this file that
is not a hygiene rule but the measurement itself: wall time and peak memory describe
whichever environment ran them, so a foreign interpreter produces a correct
measurement of the wrong thing and the summary would attribute it to this repository.
Where there is no interpreter of its own to compare against — a hosted runtime with no
virtualenv in the checkout — it stamps interpreter, platform and device into the
summary instead of refusing, so a table produced elsewhere is labelled as produced
elsewhere rather than attributed to this machine.

### The record a later session reads

That summary is the record, and it is the only one. A later session reads it to learn
that a run happened, under which reduction, and against which revision — nothing is
stored outside the repository, so nothing can fall out of sync.

Three properties make it usable rather than merely present:

- **It lives where the verification looks.** A correct record at a path nobody opens
  protects nothing.
- **Its revision declares it stale by inspection**, with no bookkeeping anywhere else.
- **The readable summary beside it is generated, never written by hand.** It is emitted
  by the notebook along with the results, carrying the revision, the protocol read from
  the configuration, the arms and the numbers. Regenerated on every run, it cannot
  drift from what it describes, because it *is* what it describes. A hand-written
  summary is a second source of truth: it goes stale in silence and is believed anyway,
  which is the same failure as a notebook that exists and never ran.

The benchmark package declares, like every module of the method, **which revision it
was built against and which sections and equations each arm exercises**. It carries no
`__provenance__` — it implements no equation — but without that declaration nobody can
answer the question a new revision immediately raises: does this change oblige the
bench to change? With it, the drift report names the arms a changed section reaches.

**And it declares its own premises beside them**: what kind of prediction the protocol
assumes, over which statistical unit, by which metric and in which direction. Those
are what a change of reach destroys — a formulation that moves from deciding a class
to estimating a quantity leaves every arm intact and every dimension meaningless.
Nothing can rule on that automatically, and nothing should try. What the tool can do
is put the premises beside what changed, so the question *is this still the same
experiment* gets asked with them in view instead of not getting asked at all.

### What has to survive the session, and what cannot be recovered later

- **Two phases, two notebooks: one trains and measures, the other loads and analyses.**
  The split is what makes a later question cheap — anything computable from weights and
  data can be added whenever it occurs to somebody. It comes with a consequence that
  has to be said out loud rather than discovered: **whatever exists only while training
  runs must be recorded now or it is gone.** Loss trajectories, per-epoch measurements,
  what a quantity did on its way to its final value — none of that can be recovered
  from a checkpoint, and re-running the campaign is the only way back.
- **A manifest with explicit indices beside every kept artefact.** Rebuilding the
  material by re-running the draw depends on every library involved producing the same
  permutation it produced the first time, which nobody promises across versions. Write
  down which inputs went where. A model that travels without its material can only be
  measured on something else.
- **The formulation's preconditions are guaranteed by the sampler.** Where the
  mathematics requires a non-empty index set, a positive trace, a class present on both
  sides, the pipeline arranges it by construction. The code that raises is right to
  raise; the mistake is letting a draw provoke it in the middle of an epoch and reading
  the crash as a defect of the method.

### A ladder, not a duel

Two complete methods measured against each other answer *which one wins* and cannot
answer *which piece did the work*. The second question is the one a paper has to
answer, and it costs almost nothing to ask at the same time: the arms differ from one
another by one thing at a time, and the pairs are written down before anything runs.

- **A floor for every statistical unit, not one floor.** The arm with its adaptation,
  correction or auxiliary term switched off — everything else identical — is what a
  gain is read against. When the two sides predict over different units, each family
  needs its own floor, or a gain cannot be separated from the representation that
  produced it.
- **One rung, one difference, and its reading declared.** Write what each pair is
  supposed to reveal next to the pair. A ladder whose rungs differ in two things is a
  table of numbers nobody can attribute.
- **Equalize what the arms *touch*, not only what they *compute*.** This is the
  expensive one. An arm that looks at data another arm never looks at is already
  different, even when it computes nothing from it: shared mutable state — the running
  statistics of a normalization layer, a cache, a moving estimate, how much of the
  random generator each arm consumes — is a channel through which arms differ without
  anyone declaring it. Enumerate that state and make every arm touch it identically,
  including the floors that have no use for it. Otherwise the rung credits the term
  with what the exposure did.
- **Equalize the unit of work per step.** Material per update and number of updates,
  fixed and declared. Two sides fed different amounts per step are being compared on
  their optimizer.

### Proving the comparison measures anything at all

A rung can read zero for two reasons that look identical on paper and are not: the
mechanism does nothing, or the mechanism was given no weight. Three habits keep them
apart, and each is cheap enough that skipping it is never the economical choice.

- **Refute a result with the smallest decisive experiment.** When a difference is
  credited to a mechanism, switch that mechanism off and see whether the difference
  survives. Two runs settle what an argument cannot, and the answer arrives before
  anything is written down. This is the audit's adversarial refuter, pointed at
  results instead of findings.
- **Report each declared component's share of the objective.** A term that is
  correctly implemented and multiplied by something tiny produces a table of exact
  zeros that reads like a result. Without the share, "it had no effect" and "it had no
  weight" are indistinguishable.
- **Calibrate the free scalars by measurement, not by inheritance.** A coefficient
  taken from prior work was calibrated for prior work's scale. Sweep it over decades
  on a single cell and find where the term begins to move the outcome, before the grid
  runs. It costs minutes and decides whether the whole campaign says anything.

### The pilot, and never launching the long run blind

A campaign that takes a day to run has to be wrong cheaply first. The pilot is not a
rehearsal of the campaign — it *is* the campaign, at a scale small enough to be wrong
in ten minutes.

- **Two knobs separate the pilot from the full run, and nothing else does.** Every
  number that defines the experiment lives in one configuration; the pilot is that
  configuration with the repetition count and the length lowered. If the pilot is a
  different program it proves nothing about the program that matters.
- **The configuration declares the scale the verdict requires, not only the scale
  running now.** Without both, a record of the pilot and the configuration agree with
  each other and everything looks finished.
- **Time one cell before committing the grid.** An estimate of the cost is cheaper
  than the cost, and it belongs as the notebook's first step rather than as a sentence
  in conversation. Report the measured figure, never the guessed one.
- **Repetitions go in the outermost loop**, so a repetition varies the material it
  draws and not merely the initialization.
- **Every change is exercised at pilot scale.** Adding an arm, adding a test, moving a
  proportion: change it, run it short, look, change it again. That cycle is what the
  pilot exists for.
- **After a revision changes, the short run comes back before the long one.** The arms
  may have moved with the mathematics, and the temptation once the code is adjusted is
  to release the whole thing.
- **Nothing releases the full run except an explicit authorization.** Not a clean
  verification, not a green pilot, not the agent concluding it is ready. Green is not
  permission.

While a run stands at pilot scale, its numbers are never quoted as results — not in
the report, not in the summary, not in conversation.

### The partition, when the comparison trains

This section is about training, so it says the ordinary thing plainly rather than
leaving it to be rediscovered: **propose a training / selection / evaluation split, by
name, in the first draft.** Whatever is fitted learns from the first; anything chosen
by looking at outcomes — a coefficient, a stopping point, a threshold — is chosen on
the second; the verdict is read only from the third. They are disjoint, and nothing
from the third is seen before the verdict.

The general rule this instantiates is in
[Design — a conversation](#design--a-conversation-and-one-question-at-the-end-of-it):
roles kept disjoint, sizes derived from what the measurement must resolve rather than
copied from convention, composition stated and not only size. Here that means: say the
proportions and where they came from, say how each part is drawn, and say what happens
to any part you would carve and not use — if nothing is chosen by looking, the middle
one is not needed and taking it costs material for nothing.

When there are two sides being compared, the split is the same for both and drawn
once. A comparison whose sides saw different material is not measuring the method.

Four things decide whether the numbers mean anything:

- **It is bounded, not shrunk.** The scale comes from what the verdict has to resolve,
  so what it answers, it answers — but it answers one question. A setting sized to
  separate a three-point gap says nothing about an advantage that only appears further
  up, and a number read without its bounds beside it will be taken for more than it
  is. Print them together, every time.
- **Speed buys repetition.** Several seeds on a small setting beat one slow run,
  because one run cannot separate a difference from its own noise. Report dispersion,
  never a bare mean.
- **The slice is stratified, not random.** The proposal requires every class to be
  present in the source collection the local correspondence uses; a random slice can
  drop one, leaving that correspondence undefined. The failure would look like a
  defect of the method and be a defect of the sampling. `benchmark.py` enforces this
  and raises rather than returning a quietly smaller slice.
- **The reduction is identical for both, and the baseline is never edited to fit it.**
  It is the user's prior work. If it cannot be driven into the common setting as it
  stands, pass `None` as its builder: the run records `not applicable` with the reason.

### One table, two settings, and a winner per row

Both settings answer the same question — where does each implementation hold — so
they share one shape and one set of rules, in `verdict.py`. The synthetic sweep is
fast and unit-free; the trained run swaps in a real model over real data. Same table,
different instrument.

Every row declares which direction wins it, and **a verdict is only granted when the
means differ by more than their combined standard error.** Anything closer is
`indistinguishable`. That threshold is the whole reason several seeds are run:
comparing two bare means always produces a winner, because every measurement differs
from every other at enough decimal places, and reporting that is reading noise out
loud. A dimension with no better direction — a parameter count — is reported and not
contested.

**And the threshold needs a floor under it, because below one it inverts.** With a
single repetition the dispersion is zero, so the combined standard error is zero, so
*every* row declares a winner from a bare difference — the rule turns into its own
opposite exactly where the protection was most needed. Declare a minimum number of
repetitions; below it, grant no verdicts, stamp the reason in the header and in the
record, and print the table anyway. Suppressing it would make the pilot a different
program from the campaign, which is the one thing the pilot may not be.

Four more things separate a table that informs from one that flatters:

- **When a claim can be satisfied by degenerating, measure the complement.** A
  distance that falls may be alignment or collapse, and the first number alone calls
  both a success. The measurement that tells them apart is reported beside it, always,
  and neither is reported alone.
- **Report the observed range and how it varies across settings, not only the mean.**
  A claim about scale — that a quantity stays bounded, that it behaves the same
  everywhere — is only a claim until its range is printed. The variation across
  settings is the sharper half: a common scale means the same quantity lands in the
  same range whichever configuration it is measuring.
- **Use paired differences when no single setting resolves anything.** Averaging raw
  values across settings folds each setting's difficulty into the dispersion and
  drowns the effect. The difference between two arms measured within the same setting
  cancels that difficulty, and agreement across settings is what carries a reading
  that no single setting could support.
- **Keep the median artefact, never the best.** Whatever is saved for later inspection
  represents the method only if it is typical. The best of thirty is an extreme of
  thirty draws, and what gets inspected afterwards describes the luckiest run.

Dimensions come from what the proposal claims to improve, not from a generic
checklist. Cost — wall time, peak memory — compares cleanly even when the two predict
on different statistical units. Accuracy needs a metric both sides can carry: the
existing probe in this lineage used a unit-free separation statistic precisely so it
could compare across units, which is worth reaching for before declaring anything
incomparable. Where no such metric exists, the row is `not applicable` with its
reason. **`not applicable` is a legitimate cell; filling it with a number is not.**

Close with the tally: where the new implementation wins, where the baseline does,
what was indistinguishable, and what could not be compared. The reader should not
have to count rows to learn the answer.

6. **Report the layout, never gate on it.** `structure` is part of the answer in
   step 2, so drift is always visible. But it does not stop the flow and it is not
   asked about again: that question belongs to the first pass, and it was answered
   there — including when the answer was "no".

## Output Contract

Report: the bound revision, the target path, the migration commit hash (if
any), the object → module map, the test result, and the three verification
statuses (`structure`, `fidelity`, `audit`, `validation`) separately. For each finding give
its kind, the equations it touches, its status with the measured rate, and the
remedy with the equations the remedy would change. State scope left out. Never
claim verification passed without the `verify` output and a green suite, and
never report a finding whose remedy validation did not run.

## References

- `references/usage.md` — worked invocations of every command.
- `scripts/implementation_cli.py` — `env`, `plan`, `apply`, `admit`, `verify`. Stdlib only.
- `assets/` — pyproject, module, test and notebook templates.
