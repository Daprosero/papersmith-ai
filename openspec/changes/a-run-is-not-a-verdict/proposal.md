# Proposal: A Run Is Not A Verdict

## Problem statement

The position ladder catches a red suite today **by convention, not by structure.**

`MIL-CREDA/AGREED.md` position item 1 is two-state and witnessed by
`` `@notebook Notebooks/verification.ipynb` ``. That notebook runs the suite and then
asserts on the exit code. A red suite raises, the cell lands an error output,
`notebook_execution()` reports `status: "errored"`, `_derive_notebook` returns `False`,
`position_state` reports a disagreement, and the next `gate`/`step` refuses. This works,
and it was verified live.

**Nothing in the forge knows that cell checked an exit code.** `notebook_execution` and
`_derive_notebook` see "a notebook whose cells did or did not error". A verification
notebook written without the assert would launder a red suite as `executed`, and every
forge-side reading would be byte-identical to the honest case. The owner's fixed rule —
*that something runs does not mean it is right* — currently rests on the notebook author
having remembered to write one line.

**The gap, stated generally: the forge has no witness kind whose derivation is tied to a
callable's raise/return outcome.** `impl_steps.run_step` already produces exactly that
outcome, structurally, in a subprocess under the target's own interpreter — and its
verdict reaches the ledger and stops there. No position item can name it.

## Scope

### In Scope

- `"step"` joins `WITNESS_KINDS` in `impl_position.py`, with `@step <stepName>` naming one
  of the target's own `__steps__` keys — the same shape `@rehearsal <jobName>` already has.
- `_derive_step(evidence, operand)` in `_DERIVERS`: a plain dict reader, two-state only.
  `returned` + current digest → `True`; `raised` → `False`; anything else, including a
  missing operand, a missing verdict, or a stale digest → `None` (**unmeasured, never
  `False`**).
- A suite digest covering **`src/` and `tests/`**, and `cmd_step` recording it on the
  ledger event so a verdict can expire.
- `_position_write_evidence` assembling the step verdicts (fold + digest comparison) and
  handing `derive()` a finished dict.
- One new refusal for "the position item names a step this target's `__steps__` does not
  carry", raised textually inside the `cmd_*` body, classified in `GATING_REFUSALS`.
- `SKILL.md` and `references/usage.md` kept true, including the derived roster counts.
- Red-first tests with mutation proofs, in both `tests/test_implementation_core.py` and
  `tests/test_proposal_implementation.py`.

### Out of Scope

- **Mechanism (B), the ordinary-agreements half.** Deferred to its own change. Motive
  below, measured, not "for completeness".
- Any change to `agreements_state`, `test_function_names`, `unparsable_tests`, or
  `settle`.
- Any change to `source_digest` itself, or to any target's `report_digest.py` stamper.
  Eighteen frozen copies live under `implementations/`; moving that algorithm marks every
  notebook in every product stale at once.
- Any change to `_skipped_rung_detail` or `POSITION_RUNG_SKIPPED`. `5243b8f`'s exemption of
  two-state items stands.
- A leveled `@step:level` witness. Two-state only; see "Why two-state".
- **Any edit under `implementations/`.** The target's declaration and its AGREED.md
  decision are the target's own change, its own commit, its own session.

## The deferral's motive, recorded verbatim

Of the declared agreement witnesses in the target's `AGREED.md`, exactly one can silently
skip: `test_and_the_gradient_comes_out_bit_identical`, whose first statement is
`torch = pytest.importorskip("torch")`. When torch is absent the test does not run,
`pytest` exits 0, the verification notebook's `assert code == 0` passes, position item 1
grades green, and the agreement stays ticked having measured nothing.

It is honest today because torch is installed. It is a latent hole that opens exactly when
the environment loses a dependency — a state this skill's own `env` step is known to
produce.

That hole is not closed by anything in this proposal, and saying so is the point of
scoping (B) out rather than gesturing at it.

## Why two-state, and why not the three alternatives

**Two-state.** A red/green verdict has no natural rung. Inventing one is precisely what
`_record_scale_level`'s own docstring refuses to do on a repository's behalf, and it is
what item 1 already says about itself: *"giving it a rung would be the position asserting a
state it does not have."*

Recorded so nobody reopens them:

1. **Leveled encoding** — dishonest by the codebase's own stated standard.
2. **Fold two-state items into the rung-skip check** — reverses `5243b8f`'s reasoned
   decision, *and is unnecessary*. `SEQUENCE_NOT_REACHED` already blocks while a two-state
   tick disagrees with fresh evidence, and `POSITION_DISAGREES` is checked before it. Item 1
   proves this live.
3. **A parallel precondition at the seal site** — duplicates a check the ladder already
   performs, creating two places that could disagree about "the suite is green".

Gating comes free. `cmd_gate` calls `impl_availability.launch_available` fresh on every
invocation regardless of any previously minted `offer` authorization, and
`GATE_AUTHORIZATION_STALE` separately invalidates a token when position status moves.

## Where this exploration and the brief were wrong

Six things were checked against source during this phase. Four held. Two did not, and one
of the two changes the design.

**1. `cmd_step` already has an ordering guard nobody mentioned.** A `__steps__` entry may
carry `advances: <ordinal>`, and `cmd_step` refuses `STEP_SEQUENCE_NOT_REACHED` when any
earlier sequence item is unticked. Its comment records the measured incident behind it. This
does **not** close the gap — a step's outcome still never reaches position derivation — but
the proposal must not reinvent it, and the target's suite-running entry should almost
certainly declare `advances: 1`.

**2. Derivers must not read the ledger. The exploration's `_derive_step` shape was wrong.**
`_derive_shard`'s docstring states the rule outright: currency is *"measured by the caller,
which is the only layer that knows both the stamp field a target declared and the digest of
the code as it stands."* `_derive_record`, `_derive_rehearsal` and `_derive_shard` are all
plain dict readers. Folding ledger events and comparing digests inside `_derive_step` would
put target-path and digest knowledge inside `_core`, against that stated layering.
**The fold and the digest comparison belong in `_position_write_evidence`;
`_derive_step` reads `evidence["stepVerdicts"][operand]` and nothing else** — the exact
shape of `_derive_rehearsal` against `smokeReady`.

**3. The scraper's own docstring is more precise than the brief.** `raised_refusal_codes`
explicitly says nested definitions **are** descended into, and names its stated limitation
as a `Refused` whose first argument is not a string literal. The top-level-helper blind spot
is real, but it is documented by `_skipped_rung_detail`, not by the scraper. The prescribed
shape is unchanged and correct: a helper that **returns** a detail or `None`, with the
`raise Refused(...)` textually inside the `cmd_*` body.

**4. A second count-bearing test exists.** Besides
`test_the_roster_states_the_counts_it_actually_holds`, there is
`test_the_derivation_finds_the_measured_sixty_five`, asserting `len(gating_codes()) == 65`
— **with the number spelled in the test's own name.** Adding one refusal requires renaming
that test, not only editing a literal.

**5. The skip count.** The brief said 85 witnesses, one skippable. Measured: **90** backticked
`` `test_*` `` tokens in `AGREED.md`, and **six** skip sites across `tests/` —
`test_creda_schedule.py` ×2 (`importorskip`), `test_distribute.py` (module-level, covering 15
tests), `test_shard_io_vendoring.py`, `test_label_noise.py` ×2. Of the six, **exactly one is a
declared witness**, so the brief's substance holds and its count does not.
`test_the_shared_implementation_matches_the_one_the_other_methods_use` is a skip site and not
a witness — it is the "1 skipped" in the target's reported 423/1.

**6. The new witness inherits the skip hole, and this must be said out loud.** `pytest`
exits 0 with skips. A `@step` witness reading `outcome == "returned"` grades green over a
suite that skipped tests, exactly as the notebook's `assert code == 0` does today. **This
design does not fix skip-laundering; it fixes assert-forgetting.** Whether the target's
callable also refuses on a non-zero skip count is the target's decision, made in the target's
own change. The forge must not encode it.

Not verified this phase: the branch/HEAD sha, and both suites — no shell was available.
`sdd-apply` and `sdd-verify` must run them rather than inherit these numbers.

## Capabilities

### New Capabilities

- `step-witness`: a position witness whose satisfaction is a declared callable's structural
  raise/return outcome, current against `src/` and `tests/`, unmeasured whenever it cannot
  be established.

### Modified Capabilities

- None. `openspec/specs/` does not exist in this repository; capabilities are declared per
  change.

## Approach

1. **`impl_position.py`** — `"step"` into `WITNESS_KINDS`; `_derive_step` into `_DERIVERS`
   as a dict reader over `evidence["stepVerdicts"]`. No `_LEVEL_DERIVERS` entry: a `@step:level`
   item must refuse rather than silently derive.
2. **`suite_digest(target)`** — new, beside `source_digest`, hashing `src/` **and** `tests/`,
   walking `tests/` the way `test_function_names`/`unparsable_tests` already do. It carries its
   own docstring stating why it is not `source_digest`, because the next reader's instinct will
   be to merge them and the merge reintroduces a fixed bug.
3. **`cmd_step`** — the ledger event grows the suite digest. Its docstring's "No digest field"
   paragraph is rewritten against its own stated doctrine, not around it: that reasoning was
   scoped to steps that self-stamp an artifact, and a bare runner has no artifact, so the
   ledger line is the only record and currency cannot otherwise be checked at all.
4. **`_position_write_evidence`** — folds `kind: "step"` events per step name in ledger order,
   latest wins, compares the recorded digest against a fresh `suite_digest`, and emits
   `evidence["stepVerdicts"] = {name: True | False | None}`.
5. **The unknown-operand refusal** — a `_step_witness_detail`-style helper returning a detail or
   `None`, with the `raise Refused(...)` inside the `cmd_*` body so the scraper sees it; the
   detail lists the target's real declared steps, mirroring `STEP_UNKNOWN`.
6. **Red-first throughout** (`strict_tdd: true`), with `PYTHONDONTWRITEBYTECODE=1` and
   `__pycache__` purged. A same-size mutation reuses a stale `.pyc` and the mutated source never
   runs; pick mutations a weaker lock would survive.

### The four exits, and what already exists

Verified in source — three of four need no new code:

| Situation | Exit | State |
|---|---|---|
| Target declares no `__steps__` at all | `STEPS_UNDECLARED`, published as a **question** | exists, reuse verbatim |
| Verdict stale (digest moved) | `POSITION_STALE`, published as a **command** | exists |
| Verdict red (`raised`) | `POSITION_DISAGREES`, published as a **command**, never a question | exists |
| Item names a step `__steps__` does not carry | **new** refusal, `INVOCATION_DEFECT`, detail lists the real ones | to build |

A discussion never lifts a block. It decides what to change so the block lifts itself. The rung
reopens because the suite went green, never because someone answered.

## Cross-repository split

**Forge (this change).** Everything above.

**Target (a separate change, separate commit, separate session).** Declare a suite-running
`__steps__` entry — a bare callable, no notebook — most likely with `advances: 1`; then decide
whether item 1's witness migrates from `@notebook` to `@step` or a new item is added. That is
the target's decision and the forge must not make it.

**What the forge does when the target has not declared the callable: it refuses.** Never a
silent pass. `STEPS_UNDECLARED` when there is no `__steps__`; the new refusal when a position
item names an operand `__steps__` does not carry; `unmeasured` — which never satisfies a tick —
when a declared step has simply never been run. There is no path on which absence reads as
green.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `.claude/skills/_core/implementation/impl_position.py` | Modified | `WITNESS_KINDS`, `_derive_step`, `_DERIVERS` |
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modified | `suite_digest` (new), `cmd_step` event + docstring, `_position_write_evidence`, `GATING_REFUSALS`, the new refusal |
| `.claude/skills/proposal-implementation/SKILL.md` | Modified | Witness-kind roster, new refusal, derived counts |
| `.claude/skills/proposal-implementation/references/usage.md` | Modified | Same |
| `tests/test_implementation_core.py` | Modified | `_derive_step` red-first + mutation proofs |
| `tests/test_proposal_implementation.py` | Modified | Digest scope, ledger shape, refusal, roster count + **test rename** |
| `implementations/**` | **Not touched** | Read as a fixture source only |
| `.claude/skills/_core/implementation/impl_steps.py` | **Not touched** | `run_step`'s five-state machine is already what this reads |

## Review Workload Forecast

| Component | Est. changed lines |
|---|---|
| `impl_position.py` — kind, deriver, docstrings | ~90 |
| `suite_digest` + its "why not `source_digest`" docstring | ~90 |
| `cmd_step` event + rewritten doctrine paragraph | ~60 |
| `_position_write_evidence` fold + currency | ~80 |
| New refusal + helper + `GATING_REFUSALS` + resolution | ~70 |
| `SKILL.md` + `usage.md` | ~80 |
| `tests/test_implementation_core.py` | ~180 |
| `tests/test_proposal_implementation.py` | ~330 |
| **Total** | **~980** |

**Decision needed before apply: No**
**Chained PRs recommended: No**
**400-line budget risk: High** *(against the session budget of **1400**: Low — ~70% consumed,
~420 lines of headroom)*

Roughly half is tests. This module's docstrings routinely run 30–60 lines per function, so the
count tracks prose density rather than reviewer burden. There is no split that leaves both halves
independently deliverable — a witness kind without its digest is a verdict that never expires,
which is worse than not having it. If apply overruns 1400 materially, stop and re-decide with the
owner rather than shipping a witness that cannot go stale.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `suite_digest` is merged into `source_digest` by a later reader | **High** | The exact bug that motivated `source_digest`'s exclusion. Both functions carry docstrings naming the other and why they differ; a test pins that adding a test file moves `suite_digest` and does **not** move `source_digest` |
| The new refusal is raised inside a top-level helper and vanishes from the roster | Medium | `_skipped_rung_detail`'s pattern: helper returns detail, `cmd_*` raises. Both roster tests must go red then green |
| `test_the_derivation_finds_the_measured_sixty_five` is edited without renaming | Medium | The number is in the name. Task list carries the rename as its own item |
| A missing verdict reads `False` instead of unmeasured | Medium | Mutation proof: flip `None` → `False` and a test must fail. This is the whole `derive()` doctrine |
| The green verdict launders skipped tests | **Accepted, out of scope** | Stated in the docstring, `SKILL.md`, and here. Not softened into an implied guarantee |
| Forge picks up target vocabulary | Low | `FORGE_VOCABULARY_FLOOR` and the derived lexicon rule must be **run**, never reasoned about. `"step"`, `"src"`, `"tests"` are existing forge words |
| A guard that cannot fire | Medium | For each refusal, ask what input reaches it given every check already running before it. `cmd_step` already refuses `STEP_UNKNOWN`, so the new refusal must be shown reachable **from the position side** |
| Baseline drift | Low | Suites must be **run**, not inherited: python and node in the forge, pytest in the target |

## Rollback Plan

Additive and self-contained. No existing witness kind changes derivation, no existing ledger
event loses a field, no `AGREED.md` bytes change in any repository, and `source_digest` is
untouched, so no notebook anywhere becomes stale.

Revert the commit. `WITNESS_KINDS` returns to four; any `kind: "step"` event carrying the new
digest field is an ordinary event the old reader already ignores. A target that had adopted
`@step` would then fail `POSITION_WITNESS_UNKNOWN_KIND` — which is loud, correct, and the
reason the target's adoption is a separate change that can be reverted on its own.

## Dependencies

- Branch `forge/a-rung-is-never-skipped` merged or still checked out; this builds on its
  two-state exemption rather than reversing it.
- `implementations/Domain_Adaptation/MIL-CREDA` readable as a fixture source.
- Gate: `npm test` **and** `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
  Baselines to re-measure, not inherit.

## Success Criteria

- [ ] **Red-first, recorded both ways**: a position item carrying `@step <name>` refuses
      `POSITION_WITNESS_UNKNOWN_KIND` before the change and derives after it.
- [ ] **Mutation proof, unmeasured**: turning a missing or stale verdict from `None` into `False`
      makes a test fail.
- [ ] **Mutation proof, digest scope**: pointing the suite witness at `source_digest` makes a test
      fail, driven by adding a test file and observing the verdict stay green when it must not.
- [ ] **Mutation proof, raised**: mapping `raised` to `None` instead of `False` makes a test fail.
- [ ] `_derive_step` reads only `evidence`; a test proves it touches no path and no ledger.
- [ ] The new refusal is found by `raised_refusal_codes`, classified in `GATING_REFUSALS`, and
      publishes something runnable; both roster tests pass with counts and the renamed test.
- [ ] A step never run derives `unmeasured` and a tick over it is reported as a disagreement.
- [ ] `FORGE_VOCABULARY_FLOOR` and the derived lexicon rule are **run** and report zero violations.
- [ ] Both forge suites run and their results recorded; nothing under `implementations/` modified,
      proven by `git status`.
- [ ] `SKILL.md` and `usage.md` state the skip-laundering non-goal in the same words used here.

## Proposal question round

Three product questions the owner may want to answer before `sdd-spec` and `sdd-design` run.
None blocks: each has a stated default that the proposal already assumes.

1. **Does a `@step:level` witness refuse, or is it simply undefined?** Default assumed:
   `_LEVEL_DERIVERS` gets no `"step"` entry and a `:level`-marked step item **refuses**, rather
   than deriving `None` forever. A silent `unmeasured` for a marker a target deliberately wrote
   is the "guard that cannot fire" shape.
2. **Should the suite digest cover anything beyond `src/` and `tests/`?** Default assumed: no —
   `conftest.py`, `pytest.ini`/`pyproject` markers and `requirements.txt` all change what the
   suite does, and none is under either root. Widening is safer and stales more often; the
   proposal takes the narrow reading deliberately, and this is the one place it may be wrong.
3. **Should the forge require the callable to run the whole of `tests/` unrestricted?** Default
   assumed: no. The forge would have to inspect the target's code to enforce it, and the
   composition it protects belongs to mechanism (B), which is deferred. Left as advisory.

A fourth is noted rather than asked, because the answer is already the owner's stated rule: the
skip-laundering hole (finding 6) stays open in the forge and is the target's to close in its own
callable.
