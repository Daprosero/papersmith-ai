```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:5ac7159e84378f290a1348f2c73c8e1e355b9956121a2cd72acb87398fb07e83
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 11/11
scenarios: 30/30
test_command: python3 -m unittest discover -s tests
test_exit_code: 0
test_output_hash: sha256:38ff7fc28dea07d9ba52011b7a5d4a72ab722d5d2a97b33fd3679c1eda5579fb
build_command: python3 -m compileall -q .claude/skills/remote-execution/scripts tests
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report

**Change**: `the-pin-the-runner-can-actually-fetch`
**Version**: spec artifact at `<scratchpad>/the-pin-the-runner-can-actually-fetch-spec.md` (11 requirements, 30 scenarios)
**Mode**: Strict TDD (C3) — full artifact set: proposal, explore, spec, design, tasks, apply-progress
**Evidence revision**: `c4ee27f`, branch `main`, working tree clean, `ahead 8`, nothing pushed
**Artifact store**: engram disconnected — report written to the scratchpad path above

Nothing in this report is taken from the apply record on trust. Every count was
re-measured, every condition was exercised against real git fixtures built for
this verification, and every reproduced inversion was applied to the working
tree and restored by writing the pristine bytes back (never `git checkout --`),
with `cmp` confirming byte-identity afterwards.

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 43 (`- [x]`/`- [ ]` items in the tasks artifact) |
| Tasks complete | 43 |
| Tasks incomplete | 0 |
| Carried open questions | Q1, Q2, Q3 — all answered in the apply record and confirmed here |

### Build & Tests Execution

**Build**: PASSED — `python3 -m compileall -q .claude/skills/remote-execution/scripts tests`, exit 0, empty output.

**Tests**: PASSED, measured by this verifier, twice (before and after the inversion series):

```text
python3 -m unittest tests.test_remote_execution   → Ran 335 tests — OK
python3 -m unittest discover -s tests             → Ran 872 tests — OK
```

Both figures match the orchestrator's independent measurement (335 / 872).
The spec's acceptance clause asks for "791 plus the new tests": 791 + 81 = 872. Met exactly.

**Counts rose rather than merely stayed green.** Re-derived independently by
AST-parsing `tests/test_remote_execution.py` at every commit blob, counting
`test_*` methods and checking for redefined classes — the exact incident that
once silently disabled seven tests here:

| Commit | Classes | Tests | Δ | Duplicate class names |
|---|---|---|---|---|
| `6460587` (pre-change) | 35 | 253 | — | none |
| `a60e5d0` | 36 | 254 | +1 | none |
| `26d8e57` | 37 | 264 | +10 | none |
| `b7cb43f` | 38 | 275 | +11 | none |
| `9224be9` | 39 | 292 | +17 | none |
| `3ef8dc8` | 41 | 309 | +17 | none |
| `82ceda7` | 42 | 321 | +12 | none |
| `726dd76` | 43 | 333 | +12 | none |
| `c4ee27f` | 44 | 335 | +2 | none |

Every delta equals the apply record's claim. `rg '^class ' | sort | uniq -d` is
empty for `tests/test_remote_execution.py` and for every other file in `tests/`.

**Coverage**: not available — this repository configures no coverage tool.

### Fixtures built for this verification

A two-repository real-git fixture under `implementations/_verify-pin`, deleted
afterwards (`git status --porcelain` empty at the end):

- `origin.git` — a bare repository serving as the declared remote, so condition (3) ran against a real `upload-pack` rather than a mock.
- `target/` — a working clone with `src/pkg/harness.py` under the declared clone path and `README.md` outside it.
- `target/pkg/` — the product directory, so `product_for()` resolved and `submit` could reach the gate.
- A non-repository target under the scratchpad (outside any enclosing repository, which the `implementations/` box could not be) for the "cleanliness cannot be proven" case.
- An independent `cmd_submit` driver with its own `FakeAdapter` and `source_digest`, counting adapter calls and diffing `*.jsonl` bytes before and after — written for this verification, not borrowed from the suite.

### Spec Compliance Matrix

All tests are in `tests/test_remote_execution.py`. "Behavioural" marks a
scenario I also exercised myself, outside the suite, on the fixture above.

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| G1 A pin MUST be a commit, not a name | A branch name is refused | `CommitShapeTests > test_a_branch_name_refuses_generation_and_writes_no_job_folder`, `…_is_refused_and_the_message_names_it` | COMPLIANT (behavioural: `--commit main` → exit 1, message names `main`, no job folder) |
| G1 | A full hex pin is accepted | `CommitShapeTests > test_a_lowercase_forty_hex_pin_is_accepted`, `test_a_forty_hex_pin_generates_a_job_folder_unchanged` | COMPLIANT (behavioural) |
| G1 | Uppercase or truncated hex is refused | `CommitShapeTests > test_uppercase_hex_is_refused`, `test_an_abbreviated_hex_pin_is_refused` | COMPLIANT (behavioural: `D903D14…` and `9bfb3df` both exit 1, naming the value) |
| G2 Reachability proven from a repo that does not hold the pin | A pin that exists locally and was never pushed | `CommitReachabilityTests > test_refuses_a_commit_that_exists_locally_and_was_never_pushed` | COMPLIANT (behavioural: unpushed HEAD refused, naming commit + remote URL, no job folder) |
| G2 | A published pin passes | `CommitReachabilityTests > test_a_published_commit_passes_without_depositing_objects_in_the_target` | COMPLIANT (behavioural: object count 24→24, `show-ref` identical, `FETCH_HEAD` absent before and after) |
| G2 | The question cannot be asked at all | `CommitReachabilityTests > test_refuses_when_the_scratch_directory_itself_cannot_be_made`, `…_cannot_be_initialised`, `test_refuses_when_network_is_unavailable_not_a_silent_pass` | COMPLIANT (behavioural: `/nonexistent/remote.git` refuses naming commit + URL) |
| G2 Probe carries no more authority than the runner | An SSH remote | `ProbeAuthorityTests > test_an_ssh_remote_refuses_through_the_reachability_path_naming_the_probe`, `…_is_not_refused_by_a_separate_guard_before_the_fetch` | COMPLIANT (behavioural: `git@host.invalid:owner/repo.git` refuses through `_verify_commit_reachable`'s one except-block, carrying the unauthenticated-probe sentence) |
| G2 | Authorization never leaks in | `ProbeAuthorityTests > test_the_allowlist_admits_no_name_that_confers_authorization`, `…_widens_for_transport_and_keeps_the_runner_s_own_path`, `test_the_child_is_told_never_to_prompt_for_credentials`, `test_the_child_never_inherits_this_process_s_terminal_on_stdin` | COMPLIANT (behavioural: planted `SSH_AUTH_SOCK`, `GIT_CONFIG_GLOBAL`, `HOME`, `GIT_ASKPASS` in the parent; child env was exactly `{PATH, GIT_TERMINAL_PROMPT=0}`, `stdin=-3` = `DEVNULL`) |
| G3 Generation refuses a dirty tree over the clone paths | A modified file under a clone path | `CleanWorkingTreeTests > test_a_modified_tracked_file_under_a_clone_path_refuses_naming_it`, `test_generation_refuses_a_dirty_tree_and_writes_no_job_folder`, `test_the_repository_is_byte_identical_after_every_refusal` | COMPLIANT (behavioural: ` M src/pkg/harness.py` named, exit 1, no folder) |
| G3 | An untracked file under a clone path | `CleanWorkingTreeTests > test_an_untracked_non_ignored_file_under_a_clone_path_refuses_naming_it`, `test_git_diff_would_not_have_seen_the_untracked_file` | COMPLIANT (behavioural, and the reason `status --porcelain` was chosen was re-measured on my own fixture: `git diff --name-only -- src/pkg` printed nothing while `git status --porcelain -- src/pkg` printed `?? src/pkg/run_search.py`) |
| G3 | Dirt outside the clone paths is irrelevant | `CleanWorkingTreeTests > test_dirt_outside_every_clone_path_passes`, `test_generations_own_untracked_output_under_tools_does_not_refuse_it` | COMPLIANT (behavioural: ` M README.md` and `?? tools/` present, generation still exit 0) |
| G3 | Cleanliness cannot be proven | `CleanWorkingTreeTests > test_a_target_that_is_not_a_repository_refuses_carrying_gits_words`, `test_a_repository_with_no_commits_refuses_carrying_gits_words` | COMPLIANT (behavioural: non-repo target outside any enclosing repository refuses carrying `fatal: not a git repository (or any of the parent directories): .git`; a repo with no commits carries `fatal: ambiguous argument 'HEAD'`) |
| G4 Same verdict refuses at a decision point, reports at a read | The pin is behind HEAD under the clone paths | `PinIsHeadTests > test_a_pin_behind_head_under_the_clone_paths_refuses`, `test_generation_refuses_a_drifted_pin_and_writes_no_job_folder` | COMPLIANT (behavioural: refusal named `src/pkg/harness.py`, the pin and HEAD) |
| G4 | Behind HEAD only outside the clone paths | `PinIsHeadTests > test_a_pin_behind_head_only_outside_the_clone_paths_passes` | COMPLIANT (behavioural: exit 0) |
| G4 | The pin is not in local history | `PinIsHeadTests > test_a_pin_absent_from_local_history_is_unknown_and_refuses`, `test_the_unknown_refusal_carries_gits_own_words_forward` | COMPLIANT (behavioural: `unknown`, carrying `fatal: Not a valid object name …^{commit}`) |
| G4 | Reading is still only reporting | `PinIsHeadTests > test_reading_a_drifted_job_folder_still_only_reports` | COMPLIANT (behavioural: `read()` on a drifted folder returned `{'status': 'drift', 'changedPaths': ['src/pkg/harness.py']}` and raised nothing) |
| G5 `--commit` MAY be omitted, defaults to HEAD | Omitted with a clean tree | `CommitDefaultTests > test_omitting_the_commit_pins_head`, `test_stdout_reports_the_pinned_commit_and_that_it_was_defaulted` | COMPLIANT (behavioural: stdout `{"commit": "9bfb3df…", "commitSource": "default-head", …}`) |
| G5 | Omitted with a dirty tree | `CommitDefaultTests > test_omitting_the_commit_with_a_dirty_tree_refuses_and_writes_nothing`, `test_a_defaulted_pin_goes_through_every_condition` | COMPLIANT (behavioural: refuses under condition (1), no folder) |
| G5 | Explicit still means explicit | `CommitDefaultTests > test_an_explicit_commit_is_never_substituted`, `test_no_remote_derived_commit_is_ever_substituted`, `test_the_python_api_and_the_cli_share_one_resolution` | COMPLIANT (behavioural: an explicit non-HEAD published pin was evaluated against all three conditions and written verbatim; `commitSource: "explicit"`) |
| G6 Submission refused before quota, not reported after | A dirty tree at submit time | `SubmitPinGateTests > test_a_dirty_tree_refuses_with_no_adapter_call_and_no_ledger_line` | COMPLIANT (behavioural: `submission refuses: the working tree is not clean…`, adapter calls 0, ledger byte-identical) |
| G6 | The pin drifted since generation | `SubmitPinGateTests > test_a_drifted_pin_refuses_before_the_adapter`, `test_the_gate_runs_before_the_digest_walk` | COMPLIANT (behavioural: adapter calls 0, ledger line count 1→1) |
| G6 | The pin was rewritten or unpushed since generation | `SubmitPinGateTests > test_an_unpushed_pin_refuses_naming_the_commit_the_remote_and_the_push` | COMPLIANT (behavioural: after pruning the object out of the bare origin, submit refused naming commit, remote and the missing push; adapter calls 0, ledger 2→2) |
| G6 | A legacy entrypoint is unaffected | `SubmitPinGateTests > test_a_legacy_entrypoint_with_no_run_config_is_unaffected` | COMPLIANT (behavioural: legacy notebook submitted, adapter called once, `staleness: None`, ledger 2→3) |
| G7 Three conditions documented and locked through a table | A condition present in code and absent from the table | `PinConditionDoctrineTests > test_the_table_documents_every_condition_in_pin_conditions_order`, `test_both_decision_points_are_named_in_every_row` | COMPLIANT (reproduced by inversion — deleting the `pin-is-head` row failed the lock with `Lists differ: ['pin-is-head'] != []`) |
| G7 | An operator looks up why generation refused | `PinConditionDoctrineTests > test_every_row_names_where_it_is_enforced_and_what_it_names`, `test_doctrine_states_the_tool_never_commits_or_pushes`, `test_doctrine_states_there_is_no_dirty_tree_escape_hatch`, `test_doctrine_documents_the_refuse_versus_report_asymmetry` | COMPLIANT (`SKILL.md:258-262` carries the exact header `\| # \| id \| Condition \| Enforced at \| Refusal names \|`, three rows in `PIN_CONDITIONS` order, both decision points on every row) |
| X Every refusal carries git's own message and names the remedy | An unanswerable question refuses with git's words | `CommitReachabilityTests > test_reachability_refusal_precedes_clone_path_resolution` (asserts the `"not our ref"` substring), `PinIsHeadTests > test_the_unknown_refusal_carries_gits_own_words_forward`, `CleanWorkingTreeTests > test_a_target_that_is_not_a_repository_refuses_carrying_gits_words` | COMPLIANT (behavioural: every refusal I induced carried git's own text; condition (3)'s carried `fatal: remote error: upload-pack: not our ref <sha>` plus the remote URL) |
| X | Nothing is written on the operator's behalf | `CleanWorkingTreeTests > test_the_repository_is_byte_identical_after_every_refusal`, `PinIsHeadTests > test_the_refusal_does_not_commit_or_push_on_the_operators_behalf`, `SubmitPinGateTests > test_a_dirty_tree_refuses_with_no_adapter_call_and_no_ledger_line` | COMPLIANT (behavioural: refs, `FETCH_HEAD` and object store unchanged after a passing probe; no ledger line after any refusal) |
| X Existing guard tests corrected, not routed around | The defect assertion is gone | `CommitReachabilityTests > test_probes_from_a_scratch_repository_and_never_from_the_target` | COMPLIANT — the old `cwd == target` assertion is inverted in place: `tests:4346-4347` now reads `assertNotEqual(probe_cwd, target)` and `assertNotIn(target, probe_cwd.parents)`. No test anywhere asserts the probe runs in a repository holding the pin. |
| X | A new class does not silently shadow an existing one | Not a single test; proven by the per-commit AST table above | COMPLIANT — 253→335 across the change, deltas matching tests added at every commit, zero duplicate class names at every commit. |
| X Every new lock proven reachable-red | A lock's reachable-red proof | Not a test; proven by the inversion series below | COMPLIANT for the seven inversions this verifier reproduced; the remaining 19 in the apply record are recorded there and not independently re-run (see WARNING 5). |

**Compliance summary**: 30/30 scenarios compliant, 11/11 requirements satisfied.

### Inversions reproduced by this verifier

Each inversion was applied to the working tree, the full `tests.test_remote_execution`
suite was run, and the file was restored by writing its pristine bytes back and
confirming with `cmp` and `shasum -a 256`. Pristine digests re-measured before
the series: `jobfolder.py` `cd394e0d7f…` and `remote_cli.py` `8ad5a5c8bf…` —
both matching the digests the apply record recorded for slice 6.

| # | Inversion | Target | Red result |
|---|---|---|---|
| 1 | `git status --porcelain` → `git diff --name-only` in condition (1) | `jobfolder.py:1183` | 12 failures, led by `test_an_untracked_non_ignored_file_under_a_clone_path_refuses_naming_it`; also reddened `CommitDefaultTests`, `PinIsHeadTests.test_condition_two_runs_after_condition_one`, and 5 `SubmitPinGateTests` |
| 2 | `_gate_job_folder_pin()` moved from before `source_digest()` to after `LEDGER.append()` | `remote_cli.py:570` → `:606` | 7 failures: 6 `SubmitPinGateTests` plus `StalenessRoutingTests.test_cmd_submit_refuses_an_incomplete_run_config_rather_than_tolerating_it` (the apply record predicted 6; the seventh is the corrected legacy test, so the record undercounted by one rather than overstating) |
| 3 | Strip the `pip install kaggle` remedy from `KaggleAdapter._run`'s `OSError` refusal | `adapters/kaggle.py` | 1 failure: `AdapterEnvironmentTests.test_a_missing_service_cli_says_what_to_install_not_just_what_failed` |
| 4 | Rename `kaggle` → `the-backend` inside `SKILL.md`'s `## Environment` body only | `SKILL.md` | 1 failure: `AdapterEnvironmentTests.test_the_environment_section_states_the_cli_this_adapter_shells_out_to` |
| 5 | Drop `--depth 1` from the probe argv | `jobfolder.py:1104` | 1 failure: `CommitReachabilityTests.test_probes_from_a_scratch_repository_and_never_from_the_target` |
| 6 | Probe from the process cwd instead of a discarded `TemporaryDirectory` | `jobfolder.py:1101-1102` | 4 failures: 3 `CommitReachabilityTests` plus `ProbeAuthorityTests.test_an_ssh_remote_is_not_refused_by_a_separate_guard_before_the_fetch` |
| 7 | Delete the `pin-is-head` row from the doctrine table | `SKILL.md:261` | 1 failure: `PinConditionDoctrineTests.test_the_table_documents_every_condition_in_pin_conditions_order`, naming `pin-is-head` |

The falsely-green shape the apply record flagged is now guarded in the test
itself: `AdapterEnvironmentTests` uses the fixture name `zzz-no-such-service-binary-zzz`
and asserts `assertNotIn("install", absent)` before asserting `assertIn("install", message.lower())`,
so the assertion cannot be satisfied by the fixture's own name.

### The two corrections in the apply record, independently confirmed

**1. `--depth 1` alone defeats the local-object-store shortcut.** Re-measured
against a bare remote that provably lacked the object (`cat-file -e` in the
origin: `fatal: Not a valid object name`), fetching from inside the repository
that holds the pin:

```text
git fetch --dry-run <origin> <pin>              → exit 0, "* branch <pin> -> FETCH_HEAD"
git fetch --dry-run --depth 1 <origin> <pin>    → exit 128, "fatal: remote error: upload-pack: not our ref <pin>"
```

Confirmed exactly as recorded. The scratch repository's remaining teeth are
therefore about where objects land, not about the answer — and that half was
confirmed separately: after a successful probe the target's object count was
24→24, `git show-ref` byte-identical, and `.git/FETCH_HEAD` absent both before
and after.

**2. The repaired doubles can never hold a cwd claim.** Confirmed structurally.
`CommitReachabilityTests._clean_tree_git` (`tests:4594-4623`) returns
`fake_run_git(args, *, cwd, timeout=None)` which never reads `cwd`, and it is
installed with `patch.object(JOBFOLDER, "_run_git", side_effect=…)`, replacing
the composition point wholesale so no git process exists to have a cwd. Three
tests use it, not two. Task 3.6's recorded outcome — "they do not fail, and no
repair could make them" — is correct, and the cwd inversion above is caught by
the two dedicated locks instead, exactly as recorded.

### Correctness (Static + behavioural evidence)

| Item | Status | Evidence |
|---|---|---|
| The seam is genuinely shared | Implemented | `verify_pin_preconditions()` has exactly two production call sites: `jobfolder.py:772` (`generate_job`, before `resolve_clone_paths()`) and `remote_cli.py:364` (inside `_gate_job_folder_pin`). No second implementation exists: `status --porcelain` appears once in executable code (`jobfolder.py:1183`); `fetch --dry-run` once (`:1104`); `_staleness_for` has exactly two callers, `_refuse_stale_pin` (`:1238`) and `read()` (`:1512`); the three condition callables are registered once each in `_PIN_CONDITION_CHECKS`. |
| Conditions fire in `PIN_CONDITIONS` order | Implemented | Behavioural, three-step: with all three violable, condition (1) spoke; fixing (1), condition (2) spoke; fixing (2), condition (3) spoke. `PIN_CONDITIONS == ("clean-worktree", "pin-is-head", "pin-published")`. |
| `submit` gates before spending | Implemented | `remote_cli.py:570` — the gate sits after `product_for()` (`:569`) and before `source_digest` (`:576`), `PACKER.plan` (`:585`), `adapter.submit` (`:595`) and `LEDGER.append` (`:605`). Behavioural: every refusal produced 0 adapter calls and a byte-identical ledger. Inversion 2 reddens 7 locks. |
| Malformed vs legacy discrimination | Implemented | Behavioural: `_job_folder_staleness()` returns `None` for BOTH a malformed config and the legacy shape — I called it directly on two fixtures and got `None` twice, so the record's warning is exact. The gate instead forks on `RUN_CONFIG_FILENAME` presence (`remote_cli.py:358`) and does not swallow `JobFolderError`. With `--product` supplied so `product_for()` cannot pre-empt it, a malformed config refuses from the gate: `JobFolderError: … run-config.json is not valid JSON`. A valid-JSON-but-incomplete config refuses with `run-config.json missing required fields: [...]`. The legacy shape submits unchanged. |
| Staleness stays in the payload | Implemented | Behavioural: a clean submit returned `staleness={'status': 'fresh', …}`; the legacy submit returned `staleness=None`. |
| `--commit` optional and never remote-derived | Implemented | `remote_cli.py:1386-1394` (`default=None`, no `required=True`); `_resolve_pin()` (`jobfolder.py:1295`) is the one resolution, local `git rev-parse HEAD` only, called before `verify_pin_preconditions()` so a defaulted pin meets every condition. `commitSource` is on stdout and absent from `run-config.json` (grepped the generated file). |
| Probe authority | Implemented | `GIT_ENV_ALLOWLIST` is `PATH` plus proxy/TLS names only — no `HOME`, no `SSH_AUTH_SOCK`, no `GIT_CONFIG_*`, no credential helper, no askpass. `GIT_TERMINAL_PROMPT=0` and `stdin=subprocess.DEVNULL` set in `_run_git`. Verified by planting all four in the parent. |
| Doctrine lock | Implemented | `SKILL.md:258-262`; both required sentences present (`SKILL.md:302`, `:306`); the refuse-vs-report asymmetry documented in `jobfolder.py:1400-1412` and in `SKILL.md`. |
| Dead `return destination` removed | Implemented | AST: `read()` has exactly one top-level `return` (its own, `:1514`). The two surviving `return destination` statements are the live returns of `resolve_destination` (`:204`) and `generate_job` (`:863`). |
| `requirements.txt` names `kaggle` | Implemented | `kaggle>=1.7` added. Installed locally at 1.7.4.5. |
| Nothing above the adapter seam names the service | Holds | `rg -li kaggle` under the skill returns exactly two files: `scripts/adapters/kaggle.py` and `SKILL.md` (documentation). No occurrence anywhere in `scripts/` outside `adapters/`. |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — one public function that is also the single test seam | Yes | `verify_pin_preconditions()`; five test classes swapped their patch target onto it. |
| D2 — condition (1) is `status --porcelain`, `diff` is the wrong instrument | Yes | Confirmed on my own fixture and by inversion 1. |
| D3 — probe from a scratch repository, shallow, unauthenticated, non-interactive | Yes | All four properties verified behaviourally. |
| D4 — `submit` refuses before quota and does not inherit `_job_folder_staleness`'s tolerance | Yes | Both halves verified behaviourally. |
| D5 — `--commit` optional, resolution shared, labelling CLI-local | Yes | `_resolve_pin()` shared; `commitSource` on stdout only. |
| D6 — `repo.ref` kept with exactly one job | Yes | Used only in the condition (3) remedy sentence (`jobfolder.py:1108`); no containment check exists. |
| Proposal D4 — two-tier `ls-remote`-first probe fallback | Deliberately not adopted | Gated on a measurement (2.1–2.9 s, 12.35 MiB) recorded in the apply record. Not re-measured here: it contacts the live service, which this verification was told not to do. |

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. **An eighth commit no artifact planned.** `c4ee27f` (`requirements.txt` + `## Environment` + the `KaggleAdapter._run` remedy + `AdapterEnvironmentTests`) satisfies no spec requirement and completes no task. Its two locks are real and both proven reachable-red here, and its content is correct — but it entered the change outside the spec, and the spec's own non-goals table would have been the place to admit or exclude it. Archive should record it as in-scope-by-adoption rather than as spec-derived.
2. **Review-workload guard exceeded, in aggregate and by a wide margin.** Measured churn `6460587..c4ee27f` is 3219 additions + 219 deletions = **3438 authored lines**, against a tasks forecast of ~895 and a cached session budget of 1200. Production and doc churn alone is 831 lines; tests are 2548. The apply record acknowledged the overrun for slice 3 only (732 vs ~230) and did not restate it for the change as a whole. Delivery was settled as direct commits on `main` with no PRs, so the 400-line per-PR guard had no PR to bind — but it was exceeded rather than satisfied, and a later reviewer of these eight commits inherits the full 3438 lines.
3. **A refusal path the spec does not name.** A malformed `run-config.json` now refuses at `submit`. This is the right call and it is stated in `82ceda7`'s body, Q1 answers it explicitly, and reusing `_job_folder_staleness` would demonstrably have let unreadability buy an exemption (I measured `None` for both shapes). It is still a behaviour change for a state that previously submitted, carried by a commit body rather than by the spec.
4. **Spec counts in the launch prompt do not match the artifact.** The prompt declared 12 requirements and 33 scenarios; the spec artifact on disk contains 11 `### … Requirement:` headings and 30 `#### Scenario` headings. I verified against the artifact and used 11/30 as authoritative. If a newer spec revision exists somewhere, this report was built against the wrong one.
5. **19 of the 26 claimed inversions were not independently re-run.** I reproduced 7, chosen as the load-bearing ones the task named plus the doctrine lock. The other 19 rest on the apply record alone. Every one I did attempt reproduced, and the one numeric disagreement (inversion 2 reddening 7 locks rather than 6) was in the implementation's favour, so I have no reason to doubt the rest — but "proven here" and "recorded there" are different claims and I am not merging them.
6. **`PIN_CONDITIONS` shipped in two steps**, so `9224be9` and `3ef8dc8` each left the tree in a state the design's 3-tuple did not describe. The delivered state is the design's tuple in the design's order, and shipping a tuple naming a condition nothing dispatched to would have been worse. Recorded because a bisect landing between those two commits meets a 2-tuple.
7. **`validate_commit_shape()` was extracted and hoisted** ahead of every condition inside `verify_pin_preconditions()`, beyond the spec's "run-config validation" wording. Both callers exist (`jobfolder.py:547` for `validate_run_config`, `:1369` for the seam), so this strictly adds a check. Judged sound; recorded because it widened where a refusal can originate.
8. **Task 6.4's second half had no target.** `.claude/skills/remote-execution/references/usage.md` does not exist — the skill has no `references/` directory at all (`fd` finds `usage.md` only under `proposal-deliberation` and `proposal-implementation`). Confirmed. `SKILL.md` was updated and now documents `--commit` as optional at `:215`, `:287`, `:299`.

**SUGGESTION**:

1. In the common case (no `--product` override, unreadable config), the operator's first message for a malformed `run-config.json` comes from `product_for()`, not the gate — `cannot resolve a product for …`. The gate's own, more informative refusal is only reached when the product resolves some other way. Not a defect; worth a sentence in doctrine if operators are expected to recognise it.
2. `submit`'s three "recorded, not fixed" items remain open and are correctly out of scope: `resolve_clone_paths` still walks the working tree, nothing cross-checks a job's declared `service` against `submit --backend`, and the live target's `identicalAcrossShards` declaration still lets two shards run different code and pool. Carry them forward as follow-ups.
3. Commit subjects run 92–110 characters. That matches this repository's established style (the preceding `docs(proposal-implementation): …` commits are the same shape), so no change is recommended — noted only so a future conventional-commit linter is not surprised.

### Verdict

**PASS WITH WARNINGS**

Every one of the 11 spec requirements and 30 scenarios is satisfied by code on
disk and proven by a test that passed at runtime; the three conditions were
exercised behaviourally on real git fixtures, fire in the declared order, each
carries git's own message forward, the seam is genuinely single, `submit` gates
strictly before it spends, and seven inversions — including all four the task
named as load-bearing — reproduced and were restored byte-identically. The
warnings are scope and process observations, not defects: none blocks archive.
