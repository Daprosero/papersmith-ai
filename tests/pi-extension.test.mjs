// Node-gate tests for the generated Pi "refuse off-path push" extension.
//
// These run under `node --test "tests/**/*.mjs"` and are deliberately NOT
// `test_*.py`, so `pytest tests/` never collects them.
//
// The extension under test is the real generated artifact: a throwaway
// workspace is produced by the real `papersmith init`, and the extension bytes
// are loaded from `<workspace>/.pi/extensions/refuse-offpath-push.ts` the way Pi
// loads them -- through jiti, requesting the default export. A plain `import()`
// of a `.ts` file does not work under Node, so the jiti load is itself part of
// the contract this file proves: Pi rejects an extension whose default export is
// not a function. The workspace's adapters directory is then replaced with one
// trivially importable synthetic adapter so the surface set -- and therefore
// every assertion -- is deterministic and independent of whether the real kaggle
// adapter's optional dependency is importable in this environment.
//
// Every degradation case is asserted twice over: the warning must be loud and
// exactly one, and the handler must RESOLVE. Pi treats a failed `tool_call`
// handler as a fail-safe block (docs/extensions.md, "Errors and cleanup"), so a
// rejection here would block every bash command in a real session.

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { createJiti } from "jiti";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const EXTENSION_RELATIVE = ".pi/extensions/refuse-offpath-push.ts";
const HOOK_RELATIVE = "skills/remote-execution/scripts/hooks/refuse_offpath_push.py";
const ADAPTERS_RELATIVE = "skills/remote-execution/scripts/adapters";
const SURFACE_TOKEN = "zz_pi_test_surface";
const SURFACE_ADAPTER = `PUSH_SURFACE = ("${SURFACE_TOKEN}",)\n`;

function makeTmp(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function generateWorkspace() {
  const destination = makeTmp("papersmith-pi-");
  const consoleScript = path.join(REPO_ROOT, ".venv", "bin", "papersmith");
  const args = ["init", destination, "--remote", "local", "--no-npm"];
  let result;
  if (fs.existsSync(consoleScript)) {
    result = spawnSync(consoleScript, args, { cwd: REPO_ROOT, encoding: "utf8" });
  } else {
    const program = 'from papersmith.cli import main; raise SystemExit(main(' + JSON.stringify(args) + "))";
    result = spawnSync("python3", ["-c", program], {
      cwd: REPO_ROOT,
      encoding: "utf8",
      env: { ...process.env, PYTHONPATH: path.join(REPO_ROOT, "src") },
    });
  }
  if (result.error || result.status !== 0) {
    return null;
  }
  return destination;
}

//: Built once: the workspace generator is an environment precondition, not the
//: subject under test, so an absent interpreter skips rather than fails.
//: An *absent generated artifact* is not an environment precondition -- it is
//: the deliverable -- so `loadFactory` asserts it and the gate goes RED on it.
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
  const destination = makeTmp("papersmith-pi-copy-");
  // `fs.cpSync` keeps the layout; node_modules may be large, so exclude it.
  fs.cpSync(source, destination, {
    recursive: true,
    filter: (entry) => !entry.includes(`${path.sep}node_modules`),
  });
  return destination;
}

async function loadFactory(root) {
  const artifact = path.join(root, EXTENSION_RELATIVE);
  assert.ok(fs.existsSync(artifact), `papersmith must generate ${EXTENSION_RELATIVE}`);
  // The exact load Pi performs: jiti, default export, and a hard requirement
  // that what comes back is the factory function.
  const jiti = createJiti(import.meta.url, { moduleCache: false });
  const factory = await jiti.import(artifact, { default: true });
  assert.equal(
    typeof factory,
    "function",
    "Pi rejects a module whose default export is not a function: jiti.import(path, { default: true }) must return the factory",
  );
  return factory;
}

function bash(command) {
  return { toolName: "bash", input: { command } };
}

async function mountExtension(root) {
  const factory = await loadFactory(root);
  const registered = [];
  const pi = {
    on: (event, handler) => {
      registered.push({ event, handler });
      return () => {};
    },
  };
  factory(pi);
  assert.equal(registered.length, 1, "the extension must register exactly one handler");
  assert.equal(registered[0].event, "tool_call");
  return {
    ...registered[0],
    invoke: (event, ctx = { cwd: root, hasUI: false }) => registered[0].handler(event, ctx),
  };
}

test("the generated extension is emitted and default-exports the tool_call factory", { skip: UNAVAILABLE }, async () => {
  const { event } = await mountExtension(WORKSPACE);
  assert.equal(event, "tool_call");
});

test("the extension allows a clean command", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, { "zz_surface.py": SURFACE_ADAPTER });
  const { invoke } = await mountExtension(root);
  assert.equal(await invoke(bash("ls -la")), undefined);
  assert.equal(await invoke(bash("echo hello")), undefined);
});

test("the extension ignores non-bash tools and empty or absent commands", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, { "zz_surface.py": SURFACE_ADAPTER });
  const { invoke } = await mountExtension(root);
  assert.equal(await invoke({ toolName: "read", input: { command: `x ${SURFACE_TOKEN}` } }), undefined);
  assert.equal(await invoke(bash("")), undefined);
  assert.equal(await invoke({ toolName: "bash", input: {} }), undefined);
  assert.equal(await invoke({ toolName: "bash" }), undefined);
});

test("the extension BLOCKS an off-path push and the reason names the surface", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, { "zz_surface.py": SURFACE_ADAPTER });
  const { invoke } = await mountExtension(root);
  const result = await invoke(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`));
  assert.ok(result, "a refusal must be a RETURNED result, never a thrown error");
  assert.equal(result.block, true);
  assert.match(result.reason, new RegExp(SURFACE_TOKEN));
  assert.match(result.reason, /refuse-offpath-push/);
});

test("the extension allows the same surface when the command routes through remote_cli.py", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, { "zz_surface.py": SURFACE_ADAPTER });
  const { invoke } = await mountExtension(root);
  assert.equal(await invoke(bash(`python3 remote_cli.py submit --note ${SURFACE_TOKEN}`)), undefined);
});

test("the extension degrades loudly, once, and still resolves when the hook hangs", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, { "zz_surface.py": SURFACE_ADAPTER });
  // Keep the real hook importable -- so the capability probe still succeeds --
  // but hang when it is executed as a program, which is how the relay invokes it.
  const hookPath = path.join(root, HOOK_RELATIVE);
  const source = fs.readFileSync(hookPath, "utf8");
  const head = source.slice(0, source.indexOf('if __name__ == "__main__":'));
  fs.writeFileSync(hookPath, `${head}if __name__ == "__main__":\n    import time\n\n    time.sleep(30)\n`, "utf8");

  const { invoke } = await mountExtension(root);
  const errors = t.mock.method(console, "error", () => {});
  assert.equal(await invoke(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  assert.equal(await invoke(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  assert.equal(errors.mock.callCount(), 1, "exactly one warning per process");
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("the extension degrades loudly when a declared surface fails to import", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, {
    "zz_broken.py": `${SURFACE_ADAPTER}raise RuntimeError("adapter cannot import")\n`,
  });
  const { invoke } = await mountExtension(root);
  const errors = t.mock.method(console, "error", () => {});
  assert.equal(await invoke(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  assert.equal(errors.mock.callCount(), 1, "a non-empty-but-incomplete surface set must not pass");
  const warning = String(errors.mock.calls[0].arguments[0]);
  assert.match(warning, /degraded/);
  assert.match(warning, new RegExp(SURFACE_TOKEN), "the warning must name the surface that did not load");
});

test("the extension degrades rather than blocks when the hook is not found from ctx.cwd", { skip: UNAVAILABLE }, async (t) => {
  const root = copyWorkspace(WORKSPACE);
  fs.rmSync(path.join(root, HOOK_RELATIVE));
  const { invoke } = await mountExtension(root);
  const errors = t.mock.method(console, "error", () => {});
  assert.equal(await invoke(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`)), undefined);
  assert.equal(errors.mock.callCount(), 1);
  assert.match(String(errors.mock.calls[0].arguments[0]), /degraded/);
});

test("the extension resolves the workspace root by walking up from ctx.cwd", { skip: UNAVAILABLE }, async () => {
  const root = copyWorkspace(WORKSPACE);
  plantAdapters(root, { "zz_surface.py": SURFACE_ADAPTER });
  const { invoke } = await mountExtension(root);
  // Pi's ExtensionContext exposes only `cwd`, and a tool call made from a
  // subdirectory must still find the guard at the workspace root.
  const nested = { cwd: path.join(root, "skills", "remote-execution"), hasUI: false };
  const result = await invoke(bash(`python3 zz_runner.py --call ${SURFACE_TOKEN}`), nested);
  assert.equal(result && result.block, true);
  assert.equal(await invoke(bash("ls -la"), nested), undefined);
});

test("the generated PI.md documents the safety extension", { skip: UNAVAILABLE }, async () => {
  const text = fs.readFileSync(path.join(WORKSPACE, "PI.md"), "utf8");
  assert.match(text, /## Safety extension/);
  assert.match(text, /\.pi\/extensions\/refuse-offpath-push\.ts/);
  assert.match(text, /refuse_offpath_push\.py/);
  assert.match(text, /tripwire, not a gate/);
});
