#!/usr/bin/env python3
"""Drop the r12 materialization kit into a target repository.

Plays the part of the agent's step 6-8: fills the scaffold gaps the skill
reports, parameterized by the scenario's name and seed.

    python3 materialize.py <target> <Name> <seed>
"""

from __future__ import annotations

import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "assets" / "kit"


def main(target: str, name: str, seed: str) -> int:
    root = Path(target).resolve()
    pkg = name.replace("-", "_")

    package = root / "src" / pkg
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(
        '"""Reference implementation of the MIL-CREDA formulation.\n\n'
        "Materializes research-concept-r12.md. Each module declares the sections\n"
        "and equations it implements in `__provenance__`, and every invariant\n"
        "listed there has a matching test under tests/.\n"
        '"""\n\n'
        '__all__ = ["bags", "entropy", "global_term", "kernels", "local_term", "objective"]\n'
    )
    for module in sorted((KIT / "src").glob("*.py")):
        (package / module.name).write_text(module.read_text())

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
    raise SystemExit(main(*sys.argv[1:4]))
