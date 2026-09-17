---
description: Deliberar el diseno experimental que pondra a prueba la propuesta
agent: build
---

Load the `experimental-deliberation` skill via the skill tool and follow `.claude/skills/experimental-deliberation/SKILL.md` exactly. Become the experimental-design tutor for this deliberation.

Steps: call the engine's `STATUS` first (`node .claude/skills/experimental-deliberation/cli.mjs '{"operation":"STATUS"}'`), resolve the base the same way as proposal-deliberation, deliberate in conversation, preview the successor, surface every loss, get operator acceptance via the question tool, then delegate the terminal publish stretch to the `experimental-publish` subagent (`@experimental-publish`). The `validated` stage may be delegated to `@experimental-validation`.
