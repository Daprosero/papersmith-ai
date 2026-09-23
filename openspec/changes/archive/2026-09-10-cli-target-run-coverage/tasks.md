# Tasks: CLI Target/Run Coverage

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 280–360 additions, 0 deletions (tests only) |
| 400-line budget risk | Low |
| 800-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Hermetic target/run coverage in `tests/test_papersmith_executor.py` | PR 1 | `pytest tests/test_papersmith_executor.py` | `npm run test:all` (hermetic suite, no network/credentials) | Revert `tests/test_papersmith_executor.py` to HEAD |

## Phase 1: Fixture Foundation

- [x] 1.1 Extend manifest helper in `tests/test_papersmith_executor.py` with `kaggle-gpu-pool` + `slurm-cluster` shapes copied from `src/papersmith/templates/papersmith.yaml.tpl`
- [x] 1.2 Add hermetic mock idiom in `tests/test_papersmith_executor.py` (`mock.patch.object` on `executor.subprocess.run`, `target.subprocess.run`, `bridges.python.run_script`, `shutil.which`)

## Phase 2: Target Check/Set Matrix

- [x] 2.1 Test `target.check_target` local / unknown-name / unsupported-provider in `tests/test_papersmith_executor.py` (patch `shutil.which`; `UserError` on unknown/unsupported)
- [x] 2.2 Test `target.check_target` kaggle up/down in `tests/test_papersmith_executor.py` (patch `bridges.python.run_script` rc 0/1; assert `reachable`)
- [x] 2.3 Test `target.check_target` ssh up/down/missing-host in `tests/test_papersmith_executor.py` (patch `target.subprocess.run`; `UserError` when host missing)
- [x] 2.4 Test `target.set_target` persistence round-trip in `tests/test_papersmith_executor.py` (`set_target` + `load_workspace_config` + CLI `set` via `papersmith.cli.main`)

## Phase 3: Run Dispatch Matrix

- [x] 3.1 Test `executor.run_profile` local ok/nonzero/timeout/OSError in `tests/test_papersmith_executor.py` (patch `executor.subprocess.run`; assert `EXECUTION_ERROR` mapping)
- [x] 3.2 Test `executor.run_profile` kaggle dry-run argv + consented `--unit` forwarding in `tests/test_papersmith_executor.py` (mocked dispatch; assert only `submit/--target/--entrypoint/--backend/--unit/--consent`; consent PASS-THROUGH)
- [x] 3.3 Test `executor.run_profile` ssh sbatch argv + mocked dispatch in `tests/test_papersmith_executor.py` (assert `ssh/sbatch/--partition/--time/--wrap`; missing host raises `UserError`)
- [x] 3.4 Test `target_override` precedence + entrypoint fallback to `runner.ipynb` in `tests/test_papersmith_executor.py`
- [x] 3.5 Test failing-exit ledger rows in `tests/test_papersmith_executor.py` (`ledger.read` asserts `dry_run:false`, nonzero `exit`, `status:failed`)

## Phase 4: CLI Wiring + Verification

- [x] 4.1 Drive 2–3 legs via `papersmith.cli.main()` in `tests/test_papersmith_executor.py` (`target set/check`, `run --dry-run/--target/--consent`)
- [x] 4.2 Verify hermetic suite via `npm run test:all` in `tests/test_papersmith_executor.py` scope (no network/credentials; no `src/` diff)
