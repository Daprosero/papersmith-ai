"""From-scratch agent series: every subagent definition, inside the workspace.

Layer purpose. ``test_agents.py`` holds the deep two-way binding contract for
the repository's own copies; this module proves the *shipped* copies — the
``.opencode/agents`` tree every ``papersmith init`` workspace carries — arrive
whole, parse, resolve the skill each stretch loads, and reach the OpenCode
routing document. An agent that only exists in the repository is not a shipped
subagent.

Read-only: nothing here launches a model or mutates a workspace.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import unittest
from pathlib import Path

from papersmith.generators import check_generated

from workspace_series import REPO_ROOT, make_workspace, new_tmp

ROUTING_DOCS = ("AGENTS.md",)
SKILL_BINDING = re.compile(r".opencode/skills/([\w-]+)/SKILL\.md")


def frontmatter(path: Path) -> dict[str, str]:
    """Parse the single-line key/value frontmatter an agent definition carries."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", f"{path} has no frontmatter"
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            value = value.strip()
            if value[:1] in {"'", '"'}:
                value = ast.literal_eval(value)
            metadata[key.strip()] = value
    return metadata


def agent_files(workspace: Path) -> list[Path]:
    return sorted((workspace / ".opencode" / "agents").glob("*.md"))


class AgentShippingTests(unittest.TestCase):

    def test_every_repository_agent_ships_in_the_workspace(self) -> None:
        workspace = make_workspace(new_tmp(self))
        repo = {path.name for path in (REPO_ROOT / ".opencode/agents").glob("*.md")}
        shipped = {path.name for path in agent_files(workspace)}
        self.assertTrue(repo, "the repository must define agents")
        self.assertEqual(shipped, repo, "the workspace must ship the whole agent tree")

    def test_every_shipped_agent_matches_its_recorded_bytes(self) -> None:
        workspace = make_workspace(new_tmp(self))
        manifest = json.loads(
            (workspace / ".papersmith" / "manifest.json").read_text(encoding="utf-8"))
        for path in agent_files(workspace):
            relpath = path.relative_to(workspace).as_posix()
            with self.subTest(agent=path.name):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(manifest["files"].get(relpath), digest,
                                 f"{relpath} does not match the workspace manifest")


class AgentContractTests(unittest.TestCase):

    def test_every_agent_parses_and_names_itself(self) -> None:
        workspace = make_workspace(new_tmp(self))
        for path in agent_files(workspace):
            with self.subTest(agent=path.name):
                metadata = frontmatter(path)
                # The filename is the name; a `name:` key, when present,
                # must agree with it.
                self.assertEqual(metadata.get("name", path.stem), path.stem)
                self.assertTrue(metadata.get("description", "").strip(),
                                "an agent without a description opens every session blind")
                self.assertEqual(metadata.get("mode"), "subagent")
                self.assertTrue(metadata.get("model", "").strip(),
                                "an agent must pin the model it runs on")

    def test_every_agent_skill_binding_resolves_in_the_workspace(self) -> None:
        workspace = make_workspace(new_tmp(self))
        for path in agent_files(workspace):
            with self.subTest(agent=path.name):
                named = SKILL_BINDING.findall(path.read_text(encoding="utf-8"))
                self.assertTrue(named, f"{path.name} names no skill to load")
                for skill in named:
                    self.assertTrue(
                        (workspace / ".opencode" / "skills" / skill / "SKILL.md").is_file(),
                        f"{path.name} names {skill}, which the workspace does not ship",
                    )


class AgentRoutingTests(unittest.TestCase):

    def test_every_routing_doc_lists_every_agent_verbatim(self) -> None:
        workspace = make_workspace(new_tmp(self))
        metadata = {path.stem: frontmatter(path) for path in agent_files(workspace)}
        for doc_name in ROUTING_DOCS:
            text = (workspace / doc_name).read_text(encoding="utf-8")
            self.assertIn(".opencode/skills/", text, f"{doc_name} must route to the skill tree")
            for stem, fields in metadata.items():
                with self.subTest(doc=doc_name, agent=stem):
                    self.assertIn(f"- `{stem}`", text)
                    self.assertIn(fields["description"], text)

    def test_generated_projections_are_clean_and_tamper_evident(self) -> None:
        workspace = make_workspace(new_tmp(self))
        self.assertEqual(check_generated(workspace), [],
                         "a fresh workspace must carry no generator drift")
        agents = workspace / "AGENTS.md"
        agents.write_text("drift\n", encoding="utf-8")
        self.assertIn("AGENTS.md", check_generated(workspace))

    def test_agent_tree_is_declared_the_single_source_of_truth(self) -> None:
        workspace = make_workspace(new_tmp(self))
        doc = (workspace / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(".opencode/agents", doc)

    def test_generated_routing_docs_document_their_command_surface(self) -> None:
        workspace = make_workspace(new_tmp(self))
        doc = (workspace / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(".opencode/commands/", doc)
        self.assertIn("refuse-offpath-push.js", doc)
