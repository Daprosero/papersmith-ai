# Apply progress: the-skill-that-audits-the-others

Store: openspec (Engram disconnected). Mode: **Strict TDD**. Delivery: commits directly on `main`,
no branches, no PRs, no push. Budget: slice 3 deferred; chain 1 → 2 → 4 → 5.

## Shell status — the streak ends here

**This phase HAS a shell.** `Bash` is available and was exercised before any file was written:

```
SHELL_OK: Fri Aug 21 16:06:09 -05 2026
/Users/diego/Proyectos/papersmith-ai
main
Python 3.9.6
v26.4.0
```

Five consecutive phases (`sdd-explore` x2, `sdd-propose`, `sdd-design`, `sdd-tasks`) ran without
one. The gate at task 0.1 is therefore **passed, not waived**, and every claim below that is
marked `CONFIRMED by execution` carries a transcript in this file.

---

## Phase 0 — gates, all run

### 0.1 Shell gate — PASS

Tools observed: `Bash`, `Read`, `Write`, `Edit`. Confirmed by executing `date`, `pwd`,
`git rev-parse`, `python3 --version`, `node --version` before authoring anything.

### 0.2 Baselines — CONFIRMED by execution

```
$ python3 -m unittest discover -s tests 2>&1 | rg '^Ran |^OK|^FAILED'
Ran 902 tests in 35.720s
OK
```

```
$ npm test 2>&1 | tail
i tests 371
i suites 0
i pass 371
i fail 0
i cancelled 0
i skipped 0
i todo 0
i duration_ms 21072.045875
NODE: v26.4.0
```

Python baseline **902**. Node baseline **371 pass, 0 fail**, Node **v26.4.0**. Both match the
figures the orchestrator carried in. Saved as the before-side of the slice-5 report.

### 0.3 Name-freedom search — CONFIRMED by execution

`rg --no-ignore --hidden -n -l` over the repository root.

| Name | Files matched | Verdict |
|---|---|---|
| `skill-audit` | the four artifacts of this change only | free |
| `skill_audit` | the four artifacts of this change only | free |
| `audit_cli` | the four artifacts of this change only | free |
| `SkillAudit` / `AuditReport` | none | free |

Every match is `openspec/changes/the-skill-that-audits-the-others/{proposal,design,spec,tasks}.md`.
Zero matches outside this change. Pass condition met.

**The blind spot is proven, not assumed.** Control on `firedrill`:

```
$ rg -n -l 'firedrill' . | wc -l              -> 5
$ rg --no-ignore --hidden -n -l 'firedrill' . | wc -l -> 6
```

The sixth file is `implementations/Domain_Adaptation/src/MIL_CREDA_Benchmark/harness.py`, invisible
to a default search. The rejected name was occupied and the default search would have said
otherwise.

### 0.4 argparse refusal wording, pinned — CONFIRMED by execution

`python3 --version` -> **Python 3.9.6**.

```
$ python3 -c "import argparse,sys;p=argparse.ArgumentParser(prog='audit_cli.py');s=p.add_subparsers(dest='command');s.add_parser('roster');s.add_parser('check-report');p.parse_args(['zzz'])"
EXIT=2
--- stdout ---
(empty)
--- stderr ---
usage: audit_cli.py [-h] {roster,check-report} ...
audit_cli.py: error: argument command: invalid choice: 'zzz' (choose from 'roster', 'check-report')
```

Stream **stderr**, exit **2**, rendering `(choose from 'a', 'b')` — each choice single-quoted,
comma-space separated. R12 is closed for this interpreter. D3 still carries the case where a future
interpreter changes the rendering: a non-matching extraction is a loud exit 2, never an empty set.

**Consequence for the CLI idiom.** Python here is **3.9.6**, where PEP 604 (`X | None`) is not
valid at annotation-evaluation time. The house idiom `def main(argv: list[str] | None = None) -> int`
survives at `remote_cli.py:1454` and `implementation_cli.py:5329` only because both files carry
`from __future__ import annotations` (`:36` and `:18`). `audit_cli.py` carries it for the same
reason. This is a house convention discovered by execution, not a deviation from the design.

### 0.5 The D1 probe, driven by hand — CONFIRMED by execution

Run from an empty scratch directory with no project root anywhere above it:

```
$ node .../proposal-deliberation/engine/cli.mjs '{"operation":"__AUDIT_NONCE__","instruction":"probe"}'
EXIT=1
--- stdout ---
{
  "status": "error",
  "message": "UNKNOWN_OPERATION: \"__AUDIT_NONCE__\" is not one of STATUS, RESOLVE_TARGET, WITHDRAW_REVISION, RESTORE_WITHDRAWN_REVISION, CREATE_SUCCESSOR, CREATE_INITIAL_REVISION, CHAT_DELIBERATION, CLOSE_DELIBERATION, MAINTENANCE"
}
--- stderr ---
(empty)
```

**Nine names recovered**: `STATUS`, `RESOLVE_TARGET`, `WITHDRAW_REVISION`,
`RESTORE_WITHDRAWN_REVISION`, `CREATE_SUCCESSOR`, `CREATE_INITIAL_REVISION`, `CHAT_DELIBERATION`,
`CLOSE_DELIBERATION`, `MAINTENANCE`. Stream **stdout**, exit **1**. The directory listing was
empty before the run and empty after it: **nothing was written**, exactly as D1 predicted from
`validateRequest` being `run()`'s first statement. The gate on the whole change passes.

### 0.6 Anchor re-verification — all confirmed, and one new correction found

| Anchor | Disk says | Verdict |
|---|---|---|
| `cli.mjs:319` | `if (operation !== undefined && (...))` | confirmed — token-present, not token-absent |
| `cli.mjs:320` | `UNKNOWN_OPERATION: ${JSON.stringify(operation)} is not one of ${[...HOST_OPERATIONS, ...TOOL_OPERATIONS].join(', ')}` | confirmed |
| `cli.mjs:332-333` | `async function run(request) {` / `validateRequest(request);` | confirmed — first statement |
| `cli.mjs:372-373` | `process.stdout.write(...)` / `process.exit(1)` | confirmed |
| `cli.mjs:20-21` | `~63 TS files` on `:20`, `roughly 0.72s` on `:21` | confirmed — tasks' correction stands |
| `proposal-deliberation/SKILL.md:243` | `## Other engine operations`, four rows `:245-250`, `:252` "None of the four" | confirmed — complement set |
| `references/usage.md:264-266` | all nine stated in prose, no table | confirmed |
| `...operation-surface.test.mjs:88-98` | `mutations`, `documentAuthority: 'FORBIDDEN'`, `explicitHandoffRequired: true` at `:92-97` | confirmed |
| `test_proposal_implementation.py:267` | `for gap in impl.scaffold_gaps(box, name):`, `:270` `impl.IGNORE_ENTRIES`, docstring `:240` | confirmed — a call site inside a `for` |
| helpers `:82 :103 :9017 :9118` | `markdown_table_rows`, `returned_keys`, `dict_literal_keys`, `subcommand_surface` | confirmed |
| `FORGE_VOCABULARY_FLOOR` `:62-63` | exact | confirmed |
| House frontmatter | `---`/`name`/`description`/`---` on lines 1-4, **five for five** | confirmed |
| `remote-execution/SKILL.md:19` | `Three modules exist so far, each service-blind and stdlib-only:` | confirmed |

**New correction, found by execution — the enumeration is five, not four.** The design and the
tasks both state that `:19`'s "Three" sits above bullets at `:21`, `:32`, `:50`, `:57` — four. The
contiguous top-level bullet run actually holds **five** items: `:21`, `:32`, `:50`, `:57` and
**`:143`**. Everything between `:58` and `:142` is blank or indented continuation, so `:143` is
inside the same list; the run is broken at `:176` by a table. Measured:

```
$ awk 'NR>=20 && NR<=240 { if ($0=="") next;
        if ($0 ~ /^- /) {printf "BULLET %d\n", NR; next}
        if ($0 ~ /^[ \t]/) next;
        printf "BREAK  %d\n", NR }' .claude/skills/remote-execution/SKILL.md
BULLET 21
BULLET 32
BULLET 50
BULLET 57
BULLET 143
BREAK  176
```

This is the change's own thesis arriving inside the change: a read-only enumeration was wrong, and
execution decided. Per spec Group 5, the executed set decides and the discrepancy is reported as a
defect in the enumeration rather than silently overwritten. `numeralMismatch` therefore reports
`counted: 5` against `stated: 3`, and the design's "four" is recorded here as corrected.

---

## Slices, as delivered

Chain 1 -> 2 -> 4 -> 5, fully sequential, slice 3 deferred. **Strict TDD: every
slice opened with an observed RED and every lock that passed on first run was
inverted, watched to fire, and restored by inverse patch — never
`git checkout --` — with `cmp` exit 0 and a matching sha256 each time.**

| Slice | Commit | RED observed | Python count | Rise |
|---|---|---|---|---|
| 1 doctrine core | `9d45d3b` | `Ran 16 tests` / `FAILED (failures=5, errors=10)` | 902 -> 919 | +17 |
| 2 `roster` | `1a3406c` | `Ran 51 tests` / `FAILED (failures=24, errors=1)` | 919 -> 954 | +35 |
| 4 `check-report` | `0ef9fa7` | `Ran 66 tests` / `FAILED (failures=18, errors=1)` | 954 -> 968 | +14 |
| 5 first report | see below | `Ran 71 tests` / `FAILED (failures=1, errors=2)` | 968 -> 973 | +5 |

Each rise equals the number of tests that slice added. The counts were read from
`Ran N tests`, never inferred from a suite being green — a duplicate class name
once silently disabled seven tests behind a green suite in this repository.

`npm test`: **371 pass, 0 fail, Node v26.4.0**, unchanged. This change ships no
`.mjs`, so a rise there would have been the surprising result. Reported
separately because the harnesses are disjoint and no single command runs both.

### Inversions run (17 budgeted, 17 run, all fired)

| # | Inversion | Observed |
|---|---|---|
| 1.9 | delete move 5's row | `[0,1,2,3,4,6,7] != [0,1,2,3,4,5,6,7]`, naming move 5 |
| 1.10 | `Ships as` names a non-subcommand | `'liveprobe' not found in {'check-report','roster','doctrine'}` |
| 1.11a | a heading states a count | `['## The seven moves'] != []` |
| 1.11b | the scanner, on a colon line above the table | `stated: 7, counted: 9, numeralLine: 48, enumerationLine: 50` |
| 1.12 | admit a floor word to the lexicon | `['transfer'] != []` |
| 1.13 | add a `license:` key | `line 3 must be the description, got 'license: MIT'` |
| 2.20a | a subparser with no documented row | `unregistered = ['manifest']` |
| 2.20b | a documented row with no subparser | `phantom = ['counts']` |
| 2.21 | corrupt the recipe's `extract` | exit `2`, not an empty `code` set |
| 2.22 | the quoted heading no longer matches disk | kind flips to `heading-not-found` |
| 2.23a | `import subprocess` in the documented side | `doctrine_side names 'subprocess'` |
| 2.23b | a borrowed producer reference | `restatement_of names 'probe_code_side'` |
| 2.24 | edit one copied helper | byte-identity fails, naming both locations |
| 2.25a | hedge an unhedged claim | the check goes quiet; the lock fires |
| 2.25b | correct the numeral | the check stops firing; the lock fires |
| 3.12 | drop the evidence-marker rule | the planted-fixture lock fires |
| 3.13 | drop the both-halves rule | the one-half lock fires |
| 3.14a | delete a documented row | `['falsifier'] != []` |
| 3.14b | document a field nothing enforces | `['reviewer'] != []` |

Nineteen ran, against seventeen budgeted: 1.11 and 2.25 each needed two, because
one direction proves the rule fires and the other proves it can stop firing.

**One inversion driver defect, found and fixed mid-flight.** The first run of
1.9 restored a deleted line with `str.replace("", old, 1)`, which prepends
rather than re-inserting, and corrupted `SKILL.md`'s first line. It was repaired
by an offset-recorded inverse patch, confirmed against the pre-inversion copy by
`cmp` (exit 0) and sha256, and the driver now records the byte offset before
editing so a deletion's inverse is an insertion at a known place. Worth stating
because it is the change's own subject: the restoration mechanism had a defect
that only executing it could reveal.

### Containment

`implementations/Domain_Adaptation`: **46,626 files**, sorted `path -> sha256`
listing taken before the first file of this change was written and again at the
end. Both listings hash to
`f9b566291f4194093993347a4325d110171bf0017c45618c9bbbc7720294b07f`; `cmp` exit
`0`. Never `git status`, which is empty over that tree by construction.

Fixture boxes lived at `implementations/_skill_audit_*` and never in the system
temporary directory; `implementations/` holds only `Domain_Adaptation` at the
end. `.claude/skills/proposal-deliberation/` and
`.claude/skills/remote-execution/` are byte-identical to `HEAD`: `mutations: 0`,
including the one-line `phantom` this audit found and did not repair.

---

## Findings this phase produced that the plan did not carry

1. **The design's enumeration was wrong, and execution decided.**
   `remote-execution/SKILL.md:19` says "Three" above a contiguous bullet run of
   **five**, not four: `:143` sits inside the same list, since everything from
   `:58` to `:142` is blank or indented continuation, and the run breaks at
   `:176`. The plan's "four" came from a phase with no shell. Recorded per spec
   Group 5: the executed set decides and the enumeration is the defect.

2. **The numeral rule needed narrowing on grammar, not exemptions.** Its first
   run on a real subject produced two false positives from a single line,
   `proposal-deliberation/SKILL.md:133`, `### 2. Build one `EditAction` per
   resolved locus` — an ordinal step marker and a distributive rate. The rule
   now requires a size claim's actual grammar (a numeral ahead of a plural noun,
   or postposed before a colon). That is a narrowing with a stated reason, not
   a list of inconvenient cases, which is the difference the doctrine insists on.

3. **A third finding nobody had enumerated**, now F3 in the report:
   `engine/proposal-workspace.ts:5546` carries a seven-member `StringEnum` whose
   own `description`, on the same physical line, promises an eighth operation
   the host refuses by name.

4. **The design's open question about `SCIENTIFIC_WORKFLOW` is closed by
   execution.** `recordRouteMetric` does have a call site
   (`engine/proposal-workspace.ts:5407`), so the design's "pending a consumer of
   `routeStages`" condition is met — but no `selectedGlobalRoute` call in the
   live source can produce that stage, and no engine `.ts` defines
   `SCIENTIFIC_WORKFLOW_OPERATION` any more. The counter exists and nothing can
   increment it. Still `not adjudicable`, for a sharper reason than the plan had.

5. **Python here is 3.9.6**, where `X | None` is not valid at annotation time.
   The house idiom survives only because `remote_cli.py:36` and
   `implementation_cli.py:18` carry `from __future__ import annotations`.
   `audit_cli.py` does the same.

## Deferred, with reasons — not dropped

- **Slice 3** (`manifest`, `counts`), spec Group 6, success criteria 6 and 8,
  and the two slice-3 inversions -> `the-manifest-that-proves-containment`.
  Reason: session budget. `manifest` had nothing to guard here because D1's
  probe is refused before any project I/O, so no slice needed a throwaway box
  for its own sake; `counts` had nothing to measure because this change ships
  no fix. The rise from 902 is proven by running the harness instead.
- **The route-metric-stage slice.** Now carries a concrete read-only candidate:
  `GlobalRouteStage` (`proposal-workspace.ts:5313`) and `RouteMetricStage`
  (`runtime-metrics.ts:3`) differ by one member each way, while
  `selectedGlobalRoute` passes one straight into `recordRouteMetric`, and
  nothing in this project typechecks those files.
- **The four helpers are copied, not shared**, into `tests/test_skill_audit.py`,
  and `markdown_table_rows` is copied a third time into `audit_cli.py`. A
  deliberate cost: sharing means editing a 75-class suite from inside a change
  about a different skill. Paid for by a byte-identity lock that names every
  location, proven reachable-red by inversion 2.24.
- **Named non-goals honoured**: `openspec/config.yaml:19,21,25` is untouched;
  the proposal's and design's "seven-move table" prose is untouched (the heading
  is corrected only inside `skill-audit`'s own doctrine);
  `implementations/Domain_Adaptation` is untouched; `proposal-deliberation` is
  untouched. Nothing was sent to any remote service; this change made no live
  call of any kind.

## The budget, measured rather than assumed

Authored lines, excluding the five artifacts earlier phases wrote and this
phase's own progress log:

| Slice | Authored (additions + deletions) |
|---|---|
| 1 | 1,161 |
| 2 | 1,014 |
| 4 | 486 |
| 5 | 273 |
| **Total** | **~2,934 against a 1,200 session budget** |

**This is a real overrun and it is reported rather than absorbed.** The plan
forecast ~1,130; the delivered work is roughly 2.6x that, and slices 1 and 2
each exceed the 400-line per-PR guard on their own. The cause is not scope
creep — every task in the plan was implemented and no unplanned feature was
added — but density: the plan costed the doctrine, the mechanism and the
per-lock discipline (planted-fixture preconditions, reachability, byte-identity,
the threat-matrix row, nineteen inversions) at roughly a third of what they take
in this repository's house style, where every constant and every guard carries
the argument for its own existence.

The four commits are independent and revert in reverse order, so the work is
re-sliceable for review without redoing it. Under `ask-on-risk` this is the
decision worth surfacing before any review begins.
