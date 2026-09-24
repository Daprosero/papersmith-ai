# Papersmith AI — OpenCode Entrypoint

Minimal harness entrypoint. This file does not duplicate guidance; it only routes
to the canonical sources of truth so a single set of docs drives every harness.

## Canonical context

- **Project context**: `openspec/project-context.md`
- **Domain guidelines**: `guidance/paper-guide/` (user drop-zone; loaded automatically by `proposal-deliberation`, optional at rest)
- **Available capabilities (skills)**: `skills/*/SKILL.md`

## Skills

Skills live once at the repository-root `skills/` tree and are projected into
`.opencode/skills` by `npm run setup:harnesses`. Read each skill's `SKILL.md`
before invoking it; it is the source of truth for that capability.

## Slash commands

The nine top-level skills are projected as OpenCode slash commands under
`.opencode/commands/` by `python scripts/sync-repo-harness.py`. Each command body
loads its `skills/<name>/SKILL.md` and takes your text as `$ARGUMENTS`. That
directory is a derived artifact — regenerate it with the script (`--check` reports
drift and exits non-zero) instead of editing it by hand.

## Safety plugin

`.opencode/plugins/refuse-offpath-push.js` is generated and auto-discovered. It
relays every `bash` invocation to
`skills/remote-execution/scripts/hooks/refuse_offpath_push.py`, so the predicate
has exactly one authority. It refuses — with a thrown error naming the matched
surface — a command that names a service's push surface without also invoking
`remote_cli.py`, and it degrades loudly rather than silently allowing when the
guard cannot be loaded. It is a tripwire, not a gate.
