## Exploration: CLI test coverage for `target set` / `target check` and `run` dispatch beyond dry-run

### Current State

`src/papersmith/core/target.py` (99 lines) owns three flows: `list_targets()` reads `papersmith.yaml` + `config.json:active_compute_target` and marks the active row; `set_target()` validates the name against `compute_targets.targets`, writes `execution_engine.active_compute_target` + `updated_at` into `.papersmith/config.json`, and returns name/provider; `check_target()` resolves `name or active` and branches by provider — `local` returns `shutil.which("python") is not None or bool(sys.executable)`, `kaggle` shells to `skills/kaggle-accounts/scripts/accounts_cli.py list --json` via `bridges.python.run_script` (timeout 30), `remote-ssh` runs `ssh -o BatchMode=yes -o ConnectTimeout=5 <host> true` via `subprocess.run`, anything else raises `UserError`. `run_cli()` prints `name: provider [*]` / `Active target: ...` / the check dict.

`src/papersmith/core/executor.py` (213 lines) resolves `target_override or profile.target or compute_targets.default`, renders jobs via `_profile_jobs()` (`{paper_slug}/{job_id}/{shard_value}` substitution, optional `--seed`-style parameter append), then dispatches per provider: `local` → `_local_job()` (`subprocess.run(job["command"])`, `TimeoutExpired`/`OSError` → `EXECUTION_ERROR`); `kaggle` → `_remote_command()` (`sys.executable skills/remote-execution/scripts/remote_cli.py submit --target --entrypoint --backend [--unit shard] [--consent]`, entrypoint scraped from the first `.py`/`.ipynb` token else `runner.ipynb` fallback) executed via `subprocess.run` + `mapped_returncode()`; `remote-ssh` → `_slurm_command()` (`ssh <host> sbatch [--partition] [--time] --wrap <command_text>`, missing host → `UserError`) executed the same way. `dry_run=True` skips all subprocess calls and records `command` only. Every job appends a `runs_ledger.jsonl` event (`profile/target/provider/job_id/shard_value/dry_run/exit/command`); status is `ok` iff all exits are 0. Consent is pass-through only — no gate lives in `executor.py`; the gate lives in `remote_cli.py submit` (per `skills/remote-execution/SKILL.md` consent-gate section).

`tests/test_papersmith_executor.py` (201 lines) proves only: ledger append/read, real local success (`python -c "print(42)"`), dry-run + shard selection with `subprocess.run` patched to fail-if-called, invalid shard/profile refusals, `target list/set/local-check` + unknown-set refusal, CLI `run --dry-run` + CLI `target list` (line 166), and `remote` bridge argv mapping. `tests/test_remote_execution.py` ships the reusable `FakeAdapter` (`Adapter` ABC, six ops, counter ids, `fetch` writes `result.txt`) plus `MultiWorkerFakeAdapter`, both exercised against ledger/packer/`remote_cli` internals — never through `executor._remote_command`. Unproven: `target set` persistence round-trip via CLI, `check` matrix (kaggle reachable/unreachable, ssh reachable/unreachable/missing-host, unknown name, unsupported provider), real local failure/timeout/OSError mapping, kaggle real dispatch with/without consent and `--unit` forwarding, ssh-sbatch argv shape and real-dispatch mapping, ledger `dry_run: false` + failing-exit rows, `target_override` precedence, entrypoint-extraction fallbacks.

Hermetic seams already exist and the existing suite shows the pattern: `mock.patch.object(executor.subprocess, "run")`, `mock.patch.object(target.subprocess, "run")`, patch `bridges.python.run_script` for the kaggle leg, `shutil.which` for the local leg, `_workspace()` + `_write_local_manifest()` fixtures (extend the manifest with `kaggle-gpu-pool`/`slurm-cluster` targets mirroring `templates/papersmith.yaml.tpl`). No live network or credential is needed; `kaggle-accounts`, audit, deliberate/implement/remote legs are out of scope per the brief.

### Affected Areas

- `src/papersmith/core/target.py` — set persistence (`config.write_json`), check connectivity seams (`shutil.which`, `run_script`, `subprocess.run`), `run_cli` print/exit paths
- `src/papersmith/core/executor.py` — `_remote_command` argv building, `_slurm_command` argv building, `run_profile` dry-run vs real branches per provider, `mapped_returncode`/`OSError` mapping, `ledger.append` rows
- `src/papersmith/core/ledger.py` — `runs_ledger.jsonl` read-back assertions for new dispatch tests (no change, read-only consumer)
- `src/papersmith/core/config.py` + `src/papersmith/schema.py` — fixture manifests must satisfy `KNOWN_PROVIDERS = ("local", "kaggle", "remote-ssh")` and `active_compute_target` validation
- `tests/test_papersmith_executor.py` — where all new coverage lands (existing `mock.patch.object` + `_workspace` patterns to extend)
- `tests/test_remote_execution.py` — `FakeAdapter`/`MultiWorkerFakeAdapter` reference for the consented-submit shape; read-only, not modified
- `skills/remote-execution/SKILL.md` + `skills/kaggle-accounts/SKILL.md` — doctrine for consent gate (`--consent` token, `--unit` campaign scoping) and `materialize`/`list --json` contract; read-only, constrains what executor tests may assert

### Approaches

1. **Sealed-seam mocking at the subprocess boundary** — extend `test_papersmith_executor.py` with `mock.patch.object` on `executor.subprocess.run`, `target.subprocess.run`, and `bridges.python.run_script` (+ `shutil.which`); assert return codes, `reachable` flags, argv shapes, consent/`--unit` forwarding, and ledger rows. Fixtures add kaggle + remote-ssh targets to the manifest.
   - Pros: fully hermetic (no network, no credentials, no PATH games); fastest; matches the file's existing idiom so review load is minimal; covers the whole check matrix and all three dispatch legs including failure/timeout/OSError paths
   - Cons: mocks can drift from real `remote_cli.py`/`ssh` behavior; proves argv construction, not that the constructed argv actually runs
   - Effort: Low

2. **Fake executables on PATH (`ssh`, `accounts_cli`) + CLI-level `main()` wiring** — stub `ssh` with a shell script that records argv and exits 0/1; stub the kaggle leg by patching `run_script` to return `CompletedProcess`; drive everything through `papersmith.cli.main(["target", ...])` / `["run", ...]` and assert stdout + exit codes.
   - Pros: proves argparse wiring (`register`/`run_cli` handlers), print formats, and exit-code contract end to end; catches CLI-only regressions Approach 1 misses (e.g. `target set` via handler not persisting)
   - Cons: PATH manipulation and fixture scripts are flakier and slower; still does not prove the remote submit actually lands (that is the skill suite's job)
   - Effort: Medium

3. **In-process FakeAdapter through real `remote_cli`** — import `skills/remote-execution/scripts/remote_cli.py`, register `FakeAdapter`, and drive `cmd_submit` to prove consented-submit + ledger semantics behind executor's argv.
   - Pros: highest fidelity for remote semantics (consent token binding, `--unit` campaign scoping, ledger event shape)
   - Cons: couples `papersmith-ai` CLI tests to skill internals that already have a 20k-line suite; does not test `executor._remote_command`'s own translation (entrypoint scraping, fallback, backend default) which is the actual unproven code; heaviest to write and review; risks duplicating `test_remote_execution.py`
   - Effort: High

### Recommendation

Approach 1 as the backbone, plus the thin CLI-wiring slice of Approach 2. Concretely: a `target check` matrix (local/kaggle-up/kaggle-down/ssh-up/ssh-down/missing-host/unknown-name/unsupported-provider), a `target set` persistence round-trip (`set_target` then `load_workspace_config` + CLI `set` variant), and a `run` dispatch matrix (local real success + nonzero + timeout + OSError; kaggle dry-run argv + real consented submit with `--unit` forwarding via mocked `subprocess.run`; ssh-sbatch dry-run argv with partition/walltime + real mocked dispatch; `target_override` precedence; entrypoint fallback to `runner.ipynb`; failing-exit ledger rows). Drive two or three of those through `main()` to lock the handler wiring. Reject Approach 3 for this change: the FakeAdapter seam is already proven where it lives, and this change's gap is the thin CLI translation above it, not the skill below it.

### Risks

- Mock drift: `subprocess.run` patches assert argv shapes that a future `remote_cli.py` flag rename could invalidate without breaking these tests — mitigate by asserting only the flags this repo owns (`submit/--target/--entrypoint/--backend/--unit/--consent`, `sbatch/--wrap`) and leaving skill-flag semantics to `test_remote_execution.py`
- Fixture manifests must stay schema-valid (`compute_targets.default` names a configured target, profile `target` exists); copy shapes from `templates/papersmith.yaml.tpl` rather than inventing new ones
- `executor.py` forwards `consent=None` today (gate enforced downstream); tests must assert pass-through, not invent a gate here, or they will conflict with the skill's consent doctrine
- Review budget: the matrix is ~10-14 small tests; keep each to one seam and one assertion family or the 800-line review budget in preflight will be breached — split into stacked slices (target leg, run leg) if it grows
- Live-network temptation: `check_target` kaggle/ssh legs and `PIN_PUBLISHED`-style probes must stay mocked; any test reaching the network or real credentials violates the brief and flakes CI

### Ready for Proposal

Yes — scope is bounded (two modules + one test file, no implementation files created by this exploration), seams are identified, hermetic patterns exist, and out-of-scope legs are named. The orchestrator should tell the user the proposal will add hermetic `target set/check` + `run` dispatch tests only, via sealed-seam mocking plus CLI wiring, with no live network or credential use.
