# Design: the-path-that-reaches-a-run

## Technical Approach

Nine findings, one path: **provision → approve → spread → launch → refuse early**. No new module and no new artifact format. Every repair lands on an existing seam — `runner_bootstrap.py`'s eight ordered responsibilities, `run-config.json`'s additive schema, `__benchmark__`'s declaration blocks, `packer.distribute()`'s already-computed spread, and `_build_parser()` as the single source of flag truth. The four product questions are settled by the user: **refuse** on mismatch, **every healthy account** with named exclusions, **per-campaign** consent never persisted, **both accelerator halves in this batch**.

Two doctrines already in this codebase carry most of the weight and are reused rather than re-argued: *a question that could not be asked is not a question answered yes* (`_verify_commit_reachable`, `_triage`'s `in_flight_source`), and *refuse while refusing still costs nothing* (`_gate_job_folder_pin`).

## Architecture Decisions

| # | Decision | Choice | Rejected alternative | Rationale |
|---|---|---|---|---|
| 1 | Accelerator matching rule | Declare `accelerator: {kind, architectures[]}`; the refusal turns on **`torch.cuda.get_device_capability()` ∈ `torch.cuda.get_arch_list()`** | Exact device-name string equality against `bootstrap.json`'s `device.name` | A name answers *is this the card I named*; the arch check answers *can this build run here*, which is the question the P100 actually failed. `Tesla T4` vs `Tesla T4 x2` makes the string brittle in both directions. The declared `architectures` is checked against the **installed** arch list, so it holds the torch build honest rather than naming a card |
| 2 | Where the refusal happens | Cell 0 (`runner_bootstrap.py`), as responsibility 8, **after** `write_bootstrap_output()` | Refuse inside `detect_hardware()`, before the write | Cell 1 already cannot run after a cell-0 `SystemExit`, so "before training" is structural. Writing first is what makes the refusal readable: `bootstrap.json` survives carrying the arriving device, the torch build and the arch list the verdict was computed from |
| 3 | Dual-architecture build | Additive `environment.install: {requirements[], indexUrl}` in `run-config.json`, run as `sys.executable -m pip install` with list argv, **before** responsibility 4 (the declared modules import torch) | An opaque command list the runner executes | The forge names two fields and no package; a requirement-specifier list cannot smuggle a flag once specifiers beginning with `-` are refused. Cost accepted: minutes per kernel × 30 shards. **Which build loaded is answered by `environment.torch`**, already recorded; `environment.archList` is added beside it because a version string does not say which architectures it covers, and the refusal turns on that |
| 4 | Consent mechanism | `submit` refuses by default; released by `--consent <token>`, where the token is the digest of *(pin commit, relative entrypoint, ordered unit list)* printed by `distribute`. Read **only from parsed argv** | A `--yes` boolean; an env var; a ledger/config key | A boolean baked into a wrapper script is today's defect in a file. A derived token is structurally self-expiring: it stops authorizing the moment the pin or the unit set moves. Three locks make non-persistence structural — argv-only reads, a whole-tree hash snapshot proving nothing on disk carries it, and a cross-campaign token that refuses. **Honest limit: no gate can prove a human was present; it proves the launch was deliberate, bound and unstored** |
| 5 | Scope of one approval | The exact ordered unit list of that invocation. Added, removed or reordered units refuse | Consent over a time window or an account set | Live worker health is the service's fact, not the operator's decision; binding it would let a flapping account revoke an approval |
| 6 | `submit` consumes `distribute` | `submit --unit` (repeatable, same flag `distribute` declares) switches to campaign mode: `PACKER.distribute()` replaces `select()`, one `adapter.submit()` and one ledger event per assignment | Reimplement the spread inside `cmd_submit` | The spread already exists and is proven; only its consumer was missing. Single-unit `submit` keeps today's `select()`/`plan()` path byte-identical |
| 7 | What the campaign result reports | `assignments[]` (whole `Plan` + units + submission id per worker), `unplaced[]`, and `skipped[]` (worker → reason), carried from `Distribution` unchanged | A count of submissions | `Distribution` already refuses to collapse its facts, and "named with its reason" is exactly `Skip.reason` |
| 8 | `env` manifest provisioning | One `pip install` invocation listing the forge's `requirements-dev.txt` **first** and every honoured target manifest **last**: `-r requirements.txt`, `-r requirements-dev.txt`, then `-e .` when `pyproject.toml`/`setup.py`/`setup.cfg` exists. `environment.yml` is reported `unhonoured` with its reason. None present → `manifests: []` and a stated absence, never a green light | Several invocations; or honouring whichever manifest is found first | One invocation makes pip resolve jointly, so a conflict surfaces as pip's own error instead of a silently shadowed pin; target-last means the target's pins are what a conflict is reported against. A conda manifest a venv cannot read is named, not ignored. `env` still hands a `nextCommand` and installs nothing itself — today's shape |
| 9 | What "live" must prove | `introspect()` additionally **imports the module the target declares as its entry** inside the prescribed interpreter. Failure → `live: unavailable` carrying the real last line | Checking `.venv` contents, or `pip list` | Importing `<Package>_Benchmark.config` is what answered `ok` on an empty venv — pure Python imports fine. The declared entry is the module that actually pulls the runtime in, so its `ModuleNotFoundError` is the truthful verdict, quoted rather than paraphrased |
| 10 | Harness name resolution | `__benchmark__` grows a seventh block, `entry: {module, function}` — the same two values `generate-job --run-module/--run-function` already require. `BENCHMARK_MODULE` stops being a location and becomes reachable only as the kit's scaffold default | Adding `harness.py` beside `benchmark.py`; scanning `src/<Package>_Benchmark/` for a harness | A second hardcoded name is the same defect twice; scanning cannot say *which* module is the harness. **Absent vs unexpected-name** falls out: declaration missing → `harnessStatus: undeclared`; declared and present → path; declared and missing → `declaredMissing`, naming the declared name and where it looked. Cost: the scaffold's "six blocks" prose and its tests move to seven |
| 11 | The two disagreeing gates | The **declaration is the fact**: `search.requiredScale`. `search_state` reads the record's own recorded scale along the declared axis names and reports `recordScale` + `scaleSatisfied`. `nextStep` may not reach `benchmark`/`piloted` when it is not satisfied | Re-implementing the harness's ceiling rule in the forge; or making `probe` stop answering | The forge cannot edit the harness (separate repo). Both gates read the same declared numbers and the same record, so neither owns a rule of its own — the axes are the target's vocabulary, carried, never learned. **`scaleSatisfied: null` (the record names none of the declared axes) does not advance either**: an unprovable precondition is not a satisfied one |
| 12 | New `nextStep` rungs | `env-first`, inserted immediately after `declare-first`; the below-scale case reuses `search-first` with a `reason` | A new state per cause | Introspection is meaningless before something is declared, so `declare-first` keeps the top of the ladder; below-scale and no-record share one remedy — run the search at declared scale |
| 13 | The three refusals | (a) `pin-published` gets its own timeout constant, separate from `_run_git`'s local default; (b) `guard_entrypoint` detects a **directory holding `run-config.json` + `runner.ipynb`** and names the notebook inside it; (c) `product_for` takes the calling subcommand and builds its remedy from `_build_parser()`'s declared flags | Hand-written per-subcommand messages | A shared budget made the verdict track the link — measured 209 s then 27 s on the same commit. A message derived from the parser cannot name a flag its subcommand does not declare; prose can and did |
| 14 | The guiding table | A **flags column** and a **stale-pin row** (job folder exists, `staleness: drift` → `generate-job`), both held by a test that reads `_build_parser()`'s subparser actions, extending the existing column-one parser check | Prose maintained by hand | This file already holds column one to the parser; doctrine held by parsed tables is the established pattern |

## Data Flow

```
distribute --unit … ──→ spread + consent challenge (read-only, records nothing)
        │                          │ token = sha256(pin, entrypoint, ordered units)
        ▼                          ▼
submit --unit … --consent <token>
   guard_entrypoint → product_for → _gate_job_folder_pin → consent gate
        │                                                       │ refuse: no token / wrong campaign
        ▼
   PACKER.distribute() ──→ per assignment: adapter.submit() → LEDGER.append()
        └──→ result: assignments[] · unplaced[] · skipped[worker → reason]

runner cell 0:  config → clone → sys.path → INSTALL → imports → detect →
                write bootstrap.json → ACCELERATOR GATE → (SystemExit | cell 1)
                                            └─ capability ∈ archList? declared ⊆ archList?

env → nextCommand(dev-reqs first, target manifests last)
        │
probe → introspect(declared entry module, in <target>/.venv) → live
        └─ live ≠ ok → env-first;  scaleSatisfied ≠ True → search-first
```

## File Changes

| File | Action | Description |
|---|---|---|
| `remote-execution/assets/runner_bootstrap.py` | Modify | Install step; `archList`/`capability` in `environment`; write-then-gate reorder; `AcceleratorError` path |
| `remote-execution/scripts/jobfolder.py` | Modify | `accelerator` + `environment.install` in `build_run_config`; `pin-published` own budget; `--entrypoint` shape message input |
| `remote-execution/scripts/remote_cli.py` | Modify | Consent gate; campaign mode in `cmd_submit`; parser-derived remedies in `product_for`; job-folder-directory detection in `guard_entrypoint`; new `submit`/`generate-job` flags |
| `remote-execution/SKILL.md` | Modify | Authorization, accelerator and spread contracts |
| `proposal-implementation/scripts/implementation_cli.py` | Modify | `cmd_env` manifests; `introspect` entry import; `search_state.recordScale`/`scaleSatisfied`; harness from declaration; `env-first` rung |
| `proposal-implementation/assets/kit/src_benchmark/__init__.py` | Modify | Seventh block, `entry`, prefilled empty |
| `proposal-implementation/SKILL.md` | Modify | Flags column, stale-pin row |
| `tests/test_remote_execution.py`, `tests/test_proposal_implementation.py` | Modify | Every lock, each seen RED first |

## Interfaces / Contracts

```jsonc
// run-config.json — additive, schemaVersion stays 1 (absent blocks behave as today)
"accelerator": { "kind": "cuda", "architectures": ["sm_60", "sm_75"] },
"environment": { "install": { "requirements": ["<spec>", "…"], "indexUrl": "https://…" } }

// bootstrap.json — additive under the environment block the proposal preserves
"environment": { "device": {...}, "torch": "…", "archList": ["…"], "capability": "sm_60" }
```

```python
# __benchmark__ — seventh block; the two values generate-job already requires
"entry": {"module": "", "function": ""}
```

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Unit | Arch comparison, install argv construction, token derivation, manifest ordering, `scaleSatisfied` tri-state, parser-derived remedies | Direct function calls; no network, no launch |
| Integration | `bootstrap()` against fake configs + a fake `torch` module (the existing `hardware_import` seam); campaign `submit` against the adapter double; `env` + `probe` over a built target tree | In-process doubles, exactly as today's suite drives cell 0 |
| E2E | None. **Nothing is launched to Kaggle** | Out of scope by the proposal's hard boundary |

Strict TDD with inversion: every lock seen to FAIL first by **disabling the guard**, never by flipping a comparison; restored by inverse patch confirmed by `sha256`. Suite count must rise from 1160 by exactly the number added.

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED tests |
|---|---|---|---|
| Documentation-like paths | **Applicable** — `env` and the runner install from `requirements.txt`/`pyproject.toml` | Manifests are handed to `pip` as `-r`/`-e` arguments and never executed or interpreted by the forge; specifiers beginning with `-` are refused so a manifest entry cannot become a flag | A spec `--index-url evil` refuses; a manifest whose contents are shell-shaped installs as data |
| Git repository selection | **Applicable** — `pin-published`'s scratch-repo probe gains its own budget | `_run_git` unchanged: `shell=False`, list argv, `PATH` allowlist, `GIT_TERMINAL_PROMPT=0`, `stdin=DEVNULL`; only the timeout argument differs, and the scratch dir stays the cwd | A slow transfer inside the new budget passes; the probe still never runs in `target` |
| Commit state | **Applicable** — consent binds the pin | Token derives from the job folder's own declared commit, read through `JOBFOLDER.read()` | A token minted at pin A refuses at pin B |
| Push state | N/A — no ref is written by this change | — | — |
| PR commands | N/A — delivery is ordered commits on `main` | — | — |
| Subprocess (added row) | **Applicable** — `pip` inside the runner | `sys.executable -m pip`, list argv, `PATH`-only env, explicit timeout, non-zero exit is a refusal — the discipline `_run_git` already sets | Timeout refuses; non-zero exit refuses; no shell is ever invoked |

## Migration / Rollout

No migration. `run-config.json` and `bootstrap.json` changes are additive under `schemaVersion 1`; a job generated before this change has no `accelerator` block and behaves exactly as today. No ledger schema change. Ordered, independently revertable commits: **(1) accelerator declaration + gate → (2) torch build → (3) spread → (4) consent → (5) env + liveness → (6) harness + gate agreement → (7) messages → (8) doctrine**. Finding 9 (doctrine) defers first against the 1200-line budget.

The consent gate turns today's green `submit` tests red. Those updates land in commit (4) **visible in the diff**, never quietly folded into another slice.

## Open Questions

- [ ] The spec's provisional wording for the accelerator declaration says *kind + name*; this design chooses *kind + architectures* (Decision 1). The spec row needs that one-line correction — the requirement ("a run does not proceed on a card that will fail") is unchanged.
- [ ] `pin-published`'s new budget needs a number. Measured evidence is 209 s and 27 s on the same commit at 12.4 MiB; the value is picked in tasks from that measurement, not invented here.
