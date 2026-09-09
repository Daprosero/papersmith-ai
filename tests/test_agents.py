"""Every agent is bound to a skill, and to that skill's own north.

An agent definition is the one place the purpose reaches a session BEFORE
anything happens: its `description` is the first thing in context on every
invocation. The skill declares the north and every refusal carries it, so it
arrives when you are blocked and when you ask -- and an agent is what makes it
arrive at the start, which is where losing it is cheapest to prevent.

That only holds while the two agree. A description that drifts from the
declared arrival is a north nobody updated, and the agent would open every
session with a destination the skill no longer has. So the arrival is read out
of the skill and asserted in the description rather than proof-read.

Stdlib only, for the same reason `test_suite_collects.py` is: this has to
survive an environment missing everything else.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / ".claude" / "agents"
SKILLS = ROOT / ".claude" / "skills"


def frontmatter(path: Path) -> dict:
    """The agent's own header, parsed without a YAML dependency.

    Three keys, one line each, values optionally quoted. A parser is not what
    this file is for, and pulling in YAML would put it back inside the class of
    things `test_suite_collects.py` exists to detect.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    header = text.split("---\n", 2)[1]
    found = {}
    for line in header.splitlines():
        match = re.match(r'^(\w+):\s*"?(.*?)"?\s*$', line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def declared_arrival(skill: str) -> str | None:
    """The `arrival` this skill's own `OBJECTIVE_FLOW` declares, or None.

    Read out of the source with `ast` rather than by importing it: importing a
    skill's CLI pulls in whatever it depends on, and this file may not depend
    on anything.
    """
    for script in sorted((SKILLS / skill).rglob("*.py")):
        # `__pycache__` holds `.pyc` under a `.py`-shaped name on some layouts
        # and is never source anyway; a decode error there would fail this file
        # for a reason that has nothing to do with what it checks.
        if "__pycache__" in script.parts:
            continue
        try:
            source = script.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # A kit template carries `{{TOKEN}}` placeholders and is not valid
            # Python until it is materialized. It is scaffolding, never a place
            # a north is declared, so failing on it would fail this file for a
            # reason that has nothing to do with what it checks.
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "OBJECTIVE_FLOW" not in names:
                continue
            flow = ast.literal_eval(node.value)
            return flow.get("arrival")
    return None


class AgentBindingTests(unittest.TestCase):

    def agents(self):
        return sorted(AGENTS.glob("*.md")) if AGENTS.is_dir() else []

    def test_there_is_at_least_one_agent(self) -> None:
        self.assertTrue(self.agents(), "no agent definitions to hold")

    def test_every_agent_names_its_own_file_and_an_existing_skill(self) -> None:
        for path in self.agents():
            header = frontmatter(path)
            self.assertEqual(header.get("name"), path.stem, path.name)
            self.assertTrue((SKILLS / path.stem).is_dir(),
                            f"{path.name} names no skill that exists")

    def test_every_agent_states_its_tools(self) -> None:
        """An agent that declares none inherits everything, which is the
        capability restriction silently not applied."""
        for path in self.agents():
            self.assertTrue(frontmatter(path).get("tools"), path.name)

    def test_a_description_carries_the_arrival_its_skill_declares(self) -> None:
        """The seal. If the north moves and the description does not, the agent
        opens every session with a destination the skill no longer has."""
        checked = 0
        for path in self.agents():
            arrival = declared_arrival(path.stem)
            if arrival is None:
                continue          # that skill declares no north; nothing to hold
            checked += 1
            self.assertIn(arrival, frontmatter(path).get("description", ""),
                          f"{path.name}'s description does not carry the "
                          f"arrival its own skill declares")
        self.assertGreater(checked, 0,
                           "no agent was actually checked against a declared "
                           "north, so this test proved nothing")
