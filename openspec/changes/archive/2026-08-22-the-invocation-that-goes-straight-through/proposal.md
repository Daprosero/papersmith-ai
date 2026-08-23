# Proposal: the-invocation-that-goes-straight-through

Domain: `remote-execution` · Store: openspec · Subject: `.claude/skills/remote-execution/`

## Intent

The requirement, in the user's words: **sending the search is sending the search, and nothing else.** A user who invokes this skill to submit a job must not be handed a decision, a fork, a credential fix, or a maintenance task. If the skill hits one, that is a defect in the skill, not news for the user. **The acceptance test for this change is a behaviour, not a suite: the next invocation goes straight through.**

Today it cannot. The rehearsal dies locally, before a single byte reaches Kaggle:

```
OSError: Could not find kaggle.json
```

Six measured facts, in the order they bind:

| # | Fact | Evidence |
|---|---|---|
| 1 | Installed client is `kaggle 1.7.4.5`, and that is the latest on PyPI | `pip index versions kaggle` — **upgrading fixes nothing** |
| 2 | The CLI's `authenticate()` demands `username` + a classic key (or a `kaggle.json`) and does **Basic** auth, before any request is built | installed client source |
| 3 | The five stored accounts each hold a **37-char `KGAT_`-prefixed access token**, not a 32-hex classic key | `.claude/skills/kaggle-accounts/store/accounts.json` |
| 4 | Basic auth with a `KGAT_` token answers **401 for every account**, valid or not | measured live |
| 5 | A working Bearer path **does exist**: `_try_fill_auth()` reads `KAGGLE_API_TOKEN` and sets `BearerAuth(api_token)` **with priority over** the Basic fallback | `kagglesdk/kaggle_http_client.py:296-305` |
| 6 | The CLI structurally cannot reach it, per Kaggle's own developers | `kagglesdk/kaggle_http_client.py:14-17` — *"This was created from kaggle_api_client.py, prior to recent changes to auth handling. The new client requires KAGGLE_API_TOKEN, so it is not currently usable by the CLI."* |

So the adapter shells out to a binary that **cannot authenticate with the credentials this skill issues**, and `submit`, `poll`, `fetch` and `smoke` all end at that binary.

### The decision is already made; (a) is disqualified by the requirement itself

Two exits existed. **(a) change what is stored** — regenerate five classic `kaggle.json` credentials by hand and emit `KAGGLE_USERNAME`/`KAGGLE_KEY`. **(b) change how it authenticates** — drive `kagglesdk` with the Bearer token instead of shelling out to the `kaggle` CLI.

**(a) is disqualified not by effort but by the requirement.** It needs a human in Kaggle's UI regenerating five tokens by hand, and again at every rotation — it puts the user permanently in the loop, which is the exact thing this change exists to eliminate. **(b) uses the tokens already stored**, the same ones already observed authenticating with Bearer (HTTP 200 across all five accounts, read-only GET). Zero user action. **This change implements (b), and does not re-open it.**

## The hardest part: this change breaks the only offline proof mechanism we have

Today the adapter shells out to a `kaggle` binary, so **a fake `kaggle` on `PATH` intercepts the call** and records exactly what crossed: argv, and which environment variables were passed. That is how the skill proves offline that `KAGGLE_API_TOKEN` crosses **by value**, that only `PATH` and that variable cross at all, and that two concurrent submissions carry two uncrossed credentials.

**If the adapter stops shelling out, a fake binary on `PATH` intercepts nothing** — and the proof mechanism silently stops proving anything while every test stays green. That is precisely the defect class this repository has spent many sessions eliminating, so the proposal treats the interception point as a first-class deliverable, not a test-fixture detail.

### A decisive measurement that constrains the topology

`KaggleHttpClient.__init__(env, verbose, renew_iap_token, username, password)` has **no token parameter** (`kagglesdk/kaggle_http_client.py:96-110`), and `_try_fill_auth()` reads `os.getenv('KAGGLE_API_TOKEN')` (`:300`). **The only public route to Bearer auth in the installed SDK is a process-global environment variable.** In-process, two concurrent workers would have to race that global, or the adapter would have to set two private attributes (`_signed_in`, `_session.auth`) on a class whose own authors say its auth handling is mid-migration. **The process boundary is therefore functional, not vestigial.**

### The three candidate interception points, weighed

| | Candidate | What it can prove | What it costs / cannot prove |
|---|---|---|---|
| **A** | A controlled HTTP endpoint | The exact prepared request through the real `requests` stack: method, path, `Authorization` header, body — the only point that can prove `enable_gpu`/`enable_internet` actually reach the wire | **Correction to the framing, measured:** `kaggle_env.get_env()` selects among a **closed enum of five hard-coded hosts**, and `KaggleEnv.LOCAL` is `http://localhost` **with no port**; `get_endpoint` is a dict lookup (`kagglesdk/kaggle_env.py:14-40`). There is no env var carrying an arbitrary base URL, so this is *not* reachable by configuration — it needs binding privileged port 80, or rewriting `_env_to_endpoint`. The fake must also return responses the SDK can deserialize |
| **B** | A recorded transport on the client session | The same prepared bytes including the `Authorization` header, with no socket and no host rewrite; `requests` is a far more stable surface than kagglesdk internals | Requires reaching `client._session`, which exists only after `_init_session()`; proves what our code *prepared*, not what a socket would carry |
| **C** | Keep the child-process boundary, make the child a small SDK driver | **Every existing guarantee survives verbatim**, including the three the public SDK surface cannot otherwise support (`per-process`, `really-concurrent`, `single-sink`); the existing fake-binary harness keeps intercepting argv and env | **C alone re-creates the blind spot one layer down.** A fake driver intercepts *before* the SDK is reached, so nothing observes that the driver builds `ApiSaveKernelRequest` with `enable_gpu`/`enable_internet` actually set — which is exactly how `machine_shape` was transmitted to nobody for the life of this skill |

**Recommended shape, for design to confirm: C at the adapter boundary, plus A or B inside the driver's own tests.** This is not a compromise between two options; they answer two different questions. The adapter boundary answers *which credential crossed, to which process, uncrossed, under concurrency*. The request boundary answers *what the request actually contained*. Neither answers the other's question, and this repository has already paid once for having only one of them.

### The rule that makes this safe, and it must be a lock rather than a paragraph

**Every interception point must assert it was reached.** A double that records nothing and a double that was bypassed are indistinguishable from a green suite. So each observing double carries a positive "I was reached" assertion — a non-zero recorded-call count, checked by the test — and each new lock is proven reachable-red by inversion. **A test that passes because its interception point disappeared is worse than no test**, and the only way to detect that is to make the absence of observation itself a failure.

## Guarantees that must survive the rewrite — enumerated from the adapter and its tests

Read off `SKILL.md`'s credential-transport table (7 rows), `CredentialSecurityTests` (C2-C6), and the `## Environment` doctrine. Verdicts:

| id | Guarantee | In-process SDK | Child SDK driver |
|---|---|---|---|
| `by-value` | The credential's stripped **content** crosses, never its path | Holds; sink is renamed from an env var to an auth object | **Verbatim** |
| `stripped` | The newline `materialize` writes never reaches the header | Holds | **Verbatim** |
| `single-reader` | No module above the adapter touches `token_path`; exactly one `.token_path` access in `adapters/kaggle.py`, AST-locked | Holds | **Verbatim** |
| `fails-closed` | An unreadable credential file is a refusal naming the path | Holds | **Verbatim** |
| `no-empty-bearer` | A file empty once stripped is a refusal naming the worker | Holds | **Verbatim** |
| `per-process` | Two concurrent workers carry two distinct, uncrossed credentials | **CANNOT HOLD** via the public surface — the only Bearer route is a process-global env var | **Verbatim** |
| `really-concurrent` | The isolation above is proven under genuine time overlap | **CANNOT HOLD** — same cause | **Verbatim** |
| C2 | Exactly one **file** reads the credential, caller-checked by interposition | Holds | **Verbatim** |
| C3 | A planted sentinel leaks into no argv, child stdout/stderr, ledger, or quarantine artifact | **PARTIAL LOSS** — the argv/stdout/stderr half loses its subject on the submit path; ledger + quarantine survive | **Verbatim** |
| C4 | No forge component holds credential-store literals or imports `accounts_cli` | Holds | **Verbatim** |
| C5 | `CredentialHandle` carries exactly `(worker_id, token_path)` | Holds | **Verbatim** |
| C6 | The only sink is one variable on one child environment; env is exactly `{PATH, KAGGLE_API_TOKEN}`, or `{PATH}` with no handle | **CANNOT HOLD as written** — there is no child environment | **Verbatim** |
| E1 | `## Environment`: *"This skill's own Python: none. Stdlib-only — no import of any packaged client."* | **LOST** | **LOST** |

**E1 is a genuine loss under either route and is named, not quietly dropped.** With the driver the import lives in one skill-shipped script rather than in the seam, but the skill still requires the package; the honest restatement is "stdlib-only except one named driver script", and the retired sentence must survive nowhere — the precedent is `test_the_retracted_by_path_claim_survives_nowhere`.

## Scope

### In scope

| Item | Files |
|---|---|
| Bearer-authenticating `submit`/`poll`/`fetch` via `kagglesdk` | `.claude/skills/remote-execution/scripts/adapters/kaggle.py`, one new driver script in that skill |
| The request-observing interception point and its "I was reached" lock | `tests/test_remote_execution.py` |
| Re-deriving the credential-transport table from what the new path actually does | `SKILL.md` table + `CredentialTransportDoctrineTests` |
| Restating `## Environment`; retiring the stdlib-only claim outright | `SKILL.md` |
| `_run`'s remedy sentence (`pip install kaggle` → what the SDK path needs) | `adapters/kaggle.py` |

SDK surface, measured by importing it rather than by reading docs — sufficient for three of the four operations:

| Adapter command | SDK method | line in `kagglesdk/kernels/services/kernels_api_service.py` |
|---|---|---|
| `submit` | `save_kernel(ApiSaveKernelRequest)` | 47 |
| `poll` | `get_kernel_session_status(...)` | 71 |
| `fetch` | `list_kernel_session_output(...)`, `download_kernel_output_zip(...)` | 59, 97 |

`ApiSaveKernelRequest` has 19 fields, confirmed by instantiating it; the load-bearing ones are `enable_gpu`, `enable_internet`, `text`, `slug`, `new_title`, `kernel_type`, `language`, `session_timeout_seconds`, `is_private`. **`enable_gpu` is a boolean and there is no `machine_shape`** — the same ceiling the CLI path already had, so `REQUEST_GPU = True` stays a request and never a receipt.

**`list_active` has no measured SDK equivalent**, and that gap is named rather than assumed away. It is an open item for design; if no method exists, capacity metering must refuse rather than guess.

### Out of scope, with reasons

- **`implementations/Domain_Adaptation`** — a separate git repository (`Daprosero/Domain_Adaptation`, HEAD `72f8a17`), read-only from the forge, carrying one uncommitted line the user owns. Never touched and never proposed.
- **`openspec/config.yaml`** — it pins the test command to `test_extract_pdf.py` and never runs the skill suites. A real defect, recorded here, deliberately left for a real audit to find.
- **`.claude/skills/kaggle-accounts/`** — no change proposed. The store already holds the right credential shape; this change consumes it differently. Editing it would be justified only if the driver needs a `materialize` field the CLI does not emit today, and nothing measured says it does.
- **Exit (a)**, regenerating classic credentials — disqualified above by the requirement itself.
- **Any live launch.** A rehearsal may be planned; it is not scheduled and runs only on the user's explicit permission. The read-only GET per account is already proven and is not repeated.
- `proposal-implementation` or any other skill.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `remote-execution`: how a Kaggle submission authenticates and how the credential's transport is proven offline — the credential-transport guarantees, the interception-point requirement, and the environment doctrine.

## Approach

1. **Confirm the topology by measurement, not by preference.** The public SDK surface offers only a process-global Bearer route (measured above); design confirms the driver route by building one submission against a controlled endpoint before any production line changes.
2. **Arm the request-observing interception first**, with its "I was reached" lock, so the new point exists and is red against today's code.
3. **Move one operation at a time** — `submit`, then `poll`, then `fetch` — each with its own reachable red, each independently revertible.
4. **Re-derive the doctrine table from behaviour.** Any row the new path cannot hold is deleted with its reason recorded, never softened into a weaker sentence.
5. **Restate `## Environment`** and assert the retired claim survives nowhere.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `.claude/skills/remote-execution/scripts/adapters/kaggle.py` | Modified | Stops driving the `kaggle` CLI; drives the SDK driver instead |
| `.claude/skills/remote-execution/scripts/` (new driver) | New | The one file permitted to import `kagglesdk` |
| `.claude/skills/remote-execution/SKILL.md` | Modified | Credential-transport table, `## Environment`, the retracted stdlib-only claim |
| `tests/test_remote_execution.py` | Modified | New request-observing interception; existing fake-binary harness retargeted at the driver |
| `requirements.txt` | Possibly modified | See question Q4 |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| An interception point silently stops intercepting and the suite stays green | **High**, and it is the central risk | Every double asserts it was reached; every lock proven reachable-red by inversion; verify by test counts **rising**, never by a suite staying green |
| Kaggle's own comment says the auth surface is mid-migration; a future version moves it again | Med | Pin the dependency at a measured version and quote that comment as the reason (Q4) |
| The fake endpoint cannot return responses the SDK deserializes, and route A stalls | Med | Route B (recorded transport) is the fallback and answers the same question one layer in |
| `list_active` has no SDK equivalent, so capacity metering loses its input | Med | Refuse rather than guess; named as an open design item, not assumed |
| The change exceeds one reviewable PR | **High** | Chained PRs, one per operation, ordered driver → submit → poll/fetch → doctrine |
| A revoked token still surfaces to the user as a maintenance task | Med | Q2 decides the policy; either way the refusal names the account and spends no quota |

**Review budget forecast:** roughly 900 authored lines (additions + deletions) — adapter ~250, driver ~200, tests ~400, doctrine ~80. Over the 800-line session budget and well over the 400-line per-PR guard, so **chained PRs are recommended**, in the order above.

## Rollback Plan

Each operation lands as one commit against `main` and reverts independently, in reverse order. The driver script is purely additive, so removing it plus reverting the adapter restores today's CLI path exactly — a broken path, but the current state, with no data to migrate: no on-disk artifact format changes and no ledger schema change. The doctrine commit reverts on its own without touching code.

## Dependencies

- `kagglesdk`, already installed alongside `kaggle 1.7.4.5`. Version pinning is Q4.
- Nothing else. No live Kaggle access is required to land this change.

## Success Criteria

- [ ] An offline test observes a submission's outbound request carrying `Authorization: Bearer <the token's value>` — the value, never the path.
- [ ] The same observation shows `enable_gpu` and `enable_internet` present and true — the `machine_shape` defect class closed **by observing the request**, not by reading the client's source.
- [ ] Two concurrent submissions for two workers are observed carrying two distinct, uncrossed credentials, with genuine overlap in time.
- [ ] Every interception point asserts it was reached, and every new lock is proven reachable-red by inversion.
- [ ] `SKILL.md`'s credential-transport table names only guarantees the new path holds; every lock has a row, every row names a real test, and each guarantee this change cannot keep is recorded as a loss.
- [ ] `## Environment` states what the skill now needs, and the retired stdlib-only claim survives nowhere.
- [ ] `python3 -m unittest discover -s tests` is green at **1084 + the number of tests added**, counted as a rise.
- [ ] No forge file names `implementations/Domain_Adaptation` vocabulary; the generality guard stays green.
- [ ] **Nothing was launched to Kaggle.**

## Proposal question round

This phase could not ask interactively. Four questions that would sharpen the proposal; the assumption each currently rests on is stated so it can be corrected now rather than discovered later. Answering, skipping, correcting the framing, or asking for a second round are all fine.

1. **How far does "goes straight through" reach?** Submitting names a worker today. If the user must decide nothing, should worker selection become fully automatic (least-loaded of the five), or is naming an account a legitimate part of "send the search"?
   *Assumed: selection is unchanged and out of scope; only authentication is repaired.*
2. **What should happen when one account's token is genuinely revoked?** A revoked credential really does need a human eventually. Should the skill refuse naming that account, or transparently move to the next healthy account and report afterwards?
   *Assumed: refuse naming the account — silently switching accounts changes whose quota was spent, which is a decision, not a repair.*
3. **If `list_active` has no SDK equivalent**, capacity metering loses its input. Refuse to submit (safe, but blocks the user — the thing this change exists to prevent), or submit without the check (fast, but can exceed the documented 2-concurrent allowance)?
   *Assumed: refuse, because exceeding the allowance surfaces to the user later and worse.*
4. **Should `kagglesdk` be pinned in `requirements.txt`**, given its own authors describe the auth surface as mid-migration?
   *Assumed: yes, pinned at the measured version, with that comment quoted as the reason.*
