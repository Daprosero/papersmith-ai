# Tasks: the-skill-that-audits-the-others

Change: `the-skill-that-audits-the-others` · New skill: `skill-audit` · Store: openspec (Engram disconnected)

## Shell status — read this first

**This phase had no Bash either.** Available tools were Read, Write, Edit, Grep and Glob only —
no `Bash`, no `codegraph_explore`, no `AskUserQuestion`. That is the **fifth consecutive phase**
of this change with no shell (`sdd-explore` ×2, `sdd-propose`, `sdd-design`, `sdd-tasks`), and it
is the defect class this change exists to institutionalise against, arriving inside the change.

**Every anchor below is `read-only`. Nothing here is `CONFIRMED by execution`.** Nothing was
simulated; no command output is reported as if it had run.

What this phase *did* do read-only: re-located every load-bearing anchor against disk rather
than trusting the design's citations. Results in §Anchor re-location. Two corrections found.

**Per design R10: if apply also has no shell, that is a blocker to report, not a condition to
work around.** Task 0.1 is that gate and it precedes every other task.

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1,130 authored (additions + deletions), slice 3 deferred |
| Per-PR budget (400) risk | Medium — largest slice ~380 |
| Session budget (1,200) risk | Low with slice 3 deferred; High without |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 4 → PR 5 (design numbering kept; 3 deferred) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium
```

**The budget decision is made — do not reopen.** Slice 3 (`manifest` + `counts`) is deferred per
the design's own reasoning: D1 refuses the roster probe *before* any project I/O, so slice A needs
no throwaway box, leaving `manifest` nothing to guard; and this change ships no fix, leaving
`counts` nothing to measure. Remaining chain 1 → 2 → 4 → 5 ≈ 1,130, inside 1,200.

**Deferral recorded as a named follow-up, not dropped:** follow-up change
`the-manifest-that-proves-containment` carries slice 3 (`manifest`, `counts`), **success criteria
6 and 8**, spec Group 6 in full, and the two slice-3 inversion locks (`manifest` change detection;
`counts` on a summary-less capture → `unreadable`). Reason: session budget, not scope doubt.

### Suggested Work Units

| Unit | Goal | PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | `SKILL.md` doctrine core + moves-table self-audit | PR 1 | `python3 -m unittest discover -s tests -p 'test_skill_audit.py'` | `python3 -m unittest discover -s tests` (full, 902 → 902+N) | delete `.claude/skills/skill-audit/SKILL.md` + `tests/test_skill_audit.py` |
| 2 | `roster` + descriptors + copied helpers | PR 2 | same focused command | full discover + `node .claude/skills/proposal-deliberation/engine/cli.mjs '{"operation":"__AUDIT_NONCE__","instruction":"probe"}'` | delete `scripts/audit_cli.py` + `references/probes/` + PR-2 test classes |
| 4 | `references/usage.md` + `check-report` + report-schema self-application | PR 4 | same focused command | full discover | delete `references/usage.md` + `check-report` subparser + PR-4 test classes |
| 5 | First damage report on the operation surface | PR 5 | `python3 .claude/skills/skill-audit/scripts/audit_cli.py check-report openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md` | full discover | delete the report file |

**Exact suite commands.** Full Python: `python3 -m unittest discover -s tests` — **baseline 902**.
Full Node: `npm test` — **371 pass on Node v26.4.0**. **Never pytest** (`-k` misses new classes).
The focused `-p 'test_skill_audit.py'` command is a development convenience only and is **never**
the acceptance command — selecting one file by pattern is the exact defect instance recorded at
`openspec/config.yaml:19,21,25`.

## Ordering and independence

**The surviving chain is fully sequential: 1 → 2 → 4 → 5.** No two surviving slices are parallel.

| Edge | Why, named rather than assumed |
|---|---|
| 2 after 1 | 2 parses a table 1 introduces. Landing 2 first ships a check whose only verdict is "there is no table" — a true finding about the wrong subject |
| 4 after 1, 2 | `check-report`'s self-application needs the report-shape table (1) and the roster mechanism (2) |
| 5 after 2, 4 | An unvalidated report is precisely the hand-maintained artefact this skill replaces |

The only parallel-capable pair the design proved (2 ∥ 3, disjoint subcommands, descriptors and
test classes) is dissolved by deferring 3. Rollback order reverses: 5 before 4, 4 before 2, 2
before 1.

---

## Phase 0 — Gates that precede the first RED (no commit)

- [x] 0.1 **Shell gate.** Confirm `Bash` is available. If it is not, **stop and report a blocker**
      (design R10); do not degrade to reading. Record the tool list observed.
- [x] 0.2 **Baselines, run and recorded verbatim.** `python3 -m unittest discover -s tests` →
      record `Ran N tests` (expect 902). `npm test` → record `# pass N` (expect 371) and
      `node --version` (expect v26.4.0). Both captures saved for the slice-5 report's before-side.
- [x] 0.3 **Name-freedom search, recorded as a table.** `rg --no-ignore --hidden -n
      'skill-audit|skill_audit|audit_cli'` over the repo root. `--no-ignore --hidden` is
      **load-bearing**: `firedrill` occurs at
      `implementations/Domain_Adaptation/src/MIL_CREDA_Benchmark/harness.py:1072`, invisible to a
      default search. Record: `| name | matches | verdict |`. Zero matches outside
      `openspec/changes/the-skill-that-audits-the-others/` is the pass condition. **This phase's
      Grep honours `.gitignore` and therefore could not decide this — the search is outstanding.**
- [x] 0.4 **Pin argparse's refusal wording.** Run `python3 --version` and
      `python3 -c "import argparse,sys;p=argparse.ArgumentParser();s=p.add_subparsers();s.add_parser('x');p.parse_args(['zzz'])"`;
      record the exact `invalid choice` rendering and the stream (stderr) and exit (2). Gates
      slice 2 (design R12).
- [x] 0.5 **Drive the D1 probe once by hand.** From a cwd with **no** project root, run
      `node .claude/skills/proposal-deliberation/engine/cli.mjs '{"operation":"__AUDIT_NONCE__","instruction":"probe"}'`.
      Record the refusal text, the stream (stdout) and the exit (1). Confirm nine names and that
      nothing was written. Pass/fail gates the whole change.
- [x] 0.6 **Re-verify the anchors this phase could only read** (§Anchor re-location), including the
      two corrections, before authoring against them.

## Phase 1 — Slice 1: doctrine core (PR 1, ~350 lines)

- [x] 1.1 RED — `tests/test_skill_audit.py`: assert `.claude/skills/skill-audit/SKILL.md` exists
      with frontmatter of **exactly `name` on line 2 and `description` on line 3**, `---` on 1 and
      4, and no `license`/`metadata`/`allowed-tools`. Spec Group 1, house shape five for five.
- [x] 1.2 RED — moves-table completeness: parse `| Move | Ships as | Lock |` with
      `markdown_table_rows`; assert exactly one row per move **0 through 7** plus exactly one row
      for the irreducibly textual move. Spec Group 1 / Group 2 (textual move).
- [x] 1.3 RED — moves-table typing: every row's `Ships as` cell names a subcommand of
      `audit_cli.py` **or** the literal `doctrine`; the textual move's row names no subcommand and
      is marked as carrying no lock. (Cross-check against argparse's real surface lands in 2.4.)
- [x] 1.4 RED — doctrine numeral rule: no numeral in `SKILL.md` states the size of an enumeration
      unless derived. Includes headings — the "seven-move table" heading enumerating moves 0–7
      **plus** a ninth textual row is corrected here under this rule, per spec §Acceptance.
- [x] 1.5 RED — activation contract: assert `SKILL.md` states no-shell as a **hard refusal** naming
      the missing capability and emitting no report/finding/candidate. Spec Group 1.
- [x] 1.6 RED — vocabulary guards, **copied** from `tests/test_proposal_implementation.py:62-63`:
      `FORGE_VOCABULARY_FLOOR` / `FORGE_LEXICON` disjointness.
- [x] 1.7 GREEN — author `.claude/skills/skill-audit/SKILL.md`: frontmatter; moves table (0–7 +
      textual); the seven failure modes of Group 3 as requirements; evidence ladder (Group 7);
      the three adjudications incl. `not adjudicable` with its own section; the eight-item report
      shape as a parseable table; Decision Gates as a two-column `| Situation | Action |` table
      (idiom: `paper-ingestion/SKILL.md:183-199`); handoff contract `mutations: 0`,
      `documentAuthority: FORBIDDEN`, `explicitHandoffRequired: true`; hard-refusal activation
      contract. **A skill cannot call SDD** — terminal state is a handoff, never an invocation.
- [x] 1.8 GREEN — create `.claude/skills/skill-audit/scripts/audit_cli.py` with `main(argv:
      list[str] | None = None) -> int`, argparse subparsers, `sys.exit(main())`, JSON to stdout
      with `sort_keys=True`, **stdlib-only**. Subparsers registered but not yet implemented beyond
      what 1.x asserts.
- [x] 1.9 **Inversion — moves-table completeness.** Delete move 5's row → assert the lock fires
      naming move 5 by number. Restore **by inverse patch, never `git checkout --`**; confirm with
      `cmp` and `shasum -c`, and `git diff --quiet` for the rest of the tree.
- [x] 1.10 **Inversion — moves-table typing.** Change one row's `Ships as` cell to a name that is
      neither a subcommand nor `doctrine` → fires naming that cell. Restore by inverse patch;
      confirm with `cmp`.
- [x] 1.11 **Inversion — numeral rule.** Insert an underived count into a heading → fires.
      Restore by inverse patch; confirm with `cmp`.
- [x] 1.12 **Inversion — lexicon/floor disjointness.** Add one floor word to `FORGE_LEXICON` →
      fires. Restore by inverse patch; confirm with `cmp`.
- [x] 1.13 **Inversion — frontmatter shape.** Add a `license:` key → fires. Restore by inverse
      patch; confirm with `cmp`.
- [x] 1.14 Run `python3 -m unittest discover -s tests`; confirm the count **rose** from 902 and
      record the new figure. Greenness alone is not evidence.
- [x] 1.15 Commit: `feat(skill-audit): the method that found twenty defects lived only in one session's head`

## Phase 2 — Slice 2: `roster` (PR 2, ~380 lines) — after Phase 1

- [x] 2.1 RED — **D3, the most dangerous failure mode.** An extraction matching nothing **raises**;
      it must never return an empty set. `roster` exits `0` for any verdict including findings and
      **`2`** when the probe could not be driven or the extraction matched nothing. Assert both
      exit codes are distinguishable. An empty code side makes every doctrine row a phantom — a
      broken probe dressed as a result.
- [x] 2.2 RED — refusal probe: driving `cli.mjs` as a **subprocess** with a nonce recovers the nine
      accepted operations from the refusal text alone, and **no operation name appears as a literal
      anywhere in the auditor**. Assert with `assertNotIn` against the auditor's own bytes. Spec
      Group 5. **Subprocess, never mock** — a wholesale double cannot hold a claim about a process.
- [x] 2.3 RED — token-present, not token-absent: omitting the operation key entirely produces no
      refusal, and `roster` reports the probe as having **yielded nothing**, never an empty
      accepted set (`cli.mjs:319` fires only when the key is present).
- [x] 2.4 RED — self-audit subcommand roster: drive `audit_cli.py` with a nonsense subcommand, take
      argparse's own refusal (wording pinned at 0.4, **stderr, exit 2**) as the roster, and hold it
      to the `| Subcommand | Derives | Emits |` table. Three sets, never a boolean.
- [x] 2.5 RED — **D2, the closure claim.** A doctrine table counts as a roster site **only if** its
      descriptor declares `scope` and quotes `headingVerbatim`, which `roster` then checks against
      disk. Without it, `.claude/skills/proposal-deliberation/SKILL.md:243-252` — headed
      `## Other engine operations`, a **complement set** of four rows — yields **five false
      `unregistered` rows**. Assert the honoured-scope path and the refused-scope path separately.
- [x] 2.6 RED — `no-closed-roster` as a **first-class result**: `SKILL.md` (complement),
      `references/usage.md:264-266` (prose, forbidden by soundness condition 5) and the `.mjs`
      test (a JS array) all emit `no-closed-roster` with the searched `file:line` range. It SHALL
      NOT raise, SHALL NOT exit non-zero as an error, and SHALL NOT report the surface as clean.
      This is the structural finding the proposal predicted.
- [x] 2.7 RED — `no derivation available for this surface` as a first-class result for a surface
      with neither probe (spec Group 5).
- [x] 2.8 RED — **soundness condition 1, mechanised.** Parse the `ast` of the doctrine-derivation
      function and assert its syntax tree contains **no reference of any kind** to the probe module
      or `subprocess` — not a call, not an import, not a borrowed constant. Forbidding only a
      *call for contents* is insufficient: `tests/test_proposal_implementation.py:267` is
      `for gap in impl.scaffold_gaps(box, name):` — a producer call deciding the **path set** — and
      `:270` borrows `impl.IGNORE_ENTRIES`, under a docstring at `:240` claiming a doctrine-faithful
      target.
- [x] 2.9 RED — three sets, never a boolean: `unregistered`, `phantom`, `duplicated` all present
      and independently populated; plus `numeralMismatch` and `notes`.
- [x] 2.10 RED — `duplicated` fires on hand-restatements **even when every restatement agrees**.
- [x] 2.11 RED — numeral check **excludes hedged numerals**. Read-confirmed necessity:
      `cli.mjs:20-21` says "~63 TS files" and "roughly 0.72s"; a check firing on those is noise, and
      noise gets exempted until it means nothing. Live target: `remote-execution/SKILL.md:19` says
      "Three modules exist so far" above bullets at `:21`, `:32`, `:50`, `:57` — **four**. Assert
      the finding names the numeral's `file:line` **and** the enumeration's `file:line`.
- [x] 2.12 RED — **threat matrix, subprocess composition** (the one Applicable row; N/A rows
      omitted): (a) a descriptor with `cwd: "../.."` escaping `--subject` → **refused**; (b) a
      descriptor argv containing `;` → passed as **one literal argument**, never interpreted
      (`subprocess.run(shell=False, ...)`, argv as a list, never a string); (c) a hanging subject →
      **timeout, exit 2**. The nonce is a fixed literal, never user text.
- [x] 2.13 RED — fixture-name precondition: every lock matching a needle against generated output
      asserts `assertNotIn(needle, fixture_name)` **first**, before its own assertion (Group 3).
- [x] 2.14 RED — reachability: a fixture that cannot reach the guarded branch fails as
      **unreachable** rather than passing (Group 3).
- [x] 2.15 RED — copied-helper byte-identity: `markdown_table_rows`, `returned_keys`,
      `dict_literal_keys`, `subcommand_surface` each byte-identical to their originals at
      `tests/test_proposal_implementation.py:82`, `:103`, `:9017`, `:9118`. **Copy, do not share** —
      sharing means editing a 75-class suite inside a change about a different skill.
- [x] 2.16 GREEN — implement `roster --subject <dir> --probe-spec <file>` in `audit_cli.py`:
      subprocess probe, descriptor-driven `stream`/`exit`/`extract`/`split`, table parse,
      heading-verbatim check, three sets, `numeralMismatch`, `notes`.
- [x] 2.17 GREEN — author
      `.claude/skills/skill-audit/references/probes/proposal-deliberation.accepted-operations.json`.
      `stream` and `exit` are **descriptor fields, not constants**: `cli.mjs` writes JSON to
      **stdout** and exits **1** (`cli.mjs:371-373`); argparse writes to **stderr** and exits **2**.
      A single hardcoded contract fits neither.
- [x] 2.18 GREEN — author `references/probes/skill-audit.subcommands.json` for the self-audit.
- [x] 2.19 GREEN — copy the four helpers into `tests/test_skill_audit.py` byte-identically.
- [x] 2.20 **Inversion — subcommand roster, both directions.** Add a subparser with no table row →
      `unregistered` fires naming it; delete a table row while its subparser remains → `phantom`
      fires naming it. Restore each by inverse patch; confirm with `cmp` and `shasum -c`.
- [x] 2.21 **Inversion — D3.** Corrupt the descriptor's `extract` → **exit 2**, not an empty `code`
      set. Restore by inverse patch; confirm with `cmp`.
- [x] 2.22 **Inversion — D2 heading verbatim.** Change `## Other engine operations` **in the
      fixture** (never in `proposal-deliberation`) → fires. Restore by inverse patch; confirm with
      `cmp`.
- [x] 2.23 **Inversion — soundness condition 1.** Add `import audit_cli` (and separately, a
      borrowed constant reference) to the derivation helper → fires naming the reference. Restore
      each by inverse patch; confirm with `cmp`.
- [x] 2.24 **Inversion — copied-helper drift.** Edit one copied helper → the drift lock fires naming
      the helper and **both** locations. Restore by inverse patch; confirm with `cmp`.
- [x] 2.25 **Inversion — numeral check.** Change a hedged numeral to unhedged → fires; and change an
      unhedged one to match its list → stops firing. Restore both by inverse patch; confirm `cmp`.
- [x] 2.26 Run the full discover; confirm the count **rose** again and record it.
- [x] 2.27 Commit: `feat(skill-audit): the roster four sites restate by hand was never derived from the running code`

## Phase 3 — Slice 4: `check-report` and `usage.md` (PR 4, ~280 lines) — after Phases 1–2

- [x] 3.1 RED — `check-report <file>` rejects a report omitting any of the eight items: ranked
      findings naming **both halves at `file:line`**; the move number; a per-finding
      `CONFIRMED by execution` **or** `read-only` marker with **no default**; a per-finding
      adjudication from the three values; `## Clean, stated as results`; `## Unchecked`; a
      falsifier; a changed-line forecast. Exit `0` valid, `1` invalid, `2` unreadable.
- [x] 3.2 RED — a finding citing a **single** `file:line` is rejected as a candidate, not a finding.
- [x] 3.3 RED — an entirely read-only report must state that fact in its **first line**; absence is
      a rejection.
- [x] 3.4 RED — a `## Clean` entry whose only support is that the suite passed is rejected. **A
      green suite is never evidence.**
- [x] 3.5 RED — a containment claim citing `git status` is rejected and the **manifest** is named as
      the required evidence. (`git status --porcelain` over `implementations/` is empty by
      construction.) `manifest` itself ships in the deferred slice; this rejection does not depend
      on it.
- [x] 3.6 RED — a finding whose evidence is a live request's success is rejected: a GET proves the
      environment answered, never a fact about the subject's code.
- [x] 3.7 RED — a report claiming a repository-wide count from **one** harness is rejected; the two
      harnesses are disjoint and no single command runs both.
- [x] 3.8 RED — planted-fixture test: a report fixture whose finding carries **no** marker **and
      whose filename does not contain the marker text** → rejected. The filename precondition is
      asserted first (Group 3).
- [x] 3.9 RED — report-schema self-description: **every** field `check-report` requires has a row in
      `SKILL.md`'s report-shape table, derived by `markdown_table_rows`, three sets both ways.
- [x] 3.10 GREEN — implement `check-report` in `audit_cli.py`.
- [x] 3.11 GREEN — author `.claude/skills/skill-audit/references/usage.md` with worked invocations
      of every shipped subcommand. Every documented invocation must be one that actually runs.
- [x] 3.12 **Inversion — report-marker requirement.** Plant a finding with no
      `CONFIRMED`/`read-only` marker → `check-report` rejects. Restore by inverse patch; `cmp`.
- [x] 3.13 **Inversion — both-halves requirement.** Reduce a finding to one `file:line` → rejects.
      Restore by inverse patch; `cmp`.
- [x] 3.14 **Inversion — schema self-description.** Delete one row from the report-shape table →
      `phantom` fires; add a required field with no row → `unregistered` fires. Restore each by
      inverse patch; confirm with `cmp` and `shasum -c`.
- [x] 3.15 Run the full discover; confirm the count **rose** and record it.
- [x] 3.16 Commit: `feat(skill-audit): the report shape this skill demands of others was enforced by its own prose`

## Phase 4 — Slice 5: the first damage report (PR 5, ~120 lines) — after Phases 2–3

- [x] 4.1 Run `roster` against `proposal-deliberation`'s accepted-operation surface using the real
      descriptor and the real installed `cli.mjs`. Capture stdout verbatim. **Move 2: the live
      subject on disk, never only fixtures.**
- [x] 4.2 Author `openspec/changes/the-skill-that-audits-the-others/audit-proposal-deliberation-operations.md`.
      Must carry: at least one **`CONFIRMED by execution`** finding; at least one
      **`not adjudicable`** finding (`SCIENTIFIC_WORKFLOW`, a `RouteMetricStage` at
      `engine/runtime-metrics.ts:3,14` refused as an operation at `cli.mjs:319-320` — **a stage is
      not an operation**, so pending a consumer of `routeStages` it is not a defect); the three
      hand-restated locations of the operation set with the **executed** set as deciding evidence;
      `## Clean, stated as results`; `## Unchecked`; a falsifier; a changed-line forecast.
- [x] 4.3 RED/GREEN — a lock asserting the shipped report passes `check-report` with exit `0`.
- [x] 4.4 **Report only. Fix nothing.** Assert `mutations: 0` against
      `.claude/skills/proposal-deliberation/`: no file under that tree differs. The wall between
      reporting and fixing **is the product** — even a one-line `phantom` deletion is not made here.
- [x] 4.5 Run **both** suites: full discover (record the final count and its rise from 902) and
      `npm test` (expect 371 unchanged — this change adds no `.mjs`). Report both **separately**.
- [x] 4.6 Confirm `implementations/Domain_Adaptation` was never edited. **Without a `manifest`
      subcommand** (deferred), use a hand-taken `shasum -r` listing before and after and record it
      as the interim evidence, explicitly marked as the gap slice 3 closes. Never `git status`.
- [x] 4.7 Commit: `docs(skill-audit): the auditor shipped with no audit to its name`

---

## Anchor re-location (this phase, read-only)

Every citation the tasks lean on was re-opened against disk rather than inherited. Two earlier
phases' citations pointed at enclosing `def` lines rather than call sites, so this was not
optional.

| Anchor | Design said | Disk says | Verdict |
|---|---|---|---|
| `engine/cli.mjs:319-321` | refusal emits the complete accepted set | `:319` guard, `:320` `UNKNOWN_OPERATION: … is not one of ${[...HOST_OPERATIONS, ...TOOL_OPERATIONS].join(', ')}` | **confirmed** |
| `engine/cli.mjs:333` | `validateRequest` is `run()`'s first statement | `:332` `async function run(request) {`, `:333` `validateRequest(request);` | **confirmed** — probe cannot mutate by construction |
| `engine/cli.mjs:371-373` | stdout + exit 1 | `:372` `process.stdout.write(...)`, `:373` `process.exit(1)` | **confirmed** |
| `engine/cli.mjs:21` hedged numerals | "roughly 0.72s" and "~63 TS files" both at `:21` | "~63 TS files" is at **`:20`**; "roughly 0.72s" at `:21` | **correction — cite `:20-21`** |
| `proposal-deliberation/SKILL.md:243-252` | `## Other engine operations`, complement, 4 rows | `:243` heading, `:245-250` four rows, `:252` "the other three … None of the four" | **confirmed** |
| `test_proposal_implementation.py:267` | `for gap in impl.scaffold_gaps(box, name):` | exact, and `:270` `impl.IGNORE_ENTRIES`, docstring `:240` | **confirmed — a call site, not a `def`** |
| helpers `:82 :103 :9017 :9118` | four helpers, one file | `markdown_table_rows:82`, `returned_keys:103`, `dict_literal_keys:9017`, `subcommand_surface:9118` | **confirmed** |
| `FORGE_VOCABULARY_FLOOR` `:62-63` | copyable guard | exact | **confirmed** |
| `…cli-operation-surface.test.mjs:88-98` | MAINTENANCE idiom | `:88` test name, `:92-97` `delegation_permitted`, `mutations: 0`, `documentAuthority: FORBIDDEN`, `explicitHandoffRequired: true` | **confirmed** (design's `:92-97` inner range is the precise one) |
| `remote-execution/SKILL.md:19` | "Three modules exist so far" above four bullets | `:19` exact, `:21` first bullet | **confirmed** |
| House frontmatter | `name` line 2, `description` line 3 | `paper-ingestion/SKILL.md:1-4` exact | **confirmed** |
| Name freedom | `skill-audit`/`skill_audit`/`audit_cli` free | `Glob` (ignores `.gitignore`, negatives real) → **no files**. `Grep` → only this change's four artifacts, **but it honours `.gitignore` and could not see `implementations/`** | **UNRESOLVED — task 0.3** |

## Spec-level assumptions carried (binding unless the user says otherwise)

The proposal's five questions were never asked — no interactive facility in any phase. Their
stated assumptions are carried forward and encoded above:

1. The report/fix wall is **absolute**; no opt-in "obvious repairs" path (task 4.4).
2. A clean surface still gets the **full report**, so an empty `## Clean` section is
   distinguishable from an unrun one (task 3.1).
3. The auditor **proposes a slicing and asks**, through the interactive question facility, never a
   question typed into a reply (doctrine, task 1.7).
4. The irreducibly textual move is **carried, marked as having no lock** (tasks 1.2, 1.3).
5. No shell is a **hard refusal**, not a degraded mode (tasks 0.1, 1.5).

## Named non-goals apply must not drift into

Both are live instances of this skill's own defect class. **Recorded, not fixed** — naming them
here so apply does not wander in.

- `openspec/config.yaml:19,21,25` selects **one** Python file with `-p 'test_extract_pdf.py'` and
  uses a node glob differing from `package.json`'s. A config change with its own blast radius; its
  own change.
- The **"seven-move table"** that enumerates eight moves (0–7) plus a ninth textual one. The
  heading is corrected inside `skill-audit`'s own doctrine under the Group 1 numeral rule
  (task 1.4); the proposal's and design's prose are not edited here.
- Anything under `implementations/Domain_Adaptation` — **never edited**.
- Anything in `proposal-deliberation` — the report names it, the change never touches it.
- **Nothing is sent to a remote service.** This change makes no live call of any kind.

## Deferred to the follow-up change

- [ ] Slice 3: `manifest --root <dir> [--baseline <file>]` and `counts --before <f> --after <f>`,
      with their inversions and spec Group 6 in full.
- [ ] Success criterion 6 (`manifest` proves a box cleaned and `Domain_Adaptation` untouched,
      without `git status`).
- [ ] Success criterion 8 as `counts` evidence (the rise from 902 is still proven here by running
      the harness — task 4.5 — just not by `counts`).

## Note on artifact size

This artifact exceeds the 530-word tasks guidance, deliberately and for the same reason the design
recorded as R14: the phase brief specifies six mandatory contents, including a per-lock inversion
task and a re-located anchor table. Density is carried by tables rather than prose. Compressing it
would drop the inversion tasks, which are the change's own doctrine applied to itself.
