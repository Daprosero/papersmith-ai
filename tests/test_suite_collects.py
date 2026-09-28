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

    def test_no_test_source_reads_through_a_removed_harness(self) -> None:
        """The canonical ``.opencode/skills`` tree is the only versioned copy;
        the removed harnesses (``.claude``, ``.pi``, ``.antigravity``) must not
        be reconstructed in path literals. Every source under ``tests/``,
        including non-`test_*.py`` helpers that unittest discovery never sees,
        must import and read skill modules through the versioned tree. Comment
        lines are not swept: matching requires an actual FORGE-rooted path
        construction.
        """
        projection = re.compile(
            r'FORGE(?:_ROOT)?\s*/\s*["\']\.(?:claude|pi|antigravity)["\']')
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
            "canonical `.opencode/skills` tree; the removed harnesses do not "
            "exist on CI or a fresh clone. Found: "
            + ", ".join(f"{k}: {v}" for k, v in sorted(offenders.items())))
