"""The mutation harness `paper-writing`'s suites run a real subprocess
against.

Extracted out of `tests/test_paper_writing.py` (design.md, `Mutation
harness generalized, in a shared helper module`) so `tests/test_paper_decisions.py`
— a second, independent suite covering `paper_region.py`, `paper_guidance.py`,
`paper_declarations.py` and `paper_provenance.py` — can run its own mutations
without importing from `test_paper_writing.py`, which would couple two
suites that own different modules. Precedent: `tests/forge_vocabulary.py`
is a non-test helper living under `tests/` for the identical reason: this
module is deliberately not named `test_*.py`, so the configured discovery
pattern never collects it as a suite of its own.

`test_paper_writing.py` imports `_run_against_mutant` from here rather than
keeping a second copy — one implementation, both suites.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
CORE_IMPLEMENTATION = FORGE_ROOT / "skills" / "_core" / "implementation"


def _run_against_mutant(
    anchor: str, replacement: str, dotted_test: str,
    *, source_path: Path = SKILL_SCRIPTS / "paper_block.py",
) -> subprocess.CompletedProcess:
    """Copy `source_path` into a fresh, uniquely named temp tree at the SAME
    relative depth the real script lives at (so the module's own
    `parents[2]` resolution still finds `_core/implementation`), patch its
    source with exactly one substitution, and run `dotted_test` against the
    mutant by pre-seeding `sys.modules[<source_path's own module name>]` in
    a bootstrap script — so the mutant is used regardless of any `sys.path`
    manipulation the test suite performs on its own (it inserts the REAL
    scripts directory at position 0 on import, which would otherwise win a
    plain `sys.path` race and silently run every mutation against the
    original file).

    `source_path` defaults to `paper_block.py` for backward compatibility
    with `test_paper_writing.py`'s own M1-M3 calls; any other script in the
    same directory works identically. Every OTHER sibling script is copied
    unmutated alongside it, because a mutated module may import one of its
    own siblings (`paper_graph.py` imports `paper_contract.py`, which
    imports `paper_scaffold.py` and `paper_vocabulary.py`; `paper_declarations.py`
    and `paper_provenance.py` both import `paper_region.py`) and that import
    must resolve to something real rather than crash before the mutation is
    ever exercised.

    Asserts the anchor matched EXACTLY once and the bytes actually changed
    before running anything: a matched-but-unapplied substitution, or one
    applied to more than one site, is not the mutation this call claims to
    run — and `git diff --stat` cannot catch it either, since the mutant
    lives in a temp directory this repository never tracks.
    """
    source_text = source_path.read_text(encoding="utf-8")
    occurrences = source_text.count(anchor)
    if occurrences != 1:
        raise AssertionError(
            f"anchor {anchor!r} matched {occurrences} times in {source_path.name}; "
            "expected exactly 1 for the mutation to be well-defined")
    mutated = source_text.replace(anchor, replacement, 1)
    if mutated == source_text:
        raise AssertionError("the substitution produced no byte change")

    real_module_name = source_path.stem
    tmp_root = Path(tempfile.mkdtemp(prefix="paper-writing-mutant-"))
    module_name = f"{real_module_name}_mutant_{uuid.uuid4().hex}"
    try:
        core_dst = tmp_root / "_core" / "implementation"
        core_dst.mkdir(parents=True)
        shutil.copy2(CORE_IMPLEMENTATION / "impl_refusals.py", core_dst / "impl_refusals.py")
        # `paper_declarations.py` also imports `impl_layout` (U2b,
        # `the-requirement-names-the-section-that-feeds-it`: the forge's own
        # canonical target-repository workspace, never re-spelled) from this
        # same directory -- copied alongside `impl_refusals.py` for the same
        # reason, or any mutation reaching `paper_declarations.py` (directly
        # or via `paper_graph.py` importing it) crashes on import before the
        # mutation is ever exercised.
        shutil.copy2(CORE_IMPLEMENTATION / "impl_layout.py", core_dst / "impl_layout.py")

        scripts_dst = tmp_root / "paper-writing" / "scripts"
        scripts_dst.mkdir(parents=True)
        for sibling in SKILL_SCRIPTS.glob("*.py"):
            if sibling.resolve() == source_path.resolve():
                continue
            shutil.copy2(sibling, scripts_dst / sibling.name)
        mutant_path = scripts_dst / f"{module_name}.py"
        mutant_path.write_text(mutated, encoding="utf-8")

        # A directory created this call, never reused across mutations: no
        # __pycache__ can be stale here. PYTHONDONTWRITEBYTECODE below also
        # stops one from being written during this very run.
        bootstrap = tmp_root / "bootstrap.py"
        bootstrap.write_text(
            "import importlib.util\n"
            "import sys\n"
            "import unittest\n"
            "\n"
            f"sys.path.insert(0, {str(scripts_dst)!r})\n"
            f"spec = importlib.util.spec_from_file_location({module_name!r}, {str(mutant_path)!r})\n"
            "mutant = importlib.util.module_from_spec(spec)\n"
            # Registered under its OWN name AND under the real module name:
            # @dataclass's field-type resolution reads `sys.modules[cls.__module__]`
            # (== the unique spec name) during `exec_module` itself, and a module
            # missing from sys.modules under its own name makes exec_module crash
            # before a single line of the mutation is ever exercised -- a failure
            # mode indistinguishable from a genuine test failure by exit code
            # alone, which is exactly why this is asserted separately below. The
            # real module name is also registered so a sibling module that
            # `import`s it (e.g. `paper_graph` importing `paper_contract`, or
            # `paper_declarations` importing `paper_region`) picks up the SAME
            # mutant object rather than re-importing the unmutated copy sitting
            # beside it in `scripts_dst`.
            f"sys.modules[{module_name!r}] = mutant\n"
            f"sys.modules[{real_module_name!r}] = mutant\n"
            "spec.loader.exec_module(mutant)\n"
            # A marker unittest's own runner never prints, so the caller can
            # tell 'the mutant module failed to even import' (a harness
            # defect) apart from 'unittest ran the named test and it failed'
            # (the actual proof this whole harness exists to produce) --
            # both exit non-zero, and only one of them says anything about
            # the mutation.
            "print('MUTANT_IMPORTED_OK')\n"
            "\n"
            f"program = unittest.main(module=None, argv=['prog', {dotted_test!r}], exit=False)\n"
            "sys.exit(0 if program.result.wasSuccessful() else 1)\n",
            encoding="utf-8",
        )

        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        existing_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(FORGE_ROOT) + (os.pathsep + existing_path if existing_path else "")

        return subprocess.run(
            [sys.executable, str(bootstrap)],
            cwd=str(FORGE_ROOT), capture_output=True, text=True, timeout=60, env=env,
        )
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
