# Verification Report: the-path-that-reaches-a-run

**Mode**: full artifacts (proposal, spec, design, tasks all present). **Verdict**: PASS WITH WARNINGS.

## Method

Per the orchestrator's explicit instruction, this verification does not accept "a test exists" as proof. Every requirement below was driven with real inputs against the actual shipped code (direct execution, real subprocesses, real local git remotes), not by reading tests and matching them to requirements. Nothing was launched to Kaggle or any real service; every git operation ran against throwaway local repositories under `implementations/_verify_*` (removed after use), and the full suite was additionally re-run under a custom outbound-socket guard.

## Baseline

`python3 -m unittest discover -s tests` → **1269 tests, OK** (matches the claimed baseline; measured myself on a quiet tree).

Re-ran the full suite under an outbound-socket guard installed via `PYTHONPATH` pointing at a scratch `sitecustomize.py` (never written into site-packages). Result: **1269 tests, OK, 0 blocked outbound-connect attempts** logged — confirms the entire suite makes zero real network calls.

## Completeness (tasks.md)

All 8 phases marked `[x]` complete, including the Phase 4 correction and Phase 7 (three misdirecting refusals). Confirmed via `apply-progress` artifact and `git log` (9 commits, all present on `main`).

## Driven and CONFIRMED WORKING

1. **The deadlock (target-environment-provisioning).** Built a throwaway target repo declaring its own `requirements.txt`. `implementation_cli.py env` correctly produced a `nextCommand` installing both the forge's `requirements-dev.txt` AND the target's own `requirements.txt`. Separately drove `introspect()` directly: with a `.venv` present but the target's runtime dependency never installed, it returned `{"status": "unavailable", "detail": "ModuleNotFoundError: ..."}`, not `"ok"` — confirming report.live no longer answers `ok` on a venv that cannot import the declared entry module. Positive control: fixing the import moved the failure further down the required-import chain, confirming the entry-module check genuinely runs first.

2. **The consent gate (launch-authorization).** Drove `remote_cli.cmd_submit()` directly with a real `FakeAdapter` and a real job folder generated via `JOBFOLDER.generate_job()` against a real local git origin (no network). Confirmed:
   - Rehearsal (`smoke=True`) with no `--consent` refuses (`ConsentError`); `adapter.submit()` never called.
   - Campaign (`--unit`) with no `--consent` refuses; adapter never called.
   - Plain single send with no `--consent` refuses (the exact original complaint's invocation); adapter never called.
   - A token minted for entrypoint A does **not** authorize entrypoint B (refused); the same token **does** authorize its own entrypoint (positive control).
   - A token minted for 4 units does **not** authorize a 6-unit campaign (refused); the same token **does** authorize its own 4-unit campaign, correctly spreading across 4 accounts (positive control).

3. **The spread (remote-execution).** Drove `packer.distribute()` directly: 5 fake accounts, one raising `WorkerUnauthorized`, 7 units → 4 healthy accounts received the round-robin spread, the 5th was named in `skipped` with reason `"unauthorized (...)"`. Reproduced the same result inside a real `cmd_submit()` campaign call.

4. **The accelerator (accelerator-contract).** Drove `runner_bootstrap.bootstrap()` end-to-end (real local git clone, no network) with a fake `torch`:
   - Uncovered capability (`sm_86` vs installed `[sm_60, sm_75]`) → `SystemExit` raised, and `bootstrap.json` already existed on disk with the exact evidence (device, torch build, arch list, capability) **before** the exception fired.
   - Genuinely covered dual-arch declaration (`sm_60`+`sm_75` both installed and declared, capability `sm_75`) → no refusal (positive control) — confirms the comparison is real, not a permanent refusal.
   - `generate_job()` called with **no** accelerator flags at all (from-zero case) still wrote the service's registered default accelerator into `run-config.json`, unprompted.

5. **The three refusals (remote-execution).**
   - (A) Simulated a git-fetch timeout via a controlled `subprocess.run` replacement: the refusal explicitly disclaims "is not, by itself, evidence the commit is unpublished," using its own 240s (`PIN_PUBLISHED_TIMEOUT_SECONDS`) budget, and never shares wording with the confirmed-refusal branch (driven separately: that branch says "push it ... and pin the commit the remote actually received," and does NOT contain the timeout disclaimer).
   - (B) Drove `guard_entrypoint()` with an actual job-folder directory: refusal reads "a file was expected, not a directory ... the notebook is at .../runner.ipynb — pass that path to --entrypoint instead." Two adjacent regression-lock cases (a bare directory shaped like a job folder but missing both files; a shallow `.ipynb` file missing the job-name component) still get the old generic "does not stay under ..." message — confirmed the narrow case does not swallow the broad ones.
   - (C) Drove `product_for()` across every subcommand: only `submit` (and `generate-job`, not applicable) name `--product` in an unresolved-product refusal; `status`, `distribute`, `fetch`, `reconcile`, and an unknown/`None` command never do — cross-checked against `_subcommand_option_strings()` reading the live parser directly (independent confirmation, not just the refusal text).

6. **Roster derivation (target-environment-provisioning).**
   - Guiding table (`proposal-implementation/SKILL.md`): independently re-ran `subcommand_surface()`/`required_flags()` against `remote_cli.py`'s live `_build_parser()` and hand-compared every row myself — all 9 subcommands and every required-flag column match exactly, including `readiness`'s `--job-dir`/`--worker` (correctly NOT `--target`/`--entrypoint`). Genuinely derived and locked, not hand-drifted.
   - Subcommand roster: same derivation confirms the full 9-command roster matches the table exactly.
   - Accelerator default (`adapters/kaggle.py`'s `sm_60`/`sm_75`): legitimately hand-written (external service knowledge, not derivable from any local parser). The only existing "lock" is a same-module tautological test (asserts the registered provider returns the module's own constant) — there is no independent ground truth this is checked against. Not a defect (the code already honestly frames this as "observed, not a law, expected to be revised"), but it is hand-written where the other two rosters are derived — noted as a SUGGESTION.

7. **Harness Name Resolution.** Drove `resolve_harness_status()` directly for both the "present under a custom declared name" case and the "declaredMissing" (file removed after declaration) case — both correctly distinguished, fixing the exact defect described (a target that followed doctrine but named its harness module differently used to report `harness: null`).

8. **search_ceilings scope.** Confirmed zero occurrences of `search_ceilings` in spec.md, proposal.md, tasks.md, or either test file beyond the explicit "recorded handoff, no task/requirement" notes. Correctly never acquired a requirement, scenario, task, or edit.

9. **Scope discipline.** `git show --stat` on all 9 commits touches only `.claude/skills/proposal-implementation/`, `.claude/skills/remote-execution/`, their two test files, and this change's own 4 openspec artifacts. Never `openspec/config.yaml`, never `implementations/Domain_Adaptation`, never another skill.

10. **No duplicate names.** AST-based, per-class check (not a flat scan) across both test files: 69 + 84 top-level classes, zero duplicate class names, zero classes with an intra-class duplicate method name.

## Confirmed by close code reading only (not independently driven with a live fixture)

- **Probe and Harness Agree on Run Readiness**: `cmd_probe()`'s `next_step` computation is structurally ordered so `"search-first"` (triggered by `search["recordFound"] is False` or `scaleSatisfied is not True`) is evaluated as an `elif` strictly before `next_step` can remain `"benchmark"` — this is enforced by Python control flow itself, not by a value that could silently diverge, but I did not build a live search-record fixture to exercise it end to end. Lower risk given the structural guarantee, but flagged for completeness.

## Claimed but honestly recorded as unproven (correct — not a defect)

`proposal.md` itself states: "whether pushing to an existing kernel preserves the accelerator chosen in Kaggle's own UI... Only a rehearsal settles that; it is not guessed here." This matches the instruction's framing exactly and is not silently assumed anywhere in the shipped code.

## Discrepancy in the orchestrator-supplied "measured facts" (WARNING)

The instruction stated as a measured fact: "there are zero occurrences of `MIL_CREDA`, `CREDA`, `Domain_Adaptation`, `harness.py` or `MNIST` in any skill." This is **false** for the bare token `CREDA`: it occurs 30+ times in `.claude/skills/proposal-deliberation/engine/proposal-workspace.ts`, an unrelated, pre-existing skill never touched by any of this batch's 9 commits (confirmed via the scope check above), referencing a Spanish-named math-proposal base file (`matematica_propuesta_CREDA.md`) that has nothing to do with MIL-CREDA/domain-adaptation. `MIL_CREDA` (with the underscore, the actual forbidden compound term) does have zero hits everywhere, confirmed. Reporting this as a factual correction to the supplied premise, not as a defect introduced by this change — the file is out of scope and the match appears to be an unrelated false cognate rather than target leakage.

## Issues

- **WARNING**: the "zero occurrences ... in any skill" premise, as literally stated, does not hold for the bare token `CREDA` (see above). No action needed on this change; flagging so the premise itself isn't propagated uncorrected.
- **SUGGESTION**: the Kaggle default-accelerator constants are hand-written service knowledge with only a tautological same-module lock; no independent ground truth ties them to a real, currently-observed hardware pool. Consistent with the code's own honest framing; not a defect.

## Verdict

**PASS WITH WARNINGS.** Every spec requirement I drove with real execution behaved exactly as specified, with both positive and negative controls where feasible. No CRITICAL findings against the shipped code itself.
