# Proposal Implementation — worked invocations

See [SKILL.md](../SKILL.md) for the contract. Everything below is a real
invocation of `scripts/implementation_cli.py`: standard library only, no keys, no
network. Each command prints one JSON object; exit code `2` means a guard
refused and nothing was touched.

Run the CLI with a **system** interpreter (`python3`). It refuses to run from a
forge virtualenv, so it can never hand the forge's interpreter to a target venv.

## 0. Bind the revision

```bash
node .claude/skills/proposal-deliberation/engine/cli.mjs '{ "operation": "STATUS" }'
```

Take `latest` (e.g. `research-concept-r12.md`). That string is what modules
declare in `__provenance__["revision"]` and what `verify --revision` compares
against. Everything downstream is bound to it.

## 1. Land the repository under `implementations/`

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone <url> implementations/<repo>   # existing repository
git init implementations/<repo>                                # new one
```

`implementations/` is gitignored in the forge, so the clone's own `.git` never becomes a
stray gitlink in the forge's index.

On a repository that tracks weights, pin the skip in the clone as well — the
environment variable covers the clone and nothing else, so a later `git reset
--hard` or branch switch starts downloading again:

```bash
git -C implementations/<repo> config --local filter.lfs.smudge "git-lfs smudge --skip -- %f"
git -C implementations/<repo> config --local filter.lfs.process "git-lfs filter-process --skip"
```

Measured: without this, `git reset --hard` on the migration commit hung
downloading blobs; with it, the same reset took 0.2 s.

`GIT_LFS_SKIP_SMUDGE=1` is not optional on a repository that tracks weights.
Measured on a real target: a smudging clone pulled **3.2 GB** of `.pth` blobs
(4.5 GB on disk); skipping it produced the same 47-file inventory in **43 MB**,
with each weight present as a 133-byte pointer. Every command here works on
paths and on `.py` sources, so the pointers are sufficient — and the LFS quota
stays untouched. Fetch real blobs only when the user actually runs a model.

## 2. The isolated environment

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py env \
  --target implementations/<repo> [--python python3.12]
```

Without `--python` the venv is built from the interpreter running the CLI.
Check `pythonVersion` in the response: the templates declare `requires-python
>= 3.10`, so pass `--python` when the system default is older.

```json
{
  "command": "env",
  "status": "created",
  "pythonVersion": "Python 3.12.4",
  "interpreter": "…/implementations/<repo>/.venv/bin/python",
  "pip": "…/implementations/<repo>/.venv/bin/pip",
  "nextCommand": "…/pip install -r …/assets/requirements-dev.txt"
}
```

Run `nextCommand` as printed. From here on, every command that touches target
code goes through the returned `interpreter`.

## 3. Plan the migration (read-only)

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py plan \
  --target implementations/<repo> --name CREDA > /tmp/plan.json
```

```json
{
  "status": "drift",
  "renames": [],
  "createDirs": ["CREDA/Notebooks", "CREDA/Results", "CREDA/Models", "src/CREDA", "tests"],
  "moves": [
    { "from": "analysis.ipynb", "to": "CREDA/Notebooks/analysis.ipynb", "reason": "notebook" },
    { "from": "utils.py", "to": "src/legacy/utils.py",
      "reason": "pre-existing implementation moves into its own package under src/" }
  ],
  "conflicts": [],
  "unclassified": ["notes.docx"],
  "scaffoldFiles": ["pyproject.toml", "src/CREDA/__init__.py", "tests/test_smoke.py",
                    "CREDA/Notebooks/verification.ipynb"]
}
```

Present `moves` to the user file by file. `unclassified` means no rule covers
those files — ask, never invent a destination. `apply` refuses while the list is
non-empty.

### `renames` beats a pile of moves

When one top-level folder already groups `Notebooks/`, `Results/` or `Models/`
and only its *name* breaks the `<Name>/` ↔ `src/<Name>/` correspondence, the
plan proposes a single directory rename instead of reclassifying its contents:

```json
{
  "renames": [{ "from": "Images", "to": "MIL-CREDA",
                "reason": "product folder has the right shape but the wrong name; renaming preserves every subtree" }],
  "createDirs": ["src/MIL_CREDA", "tests"], "moves": [], "conflicts": [],
  "referenceUpdates": [
    { "file": "src/CREDA/artifacts.py", "occurrences": 2,
      "kind": "path prefix", "replace": "Images/", "with": "MIL-CREDA/" },
    { "file": "src/CREDA/artifacts.py", "occurrences": 1,
      "kind": "quoted path segment", "replace": "\"Images\"", "with": "\"MIL-CREDA\"" }
  ]
}
```

Note `createDirs`: with a hyphenated name the product folder is `MIL-CREDA/`
but the package is `src/MIL_CREDA/`, because `import MIL-CREDA` is a syntax
error. The two forms are derived, never asked twice.

### `referenceUpdates` — a rename is half a migration

Renaming or moving a directory leaves every notebook, module and doc that
addresses the old path pointing at nothing. `apply` rewrites them inside the
same commit, mapping the planned pre-rename paths through the rename first.

Mappings come from renames **and** from moves. A move's prefix is derived by
stripping the longest common suffix, so `Alpha/Results/x.csv -> <Name>/Results/x.csv`
yields `Alpha -> <Name>`, while `Results/x.csv -> <Name>/Results/x.csv` yields
`Results -> <Name>/Results`. An ambiguous prefix (two destinations) is reported
rather than rewritten.

Two forms are detected, and the second matters most:

- **path prefix** — `Images/Results/...` in a string, a URL or prose.
- **quoted path segment** — `root / "Images"`. It contains no slash, so the
  prefix pattern cannot see it, yet it is the form that actually breaks at
  runtime. On the real target, this was the single functional break of the
  whole rename.

`anchored` says how the match is made, and the distinction is not cosmetic:

- A **pure rename** (`Images -> <Name>`) matches anywhere, because the new value
  cannot contain the old one. This is what rewrites a Colab URL such as
  `.../blob/main/Images/Notebooks/`.
- A **nesting** mapping (`Results -> <Name>/Results`) is anchored to a path
  boundary. Without that, `Images/Results/` would become
  `Images/<Name>/Results/` — measured, not hypothetical.

`apply` also removes directories left empty by the moves. `git` does not track
directories, so the old parents survive as empty shells and make a vanished
path look like it still exists.

This is not cosmetic. Reclassifying those files individually flattens
`Results/Resnet18/`, `Results/Resnet50/` and `Results/Transformer/` into one
directory — on a real target that meant three different `ImageCLEF.csv` landing
on the same path. `conflicts` catches both clash kinds (onto an existing file,
and two sources onto one destination) and `apply` refuses, because a cascade of
`git mv` onto one path destroys files silently.

Outside a rename, a file already sitting under a category folder keeps that
category and its subtree whatever its extension says: a `.csv` under `Results/`
is a result, not a dataset.

## 4. Apply, as one separate commit

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py apply \
  --target implementations/<repo> --name CREDA --plan /tmp/plan.json
```

The plan is recomputed and compared before anything moves: if the repository
changed since approval, it refuses with `PLAN_STALE`. On success everything
lands in one commit — `git revert <commit>` undoes the whole migration.

Then write the files listed in `scaffoldFiles` from `../assets/`, substituting
`{{NAME}}`, `{{NAME_LOWER}}`, `{{REVISION}}`, `{{MODULE}}`, `{{FUNCTION_NAME}}`
and `{{INVARIANT_ID}}`.

## 5. Verify

```bash
implementations/<repo>/.venv/bin/python -m pytest -q
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py verify \
  --target implementations/<repo> --name CREDA --revision research-concept-r12.md
```

```json
{
  "structure": { "status": "ok", "missingDirs": [], "strayModules": [],
                 "staleReferences": [], "scaffoldGaps": [] },
  "fidelity": {
    "status": "drift",
    "latestRevision": "research-concept-r12.md",
    "staleModules": ["src/CREDA/kernel.py"],
    "missingProvenance": [],
    "invariantsWithoutTest": ["entropy_non_negative"],
    "modules": [
      { "module": "src/CREDA/kernel.py", "revision": "research-concept-r10.md",
        "sections": ["3"], "invariants": ["kernel_is_psd"], "stale": true }
    ]
  },
  "validation": {
    "status": "ok",
    "smokeTest": true, "invariantTests": ["test_kernel_is_psd"],
    "notebook": { "status": "executed", "codeCells": 3, "unexecuted": [], "errors": [] }
  }
}
```

### The notebook is read, not counted

`notebook.status` answers whether the report was produced, not whether the file
is on disk — a template copied into place is indistinguishable from an executed
report by existence alone, and that is exactly the mistake `pyproject.toml`
already taught. The `.ipynb` records its own state, so the question is
answerable without running anything:

| status | meaning |
| --- | --- |
| `executed` | every non-empty code cell has an `execution_count` and none raised |
| `stale` | the file is there but some cells never ran — `unexecuted` lists them |
| `errored` | a cell raised; `errors` names the cell and the exception |
| `missing` / `unreadable` / `empty` | no file, unparsable JSON, or no code cells |

`errored` is caught even when the notebook was executed with `--allow-errors`,
which otherwise writes a red cell and exits zero.

### A green result needs a reachable red

Two independent ways a check proves nothing while looking like coverage.

`validation.trivialAssertions` catches the syntactic one. `audit.remediesWithoutControl`
catches the structural one: a remedy test that measures its own proposed
replacement and never exercises the declared formulation it corrects. With one
pole only, nothing in the measurement distinguishes a real improvement from a
number that would have passed whatever it was handed.

Every remedy test must show both poles on the same sweep:

```python
declared_survives += global_loss(losses) > 0.1        # Eq. (37) still penalizes
vanishes          += remedy_global_loss(losses, means) < 1e-5   # the remedy does not
```

Measured on this repository, one of the four remedy tests had no control: it
only ever called its own proposal. `audit.status` is `incomplete` while any
remains.

### Assertions that cannot fail

`validation.trivialAssertions` lists two shapes: asserting a truthy constant,
and comparing an expression with itself. The scan covers the whole test module,
not only `assert` statements — the one that got through this repository fed a
counter,

```python
frozen_unchanged += adaptation(w) == adaptation(w)   # always true
assert frozen_unchanged == SWEEP_SIZE                # perfectly legitimate
```

and stayed green through three full rounds of the scenario battery. Looking only
inside assertions finds the comfortable case, not the dangerous one. `!=` is
exempt: `x != x` is the standard NaN test.

`validation.status` is `ok` only when the smoke test exists, the notebook is
`executed`, and no trivial assertion is present. Never report the ladder as run
on anything else.

## The audit bridge

`verify` also reads `tests/findings.py` statically and reports an `audit`
section. The contract mirrors the invariant bridge: every declared finding needs
a `test_finding_<id>` proving the defect is real and a `test_remedy_<id>`
proving the proposed correction resolves it without breaking anything already
established.

```json
{
  "audit": {
    "status": "ok",
    "findings": [
      { "id": "local_penalty_guarantee_is_vacuous", "kind": "overstated-claim",
        "status": "theorem", "rate": "200/200",
        "equations": ["38"], "remedyEquations": ["38"] }
    ],
    "findingsWithoutEvidence": [], "findingsWithoutRemedy": [],
    "remediesWithoutValidation": []
  }
}
```

`kind` is one of `ill-formed`, `underspecified`, `missing-complement`,
`overstated-claim`, `ill-posed-objective`, `loose-constant`. `status` is
`theorem` (holds across the whole sweep) or `tendency` (holds at the declared
rate and must not be asserted as a law).

Both halves matter. Validating the remedy is what caught the second finding in
this repository: the first proposed fix mirrored the shape of Eq. (38), and the
sweep showed that shape cannot damp anything — which turned out to be a defect
in Eq. (38) itself, not in the fix.

### `admit` — admissibility is ruled on first

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py admit \
  --target implementations/<repo> --name <Name> --revision research-concept-r12.md
```

```json
{ "status": "admitted",
  "admitted": ["local_penalty_guarantee_is_vacuous", "..."],
  "inadmissible": {},
  "introducesNotation": { "confidence_is_an_unconstrained_decision_variable":
                          ["\\operatorname{sg}", "\\lambda_{\\mathrm{conf}}"] },
  "record": "tests/admissibility.json" }
```

The ruling is written into the target and the remedy suite reads it before
measuring anything: without it every `test_remedy_<id>` fails immediately, and a
finding ruled inadmissible is never measured while the others still run. Only
the verdict travels — the revision's text stays in the forge.

Order is the whole point. A remedy that cites a missing equation or leans on
undefined notation would otherwise be swept over 200 configurations, and those
numbers would read as evidence for something that should not have reached the
bench. `verify` requires the ruling to exist, to cover every declared finding,
and to have been issued against the same revision bytes; anything else leaves
`audit` at `incomplete`.

### Sound is not the same as complete

`audit.compatibility` answers a different question from the sweep: can the
remedy be written inside the proposal as it stands? Each finding declares `uses`
— notation the remedy leans on, which must appear verbatim in the bound
revision — and `introduces`, notation it would add.

| status | meaning |
| --- | --- |
| `ok` | every cited equation exists, all notation is already defined, nothing new |
| `needs-deliberation` | sound and validated, but it would add notation |
| `incompatible` | cites an equation the revision does not have, or leans on undefined notation |
| `unknown` | the revision could not be read; nothing is concluded |

`needs-deliberation` propagates to `audit.status`, so a remedy that would extend
the notation can never be reported as settled. On this repository three remedies
are expressible as they stand, and the fourth — freezing the confidence with
`sg[·]` and adding `L_conf` with its own coefficient — introduces three symbols
the revision does not define. That is a decision for the deliberation, not a
verdict this skill may issue.

## Reading `verify`

Two independent findings, reported separately:

- **structure drift** — the layout no longer matches, or `staleReferences` lists
  a file addressing `<folder>/<Category>` that does not resolve. Both the
  textual form and the chained quoted form (`root / "Alpha" / "Results"`) are
  detected, and an **empty** directory counts as unresolved: the content it
  named is gone. A lone quoted segment (`root / "data"`) is never flagged,
  because fallback probes for optional dataset roots are legitimately absent
  and burying the real finding is worse. Fix with `plan` → `apply`.
- **fidelity drift** — `staleModules` implement an older revision than the one
  in `--revision`; `invariantsWithoutTest` are claims declared in code with no
  test enforcing them. Both need the user's decision before you touch anything.

Omit `--revision` and `fidelity.status` is `unknown`: the modules' declared
revisions are still listed, but nothing is compared. Never report an
implementation as up to date from an `unknown` run.

## Guard codes

| Code | Meaning |
| --- | --- |
| `OUTSIDE_WORKSPACE` | Target is not under `implementations/`. Clone it there. |
| `NOT_A_GIT_REPO` | No `.git`. Migration needs a revertible commit. |
| `DIRTY_WORKTREE` | Uncommitted or untracked changes. Commit or stash first. |
| `FORGE_INTERPRETER` | The CLI is running from a forge venv. Use system `python3`. |
| `PLAN_STALE` | The repository changed after approval. Re-plan, re-approve. |
| `DESTINATION_CONFLICT` | A destination is taken, or two sources target one path. |
| `UNCLASSIFIED_FILES` | No rule covers some files. Ask where they belong. |
| `APPLY_ABORTED` | Something failed mid-migration. Nothing was committed and the tree was restored; re-run `plan`. |

`DESTINATION_CONFLICT` also covers a rename whose destination already exists.
That case is not cosmetic: `git mv A B` with `B` present does not rename, it
moves `A` *inside* `B`, which silently produces `<Name>/Images/Results/...`.

`apply` is all-or-nothing. The tree is verified clean before any mutation, so a
failure discards the partial work and restores exactly the reviewed starting
point instead of leaving a half-migrated repository.
