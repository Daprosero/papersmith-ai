#!/usr/bin/env python3
"""Drop the materialization kit into a target repository.

The forge's own harness, never a step of Flow A: an agent fills the scaffold
gaps by reading step 5, and this plays that part so the suite can examine a
freshly scaffolded target. It fills exactly the gaps the skill reports,
parameterized by the scenario's name and seed, and writes no step-9 template —
those answer an object map that does not exist at scaffold time.

    python3 materialize.py <target> <Name> <seed> [kit-directory]

The kit defaults to the skill's own templates. The forge's harness passes a
neutral fixture kit instead: a paper forge must not carry one paper's content.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from implementation_cli import IGNORE_ENTRIES

DEFAULT_KIT = Path(__file__).resolve().parents[1] / "assets" / "kit"


def writable_at_scaffold_time(source: str) -> bool:
    """Whether a substituted template is a file the scaffold may write.

    The discriminator between the two stages, and it is mechanical rather than a
    list the kit could fall out of step with. A template that still carries a
    `{{TOKEN}}` where an identifier has to be does not parse, and the tokens left
    in it — `{{FUNCTION_NAME}}`, `{{INVARIANT_ID}}`, `{{EXPECTATION}}` — are
    answers to the object map step 8 approves. Nothing could have answered them
    at scaffold time.

    Writing them anyway produced three files no target could import, and the
    checker read the resulting tree as complete. Substituting dummy identifiers
    instead would have been worse: the result parses, collects and *passes*
    while asserting nothing.
    """
    try:
        ast.parse(source)
    except SyntaxError:
        return False
    return True


def main(target: str, name: str, seed: str, kit: str | None = None) -> int:
    KIT = Path(kit).resolve() if kit else DEFAULT_KIT
    root = Path(target).resolve()
    pkg = name.replace("-", "_")

    package = root / "src" / pkg
    package.mkdir(parents=True, exist_ok=True)
    # The package exports the target's own modules, and step 9 has written none
    # of them yet. `__all__` used to be read off `assets/kit/src/` — the stage-2
    # template directory — so a scaffold advertised a name that existed only
    # because the template beside it had been copied in, unparsable and all.
    (package / "__init__.py").write_text(
        f'"""Reference implementation of the {name} formulation.\n\n'
        "Each module declares the sections and equations it implements in\n"
        "`__provenance__`, and every invariant listed there has a matching\n"
        "test under tests/.\n"
        '"""\n\n'
        "__all__ = []\n"
    )

    # The benchmark's declaration, copied verbatim like every other kit file —
    # never substituted, never populated. `arms`, `search`, `report` and
    # `distribution` stay whatever the shipped template says (empty), because
    # nothing here has run a search, wired an arm or measured a split yet.
    benchmark_package = root / "src" / f"{pkg}_Benchmark"
    benchmark_package.mkdir(parents=True, exist_ok=True)
    declaration = KIT / "src_benchmark" / "__init__.py"
    (benchmark_package / "__init__.py").write_text(declaration.read_text())

    # The report seal, staged in `nb/` beside the notebooks that print it but
    # placed inside the package, the way `benchmark.py` and `verdict.py` are.
    # `_here()` reads the repository off `parents[1]`, so this is the one
    # location from which a notebook's stamp matches what `verify` recomputes.
    seal = KIT / "nb" / "report_digest.py"
    (benchmark_package / seal.name).write_text(seal.read_text())

    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    for test in sorted((KIT / "tests").glob("*.py")):
        body = test.read_text().replace("{{PKG}}", pkg).replace("{{SEED}}", seed)
        # `test_invariants.py` and `test_synthetic.py` are step 9's, not step
        # 5's. They stay in the kit until the map that answers their tokens
        # exists; a scaffold that wrote them shipped two files pytest could not
        # collect, and `test_smoke.py`'s own `{{MODULE}}` survives because it
        # sits inside a string rather than where a name has to be.
        if writable_at_scaffold_time(body):
            (tests / test.name).write_text(body)

    notebooks = root / name / "Notebooks"
    notebooks.mkdir(parents=True, exist_ok=True)
    (notebooks / "verification.ipynb").write_text(
        (KIT / "nb" / "verification.ipynb").read_text()
        .replace("{{PKG}}", pkg).replace("{{SEED}}", seed)
    )

    pyproject = root / "pyproject.toml"
    text = pyproject.read_text() if pyproject.exists() else (
        "[build-system]\n"
        'requires = ["setuptools>=68"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        f'name = "{pkg.lower().replace("_", "-")}"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.9"\n'
        'dependencies = ["numpy>=1.24"]\n\n'
        "[tool.setuptools.packages.find]\n"
        'where = ["src"]\n'
    )
    if "[tool.pytest.ini_options]" not in text:
        text += ('\n[tool.pytest.ini_options]\n'
                 'testpaths = ["tests"]\n'
                 'pythonpath = ["src", "tests"]\n')
    pyproject.write_text(text)

    # Merged into whatever the repository already has, never written over it —
    # a checkout that already ignores things has reasons this script cannot
    # read. It was the one gap the materializer left behind, which is why a test
    # fixture hand-patched it afterwards; a producer and a hand-patch writing
    # halves of the same file is how the two trees drifted with neither being
    # wrong on its own.
    ignore = root / ".gitignore"
    ignored = ignore.read_text() if ignore.exists() else ""
    missing = [entry for entry in IGNORE_ENTRIES
               if entry.rstrip("/") not in ignored]
    if missing:
        if ignored and not ignored.endswith("\n"):
            ignored += "\n"
        ignore.write_text(ignored + "".join(f"{entry}\n" for entry in missing))

    print(f"materialized {pkg} into {root} (seed {seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
