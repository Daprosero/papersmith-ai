"""Every harness the setup script serves must be visible in a fresh clone.

`scripts/setup-harnesses.sh` projects the canonical `skills/` tree into one
directory per harness. Those links are generated, so they are ignored -- but
ignoring the whole harness directory instead of just the link makes that
harness invisible to anyone who clones the repository. A collaborator then
sees three harness directories, concludes the fourth is unsupported, and is
reasonably right to: nothing in the tree says otherwise.

That is what happened to Pi. `.gitignore` carried `.pi/` where its siblings
carried `.claude/skills`, so no file under `.pi/` could ever be committed and
the directory did not exist until somebody ran the setup script.

The roster below is derived from the shell script's own `HARNESSES` array
rather than restated here, because a fifth harness added to that array and not
to this file is exactly the drift these assertions exist to catch.
"""

import importlib.util
import re
import subprocess
import unittest
from pathlib import Path

from papersmith.core import manifest

FORGE_ROOT = Path(__file__).resolve().parent.parent
SETUP = FORGE_ROOT / "scripts" / "setup-harnesses.sh"
GITIGNORE = FORGE_ROOT / ".gitignore"
INSPECTOR = FORGE_ROOT / "skills" / "_core" / "command_center" / "health_inspector.py"

#: The shell array carries ``relpath:Label`` only, so the owning tool of each
#: label is stated here, explicitly: a tool is never derived from a path or a
#: label. A new shell label with no row below fails the roster test by name.
LABEL_TO_TOOL = {
    "Claude Code": "claude",
    "Pi": "pi",
    "OpenCode": "opencode",
    "Google Antigravity": "antigravity",
    "Antigravity (.agents)": "antigravity",
}

#: `  ".pi/skills:Pi"` -> ("\.pi/skills", "Pi"). Matched against the array the
#: script actually iterates, so the test cannot pass over a roster nobody uses.
ENTRY = re.compile(r'^\s*"([^":]+):([^"]+)"\s*$', re.MULTILINE)


def declared_harnesses() -> list[tuple[str, str]]:
    """Every `<relative skills dir>, <label>` pair the setup script serves."""
    source = SETUP.read_text(encoding="utf-8")
    block = re.search(r"HARNESSES=\((.*?)\n\)", source, re.DOTALL)
    if not block:
        raise AssertionError(
            f"no HARNESSES=( ... ) array found in {SETUP}; this test derives "
            "its roster from that array and has nothing to assert without it")
    return ENTRY.findall(block.group(1))


def shell_pairs() -> set[tuple[str, str]]:
    """``(tool, relpath)`` pairs of the shell array, via the explicit label table."""
    unknown = [label for _, label in declared_harnesses() if label not in LABEL_TO_TOOL]
    if unknown:
        raise AssertionError(
            f"setup-harnesses.sh labels {unknown} have no row in LABEL_TO_TOOL; "
            "state which tool owns each new link")
    return {(LABEL_TO_TOOL[label], rel) for rel, label in declared_harnesses()}


def inspector_pairs() -> set[tuple[str, str]]:
    """The inspector's stdlib-only fallback roster, imported by path."""
    spec = importlib.util.spec_from_file_location("health_inspector_under_test", INSPECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return set(module._FALLBACK_SKILL_LINKS)


def roster_drift(reference: set[tuple[str, str]],
                 other: set[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """Pairs only in ``reference`` and pairs only in ``other``; both empty when equal."""
    return {"missing": sorted(reference - other), "extra": sorted(other - reference)}


class HarnessParityTests(unittest.TestCase):
    def test_the_roster_is_derived_and_not_empty(self) -> None:
        """Non-vacuity. A regex that stopped matching would make every
        assertion below pass over an empty list, and a roster that found no
        harnesses reads exactly like a repository with no drift."""
        found = declared_harnesses()
        self.assertGreaterEqual(
            len(found), 4,
            f"derived only {found} from {SETUP.name}; the assertions below "
            "would be checking nothing")
        self.assertIn("Pi", [label for _, label in found])

    def test_each_harness_ignores_its_generated_link_and_nothing_more(self) -> None:
        """The link is generated, so it is ignored. The directory holding it
        is not generated, and ignoring it hides the harness from the tree."""
        ignored = {line.strip() for line in GITIGNORE.read_text(encoding="utf-8").split("\n")}
        for rel, label in declared_harnesses():
            with self.subTest(harness=label):
                self.assertIn(
                    rel, ignored,
                    f"{label}'s generated link `{rel}` is not ignored; a "
                    "rebuilt symlink would show up as a repository change")
                parent = rel.split("/")[0]
                for shape in (parent, f"{parent}/"):
                    self.assertNotIn(
                        shape, ignored,
                        f"`{shape}` ignores {label}'s whole directory, not "
                        f"just its generated link. Nothing under it can be "
                        f"committed, so the directory does not exist in a "
                        f"fresh clone and {label} reads as unsupported")

    def test_each_harness_directory_travels_with_the_repository(self) -> None:
        """Ignoring only the link is permission, not presence. A directory
        with nothing committed in it still arrives absent."""
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=FORGE_ROOT,
            capture_output=True, text=True, check=True).stdout.split("\n")
        for rel, label in declared_harnesses():
            parent = rel.split("/")[0]
            with self.subTest(harness=label):
                carried = [p for p in tracked if p.startswith(f"{parent}/")]
                self.assertTrue(
                    carried,
                    f"{parent}/ holds no committed file, so it is absent from "
                    f"a fresh clone and a collaborator has no sign {label} is "
                    "a supported harness. One tracked file is enough, and it "
                    "should say why the directory looks empty")

    def test_roster_drift_names_missing_and_extra_pairs(self) -> None:
        """Non-vacuity for the checker itself: a drifted roster must be seen."""
        reference = {("claude", ".claude/skills"), ("pi", ".pi/skills")}
        drifted = {("claude", ".claude/skills"), ("opencode", ".opencode/skills")}
        self.assertEqual(roster_drift(reference, reference), {"missing": [], "extra": []})
        self.assertEqual(
            roster_drift(reference, drifted),
            {"missing": [("pi", ".pi/skills")], "extra": [("opencode", ".opencode/skills")]})

    def test_shell_manifest_and_inspector_agree_on_the_link_roster(self) -> None:
        """One roster, stated three times by design (shell stays pure shell and
        the inspector stays stdlib-only), so agreement is enforced here."""
        shell = shell_pairs()
        self.assertEqual(len(shell), len(declared_harnesses()), "duplicate shell entry")
        canonical = set(manifest.HARNESS_SKILL_LINKS)
        self.assertEqual(
            roster_drift(canonical, shell), {"missing": [], "extra": []},
            "setup-harnesses.sh HARNESSES disagrees with manifest.HARNESS_SKILL_LINKS")
        self.assertEqual(
            roster_drift(canonical, inspector_pairs()), {"missing": [], "extra": []},
            "health_inspector._FALLBACK_SKILL_LINKS disagrees with "
            "manifest.HARNESS_SKILL_LINKS")

    def test_antigravity_keeps_its_documented_and_legacy_links(self) -> None:
        """The two Antigravity links are deliberate (manifest.py): `.agents/skills`
        is the documented path and `.antigravity/skills` stays so no existing
        workspace loses a path it already uses."""
        wanted = {("antigravity", ".agents/skills"), ("antigravity", ".antigravity/skills")}
        for name, pairs in (("shell", shell_pairs()),
                            ("manifest", set(manifest.HARNESS_SKILL_LINKS)),
                            ("inspector", inspector_pairs())):
            with self.subTest(roster=name):
                self.assertTrue(wanted <= pairs, f"{name} lost an Antigravity link")


if __name__ == "__main__":
    unittest.main()
