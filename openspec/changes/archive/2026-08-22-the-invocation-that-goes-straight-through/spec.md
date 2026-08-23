
# Spec Delta: the-invocation-that-goes-straight-through

Change: `the-invocation-that-goes-straight-through` · Modifies capability: `remote-execution`
(`.claude/skills/remote-execution/`, `tests/test_remote_execution.py`) · Store: openspec.

Baseline: `.claude/skills/remote-execution/SKILL.md`'s credential-transport table (7 rows),
`CredentialSecurityTests` (C2–C6), and the `## Environment` doctrine. This delta MODIFIES the
authentication mechanism (child-process CLI shellout → child-process `kagglesdk` driver, Bearer
instead of Basic), MODIFIES the credential-transport table and `## Environment`, and ADDS worker
auto-selection, capacity-metering fallback, dependency pinning, and the request-observing
interception point. Untouched: `.claude/skills/kaggle-accounts/`, `openspec/config.yaml`,
`implementations/Domain_Adaptation`, and any live Kaggle launch.

---

## Group 1 — The next invocation goes straight through

### ADDED Requirement: Submitting a search MUST require no decision, fork, credential fix, or maintenance task from the invoking user

A user invoking this skill's `submit` MUST be able to send a search with no argument beyond
naming what to run. Any behavior that stops on the way to Kaggle for a reason internal to the
skill (which credential, which account, which auth scheme) is a defect in the skill, never a
prompt surfaced to the user. The acceptance criterion is behavioral: once the defect this change
repairs is fixed, the next invocation MUST go straight through.

#### Scenario: A submission with no `--worker` and no prior maintenance succeeds end to end
- GIVEN five stored accounts, all holding valid tokens, and no `--worker` supplied
- WHEN `submit` runs
- THEN it SHALL complete without asking the caller to choose an account, regenerate a credential, or run any other command first

#### Scenario: The invocation that previously died locally now reaches the observed request
- GIVEN the same command line that today raises `OSError: Could not find kaggle.json`
- WHEN `submit` runs after this change
- THEN it SHALL NOT raise that error, and the request-observing interception point (Group 5) SHALL record one outbound request

### ADDED Requirement: `--worker` MUST become optional, with automatic selection among healthy accounts, and explicit naming MUST remain a legitimate override

Today `--worker` is required on `submit`, `reconcile`, `smoke record`, and `readiness` — naming
an account is already a fork reaching the user. Automatic selection MUST choose among accounts
whose health can be established (Group 3), skipping any account known to be unhealthy. An
explicit `--worker` MUST continue to mean exactly the account named.

#### Scenario: Automatic selection picks a healthy account
- GIVEN no `--worker` supplied and at least one of the five accounts is healthy
- WHEN `submit` runs
- THEN it SHALL select a healthy account and complete without prompting

#### Scenario: An explicit worker still overrides selection
- GIVEN `--worker w3` supplied and `w3` is healthy
- WHEN `submit` runs
- THEN it SHALL submit under `w3` exactly as before this change

---

## Group 2 — A revoked token is a refusal, never a silent switch, and never a silent block

### ADDED Requirement: Automatic selection MUST skip an account with a revoked token; explicitly naming a revoked account MUST be refused, naming the exact remedy

Silently switching an explicitly-named account changes whose quota is spent — that is a
decision, not a repair, and MUST NOT happen. Automatic selection, by contrast, has made no such
promise to any one account and MUST skip an unhealthy one in favor of another.

#### Scenario: Automatic selection skips a revoked account among five
- GIVEN one of five accounts holds a revoked token and the other four are healthy
- WHEN `submit` runs with no `--worker`
- THEN it SHALL select one of the four healthy accounts and SHALL NOT surface the revoked account to the caller

#### Scenario: Naming a revoked account explicitly is refused, not silently rerouted
- GIVEN `--worker w2` supplied and `w2`'s token is revoked
- WHEN `submit` runs
- THEN it SHALL refuse, SHALL name `w2` and the exact remedy (re-issuing that account's token), and SHALL NOT submit under any other account
- AND no quota SHALL be spent on any account

#### Scenario: All five accounts are unhealthy
- GIVEN every stored account's token is revoked or otherwise unhealthy
- WHEN `submit` runs with no `--worker`
- THEN it SHALL refuse, naming that no healthy account exists and the remedy (restoring at least one account's credential)

---

## Group 3 — Capacity metering survives the lost `list_active` input

### ADDED Requirement: Capacity metering MUST be rebuilt from `list_kernels` plus `get_kernel_session_status` before any refusal is considered

`list_active` has no measured `kagglesdk` equivalent. Losing that one input is not the same as
being unable to obtain in-flight-count evidence at all: `list_kernels` (enumeration) combined
with `get_kernel_session_status` (per-kernel state) MUST be attempted first to reconstruct the
same fact `list_active` supplied. Capacity metering (and, transitively, worker-health used by
Group 2/1) MUST refuse to submit only when this reconstruction is genuinely impossible, and the
refusal MUST name the exact remedy — never a bare block.

#### Scenario: Metering succeeds via the rebuilt path
- GIVEN `list_kernels` and `get_kernel_session_status` both answer for an account
- WHEN `packer.plan()` needs that account's in-flight count
- THEN it SHALL derive `inFlight` from that rebuilt path and SHALL NOT report it as unavailable

#### Scenario: Reconstruction is genuinely impossible
- GIVEN `list_kernels` fails structurally (not merely empty) for every candidate account
- WHEN a submission is attempted
- THEN it SHALL refuse, naming that live capacity evidence could not be obtained and the remedy (retry, or fall back to the ledger's own fold as `inFlightSource`)
- AND it SHALL NOT guess a count and SHALL NOT silently exceed the documented per-worker allowance

---

## Group 4 — Authentication moves to Bearer, driven by `kagglesdk`

### MODIFIED Requirement: `submit`/`poll`/`fetch` MUST authenticate with the stored Bearer token via a `kagglesdk` driver process, never via the `kaggle` CLI's Basic path

The installed `kaggle` CLI's `authenticate()` demands a classic key or `kaggle.json` and performs
Basic auth before any request is built; the five stored accounts hold 37-char `KGAT_` access
tokens, and Basic with a `KGAT_` token is refused by the service for every account. The adapter
MUST instead drive one child-process script — the only file in this skill permitted to import
`kagglesdk` — that sets the process-global `KAGGLE_API_TOKEN` for that child alone and calls
`save_kernel`/`get_kernel_session_status`/`list_kernel_session_output`/
`download_kernel_output_zip`. The child-process boundary MUST be preserved: it is what keeps two
concurrent workers' credentials from racing one process-global environment variable.
(Previously: shelled out to the `kaggle` CLI, which cannot authenticate with the stored token
shape at all.)

#### Scenario: A submission authenticates with Bearer, not Basic
- GIVEN a stored account's `KGAT_`-prefixed token
- WHEN `submit` runs
- THEN the outbound request SHALL carry `Authorization: Bearer <the token's stripped value>`
- AND no Basic-auth header SHALL be constructed anywhere on the path

#### Scenario: `enable_gpu` and `enable_internet` reach the request
- GIVEN a job requesting GPU and requiring the runner to clone over git
- WHEN `submit` builds its `ApiSaveKernelRequest`
- THEN the observed outbound request SHALL show `enable_gpu: true` and `enable_internet: true`
- AND no `machine_shape` field SHALL be relied upon, since none exists on this request shape

#### Scenario: Two concurrent submissions carry two distinct, uncrossed credentials
- GIVEN two workers submitting genuinely overlapping in time
- WHEN both driver child processes run
- THEN each SHALL carry only its own worker's token on its own environment
- AND neither SHALL observe or be able to observe the other's `KAGGLE_API_TOKEN` value

### ADDED Requirement: `kagglesdk` MUST be pinned at the measured version, and a lock MUST fail when the installed version drifts from the pin

Kaggle's own developers document the auth surface as mid-migration
(`kagglesdk/kaggle_http_client.py:14-17`). `requirements.txt` MUST pin `kagglesdk` at the version
measured working with this change, quoting that comment as the reason. A prose pin with no
enforcement is not a guarantee; a test MUST fail when the installed `kagglesdk` version differs
from the pinned one.

#### Scenario: The pin is documented with its reason
- GIVEN `requirements.txt`
- WHEN it is read
- THEN it SHALL pin `kagglesdk` at the measured version and SHALL quote Kaggle's own migration comment as the reason

#### Scenario: A drifted installation fails the lock
- GIVEN an installed `kagglesdk` version different from the pinned one
- WHEN the version-lock test runs
- THEN it SHALL fail, naming both the pinned and the installed version

---

## Group 5 — The interception point MUST prove it was reached (the hardest requirement)

### ADDED Requirement: Every interception point observing a credential or a request MUST positively assert it was reached, and a bypassed double MUST fail rather than pass silently

Today a fake `kaggle` binary on `PATH` intercepts the adapter's shellout and records argv and
environment — the offline proof that `KAGGLE_API_TOKEN` crosses by value, that only `PATH` and
that variable cross, and that two concurrent submissions carry two uncrossed credentials. Once
the adapter drives `kagglesdk` directly instead of shelling out, a fake binary on `PATH`
intercepts nothing. A test suite that stays green while its interception point silently stops
observing is indistinguishable, from the outside, from one that is genuinely passing. Every
double introduced or retargeted by this change (the driver-process double, the
request-observing double) MUST carry a non-zero recorded-call assertion checked by the test
itself, and that assertion MUST be proven reachable-red by inversion: bypass the interception
point on purpose and watch the assertion fail.

#### Scenario: The double is reached
- GIVEN the driver process double in place on `PATH` (or the request-observing double wired into the client session)
- WHEN a submission runs through the normal path
- THEN the double's recorded-call count SHALL be greater than zero
- AND the test SHALL assert that count explicitly, not merely assert on its content

#### Scenario: The double is bypassed and the suite fails, not passes
- GIVEN the production code is modified to skip the driver process (or the client session) entirely, calling the real dependency some other way
- WHEN the test suite runs
- THEN the reached-assertion SHALL fail
- AND no other passing assertion in that test SHALL mask the failure

#### Scenario: A new lock is proven reachable-red before it is trusted
- GIVEN any new lock added by this change that passes on its first run
- WHEN the guarded production behavior is inverted on purpose
- THEN the lock SHALL fail
- AND restoring the inverse patch SHALL return it to green

---

## Group 6 — The credential-transport table is re-derived from what the new path does

### MODIFIED Requirement: `SKILL.md`'s credential-transport table MUST name only guarantees the child `kagglesdk` driver topology actually holds, and any guarantee it cannot keep MUST be recorded as a loss, never softened

The prior table's seven rows (`by-value`, `stripped`, `single-reader`, `fails-closed`,
`no-empty-bearer`, `per-process`, `really-concurrent`) plus `CredentialSecurityTests`' C2–C6 MUST
each be re-evaluated against the child-driver topology this change lands. Because the
child-process boundary is preserved (Group 4), every row MUST continue to hold verbatim under
this topology, sink renamed from an environment variable read by a CLI to an environment variable
read by the driver's own `_try_fill_auth()`-equivalent call. Each row MUST map to a real,
currently-passing test; a row with no matching test MUST be deleted, not left as prose.
(Previously: table described a CLI-shellout sink; `single-reader`, `fails-closed`, and
`no-empty-bearer` described `_env_for()` feeding the `kaggle` CLI's environment.)

#### Scenario: Every row maps to a real test
- GIVEN the re-derived table
- WHEN each row is checked against the test suite
- THEN every row SHALL name a test that exists and passes
- AND no row SHALL describe a guarantee no test currently proves

#### Scenario: `per-process` and `really-concurrent` hold under the child driver
- GIVEN two concurrent submissions for two different workers
- WHEN both run through their own driver child processes
- THEN each SHALL carry only its own credential
- AND the table's `per-process`/`really-concurrent` rows SHALL remain, not be marked lost

### REMOVED Requirement: `## Environment`'s claim that this skill's own Python is stdlib-only with no import of any packaged client

(Reason: the driver script this change adds is a file inside this skill that imports `kagglesdk`
directly, so "no import of any packaged client" is no longer true of the skill as a whole. The
prior claim about the `kaggle` CLI arriving via `requirements.txt` for a shelled-out binary is a
different claim and does not save this one.)
(Migration: `## Environment` MUST be restated as "stdlib-only except one named driver script,"
naming that script and `kagglesdk` explicitly. The retired sentence MUST survive nowhere in
`SKILL.md`, per the precedent of `test_the_retracted_by_path_claim_survives_nowhere`.)

#### Scenario: The retired claim survives nowhere
- GIVEN `SKILL.md` after this change
- WHEN it is scanned for the retired sentence (or any paraphrase asserting no packaged-client import)
- THEN no match SHALL be found

#### Scenario: The restated doctrine names what the skill now needs
- GIVEN `## Environment` after this change
- WHEN it is read
- THEN it SHALL name the driver script and `kagglesdk` as the one exception to stdlib-only

---

## Cross-cutting requirements

### ADDED Requirement: No spec, scenario, example, fixture, or test name introduced by this change MAY name `implementations/Domain_Adaptation` vocabulary

The forge stays general. No requirement, scenario, or fixture in this delta or the tests it
drives MAY reference `MIL_CREDA`, `CREDA`, `harness.py`, or that target's layout. The existing
generality guard MUST stay green against every file this change touches.

#### Scenario: The generality guard scans this change's own files
- GIVEN the files this change adds or edits under `.claude/skills/remote-execution/` and `tests/test_remote_execution.py`
- WHEN the no-service / no-target-vocabulary guard runs
- THEN it SHALL find no `Domain_Adaptation`-specific vocabulary in any of them

### ADDED Requirement: Full test discovery MUST report a rising count, never a merely-green one

`python3 -m unittest discover -s tests` MUST report **1084 plus the number of tests this change
adds**, and that rise, not a bare "OK", is what verification checks.

#### Scenario: The count rises
- GIVEN the baseline of 1084 tests
- WHEN this change's tests are added and the suite runs
- THEN the reported total SHALL exceed 1084 by exactly the number of tests this change added

---

## Explicit non-goals

| Non-goal | Reason |
|---|---|
| Regenerating classic `kaggle.json` credentials by hand (exit (a)) | Disqualified by the requirement itself: it puts the user permanently in the loop, the opposite of "goes straight through". |
| Any change to `.claude/skills/kaggle-accounts/` | The store already holds the right credential shape; this change only consumes it differently. |
| Any change to `openspec/config.yaml` | Recorded as a known defect (pins the test command to `test_extract_pdf.py`), deliberately left for a real audit. |
| Any live Kaggle launch | A rehearsal MAY be planned by design/tasks; it MUST NOT be scheduled by this spec, and nothing is launched without the user's explicit permission. |
| A named-accelerator request (`machine_shape`) | `enable_gpu` is boolean; no field exists to request a specific GPU. Unchanged ceiling, not this change's defect to close. |

## Acceptance

Full discovery green at 1084 plus the number of tests this change adds, counted as a rise, not a
bare pass. Every interception point (driver-process double, request-observing double) asserts a
non-zero recorded-call count and is proven reachable-red by inversion. `SKILL.md`'s
credential-transport table names only guarantees the child-driver topology holds, with every row
mapped to a passing test and E1 restated rather than silently dropped. Nothing is launched to
Kaggle.
