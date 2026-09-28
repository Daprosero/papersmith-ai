"""OpenCode-native seal: agents, models, config, and commands stay complete.

Single harness. `.opencode/agents` is canonical (filename is the agent ID),
`.opencode/skills` holds the real skill tree, `opencode.json` is V2
(`permissions[]`, `mcp.servers`). Two distribution rules are pinned by name:

* ``mimo-v2.6-pro`` runs only ``deliberation-publish`` -- the scarcest math
  gate stays exclusive, so a later edit cannot quietly spread it.
* ``muse-spark-1.3-contributor`` trains on prompts, so it only hosts
  published-reference mechanical stretches (``paper-ingestion``,
  ``style-sampler``). Nothing that reads or writes unpublished paper,
  proposals, or code runs on it.

Stdlib only, like `test_agents.py`.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / ".opencode" / "agents"
SKILLS = ROOT / ".opencode" / "skills"
COMMANDS = ROOT / ".opencode" / "commands"
PLUGIN = ROOT / ".opencode" / "plugins" / "refuse-offpath-push.js"
CONFIG = ROOT / "opencode.json"

# agent -> model. The whole distribution in one place: adding an agent or
# moving one to another model changes this map, never a silent default.
AGENT_MODELS = {
    "audit-report": "opencode-go/qwen3.7-plus",
    "contract-auditor": "opencode-go/deepseek-v4.1-flash",
    "deliberation-publish": "opencode-go/mimo-v2.6-pro",
    "diagram-author": "opencode-go/deepseek-v4-flash-vision-exp",
    "experimental-publish": "opencode-go/qwen3.7-plus",
    "experimental-validation": "opencode-go/qwen3.7-plus",
    "experiments-build": "opencode-go/deepseek-v4.1-flash",
    "experiments-walk": "opencode-go/mimo-v2.6-flash",
    "figure-auditor": "opencode-go/deepseek-v4.1-flash",
    "figure-describer": "opencode-go/deepseek-v4-flash-vision-exp",
    "implementation-build": "opencode-go/deepseek-v4.1-flash",
    "implementation-walk": "opencode-go/mimo-v2.6-flash",
    "insumos-observer": "opencode-go/deepseek-v4.1-flash",
    "paper-ingestion": "opencode-go/muse-spark-1.3-contributor",
    "redactor": "opencode-go/qwen3.8-flash",
    "section-grounding-auditor": "opencode-go/deepseek-v4.1-flash",
    "style-sampler": "opencode-go/muse-spark-1.3-contributor",
}

MATH_ONLY_HOLDER = "deliberation-publish"
MATH_ONLY_MODEL = "opencode-go/mimo-v2.6-pro"
CONTRIBUTOR_SAFE_HOLDERS = {"paper-ingestion", "style-sampler"}
CONTRIBUTOR_MODEL = "opencode-go/muse-spark-1.3-contributor"


def frontmatter_field(path: Path, field: str) -> str | None:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    header = text.split("---\n", 2)[1]
    for line in header.splitlines():
        match = re.match(r"^" + field + r":\s*(.*)\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def frontmatter_description(path: Path) -> str:
    value = frontmatter_field(path, "description")
    assert value, f"{path} declares no `description:`"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    assert value, f"{path} has an empty description"
    return value


def skills_with_doctrine() -> list[str]:
    return sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md")
                  if not p.parent.name.startswith("_"))


class OpenCodeCompatTests(unittest.TestCase):
    def test_roster_is_exactly_the_pinned_map(self) -> None:
        found = sorted(p.stem for p in AGENTS.glob("*.md"))
        self.assertEqual(found, sorted(AGENT_MODELS),
                         f"agent roster drifted: only-disk="
                         f"{sorted(set(found) - set(AGENT_MODELS))} "
                         f"only-map={sorted(set(AGENT_MODELS) - set(found))}")

    def test_every_agent_pins_its_mapped_model(self) -> None:
        for name, model in sorted(AGENT_MODELS.items()):
            actual = frontmatter_field(AGENTS / f"{name}.md", "model")
            self.assertEqual(actual, model,
                             f"{name}.md pins {actual}, map says {model}")

    def test_math_model_stays_on_its_only_holder(self) -> None:
        holders = sorted(name for name, model in AGENT_MODELS.items()
                         if model == MATH_ONLY_MODEL)
        self.assertEqual(holders, [MATH_ONLY_HOLDER])

    def test_contributor_model_touches_no_unpublished_draft(self) -> None:
        holders = sorted(name for name, model in AGENT_MODELS.items()
                         if model == CONTRIBUTOR_MODEL)
        self.assertEqual(sorted(holders), sorted(CONTRIBUTOR_SAFE_HOLDERS))

    def test_every_agent_is_a_v2_subagent(self) -> None:
        for path in sorted(AGENTS.glob("*.md")):
            body = path.read_text(encoding="utf-8")
            frontmatter_description(path)
            self.assertIn("\nmode: subagent", body,
                          f"{path.name} lacks `mode: subagent`")
            self.assertIn("\npermissions:", body,
                          f"{path.name} lacks a `permissions:` block")
            named = re.findall(r"\.opencode/skills/([\w-]+)/SKILL\.md", body)
            self.assertTrue(named, f"{path.name} names no skill to load")
            for skill in named:
                self.assertTrue((SKILLS / skill / "SKILL.md").is_file(),
                                f"{path.name} names {skill}, missing")

    def test_config_is_v2(self) -> None:
        self.assertTrue(CONFIG.is_file(), "opencode.json does not exist")
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertNotIn("permission", config,
                         "V1 `permission` object; V2 uses `permissions`")
        permissions = config.get("permissions")
        self.assertIsInstance(permissions, list)
        for rule in permissions:
            self.assertEqual(set(rule), {"action", "resource", "effect"},
                             f"malformed permission rule: {rule}")
            self.assertIn(rule["effect"], ("allow", "ask", "deny"))
        actions = {rule["action"] for rule in permissions}
        self.assertNotIn("bash", actions, "V1 action; V2 uses `shell`")
        self.assertNotIn("task", actions, "V1 action; V2 uses `subagent`")
        self.assertIn("mcp", config)
        self.assertIn("servers", config["mcp"],
                      "V2 nests servers under `mcp.servers`")
        self.assertEqual(config.get("model"), "opencode-go/mimo-v2.6-flash")

    def test_every_skill_has_a_command(self) -> None:
        skills = skills_with_doctrine()
        self.assertGreaterEqual(len(skills), 10)
        missing = [s for s in skills if not (COMMANDS / f"{s}.md").is_file()]
        self.assertEqual(missing, [],
                         f"skills without `.opencode/commands` wrapper: {missing}")
        for skill in skills:
            frontmatter_description(COMMANDS / f"{skill}.md")
            body = (COMMANDS / f"{skill}.md").read_text(encoding="utf-8")
            self.assertIn(f".opencode/skills/{skill}/SKILL.md", body,
                          f"command {skill}.md does not load its own skill")

    def test_plugin_relays_to_the_skill_hook(self) -> None:
        self.assertTrue(PLUGIN.is_file(), f"{PLUGIN} does not exist")
        src = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("tool.execute.before", src)
        self.assertIn(".opencode/skills/remote-execution/scripts/hooks/"
                      "refuse_offpath_push.py", src)
        self.assertIn("remote_cli.py", src)

    def test_no_other_harness_survives(self) -> None:
        for leftover in (".claude", ".pi", ".antigravity", "CLAUDE.md",
                         "PI.md", "skills"):
            self.assertFalse((ROOT / leftover).exists(),
                             f"{leftover} survived the single-harness cut")
        self.assertFalse(
            (ROOT / "src" / "papersmith" / "templates" / "claude.md.tpl").exists())


if __name__ == "__main__":
    unittest.main()
