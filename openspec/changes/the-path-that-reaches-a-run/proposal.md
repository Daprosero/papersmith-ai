# Proposal: the-path-that-reaches-a-run

Change: `the-path-that-reaches-a-run` · Skills: `proposal-implementation` + `remote-execution` · Store: hybrid · Delivery: ordered commits on `main` (no branches, no PRs; the reviewable unit is the commit) · Review budget: 1200 authored lines

## Intent

**Both paths already work. That is the finding this proposal opens with, because it changes what has to be built.**

The **local path runs end to end**: `probe` → search → `ceilings.json` → the flow advances `search-first` → `report-first` → `nextStep: benchmark` → **`CAMPAIGN OK`**, 60 result rows, with `ceilings.json`, `curves/*.pdf` and `latent/` on disk. Nothing was structurally broken. Three days were spent blocked by defects that were present from the start and that **only a single end-to-end drive could surface**.

The **remote wiring also works**: the rehearsal cloned the pinned commit, imported the harness from the clone, and obtained a GPU. It died 42 seconds in, for one reason, and that reason stayed invisible until the `fetch` nested-path fix let the log be recovered.

So this change is not construction. It is the batch of ten findings that one full drive produced — the difference between a path that works and a path a user can actually walk.

**This proposal absorbs and supersedes `openspec/changes/the-step-that-closes-the-door-it-opened/`**, written before the drive reached the remote side. Everything still true there is carried forward below. That change must not be treated as a parallel change, worked, or archived separately.

## The batch, in the order the user approved

| # | Finding | Evidence | Skill |
|---|---|---|---|
| 1 | **The accelerator kills every remote run** — see below | rehearsal log; `remote-execution` | remote |
| 2 | **`submit` does not spread across accounts** — `cmd_submit` (`remote_cli.py:491`) calls `PACKER.select()`, which takes the **first healthy** account. `cmd_distribute` (`:701`) computes the spread and its own docstring says *"nothing is recorded and nothing is handed to"*. The spread exists and **nothing consumes it** | five accounts: `Daprosero`, `DaproseroM2`, `Diego9901`, `Trayectoria51`, `Trayectoria50` | remote |
| 3 | **`submit` asks nobody before launching** — the "nothing is launched without explicit permission" rule has lived only in agent instructions, never in the skill. A fresh session invoking `submit` meets nothing that asks | absence, measured | remote |
| 4 | **Three refusals name the wrong cause** — `pin-published` shares a 120 s budget with local git while transferring 12.4 MiB and reports *"commit not pushed"* (measured 209 s, then 27 s, same commit: the verdict tracked the link); `submit --entrypoint` handed the job **folder** refuses as though the folder were misplaced and sends the user to regenerate a correct job; `status` refuses on *"no explicit `--product`"* and **that subcommand does not declare `--product`** — only `submit` does | measured | remote |
| 5 | **`env` builds an environment that cannot run the target — the deadlock** | see below | impl |
| 6 | **`report.live` answered `ok` on that empty venv** — the gate that approves the environment never checks the environment can run anything, and cleared the way to a run it cannot perform | measured | impl |
| 7 | **`probe` reports `harness: null` while the harness exists** — `BENCHMARK_MODULE = "benchmark.py"` (`implementation_cli.py:1415`); the target's file is `harness.py`, the same name the target's own job config declares (`"module": "MIL_CREDA_Benchmark.harness"`) | measured | impl |
| 8 | **`probe` and the harness disagree about whether a run may start** — `probe` answered `nextStep: benchmark`; the harness then refused with *"refusing to run on ceilings searched below scale"*. Two gates over one fact, two answers | measured | impl |
| 9 | **The guiding table has no flags and no row for a stale pin** — the nine-row state→subcommand table maps a state to a subcommand but never to its flags; three mismatches hit while driving, including `readiness` (`--job-dir/--worker`, not `--target/--entrypoint`). `generate-job` covers an **absent** job folder, `reconcile` covers ledger-vs-service drift; a folder that **exists and is pinned to a stale commit** — the state that blocked a launch this week — maps to no row | measured | impl |
| 10 | **`search_ceilings` `KeyError`** — target code. **Handed over, not repaired.** See *Recorded, not proposed* | `harness.py:835-840` | — |

### Finding 1, in full — the accelerator

The rehearsal ends in `AcceleratorError: CUDA error: no kernel image is available for execution on the device` (`cudaErrorNoKernelImageForDevice`). Kaggle assigned a **Tesla P100-PCIE-16GB** (`sm_60`); the image's `torch 2.10.0+cu128` ships no kernels for that architecture.

**Asking for a T4 is impossible, and this is measurement, not opinion.** The entire installed SDK surface exposes exactly two accelerator-related fields — `enable_gpu` and `enable_tpu`. No accelerator name, no machine shape, not in the older CLI package either; `ApiSaveKernelRequest` has 19 fields and none names a device. **Retiring the `NvidiaTeslaT4`-by-name request was correct.** What was wrong is what came after: retiring the *request* left the *requirement* with nothing holding it.

The user's framing is the right one — *"no es pedir, es que cuando se use kaggle se lance con esta configuración"*:

- The job **declares** the accelerator it expects, in `run-config.json`, beside the commit, clone paths and module it already declares.
- The runner **compares** it against what arrived. **Nothing new has to be captured** — `bootstrap.json` already records `"environment": {"device": {"kind": "cuda", "name": "Tesla P100-PCIE-16GB"}, "torch": "2.10.0+cu128"}`. Only checked.
- On a mismatch it acts **in seconds, before training**, instead of dying at forty-two with a CUDA error and a spent session.
- The durable half: a torch build covering both `sm_60` and `sm_75`, so the draw stops deciding. **Its cost, stated honestly:** installing torch per kernel adds minutes to every run, and a campaign is thirty shards.

**Open decision, put to the user rather than settled here: does the accelerator check *refuse* or *warn*?** And one genuine unknown, recorded as unknown: **whether pushing to an existing kernel preserves the accelerator chosen in Kaggle's own UI. Only a rehearsal settles that; it is not guessed here.**

### Finding 5, in full — the deadlock

| Half | Evidence |
|---|---|
| `env` (`cmd_env`, `implementation_cli.py:4216`) creates `<target>/.venv`, reports `status: "created"`, and hands a `nextCommand` installing **only** the forge's `assets/requirements-dev.txt` — `pytest`, `numpy`, `ipykernel`, `nbconvert` | It never installs the target's own `requirements.txt`, where `torch`, `torchvision`, `torchcam` and `timm` are declared. `implementation_cli.py:103-110` (`ROOT_KEEP`) **already enumerates six dependency manifests**, so the general fix needs no new target vocabulary at all |
| The target's `harness.py:76-81` refuses any interpreter outside the repository **only when `<target>/.venv` exists** | Before `env`, the system interpreter runs everything — which is how a search succeeds and hides this completely. After `env` — the step the flow itself prescribes — the system interpreter is forbidden and the prescribed one raises `ModuleNotFoundError: torch` |

**Running the prescribed step is what closes the door.** Proven both ways by running it.

## Scope

### In scope — one batch, two skills, one causal story

Findings 1–9. **Why two skills:** these are not two projects. They are one path — provision, approve, spread, launch, refuse early — and a repair at either end alone leaves the path closed. The user asked for one batch. Stated here so it does not read as scope drift.

### Out of scope — the hard boundary

| Excluded | Reason |
|---|---|
| **`implementations/Domain_Adaptation`** | Separate repository (`Daprosero/Domain_Adaptation`), read-only from this forge. **Never edited.** Finding 10 lives here |
| **`openspec/config.yaml`** | It pins the test command to `test_extract_pdf.py` and never runs these suites — a real defect, deliberately left as bait for a real audit |
| Any other skill | Editable surface is exactly `.claude/skills/proposal-implementation/`, `.claude/skills/remote-execution/`, and their tests |
| **Any launch to Kaggle** | This change's own work launches nothing. Every verification is local or against doubles |
| `implementations/_e2e_full_flow` | Gitignored throwaway; the `E2E BOX ONLY` one-epoch reduction lives only there and is removed |

### Preserved, at the user's explicit request

- The **five accounts and their `KGAT_` tokens stay as they are** — that path already authenticates; nothing is regenerated.
- The **real scale is untouched**: 20 epochs × 3 seeds for the search, 30 seeds for the campaign.
- **The forge never learns `torch` or any target vocabulary.** A guard enforces it and caught four leaks in one sitting.
- **`bootstrap.json` keeps recording the arriving device** — that record is what made the accelerator diagnosis possible.

## Capabilities

### New Capabilities
- `accelerator-contract`: the job declares the accelerator it expects; the runner compares it against the arriving device before training and acts on a mismatch.
- `launch-authorization`: `submit` refuses by default and is released only by explicit, per-launch consent that is never persisted.
- `target-environment-provisioning`: `env` installs the target's own declared manifests, and `probe` reports an environment live only on executed evidence.

### Modified Capabilities
- `remote-execution`: `submit` consumes the distribution across every healthy account instead of the first one.

## Approach

| # | Approach | Boundary held |
|---|---|---|
| 1 | Declare the expected accelerator in `run-config.json`; the runner compares against `bootstrap.json`'s already-recorded device and acts **before** training. Torch build covering `sm_60`+`sm_75` as the durable half, with its per-run cost stated | The forge names a **field**, never a device model or package |
| 2 | `submit` consumes `distribute()` rather than `select()`. The honest guarantee is **every healthy account**, with any account left out **named in the result along with why** | Unit opacity, as the archived distribution change settled |
| 3 | `submit` refuses unless the invocation itself carries explicit consent; **consent travels with the invocation and is never persisted** — any stored switch reproduces today's defect with extra steps. Ask once per launch; once approved, continue | Not a config flag, not an env var that outlives the process |
| 4 | Separate the budget from the verdict and the shape from the location: `pin-published` gets its own budget; `--entrypoint` names the **shape** it wanted; `status` cannot refuse on a flag it does not declare, locked by a **parser-derived** test | Messages derived from the parser, never hand-written prose |
| 5 | `env` provisions the target's own declared manifests, keyed off the names `ROOT_KEEP` already enumerates | **The forge must not learn a package name** |
| 6 | `probe` stops answering `live: ok` on a venv it has only inspected; liveness becomes evidence of an execution, and `nextStep` may not advance past an environment that has produced none | — |
| 7 | `probe` distinguishes *absent* from *not under the name I expected*, taking the name from the target's **own declaration** | **Not** a second hardcoded name |
| 8 | One fact, one gate: `probe` and the harness must not answer differently about whether a run may start | — |
| 9 | The state→subcommand table grows a **flags column** and a **stale-pin row**, both derived from `remote_cli`'s parser by a test | Doctrine held by parsed tables, never prose |

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `.claude/skills/remote-execution/scripts/remote_cli.py` | Modified | Consent gate and distribution consumption in `cmd_submit`; three refusal messages; `pin-published` budget |
| `.claude/skills/remote-execution/scripts/` (job generation / runner) | Modified | Accelerator declaration in `run-config.json`; pre-training comparison against `bootstrap.json` |
| `.claude/skills/remote-execution/SKILL.md` | Modified | Authorization contract, accelerator contract, spread guarantee |
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modified | `cmd_env` provisioning; `probe` liveness, harness discovery, gate agreement |
| `.claude/skills/proposal-implementation/SKILL.md` | Modified | Table flags column, stale-pin row |
| `tests/test_remote_execution.py`, `tests/test_proposal_implementation.py` | Modified | New locks, each seen RED first |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **The consent gate turns today's green `submit` tests red** | **High — expected, and named as a cost** | Those tests encode the ungated behaviour. Updating them is part of the change and **must be visible in the diff, not quietly updated** |
| Target vocabulary (`torch`, a device model, a package name) leaks into the forge | **High** | The fix names *manifests* and *fields*, never packages or devices; the vocabulary guard is run deliberately — it caught four leaks in one sitting |
| The refuse-or-warn decision is settled by the agent instead of the user | High | Raised as an explicit open decision below; not resolved in this proposal |
| Push-to-existing-kernel accelerator preservation is guessed | Med | **Recorded as an unknown. Only a rehearsal settles it — and no launch happens in this change** |
| Per-kernel torch install makes every run minutes slower × 30 shards | Med | Cost stated up front so the tradeoff is chosen, not discovered |
| Liveness-by-execution makes `probe` slow or newly failure-prone | Med | Smallest possible executed evidence; a target with no environment gets a truthful refusal, never a hang |
| 1200-line review budget exceeded | Med | Ordered commits, one per finding cluster; finding 9 (doctrine) is the first slice to defer |
| A repair appears to need an edit under `implementations/` | Med | Report as a finding; never edit. Finding 10 is the precedent |

## Rollback Plan

Ordered, independently `git revert`-able commits on `main`. Behaviour-bearing commits: the accelerator contract (1), the spread (2), the consent gate (3), provisioning + liveness (5+6). Reverting (3) restores today's ungated `submit`; reverting (5+6) restores today's deadlock; reverting (1) restores today's silent 42-second CUDA death. Message and doctrine commits (4, 9) are inert. No on-disk artifact format changes beyond the additive `run-config.json` field and **no ledger schema change**, so no migration. TDD inversion throughout: every lock seen to FAIL before it passes, restored by inverse patch confirmed by `sha256` — never `git checkout --`.

## Dependencies

- Baseline: `python3 -m unittest discover -s tests` → **1160 tests, OK**. HEAD `3b1590a`, tree clean.
- `rg`/`fd` honour `.gitignore` **and hide dotfiles**; `implementations/` is gitignored and the ledger lives in `.remote-execution/` — pass `--no-ignore -H`.
- No network, no Kaggle launch, no credential regeneration.

## Success Criteria

- [ ] A job declares its expected accelerator; a mismatch is detected **before training** from the device `bootstrap.json` already records, in seconds rather than at forty-two.
- [ ] `submit` uses **every healthy account**, and any account left out is **named with its reason** — never silently dropped.
- [ ] `submit` refuses to launch without explicit consent carried by the invocation, and **no consent is persisted** between invocations.
- [ ] Each of the three refusals names its real cause; `status` cannot refuse on a flag it does not declare, held by a parser-derived test.
- [ ] After `env` and its `nextCommand`, the prescribed interpreter runs the target's campaign without `ModuleNotFoundError`, and the repository's own interpreter refusal is not triggered.
- [ ] `probe` cannot report a live environment, nor advance `nextStep`, without evidence that something executed.
- [ ] `probe` distinguishes an absent harness from one under an unexpected name, without a second hardcoded name.
- [ ] `probe` and the harness give the same answer about whether a run may start.
- [ ] The state→subcommand table carries flag shapes and a stale-pin row, both derived from the parser by a test.
- [ ] The forge contains **no target vocabulary** — no package, module, or device name from any repository under `implementations/`.
- [ ] Suite count **rises** from 1160 by exactly the number of tests added; a suite merely staying green is not evidence.
- [ ] Every new lock proven reachable-red by inversion, restored by inverse patch confirmed by `sha256`.
- [ ] **Nothing was launched to Kaggle.**

## Proposal question round

Interactive mode; this phase cannot address the user directly. Four product questions, with the assumption standing in meanwhile so it can be corrected now rather than discovered later. Answering, skipping, correcting the framing, or asking for a second round are all fine.

1. **Refuse or warn on an accelerator mismatch?** This is the user's own open decision and is deliberately unsettled. *Refuse* spends a session's setup and returns nothing but a clear reason; *warn* lets a P100 run start and probably die anyway at the first kernel launch, having burned the session. **Assumed meanwhile: refuse.**
2. **What does "the total of the accounts is used" mean when one account is unhealthy?** Assumed: the guarantee is over **healthy** accounts, and any account left out is named with its reason. The stricter reading — refuse the whole distribution unless all five are healthy — trades throughput for uniformity. Which is the requirement?
3. **What is the unit of consent?** Assumed: per **launch**, never persisted, because any stored switch reproduces today's defect with extra steps. That means a scripted or unattended campaign of thirty shards carries consent thirty times. Is a per-campaign consent, carried by one invocation that then submits many, acceptable instead?
4. **Is the dual-architecture torch build in this batch, or after a rehearsal settles the unknown?** It costs minutes on every one of thirty shards. Assumed: the **declaration + comparison** lands now (it is cheap and stops the silent death immediately) and the torch build is decided once a rehearsal has answered whether pushing to an existing kernel preserves the UI-chosen accelerator.

**Assumptions standing in if the round is skipped:** refuse on mismatch; the guarantee covers healthy accounts with named exclusions; consent is per-launch and never persisted; declaration + comparison now, torch build after a rehearsal.

## Recorded, not proposed

**Finding 10 is a handoff, not a repair.** `search_ceilings` (`implementations/Domain_Adaptation`, `harness.py:835-840`) builds `centred` and `pooled` keyed by the **current** `CEILING_GRID`, then iterates cells read back from the **record**, which may have been written under a different grid:

```python
835: centred: dict[float, list[float]] = {c: [] for c in grid}
840:     centred[ceiling].append(value - middle)   # KeyError when ceiling ∉ grid
```

Any recorded cell whose ceiling has left the grid raises a bare `KeyError` with no explanation. **Changing the grid is an ordinary thing for a researcher to do.** This is target code in a separate repository, read-only from this forge. It is handed to the user with its line and its trigger. **It must not acquire tasks, and nothing here proposes touching it.**
