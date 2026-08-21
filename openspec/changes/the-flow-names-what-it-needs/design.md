# Design: the-flow-names-what-it-needs

Change: `the-flow-names-what-it-needs` · Skill: `proposal-implementation` · Store: engram unavailable — written to scratchpad.

Inputs: the proposal and `halves-nobody-joined.md`. The settled decisions (F1 at Flow A step 8, F2 as option (a) narrowed to the refusal, F7's five sites plus the derived guard, the three rosters, `tools/` needing a sentence rather than a template) are carried forward unchanged. Everything below is the mechanism.

## Technical Approach

One repair per finding, plus one shared derivation helper that three of them reuse. The doctrine repairs are not prose edits with a prose test behind them: each converts its target list into a **parseable markdown table**, and a test derives the same list from the code with `ast` and asserts set equality. That is why the table conversion is a prerequisite of the lock and not a tidying pass.

Three corrections to the proposal, found by reading the code during design, are folded in below and flagged where they land: the `record` default cannot become `None` at one of its two sites; `latent` leaks at a **sixth** site the proposal did not list; and the word-level derived guard has a much larger legitimate-vocabulary overlap than estimated, which changes how the lexicon must be defended rather than whether it exists.

---

## Architecture Decisions

### D1 — the `record` default becomes `""` at one site and `None` at the other

`implementation_cli.py:4039` feeds `_is_reporting_cell(..., record_name)`, which is typed `str | None` and opens with `if not record_name: return False` (`:3983`, `:3990`). So `record_name = contract.get("record")` is safe and behaviour-preserving.

`implementation_cli.py:3365` is different: `p.name in (contract.get("record") or "latent.json")`. Dropping the default to `None` makes it `p.name in None` — a **`TypeError` on every target that declares no record**. The default there becomes `""`: `p.name in ""` is `False` for any non-empty name, which is exactly "no record declared, no record found".

**Choice**: `contract.get("record")` at `:4039`, `contract.get("record") or ""` at `:3365`.
**Alternatives considered**: `None` at both (crashes); rewriting `:3365` to `p.name == record_name` (fixes the substring defect, which is a declared non-goal — see D8).
**Rationale**: the smallest change that removes the leak without touching the operator whose defect is being reported separately.

### D2 — a sixth leak site

`implementation_cli.py:5114` reads "the report also renders latent-analysis quantities (e.g. `geometry.ratio`, `domainSeparability`)". `latent` there is the same target's vocabulary as the other five, in a comment inside `cmd_verify` — the function commit 7 also edits. It joins commit 1's site list, rewritten to name the shape generically ("quantities the report renders that never sit on a shard").

### D3 — the derived guard: two units, one lexicon, one floor

Measured, not estimated. Deriving tokens from `implementations/Domain_Adaptation` (directory name, `src/*` package names, module basenames) and searching the four guarded forge surfaces produces hits on `harness`, `wiring`, `tables`, `figures`, `verdict`, `models`, `objective`, `shard`, `shards`, `digest`, `training`, `pipeline`, `kernel(s)`, `confidence`, `artifacts`, **and on ordinary English**: `attention` ("spends the reader's attention", `SKILL.md:588`), `adaptation` ("the arm with its adaptation switched off", `:1487`), `rungs` ("a ladder whose rungs differ", `:1493`).

That is the honest cost the proposal named, one size larger: once ordinary English nouns enter the lexicon, a word-level denylist derived from one target admits most of that target's module names by common-noun overlap. And `harness` **must** be in the lexicon — `probe` reports a `harness` key (`implementation_cli.py:2123`) and the doctrine says "the harness refuses" — which means the word-level rule **cannot catch `harness.render_panorama`**, one of the five sites it was adopted to catch.

So the guard is built at two units:

| Rule | Unit | Derived from | Catches | Cannot catch |
|---|---|---|---|---|
| **A — example vocabulary** | dotted name inside a worked `report`/declaration example | nothing external; a declared allowlist `{"tables", "figures"}`, the names the kit's own `__init__.py` already uses | `harness.render_panorama`, `latent.grid`, `"latent.json"` — every dotted site of F7 | attribute names (`tables.conclusion_rungs`) |
| **B — target words** | word, `\bword\b`, case-insensitive | `implementations/*` directory, `src/*` package and module basenames, minus the declared forge lexicon | `latent` in prose (`SKILL.md:1236`, `:1240`, `cli:2725`, `:3365`, `:4039`, `:5114`), any future distinctive target word | ordinary-English overlaps, which the lexicon must admit |
| **C — floor** | word | the existing fixed list at `tests:4716`, plus `latent` | leaks somebody already found | anything new |

Rule A is an **allowlist**, which is why it is precise where B is not: a worked example may draw only from two declared names, so a leak in an example is caught without anyone having enumerated the leak.

**How the lexicon is declared, and how it resists being weakened.** A module-level `FORGE_LEXICON: dict[str, str]` beside the guard in `tests/test_proposal_implementation.py` — word to one-line reason. Two meta-tests defend it, both cheap:

1. every entry's reason is non-empty and at least a few words, so adding a word costs an argument rather than a comma;
2. `FORGE_LEXICON.keys()` and the rule-C floor are **disjoint**, so nobody can silence `creda`, `kaggle` or `latent` by lexicon entry.

**Alternatives considered**: a data file under `tests/` (a second thing to find, and the reason column is the review artifact); a set instead of a dict (nothing to review); word-level derivation alone (misses `harness.render_panorama`, the site C1 names).

### D4 — F1 lands at Flow A step 8, and the kit is untouched

Step 7 is already `[GATE] Ask for authorization to implement`; step 8 already presents a map and waits for approval. Step 8 gains the declaration's `revision` and `premises` beside the map, and writes them into `src/<Package>_Benchmark/__init__.py` on approval. `assets/kit/src_benchmark/__init__.py:21` ("asked for by the flow, never invented here") becomes true without editing the kit. `SKILL.md:717`'s `AGREEMENTS.md` rule — append at every gate, before writing the code the gate authorized — is the existing doctrine this instantiates, and `SKILL.md:604-646`'s protocol draft already produces `premises` field for field.

`revision` is **proposed** as Flow A step 1's `latest` and confirmed inside the approval, never taken silently: `SKILL.md:913-915` forbids a fabricated value.

**Alternatives considered and rejected** (carried from the proposal, unchanged): step 5b (name unconfirmed, `premises` would be invented); step 16 or Flow B (dead-ends at `declare-first`, today's bug moved later); a new numbered step (steps 5, 9, 15, 16 are cross-referenced at `:475`, `:508`, `:510`, `:554`, `:846`; renumbering is diff with no product).

### D5 — F3: `smokeReady` and staleness are documented, never gating. Position taken.

**They stay reported.** The proposal's reasons hold, and the code adds a decisive one: `remote_execution_jobs_state` returns `{"jobs": [], "services": 0, "smokeReady": {}}` when the remote-execution CLI is not on disk at all (`:4900-4901`), which is byte-identical to what it returns for a target that has the CLI and no jobs. **The fact as computed cannot tell "not ready" from "not applicable"**, and a gate needs exactly that distinction. A ladder branch on it would have to invent a meaning for the empty dict and would suppress a legitimate `benchmark` answer for every target that never uses remote execution.

Two things follow. First, `smokeReady: false` and `staleness: drift` get **Decision Gates rows** — the human reads them beside the `benchmark` answer. Second, the position is locked **behaviourally**, not by prose: a test builds a target whose `smokeReady` is `{job: False}` and asserts `probe` still answers `benchmark`. That test is the artifact that makes this a decision rather than an omission.

**The falsifier, recorded**: if `remote_execution_jobs_state` grew a per-job link to the campaign about to be offered, gating becomes expressible and this decision should be revisited. Until then it is not.

### D6 — F2: `verify --shards` path-imports `shard_io.py` directly

`shard_io.disagreements` reads `entry["stamp"].get(field)` (`shard_io.py:65`) and nothing else, so the refusal needs no grouping vocabulary. `verify` grows one optional flag; omitted, it behaves exactly as today.

**Choice**: a third path-import constant `REMOTE_EXECUTION_SHARD_IO_SCRIPT` with a lazy loader, called only inside the `--shards` branch.
**Alternatives considered**: `_load_remote_execution_cli().SHARD_IO` — reuses an already-authorized import, but drags `jobfolder`, `adapter`, `packer` and `credentials` and a service-adapter dispatch surface into a read-only checker that runs on every target, including every target with no remote execution.
**Rationale**: `shard_io.py` is stdlib-only and names no service, and its own docstring says it is the half that belongs to a forge serving more than one paper. The module-identity argument that forced `remote_cli` to be loaded once (`:4806-4811`, `JobFolderError` `isinstance` matching) does not apply: `shard_io.py` defines no exception class and no class at all. The module comment at `:38-52` widens from two files to three and re-states the same audit fact.

`--shards` is read with `getattr(args, "shards", None)`, because ten existing tests build `argparse.Namespace(target=..., name=..., revision=None)` by hand and an optional flag must not break them. The tradeoff — `getattr` hides a mis-wired flag name — is paid off by the cross-join test invoking `main(["verify", ..., "--shards", ...])` through the real parser.

### D7 — the roster helper, and where each roster is weaker than a behavioural lock

One module-level helper in the test file, `returned_keys(source, function)`: parse with `ast`, find the `FunctionDef`, collect the string keys of **every** `Return` whose value is a `Dict`, and assert all such returns carry the same key set. That second assertion is not decoration — it is the derived lock for D9's symmetry fix.

| Roster | Derives | Holds to | Fails when | Cannot cover | Its partner |
|---|---|---|---|---|---|
| **Status** | top-level string keys of `cmd_verify`'s single dict return (`:5161`, 13 keys) and `cmd_probe`'s (`:2116`, 17 keys), minus each command's identity keys | two new Output Contract tables, `Status \| What it reports \| Gates?`, column 1 stripped of backticks | set inequality, message naming each side ("`coupling` is returned by `cmd_verify` and named in no Output Contract row") | nested keys, and whether columns 2–3 are **true** | the existing `coupling_state` behavioural tests; for the `Gates?` column, D5's behavioural partner |
| **`remoteExecution` facts** | keys of `remote_execution_jobs_state`'s two dict returns (`:4901`, `:4942`) — `jobs`, `services`, `smokeReady` | a sub-table under `probe`'s `remoteExecution` row | set inequality, or the two returns disagreeing | per-job `staleness` shape | D5's behavioural partner |
| **Command** | `add_parser("…")` string literals in `remote_cli._build_parser`, including the nested `smoke record` → 9 entries | `Subcommand \| The reported state that routes here \| Where the flags are documented` | set inequality | flags, and whether the routing state named is real | commit 5's presence test for `reconcile` at both ends |
| **Declaration blocks** | the six top-level keys of `__benchmark__` in `assets/kit/src_benchmark/__init__.py` | `Block \| Filled by \| When`, and each Flow-A cell must name a step number that exists in the Flow A list and whose text mentions the block | a block missing a row, a cell naming a step that does not exist, or a step that does not mention its block | **whether the step works.** Flow A is prose executed by an agent; the residual is prose matching | **none exists.** Stated, not claimed away — this is the weakest lock in the change |

**The fourth test the proposal rejected stays rejected**: "every reported fact must be branched on or documented" is false by construction, because `coupling` is explicitly reported and never gating (`:2140`, `:4006`). The bar is documentation, which is why every roster is a table of statuses and not a table of branches.

### D8 — the substring defect is a non-goal, and commit 1 must not accidentally fix it

`implementation_cli.py:3365` uses `p.name in (contract.get("record") or …)` where equality was meant: a declared record of `"summary.json"` also matches a file named `sum.json`. It stays reported, not fixed, for two reasons. It is a different class — a wrong operator, not a capability nobody names — so it deserves its own evidence and its own commit. And fixing it changes which file `verify` selects as the record on any target whose declared name contains another JSON filename, which feeds `introspect`, `inertConclusions` and the permutation check: a behavioural blast radius that has no business riding inside a vocabulary repair. Commit 1 changes the **default only** (D1); the operator is left byte-identical.

### D9 — `distribution_state`'s missing `shardsArrived` is locked by the roster it already breaks

The `none`/`absent`/`undeclared` branches (`:622`, `:628`) return `shardsDisagree` and omit `shardsArrived`, so the key vanishes for exactly the targets that declare no distribution. Adding `distribution_state` to the roster helper's function list makes the all-returns-agree assertion fail **before** the fix, which is RED-before-GREEN by construction rather than by ceremony. It lands in commit 7 for that reason, not in 3.

---

## Data Flow

    verify --shards <dir>
        │
        ├─ resolve_benchmark_declaration ──→ contract["distribution"]["identicalAcrossShards"]
        │                                                     │
        └─ shard_io.read_shards(<dir>) ──→ [ {shard, stamp, runs} … ]
                    │                                         │
                    └──────────→ shard_io.disagreements(shards, fields)
                                              │
                    {"disagreements": …, "shardsArrived": [names]}
                                              │
                                    distribution_state(..., merged=…)
                                              │
                          distribution.shardsDisagree / .shardsArrived

    tests/…::returned_keys(cli.py, "cmd_verify") ──┐
    tests/…::returned_keys(cli.py, "cmd_probe")  ──┼─→ set equality ─→ SKILL.md Output Contract tables
    tests/…::add_parser literals (remote_cli.py) ──┼─→ set equality ─→ SKILL.md subcommand table
    tests/…::__benchmark__ keys (kit/__init__.py) ─┘                 ─→ SKILL.md block table ─→ Flow A step 8

## File Changes

| File | Action | Description |
|---|---|---|
| `.claude/skills/proposal-implementation/scripts/implementation_cli.py` | Modify | `:2723-2726` and `:5114` comment examples de-leaked; `:3365` default `""`; `:4039` default dropped; `:38-52` import comment widened; `REMOTE_EXECUTION_SHARD_IO_SCRIPT` + loader; `cmd_verify` builds `merged`; `main()` adds `--shards` to `verify`; `distribution_state`'s three early returns gain `shardsArrived` |
| `.claude/skills/proposal-implementation/SKILL.md` | Modify | step 8 (F1); declaration section block table; `:1230-1242` worked example rewritten; Output Contract → two tables; `remoteExecution` fact sub-table; Decision Gates +4 rows; `:1035-1044` names `remote_cli reconcile`; subcommand→state table; `:370-388` gains the `generate-job` sentence; `:1560-1567` names `--shards` |
| `.claude/skills/proposal-implementation/references/usage.md` | Modify | Reading `verify` (`coupling`, `lfs`, shard facts); `reconcile`, `poll`, `generate-job` invocations; a section pointing at `remote-execution` for flags |
| `tests/test_proposal_implementation.py` | Modify | `FORGE_LEXICON` + two meta-tests; rules A/B/C; `returned_keys` helper; four roster classes; D5's behavioural partner; F2's cross-join |
| `assets/kit/**` | **Unchanged** | `src_benchmark/__init__.py:21` becomes true once Flow A has the step; `tools/` needs a sentence, not a template (`remote_cli.py:1307` already writes `<target>/tools/<service>/<job-name>/`) |
| `implementations/**` | **Read-only** | C2. Rule B enumerates names and reads nothing else |

## Interfaces / Contracts

```python
# implementation_cli.py — cmd_verify, inside the --shards branch only
merged = None
shards_root = getattr(args, "shards", None)
if shards_root:
    shard_io = _load_remote_execution_shard_io()
    shards = shard_io.read_shards(Path(shards_root))
    fields = list(((resolved["contract"] or {}).get("distribution") or {})
                  .get("identicalAcrossShards") or [])
    merged = {"disagreements": shard_io.disagreements(shards, fields),
              "shardsArrived": [entry["shard"] for entry in shards]}
```

```python
# tests/test_proposal_implementation.py
FORGE_LEXICON: dict[str, str] = {
    "harness": "probe reports a `harness` key and the doctrine calls the "
               "benchmark module a harness; the forge's own file is benchmark.py",
    # … one reason per entry, asserted non-empty and disjoint from the floor
}
EXAMPLE_MODULE_NAMES = frozenset({"tables", "figures"})  # rule A allowlist
```

## Commit Decomposition

Seven commits on `main`, conventional subjects, no `Co-Authored-By`. Subjects as proposed.

| # | Finding | Regions touched | Est. lines | Depends on |
|---|---|---|---|---|
| 1 | F7 leak + guard | `cli:2723-2726/3365/4039/5114`, `SKILL.md:1230-1242`, tests guard class | ~190 | — |
| 2 | F1 ask | `SKILL.md:499`, `:913-926` + block table, new test class | ~110 | — |
| 3 | F5 `coupling`/`lfs` | `SKILL.md:1751-1764` → two tables, `usage.md`, roster helper + status roster | ~110 | — |
| 4 | F3 `smokeReady`/staleness | `remoteExecution` sub-table, Decision Gates +2, `usage.md`, roster pair + behavioural partner | ~130 | **3** (roster helper) |
| 5 | F6 `reconcile` | `SKILL.md:1035-1044`, Decision Gates +2, `usage.md` | ~70 | — |
| 6 | #8 subcommands + `tools/` | subcommand table, `SKILL.md:370-388` sentence, `usage.md` section, command roster | ~220 | — |
| 7 | F2 shard refusal | `cli` `distribution_state`/`cmd_verify`/`main`, `SKILL.md:1560-1567`, `usage.md`, cross-join + roster pair | ~160 | **3** (roster helper) |

**Independence.** The file regions are disjoint except for the Decision Gates table (commits 4 and 5 each append distinct rows) and `tests/test_proposal_implementation.py` (each commit adds its own class). Sequential landing on `main` means no merge conflict; each commit is `git revert`-able alone.

**Genuine ordering constraints**: `3 → 4` and `3 → 7`, both because the roster helper is introduced in 3. Everything else is policy, not dependency: **1 first** so the widened guard stands in front of ~500 new lines of prose, and **7 last** because it is the one decision with a stated falsifier and reverting it costs only itself.

## Testing Strategy

`python3 -m unittest tests.test_proposal_implementation` (402 green now) and `python3 -m unittest discover -s tests` (743 green). Not `pytest`; not `-k`.

| # | RED first | The lock | Inversion planned |
|---|---|---|---|
| 1 | Rule B fires on the live tree before the lexicon exists; rule A fires on `SKILL.md:1232`, `:1236`, `:1240` and `cli:2723`, `:2725` | rules A/B/C + two lexicon meta-tests | The disjointness meta-test passes on first run → add `creda` to `FORGE_LEXICON`, watch it fire, remove **by inverse patch**. Rule A's reachability is proven the way `test_a_leak_into_a_script_is_caught` (`tests:4740-4766`) already does it: a tree built for the purpose with one planted `latent.grid`, asserting exactly which file was caught |
| 2 | Block table absent → roster fails; step 8 does not mention `premises` | block roster + Flow-A step resolution | The "cell names an existing step that mentions the block" clause passes once written → change the cell to `step 99`, watch it fire, restore by inverse patch |
| 3 | Output Contract names 11, `cmd_verify` returns 13 → fails on `coupling`, `lfs` | status roster | Not needed — RED by construction. After green: rename a returned key in a scratch copy of the parsed source, confirm the message names it |
| 4 | `remoteExecution` sub-table absent | roster pair + `probe` answers `benchmark` with `smokeReady: {job: False}` | **The important one.** The behavioural partner passes on first run → add a `smokeReady` branch to the ladder at `:2090-2106`, watch it fire, remove by inverse patch. That is what makes D5 a decision |
| 5 | `reconcile` appears in no doctrine section and no gates row | presence at both ends (doctrine section + Decision Gates + `usage.md`) | Weakest lock in the set, and named as such; its partner is commit 6's roster, which makes `reconcile` a **required** row |
| 6 | Subcommand table absent → 9 derived, 0 documented; `tools/` section names no command | command roster + `tools/` sentence test | Passes only after the table exists → drop the `poll` row, watch it fire, restore by inverse patch |
| 7 | `--shards` does not exist → `argparse` exits 2; `distribution_state`'s early returns omit `shardsArrived` | cross-join through `main(["verify", …, "--shards", …])` over a **real** shard directory, asserting `distribution.shardsDisagree` and `shardsArrived` from the command's own stdout | Behavioural variation rather than inversion: delete one shard directory, assert `shardsArrived` shrinks by one — proving the number is read from disk and not from a fixture, which is the whole objection at `SKILL.md:313-317` |

Throwaway targets go under `implementations/_<name>` (`verify` needs `git init`; `plan` also needs a commit or `DIRTY_WORKTREE`) and are deleted in `addCleanup`.

## Consumer Inventory

| Widened contract | Consumers | Action |
|---|---|---|
| `verify --shards` | `main()`'s per-command parser loop (`:5267-5291`); `cmd_verify`; ten hand-built `argparse.Namespace(...)` call sites in the suite (`tests:2615`, `:2630`, `:2794`, `:4178`, `:5083`, `:5095`, `:5111`, `:5122`, …) | `getattr(args, "shards", None)` — no test edits. Flag added to the `verify` subparser only; `admit`, `handoff`, `probe` untouched |
| Output Contract 11 → 13 | `SKILL.md:1755-1756` prose; `references/usage.md` "Reading `verify`"; any suite assertion over the eleven | Prose becomes a 13-row table; `usage.md` gains `coupling` and `lfs`; the status roster becomes the single source and any surviving hardcoded list is deleted rather than updated |
| Two new doctrine tables (statuses, subcommands) | The rosters that parse them; readers of `SKILL.md` | Column 1 is machine-read; columns 2–3 are prose and are **not** asserted. Adding a status or a subcommand now fails the suite until its row exists — which is the point |
| `distribution.shardsArrived` present on all branches | `SKILL.md:1560-1567`; readers of `verify`'s JSON | A key that used to vanish now always appears, `[]` when nothing merged. Widening, not narrowing: no consumer can break on a key appearing |
| `implementations/` read by the suite | Rule B | Read-only enumeration of names. Skips with an explicit message when no target is present, so it is silent exactly when nobody has one |

## Threat Matrix

The change adds one CLI flag and one path-import. No shell, no subprocess, no VCS or PR automation, no executable-file classification.

| Boundary | Applicability | Design response |
|---|---|---|
| Documentation-like paths | N/A — no file is classified as executable or run; `read_shards` parses JSON with `json.loads` and executes nothing | — |
| Git repository selection | N/A — `--shards` is not a repository selector; `resolve_target` and the existing `implementations/`+clean-tree guard are unchanged | — |
| Commit state | N/A — nothing in this change stages, commits or reads the index | — |
| Push state | N/A — no push, no branch, no PR | — |
| PR commands | N/A — seven commits on `main`, no PR automation | — |

One new boundary sits outside this matrix and is stated rather than skipped: `--shards <dir>` is a caller-supplied path that `verify` reads. Expected safe behaviour — a directory that does not exist yields `[]`, hence `shardsArrived: []` and `shardsDisagree: []`, which `SKILL.md:1565-1567` already defines as a legitimate answer ("three shards planned and two returned is a smaller campaign"). Failure behaviour — a malformed `shard.json` raises from `json.loads` inside `read_shards`; that propagates, because a shard file that is not JSON is not a smaller campaign, it is an unreadable one, and silently treating it as absent is the silence this skill exists to break. A planned test covers both.

## Migration / Rollout

No migration. Two commits touch runtime behaviour: commit 1 (two defaults, behaviour-preserving except where a target relied on the guess — which is the leak) and commit 7 (a new optional flag; omitted, `verify` behaves exactly as today, and `shardsArrived` gains a key rather than losing one). Commits 2–6 are doctrine and tests.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The forge lexicon grows until rule B constrains nothing | **High** — ordinary English overlaps (`attention`, `adaptation`, `rungs`) are already forced in | Rule A does the precise work and needs no lexicon; the floor is disjoint from the lexicon by test; every entry carries a reviewed reason |
| Rule B couples the suite to `implementations/` contents | Medium | Read-only (C2); skips with an explicit message when no target exists; stated as a known blind spot |
| No mechanical rule catches a leaked **attribute** name (`tables.conclusion_rungs`, `cli:2724`) | Medium | Repaired by hand inside commit 1's example rewrite; the residue is named here rather than claimed away |
| Commit 2's Flow-A lock is prose matching | Medium | Named as the weakest lock in the change; no behavioural partner exists because Flow A is prose executed by an agent |
| F2 (a) is the wrong call | Low | Falsifier checked on disk (`shard_io.py:65` reads stamps); flipping to (b) reverts commit 7 alone, which lands last |
| A repair appears to need an edit under `implementations/` | Low | None identified. The target's `premises` misspelling (`unit` for `statisticalUnit`) is **evidence for F1, not a repair** — correcting it would be a C2 breach and is reported instead |
| Suite runtime grows (rule B walks `implementations/`) | Low | Name enumeration only — directory and module basenames, no file contents read from the target |

**Review-budget forecast against 1200 lines**: ~**790 authored changed lines** (range 660–960), largest commit ~220, all seven under the 400-line per-PR default. **Risk: Low-to-Medium.** The two items that could run hot are unchanged from the proposal — commit 1's guard (now carrying two rules and two meta-tests, +~10 lines over the estimate) and commit 7's cross-join fixture. Both are the first to slice and the last to cut.

## Open Questions

- [ ] The proposal's four questions were never put to the user (interactive mode, no user channel from a phase agent). The assumptions stand: F2 → (a-narrow); the derived guard is in scope in commit 1; the full worked example is rewritten; the ladder is not touched; `tools/` gets no kit template.
- [ ] Rule A's allowlist is `{"tables", "figures"}` because that is what the kit already uses. If a future worked example legitimately needs a third module name, adding it is a one-line reviewed change — but nobody has needed one yet, and the allowlist should not be pre-grown.
