"""Single harness: OpenCode natively, nothing projected, nothing ignored away.

There is no setup script anymore -- `.opencode/skills` holds the real skill
tree and `.opencode/agents` the real agent roster, both committed. The only
thing this file holds is the negative: no other harness directory may
reappear, and `.gitignore` may not hide the native tree from a fresh clone.
"""

import subprocess
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parent.parent
GITIGNORE = FORGE_ROOT / ".gitignore"

REMOVED_HARNESSES = (".claude", ".pi", ".antigravity", "CLAUDE.md", "PI.md",
                     "skills", "scripts/setup-harnesses.sh")


class SingleHarnessTests(unittest.TestCase):
    def test_no_other_harness_exists_on_disk(self) -> None:
        for leftover in REMOVED_HARNESSES:
            self.assertFalse((FORGE_ROOT / leftover).exists(),
                             f"{leftover} is back; this branch serves "
                             "OpenCode only")

    def test_the_native_tree_is_committable(self) -> None:
        """`.opencode/skills` and `.opencode/agents` are real files, so the
        ignore file must not exclude them -- otherwise a fresh clone would
        arrive without the skills and the agents nobody can see."""
        ignored = {line.strip()
                   for line in GITIGNORE.read_text(encoding="utf-8").split("\n")}
        for prefix in (".opencode/skills", ".opencode/agents"):
            for shape in (prefix, f"{prefix}/", ".opencode", ".opencode/"):
                self.assertNotIn(
                    shape, ignored,
                    f"`{shape}` in .gitignore hides the native {prefix} "
                    "tree from a fresh clone")

    def test_the_native_tree_travels_with_the_repository(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=FORGE_ROOT,
            capture_output=True, text=True, check=True).stdout.split("\n")
        pending = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=FORGE_ROOT,
            capture_output=True, text=True, check=True).stdout.split("\n")
        # `--others` covers work in progress; a fresh clone carries it all
        # committed, so either side counts.
        present = set(tracked) | set(pending)
        for prefix in (".opencode/skills/", ".opencode/agents/",
                       ".opencode/commands/"):
            carried = [p for p in present if p.startswith(prefix)]
            self.assertTrue(carried, f"nothing under {prefix} is committed")


if __name__ == "__main__":
    unittest.main()
