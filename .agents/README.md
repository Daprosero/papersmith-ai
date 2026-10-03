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

`.antigravity/skills` is a second link to the same tree, and
`.antigravity/rules.md` is the generated routing document. Neither location
appears in Antigravity's documentation (the documented ones are `.agents/skills`,
`AGENTS.md` / `GEMINI.md` and `.agents/rules`); they are kept for compatibility
until the user decides whether to move them. See
`docs/harness-support-matrix.md`. No guard is generated for Antigravity until its
hook input schema is sourced (`docs/guard-hooks.md`).

This file exists so the directory itself travels with the repository.
