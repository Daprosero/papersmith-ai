# Worked invocations

Every invocation below is one that runs, from the repository root, exactly as
written. A reference documenting a command nobody can type is the same defect
this skill is pointed at other people's documents to find, so a lock drives
each of these and requires JSON on stdout.

## `roster` against the first subject

Derives the accepted-operation set of the deliberation host by driving it as a
real process and reading the roster out of its own refusal, then holds that
against every documented site the recipe declares.

```
$ python3 .claude/skills/skill-audit/scripts/audit_cli.py roster --subject .claude/skills/proposal-deliberation --probe-spec .claude/skills/skill-audit/references/probes/proposal-deliberation.accepted-operations.json --repo-root .
```

Exit `0`. Read `comparison` before reading the sets: `not-run` means no site
carried a closed roster, so `unregistered` is deliberately empty rather than
clean. `notes` names each site and the range that was searched.

## `roster` against the auditor itself

The same move, pointed back at this tool. `argparse`'s own refusal is the
roster, and the documented side is the subcommand table in `SKILL.md`.

```
$ python3 .claude/skills/skill-audit/scripts/audit_cli.py roster --subject .claude/skills/skill-audit --probe-spec .claude/skills/skill-audit/references/probes/skill-audit.subcommands.json --repo-root .
```

Exit `0`, with `unregistered` and `phantom` both empty. Add a subparser without
adding its row and `unregistered` names it; delete the row and leave the
subparser and `phantom` names it.

## `check-report` against a report

```
$ python3 .claude/skills/skill-audit/scripts/audit_cli.py check-report .claude/skills/skill-audit/references/example-report.md
```

Exit `0` and an empty `violations` list. Exit `1` lists what is missing, each
violation naming the item, why it matters, and where. Exit `2` means the report
could not be read at all, which is not the same claim as reading an invalid one.

## `structure` against the auditor's own layout

Derives the declared side from `SKILL.md`'s own `## The shipped files` table,
the on-disk side by walking `--subject` itself, and the from-zero side by
running the recipe's own `git archive` + `tar` steps inside a fresh, empty box
under `implementations/`, then removes the box and adjudicates arithmetically.

```
$ python3 .claude/skills/skill-audit/scripts/audit_cli.py structure --subject .claude/skills/skill-audit --spec .claude/skills/skill-audit/references/probes/skill-audit.structure.json --repo-root .
```

Exit `0` for any verdict, `outcome` included. Against an uncommitted change
this reads `builder-broken` — the from-zero side is built from `HEAD`, so a
file added on disk but not yet committed is genuinely absent from a fresh
install, and that is documented as accurate rather than papered over.

## `walkthrough` against the auditor's own first-run flow

Drives an ordered sequence of real invocations against one shared box under
`implementations/`: `check-report` refusing to read a report that does not
exist yet, `check-report` accepting the shipped example, and `roster` against
the auditor's own subcommand surface. Each step is held to its own declared
`expect`; the first step whose observation contradicts it is the stall.

```
$ python3 .claude/skills/skill-audit/scripts/audit_cli.py walkthrough --subject .claude/skills/skill-audit --spec .claude/skills/skill-audit/references/probes/skill-audit.first-run.json --repo-root .
```

Exit `0` for any verdict, `stall` included. A `null` `stall` means every step
matched its own expectation; a non-`null` `stall` names the step's index and
kind, and `unreached` lists every gate at or after it. A step may declare
`"role": "setup"` to stand up a fixture without asserting anything about the
subject; a setup step is never counted among `gates.passed`, and its failure
is reported directly as `"setup-failed"` at exit `2` -- never `"stalled"` --
because a void run has no unchecked gates, it has no run.

## `reading-diff` against the shipped reading pair

Two supplied readings of the same prose surface -- this skill's own
subcommand table -- compared by mechanical diff. Neither reading calls
`doctrine_side` or `probe_code_side`; a subcommand, not a flag, is what
keeps `comparison` at `not-run` for this surface permanently, whatever the
two readers agree on.

```
$ python3 .claude/skills/skill-audit/scripts/audit_cli.py reading-diff --surface subcommands --reading .claude/skills/skill-audit/references/probes/skill-audit.reading-a.json --reading .claude/skills/skill-audit/references/probes/skill-audit.reading-b.json
```

Exit `0`, `agreement: "single-reading"` -- both readers name the same five
subcommands, so `onlyIn` is empty on both sides. `comparison` stays
`"not-run"` regardless: two readers agreeing proves the prose has one
reading, never that it is closed. `candidates` carries the shared set, for
a caller to drive as `walkthrough` gates next; `reading-diff` itself never
runs a process.

## Exit codes, in one place

| Exit | `roster` | `check-report` | `structure` | `walkthrough` | `reading-diff` |
| --- | --- | --- | --- | --- | --- |
| `0` | it looked, and this is the verdict | the report is valid | it looked, and this is the outcome | it looked, `stall` included | it compared, agreement or divergence |
| `1` | not used | the report is invalid | not used | not used | not used |
| `2` | it could not look | the report could not be read | a side could not be derived, the box was not empty, or the build escaped it | a step declared no expectation, the box was not empty, the flow was never entered, a `kind: "setup"` step failed (`"setup-failed"`), or the recipe declared no `"gate"` step at all | not exactly two `--reading` flags, or a reading file could not be read or named an empty `members` list |
