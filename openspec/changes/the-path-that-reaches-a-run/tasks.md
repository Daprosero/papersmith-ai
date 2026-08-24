# Tasks: the-path-that-reaches-a-run

Baseline: `python3 -m unittest discover -s tests` → 1160 tests, OK. HEAD `3b1590a`, tree clean.
TDD-with-inversion applies to every RED task below: write test → run → paste failure → implement → pass → invert the guarded **effect** (never the operator, never a call-twice determinism check) → watch it fire → restore by **inverse patch** (never `git checkout --`, never `str.replace("", ...)`) → confirm restore by `sha256` of the whole file.
Finding 10 (`search_ceilings` `KeyError`, `implementations/Domain_Adaptation/harness.py:835-840`) is a recorded handoff. **No task here.**

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~900–1200 (8 commits, roughly 100–220 each) |
| 400-line budget risk | High in aggregate vs. the default 400-line single-review budget; Low–Medium per individual commit |
| Chained PRs recommended | Yes (as ordered commits — see note) |
| Suggested split | 8 ordered commits, ladder below |
| Delivery strategy | Session-established: **ordered commits on `main`, no branches/PRs, the commit is the reviewable unit**, budget 1200 authored lines |
| Chain strategy | Mapped to `stacked-to-main` for guard compatibility — no closer literal enum exists; each commit lands to `main` in order, independently `git revert`-able |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units (= the 8 design commits)

| Unit | Goal | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|
| 1 | Accelerator declare+gate (Decisions 1,2) | `python3 -m unittest tests.test_remote_execution -k Accelerator` | N/A — fake `torch`/`hardware_import` double, no Kaggle launch | Revert restores silent 42s CUDA death |
| 2 | Dual-arch torch build (Decision 3) | `-k Install` | N/A — argv-capture double | Revert removes `environment.install`, no pip step added |
| 3 | Spread consumption (Decisions 6,7) | `-k Distribute or CampaignSubmit` | N/A — adapter double | Revert restores first-healthy-only `select()` |
| 4 | Consent gate (Decisions 4,5) | `-k Consent` | N/A — argv-only | Revert restores today's ungated `submit` (named risk) |
| 5 | env + liveness (Decisions 8,9,12) | `-k Env or Introspect` | Built local target-tree fixture, prescribed interpreter subprocess, no launch | Revert restores the deadlock |
| 6 | Harness + gate agreement (Decisions 10,11) | `-k Harness or ScaleSatisfied` | N/A — fixture-based | Revert restores `harness: null` + gate disagreement |
| 7 | Three refusal messages (Decision 13) | `-k PinPublished or Entrypoint or ProductFor` | N/A — message-only | Inert; revert restores misdirecting text |
| 8 | Guiding table doctrine (Decision 14) | `-k GuidingTable` | N/A — parser-derived prose check | Inert; defers first if budget tightens |

---

## Phase 1 — Accelerator declare + gate (Findings 1; Decisions 1, 2)

- [x] 1.1 RED `tests/test_remote_execution.py`: `build_run_config` writes `accelerator: {kind, architectures[]}`. Run, fail, paste.
- [x] 1.2 GREEN `jobfolder.py::build_run_config`: add the field (names only, no device value).
- [x] 1.3 Invert (disable the write) → confirm fails → restore by inverse patch, confirm by `sha256`.
- [x] 1.4 RED: `runner_bootstrap.py` writes `bootstrap.json` (responsibility ≤7) **before** any `AcceleratorError`; gate becomes responsibility 8.
- [x] 1.5 GREEN: capture `environment.archList` (`torch.cuda.get_arch_list()`) + `capability` (`torch.cuda.get_device_capability()`) beside `environment.torch`; reorder gate after `write_bootstrap_output()`.
- [x] 1.6 RED: arriving `capability` outside installed `archList` refuses in cell 0, evidence already on disk.
- [x] 1.7 GREEN: implement assertion 1 (`capability ∈ archList`); raise `AcceleratorError` (`SystemExit`).
- [x] 1.8 Invert strongest case: disable this refusal with a fake-double capability outside `archList` → confirm training would proceed → restore by inverse patch + `sha256`.
- [x] 1.9 RED: declared `architectures` not covered by installed `archList` refuses (verifies the dual-arch build rather than assuming it — assertion 2).
- [x] 1.10 GREEN: implement assertion 2. Invert/restore per lock discipline.
- [x] 1.11 `remote-execution/SKILL.md`: document the accelerator contract (declare → compare → refuse before training).

## Phase 2 — Dual-architecture torch build (Finding 1; Decision 3)

- [x] 2.1 RED: `build_run_config` writes additive `environment.install: {requirements[], indexUrl}`.
- [x] 2.2 GREEN `jobfolder.py`: construct the block (fields only, no hardcoded package).
- [x] 2.3 RED: `runner_bootstrap.py` runs `sys.executable -m pip install` with list argv, **before** responsibility 4 (declared-module import).
- [x] 2.4 GREEN: implement install step — `PATH`-only env, explicit timeout, non-zero exit refuses (threat-matrix subprocess row).
- [x] 2.5 RED: a requirement specifier beginning with `-` (e.g. `--index-url evil`) refuses; a shell-shaped manifest entry installs only as inert data.
- [x] 2.6 GREEN: validate specifiers before invoking pip.
- [x] 2.7 Invert (disable the specifier-prefix guard) → confirm the malicious spec passes → restore by inverse patch + `sha256`.
- [x] 2.8 RED: pip timeout refuses; non-zero exit refuses; no shell is ever invoked.
- [x] 2.9 GREEN: implement. Integration: fake `torch` double covering both `sm_60`/`sm_75` confirms `environment.torch`+`archList` recorded post-install.

## Phase 3 — Full healthy-account spread consumption (Finding 2; Decisions 6, 7)

- [x] 3.1 RED `tests/test_remote_execution.py`: `cmd_submit` with repeatable `--unit` switches to campaign mode and calls `PACKER.distribute()`, not `select()`.
- [x] 3.2 GREEN `remote_cli.py::cmd_submit` (`:491`): add `--unit` (same flag `distribute` declares); branch to campaign mode.
- [x] 3.3 RED: campaign result reports `assignments[]`/`unplaced[]`/`skipped[worker→reason]` straight from `Distribution`/`Skip.reason`, one `adapter.submit()` + one ledger event per assignment.
- [x] 3.4 GREEN: implement per Decision 7 — no new triage logic, carry `Distribution` unchanged.
- [x] 3.5 RED regression lock: single-unit `submit` (no `--unit`) stays byte-identical to today's `select()`/`plan()` path.
- [x] 3.6 Invert: swap `distribute()` back to `select()` inside the campaign branch → confirm a four-of-five-healthy campaign only reaches the first account → restore by inverse patch + `sha256`.
- [x] 3.7 `remote-execution/SKILL.md`: document the spread guarantee — every healthy account, exclusions named with reason.

### Phase 3 Addendum — user-required additions (session prompt, not in original tasks.md)

- [x] 3A.1 `adapters/kaggle.py`: declare `KAGGLE_ACCELERATOR_KIND`/`KAGGLE_ACCELERATOR_ARCHITECTURES` beside `KAGGLE_WORKER_CAPACITY`, same honest "observed, not a law" framing — service knowledge, never a forge default.
- [x] 3A.2 `adapter.py`: a third registry (`register_default_accelerator`/`resolve_default_accelerator`), the same shape as `register_metadata`, so `jobfolder.py` can ask a service adapter for its default without naming it.
- [x] 3A.3 `jobfolder.py::generate_job()`: thread `accelerator_kind`/`accelerator_architectures`/`environment_requirements`/`environment_index_url` down to `build_run_config` (currently absent from the fifteen-plus params passed at `:861`); when neither accelerator half is given, resolve a default from `ADAPTER.resolve_default_accelerator(service)`.
- [x] 3A.4 `remote_cli.py`: `generate-job` gains `--accelerator-kind`/`--accelerator-architecture` (override) and `--environment-requirement`/`--environment-index-url` (target's own declared install — never a forge default).
- [x] 3A.5 Invert strongest case: disable the default-accelerator resolution in `generate_job()` → confirm a from-zero job generates with no `accelerator` block (unprotected) → restore by inverse patch + `sha256`.

## Phase 4 — Per-campaign consent gate (Finding 3; Decisions 4, 5) — turns today's green `submit` tests red

- [x] 4.1 Grep every existing `cmd_submit` test lacking a consent token; list them so the update is visible in the diff, not folded silently elsewhere.
- [x] 4.2 RED: `submit` without `--consent` refuses.
- [x] 4.3 GREEN `remote_cli.py`: add `--consent <token>`; refuse when absent; read **only** from parsed argv.
- [x] 4.4 RED: token = `sha256(pin commit, relative entrypoint, ordered unit list)`, printed by `distribute`; `submit` recomputes it from the job folder's own declared commit (`JOBFOLDER.read()`) + argv unit list, and refuses on mismatch.
- [x] 4.5 GREEN: shared token-derivation function used by both `distribute`'s print and `submit`'s verify.
- [x] 4.6 RED (commit-state threat-matrix case): a token minted at pin A refuses at pin B.
- [x] 4.7 RED (Decision 5 scope): added, removed, or reordered units in the invocation refuse against the minted token.
- [x] 4.8 GREEN: bind the check to exact ordered-unit-list equality.
- [x] 4.9 RED: whole-tree hash snapshot across two invocations proves nothing on disk stores consent (no config, no env var, no ledger line).
- [x] 4.10 RED: a cross-campaign token (minted for a different unit set) refuses.
- [x] 4.11 Invert strongest case: disable the ordered-unit-list equality check → confirm a token minted for a smaller unit set still authorizes a campaign whose unit list grew → restore by inverse patch + `sha256`.
- [x] 4.12 Update every test listed in 4.1 to pass `--consent` explicitly — this update must be its own visible diff hunk.
- [x] 4.13 `remote-execution/SKILL.md`: document the authorization contract — per-campaign, argv-only, never persisted, and the honest limit: no gate can prove a human was present, only that the launch was deliberate, bound and unstored.

## Phase 5 — env provisioning + executed-evidence liveness (Findings 5, 6; Decisions 8, 9, 12)

- [x] 5.1 RED `tests/test_proposal_implementation.py`: `cmd_env`'s `nextCommand` lists forge dev-reqs first, then honoured target manifests last (`requirements.txt`, target's `requirements-dev.txt`, `-e .` when `pyproject.toml`/`setup.py`/`setup.cfg` exists) — names only from `ROOT_KEEP` (`:103`).
- [x] 5.2 GREEN `implementation_cli.py::cmd_env` (`:4216`): build the single pip-install invocation per Decision 8 ordering; `environment.yml` present → reported `unhonoured` with reason; none present → `manifests: []`, stated absence.
- [x] 5.3 RED (forge-vocabulary guard): no hardcoded package name appears in `cmd_env`'s construction — manifest filenames only.
- [x] 5.4 RED: `introspect()` (`:2991`) reports live only after **executing** an import of the declared entry module inside `<target>/.venv`; an empty venv whose pure-Python config imports fine → `live: unavailable`, real last line quoted verbatim.
- [x] 5.5 GREEN: execute the entry-module import via the prescribed interpreter subprocess; on failure return `unavailable` + verbatim last stderr line.
- [x] 5.6 RED: `nextStep` does not advance past `env-first` (Decision 12: new rung right after `declare-first`) while `live ≠ ok`.
- [x] 5.7 GREEN: insert the `env-first` rung.
- [x] 5.8 Invert strongest case: stub `introspect` to report `ok` without executing anything → confirm `probe` reports live on a venv that cannot import the entry module → restore by inverse patch + `sha256`.
- [x] 5.9 Integration: built target-tree fixture — prescribed interpreter runs the target's own manifest-declared deps with no `ModuleNotFoundError`, and the repo's own interpreter refusal (`harness.py:76-81`, out of scope to edit) is not triggered.

## Phase 6 — Harness resolution + gate agreement (Findings 7, 8; Decisions 10, 11)

- [x] 6.1 RED: `assets/kit/src_benchmark/__init__.py` scaffold test — `__benchmark__` gains a seventh block `entry: {module, function}`, prefilled empty; update the "six blocks" scaffold test to seven (non-additive cost, named explicitly).
- [x] 6.2 GREEN: add the `entry` block verbatim per the Interfaces/Contracts spec.
- [x] 6.3 RED: `probe_state` (`:1634`) reports `harnessStatus: undeclared` when `entry.module` is empty; declared+present → path; declared+missing → `declaredMissing` naming the declared name and searched path. `BENCHMARK_MODULE` (`:1415`) stops being the primary lookup, reachable only as the scaffold default.
- [x] 6.4 GREEN: read `entry.module` from the declaration; implement the three-way branch.
- [x] 6.5 RED: one absent-harness-file target vs. one present-under-declared-name target — distinguished without a second hardcoded name (forge-vocabulary guard applies).
- [x] 6.6 RED: `search_state` (`:691`) reads declared `search.requiredScale`, compares against the record's own recorded scale along declared axis names, returns `recordScale` + tri-state `scaleSatisfied` (`true`/`false`/`null`).
- [x] 6.7 GREEN: implement per Decision 11 — `scaleSatisfied: null` (record names none of the declared axes) advances neither gate.
- [x] 6.8 RED: `nextStep` does not report `benchmark`/`piloted` while `scaleSatisfied` is `false` or `null`; the below-scale case reuses `search-first` with a `reason` (Decision 12).
- [x] 6.9 GREEN: wire `scaleSatisfied` into the `nextStep` gate.
- [x] 6.10 Invert strongest case: default `scaleSatisfied` to `true` when the record has no matching axis (disable the null branch) → confirm `nextStep: benchmark` advances on an unprovable precondition → restore by inverse patch + `sha256`.
- [x] 6.11 `proposal-implementation/SKILL.md`: document the seventh scaffold block.

## Phase 7 — Three misdirecting refusals, each its own case (Finding 4; Decision 13) — fixes the spec's flagged thinness

- [ ] 7.1 RED (case A — `pin-published`): a pushed commit transferring 12.4 MiB on a slow link (measured 209s, then 27s re-run same commit) must not report "not pushed" from transfer time alone; the scratch-repo probe still never runs in `target`.
- [ ] 7.2 GREEN `jobfolder.py` (`:910`): add `PIN_PUBLISHED_TIMEOUT_SECONDS`, separate from `GIT_TIMEOUT_SECONDS` (120s) — set to **240s** (≈1.15× the measured 209s worst case, rounded up, giving headroom above the observed worst case while staying bounded); pass it to the `pin-published` `_run_git` call only.
- [ ] 7.3 Invert: reuse `GIT_TIMEOUT_SECONDS` for the pin-published probe (disable the separation) → confirm the slow-transfer case regresses to "not pushed" → restore by inverse patch + `sha256`.
- [ ] 7.4 RED (case B — `--entrypoint`): a valid job folder (directory holding `run-config.json` + `runner.ipynb`) passed to `--entrypoint` reports "a file was expected, notebook is at `<path>`" — never "regenerate a job".
- [ ] 7.5 GREEN `remote_cli.py::guard_entrypoint` (`:374`): detect the directory-holding-job-folder shape; name the notebook inside it.
- [ ] 7.6 Invert (disable shape detection) → confirm the folder input still misdirects to regenerate-job → restore by inverse patch + `sha256`.
- [ ] 7.7 RED (case C — `status --product`): a `status` invocation lacking `--product` must not refuse citing a flag `status`'s own parser never declares; test reads `_build_parser()`'s `status` subparser actions directly.
- [ ] 7.8 GREEN `remote_cli.py::product_for` (`:182`): derive the remedy from the calling subcommand's actual declared flags, never hand-written prose.
- [ ] 7.9 Invert (revert to hand-written status message) → confirm `status` refuses citing `--product` → restore by inverse patch + `sha256`.
- [ ] 7.10 `remote-execution/SKILL.md`: note refusal messages are parser-derived.

## Phase 8 — Guiding table doctrine (Finding 9; Decision 14) — defers first if the 1200-line budget tightens

- [x] 8.1 RED `proposal-implementation/SKILL.md`: parser-derived test reads `_build_parser()`'s subparser actions; asserts every table row names its applicable flags, and a stale-pin row exists (job folder exists, `staleness: drift` → `generate-job`).
- [x] 8.2 GREEN: add the flags column (`readiness` lists `--job-dir`/`--worker`, never `--target`/`--entrypoint`); add the stale-pin row.
- [x] 8.3 Invert (remove the stale-pin row) → confirm the parser-derived test fails → restore by inverse patch + `sha256`.
- [x] 8.4 Confirm final suite count = 1160 + total tests added across Phases 1–8; a suite merely staying green is not evidence, and a test green on first write covering already-held behaviour counts as coverage, not a caught defect.

---

**Hard scope reminder for every phase**: editable surface is exactly `.claude/skills/proposal-implementation/`, `.claude/skills/remote-execution/`, and their tests. Never `implementations/Domain_Adaptation`, never `openspec/config.yaml`. Run the forge-vocabulary guard after each phase. Nothing is launched to Kaggle by any task above.
