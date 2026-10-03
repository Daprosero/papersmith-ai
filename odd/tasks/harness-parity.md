# Feature: harness parity (skills, commands, agents/plugins in every harness; init wires all)

## Objective
Skills, slash commands, and agents/plugins work in each harness (Claude Code, OpenCode, Pi, Google Antigravity), and `papersmith init` / `upgrade` wire all of them automatically, reporting honestly what is wired, unsupported, failed or blocked.

## Problem (verified baseline, e1feb9b)
- `link_harness_skills` swallows `OSError` (manifest.py:229) and silently skips a real directory at a link path (manifest.py:219-220); init cannot report either.
- `.pi/agents` is generated in workspaces but absent from the checkout (`PROJECTION` in scripts/sync-repo-harness.py omits it).
- OpenCode and Antigravity have no agents; Antigravity has no commands; "unsourced" claims in rules docs.
- Link roster is stated three times (setup-harnesses.sh, HARNESS_SKILL_LINKS, health_inspector._FALLBACK_SKILL_LINKS).

## Decisions (Judgment Day APPROVED: round 1 + scoped re-judgment; plan v3 = scratchpad plan_v3_frozen.md, sha256 82b2c757...)
- J1: never write `.claude/settings.json` (gitignored, user-owned; tests/test_remote_execution.py:205-208). Claude hook = documented opt-in snippet only.
- J2: add `link_harness_skills_report(root, tools) -> LinkReport(linked, failed, blocked)`; keep `link_harness_skills -> list[str]` as a thin wrapper. Callers: init.py:249, upgrade.py:202 (NOT the ~242 unlink handler).
- S1: `scripts/setup-harnesses.sh` stays pure shell (ships in KIT_ENTRIES). Parity enforced by extending tests/test_harness_parity.py (relpath set + explicit label-to-tool table).
- No `.mcp.json`, no copy fallback for symlinks, no opencode.json permission change, no version bump (release is a separate chore PR the user decides).
- External claims (OpenCode agents dir/schema, Antigravity workflows/agents, Pi extensions) only after T0 verification with cited sources; unsourced => unsupported, documented.

## Mode
TDD strict (source: user config + project), runner: focused `.micromamba/envs/papersmith/bin/pytest <file>`, tier `npm run test:fast`, full `npm run test:py` (CI gate only before PR). Commits: Conventional, NO AI attribution (user rule). Delivery: ask-on-risk; chain slices (T1,T2,T6) (T0,T3) (T4,T5) (T7,T8). Push/PR/merge are the user's decision. ~400 authored-line planning heuristic per task (advisory).

## Tasks
- [x] T1 link report + init/upgrade warnings; wrapper keeps callers/tests unchanged (route: delegated writer)
- [x] T2 `.pi/agents` in sync-repo-harness PROJECTION + pytest for `_expected/_orphans/--check` exit 3 (route: delegated writer)
- [x] T6 extend tests/test_harness_parity.py across shell array, HARNESS_SKILL_LINKS, inspector fallback (route: delegated writer)
- [x] T0 external verification matrix with cited sources, committed as docs
- [x] T3 OpenCode agents translator + wiring (TOOL_OUTPUTS, audit _EXTRA_STATIC, synchronized_paths, PROJECTION) + pinned-test updates in the same commit
- [ ] T4 Antigravity commands/agents only if sourced, else correct docs wording
- [ ] T5 guard/hook parity (no settings.json write; Pi only if sourced; fail-safe + tests)
- [ ] T7 per-harness wiring summary in init/upgrade + e2e + health_inspector structural check covers agents/plugins (no gen-claude.py)
- [ ] T8 docs (README, PI.md, OPENCODE.md, rules) + CHANGELOG Unreleased

## Progress / evidence
(branch feat/harness-parity created from main e1feb9b)

### Slice 1 (T1, T2, T6) - writer evidence
- T1 (c32a02f) RED: `.micromamba/envs/papersmith/bin/pytest tests/test_papersmith_init.py tests/test_papersmith_upgrade.py -q` -> 6 failed (AttributeError: module 'papersmith.core.manifest' has no attribute 'link_harness_skills_report'); wrapper test passed unchanged. GREEN: same command -> 46 passed. `npm run test:fast` -> 247 passed. Route: delegated writer.
- T2 (6ab5173) RED: `pytest tests/test_sync_repo_harness.py -q` -> 4 failed, 2 passed (PROJECTION lacked `.pi/agents`; `_expected`/`_orphans`/`--check` exit 3 tests). GREEN: after PROJECTION + `python scripts/sync-repo-harness.py` (19 files synced) -> 6 passed; `--check` clean (53 files). `npm run test:fast` -> 166 passed. Route: delegated writer.
- T6 (d5f52b9) RED: roster already agreed, so RED is by mutation, not a natural failure: deleting the `pi` row from `health_inspector._FALLBACK_SKILL_LINKS` -> roster test failed (`missing: [('pi', '.pi/skills')]`); adding an unmapped shell label -> failed with "no row in LABEL_TO_TOOL". Mutations reverted. GREEN: `pytest tests/test_harness_parity.py -q` -> 6 passed, 13 subtests. `npm run test:fast` -> 166 passed. Route: delegated writer.

### Slice 2 - T0 writer evidence
- T0: `docs/harness-support-matrix.md` written from primary vendor docs read 2026-10-02 (OpenCode, Pi raw docs, Antigravity, Claude Code). Key verdicts: OpenCode agents `.opencode/agents/` + `permission` (supported); Antigravity agents `.agents/agents/` and hooks `.agents/hooks.json` supported, workflows deprecated 2026-11-01 with path unverified, `.antigravity/*` unsupported (no source); Pi core has no sub-agents (`.pi/agents` needs third-party pi-subagents), `tool_call` extension can block, `mcp`/`mcpScript` tool names unsourced. Docs only, no tests. Route: delegated writer.

- T3 (%s) RED: `pytest tests/test_papersmith_generators.py -q` -> collection ImportError (`cannot import name 'collect_opencode_agents'`); e2e `pytest tests/test_workspace_commands_e2e.py -k opencode_agents` -> 1 failed (AssertionError: no `.opencode/agents/zz-ghost.md`). GREEN: both files -> 94 passed. `npm run test:fast` -> 3324 passed, 6 skipped. `sync-repo-harness.py` synced 19 files, `--check` clean (72). Route: delegated writer. Decisions: `.opencode/agents/*` is dynamic like `.pi/agents`, so not in `TOOL_OUTPUTS`/`_EXTRA_STATIC` (static-only by contract); upgrade stale removal via `DYNAMIC_PREFIXES`. Known gap, not fixed: `.pi/agents/` is absent from `DYNAMIC_PREFIXES`. Note: `PI_TOOL_MAP` websearch->mcpScript / webfetch->mcp have no Pi source (T0).

## Next step
Slice 2 done (T0, T3). Next: T4, T5.
