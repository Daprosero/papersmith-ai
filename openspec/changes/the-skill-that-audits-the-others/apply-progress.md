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
