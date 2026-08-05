---
name: proposal-coding
description: "Trigger: turn the latest managed mathematical proposal into working Python, scaffold or reorganize a target repository, or verify an existing implementation's layout and revision fidelity. Isolated venv, keyless, fail-closed."
---

# Proposal Coding

Turn the current managed revision (`research-concept-rNN.md`) into Python that
runs, in a target repository, and then prove it: smoke, invariants, synthetic
data. Text is not the deliverable — code with a traceable link back to the
mathematics is.

## Non-negotiable isolation

Every run works inside `coding/<repo>/` and uses **that repository's own
`.venv`**. Never the forge's virtualenv, never system Python for target code.
`coding/` is gitignored; the CLI refuses any target outside it, and refuses to
create a venv from a forge interpreter.

## Activation Contract

Activate when the user asks to implement, code, scaffold, reorganize or verify
the implementation of the managed proposal. Do not activate for edits to the
proposal itself — that is `paper-proposal`.

## Hard Rules

- Bind to the revision `paper-proposal`'s `STATUS` reports as `latest`. Never
  guess the base and never read `proposals/` by hand.
- Never write implementation code before the user approves the mapping from
  mathematical object to module.
- Dirty target worktree → stop and report. Never mutate an unclean repository.
- Migration is `git mv` in its own separate commit, before any new code.
- Never flatten an organized subtree. A product folder with the right shape and
  the wrong name is one rename, not one move per file.
- Clone with `GIT_LFS_SKIP_SMUDGE=1` **and** persist the skip in the clone's
  local config. Pointers are enough to reorganize; the env var only covers the
  clone, so any later checkout or reset re-downloads gigabytes and burns the
  LFS quota.
- `tests/*.py` is the source of truth and is fail-closed. The notebook is the
  executed report, never the only place a claim is checked.
- Every module under `src/<Name>/` declares `__provenance__`; every id in its
  `invariants` has a matching `test_<id>`. No provenance, no merge.
- Never fabricate mathematics. A test whose claim is not traceable to the
  proposal does not belong in the suite.
- v1 scope is smoke + invariants + synthetic data. Classic SOTA datasets and
  baseline comparison are out of scope; say so instead of improvising them.

## Target layout

```
<repo>/
├── <Name>/            Notebooks/  Data/ (only if data exists)  Results/  Models/
├── src/<Name>/        the implementation (.py), one module per mathematical object
├── tests/             test_smoke.py, test_invariants.py
└── pyproject.toml     isolation marker: anchors pytest/ruff to this repo
```

`<Name>` is chosen by the user. Pre-existing code moves to its own package
under `src/`, never into `src/<Name>/`. `pyproject.toml` must carry
`[tool.pytest.ini_options]` with `pythonpath = ["src"]`: without it the suite
cannot import the package offline, and an existing file that lacks the table
counts as a gap, not as compliance.

## Decision Gates

| Situation | Action |
| --- | --- |
| No repository yet | Ask: create new, or clone an existing URL |
| Repository empty | Scaffold the layout directly; no migration commit |
| Layout already compliant, code present | Verification mode only |
| Layout drift | `plan` → present the map → user approves → `apply` |
| Product folder right shape, wrong name | `plan` proposes one rename; subtrees stay intact |
| Plan reports `unclassified` or `conflicts` | Ask where those files belong; never guess |
| `verify` reports structure drift | Report it as its own finding, ask before fixing |
| `verify` reports stale modules | Report revision drift separately; ask before rewriting |
| Target outside `coding/`, or dirty tree | Refuse and report the guard |

## Execution Steps

1. `node .claude/skills/paper-proposal/engine/cli.mjs '{ "operation": "STATUS" }'` → take `latest`.
2. Ask the user for `<Name>` and the repository (new or existing URL).
3. `GIT_LFS_SKIP_SMUDGE=1 git clone <url> coding/<repo>` (or `git init`), pin the
   LFS skip in the clone's local config (see `references/usage.md`), then `env`.
4. Install dev dependencies with the printed target `pip`, never the forge's.
5. `plan` → show every move with its reason → get explicit approval → `apply`.
6. Fill scaffold gaps from `assets/` (pyproject, `__init__.py`, smoke test, notebook).
7. Present the object → module map. Wait for approval. Only then write code.
8. Write one module per object with `__provenance__`, plus its invariant tests.
9. Run the suite with the target interpreter, then execute the notebook.
10. `verify --revision <latest>` and report both statuses.

## Output Contract

Report: the bound revision, the target path, the migration commit hash (if
any), the object → module map, the test result, and the two verification
statuses (`structure`, `fidelity`) separately. State scope left out. Never
claim verification passed without the `verify` output and a green suite.

## References

- `references/usage.md` — worked invocations of every command.
- `scripts/coding_cli.py` — `env`, `plan`, `apply`, `verify`. Stdlib only.
- `assets/` — pyproject, module, test and notebook templates.
