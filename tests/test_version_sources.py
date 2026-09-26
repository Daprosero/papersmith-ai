"""This project states its version twice, and only one statement is derived.

`pyproject.toml` does the right thing: it declares `dynamic = ["version"]`
and reads `papersmith.__version__`, so the Python distribution has exactly
one source and cannot drift from it. `package.json` carries its own literal.
The two agree today, and nothing asks them to.

That is the shape this repository already names elsewhere as prose outliving
its mechanism: a fact written in two places, with a mechanism holding only
one of them. Nobody notices until a release bumps one and ships the other,
and by then the wrong number is in whatever artifact carried it.

So this file asks three questions, all derived rather than restated:

  agreement   `package.json`'s literal equals the version the distribution
              actually builds with
  derivation  `pyproject.toml` still reads that version from the module
              rather than declaring a third literal of its own
  shape       both answers are real version strings, so the comparison
              cannot pass by matching two empty values

The third exists because the first two are equality checks, and two blanks
are equal. A guard that passes over nothing reads exactly like a guard that
looked.
"""

import json
import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

import papersmith

FORGE_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = FORGE_ROOT / "package.json"
PYPROJECT = FORGE_ROOT / "pyproject.toml"
CHANGELOG = FORGE_ROOT / "CHANGELOG.md"

#: A release tag, as this project spells one. `backup/...` tags exist and are
#: not releases, which is why the shape is matched rather than "any tag".
RELEASE_TAG = re.compile(r"^v(\d+\.\d+\.\d+)$")

#: What a user receives. `tests/` is deliberately absent: a suite growing is
#: not a reason to cut a release, and treating it as one would make every
#: guard added here demand a version bump of its own.
SHIPPED_ROOTS = ("src", "skills", "scripts")

#: The attribute `pyproject.toml` must keep reading. Named here because the
#: point of the assertion is that this exact indirection survives: any other
#: value, including a literal that happens to be correct today, reintroduces
#: the third source this file exists to refuse.
DERIVED_FROM = "papersmith.__version__"

#: Loose on purpose. This file is not the place to rule on a versioning
#: scheme -- that is an unmade product decision -- but "at least two
#: dot-separated numbers" is enough to tell a version from an empty string
#: or a placeholder, which is all the non-vacuity check needs.
VERSION_SHAPE = re.compile(r"^\d+\.\d+(\.\d+)?([-.+].*)?$")


def manifest_version() -> str:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]


def distribution_version() -> str:
    """What the built distribution carries, asked of the module `pyproject`
    reads rather than of the file it lives in.

    Reading the source text with a regex would test a different thing: that
    a literal is spelled a certain way, not that the package exposes it.
    `setuptools` imports this attribute, so importing it is the same
    question the build asks.
    """
    return papersmith.__version__


class VersionSourcesAgreeTests(unittest.TestCase):
    def test_both_sources_state_a_real_version(self) -> None:
        """Non-vacuity. The assertions below compare two strings, and two
        empty strings compare equal, so a `package.json` that lost its
        `version` key and a module whose attribute became `""` would pass
        a bare equality check while stating nothing at all."""
        for label, value in (("package.json", manifest_version()),
                             (DERIVED_FROM, distribution_version())):
            with self.subTest(source=label):
                self.assertTrue(value, f"{label} states no version at all")
                self.assertRegex(
                    value, VERSION_SHAPE,
                    f"{label} states {value!r}, which is not a version")

    def test_the_node_manifest_matches_the_distribution(self) -> None:
        node = manifest_version()
        distribution = distribution_version()
        self.assertEqual(
            node, distribution,
            f"package.json says {node!r} and the distribution builds "
            f"{distribution!r}. One of them ships in an artifact that says "
            "the wrong thing, and which one depends only on who reads it")

    def test_pyproject_still_derives_instead_of_restating(self) -> None:
        """The agreement above is only maintainable while the Python side
        stays derived. A third literal would make the next release a
        three-way edit, and the assertion above would still pass with two
        of the three bumped."""
        pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        project = pyproject.get("project", {})
        self.assertIn(
            "version", project.get("dynamic", []),
            "pyproject.toml no longer declares its version dynamic, so it "
            "now carries a literal of its own")
        self.assertNotIn(
            "version", project,
            "pyproject.toml declares a static version beside the dynamic "
            "one, which is the third source this file refuses")
        dynamic = pyproject.get("tool", {}).get("setuptools", {}).get("dynamic", {})
        self.assertEqual(
            dynamic.get("version"), {"attr": DERIVED_FROM},
            f"pyproject.toml must keep reading {DERIVED_FROM}; it reads "
            f"{dynamic.get('version')!r}")

    def test_the_imported_module_is_this_checkout(self) -> None:
        """`papersmith` is installed editable, so the attribute read above
        should come from this tree. If a different installation shadowed it,
        every assertion here would be about someone else's version and would
        keep passing while this checkout drifted."""
        source = Path(papersmith.__file__).resolve()
        self.assertEqual(
            source, (FORGE_ROOT / "src" / "papersmith" / "__init__.py").resolve(),
            f"`import papersmith` resolved to {source}, which is not this "
            f"checkout. Run `npm run setup:env` so the editable install "
            "points here (interpreter: " + sys.executable + ")")


class ReleaseHygieneTests(unittest.TestCase):
    """A version that never moves makes everything downstream of it inert.

    `0.1.0` was set in the commit that created the package and did not change
    again for more than a thousand commits. Nothing was wrong with the code
    that read it -- `upgrade` compares versions to refuse a downgrade, and
    that comparison is correct -- but with one value in circulation it could
    never fire. A guard that cannot fire and a guard that passes look the
    same from outside, which is the failure this class exists to make loud.
    """

    @staticmethod
    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=FORGE_ROOT,
            capture_output=True, text=True, check=True).stdout

    def _release_tags(self) -> list[tuple[tuple[int, ...], str, str]]:
        """Every release tag as `(order, tag, version)`, oldest first."""
        found = []
        for line in self._git("tag").split("\n"):
            matched = RELEASE_TAG.match(line.strip())
            if matched:
                version = matched.group(1)
                found.append((tuple(int(p) for p in version.split(".")),
                              line.strip(), version))
        return sorted(found)

    def test_the_changelog_documents_the_current_version(self) -> None:
        """A bump with no entry leaves a reader asking git what changed, which
        is the state this file was written to end. Checked against the version
        the distribution builds, so a changelog can only be right about the
        version that actually ships."""
        self.assertTrue(CHANGELOG.is_file(), f"no changelog at {CHANGELOG}")
        text = CHANGELOG.read_text(encoding="utf-8")
        version = distribution_version()
        self.assertRegex(
            text, re.compile(rf"^##\s+{re.escape(version)}\s*$", re.MULTILINE),
            f"the distribution builds {version} and CHANGELOG.md has no "
            f"`## {version}` section, so the version moved and the record "
            "did not")

    def test_shipped_changes_since_the_last_release_moved_the_version(self) -> None:
        """Once a release is tagged, changing what users receive without
        moving the version is what froze `0.1.0` for a thousand commits.

        Skips -- announced, never silently -- until a release tag exists,
        because before the first one there is no claim to compare against.
        An announced skip and a pass are different answers and this
        repository keeps them apart deliberately.
        """
        tags = self._release_tags()
        if not tags:
            self.skipTest(
                "no release tag matching `vN.N.N` exists yet, so there is no "
                "released version to compare against; this is silence rather "
                "than a pass")
        _, tag, released = tags[-1]
        changed = [path for path in
                   self._git("diff", "--name-only", f"{tag}..HEAD", "--",
                             *SHIPPED_ROOTS).split("\n") if path.strip()]
        if not changed:
            return
        self.assertNotEqual(
            distribution_version(), released,
            f"{len(changed)} shipped file(s) changed since {tag} and the "
            f"version is still {released}. Two builds a user cannot tell "
            f"apart are two builds `upgrade` cannot order either. First "
            f"changed: {changed[0]}")


if __name__ == "__main__":
    unittest.main()
