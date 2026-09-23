"""The forge's own scaffolding: every declared source folder reaches a clone.

The rule the operator states for the whole forge is that **a skill creates the
folders it needs, the structure travels to GitHub and the content never does**.
`.gitignore` already enforces the second half for `guidance/` (`guidance/*/*`
with a `!guidance/*/.gitkeep` escape). Nothing enforced the first half, and it
was broken: `guidance/data-paper/` existed on this disk, is declared
`required: true` by `experimental-deliberation`'s profile, and had no
`.gitkeep` -- so a fresh clone arrived without the one source that domain
cannot draft without, while the *optional* `guidance/paper-guide/` shipped
fine.

Both sides are derived, neither is listed here:

  declared -- every `sources[].path` under `guidance/` in any skill's
      `profile.ts`. That array is not prose: it is what the engine loads, so a
      folder named there is a folder the forge tells you to fill.
  travelling -- every `guidance/*/.gitkeep` git actually tracks. Asked of git,
      not of the filesystem, because a folder that exists only on this disk is
      exactly the failure being tested.

Prose examples are correctly outside the set: `paper-ingestion`'s SKILL.md
mentions `guidance/datasets/` as an illustration of source-root discovery
("e.g. a `guidance/datasets/` folder"), and discovery finds any folder holding
a PDF, so illustrations must not become shipped scaffolding.
"""

import re
import subprocess
import sys
import unittest
from pathlib import Path

# The shared derivations live beside the suites, importable without being one.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import forge_vocabulary  # noqa: E402  (path set above)

FORGE_ROOT = Path(__file__).resolve().parent.parent
SKILLS = FORGE_ROOT / "skills"

#: `{ path: "guidance/x", ... }` and `{ path: CONST, ... }` alike; the constant
#: form is resolved against its own `const NAME = "guidance/x"` declaration so a
#: profile that names its source once, at the top, is still read.
SOURCE_ENTRY = re.compile(r'\{\s*path:\s*(?:"([^"]+)"|([A-Z_][A-Z0-9_]*))\s*,')
CONST_STRING = re.compile(r'(?m)^const\s+([A-Z_][A-Z0-9_]*)\s*=\s*"([^"]+)"\s*;')


def declared_guidance_sources() -> dict[str, list[str]]:
    """Guidance folder -> the profiles that declare it as a source."""
    declared: dict[str, list[str]] = {}
    for profile in sorted(SKILLS.glob("*/profile.ts")):
        text = profile.read_text(encoding="utf-8")
        constants = dict(CONST_STRING.findall(text))
        for literal, name in SOURCE_ENTRY.findall(text):
            path = literal or constants.get(name)
            if path and path.startswith("guidance/"):
                declared.setdefault(path, []).append(profile.parent.name)
    return declared


def travelling_guidance_folders() -> set[str]:
    """Folders whose `.gitkeep` git tracks -- what a clone actually receives.

    The derivation itself lives in `forge_vocabulary`, because rule B's denylist
    needs the identical answer to know which names are the forge's own structure
    rather than a paper's vocabulary. Two derivations would drift, and the half
    that drifted would report the forge leaking a folder the forge ships.
    """
    return {f"guidance/{name}" for name in forge_vocabulary.travelling_guidance_folders(FORGE_ROOT)}


class DeclaredGuidanceSourcesTravelTests(unittest.TestCase):
    def test_the_derivation_finds_something_to_check(self):
        """A silent empty set would let this whole file pass vacuously."""
        declared = declared_guidance_sources()
        self.assertGreaterEqual(
            len(declared), 2,
            "no guidance source parsed out of any profile.ts -- the regexes "
            "stopped matching the profiles' shape, so every assertion below "
            "is passing over an empty set",
        )

    def test_every_declared_guidance_source_reaches_a_clone(self):
        declared = declared_guidance_sources()
        travelling = travelling_guidance_folders()
        missing = {
            path: profiles
            for path, profiles in declared.items()
            if path not in travelling
        }
        self.assertEqual(
            missing, {},
            "declared as a source by a profile the engine loads, but no "
            "`.gitkeep` is tracked, so a fresh clone never receives the "
            "folder: " + ", ".join(
                f"{path} (declared by {', '.join(who)})"
                for path, who in sorted(missing.items())
            ),
        )

    def test_a_travelling_folder_holds_nothing_but_its_gitkeep(self):
        """The other half of the rule: structure travels, content never does."""
        tracked = subprocess.run(
            ["git", "ls-files", "guidance/"],
            cwd=FORGE_ROOT, capture_output=True, text=True, check=True,
        ).stdout.split()
        leaked = [e for e in tracked if Path(e).name != ".gitkeep"]
        self.assertEqual(
            leaked, [],
            "versioned under guidance/ but not a `.gitkeep` -- research "
            f"material reaching GitHub is the leak the rule exists to stop: {leaked}",
        )


if __name__ == "__main__":
    unittest.main()
