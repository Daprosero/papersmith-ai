# SDD Project Context: papersmith-ai

## Session
- Init date: `2026-09-09`
- Artifact store: `both` (hybrid: `openspec/` files + Engram observations)
- Strict TDD: `true` (marker in `openspec/config.yaml`; test runner present)
- Full test command: `pnpm test:all` (`pnpm test` + `pytest`)

## Workspace
- Root: `/home/carlos/Documents/projects/papersmith-ai`
- Git root: recognized by `git rev-parse`
- Entrypoints: `AGENTS.md` (routes to `openspec/project-context.md`, `guidance/paper-guide/`, `.opencode/skills/*/SKILL.md`)
- No `AGENTS.md`, `GEMINI.md`, or `.cursorrules` present

## Stack signals
| Area | Signal |
| --- | --- |
| Runtime | Mixed Python (>=3.11) + Node.js (ESM, `type: module`) repository |
| Python | src-layout package `papersmith` (`src/papersmith/{core,bridges,mcp}`, `pipx install .`, entrypoint `papersmith.cli:main`) |
| Python deps | `requests`, `nbformat`, `nbclient`, `ipykernel`, `numpy`, `pytest`, `torch`, `PyMuPDF`, `PyYAML`, `jsonschema`, `kagglesdk==0.1.37` (`requirements.txt`) |
| Node deps | `jiti`, `typebox`, `typescript`, `@types/node` (`package.json`, `tsconfig.json`); `pnpm typecheck` (`tsc`); no eslint/prettier |
| Config | `pyproject.toml` (setuptools src-layout, pytest `testpaths`, ruff lint `E,F,W,I`), `papersmith.yaml` (ingestion engine/mode) |
| Measured runtime | `node v26.8.1`, `.venv` Python `3.14.7`, `pytest 9.1.0` |
| Repo markers | `requirements.txt`, `tests/`, `.opencode/`, `src/`, `docs/`, `guidance/`, `scripts/`, `openspec/`, `papersmith.yaml`, `tsconfig.json` |

## Architecture
- `src/papersmith/core/` — init, status, ingest, upgrade, executor, ledger
- `src/papersmith/bridges/` — Node, Python, deliberation, remote-execution bridges
- `src/papersmith/mcp/` — stdio Model Context Protocol server exposing workspace and paper-writing verbs
- `.opencode/skills/` — native skill tree (`experimental-deliberation`, `experimental-implementation`, `figure-review`, `kaggle-accounts`, `paper-ingestion`, `paper-writing`, `proposal-deliberation`, `proposal-implementation`, `remote-execution`, `skill-audit`); `.opencode/agents/` holds the 17 subagents
- `guidance/paper-guide/` — domain guidelines; `scripts/setup_env.py` — isolated runtime provisioning
- CI (`.github/workflows/test.yml`): Node suite (`pnpm install --frozen-lockfile` + `pnpm test`) and Python suite (`pip install -r requirements.txt`, `pytest` on 3.11/3.12)

## SDD config summary
- `openspec/config.yaml` exists with `strict_tdd: true`
- `apply.test_command` and `verify.test_command` both point to `pnpm test:all`
- `openspec/changes/` holds active changes; `openspec/changes/archive/` holds completed changes
- `openspec/specs/` is the (currently empty) source-of-truth directory
- `.atl/skill-registry.md` indexes project/user skills (refreshed 2026-09-09)

## Persistence conventions
- `openspec/changes/<change>/` stores proposal, spec, design, tasks, and verify artifacts
- `openspec/changes/archive/YYYY-MM-DD-<change>/` stores completed changes (audit trail, never modified)
- `openspec/specs/<domain>/spec.md` is the merged source of truth (populated by sdd-archive)
- Engram mirrors: `sdd-init/papersmith-ai`, `sdd/papersmith-ai/testing-capabilities`, `skill-registry`

## Notes
- This refresh supersedes the stale 2026-07-16 record (pointed at a `/Users/diego/...` root, `node v26.4.0`/`python3 3.9.6`, and a `.venv/.../unittest` command that no longer matches `package.json` or CI; the Python suite runs under `pytest`).
- `ruff` is configured in `pyproject.toml` but its binary is not installed in `.venv` or on PATH; no type checker, formatter, or coverage tool is configured.
- No application code was modified during init.
