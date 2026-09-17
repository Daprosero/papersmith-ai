---
description: Enviar trabajo a workers remotos y llevar el registro de lo que volvio
agent: build
---

Load the `remote-execution` skill via the skill tool and follow `.claude/skills/remote-execution/SKILL.md` exactly.

Always route launches through `scripts/remote_cli.py submit` (or `--smoke` for rehearsals). Never invoke push surfaces (`kernels_push`, `kaggle_driver.py`) directly: the `.opencode/plugins/refuse-offpath-push.js` guard will refuse it. Worker identity comes only from `kaggle-accounts list --json`, never from a pasted secret.
