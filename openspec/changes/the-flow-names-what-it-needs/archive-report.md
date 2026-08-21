# Archive Report — the-flow-names-what-it-needs

Change: `the-flow-names-what-it-needs` · Domain: `proposal-implementation` (the forge:
`.claude/skills/proposal-implementation/**` plus `tests/test_proposal_implementation.py`) ·
Closed: 2026-08-20 · Repository: `/Users/diego/Proyectos/papersmith-ai`.

Session preflight: execution mode `interactive`, artifact store `engram`, delivery strategy
`ask-on-risk`, review budget 1,200 lines.

**Artifact store note.** The Engram MCP server was disconnected for the whole cycle, so no
observation IDs exist for any artifact of this change. Every artifact is a file, and the
inventory below records paths in place of observation IDs. This is the one traceability gap
in the record, and it is stated rather than papered over: the artifacts live in a
session-scoped temporary directory and are not durable.

**Final state at close.** `main` at `e21f46c`, worktree clean, **8 commits ahead of
`origin/main`, nothing pushed**. Archiving here is bookkeeping, not delivery.

---

## 1. Gate: the verify verdict and why archive proceeded

The persisted `verify-report` records **`verdict: fail`** on one CRITICAL, written when `main`
stood at `21a0064`. That finding was closed afterwards by commit `e21f46c`. Per the
Final-State Authority hierarchy, the report is an intermediate snapshot; the state at close is
recorded below, and the snapshot's `fail` is history, not the current state.

Archive did not accept a prompt assertion that the CRITICAL was closed. It was reproduced
mechanically at archive time, by the same mutation the verifier used.

### CRITICAL-1 (per `verify-report`, at `21a0064`) — rule B had no standing reachability test

The derived vocabulary denylist (rule B) was only ever asserted against a clean checkout, where
it is green because nothing is wrong. The verifier proved the gap by mutation: neutering rule
B's matcher inside `leaks()` left the whole suite at `Ran 448 tests … OK`, while the same
treatment of rule A produced 2 failures and emptying the floor produced 1.

**Closed by `e21f46c`**, which adds a scratch-tree test planting `paddock` — a word on no fixed
list, derived from a *module basename* rather than a directory name — and asserts rule B names
both the file and the word.

### Reproduction performed at archive time

Baseline: `tests/test_proposal_implementation.py` sha256
`9fb3e7ee3fd8134817db3b061f501e4c1f2ca91218298ac9aec34a1bbbb4aaa9`, copied to a pristine
reference before any edit.

Mutation applied (`tests/test_proposal_implementation.py:8147`, rule B's matcher inside
`leaks`):

```diff
@@ -8144,7 +8144,7 @@
         for document in self.guarded_documents(root):
             text = self.scannable_text(document)
             hits = [word for word in denylist
-                    if re.search(rf"\b{re.escape(word)}\b", text)]
+                    if re.search(rf"\bZZZ{re.escape(word)}ZZZ\b", text)]
             if hits:
                 base = self.SKILL_ROOT if root is None else Path(root)
                 found[str(document.relative_to(base))] = hits
```

`python3 -m unittest tests.test_proposal_implementation`:

```
FAIL: test_rule_b_names_the_file_and_the_word_a_planted_leak_is_in (tests.test_proposal_implementation.ForgeVocabularyDerivedGuardTests)
Rule B, proven the way rules A and C already are.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/diego/Proyectos/papersmith-ai/tests/test_proposal_implementation.py", line 8276, in test_rule_b_names_the_file_and_the_word_a_planted_leak_is_in
    self.assertEqual(
AssertionError: {} != {'scripts/leaky.py': ['paddock']}
- {}
+ {'scripts/leaky.py': ['paddock']} : rule B has to name the file and the word, because a guard that reports only that something is wrong repairs nothing

----------------------------------------------------------------------
Ran 449 tests in 16.795s

FAILED (failures=1)
```

The mutation that was silent at `21a0064` now fires, on the new test alone. The finding is
genuinely closed.

Restore, by inverse patch — never `git checkout --`:

```
$ patch tests/test_proposal_implementation.py < inverse.patch
patching file 'tests/test_proposal_implementation.py'
$ cmp tests/test_proposal_implementation.py archive-gate/pristine.py
cmp: identical (silent)
$ shasum -a 256 tests/test_proposal_implementation.py archive-gate/pristine.py
9fb3e7ee3fd8134817db3b061f501e4c1f2ca91218298ac9aec34a1bbbb4aaa9  tests/test_proposal_implementation.py
9fb3e7ee3fd8134817db3b061f501e4c1f2ca91218298ac9aec34a1bbbb4aaa9  archive-gate/pristine.py
$ rg -c ZZZ tests/test_proposal_implementation.py     # exit 1, no residue
$ git diff --quiet && echo "git diff: clean"
git diff: clean
```

### Gates measured at archive time, on the restored tree

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_proposal_implementation` | **`Ran 449 tests` — OK** |
| `python3 -m unittest discover -s tests` | **`Ran 790 tests` — OK** |
| `git status --porcelain` | empty |
| `git status -sb` | `## main...origin/main [ahead 8]` |

These supersede the `verify-report`'s 448 / 789, which were measured before `e21f46c`.

### `implementations/` proven untouched — and the correction that made the proof necessary

The verifier's correction is adopted and carried forward: **`implementations/*` is gitignored**
(`.gitignore:33`), so `git status --porcelain implementations/` is empty *by construction* and
proves nothing about that directory. Task 8.1's stated check does not hold up; the claim it was
making is nevertheless true, proven a different way.

A content manifest of every path under `implementations/` (relative path, type, mode, size, and
a sha256 for every file under 2 MB; symlink targets hashed) was taken before the archive-time
suite runs and again after them:

| Manifest | Entries | sha256 |
|---|---|---|
| before | 51,558 | `192ccab41a5ef426e276fa75b89de1cbdec279daf952cf724df28e49107ebeb5` |
| after | 51,558 | `192ccab41a5ef426e276fa75b89de1cbdec279daf952cf724df28e49107ebeb5` |

`diff` between them produces **zero lines**. `eza -a implementations/` afterwards shows only
`.gitkeep` and `Domain_Adaptation` — every throwaway target created by the suite was cleaned
up. The digest also matches the one the last apply agent recorded, so the directory is
byte-identical to its state before the remediation launch.

### Native review gate

`gentle-ai review mode status` reports **receipt-driven development: off (decided by default)**,
global and clone-local both unset. No review was ever started for this candidate, so `reviewGate`
is structurally absent and archive proceeds under ordinary repository policy. No receipt,
transaction, ledger, or gate-context artifact exists to read, and none was manufactured.

### Task completion gate

The tasks artifact carries **62 checked boxes and zero unchecked implementation tasks**
(`rg '^\s*- \[ \]'` returns nothing). No stale-checkbox reconciliation was needed or performed.

---

## 2. The eight commits

Every commit is scoped to one finding, carries a `type(proposal-implementation):` subject, sits
directly on `main` with no branch and no PR, and is `git revert`-able alone. A scan of all eight
subjects and bodies for `co-authored-by|generated with|claude|anthropic|ai-assisted` returns
nothing. Line counts are `additions + deletions`, measured from `git show --numstat`.

| # | SHA | Subject | The seam it closed | Lines |
|---|---|---|---|---|
| 1 | `5602818` | `fix(…): a target's own filename was the default the forge guessed when a report declared none` | **F7** — the live target's `latent.json` was the forge's default at six sites, plus the vocabulary guard rebuilt as three rules (A: example allowlist, B: derived denylist, C: fixed floor) with two meta-tests | **466** |
| 2 | `866ea79` | `fix(…): three places say the flow asks for the declaration's revision and premises and no step does` | **F1** — Flow A step 8 now asks for and records `revision` and `premises`, behind step 7's existing gate; no new gate, no renumbering; plus the declaration-block roster | 164 |
| 3 | `27348f2` | `docs(…): the output contract names eleven statuses and verify reports thirteen` | **F5** — the Output Contract named eleven statuses while `verify` returns thirteen; inline list becomes a 13-row table, `coupling` and `lfs` added, held by the status roster | 202 |
| 4 | `c754996` | `docs(…): probe reports a job that never rehearsed and answers benchmark anyway` | **F3** — `probe`'s job facts documented and *deliberately never gating*, with two Decision Gates rows and a behavioural partner; plus the `cmd_probe` status roster | 357 |
| 5 | `686e5e0` | `docs(…): the reference promises a real invocation of every command and works none for probe` | `usage.md` opens by promising a real invocation of every command and worked none for `probe`, `name` or `compose`; locked by a roster over the dispatch table | 174 |
| 6 | `065df8e` | `docs(…): eight remote-execution subcommands and the tools directory that holds them are named nowhere in this flow` | **#8 + F6** — the subcommand→state table over all eight leaves, the `tools/<service>/<job-name>/` producer named (`generate-job`), and `remote_cli reconcile` named at all three ends | 268 |
| 7 | `21a0064` | `fix(…): the shard-disagreement refusal has a reader, a doctrine and no producer` | **F2** — `verify --shards` gives the shard-disagreement refusal its first production caller, plus `shardsArrived` symmetry across every distribution branch | 354 |
| 8 | `e21f46c` | `test(…): the derived guard could be switched off and all 448 tests stayed green` | rule B's reachability lock — the verify CRITICAL, closed | 59 |

Files touched across the whole range, and only these four:
`.claude/skills/proposal-implementation/SKILL.md`,
`.claude/skills/proposal-implementation/references/usage.md`,
`.claude/skills/proposal-implementation/scripts/implementation_cli.py`,
`tests/test_proposal_implementation.py`.

---

## 3. The root, and the structural answer

**The root defect class:** a capability exists in one place, and no doctrine on the path that
reaches it names it. A status is computed, reported, and appears in no contract. A remedy is
named and its command is never given. A directory is argued for at length and no step creates
it. A declaration field is asserted to be "asked by this flow" and the flow has no such step.
A reader is written, documented, and has no producer.

This change is **instances eight through fourteen of that shape in this repository**, following
the seven closed by `scaffold-materialization-seam` and `three-trees-one-scaffold`. That
repetition, not any individual finding, is what the change was built to answer.

**The structural answer was three rosters, not seven patches.** Each derives a list from code
and holds it to a parseable table in doctrine, so the *next* instance fails the suite instead of
waiting to be found by hand:

| Roster | Derived from | Held to |
|---|---|---|
| Status roster | AST-derived top-level return keys of `cmd_verify` (13 statuses) and `cmd_probe` (13 facts), minus identity keys | the two new Output Contract tables |
| Command roster | `add_parser` literals in `remote_cli._build_parser`, nested subparsers followed, leaves only (8) | the subcommand→state table |
| Declaration-block roster | the six top-level `__benchmark__` keys of the kit's `src_benchmark/__init__.py` | the block→"filled by" table, each Flow-A cell resolving to a step that exists and names the block |

Plus the rebuilt **three-rule vocabulary guard** (A allowlist / B derived denylist / C fixed
floor) with two meta-tests defending the lexicon, and a fourth roster over `usage.md`'s worked
invocations added in commit 5.

A fourth agreement test — "every fact a command reports must be branched on or documented" —
was considered and rejected as false by construction: `coupling` is explicitly reported and
never gating. The bar is documentation, not consumption.

---

## 4. Phase 0's measured result

The most compact fact the change produced. Of **34 words derived from the live target**
(`Domain_Adaptation`: directory name, `src/*` package names, module basenames, split and
lowercased):

- **one word — `latent` — was a real leak**, at six sites (`SKILL.md:1236`, `:1240`,
  `implementation_cli.py:2725`, `:3365`, `:4039`, `:5114`). It is the target's own module and
  its own record filename.
- **twenty-six were legitimate forge vocabulary** and became `FORGE_LEXICON`, each with a
  written reason a meta-test requires to be at least four words long, so admitting a word costs
  an argument rather than a comma.
- **seven hit nothing** (`bags`, `conditional`, `creda`, `global`, `mil`, `renyi`, `schedules`)
  and remained on the derived denylist.

Across roughly **1,145 further lines of doctrine and test prose** written in commits 2–7, rule B
stayed silent and **no lexicon entry was needed or added** — which is the outcome the guard
exists to produce, measured rather than assumed. Four leaked *attribute* names, which no word
rule can derive, were repaired by hand inside commit 1 and named as a residue rather than
claimed away.

---

## 5. The two methodological results — the change's real yield

### 5.1 Task 4.5 — a position is defended only if its inversion can fire

The F3 decision — `smokeReady` and job staleness are **reported, never gating** — is a position,
not an omission, and it is defended only because its inversion fires.

The apply agent's first fixture would have made that indefensible. It answered `report-first`,
and the rung under test is guarded by `next_step in ("benchmark", "piloted")`, so the inversion
**could never have failed**. That is a property of every pre-existing probe fixture in the
suite: none reaches `benchmark`, because `report_state` needs a live interpreter and a full
report contract.

The apply agent therefore had to build the suite's first probe fixture that genuinely reaches
`benchmark` — `config.py`, a `tables.py` whose `conclude` moves with its input, a record on
disk, a declared `components` block, and a `.venv/bin/python` symlinked to the running
interpreter. With it, the planted `smokeReady` branch produced two real failures. The verifier
reproduced the fixture and the inversion independently, and confirmed outside the suite that it
reaches `nextStep: benchmark` with `report: ok` before any job folder exists.

The lesson generalizes: **a fixture that cannot reach the branch under test makes its own
assertion unfalsifiable**, and no amount of green proves otherwise.

### 5.2 Mutation is the only honest reachability proof

A guard asserted only against a clean checkout is indistinguishable from a guard that is
switched off. That is precisely what found CRITICAL-1: rule B — the entire subject of the
change's central new requirement — could be completely disabled with all 448 tests still green.

It is the change's own doctrine turned on the change: *a guard that passes because nothing is
wrong today has not been shown to do anything.* Commit `e21f46c` now prevents it, and the same
mutation was re-run at archive time to confirm the lock holds.

---

## 6. Open items, recorded as not closed

None of these blocked archive. All are recorded so a future reader does not mistake them for
finished work.

1. **WARNING-1 — the review budget was exceeded, and no exception was ever accepted.**
   Measured `additions + deletions` per commit: 466, 164, 202, 357, 174, 268, 354 for the seven
   implementation commits = **1,985 authored lines**, against a **1,200-line session budget** —
   65% over. Including commit 8's 59 lines, the change totals **2,044** (2,015 additions, 29
   deletions). **Commit 1 alone is 466 lines, over the 400-line per-unit default.** The tasks
   artifact forecast ~790 (range 660–960). The apply record's closing line
   ("1145 … against a session budget of 1200") counts only launch 2's four commits; launch 1's
   three add another 832. **No `size:exception` was ever explicitly accepted by the user.** This
   is recorded as an overrun that happened, not as an approved allowance. Nothing about the work
   is unsound, and the per-commit slicing means only commit 1 breaches the per-unit default.

2. **WARNING-3 — the design's Commit Decomposition table is one row stale.** Commit 5 repaired a
   finding the design never carried (`usage.md` working no `probe`, `name` or `compose`
   invocation), and F6 was folded into commit 6, where the subcommand roster makes `reconcile` a
   *required* row rather than a presence check. Both deviations were judged sound by the
   verifier. The design record was not rewritten; this report is the reconciliation.

3. **SUGGESTION-1's residual escape hatch, confirmed by injection.** A leak in a word nobody has
   found yet can still be silenced by one `FORGE_LEXICON` entry: the disjointness meta-test only
   defends words *already on the floor*. The verifier planted `renyi` in `SKILL.md` and added a
   plausible four-word reason for it — suite green. This is the design's own **High**-likelihood
   risk ("the forge lexicon grows until rule B constrains nothing"), confirmed rather than new.

4. **Roster columns two and three are prose.** `smoke record`'s and `readiness`'s rows are
   asserted only in column one, against the parser; the routing state and flag-location columns
   are read by no test. The verifier checked both by reading code and found them **true** —
   `cmd_probe` really does call `rcli.cmd_readiness(...)` at `implementation_cli.py:4986` to
   compute `smokeReady`, and `cmd_smoke_record` writes the verdict `readiness` reads — but true
   is not asserted. Every roster class states this in its own docstring.

5. **The remaining WARNINGs and SUGGESTIONs from the `verify-report`, all still open:**
   - **WARNING-2** — `premises` field names are held by prose alone. `SKILL.md:523` and the
     kit's `assets/kit/src_benchmark/__init__.py:27-30` agree today, but the kit's names live in
     a *comment* (the live value is `"premises": {}`), so an AST-derived lock is unavailable
     without restructuring the kit. The two copies can drift silently.
   - **WARNING-4** — the Windows branch of the F3 fixture (`os.name == "nt"`, writing
     `Scripts/python.exe`) is written and never exercised on this platform. The `.venv` symlink
     is also not a built environment; the docstring says so plainly.
   - **SUGGESTION-2** — rule B splits compound names on `_` and drops tokens under three
     characters, so a future target module named from two lexicon words would pass it entirely.
     Today's instances (`report_digest`, `shard_io`) are harmless: the direction is forge→target.
   - **SUGGESTION-3** — as item 4 above.

6. **Out of scope for this change, and still open elsewhere:**
   - `kaggle-accounts`' undocumented `materialize` command (`accounts_cli.py:690-764`), which
     writes plaintext tokens under `store/workers/<user>/token` that `remove` never deletes.
     Security-adjacent and carrying its own credential decision.
   - The stale prose at `remote-execution/SKILL.md:398-400`, which claims probe's
     `remoteExecution` fact "does not exist yet". It exists.
   - The substring defect at `implementation_cli.py:3365` — `p.name in (contract.get("record")
     or "")` where equality was meant, so a declared `"summary.json"` also matches `sum.json`.
     A **stated non-goal**: commit 1 changed the default only and left the operator
     byte-identical, because fixing it changes which file `verify` selects as the record and
     feeds `introspect`, `inertConclusions` and the permutation check.
   - `proposal-deliberation`'s 50-plus engine modules — **the largest unaudited surface in this
     repository**, never scanned by any exploration to date.

---

## 7. Delivery state

**Eight commits, local on `main`, nothing pushed, by the user's explicit choice.** No branch was
created, no PR opened, and `origin/main` does not contain any of this work
(`## main...origin/main [ahead 8]`). Receipt-driven development is off, so delivery follows
ordinary repository policy. Archiving this change closes the SDD cycle; it does not deliver the
work, and nothing in this report should be read as implying that it did.

Rollback remains per-commit: each of the eight is independently `git revert`-able. Only two
touch runtime behaviour — commit 1 (two defaults, behaviour-preserving except where a target
relied on the guess, which was the leak) and commit 7 (one optional flag; omitted, `verify`
behaves exactly as before, and `shardsArrived` gains a key rather than losing one).

---

## 8. Artifact inventory (paths in place of observation IDs)

Engram was disconnected for the entire cycle, so **no observation IDs exist**. Scratchpad root:
`/private/tmp/claude-501/-Users-diego-Proyectos-papersmith-ai/bbf0d055-1eda-4f88-a67c-39777642bdcc`.

| Artifact | Path | Notes |
|---|---|---|
| exploration | `<scratchpad>/halves-nobody-joined.md` | the origin: findings F1–F7 plus #8 |
| proposal | `<scratchpad>/the-flow-names-what-it-needs-proposal.md` | four questions never put to the user; assumptions stood in |
| spec | `<scratchpad>/the-flow-names-what-it-needs-spec.md` | 14 requirements, 26 scenarios, 7 groups + cross-cutting |
| design | `<scratchpad>/the-flow-names-what-it-needs-design.md` | D1–D9; Commit Decomposition table one row stale (item 6.2) |
| tasks | `<scratchpad>/the-flow-names-what-it-needs-tasks.md` | 62 boxes, all `[x]`; includes the launch-3 remediation box R.1 |
| apply-progress | `<parent>/the-flow-names-what-it-needs-apply-progress.md` | three launches: commits 1–3, commits 4–7 + Phase 8, and the remediation |
| verify-report | `<scratchpad>/the-flow-names-what-it-needs-verify-report.md` | `verdict: fail`, superseded on its CRITICAL by `e21f46c` |
| archive-report | `<scratchpad>/the-flow-names-what-it-needs-archive-report.md` | this file |
| archive-time evidence | `<scratchpad>/archive-gate/` | `pristine.py`, `inverse.patch`, `impl_before.tsv`, `impl_after.tsv` |

**No specs were merged and no change folder was moved.** The artifact store is `engram`, and no
`openspec/changes/the-flow-names-what-it-needs/` directory exists (the active `openspec/changes/`
holds five unrelated changes). Steps 2 and 3 of the archive procedure are therefore not
applicable, no artifact bytes were copied or moved, and no file content passed through the
model's read/write path.

---

## 9. Final-state reconciliation

Recorded explicitly so no reader takes a snapshot claim for a current fact:

| Fact | Snapshot claim | State at close | Where it changed |
|---|---|---|---|
| Verify verdict | `fail`, 1 CRITICAL (`verify-report`, at `21a0064`) | CRITICAL closed; reproduced by mutation at archive time | `e21f46c` |
| Scenario coverage | 25 of 26 (`verify-report`) | 26 of 26 | `e21f46c` |
| Skill suite | 448 OK (`verify-report`, `apply-progress` launch 2) | **449 OK**, measured at archive | `e21f46c` |
| Full discovery | 789 OK (same) | **790 OK**, measured at archive | `e21f46c` |
| Commit count | 7 (`verify-report`) | **8** | `e21f46c` |
| Authored lines | 1,985 over 7 commits (`verify-report`) | 1,985 over 7; **2,044 over 8** | `e21f46c` (+59) |
| `implementations/` untouched | asserted via `git status` (`apply-progress` task 8.1) | proven by 51,558-entry manifest, zero differences; the `git status` check is void because the path is gitignored | verifier's correction, re-proven here |

No unrankable contradiction was found between the launch prompt, the repository, and the
artifacts. Every final-state fact asserted in the launch prompt was independently corroborated
against the repository during this phase.

**The SDD cycle for `the-flow-names-what-it-needs` is complete and closed.**
