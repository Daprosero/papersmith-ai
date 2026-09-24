# papersmith workspace — generated files and local state
.micromamba/
.venv/
node_modules/
__pycache__/
*.pyc
.scratch/
.env*
.papersmith/runs_ledger.jsonl
skills/paper-ingestion/.venv/
kaggle-inbox/*
!kaggle-inbox/.gitkeep

# Research content: the folder travels, its contents stay home. Every entry
# here mirrors this framework's own root .gitignore — a workspace is meant to
# reach the same "structure versioned, content local" contract this repo
# holds itself to, so nobody's papers, proposals, or run products leave their
# machine by accident. `sections/` is deliberately NOT listed: it travels with
# content, like `skills/`, because the ten section contracts are generic
# writing scaffolding, not this workspace's own research.
guidance/*/*
!guidance/*/.gitkeep
proposals/*
!proposals/.gitkeep
paper/*
!paper/.gitkeep
experiments/*
!experiments/.gitkeep
implementations/*
!implementations/.gitkeep
