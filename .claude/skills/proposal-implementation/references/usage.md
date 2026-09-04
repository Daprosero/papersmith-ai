# Proposal Implementation — worked invocations

See [SKILL.md](../SKILL.md) for the contract. Everything below is a real
invocation of `scripts/implementation_cli.py`: standard library only, no keys, no
network. Each command prints one JSON object; exit code `2` means a guard
refused and nothing was touched.

Run the CLI with a **system** interpreter (`python3`). It refuses to run from a
forge virtualenv, so it can never hand the forge's interpreter to a target venv.

## 0. Bind the revision

```bash
node .claude/skills/proposal-deliberation/cli.mjs '{ "operation": "STATUS" }'
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

### The name, normalized before the directory exists

The product directory and the Python package are two spellings of one name, and
a hyphen is legal in exactly one of them. `name` answers that before anything is
created, which is the only moment the answer is free:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py name \
  --name "Example-Method"
```

```json
{ "status": "ok", "name": "Example-Method", "package": "Example_Method" }
```

It is the one command that takes no `--target`: normalizing a name runs before a
repository exists. Show the pair to the user before scaffolding either, because
renaming afterwards is a migration and this is a question.

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
  "nextCommand": "…/pip install -r …/assets/requirements-dev.txt -r …/requirements.txt",
  "manifests": {
    "rows": [{"name": "requirements.txt", "status": "honoured"}],
    "args": ["-r", "…/requirements.txt"]
  }
}
```

`nextCommand` is one invocation: the forge's own dev requirements first, then
every manifest the target declares and this flow can honour — `-r
requirements.txt`, `-r requirements-dev.txt`, `-e .` when a build descriptor
exists — last. A conda `environment.yml` is named in `manifests.rows` with
`"status": "unhonoured"` and a reason, never silently skipped; a target that
declares nothing gets `"rows": []` and an `absentNote` saying so. Run
`nextCommand` as printed. From here on, every command that touches target
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
  "scaffoldFiles": [".gitignore (.venv/, __pycache__/, .ipynb_checkpoints/, .implementation/)",
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

## Materialize the scaffold

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --stage scaffold --plan /tmp/plan.json --seed 7
```

This is the command that fills every scaffold gap — never the agent copying
files by hand. It writes every one of `scaffoldFiles`' eleven file
destinations from `assets/kit/` — `kit/src_benchmark/`, `kit/tests/` and
`kit/nb/`, with `src/<Package>/__init__.py` authored directly — merges the
two anchors (`.gitignore`, `pyproject.toml [tool.pytest.ini_options]`) into
whatever the target already has, and records every write in
`<Name>/.implementation/materialization.json`, git-ignored, written last and
atomically after every file has landed.

The plan gate is the same one `apply` uses: `PLAN_MISMATCH` for a plan
produced elsewhere, `PLAN_STALE` if the repository's structure moved since
approval. `--stage` requires a clean worktree — commit whatever `apply` just
produced first. A destination already present on disk is never a
destination: it is simply excluded from what this call writes, so a target
scaffolded by hand keeps its hand-written files untouched (and unrecorded —
see `UNRECORDED_SCAFFOLD` below). `DESTINATION_CONFLICT` fires only on the
genuine race of a file appearing between that computation and the write.

## Materialize the object scaffolding

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --stage objects --plan /tmp/plan.json --seed 7
```

The three destinations SKILL.md step 9 names: `src/<Package>/module.py`,
`tests/test_invariants.py`, `tests/test_synthetic.py`. Same plan/clean-worktree
preflight as `--stage scaffold`, plus one more: it refuses
`OBJECT_MAP_NOT_APPROVED` until `src/<Package>_Benchmark/__init__.py` carries
step 8's `revision`/`premises`. Unlike scaffold, this write is **not** gated on
the result parsing — `writable_at_scaffold_time`'s `ast.parse` check is scoped
to the scaffold stage on purpose. All three templates carry tokens
(`{{FUNCTION_NAME}}`, `{{INVARIANT_ID}}`, `{{EXPECTATION}}`, ...) sitting
inside Python identifiers that only step 9's own authoring can answer, so this
stage writes them as scaffolding for the agent to author over, left standing
exactly like `{{MODULE}}` is in a freshly scaffolded `test_smoke.py`. Author
the real module and tests, then run `materialize --authored <path>` on each of
the three so `verify` stops reading them as drift.

## Materialize the harness

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --stage harness --plan /tmp/plan.json
```

The three destinations the harness-wiring section names: `benchmark.py`,
`verdict.py`, `probe.ipynb`. No `--seed`: none of the three carries a
`{{SEED}}` token (`probe.ipynb` carries `{{SEEDS}}` instead, answered later, at
probe time, not by this command). No object-map precondition either —
`benchmark.py`/`verdict.py` carry no token at all and parse the moment they
land. `wiring.py` stays out of this stage entirely: SKILL.md states it is
bespoke-authored, never a kit destination.

### Declaring authorship, and adopting what was never recorded

Two more modes, both ledger-only — no file write, no plan gate, and
deliberately no clean-worktree requirement, because the file they name is by
definition an uncommitted edit:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --authored src/Example_Method/module.py
```

`--authored <path>` releases the drift seal on one receipt-recorded
destination after the agent has genuinely authored over it — the record's
`writtenSha256` is updated to the new bytes and `kind` becomes `"authored"`.
It refuses `NO_RECEIPT_ENTRY` on a path the engine never wrote in the first
place; that path is adopted, not re-sealed. The release is per-declaration:
a second silent edit after this drifts again.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py materialize \
  --target implementations/<repo> --name Example-Method \
  --adopt tests/test_smoke.py
```

`--adopt <path>` is the remedy for `UNRECORDED_SCAFFOLD` (see the refusal
table below): a kit destination exists on disk with no receipt entry
explaining it — most commonly because a target was scaffolded before this
command existed. Adoption records the destination's current sha256 with
`kind: "adopted"`, distinguishable forever from `"materialized"`. **This
degrades the guarantee, and says so where an operator reads it**: adoption
records who is responsible for the bytes; it does not verify the bytes came
from the kit. For an adopted destination the guarantee is "the record names
who wrote them," not "the engine owns the bytes." Adopt one path at a time,
deliberately — there is no batch or automatic adopt, because auto-adopting
would record engine confidence in bytes the engine never saw.

Substitute these placeholders. Every one of them occurs in some template, and
no template carries any other. `materialize --stage scaffold` substitutes
`{{PKG}}` and `{{SEED}}` itself; every other token is left standing on
purpose, and refuses `STAGE_CANNOT_ANSWER` if a scaffold-stage `.py`
destination still fails to parse after that substitution.

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

### `--shards` — the refusal a split campaign needs

A campaign divided across machines comes back as a directory of shards, one
subdirectory each, every one holding its own `shard.json` stamp. Hand `verify`
that directory and it checks what the declaration said had to be identical:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py verify \
  --target implementations/<repo> --name <Name> --shards <Name>/Results/shards
```

```json
{ "distribution": { "status": "incomplete",
                    "shardsDisagree": ["epochs"],
                    "shardsArrived": ["shard-00", "shard-01"] } }
```

`shardsDisagree` names the fields, not the shards, because the field is what
the declaration promised and the shards are where the promise broke.
`shardsArrived` is read off the disk every time, so three shards planned and two
returned reports two — a smaller campaign, not a failed one.

Omit the flag and both are empty. That means nothing was checked, not that
nothing was wrong, and the difference is the whole reason the flag exists. A
shard directory that is not there yet reports nothing arrived; a `shard.json`
that is not JSON raises, because an unreadable shard is not a shard that never
came back and must not be quietly counted as one.

`verify` never averages or pools what it read. Merging what may legitimately be
merged is the target's own work, in its own harness — see `SKILL.md` for why
that division is deliberate.

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

### `compose` — the remedy takes the entry's place

A deliberation replaces a whole entry, and an entry is almost always more than
the equation at issue. `compose` substitutes the remedy inside the resolved
entry's own text rather than handing back the bare block, so every neighbouring
line the entry carries survives:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py compose \
  --target implementations/<repo> --finding <finding-id> --entry-text -
```

`--entry-text -` reads the entry from stdin, which is what you want for anything
longer than a line. The finding's own `remedy_block` supplies the replacement,
and the equation's `\tag{n}` is the identity used to find what it replaces — so
the substitution lands on the equation the finding names and not on whatever
happens to look similar.

Refusals are named rather than silent: `NO_SUCH_FINDING`, `NO_REMEDY_BLOCK` for a
finding whose correction was never written, and `EMPTY_ENTRY`.

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

Nine more are reported and none of them is a finding, which is exactly why
they were easy to leave undocumented:

- **`coupling`** — which notebook cells reach into the target's internals instead
  of going through its declared surface. It **never gates**: it is a static
  reading, and a cell that reaches inside is sometimes the right thing to have
  written. Read it before deciding a notebook is portable, and do not treat a
  non-empty result as a defect to fix on sight.
- **`lfs`** — which large files under the target are real content and which are
  still unfetched pointers. A pointer is not a missing file and not a broken
  one; it is a file nobody has paid to download yet. Read it when a run reports
  data it cannot open, because that is what it usually is.
- **`position`** — the execution sequence's derived state, read from
  `<Name>/AGREED.md`'s own position section. Every mark is measured, never
  asserted: `sequence` lists each step's disk mark beside what the evidence
  actually says, `disagreements` names a mark contradicted by measurement, and
  `unmeasured` names a witness this invocation could not check at all (most
  commonly `@shard` without `--shards`). It **never gates** — read it before
  telling a human a step is done.
- **`agreements.witness`** — a nested reading of every checklist item's
  optional trailing `` `test_<id>` `` token (`settle --witness` is the only
  command that ever writes one). Three states, never collapsed into one
  another: `unwitnessed` (the line carries no token — a state, not a
  failure), `unmeasured` (a token is declared but this run could not, or
  would not, call it a contradiction — this CLI never executes a suite, so
  even a token whose function name *is* found among `test_<id>` functions
  stays `unmeasured`, never "proven"), and `disagrees` (declared, `tests/`
  is readable and fully parsed, the item is ticked, and the declared
  function is absent). `summary` prints `"N of M witnessed"` on every run,
  including a target with zero declared tokens (`"0 of 0 witnessed"`) —
  silence never stands in for "nothing is declared". It **never gates
  here** — `close` is the one place `disagrees` refuses
  (`AGREEMENT_DISAGREES`); `verify` and `probe` only ever report it.
- **`toDiscuss`** — one directly runnable, `shlex.quote`-escaped `discuss`
  command per `audit.localRemediesNotWritten` finding id, asking whether
  that finding's local remedy is written now or deliberately deferred (and
  why). Question text derives from the finding id alone, never a count or
  anything else that could vary between calls while the same finding stays
  unwritten — run it verbatim, or run `discuss` by hand. Never published
  for `prose.staleRevisions`/`unresolvedSymbols` (unbounded per call, and
  the engine already declines to judge them) or `agreements.witness.
  unwitnessed` (a legitimate resting state, not an open question). It
  **never gates** — publishing the command lowers the friction to ask; it
  does not prove whoever answers it is the operator.
- **`undeclaredOptional`** — every optional key a DECLARED `search` or
  `distribution` block left unanswered: `search.record`,
  `search.currentWhen`, `distribution.currentWhen`,
  `distribution.shardsRoot`. Each entry names
  its `section`, `field` and the exact `consequence` its absence carries —
  e.g. without `search.record` nothing was ever told which artefact the
  search writes, so `recordFound` answers `null` on every run and `probe`
  keeps answering `search-first`; without `search.currentWhen`, a found
  record is trusted on the
  strength of being present, never checked against the code that produced
  it. **Reported, never demanded**: a target with no search, or no split
  run, is asked nothing here either — the same restraint every other
  optional field in this file already keeps. It **never gates** — an
  unanswered optional field is a legitimate resting state, not a defect;
  this only makes the option visible.
- **`undeclaredLadder`** — the ordered rung ladder `__levels__` names, in
  the case where it names none: `declaration`, the `path` of the file that
  would carry it, and the exact `consequence` of leaving it empty. That
  consequence is the point, so it is spelled out rather than named:
  `POSITION_RUNG_SKIPPED` — the refusal that stops a pass sealing at a rung
  whose predecessor the evidence has not reached — can never fire against an
  empty ladder; `position.attainedLevel` stays `null` on every run, because
  there is no rung name to answer with; every sequence item stays two-state,
  since a `:level`-marked witness is refused outright
  (`POSITION_LEVELS_UNDECLARED`), so a step that got part of the way has no
  rung to be recorded at; and `--target-level` accepts any word, because
  `POSITION_TARGET_LEVEL_UNKNOWN` compares against a declared vocabulary and
  there is none. `null` when a ladder is declared, and `null` for a target
  with no benchmark package to declare one in — `structure.scaffoldGaps`
  already names that missing file. **Reported, never demanded**: a
  repository whose steps are all two-state legitimately has no ladder, and
  the forge never invents a rung name on its behalf. It **never gates**.
- **`unreachableLadder`** — the other half of the same declaration, and the
  one `undeclaredLadder` cannot reach: a ladder that WAS named, long enough
  that the sequence beside it can never climb to the launch floor. It carries
  `levels` (the ladder as declared), `requiredLevel` (the rung
  `launch_available` floors a launch at, `levels[-2]`), `highestAttainable`
  (the highest rung every leveled item in the sequence could EVER grade
  satisfied at), `cappedBy` (the ordinals and witnesses holding it there) and
  the `consequence`. It fires only when the second sits strictly below the
  first — from four declared rungs up, with one leveled `@rehearsal` item
  anywhere in the sequence: `smokeReady` is two-valued, so that item can never
  prove more than the floor plus one rung, and `position.attainedLevel` is the
  highest rung at which *every* leveled item grades satisfied. `gate` then
  answers `RUNG_NOT_ATTAINED` on every call, naming a rung nothing that can
  run will reach. Two exits, both the target's own: declare at most three
  rungs, or drop the `:level` marker from that item and record it two-state
  (the grammar's default). The forge takes neither on its own — a launch floor
  that moved with whatever the sequence happens to hold would let *adding* a
  leveled item quietly *lower* the threshold for every item beside it. `null`
  when the ladder and the sequence can meet, and `null` below two rungs, where
  the rung threshold does not apply at all. It **never gates**.
- **`unfinishableFlow`** — an ordered flow the target cannot walk to the end
  of below its own declared scale, said before the first step runs. It carries
  `requiredScale` (the scale the search declares for itself, which is what
  decides), `blockedBy` (every sequence item a run below that scale can never
  tick), `blockedSteps` (every declared step that must wait behind the earliest
  of them) and the `consequence`. The pair that makes an item unsatisfiable is
  two-state **and** graded against a declared scale, never two-state alone: a
  two-state `@notebook` item is satisfied by a notebook executed against these
  sources and ticks fine at pilot, while a two-state `@record` item is graded on
  `search.scaleSatisfied` and derives `false` until the full scale is reached —
  with no rung for a smaller run to earn partial credit at. `step` then refuses
  `STEP_SEQUENCE_NOT_REACHED` for every step above it, on every call, while
  `pilotCompleteness` asks for that same flow to finish at pilot. The exit is
  the target's own and is already built: mark that item leveled and give it a
  named witness, `@record:level <name>`, backed by one `__records__` entry per
  record the flow actually produces, each with its own `path` and its own
  `requiredScale` — a named entry is graded against ITS own scale, so the
  record a smaller run leaves behind reaches a rung a smaller pass can be
  sealed at while the entry declaring the full scale still reaches the top.
  `null` when the search declares no scale, when no item is graded against one,
  and when no step waits behind such an item. It **never gates** — the refusal
  it reports ahead of is unchanged, and nobody is let through any earlier.

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

## `position` — refresh and install the execution sequence

`verify`/`probe` only ever *read* the position section (above). `position` is
the one command that writes it — `settle` (below) is the other writer into
`<Name>/AGREED.md`, and the two never touch the same lines: `position` only
ever rewrites the marks of its own delimited block, `settle` only ever inserts
one plain checklist line outside it. No flag: re-derive the marks of whatever
block is already there, touching nothing else about it — not the item text,
not the order, not which witness each one names.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py position \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id>
```

```json
{ "status": "written", "holder": "Method/AGREED.md",
  "wrote": [2], "left": [1], "unmeasured": [3],
  "sequence": [ "..." ] }
```

`status` is `"written"` only when something actually moved — a mark flipped, or
the header rebound to a different revision. Nothing to flip and nothing to
rebind reports `"unchanged"` and touches neither the file nor the ledger:
writing a fresh timestamp over marks nobody re-measured would claim work that
did not happen. `"absent"` means there is no block yet — install one first.

`--shards <dir>` measures every `@shard` witness against that directory,
whichever write mode this call uses — a bare refresh included. Without it,
`@shard` reads `unmeasured` (never `False`): the shard may well have
arrived, this invocation simply was not told where to look.

### `--target-level` — the rung this pass is aiming at

Every write mode also takes `--target-level <level>`, the header field a
mark is now measured against: a witness's mark means "reached the level
this pass asks for", not a bare pass/fail, unless the witness is two-state
(see below). `<level>` must be one of the target's own `__levels__`, a
second top-level literal declared next to `__benchmark__` in the benchmark
package's `__init__.py` (or `config.py`) — an ordered list, entirely in the
target's own words, e.g. `__levels__ = ["local", "cluster"]`. Required only
for a fresh header with nothing to inherit one from; a bare refresh reuses
whatever the existing block already recorded when `--target-level` is
omitted, the same way it never asks a caller to retype item text nobody
changed. Refuses `POSITION_TARGET_LEVEL_REQUIRED` (fresh header, nothing
given or to inherit), `POSITION_TARGET_LEVEL_UNKNOWN` (the value named is
not one of `__levels__`'s own entries), and `POSITION_LEVELS_UNDECLARED` (a
leveled witness exists in the sequence but `__levels__` declares no
ladder).

#### A rung is never skipped going forward

Naming a declared rung is not the same as being allowed to reach it. **To
seal at rung N, every leveled item in the sequence must already grade as
satisfied at rung N-1** — otherwise `POSITION_RUNG_SKIPPED`, a work state
whose published `resolve` names the rung this target *can* seal next and
asks what has to run before the one above it can be claimed. The rung whose
whole purpose is proving the flow runs before anything is spent further up
is exactly the rung a jump would skip.

The check reads the **evidence**, never the ledger. "Was there a prior pass
at the rung below" would be the obvious rule and is deliberately not the
one: a target that has never run this command has no `position.jsonl` at
all, so a history check would pass vacuously on precisely the repositories
it exists to stop. Instead the sequence is re-graded by
`impl_position.derive` itself at the previous rung, so "satisfied at rung
N-1" means here exactly what it means when a mark is written.

**The header states an aim, not an attainment.** `target=` is the rung a
pass is *aiming at*, and an aim legitimately sits one rung above what has
been reached — otherwise no pass could ever climb. So the rule is put to
the evidence and never to that field: `attained_level` answers *which rung
the evidence currently reaches* (the highest rung at which every leveled
item grades satisfied), and an aim may reach at most one rung above it.
Where a pass came from is not consulted at all — a retreat and a re-seal
land on rung N and assert that N-1 is reached exactly as a climb to N
does.

That separation is also published: `position`'s state carries
`attainedLevel` beside `targetLevel`, so the gap between what a pass aims
at and what backs it can be read without tripping a refusal to find it.

Three boundaries, each of them decided rather than fallen into:

- **The first rung has no predecessor.** Sealing at `__levels__[0]` is
  always possible, including on a repository with no evidence whatsoever —
  a ladder needs a bottom step or nothing can ever start. This is also what
  keeps an operator from ever being cornered: `position` is the instrument
  that measures, and an instrument that refuses to take a reading because
  the reading is bad hides the regression it exists to report. When
  evidence collapses, the floor is still sealable, demoting the header to
  it is the honest reading, and the refusal that sends an operator there
  names every item that came up short.
- **Two-state items do not participate.** Their verdict is computed without
  the ladder and is identical at every rung, so they say nothing about
  which rung was reached. Folding them in would refuse a legitimate advance
  because some unrelated boolean step is still open. Their own ordering is
  already held, within a rung, by `SEQUENCE_NOT_REACHED`.
- **Unmeasured is not attained.** A leveled item nobody could measure does
  not satisfy the rung below, because "we did not look" is not "it has been
  reached". This is also what separates the rule from a cheaper one that
  merely counts ladder positions: even a single-step advance is refused
  when the step below it is not *shown* attained.

A target that declares no `__levels__` at all is entirely unaffected: no
ladder, no rungs, no progression to enforce. Unaffected is not the same as
unremarked — nothing here ever asks a target for a ladder, so `verify`
reports the absence and what it costs under `undeclaredLadder` above, and
leaves the decision where it belongs.

Each witness in the block's markdown may carry `:level` right after its
kind — `` `@rehearsal:level governing-search` `` — to opt into being
measured against the declared ladder instead of a plain pass/fail. Omitted
(the default, unchanged from before this mechanism existed), a witness is
**two-state**: satisfied or not, with no rung ever assigned to it — a step
that only ever holds or does not (a local check with nothing in between)
declares itself this way and is never assigned a level string, no matter
how the evidence underneath it reads.

`--sequence -` installs a fresh section instead of refreshing one, reading an
ordered JSON array of `{text, witness: {kind, operand, twostate}}` from
stdin — `witness.twostate` defaults to `true` when omitted, the same
default the markdown grammar itself keeps:

```bash
echo '[{"text": "Search for the governing value.",
        "witness": {"kind": "record"}},
       {"text": "Rehearse the campaign job.",
        "witness": {"kind": "rehearsal", "operand": "governing-search",
                    "twostate": false}}]' \
  | python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py position \
      --target implementations/<repo> --name <Name> \
      --revision research-concept-r05.md --session <your-session-id> \
      --target-level local --sequence -
```

Every declared item is validated by the same grammar that reads a hand-authored
block — a malformed witness is refused here, not left to surface at the next
`verify`. Installing over a block that already exists refuses
`POSITION_BLOCK_EXISTS` unless `--replace` is also given.

The holder is found by shape, never by a fixed filename — the same rule
`agreements_state` already applies. Refuses `POSITION_HOLDER_ABSENT` when no
markdown file in the product folder holds anything to append into, and
`POSITION_HOLDER_AMBIGUOUS` when more than one candidate exists and none is
decidable without a human choosing. A malformed existing block —  no witness,
an unknown witness kind, or more than one `<!-- position -->` opener — refuses
with `POSITION_ITEM_WITHOUT_WITNESS`, `POSITION_WITNESS_UNKNOWN_KIND`,
`POSITION_ITEM_MALFORMED`, `POSITION_BLOCK_MALFORMED` or
`POSITION_BLOCK_NOT_UNIQUE`: the same class `MALFORMED_FINDINGS` already is
for `read_findings`, a broken artifact rather than a not-yet-ready target.

### `--reconcile` — reconstruction from what the target already has

For a target that already has notebooks, job folders and a declared search
but no position section yet:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py position \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --target-level local --reconcile
```

Builds one `@record` from the benchmark's declared search, one `@rehearsal`
per discovered job folder, one `@notebook` per `Notebooks/*.ipynb` in name
order, and — with `--shards` also given — one `@shard` per arrived shard,
each measured `True` against that same directory in the same call, not left
`unmeasured` until some later invocation happens to pass `--shards` too.
Every discovered witness is two-state — reconciliation discovers that a
step exists, never what a human means by it, and only a human editing
`AGREED.md` to add `:level` afterward can say a step has rungs at all.
Existing items are matched by witness identity (kind and operand) and keep
their text and their order exactly; only a witness with no match is
appended, its text a placeholder for a human to write over. Safe to run
again: an unchanged target appends nothing and reports `"unchanged"`.
`--sequence` and `--reconcile` together refuse `POSITION_SEQUENCE_AND_RECONCILE`
— only one of the two may name this call's sequence. `--target-level` is
required here too only for a fresh header; a `--reconcile` that merges into
an existing block reuses its recorded target when omitted.

## `discuss` — a question with a return value

Replaces telling the agent, in prose, to name a collision with an existing
agreement and wait: `discuss` makes "I asked" a fact with a ledger line
instead. It never gates — an unanswered question is a reported `status`,
not a refusal.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py discuss \
  --target implementations/<repo> --name <Name> \
  --about "rehearsal governing-search" \
  --question "Should this job rehearse before the campaign?"
```

```json
{ "status": "open", "about": {"ordinal": null, "kind": "rehearsal",
                              "operand": "governing-search"},
  "measured": null, "collides": [], "collisionSearch": "performed",
  "asked": "Should this job rehearse...", "answered": null }
```

`--about` names the step either by its ordinal in the current position
sequence, or by a bare witness spec (`"kind"` or `"kind operand"`) when
there is no sequence item yet to number — for `notebook`/`rehearsal`/`shard`
the operand is required (`DISCUSS_ABOUT_OPERAND_REQUIRED` refuses a bare
`--about notebook` with none); `record` is the one witness kind that keeps
accepting none. `--answer` (optionally `-` to read stdin, like `--question`)
moves `status` from `"open"` to `"answered"`; at most one of
`--question`/`--answer` may read stdin in the same call. `collides` is
computed fresh against every checklist item in the product folder's
markdown that names the same operand — never remembered from an earlier
call, and never against the position section's own item lines, which are
excluded from the search along with the rest of the block. `collisionSearch`
distinguishes the two ways `collides` can read `[]`: `"performed"` when the
witness carried an operand to search with, `"unperformed"` for the one kind
(`record`) that never does — an empty list alone cannot tell "searched, found
nothing" apart from "could not search at all".

## `settle` — place what `discuss` answered

Once a `discuss` question is answered, `settle` performs the actual write —
the agent drafts the question and the proposed sentence, `settle` validates,
refuses, and writes. It never authors the text and never ticks the box: the
mark placed is always `[ ]`, and the text placed is `--text`, verbatim.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --about "notebook Notebooks/verification.ipynb" \
  --text "the free scalar stays at its neutral and identical across arms" \
  --under "## Ladder"
```

```json
{ "status": "written", "holder": "Method/AGREED.md",
  "about": {"ordinal": null, "kind": "notebook",
           "operand": "Notebooks/verification.ipynb", "twostate": true},
  "text": "the free scalar stays at its neutral and identical across arms",
  "under": "## Ladder", "supersedes": null, "collides": [] }
```

`--about` takes the identical shape `discuss`'s own `--about` does (an ordinal
or a bare witness spec), matched against the ledger by witness identity
`(kind, operand)` — ANY answered `discuss` event for that identity satisfies
this, never newest-wins, so a later open clarifying question never erases an
earlier answer. Refuses `SETTLE_NOT_DISCUSSED` when no `discuss` event names
it at all, `SETTLE_DISCUSSION_UNANSWERED` when one does but none is answered.

`--under` is matched by exact equality against a heading line, hash marks
included — `## Figures` never matches `## Figures — phase 2` — and the item
is inserted at the first non-blank line after it, so the document's own
`heading / blank / bullets` shape survives untouched. Refuses
`SETTLE_HEADING_ABSENT` or `SETTLE_HEADING_AMBIGUOUS` when it occurs zero, or
more than one, times across every markdown file `agreements_state` already
knows holds checklist items; `SETTLE_HOLDER_ABSENT` when none does at all.

On a collision — the same collision search `discuss` already reports — name
the existing item this placement supersedes with `--supersedes "<exact
text>"`, or `settle` refuses `SETTLE_COLLIDES_UNNAMED`. The refusal names
every colliding text verbatim, never a bare count ("2 existing
agreement(s)"), and also prints one directly runnable, `shlex.quote`-escaped
`discuss` command asking which one, if any, this placement supersedes — the
same identity-derived, `discuss --answer` retirement discipline
`DISCUSSION_UNANSWERED` uses. `--supersedes` must exact-match a member of the
computed collision list (`SETTLE_SUPERSEDES_UNKNOWN` otherwise) and is
recorded in the ledger event only: the document itself still needs a
human-written `Reversed` paragraph to show a supersession actually happened.
`--text -` and `--supersedes -` cannot both read stdin in one call
(`SETTLE_STDIN_CONFLICT`).

### `--witness` — binding this agreement to a test, at write time

Optional `--witness test_<id>` names this agreement's own function in the
declared-invariants suite — a separate identity from `--about`, which names
the *position* witness this placement discussed. Given, it is persisted
verbatim into the written line as a trailing `` `test_<id>` `` token;
omitted, the line is byte-identical to the pre-witness grammar, exactly as
it always was. Refused `SETTLE_WITNESS_MALFORMED` if given and it does not
match `test_[A-Za-z0-9_]+` — a malformed value would otherwise round-trip
as inert trailing text, never as a witness `agreements_state` could read
back.

**`settle` is the only command that ever writes this token.** There is no
`patch` or `edit` subcommand, by design (spec Group 5): a witness token is
bound either at the moment an agreement is placed (`--witness`, above) or,
with `--attach` (below), afterward — both routes stay inside this one
command; there is still no third way in. Hand-typing one into `AGREED.md`
is unsupported doctrine, not a technical prevention — the parser cannot,
and does not try to, distinguish a skill-written token from a hand-typed
one, so `verify` and `close` evaluate either exactly the same way.

### `--attach` — binding a witness to a line already settled

`--text` only ever CREATES with the shape above; there was no way to bind
`--witness` onto an agreement a prior `settle` call already placed, ticked
or not, without either hand-editing `AGREED.md` (unsupported) or
re-`settle`ing it (which would write a fresh `[ ]` line and un-tick
whatever was already reached). `--attach` closes that gap:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --attach \
  --text "the free scalar stays at its neutral and identical across arms" \
  --witness test_the_free_scalar_stays_neutral
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "attach": true,
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": "test_the_free_scalar_stays_neutral",
  "supersedes": null, "collides": [] }
```

`--text` is matched by EXACT equality against an existing line's own
`AGREEMENT_LINE` text group — the identical "found by shape, matched
exactly" discipline `--under` already uses for a heading. Refuses
`SETTLE_TEXT_ABSENT` when it matches no existing line, `SETTLE_TEXT_AMBIGUOUS`
when it matches more than one — which one receives the witness is not
decidable without a human choosing, the same reasoning
`SETTLE_HEADING_AMBIGUOUS` already states one level up. `--witness` is
required in this mode (`SETTLE_WITNESS_REQUIRED` if omitted — binding one
is the entire point) and refused `SETTLE_ALREADY_WITNESSED` if the located
line already carries a token: `--attach` never replaces one, only adds.

**The mark is never touched.** A ticked item stays ticked, an open one
stays open — only the witness token is appended, and everything else in
the holder file is byte-identical afterward. `--under` and `--supersedes`
name nothing in this mode and are refused `SETTLE_ATTACH_CONFLICT` if
given together with `--attach`.

**The discussion precondition is skipped, on purpose.** `SETTLE_NOT_DISCUSSED`
/ `SETTLE_DISCUSSION_UNANSWERED` exist so nothing is PLACED without having
been discussed first. A line `--attach` matches was, by construction,
already placed by an earlier `settle` call — it already passed that gate
once. Binding a witness onto it afterward is not placing a new agreement;
requiring a fresh `discuss` per already-settled line would be ceremony
with nothing behind it. `--about` is not even resolved in this mode, since
there is no discussion gate left to check it against.

**This is the mechanism, not the retrofit.** Running `--attach` over every
already-settled line in a target is a separate, bounded, operator-directed
pass — never something a flow does incrementally as it happens to
encounter an unwired agreement.

### `--remove` — the eraser, guarded by the record itself

`--text` only ever CREATES, and `--attach` only ever binds a witness onto
a line that stays exactly where it was. Neither ever deletes one. Moving
an agreement between sections, or dropping one the target has genuinely
outgrown, had no supported path at all — either a hand edit
(unsupported) or leaving a retired line sitting under a heading it no
longer belongs to. `--remove` closes that gap by deleting the located
line's own bytes outright, including its trailing newline, and touching
no other byte in the document:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --remove \
  --text "the free scalar stays at its neutral and identical across arms"
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "remove": true,
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": null,
  "supersedes": null, "collides": [] }
```

`--text` is matched by the identical exact-equality discipline `--attach`
already uses. Refuses `SETTLE_TEXT_ABSENT` / `SETTLE_TEXT_AMBIGUOUS` the
same way.

**The guard: nothing is deleted before it is explained.** This is the
single most destructive write this command can make — unlike `--attach`
(adds a token) or the create path (adds a line), nothing `--remove`
deletes is recoverable from anything `settle` itself ever wrote. The
guard is inherited from the document's own stated convention: the `##
Reversed` section's own preamble already says, in prose, "Written rather
than deleted: an agreement that was turned over is part of the record,
and removing it would lose exactly what this file exists to keep."
`--remove` therefore refuses `SETTLE_NOT_REVERSED` unless the EXACT text
it would delete is already quoted, bold, under a `## Reversed` heading
somewhere in the same holder file the line itself lives in — a full quote
or one truncated with a trailing ellipsis (`...`/`…`) whose visible
prefix exactly matches `--text`'s own opening words. This forces the
write that explains WHY an agreement was turned over to exist BEFORE the
write that erases it can happen. `--remove` never authors that
explanation itself — write it by hand, or with `--reverse` (below), which
writes both in one call.

**Conflicts.** `--under`, `--supersedes` and `--witness` name nothing in
this mode (there is no new item to place, and no witness to bind onto a
line being deleted) and are refused `SETTLE_REMOVE_CONFLICT` if given
together with `--remove`, so a flag the caller bothered to type is never
silently ignored.

### `--reverse` — writing the explanation and the deletion in one call

`--remove` shipped guarded by `SETTLE_NOT_REVERSED`, correctly — but
measured after shipping it, nothing could ever satisfy that guard except
a hand edit: `settle` places `- [ ] {text}` checklist bullets, and a `##
Reversed` entry is bold-quoted prose in a different shape, so no existing
command could write one. `--reverse` closes that gap by writing the `##
Reversed` entry and performing the deletion in the SAME call:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --reverse \
  --text "the free scalar stays at its neutral and identical across arms" \
  --paragraph "Reversed because the underlying measurement changed."
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "reverse": true,
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": null,
  "paragraph": "Reversed because the underlying measurement changed.",
  "supersedes": null, "collides": [] }
```

**The guard that makes it safe: it refuses without an explanation.** The
engine never authors the reasoning behind a reversal — that is a human's
call, not a computed fact. `--paragraph` is therefore required
(`SETTLE_PARAGRAPH_REQUIRED` if blank or omitted): an `--reverse` call
carrying no paragraph has nothing to explain with, and this mode's entire
point is writing that explanation down.

**One transaction, never two separate writes.** Both the new `##
Reversed` entry and the deleted checklist line are folded into ONE
spliced buffer, computed from the same pre-image bytes, before the single
shared compare-and-swap write at the bottom of this command ever runs.
There is no intermediate state where one edit has landed and the other
has not — both land in the one written file, or the write itself refuses
(`POSITION_HOLDER_MOVED`, the holder changed underneath it) and NEITHER
does. The entry is appended last, immediately before the section's own
position block when one exists, or at the section's own end otherwise —
never first, since a reversal explains something that just happened.

Refuses `SETTLE_ALREADY_REVERSED` if the exact text is already quoted
under `## Reversed` — this mode writes a NEW explanation together with
the deletion, and would duplicate one the document already has. In that
state the explanation already exists and only the deletion is still
pending; plain `--remove` (above) is the reachable command for exactly
that case. Refuses `SETTLE_HEADING_ABSENT` when no `## Reversed` heading
exists in the holder at all — this mode places its entry under an
existing section and never authors one, the identical restraint the
create path's own `--under` already keeps for a heading it is given —
and `SETTLE_HEADING_AMBIGUOUS` when more than one `## Reversed` heading
occurs in the same holder.

**Conflicts.** `--under`, `--supersedes` and `--witness` name nothing in
this mode (the identical reasoning `--remove`'s own conflict already
gives) and are refused `SETTLE_REVERSE_CONFLICT` if given together with
`--reverse`; giving `--paragraph` in any OTHER mode is refused the same
way, since that flag feeds an entry only `--reverse` ever writes.

### `--done` — the tick this class closes

`--remove` and `--reverse` are *compositions* of verbs this file already
had: editing an agreement's text is `--reverse` (which explains why)
followed by a fresh placement; moving one between sections is `--remove`
(once explained) followed by placement under the new heading.
Ticking one had no composition at all — nothing either of those two could
do, alone or chained, ever changed a mark from `[ ]` to `[x]`. Every ticked
agreement a real target carries was typed by hand. `--done` closes that
gap:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py settle \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --done \
  --text "the free scalar stays at its neutral and identical across arms"
```

```json
{ "status": "written", "holder": "Method/AGREED.md", "done": true,
  "about": null, "text": "the free scalar stays at its neutral and identical across arms",
  "under": null, "witness": "test_the_free_scalar_stays_neutral",
  "supersedes": null, "collides": [] }
```

`--text` is matched by the identical exact-equality discipline `--attach`
already uses. Refuses `SETTLE_TEXT_ABSENT` / `SETTLE_TEXT_AMBIGUOUS` the
same way.

**The guard: a tick must rest on a witness.** Refused `SETTLE_NOT_WITNESSED`
unless the located line already carries a `` `test_<id>` `` token — bind
one first with `--attach`. A tick asserts the work is done; a line nobody
can point a test at cannot assert that through this command. This is
decided, not merely present: a real target carries agreements ticked with
no witness at all — irreducible arguments no test could ever measure — and
this guard leaves those permanently unreachable through `--done`, on
purpose. An unwitnessed line already reports `unwitnessed` in
`agreements_state`, a state this file treats as legitimate; a human may
still tick one by hand, the same "unsupported, never technically
prevented" doctrine that already covers a hand-typed `--witness` token.
Refused `SETTLE_ALREADY_DONE` if the located mark is already `x`/`X` —
`--done` never re-ticks an already-ticked line.

**Only the mark moves.** `--text`, any witness token the line already
carries, and every other byte in the holder file are byte-identical
afterward — the single byte inside the checklist mark's own brackets is
the only thing this writes. `--under`, `--supersedes`, `--witness` and
`--paragraph` do not apply with `--done` and are refused
`SETTLE_DONE_CONFLICT` if given, and so are `--attach`, `--remove` and
`--reverse` themselves. The discussion precondition is skipped for the
identical reason `--attach` skips it: a line `--done` matches was already
discussed and placed by a prior `settle` call.

**Un-ticking is deliberately out of scope.** `--done` closes a measured
gap — no composition of the other modes could ever produce a tick.
Retracting one is a different kind of assertion (a prior claim was wrong,
not that a fact came true) and would need its own guard, designed on its
own terms; nothing measured against a real target found a mistakenly
ticked agreement this command needed to correct. A human may still
un-tick a line by hand today, the same doctrine that already covers every
other hand edit this file does not itself perform.

## `defect` — declare a forge file broken

Records that some file this forge itself ships is currently wrong — a bug in
`implementation_cli.py`, a stale claim in `SKILL.md`, anything under
`.claude/skills/`. While it stays open, `step`, `gate`, `offer`, `close`,
`settle`, `apply` and `admit` all refuse `FORGE_DEFECT_OPEN` for this exact
`<target>/<name>`; `probe`, `verify`, `position`, `plan`, `compose`,
`handoff` and `discuss` stay reachable throughout. `main()` also appends this
same kind of event on its own, with no `defect` call at all, the moment any
OTHER exception reaches it while dispatching a command — see SKILL.md's
"When the forge itself crashes mid-flow".

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py defect \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --file .claude/skills/proposal-implementation/scripts/implementation_cli.py \
  --detail "cmd_step ignores STEP_MALFORMED for an entry missing 'function'"
```

```json
{ "command": "defect", "target": "<repo>", "name": "<Name>",
  "file": ".claude/skills/proposal-implementation/scripts/implementation_cli.py",
  "fileSha256": "<64-char hex>", "session": "<your-session-id>",
  "at": "2026-08-27T00:00:00Z",
  "detail": "cmd_step ignores STEP_MALFORMED for an entry missing 'function'" }
```

`--file` must resolve under `FORGE_ROOT/.claude/skills/`; a path outside that
tree refuses `DEFECT_FILE_NOT_FORGE_OWNED`, checked BEFORE existence, so this
command never reports on the existence of anything outside it. A path that
does not resolve to a regular file refuses `DEFECT_FILE_ABSENT` — declaring
against an already-absent path is refused rather than recorded, because the
honest reading of a `--file` nobody can find is a typo, not a forge bug; the
genuine case ("this module is missing") is declarable against the file that
fails to find it, which exists. `--detail` is optional free text and is
omitted from the ledger event entirely, never written as `null`, when not
given. Clearing happens the moment the named file's bytes change — editing
it, even to fix the exact thing declared, clears the defect; asserting the
fix in a fresh `--detail` on unchanged bytes does not. Deleting the file
after the declaration clears it too, on the same rule: an absent file can
never again match the recorded digest, so absence is treated as the
strongest possible change, not a bypass that needs closing.

## Probe — what stands between this repository and a benchmark

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py probe \
  --target implementations/<repo> --name <Name> --revision research-concept-r05.md
```

`--revision` is optional here for the same reason it is optional on `verify`:
omit it and the newest published revision of the family the bench declares is
discovered. Everything else is required.

```json
{ "status": "ok", "nextStep": "benchmark", "comparable": true,
  "backend": { "trainable": true },
  "results": { "status": "absent" },
  "remoteExecution": { "status": "absent", "jobs": [], "services": 0,
                       "smokeReady": {} },
  "kind": "read-only" }
```

`probe` runs nothing and changes nothing — `kind` says so in the output itself,
and the exit status is `0` whatever it finds. `nextStep` is the answer and there
is exactly one of them: the ladder is ordered, so the first thing standing in
the way is the only thing reported. Eleven values are possible. Eight prescribe
work and each has its own section in `SKILL.md` — `convert`, `declare-first`,
`env-first`, `wiring-first`, `poll-first`, `search-first`, `report-first` and
`benchmark`. The other three have no section: `nothing-to-compare` and
`already-benchmarked` prescribe no work at all, and `piloted`'s own rule keeps
its question open rather than handing over a list of steps.

**Prescribing no section is not the same as publishing nothing.** Nine of the
eleven publish `resolve` (below); only the two that name no work at all —
`nothing-to-compare` and `already-benchmarked` — publish `null`, and they say so
in `PROBE_NEXT_STEPS` rather than by omission.

Never read past the answer for a reason to skip it. A rung fires because
everything above it is already settled, so the next one down says nothing about
whether the campaign is a good idea yet.

## The remote-execution seam

The commands that send work to a worker belong to the forge's
`remote-execution` skill, not to this one: `probe` and `verify` read the ledger
and the job folders, and never submit, poll or repair anything. But a reader
told to wait, or told a ledger has drifted, needs a name to type. Three
invocations, in the shape this flow reaches them:

```bash
# a submission is out and its answer has not come back — `nextStep: "poll-first"`
python3 .claude/skills/remote-execution/scripts/remote_cli.py poll \
  --submission-id <id> --backend <backend>

# the ledger and the service disagree — `remoteExecution` reporting drift or unreliable
python3 .claude/skills/remote-execution/scripts/remote_cli.py reconcile \
  --target implementations/<repo> --entrypoint <Name>/Notebooks/<notebook>.ipynb \
  --worker <worker> --backend <backend>

# there is no job folder for the campaign about to be offered
python3 .claude/skills/remote-execution/scripts/remote_cli.py generate-job \
  --target implementations/<repo> --service <service> --job-name <job> \
  --product <Name> --commit <sha> --repo-url <url> --repo-ref <ref> \
  --clone-path src --run-module <module> --run-function <function>
```

`generate-job` is what places `tools/<service>/<job-name>/`; nothing in this
skill scaffolds that directory, and there is no template for it here.

**The flags above are the shape, not the list.** Every one of these subcommands
takes more than is shown — overrides, rehearsal flags, resolution switches — and
they are documented once, in the `remote-execution` skill that owns them. A
second copy here would be a second thing to keep in step, which is the same
defect the tables in `SKILL.md` exist to prevent. `SKILL.md`'s own subcommand
table says which reported state routes to which command; this says how the three
a reader of this flow actually reaches are typed.

## Reading `probe`

`probe` looks and reports: it runs nothing, submits nothing, and never changes
the exit status. `nextStep` is the answer; everything else is what a human needs
in order to decide what to do about the answer.

Two facts about remote execution are reported beside that answer and gate
nothing, which is exactly what makes them easy to walk past:

- **`smokeReady`** — per job folder, whether a rehearsal has already passed on
  the commit that job is pinned to. `false` does not mean the job is broken; it
  means either that nothing has been rehearsed yet, or that the rehearsal on
  record was against a different commit. Read it before offering a long run: a
  rehearsal finds cheaply what the long run would find expensively. Recording one
  belongs to the `remote-execution` skill's own CLI — `probe` never submits.
- **`staleness`** — per job folder, inside `remoteExecution.jobs`. `fresh` means
  the pinned commit still matches the declared clone paths; `drift` means the
  repository has moved and the job would clone older code than the one on disk;
  `unknown` means the question could not be answered at all, because there is no
  git history or the pinned commit is not in it. `unreadable` is a fourth verdict
  and a different problem: that job's own `run-config.json` could not be parsed,
  so staleness was never attempted and a blank cell would have read as "nothing
  wrong".

Neither one is a rung on the ladder, and that is a position rather than an
oversight: the fact as computed cannot tell a repository that is not ready apart
from one that never sends work anywhere. `SKILL.md`'s Output Contract carries the
argument and states what would change it.

**`pilotCompleteness` is a rung, and two of them.** It answers whether the
ordered flow the target declared has actually finished at pilot: `status:
"undeclared"` when no `__steps__` entry carries an `advances` ordinal (the rule
does not apply, and the ladder answers what it always did), `"incomplete"` while
any step is short, `"complete"` once none is. `incomplete` names the steps still
short, in declared order — read that, not a count. Each row says why: `ran` is
the step's own ledger verdict (`null` is unmeasured, which includes a run
recorded against a suite that has since moved), `notebook` is the file its own
sequence item names, and `notebookCurrent` is whether that file is executed
against these sources. Existence is not evidence — a template copied into place
and an executed report look identical until the execution counts are read.

While it is `"incomplete"` the answer is `pilot-first` and the offer of the
declared scale is withheld: the outputs are what anybody reads to know the agreed
thing is there, and there are none yet. Once it is `"complete"` the answer is
`pilot-decisions` until every step has been decided — one `discuss` bucket per
step, asking how the full run carries it. Read `remoteExecution.necessity`
alongside those questions; it classifies job folders rather than steps, so it
informs the decisions and never makes them.

Two more fields are reported beside `nextStep`, and they are the answer to
"what do I do about it" — published by the engine rather than composed by
whoever reads the output:

- **`resolve`** — what this answer's work actually is. `{kind: "command",
  command}` where the flow can name the whole exit (`env-first` resolves to
  `implementation_cli.py env --target <t>`; run it unedited). `{kind:
  "question", question, command}` where the next act is a decision, in which
  case `command` is the runnable `discuss` invocation that opens it. `null`
  only at `nothing-to-compare` and `already-benchmarked`, the two answers
  `PROBE_NEXT_STEPS` declares terminal.

  **Wherever the flow reaches the point of running experiments, the question
  is the same one**: continue the flow toward the declared scale, or complement
  the experiments first. Three answers reach that point — `benchmark` (the
  offer to run), `piloted` (a run already made below the scale it declared)
  and `search-first` (a declared search that has chosen nothing yet, and a
  search is an experiment with a scale of its own). `search-first` used to
  publish nothing at all.

- **`toDiscuss`** — the question-shaped half of `resolve`, as a list, so a
  reader can treat every open question the same way whichever command reported
  it. Each entry is one directly runnable, `shlex.quote`-escaped `discuss`
  command. For `piloted` and `search-first` the question names the target/name
  pair and the DECLARED scale the protocol asks for — never the currently-
  achieved count, which climbs on every poll while the decision has not changed.
  Run it verbatim, or run `discuss` by hand. It **never gates** — the same
  non-goal as `verify`'s own `toDiscuss` above.

`wiring` is reported at two answers, not one: `benchmark`, where the draft is
the raw material the run offer is built from, and `wiring-first`, where an arm
declares mathematics it never calls and the draft is the very thing that state
is missing. It was guarded on `benchmark` alone, and because the `wiring-first`
override runs before that guard, the one answer naming missing wiring came back
with `wiring: null`.

## `propose` — the campaign proposal

Appends one `proposal` event to `.implementation/position.jsonl`, scoped to
a whole CAMPAIGN — matching `gate --unit`'s own campaign scope — never to a
single job. Names every job it covers, its intended workers, its dependency
edges (if any) and a human-authored rationale: the four facts the spec's
"One Proposal Per Campaign" requirement names.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py propose \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --job governing-search --job ablation-a \
  --worker worker-1 --worker worker-2 \
  --depends-on ablation-a:governing-search \
  --rationale "Full-scale campaign for the accepted research concept."
```

`--job` (repeatable, at least one) is the human-declared subset of currently
discovered job folders THIS proposal authorizes — checked later, at `gate`
time, for job membership. `--worker` (repeatable, at least one) is a
declared list of intended accounts, recorded as write-only history — read by
no code path in this file. `--depends-on <job>:<dependency>` (repeatable,
optional) names one ordering edge per flag. `--rationale` is required and
non-blank, refused `EMPTY_RATIONALE` otherwise — the same discipline `gate`'s
own `--justification` already keeps.

`campaign: {commit, jobSet}` is never argv: it is a live-disk snapshot —
every job folder `_discovered_job_folders()` currently finds, and the single
commit they all currently agree on (`null` when they disagree) — re-derived
identically at `gate` time to detect drift. This is deliberately a
DIFFERENT fact from `--job`'s declared subset: `jobSet` moves the moment ANY
job folder is added or removed, regardless of which jobs this particular
proposal named.

Multi-use by design — there is no consumed marker and no
`GATE_PROPOSAL_CONSUMED`. Calling `propose` again appends a fresh event
rather than editing or replacing the last one; a bound proposal survives a
same-campaign retry (a failed job's retry re-verifies against the same
proposal, no re-propose needed) because its own staleness keys (`commit`,
`jobSet`) are structurally distinct from the authorization's own seven
(never `entrypoint`, never `positionStatus`).

## `offer` — the state-derived action menu

The fifth ledger-appending command, named after its own event kind the same
way `position`/`discuss`/`gate`/`close`/`step` already are. Records the
flow-continuation answer as a closed token (never free text) and publishes a
closed action set: one `launch` per job the identical shared rule `gate`
itself reads (`impl_availability.launch_available`) already says is
available, plus `run-step` when the recorded answer is `yes` or
`expand-contract` when it is `no`. An unavailable action is omitted
entirely — never disabled with a reason attached — and the standing
explanation is still the position sequence and the Decision Gates table, not
a per-action string.

`expand-contract`'s published `command` is a `discuss --about record
--question <text>` invocation, not a write: it carries no `--session`
(`discuss` is the one write-adjacent command that registers none), and
running it verbatim only appends a `discuss` event to
`.implementation/position.jsonl` — `AGREED.md` is never touched. This
repoints what used to publish `position --reconcile` on the same branch, a
write an agent could run believing itself still inside the "what should the
contract still add" conversation this branch is meant to open.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py offer \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --answer yes
```

`--answer` is required on EVERY call — never read back from a prior `offer`
event, no matter how many exist or what they contain. `OFFER_UNANSWERED`
refuses whenever `--answer` is omitted, checked first, before the revision
is even read; the refusal is identical whether the target's ledger holds no
`offer` event, one, or many. A supplied answer is always honored and always
appends a new event — it is never compared against, or deduplicated against,
any prior `offer` event's answer. Refuses `OFFER_ANSWER_NOT_A_TOKEN` when
`--answer` is given something other than `yes`/`no`, and
`REVISION_UNREADABLE` when the pinned revision cannot be read. It does not
touch a token an earlier `offer` already minted; see `gate`'s own closing
paragraph for that gap, stated in full there.

Every published `launch` action's `binding` carries a minted `authorization`
token — a digest over the engine's own re-derived binding (job, commit,
entrypoint, units, rung, revision, position status, and now the digest of
whichever campaign `proposal` event currently names this job, or `null`
when none does), never over this call's argv alone — and its own
`binding.authorization` key names the same value already appended to the
action's `command` string as `--authorization <token>`, so the next step is
to run that command exactly as printed. A token minted while no proposal
covers this job (`proposalDigest: null`) still mints and still passes
`gate`'s own authorization check; `gate` then refuses `GATE_PROPOSAL_UNKNOWN`
on the SEPARATE proposal precondition — publish one with `propose` first.

## `gate` — the launch authorization record

The second, independent precondition a non-rehearsal `submit` reads before it
may run (design's launch-authorization domain). Binds an un-forgeable
readiness measurement — a rehearsal that actually ran and was recorded, read
back through `smokeReady` — to a human-legible justification, and appends
the pair, plus one `authorization-consumed` event naming the token spent.
Prints no token of its own: nothing here can be minted by computing a digest
over the caller's own argv. `--authorization <token>` is required and must
instead name a token an earlier `offer` publish already minted — copy it
from that `launch` action's own `command` string or `binding.authorization`.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py gate \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --job governing-search --worker <account> \
  --justification "Rehearsal passed at the pinned commit; launching the full grid." \
  --authorization '3f9c...e21a'
```

Repeatable `--unit`, in place of `--worker`, authorizes a CAMPAIGN launch
instead — one that will spread across every healthy account via `submit
--unit ...` rather than one named account. It binds the exact ordered unit
list that later `submit --unit ...` will carry, the same derivation
`campaign_consent_token()` already uses when minting the launch's consent
token, and records `worker: null`: a campaign names no single account.
`--worker` and `--unit` are mutually exclusive.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py gate \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --job governing-search --unit shard-0 --unit shard-1 --unit shard-2 \
  --justification "Rehearsal passed at the pinned commit; launching the campaign." \
  --authorization '9a10...5b3c'
```

Once the authorization token itself verifies, `gate` requires a bound
campaign proposal naming this job (published by `propose`) and, when this
job classifies `optional` (`classify_remote_necessity`'s own verdict — the
recorded facts do not decide), a matching human election:

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py gate \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --job ablation-a --worker w1 \
  --justification "No declared accelerator or local budget; electing anyway." \
  --authorization '3f9c...e21a' --elect ablation-a
```

`--elect <job>` (repeatable) is argv, per invocation, never stored and
reused — the same "asked every time" discipline `--justification` already
keeps. A job with no declared `accelerator` and no `--local-budget-seconds`
classifies `optional` and needs `--elect` at every gate call; that is
intended, not a bug — it is the recorded facts saying "not decided", never
"skip it".

Refuses `EMPTY_JUSTIFICATION` on blank input, `POSITION_ABSENT`/`POSITION_STALE`
when there is nothing current to gate against, `POSITION_UNBACKED` when a step
is ticked and its witness was never measured — a blank box claims nothing and
is honest for it, a ticked one asserts a step was reached, and a launch is not
authorized against an assertion nobody checked — `POSITION_SHARDS_UNDECLARED`
when the ticked item's witness is `@shard` and nothing named where a returned
shard lands (no `distribution.shardsRoot` declared, `gate` itself carries no
`--shards` flag to override with) — a different fact from `POSITION_UNBACKED`:
this tick was never told where to look, rather than looked-at and found
silent — `NOT_READY` when no passing
rehearsal is on file for this job at its current pin, `SEQUENCE_NOT_REACHED`
when an earlier item in the sequence is still open — a launch that would skip
a rung is refused rather than authorized around it —
`GATE_WORKER_UNIT_CONFLICT`/`GATE_WORKER_REQUIRED` when `--worker` and
`--unit` are both given or neither is, six authorization codes:
`GATE_AUTHORIZATION_REQUIRED` (`--authorization` omitted — there is no
default), `GATE_AUTHORIZATION_UNKNOWN` (no ledger record vouches for the
token, or it no longer re-digests to its own recorded fields),
`GATE_AUTHORIZATION_SUPERSEDED` (a legitimate token minted before
`proposalDigest` joined the binding, re-digesting correctly under the
7-key shape that predates it — diagnostic only, refused exactly as hard as
`UNKNOWN`), `GATE_AUTHORIZATION_MISMATCH` (the record names a different job
or unit list), `GATE_AUTHORIZATION_STALE` (a bound fact — pin, entrypoint,
rung, revision, position status — has moved since minting, never merely
elapsed time), and `GATE_AUTHORIZATION_CONSUMED` (the token already
authorized one successful `gate` call; single-use, never reusable); three
proposal codes: `GATE_PROPOSAL_UNKNOWN` (the token names no campaign
proposal this ledger still vouches for), `GATE_PROPOSAL_MISMATCH` (a
genuine, current proposal exists but does not name this job),
`GATE_PROPOSAL_STALE` (the proposal's own `commit`/`jobSet` no longer
matches live disk); and two election codes: `GATE_ELECTION_REQUIRED` (this
job classifies `optional` and no `--elect` names it),
`GATE_ELECTION_MISMATCH` (`--elect` names a different job, or names this
job while it does not classify `optional`). There is deliberately no
`GATE_PROPOSAL_REQUIRED` and no `--proposal` flag — the proposal
precondition is entirely engine-derived from the authorization token's own
`proposalDigest`, never argv. A `gate` record written before this mechanism
existed carries no token and is neither migrated nor invalidated — the
requirement binds the *command*, not the record.

A later `offer` call over a changed experiment contract does not revoke an
outstanding, unconsumed token, either — `offer` no longer recomputes or
compares any contract digest at all (see `offer`'s own docstring). This is
reasoned, not executed or measured: `_AUTHORIZATION_BINDING_KEYS` carries no
contract fact, and adding one would make every token minted before this
mechanism existed re-digest to a different value — refused as
`GATE_AUTHORIZATION_UNKNOWN`, whose own message says the event was edited
after minting. That would be a true refusal under a false explanation, and
this codebase does not ship one. Only the seven facts
`GATE_AUTHORIZATION_STALE` already names can invalidate a token; a change to
the underlying contract is not one of them, and no new `gate` refusal exists
to close that gap. It is left open on purpose. `GATE_PROPOSAL_STALE` is a
separate, later check over a separate fact (the proposal's own `commit`/
`jobSet`, never `_AUTHORIZATION_BINDING_KEYS`' seven) — it does not widen
what invalidates the token itself.

## `close` — the finishing precondition

Writing the position becomes a precondition of finishing, not a courtesy:
`close` refuses while a transition has been made and not recorded, and names
which one, rather than always succeeding.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py close \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id>
```

Checked against the position exactly as recorded, before the refresh that
follows — the identical ladder `gate` calls first
(`impl_availability.position_honest`, shared rather than reimplemented):
`POSITION_ABSENT` when no section was ever generated, `POSITION_STALE` when
it is bound to a revision that has moved on, `POSITION_UNBACKED` when a
sequence item is ticked and its witness was never measured, `POSITION_
SHARDS_UNDECLARED` when the ticked item carries a `@shard` witness and
nothing named where a returned shard lands — neither an explicit `--shards
<dir>` at `position` nor this target's own declared `distribution.
shardsRoot` — so the tick cannot be checked at all, a different fact from
`POSITION_UNBACKED`'s "checked, and found silent", and `POSITION_DISAGREES`
when a recorded mark still contradicts its own measured evidence. Right
after that ladder, a second and independent axis: `AGREEMENT_DISAGREES`
when a ticked `AGREEMENTS.md`-style checklist item's own declared
`test_<id>` witness (`settle --witness`) is absent from a fully-parsed
`tests/` — the only place in the whole CLI this ever gates; `verify` and
`probe` only ever report it. Only once both checks are clean does `close`
refresh — picking up any position witness that has become measurable since
— and record the transition. A second `close` over the identical, unmoved
position reports `"not_open"` rather than appending a second event.

## `step` — run one declared local step, isolated

The executor for the isolation rule stated at the very top of `SKILL.md`
("Executing a notebook needs `PATH`, not just the right `python`"): a target
names one callable in its own `__steps__`, and this runs exactly that one,
as a subprocess under the target's own `.venv/bin/python`, `PATH` prefixed
by that interpreter's own directory so a notebook's kernelspec resolves it
rather than whatever `python` happens to be first on the inherited `PATH`.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py step \
  --target implementations/<repo> --name <Name> --session <your-session-id> \
  --step verification
```

Runs exactly one step per call — no flag sequences or dispatches more than
one, and this never consults `probe`'s `nextStep`. A step that declares
`advances` is refused `STEP_SEQUENCE_NOT_REACHED` while an earlier sequence
item is still unticked — and the mark it reads is the literal one in the
target's own `AGREED.md`, which a step that just ran does not update.
`position` is the only writer into that section, so `step` never re-derives
it; the refusal publishes the exact `position` refresh instead, bound to the
revision the block already names, as a command run unedited. That pair —
**run the step, commit its product, re-derive `position`, run the next
step** — is the whole loop between two ordered steps.

Every successful call publishes that loop for itself, in `next`, so it is
read where it is needed rather than remembered from here. `next[0]` is the
`git status --porcelain` listing of what this step just left in the tree:
**a step's product must be committed before the next step runs**, because
every step dirties the target and the next one refuses `DIRTY_WORKTREE`
until it is clean. The commit message is the operator's; this skill never
writes one. `next[1]`, when the product carries a readable position block,
is the exact `position` refresh, bound to the block's own revision. A
six-step flow is therefore six `step` calls, five commits and five
refreshes — not one command repeated six times. Refuses `DIRTY_WORKTREE`
before any subprocess spawns (a step mutates the target, same guard
`plan`/`apply` already call). When the ledger's latest `step` event is a
bare `started`, that refusal's published question says so: it names the
step that was killed, when it started, that what it left behind is partial
product a re-run does not resume, and it publishes `git clean -nd` — a dry
run listing exactly which untracked paths a cleanup would remove, removing
none of them. Which of them are the dead run's leftovers stays the
operator's reading; the engine never authors the removal. Also refuses `STEPS_UNDECLARED` when the target's
`__steps__` names nothing at all, `STEP_UNKNOWN` when it names something and
`--step` is not one of them, `STEP_MALFORMED` when the named entry is
missing `module` or `function`; `INTERPRETER_ABSENT` when the target has no
`.venv` yet (`env` first); and, once the subprocess itself has run,
`STEP_MODULE_MISSING` / `STEP_FUNCTION_MISSING` / `STEP_NOT_CALLABLE` when
the declared callable does not resolve inside the venv, or
`STEP_RUNNER_SILENT` when the process exited without ever writing a verdict
— died before resolution even began, so nothing here can say whether the
step ran. Those four target-side refusals each leave a `refused` terminal
event in the ledger naming the code; the forge-side refusals above them
(`FORGE_DEFECT_OPEN` through `INTERPRETER_ABSENT`) leave nothing at all,
which is what keeps "no event" meaning exactly one thing.

Every run past `INTERPRETER_ABSENT` appends a **pair** of `kind: "step"`
events to `.implementation/position.jsonl`. The first, `outcome:
"started"`, is written the instant before the subprocess spawns and carries
the step's name, its dotted callable, the interpreter path and the session —
nothing else. So the ledger's *shape* answers the question an exit code
cannot: **no event at all means this command never started** (a mis-resolved
invocation, a wrong working directory — nothing here ever ran); **a
`started` with no partner after it means it started and was killed** (a
harness timeout, a `SIGKILL`) and its product is partial; **a terminal event
means it ran and reported**. Do not read a step's success off an exit status
or off stdout: read it off this pair.

The terminal event carries the step's name, its dotted callable,
the interpreter path, `outcome` (`returned`/`raised`/`unknown`), exit
status, `error` (the raised exception, formatted once inside the
subprocess itself, since the step's own stdout/stderr are inherited live
rather than captured), and `suiteDigest` — `suite_digest(target)`, every
`.py` under `src/` and `tests/` plus five fixed environment manifests
(`requirements.txt`, `pyproject.toml`, `setup.cfg`, `tox.ini`,
`pytest.ini`), computed fresh at write time, unconditionally regardless of
outcome. This reverses "no digest field" only for a bare runner step with
no self-stamping artifact of its own; a notebook still recomputes
`source_digest` fresh against its own `DIGEST_MARKER` output, so a
ledger-carried copy there would still be redundant. An `@step <name>`
witness in `position`'s own sequence folds the ledger's latest event per
name (latest wins) against a live digest: `True` for a current `returned`,
`False` for a current `raised`, `unmeasured` for a stale digest, a
pre-change event with no digest at all, or no event at all — never a false
`True`/`False` over code nobody ran against. **Stated non-goal**: this does
not distinguish a fully-executed suite from one that skipped tests —
`pytest` exits 0 on skips, so `returned` grades green over a skipped suite
exactly as a notebook report already does. An unknown `--step` name is
`STEP_UNKNOWN` on this command; the identical operand named inside a
position sequence's `@step` witness is `POSITION_STEP_UNKNOWN` instead,
raised by `position` (an argument to `step` is an invocation the caller
typed; a position item's operand lives in AGREED.md, so clearing it means
editing the document or declaring the step) — `STEPS_UNDECLARED` covers
the case where `__steps__` names nothing at all, in either command,
verbatim. This never touches `gate`: it calls none of the remote-execution
loaders, and a `kind: "step"` line is invisible to
`_verify_launch_authorization`, which selects on the exact string
`"gate"`.

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
| `DESTINATION_CONFLICT` | A destination is taken, or two sources target one path. For `materialize --stage`, a destination appeared between the destination set's computation and the write; the whole stage refuses before any byte lands. |
| `UNCLASSIFIED_FILES` | No rule covers some files. Ask where they belong. |
| `APPLY_ABORTED` | Something failed mid-migration, or mid-`materialize`. Nothing was committed/written and the tree was restored; re-run `plan`. |
| `MATERIALIZE_MODE_REQUIRED` | `materialize` needs exactly one of `--stage`/`--authored`/`--adopt`; none was given. |
| `MATERIALIZE_MODE_CONFLICT` | Two or more of `--stage`/`--authored`/`--adopt` were given together; the three modes are mutually exclusive. |
| `PLAN_REQUIRED` | `materialize --stage` needs `--plan <approved plan JSON>`. |
| `SEED_REQUIRED` | `materialize --stage scaffold` needs `--seed`, substituted into `{{SEED}}`. |
| `STAGE_CANNOT_ANSWER` | A scaffold-stage `.py` destination still fails `ast.parse` after `{{PKG}}`/`{{SEED}}` substitution — its remaining token answers a later step. Names the file. Never raised by `objects`/`harness`: their three destinations are either written with tokens deliberately left standing (`objects`) or already parse cleanly (`harness`'s two `.py` files). |
| `OBJECT_MAP_NOT_APPROVED` | `materialize --stage objects` ran before step 8's `revision`/`premises` were recorded in `src/<Package>_Benchmark/__init__.py`. The detail names whichever of the two is still blank, so a half-written map does not send you back to re-read the half that is already right. Get that declaration approved and written first. |
| `SCAFFOLD_DRIFT` | (`verify`, reported in `structure.scaffoldDrift`, never raised) A receipt-recorded scaffold destination's on-disk bytes no longer match its `writtenSha256`. Release the seal with `materialize --authored <path>` after declaring the edit. `objects`/`harness` destinations get the identical check under `structure.objectDrift`/`structure.harnessDrift`. |
| `UNRECORDED_SCAFFOLD` | (`verify`, reported in `structure.unrecordedScaffold`, never raised) A scaffold destination exists on disk with no receipt entry — most often because the target was scaffolded before this command existed. Remedy: `materialize --adopt <path>`, one path at a time, deliberately. **This degrades the guarantee**: adoption records who is responsible for the bytes, never that they came from the kit — the record names who wrote them, not that the engine owns them. `objects`/`harness` destinations get the identical check under `structure.unrecordedObjects`/`structure.unrecordedHarness`. |
| `NOT_A_KIT_DESTINATION` | `materialize --authored`/`--adopt` named a path outside the seventeen kit destinations (eleven scaffold, three objects, three harness). The receipt is not a general-purpose ledger. |
| `MATERIALIZE_PATH_ABSENT` | `materialize --authored`/`--adopt` named a path with no bytes on disk. |
| `NO_RECEIPT_ENTRY` | `materialize --authored <path>` named a path the engine never wrote. There is no seal to release; use `--adopt`. |
| `ALREADY_RECORDED` | `materialize --adopt <path>` named a path the receipt already carries. Adoption is not a re-seal; use `--authored`. |

### Every refusal says how it is cleared

Every refusal leaves the CLI through one handler and prints the same JSON:
`status`, `code`, `detail`, exit `2`, nothing appended anywhere. Refusals a call
to one of the nine **gating** commands can reach — `apply`, `admit`, `gate`,
`offer`, `close`, `step`, `settle`, `materialize`, `position` — carry one more
thing, and which ones carry it is itself the answer to a question:

> Can the caller clear this by changing the invocation alone, without touching
> the repository?

**Yes — an invocation defect.** The detail already names the flag, the token or
the mutual exclusion. Forty-nine codes, and nothing is published beside them:
`SETTLE_STDIN_CONFLICT`, `OFFER_ANSWER_NOT_A_TOKEN`, `MATERIALIZE_MODE_REQUIRED`,
`NOT_A_GIT_REPO`, `GATE_ELECTION_REQUIRED` and the rest. Retype the call.

**No — a work state.** Somebody has to act on the repository, so the payload
carries a `resolve` key saying what. Sixty-three codes, including
`POSITION_DISAGREES`, `AGREEMENT_DISAGREES`, `POSITION_STALE`, `DIRTY_WORKTREE`,
`GATE_AUTHORIZATION_CONSUMED`, `STEP_MODULE_MISSING`,
`POSITION_RUNG_SKIPPED`, `POSITION_STEP_UNKNOWN`, `STEPS_UNDECLARED`,
`POSITION_RECORD_MALFORMED` and `NOT_READY`:

```json
{ "status": "refused", "code": "POSITION_STALE",
  "detail": "the position section is bound to a revision whose bytes no longer match; ...",
  "resolve": { "kind": "command",
               "command": "implementation_cli.py position --target implementations/repo --name Name --session s1 --revision r7.md" } }
```

`resolve.kind` is `command` when the engine can name the whole exit — run it
unedited — and `question` when the next act is a decision nobody but a human
can take, in which case `resolve.command` is the runnable `discuss` invocation
that opens it and `resolve.question` is the text it will ask.

`POSITION_DISAGREES` — a ticked item whose own witness contradicts the mark —
resolves to re-executing the verification notebook under the target's own venv
with that venv's `bin` on `PATH`, then re-running `position` to rebind. The
`PATH` prefix is not decoration; see
[Executing a notebook needs `PATH`](../SKILL.md#executing-a-notebook-needs-path-not-just-the-right-python).

The roster lives in `implementation_cli.py` as `GATING_REFUSALS`, and the suite
derives the gating commands' refusal codes from their own source: **a refusal
added to a gating command fails the tests until it has been classified.** No
code reaches a reader as a bare word again.

`DESTINATION_CONFLICT` also covers a rename whose destination already exists.
That case is not cosmetic: `git mv A B` with `B` present does not rename, it
moves `A` *inside* `B`, which silently produces `<Name>/Images/Results/...`.

`apply` is all-or-nothing. The tree is verified clean before any mutation, so a
failure discards the partial work and restores exactly the reviewed starting
point instead of leaving a half-migrated repository.
