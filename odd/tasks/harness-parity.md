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
- [x] T4 Antigravity agents (sourced; no commands/workflows) + Pi DYNAMIC_PREFIXES gap fix
- [x] T5 guard/hook parity (no settings.json write; Pi only if sourced; fail-safe + tests)
- [x] T7 per-harness wiring summary in init/upgrade + e2e + health_inspector structural check covers agents/plugins (no gen-claude.py)
- [x] T8 docs (README, PI.md, OPENCODE.md, rules) + CHANGELOG Unreleased

## Progress / evidence
(branch feat/harness-parity created from main e1feb9b)

### Slice 1 (T1, T2, T6) - writer evidence
- T1 (c32a02f) RED: `.micromamba/envs/papersmith/bin/pytest tests/test_papersmith_init.py tests/test_papersmith_upgrade.py -q` -> 6 failed (AttributeError: module 'papersmith.core.manifest' has no attribute 'link_harness_skills_report'); wrapper test passed unchanged. GREEN: same command -> 46 passed. `npm run test:fast` -> 247 passed. Route: delegated writer.
- T2 (6ab5173) RED: `pytest tests/test_sync_repo_harness.py -q` -> 4 failed, 2 passed (PROJECTION lacked `.pi/agents`; `_expected`/`_orphans`/`--check` exit 3 tests). GREEN: after PROJECTION + `python scripts/sync-repo-harness.py` (19 files synced) -> 6 passed; `--check` clean (53 files). `npm run test:fast` -> 166 passed. Route: delegated writer.
- T6 (d5f52b9) RED: roster already agreed, so RED is by mutation, not a natural failure: deleting the `pi` row from `health_inspector._FALLBACK_SKILL_LINKS` -> roster test failed (`missing: [('pi', '.pi/skills')]`); adding an unmapped shell label -> failed with "no row in LABEL_TO_TOOL". Mutations reverted. GREEN: `pytest tests/test_harness_parity.py -q` -> 6 passed, 13 subtests. `npm run test:fast` -> 166 passed. Route: delegated writer.

### Slice 2 - T0 writer evidence
- T0: `docs/harness-support-matrix.md` written from primary vendor docs read 2026-10-02 (OpenCode, Pi raw docs, Antigravity, Claude Code). Key verdicts: OpenCode agents `.opencode/agents/` + `permission` (supported); Antigravity agents `.agents/agents/` and hooks `.agents/hooks.json` supported, workflows deprecated 2026-11-01 with path unverified, `.antigravity/*` unsupported (no source); Pi core has no sub-agents (`.pi/agents` needs third-party pi-subagents), `tool_call` extension can block, `mcp`/`mcpScript` tool names unsourced. Docs only, no tests. Route: delegated writer.

- T3 (%s) RED: `pytest tests/test_papersmith_generators.py -q` -> collection ImportError (`cannot import name 'collect_opencode_agents'`); e2e `pytest tests/test_workspace_commands_e2e.py -k opencode_agents` -> 1 failed (AssertionError: no `.opencode/agents/zz-ghost.md`). GREEN: both files -> 94 passed. `npm run test:fast` -> 3324 passed, 6 skipped. `sync-repo-harness.py` synced 19 files, `--check` clean (72). Route: delegated writer. Decisions: `.opencode/agents/*` is dynamic like `.pi/agents`, so not in `TOOL_OUTPUTS`/`_EXTRA_STATIC` (static-only by contract); upgrade stale removal via `DYNAMIC_PREFIXES`. Known gap, not fixed: `.pi/agents/` is absent from `DYNAMIC_PREFIXES`. Note: `PI_TOOL_MAP` websearch->mcpScript / webfetch->mcp have no Pi source (T0).

- T4 (86e7a95) gate passed: tools from https://antigravity.google/docs/hooks, schema from /docs/subagents (model optional, default inherit; policy values off/auto/eager/sandbox, semantics undefined). RED: `pytest tests/test_papersmith_generators.py` -> collection ImportError (`collect_antigravity_agents`); e2e `-k antigravity_agents` -> 1 failed. Then 3 failed (unquoted `off` parses as bool; pinned expected-path set) -> fixed by quoting + updating set. GREEN: generators+e2e 104 passed; `test_harness_parity`+`test_sync_repo_harness` 12 passed; `npm run test:fast` 268 passed; sync synced 19 files, `--check` clean (91). Pi gap (599e503): RED `-k stale_pi_agents` failed (`.pi/agents/zz-ghost.md` not in removed), GREEN 60 passed, test:fast 180 passed. `PI_TOOL_MAP` untouched (mcp/mcpScript unsourced). Decision for user: `.antigravity/rules.md` unsupported by docs; AGENTS.md/GEMINI.md not created. Route: delegated writer.

- T5 (a813ee2, 4f5b850) Pi sourced from raw extensions.md (`.pi/extensions`, JS + default factory, `tool_call` -> `{block:true,reason}`, throwing handler blocks) + upstream permission-gate.ts (`event.input.command`); generated `.pi/extensions/refuse-offpath-push.js` from `pi-extension.js.tpl` (same Python guard, fail-open, anchored on own file). Claude: `docs/guard-hooks.md` opt-in snippet only (no settings.json). Antigravity: unsupported, documented (schema only seen via page summary). Static output like the OpenCode plugin: `_EXTRA_STATIC["pi"]` added, not DYNAMIC_PREFIXES, not TOOL_OUTPUTS. RED: generators+e2e pi tests -> 4 failed (FileNotFoundError `.pi/extensions/refuse-offpath-push.js`); the template file was written before the tests (unwired, inert), the node tests skipped (init unavailable) until wiring. GREEN: generators+e2e 108 passed; sync_repo_harness 6 passed; `node --test tests/pi-extension.test.mjs tests/opencode-plugin.test.mjs` 17 pass; `npm run test:fast` 3338 passed, 6 skipped; sync synced 1 file, `--check` clean (92). Pinned: generators expected-path set. Route: delegated writer.

- T7 (43e2a14, 8ac0de6) matrix in `generators.HARNESS_CAPABILITIES` (derived from COMMAND_TOOLS/COMMAND_PREFIXES + new AGENT_DIRS/PLUGIN_FILES that `render_files` writes through); `core/wiring.py` summarizes (wired|unsupported|failed|blocked) and `init`/`upgrade` print one line per active harness and add a `wiring` result key. Inspector structural fallback checks projected agents (when `.claude/agents` has sources) and plugin/extension, with `_FALLBACK_AGENT_DIRS/_PLUGIN_FILES` pinned to the real tables. RED: `pytest tests/test_harness_matrix.py -q` -> collection ImportError (`cannot import name 'wiring'`); `pytest tests/test_harness_parity.py tests/test_command_center_health.py -q` -> 5 failed (no `_FALLBACK_AGENT_DIRS`, no `agent_dir`). GREEN: matrix file 15 passed; parity+health 23 passed; `npm run test:fast` -> 3118 passed, 3 skipped (both commits). Pinned tests updated: health pi structural test and `_wire_all_harnesses` fixture (agents/plugins). Route: delegated writer.

- T8 (887d3de) docs only plus one pinning test: README per-harness table (between `harness-capabilities` markers) compared to `HARNESS_CAPABILITIES` by `ReadmeCapabilityTableTests` in tests/test_harness_parity.py (no RED: prose; the test passed against the table). Edited README.md (kept Spanish), PI.md, OPENCODE.md, .pi/README.md, .agents/README.md, .antigravity/rules.md, CHANGELOG Unreleased consolidated. Counts recomputed: 19 agents (each of .claude/.pi/.opencode/.agents), 11 skills, 11 commands, 12 CLI commands; README counts already correct. Stale and left alone: openspec/config.yaml says 52 .mjs / 18 test_*.py (now 83 / 74). Checks: harness_parity+workspace_agents_e2e+sync_repo_harness 22 passed; sync `--check` clean (92); `npm run test:fast` 191 passed. Route: delegated writer.

- README support matrix + Antigravity note (follow-up): README gains a sourced "Matriz de soporte verificada" (URLs + 2026-10-02) and an Antigravity commands note; `Capability.note` added (antigravity commands, supported stays False, no generator output changes); `ReadmeCapabilityTableTests` requires `unsupported` and the note when present. RED: `pytest tests/test_harness_parity.py -q` -> 3 failed (no `note` attribute). GREEN: focused trio 23 passed; `npm run test:fast` 290 passed.

## Next step
T8 done. Feature complete locally; push/PR is the user's decision.
