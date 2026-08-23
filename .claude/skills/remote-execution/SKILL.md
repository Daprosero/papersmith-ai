---
name: remote-execution
description: "Trigger: durable record of what a repository has submitted to a remote worker, what came back, and how much to submit at once. This skill ships the append-only ledger (write path and the fold that derives per-entrypoint state), the backend-agnostic adapter seam (ABC + frozen shapes + registry), the packer's capacity clamp and worker auto-selection, the full `remote_cli` front door (`submit` with its path guard, optional `--worker` and `--smoke`, `status`, `poll`, `fetch` with quarantine, `reconcile`, `generate-job`, `smoke record`, `readiness`), and one concrete backend: `adapters/kaggle.py` — the ONLY file in this entire skill allowed to name a service. It shells out to `adapters/kaggle_driver.py`, the ONLY file in this skill permitted to import the packaged `kagglesdk` client (pinned `kaggle==1.7.4.5`, since `kagglesdk` ships inside that distribution) rather than the `kaggle` CLI's own Basic-auth path, which the stored token shape cannot authenticate against at all; derives worker identity solely from kaggle-accounts' own sanctioned `list --json` command, and accepts credentials only as a `CredentialHandle(worker_id, token_path)` — read at exactly one expression, in that one file, and put on `KAGGLE_API_TOKEN` for one child process, because `kagglesdk`'s own `_try_fill_auth()` reads that variable by value with no path check at all — the CLI itself authenticates neither a path nor that variable. A rehearsal run (`smoke.jsonl`, a distinct file from the main ledger) proves readiness from evidence-completeness, never a human assertion, and never a clock. Stdlib-only except that one named driver script."
---

# Remote Execution

A submission to a remote worker is a fact once it happens, and this skill's
job is to make sure that fact survives being written, to derive current
state from the record rather than store it separately, and to decide how
much work a worker is asked to take on at once without either side of that
decision asserting the other's fact. Nothing here yet talks to a real
service — that is a concrete adapter, still to come — but the CLI a user
would invoke directly (`submit`, `status`, `poll`, `fetch`, `reconcile`) is
in place today, exercised against a `FakeAdapter` only.

## Current Scope

Three modules exist so far, each service-blind and stdlib-only:

- `scripts/ledger.py` — `append(path, event)` appends one JSON-encoded event
  as a single line to `<target>/<Name>/.remote-execution/ledger.jsonl`. The
  file is opened `O_APPEND`; a line, once written, is never rewritten or
  deleted (see below for why an append can be trusted at all).
  `fold(lines, live_digest)` derives current per-entrypoint state from that
  log — `pending | returned | errored`, whether a pending submission is
  `staleInFlight`, and which `returned` results are `fromStaleSubmission` —
  the currency rule that tells a fresh result from a stale one.
  `submitted_event(...)`, `returned_event(...)`, `errored_event(...)` build
  the three event kinds this ledger records, with the field names and
  truncation rules this schema fixes (see below).
- `scripts/adapter.py` — the `Adapter` ABC every backend-specific module
  must satisfy in full (exactly six operations), the frozen data shapes
  that cross the seam (`Worker`, `Job`, `Submission`, `Status`, `Fetched`),
  and a name-to-class registry a caller can select a backend by without
  importing it directly. `Job.run_config` is an opaque
  `Mapping[str, object]` — normalized in `__post_init__` to a
  `MappingProxyType` over a private copy, so mutating it (or mutating the
  caller's own original dict afterward) is structurally refused. The
  packer and the ledger never read or branch on a key inside it; an empty
  `run_config` is the legacy shape every existing caller uses, a non-empty
  one is what a generated job carries. A second, separate registry,
  `register_metadata`/`resolve_metadata`, maps a name to a
  `fn(run_config) -> (filename, text)` callable — kept off the ABC
  entirely so a backend needing a service-specific metadata file (an
  accelerator request, say) never forces every other backend to grow a
  method it does not need. `adapters/kaggle.py` is the one concrete
  backend this skill ships; its own test suite also stands a `FakeAdapter`
  in for a second one, to prove the seam generalizes.
- `scripts/packer.py` — `plan(...)` clamps a repository's declared
  per-worker request to the cap the adapter states through `workers()`,
  deducting what is already committed (from the ledger's fold, refined by
  `list_active()` when the adapter answers). The clamp is never a silent
  minimum: `plan()` returns `requested`, `cap`, `inFlight` and `granted` as
  four separate numbers, plus `inFlightSource` recording whether `inFlight`
  came from the live service or fell back to the ledger. `plan()` never
  swallows `ADAPTER.WorkerUnauthorized` — every OTHER `list_active()`
  failure still degrades to the ledger count, but a refused credential is
  a decision-bearing fact, not a mere unreachable one, and propagates.
  `select(...)` picks a worker for a caller who names none: it walks
  `adapter.workers()` in declared order and returns the first one whose
  `plan()` both answered from the live service (`inFlightSource ==
  "list_active"`, never a ledger fallback — a worker this call could not
  actually confirm is never counted healthy) and still has capacity
  granted; naming no healthy worker at all is a refusal listing every
  account tried and the remedy, never a silent pass or an arbitrary pick.
- `scripts/remote_cli.py` — the CLI front door, five submission/status
  commands (`submit`, `status`, `poll`, `fetch`, `reconcile`) plus
  `generate-job`, `smoke record` and `readiness` (see "Smoke" below).
  - `submit`'s `--worker` is OPTIONAL: naming one keeps today's behavior
    exactly (an unhealthy named account refuses, never silently reroutes
    — switching accounts on a caller's behalf would spend a different
    account's quota than the one asked for); omitting it hands the choice
    to `packer.select()` above. `reconcile`, `smoke record` and
    `readiness` keep `--worker` REQUIRED — each already names one
    account's own local state (its ledger, its evidence, its capacity),
    never a fresh submission decision, so there is no fork for automatic
    selection to remove there.
  - `submit` guards the entrypoint, resolves the product via
    `product_for()` (the SAME function `status`, `fetch` and `reconcile`
    call — never an inline `parts[0]` derivation of its own), computes a
    fresh `source_digest()`, calls `packer.plan()` (a named worker) or
    `packer.select()` (none named), hands the job to a registered
    adapter's `submit()`, and appends the resulting `submitted`
    event to the ledger — in that order. A job-folder submission whose
    product cannot be resolved (no `--product`, no `product` declared in
    its own `run-config.json`) is refused right there, before the digest,
    the plan or the adapter ever run — never silently recorded under
    `tools`. `--product` is `submit`'s own CLI flag reaching `product_for`'s
    `explicit` argument, its highest-priority resolution step; `status`,
    `fetch` and `reconcile` do not yet expose an equivalent flag, since each
    reads an already-generated job folder whose own `run-config.json`
    already declares its product. The `entrypoint` field a `submitted`
    event records is the resolved entrypoint's path relative to the
    resolved product directory for the legacy shape (`Notebooks/a.ipynb`);
    for the job-folder shape, whose product directory is never an ancestor
    of the entrypoint at all, it falls back to the path relative to
    `target` instead (`tools/<service>/<job-name>/runner.ipynb`) — both
    stay unique per submission, and neither pretends a containment
    relationship the job-folder shape does not have. `guard_entrypoint()` is
    the ONLY place in this whole
    skill that holds an opinion about what KIND of file may run remotely:
    `Path.resolve()` first, then refuse anything whose resolved path does
    not match one of exactly two admitted shapes and end `.ipynb`:
    `<target>/<Name>/Notebooks/**.ipynb` (the legacy shape) or
    `<target>/tools/<service>/<job-name>/*.ipynb` (the job-folder shape,
    exactly four path components past `target` — not "at least four").
    `TOOLS_DIRNAME` ("tools") is a forge-layout constant, never a service
    name, and it is excluded from this module's own no-service source
    scan for exactly that reason. Everything below the guard
    (`Job.entrypoint`, the ledger's `entrypoint` field, the fold's indices)
    stays deliberately blind to that question; widening this one guard,
    not reworking any of those, is how a future non-notebook workload
    becomes admissible. `--smoke` sets `run_config["mode"] = "smoke"` on
    the `Job` handed to the adapter, and routes the resulting `submitted`
    event to `smoke.jsonl` instead of `ledger.jsonl` (see "Smoke" below) —
    both together, never one without the other.
  - `status` folds the ledger and reports per-entrypoint state, what is
    `staleInFlight`, what is quarantined, and `unreadableLines`. It accepts
    no `adapter` parameter at all — a structural fact, not a convention —
    so it reports and never resolves anything.
  - `poll` asks the adapter for one submission's status and refuses a
    `Status.state` outside the seam's own five-value vocabulary itself,
    rather than trusting every adapter to have gone through
    `ADAPTER.Status.__post_init__`'s own validation.
  - `fetch` materializes into `<dest>.partial/` and renames into place only
    on `Fetched.complete == True`; only a completed rename appends a
    `returned` event, so a crash mid-fetch leaves the submission `pending`
    — retryable, never a false `returned`. `LEDGER.currency_verdict()` (the
    same rule `fold()` itself uses) is evaluated before the rename: a
    `fromStaleSubmission` result overrides the caller's requested `dest`
    entirely and is fetched into
    `<target>/<Name>/.remote-execution/quarantine/<submissionId>/` instead
    — structurally outside `Results/shards/`, so it is parked and
    auditable, never merged. Every `returned` event also carries
    `observedConcurrency`: `LedgerState.pending_for(worker)` read from the
    ledger state at the top of the call, so a service throttling below the
    packer's own grant becomes a visible, different number instead of an
    assumed one.
  - `reconcile` compares `adapter.list_active(worker)` against the ledger's
    own pending set for that worker, in both directions, and only ever
    reports the difference. An id the service has that the ledger lacks is
    `orphanRemote` — reported, never auto-cancelled and never auto-adopted,
    because adopting would fabricate a `submitted` line with no digest, and
    the digest is the entire basis a later result is judged current by. A
    `pending` ledger submission the service no longer lists is
    `orphanLocal` — reported, and `--resolve` (human-invoked only, default
    `False`) is the one path that appends `errored(reason="not-found-at-service")`
    for it.
  - `product_for(target, entrypoint, explicit=None)` resolves which
    product's ledger an entrypoint belongs to — explicit, never guessed.
    Replaces the narrower `name_for()`: an explicit `--product` wins over
    everything; else, for the job-folder shape, the `product` field
    declared in that job's own `run-config.json` (read beside the
    entrypoint, if present); else, for the legacy shape, `<Name>` — the
    first path component past `target`, exactly as `name_for()` always
    derived it; else the call is refused, never silently mapped to a
    guess. Whatever step resolves a product, it must name an existing
    directory directly under `target` and must not be `TOOLS_DIRNAME`
    itself. `status`, `fetch`'s quarantine path and `reconcile`'s ledger
    selection all call this SAME function, so none of them can grow a
    second copy that quietly disagrees with another.
- `scripts/adapters/kaggle.py` — the ONE file below the adapter seam allowed
  to name a service. `workers()` reports usernames from kaggle-accounts' own
  sanctioned `list --json` command (run as a subprocess; this module never
  opens kaggle-accounts' own credential file itself, directly or otherwise),
  each stamped with this service's own documented per-worker allowance
  (`KAGGLE_WORKER_CAPACITY`, a module constant, explicitly not a universal
  one). `submit`/`poll`/`fetch`/`cancel`/`list_active` shell out to
  `adapters/kaggle_driver.py` — the ONLY file in this skill permitted to
  import `kagglesdk`, invoked as a child process the same way this adapter
  used to invoke the `kaggle` CLI directly: `shell=False`, list argv, an
  env built from an allowlist (`PATH` plus, when a credential is involved,
  `KAGGLE_API_TOKEN`), and an explicit timeout on every call; a non-zero
  exit or an expired timeout is a refusal (`KaggleAdapterError`), never a
  fabricated `Status`, `Submission` or `Fetched`. `poll()` translates the
  driver's own reported `KernelWorkerStatus` member name into the seam's
  five-value vocabulary and never passes it through; the raw name goes in
  `Status.detail` only. `CredentialHandle(worker_id, token_path)` is
  the only credential type this adapter accepts, exposes no read method, and
  is consumed at exactly one expression in the whole skill: `_env_for()`
  reads the file that path names and puts its stripped CONTENT on
  `KAGGLE_API_TOKEN` for one child process — the driver's own.

  **The credential travels by value, and that is a trade, not a wording
  change.** The installed client's `_try_fill_auth()` reads
  `KAGGLE_API_TOKEN` and hands it straight to `BearerAuth(api_token)` — by
  value, with no path check of any kind — so a path in that variable becomes
  the literal text of an `Authorization: Bearer` header and authenticates
  nothing. The legacy `KAGGLE_CONFIG_DIR`/`kaggle.json` shape is not an
  escape from that either: it routes an access token (`KGAT...`, the shape
  this skill's credential store issues) through a Basic-auth path it was
  never meant for, and Kaggle answers 401 for every account regardless of
  validity. There is no by-path option left to prefer, so the by-path
  invariant this skill used to claim is spent. What replaces it is narrower,
  structural, and each row below is held to a test rather than to a reader's
  memory.

| # | id | Guarantee | Enforced by | Proven by |
|---|---|---|---|---|
| 1 | `by-value` | `KAGGLE_API_TOKEN` carries the token file's stripped content, never its path — the only shape the installed client authenticates | `_env_for()` | `test_the_env_value_is_the_files_stripped_content_and_never_its_path` |
| 2 | `stripped` | The newline `kaggle-accounts`' `materialize` writes never reaches the header; a newline inside a bearer header is a malformed header, not a credential | `_env_for()` | `test_the_newline_materialize_writes_never_reaches_the_header` |
| 3 | `single-reader` | No module above the adapter touches `token_path` at all, so a credential value has no route into any of them | `_env_for()`, and the absence of the attribute everywhere else | `test_no_module_above_the_adapter_can_reach_the_credential_file` |
| 4 | `fails-closed` | A credential file that cannot be read is a refusal naming the path, never a request sent without one | `_env_for()` | `test_a_credential_file_that_cannot_be_read_is_a_refusal` |
| 5 | `no-empty-bearer` | A credential file holding nothing once stripped is a refusal naming the worker — never an empty bearer header | `_env_for()` | `test_an_empty_credential_file_is_refused_rather_than_sent_as_a_bare_bearer` |
| 6 | `per-process` | Two concurrent submissions for two workers carry two distinct, uncrossed credentials: one fresh env dict per `subprocess.run`, never a shared or process-wide one | `_env_for()`, `_run()` | `test_two_concurrent_submissions_carry_two_distinct_uncrossed_credentials` |
| 7 | `really-concurrent` | The isolation above is proven under genuine overlap, not against two runs that merely happened in sequence | the falsifier's own fake `kaggle`, which records when it started and finished | `test_the_two_submissions_genuinely_overlapped_in_time` |
| 8 | `reached` | Every interception point this driver topology adds — the OUTER double (`kaggle_driver.py` faked on `PATH`) and the INNER double (a recording `requests` transport mounted on the driver's own client session) — asserts a non-zero recorded-call count before any assertion about content; a bypassed double fails rather than passing silently | `_run()`'s subprocess boundary (outer); the driver's own mounted transport in its test fixtures (inner) | `test_outer_interception_reached_count` |
| 9 | `no-sdk-above-the-driver` | `adapters/kaggle.py` names `kagglesdk` nowhere at all — text AND AST, so a live `import` and a docstring mention are both caught, not a reader's promise | `adapters/kaggle.py`'s own source (the absence of the name) | `test_driver_names_kagglesdk_nowhere_in_adapter` |
| 10 | `wire-bearer` | The prepared outbound request carries `Authorization: Bearer <the token's stripped value>`, observed below `BearerAuth.__call__` and above the socket — never a Basic header, anywhere on this path | `kaggle_driver.py`'s `_build_client()` plus the recording `requests` transport mounted on it in its own tests | `test_wire_bearer_header_carries_token_value` |

  Rows 8-10 are new to the child-driver topology; rows 1-7 hold verbatim
  under it — the sink is still `_env_for()`, only what reads the value on
  the other end changed (the `kaggle` CLI's `authenticate()` before this
  change, `kagglesdk`'s own `_try_fill_auth()` now). `fetch`'s per-file
  download URLs (`list_kernel_session_output`) are a known open question,
  not a row: whether they need this session's own Bearer credential or
  answer to an anonymous GET is settled only by a live rehearsal, not run
  by this change. `cmd_fetch` attaches the defensive choice (the same
  already-authenticated session `poll`/`submit` use) rather than guessing,
  and that choice stays **`unverified-by-rehearsal`** until a rehearsal,
  run only on the user's explicit permission, settles it either way.

  `REQUEST_GPU = True` is
  declared here, and here alone in this whole skill — a request, not a
  receipt; what a submission actually ran on is a fact the service states
  at poll/fetch time in `Status.detail`, never assumed from this constant.
  **A named accelerator cannot be requested through this client at all.**
  `assemble_metadata` used to emit `machine_shape: "NvidiaTeslaT4"` and omit
  `enable_gpu` on a claim that the boolean keys were deprecated in favour of
  it; `kernels_push()` in the installed `kaggle` reads `enable_gpu` and
  `enable_tpu` and builds its request field by field, and the string
  `machine_shape` occurs nowhere in that package, so that key was never
  transmitted and every push this skill made ran on CPU. Which GPU a session
  receives is the service's own choice, reported like every other fact this
  skill refuses to guess at. `assemble_metadata`
  writes that request, and every other worker-independent field a push
  needs, into a `kernel-metadata.json` template: `enable_gpu: true` (the
  key the installed client reads, and the one its own `kernels init`
  template writes),
  `enable_internet: true` (the generated runner clones over git inside the
  kernel, and Kaggle disables internet by default), `language`,
  `kernel_type`, `is_private`, and a `title` derived from the job's own
  name. `id` (`<owner>/<kernel-slug>`) and `code_file` are written BLANK —
  no worker is assigned at `generate-job` time, and the same job folder
  pushed to five different accounts needs five different `id` values, so a
  static file written once cannot hold it. `assemble_metadata` is
  registered under `ADAPTER.register_metadata("kaggle", ...)`, the second
  registry `adapter.py` exposes. `KaggleAdapter.submit()` refuses, before
  ever shelling out to `kernels push`, when `job.run_config` is non-empty
  (a generated job) and `kernel-metadata.json` is absent beside the
  entrypoint — an empty `run_config` is the legacy shape and is never
  checked, which is what keeps the credential-sentinel test's legacy-shaped
  `cmd_submit` call passing unchanged. When the metadata file IS present,
  `submit()` completes it — filling in `id` from `job.worker` and the
  entrypoint's own slug, and `code_file` from the entrypoint's own
  basename — inside a STAGED COPY of the job folder in a temp directory,
  and pushes that copy; the versioned `kernel-metadata.json` inside the
  job folder itself is only ever read, never rewritten, so a second push
  to a second worker starts from the same pristine template. This
  completion is driven by the metadata file's own presence, not by
  `run_config`: `cmd_submit` only ever sets `run_config["mode"] = "smoke"`
  for a smoke run, so an ordinary (non-smoke) job-folder submission
  reaches `submit()` with an EMPTY `run_config`, same as the legacy shape
  — the metadata file's presence is what distinguishes them. `cancel()`
  refuses explicitly: Kaggle's own CLI documents no single-kernel cancel
  operation, and this adapter does not guess at an unofficial one.

Every `remote_cli` command a user would invoke (`submit`, `status`, `poll`,
`fetch`, `reconcile`) exists today. `submit`/`poll`/`fetch`/`reconcile` are
exercised in this skill's own test suite against both a `FakeAdapter` and
`adapters/kaggle.py` (the latter only ever against a fake `kaggle`
executable — no test in this suite reaches the network or a real account).

- `scripts/jobfolder.py` — `generate-job`, driven through `remote_cli.py`
  the same way every other command is: `remote_cli.py` loads it as a
  sibling module (`JOBFOLDER = _load_sibling(...)`) and its CLI parser gains
  a `generate-job` subcommand. `generate_job()` builds
  `<target>/tools/<service>/<job-name>/` — `run-config.json`,
  `runner.ipynb`, and one adapter-supplied metadata file — from
  target-supplied values (`--service`, `--job-name`, `--product`,
  an optional `--commit`, `--repo-url`/`--repo-ref`, `--clone-path` repeated,
  `--run-module`/`--run-function`/`--run-kwargs`, an optional
  `--smoke-module`/`--smoke-function`/`--smoke-kwargs`, and an optional
  repeatable `--smoke-required-evidence` — see "Smoke" below for what that
  last one is for) plus one adapter
  registry call: `ADAPTER.resolve_metadata(service)(run_config)` returns an
  opaque `(filename, text)` pair this module writes without ever learning
  what either means — the same registry `adapters/kaggle.py` already
  registers `assemble_metadata` under (see above). `--target` is resolved
  first, and `resolve_destination()` derives the job folder's path from
  that resolved value and refuses outright when the result does not stay
  under `target` — the guard against a crafted `--service`/`--job-name`
  (`../../etc`, say) writing outside the target repository. `run-config.json`
  is written first inside a `<job>.partial/` staging directory, then
  `runner.ipynb`, then the metadata file, and only a fully-written
  `.partial/` is ever renamed into place with `os.replace` — a half-written
  job folder cannot exist. Regeneration (`--regenerate`) replaces an
  existing job folder the same way, via a double-rename (existing folder
  aside under a fresh unused name, new folder into place, aside folder
  removed only after that second rename actually succeeds) so `destination`
  is always either the old folder or the new one, never neither and never a
  mix. A leftover `<job>.partial/` from a previous failed generation is
  reported and refused, never read as a job folder. `run-config.json`'s
  schema is validated both when `generate_job()` builds one and by a
  standalone `validate_run_config()` any future reader can call again;
  `clonePaths` is validated structurally at generation (non-empty, no
  absolute path, no `..`) by `validate_clone_paths()`.
  `runnerTemplate` records each runner asset's path and sha256 as inert
  provenance — deliberately not a drift check; adding one would be a second
  staleness condition, out of bounds for this skill (see design #744
  section 2).

  **The three pin conditions.** Before any of that — before clone paths are
  even resolved, before a byte is written, before any quota is spent — the
  pin goes through three conditions. They live in ONE function,
  `jobfolder.verify_pin_preconditions()`, and both decision points call it
  and nothing else: `generate-job`, which writes a job folder, and
  `submit`, which spends remote quota. One word differs between the two
  calls — the one that appears in the refusal. The order below is the
  contract, and it is cheapest-first: two local, instant questions before
  the one that reaches a network. The first failure refuses; nothing is
  written, nothing is submitted, no ledger event is appended.

| # | id | Condition | Enforced at | Refusal names |
|---|---|---|---|---|
| 1 | `clean-worktree` | The working tree is clean over the declared clone paths — `git status --porcelain`, so an untracked file counts and an ignored one does not. Not a repository, or no commits, refuses too. | `generate-job`, `submit` | Every offending path, and `git add`/`git commit`/`git restore` as the remedy |
| 2 | `pin-is-head` | The pin is HEAD, or nothing changed between the pin and HEAD under the declared clone paths. `unknown` refuses as firmly as `drift`. | `generate-job`, `submit` | The changed clone paths, the pin and HEAD, and git's own message |
| 3 | `declared-paths-exist` | Every declared clone path exists at the pin — `git cat-file -e <pin>:<path>`, asked of the pin and never of the working tree. `sparse-checkout` accepts a path the tree does not contain and fetches nothing for it, silently. | `generate-job`, `submit` | Every absent path, and that the remedy is committing them and pinning the commit that carries them |
| 4 | `pin-published` | The declared remote can serve the pin — `git fetch --dry-run --depth 1` from a scratch repository. | `generate-job`, `submit` | The commit, the remote URL, the missing push addressed to `--repo-ref`, and git's own message |

  **Why condition (1) exists, and why it is `status` and not `diff`.**
  `resolve_clone_paths()` walks the WORKING TREE. Without this condition
  generation validated bytes the runner would never receive: a brand-new
  `run_search.py` that was never `git add`ed satisfied the import walk
  happily and was simply absent from the commit the runner clones, and the
  job died in the kernel with `ModuleNotFoundError` after quota was spent.
  `git diff` cannot catch that — it enumerates changes to *tracked*
  content, so an untracked path is outside its domain by construction. The
  pathspec is what keeps generation possible at all, since `generate-job`
  writes its own untracked output under `<target>/tools/`.

  **Why condition (2) refuses here and only reports at `read()`.** It is
  the same verdict, from the same one computation
  (`jobfolder._staleness_for()`), consumed two ways on purpose: it
  **refuses at a decision point** and **only reports** at `read()`.
  Reading is an observation — refusing there would make a drifted job
  folder unreadable, which is the one state where reading it matters most,
  and `status`, `fetch` and `reconcile` would lose the ability to say what
  is wrong. Refusing belongs where something irreversible is about to
  happen. For a long time only the reporting half existed, and a job
  folder pinned to code that had already moved on was generated, submitted
  and run with the drift printed beside the submission id like weather.

  **`--commit` is optional, and defaults to HEAD.** Omit it and the pin is
  the target's HEAD; stdout reports the commit and `commitSource:
  default-head`, so you can see what was pinned without opening the job
  folder. That source is stdout only — it describes how you typed an
  argument, not a fact about the job, and `run-config.json` records facts
  about the job. The default is safe only because of conditions (1) and
  (2): HEAD is the code that was validated precisely because the tree is
  clean over the clone paths and the pin is that commit. It is resolved
  locally, with `git rev-parse HEAD`, and never from the remote — the
  remote's tip was measured to be older than the entrypoint the operator
  needed, so a remote-derived default would pin code older than yours,
  pass every local check and die in the kernel after quota is spent. An
  explicit `--commit` is never substituted, discovered or overridden, and
  meets the same three conditions.

  **No escape hatch.** There is deliberately no dirty-tree escape hatch:
  no flag accepts a dirty tree, a drifted pin or an unpublished commit,
  and none will be added.
  Every refusal names the exact commands you can run and stops there: the
  tool never commits or pushes on your behalf, and never stages, stashes,
  resets or fetches into your repository either. A commit message is a
  human artifact, and an automatic commit poisons the very history later
  used to say which code produced which number.

  **The reachability probe** — condition (3) in detail. `generate-job`
  refuses a `--commit` the declared
  `--repo-url` cannot serve. `git cat-file -e` proves only that the pin
  exists in the checkout you are standing in, which is never in doubt and
  is not the question; the runner clones a *remote* and checks the pin out
  inside the kernel, so an unpushed pin fails there, after quota is spent.
  `git ls-remote <url> <sha>` cannot answer it either — `ls-remote` matches
  ref *names*, so a bare 40-hex pin comes back empty with exit 0 whether or
  not the remote has it. What answers it is `git fetch --dry-run --depth 1
  <url> <sha>`, whose exit code is the remote's own upload-pack either
  serving the commit or refusing it with `not our ref`.

  Three properties of that probe are load-bearing, and each was learned by
  getting it wrong first:

  1. **It runs in a scratch repository, thrown away afterwards — never in
     your repository.** A repository that already holds the pin answers the
     request from its own object store without contacting the remote at
     all, and the repository you ran `generate-job` from always holds the
     pin you just committed. The first version of this check asked from
     there and therefore passed for every pin anyone could write.
  2. **`--depth 1`, matching what `assets/runner_bootstrap.py` fetches.**
     The probe is only meaningful if it is the runner's own operation.
     `--dry-run` suppresses ref updates but not object transfer, so a
     full-depth probe would pull unbounded history on every generation —
     and running any depth inside your repository would leave those objects
     there (12.8 MiB per generation, measured against this project's own
     remote).
  3. **It is unauthenticated, and stays that way.** The child's environment
     is built from an allowlist that admits `PATH`, proxy configuration and
     the trust store, and admits no credential helper, no agent socket and
     no `HOME`. `runner_bootstrap.py` clones with no credential step at
     all, so a probe that authenticated would pass jobs whose runner can
     never clone the repository — the same defect one layer up. An SSH
     `--repo-url` is not refused on sight; it is probed like any other and,
     if it fails, the refusal says the probe was unauthenticated so the
     failure is not misread as a local accident.

  The refusal names the commit, the remote, the missing push addressed to
  `--repo-ref`, and carries git's own message. Failure to create or
  initialise the scratch repository refuses on that same path: a question
  that cannot be asked is never reported as a clean answer. Nothing is
  written into your repository by the probe — no ref, no `FETCH_HEAD`, no
  object — and the tool never commits or pushes on your behalf.

- `assets/runner_bootstrap.py` (cell 0) and `assets/runner_invoke.py`
  (cell 1) now hold their REAL content — copied byte-for-byte into every
  generated `runner.ipynb`, with zero interpolation, by `jobfolder.py`'s
  `build_notebook()` exactly as before. Both files are importable modules:
  nothing runs at import time, and the one orchestrating call in each
  (`bootstrap()`, `invoke()`) sits behind `if __name__ == "__main__":` —
  the state a notebook cell's own top-level code runs in, and what lets
  the forge test suite (`RunnerBootstrapTests`, `RunnerInvokeTests`)
  import each file under its own module name and drive every function
  directly against fake `run-config.json` payloads, with no notebook and
  no real clone involved for most of them.
  - `runner_bootstrap.py`'s `bootstrap()` runs, in order: read and
    validate `run-config.json` (`load_run_config`); sparse-clone the
    pinned commit (`clone_repo`, entirely through `_run_git()` — the one
    composition point for every git call: `shell=False`, list argv, a
    PATH-only env allowlist, an explicit timeout, non-zero exit is a
    refusal); put the clone's `src/` on `sys.path`
    (`add_clone_to_path`); import every declared entry module (the
    normal `run.module` and, when present, `run.smoke.module`) and
    assert each one's `__file__` resolves under that same clone
    (`verify_imports_under_clone` — the "pip-installed copy" refusal);
    detect hardware (`detect_hardware` — `torch` not importable IS
    "hardware missing", with no silent CPU fallback); write
    `bootstrap.json`. Any refusal along that path raises `SystemExit`
    on the spot, before cell 1 ever gets a chance to run.
  - `runner_invoke.py`'s `invoke()` selects the normal `run` block or its
    `smoke` variant (when `run_config["mode"] == "smoke"`, the mode a
    later slice's `submit --smoke` sets) via `select_block()`, resolves
    `module`/`function` through `importlib` via `resolve_callable()`, and
    calls it with its declared `kwargs`.
  - Both files gained their own `*_module_names_no_service` guard, in the
    same family as `jobfolder.py`'s, `adapter.py`'s, `remote_cli.py`'s
    and `credentials.py`'s — eight in total across this skill now.

  `resolve_clone_paths(target, entry_modules, declared_clone_paths)` now
  holds real content, wired into `generate_job()`. It reuses
  `implementation_cli.py`'s `prior_work_state()` idiom exactly for the walk
  itself (`ast.parse` + `ast.walk` over `ast.Import`/`ast.ImportFrom`,
  inspecting only `node.module`/`alias.name`, with no relative-import
  resolution and no per-name submodule disambiguation) — walked
  transitively, over every module the declared entry modules (`run.module`,
  plus `run.smoke.module` when present) reach, instead of over one fixed
  file set. The granularity rule: a resolved import maps to its top-level
  package directory under `src/`, never to a single file (`src/A/B/C.py`
  => clone path `src/A`; a true top-level module `src/A.py` => clone path
  `src/A.py`). An import that is not this repository's own code (its
  top-level segment names nothing under `<target>/src` at all) is filtered
  and never becomes a clone path or an uncertainty.

  It returns `{declared, computed, computedNotDeclared, unresolved}`.
  `computedNotDeclared` non-empty always refuses generation, naming every
  missing path — never a warning, since this is exactly the sibling-import
  bug that broke a real run. `unresolved` names every uncertain case: a
  non-literal `importlib.import_module(...)` call, any `__import__(...)`
  call, a `sys.path` mutation, an unparsable file, or an import that looks
  like this repository's own code but does not resolve to a file on disk —
  a non-empty result also refuses generation unless `--accept-unresolved`
  is passed, which writes the uncertainty verbatim into `run-config.json`'s
  `unresolvedImports` instead of guessing, converting a silence into a
  recorded, reportable decision. `--accept-unresolved` never bypasses a
  `computedNotDeclared` refusal — only `unresolved`.

  `validate_clone_paths()` gained an optional `target` argument: when
  given, each clone path is also resolved against it and refused if that
  resolution escapes `target` (the symlink-escape case a purely textual
  check cannot see). This is the SAME validator every caller uses —
  `build_run_config()` at generation time (structural only), and
  `resolve_clone_paths()` again once `target` is known — never a second,
  parallel validator for the symlink case.

  Open question this slice inherited from `cmd_submit`'s own `--product`
  migration (T6b) and did not change: `status`, `fetch` and `reconcile`
  still expose no `--product` flag, only `submit` does. This slice's own
  decision: leave that as is. Each of those three commands reads an
  already-generated job folder whose own `run-config.json` already
  declares its product (`product_for()`'s step 2), so an explicit override
  is not load-bearing there the way it is for `submit`, which can be asked
  to record a submission for a job folder with no declared product at all.
  `generate-job` itself needs no `--product` resolution step either — it
  writes the declared `product` value straight into `run-config.json`, it
  never has to resolve one from a path the way `product_for()` does.

  `jobfolder.read(job_dir) -> JobFolder` is now the ONE reader. There is
  no `is_stale()` a caller can forget: `JobFolder.staleness` is computed
  INSIDE `read()`, before it ever constructs one, so reading a job folder
  without getting a staleness verdict alongside it is not something this
  module's API can express at all. `JobFolder` carries `path`, `run_config`
  (re-validated on every read through the same `validate_run_config()`
  `generate_job()` already calls, never a second copy) and `staleness`.

  There is exactly ONE staleness condition, always computed, never
  skippable:

  ```
  head    = git rev-parse HEAD                      # detached HEAD unchanged
  exists  = git cat-file -e <pinned>^{commit}
  changed = git diff --name-only <pinned> HEAD -- <clonePaths…>
  ```

  The pathspec (`-- <clonePaths…>`) does the intersection with the
  declared clone paths itself — deliberately: there is no second,
  independent prefix-matching implementation anywhere in this module that
  could drift from `implementation_cli.py`'s own `prior_work_state.reached()`.
  Verdict is `drift` iff `changed` is non-empty, and it is NEVER a
  refusal — staleness informs, it does not block; two non-gating layers
  already cover it (reported at submit and at `generate-job`'s own CLI
  output, `fromStaleSubmission` on `fetch`). `run-config.json`'s
  `runnerTemplate` provenance is deliberately NOT part of this condition —
  see the note on it above; adding a template-drift check would be a
  SECOND staleness condition, which is out of scope by design.

  `unknown`, with a reason, whenever the question cannot be answered at
  all: no git history, not a repository, or an absent pinned commit —
  reusing `implementation_cli.py`'s own `prior_work_state()`
  `recordStatus: "unavailable"` → `unknown` discipline, never letting an
  unanswerable record pass for a clean one. `unknown` is never rendered as
  `fresh`: absence of evidence is not evidence of freshness, and the two
  are separate branches in `_staleness_for()`, neither one falling back to
  the other.

  `clonePaths` is validated again inside `read()`, through the SAME
  `validate_clone_paths()` `generate_job()` already calls at generation
  time (including its optional `target` argument for the symlink-escape
  check) — never a second, parallel validator. The target a staleness
  check runs `git` against is derived structurally from `job_dir` itself
  (`<target>/tools/<service>/<job-name>/`, exactly as
  `resolve_destination()` builds it), not accepted as a second argument.

  `read()` has its own `_run_git()` — a SEPARATE single composition point
  from `assets/runner_bootstrap.py`'s own `_run_git()` (the two modules
  share no import), with the exact same discipline: `shell=False`, list
  argv, a `PATH`-only env allowlist, an explicit timeout, and `cwd` always
  the caller's already-resolved target — never `git -C` applied to a raw,
  unresolved argument. A pinned commit carrying shell metacharacters
  reaches this argv as one element and is never evaluated by a shell.

  Every job-folder-touching command that exists today routes through
  `read()` and reports its `staleness` alongside whatever else it already
  reports: `generate-job`'s own CLI output, `submit`, `status`, `fetch`
  (both its early "not complete yet" return and its final one), and
  `reconcile`. `remote_cli._job_folder_staleness()` is the one place that
  decides WHETHER a given entrypoint has a job folder to route through at
  all — `None` for the legacy shape (no job folder exists) and for a
  `run-config.json` `read()` cannot make sense of, the same tolerant
  "falls through cleanly" rule `product_for()`'s own narrower run-config
  lookup already applies one step up, so an already-tolerant command never
  became stricter just because staleness reporting was added beside it.
  `poll` is deliberately NOT routed: it receives only `--submission-id`
  and must not learn the worker or the job, so it has no job folder to
  route through in the first place. `readiness` (see below) now routes
  through this same `read()` too, never a second staleness computation of
  its own. Probe's own `remoteExecution` fact does not exist yet (a later
  slice builds it); once it does, it will route through `read()` the same
  way.

## Smoke — a readiness gate, evidence-derived

A smoke run is a rehearsal, not a submission whose result feeds any report.

**A distinct file, not a fourth ledger `kind`.**
`<target>/<product>/.remote-execution/smoke.jsonl` lives beside
`ledger.jsonl`, appended through the exact same `ledger.append()` — but a
different FILE, load-bearing not stylistic. A fourth `kind` inside
`ledger.jsonl` was rejected: `fold()` indexes `latest[entrypoint]`, so a
smoke submission recorded there would become that entrypoint's latest
`submitted` event and silently reclassify a real, still-pending full run
as superseded. `fold()` never reads `smoke.jsonl`, so that is structurally
impossible. `smoke.jsonl` carries two kinds with no such conflict, since
nothing folds it that way: the ordinary `submitted` event a smoke
SUBMISSION writes, and a `smokeResult` event `smoke record` writes.

**`submit --smoke` stays explicit and human-invoked.** It sets
`run_config["mode"] = "smoke"` on the `Job` — opaque to `packer.py`/
`ledger.py` like every other `run_config` key — and routes the resulting
`submitted` event to `smoke.jsonl` instead of `ledger.jsonl`.
`assets/runner_invoke.py`'s `select_block()` already branches on that mode
to pick the declared `run.smoke` block over the normal `run` block.

**The verdict is not a human assertion.** `remote_cli.py smoke record
--job-dir <dir> --from-artifact <path> --worker <worker>` reads the
artifact (a fetched `shard.json`) and passes iff
`shard_io.completeness(stamp, required)` — the SAME predicate T10's
`merge()` uses — reports it complete. Smoke pass ≡ *the evidence stamp is
complete, at this commit, on this worker*. The `required` list reaches
`smoke record` WITHOUT this forge naming a field of its own: it travels
through `run-config.json`'s `run.smoke.requiredEvidence`, declared by the
TARGET at `generate-job` time via the repeatable
`--smoke-required-evidence` flag — carried, never interpreted, the same
way `run.module`/`clonePaths` already are (confirmed by
`test_remote_cli_source_names_no_evidence_field_of_its_own`). Declaring
that list without a smoke block is refused at generation time. `smoke
record` routes through `jobfolder.read()`, and — unlike
`_job_folder_staleness()` — does NOT swallow a `JobFolderError`: this
command has no legacy-shape fallback to fall through to.

**Readiness, and no clock.** `remote_cli.py readiness --job-dir <dir>
--worker <worker>` reports whether a job is ready for its full submission
on that worker — issues no submission, offers no menu, the same
"reports and resolves nothing" discipline `status` already holds
structurally (no `adapter` parameter in either signature). It binds three
facts on the LATEST `smokeResult` record for this job (append order, last
line wins): `result == "pass"`, `commit` equal to the job's CURRENT
pinned commit, `worker` equal to the worker asked about. Nothing here
reads a timestamp — a record's usefulness expires the moment the job
re-pins to a different commit or the worker changes, never after elapsed
time.

`probe` states the fact and submits nothing — `readiness` reports only.
`piloted` (a `proposal-implementation` concept) is untouched, and neither
state implies the other.

## Why append, not a status record

A lost append is detectable — the file is simply shorter than expected, or a
line is malformed. A lost in-place mutation of a "current status" record is
not: the write either lands or it silently doesn't, and there is no earlier
version left to compare against. So this ledger only ever grows. Resubmitting
something appends a new `submitted` line; it never erases the one it
supersedes.

## Why an append can be trusted

Four things, held together, and the first two are enforced in code, not by
convention:

- The return value of `os.write()` is checked against the byte count of the
  event about to be written, and a mismatch raises. A write can legitimately
  return short, and a short write is exactly what tears a JSONL line — a
  torn line is a lost submission, which is the one outcome this ledger
  exists to make impossible. This check is the actual defence, not the mere
  existence of an append call.
- Every event is capped at 4096 bytes before it is ever written. The
  fields in this schema — a path, a 64-hex digest, an opaque id, a worker
  name, a timestamp, an already-truncated failure reason — have no business
  producing a line anywhere near that size; exceeding it means something
  that should have been truncated was not. This number is a sanity bound on
  this schema, not `PIPE_BUF`: `PIPE_BUF` governs pipes and FIFOs, not
  regular files, and its value is platform-specific anyway (512 on darwin,
  4096 on Linux) — the wrong number, from the wrong object, and on this
  platform from the wrong operating system.
- `O_APPEND` on a regular, local file makes seek-to-end-and-write atomic as a
  unit with respect to other appenders, so two concurrent writers cannot
  interleave into the same region. `append()` writes through a raw fd
  (`os.open`/`os.write`), never Python's buffered `open(path, "a")`, because a
  buffered file object may split one logical write across syscalls and
  reintroduce exactly the interleaving `O_APPEND` exists to prevent.
- The ledger lives on a local filesystem only. NFS does not honor `O_APPEND`
  atomicity; the ledger is expected to live inside the target's own git
  checkout, which is a local clone.

## Event kinds

| event | fields |
|---|---|
| `submitted` | `ts`, `entrypoint`, `sourceDigest`, `submissionId`, `worker`, `requestedCapacity`, `grantedCapacity` |
| `returned` | `ts`, `submissionId`, `artifactPath`, `observedConcurrency` |
| `errored` | `ts`, `submissionId`, `reason` (truncated to 512 chars) |

`entrypoint` is the field name for the thing executed remotely — not
`notebook`. This schema and the adapter seam (`scripts/adapter.py`) both use
the same name for it, and neither carries a format opinion about what it
points to; that policy question belongs to the CLI that submits, not to
this record.

This table is `ledger.jsonl`'s own vocabulary — the one `fold()` indexes
by `latest[entrypoint]`. `smoke.jsonl` is a physically separate file (see
"Smoke" above) and carries its own, unrelated vocabulary:

| event | fields |
|---|---|
| `submitted` | the same shape as above — written by `submit --smoke` |
| `smokeResult` | `ts`, `jobName`, `result` (`"pass"`/`"fail"`), `commit`, `worker`, `missing` — written by `smoke record` |

## Environment

**This skill's own Python is stdlib-only except one named driver script.**
The prior sentence here claimed a floor this section no longer defends and a
packaged-client absence this driver script disproves; both are retired
outright, not softened into a paraphrase that would leave the same claim in
different words. Every module here — the ledger, the adapter seam, the packer, `remote_cli.py`,
`jobfolder.py`, the runner assets — imports nothing beyond the standard
library. The one exception is `adapters/kaggle_driver.py`: it imports
`kagglesdk`, vendored inside the `kaggle` distribution this repository's own
`requirements.txt` pins at `kaggle==1.7.4.5` (see the credential-transport
table above), and it is the ONLY file in this skill permitted to. Nothing
else in this skill needs it: the ledger, the packer, the seam and every
command that only reads them run with no packaged client installed at all.
But `submit`, `poll`, `fetch` and `smoke` all end at that one driver script,
so on an interpreter that cannot import `kagglesdk` they cannot start.

**No enforced minimum Python version — the driver's own selftest gates,
never a version number.** This skill declares no `python_requires` and holds
no version floor anywhere in its code; what actually gates is
`kaggle_driver.py selftest`, run against the exact interpreter that will
invoke it (`sys.executable`, inherited from the calling adapter process). It
reports whether `kagglesdk` imports under that interpreter and, if it does
not, refuses by name — the interpreter path and the exact install command —
rather than asserting a version nothing checks
(`test_driver_selftest_imports_kagglesdk`). Measured on this machine:
`kagglesdk` is installed and importable under the system `/usr/bin/python3`
(3.9); it is not installed under the Homebrew 3.11/3.12 interpreters also
present here. Whichever interpreter a given machine actually resolves
`sys.executable` to is the one the selftest must pass under, and that is an
empirical fact about that machine, never a version this skill promises in
advance.

Check pip's own note about where it put the driver's dependency: if that
directory is not on the resolving interpreter's import path, the package is
installed and still unreachable, which reads exactly like not having
installed it. A backend that cannot be found refuses by name and says this —
see `KaggleAdapter._run` and `kaggle_driver.py`'s own import-time refusal —
rather than surfacing a raw traceback and leaving a reader to guess.

A second backend brings its own answer to this section: nothing above the
adapter seam knows a service exists, so nothing above it knows what a service
needs.

## Ledger data location

Code is forge-owned and lives here, inside the skill. Data is target-owned:
`<target>/<Name>/.remote-execution/ledger.jsonl`, inside the target's own git
checkout, alongside the repository whose submissions it records.

## Smoke data location

`<target>/<product>/.remote-execution/smoke.jsonl` — the SAME directory
`ledger.jsonl` lives in, product-scoped exactly like it, but a distinct
file (see "Smoke" above for why that separation is load-bearing, not
stylistic).

## Quarantine location

`<target>/<Name>/.remote-execution/quarantine/<submissionId>/` — a
`fromStaleSubmission` result's fetch destination, structurally outside
`Results/shards/`. This is what makes the non-merging structural rather than
procedural: the tree a shard reader enumerates never contains this path, so
there is nothing a filter could forget to apply.
