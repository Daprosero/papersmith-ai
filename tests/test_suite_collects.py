"""Every test module in this suite actually loads.

The defect this closes is circular and cost 730 invisible tests. `test_forge_gate`
already carries a collection check -- and it needs PyYAML to import, so on a
machine without it the module that would report the problem is itself one of the
modules that did not load. The suite then ran 2020 of 2750 tests and said `OK` on
every one it managed to reach, which is indistinguishable from a green suite.

So this module imports NOTHING outside the standard library, deliberately and
permanently. It is the one check that has to survive an environment missing
everything else, and any dependency added here would put it back inside the
class of things it exists to detect.

It reports the reason, not just the count: a module that fails to load because a
declared dependency is absent is an environment to fix, and one that fails to
load because of a syntax error is a defect -- and a bare "did not collect" reads
the same for both.
"""

import re
import unittest
import unittest.loader
from pathlib import Path

TESTS = Path(__file__).resolve().parent


class SuiteCollectsTests(unittest.TestCase):

    def test_every_test_module_loads(self) -> None:
        loader = unittest.loader.TestLoader()
        suite = loader.discover(str(TESTS), pattern="test_*.py",
                                top_level_dir=str(TESTS))

        broken = {}

        def walk(node):
            for child in node:
                if isinstance(child, unittest.TestSuite):
                    walk(child)
                    continue
                name = getattr(child, "_testMethodName", "")
                if type(child).__name__ == "_FailedTest":
                    try:
                        child.debug()
                    except Exception as reason:      # noqa: BLE001 -- the reason IS the report
                        broken[name] = f"{type(reason).__name__}: {reason}"
                    else:
                        broken[name] = "did not load, and gave no reason"

        walk(suite)

        self.assertEqual(
            broken, {},
            "a test module did not load, so every test it holds silently did "
            "not run -- a suite that reports OK over the modules it managed to "
            "reach is indistinguishable from a green one. Install what the "
            "declared manifest names, or fix the module")

    def test_no_test_source_reads_the_generated_skill_projection(self) -> None:
        """The canonical ``skills/`` tree is the only versioned copy; the
        ``.claude/skills`` projection is gitignored and absent on a fresh
        clone. A test that builds FORGE/FORGE_ROOT-rooted paths through it
        fails exactly the way the 13-test CI regression did (run
        35758553625): imports still resolve through sys.path entries seeded
        by earlier-collected modules, then `read_text()` on the missing
        projection dies with FileNotFoundError at test time -- a suite that
        says OK over the modules it reached is indistinguishable from a
        green one. Every source under ``tests/``, including non-`test_*.py``
        helpers that unittest discovery never sees, must import and read
        skill modules through the versioned tree. Comment lines are not
        swept: matching the bare ``"skills"``/``".claude"`` join requires
        an actual FORGE-rooted path construction, so the workspace-e2e
        `HARNESS_LINKS` literal needs no carve-out.
        """
        projection = re.compile(
            r'FORGE(?:_ROOT)?\s*/\s*["\']\.claude["\']\s*/\s*["\']skills["\']')
        offenders: dict[str, str] = {}
        for source in sorted(TESTS.rglob("*.py")):
            for number, line in enumerate(
                    source.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if projection.search(line):
                    offenders[f"{source.relative_to(TESTS)}:{number}"] = line.strip()

        self.assertEqual(
            offenders, {},
            "test sources must import and read skill modules through the "
            "canonical `skills/` tree; the generated `.claude/skills` "
            "projection is gitignored and does not exist on CI or a fresh "
            "clone, so those 13 tests fail there. Found: "
            + ", ".join(f"{k}: {v}" for k, v in sorted(offenders.items())))
