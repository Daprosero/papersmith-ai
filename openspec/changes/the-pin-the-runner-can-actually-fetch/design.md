# Design: the-pin-the-runner-can-actually-fetch

Change: `the-pin-the-runner-can-actually-fetch` · Store: engram (MCP down — mirrored here) · Input: the 12-requirement spec, the proposal, and the orchestrator's settled corrections (`git status --porcelain`, the `submit` gate).

**Verification note, stated first because it bounds every claim below.** This phase was given no shell tool (Read/Edit/Write/Grep/Glob only). Nothing here was executed. Every claim is either read off the source at a named line, or established by a tool that does not honour `.gitignore` (`Glob` — it returns `.venv/` and `implementations/`, so its negatives are real evidence). Items requiring a shell are marked **MEASURE** and carried into tasks.

---

## Technical approach

One shared precondition function in `jobfolder.py` holds all three conditions in order and is the **only** thing either decision point calls. `generate-job` calls it before `resolve_clone_paths()`; `submit` calls it before the digest, the plan, the adapter and the ledger. Two callers, one implementation, one message shape, one order — by construction rather than by convention.

---

## Architecture decisions

### D1 — The shared home is one public function that is also the single test seam

**Choice.** `jobfolder.verify_pin_preconditions(*, target, commit, clone_paths, repo_url, repo_ref, decision)` — public (crosses the module boundary to `remote_cli`), raising `JobFolderError`. It dispatches over an ordered module constant:

```python
PIN_CONDITIONS = ("clean-worktree", "pin-is-head", "pin-published")
```

`generate_job()` loses its direct `_verify_commit_reachable()` call; that check becomes condition 3 inside the new function. `decision` is the one word that differs between the two call sites (`"generation"` / `"submission"`).

**Alternatives rejected.** (a) Three separate calls from `generate_job` and three more from `cmd_submit` — six call sites that can drift in order or in one-sided omission. (b) The block in `remote_cli.py` — every git call and `_run_git`, the single composition point, live in `jobfolder.py`; `remote_cli` would have to reach into a private.

**Rationale, and the finding that makes it load-bearing.** Four existing test classes stay offline by patching exactly one name: `unittest.mock.patch.object(JOBFOLDER, "_verify_commit_reachable", return_value=None)` at `tests:3574`, `:4479`, `:4773`, `:5661`. That seam is the current whole-precondition boundary. If conditions (1) and (2) are added *beside* it, that boundary silently narrows and the suite breaks widely: `GenerateJobTests` (`:3567`) builds plain directories that are not git repositories at all, so condition (1) would refuse every generation in it; `StalenessTests` deliberately generates job folders in a non-repo (`:4604`, `:4633`) and with a pin absent from history (`:4618`) to reach `read()`'s `unknown` branch — states condition (2) exists to forbid. Making the new function the seam turns that whole migration into **four one-line patch-target swaps**, with every assertion in those classes untouched. Choosing the seam is choosing the size of this change.

### D2 — Condition (1) is `git status --porcelain`, and `git diff` is the wrong instrument

**Choice.** `git status --porcelain -- <clone_paths…>`, preceded by `git rev-parse HEAD` so "not a repository / no commits" refuses with git's own words instead of surfacing as a list of `??` lines.

**Rationale.** The two conditions ask different questions of different operands.

| | Question | Operands | Complete instrument |
|---|---|---|---|
| (1) | is the working tree the same bytes the runner will clone? | worktree + index vs `HEAD` | `status --porcelain` |
| (2) | does the pinned tree differ from HEAD's under these paths? | two committed trees | `diff --name-only` |

For (2), both operands are commits, so every path in either is tracked by construction and `diff` is complete — which is why `_staleness_for` (`jobfolder.py:923-925`) legitimately uses it and why this design reuses that function untouched. For (1), the danger set includes paths git does not track *at all*. `git diff` enumerates changes to tracked content; an untracked path is outside its domain by construction, not by omission. Demonstrated by the user in a scratch repo: one modified tracked file plus one never-added file — `git diff --name-only` reports only the modified one, `status --porcelain` reports `M existente.py` **and** `?? run_search.py`. This is the live case, not a hypothetical: `resolve_clone_paths()` walks the **working tree** (`jobfolder.py:349-351`), so a brand-new `run_search.py` that was never `git add`ed is validated happily by generation and is absent from the commit the runner clones. A `diff`-based condition (1) is blind to exactly the case the condition exists to catch.

Two further properties fall out for free and match the spec: `--porcelain` omits ignored files unless `--ignored` is passed, and the `-- <clone_paths…>` pathspec is the same intersection idiom `_staleness_for` already uses — no second prefix-matcher. The pathspec is also what keeps generation possible at all: `generate_job` itself writes untracked files under `<target>/tools/`, so an unscoped cleanliness check would forbid its own output.

### D3 — The probe asks from a scratch repository, shallow, unauthenticated, non-interactive

**Choice.** `_verify_commit_reachable(commit, repo_url, repo_ref)` — the `target` parameter is **removed**, because a repository that holds the pin cannot ask the question (`jobfolder.py:867`). Inside one `try`: `tempfile.TemporaryDirectory()` → `git init -q` → `git fetch --dry-run --depth 1 <url> <commit>`, both through `_run_git`. `git init` inside the same `try` is deliberate: a scratch repo that cannot be created is an unanswerable question and must refuse on the same path, carrying the URL (this is what makes `tests:4136`'s existing requirement true rather than producing the WIP patch's two spurious reds).

`--depth 1` matches `runner_bootstrap.py:169` exactly; `--dry-run` suppresses ref updates, not object transfer, so full depth would both ask a different question and pull unbounded history per generation.

**Authority.** `GIT_ENV_ALLOWLIST` widens only for asker-side transport — `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`/`NO_PROXY` (both cases), `SSL_CERT_FILE`, `SSL_CERT_DIR`, `GIT_SSL_CAINFO` — never authorization: no `HOME`, no `SSH_AUTH_SOCK`, no credential helper. `runner_bootstrap.py:70` holds `("PATH",)` and `:166-170` clones with no credential step, so a probe with more authority than the runner would pass for jobs the runner can never run — this change's own defect one layer up. Two additions to `_run_git` make "must not block on a prompt" true rather than hopeful: `GIT_TERMINAL_PROMPT=0`, and `stdin=subprocess.DEVNULL` (the parent's stdin is a tty in an interactive session, and `ssh` prompts on a channel `GIT_TERMINAL_PROMPT` does not govern). Both are set at the single composition point and are inert for the local calls.

**Rejected.** `ls-remote <url> <commit>` — matches ref *names*; a bare 40-hex pin returns empty with exit 0 either way. The existing docstrings say so and stay true.

### D4 — `submit` refuses before quota, and does not inherit `_job_folder_staleness`'s tolerance

**Choice.** A new `remote_cli._gate_job_folder_pin(resolved_entrypoint)` placed in `cmd_submit` immediately after `product_for()` (`:497`) and before `digest_fn` (`:503`) — before the digest walk, the plan, `adapter.submit()` and `LEDGER.append()`. It returns early when no `run-config.json` sits beside the entrypoint (the legacy shape, unchanged per spec Group 6), otherwise routes through `JOBFOLDER.read()` and `_target_for_job_dir()` and calls the shared function with the job's own declared pin, clone paths and remote. `JOBFOLDER.JobFolderError` joins submit's CLI except-tuple (`remote_cli.py:1397`) unwrapped, so the message reaching stderr is byte-identical to generation's.

**The finding the spec asked for.** `_job_folder_staleness` (`:286-309`) returns `None` on **two** paths, not one: the legacy shape *and* a `JobFolderError` from `read()` — a job folder whose `run-config.json` is malformed, missing a required field, or (after C4) carries a non-hex commit. Reusing it as the gate's discriminator would let a job folder skip all three conditions by being unreadable, which is the worse half of this change's own defect class. So the gate discriminates on the *file's presence*, and does not swallow `JobFolderError`. A legacy submission skipping all three conditions is acceptable and is not a finding: it has no declared pin, no declared clone paths and no declared remote, so there is nothing to check — and unlike a job folder, it never promises a runner a commit. A malformed job folder skipping them **would** be a finding, and is closed here. Precedent: `cmd_smoke_record` already states "Unlike `_job_folder_staleness()`, a `JobFolderError` here is NOT swallowed" (`:951`).

**Cost of condition (3) per submission — settled without the measurement.** The probe is one shallow fetch alongside an operation that already dials out, uploads a staged copy of the job folder and spends remote quota; a rehearsal (`submit --smoke`) is a real submission too. The guard cannot be more expensive than the thing it guards. The absolute number is still **MEASURE** (below), and the two-tier fallback is specified in case it is bad.

**Two-tier fallback, deferred, not adopted now.** If measurement shows the probe is slow: `git ls-remote <url> <repo.ref>` first and accept when the returned tip equals the pin (transfer-free, and tip==pin *proves* the remote serves it), falling through to the shallow fetch otherwise. It is a pure accelerator — a wrong or stale `repo.ref` only costs the fallback — so it does not resurrect the rejected "validate the pin is on the declared ref" guard. Not shipped unmeasured.

### D5 — `--commit` optional: resolution shared, labelling CLI-local

**Choice.** `generate_job(commit: str | None = None)` resolves `git rev-parse HEAD` inside `jobfolder`, so the Python API and the CLI share one implementation; `remote_cli.py:1313` drops `required=True`. The CLI already calls `JOBFOLDER.read(destination)` for staleness (`:1553`), so it reports the pin from `run_config["commit"]` and `commitSource` from whether `args.commit` was typed — **on stdout only**, never in `run-config.json`, where it would describe how the caller typed an argument rather than a fact about the job. No change to `generate_job`'s return type.

**Constraint.** This must land after conditions (1) and (2), and after commit-shape validation. HEAD is a safe default only because (1) proves the validated bytes are the committed bytes and (2) proves the pin is that commit.

### D6 — `repo.ref` confirmed: kept, one job

Grepped the whole skill: written at `jobfolder.py:546`, plumbed at `:482`, `:621`, `:695`, `remote_cli.py:1534`. **Zero readers** (`kaggle.py:740`'s `ref` is an unrelated Kaggle API row field). `runner_bootstrap.py:65` requires `repo` but reads only `repo["url"]`. Confirmed as the spec has it: keep it, and give it exactly one job — the remedy sentence in condition (3)'s refusal ("push it to `<ref>` on `<url>`"). Its second possible job (D4's deferred fast path) is not adopted.

---

## Data flow

```
generate-job                                    submit
    │                                              │
resolve_target/destination                    guard_entrypoint → product_for
    │                                              │
    │                                    _gate_job_folder_pin
    │                                     ├─ no run-config.json? → return (legacy)
    │                                     └─ JOBFOLDER.read() (errors NOT swallowed)
    ▼                                              ▼
    └────────► jobfolder.verify_pin_preconditions(…, decision) ◄────┘
                    │ (1) clean-worktree   rev-parse HEAD; status --porcelain -- <paths>
                    │ (2) pin-is-head      _staleness_for(...) ≠ fresh → refuse
                    │ (3) pin-published    scratch repo: init -q; fetch --dry-run --depth 1
                    ▼
              JobFolderError, carrying git's own text  ── refuse; nothing written,
                                                          nothing submitted, no ledger event
    │                                              │
resolve_clone_paths → build → .partial → rename   digest → plan → adapter.submit → ledger.append
```

Order is cheapest-first: two local, instant conditions before the one network call.

---

## File changes

| File | Action | What |
|---|---|---|
| `scripts/jobfolder.py` | Modify | `PIN_CONDITIONS`, `verify_pin_preconditions`, `_refuse_dirty_worktree`, `_refuse_stale_pin`; `_verify_commit_reachable` rewritten (scratch repo, `--depth 1`, loses `target`); `GIT_ENV_ALLOWLIST` widened; `_run_git` gains `GIT_TERMINAL_PROMPT=0` + `stdin=DEVNULL`; `import tempfile`; `validate_run_config` commit shape; `generate_job(commit=None)`; docstrings `:20-36`, `:824-865`; dead `return destination` `:989` removed |
| `scripts/remote_cli.py` | Modify | `_gate_job_folder_pin`; call in `cmd_submit` after `product_for`; `JobFolderError` into submit's except-tuple `:1397`; `--commit` no longer `required` `:1313`; `commit`/`commitSource` on generate-job stdout |
| `SKILL.md` | Modify | The three-condition table (new parseable header), the probe paragraph, "never commits or pushes on your behalf", "no dirty-tree escape hatch" |
| `tests/test_remote_execution.py` | Modify | 4 seam swaps, 4 probe call-site edits, 1 argv assertion, 1 defect assertion deleted, 2 mock-fidelity repairs, `SKILL_MD` constant, 5 new classes |

## Interfaces

```python
PIN_CONDITIONS = ("clean-worktree", "pin-is-head", "pin-published")   # order is the contract

def verify_pin_preconditions(*, target: Path, commit: str, clone_paths: Sequence[str],
                             repo_url: str, repo_ref: str, decision: str) -> None:
    """Raises JobFolderError on the first failing condition, in PIN_CONDITIONS order."""

def _verify_commit_reachable(commit: str, repo_url: str, repo_ref: str) -> None:   # no `target`
```

Doctrine table header the lock parses (exact line):

`| # | id | Condition | Enforced at | Refusal names |`

The lock asserts `[row.id for row in rows] == list(JOBFOLDER.PIN_CONDITIONS)` and names any id present in code and absent from the table. Prose cannot be held to code; a table can.

---

## Commit decomposition

| # | Commit | Depends on | Est. lines (add+del) |
|---|---|---|---|
| 1 | *(landed `a60e5d0`)* D1 adapter side-load | — | — |
| 2 | C4 commit-shape validation | — | ~60 |
| 3 | D2+C5+C5b: scratch-repo probe, env allowlist, `--depth 1`, `stdin=DEVNULL`, docstrings, SKILL.md probe prose | — | ~230 |
| 4 | C1+C2 + the shared home + `PIN_CONDITIONS` + doctrine table + lock + 4 seam swaps | 3 | ~290 |
| 5 | Group 6: the `submit` gate | 4 | ~195 |
| 6 | C3 `--commit` optional + dead `return` removal | 4, 2 | ~120 |

**Independence proof.** 2 touches only `validate_run_config` and its own tests; it shares no line with 3, 4, 5 or 6 and can land in any position. 3 rewrites one function body, one constant and two docstrings; it does not create or call the shared home. **Hard constraints:** 4 → 5 (5 calls the function 4 introduces); 4 → 6 (a HEAD default is only safe once (1) and (2) refuse — landing 6 first ships exactly the silent-wrong-pin behaviour this change exists to remove); 2 → 6 (a default pin must be shape-checked). **Soft:** 3 → 4, so the "carry git's own message" idiom is already established where `tests:4200` depends on it. The chain is 2 · 3 → 4 → 5 → 6.

---

## Testing strategy

| Group | New class (name verified free) | RED first | Real git fixture? |
|---|---|---|---|
| 1 · C4 | `CommitShapeTests` | `--commit main` accepted today → assert refusal naming `main`; uppercase/abbreviated hex | no (pure validation) |
| 2 · probe | *(corrected `CommitReachabilityTests`)* + `ProbeAuthorityTests` | probe runs in a repo that holds the pin → passes today, must refuse from scratch; allowlist source-scan for credential/auth names | yes, e2e (a local origin repo + an unpushed commit) |
| 3 · C1 | `CleanWorkingTreeTests` | modified tracked file; **untracked** file; dirt outside clone paths passes; non-repo carries git's words | yes — the untracked case cannot be expressed with a mock |
| 4 · C2 | `PinIsHeadTests` | pin behind HEAD under clone paths refuses; behind only outside them passes; absent pin (`unknown`) refuses; `read()` still only reports | yes |
| 5 · C3 | `CommitDefaultTests` | omitted pins HEAD + stdout reports source; omitted with dirty tree refuses under (1); explicit is never substituted | yes |
| 6 · submit | `SubmitPinGateTests` | dirty tree → no adapter call, **no ledger line**; drifted pin; unpushed pin; legacy entrypoint identical; malformed run-config refuses | yes + `FakeAdapter` |
| 7 · doctrine | `PinConditionDoctrineTests` | delete a table row → fail naming the id | n/a |

**Inversions planned for every lock expected to pass on first run** (invert the production line, observe red, restore **by inverse patch**, never `git checkout --`): (a) flip condition (1)'s emptiness test; (b) make condition (2) accept `drift`; (c) drop `--depth 1` from the probe argv; (d) point the probe's `cwd` back at the target; (e) remove the gate call from `cmd_submit`; (f) delete one `PIN_CONDITIONS` entry. Verify by the total count **going up**, not by the suite staying green — a redefined class name silently disabled seven tests here once. Grep every class and helper name before adding it: `CleanWorkingTreeTests`, `PinIsHeadTests`, `CommitShapeTests`, `CommitDefaultTests`, `SubmitPinGateTests`, `PinConditionDoctrineTests`, `ProbeAuthorityTests`, `verify_pin_preconditions`, `PIN_CONDITIONS`, `_gate_job_folder_pin`, `COMMIT_PATTERN` are all free today (grepped); `CommitReachabilityTests` and `ServiceResolutionTests` are occupied.

**The mock-fidelity claim, argued from the source rather than asserted.** `tests:4166` and `:4189` mock `_run_git` as `Mock(returncode=0)`. Once generation asks git more questions, `result.stdout` is an auto-`Mock` and `.splitlines()` returns a truthy `Mock`, so condition (1) reads a clean tree as dirty and `_staleness_for` reads no diff as `drift`: both refuse. `stdout=""` makes the double answer as real git answers **for a clean tree** — `"".splitlines() == []` — which is the fixture those two tests were always assuming. It is not permissiveness *for their subject*: their subject is reachability, and both stay reachable-red under inversion (d) and under removing the `_verify_commit_reachable` call. It **is** silent about conditions (1) and (2), which is exactly why those two conditions are locked with real git fixtures in their own classes and never through this double. **Planned proof at apply:** run inversion (d) and confirm `:4166` fails with the corrected doubles in place. If it does not, replace both doubles with a real fixture repo (the spec's stated preference) rather than keeping them.

**The existing seven, precisely.** `:4099` (`cwd == target`) is the defect written down as a requirement — deleted, replaced by an assertion that the probe's cwd is neither the target nor any repository holding the pin. `:4097`'s argv assertion gains `--depth 1`: *more* faithful to its own class docstring, which claims the probe is the operation the runner performs, and `runner_bootstrap.py:169` is `fetch --depth 1 origin <commit>`. `:4200` keeps its `"not our ref"` substring assertion, which is why every new refusal carries git's message forward (`_run_git:816-819` embeds `stderr`; `_staleness_for`'s `unknown` reason embeds the wrapped error; condition (1) wraps `_run_git`). **One correction to the "the other three stay untouched" expectation:** their *assertions* stay untouched, but four tests (`:4080`, `:4101`, `:4113`, `:4136`) pass `target` positionally to `_verify_commit_reachable` and each needs a one-line call-site edit once that parameter is removed. Keeping a dead `target` parameter to avoid four mechanical lines would be prose that lies.

**Commands.** `python3 -m unittest tests.test_remote_execution` (254), then `python3 -m unittest discover -s tests` (791 baseline). Never pytest; `-k` misses new classes. Throwaway boxes under `implementations/_<name>`, deleted after. `implementations/Domain_Adaptation` is never edited. `fd`/`rg` need `--no-ignore` to see `implementations/` at all.

---

## Consumer inventory (every widened contract)

| Contract | Consumers | Effect |
|---|---|---|
| `_verify_commit_reachable(target, commit, url)` → `(commit, url, ref)` | `jobfolder.py:667`; `tests:4080/4101/4113/4136` | 1 production line, 4 mechanical test lines; no assertion changes |
| Probe argv + a preceding `init -q` in a scratch cwd | `tests:4095-4098`; docstrings `:20-36`, `:824-865`; SKILL.md (documents it nowhere today) | argv assertion updated; prose corrected |
| `GIT_ENV_ALLOWLIST`, `GIT_TERMINAL_PROMPT`, `stdin=DEVNULL` | every `_run_git` call: `rev-parse`, `cat-file`, `diff`, new `status`, `init`, `fetch` | inert for local calls; no test asserts the allowlist today (grepped: zero hits) — a source-scan lock is added |
| Whole-precondition stub seam | `tests:3574`, `:4479`, `:4773`, `:5661` | 4 one-line patch-target swaps; **without this seam the migration is suite-wide** |
| `validate_run_config` commit shape | `build_run_config` (generation) and `read()` (**every** read) | in-suite fixtures are all 40-hex or real commits (grepped: `"abc123"` at `:1252` is already an expected refusal, `:5576` is `shard_io`); on disk, `Glob` finds **no `run-config.json` anywhere in the repo, ignored paths included** — no job folder can be invalidated |
| `cmd_submit` gains refusals and can raise `JobFolderError` | CLI dispatch `:1397`; ~22 direct `cmd_submit` call sites in tests, of which the job-folder-shaped ones (~4 classes, incl. `:4860/4894/4914`, `:5744-5820`) now meet the gate | except-tuple widened; those classes stub the shared seam (two already stub `_verify_commit_reachable` and only swap the name) |
| `--commit` optional | `remote_cli.py:1313`, `:1532`; `references/usage.md` and `SKILL.md:215` describe it as required | flag and docs updated; every existing caller passing `--commit` is unaffected |

## Threat matrix

| Boundary | Applicability | Design response | Planned RED tests |
|---|---|---|---|
| Documentation-like paths | **N/A** — no file is classified or executed by this change; `guard_entrypoint` is untouched | — | — |
| Git repository selection | **Applicable** — the probe's cwd *is* the defect; `_run_git` uses `cwd=`, never `git -C` on a raw argument | probe runs in a fresh `TemporaryDirectory`, never the target, never a repo holding the pin; conditions (1)/(2) run against `resolve_target()`'s already-resolved path | probe cwd is neither target nor pin-holder; refusal when the scratch repo cannot be created |
| Commit state | **Applicable** — condition (1) is entirely about index/worktree semantics | `status --porcelain` covers modified, staged, and untracked (`??`); ignored excluded; empty index / no commits refuse via `rev-parse HEAD` with git's words | one test per state: modified, staged-not-committed, untracked, ignored-passes, no-commits, not-a-repo |
| Push state | **Applicable** — condition (3) is destination/ref resolution against an untrusted URL | pin is compared against what the declared remote can serve; `repo.ref` appears only in the remedy sentence; SSH-shaped URLs refuse through the same path with an enriched message, not a second guard | unpushed pin refuses; SSH URL refuses naming the unauthenticated probe; no auth var reaches the child |
| PR commands | **N/A** — no PR or push automation; the tool never stages, commits, pushes, stashes or fetches into the target | — | a test asserting the working tree, index, refs and remotes are unchanged after every refusal |

## Migration / rollout

No migration. `Glob` (which does not honour `.gitignore`) finds no `run-config.json` anywhere in the repository, so no job folder on disk can be invalidated by the shape check or newly refused by the submit gate. Each slice is one commit and reverts independently, except that 6 must be reverted before 4.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **MEASURE unavailable this phase** — probe elapsed time and bytes against the live remote are still unmeasured (no shell) | certain | First task of slice 3: build a scratch repo, run `fetch --dry-run --depth 1` against `https://github.com/Daprosero/Domain_Adaptation`, record time and bytes. Adopt the D4 two-tier fast path only if it is bad. The `--depth 1` decision does not turn on the number |
| `--dry-run` + `--depth 1` interaction unverified against a real remote | Low | Same task; fallback is dropping `--dry-run` (the scratch dir is discarded anyway) — but `tests:4097` then loses a meaningful assertion, so prefer keeping it |
| The `submit` gate tightens the workflow: every rehearsal and every resubmission now requires a clean tree and pin==HEAD | **Med** | Intended, and it strengthens `cmd_readiness`'s existing `latest.commit == run_config["commit"]` binding (`remote_cli.py:1071`): the rehearsed bytes and the submitted bytes become the same bytes. Refusals name the exact commands; the tool never commits or pushes |
| Slice 4 exceeds 400 changed lines | **Med** | Splits cleanly at the seam: 4a = shared home + condition (1) + seam swaps, 4b = condition (2) + doctrine table + lock |
| The mock-fidelity repair turns out to be permissiveness | Low | Proof obligation (inversion (d)) is a task, not a claim; failing it forces the real-fixture replacement |
| A corporate proxy or custom CA still breaks the probe | Low | Refusal is local, free and re-runnable; the message names the proxy possibility |

**Review budget forecast (session budget 1200).** ~895 authored lines (additions + deletions) across five slices of 60–290. Under the session budget as one review; **over the 400-line per-PR guard**, so chained PRs are recommended, ordered 2 · 3 → 4 → 5 → 6. This exceeds the proposal's ~600 because the `submit` gate became its own slice and the doctrine table plus its lock are real work.

## Open questions

- [ ] **MEASURE**: probe cost (time, bytes) — decides whether D4's two-tier fast path ships.
- [ ] Confirm the D4 decision that a job folder with an unreadable `run-config.json` must be **refused** at submit rather than inheriting `_job_folder_staleness`'s silent `None`. It is a new refusal path the spec does not name.
- [ ] Confirm that swapping four offline test classes onto the wider `verify_pin_preconditions` seam is acceptable (it is what keeps slice 4 small), rather than converting their fixtures into real git repositories.
