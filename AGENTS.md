# Papersmith AI — OpenCode Entrypoint

Native OpenCode project. Skills, agents, and commands live under `.opencode/`;
this file is the only routing doc — read the canonical source before acting.

## Canonical context

- **Workspace configuration**: `papersmith.yaml`
- **Skills**: `.opencode/skills/*/SKILL.md` — the source of truth per capability.
  Read the skill before invoking it.
- **Agents**: `.opencode/agents/*.md` — one stretch each, `mode: subagent`,
  model pinned in frontmatter. The filename is the agent ID.
- **Slash commands**: `.opencode/commands/<skill>.md` — one per skill, body
  loads that skill's `SKILL.md` with your text as `$ARGUMENTS`. Generated
  artifact: `papersmith audit --check-drift` reports drift, `papersmith
  upgrade` restores. Do not edit by hand.

## Model policy

- Default primary: `opencode-go/mimo-v2.6-flash` (see `opencode.json`).
- `deliberation-publish` runs `opencode-go/mimo-v2.6-pro` and nothing else
  runs it — the scarcest math gate stays exclusive.
- `opencode-go/muse-spark-1.3-contributor` trains on prompts: it only hosts
  `paper-ingestion` and `style-sampler` (published references, verbatim
  copies). Nothing that reads or writes unpublished paper, proposals, or
  code runs on it.

## Safety plugin

`.opencode/plugins/refuse-offpath-push.js` is generated and auto-discovered.
It relays every shell invocation to
`.opencode/skills/remote-execution/scripts/hooks/refuse_offpath_push.py`, so
the predicate has exactly one authority. It refuses — with a thrown error
naming the matched surface — a command that names a service's push surface
without also invoking `remote_cli.py`, and it degrades loudly rather than
silently allowing when the guard cannot be loaded. Tripwire, not gate.
