# Design: Automate Move 6, and widen what already reaches

> **Stated exception to the 800-word design cap**, taken for the same reason
> the proposal and spec took theirs. This change ships a mechanism whose whole
> subject is doctrine that promises more than its code delivers. A design that
> dropped a decision to meet a word budget would leave `sdd-tasks` improvising
> the very seams this document exists to fix. Four decisions carry rejected
> alternatives; the ten soundness conditions map to concrete code; the breakage
> enumeration carries its Products half.

## Technical Approach

Three ordered commits, one branch, one change folder — the
`the-pilot-proves-the-science` precedent. Commit **0** sweeps a live defect at
two sites. Commit **a** ships the Move 6 subcommand as a new section *inside*
`scripts/audit_cli.py`. Commit **b** widens recipes only.

The mechanism is not new: `run_sensitivity` already performs
copy → control gate → baseline → one variation at a time → restore-by-digest →
tree-escape gate → `## Unchecked` overflow. Move 6 is that loop with the
substrate changed from *absence in a copy* to *a literal in the real tree*, and
with the one half `run_sensitivity` does not have — a proof that the **write**
landed — added. Everything else is reused, not re-derived.

## Architecture Decisions

### Decision: the probe lives in `audit_cli.py`, not a new module

| Option | Tradeoff | Decision |
| --- | --- | --- |
| New `scripts/inversion.py` | A ~3,626-line file stops growing; but **eight** existing self-locks read `CLI` as one file — `ast.parse(CLI.read_text())` at `tests/test_skill_audit.py` lines 440, 1303, 3773, 5245, 5674, 5706, 5733, plus `dict_literal_keys(CLI, "REPORT_SHAPE")` and `subcommand_surface(CLI, "build_parser")`. New code in a second file escapes every one of them **silently**, and a second `scripts/` row would have to be added to the shipped-files table before the module is even useful | Rejected |
| A new section in `audit_cli.py` | The file grows by ~300 lines; every AST self-lock keeps reach over the new code with no edit | **Chosen** |

**Rationale**: the repository's own locks define the module boundary. A split
that costs the skill its self-audit reach, in the change that automates
self-auditing, is the defect class under repair.

### Decision: the subcommand is named `inversion`

`FORGE_LEXICON` (`tests/test_skill_audit.py`) already owns the word, with the
argument written: *"inversion: breaking a guarded fact on purpose to watch its
lock fire, the only proof this skill accepts that a lock runs at all."* That is
this subcommand's definition, already on disk, already past the vocabulary
floor. `substitution` and `mutation` were rejected: each needs a new
`FORGE_LEXICON` entry arguing for a word the skill already has, and Move 6's
own verb in the moves table is *invert*.

### Decision: mutate the real tree in place, not a copy

| Option | Tradeoff | Decision |
| --- | --- | --- |
| `materialize_subject_copy` + mutate the copy (`sensitivity`'s idiom) | Restore cannot partially fail. But a guarded fact's **declaring test lives outside `--subject`** (`tests/test_skill_audit.py` at the repository root), so a copy of the subject alone cannot host its own observing run; copying the whole repository is out of proportion and drags `implementations/` | Rejected |
| In-place write, restore from recorded bytes in a `finally` | The doctrine Move 6 already specifies (`sha256` → write → run → **inverse patch** → re-`sha256`), and the only reading under which condition 5's *"never `git checkout --`"* means anything — that rule only bites on a tracked file | **Chosen** |

`restore_exact_bytes` is reused **verbatim**, unedited: its signature
`(copy_root, original)` takes any root and a `{relative: bytes}` map, so passing
the repository root works with no change. **Stated cost**: its refusal message
reads `kind=sensitivity-restore-failed`, and an inversion restore failure will
therefore report under that kind. Renaming it would edit the function the
proposal requires verbatim and would break the one assertion at
`tests/test_skill_audit.py:6635`. One mechanism keeps one spelling; the doctrine
says so rather than shipping a second name for one function.

### Decision: condition 10 lands as a per-finding field, not a `## ` section

A new `## ` heading enters `run_check_report`'s **unconditional** sweep
(`for item, marker in REPORT_SHAPE.items()`), which would invalidate every
report ever written. A `- ` marker is enforced by explicit per-finding code and
touches nothing else. Chosen shape: `- Reachability: fires|silent: <what this
does not prove>` — the exact `undecided: <reason>` idiom already in the file —
required **iff** a finding carries `- Move: 6`, refused everywhere else,
bidirectional, mirroring the `remedy` scope check. Scope is `- Move: 6` alone,
not `Move 6 + not adjudicable`: a lock that *fires* is a clean result, not a
finding under `## Not adjudicable`, and condition 10 binds both outcomes.

## The `mutations` recipe grammar

`SKILL.md`'s Move 6 detail already names this block, so the grammar is
implementing existing doctrine, not inventing it.

```json
{
  "surface": "self-guarded-facts",
  "exclude": ["__pycache__/*", "*.pyc", ".DS_Store"],
  "mutations": [
    {
      "fact": "the schema version the validator holds",
      "file": "scripts/audit_cli.py",
      "line": 2703,
      "_line_note": "illustrative; the shipped recipe's line is re-derived at write time, since this change edits this file",
      "literal": "REPORT_SCHEMA_VERSION = 1",
      "replacement": "REPORT_SCHEMA_VERSION = 97",
      "observe": {
        "argv": [".venv/bin/python", "-m", "unittest",
                 "tests.test_skill_audit.ReportSchemaVersionTests"],
        "cwd": ".", "env": ["PATH", "HOME"]
      }
    }
  ]
}
```

- `file` resolves under `--subject` with `resolve_site`'s discipline: no
  absolute path, no `..`. `line` is 1-based.
- **Condition 4** is `line_text.count(literal)`: `0` → `Unprobeable`
  `kind=fact-absent`; `>= 2` → `Unprobeable` `kind=fact-ambiguous`, and neither
  occurrence is substituted. Scoped to the declared line, not the file — a
  literal repeated elsewhere in the file is correctly untouched.
- **Condition 6** is mechanical, not advisory. Delete every member of
  `COMPARISON_OPERATORS` (`==`, `!=`, `<=`, `>=`, `<`, `>`, ` is not `, ` is `,
  ` not in `, ` in `) from both `literal` and `replacement`; if the two
  remainders are equal, refuse `kind=operator-flip`. A substitution that only
  moves the comparison never runs.
- `observe` is **per fact and mandatory** (condition 7). A fact with no
  `observe` block is `Unprobeable`. There is no recipe-level default observing
  run and no derived suite roster — inventing one would be the second
  hand-written roster this skill refuses everywhere else.

## Data Flow

    recipe.mutations ──sorted(file,line,literal)──▶ first 8 ──▶ rest ──▶ ## Unchecked
            │
            ▼
    baseline gate: each distinct observe.argv run once, unmutated
            │  not green ──▶ Unprobeable  kind=baseline-not-green
            ▼
    per fact, serial:
      read bytes ──▶ sha256(before)
      presence + single-match + operator-flip checks       (conds 1, 4, 6)
      write replacement ──▶ sha256(after) != sha256(before) (cond 2)
            │  equal ──▶ Unprobeable, the observing run never executes
            ▼
      observe.argv via the shared child-env helper           (conds 3, 7)
            │
      restore_exact_bytes(root, {relative: before})          (cond 5)
            │  digest mismatch ──▶ Unprobeable, sweep halts, next fact untouched
            ▼
      red ──▶ "fires"      green ──▶ "silent" ──▶ ## Not adjudicable (conds 8, 9)
            │
            ▼
    tree_digest(subject) before == after ──▶ else kind=build-escaped-the-box
    finally: restore every recorded fact, always

The **baseline gate is an addition this design makes** — see *Measured gaps*
below.

## Change 0: the shared child-environment helper

Both sites today independently run the same three lines
(`sorted(set(names) - set(DRIVER_ENV_ALLOWLIST))` → raise → dict-comprehension
`if name in os.environ`). One helper replaces both:

```python
def constructed_child_env(names, label):
    """The only place a child environment is built. `PYTHONDONTWRITEBYTECODE`
    is injected unconditionally -- never inherited, never recipe-declarable --
    so a same-size mutation can never execute a cached `.pyc`."""
    unknown = sorted(set(names) - set(DRIVER_ENV_ALLOWLIST))
    if unknown:
        raise Unprobeable(f"{label} names env {unknown}, outside ...")
    env = {name: os.environ[name] for name in names if name in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env, sorted(name for name in names if name not in os.environ)
```

`label` preserves each site's distinct refusal wording. `PYTHONDONTWRITEBYTECODE`
stays **out** of `DRIVER_ENV_ALLOWLIST`, so a recipe naming it is still refused
`Unprobeable` — deliberate, and the doctrine paragraph says so.

**Stated hole, not silently closed**: `exec`-kind box steps pass `env=None` and
inherit the whole parent environment; they construct nothing, so the helper does
not reach them. Widening `exec` would change it from *inherit* to *constructed*
— a third site outside this change's declared scope. `inversion`'s observing run
therefore always goes through the helper, never through an `exec` step.

## What Breaks — Producers AND Products

### Producers

| Site | Effect |
| --- | --- |
| `run_box_step`, `run_sensitivity_drive` | Child-env construction replaced by the helper (commit 0) |
| `build_parser`, `DISPATCH` | New `inversion` subcommand (a1) |
| `run_check_report` | Condition-9 cause check inside the existing `undecided:` branch; new condition-10 `- Reachability:` scope check (a2) |
| `REPORT_SHAPE` + `SKILL.md` shape table | One new key/row pair. `ReportSchemaSelfDescriptionTests` locks both directions — they land in one commit |
| `SKILL.md` | Moves row 6, Move 6 detail, subcommands table, exit codes, shipped files, Decision Gates, `How the moves fail`, allowlist doctrine |
| `references/usage.md` | One worked invocation; `UsageReferenceTests` executes what is documented |
| `references/probes/skill-audit.structure.json` | Its declared side is the shipped-files table; the new recipe needs its row or `unregistered` fires |
| `tests/test_skill_audit.py` | Red-first locks, all three commits |

### Products — records already written under the old shape

| Product | Verdict |
| --- | --- |
| `references/example-report.md` | Carries `- Move: 6: skipped`, **no Move-6 finding** (measured). Conditions 9 and 10 are both conditional on a Move-6 finding, so the widening alone leaves it valid. Commit a2 adds a Move-6 finding to it deliberately, which forces `- Self-digest:` to be recomputed **in that same commit** |
| `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md` | The one issued report on disk. Also `- Move: 6: skipped`, no Move-6 finding → untouched by this change. **Measured, pre-existing**: it already fails `check-report` on `remedy` today, because its `F4` carries `- Remedy:` on a `- Move: 0` finding, which the out-of-scope branch refuses. `SKILL.md`'s own "The shape of a report" already states this class and its remedy (re-run the audit, never hand-edit). Not introduced, not worsened, and not repaired here |
| Any other report | **None exist.** Asserted, not assumed: `tests/test_skill_audit.py` proves exactly one file under `openspec/changes/**/*.md` carries both `## Frozen` and `## Ranked findings` |
| `references/probes/*.json` | No shipped recipe declares `mutations`. The block is purely additive; no existing recipe changes shape |
| `## Move outcomes` rows in every issued report | `move_roster` derives ids from the moves table; row 6's **id** does not change, only its `Ships as` cell. Every existing `- Move: 6: skipped: <reason>` row stays valid |

## Commit boundaries and budget

Authored `additions + deletions`, excluding generated output. Budget **1400**.

| Commit | Contents | Forecast |
| --- | --- | --- |
| **0** `a-driven-child-purges-its-own-bytecode` | `constructed_child_env`, two call sites, allowlist doctrine paragraph, one `How the moves fail` row, a lock per site, an AST class-sweep lock (no `os.environ[...]` child-env comprehension outside the helper), one mutation-reachability proof | **150–195** |
| **a1** the mechanism | `run_inversion` + fact resolution/write/observe/restore helpers, `build_parser` + `DISPATCH`, the self-probe recipe, and — same commit, non-negotiable — the subcommands-table row, exit-codes paragraph, shipped-files row, `usage.md` invocation, moves row 6, Decision Gates rows, the Move 6 detail rewritten to v1's actual scope. ~20 locks | **760–950** |
| **a2** the report side | Conditions 9 and 10 in `check-report`, `UNDISTINGUISHED_CAUSES`, the `reachability` `REPORT_SHAPE` key with its `SKILL.md` row, the doctrine-agreement lock, `example-report.md`'s Move-6 finding + rosters + self-digest, ~6 locks | **165–245** |
| **b** `the-defects-already-within-reach` | Three widened `references/probes/*.json` recipes, their shipped-files rows, no code | **215–275** |

`Decision needed before apply: No`. Every commit is under 1400 on its own; the
whole of (a) at its upper band is 1,195, still inside. **The a1/a2 seam is named
now anyway**, so `sdd-tasks` inherits it rather than improvising if the forecast
grows: the seam is *the mechanism and everything a self-probe would redden
without* (a1) versus *the report-shape widening* (a2). Row 6's `Ships as` cell
moves in a1 so no commit ever ships doctrine disagreeing with code; the
`test_every_row_ships_as_a_real_subcommand_or_as_doctrine` lock permits either,
so this is a correctness choice, not a lock-forced one.

## Interfaces

New constants in `audit_cli.py`: `INVERSION_FACT_CAP = 8`,
`INVERSION_VARIATION_RANGE`, `COMPARISON_OPERATORS`, `UNDISTINGUISHED_CAUSES =
("obsolete guard", "equivalent mutant", "degenerate fixture", "none
determined")`, `REACHABILITY_VALUES = ("fires", "silent")`.

`inversion` emits: `baseline`, `facts`, `factsDriven`, `factsUnchecked`,
`factsTotal`, `matrix`, `notAdjudicable`, `observed`, `frozen`, `notes`,
`range`. Exit `0` for any verdict including every fact `silent`; exit `2` only
for an inability to look: no `mutations` block, `fact-absent`,
`fact-ambiguous`, `operator-flip`, a no-op write, `baseline-not-green`, a
restore digest mismatch, `build-escaped-the-box`, or a timeout.

**No new stdlib import.** `ast` is *not* added: v1 defers the delete/update
classifier, so nothing needs it. The import line stays `argparse, hashlib, json,
os, re, shutil, subprocess, sys, uuid, fnmatch.fnmatch, pathlib.Path`.

## Testing Strategy

`strict_tdd: true`. Every lock is RED first, and — because this change's whole
subject is the stale-`.pyc` trap — every RED/GREEN cycle runs with
`PYTHONDONTWRITEBYTECODE=1` and `__pycache__` purged, or the proof is void. Both
suites, serially, never concurrently:
`npm test && .venv/bin/python -m unittest discover -s tests -p 'test_*.py'`.
Every scratch path carries `RUN_SUFFIX` (`tests/test_skill_audit.py` already
defines `f"_{os.getpid()}"`); a fixed-name scratch path has produced 142
concurrent failures here.

| Layer | What | Approach |
| --- | --- | --- |
| Unit | Each of conditions 1–10, plus the baseline gate | One lock per condition, each failing if its condition alone were dropped |
| Unit | Both child-env sites | One lock per site + one AST lock proving no second construction site exists |
| Integration | Cap and overflow | A 10-fact recipe yields 8 driven, 2 named individually under `## Unchecked` |
| Integration | `check-report` conditions 9/10 | A reason naming none of the four causes fails; a Move-6 finding with no `- Reachability:` fails; a non-Move-6 finding carrying one fails |
| Self-probe | `roster` / `structure` | The new subcommand and the new recipe file each have their row; `unregistered` and `phantom` stay empty |
| Doctrine | `UNDISTINGUISHED_CAUSES` | Each member appears verbatim in `SKILL.md`'s `remedy` row — the `stage_model_total` / `REPORT_SCHEMA_VERSION` idiom, never a second hand-written roster |

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
| --- | --- | --- | --- |
| Documentation-like paths | **N/A** — `inversion` substitutes a declared `(file, line, literal)` and never classifies a path as executable; `argv[0]` comes from the recipe's `observe` block, never from a mutated file | — | — |
| Git repository selection | **Applicable** — `file` resolves under `--subject`, `observe.cwd` under `--repo-root`, both through `resolve_under`/`resolve_site` | Absolute paths and `..` are refused; the observing run never chooses its own root | A recipe naming an absolute `file`, and one with `..`, each exit `2` |
| Commit state | **Applicable** — this is the only subcommand that writes into the tracked tree | Restore from recorded bytes in a `finally`, confirmed by sha256; then a `tree_digest` before/after gate over the whole subject. A mismatch is `Unprobeable`, never a finding, and the sweep stops rather than mutating the next fact | A restore whose bytes differ exits `2` and the next fact is never mutated; a drive writing elsewhere in the subject exits `2` as `build-escaped-the-box` |
| Push state | **N/A** — no VCS automation; the skill reports and never repairs | — | — |
| PR commands | **N/A** — no PR automation | — | — |
| Subprocess composition | **Applicable** (added row) | `argv` a list of strings, `shell=False`, per-step timeout, constructed child env from the shared helper, `assert_no_subject_reference` over every part — `run_sensitivity_drive`'s existing discipline | A hanging observing run exits `2`; a recipe naming an env outside the allowlist exits `2` |

## Measured gaps in the inputs

1. **The ten conditions have no baseline gate, and need one.** Condition 2
   proves the bytes changed; conditions 8/10 read the observing run's colour.
   Nothing requires the observing run to have been **green before the
   mutation**. Against an already-red suite, every fact would report `fires` and
   the probe would announce ten working locks having proven nothing — the
   `green-because-nothing-happened` defect inverted. This design adds a baseline
   gate, modelled on `sensitivity`'s own baseline drive and control gate: each
   distinct `observe.argv` runs once unmutated, and a non-green baseline is
   `Unprobeable` `kind=baseline-not-green`. Carry it into `tasks.md` as a
   first-class condition, not a nicety.
2. **The doctrine overclaim is larger than the spec says.** The spec's
   `SKILL.md` requirement names only the AST delete/update classifier. Measured:
   `SKILL.md`'s Move 6 detail also opens *"A guarded fact whose mutation leaves
   the suite green **is an obsolete guard**"* — a flat assertion that condition
   9 exists to refute, since the cause may equally be an equivalent mutant or a
   degenerate fixture. Both sentences are corrected, or the change ships
   doctrine contradicting its own new soundness condition.
3. **The spec's condition-8 wording and its `SKILL.md` requirement disagree.**
   Condition 8 says a Move-6 finding carries *"a `- Remedy:` from the existing
   delete/update/undecided vocabulary"*; the `SKILL.md` requirement says every
   v1 finding carries `undecided: <reason>`, never `delete` or `update`.
   Resolved without changing either: the **validator** keeps accepting all three
   (human-authored reports may use them), while **v1's emitter** produces only
   `undecided: <reason>`. Both statements are true of different actors, and the
   design states which is which.
4. **`SKILL.md` already names the `mutations` block.** The Move 6 detail says
   guarded facts come from the declared lock roster *"where one exists,
   otherwise from the probe recipe's declared `mutations` block."* v1 implements
   the second half only, so the doctrine sentence needs narrowing rather than
   inventing — the spec reads as though the grammar were new.

## Migration / Rollout

No migration. No data, no external state, no feature flag. Each commit reverts
independently, with one ordering rule carried from the proposal: reverting
commit 0 re-arms the stale-`.pyc` trap, so it may only be reverted together with
(a) once (a) has landed.

## Open Questions

- [ ] None blocking. The `exec`-kind inheritance hole and the shared
      `kind=sensitivity-restore-failed` message are both **decided** above as
      stated costs, not open items.
