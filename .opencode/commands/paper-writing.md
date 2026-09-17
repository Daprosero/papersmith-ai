---
description: Escribir el paper bloque por bloque con cada afirmacion atada a evidencia
agent: build
---

Load the `paper-writing` skill via the skill tool and follow `.claude/skills/paper-writing/SKILL.md` exactly. Stdlib-only, keyless CLI (`scripts/paper_cli.py`).

Subagents available: `@insumos-observer` (observe five facts), `@redactor` (draft one block), `@contract-auditor` (judge a draft), `@style-sampler` (resolve style samples), `@diagram-author` (author one TikZ diagram via render). Discovery runs through the agent's own MCP servers; resolution stays CLI-side over stdlib urllib (OpenAlex/Crossref/arXiv).
