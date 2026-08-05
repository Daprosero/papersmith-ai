# Proposal Coding — worked invocations

See [SKILL.md](../SKILL.md) for the contract. Everything below is a real
invocation of `scripts/coding_cli.py`: standard library only, no keys, no
network. Each command prints one JSON object; exit code `2` means a guard
refused and nothing was touched.

Run the CLI with a **system** interpreter (`python3`). It refuses to run from a
forge virtualenv, so it can never hand the forge's interpreter to a target venv.

## 0. Bind the revision

```bash
node .claude/skills/paper-proposal/engine/cli.mjs '{ "operation": "STATUS" }'
```

Take `latest` (e.g. `research-concept-r12.md`). That string is what modules
declare in `__provenance__["revision"]` and what `verify --revision` compares
against. Everything downstream is bound to it.

## 1. Land the repository under `coding/`

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone <url> coding/<repo>   # existing repository
git init coding/<repo>                                # new one
```

`coding/` is gitignored in the forge, so the clone's own `.git` never becomes a
stray gitlink in the forge's index.

On a repository that tracks weights, pin the skip in the clone as well — the
environment variable covers the clone and nothing else, so a later `git reset
--hard` or branch switch starts downloading again:

```bash
git -C coding/<repo> config --local filter.lfs.smudge "git-lfs smudge --skip -- %f"
git -C coding/<repo> config --local filter.lfs.process "git-lfs filter-process --skip"
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
python3 .claude/skills/proposal-coding/scripts/coding_cli.py env \
  --target coding/<repo> [--python python3.12]
```

Without `--python` the venv is built from the interpreter running the CLI.
Check `pythonVersion` in the response: the templates declare `requires-python
>= 3.10`, so pass `--python` when the system default is older.

```json
{
  "command": "env",
  "status": "created",
  "pythonVersion": "Python 3.12.4",
  "interpreter": "…/coding/<repo>/.venv/bin/python",
  "pip": "…/coding/<repo>/.venv/bin/pip",
  "nextCommand": "…/pip install -r …/assets/requirements-dev.txt"
}
```

Run `nextCommand` as printed. From here on, every command that touches target
code goes through the returned `interpreter`.

## 3. Plan the migration (read-only)

```bash
python3 .claude/skills/proposal-coding/scripts/coding_cli.py plan \
  --target coding/<repo> --name CREDA > /tmp/plan.json
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
  "renames": [{ "from": "Images", "to": "CREDA",
                "reason": "product folder has the right shape but the wrong name; renaming preserves every subtree" }],
  "createDirs": ["tests"], "moves": [], "conflicts": []
}
```

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
python3 .claude/skills/proposal-coding/scripts/coding_cli.py apply \
  --target coding/<repo> --name CREDA --plan /tmp/plan.json
```

The plan is recomputed and compared before anything moves: if the repository
changed since approval, it refuses with `PLAN_STALE`. On success everything
lands in one commit — `git revert <commit>` undoes the whole migration.

Then write the files listed in `scaffoldFiles` from `../assets/`, substituting
`{{NAME}}`, `{{NAME_LOWER}}`, `{{REVISION}}`, `{{MODULE}}`, `{{FUNCTION_NAME}}`
and `{{INVARIANT_ID}}`.

## 5. Verify

```bash
coding/<repo>/.venv/bin/python -m pytest -q
python3 .claude/skills/proposal-coding/scripts/coding_cli.py verify \
  --target coding/<repo> --name CREDA --revision research-concept-r12.md
```

```json
{
  "structure": { "status": "ok", "missingDirs": [], "strayModules": [], "scaffoldGaps": [] },
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
  "validation": { "smokeTest": true, "invariantTests": ["test_kernel_is_psd"], "notebook": true }
}
```

Two independent findings, reported separately:

- **structure drift** — the layout no longer matches. Fix with `plan` → `apply`.
- **fidelity drift** — `staleModules` implement an older revision than the one
  in `--revision`; `invariantsWithoutTest` are claims declared in code with no
  test enforcing them. Both need the user's decision before you touch anything.

Omit `--revision` and `fidelity.status` is `unknown`: the modules' declared
revisions are still listed, but nothing is compared. Never report an
implementation as up to date from an `unknown` run.

## Guard codes

| Code | Meaning |
| --- | --- |
| `OUTSIDE_WORKSPACE` | Target is not under `coding/`. Clone it there. |
| `NOT_A_GIT_REPO` | No `.git`. Migration needs a revertible commit. |
| `DIRTY_WORKTREE` | Uncommitted or untracked changes. Commit or stash first. |
| `FORGE_INTERPRETER` | The CLI is running from a forge venv. Use system `python3`. |
| `PLAN_STALE` | The repository changed after approval. Re-plan, re-approve. |
| `DESTINATION_CONFLICT` | A destination already exists. Resolve with the user. |
| `UNCLASSIFIED_FILES` | No rule covers some files. Ask where they belong. |
