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
- Every module under `src/<Name>/` declares `__provenance__`; every id in its
  `invariants` has a matching `test_<id>`. No provenance, no merge.
- Never fabricate mathematics. A test whose claim is not traceable to the
  proposal does not belong in the suite.
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
- A screening result is never reported as the benchmark, and a winner is never
  declared from two bare means. Both settings — the fast unit-free sweep and the
  trained run over real data — carry the reduction that produced them and grant a
  verdict only past the combined standard error.

## Target layout

```
<repo>/
├── <Name>/            Notebooks/  Data/ (only if data exists)  Results/  Models/
├── src/<Package>/     the implementation (.py), one module per mathematical object
├── tests/             smoke, invariants, synthetic, findings + audit + remedies
└── pyproject.toml     isolation marker: anchors pytest/ruff to this repo
```

`<Name>` is chosen by the user. `<Package>` is its importable form: a hyphen is
legal in a directory but not in a Python identifier, so `Example-Method/` pairs with
`src/Example_Method/`. Never scaffold `src/<Name>/` when the two differ — nothing
could import it. Pre-existing code moves to its own package under `src/`, never
into `src/<Package>/`. `pyproject.toml` must carry
`[tool.pytest.ini_options]` with `pythonpath = ["src"]`: without it the suite
cannot import the package offline, and an existing file that lacks the table
counts as a gap, not as compliance.

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

- **`src/` has no implementation of the current proposal** → this is a first pass.
  Run [Flow A](#flow-a--first-pass).
- **`src/` already implements it** → run [Flow B](#flow-b--every-later-pass).

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

Every step marked **[GATE]** is a decision with a known set of answers, so **ask it
as a choice, not as prose**. Use the runtime's interactive question UI when it has
one, with the outcomes as explicit options; where it does not, write the same options
out and say which answers are accepted, then stop.

An open question — "do you want me to reorganize?" — leaves the user guessing what
the alternatives are and what each costs. Every gate here has more than two outcomes,
and the third is usually the interesting one:

| gate | the options that must be visible |
|---|---|
| reorganize | apply it · leave the layout alone · **too large: take it to its own session** |
| the name | use `<Name>`/`<Package>` as normalized · type a different one |
| implement | go ahead · stop here |
| corrections to the proposal | publish them · leave the findings open · review them one by one first |
| convert to PyTorch | convert implementation and tests · not now |
| the wiring | this draft is right · complete or correct it first |
| run the benchmark | run it · not now (it downloads a dataset and uses the machine) |

Two rules for every one of them:

- **Never present an option the flow cannot honour.** A reorganization above the
  limit is not offered as "apply it": that answer would be refused after the user
  chose it, which is worse than not offering it.
- **Say what each option costs before it is chosen**, not after. Publishing advances
  the real lineage; the benchmark downloads data and occupies the machine; declining
  the layout leaves drift that every later run will report. A choice made without its
  consequence is not a decision, and the authorization it produces is not one either.

## Flow B — every later pass

1. Read `src/` and take `latest` from `STATUS`.
2. `verify --revision <latest>`. This is the whole state of the repository in one
   answer: `structure` covers the layout, `fidelity` covers whether the code still
   matches the mathematics, plus `audit` and `validation`.
3. **No differences** → report all four as green, then run `probe --revision <latest>`
   before asking anything and follow its `nextStep`. See
   [Conversion, then benchmark](#conversion-then-benchmark). On `nothing-to-compare`
   or `already-benchmarked`, **ask the user what they want to do next** and invent
   no work.
4. **Differences in fidelity** → **[GATE] ask whether the user made those changes.**
   - **They did** → the code is ahead of the proposal. Remind them to update the
     mathematics and hand them the prompt that does it. Do not edit their code to
     match an older proposal.
   - **They did not** → the code has drifted. Correct it and re-run the validations,
     bounded by the same three passes as Flow A step 16.
## Conversion, then benchmark

Run `probe --revision <latest>` and follow its `nextStep`. The order it reports is
not a preference: an implementation that computes with numpy **cannot be trained**.
There is no autograd and nothing to place on a device, so proposing a comparison
first would ask the user to approve a run that cannot happen.

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

`probe` returns a `wiring` draft, assembled from each module's `__provenance__`
rather than guessed. **Present it and let the user complete it.** The harness knows
how to train and measure; it cannot know what makes *this* method trainable — which
modules carry the terms, where a backbone's features enter them, what the classifier
head predicts over. That is the user's mathematics, and this skill proposes rather
than decides, exactly as it does with the migration plan and the object→module map.

The draft's `offer` starts from `fromBaseline`: the backbones, datasets and trained
weights the prior work actually uses, read from its own code. That environment is
where its published results were obtained, so it is the one a comparison means
something in — proposing a set of well-known benchmarks instead would be a guess
about the field, and would measure both implementations somewhere neither has been
measured before. `lighterAlternatives` is offered beside it for when the baseline's
own setting is too slow to screen with. Offer both; do not pick for the user.

Write the completed wiring as `<Name>/Notebooks/wiring.py`, exposing `build_new` and
`build_baseline`. `build_baseline` may be `None` when the prior work cannot run under
the common reduction as it stands: that is a `not applicable` with its reason, and
the baseline is never edited to make a comparison possible.

**[GATE]** then ask before running: it is quick by design, but it is still the user's
machine, and it downloads a dataset.

Execute the notebook with the target repository's own interpreter, as with the suite.
`benchmark.py` refuses under any other and says which one to use — for this file that
is not a hygiene rule but the measurement itself: wall time and peak memory describe
whichever environment ran them, so a foreign interpreter produces a correct
measurement of the wrong thing and the summary would attribute it to this repository.

Copy `benchmark.py`, `verdict.py` and `probe.ipynb` from `assets/kit/nb/` into
`<Name>/Notebooks/`, fill in the reduction, and execute the notebook. Without
`wiring.py` the harness refuses and says what is missing — running anyway would train
a bare backbone and report it as the method. It trains each implementation over every seed, measures accuracy, wall
time, peak memory and parameter count, and writes `<Name>/Results/Probe_results.json`.

That summary is the record. A later session reads it to learn that a screening ran,
under which reduction, and against which revision — a summary naming an older
revision is stale by inspection, so nothing is stored outside the repository and
nothing can fall out of sync.

Four things decide whether the numbers mean anything:

- **It is a screening run, never the benchmark.** ResNet-18 and a slice of the data.
  A reduced setting can invert a result — a method needing capacity or volume to show
  its advantage loses here and wins at full scale. Say `probe`, `screening`, never
  "results", and print the reduction beside every number. A number that can be read
  without its reduction is a number that will be misquoted.
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

5. **Report the layout, never gate on it.** `structure` is part of the answer in
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
