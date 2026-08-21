# Tasks: the-pin-the-runner-can-actually-fetch

Store: engram (MCP down — mirrored here). Design status was `partial` (no shell); every unmeasured item below is a task, not a claim.

Path aliases: **JF** = `.claude/skills/remote-execution/scripts/jobfolder.py` · **RC** = `.../scripts/remote_cli.py` · **SK** = `.claude/skills/remote-execution/SKILL.md` · **T** = `tests/test_remote_execution.py`.

Commands: `python3 -m unittest tests.test_remote_execution` · `python3 -m unittest discover -s tests`. Never pytest, never `-k`. Boxes under `implementations/_<name>`, deleted after. Never edit `implementations/Domain_Adaptation`. `fd`/`rg` need `--no-ignore`. Restore inversions by inverse patch, never `git checkout --`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~895 authored (add+del) |
| Session budget (1200) | Under, as one review |
| 400-line budget risk | High (per-PR); slices 3 and 5 approach it, 4 exceeds it undivided |
| Chained PRs recommended | Yes |
| Suggested split | 2 · 3 → 4a → 4b → 5 → 6 |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Lines | Focused test command | Runtime harness | Rollback boundary |
|------|------|----|-------|----------------------|-----------------|-------------------|
| 2 | Commit shape refused in `validate_run_config` | PR 2 | ~60 | `python3 -m unittest tests.test_remote_execution.CommitShapeTests` | N/A — pure validation, no process | JF `validate_run_config` + `CommitShapeTests` |
| 3 | Probe from a scratch repo, `--depth 1`, env/auth discipline | PR 3 | ~230 | `... tests.test_remote_execution.CommitReachabilityTests tests.test_remote_execution.ProbeAuthorityTests` | Real fetch against `https://github.com/Daprosero/Domain_Adaptation` (task 2.1) | JF `_verify_commit_reachable`, `GIT_ENV_ALLOWLIST`, `_run_git`, docstrings, SK probe prose |
| 4a | Shared home + condition (1) + 4 seam swaps | PR 4a | ~170 | `... tests.test_remote_execution.CleanWorkingTreeTests` | Real git fixture repo (dirty/untracked/non-repo) | JF `verify_pin_preconditions`, `PIN_CONDITIONS`, `_refuse_dirty_worktree` |
| 4b | Condition (2) + doctrine table + lock | PR 4b | ~120 | `... tests.test_remote_execution.PinIsHeadTests tests.test_remote_execution.PinConditionDoctrineTests` | Real git fixture repo (drift/unknown) | JF `_refuse_stale_pin`, SK table |
| 5 | `submit` gate before quota | PR 5 | ~195 | `... tests.test_remote_execution.SubmitPinGateTests` | `FakeAdapter` + real fixture; assert no ledger line | RC `_gate_job_folder_pin` + its `cmd_submit` call |
| 6 | `--commit` optional, defaults to HEAD | PR 6 | ~120 | `... tests.test_remote_execution.CommitDefaultTests` | Real fixture, CLI stdout JSON | RC `:1313` flag, JF `generate_job` default |

### Ordering / independence check

- 2 and 3 are independent of everything and of each other: 2 touches only `validate_run_config`; 3 touches only the probe, the allowlist and `_run_git`. Either may land first.
- **Hard:** 4 → 5 (5 calls the function 4 introduces). **Hard:** 4 → 6 (a HEAD default before conditions (1)/(2) ships exactly the silent-wrong-pin behaviour this change removes). **Hard:** 2 → 6 (a defaulted pin must be shape-checked). **Soft:** 3 → 4, so the carry-git's-message idiom exists where `T:4200` depends on it.
- 4a → 4b (4b adds a condition to the tuple 4a introduces). Revert order: 6 before 4.
- No two units may be worked in parallel past 4a; 2 and 3 may.

---

## Phase 0 — Baseline (blocks everything)

- [x] 0.1 Run `python3 -m unittest tests.test_remote_execution` and `python3 -m unittest discover -s tests`. Record both counts verbatim (expected 254 / 791). Every later step is judged by the count **going up** by the number of tests added, never by "still OK".
- [x] 0.2 Grep `--no-ignore` for each new name before writing it: `verify_pin_preconditions`, `PIN_CONDITIONS`, `COMMIT_PATTERN`, `_refuse_dirty_worktree`, `_refuse_stale_pin`, `_gate_job_folder_pin`, `SKILL_MD`, and the 6 new class names. A duplicate class silently disabled seven tests here once.

## Phase 1 — Slice 2: commit shape (C4, spec Group 1)

- [x] 1.1 RED: add `CommitShapeTests` to T — `--commit main` accepted today must refuse naming `main`; `D903D14` (uppercase) refuses; abbreviated hex refuses; a lowercase 40-hex pin is accepted; no job folder written on refusal.
- [x] 1.2 GREEN: add `COMMIT_PATTERN` (lowercase 40- or 64-hex) and the refusal in `validate_run_config` (JF `:441-463`), naming the value and stating a branch or tag name is not a pin.
- [x] 1.3 Inversion: widen `COMMIT_PATTERN` to accept any string, confirm `CommitShapeTests` fails, restore by inverse patch.
- [x] 1.4 Full suite; counts up by the number added. Commit: `feat(remote-execution): a pin that is a branch name is a pin the runner resolves differently every day`

## Phase 2 — Slice 3: the probe (D2 + C5 + C5b, spec Group 2)

- [x] 2.1 **MEASURE (first, blocks 2.3):** build a scratch repo in a throwaway box, run `git init -q` then `git fetch --dry-run --depth 1 https://github.com/Daprosero/Domain_Adaptation <a-published-commit>`; record elapsed seconds and transferred bytes. Also confirm `--dry-run` + `--depth 1` behaves against the live remote. **If the probe is slow, D4's two-tier `ls-remote`-first fallback stops being optional** — record the number and the decision in the commit body.
- [x] 2.2 RED: correct the existing `CommitReachabilityTests` (T`:4002`) — delete the `cwd == target` assertion at `T:4099` and replace it with one asserting the probe's cwd is neither the target nor any repository holding the pin; update the argv assertion at `T:4097` for `--depth 1`. Add an e2e case: a local origin repo plus an unpushed commit must refuse.
- [x] 2.3 RED: add `ProbeAuthorityTests` — source-scan `GIT_ENV_ALLOWLIST` for credential/agent/HOME/global-config names (must be absent); assert `GIT_TERMINAL_PROMPT=0` and `stdin=DEVNULL` reach the child; an SSH-shaped URL refuses through the reachability path with the unauthenticated-probe sentence and no separate guard.
- [x] 2.4 GREEN: rewrite `_verify_commit_reachable(commit, repo_url, repo_ref)` in JF (`:823`) — `target` parameter **removed**; `tempfile.TemporaryDirectory()` → `git init -q` → `fetch --dry-run --depth 1`, `git init` **inside the same `try`**; widen `GIT_ENV_ALLOWLIST` for transport only (proxy, `SSL_CERT_FILE`, `SSL_CERT_DIR`, `GIT_SSL_CAINFO`); add `GIT_TERMINAL_PROMPT=0` and `stdin=subprocess.DEVNULL` to `_run_git` (`:784`); `import tempfile`.
- [x] 2.5 Mechanical: update the one production call site JF`:667` and the four positional call sites in T (`:4091`, `:4108`, `:4129`, `:4158`) — call-site edits only, no assertion changes.
- [x] 2.6 Correct the prose: JF docstrings `:20-36` and `:824-865`, and T`:4003-4033`. Add the probe paragraph to SK (documented nowhere today).
- [x] 2.7 Inversion (c): drop `--depth 1` from the probe argv, confirm the argv lock fails, restore by inverse patch. Inversion (d): point the probe's `cwd` back at the target, confirm the e2e case and the new cwd assertion fail, restore by inverse patch.
- [x] 2.8 Full suite; counts up. Commit: `fix(remote-execution): the probe asked the one repository that already knew the answer`

## Phase 3 — Slice 4a: the shared home + condition (1) (C1, spec Group 3)

- [x] 3.1 RED: add `CleanWorkingTreeTests` with **real git fixtures** — modified tracked file refuses naming the path; **untracked non-ignored** file refuses naming it (this case cannot be expressed with a mock); staged-not-committed refuses; ignored file passes; dirt outside the clone paths passes; not-a-repo and no-commits refuse carrying git's own words; repository byte-identical after every refusal.
- [x] 3.2 GREEN: add `PIN_CONDITIONS = ("clean-worktree", "pin-is-head", "pin-published")` and public `verify_pin_preconditions(*, target, commit, clone_paths, repo_url, repo_ref, decision)` to JF, dispatching in tuple order and raising `JobFolderError`. Implement `_refuse_dirty_worktree` as `git rev-parse HEAD` then `git status --porcelain -- <clone_paths…>` — **never `git diff`**: `diff` cannot see an untracked `run_search.py`, which is the case the condition exists to catch. Condition (3) becomes the third entry, calling the probe.
- [x] 3.3 Remove the direct `_verify_commit_reachable` call from `generate_job` (JF`:667`); call `verify_pin_preconditions(..., decision="generation")` before `resolve_clone_paths()`.
- [x] 3.4 Seam swap: change the patch target at T`:3574`, `:4479`, `:4773`, `:5661` from `_verify_commit_reachable` to `verify_pin_preconditions`. Four one-line edits; no assertion changes.
- [x] 3.5 Mock-fidelity repair: add `stdout=""` to the `Mock(returncode=0)` doubles at T`:4166` and `:4189`.
- [x] 3.6 **Prove the fidelity claim, do not assert it:** with 3.5 in place, run inversion (d) (probe cwd back at the target) and confirm `T:4166` still fails. If it does not, the doubles are permissiveness — replace both with a real git fixture repo instead of keeping them. Record which outcome occurred.
- [x] 3.7 Inversion (a): flip condition (1)'s emptiness test, confirm `CleanWorkingTreeTests` fails, restore by inverse patch.
- [x] 3.8 Full suite; counts up. Commit: `feat(remote-execution): nothing checked that the runner would receive the code generation validated`

## Phase 4 — Slice 4b: condition (2) + doctrine (C2, spec Groups 4 and 7)

- [x] 4.1 RED: add `PinIsHeadTests` (real fixtures) — pin behind HEAD **under** the clone paths refuses naming the changed paths and both commits; behind HEAD only **outside** them passes; a pin absent from history yields `unknown` and refuses; `read()` on a drifted job folder still only reports `drift`.
- [x] 4.2 GREEN: add `_refuse_stale_pin` calling the existing `_staleness_for` (JF`:877`) — no second diff — refusing on `drift` and `unknown`, carrying the wrapped error text forward.
- [x] 4.3 RED: add `PinConditionDoctrineTests` parsing SK for the exact header `| # | id | Condition | Enforced at | Refusal names |` and asserting `[row.id for row in rows] == list(JOBFOLDER.PIN_CONDITIONS)`, naming any id present in code and absent from the table. T has **no** `markdown_table_rows` helper (grepped) — add a local parser and a `SKILL_MD` constant from `REPOSITORY_ROOT` (T`:40`).
- [x] 4.4 GREEN: write the SK table plus the sentences "the tool never commits or pushes on your behalf" and "there is no dirty-tree escape hatch", and document the refuse-at-a-decision-point / report-at-`read()` asymmetry in JF.
- [x] 4.5 Inversion (b): make condition (2) accept `drift`, confirm `PinIsHeadTests` fails, restore. Inversion (f): delete one `PIN_CONDITIONS` entry from the SK table, confirm the doctrine lock fails naming that id, restore by inverse patch.
- [x] 4.6 Full suite; counts up. Commit: `feat(remote-execution): the staleness verdict only ever reported, at the one place that should refuse`

## Phase 5 — Slice 5: the `submit` gate (spec Group 6)

- [x] 5.1 RED: add `SubmitPinGateTests` (real fixture + `FakeAdapter`) — dirty tree refuses with **no adapter call and no ledger line**; drifted pin refuses before the adapter; unpushed pin refuses naming commit, remote and the missing push; a legacy entrypoint with no `run-config.json` behaves identically to today; a **malformed `run-config.json` refuses** rather than skipping all three conditions.
- [x] 5.2 GREEN: add `_gate_job_folder_pin(resolved_entrypoint)` to RC, called in `cmd_submit` after `product_for()` (RC`:497`) and before `digest_fn` (RC`:503`). Discriminate on **`run-config.json`'s presence**, not `_job_folder_staleness` (RC`:286-309`), which returns `None` for both the legacy shape and an unreadable config; **do not swallow `JobFolderError`** (precedent RC`:951`). Route through `JOBFOLDER.read()` and `_target_for_job_dir()` into `verify_pin_preconditions(..., decision="submission")`.
- [x] 5.3 Add `JOBFOLDER.JobFolderError` unwrapped to submit's CLI except-tuple (RC`:1397`) so stderr is byte-identical to generation's. Confirm staleness stays in the return payload.
- [x] 5.4 Stub the shared seam in the ~4 job-folder-shaped `cmd_submit` test classes (incl. T`:4860/4894/4914`, `:5744-5820`); two already stub `_verify_commit_reachable` and only swap the name.
- [x] 5.5 Inversion (e): remove the gate call from `cmd_submit`, confirm `SubmitPinGateTests` fails, restore by inverse patch.
- [x] 5.6 Full suite; counts up. Commit: `fix(remote-execution): submit spent the quota first and reported the staleness afterwards`

## Phase 6 — Slice 6: `--commit` optional (C3, spec Group 5)

- [x] 6.1 RED: add `CommitDefaultTests` (real fixtures) — omitted with a clean tree pins HEAD and stdout reports the commit and `commitSource`; omitted with a dirty tree refuses under condition (1) and defaults no pin into a job folder; an explicit `--commit` is never substituted or remote-derived; `commitSource` is **absent** from `run-config.json`.
- [x] 6.2 GREEN: `generate_job(commit: str | None = None)` resolving `git rev-parse HEAD` inside JF (one implementation shared by the CLI and the Python API); drop `required=True` at RC`:1313`; report `commit` and `commitSource` on generate-job stdout only.
- [x] 6.3 Remove the dead `return destination` at JF`:989` (no behavioural delta; recorded in the spec so it is not read as scope creep).
- [x] 6.4 Update `references/usage.md` and `SK:215`, which describe `--commit` as required.
- [x] 6.5 Inversion: make the default bypass `verify_pin_preconditions`, confirm the dirty-tree default case fails, restore by inverse patch.
- [x] 6.6 Full suite; counts up. Acceptance: `discover -s tests` green at 791 + the new tests, count verified to have **risen**. Commit: `feat(remote-execution): --commit can be omitted once HEAD is provably the code that was validated`

## Carried open questions (answer during apply, do not silently assume)

- [x] Q1 Confirm a job folder with an unreadable `run-config.json` must be **refused** at submit (a new refusal path the spec does not name).
- [x] Q2 Confirm swapping four offline test classes onto the wider `verify_pin_preconditions` seam is acceptable, rather than converting their fixtures into real git repositories.
- [x] Q3 Report task 2.1's measurement before deciding on the two-tier probe fallback.
