# Harness support matrix (project level)

Date reached for every source below: **2026-10-02**. Sources were read with a
page fetcher that summarizes the page, plus raw Markdown fetched for the Pi
docs. A cell with no URL says `unverified` or `unsupported (no source found)`.
Docs of fast-moving tools change; re-verify before relying on a cell after this
date.

Verdicts: `supported` (a primary source states it), `unsupported` (a primary
source says the feature is absent or deprecated), `unverified` (no primary
source read, or only a third-party source).

## OpenCode

| Capability | Verdict | Location / schema | Source (2026-10-02) |
| --- | --- | --- | --- |
| Skills | supported | `.opencode/skills/<name>/SKILL.md`; also reads `.claude/skills/` and `.agents/skills/` | https://opencode.ai/docs/skills/ |
| Commands | supported | `.opencode/commands/*.md`; frontmatter `description`, `agent`, `model`, `subtask`; `$ARGUMENTS` and `$1`, `$2`... | https://opencode.ai/docs/commands/ |
| Agents | supported | `.opencode/agents/*.md` (plural; singular `agent/` not mentioned). Frontmatter: `description` (required), `mode` (`primary`/`subagent`/`all`), `model` (`provider/model`), `temperature`, `top_p`, `steps`, `permission`, `color`, `hidden`, `disable`. `tools` is documented as deprecated in favor of `permission`. Permission keys: `read`, `edit`, `glob`, `grep`, `list`, `bash`, `task`, `external_directory`, `todowrite`, `webfetch`, `websearch`, `lsp`, `skill`, `question`, `doom_loop`; values `allow`/`ask`/`deny` or glob objects | https://opencode.ai/docs/agents/ |
| Plugins / hooks | supported | `.opencode/plugins/` (plural). `tool.execute.before` may `throw` to block a tool call; the docs example blocks `input.tool === "bash"` | https://opencode.ai/docs/plugins/ |
| MCP / config | supported | `opencode.json` in the project root; MCP under the `mcp` key; `.opencode` directories rank above project config | https://opencode.ai/docs/config/ |

## Pi (pi coding agent, `badlogic/pi-mono`)

| Capability | Verdict | Location / schema | Source (2026-10-02) |
| --- | --- | --- | --- |
| Skills | supported | `.pi/skills/` (project) and `.agents/skills/` (ancestors up to the repo root). The skills page lists only the `.agents/skills` locations; `.pi/skills/` is in the configuration page | https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/configuration.md ; https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md |
| Prompts (slash commands) | supported | `.pi/prompts/*.md`, direct `.md` children only, loaded after project trust is granted. Arguments: `$1`, `$@`, `$ARGUMENTS`, `${1:-default}`; frontmatter `description`, `argument-hint` | https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/prompt-templates.md |
| Agents / subagents | unsupported in core; third-party only | Core README: "skips features like sub-agents and plan mode". The `pi-subagents` package (nicobailon) reads `.pi/agents/**/*.md` ("in standard Pi") and legacy `.agents/**/*.md`; its frontmatter uses `tools: read, grep, find, ls` (list form also appears) | https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/README.md ; https://github.com/nicobailon/pi-subagents/blob/main/docs/agents.md |
| Extensions / hooks | supported | `.pi/extensions/` (TS/JS files or dirs with `index.ts`). `pi.on("tool_call", ...)` can block: `return { block: true, reason }`; a throwing `tool_call` handler blocks as a fail-safe. Extensions run with full process permissions | https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/extensions.md ; https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/configuration.md |
| Tool-call guard for `bash` | supported (mechanism) | Handler inspects `event.toolName` / input and returns `{ block: true }`. The docs show an approval example, not a bash-specific one | extensions.md (above) |
| MCP / config | supported | `.pi/mcp.json` (built-in MCP extension `builtin:mcp`), `.pi/settings.json`; project config loads only after trust | https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/configuration.md ; https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/mcp.md |
| Built-in tool names | supported | `read`, `bash`, `powershell`, `edit`, `write`, `grep`, `find`, `ls` | https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/settings.md |
| Tool names `mcp`, `mcpScript` | unsupported (no source found) | Docs name MCP tools `mcp__<server>__...` and a `codemode` extension; no tool named `mcp` or `mcpScript` found | pi docs above |

## Google Antigravity

| Capability | Verdict | Location / schema | Source (2026-10-02) |
| --- | --- | --- | --- |
| Skills | supported | Workspace `.agents/skills/<name>/SKILL.md` (frontmatter `name`, `description`); legacy `.agent/skills` kept; global `~/.gemini/config/skills/`. Explicit invocation `/<skill-name>` | https://antigravity.google/docs/skills |
| Skills at `.antigravity/skills` | unsupported (no source found) | Not mentioned on the skills or rules pages | https://antigravity.google/docs/skills ; https://antigravity.google/docs/rules |
| Rules | supported | `AGENTS.md` or `GEMINI.md` (no frontmatter) in a directory or in `.agents/`; `.agents/rules/*.md` needs frontmatter `trigger` (`model_decision`, `always_on`, `glob`, `manual`); legacy `.agent/rules/` | https://antigravity.google/docs/rules |
| Rules at `.antigravity/rules.md` | unsupported (no source found) | `.antigravity/` is not a recognized directory in the rules docs | https://antigravity.google/docs/rules |
| Workflows / commands | supported but deprecated | Slash-invoked Markdown files, max 12,000 characters, created via the Customizations panel (Global or Workspace). "Workflows are being deprecated in favor of Agent skills by November 1, 2026"; migration via `/migrate-workflows`. A file path for workspace workflows was not found in the pages read: `.agents/workflows` is `unverified` | https://antigravity.google/docs/ide/workflows |
| Agents / subagents | supported | `.agents/agents/<name>.md` or `.agents/agents/<name>/agent.md`; frontmatter `name`, `description` (required), `tools`, `model`, `commandExecutionPolicy`; tool names such as `view_file`, `grep_search`, `run_command` | https://antigravity.google/docs/subagents |
| Hooks / guards | supported | `.agents/hooks.json`; events `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop`; `PreToolUse` `decision` may be `deny` (hard block) or `ask`. Exact hook input schema (how a bash command is exposed) was not read: `unverified` | https://antigravity.google/docs/hooks |
| MCP / config | supported | `.agents/mcp_config.json` (workspace), `~/.gemini/config/mcp_config.json` (global) | https://antigravity.google/docs/mcp |

## Claude Code

| Capability | Verdict | Location / schema | Source (2026-10-02) |
| --- | --- | --- | --- |
| Skills | supported | `.claude/skills/<name>/SKILL.md` | https://code.claude.com/docs/en/skills |
| Commands | supported (legacy format) | `.claude/commands/*.md`; "Custom commands have been merged into skills"; same frontmatter minus `name`/`paths`; `$ARGUMENTS`, `$N` | https://code.claude.com/docs/en/skills |
| Agents | supported | `.claude/agents/*.md`; frontmatter `name`, `description` (required), `tools` (comma-separated), `model`, `permissionMode`, `skills`, `memory`, `mcpServers`, `maxTurns` | https://code.claude.com/docs/en/sub-agents |
| Hooks | supported | `.claude/settings.json` (shareable), `.claude/settings.local.json`, `~/.claude/settings.json`; also plugin `hooks.json`, skill and subagent frontmatter. `PreToolUse` blocks via exit code 2 or JSON `permissionDecision: "deny"`. Documentation only here: this repo never writes `settings.json` | https://code.claude.com/docs/en/hooks |
| MCP / config | supported | `.mcp.json` at the project root (`mcpServers`); requires workspace trust. This repo decided not to add one | https://code.claude.com/docs/en/mcp |

## Contradicted or unsupported repo claims

Compared against files read on 2026-10-02.

| Repo claim | Where | Finding |
| --- | --- | --- |
| Antigravity skills are projected into `.antigravity/skills` | `.antigravity/rules.md`, `.agents/README.md` | Not in the Antigravity docs; docs use `.agents/skills` (legacy `.agent/skills`). Unsupported (no source found) |
| `.antigravity/rules.md` is the Antigravity entrypoint | `.agents/README.md`, `.antigravity/rules.md` | Not in the docs. Documented entrypoints are `AGENTS.md`, `GEMINI.md`, `.agents/AGENTS.md`, `.agents/GEMINI.md`, `.agents/rules/*.md` |
| "no command files are generated"; Antigravity invokes `/<name>` via `.agents/skills` | `.antigravity/rules.md` | Supported: the skills page documents `/<skill-name>` invocation |
| Antigravity has no agents (feature problem list) | `odd/tasks/harness-parity.md` | Contradicted: `.agents/agents/*.md` is documented |
| `.agents/workflows` exists and is deprecated 2026-11-01 | task context | Deprecation date confirmed; the `.agents/workflows` path is `unverified` |
| Pi `.pi/skills` symlink | `.pi/README.md`, `PI.md` | Supported by the configuration page; the skills page lists only `.agents/skills`, which Pi also reads |
| Pi prompts in `.pi/prompts/<name>.md` with `$ARGUMENTS` | `.pi/README.md`, `PI.md` | Supported |
| `.pi/agents` agent projection | `generators.py` `PI_TOOL_MAP`, `.pi/agents` | Core Pi has no sub-agents; only the third-party `pi-subagents` package documents `.pi/agents/**/*.md`. The projection works only when that package is installed |
| `PI_TOOL_MAP`: `websearch` to `mcpScript`, `webfetch` to `mcp` | `src/papersmith/generators.py` | Unsupported (no source found): Pi docs name no tool `mcp` or `mcpScript`. `read`, `bash`, `edit`, `write`, `grep`, `find` are supported built-ins |
| OpenCode plugin at `.opencode/plugins/`, thrown error blocks a bash call | `OPENCODE.md`, `refuse-offpath-push.js` | Supported (`tool.execute.before` throw) |
| OpenCode commands at `.opencode/commands/` with `$ARGUMENTS` | `OPENCODE.md` | Supported |
| OpenCode skills at `.opencode/skills` | `OPENCODE.md` | Supported |

## Implications for T3/T4/T5

- T3 (OpenCode agents): may write `.opencode/agents/*.md` (plural) with
  `description`, `mode: subagent`, optional `model`, and `permission` (not the
  deprecated `tools`). Tool restrictions must use permission keys, not Claude
  tool names. No singular `agent/` directory.
- T4 (Antigravity): may generate `.agents/agents/<name>.md` (`name`,
  `description`, `tools` with Antigravity tool names, `model`). Workflows are
  deprecated and their file path is unverified: do not generate workflow files.
  Skills already work via `/<skill-name>`. Docs wording about
  `.antigravity/skills` and `.antigravity/rules.md` has no source and must be
  stated as unsupported or legacy; `AGENTS.md` / `.agents/rules/` are the
  documented rules locations.
- T5 (guards): OpenCode plugin guard is verified. Pi guard is possible through a
  `.pi/extensions/` `tool_call` handler returning `{ block: true }` (extension
  runs with full permissions and project trust applies). Antigravity guard is
  possible through `.agents/hooks.json` `PreToolUse` `deny`, but the hook input
  schema is unverified: implement only after reading it. Claude Code hook stays a
  documented opt-in snippet; this repo does not write `.claude/settings.json`.
- Pi agents: stay unsupported in core. Keep `.pi/agents` documented as
  requiring the third-party `pi-subagents` package; the `mcp`/`mcpScript` mapping
  has no source.

## Tooling notes

WebFetch summaries come from a small model, so quoted strings were not
re-checked against raw HTML except for the Pi docs, which were read as raw
Markdown. context7 was not used; primary vendor pages were reachable directly.

## T4 outcome (Antigravity agents, 2026-10-02)

Gate passed; `.agents/agents/<name>.md` is generated. Sources:
https://antigravity.google/docs/subagents (frontmatter: `tools` string[] default
`[]`; `model` default `inherit`, values `inherit`/`flash`/`pro`;
`commandExecutionPolicy` default `sandbox`, values `off`/`auto`/`eager`/`sandbox`)
and https://antigravity.google/docs/hooks (tool names `view_file`,
`write_to_file`, `replace_file_content`, `multi_replace_file_content`,
`list_dir`, `find_by_name`, `grep_search`, `search_web`, `read_url_content`,
`run_command`). Mapping: Read to `view_file`; Glob to `find_by_name` +
`list_dir`; Grep to `grep_search`; Write to `write_to_file`; Edit to the two
replace tools; Bash to `run_command`; WebSearch to `search_web`; WebFetch to
`read_url_content`. `model` is omitted (inherits).

Caveats: the subagents page does not enumerate tools (the list comes from the
hooks page) and does not define each `commandExecutionPolicy` value. `off` is
used for agents without `run_command` as the most restrictive reading of
"auto-execution policy" and is secondary to the `tools` allow-list; agents with
`run_command` get the documented default `sandbox`. The value is quoted because
an unquoted `off` is a YAML 1.1 boolean. Decision for the user: `.antigravity/rules.md`
has no documented support; `AGENTS.md`/`GEMINI.md`/`.agents/rules/` are the
documented entrypoints and were deliberately not created.
