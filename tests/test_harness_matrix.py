"""One support matrix, derived from what the generators emit, and the wiring
summary `init` / `upgrade` print from it."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from papersmith import generators
from papersmith.core import manifest, wiring
from papersmith.generators import ALL_TOOLS, HARNESS_CAPABILITIES, render_files

from workspace_series import capture, make_workspace, new_tmp

CAPS = ("skills", "commands", "agents", "plugins")

SUPPORTED = {
    "claude": {"skills", "commands", "agents"},
    "opencode": {"skills", "commands", "agents", "plugins"},
    "pi": {"skills", "commands", "agents", "plugins"},
    "antigravity": {"skills", "agents"},
}


def supported(tool: str) -> set[str]:
    return {cap for cap, entry in HARNESS_CAPABILITIES[tool].items() if entry.supported}


class MatrixTests(unittest.TestCase):
    def test_every_tool_has_every_capability_marked(self) -> None:
        self.assertEqual(set(HARNESS_CAPABILITIES), set(ALL_TOOLS))
        for tool in ALL_TOOLS:
            self.assertEqual(set(HARNESS_CAPABILITIES[tool]), set(CAPS), tool)

    def test_matrix_values(self) -> None:
        for tool, expected in SUPPORTED.items():
            self.assertEqual(supported(tool), expected, tool)

    def test_skills_capability_agrees_with_the_link_roster(self) -> None:
        linked = {tool for tool, _ in manifest.HARNESS_SKILL_LINKS}
        self.assertEqual({t for t in ALL_TOOLS if "skills" in supported(t)}, linked)

    def test_matrix_matches_what_render_files_emits(self) -> None:
        """A generator output with no matrix entry, or an entry with no output."""
        workspace = make_workspace(new_tmp(self))
        rendered = set(render_files(workspace, tools=ALL_TOOLS))
        for tool in ALL_TOOLS:
            only = set(render_files(workspace, tools=(tool,)))
            observed = set()
            for cap in ("commands", "agents", "plugins"):
                artifact = HARNESS_CAPABILITIES[tool][cap].artifact
                if artifact and any(p == artifact or p.startswith(artifact.rstrip("/") + "/")
                                    for p in only):
                    observed.add(cap)
            if tool == "claude":
                # Claude's agents are the kit's own source files, not rendered.
                observed.add("agents")
            declared = supported(tool) - {"skills"}
            self.assertEqual(observed, declared, tool)
        # Every rendered path under a capability location belongs to a tool
        # that declares it: nothing is emitted unlisted.
        owned = [e.artifact for t in ALL_TOOLS for c, e in HARNESS_CAPABILITIES[t].items()
                 if e.supported and e.artifact]
        for path in rendered:
            if path.startswith((".pi/agents/", ".opencode/agents/", ".agents/agents/",
                                ".pi/prompts/", ".claude/commands/", ".opencode/commands/",
                                ".pi/extensions/", ".opencode/plugins/")):
                self.assertTrue(
                    any(path == a or path.startswith(a.rstrip("/") + "/") for a in owned),
                    f"{path} is generated but absent from the support matrix")


class WiringSummaryTests(unittest.TestCase):
    def test_default_init_wires_everything_the_matrix_supports(self) -> None:
        workspace = make_workspace(new_tmp(self))
        summary = wiring.summarize(workspace, ALL_TOOLS, manifest.LinkReport(), [])
        for tool in ALL_TOOLS:
            for cap in CAPS:
                want = "wired" if cap in SUPPORTED[tool] else "unsupported"
                self.assertEqual(summary[tool][cap], want, f"{tool}.{cap}")

    def test_link_failures_and_blocks_come_from_the_link_report(self) -> None:
        workspace = make_workspace(new_tmp(self))
        report = manifest.LinkReport(failed=[".pi/skills"], blocked=[".opencode/skills"])
        summary = wiring.summarize(workspace, ALL_TOOLS, report, [])
        self.assertEqual(summary["pi"]["skills"], "failed")
        self.assertEqual(summary["opencode"]["skills"], "blocked")
        self.assertEqual(summary["claude"]["skills"], "wired")

    def test_skipped_generated_paths_are_failed(self) -> None:
        workspace = make_workspace(new_tmp(self))
        skipped = [".opencode/plugins/refuse-offpath-push.js", ".pi/agents/x.md"]
        summary = wiring.summarize(workspace, ALL_TOOLS, manifest.LinkReport(), skipped)
        self.assertEqual(summary["opencode"]["plugins"], "failed")
        self.assertEqual(summary["pi"]["agents"], "failed")
        self.assertEqual(summary["pi"]["plugins"], "wired")

    def test_missing_artifact_is_not_reported_wired(self) -> None:
        workspace = make_workspace(new_tmp(self))
        (workspace / ".pi/extensions/refuse-offpath-push.js").unlink()
        summary = wiring.summarize(workspace, ("pi",), manifest.LinkReport(), [])
        self.assertEqual(summary["pi"]["plugins"], "failed")

    def test_format_is_one_line_per_active_harness(self) -> None:
        summary = {"claude": {c: "wired" for c in CAPS} | {"plugins": "unsupported"}}
        lines = wiring.format_summary(summary)
        self.assertEqual(len(lines), 1)
        self.assertEqual(
            lines[0],
            "claude: skills=wired commands=wired agents=wired plugins=unsupported")


class InitUpgradeOutputTests(unittest.TestCase):
    def test_init_prints_summary_and_exits_zero(self) -> None:
        workspace = new_tmp(self) / "ws"
        rc, out, _ = capture(["init", str(workspace), "--no-npm", "--no-env"])
        self.assertEqual(rc, 0)
        self.assertEqual(sum(1 for l in out.splitlines() if l.startswith("  ") and "skills=" in l),
                         len(ALL_TOOLS))
        self.assertIn("antigravity: skills=wired commands=unsupported agents=wired "
                      "plugins=unsupported", out)

    def test_init_scoped_tools_lists_only_active(self) -> None:
        workspace = new_tmp(self) / "ws"
        rc, out, _ = capture(["init", str(workspace), "--tools", "claude", "--no-npm", "--no-env"])
        self.assertEqual(rc, 0)
        self.assertIn("claude: skills=wired", out)
        for other in ("opencode", "pi", "antigravity"):
            self.assertNotIn(f"{other}: skills=", out)

    def test_upgrade_prints_summary_and_is_idempotent(self) -> None:
        workspace = make_workspace(new_tmp(self))
        rc, out, _ = capture(["upgrade", str(workspace)])
        self.assertEqual(rc, 0)
        self.assertIn("changed files: 0", out)
        self.assertIn("opencode: skills=wired commands=wired agents=wired plugins=wired", out)

    def test_results_keep_old_keys_and_add_wiring(self) -> None:
        from papersmith.core import init as init_module, upgrade as upgrade_module
        workspace = new_tmp(self) / "ws"
        result = init_module.initialize(workspace, run_npm=False, run_env=False)
        for key in ("workspace", "name", "version", "active_tools", "remote",
                    "default_target", "copied_files", "generated_files", "warnings"):
            self.assertIn(key, result)
        self.assertEqual(set(result["wiring"]), set(ALL_TOOLS))
        up = upgrade_module.upgrade(workspace)
        for key in ("workspace", "version", "active_tools", "changed_files",
                    "preserved_files", "removed", "stranded", "unsynchronized",
                    "link_warnings"):
            self.assertIn(key, up)
        self.assertEqual(up["changed_files"], [])
        self.assertEqual(set(up["wiring"]), set(ALL_TOOLS))
        json.dumps(up["wiring"])


class HarnessE2ETests(unittest.TestCase):
    def _assert_wired(self, workspace: Path, tool: str) -> None:
        for cap, entry in HARNESS_CAPABILITIES[tool].items():
            if not entry.supported:
                continue
            if cap == "skills":
                for t, rel in manifest.HARNESS_SKILL_LINKS:
                    if t == tool:
                        link = workspace / rel
                        self.assertTrue(link.is_symlink(), rel)
                        self.assertEqual(link.resolve(), (workspace / "skills").resolve(), rel)
            elif cap == "plugins":
                self.assertTrue((workspace / entry.artifact).is_file(), entry.artifact)
            else:
                files = list((workspace / entry.artifact).glob("*.md"))
                self.assertTrue(files, f"{tool}.{cap}: no files under {entry.artifact}")

    def test_default_init_leaves_every_harness_fully_wired_and_upgrade_is_idempotent(self) -> None:
        workspace = make_workspace(new_tmp(self))
        for tool in ALL_TOOLS:
            self._assert_wired(workspace, tool)
        rc, out, _ = capture(["upgrade", str(workspace)])
        self.assertEqual(rc, 0)
        self.assertIn("changed files: 0", out)

    def test_scoped_init_leaves_the_others_absent(self) -> None:
        workspace = new_tmp(self) / "ws"
        rc, _, _ = capture(["init", str(workspace), "--tools", "claude", "--no-npm", "--no-env"])
        self.assertEqual(rc, 0)
        self._assert_wired(workspace, "claude")
        for rel in (".opencode/skills", ".pi/skills", ".antigravity/skills", ".agents/skills",
                    ".opencode/commands", ".pi/prompts", ".opencode/agents", ".pi/agents",
                    ".agents/agents", ".opencode/plugins", ".pi/extensions"):
            self.assertFalse((workspace / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
