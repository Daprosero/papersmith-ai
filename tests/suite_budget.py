"""How many lines of CODE a suite spends, as distinct from how many lines it has.

A suite budget exists to stop a layer sprawling in scope. It is not a ration on
explanation, and the two were the same number until this module existed:
`tests/test_cli_paper_e2e.py` capped its own total line count, so a docstring
saying why a fixture is shaped the way it is competed for room with the
assertions it described. That cost was paid for real -- nine one-line
docstrings, added to explain nine fixtures, pushed the file from 796 to 805 and
broke the budget test, and the explanation was dropped rather than the fix.

A repository whose whole discipline is writing down WHY cannot also charge rent
for it. So the count below skips what a reader is owed and counts what the
suite actually does:

  skipped   blank lines; comment-only lines; every line of a module, class or
            function docstring
  counted   everything else

Docstrings are found with `ast`, not by looking for quote characters: a triple
quote appears inside ordinary string literals, and a line-oriented scanner
cannot tell a docstring from a fixture that contains one. `ast` is asked which
statements are docstrings, which is the question.

The counter is deliberately shared and separately tested (`test_suite_budget.py`)
rather than living inside the one suite it currently bounds. A budget that can
only be exercised by editing the file it constrains cannot be shown to work
without perturbing the thing it measures.
"""

from __future__ import annotations

import ast


def docstring_line_numbers(tree: ast.AST) -> set[int]:
    """Every line occupied by a module/class/function docstring in `tree`.

    A docstring is the first statement of its body and a bare string
    constant -- the same test the interpreter itself applies, so this cannot
    drift from what Python calls a docstring.
    """
    occupied: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            occupied.update(
                range(first.lineno, (first.end_lineno or first.lineno) + 1)
            )
    return occupied


def code_line_count(source: str) -> int:
    """Lines of `source` that are neither blank, comment, nor docstring.

    Raises `SyntaxError` on source that does not parse, deliberately: a
    budget computed over a file the interpreter would refuse is a number
    about nothing, and silently returning the raw line count would make an
    unparseable suite look like a cheaper one.
    """
    tree = ast.parse(source)
    skip = docstring_line_numbers(tree)
    counted = 0
    for number, line in enumerate(source.splitlines(), 1):
        if number in skip:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        counted += 1
    return counted
