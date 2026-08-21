# Apply progress: the-pin-the-runner-can-actually-fetch

Store: engram is disconnected — this file is the artifact. Mode: strict TDD (C3).
Delivery: commits directly on `main`, no branches, no PRs.

Scope of this launch: Phase 0, task 2.1 (the measurement), tasks 2.2–2.8 (the probe slice).
Explicitly NOT in this launch: slice 2 / commit-shape (`CommitShapeTests`, `COMMIT_PATTERN`),
slices 4a, 4b, 5, 6.

---

## Phase 0 — Baseline, measured here (not inherited)

- [x] 0.1 Baseline at `a60e5d0`, working tree clean:

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_remote_execution` | `Ran 254 tests in 9.795s` — OK |
| `python3 -m unittest discover -s tests` | `Ran 791 tests in 27.344s` — OK |

Both figures match the orchestrator's. Every later step below is judged by these counts
going **up** by the number of tests added, never by the suite staying green.

- [x] 0.2 Name grep before writing (`rg --no-ignore --hidden`):

| Name | Occurrences before this slice |
|---|---|
| `ProbeAuthorityTests` | 0 — free |
| `verify_pin_preconditions` | 0 — free (not this slice) |
| `COMMIT_PATTERN` | 0 — free (not this slice) |
| `GIT_ENV_ALLOWLIST` | `jobfolder.py` (4), `assets/runner_bootstrap.py` (3) — occupied, widened not created |
| `CommitReachabilityTests` | `tests:4002` (definition) + `tests:3569` (a comment) — occupied, corrected in place |
| `GIT_TERMINAL_PROMPT` | 0 in first-party code (only vendored `pip` copies) |
| `tempfile` in `jobfolder.py` | mentioned in a comment at `:178`; **not imported** |

Duplicate-class check on the whole test file: `rg '^class '` piped through `sort | uniq -d`
returns empty — no class name is defined twice today.

---

## Task 2.1 — MEASURE (gates the two-tier decision)

Throwaway box `implementations/_probe-measure`, deleted after; `env -i PATH=… GIT_TERMINAL_PROMPT=0`
so the measurement carried the same authority the shipped probe will.
Live remote `https://github.com/Daprosero/Domain_Adaptation`, tip `225310f5…`,
ancestor `2f2d40e6…` (read out of the tip's own commit object).

| Probe | Elapsed | Transferred | Written into `.git` |
|---|---|---|---|
| `ls-remote <url>` (all refs) | 0.63 s | refs only | — |
| `ls-remote <url> main` (D4 tier-1) | 0.73 / 0.76 / 0.79 s | refs only | — |
| `fetch --dry-run --depth 1 <url> <tip>` | 2.38 / 2.78 / 2.91 s | 12.35 MiB, 199 objects | 12.8–13.2 MiB |
| `fetch --dry-run --depth 1 <url> <ancestor>` | 2.09 s | ~12.5 MiB | 12.5 MiB |

Three further facts the measurement settled, each of which the design could only assume:

1. **`--dry-run` + `--depth 1` works against the live remote for a bare 40-hex pin, and for a
   non-tip ancestor too** (exit 0). GitHub serves a reachable SHA in a want, so the probe does
   not silently depend on the pin being a ref tip.
2. **`--dry-run` wrote no ref and no `FETCH_HEAD`** (`show-ref` → 0 refs, `.git/FETCH_HEAD` absent)
   **but it did write ~12.8 MiB of objects.** This is the sharpest argument for the scratch
   directory: `--dry-run` suppresses ref updates, not object transfer, so the current probe is
   not merely useless in the target — it deposits the remote's pack there on every generation.
3. **`ls-remote <url> <40-hex>` returned empty with exit 0** while the remote demonstrably serves
   that commit — reconfirming, against the live remote, the rejection the existing docstrings
   already record.

**Decision on D4's two-tier `ls-remote`-first fallback: NOT adopted.** The design's condition was
"adopt only if the probe is bad". At 2.1–2.9 s it is not bad: it sits beside `submit`, which
already dials out, uploads a staged job folder and spends remote quota. Tier-1 would save ~2 s and
~12 MiB only when the pin happens to equal the declared ref's tip, and would *add* ~0.75 s to every
other generation plus a second code path and a second remote round trip. The 12 MiB is a real cost
and is recorded, but it is bounded by `--depth 1` and is discarded with the scratch directory.

Carried open question Q3 is answered: the measurement is reported and the fallback stays deferred.

---

## Slice 3 — the probe (tasks 2.2–2.8) — LANDED `26d8e57`

Files: `.claude/skills/remote-execution/scripts/jobfolder.py`,
`.claude/skills/remote-execution/SKILL.md`, `tests/test_remote_execution.py`.
679 insertions, 53 deletions.

### TDD cycle evidence

| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 2.2 corrected `CommitReachabilityTests` | 6 of 7 new/corrected methods failed | 264/264 OK | argv + cwd assertions rewritten in place |
| 2.3 `ProbeAuthorityTests` | 5 of 6 failed (see below) | 264/264 OK | — |
| 2.4 probe rewrite | — (drives the above) | 264/264 OK | `_looks_like_ssh_remote` extracted |
| 2.5 call sites | — | 264/264 OK | — |
| 2.6 prose (JF ×2, T ×1, SKILL.md) | n/a | 801/801 OK | — |
| 2.7 inversions | 4 of 4 caught | restored byte-identical | — |

RED run, 264 tests, `FAILED (failures=19, errors=2)`. Distinct methods red:

```
ERROR test_a_published_commit_passes_without_depositing_objects_in_the_target
ERROR test_refuses_when_the_scratch_directory_itself_cannot_be_made
FAIL  test_probes_from_a_scratch_repository_and_never_from_the_target
FAIL  test_refuses_a_commit_that_exists_locally_and_was_never_pushed
FAIL  test_refuses_when_the_scratch_repository_cannot_be_initialised
FAIL  test_an_ssh_remote_refuses_through_the_reachability_path_naming_the_probe
FAIL  test_an_ssh_remote_is_not_refused_by_a_separate_guard_before_the_fetch
FAIL  test_the_allowlist_widens_for_transport_and_keeps_the_runner_s_own_path
FAIL  test_the_child_is_told_never_to_prompt_for_credentials
FAIL  test_the_child_never_inherits_this_process_s_terminal_on_stdin
```

`test_the_allowlist_admits_no_name_that_confers_authorization` was the one
lock green on first run; inversion (g) is its reachable-red proof.

### Counts — up, not merely green

| Suite | Before | After | Delta | Tests added |
|---|---|---|---|---|
| `tests.test_remote_execution` | 254 | **264** | +10 | 10 |
| `discover -s tests` | 791 | **801** | +10 | 10 |

Both OK. The delta equals the number of tests added in both suites, so no
class was shadowed and no test was silently disabled.

### Inversions — all restored by inverse patch, verified by `cmp` + sha256

Pristine `jobfolder.py` = `85a711608dba4217d4ae637f7822f76ec807f77496f3dde626d7a3c55c7eabbe`,
re-verified byte-identical after each.

| # | Inversion | Caught by | Assertion that fired |
|---|---|---|---|
| c | drop `--depth 1` from the probe argv | `test_probes_from_a_scratch_repository…` | argv list differs |
| d | probe from the process cwd instead of a discarded scratch repo | same test | `True is not false : the scratch repository outlived the probe` |
| d2 | probe from the repository that holds the pin | `test_a_published_commit_passes_without_depositing_objects_in_the_target` | object listing differs |
| g | admit `SSH_AUTH_SOCK` to `GIT_ENV_ALLOWLIST` | `test_the_allowlist_admits_no_name…` **and** the corrected `StalenessTests` lock | `['SSH_AUTH_SOCK'] != []` |

### Findings that changed the design's reasoning

1. **`--depth 1` alone also defeats the local-object-store shortcut.** Measured:
   `fetch --dry-run <url> <unpushed>` inside the pin-holder exits **0**; the same
   fetch **with `--depth 1`** inside the same repository exits **128,
   `upload-pack: not our ref`**. The plan expected inversion (d) to redden the
   unpushed-commit e2e case; it does not, because the answer stays correct once
   the fetch is shallow. The scratch repository's teeth are therefore not in the
   answer but in **where the objects land**, which is what inversion (d2) and the
   object-deposit lock establish. Recorded because slice 4a's task 3.6 leans on
   inversion (d) as a proof instrument and must use (d2) or the cwd assertion
   instead.
2. **One test did hold `GIT_ENV_ALLOWLIST`**, contrary to the design's consumer
   inventory ("no test asserts the allowlist today — grepped: zero hits").
   `StalenessTests.test_run_git_env_is_a_path_only_allowlist` asserted
   `set(recorded_env) == {"PATH"}` and broke on the widening. Corrected, not
   routed around: it now proves nothing reaches the child that the allowlist did
   not name, against `HOME`, `SSH_AUTH_SOCK` and `GIT_CONFIG_GLOBAL` planted in
   the parent — strictly more than it asserted before — and inversion (g) shows
   it still has teeth. Renamed to
   `test_run_git_env_admits_nothing_beyond_the_declared_allowlist`.
3. **`--dry-run` does not suppress object transfer.** 12.35 MiB received, 12.8 MiB
   written into the probing repository's object store, with no ref and no
   `FETCH_HEAD`. This is the second and quieter reason the probe must not run in
   the target.

### Deviation from the forecast

Slice 3 was forecast at ~230 authored lines; it landed at **732** (add+del:
`jobfolder.py` 188/39, `tests` 446/14, `SKILL.md` 45/0). Under the 1200 session
budget, over the 400 per-PR guard — which has no PR to apply to, since delivery
is settled as direct commits on `main`. The overrun is concentrated in prose the
tasks required (three docstrings plus a SKILL.md section for a probe documented
nowhere) and in the two real-git-fixture tests, which need a two-repository
fixture a mock cannot supply. Not split, because the RED tests and the
implementation they drive cannot land in separate commits without a knowingly
red commit in between.

### Work unit evidence

| Evidence | Value |
|---|---|
| Focused test command | `python3 -m unittest tests.test_remote_execution` → `Ran 264 tests` / OK |
| Runtime harness | Real `git fetch --dry-run --depth 1` against `https://github.com/Daprosero/Domain_Adaptation` (task 2.1) and against two real local repositories in the e2e tests |
| Rollback boundary | `git revert 26d8e57` — the slice touches only `_verify_commit_reachable`, `GIT_ENV_ALLOWLIST`, `_run_git`, one call site, three docstrings and one SKILL.md section. It creates nothing later slices depend on. |

---

## Not done in this launch

- Slice 2 / commit-shape (`COMMIT_PATTERN`, `CommitShapeTests`, tasks 1.1–1.4) —
  the launch prompt listed commit-shape validation under "out of scope" while its
  header said "slices 2 and 3", and its own scope section described only the
  measurement and the probe. Read as: not mine. Flagged for the orchestrator.
- Slices 4a, 4b, 5, 6, and open questions Q1 and Q2.

---

# Launch 2 — slices 2, 4a, 4b, 5, 6 (the remainder)

Store: engram still disconnected — appended here. Mode: strict TDD (C3).
Delivery: commits directly on `main`, no branches, no PRs, no push (C4).
Baseline re-measured at `26d8e57`, working tree clean: `tests.test_remote_execution`
**264**, `discover -s tests` **801** — both match the orchestrator's figures.

## Name grep before writing (`rg --no-ignore --hidden`)

`COMMIT_PATTERN`, `CommitShapeTests`, `verify_pin_preconditions`, `PIN_CONDITIONS`,
`_refuse_dirty_worktree`, `_refuse_stale_pin`, `CleanWorkingTreeTests`, `PinIsHeadTests`,
`PinConditionDoctrineTests`, `SubmitPinGateTests`, `CommitDefaultTests`,
`_gate_job_folder_pin`, `commitSource` — **0 occurrences each**. `SKILL_MD` and
`markdown_table_rows` exist only in `tests/test_proposal_implementation.py`, a different
module with no import between them. `rg '^class '` piped through `sort | uniq -d` on the
whole test file returns empty before and after every commit.

## Commits, in order

| SHA | Slice | remote_execution | discover | Δ | tests added | rose by the expected amount? |
|---|---|---|---|---|---|---|
| `b7cb43f` | 2 — commit shape | 264 → **275** | 801 → **812** | +11 | 11 | yes |
| `9224be9` | 4a — shared seam + condition (1) | 275 → **292** | 812 → **829** | +17 | 17 | yes |
| `3ef8dc8` | 4b — condition (2) + doctrine | 292 → **309** | 829 → **846** | +17 | 17 | yes |
| `82ceda7` | 5 — the submit gate | 309 → **321** | 846 → **858** | +12 | 12 | yes |
| `726dd76` | 6 — `--commit` optional | 321 → **333** | 858 → **870** | +12 | 12 | yes |

Every delta equals the number of tests added, in both suites, so no class was shadowed
and no test was silently disabled. All five commits are on `main`, none pushed.

## RED transcripts actually observed

- **Slice 2** — `CommitShapeTests`, 11 tests, `FAILED (failures=8)`. Red methods:
  `test_a_branch_name_is_refused_and_the_message_names_it`,
  `test_a_branch_name_refuses_generation_and_writes_no_job_folder`,
  `test_a_commit_carrying_shell_metacharacters_is_refused_by_shape`,
  `test_a_non_string_commit_is_refused_rather_than_crashing`,
  `test_an_abbreviated_hex_pin_is_refused`,
  `test_reading_a_job_folder_whose_pin_is_a_name_refuses`,
  `test_the_refusal_says_a_branch_or_tag_name_is_not_a_pin`,
  `test_uppercase_hex_is_refused`. All eight: `AssertionError: JobFolderError not raised`.
- **Slice 4a** — `CleanWorkingTreeTests`, 17 tests, `FAILED (failures=1, errors=14)`.
- **Slice 4b** — `PinIsHeadTests` + `PinConditionDoctrineTests`, 17 tests, `FAILED (failures=12)`.
- **Slice 5** — `SubmitPinGateTests`, 11 tests, `FAILED (failures=8, errors=1)`.
- **Slice 6** — `CommitDefaultTests`, 12 tests, `FAILED (failures=1, errors=8)`.

## Inversions — every one restored by inverse patch, verified `cmp` + sha256

Pristine hashes re-verified byte-identical after each: `jobfolder.py`
`c714cad0…` (2), `0887004548…` (4a), `fc25b3d450…` (4b), `cd394e0d7f…` (6);
`SKILL.md` `b7fb5985e3…` (4b); `remote_cli.py` `f71c90d974…` (5), `8ad5a5c8bf…` (6).

| Slice | Inversion | Caught by |
|---|---|---|
| 2 | `COMMIT_PATTERN` → `.*` | 7 refusal locks |
| 2 | `COMMIT_PATTERN` → 40-hex only | the 64-hex acceptance lock |
| 2 | `COMMIT_PATTERN` → matches nothing | all 3 acceptance locks |
| 4a | condition (1)'s emptiness test flipped | 11 of 17, incl. both first-run greens |
| 4a | `status --porcelain` → `diff --name-only` | 5, led by the untracked-file lock |
| 4a | `pin-published` dropped from `PIN_CONDITIONS` | 2 reachability locks |
| 4a | probe cwd → process cwd (task 3.6) | the 2 dedicated scratch/cwd locks |
| 4b | condition (2) accepts `drift` | 3 refusal locks |
| 4b | condition (2) refuses `fresh` too | 4 acceptance locks |
| 4b | `PIN_CONDITIONS` reordered | 2 ordering locks + the table-order lock |
| 4b | `read()` made to refuse on drift | the report-only lock |
| 4b | `pin-is-head` table row deleted | the doctrine lock, naming `pin-is-head` |
| 4b | `submit` dropped from Enforced-at | the two-decision-points lock |
| 4b | never-commits-or-pushes sentence removed | its lock |
| 4b | refuse-at-a-decision-point prose removed | the asymmetry lock |
| 5 | gate call removed from `cmd_submit` | 9 locks |
| 5 | gate moved to after `LEDGER.append` | 6 locks |
| 5 | fork changed to `_job_folder_staleness` | malformed-config lock + its AST companion |
| 5 | presence check removed | the legacy-unaffected lock |
| 5 | `staleness` dropped from the payload | the payload locks |
| 6 | default bypasses `verify_pin_preconditions` | dirty-tree-default + every-condition locks |
| 6 | explicit `--commit` substituted by HEAD | both explicit-means-explicit locks |
| 6 | pin resolved from the remote | 6 locks, led by no-remote-derived-commit |
| 6 | CLI resolves HEAD itself | the one-resolution lock |
| 6 | `commitSource` written into `run-config.json` | its absence lock |
| 6 | unreachable `return` restored to `read()` | the dead-return lock |

## Task 3.6 — the proof obligation, with the outcome that actually occurred

The design asked: with the mock-fidelity repair in place, invert the probe's cwd and
confirm the two repaired doubles still fail; if they do not, replace them with real
fixtures. **They do not fail, and no repair could make them.** They mock `_run_git`
entirely, so they cannot observe a cwd at all — they were never cwd locks. The cwd
inversion is caught by the two dedicated locks
(`test_probes_from_a_scratch_repository_and_never_from_the_target`,
`test_refuses_when_the_scratch_directory_itself_cannot_be_made`).

The permissiveness question that CAN be asked of the repair is whether it weakens the
doubles' own subject. Measured: dropping `pin-published` from `PIN_CONDITIONS` reddens
both. So the doubles are kept, and conditions (1) and (2) are locked against real git
repositories in their own classes and never through them. This also confirms the
previous launch's correction #1 — `--depth 1` alone defeats the local-object-store
shortcut, so inversion (d) is not the instrument for this obligation.

## Existing tests corrected in place, never routed around

1. `StalenessTests.test_pinned_commit_carrying_shell_metacharacters_reaches_argv_verbatim_and_executes_nothing`
   built its fixture by generating a job folder pinned to a shell-injection string. Shape
   validation refuses that at generation and again at every read, so it now drives
   `_staleness_for` directly. Its claim is about `_run_git`'s `shell=False` list argv, not
   about the job folder that used to be the only route to it. `CommitShapeTests` adds the
   other half: that value can no longer reach a job folder at all.
2. `StalenessRoutingTests.test_cmd_submit_tolerates_an_incomplete_run_config_and_reports_no_staleness`
   asserted exactly the behaviour slice 5 removes. Corrected to require the refusal, with
   the reasoning recorded: its old argument was right for REPORTING and wrong for GATING.
   A companion test was added proving the tolerance itself was not deleted, only removed
   from the gate's path — `_job_folder_staleness()` still falls through cleanly.
3. Five `cmd_submit` fixtures in `SubmitTests` and `SmokeTests` wrote
   `{"product": "MIL-CREDA"}` as a whole `run-config.json`. They now write a complete one
   through a shared helper. Their subjects are untouched; `product_for()`'s tolerance of
   an incomplete config keeps its coverage in `ProductForTests`, which does not submit.
4. Three `CommitReachabilityTests` doubles repaired via `_clean_tree_git()` — see task 3.6.
5. Five seam patch targets swapped from `_verify_commit_reachable` to
   `verify_pin_preconditions` (`JobFolderTests`, `CommitShapeTests`, `StalenessTests`,
   `StalenessRoutingTests`, `SmokeTests`), plus a new stub in `SubmitTests`. No assertion
   in any of them changed.

## Deviations from the design

1. **`PIN_CONDITIONS` shipped in two steps.** 4a landed
   `("clean-worktree", "pin-published")`; 4b inserted `"pin-is-head"` in the middle. The
   design's 3-tuple in 4a would have named a condition nothing dispatched to.
2. **Commit-shape validation was extracted and moved earlier.** `validate_commit_shape()`
   is one implementation with two callers, and `verify_pin_preconditions()` checks it
   ahead of every condition. A name-shaped pin makes each condition compare a value to
   itself and answer yes; checking shape after them cost a wasted network round trip for
   a pin that was going to be refused anyway.
3. **A new refusal path the spec does not name**, adopted deliberately and stated in
   commit `82ceda7`'s body: a malformed `run-config.json` refuses at submit.
4. **`references/usage.md` does not exist** in this repository, so task 6.4's second half
   had nothing to update. `SKILL.md` was the only doctrine naming `--commit`.
5. **`test_the_dead_return_after_read_is_gone`** was written with a wrong assertion first
   (`read()` legitimately ends with a `return`); corrected to count top-level returns and
   proven reachable-red by restoring the dead statement.

## Carried open questions

- Q1 — **answered: yes.** A malformed `run-config.json` refuses at submit. Recorded in
  `82ceda7`'s body as a new refusal path the spec does not name.
- Q2 — **answered: yes.** Five one-line patch-target swaps, no assertion changed, and the
  classes' own fixtures (plain directories, non-repos, pins absent from history) are
  states the conditions forbid at a decision point and `read()` only reports.
- Q3 — answered in launch 1.

## End-to-end, against the live target

`implementations/Domain_Adaptation` (never edited), tree clean, HEAD
`d903d1489510e0ff892eada5cd5e9ce79c9596a9`, remote `main` tip `225310f5…` — so HEAD is
unpushed. `generate-job` with `--commit` OMITTED:

```
error: generation refuses: commit 'd903d1489510e0ff892eada5cd5e9ce79c9596a9' could not be
confirmed reachable on the declared remote 'https://github.com/Daprosero/Domain_Adaptation'
— a runner would attempt and fail this same fetch inside the kernel, after quota is
already spent: git fetch --dry-run --depth 1 https://github.com/Daprosero/Domain_Adaptation
d903d1489510e0ff892eada5cd5e9ce79c9596a9 exited 128: fatal: remote error: upload-pack: not
our ref d903d1489510e0ff892eada5cd5e9ce79c9596a9 — push it to 'main' on
'https://github.com/Daprosero/Domain_Adaptation' and pin the commit the remote actually
received
```

exit 1. The pin was defaulted to HEAD, conditions (1) and (2) passed, condition (3)
refused. Target byte-unchanged: `git status --porcelain` empty before and after, and
`tools/` held 5 entries before and 5 after.

**To make it succeed:** `git -C implementations/Domain_Adaptation push origin main`, then
re-run the same command. Nothing else — the tree is already clean and the pin is already
HEAD, so conditions (1) and (2) are satisfied today.

## Recorded, not fixed

- `resolve_clone_paths` still walks the working tree. Addressed by condition (1) rather
  than by changing that function, exactly as the spec's non-goals state.
- Nothing cross-checks a job's declared `service` against `submit --backend`.
- The live target declares `"identicalAcrossShards": ["epochs"]` only, so two shards can
  run different code and `merge()` pools them silently. Target-side, forbidden by C2.
