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
- v1 scope is smoke + invariants + synthetic + audit + remedies. Classic SOTA
  datasets and baseline comparison are out of scope; say so instead of
  improvising them.

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
    - **Faithful** → stop here.
    - **Not faithful** → correct the code and re-enter from step 15. **At most
      three passes.** If the third still is not faithful, stop and hand the user
      the decision, with what the three attempts established. A loop with no bound
      does not fail — it keeps trying, and nobody notices.

## Flow B — every later pass

1. Read `src/` and take `latest` from `STATUS`.
2. `verify --revision <latest>`. This is the whole state of the repository in one
   answer: `structure` covers the layout, `fidelity` covers whether the code still
   matches the mathematics, plus `audit` and `validation`.
3. **No differences** → report all four as green, then run `probe` before asking
   anything. See [The comparative probe](#the-comparative-probe). If it reports no
   baseline, or a summary that is already `current`, **ask the user what they want
   to do next** and invent no work.
4. **Differences in fidelity** → **[GATE] ask whether the user made those changes.**
   - **They did** → the code is ahead of the proposal. Remind them to update the
     mathematics and hand them the prompt that does it. Do not edit their code to
     match an older proposal.
   - **They did not** → the code has drifted. Correct it and re-run the validations,
     bounded by the same three passes as Flow A step 16.
## The comparative probe

The layout keeps pre-existing code in its own package under `src/`, so a repository
that had an implementation before still has it after the reorganization. That
leftover package is a baseline, and `probe` finds it by reading the tree.

Offer the probe only when `comparable` is true and `results.status` is `absent` or
`stale`. **[GATE]** ask before running it: it is quick by design, but it is still the
user's machine.

Scaffold `<Name>/Notebooks/probe.ipynb` from `assets/kit/nb/`, fill it in, execute it,
and let it write `<Name>/Results/Probe_results.json`. That summary is the record —
a later session reads it to learn that a probe ran, under which reduction, and
against which revision. A summary naming an older revision is stale by inspection,
so nothing is stored outside the repository and nothing can fall out of sync.

Four things decide whether the result means anything:

- **It is a screening run, never the benchmark.** Small backbone, a slice of the data.
  A reduced setting can invert a result — a method needing capacity or volume to show
  its advantage loses here and wins at full scale. Say `probe`, `screening`, never
  "results", and print the reduction beside every number. A number that can be read
  without its reduction is a number that will be misquoted.
- **Speed buys repetition.** Several seeds on a small setting beat one slow run,
  because one run cannot separate a difference from its own noise. Report dispersion.
- **The slice is stratified, not random.** The proposal requires every class to be
  present in the source collection the local correspondence uses; a random slice can
  drop one, leaving that correspondence undefined. The failure would look like a
  defect of the method and be a defect of the sampling.
- **The reduction is identical for both, and the baseline is never edited to fit it.**
  It is the user's prior work. If it cannot be driven into the common setting as it
  stands, that is a `not applicable`, with the reason.

Dimensions come from what the proposal claims to improve, not from a generic
checklist. Cost — time per epoch, peak memory, parameters, inference latency —
compares cleanly even when the two predict on different statistical units. Accuracy
does not: if one predicts per instance and the other per bag, a single number would
require inventing an aggregation rule that can dominate what it claims to measure.
**`not applicable` is a legitimate cell; filling it with a number is not.**

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
