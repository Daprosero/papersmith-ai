# SDD Project Context: papersmith-ai

## Session
- Change seed: `scientific-reasoning-workflow`
- Artifact store: `both`
- Memory backend: Engram unavailable in this session; OpenSpec is the persisted backend for this refresh

## Workspace
- Root: `/Users/diego/Desktop/Proyectos/papersmith-ai`
- Git root: not recognized by `git rev-parse` from this directory
- CodeGraph: `.codegraph/` is missing; init attempt failed because the root was not recognized as a CodeGraph project

## Stack signals
| Area | Signal |
| --- | --- |
| Runtime | Mixed Python + Node.js repository |
| Python deps | `PyMuPDF`, `PyYAML`, `jsonschema` |
| Test signals | Node built-in `node:test` suites in `tests/*.test.mjs`; Python `unittest` suite in `tests/test_extract_pdf.py` |
| Repo markers | `requirements.txt`, `tests/`, `.pi/`, `openspec/`, `papersmith.yaml` |

## SDD config summary
- `openspec/config.yaml` exists
- `strict_tdd: false`
- No reliable single test runner was detected
- Proposal/spec/design/tasks rules are enabled
- `apply.test_command` and `verify.test_command` are blank

## Notes
- `.atl/skill-registry.md` exists and indexes project/user skills
- No application code or proposal content was modified during init
