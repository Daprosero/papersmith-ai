"""Every test-side scratch-directory helper must resolve what it hands back.

On macOS, `tempfile` hands out paths under `/var`, and `/var` is a symlink to
`/private/var`. Production code such as `python.run_script()` (and several
other bridges) calls `.resolve()` on the workspace it is given, because the
path it builds internally is later compared against the path the caller
handed it. When a test-side fixture builds a scratch directory from
`tempfile.TemporaryDirectory()` or `tempfile.mkdtemp()` and returns it
*without* resolving it, the fixture's own value and production's own answer
are two spellings of the same directory (`/var/...` vs `/private/var/...`)
that compare unequal. The test then fails on a platform detail while the
code under it is correct -- the fixture is what is wrong, not the assertion
and not production. See `tests/test_papersmith_bridges.py::BridgesTests.new_tmp`
for the corrected shape and its own explanation.

Resolving once, inside the helper, beats resolving at every call site: every
caller of the helper -- and every future caller -- inherits the fix for
free, instead of each assertion having to remember to call `.resolve()` on
what it got back. A helper that forgets to resolve reintroduces exactly the
bug this file exists to catch, silently, the next time someone copies the
`new_tmp`/`mkdtemp` shape into a new test class.

This file is the lock: it derives the set of test modules from `tests/` on
disk (never a hardcoded file list, which would go stale the moment a new
suite is added), parses each one with `ast`, and fails, naming every
offending `file:line` and function name, when a function's `return`
statement builds a `Path(...)` directly from a `TemporaryDirectory`/
`mkdtemp` value without a `.resolve()` call on the returned expression.

A regex over source text would both miss spellings (`Path(x).resolve()` with
whitespace, an aliased `resolve(strict=True)` call, a nested expression) and
could fire on prose mentioning "resolve" in a docstring or comment; the AST
walk sees only real `Return` nodes and real `Call` nodes, so it cannot be
fooled by either.
"""

import ast
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# The two spellings this repository's test suite actually uses to obtain a
# scratch directory. Both are attribute calls (`tempfile.TemporaryDirectory`,
# `tempfile.mkdtemp`) in every real site found on this disk, but the bare
# name is also accepted in case a future test does `from tempfile import
# mkdtemp`.
_TEMP_SOURCE_CALL_NAMES = {"TemporaryDirectory", "mkdtemp"}


def _is_temp_producing_call(node: ast.AST) -> bool:
    """True when `node` is a call to `tempfile.TemporaryDirectory()` /
    `tempfile.mkdtemp()`, or a bare `TemporaryDirectory()` / `mkdtemp()`
    reached through a `from tempfile import ...`.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in _TEMP_SOURCE_CALL_NAMES
    if isinstance(func, ast.Name):
        return func.id in _TEMP_SOURCE_CALL_NAMES
    return False


def _is_resolve_call(node: ast.AST) -> bool:
    """True when `node` is `<expr>.resolve()` (with or without arguments)."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "resolve"
    )


def _path_call_is_unresolved_temp(call: ast.Call, temp_holder_names: set) -> bool:
    """True when `call` is `Path(<temp-producing-expression>)`.

    `<temp-producing-expression>` is either the temp call inlined
    (`Path(tempfile.mkdtemp())`), or `<name>.name` where `<name>` was bound
    earlier in the same function to a `TemporaryDirectory()` result
    (`holder = tempfile.TemporaryDirectory(); ...; Path(holder.name)`).
    """
    if not (isinstance(call.func, ast.Name) and call.func.id == "Path"):
        return False
    if not call.args:
        return False
    arg = call.args[0]
    if _is_temp_producing_call(arg):
        return True
    if isinstance(arg, ast.Attribute) and arg.attr == "name" and isinstance(arg.value, ast.Name):
        return arg.value.id in temp_holder_names
    return False


def _own_descendants(node: ast.AST):
    """Yield every descendant of `node`, without crossing into a nested
    function or lambda's own scope.

    This keeps each function's analysis local: a helper defined *inside*
    another function is analyzed on its own turn (`ast.walk` on the whole
    module still visits it directly), and its returns/assignments never get
    attributed to the outer function.
    """
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        yield child
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(child))


def find_unresolved_scratch_returns(source: str, filename: str = "<string>"):
    """Return `(function_name, lineno)` for every function in `source` whose
    body returns an unresolved `Path(...)` built from a
    `TemporaryDirectory`/`mkdtemp` value.

    Two passes per function, restricted to that function's own scope via
    `_own_descendants`:
      1. collect every local name assigned directly from a temp-producing
         call (`holder = tempfile.TemporaryDirectory()`);
      2. inspect every `return`, and flag it unless its value is a
         `.resolve()` call, or is not a temp-derived `Path(...)` at all.
    """
    tree = ast.parse(source, filename=filename)
    findings = []

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        temp_holder_names = set()
        for stmt in _own_descendants(func):
            if (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
                and _is_temp_producing_call(stmt.value)
            ):
                temp_holder_names.add(stmt.targets[0].id)

        for stmt in _own_descendants(func):
            if not (isinstance(stmt, ast.Return) and stmt.value is not None):
                continue
            value = stmt.value
            if _is_resolve_call(value):
                continue
            if isinstance(value, ast.Call) and _path_call_is_unresolved_temp(value, temp_holder_names):
                findings.append((func.name, stmt.lineno))

    return findings


def discover_test_modules():
    """Every `.py` file under `tests/`, derived from disk -- never a
    hardcoded list, which would go stale the moment a new suite file is
    added. `__pycache__` is the only exclusion.
    """
    return sorted(
        path for path in TESTS_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
    )


class ScratchFixtureResolutionDerivationTests(unittest.TestCase):
    """Non-vacuity: prove the scan actually found and parsed test modules.

    A path typo in `discover_test_modules` (wrong directory, wrong glob)
    would make the main guard below pass by finding nothing to check --
    which reads as compliance while checking nothing. See the local idiom in
    `tests/test_forge_scaffolding.py::DeclaredGuidanceSourcesTravelTests
    ::test_the_derivation_finds_something_to_check`.
    """

    def test_the_derivation_finds_something_to_check(self) -> None:
        modules = discover_test_modules()
        self.assertGreaterEqual(
            len(modules), 50,
            "the scan under tests/ found fewer than 50 Python files -- "
            "discover_test_modules() is very likely pointed at the wrong "
            "directory, so the guard below would be checking almost nothing",
        )
        total_bytes = sum(module.stat().st_size for module in modules)
        self.assertGreater(
            total_bytes, 100_000,
            "the discovered modules total under 100KB of source -- that is "
            "far too little for this suite; the derivation is not reading "
            "real files",
        )
        parsed_functions = 0
        for module in modules:
            # An empty `__init__.py` is legitimate and expected here (e.g.
            # tests/experiments_seal/__init__.py); only the aggregate byte
            # count above is the non-vacuity signal, not each file alone.
            source = module.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(module))
            parsed_functions += sum(
                1 for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
        self.assertGreater(
            parsed_functions, 100,
            "parsing every discovered module found fewer than 100 function "
            "definitions in total -- the files are not being parsed",
        )


class ScratchFixtureResolutionDetectorControlTests(unittest.TestCase):
    """Positive and negative controls for the detector itself.

    Without a positive control, a detector that silently stopped matching
    (a refactor of `_is_temp_producing_call`, an AST shape it never saw
    coming) would read as a clean sweep instead of as a broken lock -- this
    repository's own established doctrine is that an untested guard is not
    a guard.
    """

    def test_detector_flags_the_holder_name_shape(self) -> None:
        synthetic = (
            "import tempfile\n"
            "from pathlib import Path\n"
            "\n"
            "class T:\n"
            "    def new_tmp(self):\n"
            "        holder = tempfile.TemporaryDirectory()\n"
            "        self.addCleanup(holder.cleanup)\n"
            "        return Path(holder.name)\n"
        )
        found = find_unresolved_scratch_returns(synthetic, filename="<synthetic-holder>")
        self.assertEqual(found, [("new_tmp", 8)])

    def test_detector_flags_the_inline_mkdtemp_shape(self) -> None:
        synthetic = (
            "import tempfile\n"
            "from pathlib import Path\n"
            "\n"
            "def new_tmp():\n"
            "    return Path(tempfile.mkdtemp())\n"
        )
        found = find_unresolved_scratch_returns(synthetic, filename="<synthetic-mkdtemp>")
        self.assertEqual(found, [("new_tmp", 5)])

    def test_detector_does_not_flag_the_resolved_shape(self) -> None:
        synthetic = (
            "import tempfile\n"
            "from pathlib import Path\n"
            "\n"
            "class T:\n"
            "    def new_tmp(self):\n"
            "        holder = tempfile.TemporaryDirectory()\n"
            "        self.addCleanup(holder.cleanup)\n"
            "        return Path(holder.name).resolve()\n"
        )
        found = find_unresolved_scratch_returns(synthetic, filename="<synthetic-resolved>")
        self.assertEqual(found, [])

    def test_detector_does_not_flag_an_unrelated_path_return(self) -> None:
        synthetic = (
            "from pathlib import Path\n"
            "\n"
            "def workspace(tmp_path):\n"
            "    return Path(tmp_path) / 'workspace'\n"
        )
        found = find_unresolved_scratch_returns(synthetic, filename="<synthetic-unrelated>")
        self.assertEqual(found, [])


class ScratchFixtureResolutionGuardTests(unittest.TestCase):
    """The lock itself: no test module may return an unresolved
    scratch-directory Path from a helper function.
    """

    def test_no_test_helper_returns_an_unresolved_scratch_directory(self) -> None:
        offenders = []
        for module_path in discover_test_modules():
            source = module_path.read_text(encoding="utf-8")
            try:
                found = find_unresolved_scratch_returns(source, filename=str(module_path))
            except SyntaxError as exc:  # pragma: no cover - would mean a broken test file
                self.fail(f"{module_path} failed to parse: {exc}")
                continue
            for function_name, lineno in found:
                relative = module_path.relative_to(TESTS_DIR.parent)
                offenders.append(f"{relative}:{lineno} ({function_name})")

        self.assertEqual(
            offenders, [],
            "unresolved scratch-directory fixture return(s) found -- each of "
            "these returns a Path built from tempfile.TemporaryDirectory()/"
            "mkdtemp() without .resolve(), which on macOS (/var -> "
            "/private/var) compares unequal to production's own resolved "
            "answer for the same directory. Add .resolve() to the returned "
            "Path, mirroring tests/test_papersmith_bridges.py::BridgesTests"
            ".new_tmp:\n  " + "\n  ".join(offenders)
        )


if __name__ == "__main__":
    unittest.main()
