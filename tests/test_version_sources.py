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
import sys
import tomllib
import unittest
from pathlib import Path

import papersmith

FORGE_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = FORGE_ROOT / "package.json"
PYPROJECT = FORGE_ROOT / "pyproject.toml"

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


if __name__ == "__main__":
    unittest.main()
