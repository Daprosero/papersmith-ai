```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:f29d79028381426e997d9f4e04e117d7ba0a1c4e84300508c9dea1ca8c9a7366
verdict: fail
blockers: 1
critical_findings: 1
requirements: 13/14
scenarios: 25/26
test_command: python3 -m unittest tests.test_proposal_implementation
test_exit_code: 0
test_output_hash: sha256:2907315d545026e2b5aceae1b2aaca7c10b8ba40705039c841f4b11f045f0f29
build_command: python3 -m unittest discover -s tests
build_exit_code: 0
build_output_hash: sha256:53a7f94d8016be151a5a42741035f98bb617173750cbd3bbf5f3b4c3773bef1e
```

# Verification Report — the-flow-names-what-it-needs

Change: `the-flow-names-what-it-needs` · Domain: `proposal-implementation` ·
Mode: full artifact set (spec + design + tasks + apply record) ·
Store: engram MCP disconnected — this file is the report ·
Repository: `/Users/diego/Proyectos/papersmith-ai`, branch `main` at `21a0064`,
worktree clean, `ahead 7` of `origin/main`, nothing pushed.

**Verdict: FAIL on one finding, and the finding is narrow.** Every one of the
fourteen spec requirements is satisfied by code on disk, and I proved the
load-bearing ones by running them myself rather than by reading the apply
record. One spec scenario has no standing covering test, and a mutation shows
that gap is real rather than bookkeeping: rule B — the derived guard that is
the entire subject of Group 1's ADDED requirement — can be silently disabled
with all 448 tests still green.

---

## 1. Evidence I measured myself

| Command | Exit | Result |
|---|---|---|
| `python3 -m unittest tests.test_proposal_implementation` | 0 | **448 tests, OK** (run four times; identical) |
| `python3 -m unittest discover -s tests` | 0 | **789 tests, OK** (run three times; identical) |

Both counts match the apply record and the launch brief. The design's baseline
figures (402 / 743) are the pre-change numbers, so the change added 46 and 46
tests respectively.

`implementations/` was proven untouched at byte level rather than by
`git status`. **`implementations/*` is gitignored** (`.gitignore:33`), so the
apply record's Phase 8.1 check — "`git status --porcelain implementations/` is
empty" — is empty by construction and proves nothing. I took a 51,557-entry
manifest of every path under `implementations/` (mode, size, `mtime_ns`, and a
sha256 for every file under 2 MB), ran the full 789-test suite, and re-took it:
**identical, zero differences.** The cross-cutting scenario is genuinely proven.

---

## 2. Constraint checks

### C1 — no target vocabulary in the forge: HOLDS, proven by injection

The live derivation, run independently: one target on disk
(`Domain_Adaptation`), 34 derived words, a lexicon of 26, a rule-B denylist of
8 (`bags`, `conditional`, `creda`, `global`, `latent`, `mil`, `renyi`,
`schedules`), **zero leaks across all 13 guarded surfaces**, and zero rule-A
violations across the 21 dotted names rule A sees.

I also ran a second, independent scan the guard does not perform: all 28
**unsplit** package and module basenames of the live target against every forge
file. It produced 14 files of hits, and every hit is either a `FORGE_LEXICON`
word or a forge-owned filename the target copied *from* the forge
(`report_digest`, `shard_io`). No hit is target-specific vocabulary. C1 holds.

**Four injections, each proving one rule catches what the others cannot:**

| # | Planted | Expected catcher | Result |
|---|---|---|---|
| 1 | `CONTRACT = {"renderers": ["harness.render_panorama"]}` appended to `SKILL.md` | rule A only (`harness` is in the lexicon, so rule B is structurally blind) | **Rule A fired**, naming `('SKILL.md', 1947, 'harness.render_panorama')`. Rule B stayed silent, exactly as designed. 1 failure. |
| 2 | the prose word `renyi` appended to `SKILL.md` | rule B only (not a dotted name, not on the floor) | **Rule B fired**: `{'SKILL.md': ['renyi']} != {}` — names file and word. Rules A and C silent. 1 failure. |
| 3 | the prose word `kaggle` appended to `SKILL.md` | rule C only (on the floor, derived from no target) | **Rule C fired**: `'kaggle' is some target's vocabulary, not the forge's`. 1 failure. |
| 4 | `latent` and `creda` added to `FORGE_LEXICON` | the disjointness meta-test | **Fired**: `Lists differ: ['creda', 'latent'] != []`. A floor word cannot be silenced by a lexicon entry. |

Every injection was restored by inverse patch and byte-verified (`cmp` plus
`shasum -a 256 -c`), and `git diff --quiet` was clean after each.

**Rule B goes silent, not green, on a target-free checkout.** Confirmed
independently of the suite by calling `derived_denylist()` against an empty
directory: `SkipTest: no repository under implementations/, so rule B has no
vocabulary to derive and this is silence rather than a pass`.

### C2 — nothing under `implementations/` edited: HOLDS

`git diff --name-only 7b89dd6..21a0064` touches exactly four files:
`SKILL.md`, `references/usage.md`, `scripts/implementation_cli.py`,
`tests/test_proposal_implementation.py`. No path under `implementations/`
appears in any of the seven diffs. The live target's `premises` misspelling was
left alone, correctly, as evidence for F1.

### C3 — RED before GREEN: four inversions reproduced

I did not take the apply record's transcripts on trust. Four were re-run
against the live tree:

| Task | Inversion | Result |
|---|---|---|
| **4.5** | added a `smokeReady` rung to `cmd_probe`'s chain after `poll-first` | **Fired: 2 failures** — `test_a_job_that_never_rehearsed_still_reaches_the_benchmark_offer` and `test_a_job_pinned_to_a_commit_that_is_not_in_the_history_still_offers_the_run`, both `'smoke-first' != 'benchmark'`. |
| 1.9 | `creda`/`latent` into `FORGE_LEXICON` | Fired (injection 4 above). |
| 2.6 | `premises` cell changed to `Flow A step 99` | **Fired**: `test_every_flow_a_cell_names_a_step_that_mentions_its_block`. |
| 6.6 | `poll` row dropped from the subcommand table | **Fired: 2 failures** — the roster (`['poll'] != []`) and the rung-names-the-command test. |

All four restored by inverse patch and byte-verified.

**Task 4.5 in particular, because the brief flagged it.** The apply agent's
first fixture was genuinely unfalsifiable — it answered `report-first`, and the
rung is guarded by `next_step in ("benchmark", "piloted")`, so no inversion
could have fired. The replacement fixture is sound, and I proved it by running
`probe` on it myself outside the suite:

```
BEFORE job folder: nextStep= benchmark   report= ok   smokeReady= {}   jobs= []
AFTER  job folder: nextStep= benchmark   smokeReady= {'job': False}
```

It reaches `nextStep: benchmark` with `report: ok` **before any job folder
exists**, which is exactly the pole the earlier fixture lacked, and the
inversion fires against it. **F3's position is a defended decision, not an
undefended omission.**

### C4 — seven commits, correct style, nothing pushed: HOLDS

Seven commits `5602818 → 21a0064`, each scoped to one finding, all with
`type(proposal-implementation):` subjects. A scan of every subject and body for
`co-authored-by|generated with|claude|anthropic|ai-assisted` returns nothing.
The reflog shows all seven committed directly on `main`; no branch was created
for this change. `ahead 7`, nothing pushed, no PR.

---

## 3. Spec compliance matrix

| Group | Requirement | Status | Proof |
|---|---|---|---|
| 1 | Forge MUST NOT guess a record name | **PASS** | `UndeclaredRecordEndToEndTests`; plus my own run: `verify` on a target declaring no `record` exits 0 with empty stderr and `report.status: drift`. Inverting `:3382` to `or None` reproduces `TypeError: argument of type 'NoneType' is not iterable` — the design's D1 correction proven, not accepted. Declared-record behaviour proven identical by diffing the pre-change CLI (`7b89dd6`) against the current one on the same target: **zero differing keys**. |
| 1 | A derived guard MUST catch unlisted target vocabulary | **PASS with one untested scenario** | Injections 1–4 above. See CRITICAL-1. |
| 2 | Flow A MUST record `revision` and `premises` | **PASS** | `SKILL.md:511-524`: step 8, behind step 7's existing gate, writes both into `src/<Package>_Benchmark/__init__.py` before authorized code, `revision` proposed as step 1's `latest` and confirmed in the same approval, `premises` carried across as `prediction`/`statisticalUnit`/`metric`/`direction`. No renumbering. `DeclarationBlockRosterTests` (4 tests). |
| 2 | A declaration-block roster MUST hold blocks to filling steps | **PASS** | 6 kit blocks, 6 rows, every Flow-A cell resolves to an existing step that mentions its block. Inversion 2.6 reproduced. Residual prose matching is stated in the class docstring, not claimed away. |
| 3 | Output Contract MUST enumerate every `verify` status | **PASS** | Derived independently: `cmd_verify` returns 16 keys, minus 3 identity keys = **13**; the table has exactly **13** rows and the sets are equal. `coupling` row reads `**Never** — a static fact, reported so somebody can decide about it`; `lfs` present. |
| 3 | A status roster MUST hold each command's statuses to its table | **PASS** | `VerifyStatusRosterTests` asserts both directions; `test_the_roster_names_a_renamed_key` proves the message names each side against a scratch copy. |
| 4 | `probe`'s facts documented and readable, never gating | **PASS** | `cmd_probe` 17 keys − 4 identity = **13**, table has 13 rows; job sub-table `jobs`/`services`/`smokeReady` matches `remote_execution_jobs_state` exactly; two Decision Gates rows. Ladder unchanged, proven by inversion 4.5. |
| 5 | A reported drift MUST name the command that repairs it | **PASS** | `remote_cli reconcile` at `SKILL.md:1085` (the `poll-first` drift paragraph — "reconciling the ledger by hand" is gone), two Decision Gates rows at `:418-419`, and a worked invocation at `usage.md:596`. Three ends, all held by tests. |
| 6 | Every remote-execution subcommand MUST be named | **PASS** | Derived independently from `remote_cli._build_parser`: **8 leaves** — `fetch`, `generate-job`, `poll`, `readiness`, `reconcile`, `smoke record`, `status`, `submit`. Table has 8 rows. `usage.md` works `reconcile`, `poll`, `generate-job` only and shows a proper subset of each one's flags. |
| 6 | A command roster MUST hold the parser to the table | **PASS** | Inversion 6.6 reproduced. |
| 7 | `verify` MUST be able to refuse a disagreeing shard set | **PASS** | My own run outside the suite: three shards, two disagreeing fields → `shardsDisagree: ["datasetSize","epochs"]`, `shardsArrived: ["a","b","c"]`, `status: incomplete`. Deleting shard `b` and re-running gives `shardsArrived: ["a","c"]` and `shardsDisagree: ["datasetSize"]` — **the numbers move with the disk**. No averaged or pooled value anywhere. A malformed `shard.json` propagates `json.decoder.JSONDecodeError` and exits 1. `--shards` is accepted by `verify` alone (`probe`, `admit`, `handoff`, `apply` all answer `unrecognized arguments: --shards`). |
| 7 | `shardsArrived` MUST be reported symmetrically | **PASS** | Proven end-to-end against the pre-change CLI on a target declaring no distribution: before → no `shardsArrived`; after → `shardsArrived: []`, everything else byte-equal. Purely additive. `returned_keys(CLI, "distribution_state")` now agrees across all branches on 11 keys including `note` and `shardsArrived`. |
| CC | Doctrine locked to code MUST be locked through a table | **PASS** | Five parseable tables, each derived-against. Four inversions reproduced. |
| CC | Forge stays general, `implementations/` untouched | **PASS** | C1 and C2 above, plus the 51,557-entry manifest. |

**Scenario coverage: 25 of 26.** The one uncovered scenario is Group 1's
"An unlisted target word planted in a forge file is caught".

---

## 4. Issues

### CRITICAL

**CRITICAL-1 — rule B has no standing reachability test, and the gap is real, not clerical.**

Spec Group 1 requires the scenario: *"GIVEN a scratch tree whose target owns a
word absent from the forge lexicon and from the fixed list, WHEN that word is
planted in one forge file and the guard runs, THEN the guard SHALL fail AND the
message SHALL name that exact file and word."*

No standing test does this. Rule A has one
(`test_rule_a_names_the_file_a_planted_example_leak_is_in`) and rule C has one
(`test_a_leak_into_a_script_is_caught`), but both plant `latent`/`ramp`, which
are on the fixed floor. Rule B — the new, derived rule that Group 1's whole
ADDED requirement is about — is only ever asserted against the live tree, where
it is green because nothing is wrong.

I proved this is a live defect rather than a technicality, by mutation:

```python
# tests/test_proposal_implementation.py, ForgeVocabularyDerivedGuardTests.leaks
hits = [word for word in denylist
        if re.search(rf"\bZZZ{re.escape(word)}ZZZ\b", text)]   # can never match
```

→ **`Ran 448 tests … OK`.** Rule B can be completely disabled and the entire
suite stays green. The contrast is decisive: the same neutering applied to
rule A produces 2 failures, and emptying `FORGE_VOCABULARY_FLOOR` produces 1.

This is the change's own doctrine turned on the change: *"A guard that passes
because nothing is wrong today has not been shown to do anything."* The apply
record's task 1.1 RED (27 words across 13 files with an empty lexicon) proved
rule B reachable **at the moment it was written**; nothing preserves that proof.

Remedy: one test, in the shape the other two already use — a scratch forge
tree, a scratch `implementations/` root owning a word in neither the lexicon
nor the floor, that word planted in one file, asserting the exact
`{file: [word]}` returned. Roughly fifteen lines, no design decision.

### WARNING

**WARNING-1 — the review-workload budget was exceeded, and the apply record's budget statement is scoped to one launch.**

Measured `additions + deletions` per commit: **466**, 164, 202, 357, 174, 268,
354 — **1,985 authored lines total**. The tasks artifact forecast ~790 (range
660–960) against a session budget of 1,200; the actual is **65% over budget**.
Commit 1 alone is **466 lines, over the 400-line per-unit default**, against a
design estimate of ~190. The apply record's closing line ("1145 … against a
session budget of 1200") counts only launch 2's four commits; launch 1's three
add another 832. No `size:exception` was recorded. This is a process finding
only — nothing about the work is unsound, and the seven-commit slicing means no
single review unit except commit 1 breaches the default.

**WARNING-2 — `premises` field names are held by prose alone.**

Spec Group 2 requires "`premises` field names SHALL match the kit's declared
names." They do — I checked: `SKILL.md:523` names `prediction`,
`statisticalUnit`, `metric`, `direction`, and the kit declares exactly those at
`assets/kit/src_benchmark/__init__.py:27-30`. But no test derives them from the
kit, so the two copies can drift silently. Mitigating: the kit's names live in a
**comment** (the live value is `"premises": {}`), so an AST-derived lock is not
available without restructuring the kit — which is why this is a WARNING and
not a second CRITICAL.

**WARNING-3 — design deviations, all sound, all leaving the design one row stale.**

Judged individually, as the brief asked:

- **Commit 5 repairing a finding the design never carried** (`usage.md` works no
  `probe`, `name` or `compose` invocation): **sound, not overreach.** The lock is
  a roster over `dict_literal_keys(CLI, "COMMANDS")`, and a roster is all-or-nothing
  by construction — `name` and `compose` had to be worked or the roster could not
  exist. Working only `probe` would have meant three assertions instead of a lock,
  which is the weaker artifact this whole change exists to replace. The `probe`
  invocation is handed to the **real process** against a nonexistent target, so
  argparse validates every flag.
- **F6 folded into commit 6 instead of getting commit 5**: sound. The subcommand
  roster makes `reconcile` a *required* row, which is a stronger lock than the
  presence test the design planned for it. The design's Commit Decomposition table
  is one row out of date and should be reconciled at archive.
- **`cmd_probe`'s status roster absorbed into commit 4** by orchestrator decision:
  sound; design D7 already anticipated "two new Output Contract tables".
- **`distribution_state`'s repair wider than D9 predicted**: correct and honest.
  The early branches also carried `note`, which the declared branch did not, so
  `shardsArrived` alone would have left the helper red. Full symmetry was the
  actual fix, and it is widening in both directions — I confirmed no consumer
  changes: on a declared-distribution target the pre-change and post-change
  outputs are identical, and on an undeclared one the only difference is the new
  key.
- **8 subcommand leaves, not the design's 9**: the apply record is right and the
  design was wrong. `smoke` is a group whose subcommand is `required=True`
  (`remote_cli.py:1350`), and I confirmed by invocation that `remote_cli smoke`
  alone is refused (`error: the following arguments are required: smoke_command`).
  It names no runnable invocation, so documenting it would document something
  nobody can type. The design counted the group parser.

**WARNING-4 — the Windows branch of the F3 fixture is written and never exercised.**

`ProbeReportedFactsRosterTests.build_target` symlinks `sys.executable` into
`.venv/bin/python`, with an `os.name == "nt"` branch writing
`Scripts/python.exe`. On this platform that branch never runs. The symlink is
also not a built environment — it works because the live half of the report
check only needs an interpreter that can import off `src/`, which the docstring
states plainly. Both are honest; neither is proven on Windows.

### SUGGESTION

**SUGGESTION-1 — the lexicon's remaining escape hatch, confirmed by injection.**
I planted `renyi` in `SKILL.md` *and* added a plausible four-word reason for it
to `FORGE_LEXICON`: **suite green, 12/12 OK**. The disjointness meta-test only
defends words already on the floor, so a leak in a word nobody has found yet can
still be silenced by one lexicon entry. This is precisely the design's own
**High**-likelihood risk ("the forge lexicon grows until rule B constrains
nothing"), named at D3 and in the risk table. Reported as confirmed, not as new.

**SUGGESTION-2 — rule B splits compound names, so a compound of two lexicon words is invisible.**
`report_digest` and `shard_io` appear in the forge and rule B cannot see them as
units (it splits on `_` and drops tokens under three characters). Both are
harmless — they are the forge's own filenames the target adopted, so the
direction is forge→target — but a future target module named from two lexicon
words would pass rule B entirely.

**SUGGESTION-3 — columns two and three of every roster are prose, as documented.**
The brief flagged `smoke record` and `readiness` specifically. I checked both by
reading code rather than accepting the table: `cmd_probe` really does call
`rcli.cmd_readiness(job_dir=…, worker=…)` at `implementation_cli.py:4986` to
compute `smokeReady`, and `cmd_smoke_record` is what writes the verdict
`readiness` reads. **Both claims are true.** They are simply not *asserted*, and
every roster class says so in its own docstring.

---

## 5. Task completion

All 31 boxes across Phases 0–8 are `[x]` in the tasks artifact, and each one I
sampled is matched by code on disk. Phase 8.1's stated check is the one that
does not hold up — `git status` cannot see an ignored directory — but the claim
it was making is true, and I proved it a different way (Section 1).

## 6. Final verdict

**FAIL** — one CRITICAL, four WARNING, three SUGGESTION.

The failure is a missing fifteen-line test, not a broken deliverable. Every
requirement is satisfied and every load-bearing behaviour was reproduced at
runtime during this verification. What is missing is the standing proof that the
change's central new guard still works tomorrow — and that proof is exactly what
this change spent seven commits arguing nobody should go without.
