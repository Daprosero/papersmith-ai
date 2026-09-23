# Proposal: CLI Target/Run Coverage

## Intent

Problem: `target set/check` and `run` dispatch beyond `--dry-run` are unproven — check matrix, consent/`--unit` forwarding, failure mapping, and ledger rows have no tests. Cover them hermetically in `tests/test_papersmith_executor.py` with zero live network or credential use.

## Scope

### In Scope
- `target check` matrix: local, kaggle up/down, ssh up/down/missing-host, unknown name, unsupported provider
- `target set` persistence round-trip (`set_target` + `load_workspace_config` + CLI `set`)
- `run` dispatch matrix: local (ok/nonzero/timeout/OSError), kaggle (dry-run argv, consented `--unit` forwarding), ssh (sbatch argv, mocked dispatch)
- `target_override` precedence, entrypoint fallback to `runner.ipynb`, failing-exit ledger rows
- 2–3 legs driven through `papersmith.cli.main()` to lock handler wiring

### Out of Scope
- `kaggle-accounts` subcommand, audit, deliberate/implement/remote legs
- Approach 3 FakeAdapter duplication; live network, real credentials
- Any `src/` implementation change (tests only)

## Capabilities

### New Capabilities
- None — test-only change, no new product behavior.

### Modified Capabilities
- None — `cli-paper-e2e` requirements unchanged; no delta spec needed.

## Approach

Approach 1 (sealed-seam mocking at subprocess boundary) as backbone: `mock.patch.object` on `executor.subprocess.run`, `target.subprocess.run`, `bridges.python.run_script`, `shutil.which`; extend manifest fixture with kaggle + remote-ssh targets. Thin Approach 2 slice for CLI wiring. Reject Approach 3.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tests/test_papersmith_executor.py` | Modified | All new coverage (~10–14 small tests) |
| `src/papersmith/core/target.py` | Read-only | Seams under test, no edits |
| `src/papersmith/core/executor.py` | Read-only | Seams under test, no edits |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Mock drift from `remote_cli.py` flags | Med | Assert only repo-owned flags; skill semantics stay in `test_remote_execution.py` |
| Schema-invalid fixtures | Low | Copy shapes from `templates/papersmith.yaml.tpl` |
| Budget breach (800 lines) | Med | One seam per test; split stacked slices if grown |

## Rollback Plan

Revert `tests/test_papersmith_executor.py` to HEAD; no `src/`, ledger, or store state changes to undo.

## Dependencies

- `exploration.md` + Engram `sdd/cli-target-run-coverage/explore`; skill doctrines `remote-execution` (consent pass-through), `kaggle-accounts` (`list --json`).

## Success Criteria

- [ ] Check + set + dispatch matrices green via `npm run test:all`, hermetic (no network/credentials)
- [ ] Consent asserted as pass-through; `target_override` and fallback proven
- [ ] Diff within 800-line review budget
