# Papersmith AI — `.agents` directory (Google Antigravity)

This directory holds two things for Antigravity: `agents/`, which is generated
from `.claude/agents/` and versioned, and `skills`, which is **generated**, not
versioned.

`agents/<name>.md` files are derived by `python scripts/sync-repo-harness.py`
(`--check` reports drift). Edit `.claude/agents/`, never the generated files.

```
npm run setup:harnesses
```

That command links `.agents/skills -> ../skills`, the one canonical tree every
harness reads. Antigravity invokes each skill as `/name`. The link is a relative
symlink rebuilt on demand rather than another copy of the skills.

`.antigravity/skills` is a second link to the same tree, kept for now for
workspaces that already reference it. `.antigravity/rules.md` is the generated
Antigravity entrypoint.

This file exists so the directory itself travels with the repository.
