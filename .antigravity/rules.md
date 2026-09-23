# Papersmith AI — Google Antigravity Rules

Minimal harness entrypoint. This file does not duplicate guidance; it only routes
to the canonical sources of truth so a single set of docs drives every harness.

## Canonical context

- **Project context**: `openspec/project-context.md`
- **Domain guidelines**: `guidance/paper-guide/`
- **Available capabilities (skills)**: `skills/*/SKILL.md`

## Skills

Skills live once at the repository-root `skills/` tree and are projected into
`.antigravity/skills` by `npm run setup:harnesses`. Read each skill's `SKILL.md`
before invoking it; it is the source of truth for that capability.

## Invoking skills

Antigravity receives no generated slash commands — only `claude` and `opencode`
produce command files. Invoke a capability by asking for it by name; the agent
reads `skills/<name>/SKILL.md` before the work starts, and that file remains the
source of truth.
