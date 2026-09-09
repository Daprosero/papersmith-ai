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
