---
description: Validar o remover credenciales de Kaggle (validate / remove / materialize)
agent: build
---

Load the `kaggle-accounts` skill via the skill tool and follow `.claude/skills/kaggle-accounts/SKILL.md` exactly. Stdlib-only, never prints credential values.

Ask via the question tool whether to validate or remove; `materialize` is code-only (writes one worker's token to a file and prints the path, never the value). Credentials never leave disk.
