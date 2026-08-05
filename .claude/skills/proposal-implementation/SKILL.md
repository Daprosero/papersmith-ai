---
name: proposal-implementation
description: "Trigger: turn the latest managed mathematical proposal into working Python, scaffold or reorganize a target repository, or verify an existing implementation's layout and revision fidelity. Isolated venv, keyless, fail-closed."
---

# Proposal Coding

Turn the current managed revision (`research-concept-rNN.md`) into Python that
runs, in a target repository, and then prove it: smoke, invariants, synthetic
data. Text is not the deliverable — code with a traceable link back to the
mathematics is.

## Non-negotiable isolation

Every run works inside `implementations/<repo>/` and uses **that repository's own
`.venv`**. Never the forge's virtualenv, never system Python for target code.
`implementations/` is gitignored; the CLI refuses any target outside it, and refuses to
create a venv from a forge interpreter.

## Activation Contract

Activate when the user asks to implement, code, scaffold, reorganize or verify
the implementation of the managed proposal. Do not activate for edits to the
proposal itself — that is `proposal-deliberation`.

## Hard Rules

- Bind to the revision `proposal-deliberation`'s `STATUS` reports as `latest`. Never
  guess the base and never read `proposals/` by hand.
- Never write implementation code before the user approves the mapping from
  mathematical object to module.
- Dirty target worktree → stop and report. Never mutate an unclean repository.
- Migration is `git mv` in its own separate commit, before any new code.
- Never flatten an organized subtree. A product folder with the right shape and
  the wrong name is one rename, not one move per file.
- A migration is not finished until the references move with it. Moves break
  paths exactly as renames do. Present `referenceUpdates` alongside the moves
  and never apply one without the other.
- Rewrite only what is unambiguous; report the rest. A path the skill cannot
  remap safely belongs in `staleReferences`, not in a guessed substitution.
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
- Audit the mathematics, not the code. A finding is an ill-formed term, a claim
  stated more strongly than the construction supports, a missing complement, or
  a constant that does not hold up.
- No finding without a remedy, and no remedy without validation. Both are
  measured over the same randomized sweep of 200 configurations.
- Classify every finding. `theorem` demands the full sweep; `tendency` must
  declare its measured rate and must never be asserted as a law.
- Remedies live in `tests/`, never in `src/`. Establishing that a correction is
  sound is not the same as adopting it.
- v1 scope is smoke + invariants + synthetic + audit + remedies. Classic SOTA
  datasets and baseline comparison are out of scope; say so instead of
  improvising them.

## Target layout

```
<repo>/
├── <Name>/            Notebooks/  Data/ (only if data exists)  Results/  Models/
├── src/<Package>/     the implementation (.py), one module per mathematical object
├── tests/             smoke, invariants, synthetic, findings + audit + remedies
└── pyproject.toml     isolation marker: anchors pytest/ruff to this repo
```

`<Name>` is chosen by the user. `<Package>` is its importable form: a hyphen is
legal in a directory but not in a Python identifier, so `MIL-CREDA/` pairs with
`src/MIL_CREDA/`. Never scaffold `src/<Name>/` when the two differ — nothing
could import it. Pre-existing code moves to its own package under `src/`, never
into `src/<Package>/`. `pyproject.toml` must carry
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
| Plan reports `referenceUpdates` | Show them; `apply` rewrites them in the same commit |
| `verify` reports `staleReferences` | A path points nowhere: report before writing any code |
| Plan reports `unclassified` or `conflicts` | Ask where those files belong; never guess |
| `verify` reports structure drift | Report it as its own finding, ask before fixing |
| `verify` reports stale modules | Report revision drift separately; ask before rewriting |
| Target outside `implementations/`, or dirty tree | Refuse and report the guard |

## Execution Steps

1. `node .claude/skills/proposal-deliberation/engine/cli.mjs '{ "operation": "STATUS" }'` → take `latest`.
2. Ask the user for `<Name>` and the repository (new or existing URL).
3. `GIT_LFS_SKIP_SMUDGE=1 git clone <url> implementations/<repo>` (or `git init`), pin the
   LFS skip in the clone's local config (see `references/usage.md`), then `env`.
4. Install dev dependencies with the printed target `pip`, never the forge's.
5. `plan` → show every rename, move and reference update with its reason → get
   explicit approval → `apply`, which lands all three in one commit.
6. Fill scaffold gaps from `assets/` (pyproject, `__init__.py`, smoke test, notebook).
7. Present the object → module map. Wait for approval. Only then write code.
8. Write one module per object with `__provenance__`, plus its invariant tests.
9. Audit: sweep 200 configurations, declare each finding in `tests/findings.py`
   with its kind, status, measured rate and proposed remedy.
10. Validate every remedy over the same sweep: it must resolve its finding and
    preserve the properties already established.
11. Run the suite with the target interpreter, then execute the notebook.
12. `verify --revision <latest>` and report structure, fidelity and audit.

## Output Contract

Report: the bound revision, the target path, the migration commit hash (if
any), the object → module map, the test result, and the three verification
statuses (`structure`, `fidelity`, `audit`) separately. For each finding give
its kind, the equations it touches, its status with the measured rate, and the
remedy with the equations the remedy would change. State scope left out. Never
claim verification passed without the `verify` output and a green suite, and
never report a finding whose remedy validation did not run.

## References

- `references/usage.md` — worked invocations of every command.
- `scripts/implementation_cli.py` — `env`, `plan`, `apply`, `verify`. Stdlib only.
- `assets/` — pyproject, module, test and notebook templates.
