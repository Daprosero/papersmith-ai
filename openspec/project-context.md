# SDD Project Context: papersmith-ai

## Session
- Change seed: `scientific-reasoning-workflow`
- Artifact store: `both`
- Memory backend: Engram unavailable in this session; OpenSpec is the persisted backend for this refresh

## Workspace
- Root: `/Users/diego/Desktop/Proyectos/papersmith-ai`
- Git root: recognized by `git rev-parse`
- CodeGraph: `.codegraph/` exists; the MCP proxy was unavailable in this session, so filesystem-backed verification was used

## Stack signals
| Area | Signal |
| --- | --- |
| Runtime | Mixed Python + Node.js repository |
| Python deps | `PyMuPDF`, `PyYAML`, `jsonschema` |
| Test signals | Node built-in `node:test` suites in `tests/*.test.mjs`; Python `unittest` suite in `tests/test_extract_pdf.py` |
| Runtime versions | `node v26.4.0`, `python3 3.9.6` |
| Repo markers | `requirements.txt`, `tests/`, `.pi/`, `openspec/`, `papersmith.yaml` |

## SDD config summary
- `openspec/config.yaml` exists
- `strict_tdd: true`
- Proposal/spec/design/tasks rules are enabled
- `apply.test_command` and `verify.test_command` point to the combined Node + Python test command
- Detected runnable suites: `node --test tests/*.test.mjs` and `python3 -m unittest discover -s tests -p 'test_extract_pdf.py'`

## Persistence conventions
- `.paper-proposal-v2/state/*.json` stores derived document state by revision; current example: `research-concept-r01.md.json`
- `.paper-proposal-v2/receipts/` stores document receipts; no receipt files were present during this refresh
- `.paper-proposal-v2/withdrawn/<operationId>/` stores withdrawn-revision metadata and audit markers; current example: `1ebc189c-da54-4b94-9d26-ea3e68a71adb`
- `openspec/changes/<change>/` stores proposal, spec, design, tasks, and apply-progress artifacts
- `openspec/project-context.md` is the file-backed init record for this refresh

## Notes
- `.atl/skill-registry.md` exists and indexes project/user skills
- Existing persistent state was verified at `.paper-proposal-v2/state/research-concept-r01.md.json`
- No application code or proposal document was modified during init
