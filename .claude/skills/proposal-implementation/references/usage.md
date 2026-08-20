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

Take `latest` (e.g. `research-concept-r05.md`). That string is what modules
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
  --target implementations/<repo> --name Example-Method > /tmp/plan.json
```

```json
{
  "status": "drift",
  "renames": [],
  "createDirs": ["Example-Method/Notebooks", "Example-Method/Results", "Example-Method/Models", "src/Example_Method", "tests"],
  "moves": [
    { "from": "analysis.ipynb", "to": "Example-Method/Notebooks/analysis.ipynb", "reason": "notebook" },
    { "from": "utils.py", "to": "src/legacy/utils.py",
      "reason": "pre-existing implementation moves into its own package under src/" }
  ],
  "conflicts": [],
  "unclassified": ["notes.docx"],
  "scaffoldFiles": [".gitignore (.venv/, __pycache__/, .ipynb_checkpoints/)",
                    "pyproject.toml [tool.pytest.ini_options] pythonpath",
                    "src/Example_Method/__init__.py",
                    "src/Example_Method_Benchmark/__init__.py",
                    "src/Example_Method_Benchmark/report_digest.py",
                    "tests/test_smoke.py", "tests/findings.py",
                    "tests/conftest.py", "tests/sweep.py",
                    "tests/admissibility.py",
                    "tests/test_audit.py", "tests/test_remedies.py",
                    "Example-Method/Notebooks/verification.ipynb"]
}
```

Present `moves` to the user file by file. `unclassified` means no rule covers
those files — ask, never invent a destination. `apply` refuses while the list is
non-empty.

`status` is `compliant` only when there is nothing left to decide: no move, no
rename, no missing directory, no scaffold gap **and** no `conflicts` or
`unclassified`. A tree `apply` is about to refuse is never reported as settled.

### `renames` beats a pile of moves

When one top-level folder already groups `Notebooks/`, `Results/` or `Models/`
and only its *name* breaks the `<Name>/` ↔ `src/<Name>/` correspondence, the
plan proposes a single directory rename instead of reclassifying its contents:

```json
{
  "renames": [{ "from": "Images", "to": "Example-Method",
                "reason": "product folder has the right shape but the wrong name; renaming preserves every subtree" }],
  "createDirs": ["src/Example_Method", "tests"], "moves": [], "conflicts": [],
  "referenceUpdates": [
    { "file": "src/Example_Method/artifacts.py", "occurrences": 2,
      "kind": "path prefix", "replace": "Images/", "with": "Example-Method/" },
    { "file": "src/Example_Method/artifacts.py", "occurrences": 1,
      "kind": "quoted path segment", "replace": "\"Images\"", "with": "\"Example-Method\"" }
  ]
}
```

Note `createDirs`: with a hyphenated name the product folder is `Example-Method/`
but the package is `src/Example_Method/`, because `import Example-Method` is a syntax
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
directory — on a real target that meant three different `results.csv` files landing
on the same path. `conflicts` catches both clash kinds (onto an existing file,
and two sources onto one destination) and `apply` refuses, because a cascade of
`git mv` onto one path destroys files silently.

Outside a rename, a file already sitting under a category folder keeps that
category and its subtree whatever its extension says: a `.csv` under `Results/`
is a result, not a dataset.

## 4. Apply, as one separate commit

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py apply \
  --target implementations/<repo> --name Example-Method --plan /tmp/plan.json
```

The plan is recomputed and compared before anything moves: if the repository
changed since approval, it refuses with `PLAN_STALE`. The comparison covers the
`referenceUpdates` too, not only the renames, moves and directories — a commit
that edits nothing but a file's *contents* leaves all three identical, and
without that check `apply` would rewrite a file that was never on the list the
user approved. On success everything lands in one commit — `git revert <commit>`
undoes the whole migration.

Then write every file listed in `scaffoldFiles`. The templates live under
`assets/kit/` inside this skill — `kit/src/`, `kit/src_benchmark/`, `kit/tests/`
and `kit/nb/` — with `assets/pyproject.template.toml` beside them. SKILL.md
step 5 carries the gap → template mapping file by file.

Substitute these placeholders. Every one of them occurs in some template, and
no template carries any other.

`Answered at` says when the value exists, which is not the same as when the file
carrying the token is written. `tests/test_smoke.py` is placed by the scaffold and
carries `{{MODULE}}`, which only step 9 can answer: a leftover `{{MODULE}}` there
is the scaffold posing its question, not a substitution somebody missed. Guessing
a value to make it disappear produces a suite that passes while asserting nothing.

| Token | Substituted with | Answered at |
| --- | --- | --- |
| `{{NAME}}` | the `<Name>/` product folder form | scaffold |
| `{{NAME_LOWER}}` | the distribution name, lowercased and hyphenated | scaffold |
| `{{PKG}}` | the `src/<Package>/` importable form | scaffold |
| `{{MODULE}}` | the module being written, without its suffix | step 9 |
| `{{FUNCTION_NAME}}` | the function that module's invariant is asserted over | step 9 |
| `{{INVARIANT_ID}}` | the invariant's identifier, as `__provenance__` declares it | step 9 |
| `{{REVISION}}` | the bound revision's filename | scaffold |
| `{{SECTION}}` | the section of the proposal the module implements | step 9 |
| `{{EQUATION}}` | the equation it implements, by tag | step 9 |
| `{{ONE_LINE_STATEMENT_OF_THE_MATHEMATICAL_OBJECT}}` | one line saying what the module computes | step 9 |
| `{{SEED}}` | the seed the suite fixes | scaffold |
| `{{SEEDS}}` | the seeds a probe run repeats over | probe |
| `{{EPOCHS}}` | the epoch count a probe run reduces to | probe |
| `{{FRACTION}}` | the fraction of the data a probe run uses | probe |
| `{{DATASET}}` | the dataset a probe run reads | probe |
| `{{BASELINE}}` | the baseline a probe compares against | probe |
| `{{PROBE_RESULTS}}` | the filename a probe writes its record to | probe |
| `{{EXPECTATION}}` | what a synthetic case is expected to produce | step 9 |

## 5. Verify

```bash
implementations/<repo>/.venv/bin/python -m pytest -q
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py verify \
  --target implementations/<repo> --name Example-Method --revision research-concept-r05.md
```

```json
{
  "structure": { "status": "ok", "missingDirs": [], "strayModules": [],
                 "staleReferences": [], "scaffoldGaps": [] },
  "fidelity": {
    "status": "drift",
    "latestRevision": "research-concept-r05.md",
    "staleModules": ["src/Example_Method/kernel.py"],
    "missingProvenance": [],
    "invariantsWithoutTest": ["entropy_non_negative"],
    "modules": [
      { "module": "src/Example_Method/kernel.py", "revision": "research-concept-r03.md",
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
  --target implementations/<repo> --name <Name> --revision research-concept-r05.md
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

`fidelity.status` carries four values, and the headline never reads better than
the block underneath it:

| value | meaning |
| --- | --- |
| `unknown` | no revision could be established at all — none was given and none discovered — so nothing was compared |
| `drift` | something that exists is defective: a stale module, missing provenance, an untested invariant, or an arm that never calls what it declares |
| `undeclared` | the Benchmark package exists and every block of `__benchmark__` is still at its scaffolded empty value; `fidelity.benchmark.status` reports the same word |
| `ok` | a declared benchmark, and none of the above |

`drift` outranks `undeclared` on purpose, the way `unfaithful` already outranks
`stale` inside `fidelity.benchmark`: a stale module is a defect in something that
exists, and an undeclared benchmark is the absence of a declaration. An
**absent** Benchmark package is deliberately not folded in — there is nothing to
be unfaithful to, and `structure.scaffoldGaps` already names the missing file.

### Which revision counts as the newest

Without `--revision`, `verify` derives a family from the name the bench itself
declares and discovers the newest member. Only **published** revisions are
eligible: a revision is published when the deliberation skill writes the artifact
marker as the file's first bytes, and a draft, an export or a copy dropped into
the same directory carries no marker. Before that rule existed, such a file
became "the newest" and every module was reported stale against a document nobody
had published.

The discriminator is the marker, never a filename shape — the resolver knows no
naming convention, by design, so a forge whose revisions are `draft-4.md` is
served by the identical code. Three additive fields say what discovery saw:

| field | meaning |
| --- | --- |
| `fidelity.markerOwned` | `true` when at least one candidate of the family carries the marker, so only marked candidates were eligible; `false` when none does and resolution is exactly what it always was |
| `fidelity.nonManagedCandidates` | the unmarked candidates that were passed over, named rather than silently filtered |
| `fidelity.revisionTie` | candidates tying on the digit tuple (`draft-1.md` and `draft-01.md` are one family and one key); the deterministic pick is preserved and the ambiguity is reported |

All three are reported and none of them refuses: `verify` reads, and a stray file
in a directory must not stop the whole check. The filter applies to discovery
only — an explicit `--revision` is read verbatim, whether or not it is marked.

## `handoff` — back to the deliberation, sized by reach

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py handoff \
  --target implementations/<repo> --name <Name> --revision research-concept-r05.md
```

Every open finding is measured against the document itself: how many equations
the remedy rewrites, how much notation it adds, and how often the rest of the
text cites those equations. Nothing is judged — all three are read.

| class | condition | what happens |
| --- | --- | --- |
| `local` | one equation, no new notation, cited at most once elsewhere | `settleInline`: an agenda item for the current deliberation |
| `structural` | anything wider | `deferToOwnSession`: a ready prompt saying why it needs its own session |

A deferred item says why in `deferredBecause`:

| value | meaning |
| --- | --- |
| `structural-reach` | the remedy rewrites more than one equation, adds notation, or touches an equation the text leans on |
| `remedy-text-missing` | local reach, but nobody wrote the corrected block (`remedy_block`) |
| `remedy-locus-missing` | it measures as local only because `remedy_equations` is empty, so there is no equation to resolve against |

Measured on this repository: three remedies are local, and the confidence one is
not — it rewrites two equations, adds three symbols, and touches Eq. (24), which
the text cites three times.

`adoption` is read from the revision rather than assumed:

| state | meaning |
| --- | --- |
| `open` | the text the remedy replaces is still there |
| `adopted` | it is gone and an expected form is present |
| `changed-unrecognized` | it is gone but nothing expected appeared — confirm by hand |
| `unknown` | the finding declares no marker |

Inference is textual, so it is built to fail toward `open`. An adopted finding
stops counting as introducing notation: the deliberation settled that when it
published.

### After adoption: the remedy becomes an invariant

`audit.migration` closes the loop. Once the deliberation publishes a remedy it
is no longer a correction under consideration — it is what the proposal says,
and it belongs where every other claim of the proposal lives.

Each finding declares `becomes_invariant`. When its adoption reads `adopted`,
three things must have happened:

```
test_remedy_<id>            retired
test_<becomes_invariant>    present in the invariant suite
__provenance__["invariants"] declares <becomes_invariant> in the module
```

`audit.status` stays `incomplete` until all three hold. The skill checks the
move; writing it is the agent's work, as with any other code. Leaving the
remedy in place would keep reporting a defect the revision no longer has.

## Guard codes

A guard's failure is silent by definition: when one stops working, every happy
path stays green. They are exercised as a suite, each driven to its failure
state, alongside the scenarios — not verified by hand once.



| Code | Meaning |
| --- | --- |
| `OUTSIDE_WORKSPACE` | Target is not under `implementations/`. Clone it there. |
| `NOT_A_GIT_REPO` | No `.git`. Migration needs a revertible commit. |
| `DIRTY_WORKTREE` | Uncommitted or untracked changes. Commit or stash first. |
| `FORGE_INTERPRETER` | The CLI is running from a forge venv. Use system `python3`. |
| `PLAN_STALE` | The repository changed after approval — a rename, a move, a directory **or a reference update**. Re-plan, re-approve. |
| `MALFORMED_FINDINGS` | `tests/findings.py` exists but cannot be read as a list of mappings each carrying an `id`. Reading it as empty would answer `audit: none`, which is what an audited, clean repository answers. |
| `DESTINATION_CONFLICT` | A destination is taken, or two sources target one path. |
| `UNCLASSIFIED_FILES` | No rule covers some files. Ask where they belong. |
| `APPLY_ABORTED` | Something failed mid-migration. Nothing was committed and the tree was restored; re-run `plan`. |

`DESTINATION_CONFLICT` also covers a rename whose destination already exists.
That case is not cosmetic: `git mv A B` with `B` present does not rename, it
moves `A` *inside* `B`, which silently produces `<Name>/Images/Results/...`.

`apply` is all-or-nothing. The tree is verified clean before any mutation, so a
failure discards the partial work and restores exactly the reviewed starting
point instead of leaving a half-migrated repository.
