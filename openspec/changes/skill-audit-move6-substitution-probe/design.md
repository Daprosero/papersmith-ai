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
| `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md` | The one issued report on disk. Also `- Move: 6: skipped`, no Move-6 finding → untouched by this change. **Corrected by the re-run design phase; the claim previously in this cell was wrong.** It does *not* fail `check-report` on `remedy`, because it is never judged at all: the file carries no `## Report integrity`, no `- Schema:` and no `- Self-digest:` (measured by search over the file), so `report_identity_gate` (`audit_cli.py:2905-2916`) returns `predates-the-schema`, exit `2`, with a payload carrying **no `violations` key**. It can never become judgeable either: `HistoricalReportRecordTests.PRE_FALSIFICATION_SHA256` (`tests/test_skill_audit.py:3328`) pins it byte-identical and its docstring forbids retro-fitting `## Report integrity`. Consequence, load-bearing below: **`references/example-report.md` is the only report on disk that retroactive invalidation can reach** |
| Any other report | **None exist.** Asserted, not assumed: `tests/test_skill_audit.py` proves exactly one file under `openspec/changes/**/*.md` carries both `## Frozen` and `## Ranked findings` |
| `references/probes/*.json` | No shipped recipe declares `mutations`. The block is purely additive; no existing recipe changes shape |
| `## Move outcomes` rows in every issued report | `move_roster` derives ids from the moves table; row 6's **id** does not change, only its `Ships as` cell. Every existing `- Move: 6: skipped: <reason>` row stays valid |

## Commit boundaries and budget

> **Superseded in part.** The table below is still the plan for the four commits
> this change ships. The seven `audit-scope-hardening` requirements do not fit
> beside them; the whole re-forecast, across three changes, is in *The re-run
> design phase* at the end of this document.

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

---

# The re-run design phase: `audit-scope-hardening`

Everything above is unchanged except the two corrections marked in place. This
half designs the seven requirements `spec.md`'s fifth capability added, and
re-forecasts the whole body of work.

## The three doors that retroactively invalidate a report

Measured first, because four decisions below turn on it. The earlier design
found one door and treated it as the only one. There are three, and they are
not equally expensive:

| Door | Mechanism | Reach |
| --- | --- | --- |
| A new unconditional `## ` heading in `REPORT_SHAPE` | `run_check_report`'s sweep at `audit_cli.py:3164` demands every `## ` marker | Every schema-carrying report |
| A new row in the **moves** table | `move_roster` (`audit_cli.py:2170`) derives the required `## Move outcomes` roster from it; `move-outcomes` is unconditional | Every schema-carrying report |
| A new row in the **stages** table | `stage_roster` (`audit_cli.py:2343`) does the same for `## Stage outcomes` | Every schema-carrying report |

And one door that does **not** invalidate anything, which the earlier design
missed: the sweep at `audit_cli.py:3162-3166` skips any item a stages-table
`Demands` cell names. A `## ` heading demanded by a stage is conditional, not
unconditional.

The price of all three doors is now known and small: exactly one report on disk
carries `## Report integrity`, and it is `references/example-report.md`, which we
own and re-sign. The historical report is unjudgeable and pinned (see the
corrected Products row above). **Retroactive invalidation is therefore a cost of
one file, not an argument that decides anything by itself.** The `## Not
adjudicable` reasoning above stands on its own merits; it no longer needs this
one.

## Which of the seven are recipe, and which are code

| # | Requirement | Verdict | Why |
| --- | --- | --- | --- |
| R1 | an enumerator's reach is measured, not only its result | **Code, new subcommand, `ast`** | No shipped grammar classifies a check's *iteration source*. `roster`'s only code-side derivation is `probe_code_side`, which drives a process and parses no source — deliberately (`audit_cli.py:307-318`). A regex over the check's text would itself be a bounded enumeration claiming to derive, i.e. the exact defect in this requirement's own third bullet |
| R2 | a guard is reachable for every member of the set it guards | **Code in `roster` + recipe block** | Both halves stay derived: members from the subject's own refusal, variants from a pure function, reach from driving the guard. No source is read, so `roster` keeps its language independence |
| R3 | renaming is not generalising | **Code in `roster`, reusing R2's loop + recipe** | Same drive, one different transformation. Deliberately reports two facts and adjudicates nothing |
| R4 | the from-zero drive demands what the subject reads | **Recipe/doctrine only — report shape** | The stronger, derived form is out of reach and the design says so rather than smuggling it. See below |
| R5 | an artefact is judged by what it shows | **Code in `structure` + recipe** | Zero-length is already latent in `tree_digest`'s output; "units produced no output" is format knowledge, so the recipe declares the pattern and the forge learns nothing about any format |
| R6 | a driven step is graded on what it wrote | **Code in `walkthrough` + recipe** | `walkthrough` takes no digest at any point today. No recipe can add one |
| R7 | a reported state names its exit | **Code, new subcommand + new move** | See *The one genuinely new surface* |

One of seven is recipe-only. Five of the remaining six **widen a shipped
subcommand** rather than add one, which keeps the proposal's own argument intact:
the instruments were under-aimed more often than they were under-built. Only R1
and R7 add a subcommand, and each adds it because the question it asks has no
existing surface, not because a recipe was inconvenient.

### R4: the honest gap, stated instead of built

Stage 2 is `## User drive` (`audit_cli.py:2256-2340`), an operator-driven stage
whose only machine surface is `check-report`'s `user-drive` item. The requirement
wants the audit to *record every declaration the subject reads from its target*
during the drive. The audit cannot: `structure`'s from-zero driver is an external
process (`claude -p`), the tool holds `subprocess.run()` and nothing else, and
`SKILL.md:307-315` already states that ceiling in its own words — *"this tool
only ever calls `subprocess.run()` and holds no authority over what happens on
either side of that call."*

So R4 ships as the structural half only: a `### Demanded, not scaffolded`
subsection under `## User drive`, required non-empty and permitted to read
`(none)` explicitly, enforced by exactly the code that already enforces
`### Declared, not proven` (`user_drive_declared_only_nonempty`,
`audit_cli.py:2317`). Per item it names the declaration, where it belongs, and
the consequence of its absence — the requirement's own three fields.

- It is a `###` inside a **conditional** item, so it adds no `REPORT_SHAPE` key,
  opens none of the three doors, and invalidates nothing.
- It is an operator's declaration, never a proof. The doctrine says so in the
  same sentence it already says it for stages 3–5.
- The derived form — scaffold into an empty box, drive the subject against that
  box, and collect what it refuses for — is recorded as the deferred stronger
  version with its own name, not dropped. It is a whole drive shape (~200–280
  code) and it belongs after R6 has taught `walkthrough` to digest.

This is the proposal's own precedent applied unchanged: where the shipped
grammar cannot express the aim, the gap is the reported finding, never a code
change smuggled into a recipe.

## Decision: R6 digests the **box**, not the subject — the spec is wrong here

`run_walkthrough` runs every step with `cwd = box` (`audit_cli.py:1904`), and the
box is `{repoRoot}/implementations/_walkthrough_{surface}` (`audit_cli.py:1846`).
A correct step writes into the box. It never writes into the subject.

`spec.md:392` and `spec.md:600` both require the digest to cover *the subject
tree*. Implemented literally, the subject digest is unchanged across **every**
correct step, so every step in every recipe would be reported as having produced
nothing, and the requirement would fire on the whole flow rather than on the
defect. Measured, not inferred: no line of `run_walkthrough` writes to the
subject, and `step_cwd` defaults to `box` with `resolve_under(step["cwd"], box, …)`
refusing anything outside it.

The design therefore reads the requirement's aim rather than its noun:

| Observation | Verdict |
| --- | --- |
| box digest unchanged across a step, step not declared `readOnly` | finding: the step returned without producing |
| box digest changed, entirely inside the step's declared `roots` | clean, and the roster is reported with counts either way |
| box digest changed, partly or wholly outside the declared `roots` | finding: the step wrote into a tree it does not own |
| box digest unchanged, step declared `readOnly` | expected, no finding |
| **subject** digest changed across any step | `Unprobeable`, `kind=step-escaped-the-box`, sweep halts |

The last row is a second, real gap closed for free: `structure` has a subject
before/after escape gate (`audit_cli.py:1258-1266`) and `walkthrough` has none at
all. A `walkthrough` step writing into the subject today is silent.

Both digests go through `tree_digest`, the module's only permitted walker, so
`SingleWalkTests` stays green with no edit. Per-step cost is one walk of a
throwaway box.

## Decision: R2 and R3 stay inside `roster`, and drive rather than parse

R2's two halves are both derived, which is the only reason it may live beside
`probe_code_side`:

    guarded members   ──▶ probe_code_side(recipe.guardReach.producer)   [driven]
            │
            ▼
    identifier_variants(member)  ──▶ plural, underscore-joined, case-joined,
            │                        derived by one pure function, never listed
            ▼
    for each variant: drive the guard  ──▶ reached | not-reached
            │
            ▼
    control first: the bare member MUST be reached, or kind=guard-never-fires

The control gate is not optional and is not new: it is `candidate_gate_steps`'
own inverted control (`audit_cli.py:1769-1805`) argued for a second time in a
second place. A guard that never fires at all would otherwise report every
variant unreachable and look like eleven findings instead of one broken probe.

Rejected alternative — **the recipe declares the matcher pattern and the audit
compiles it with `re`**. Cheaper by roughly 80 lines, and wrong: the pattern
would be a hand-copy of the subject's own source living beside it, free to drift,
which is the precise class this skill exists to find. Rejected.

Rejected alternative — **put it in `walkthrough`'s `candidateGates`**. That block
already drives candidates against a declared refusal, and adding a polarity flag
would be ~30 lines. Rejected on two counts: its candidates are a hand-written
list where the requirement demands derived variants, and a guarded vocabulary is
a closed set, which makes it Move 0's subject and `roster`'s home. Attributing a
`- Move: 0` finding to a `walkthrough` payload would put the moves table and the
subcommands table into disagreement for no gain.

Where the subject exposes no driveable guard, the result is
`kind=no-driveable-guard`, a first-class finding with the range that was
searched — the `no-closed-roster` idiom (`SKILL.md:332-334`) reused verbatim,
never an empty roster and never a clean verdict.

## Decision: R3 stops at two facts, and a carried constant keeps it there

R3's whole value is its boundary, so the boundary is mechanised rather than
promised.

The probe: take an input the guard refuses; substitute the guarded member with a
neutral token, leaving every other byte alone; drive the guard again. If it now
passes, the guard's verdict moved when the identifier moved and the content did
not. That licenses exactly one sentence — *identity was measured, content was
not* — and it is the sentence the requirement asks for.

Three mechanisms hold it there:

1. The verdict vocabulary is a **two-value closed roster**,
   `IDENTITY_MEASURED = ("identity-measured", "not-determined")`. There is no
   third value, so no code path can emit one meaning "the content is specific".
2. A lock asserts the roster's cardinality and its two members, the
   `REMEDY_VALUES` / `FOUND_BY_VALUES` idiom already in the file.
3. Every payload carries a permanent stated limit regardless of verdict — the
   `READING_DIFF_LIMIT` precedent (`audit_cli.py:2022-2025`), which exists for
   exactly this failure mode: a caller copying a result without its ceiling and
   upgrading it into a stronger claim. The constant says that a rename-insensitive
   guard proves the matcher tests identity, and proves nothing whatever about
   whether the content behind it is still specific.

The 853-occurrence rename in the source session is the argument for that
constant, not merely for the check.

## Decision: R5 finds emptiness in a digest already computed

`structure` already builds `tree_digest(from_zero_root, exclude)`
(`audit_cli.py:1272`). A zero-length file's sha256 is a constant, so
produced-but-empty needs no second walk, no new API, and no `os.stat`:

```python
EMPTY_FILE_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
```

Per artefact the payload reports `produced` / `produced-but-empty` / `absent` —
three values, never a boolean, because "nobody produced it" and "it was produced
carrying nothing" are different defects with different remedies. That is the
same argument `structure`'s own three-way outcome already makes.

The second half — *an executed artefact whose units produced no output* — is
format knowledge. Twenty-two code cells in three notebooks is one format's
spelling of it, and the forge must not learn that spelling. So the recipe
declares, per artefact kind, a `contentPattern`; the audit reports
`carries-no-match` against the recipe's own declaration and knows nothing about
any format. A kind with no declared `contentPattern` is reported as
`content-not-declared`, never assumed full.

## The one genuinely new surface: R7 becomes move 11 and the `exits` subcommand

The eleven moves each ask whether the subject is correct. This asks whether the
subject lets its operator out. Three placements were considered:

| Option | Tradeoff | Decision |
| --- | --- | --- |
| A section of an existing report, enforced by `check-report` | No new code, no new move, no door opened. But the requirement demands **execution** of the published act, and `check-report` executes nothing, takes no `--subject` drive, and must not: report validation would become side-effecting and non-deterministic, and its `0/1/2` contract would acquire a fourth meaning | Rejected |
| A new subcommand with no moves-table row | Legal — `test_every_row_ships_as_a_real_subcommand_or_as_doctrine` (`tests/test_skill_audit.py:543`) runs moves→subcommands only, and `check-report` is itself a subcommand with no move. But its findings would carry a `- Move:` value with no row in `## Move outcomes`, and `## Undecidable`'s `- Rung: probe` cross-check requires the named move's row read `ran`, so its findings could never be attributed | Rejected |
| **Move 11 + the `exits` subcommand** | Opens the moves door, which costs one row in `references/example-report.md` and its re-signature — measured above as the whole cost. Adds **zero** `REPORT_SHAPE` keys: an exit finding is an ordinary ranked finding carrying `- Move: 11` | **Chosen** |

**Justification from the locks, since the brief asked for it.** The moves table
and `REPORT_SHAPE` are *not* held to each other.
`ReportSchemaSelfDescriptionTests` (`tests/test_skill_audit.py:3355-3380`) binds
`dict_literal_keys(CLI, "REPORT_SHAPE")` to the "shape of a report" table and to
nothing else. The moves table is bound separately by `move_roster` plus the
`Ships as` lock; the stages table by `stage_roster`, which is the only reason a
`Demands` cell must name a `REPORT_SHAPE` key. Three locks, three tables. That
separation is precisely what lets move 11 ship without touching `REPORT_SHAPE`
at all — the widest change to the moves surface that leaves
`ReportSchemaSelfDescriptionTests` untouched by construction rather than by care.

`exits` is chosen over `way-out` and `escape`: the subcommands are plain nouns
(`roster`, `structure`, `walkthrough`, `sensitivity`), no lexicon entry is
required (five shipped subcommands are absent from `FORGE_LEXICON`), and
`escape` already means something else in this file — `build-escaped-the-box`.

### How `exits` verifies by executing, inside stdlib-only, no-network, never-repairs

    states side ──▶ probe_code_side(recipe.states)      [driven, reused verbatim]
            │
            ▼
    per state: recipe-declared extraction over the subject's own text,
               anchored on that state's name  ──▶ the published act, as text
            │
            ├── no act, and the recipe/subject declares the exit a human
            │   judgement ──▶ `judgement`, reported, NOT a finding
            ├── no act, nothing declared ──▶ `unstated`, a finding, reported
            │   with the driveable range that was searched
            ▼
    admission gate, before any process starts:
      • splits into a list of strings, or `published-but-unparseable`
      • no shell metacharacter (; | & $ > < ` newline), because `shell=False`
        would pass them literally and the act would be misreported as broken
      • argv[0] resolves under --subject/--repo-root, or sits in the recipe's
        declared interpreter allowlist — the DRIVER_ENV_ALLOWLIST precedent
            │
            ▼
    materialize_subject_copy(subject, box, exclude)     [reused verbatim]
      the act runs against a COPY. An exit that repairs is allowed to repair,
      and repairs nothing that survives the run.
            │
      constructed_child_env(...)  [commit 0's helper — so PYTHONDONTWRITEBYTECODE]
      cwd inside the copy, shell=False, per-act timeout
            │
            ▼
    tree_digest(real subject) before == after
      ──▶ else Unprobeable, kind=exit-escaped-the-box, sweep halts
    finally: erase_box(box)

The result roster is closed and five-valued: `published-and-ran`,
`published-but-not-executable` (`FileNotFoundError`), `published-but-unparseable`,
`published-but-timed-out`, `unstated`. **`published-and-ran` deliberately does
not read the act's exit code.** The requirement is *a published exit that cannot
be run is not an exit* — reachability, not success. An act that runs and refuses
has been published and can be run; judging whether its refusal was correct is a
different question and this probe does not ask it.

Nothing here is a repair of the subject. The only writes are into a copy inside a
box that is adopted only when empty and erased in a `finally`, and the real
subject's digest gate makes a violation an inability to look rather than a
finding — the same ruling `structure` and `sensitivity` already carry.

**Stated out of reach, because the spec over-reaches here.** `spec.md:638-642`
asks that an unpublished mechanical exit be reported *"and the exit it found is
named"*. The audit cannot find an exit the subject never published: locating one
means searching the subject's surface for an act that would clear a named state,
and any name-similarity heuristic is a guess — refused by exactly the boundary R3
draws. v1 reports `unstated` together with the driveable range it searched, in
the `no-closed-roster` idiom, and says in doctrine that discovering an unpublished
exit is not something it can do. Reported back as a spec correction rather than
implemented as a guess.

## R1: the one that needs `ast`, and cannot live in `roster`

`probe_code_side`'s docstring is explicit that no source of the subject is
parsed, and that this is why the subject may be written in any language
(`audit_cli.py:307-318`). R1 asks a question only source answers: is this check's
iteration source *derived from the subject*, or bounded — a literal collection, a
single module's namespace, or a subset filtered before the assertion.

Three consequences, all stated rather than absorbed:

1. **`ast` enters `audit_cli.py`.** The import line becomes `argparse, ast,
   hashlib, json, os, re, shutil, subprocess, sys, uuid, fnmatch.fnmatch,
   pathlib.Path`. Confirmed still absent today. Note the precise scope of the
   earlier design's "no new stdlib import": it was a claim about the CLI. The
   *suite* already imports `ast` and uses it in `dict_literal_keys`
   (`tests/test_skill_audit.py:116`), which is what makes seven of the self-locks
   possible in the first place.
2. **It is Python-only, and says so.** A non-Python subject's checks are reported
   `unreachable-for-this-language`, never guessed at, never silently absent.
3. **It does not go in `roster`.** A second code-side derivation inside
   `run_roster` would fork the one function whose whole argument is that there is
   no second parser to drift from the first.

The claim side is the check's own name and docstring; the enumeration side is its
iteration source, classified from the syntax tree into a closed roster —
`derived`, `literal-collection`, `single-namespace`, `filtered-subset`. A check
whose stated claim is universal and whose enumeration is bounded is reported with
**both facts side by side**, which is the requirement's own wording and its own
refusal to adjudicate: it does not say the check is wrong, it says what the check
claims and what it walks.

The subject's checks live outside `--subject` — `tests/test_skill_audit.py` sits
at the repository root — exactly as the Move 6 decision above already measured
for guarded facts. `resolve_site`'s `root: "repo"` already covers this; no new
path grammar is needed.

Move 12 by the same reasoning as move 11.

## The full re-forecast, and the split

Ten commits, ~4,100–5,485 authored lines. Every commit is under 1400 on its own;
the aggregate is not one change, and packing it into one would be the silent
overreach this skill is pointed at other people's work to find. **Three changes,
proposed rather than assumed.**

### Change A — this change, unchanged in scope

| Commit | Contents | Forecast |
| --- | --- | --- |
| **0** | `constructed_child_env`, two sites, doctrine, locks | 150–195 |
| **a1** | the `inversion` mechanism and everything a self-probe would redden without | 760–950 |
| **a2** | conditions 9/10 in `check-report`, the `reachability` field, `example-report.md` | 165–245 |
| **b** | three widened `references/probes/*.json` recipes, their shipped-files rows, **no code** | 215–275 |

Total 1,290–1,665. Commit **b** is recipes-only *only after* the two
requirements mis-filed into its capability are moved out — see the measured
errors below.

### Change B — `the-audit-grades-what-a-step-wrote`

Widens shipped surfaces. No new move, no new subcommand, no new stdlib import.

| Commit | Contents | Forecast | Seam |
| --- | --- | --- | --- |
| **B1** | R6: per-step box digest, `roots`, `readOnly`, the subject escape gate `walkthrough` lacks | 370–500 | the drive engine learns to measure what a step wrote |
| **B2** | R2 + R3: `guardReach` block, `identifier_variants`, the control gate, the rename probe and its carried limit | 520–680 | the guard side of Move 0, one loop, two questions |
| **B3** | R5 + R4: `structure`'s `produced` roster and `contentPattern`; `### Demanded, not scaffolded` and its `check-report` enforcement | 500–700 | stage 2's two halves, one report section each |

Total 1,390–1,880. B1 must precede B3 only if B3's deferred derived form is ever
taken; as shipped, the three are independent.

### Change C — `the-questions-the-eleven-moves-do-not-ask`

Two new moves, two new subcommands, `ast` enters.

| Commit | Contents | Forecast | Seam |
| --- | --- | --- | --- |
| **C1** | R7 mechanism: `exits`, the admission gate, the copy-and-box drive, the five-value roster | 720–980 | the mechanism and everything a self-probe would redden without |
| **C2** | R1 mechanism: the `ast` enumeration-reach subcommand, its four-value classification, its language ceiling | 700–960 | same seam, second subcommand |

Total 1,420–1,940. Each commit carries its own moves row, subcommands row,
shipped-files row, `usage.md` invocation, exit-code paragraph, and
`example-report.md` re-signature **in the same commit as its code** — the
`unregistered` rule, applied twice.

If C1 or C2 grows past its upper band during `sdd-tasks`, the seam is already
named and is the same one a1/a2 uses: the mechanism, then the doctrine and report
side. Neither is close enough to 1400 to slice pre-emptively.

**Decision needed before apply: yes** — whether Change B and Change C become
their own SDD changes or this branch carries all ten commits. The design's
recommendation is three changes. It is a routing decision, not an architectural
one, so it is surfaced rather than taken.

## Measured errors in the inputs to this phase

Each verified against source, not inferred.

1. **`spec.md:456` says "Six requirements added" and lists seven.** Headings at
   461, 503, 525, 545, 569, 589, 618. The brief's count of seven is the correct
   one.
2. **`probe-recipe-coverage` contradicts itself.** `spec.md:322-327` requires
   *"This change MUST NOT alter `scripts/audit_cli.py` or any other shipped
   code"*, and then `spec.md:381-420` and `spec.md:421-450`, in the same
   capability, require per-step tree digests and a filesystem-versus-roster
   enumeration — neither expressible in any shipped recipe grammar. Both must
   move out of that capability, or commit **b** stops being recipes-only and its
   215–275 forecast is void.
3. **`spec.md:381-420` and `spec.md:589-616` are the same requirement written
   twice**, under two capabilities, the second a superset (it adds the
   declared-roots half). Left as-is, this ships either two implementations of one
   rule or one rule silently unimplemented. Merge into the Move 8 requirement.
4. **The subject-tree digest is the wrong tree** for both copies of that
   requirement — see the R6 decision above. `run_walkthrough` runs every step
   with `cwd = box`; a correct step never touches the subject, so the literal
   reading fires on every step of every flow.
5. **`spec.md:638-642` asks the audit to name an exit the subject never
   published.** Not derivable without a name-similarity guess, which the
   neighbouring R3 requirement forbids in principle. v1 reports `unstated` plus
   the range searched.
6. **The existing design's Products row was wrong about the historical report.**
   Corrected in place above: it is `predates-the-schema`, never judged, and
   permanently pinned — which makes retroactive invalidation a one-file cost
   rather than a stranded archive.
7. **The brief's claim that `ReportSchemaSelfDescriptionTests` holds the moves
   table and `REPORT_SHAPE` to each other is wrong.** It binds `REPORT_SHAPE` to
   the report-shape table only (`tests/test_skill_audit.py:3363-3367`). Three
   tables, three separate locks. Correcting it is what makes move 11 cheap.
8. **The brief attributes R1 to Move 0 / `roster`.** `roster` cannot host it
   without breaking `probe_code_side`'s stated language independence and adding a
   second code-side derivation to the one function whose argument is that there
   is no second parser. R2 and R3 do belong there; R1 does not.
9. **The earlier design's "no new stdlib import" is a claim about the CLI only.**
   The suite already imports and uses `ast` (`tests/test_skill_audit.py:116`).
   R1 adds it to `audit_cli.py`; nothing about the suite changes.

## What this phase did not do

No suite was run. This phase has no shell: every measurement above comes from
reading source at the cited symbol and line. The baseline in the brief — Python
2457 Ran / OK (skipped=3), npm 386 pass — is carried forward unverified by this
phase, and `sdd-tasks` should re-measure it before the first RED.
