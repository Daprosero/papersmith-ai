"""`suite_budget.code_line_count`'s own controls.

The counter decides whether a suite is over budget, so a counter that stopped
counting would read exactly like a suite that stopped growing. Every control
below is therefore paired: one that must be counted beside one that must not,
so a change that zeroed the count and a change that counted everything are
both caught rather than only the first.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import suite_budget  # noqa: E402  (path set above)


class CodeLineCountTests(unittest.TestCase):
    def test_a_plain_statement_is_counted(self) -> None:
        """The positive control. Without it, a counter that returned 0 for
        everything would satisfy every other case in this class."""
        self.assertEqual(suite_budget.code_line_count("x = 1\n"), 1)

    def test_blank_lines_are_not_counted(self) -> None:
        self.assertEqual(suite_budget.code_line_count("x = 1\n\n\n\ny = 2\n"), 2)

    def test_comment_only_lines_are_not_counted(self) -> None:
        source = "# why this exists\nx = 1\n    # and this\ny = 2\n"
        self.assertEqual(suite_budget.code_line_count(source), 2)

    def test_a_trailing_comment_does_not_exempt_its_code(self) -> None:
        """The other direction: only a line that is ONLY a comment is free.
        A comment after real code must not buy that line out of the budget,
        or the cheapest way under a cap becomes appending `  # note`."""
        self.assertEqual(suite_budget.code_line_count("x = 1  # a note\n"), 1)

    def test_a_module_docstring_is_not_counted(self) -> None:
        source = '"""Line one.\n\nLine three.\n"""\nx = 1\n'
        self.assertEqual(suite_budget.code_line_count(source), 1)

    def test_function_and_class_docstrings_are_not_counted(self) -> None:
        source = (
            'class A:\n'
            '    """What A is for.\n\n'
            '    At length.\n'
            '    """\n'
            '    def b(self):\n'
            '        """And what b does."""\n'
            '        return 1\n'
        )
        # `class A:`, `def b(self):`, `return 1` -- three lines of code.
        self.assertEqual(suite_budget.code_line_count(source), 3)

    def test_a_string_that_is_not_a_docstring_is_counted(self) -> None:
        """The control that a quote-hunting scanner would fail.

        A triple-quoted literal assigned to a name is code: it is data the
        suite carries, often a fixture. Only the FIRST statement of a body,
        and only a bare string constant, is a docstring -- which is why the
        counter asks `ast` instead of looking for quotes.
        """
        source = 'FIXTURE = """alpha\nbeta\n"""\n'
        self.assertEqual(suite_budget.code_line_count(source), 3)

    def test_a_second_string_statement_in_a_body_is_counted(self) -> None:
        """Only the first statement is the docstring; a bare string further
        down is an ordinary (if useless) expression and pays for itself."""
        source = 'def f():\n    """Real docstring."""\n    "not a docstring"\n    return 1\n'
        self.assertEqual(suite_budget.code_line_count(source), 3)

    def test_unparseable_source_refuses_instead_of_guessing(self) -> None:
        """A budget over a file the interpreter would reject is a number
        about nothing. Falling back to the raw line count would make an
        unparseable suite look cheaper than it is."""
        with self.assertRaises(SyntaxError):
            suite_budget.code_line_count("def broken(:\n")

    def test_the_counter_is_exercised_against_a_real_suite(self) -> None:
        """Non-vacuity: every case above is synthetic, so a counter that
        only worked on four-line strings would pass them all. This reads a
        real suite off disk and insists the answer is both non-zero and
        smaller than its raw line count -- the two ways the counter can be
        trivially wrong."""
        own = Path(__file__).resolve()
        source = own.read_text(encoding="utf-8")
        counted = suite_budget.code_line_count(source)
        raw = len(source.splitlines())
        self.assertGreater(counted, 0, "the counter found no code in a real suite")
        self.assertLess(
            counted, raw,
            "this module is mostly docstrings, so a count equal to its raw "
            "line total means nothing is being skipped",
        )


if __name__ == "__main__":
    unittest.main()
