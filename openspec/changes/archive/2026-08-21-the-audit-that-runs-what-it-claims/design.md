# Design: the-audit-that-runs-what-it-claims

## Technical Approach

Three additions to one module, all built on the split this skill already proved: the
recipe carries the subject, the machinery stays general. One new primitive —
`tree_digest(root, exclude)` — is the only code in `audit_cli.py` allowed to touch the
filesystem, and it serves the walk, the containment proof, and the follow-up change's
`manifest`. `structure` derives three path sets and picks the odd one out arithmetically.
`walkthrough` drives an ordered sequence and names the index that stalls. `check-report`
gains two enforced sections, and the move roster behind one of them is **derived from
`SKILL.md`'s own moves table** rather than listed in the tool.

## Architecture Decisions

### Decision: the from-zero builder is recipe-declared steps, and the auditor's builder is its repository at `HEAD`

| Option | Tradeoff | Decision |
|---|---|---|
| Ship a scaffold script for the auditor | Its file list would be hand-written — a third restated roster; theatre | Rejected |
| Point the first recipe at another skill's `materialize.py` | Ruled out by the user | Rejected |
| `fromZero.steps` = ordered argv lists run inside the box; the auditor declares `git archive HEAD:<subject>` + `tar -x` | Needs `git`/`tar`; absent → exit `2` | **Chosen** |

The auditor has no materializer, and its honest from-zero producer is what a fresh install
materializes. Uncommitted work then reads as `builder-broken`, which is literally true: a
fresh install would not have it.

### Decision: the recipe shape for `structure`

```json
{"surface": "shipped-files",
 "declared": {"table": "| Path | Holds |", "column": 0},
 "disk": {"root": "."},
 "fromZero": {"root": "build", "steps": [
   ["git","-C","{repoRoot}","archive","--format=tar","-o","{box}/subject.tar","HEAD:.claude/skills/skill-audit"],
   ["tar","-xf","{box}/subject.tar","-C","{box}/build"]]},
 "exclude": ["__pycache__/*", "*.pyc", ".DS_Store"]}
```

Only `{repoRoot}`, `{subject}`, `{box}` interpolate, each resolved absolutely by the tool;
any other `{...}` is `Unprobeable`. `shell=False`, cwd always the box. Declared side reuses
`markdown_table_rows` + the cell cleaning `doctrine_side` already does.

**Normalisation** — one function, applied to all three sides and to `exclude`:
POSIX separators, `./` stripped, no trailing slash, **files only**, **case preserved**,
sets compared sorted. A declared cell ending in `/`, absolute, containing `..`, a glob
character, or a backslash is a shape the walk can never produce: it goes to `notes` as
`shape-not-walkable` and is excluded from all three sides. It is never expanded against the
disk (that would let the producer build the documented side) and never counted as a
divergence (that would blame the disk for a spelling). A declared member matching a walked
member only case-insensitively is `notes` kind `case-only-divergence`, never folded.
**Any side that normalises to zero members is `Unprobeable`, exit `2`** — an empty declared
side would print "the document is wrong" over the whole disk.

**Outcome** (`ADJUDICATIONS` untouched at three): all equal → `agree`; exactly one side
differs → `disk-stale` | `builder-broken` | `document-wrong`; all three pairwise different →
`three-way-divergence`. Evidence is emitted as sets — `onlyIn` and `missingFrom`, per side —
never a boolean. The tool emits no adjudication; mapping outcome to adjudication is a new
doctrine row applied by the auditor.

### Decision: the box, and what an escape means

`<repoRoot>/implementations/_structure_<surface>` per `SKILL.md:225`. Existing and
`tree_digest` proves it empty → adopted; non-empty → exit `2` naming the path. Removed in a
`finally`, absence proven by `tree_digest` of `implementations/`, never `git status`
(`FORBIDDEN_SUPPORT`, `audit_cli.py:556`). `tree_digest(subject)` is taken before and after
the build: **any change → exit `2`, kind `build-escaped-the-box`, changed paths named.**
Not a finding: the tool cannot tell an intended write from an escape, and the auditor
reporting a mutation it caused itself as the subject's defect breaks its own `mutations: 0`.

### Decision: the recipe shape for `walkthrough`

Steps are `{"name", "argv", "cwd"?, "expect": {"exit": int|"any"|"nonzero", "stdout"?,
"stderr"?, "absent"?}, "reset"?: false}`. **A step declaring no expectation is
`Unprobeable`** — a gate that asserts nothing is not a gate. `exit` and stream regexes may
both be declared and all declared parts must hold.

- **Expected failure vs. stall**: a step matching its own `expect` is `passed` whatever its
  exit code, so a documented refusal is a pass. The **first** step whose observation
  contradicts its declaration is the `stall`; a timeout is a stall of kind `timeout`.
- Every later step is `unreached`, and the report puts them in `## Unchecked`
  (`SKILL.md:187-189`), never in clean.
- `argv[0]` missing at index 0 → `Unprobeable` (the flow was never entered). At index > 0 →
  a stall: a documented command that is not there is a fact about the flow.
- **One box for the whole sequence**, state accumulating as a user's would; a step may
  declare `"reset": true` to demand a fresh empty box. Same box helper, same proof.
- Exit `0` for any verdict including a stall; `2` only for inability.

### Decision: the move roster is derived, and `check-report` reads its own `SKILL.md`

`check-report` resolves `Path(__file__).resolve().parent.parent / "SKILL.md"`, parses the
moves table with the module's own `markdown_table_rows`, and requires one row in
`## Move outcomes` per numbered move plus the literal `textual` for the single unnumbered row
(a shape `MovesTableTests` already locks). A missing or unparseable table is exit `2`, not a
pass; `--moves <path>` is the named override. Each outcome cell must be `ran` or
`skipped: <reason>` with a non-empty reason. Rationale: a hand-written move list inside the
validator ships defect D itself.

### Decision: `repair-units` is enforced by coverage, not arithmetic

`## Repair units`, a table `| Unit | Findings | Changed lines |`. Every `### F<n>.` block
appears in exactly one unit; a label naming no finding is a violation; the forecast cell must
be an integer. No sum check against `## Changed-line forecast` — brittle over-enforcement.
`SKILL.md:247-248` drops "the slicing" for "the repair units"; `## Scope, and who chooses it`
keeps `slicing`.

### Decision: the moves table's rows 1 and 2 — corrected *and* extended

Row 1 → `Ships as: structure`: its own sentence *is* the from-zero diff. **Row 2 stays
`roster`**, against gap A's second half: `probe_code_side` resolves `--subject` and runs it
as a real process from its own directory (`audit_cli.py:317-333`), which is exactly "drive
the subject as it exists on disk". New **move 8**, `Ships as: walkthrough`, for the ordered
user-mode drive. Appended, not inserted: renumbering would silently change what `- Move: 3`
means in every already-shipped report.

### Decision: the `manifest` contract with the follow-up change

Binding, and enforced by a lock rather than by prose:

1. `tree_digest(root, exclude=()) -> dict[str, str]`, POSIX relative path → sha256, files
   only, in the code-side section below the `ast` divider.
2. **`SingleWalkTests` asserts, over `audit_cli.py`'s syntax tree, that `rglob`/`walk`/
   `iterdir`/`scandir`/`glob` appear inside `tree_digest` and nowhere else.** The follow-up
   physically cannot add a second walk without turning that lock red.
3. `manifest --root --baseline` is a thin subcommand over it; `added`/`removed`/`changed`
   come from a `digest_diff(before, after)` the follow-up adds *beside* `tree_digest`.
4. Exclusion semantics are fixed here — recipe-declared globs, **no built-in defaults**, a
   default being a hidden narrowing of the domain — and the follow-up inherits them.
5. `tests/test_skill_audit.py:1527` deletes its private copy and imports the shipped one.

## Data Flow

    recipe ──┬─ declared → markdown_table_rows → normalise ─┐
             ├─ disk     → tree_digest(subject)  → normalise ┼→ odd-side-out → outcome + sets
             └─ fromZero → box(empty) → steps → tree_digest ─┘        │
                              │                                       └→ notes, containment
                              └─ subject digest before/after → escape → exit 2

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/skill-audit/scripts/audit_cli.py` | Modify | `tree_digest`, box helpers, `structure`, `walkthrough`, two `REPORT_SHAPE` keys, derived move roster |
| `.claude/skills/skill-audit/SKILL.md` | Modify | New `## The shipped files` table (the declared side); moves row 1 + new row 8; two subcommand rows; two report-shape rows; five Decision Gates; `## Handoff` prose |
| `.claude/skills/skill-audit/references/probes/skill-audit.structure.json` | Create | Structure recipe, subject = the auditor |
| `.claude/skills/skill-audit/references/probes/skill-audit.first-run.json` | Create | Walkthrough recipe, subject = the auditor |
| `.claude/skills/skill-audit/references/usage.md` | Modify | One worked invocation per new subcommand; exit table gains two columns |
| `.claude/skills/skill-audit/references/example-report.md` | Modify | Gains `## Move outcomes` and `## Repair units` or it stops validating |
| `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md` | Modify | Same two sections — `FirstDamageReportTests` runs `check-report` over it |
| `tests/test_skill_audit.py` | Modify | New locks; the four named locks co-edited; `tree_digest` copy deleted |

No file under `implementations/` and no other skill is edited.

## Interfaces / Contracts

`structure` payload: `{surface, sides{declared,disk,fromZero}, outcome, onlyIn{...},
missingFrom{...}, notes[], containment{box,beforeEmpty,afterRemoved}}`.
`walkthrough` payload: `{surface, steps[{index,name,outcome,expected,observed}],
stall|null, unreached[], containment{...}}`. Both: exit `0` any verdict, `2` inability.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | normalisation, `shape-not-walkable`, outcome arithmetic, move-roster derivation, repair-unit coverage | fixtures in a `BoxMixin` box |
| Integration | all three `structure` outcomes, `three-way-divergence`, walkthrough stall, box escape | real subprocesses in a real box |
| Inversion | every new lock seen RED first; restore by inverse patch, never `git checkout --` | `strict_tdd: true` |
| Suite integrity | `SuiteIntegrityTests`: no duplicate top-level class name and no duplicate `test_` name within a class | `ast` over this test file |
| Counting | `python3 -m unittest discover -s tests` before/after; the count must rise by the number added | `openspec/config.yaml:19,21` never runs this file and is **out of scope** |

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|---|---|---|---|
| Documentation-like paths | N/A — walked files are hashed, never classified or executed | — | — |
| Git repository selection | Applicable — the shipped recipe runs `git -C {repoRoot}` | `{repoRoot}`/`{subject}`/`{box}` are resolved absolutely by the tool, never taken as recipe strings; cwd is always the box; `shell=False`; unknown token → exit `2` | a recipe with an unknown `{token}`; a build writing into the subject root → exit `2` `build-escaped-the-box` |
| Commit state | Applicable — from-zero reads `HEAD`, so uncommitted or staged-only files change that side | Documented: the builder is the repository at `HEAD`; an uncommitted file is genuinely absent from a fresh install | a file on disk and absent from `HEAD` yields `builder-broken` |
| Push state | N/A — this repo has no branches and nothing pushes | — | — |
| PR commands | N/A — no PR automation; three ordered commits on `main` | — | — |

## Migration / Rollout

No migration. Three ordered commits on `main`, slice 1 first so slices 2 and 3 are covered by
the derived roster instead of editing it twice. Each reverts independently in reverse order.
The ~1,030-line forecast against `review_budget_lines: 800` is acknowledged and accepted;
scope is not silently shrunk to fit it.

## Open Questions

- [ ] Row 2 of the moves table is kept at `Ships as: roster` against gap A's second half, on
      the evidence at `audit_cli.py:317-333`. Overrule and it becomes `structure` in slice 2.
- [ ] `git` and `tar` become soft prerequisites of the shipped `structure` recipe — absent,
      the worked invocation exits `2` and `UsageReferenceTests` (which accepts only `0`/`1`)
      turns red on a machine without them.
