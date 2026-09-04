# Proposal: Automate Move 6, and widen what already reaches

> **Stated exception to the 450-word proposal cap.** This proposal carries the
> soundness-conditions table and the out-of-reach list in full. Both are the
> deliverable's spine, and dropping a row to meet a word budget is the exact
> defect this skill exists to find. The exception is recorded here rather than
> taken silently.

Subject: `.claude/skills/skill-audit/`. Stdlib only, no venv, no network. The
skill reports and never repairs; every design below holds that.

## Problem statement

A guard that cannot fire and a guard that works look identical from the outside.
A 4-day `proposal-implementation` session produced 24 defects of that shape, and
`skill-audit` — the instrument built to find exactly this class — reaches almost
none of them mechanically today.

The framing that opened this work was wrong, and the correction reshapes it.
The ask was to extend `sensitivity` with a substitution variation. It is not
that. `SKILL.md`'s own moves table already ships the answer:

    | 6. Invert every lock the audit leans on, and watch it fire | `doctrine` | `tests/test_skill_audit.py` |

`doctrine` means prose with no code. Move 6's detail section already specifies
the whole mechanism — sha256 before, write the mutation, run, apply the inverse
patch, re-sha256, assert equality — over a `(file, line, literal)` **guarded
fact**. `check-report` already holds the report shape waiting for a Move-6
finding: the `## Not adjudicable` bucket, its three `- Delete:` / `- Update:` /
`- Undecided:` rosters, and the `- Remedy:` field scoped to exactly
`- Move: 6` + `- Adjudication: not adjudicable`.

**The mechanism was designed and never automated.** This proposal automates it,
and does not orbit `sensitivity`: Move 10's absence-based variation answers a
structurally different question (was a value computed, or typed in) and states
that ceiling deliberately.

## Three changes, ordered

| # | Change | Forecast (authored lines) | Budget risk vs 1400 |
| --- | --- | --- | --- |
| 0 | `a-driven-child-purges-its-own-bytecode` | 145–175 | Low |
| a | `the-lock-that-fires-when-the-value-changes` (Move 6 v1) | 945–1175 | Medium |
| b | `the-defects-already-within-reach` (recipe widening) | 215–275 | Low |

Order is a dependency, not a preference: (a)'s soundness condition 3 cannot hold
until (0) has landed. (b) depends on neither and may land in parallel.

---

# Change 0 — a driven child purges its own bytecode

## Intent

A live, pre-existing defect, verified in this phase. `DRIVER_ENV_ALLOWLIST` does
not carry `PYTHONDONTWRITEBYTECODE`, so `structure`'s `driver` step and every
`sensitivity` drive run today with the stale-`.pyc` trap armed: a same-size edit
executes cached bytecode, and a dead lock reads as live.

It is a defect **today**, independent of Move 6, and it is load-bearing for any
mutate-and-rerun feature.

## Where it lands, and why not inside (a)

**Its own change, first.** Four measured reasons:

1. It is a defect in shipped code now. Bundling it into a 900–1175-line feature
   makes it impossible to revert independently of a feature that has not shipped.
2. The exploration forecasts (a) at 900–1400 alone. Adding this crosses 1400.
3. It exists at **two sites** — `run_box_step` and `run_sensitivity_drive` each
   build `child_env` independently against the same allowlist. Sweeping the
   class rather than fixing the instance is its own reviewable unit, and this
   repository has already been burned by fixing one of a pair.
4. Its red proof is cheap and self-contained: assert the constructed child
   environment carries `PYTHONDONTWRITEBYTECODE=1` unconditionally, at both
   sites, regardless of the parent's environment and regardless of the recipe.

Counter-argument, recorded: a three-change chain costs coordination that a
~160-line fix folded into (a) would not. It loses to independent revertability
of a live defect plus the budget arithmetic.

## Scope

In scope: unconditional injection of `PYTHONDONTWRITEBYTECODE=1` into every
constructed child environment, at both sites, through one shared helper; the
`DRIVER_ENV_ALLOWLIST` doctrine paragraph updated to say the name is injected,
never inherited and never recipe-declarable; a `How the moves fail` row; a
red-first lock per site plus a mutation-reachability proof.

Out of scope: widening the allowlist for any other name; changing what a recipe
may declare beyond refusing this one name as redundant.

---

# Change a — the lock that fires when the value changes

## Intent

Automate Move 6 as a subcommand, so a guarded fact whose mutation leaves the
suite green becomes a mechanical finding instead of an operator's discipline.

## Scope

**In scope**

- A new subcommand driving one substitution per guarded fact, serial, each
  restored before the next, hard cap 8 per run, overflow to `## Unchecked`.
- `restore_exact_bytes` reused **verbatim** for the restore side.
- The write side, with the guarantee the original failure specifies:
  `sha256(before) != sha256(after-write)`, asserted **before the drive runs** —
  the exact symmetric counterpart of the per-file
  `sha256(before) == sha256(after-restore)` that already exists on restore.
  Nothing in the file proves a write changed anything today.
- Guarded facts sourced from **the recipe's own declared `mutations` block
  only**.
- `SKILL.md` moves-table row 6 and the subcommands table updated; the new probe
  recipe added with its shipped-files row in the same change.

**Out of scope, deferred with reasons**

| Deferred | Why |
| --- | --- |
| "The subject's own declared lock roster" as a fact source | Needs new table-site grammar. Same deferral pattern `SKILL.md` already used for Move 7's `counts` |
| The AST delete/update/undecided classifier | `check_citations.py` — cited in `SKILL.md` as the precedent — **does not exist in this repository** (verified). A later phase cannot reuse it, only imitate it, written fresh against stdlib `ast`, which `audit_cli.py` does not currently import. Second reason to keep it out of v1 |
| Variation by removing a whole production module | A real alternative, recorded rather than dropped — see "The fork not taken" below |

## The soundness conditions

Ten conditions. Each forbids one specific way a substitution result becomes
meaningless. All hold or the result is not read.

| # | Condition | What it forbids |
| --- | --- | --- |
| 1 | The literal is proven present before mutating | A mutation that "succeeds" against a fact that is not there, reporting a lock green when nothing was ever changed |
| 2 | The post-write digest differs from the pre-write digest | A write that did not land reading as a mutation. Asserted before the drive, never after |
| 3 | Bytecode is purged unconditionally, never by recipe declaration | A same-size mutation executing cached `.pyc`, so a dead lock reads as live. Depends on Change 0 |
| 4 | The guarded fact resolves to exactly one match | A multi-match substitution changing more than the fact under test, so the observed red belongs to something else |
| 5 | Restoration is confirmed by sha256, never `git checkout --` | A checkout silently discarding unrelated work; and a damaged tree continuing to be mutated instead of halting `Unprobeable` |
| 6 | The substitution inverts the **effect** the guard asserts, not the comparison around it | Flipping `==` to `!=`, which only changes which subset is excluded and yields a different wrong answer, never the absence of the fact |
| 7 | The observing run is the one the guarded fact declares | A hand-picked subset that happens to be green; and running one of a repository's two suites |
| 8 | A green mutation is reported `not adjudicable` with its remedy, never silently accepted | An obsolete guard passing as a working one |
| 9 | **A green mutation states which of three causes it could not distinguish** | Reporting "obsolete guard" when the cause was an *equivalent mutant* (bytes moved, behaviour identical) or a *degenerate fixture* (the fixture's own correct answer already equals the mutant's output). Condition 2 proves bytes moved; nothing proves behaviour moved. `- Remedy: undecided: <reason>` is the honest landing, and the report must say so rather than defaulting to `delete` |
| 10 | **A red mutation is not read as proof the fact is fully witnessed** | Treating "the suite went red" as "every consumer of this fact is asserted on". The probe reports lock *reachability*, never lock *coverage*, and must state that on its own payload |

Conditions 1–8 are carried from the exploration. **9 and 10 are added by this
phase**, both grounded in defects the fuller-set re-check surfaced: a mutation
that survived because the fixture's true hit count was already `0`, two
prescribed mutations that were no-ops as written, and a staleness guard whose
asserted consumer went red while two sibling consumers of the same signal stayed
broken and unreported.

## Not reachable, stated

A proposal claiming otherwise would be the exact over-claim this skill exists to
catch.

| Out of reach | Why |
| --- | --- |
| A dead accumulator (one Store, one Load, zero `.add`) | A **static** fact. There is no live input that makes it accumulate |
| A duplicate test-class name | A Python namespace rebinding, invisible to content substitution — and already Move 7's deferred `counts` job |
| A `for x in set(counts.values())` assertion that degenerates when two counts tie | Needs multiple differently-shaped data states, not a one-shot mutation |
| **A partially-witnessed fact** | Substitution proves *a* lock fires; it never enumerates the fact's other consumers. Reaching it needs consumer enumeration — Move 0's job, over every field the producer emits. Counterpart of condition 10 |
| **An omitted branch or a missing asymmetry** | Substitution mutates what is written. It cannot mutate what was never written: a guard that treats "unmeasured and blank" identically to "unmeasured and ticked" has no literal to substitute |
| An operator-side error | Not a subject artifact at all. Condition 7 mitigates only the "ran the wrong suite" instance, and only inside the probe's own run |

## The fork not taken

Removing a whole production module — keeping the tests and stashing the file —
closed five absence-asserting tests in the source session, and its own record
argues it beats mutation: it touches no source and cannot reuse a stale `.pyc`.

Deferred from v1 anyway, recorded rather than dropped. It answers "is this module
load-bearing" rather than "does this lock discriminate on a value", and stashing
a module makes every import of it fail, so the resulting red is uninformative
about *which* fact. Revisit once v1 has real findings to compare against.

---

# Change b — the defects already within reach

## Intent

Three of the concrete defects the source session found are reachable by
subcommands that already exist, as **recipe** gaps rather than code gaps.
Widening a surface is cheaper than building a new probe, and it says something
different about the skill: that its existing instruments were under-aimed, not
under-built.

## Scope

| Defect shape | Surface | Confidence |
| --- | --- | --- |
| A constant spelled three times | `roster`'s `restatement_of` / `duplicated` (`search.paths` + `search.quorum`) | **Conditional — see below** |
| A refusal sunk by an earlier check that consumed the same evidence | `walkthrough`, which drives a documented flow in order and names the first step whose expectation breaks | High |
| A declaration nothing ever demanded from a repository built from zero | `structure`'s "drive from ignorance" stage | High |

The fuller-set re-check adds a **fourth** defect to the `walkthrough` column:
two separately-documented decisions that are each correct and, in combination,
block every launch with a refusal message that is false. That is an ordering
defect across commands against one shared state — precisely what `walkthrough`
drives, and precisely what no substitution reaches.

Out of scope: any new code. If a recipe cannot be written against the shipped
grammar, the finding is that gap, reported — not a code change smuggled into a
recipe change.

---

## Capabilities

`openspec/specs/` does not exist in this repository; recent changes place their
spec flat at `openspec/changes/<name>/spec.md`. Follow that local convention.

### New Capabilities

- `substitution-probe`: the Move 6 subcommand, its recipe `mutations` grammar,
  its ten soundness conditions, its cap and overflow behaviour, and its exit-code
  contract (`0` for any verdict; `2` only for an inability to look).
- `driver-child-environment`: what a constructed child environment always
  carries, at every site that builds one, independent of parent and recipe.

### Modified Capabilities

- `report-shape`: `## Not adjudicable` and `- Remedy:` already specify the
  Move-6 finding. Change (a) must add the payload fields conditions 9 and 10
  demand — the undistinguished-cause statement and the reachability-not-coverage
  statement — and `check-report` must enforce them.
- `probe-recipe-coverage`: Change (b)'s capability, omitted from this section
  when the proposal was first written and added here so the spec is not the only
  artifact that carries it. What the shipped recipe grammar must be able to aim
  at: a constant restated across sites (`roster`), a refusal sunk by an earlier
  check and an ordering defect across commands against one shared state
  (`walkthrough`), and a declaration nothing demands from a repository built
  from zero (`structure`). Modified rather than new — all three subcommands
  ship today; what changes is what their recipes aim at, and where the grammar
  cannot express the aim, the reported finding is that gap.

## Approach

Reuse before build, at every point where the file already holds the discipline:
`restore_exact_bytes` verbatim; `run_box_step`'s child-environment construction
shared rather than re-implemented; `sensitivity`'s copy-and-freeze idiom for the
box; the existing `## Unchecked` overflow convention for the cap.

Build only the write side and its digest proof, because that is the one half the
file does not have and the one half the original failure was made of.

## Affected Areas

| Area | Impact | Description |
| --- | --- | --- |
| `.claude/skills/skill-audit/scripts/audit_cli.py` | Modified | Change 0: shared child-env helper, two call sites. Change a: the Move 6 subcommand |
| `.claude/skills/skill-audit/SKILL.md` | Modified | Moves table row 6, subcommands table, exit codes, Decision Gates, shipped-files rows, allowlist doctrine |
| `.claude/skills/skill-audit/references/probes/` | New | One Move 6 self-probe recipe (a); three widened recipes (b) |
| `.claude/skills/skill-audit/references/usage.md` | Modified | One worked invocation for the new subcommand |
| `.claude/skills/skill-audit/references/example-report.md` | Modified | A Move-6 `not adjudicable` finding with its `- Remedy:` |
| `tests/test_skill_audit.py` | Modified | Red-first locks across all three changes |

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Change (a) crosses 1400 authored lines | Medium | Slice at the mechanism/doctrine seam: mechanism + tests, then `SKILL.md` + recipe + report shape. Forecast re-measured by `sdd-tasks` before apply |
| A new probe file lands before its shipped-files row, repeating the skill's own recorded defect | Medium | The row and the file land in one commit; `structure`'s self-probe catches the gap if they do not |
| Adding a subcommand without its `SKILL.md` table row fires `unregistered` on the skill's own `roster` self-probe | High if forgotten | Same-change requirement, and the self-probe is the detector |
| A green mutation is read as an obsolete guard when it was an equivalent mutant | Medium | Condition 9 — the finding must name what it could not distinguish |
| Change 0's fix lands at one site and not the other | Medium | The two-site sweep is the change's stated scope, with a lock per site |

## Rollback Plan

Each change is one revertable commit range touching only
`.claude/skills/skill-audit/` and `tests/test_skill_audit.py`. No data, no
migration, no external state. Reverting (a) leaves (0) in place and correct on
its own terms; reverting (0) re-arms the stale-`.pyc` trap and must therefore be
reverted only together with (a) if (a) has landed.

## Dependencies

- (a) depends on (0) for soundness condition 3.
- (b) depends on neither.
- Move 7's `counts` remains deferred to `the-manifest-that-proves-containment`
  and is not a dependency of anything here.

## Success Criteria

- [ ] `PYTHONDONTWRITEBYTECODE=1` is present in every constructed child
      environment at both sites, proven by a red-first lock per site.
- [ ] A substitution whose write does not change the file's digest halts before
      the drive, proven by a lock.
- [ ] A guarded fact whose mutation leaves the suite green is reported
      `not adjudicable` with a `- Remedy:` and a statement of what it could not
      distinguish, and `check-report` rejects a report missing either.
- [ ] Each of the ten soundness conditions has at least one lock naming it.
- [ ] The skill's own `roster`, `structure` and `walkthrough` self-probes stay
      clean after each change.
- [ ] Both suites green after each change, run serially:
      `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests`
      and `npm test`.

## Measured corrections to the brief that opened this phase

Recorded because the opening premise was already wrong once, and assuming it was
the only time is how the next one survives.

1. **The bytecode defect fails harder than described.** The brief describes a
   silent drop — "a child cannot receive a bytecode-purge instruction even when
   the recipe declares one". Measured: unknown names are diffed against the
   allowlist and **raise `Unprobeable`**, so a recipe declaring
   `PYTHONDONTWRITEBYTECODE` refuses the whole step rather than dropping it.
   And even with the name allowlisted, the child environment is built with
   `if name in os.environ`, so the purge would still depend on the *parent's*
   environment. Both push the fix toward unconditional injection — the
   conclusion is unchanged, the mechanism is sharper, and the fix is a different
   edit than a one-line allowlist addition.
2. **The defect is at two sites, not one.** The brief names the allowlist.
   `run_box_step` and `run_sensitivity_drive` each build a child environment
   against it independently. The fix is a sweep.
3. **(b)'s `duplicated` item is conditional, not free.** `roster`'s code side is
   derived by driving the subject and reading its **refusal message**, and the
   recipe's `cwd` must resolve inside `--subject`. A constant living in a test
   helper has no refusal message and no driveable producer. The recipe is
   writable only if some driveable surface emits that closed set; otherwise the
   honest output is `no-closed-roster`, which is a first-class finding and not a
   failure. Not claimed as a certainty.
4. **A stale project memory, corrected.** The auto-memory note
   `configured-verify-command-runs-almost-nothing` says `openspec/config.yaml`
   pins tests to one file. Measured today: it runs
   `-p 'test_*.py'` under `.venv/bin/python`, the full discovery pattern. That
   memory is out of date.
5. **The 450-word proposal cap.** Taken as a stated exception, at the top of this
   file, rather than met by dropping the soundness table.

## Citations checked

`_shared/tools/check_citations.py` — the tool the shared protocol names for this
job — **does not exist in this repository**, so every citation below was resolved
by hand, by symbol name and never by line:

| Claim | Result |
| --- | --- |
| `SKILL.md` moves-table row 6 ships as `doctrine` | Confirmed, verbatim |
| Move 6's detail specifies sha256/inverse-patch/re-sha256 and `(file, line, literal)` | Confirmed |
| `check-report` holds `not-adjudicable` + `remedy` items | Confirmed, both present |
| `DRIVER_ENV_ALLOWLIST` lacks `PYTHONDONTWRITEBYTECODE` | Confirmed |
| `restore_exact_bytes`, `vary_by_absence`, `run_sensitivity`, `run_sensitivity_drive`, `run_box_step`, `BOX_STEP_KINDS`, `restatement_of` | All confirmed present |
| `audit_cli.py` does not import `ast` | Confirmed — imports are `argparse`, `hashlib`, `json`, `os`, `re`, `shutil`, `subprocess`, `sys`, `uuid`, `fnmatch.fnmatch`, `pathlib.Path` |
| `check_citations.py` exists anywhere in the repository | **Confirmed absent** |
| `tests/forge_vocabulary.py` splits the floor into three halves | Confirmed: `FORGE_SERVICE_VOCABULARY`, `FORGE_TARGET_DOMAIN_WORDS`, `FORGE_TARGET_PROPER_NOUNS` |
