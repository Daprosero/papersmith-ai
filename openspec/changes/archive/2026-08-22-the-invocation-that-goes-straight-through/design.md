# Design: the-invocation-that-goes-straight-through

Domain: `remote-execution` · Store: openspec · Depends on: `proposal.md`

## Technical Approach

`adapters/kaggle.py` keeps its child-process boundary and changes only what the
child is: a skill-shipped SDK driver (`adapters/kaggle_driver.py`) instead of the
`kaggle` binary. The credential's single sink (`_env_for()`) is untouched.
Selection, health and metering are rebuilt on measured SDK calls so an ordinary
`submit` needs no argument, no fork and no repair from the user.

## Architecture Decisions

### Decision 1: Child-process SDK driver, not an in-process SDK call

| Option | Tradeoff | Decision |
|---|---|---|
| In-process `kagglesdk` | `KaggleHttpClient.__init__` (`:96-110`) takes **no token**; `_try_fill_auth` (`:300`) reads the process-global `KAGGLE_API_TOKEN`. Two concurrent workers race one global, or we set `_signed_in`/`_session.auth` on a class its own authors call mid-migration | Rejected |
| Child SDK driver | One credential per process environment; argv/env interception survives | **Chosen** |

**Rationale — the convergence is the argument, not testability.** The one route to
Bearer auth is a process global, so a process per submission is what makes
concurrent credentials *correct*; that same boundary is what keeps an argv/env
observation point alive. Correctness and observability are the same fact here.
Removing the boundary would break `per-process`/`really-concurrent` and blind the
proof in one stroke.

### Decision 2: Two interception points, each with a reached-assertion

| Point | Where | Answers |
|---|---|---|
| **Outer** (adapter → driver) | fake driver on an injected path, records argv + received env | which credential crossed, to which process, uncrossed, under overlap |
| **Inner** (driver → wire) | a recording `requests` transport adapter mounted on the client session, in the driver's own tests | what the prepared request contained |

Route A (controlled HTTP endpoint) is **rejected on measurement**: `kaggle_env`
selects from a closed five-host enum, `LOCAL` is `http://localhost` with no port,
`get_endpoint` is a dict lookup. No variable carries a base URL, so A needs
privileged port 80 or a rewrite of `_env_to_endpoint`. Route B intercepts below
`BearerAuth.__call__` and above the socket, on a documented `requests` extension
point, and returns a synthetic JSON response `_prepare_response` deserializes.

**Telling a bypassed double from a working one — three independent failures:**

1. Every recorder asserts a **non-zero recorded-call count** before asserting
   anything about content. Zero records is a failure, never a vacuous pass.
2. **`adapters/kaggle.py` may not name `kagglesdk` at all** (AST + text lock). An
   edit that inlines the SDK and empties the recorder fails this instead.
3. The driver constructs a client at **exactly one expression** (AST-locked, the
   idiom C5 already uses for `.token_path`). Operation functions receive a client;
   a self-built one would bypass the mounted transport and attempt a real socket.

A fourth, general lock: every `ClassDef` name in `tests/test_remote_execution.py`
must be unique — a duplicate class name once silently disabled seven tests here
while the suite still reported OK.

### Decision 3: The credential's path, end to end

`materialize` writes the file → `CredentialHandle(worker_id, token_path)` →
`_env_for()` reads it once, strips it, and puts the **value** on
`KAGGLE_API_TOKEN` of one child environment → `subprocess.run(env=...)` → the
SDK's `_try_fill_auth` reads that variable → `BearerAuth`. Unchanged from today
except the child's identity.

**Exactly one reader, structurally:** the parent reads the file at one AST-locked
expression; the **driver reads neither the file nor the variable** — new lock:
the strings `KAGGLE_API_TOKEN` and `token` occur **zero times** in the driver
source. A second reader cannot appear without failing one of the two locks.

**Fails closed:** unreadable file and empty-once-stripped file both refuse before
any process starts (unchanged). The driver's error path prints a typed message
and never `os.environ`, so a traceback cannot become a leak.

**Open, resolved by measurement in apply:** the child env allowlist is
`{PATH, KAGGLE_API_TOKEN}`. A `driver selftest` op run as a real child under
exactly that env must import `kagglesdk`. If user-site resolution needs `HOME`,
the allowlist widens by exactly one non-credential variable and C6's row states
the new exact set — a documented widening, never a silent one.

### Decision 4: `save_kernel` request construction

`submit()`'s staging (metadata completion, run-config cell injection) is
byte-identical to today. Only the last step changes: instead of
`kernels push -p <dir>`, the adapter passes the **staging directory path** on
argv (small, credential-free) and the driver maps the file to the request in one
named function.

| metadata key | request field | note |
|---|---|---|
| `id` (`owner/slug`) | `slug` | **trap**: SDK `id` is an `int`; the string belongs on `slug` |
| `title` | `new_title` | |
| `code_file` | — | consumed as a path; its bytes become `text` |
| `language`, `kernel_type`, `is_private`, `enable_gpu`, `enable_internet` | same names | booleans set explicitly, never by default |

**Nothing is silently dropped.** The table is closed: a metadata key that is
neither mapped nor explicitly consumed is a **refusal naming the key**. This
closes the `machine_shape` defect class structurally — a key nothing transmits
now fails loudly instead of travelling to nobody.

### Decision 5: Automatic worker selection

`--worker` becomes optional. When absent, `packer.select()` walks
`adapter.workers()` in declared order (the accounts CLI's own stable order) and
takes the **first worker with `granted >= 1`**.

- **Healthy** = the metering read for that worker returned. Concretely: the
  authenticated `list` call succeeded.
- **Refused** = the driver exited with the distinct unauthorized code (401/403),
  which the adapter maps to a new seam exception `WorkerUnauthorized(AdapterError)`.
- **Unknown** = timeout, connection failure, 5xx. Skipped and *recorded*, never
  counted as healthy.
- `packer.plan()`'s blanket `except Exception` is narrowed so a `WorkerUnauthorized`
  propagates instead of silently degrading to the ledger count — otherwise a
  revoked account looks healthy.
- **No worker healthy** = terminal refusal listing each account and its observed
  reason, distinguishing "all revoked" from "service unreachable". Never an
  arbitrary pick, never a silent pass.
- **Explicit `--worker` naming a revoked account** = refusal naming the account
  and the remedy (re-materialize that account's credential through the accounts
  skill's own command), no fallback, no further quota spent. Selection skips;
  naming refuses — one coherent policy.

Rejected: least-loaded, which probes all five accounts on every submit for a
tie-break that still falls back to declared order. Explicit `--worker` keeps
today's non-enforcing behaviour (`granted` is recorded, not gated).

### Decision 6: Capacity metering without `list_active`

**Measured: rebuildable, so nothing refuses.** `list_kernels(group=PROFILE,
user=<worker>, sort_by=DATE_RUN)` returns `ApiKernelMetadata` items carrying
`ref`/`slug` but **no status**; `get_kernel_session_status(user_name, kernel_slug)`
returns `KernelWorkerStatus`. Active = count of `QUEUED`/`RUNNING`. Cost `1 + N`
requests, bounded to the first page sorted by most-recently-run — the only
kernels that can still be active. That bound is stated, not claimed away.
Fallback if the bound proves wrong: `plan()`'s existing ledger-derived count with
`in_flight_source="ledger"`, already the documented degraded mode.

### Decision 7: Retiring the environment claim

`## Environment`'s "This skill's own Python: none. Stdlib-only — no import of any
packaged client." is **retired outright**, not softened. Replacement states: the
skill's modules are stdlib-only; **one named driver script imports `kagglesdk`**;
the interpreter running the skill must be able to import it, and a failure to do
so refuses by name against `sys.executable`. A new
`test_the_retired_stdlib_only_claim_survives_nowhere` (the precedent's exact
idiom) scans SKILL.md, the adapter, the seam, `credentials.py` and the driver for
the retired sentences and requires zero occurrences.

### Decision 8: Pin and drift lock

`kagglesdk` ships **inside** the `kaggle` distribution (`kaggle-1.7.4.5.dist-info`)
— there is no separate distribution to pin. `requirements.txt` line 4 becomes
`kaggle==1.7.4.5`. Drift lock, two halves: the pin parsed from `requirements.txt`
must equal `importlib.metadata.version("kaggle")`; and the measured auth surface
(`_try_fill_auth` reads `KAGGLE_API_TOKEN`; `ApiSaveKernelRequest` carries the
exact field set mapped above) is asserted against the installed package. A
version bump that moves the auth surface fails loudly.

## Data Flow

    remote_cli submit [--worker?]
         │
         ├─ packer.select() ──→ adapter.workers() ──→ accounts_cli list --json
         │                 └──→ adapter.list_active(w) ─┐
         ↓                                              │
    adapter.submit(job)                                 │
         ├─ stage copy (metadata + run-config cell)     │
         ├─ _env_for(handle)  ── the ONE credential read│
         ↓                                              │
    subprocess.run([sys.executable, kaggle_driver.py, submit, --staging DIR],
                   env={PATH, KAGGLE_API_TOKEN})    ←── outer interception
         ↓
    driver: map metadata → ApiSaveKernelRequest → KernelsApiClient
         ↓
    requests.Session.send(prepared)              ←── inner interception
         ↓
    stdout: one JSON object   │  exit 0 ok · 3 unauthorized · other refusal

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/remote-execution/scripts/adapters/kaggle_driver.py` | Create | The one file importing `kagglesdk`; five ops, JSON stdout, typed exit codes |
| `.claude/skills/remote-execution/scripts/adapters/kaggle.py` | Modify | argv target becomes the driver; `_run` remedy sentence rewritten; JSON parsing replaces CLI-prose parsing; `kagglesdk` named nowhere |
| `.claude/skills/remote-execution/scripts/adapter.py` | Modify | Add `WorkerUnauthorized(AdapterError)` — backend-blind name |
| `.claude/skills/remote-execution/scripts/packer.py` | Modify | Add `select()`; narrow `plan()`'s swallow |
| `.claude/skills/remote-execution/scripts/remote_cli.py` | Modify | `--worker` optional; select when absent |
| `.claude/skills/remote-execution/SKILL.md` | Modify | Transport table rows, `## Environment`, selection policy |
| `tests/test_remote_execution.py` | Modify | Retarget the recorder; new interception + selection + drift classes |
| `requirements.txt` | Modify | `kaggle>=1.7` → `kaggle==1.7.4.5` (one line; the only file outside the skill) |

## Guarantee Verdicts

| id | Verdict under the chosen topology |
|---|---|
| `by-value` | **Preserved verbatim** — same `_env_for()` expression |
| `stripped` | **Preserved verbatim** |
| `single-reader` | **Preserved and strengthened** — AST lock unchanged, plus the driver names no credential at all |
| `fails-closed` | **Preserved verbatim** |
| `no-empty-bearer` | **Preserved verbatim** |
| `per-process` | **Preserved verbatim**, and now load-bearing: it is the reason for the topology |
| `really-concurrent` | **Preserved** — recorder moves from the fake `kaggle` binary to the fake driver |
| C2 (one file reads it, caller-checked) | **Preserved verbatim** — interposition still sees one caller |
| C3 (sentinel leaks nowhere) | **Preserved whole**, where in-process was a partial loss; child argv/stdout/stderr keep their subject. New obligation: the driver's error path never prints `os.environ` |
| C4 (no store literals / no `accounts_cli` import) | **Preserved**, scan list extended to the driver |
| C5 (`CredentialHandle` shape, one `.token_path`) | **Preserved verbatim** |
| C6 (one variable on one child env) | **Preserved in shape; exact set re-measured.** `{PATH, KAGGLE_API_TOKEN}` unless the selftest proves the import needs one more non-credential variable, in which case the row states the new exact set |
| E1 (`## Environment` stdlib-only) | **LOST.** Named as a loss, retired outright, locked to survive nowhere |

New rows the transport table gains: `reached` (every double asserts a non-zero
recorded-call count), `no-sdk-above-the-driver`, `wire-bearer` (the prepared
request carries `Authorization: Bearer <value>`). The accelerator doctrine gains
a wire observation of `enableGpu`/`enableInternet`. `LOCK_CLASSES` must name the
new lock class, or the doctrine test cannot see it.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | metadata→request mapping, unmapped-key refusal, status translation, `select()` ordering/skip/terminal | Direct calls; no process, no socket |
| Integration (outer) | credential value, allowlist env, concurrency overlap, bypass detection | Fake driver on an injected path recording argv + env; reached-count first |
| Integration (inner) | Bearer header, `enableGpu`/`enableInternet` on the wire | Recording `requests` transport on the driver's client; synthetic JSON response |
| Doctrine | table↔test binding, retired claims, pin drift, unique class names | Static AST/text scans |
| E2E | none | No live launch. A rehearsal may be planned; it is **not** scheduled |

Every new lock is proven reachable-red by inversion, restored by inverse patch
confirmed by sha256. Verification is by test count **rising** from 1084 by the
number added — never by a suite staying green.

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|---|---|---|---|
| Documentation-like paths (`requirements.txt`) | **Applicable** — one line edited | A declaration this skill reads as text and never executes; the pin is parsed, not run | Pin-drift test parses `requirements.txt` and compares to the installed version |
| Git repository selection | N/A — this change performs no VCS operation | — | — |
| Commit state | N/A — no index or worktree interaction | — | — |
| Push state | N/A — `kernels push` is not a git push; no ref resolution exists here | — | — |
| PR commands | N/A — no PR automation | — | — |

**Subprocess/argv addendum (the real boundary).** Every driver call stays
`shell=False`, list argv, explicit timeout, allowlist env. Safe behaviour: argv
carries only paths and a username; the credential crosses only via env. Failure
behaviour: non-zero exit or timeout is a `KaggleAdapterError`, exit 3 is
`WorkerUnauthorized`; neither fabricates a `Status`, `Submission` or `Fetched`.
RED tests: sentinel-absent-from-argv, exact-env-set, timeout refusal,
unauthorized mapping.

## Migration / Rollout

Additive driver plus an adapter revert restores today's (broken) CLI path exactly.
No artifact format, ledger schema or on-disk data changes. Slices, each
independently revertible: **1** driver + inner interception → **2** submit →
**3** poll/fetch → **4** selection + metering → **5** doctrine + pin.

## Open Questions

- [ ] Does the interpreter the skill runs under import `kagglesdk`? The installed
      distribution is under a **Python 3.9 user site**, while the skill requires
      3.10+. `driver selftest` must be the first thing run in apply; if it fails,
      the refusal text is the deliverable and the install is the user's.
- [ ] `fetch`: `download_kernel_output_zip` needs a `kernel_session_id` no measured
      response carries, so fetch goes file-by-file through
      `list_kernel_session_output`'s URLs plus the session `log`. Whether those
      URLs need the session's auth is the one thing only a rehearsal settles.
- [ ] Review budget: ~1100 authored lines against a cached `single-pr` strategy
      and an 800-line session budget. `sdd-tasks` must forecast and resolve.

*Size note: this artifact exceeds the 800-word design budget because the change
brief mandates eight decisions, thirteen guarantee verdicts and the matrix.*
