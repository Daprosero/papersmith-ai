// OpenCode port of `.claude/skills/remote-execution/scripts/hooks/refuse_offpath_push.py`.
//
// Original: a Claude Code `PreToolUse` hook for the `Bash` tool. It refused a
// command naming a service push surface without also invoking `remote_cli.py`.
// This plugin implements the same tripwire on OpenCode's `tool.execute.before`.
//
// Semantics preserved:
// - A command is refused only when it names a push surface AND does not also
//   name `remote_cli.py` (the one place `_verify_launch_authorization()` lives).
// - Push surfaces are never hardcoded here as the source of truth: each adapter
//   under `.claude/skills/remote-execution/scripts/adapters/` declares its own
//   module-level `PUSH_SURFACE` tuple. This file reads those declarations at
//   startup and falls back to the last known pair only if the scan fails.
// - Fail-open on unreadable input (a tripwire that cannot parse refuses nothing).
// - This is a tripwire, not the gate. The load-bearing precondition is
//   `_verify_launch_authorization()` inside `submit` itself.
import fs from "node:fs"
import path from "node:path"

const SUBMIT_MARKER = "remote_cli.py"
const FALLBACK_SURFACES = ["kaggle_driver.py", "kernels_push"]

function loadPushSurfaces(projectRoot) {
  try {
    const dir = path.join(
      projectRoot,
      ".claude",
      "skills",
      "remote-execution",
      "scripts",
      "adapters"
    )
    if (!fs.existsSync(dir)) return [...FALLBACK_SURFACES]
    const surfaces = []
    for (const entry of fs.readdirSync(dir).sort()) {
      if (!entry.endsWith(".py") || entry === "__init__.py") continue
      const src = fs.readFileSync(path.join(dir, entry), "utf8")
      const m = src.match(/PUSH_SURFACE[^=]*=\s*\(([^)]*)\)/)
      if (!m) continue
      for (const tok of m[1].match(/["']([^"']+)["']/g) ?? []) {
        surfaces.push(tok.slice(1, -1))
      }
    }
    return surfaces.length > 0 ? surfaces : [...FALLBACK_SURFACES]
  } catch {
    return [...FALLBACK_SURFACES]
  }
}

function offpathPush(command, pushSurfaces) {
  if (command.includes(SUBMIT_MARKER)) return null
  for (const token of pushSurfaces) {
    if (token && command.includes(token)) return token
  }
  return null
}

export const RefuseOffpathPush = async ({ directory, worktree }) => {
  const root = directory ?? worktree ?? process.cwd()
  const pushSurfaces = loadPushSurfaces(root)

  return {
    "tool.execute.before": async (input, output) => {
      if (input?.tool !== "bash") return
      const command =
        output?.args?.command ?? input?.args?.command ?? output?.args?.cmd ?? ""
      if (typeof command !== "string" || command.length === 0) return

      const matched = offpathPush(command, pushSurfaces)
      if (matched === null) return

      throw new Error(
        `refusing: this command names a push surface (${JSON.stringify(matched)}) ` +
          `without invoking ${SUBMIT_MARKER} -- a launch that skips \`submit\` ` +
          `skips its own authorization precondition ` +
          `(\`_verify_launch_authorization()\`). Route the launch through ` +
          `\`remote_cli.py submit\` (or \`--smoke\` for a rehearsal) instead.`
      )
    },
  }
}
