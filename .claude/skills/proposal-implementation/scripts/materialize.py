#!/usr/bin/env python3
"""Drop the materialization kit into a target repository.

Plays the part of the agent's step 6-8: fills the scaffold gaps the skill
reports, parameterized by the scenario's name and seed.

    python3 materialize.py <target> <Name> <seed> [kit-directory]

The kit defaults to the skill's own templates. The forge's harness passes a
neutral fixture kit instead: a paper forge must not carry one paper's content.
"""

from __future__ import annotations

import sys
from pathlib import Path

DEFAULT_KIT = Path(__file__).resolve().parents[1] / "assets" / "kit"


def main(target: str, name: str, seed: str, kit: str | None = None) -> int:
    KIT = Path(kit).resolve() if kit else DEFAULT_KIT
    root = Path(target).resolve()
    pkg = name.replace("-", "_")

    package = root / "src" / pkg
    package.mkdir(parents=True, exist_ok=True)
    # Read the module list off the kit. Naming them literally described one
    # formulation's modules, so any other kit produced an __init__ that
    # exported names its own package does not define.
    modules = [module.stem for module in sorted((KIT / "src").glob("*.py"))]
    (package / "__init__.py").write_text(
        f'"""Reference implementation of the {name} formulation.\n\n'
        "Each module declares the sections and equations it implements in\n"
        "`__provenance__`, and every invariant listed there has a matching\n"
        "test under tests/.\n"
        '"""\n\n'
        f"__all__ = {sorted(modules)!r}\n"
    )
    for module in sorted((KIT / "src").glob("*.py")):
        (package / module.name).write_text(module.read_text())

    # The benchmark's declaration, copied verbatim like every other kit file —
    # never substituted, never populated. `arms`, `search`, `report` and
    # `distribution` stay whatever the shipped template says (empty), because
    # nothing here has run a search, wired an arm or measured a split yet.
    benchmark_package = root / "src" / f"{pkg}_Benchmark"
    benchmark_package.mkdir(parents=True, exist_ok=True)
    declaration = KIT / "src_benchmark" / "__init__.py"
    (benchmark_package / "__init__.py").write_text(declaration.read_text())

    tests = root / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    for test in sorted((KIT / "tests").glob("*.py")):
        (tests / test.name).write_text(
            test.read_text().replace("{{PKG}}", pkg).replace("{{SEED}}", seed)
        )

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

    print(f"materialized {pkg} into {root} (seed {seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
