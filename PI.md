# Papersmith AI — Pi Entrypoint

Minimal harness entrypoint. This file does not duplicate guidance; it only routes
to the canonical sources of truth so a single set of docs drives every harness.

## Canonical context

- **Project context**: `openspec/project-context.md`
- **Domain guidelines**: `guidance/paper-guide/` (user drop-zone; loaded automatically by `proposal-deliberation`, optional at rest)
- **Available capabilities (skills)**: `skills/*/SKILL.md`

## Skills

Skills live once at the repository-root `skills/` tree and are projected into
`.pi/skills` by `npm run setup:harnesses`. Read each skill's `SKILL.md`
before invoking it; it is the source of truth for that capability.

## Invoking skills

Every top-level skill under `skills/` is also generated as a Pi prompt template
in `.pi/prompts/<name>.md`, so it can be invoked as `/<name>`. Each template
loads that skill's `SKILL.md` and passes your text through as `$ARGUMENTS`. The
directory is a framework artifact: regenerate it with `python scripts/sync-repo-harness.py`
(`--check` reports drift), so do not edit it by hand.

## Agents

Subagent definitions are projected from `.claude/agents/` into `.pi/agents/` by
`python scripts/sync-repo-harness.py`. Pi core has no sub-agents: those files are
read only when the third-party `pi-subagents` package is installed. Edit the
source in `.claude/agents/`, never the projection.

## Safety extension

`.pi/extensions/refuse-offpath-push.js` is generated. It registers a `tool_call`
handler that relays `bash` commands to
`skills/remote-execution/scripts/hooks/refuse_offpath_push.py` and blocks only
when the guard exits with status `2`; it fails open when the guard, python or
the event is unusable. It is a tripwire, not a gate. See `docs/guard-hooks.md`.
