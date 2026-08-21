# Proposal: the-flow-names-what-it-needs

Change: `the-flow-names-what-it-needs` · Skill: `proposal-implementation` · Store: engram (MCP down — written to scratchpad)

## Intent

Seven defects in `proposal-implementation` share one shape: **a capability exists, and no doctrine on the path that reaches it names it.** A status is computed and reported and appears in no contract (`coupling`, `smokeReady`, job staleness). A remedy is named and its command is never given (`reconcile`). A directory is argued for at length and no step creates it (`tools/`). A declaration field is asserted to be "asked by this flow" and the flow has no such step (`revision`, `premises`). A reader is written, documented, and has no producer (`shardsDisagree`). Each was found by hand, one at a time.

That repetition — instances eight through fourteen of the same shape in this repository — is the finding. Seven hand-written patches would leave the eighth instance to be found by hand too. The durable answer is the one the predecessor change already used: **agreement tests that derive one list from code and hold it to a parseable table in the doctrine.** Two such tests (a status roster, a command roster) cover four of the seven findings and every future instance in those two dimensions. A third, narrower one covers F1. F2 and F7 are different classes and are argued separately below.

## Scope

### In scope — files touched, by finding

| Finding | Files |
|---|---|
| F7 leak | `scripts/implementation_cli.py` (`:2725`, `:3365`, `:4039`), `SKILL.md` (`:1230-1242`), `tests/test_proposal_implementation.py` (guard class `:4620-4770`) |
| F1 ask | `SKILL.md` (Flow A step 8 `:499`; declaration section `:913-926`), tests |
| F5 `coupling` | `SKILL.md` (Output Contract `:1751-1764`), `references/usage.md` (§Reading `verify`), tests |
| F3 `smokeReady`/staleness | `SKILL.md` (probe output roster; Decision Gates `:389-412`), `references/usage.md`, tests |
| F6 `reconcile` | `SKILL.md` (`:1035-1044`; Decision Gates), `references/usage.md`, tests |
| #8 `generate-job` + seam | `SKILL.md` (`:370-388`, Flow B/Conversion routing), `references/usage.md` (new section), tests |
| F2 shard refusal | `scripts/implementation_cli.py` (`cmd_verify`, parser, `distribution_state` early branches), `SKILL.md` (`:1560-1567`), `references/usage.md`, tests |

No `assets/kit/` change is required: `src_benchmark/__init__.py:21` already asserts the ask correctly and becomes true once Flow A has the step.

### Out of scope
- **F4** — `kaggle-accounts`' undocumented `materialize`. Different skill, carries its own credential decision.
- **`remote-execution/SKILL.md:398-400`** — stale prose claiming probe's `remoteExecution` fact "does not exist yet".
- Any edit under `implementations/` (C2). Repairs that appear to need one are reported as findings.
- Making the forge *merge* shard results (average/pool). See F2.
- `implementation_cli.py:3365`'s `p.name in (contract.get("record") or ...)` — `in` against a string is a substring test, not equality. Noted while reading; a separate defect, reported not fixed.

## Capabilities

**New:** none. **Modified:** none at spec level — this change adds doctrine, three agreement tests, one optional `verify` flag, and removes one leaked default.

## Approach, per finding

### F7 — the leak, and the shape of the guard (commit 1)

The exploration found one word. Reading disk found **five sites of one leak**, and it is wider than a filename:

| Site | Leak | Target origin |
|---|---|---|
| `implementation_cli.py:4039` | `contract.get("record") or "latent.json"` | `MIL_CREDA_Benchmark/__init__.py:142` |
| `implementation_cli.py:3365` | same default, second copy | same |
| `implementation_cli.py:2725` | worked example in a comment | same |
| `SKILL.md:1240` | `"record": "latent.json"` | same |
| `SKILL.md:1236` | `"figures": [..., "latent.grid"]` | `latent.py`, `latent.latent_grid` (`:113-115`) |
| `SKILL.md:1232` | `"harness.render_panorama"` | `MIL_CREDA_Benchmark/harness.py` — **named explicitly by C1** |

**Chosen:** drop both defaults to `None` (`_is_reporting_cell` at `:3990` already handles `None` — it returns `False` for the record shape, so this is behaviour-preserving except where a target relied on the guess, which is the leak); rewrite the worked example at `SKILL.md:1230-1242` with invented generic names consistent with the file's own (`tables.render`, `figures.curves`), retiring `latent.*` and `harness.*`.

**Rejected:** fixing only `:4039`. It leaves four sites and teaches the target's vocabulary in the one example every reader copies.

**The harder question — is a fixed word list the right shape?** No. `test_the_whole_forge_borrows_no_repository_s_vocabulary` (`tests:4698-4720`) scans seven hardcoded words, so it only ever catches leaks somebody already found; it did not catch `latent` and would not catch the next one. **Chosen:** keep the fixed list as a floor and add a *derived* guard — enumerate the vocabulary of every target under `implementations/` (directory names, `src/*` package names, module basenames), subtract a declared **forge lexicon** of words the forge legitimately owns, and fail on the remainder. This inverts the maintenance burden: adding to the lexicon is a deliberate reviewed act; today's list requires a leak to have been discovered first.

Honest cost, stated rather than hidden: (i) the target's module names overlap the forge's own legitimate vocabulary (`figures`, `tables`, `config`, `wiring`, `verdict`, `report_digest`, `schedules`), so the lexicon needs ~10–15 entries; (ii) it reads `implementations/` (read-only — C2 holds) and must skip with an explicit message in a clone with no target, so it is silent exactly when nobody has a target; (iii) it is still not complete — nothing is. It changes the failure mode from *catches what was already found* to *catches any word this repository's own targets own*, and it would have caught all five sites above.

### F1 — where the ask lives in Flow A (commit 2)

**Chosen: step 8, behind step 7's existing gate. No new gate, no renumbering.**

Three things make this forced rather than preferred:

1. **`premises` is already spoken at that gate and simply never written down.** `SKILL.md:604-646` requires the draft that wins authorization to state the experiment as a protocol — what is predicted, over which statistical unit, by which metric, in which direction. That is `premises`, field for field. The repair is not a new question; it is recording an answer the gate already produced.
2. **The doctrine already governs exactly this act.** `SKILL.md:717` — "Append to it at every gate, before writing any code the gate authorized" — is `AGREEMENTS.md`'s rule, and it is the same act: a gate produced a settlement, and the settlement goes to a file before code. Writing the declaration at step 8 is that rule applied to the second file that records a gate.
3. **`revision` is proposed, not assumed.** Flow A step 1 already holds `latest`. Taking it silently is the fabrication `:913-915` forbids ("not a value `materialize.py` or any other tool fabricates"), so step 8 proposes `latest` and confirms it inside the approval already being asked for.

**Rejected — step 5b, right after scaffolding.** At step 5 the name is unconfirmed (step 6) and no protocol conversation has happened, so `premises` would be invented — precisely what `:913` forbids.
**Rejected — step 16 or Flow B.** Step 16 continues into Flow B step 3, where `probe` immediately answers `declare-first`. A first pass that has not written them dead-ends at the rung whose remedy is the missing step: today's bug, moved one step later.
**Rejected — inserting a new numbered step.** Steps 5, 9, 15 and 16 are cross-referenced (`:475`, `:508`, `:510`, `:554`, `:846`); renumbering is a large diff whose only product is risk.

Live-target evidence the gap is real and costly: its `premises` spells the field `unit` where the kit and `SKILL.md` both say `statisticalUnit` — the drift you get when the question is never asked.

### F5 — `coupling` (commit 3), F3 — `smokeReady`/staleness (commit 4)

Both are "reported, documented nowhere". `verify` returns **thirteen** top-level status keys (`structure`, `priorWork`, `agreements`, `prose`, `search`, `distribution`, `remoteExecution`, `coupling`, `fidelity`, `lfs`, `report`, `audit`, `validation`); the Output Contract at `:1755-1756` names **eleven**.

**Chosen:** convert the Output Contract's inline parenthesised list into a **table**, one row per status with what it reports and whether it gates, and add `coupling` and `lfs`. Add a second table for `probe`'s reported facts, covering `coupling`, `remoteExecution.jobs`, `remoteExecution.smokeReady` and `staleness`. Both tables are then locked by the status-roster agreement test (below). For F3, also add the two Decision Gates rows the ladder cannot express: `smokeReady: false` and `staleness: drift` are reported beside a `benchmark` answer and must be read before a campaign is offered.

**Rejected:** making the ladder branch on `smokeReady`/staleness. `coupling`'s own contract says it is "reported and never gating" (`:2140`, `:4006`), and `probe` is read-only; converting a reported fact into a fifth ladder branch changes what `nextStep` means and would suppress a legitimate `benchmark` answer on a target that never uses remote execution at all. The defect is that a human reading the `benchmark` section is told nothing about a fact printed two lines above it — that is a doctrine gap, and doctrine is where it is repaired.

### F6 — `reconcile` (commit 5), #8 — the seam (commit 6)

`SKILL.md:1035-1044` names the fix for `drift`/`unreliable` as "reconciling the ledger by hand" and never gives the command. None of `remote_cli`'s eight subcommands (`submit`, `status`, `poll`, `fetch`, `reconcile`, `generate-job`, `smoke record`, `readiness`) appears in this skill's `SKILL.md` or `usage.md` — including `poll`, which `poll-first` tells the reader to wait for without naming.

**Chosen: name and route, do not duplicate.** `remote-execution/SKILL.md:17-120` already documents every flag well. This skill adds a table mapping each subcommand to the reported state that routes a reader to it, plus `usage.md` invocations for `reconcile`, `poll` and `generate-job` only, and points at `remote-execution` for the rest.

**Rejected:** duplicating flag documentation here. Two copies of a flag list is the drift `remote_execution_jobs_state:4884-4890` already refuses to create in code; doing it in prose is the same mistake.

**The third leg — `tools/`.** `SKILL.md:370-388` argues at length that `tools/` must exist, and no step creates one. Disk gives the answer: `generate-job` writes to `<target>/tools/<service>/<job-name>/` (`remote_cli.py:1307`), and `submit`'s `guard_entrypoint()` admits exactly that shape. So **`tools/` needs no scaffold step and no kit template — it needs the sentence saying which command places it.** That is the whole repair, and it is why the missing template the exploration expected turns out not to be missing.

### F2 — the fork, decided (commit 7)

**I disagree with the orchestrator's reading of (b), on evidence read off disk. I propose (a), narrowed to the refusal.**

The class of this change is "a capability exists and nothing reaches it". The default remedy of that class is to join the halves; amputation is right only when joining would force the forge to learn something it must not know. Here it would not:

- **`disagreements()` reads only stamps.** `shard_io.py:65` — `entry["stamp"].get(field)`. It never touches `runs.jsonl`, so it never touches the grouping of records into result cells, which is the part the module's own docstring (`:6-16`) says stayed in the target deliberately.
- **`identicalAcrossShards` is already in the declaration schema the forge owns** (`SKILL.md:909`, `DISTRIBUTION_DECLARATION`). The forge does not learn what a field means; it echoes a name the repository declared.
- **`read_shards()` assumes only the ambient `shard.json` + `runs.jsonl` contract** (`:2-20`), which the forge already declares.
- **The doctrine sentence promises a refusal, not a merge.** "Shards agree on what they said had to agree, or the merge refuses. Not averages — refuses" (`:1560-1563`). A refusal is generic. An average is not.

**Chosen:** `verify` grows one optional `--shards <dir>`. When given, it calls `shard_io.read_shards`, computes `disagreements(shards, declared identicalAcrossShards)`, and passes `{"disagreements": …, "shardsArrived": […]}` as `distribution_state`'s existing `merged`. This gives `read_shards` and `disagreements` their first production caller, makes `shardsDisagree`/`shardsArrived` reachable, and honours `:1565-1567` ("scale is recomputed from what came back") with a number read from disk. Doctrine is split explicitly: **the forge refuses; the target averages.**

**Rejected — (b), removal.** It deletes a rule the doctrine argues for over eight lines, moves an invariant into every future target's hands because the current one happens to have built its own, and leaves the forge shipping `shard_io.py` with two of three functions dead. "Something must say who calls `disagreements`" is the objection (b) has to answer; under (a) the forge itself calls it, and the objection dissolves.

**The falsifier that would flip this to (b):** if the fields named by `identicalAcrossShards` lived in `runs.jsonl` rows rather than in the `shard.json` stamp, the refusal would require grouping and would belong to the target. I checked: `shard_io.py:65` reads the stamp. It does not.

**Small correctness item folded in:** `distribution_state`'s `none`/`absent`/`undeclared` branches (`:621-632`) return `shardsDisagree` but not `shardsArrived`, so the key vanishes for some targets. Made symmetric in the same commit.

## Does one structural repair prevent recurrence?

Not one. **Three, and together they cover the class rather than the instances.**

| Agreement test | Derives from code | Holds to | Covers | Catches in future |
|---|---|---|---|---|
| **Status roster** | AST: top-level string keys of `cmd_verify`'s and `cmd_probe`'s `return {…}` literals, minus `command`/`target`/`name` | the two new Output Contract tables | F5, F3 | every status added without doctrine |
| **Command roster** | AST: `add_parser("…")` literals in `remote_cli._build_parser`, incl. `smoke` subparsers | the subcommand→state table | F6, #8 | every subcommand this flow can route to |
| **Declaration blocks** | AST: the six top-level keys of `assets/kit/src_benchmark/__init__.py`'s `__benchmark__` | the block→"filled by" table, whose Flow-A cells must resolve to a step that exists and names the block | F1 | a block whose named filling step is deleted or renumbered |

Both `cmd_verify` and `cmd_probe` return single dict literals with constant keys, so the derivation is mechanical, not heuristic.

**Not covered, and why.** F2 is a documented reader with no producer — no roster catches it, because the field *is* documented; the defect is that nothing computes it. Its honest lock is the cross-join the doctrine itself demands at `:313-317`: run the real producer, assert the real reader sees it — never two fixtures written by the same hand. F7 is a vocabulary defect, locked by the derived guard.

**A fourth test considered and rejected:** "every fact a command reports must be branched on or documented." It would be false by construction — `coupling` is explicitly "reported and never gating" (`:4006`), and `probe` reports several facts it must never gate on. The roster test demands *documentation*, not consumption. That is the right bar and the reason the roster is stated as a table of statuses rather than a table of branches.

## Commit decomposition

One per finding, on `main`, each independently landable, each well under the 400-line per-PR default.

| # | Subject | Est. lines |
|---|---|---|
| 1 | `fix(proposal-implementation): a target's own filename was the default the forge guessed when a report declared none` | ~180 |
| 2 | `fix(proposal-implementation): three places say the flow asks for the declaration's revision and premises and no step does` | ~110 |
| 3 | `docs(proposal-implementation): the output contract names eleven statuses and verify reports thirteen` | ~100 |
| 4 | `docs(proposal-implementation): probe reports a job that never rehearsed and answers benchmark anyway` | ~130 |
| 5 | `docs(proposal-implementation): the fix for a drifted ledger is named in a docstring and nowhere a reader looks` | ~70 |
| 6 | `docs(proposal-implementation): eight remote-execution subcommands and the tools directory that holds them are named nowhere in this flow` | ~220 |
| 7 | `fix(proposal-implementation): the shard-disagreement refusal has a reader, a doctrine and no producer` | ~150 |

**Why F7 leads rather than F1**, which is the higher-priority finding: commits 2–7 add roughly 500 lines of new doctrine prose and worked examples, which is exactly the surface a leak enters through. The widened guard belongs in front of them, not behind. F1 is fully independent and follows immediately.

## Test strategy

Behaviour-first, RED confirmed before GREEN, `python3 -m unittest tests.test_proposal_implementation` (402 green now) and `python3 -m unittest discover -s tests` (743 green). Not `pytest`; `-k` misses newly added classes.

**Doctrine-only repairs are locked by parsing a table, never prose.** Prose cannot be held to code. So each doctrine repair here *includes converting its target into a parseable table* — the Output Contract's inline status list becomes a table, probe's facts become a table, the subcommand→state mapping is a table, the six blocks become a table — and the test parses that table and compares it to an AST-derived list from the code. Where a cell must name a Flow A step (F1), the test additionally requires that step to exist and to name the block; the residual prose-matching there is stated as a limitation rather than claimed away.

**Every lock that passes on first run is proven reachable-red by inversion**, per the established local idiom: break the guarded fact (drop a roster row, rename a returned key, plant a leak in a scratch tree), watch it fire, restore **by inverse patch, never `git checkout --`**. Inversion has three times disproved a lock's own stated claim in this repository, so it is part of the method. The existing guard already models this — `test_a_leak_into_a_script_is_caught` (`tests:4740-4766`) builds a tree, plants one leak, and asserts exactly which file was caught; the derived guard gets the same treatment.

**F2 gets the cross-join, not a fixture.** `tests:2384-2389` and `:2410-2413` exercise `merged` with hand-written dicts, which is the failure `:313-317` names. The new test writes a real shard directory to disk, runs `verify --shards` end to end, and asserts `distribution.shardsDisagree` and `shardsArrived` from the command's own output. Throwaway targets go under `implementations/_<name>` (`verify` needs `git init`; `plan` also needs a commit, or `DIRTY_WORKTREE`) and are deleted.

## Risks and non-goals

| Risk | Likelihood | Mitigation |
|---|---|---|
| The derived guard fires on legitimate forge vocabulary (`figures`, `tables`, `config`, `wiring`) | High — certain on first run | The forge lexicon is the deliverable, written once and reviewed; the fixed list stays as a floor |
| The derived guard couples the forge suite to `implementations/` contents | Medium | Read-only (C2 holds); skips with an explicit message when no target exists; stated as a known blind spot, not hidden |
| The status roster becomes noise if `cmd_verify` grows nested-key churn | Low | Scoped to top-level keys only, which are the statuses the contract is about |
| The command roster couples this skill to `remote-execution`'s parser | Medium | That coupling is the point — this flow routes readers to those commands; a new subcommand should force a doctrine decision |
| F2 (a) is the wrong call and the merge really does belong to the target | Low | Falsifier is stated and was checked on disk (`shard_io.py:65` reads stamps); flipping to (b) costs commit 7 only, which lands last |
| C1 breach reintroduced by the ~500 new lines of prose | Medium | Commit 1 lands the widened guard first, deliberately |

**Non-goals:** F4; the stale `remote-execution/SKILL.md:398-400`; any edit under `implementations/`; a forge-side average/pool; new gates in Flow A; renumbering Flow A's steps.

**Review-budget forecast (1200 lines):** estimated **~780 authored changed lines** (range 650–950), largest commit ~220. **Risk: Low-to-Medium.** The two items that could push past 950 are the derived vocabulary guard (commit 1) and the F2 cross-join fixture (commit 7); both are the last things to cut and the first things to slice if the count runs hot.

## Rollback

Seven independent commits on `main`, no branches or PRs. Each is `git revert`-able alone. Only two touch runtime behaviour: commit 1 (two defaults `→ None`, behaviour-preserving except where a target relied on the guess) and commit 7 (a new optional flag; omitted, `verify` behaves exactly as today). Commits 2–6 are doctrine and tests only.

## Success criteria

- [ ] `verify`'s and `probe`'s reported statuses are each enumerated in a doctrine table, and a test derives them from the code and fails on any divergence.
- [ ] Every `remote_cli` subcommand this flow can route a reader to is named in this skill's doctrine, held by a test derived from that parser.
- [ ] Flow A has a step that writes `revision` and `premises`, and the three places asserting the ask resolve to it.
- [ ] `latent` and `harness` appear nowhere in the forge, and a leak using a word nobody has listed is caught by a test.
- [ ] `distribution.shardsDisagree` is produced by a real command over a real shard directory, not by a fixture.
- [ ] Both suites green: 402 and 743 plus the new tests.

## Proposal question round

Interactive mode; I cannot address the user directly from this phase. Four questions, and the assumptions standing in for them meanwhile.

1. **F2 is the one real fork and I decided against the framing I was given.** The proposal argues (a-narrow) — the forge grows a *refusal*, never a merge — because `disagreements()` reads only shard stamps and so needs none of the grouping vocabulary that belongs to the target. Does that hold, or is there a reason outside the code to move the whole responsibility down to targets?
2. **Does the derived vocabulary guard belong in this change, or is it its own?** It is the only item here that changes how the forge polices itself rather than what it says, it will fire on legitimate words on first run, and it makes the suite read `implementations/`. Cutting it shrinks commit 1 by roughly 90 lines and leaves F7 repaired but the guard still reactive.
3. **`SKILL.md:1230-1242`'s worked example is substantially copied from the live target** — `latent.grid`, `latent.json`, `harness.render_panorama`, and a translated `SEEDS`/`FULL_SEEDS` selection. Replacing it with invented names is more churn than F7 as scoped. Confirm that the whole example is in scope, or hold it back to just the two code defaults.
4. **Should probe's `smokeReady`/staleness ever gate?** The proposal keeps them reported-only and repairs the doctrine, on the grounds that a target with no remote execution must still reach `benchmark`. If the intent is that a stale job should actually block a campaign offer, that is a ladder change and a different, larger commit.

**Assumptions standing in, if the round is skipped:** F2 → (a-narrow); the derived guard is in scope in commit 1; the full worked example is rewritten; the ladder is not touched; `tools/` gets no kit template because `generate-job` already places it.
