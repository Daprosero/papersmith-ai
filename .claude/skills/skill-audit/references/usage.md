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

## Exit codes, in one place

| Exit | `roster` | `check-report` |
| --- | --- | --- |
| `0` | it looked, and this is the verdict | the report is valid |
| `1` | not used | the report is invalid |
| `2` | it could not look | the report could not be read |
