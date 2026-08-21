# Tasks: the-flow-names-what-it-needs

Change: `the-flow-names-what-it-needs` · Skill: `proposal-implementation` · Store: engram (MCP down — written to scratchpad).
Source of truth: the DESIGN. Where the proposal disagrees, the design wins (three corrections carried below).

## Test commands

- Skill suite (every commit ends here): `python3 -m unittest tests.test_proposal_implementation` — 402 green now.
- Full discovery: `python3 -m unittest discover -s tests` — 743 green now.
- One class: `python3 -m unittest tests.test_proposal_implementation.VerifyStatusRosterTests` — never `-k`.
- `fd`/`rg` need `--no-ignore` to see `implementations/`. `rg -r` is `--replace`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~790 authored (range 660–960); largest unit ~220 |
| Session review budget | 1200 lines — headroom on every unit |
| 400-line budget risk | Medium |
| Chained PRs recommended | No — C4 mandates seven commits on `main`, no branches, no PRs |
| Suggested split | Commit 1 → 2 → 3 → 4 → 5 → 6 → 7 (each its own review unit) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Medium

Justification: the slice plan is not an open team decision — C4 fixes it at one commit per finding on `main`. Every unit is ≤220 authored lines, under both the 400 default and the session's 1200 budget. Nothing is left to ask.

### Suggested Work Units

| Unit | Goal | Focused test command | Runtime harness | Rollback boundary |
|------|------|----------------------|-----------------|-------------------|
| 1 | F7 leak repaired at six sites + derived guard (rules A/B/C + 2 meta-tests) | `python3 -m unittest tests.test_proposal_implementation.ForgeVocabularyDerivedGuardTests` | `verify` on a throwaway target declaring no `record` — proves `p.name in ""` does not raise | `cli:2723-2726/3365/4039/5114`, `SKILL.md:1230-1242`, one new test class |
| 2 | F1: Flow A step 8 records `revision` + `premises`; block roster | `…DeclarationBlockRosterTests` | N/A — Flow A is prose executed by an agent; no runtime path exists (design D7, weakest lock) | `SKILL.md:499`, `:913-926`, one new test class |
| 3 | F5: Output Contract → 13-row table; `returned_keys` helper + status roster | `…VerifyStatusRosterTests` | N/A — doctrine held to AST-derived keys | `SKILL.md:1751-1764`, `usage.md`, helper + class |
| 4 | F3: `remoteExecution` fact sub-table, 2 Decision Gates rows, behavioural partner | `…ProbeReportedFactsRosterTests` | `probe` on a throwaway target with `smokeReady: {job: False}` → must still answer `benchmark` | `SKILL.md` probe/gates rows, `usage.md`, one class |
| 5 | F6: `remote_cli reconcile` named at all three ends | `…ReconcileRemedyNamedTests` | N/A — presence check over doctrine text | `SKILL.md:1035-1044`, gates rows, `usage.md` |
| 6 | #8: subcommand→state table, `tools/` producer sentence, command roster | `…RemoteExecutionCommandRosterTests` | N/A — parser parsed by AST, never invoked | `SKILL.md:370-388` + table, `usage.md` section, one class |
| 7 | F2: `verify --shards` + `shardsArrived` symmetry + cross-join | `…ShardRefusalCrossJoinTests` | `implementation_cli.py verify --target implementations/_shardbox --name … --shards <dir>` over a real shard directory | `cli` loader/`cmd_verify`/`main`/`distribution_state`, `SKILL.md:1560-1567`, `usage.md`, one class |

## Phase 0: Settle the lexicon (blocking, exploratory, bounded)

- [x] 0.1 Write rule B's derivation as a throwaway script under the scratchpad: enumerate `implementations/*` directory names, `src/*` package names and module basenames; search the four guarded surfaces with `\bword\b`, case-insensitive. Read-only (C2).
- [x] 0.2 Run it once and capture the full hit list verbatim (expected to include `harness`, `wiring`, `tables`, `figures`, `verdict`, `models`, `objective`, `shard(s)`, `digest`, `training`, `pipeline`, `kernel(s)`, `confidence`, `artifacts`, `attention`, `adaptation`, `rungs`, `latent`).
- [x] 0.3 Triage every hit exactly once into (a) `FORGE_LEXICON` with a one-line reason, (b) a leak repaired by task 1.5, or (c) the rule-C floor. **Stopping rule**: re-run once after triage; zero remaining ends Phase 0. A word appearing only after an edit is a new leak, not lexicon discovery — it goes to (b), never to (a). Never a third derivation round; if one seems needed, stop and report.
- [x] 0.4 Delete the throwaway script. Nothing under `implementations/` was written.

## Phase 1: Commit 1 — F7 leak + derived guard (~190 lines)

- [x] 1.1 RED — add `FORGE_LEXICON: dict[str, str]` (empty) and rule B to a new `ForgeVocabularyDerivedGuardTests`; run the class; confirm it fires and names the Phase-0 words.
- [x] 1.2 RED — add rule A: every dotted name inside a worked `report`/declaration example must have its module part in `EXAMPLE_MODULE_NAMES = frozenset({"tables", "figures"})`. Run; confirm it names `SKILL.md:1232` (`harness.render_panorama`), `:1236` (`latent.grid`), `:1240` (`"latent.json"`), `cli:2723`, `:2725`.
- [x] 1.3 RED — add the "no target present" case: a clone with no `implementations/` repository skips with an explicit message; assert skip, not pass-by-silence.
- [x] 1.4 GREEN — fill `FORGE_LEXICON` from task 0.3, one reviewed reason per entry; add rule C: the existing floor at `tests:4716-4717` gains `latent`.
- [x] 1.5 GREEN — repair the six leak sites: rewrite `SKILL.md:1230-1242`'s worked example with invented names (`tables.render`, `figures.curves`) including the leaked **attribute** names by hand; de-leak `cli:2723-2726` and the `:5114` comment (name the shape generically — "quantities the report renders that never sit on a shard").
- [x] 1.6 GREEN — `cli:3365`: `contract.get("record") or ""`. **Not `None`** — `p.name in None` raises `TypeError` on every target declaring no record. Leave the `in` operator byte-identical (D8: the substring defect is a non-goal).
- [x] 1.7 GREEN — `cli:4039`: plain `contract.get("record")`; `_is_reporting_cell` is `str | None` and returns `False` on falsy input (`:3983`, `:3990`).
- [x] 1.8 GREEN — add the two meta-tests: every lexicon reason is non-empty and ≥4 words; `FORGE_LEXICON.keys()` and the rule-C floor are **disjoint**.
- [x] 1.9 INVERSION (disjointness passes on first run) — add `creda` to `FORGE_LEXICON`, run the class, watch it fire, remove **by inverse patch, never `git checkout --`**, confirm `git diff --quiet`.
- [x] 1.10 INVERSION (rule A) — build a scratch tree with one planted `latent.grid` in the manner of `test_a_leak_into_a_script_is_caught` (`tests:4740-4766`); assert exactly which file was named.
- [x] 1.11 Runtime harness — run `verify` on a throwaway target under `implementations/_norecord` (needs `git init`) whose report declares no `record`; confirm no `TypeError`. Delete in `addCleanup`.
- [x] 1.12 Both suites green → commit: `fix(proposal-implementation): a target's own filename was the default the forge guessed when a report declared none`.

## Phase 2: Commit 2 — F1, the ask (~110 lines)

- [x] 2.1 RED — `DeclarationBlockRosterTests`: derive the six top-level `__benchmark__` keys from `assets/kit/src_benchmark/__init__.py` with `ast`; parse a `| Block | Filled by | When |` table in `SKILL.md`. Run; confirm it fails because the table is absent.
- [x] 2.2 RED — assert Flow A step 8 names both `revision` and `premises`. Run; confirm it fails.
- [x] 2.3 GREEN — `SKILL.md:499`, step 8: present the declaration's `revision` and `premises` beside the map, and write them into `src/<Package>_Benchmark/__init__.py` on approval. `revision` is **proposed** as step 1's `latest` and confirmed inside the approval (`:913-915` forbids fabrication). `premises` field names come from the gate's protocol draft (`:604-646`). No new gate, no renumbering.
- [x] 2.4 GREEN — add the block table to the declaration section (`:913-926`), every Flow-A cell naming a step number.
- [x] 2.5 GREEN — extend the roster: each Flow-A cell must name a step that **exists** and whose text mentions the block. Record the residual prose matching as a stated limitation in the test docstring.
- [x] 2.6 INVERSION (2.5 passes once written) — change one cell to `step 99`, run, watch it fire, restore by inverse patch, `git diff --quiet`.
- [x] 2.7 Both suites green → commit: `fix(proposal-implementation): three places say the flow asks for the declaration's revision and premises and no step does`.

## Phase 3: Commit 3 — F5, `verify` statuses (~110 lines) · unblocks 4 and 7

- [x] 3.1 GREEN(helper) — module-level `returned_keys(source, function)`: `ast`-parse, find the `FunctionDef`, collect string keys of **every** `Return` whose value is a `Dict`, and assert all such returns carry the same key set.
- [x] 3.2 RED — `VerifyStatusRosterTests`: `returned_keys(cli, "cmd_verify")` (13 keys, `:5161`) minus identity keys, compared to a `| Status | What it reports | Gates? |` table. Run; confirm it fails naming `coupling` and `lfs`.
- [x] 3.3 GREEN — `SKILL.md:1751-1764`: inline parenthesised list → a 13-row table; `coupling` documented as reported and **never gating** (`cli:2140`, `:4006`); `lfs` added.
- [x] 3.4 GREEN — `references/usage.md` "Reading `verify`" gains `coupling` and `lfs`.
- [x] 3.5 GREEN — delete any surviving hardcoded eleven-status list in the suite; the roster is the single source.
- [x] 3.6 Reachability — RED by construction, no inversion needed. Post-green, rename a returned key in a scratch copy of the parsed source and confirm the failure message names it.
- [x] 3.7 Both suites green → commit: `docs(proposal-implementation): the output contract names eleven statuses and verify reports thirteen`.

## Phase 4: Commit 4 — F3, `smokeReady`/staleness (~130 lines) · after 3

- [x] 4.1 RED — `ProbeReportedFactsRosterTests`: `returned_keys(cli, "remote_execution_jobs_state")` (`jobs`, `services`, `smokeReady`; both returns must agree) held to a sub-table under `probe`'s `remoteExecution` row. Confirm it fails — the sub-table is absent.
- [x] 4.2 RED — assert Decision Gates carries rows for `smokeReady: false` and `staleness: drift` beside a `benchmark` answer. Confirm both fail.
- [x] 4.3 GREEN — add `probe`'s reported-facts table (`coupling`, jobs, `smokeReady`, `staleness`), the two Decision Gates rows, and the `usage.md` reading guidance.
- [x] 4.4 GREEN(behavioural partner) — build a throwaway target under `implementations/_smokebox` whose `smokeReady` is `{job: False}`; assert `probe` still answers `benchmark`. `addCleanup` deletes it.
- [x] 4.5 INVERSION — **the one that matters most.** 4.4 passes on first run, so add a `smokeReady` branch to the ladder at `cli:2090-2106`, run 4.4, watch it fire, remove **by inverse patch**, confirm `git diff --quiet`. This is what makes D5 a decision rather than an omission.
- [x] 4.6 Record in the test docstring why gating is impossible: `remote_execution_jobs_state` returns `{"jobs": [], "services": 0, "smokeReady": {}}` when the remote-execution CLI is absent (`:4900-4901`) — byte-identical to a target that has it and has no jobs. Include the falsifier (a per-job link to the campaign being offered).
- [x] 4.7 Both suites green → commit: `docs(proposal-implementation): probe reports a job that never rehearsed and answers benchmark anyway`.

## Phase 5: Commit 5 — F6, the named remedy (~70 lines)

- [x] 5.1 RED — `ReconcileRemedyNamedTests`: `remote_cli reconcile` must appear in the `SKILL.md:1035-1044` drift/unreliable section, in the Decision Gates table, and as an invocation in `usage.md`. Confirm it fails at all three ends.
- [x] 5.2 GREEN — name the subcommand at `:1035-1044` (replacing "reconciling the ledger by hand"), add two Decision Gates rows, add the `usage.md` invocation.
- [x] 5.3 INVERSION — remove the `usage.md` invocation, watch the presence test fire, restore by inverse patch, `git diff --quiet`. Note in the docstring that this is the weakest lock in the set; its partner is commit 6's roster, which makes `reconcile` a **required** row.
- [x] 5.4 Both suites green → commit: `docs(proposal-implementation): the fix for a drifted ledger is named in a docstring and nowhere a reader looks`.

## Phase 6: Commit 6 — #8, the seam (~220 lines, largest unit)

- [x] 6.1 RED — `RemoteExecutionCommandRosterTests`: derive `add_parser("…")` literals from `remote_cli._build_parser`, including the nested `smoke record` → 9 entries; hold to a `| Subcommand | The reported state that routes here | Where the flags are documented |` table. Confirm 9 derived, 0 documented.
- [x] 6.2 RED — assert `SKILL.md:370-388` names `generate-job` and the path shape `tools/<service>/<job-name>/`. Confirm it fails.
- [x] 6.3 GREEN — add the subcommand→state table, one row per derived subcommand including `poll`.
- [x] 6.4 GREEN — add the `generate-job` sentence at `:370-388` (`remote_cli.py:1307` already writes that shape). No scaffold step, no kit template.
- [x] 6.5 GREEN — `usage.md` section: invocations for `reconcile`, `poll`, `generate-job` only, pointing at the `remote-execution` skill for flags. Add a test asserting no flag list is duplicated here.
- [x] 6.6 INVERSION — drop the `poll` row, run the roster, watch it fire, restore by inverse patch, `git diff --quiet`.
- [x] 6.7 Both suites green → commit: `docs(proposal-implementation): eight remote-execution subcommands and the tools directory that holds them are named nowhere in this flow`.

## Phase 7: Commit 7 — F2, the shard refusal (~160 lines) · after 3, lands last

- [x] 7.1 RED — add `distribution_state` to the roster helper's function list; the all-returns-agree assertion fails because the `none`/`absent`/`undeclared` branches (`:622`, `:628`) omit `shardsArrived`. RED by construction.
- [x] 7.2 GREEN — those three early returns gain `shardsArrived` (`[]`). Widening only: no consumer breaks on a key appearing.
- [x] 7.3 RED — `ShardRefusalCrossJoinTests`: write a **real** shard directory to disk under a throwaway target `implementations/_shardbox` (`git init`; `plan` also needs a commit or `DIRTY_WORKTREE`) and invoke `main(["verify", …, "--shards", dir])`. Confirm `argparse` exits 2 — the flag does not exist.
- [x] 7.4 GREEN — `cli`: add `REMOTE_EXECUTION_SHARD_IO_SCRIPT` + `_load_remote_execution_shard_io()`, path-importing `shard_io.py` **directly**, not via `remote_cli.SHARD_IO` (D6: that would drag `jobfolder`, `adapter`, `packer`, `credentials` into a read-only checker; `shard_io.py` defines no class, so the module-identity argument does not apply). Widen the `:38-52` import comment from two files to three.
- [x] 7.5 GREEN — `cmd_verify` builds `merged` inside the `--shards` branch only, reading the flag with `getattr(args, "shards", None)` so the ten hand-built `argparse.Namespace(...)` call sites need no edit; `main()` adds `--shards` to the `verify` subparser only.
- [x] 7.6 GREEN — assert from the command's own stdout: `distribution.shardsDisagree` reports the disagreement and `shardsArrived` lists the shards read; add the agreeing-shards case; add the flag-omitted case asserting output identical to today.
- [x] 7.7 GREEN — boundary tests: a `--shards` directory that does not exist yields `shardsArrived: []` and `shardsDisagree: []` (a legitimate answer per `SKILL.md:1565-1567`); a malformed `shard.json` propagates the `json.loads` error rather than being treated as absent.
- [x] 7.8 BEHAVIOURAL VARIATION (instead of inversion) — delete one shard directory and assert `shardsArrived` shrinks by one, proving the number is read from disk and not from a fixture (`SKILL.md:313-317`).
- [x] 7.9 GREEN — `SKILL.md:1560-1567` names `--shards` and states explicitly that **the forge refuses and the target averages**; `usage.md` gains the invocation.
- [x] 7.10 Both suites green → commit: `fix(proposal-implementation): the shard-disagreement refusal has a reader, a doctrine and no producer`.

## Phase 8: Closing checks (no commit of its own)

- [x] 8.1 Confirm every throwaway target under `implementations/_*` was deleted and `git status --porcelain implementations/` is clean — the cross-cutting spec scenario "the suite leaves targets untouched".
- [x] 8.2 Confirm no forge file names anything particular to a target: full skill suite green with rules A/B/C active.
- [x] 8.3 Confirm seven commits on `main`, no branches, no PRs, no `Co-Authored-By` in any subject or body.

## Independence check

Hard edges — **only two**: `3 → 4` and `3 → 7`, both because `returned_keys` is introduced in commit 3.

Everything else is policy, not dependency:
- **1 first** so the widened guard stands in front of ~500 new lines of doctrine prose (commits 2–7 are exactly the surface a leak enters through).
- **7 last** because it is the one decision carrying a stated falsifier, and reverting it costs only itself.

File regions are disjoint except two shared surfaces, neither a conflict when landed sequentially on `main`: the Decision Gates table (commits 4 and 5 each **append distinct rows**) and `tests/test_proposal_implementation.py` (each commit adds its **own class**). Every commit is `git revert`-able alone. Commits 2, 5 and 6 have no dependency in either direction and may land in any order relative to each other and to 1.

## Non-goals actively guarded during apply

- The `p.name in (...)` substring defect stays **reported, not fixed** — commit 1 changes the default only, operator byte-identical (D8).
- The readiness ladder is not touched except inside inversion 4.5, which is removed by inverse patch.
- No kit template or scaffold step for `tools/`; no duplicated remote-execution flag documentation; no forge-side average, pool or merge of shard results.
- No edit anywhere under `implementations/` — the live target's `premises` misspelling (`unit` for `statisticalUnit`) is **evidence for F1, not a repair**.

---

## Apply record (launch 2)

All 31 remaining boxes closed. One deviation from this file, directed by the
launch prompt and recorded rather than absorbed: commit 5 became the missing
worked `probe` invocation in `usage.md` (a finding the design never carried),
and F6 — `remote_cli reconcile` named at all three ends — landed inside commit
6, where the subcommand roster makes `reconcile` a required row anyway. Nothing
planned was dropped; one extra finding was repaired.

Commits, in order: `c754996`, `686e5e0`, `065df8e`, `21a0064`, all on `main`.
Final suites: 448 in `tests.test_proposal_implementation`, 789 across
`discover -s tests`. Both OK. Evidence, RED transcripts and inversion outcomes
are in `the-flow-names-what-it-needs-apply-progress.md`.

---

## Verify remediation (launch 3) — commit 8, test-only

Not a planned box. Opened by the verify report's single CRITICAL, which is
Group 1's one uncovered scenario, and closed the same way the plan closes
everything else.

- [x] R.1 Rule B's reachability held by a standing scratch-tree test that names
      the file and the word, in the shape rules A and C already use. RED by
      mutation of `leaks`, restored by inverse patch and byte-verified.

Commit: `e21f46c` on `main`. Suites: **449** in
`tests.test_proposal_implementation`, **790** across `discover -s tests`. Both
OK. Rule B's silence on a target-free clone was already locked and is untouched.
