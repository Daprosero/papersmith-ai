# Papersmith AI — Claude Code Entrypoint

Minimal harness entrypoint. This file does not duplicate guidance; it only routes
to the canonical sources of truth so a single set of docs drives every harness.

## Canonical context

- **Project context**: `openspec/project-context.md`
- **Domain guidelines**: `guidance/paper-guide/` (user drop-zone; loaded automatically by `proposal-deliberation`, optional at rest)
- **Available capabilities (skills)**: `skills/*/SKILL.md`

## Skills

Skills live once at the repository-root `skills/` tree and are projected into
`.claude/skills` by `npm run setup:harnesses`. Read each skill's `SKILL.md`
before invoking it; it is the source of truth for that capability.

## Slash commands

The nine top-level skills are projected as Claude Code slash commands under
`.claude/commands/` by `python scripts/sync-repo-harness.py`. Each command body
loads its `skills/<name>/SKILL.md` and takes your text as `$ARGUMENTS`. That
directory is a derived artifact — regenerate it with the script (`--check` reports
drift and exits non-zero) instead of editing it by hand.
