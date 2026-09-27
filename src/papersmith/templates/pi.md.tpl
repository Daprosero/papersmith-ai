# {{title}} — Pi Runtime

Pi appends this file to the project system prompt. The workspace's agent
definitions come from the canonical `.claude/agents/` tree and its skills from
the canonical `skills/` tree, both projected by `papersmith` {{version}}.

Read `papersmith.yaml`, `guidance/paper-guide/`, and the applicable
`skills/*/SKILL.md` before working on the paper.

## Agents

{{agents}}

## Skills

Pi discovers this workspace's skills through `.pi/settings.json`, whose
`"../skills"` entry resolves from the project `.pi/` directory to the canonical
`skills/` tree. Pi exposes each loaded skill natively as `/skill:<name>`
(`enableSkillCommands` defaults to true), so no command files are generated for
Pi — generating them would duplicate nine commands that already exist. Read the
applicable `skills/<name>/SKILL.md`; it remains the source of truth.

## Precedence

A trusted project `.pi/APPEND_SYSTEM.md` takes precedence over the operator's
own `~/.pi/agent/APPEND_SYSTEM.md`, and the two are never combined. This file
therefore suppresses the operator's own system-prompt append inside this
workspace.

## Safety extension

`.pi/extensions/refuse-offpath-push.ts` is generated and loaded by Pi from the
project `.pi/` directory. It relays each `bash` invocation to the
`remote-execution` skill's own `refuse_offpath_push.py`, so the predicate has
exactly one authority and a second service is covered by that service's own
adapter. It blocks — by returning `{ block: true, reason }` naming the matched
surface — a command that names a service's push surface without also invoking
`remote_cli.py`, and it degrades loudly rather than silently allowing when the
guard cannot be loaded. It is a tripwire, not a gate.
