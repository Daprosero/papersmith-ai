"""OpenCode compatibility seal: the `.opencode/` mirror stays complete.

`.claude/skills` is canonical (OpenCode discovers it natively) and
`.claude/agents` stays canonical for Claude Code. What OpenCode needs on top:

  commands -- one `.opencode/commands/<skill>.md` per skill with a SKILL.md,
      so `/name` keeps working (OpenCode skills load via the `skill` tool,
      slash commands are a separate namespace).
  agents   -- one `.opencode/agents/<stretch>.md` per `.claude/agents` file,
      same stem, same `description`, same body; only the frontmatter changes
      (`mode: subagent` + `permission:` instead of `tools:`).
  plugin   -- `.opencode/plugins/refuse-offpath-push.js` porting the
      `PreToolUse` tripwire onto `tool.execute.before`.
  config   -- `opencode.json` with `skill`/`question` allowed, push surfaces
      on `ask`, and an `mcp` key (migrated from `.mcp.json`).

Stdlib only, like `test_agents.py`.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_AGENTS = ROOT / ".claude" / "agents"
OPENCODE_AGENTS = ROOT / ".opencode" / "agents"
COMMANDS = ROOT / ".opencode" / "commands"
PLUGIN = ROOT / ".opencode" / "plugins" / "refuse-offpath-push.js"
CONFIG = ROOT / "opencode.json"
SKILLS = ROOT / ".claude" / "skills"

# Allowed subagent models. Qwen 3.8 Max is reserved for the single most
# critical mathematical-reasoning stretch (deliberation-publish, the terminal
# math gate) -- pinning it by name AND by exclusive holder below, so a later
# edit cannot quietly spread the scarcest pool. The Contributor-tier model
# trains on prompts, so it only hosts read-mostly mechanical stretches and
# never authorship: nothing that WRITES the unpublished paper, proposals or
# code runs on it (see CONTRIBUTOR_SAFE_HOLDERS).
ALLOWED_SUBAGENT_MODELS = {
    "opencode/qwen3.8-max",
    "opencode/deepseek-v4-pro",
    "opencode/deepseek-v4.1-flash",
    "opencode/deepseek-v4-flash-vision-exp",
    "opencode/mimo-v2.5",
    "opencode/muse-spark-1.3-contributor",
}
QWEN_MATH_ONLY_HOLDER = "deliberation-publish"
CONTRIBUTOR_SAFE_HOLDERS = {
    "style-sampler",      # verbatim copy of already-published references
    "paper-ingestion",    # published reference PDFs -> Markdown
    "insumos-observer",   # read-only: reports facts with quoted evidence
    "contract-auditor",   # read-only: judges drafts, writes no bytes
}


def frontmatter_field(path: Path, field: str) -> str | None:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    header = text.split("---\n", 2)[1]
    for line in header.splitlines():
        match = re.match(r'^' + field + r':\s*(.*)\s*$', line)
        if match:
            return match.group(1).strip()
    return None


def frontmatter_description(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} has no frontmatter"
    header = text.split("---\n", 2)[1]
    for line in header.splitlines():
        match = re.match(r'^description:\s*(.*)\s*$', line)
        if match:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            return value
    raise AssertionError(f"{path} declares no `description:`")


def skills_with_doctrine() -> list[str]:
    return sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))


class OpenCodeCompatTests(unittest.TestCase):
    def test_config_exists_and_parses(self) -> None:
        self.assertTrue(CONFIG.is_file(), "opencode.json does not exist")
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertIn("permission", config)
        self.assertIn("mcp", config)

    def test_config_keeps_skill_and_question_usable(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        perm = config["permission"]
        self.assertEqual(perm.get("skill"), "allow")
        self.assertEqual(perm.get("question"), "allow")

    def test_config_asks_on_push_surfaces(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        bash = config["permission"].get("bash", {})
        self.assertIsInstance(bash, dict)
        blob = json.dumps(bash)
        self.assertIn("kernels_push", blob)
        self.assertIn("kaggle_driver.py", blob)

    def test_every_skill_has_a_command(self) -> None:
        skills = skills_with_doctrine()
        self.assertGreaterEqual(len(skills), 9)
        missing = [s for s in skills if not (COMMANDS / f"{s}.md").is_file()]
        self.assertEqual(missing, [],
                         f"skills without `.opencode/commands` wrapper: {missing}")
        for skill in skills:
            desc = frontmatter_description(COMMANDS / f"{skill}.md")
            self.assertTrue(desc, f"command {skill}.md has empty description")
            body = (COMMANDS / f"{skill}.md").read_text(encoding="utf-8")
            self.assertIn(skill, body,
                          f"command {skill}.md never names its own skill")

    def test_agent_rosters_match(self) -> None:
        claude = sorted(p.stem for p in CLAUDE_AGENTS.glob("*.md"))
        opencode = sorted(p.stem for p in OPENCODE_AGENTS.glob("*.md"))
        self.assertTrue(claude)
        self.assertEqual(opencode, claude,
                         f".opencode/agents drifted from .claude/agents: "
                         f"only-claude={sorted(set(claude) - set(opencode))} "
                         f"only-opencode={sorted(set(opencode) - set(claude))}")

    def test_opencode_agents_keep_descriptions_and_bodies(self) -> None:
        for src in sorted(CLAUDE_AGENTS.glob("*.md")):
            mirror = OPENCODE_AGENTS / src.name
            self.assertTrue(mirror.is_file(), f"{src.name} has no mirror")
            self.assertEqual(frontmatter_description(mirror),
                             frontmatter_description(src),
                             f"{src.name} description drifted between runtimes")
            body = mirror.read_text(encoding="utf-8")
            self.assertIn("\nmode: subagent", body,
                          f"{mirror.name} lacks `mode: subagent`")
            self.assertIn("\npermission:", body,
                          f"{mirror.name} lacks a `permission:` block")
            named = re.findall(
                r"(?:\.claude|\.opencode)/skills/([\w-]+)/SKILL\.md", body)
            self.assertTrue(named, f"{mirror.name} names no skill to load")
            for skill in named:
                self.assertTrue((SKILLS / skill / "SKILL.md").is_file(),
                                f"{mirror.name} names {skill}, missing")

    def test_plugin_ports_the_tripwire(self) -> None:
        self.assertTrue(PLUGIN.is_file(), f"{PLUGIN} does not exist")
        src = PLUGIN.read_text(encoding="utf-8")
        self.assertIn("tool.execute.before", src)
        self.assertIn("remote_cli.py", src)
        self.assertIn("kaggle_driver.py", src)
        self.assertIn("kernels_push", src)

    def test_subagent_models_stay_inside_the_allowed_catalog(self) -> None:
        mirrors = sorted(OPENCODE_AGENTS.glob("*.md"))
        self.assertGreaterEqual(len(mirrors), 14)
        for mirror in mirrors:
            model = frontmatter_field(mirror, "model")
            self.assertTrue(model, f"{mirror.name} declares no `model:`")
            self.assertIn(model, ALLOWED_SUBAGENT_MODELS,
                          f"{mirror.name} uses {model}, outside the allowed "
                          f"catalog {sorted(ALLOWED_SUBAGENT_MODELS)}")

    def test_qwen_stays_on_the_critical_math_stretch_only(self) -> None:
        holders = sorted(
            p.stem for p in OPENCODE_AGENTS.glob("*.md")
            if frontmatter_field(p, "model") == "opencode/qwen3.8-max")
        self.assertEqual(holders, [QWEN_MATH_ONLY_HOLDER],
                         f"qwen3.8-max must stay on "
                         f"{QWEN_MATH_ONLY_HOLDER} only, found: {holders}")

    def test_contributor_model_touches_no_draft(self) -> None:
        for mirror in sorted(OPENCODE_AGENTS.glob("*.md")):
            if frontmatter_field(mirror, "model") == \
                    "opencode/muse-spark-1.3-contributor":
                self.assertIn(mirror.stem, CONTRIBUTOR_SAFE_HOLDERS,
                              f"{mirror.name} runs on a training-on-prompts "
                              f"tier but is not a read-mostly mechanical "
                              f"stretch -- move it to a non-training model")


if __name__ == "__main__":
    unittest.main()
