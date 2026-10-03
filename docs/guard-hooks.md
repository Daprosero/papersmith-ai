# Guard hooks per harness

The workspace ships one authority for the "refuse off-path push" tripwire: the
Python script `skills/remote-execution/scripts/hooks/refuse_offpath_push.py`. It
refuses a bash command that names a service push surface without also invoking
`remote_cli.py`. It is a tripwire, not a gate: `python -c`, heredocs and script
files that shell out defeat simple substring matching. The load-bearing check is
`_verify_launch_authorization()` inside `remote_cli.py submit`.

Sources were read on 2026-10-02; see `docs/harness-support-matrix.md`.

| Harness | Status | How |
| --- | --- | --- |
| OpenCode | generated | `.opencode/plugins/refuse-offpath-push.js` (`tool.execute.before` throws) |
| Pi | generated | `.pi/extensions/refuse-offpath-push.js` (`tool_call` returns `{ block: true, reason }`) |
| Claude Code | opt-in snippet only | paste the JSON below into your own settings |
| Antigravity | unsupported | hook input schema not verified (see below) |

The generated relays never re-implement the predicate. They call the Python
guard, and they fail open: a missing guard, missing python, spawn error, timeout
or malformed event allows the call after one warning. Only an explicit exit
status `2` from the guard blocks.

## Claude Code (opt-in, not generated)

This repository never writes or merges `.claude/settings.json`: it is gitignored
and user-owned. To turn the guard on, add this to your own `.claude/settings.json`
(or `.claude/settings.local.json`, or `~/.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/skills/remote-execution/scripts/hooks/refuse_offpath_push.py\""
          }
        ]
      }
    ]
  }
}
```

Protocol, as far as it is confirmed:

- The guard reads a JSON object on stdin with `tool_name` and
  `tool_input.command` (the contract is stated in the guard's own docstring).
- It exits `2` with a refusal on stderr to block, and `0` silently otherwise,
  including when the payload cannot be parsed. Per
  https://code.claude.com/docs/en/hooks, a `PreToolUse` hook blocks via exit code
  `2` or via JSON output with `permissionDecision: "deny"`; this guard uses the
  exit-code form only.
- `$CLAUDE_PROJECT_DIR` as the project-root variable and the exact `settings.json`
  hook nesting above were NOT re-verified against the hooks page in this change.
  Check the page before relying on them.
- Unlike the generated relays, this raw hook has no capability probe and no
  timeout of its own: if `python3` is missing the hook command fails, and how
  Claude Code treats a non-0/non-2 hook exit is not covered here.

## Antigravity (unsupported until verified)

Antigravity documents `.agents/hooks.json` with `PreToolUse` and a `decision`
of `deny` (https://antigravity.google/docs/hooks). No guard is generated, because
the hook input schema is not verified to the standard used for the other
harnesses. A page summary (not the raw page) suggests the payload names the tool
in `toolCall.name` and exposes `run_command` arguments as `CommandLine` and
`Cwd`, and that the output is a `decision` string rather than an exit code. That
differs from the stdin shape the Python guard reads (`tool_name` and
`tool_input.command`), so wiring it would need an adapter whose behaviour is
unverified. Revisit once the raw schema, including the exit and output
protocol, is read.
