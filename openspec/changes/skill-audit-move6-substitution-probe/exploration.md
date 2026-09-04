# Exploration: skill-audit-move6-substitution-probe

> Materialized from Engram observation `#1434`
> (`sdd/skill-audit-move6-substitution-probe/explore`, project `papersmith-ai`,
> 2026-09-04) by the proposal phase. The exploration session was granted no
> `Write` tool, so the `hybrid` store's filesystem leg was never written. This
> file is that leg. Content is the observation's, transcribed rather than
> re-derived; the proposal phase's own re-measurements live in `proposal.md`,
> never edited into this record.

## What was explored

Whether `skill-audit` needs a substitution (edit-a-value) mutation probe to
catch the 24-defect class found in a 4-day `proposal-implementation` session —
"a guard that cannot fire and a guard that works look identical."

## Why the original framing did not hold

`sensitivity` (Move 10, `run_sensitivity` in `scripts/audit_cli.py`) varies only
**by absence** (`vary_by_absence` / `restore_exact_bytes`) to answer "was a
declared OUTPUT value computed, or typed in". It cannot prove a guard fires on a
bad value that is **present** — dead accumulators, regex misses and degenerate
`set()` assertions all live in presence, not absence.

## Where the real precedent is

| Finding | Detail |
| --- | --- |
| Move 6 is the precedent, not Move 10 | `SKILL.md`'s moves table ships Move 6 ("Invert every lock the audit leans on, and watch it fire") as `doctrine` — no code, no CLI subcommand |
| The mechanism is already designed | Move 6's detail section already describes sha256-before / write-mutation / run / inverse-patch / re-sha256, and a `(file, line, literal)` **guarded fact** |
| Its source grammar does not exist | The guarded fact comes from "the subject's own declared lock roster" or "the probe recipe's declared `mutations` block" — neither exists as recipe grammar or as code. Grepped: no `mutations` block in any `references/probes/*.json`, no `run_move6` / `invert` function in `audit_cli.py` |
| Pre-write digest proof exists nowhere | `restore_exact_bytes` proves restoration only, never that the mutation itself changed bytes. This is exactly the operator's own failure mode: the edit did not apply, and the anchor assertion still passed |
| The driver cannot purge bytecode | `DRIVER_ENV_ALLOWLIST` has no `PYTHONDONTWRITEBYTECODE`, and `child_env` is built only from recipe-declared names against that allowlist — reproducing the "same-size mutation reuses stale `.pyc`" defect inside any future mutation-drive mechanism |
| `check_citations.py` does not exist here | Cited in `SKILL.md` as the AST delete-vs-update precedent (`symbols_in` / `repo_symbols`). Absent from `papersmith-ai`. Must be reimplemented with stdlib `ast`, never reused or vendored |

## Defects reachable without new code

| Defect shape | Already-shipped surface |
| --- | --- |
| A constant restated by hand in several places | `roster`'s `restatement_of` / `duplicated` — finds hand-restated closed sets across files |
| A refusal placed after another check that sinks the same evidence | `walkthrough` (Move 8) — an ordering/reachability defect, reachable by a recipe naming the ladder steps in order, never by literal substitution |
| A duplicate test-class name | Move 7's `counts` subcommand, already deferred to the follow-up change `the-manifest-that-proves-containment`. Out of scope for any substitution probe |

## Recommended shape

A new subcommand implementing Move 6, which:

- reuses `restore_exact_bytes` **verbatim** for the restore side;
- adds a symmetric **pre-write digest proof**;
- forces bytecode purge in the driven child environment;
- scopes v1 to the **recipe-declared `mutations` block only**.

Deferred to keep the change inside the review budget: the "subject's own declared
lock roster" source (needs new table-site grammar) and the AST
delete/update/undecided classifier. Full Move 6 automation plus tests estimated
at 900–1400+ lines on its own — comparable to `sensitivity`'s ~370-line
implementation plus ~9 test classes.

## Not reachable by any substitution probe

| Out of reach | Why |
| --- | --- |
| A dead accumulator (one Store, one Load, zero `.add`) | A static AST fact. There is no live input to construct, because the code cannot repair itself to be tested |
| A degenerate `set()`-tie assertion | Needs multi-drive adversarial data generation, not single-literal substitution |
| A duplicate class name | Module attribute rebinding — Move 7's job |

## Stated limit of this exploration

The reachability analysis above is grounded against **7** of the session's 24
defects, the only ones named concretely at the time. A re-check against the
fuller set was owed to a later phase.
