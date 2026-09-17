---
description: Deliberar la matematica y publicar revisiones gestionadas
agent: build
---

Load the `proposal-deliberation` skill via the skill tool and follow `.claude/skills/proposal-deliberation/SKILL.md` exactly. Become the mathematical tutor for this deliberation.

Steps: call the engine's `STATUS` operation first (`node .claude/skills/proposal-deliberation/cli.mjs '{"operation":"STATUS"}'`), never eyeball `proposals/` yourself. If no managed revision exists, create v1 via `CREATE_INITIAL_REVISION`. Otherwise deliberate in conversation, resolve the target entry, preview the successor, show every equation/tag/citation that would disappear, get explicit operator acceptance via the question tool, then delegate the terminal publish stretch to the `deliberation-publish` subagent (`@deliberation-publish`).
