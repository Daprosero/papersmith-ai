---
description: Ingerir PDFs de referencia a Markdown legible (LaTeX + tablas + figuras)
agent: build
---

Load the `paper-ingestion` skill via the skill tool and follow `.claude/skills/paper-ingestion/SKILL.md` exactly. Every rule lives there.

Steps: run the discovery script with `--list` first (reads `papersmith.yaml`, never touches files), report loose PDFs and unfiled ones, then ask the user which ones to ingest via the question tool. Only after approval, run the script again with the approved paths. Engines stay canonical under `.claude/skills/paper-ingestion/`.
