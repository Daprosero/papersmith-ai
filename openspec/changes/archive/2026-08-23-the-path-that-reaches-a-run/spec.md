# Spec: the-path-that-reaches-a-run

No `openspec/specs/` baseline exists yet — each domain below is a full requirement set, not a delta. Finding 10 (`search_ceilings` `KeyError`, target repo) is a recorded handoff; no requirement covers it.

## Domain: accelerator-contract (New)

| Requirement | Rule (MUST) | Scenario |
|---|---|---|
| Accelerator Declaration | `run-config.json` declares `accelerator: {kind, architectures[]}`; the forge names the two fields and never their values. An architecture list, not a device name: a name answers *is this the card I named* and breaks on `Tesla T4` against `Tesla T4 x2` in both directions, while an architecture answers *can this build run here*, which is the question the P100 failed | G: job prepared — W: `run-config.json` generated — T: architectures comparable to the arriving capability |
| Pre-Training Comparison and Refusal | The arriving capability must appear in the installed arch list, and the declared architectures must be covered by that same list. The refusal is written AFTER `bootstrap.json`, never before: a refusal whose evidence was never written is unreadable no matter how early it fires | G: the arriving capability is outside the installed arch list — W: the check runs in cell 0 — T: refuses in seconds with the evidence already on disk, and training never starts |
| Dual-Architecture Torch Coverage | Torch build covers `sm_60` and `sm_75`; comparison pass guarantees a runnable kernel; per-shard install minutes (x30 shards) is an accepted cost | G: shard provisioned — W: comparison passes either architecture — T: matching kernel available |

## Domain: launch-authorization (New)

| Requirement | Rule (MUST) | Scenario |
|---|---|---|
| Per-Campaign Consent Gate | `submit` refuses without explicit invocation-carried consent; one approval covers every shard that invocation submits, never one per shard | G: consent granted for a thirty-shard campaign invocation — W: it runs — T: all thirty shards submit, no further prompts |
| Consent Is Never Persisted | Consent is never a config key, env var, or any switch outliving the process | G: prior invocation ran with consent — W: new invocation runs without consent — T: refuses exactly as if none had consented |

## Domain: remote-execution (Modified)

| Requirement | Rule (MUST) | Scenario |
|---|---|---|
| Full Healthy-Account Spread Consumption (Previously: first-healthy-account only; spread computed, never consumed) | `submit` consumes the distribution across every healthy account; excluded accounts are named with reason | G: four of five accounts healthy — W: `submit` runs a campaign — T: four receive the spread, fifth named with reason |
| `pin-published` Owns Its Time Budget | `pin-published` evaluates against its own budget, separate from git transfer time | G: pushed commit transfers 12.4 MiB on a slow link — W: `pin-published` evaluates within its own budget — T: does not report "not pushed" from transfer time alone |
| `--entrypoint` Names the Shape It Wanted | Given a folder, `submit --entrypoint` reports a file was expected, never redirecting to regenerate a sound job | G: valid job folder passed to `--entrypoint` — W: `submit` evaluates it — T: reports a file was expected, not a job to regenerate |
| `status` Refuses Only on Its Own Declared Flags | `status` never refuses for missing `--product` unless `status` itself declares that flag | G: `status` invocation lacks `--product` — W: `status`'s parser inspected — T: does not refuse for a flag `status` never declares |

## Domain: target-environment-provisioning (New)

| Requirement | Rule (MUST) | Scenario |
|---|---|---|
| Target Manifest Provisioning | `env`'s `nextCommand` installs the target's own declared manifests (`ROOT_KEEP` names), beside forge's `requirements-dev.txt`; forge never hardcodes a target package name | G: `env` ran for a target declaring its own `requirements.txt` — W: prescribed interpreter runs the target's campaign — T: no `ModuleNotFoundError` for a manifest-declared dependency |
| Liveness Requires Executed Evidence | `report.live`/`probe` report live, and `nextStep` advances past an environment, only on evidence something executed; a `.venv` alone is insufficient | G: `.venv` exists with nothing executed inside it — W: `report.live` evaluates it — T: does not report `ok`, `nextStep` does not advance |
| Harness Name Resolution from Target Declaration | `probe` takes the harness module name from the target's own declaration, distinguishing absent from present-under-a-different-name, without a second hardcoded name | G: one target has no harness file, another has it under the declared name — W: `probe` looks for each — T: reports absent for the first, present for the second |
| Probe and Harness Agree on Run Readiness | `probe`'s `nextStep` and the harness's own preflight refusal evaluate readiness from the same fact | G: ceilings searched below required scale — W: `probe` computes `nextStep` — T: does not report `nextStep: benchmark` while harness would refuse |
| Guiding Table Completeness | Table lists each row's applicable flags and includes a row for a stale-pinned job folder; both derive from `remote_cli`'s parser, locked by a parser-derived test | G: job folder pinned to a stale commit — W: table consulted and compared to parser — T: row exists naming right subcommand; `readiness` lists `--job-dir`/`--worker`, not `--target`/`--entrypoint` |
