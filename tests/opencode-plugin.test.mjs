// Node-gate tests for the generated OpenCode "refuse off-path push" plugin.
//
// These run under `node --test "tests/**/*.mjs"` and are deliberately NOT
// `test_*.py`, so `pytest tests/` never collects them.
//
// The plugin under test is the real generated artifact: a throwaway workspace is
// produced by the real `papersmith init`, and the plugin bytes are imported from
// `<workspace>/.opencode/plugins/refuse-offpath-push.js`. The workspace's
// adapters directory is then replaced with one trivially importable synthetic
// adapter so the surface set — and therefore every assertion — is deterministic
// and independent of whether the real kaggle adapter's optional dependency is
// importable in this environment.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PLUGIN_RELATIVE = ".opencode/plugins/refuse-offpath-push.js";
const HOOK_RELATIVE = ".opencode/skills/remote-execution/scripts/hooks/refuse_offpath_push.py";
const ADAPTERS_RELATIVE = ".opencode/skills/remote-execution/scripts/adapters";
const SURFACE_TOKEN = "zz_plugin_test_surface";

function makeTmp(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function generateWorkspace() {
  const destination = makeTmp("papersmith-plugin-");
  const winScript = path.join(REPO_ROOT, ".venv", "Scripts", "papersmith.exe");
  const posixScript = path.join(REPO_ROOT, ".venv", "bin", "papersmith");
  const consoleScript = fs.existsSync(winScript)
    ? winScript
    : posixScript;
  const args = ["init", destination, "--remote", "local", "--no-npm"];
  let result;
  if (fs.existsSync(consoleScript)) {
    result = spawnSync(consoleScript, args, { cwd: REPO_ROOT, encoding: "utf8" });
  } else {
    const program = 'from papersmith.cli import main; raise SystemExit(main(' + JSON.stringify(args) + "))";
    const interpreter = process.platform === "win32" ? "python" : "python3";
    result = spawnSync(interpreter, ["-c", program], {
      cwd: REPO_ROOT,
      encoding: "utf8",
      env: { ...process.env, PYTHONPATH: path.join(REPO_ROOT, "src") },
    });
  }
  if (result.error || result.status !== 0) {
    return null;
  }
  if (!fs.existsSync(path.join(destination, PLUGIN_RELATIVE))) {
    return null;
  }
  return destination;
}

//: Built once: the corpus generator is an environment precondition, not the
//: subject under test, so an absent interpreter skips rather than fails.
const WORKSPACE = generateWorkspace();
const UNAVAILABLE = WORKSPACE ? false : "papersmith init unavailable in this environment";

function plantAdapters(root, modules) {
  const directory = path.join(root, ADAPTERS_RELATIVE);
  fs.rmSync(directory, { recursive: true, force: true });
  fs.mkdirSync(directory, { recursive: true });
  for (const [name, body] of Object.entries(modules)) {
    fs.writeFileSync(path.join(directory, name), body, "utf8");
  }
}

function copyWorkspace(source) {
  const destination = makeTmp("papersmith-plugin-copy-");
  // `fs.cpSync` keeps the layout; node_modules may be large, so exclude it.
  fs.cpSync(source, destination, {
    recursive: true,
    filter: (entry) => !entry.includes(`${path.sep}node_modules`),
  });
  return destination;
}

// The generated plugin is dependency-free (V2 `{id, setup}` shape, no
// `@opencode/plugin` import), so plain `node --test` imports it directly.
function fakeContext(root) {
  const hooks = {};
  return {
    hooks,
    ctx: {
      location: { directory: root },
      tool: {
        hook: async (name, handler) => {
          hooks[name] = handler;
        },
      },
    },
  };
}

async function loadPlugin(root) {
  const url = pathToFileURL(path.join(root, PLUGIN_RELATIVE)).href;
  const module = await import(url);
  assert.equal(typeof module.default, "object", "the generated module must default-export a plugin definition");
  assert.equal(module.default.id, "refuse-offpath-push");
  assert.equal(typeof module.default.setup, "function");
  const { hooks, ctx } = fakeContext(root);
  await module.default.setup(ctx);
  assert.equal(typeof hooks["execute.before"], "function", "setup must register the execute.before hook");
  return hooks;
}

function invoke(hooks, command) {
  return hooks["execute.before"]({ tool: "shell", input: { command } });
}

test("generated plugin default-exports a V2 definition with the shell pre-execution hook", { skip: UNAVAILABLE }, async () => {
  const hooks = await loadPlugin(WORKSPACE);
  assert.equal(typeof hooks["execute.before"], "function");
});

test("plugin allows a clean command", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE: tuple[str, ...] = ("${SURFACE_TOKEN}",)\n`,
  });
  const hooks = await loadPlugin(root);
  await invoke(hooks, "ls -la");
  await invoke(hooks, "echo hello");
});

test("plugin ignores non-shell tools and empty commands", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  const hooks = await loadPlugin(root);
  await hooks["execute.before"]({ tool: "read", input: { command: `x ${SURFACE_TOKEN}` } });
  await invoke(hooks, "");
  await invoke(hooks, undefined);
});

test("plugin THROWS on an off-path push and the message names the surface", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  const hooks = await loadPlugin(root);
  await assert.rejects(
    () => invoke(hooks, `python3 zz_runner.py --call ${SURFACE_TOKEN}`),
    (error) => {
      assert.ok(error instanceof Error, "refusal must be a thrown Error, not a logged string");
      assert.match(error.message, new RegExp(SURFACE_TOKEN));
      assert.match(error.message, /refuse-offpath-push/);
      return true;
    },
  );
});

test("plugin allows the same surface when the command routes through remote_cli.py", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  const hooks = await loadPlugin(root);
  await invoke(hooks, `python3 remote_cli.py submit --note ${SURFACE_TOKEN}`);
});

test("plugin degrades loudly, once, and allows when the hook hangs past the timeout", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_surface.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`,
  });
  // Keep the real hook's module (so the capability probe succeeds) but hang when
  // it is executed as a program, which is how the relay invokes it.
  const hookPath = path.join(root, HOOK_RELATIVE);
  const source = fs.readFileSync(hookPath, "utf8");
  const withoutMain = source.slice(0, source.indexOf("if __name__ == \"__main__\":"));
  fs.writeFileSync(hookPath, `${withoutMain}\nimport time\n\ntime.sleep(30)\n`, "utf8");

  const hooks = await loadPlugin(root);
  const errors = t.mock.method(console, "error", () => {});
  await invoke(hooks, `python3 zz_runner.py --call ${SURFACE_TOKEN}`);
  await invoke(hooks, `python3 zz_runner.py --call ${SURFACE_TOKEN}`);
  assert.equal(errors.mock.callCount(), 1, "exactly one warning per process");
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("plugin degrades loudly when a declared surface fails to load", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_broken.py": `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\nraise RuntimeError("adapter cannot import")\n`,
  });
  const hooks = await loadPlugin(root);
  const errors = t.mock.method(console, "error", () => {});
  await invoke(hooks, `python3 zz_runner.py --call ${SURFACE_TOKEN}`);
  assert.equal(errors.mock.callCount(), 1, "a non-empty-but-incomplete surface set must not pass");
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});
