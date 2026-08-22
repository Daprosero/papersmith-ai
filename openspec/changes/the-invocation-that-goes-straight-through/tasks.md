# Tasks: the-invocation-that-goes-straight-through

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900-1100 (adapter ~250, driver ~200, tests ~400, doctrine ~80) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 5 ordered commits on `main` (this repo has no branches/PRs) |
| Delivery strategy | single-pr (cached) |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Conflict to resolve before apply**: cached `single-pr` normally maps to "require `size:exception`," but this repo has no PR mechanism and design already mandates 5 independently-revertible ordered commits. Recommendation: treat each commit below as the `single-pr` guard's reviewable unit (equivalent to `stacked-to-main`) rather than compress into one commit. Orchestrator must confirm this reading with the user before `sdd-apply`. Report the overrun; do not shrink scope to fit it.

### Suggested Work Units

| Unit | Goal | Commit | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Driver + inner interception (proves Bearer crosses, offline) | 1 | `python3 -m unittest tests.test_remote_execution.DriverInterceptionTests` | N/A — offline only, no live launch | Delete `kaggle_driver.py` + its test class; nothing else touched |
| 2 | `submit` wired through the driver, outer interception | 2 | `python3 -m unittest tests.test_remote_execution.SubmitDriverWiringTests` | N/A — offline only | Revert `submit()`/`_push()`/`_run()` to CLI shellout; delete outer-interception tests |
| 3 | `poll`/`fetch` wired through the driver | 3 | `python3 -m unittest tests.test_remote_execution.PollFetchDriverTests` | N/A — pending rehearsal permission (open question) | Revert `poll()`/`fetch()` to CLI shellout |
| 4 | Auto-selection + rebuilt capacity metering | 4 | `python3 -m unittest tests.test_remote_execution.WorkerSelectionAndMeteringTests` | N/A — offline only | Revert `--worker` to required; delete `packer.select()`/`WorkerUnauthorized` |
| 5 | Doctrine, `## Environment`, pin+drift | 5 | `python3 -m unittest tests.test_remote_execution.DoctrinePinTests` | N/A — static/text only | Revert `requirements.txt` line + `SKILL.md` sections |

## Phase 1: Driver + inner interception (Commit 1 — proves the credential authenticates, without launching anything)

- [x] 1.1 RED: `test_driver_client_constructed_at_one_locked_expression` (AST lock, C5's `.token_path` idiom) — write, run, paste failure.
- [x] 1.2 RED: `test_driver_names_kagglesdk_nowhere_in_adapter` scanning `adapters/kaggle.py` — write, run, paste failure.
- [x] 1.3 RED: `test_unique_class_def_names_in_test_file` over `tests/test_remote_execution.py` — write, run.
- [x] 1.4 RED: `test_inner_interception_reached_count` — recording `requests` transport, count>0 before content — write, run, paste failure.
- [x] 1.5 GREEN: create `adapters/kaggle_driver.py` — only file importing `kagglesdk`; ops `submit`/`poll`/`fetch`/`selftest`; JSON stdout; exit 0/3/other; client built at one locked expression.
- [x] 1.6 GREEN: mount recording transport in driver's test fixtures; make 1.1-1.4 pass.
- [x] 1.7 INVERT 1.1: add a second ad hoc client build in an operation function; confirm fail; restore by inverse patch; confirm sha256.
- [x] 1.8 INVERT 1.2: temporarily import `kagglesdk` in `adapters/kaggle.py`; confirm fail; restore by inverse patch; sha256.
- [x] 1.9 INVERT 1.3: duplicate a `ClassDef` name; confirm fail; restore by inverse patch; sha256.
- [x] 1.10 RED→GREEN: `test_driver_selftest_imports_kagglesdk` against `sys.executable`; refusal names exact interpreter + install command.
- [x] 1.11 RED→GREEN: `test_wire_bearer_header_carries_token_value` — the request that first proves the credential authenticates, offline.
- [x] 1.12 RED→GREEN: `test_enable_gpu_and_enable_internet_on_wire`.

## Phase 2: `submit` wired through the driver (Commit 2)

- [ ] 2.1 RED: `test_outer_interception_reached_count` — fake driver on injected `PATH`, argv+env recorded, count>0 first.
- [ ] 2.2 RED: `test_metadata_id_maps_to_slug_never_int_id` (the `id`-is-`int` trap).
- [ ] 2.3 RED: `test_unmapped_metadata_key_refuses` (closed-table refusal).
- [ ] 2.4 RED: `test_sentinel_absent_from_argv`, `test_exact_env_allowlist_submit` (threat-matrix subprocess/argv addendum).
- [ ] 2.5 GREEN: retarget `submit()`/`_push()` in `adapters/kaggle.py` to invoke `kaggle_driver.py` via `sys.executable`; staging dir on argv; map metadata → `ApiSaveKernelRequest` per Decision 4's table; refuse on unmapped key.
- [ ] 2.6 GREEN: rewrite `_run`'s remedy sentence (was `pip install kaggle`) to name the SDK-path install command for the interpreter in play.
- [ ] 2.7 Run 2.1-2.4 green; confirm suite count rises.
- [ ] 2.8 INVERT 2.1: call driver inline instead of via subprocess; confirm fail; restore by inverse patch; sha256.
- [ ] 2.9 INVERT 2.2: revert mapping to `id=owner/slug`; confirm fail; restore; sha256.
- [ ] 2.10 RED→GREEN: `test_two_concurrent_submissions_uncrossed_credentials` — genuine time overlap, two driver processes.

## Phase 3: `poll`/`fetch` wired through the driver (Commit 3)

- [ ] 3.1 RED→GREEN: retarget `poll()` to driver's `get_kernel_session_status`; update status-translation test.
- [ ] 3.2 OPEN QUESTION, named not solved: does `list_kernel_session_output`'s URLs need session auth? Resolution step: a rehearsal, run only on the user's explicit permission — not scheduled here.
- [ ] 3.3 RED→GREEN: implement `fetch()` file-by-file via `list_kernel_session_output` + session `log`; if 3.2 unresolved, attach auth defensively and mark the doctrine row `unverified-by-rehearsal`.
- [ ] 3.4 RED→GREEN: `test_fetch_never_relies_on_kernel_session_id_from_status_response`.

## Phase 4: Auto-selection + rebuilt capacity metering (Commit 4)

- [ ] 4.1 Add `WorkerUnauthorized(AdapterError)` to `adapter.py`; narrow `packer.plan()`'s `except Exception` (packer.py:159) so it propagates instead of degrading to ledger silently.
- [ ] 4.2 RED→GREEN: `test_plan_propagates_worker_unauthorized_not_ledger_fallback`.
- [ ] 4.3 Add `packer.select()`: walk `adapter.workers()` in declared order, first `granted >= 1`; skip unhealthy; never gates an explicit `--worker`.
- [ ] 4.4 RED→GREEN: `test_select_skips_revoked_account_among_five`.
- [ ] 4.5 RED→GREEN: `test_select_refuses_when_all_five_unhealthy_naming_reason`.
- [ ] 4.6 RED→GREEN: `test_explicit_worker_naming_revoked_account_refuses_with_remedy_no_fallback` — no quota spent.
- [ ] 4.7 `remote_cli.py:1296`: make `submit`'s `--worker` optional; call `packer.select()` when absent.
- [ ] 4.8 RED→GREEN: `test_submit_with_no_worker_all_healthy_completes_end_to_end`, `test_previously_dying_invocation_now_reaches_observed_request`.
- [ ] 4.9 Decide+document the other three `required=True` sites — `reconcile` (`remote_cli.py:1362`), `smoke record` (`:1441`), `readiness` (`:1449`): each keeps `required=True`; add one code comment per site + one `SKILL.md` selection-policy line stating why (each targets one already-known account's local state, not a new submission decision — Group 1's "no fork" scope does not extend to them). Flip to optional+select instead if this reasoning is rejected at apply time — never leave unaddressed.
- [ ] 4.10 Rebuild capacity metering in `adapters/kaggle.py`: `list_kernels(group=PROFILE, sort_by=DATE_RUN)` + `get_kernel_session_status` per ref, first page only; wire into health/`list_active()`.
- [ ] 4.11 RED→GREEN: `test_metering_derives_in_flight_via_rebuilt_path`.
- [ ] 4.12 RED→GREEN: `test_metering_refuses_naming_remedy_when_list_kernels_fails_structurally`.
- [ ] 4.13 INVERT 4.2: force `list_kernels` to raise generically; confirm fail; restore by inverse patch; sha256.

## Phase 5: Doctrine, `## Environment`, pin + drift (Commit 5)

- [ ] 5.1 `requirements.txt:4`: `kaggle>=1.7` → `kaggle==1.7.4.5`; comment quotes the mid-migration source note.
- [ ] 5.2 RED→GREEN: `test_pin_matches_installed_kaggle_version`.
- [ ] 5.3 RED→GREEN: `test_drifted_installation_fails_naming_both_versions`; invert by monkeypatching the installed version; confirm fail; restore; sha256.
- [ ] 5.4 Rewrite `SKILL.md`'s credential-transport table: keep the seven prior rows verbatim (sink renamed); add `reached`, `no-sdk-above-the-driver`, `wire-bearer`; every row cites its test name.
- [ ] 5.5 RED→GREEN: `test_every_transport_table_row_maps_to_a_passing_test`.
- [ ] 5.6 Retire `## Environment`'s stdlib-only sentence outright; restate "stdlib-only except one named driver script"; correct the false "Requires Python 3.10+" line to measured reality (no enforced minimum; the selftest, not a version check, is what gates).
- [ ] 5.7 RED→GREEN: `test_the_retired_stdlib_only_claim_survives_nowhere` (precedent idiom) scanning `SKILL.md`, adapter, seam, `credentials.py`, driver.
- [ ] 5.8 RED→GREEN: confirm the generality guard runs clean against every file this change touches.
- [ ] 5.9 Run `python3 -m unittest discover -s tests`; confirm total = 1084 + N, reported as a rise.

## Phase 6: Closing verification (cross-cutting, no new files)

- [ ] 6.1 Confirm nothing was launched to Kaggle; the fetch rehearsal (3.2) stays unscheduled pending explicit user permission.
- [ ] 6.2 Confirm `implementations/Domain_Adaptation` and `openspec/config.yaml` remain untouched.
- [ ] 6.3 Report the final count-rise (baseline 1084 → new total) exactly, not as a bare "OK".

*Size note: this artifact exceeds the 530-word budget because the change brief mandates five independently-revertible commits, three bypass-detection locks each requiring its own RED/GREEN/invert/restore cycle, a distinct decision for four `--worker`-required call sites, and two explicitly-named open questions — compressing further would produce the vague tasks the writing rules forbid.*
