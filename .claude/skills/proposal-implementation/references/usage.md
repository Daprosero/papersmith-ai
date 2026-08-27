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

Three more are reported and none of them is a finding, which is exactly why
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
the one command that writes it, and the only writer into `<Name>/AGREED.md` at
all. No flag: re-derive the marks of whatever block is already there, touching
nothing else about it — not the item text, not the order, not which witness
each one names.

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

`--sequence -` installs a fresh section instead of refreshing one, reading an
ordered JSON array of `{text, witness: {kind, operand}}` from stdin:

```bash
echo '[{"text": "Search for the governing value.",
        "witness": {"kind": "record"}},
       {"text": "Rehearse the campaign job.",
        "witness": {"kind": "rehearsal", "operand": "governing-search"}}]' \
  | python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py position \
      --target implementations/<repo> --name <Name> \
      --revision research-concept-r05.md --session <your-session-id> --sequence -
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
  --revision research-concept-r05.md --session <your-session-id> --reconcile
```

Builds one `@record` from the benchmark's declared search, one `@rehearsal`
per discovered job folder, one `@notebook` per `Notebooks/*.ipynb` in name
order, and — with `--shards` also given — one `@shard` per arrived shard.
Existing items are matched by witness identity (kind and operand) and keep
their text and their order exactly; only a witness with no match is
appended, its text a placeholder for a human to write over. Safe to run
again: an unchanged target appends nothing and reports `"unchanged"`.
`--sequence` and `--reconcile` together refuse `POSITION_SEQUENCE_AND_RECONCILE`
— only one of the two may name this call's sequence.

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
  "measured": null, "collides": [], "asked": "Should this job rehearse...",
  "answered": null }
```

`--about` names the step either by its ordinal in the current position
sequence, or by a bare witness spec (`"kind"` or `"kind operand"`) when
there is no sequence item yet to number. `--answer` (optionally `-` to read
stdin, like `--question`) moves `status` from `"open"` to `"answered"`; at
most one of `--question`/`--answer` may read stdin in the same call.
`collides` is computed fresh against every checklist item in the product
folder's markdown that names the same operand — never remembered from an
earlier call.

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
the way is the only thing reported. Ten values are possible. Seven prescribe
work and each has its own section in `SKILL.md` — `convert`, `declare-first`,
`wiring-first`, `poll-first`, `search-first`, `report-first` and `benchmark`.
The other three prescribe none, and deliberately have no section:
`nothing-to-compare`, `piloted` and `already-benchmarked`.

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

## `gate` — the launch authorization record

The second, independent precondition a non-rehearsal `submit` reads before it
may run (design's launch-authorization domain). Binds an un-forgeable
readiness measurement — a rehearsal that actually ran and was recorded, read
back through `smokeReady` — to a human-legible justification, and appends
the pair. Prints no token: nothing here can be minted by computing a digest
over the caller's own argv.

```bash
python3 .claude/skills/proposal-implementation/scripts/implementation_cli.py gate \
  --target implementations/<repo> --name <Name> \
  --revision research-concept-r05.md --session <your-session-id> \
  --job governing-search --worker <account> \
  --justification "Rehearsal passed at the pinned commit; launching the full grid."
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
  --justification "Rehearsal passed at the pinned commit; launching the campaign."
```

Refuses `EMPTY_JUSTIFICATION` on blank input, `POSITION_ABSENT`/`POSITION_STALE`
when there is nothing current to gate against, `NOT_READY` when no passing
rehearsal is on file for this job at its current pin, `SEQUENCE_NOT_REACHED`
when an earlier item in the sequence is still open — a launch that would skip
a rung is refused rather than authorized around it — and
`GATE_WORKER_UNIT_CONFLICT`/`GATE_WORKER_REQUIRED` when `--worker` and
`--unit` are both given or neither is.

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
follows: `POSITION_ABSENT` when no section was ever generated,
`POSITION_STALE` when it is bound to a revision that has moved on, and
`POSITION_DISAGREES` when a recorded mark still contradicts its own measured
evidence. Only once that check is clean does `close` refresh — picking up
any witness that has become measurable since — and record the transition. A
second `close` over the identical, unmoved position reports `"not_open"`
rather than appending a second event.

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
