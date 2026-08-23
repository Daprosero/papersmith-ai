# Verification Report: the-invocation-that-goes-straight-through

Mode: full (proposal + spec + design + tasks all present, all 51 tasks checked).
Method: driven execution with self-built doubles, not test-reading. Nothing launched
to Kaggle. All checks below ran offline under an outbound-socket guard (see Evidence).

## 1. Test suite (independently re-run, not re-derived from prior claims)

`python3 -m unittest discover -s tests`, run under a global outbound-socket guard
(`socket.socket.connect`/`connect_ex` patched to raise on any non-loopback address,
loaded via `sitecustomize.py` on `PYTHONPATH` so it also covers the real `subprocess.run`
calls in `test_driver_selftest_imports_kagglesdk`, which do not override `env=` and so
inherit the guard):

```
Ran 1125 tests in 94.638s
OK
```

Guard log: empty (no file created) → **zero outbound connection attempts, blocked or
otherwise, across the entire suite.** Independently confirms the 1125/OK/0-outbound
claim.

Baseline re-measured directly from git (`git worktree add --detach <tmp> 3085907`,
the commit immediately preceding this change's first commit `21deeee`): **1084 tests**,
confirmed both by `unittest discover` and by static `def test_` count. Per-commit
`def test_` counts in `tests/test_remote_execution.py` read via `git show <sha>:...`:

| commit | test count | delta |
|---|---|---|
| `3085907` (base) | 355 | — |
| `21deeee` | 363 | +8 |
| `2f23340` | 369 | +6 |
| `5469592` | 375 | +6 |
| `3be19a5` | 386 | +11 |
| `a468cbe` | 396 | +10 |

Total: 355 → 396 = **+41**, matching the repo-wide 1084 → 1125 rise exactly. This
independently confirms the rise is real and reproducible, and matches the per-commit
breakdown given in the verification brief (7+1, 6, 6, 11, 10 = 41).

**Finding (WARNING, documentation only):** `tasks.md` (5.9, 6.3) asserts "baseline
measured at apply time was 1115, not the design-time estimate of 1084" and reports
"1115 + 10 = 1125." This is not supported by git history: the actual baseline at
the commit preceding this change is 1084 (matching the design's own estimate), and
this change added 41 tests, not 10. The final acceptance criterion — a rising count,
1125, correctly reported as a rise rather than a bare "OK" — is still satisfied; only
`tasks.md`'s own bookkeeping of *how much* it rose by is wrong. Does not affect
correctness of the shipped code.

## 2. Driven checks (executed, not read)

### 2.1 Driver `selftest`
Ran directly: `python3 kaggle_driver.py selftest` under this repo's own interpreter →
`{"ok": true, "interpreter": "/Library/Developer/CommandLineTools/usr/bin/python3"}`,
exit 0. Ran under `python3.11` and `python3.12` (present on this machine, confirmed to
lack `kagglesdk`) → both refuse, naming the exact resolved interpreter path and
`pip install --user kaggle==1.7.4.5`, exit 1. **WORKS.**

### 2.2 `submit` with no `--worker`, doubles built here (not the suite's fixtures)
Built a `FakeAdapter(ADAPTER.Adapter)` with 5 workers, no subprocess, no network, and
drove `remote_cli.cmd_submit()` directly:
- All 5 healthy → `packer.select()` picked `w1` (declared order), `adapter.submit`
  called exactly once, for `w1`. No prompt, no exception, no fork. **WORKS.**
- `w2` revoked (raises `WorkerUnauthorized` from `list_active`), no `--worker` →
  selection skipped `w2` silently and picked the next healthy account; `w2` never
  appeared in `adapter.submitted`. **WORKS.**
- All 5 revoked → `PackerError` raised naming every account and the remedy
  (restore a credential / retry), zero quota spent. **WORKS.**

### 2.3 `submit --worker w2` naming a revoked account
Same fake adapter, `worker="w2"` (revoked) supplied explicitly → `ADAPTER.WorkerUnauthorized`
propagated out of `cmd_submit` uncaught, naming `w2`; `adapter.submitted == []` (no
quota spent, no silent reroute to another account). **WORKS**, exactly as Group 2's
spec requires. (The real adapter's own message additionally names the remedy —
"re-materializing that account's token through the accounts skill's own command" —
confirmed by source inspection of `kaggle.py:956-961`; my fake adapter's exception
text was my own stand-in and did not carry that remedy string, which is why this
check is split between driven wiring proof and source-read remedy confirmation.)

### 2.4 The credential's path
- `.token_path` attribute access (AST, not text — checked directly): exactly one
  occurrence in the whole skill, `kaggle.py:523`, inside `_env_for()`. Every other
  hit anywhere in the skill is prose (docstrings), confirmed by reading each match.
- `kaggle_driver.py`: zero `os.environ`/`getenv` reads anywhere (`rg` confirms zero
  code hits; the string "token"/"KAGGLE_API_TOKEN" appears only in docstrings, and
  the suite's own `test_the_driver_never_reads_the_environment_at_all` correctly
  AST-scans for actual attribute/name access rather than text, so it is not fooled
  by the prose). **The driver reads the environment zero times — confirmed.**
- By-value, not by-path: `_env_for()` does `handle.token_path.read_text().strip()`
  onto `KAGGLE_API_TOKEN` — the file's content crosses, never its path. **Confirmed
  by source; already covered by a passing test** (`test_the_env_value_is_the_files_stripped_content_and_never_its_path`).

## 3. The interception points — bypassed on purpose, both go RED (the hardest requirement)

**This is the single most important result in this verification.**

### 3.1 Inner (driver → wire, `_RecordingTransport` on the real `requests.Session`)
Copied `kaggle_driver.py` to a scratch location (the shipped repo file was never
edited — confirmed unchanged sha256 `e408f1cc...` before and after), patched only
the copy's `cmd_submit` to construct a second, un-mounted `KernelsApiClient(KaggleHttpClient())`
inline (the exact bypass the spec names: "calling the real dependency some other
way"). Ran it under the outbound-socket guard, driving the SAME `_kaggle_http_client_with_recorder`
setup the real test uses. Result:

```
cmd_submit raised: ConnectionError: HTTPSConnectionPool(host='www.kaggle.com', port=443):
  ...blocked real connect() to ('35.244.233.98', 443)
recorder.calls on the MOUNTED (bypassed-past) recorder: 0
```

The bypassed code reached for a **real socket to Kaggle's real resolved IP** — my
guard blocked it. `recorder.calls == 0` proves `assertGreater(len(recorder.calls), 0, ...)`
would fail exactly as the spec requires: a bypassed double does not pass silently,
it goes to zero and fails. This also independently proves the interception point is
not vacuous — the production code path genuinely reaches for the network the instant
the recorder is skipped.

### 3.2 Outer (adapter → driver subprocess boundary)
No repo file touched; monkeypatched `KAGGLE.subprocess.run` at runtime (scoped to
one process) to fabricate a successful result without ever launching the fake
recording driver on disk — i.e. "call the driver inline," the exact inversion named
in `tasks.md` 2.8. Result: `adapter.submit()` still returned a (fabricated) success,
but **zero record files were created** by the fake driver, so
`assertGreater(len(records), 0, ...)` would fail. **Confirmed reachable-red.**

### 3.3 The revoked-account swallow, restored on purpose
Rebound `packer.plan` at runtime to a byte-for-byte reproduction of the OLD
`except Exception: pass` (swallowing `WorkerUnauthorized` too, falling back to the
ledger count) and re-ran the exact `--worker w2` (revoked) scenario:

```
BEFORE (real code):  refused, adapter.submitted == []
AFTER (old swallow):  cmd_submit returned normally, adapter.submitted == ['w2']
```

**Confirmed: with the old swallow restored, a revoked account is genuinely
submitted against** — the exact regression Decision 4's narrowed `except` exists to
prevent, reproduced live rather than asserted from reading the diff.

### 3.4 The drift lock
Read the real pin (`1.7.4.5`) against the real installed version (`1.7.4.5`, match,
no failure) and separately simulated a drifted pin (`1.7.0.0`) against the real
installed version → `AssertionError` naming both versions. `DoctrinePinTests` (10
tests) run live: all pass. **Confirmed both directions.**

## 4. Surviving decision paths — walked one by one

| Command | Requires `--worker`? | Decision reaches the caller? |
|---|---|---|
| `submit` | optional (auto-selects) | **No** — the one command this whole change targets; proven driven above |
| `poll` | never took one; splits worker from `--submission-id` | No |
| `fetch` | never took one, same reason | No |
| `status` | no adapter/worker at all | No |
| `generate-job` | no worker (runs before any submission) | No — its many required flags describe *what* to run, not a credential/account fork |
| `reconcile` | **required=True** | Reports on an *already-chosen* account's local-vs-remote state (`worker.get("worker") == worker` filters the ledger); never a new submission decision. Reasoning holds. |
| `smoke record` | **required=True** | Tags which account produced an artifact you already fetched from that account; not a selection fork. Reasoning holds. |
| `readiness` | **required=True** | Answers "is this ready to run on *this* worker," a question that is inherently per-worker by construction (`latest.get("worker") == worker`). Reasoning holds. |

Judged by reading each function's body, not by trusting the code comment alone.
**No surviving path where an ordinary `submit` invocation needs the caller to decide,
fork, fix a credential, or run a maintenance command first.** The three remaining
`required=True` sites are legitimately outside the "send a search" scope the spec
itself draws (Group 1 targets `submit` only), and each is genuinely account-specific
by what it computes, not a residual "which account" fork.

## 5. Hand-written vs. derived rosters

| Item | Derived or hand-written | Locked to reality? |
|---|---|---|
| Worker declared order | Derived — `accounts_cli list --json`, subprocess, not cached | N/A, live |
| Capacity metering (`in_flight`) | Derived — `list_kernels` + `get_kernel_session_status`, real SDK calls | N/A, live |
| `KAGGLE_WORKER_CAPACITY = 2` | **Hand-written** | No automated lock ties it to Kaggle's actual current allowance (the module's own comment says so explicitly: "measured...not a law"); a test only asserts the constant equals itself. This is inherent — nothing in this repo can derive a live service policy — and the code is honest about it, but it is worth naming since the brief specifically asked. |
| `_KAGGLE_STATUS_TO_SEAM` (status enum table) | Hand-written | Closed vocabulary, unmapped falls to `"unknown"` deliberately rather than guessing — not a rise risk |
| `MODULE_SCRIPTS` (vocabulary guard) | Hand-written list | Now includes `kaggle_driver.py` (this change's own fix, task 5.8); does **not** include `tests/test_remote_execution.py` itself |
| Credential-transport table (`SKILL.md`) | Hand-written prose | Every one of its 10 rows names a real, existing, passing test (verified directly — grepped each cited test name) |

## 6. Claimed-but-unproven, named honestly rather than settled

- **`fetch`'s per-file URL auth** (`list_kernel_session_output`'s URLs): `SKILL.md`
  explicitly marks this `unverified-by-rehearsal` (line 221) and `kaggle_driver.py`'s
  own docstring documents the defensive choice made instead of guessing. Confirmed
  this is recorded as unverified, not silently upgraded to a settled fact anywhere I
  checked (`SKILL.md`, the driver's docstring, the design doc).
- No other claim I checked was recorded as settled without a passing test backing
  it — every credential-transport table row maps to a real test (grepped and
  confirmed each of the 10 cited test names exists exactly once).

## 7. Pre-existing findings, explicitly NOT this change's regression (per the brief)

- `tests/test_remote_execution.py` carries the target vocabulary (`MIL_CREDA`,
  `CREDA`, `harness.py`) far beyond the ~225 figure I could reproduce exactly
  (my own counts: 108/220/38 raw hits across the three patterns, overlapping);
  `MODULE_SCRIPTS` does not scan the test file itself. Confirmed pre-existing and
  deliberately unaddressed — production scripts under `.claude/skills/remote-execution/`
  are independently confirmed clean (zero hits each).
- `openspec/config.yaml` still pins only `test_extract_pdf.py`; confirmed untouched
  by this change (`git diff --stat` across all 5 commits shows no touch to it or to
  `implementations/Domain_Adaptation`).

## 8. New findings from this verification (not previously named in the brief)

**WARNING — stale module docstring in `adapters/kaggle.py` (lines 1-63).** The
file's own header still reads "to shell out to the `kaggle` command-line tool"
and "Run with any Python 3.10+ (stdlib-only, no `kaggle` package import — this
module shells out to the CLI, it never imports it)." Both sentences are false of
the code as shipped: `submit`/`poll`/`fetch`/`list_active` all shell out to
`kaggle_driver.py`, not the `kaggle` CLI (confirmed at lines 799/849/879/919), and
the module is not "no `kaggle` package import" in spirit — its sibling driver is.
Group 6 of the spec scoped this rewrite to `SKILL.md`'s table and `## Environment`
only, so this is not a spec violation, but it is exactly the class of stale doctrine
this whole change exists to eliminate, left standing one file over. Does not affect
behavior — nothing reads this docstring to make a runtime or loading decision, unlike
the `SKILL.md` frontmatter, which is correctly updated (verified below).

**SUGGESTION — dead code.** `_normalize_status_word()` (kaggle.py:220) is defined
but called nowhere in the file (confirmed via `rg`); its own docstring still claims
`list_active()` is one of its callers, which is no longer true now that
`list_active()` reads bare `KernelWorkerStatus` names via `_KAGGLE_STATUS_TO_SEAM`
directly. Harmless, but should be removed or its docstring corrected.

## 9. Doctrine frontmatter — the three falsified claims

Checked `SKILL.md`'s `description:` field directly:
- "shells out to the `kaggle` CLI" → **removed**; now reads "shells out to
  `adapters/kaggle_driver.py`."
- "stdlib-only" (unqualified) → **removed**; now reads "Stdlib-only except that
  one named driver script."
- "the installed client authenticates `KAGGLE_API_TOKEN` by value" → **restated
  correctly**, attributed to `kagglesdk`'s own `_try_fill_auth()` specifically,
  with an explicit clause that the CLI itself authenticates neither a path nor
  that variable — the opposite of the retracted claim, not a softened repeat of it.

## 10. Scope

`git diff --stat 3085907..a468cbe` across all 5 commits touches exactly:
`.claude/skills/remote-execution/{SKILL.md,scripts/adapter.py,scripts/adapters/kaggle.py,
scripts/adapters/kaggle_driver.py,scripts/packer.py,scripts/remote_cli.py}`,
`tests/test_remote_execution.py`, `requirements.txt`, and this change's own
`openspec/changes/the-invocation-that-goes-straight-through/*`. No other skill,
`openspec/config.yaml`, or `implementations/Domain_Adaptation` touched. Confirmed.
Class/method name collisions: none, checked independently by AST (top-level
`ClassDef` names and every `test_` method within every class), not merely by
running the one lock test that already covers class names.

## Verdict

**PASS WITH WARNINGS.**

No CRITICAL findings. Every acceptance-criterion behavior in the spec was driven
with hand-built doubles and observed working, not merely read as "a test exists for
this": auto-selection, revoked-account refusal-with-remedy, all-revoked refusal,
the Bearer-not-Basic wire proof (existing test, re-run), both interception points
proven reachable-red by actually bypassing them (one of which reached for a real
Kaggle IP that only my socket guard stopped), the swallow regression reproduced
live, and the drift lock fired on a simulated drift. 1125/OK/zero-outbound
independently reconfirmed from a fresh baseline worktree, not merely re-stated.

3 WARNINGS (tasks.md's own +10/1115 bookkeeping is wrong though the true rise of
+41 from a true baseline of 1084 is correct and matches the spec's own acceptance
wording; the stale kaggle.py module docstring; nothing else rises to CRITICAL).
1 SUGGESTION (dead `_normalize_status_word`). 0 CRITICAL.

Nothing was launched to Kaggle. Zero outbound socket attempts observed, confirmed
independently under a fresh guard covering both the parent process and the real
child processes the suite spawns.
