"""Change `the-second-skill-the-seam-was-for`, slice A1, task 1.7: the
CHANGE half of mutation proof (X2) for this skill's own profile leaves.
Removal is already proven, all sixteen leaves, by
`test_experimental_implementation.py::LeafRefusalTests`.

Runtime harness (design.md's own landing table, A1 row): **Direct** -- import
the engine with `IMPLEMENTATION_DOMAIN_PROFILE` pointed at this skill's own
`impl_profile.py`, a fresh uncached load per case, never the plain `import
implementation_engine` statement (which would share `sys.modules` state with
whichever OTHER test module in this same process imported it first under a
DIFFERENT profile -- `tests/seal/harness.py` and
`tests/test_implementation_domain_mutation.py` both do that for the
sibling's own profile). No subprocess corpus exists yet for this skill (that
lands at A2, design.md D7); the corpus-driven, subprocess-real proof style
`test_implementation_domain_mutation.py` uses for the sibling is deferred to
A2 for `documents.directory`, the one leaf this file does NOT cover --
fourteen of this profile's fifteen change-mutable leaves are proven here,
each against the module-level engine constant the leaf feeds directly
(`implementation_engine.py`'s own `SKILL_ROOT = PROFILE["kit"]["root"]`-style
reads).

Anchor discipline (design.md D8), the same rule the sibling's own suite
uses: before every mutation, the real profile source's occurrence count for
the OLD literal is asserted to be exactly 1, so the substitution is
unambiguous, and the scratch copy is asserted 0/1 after.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
ENGINE_DIR = FORGE / "skills" / "_core" / "implementation" / "engine"
ENGINE_FILE = ENGINE_DIR / "implementation_engine.py"
REAL_PROFILE = (
    FORGE / "skills" / "experimental-implementation"
    / "impl_profile.py")

_counter = itertools.count()


def _fresh_engine_under(profile_path: Path):
    """A fresh, uncached `implementation_engine` load, resolved against
    `profile_path` -- never `sys.modules["implementation_engine"]`, which
    every OTHER test module in this process may already have cached under a
    different profile."""
    import contextlib
    import os

    @contextlib.contextmanager
    def _env(value):
        had = "IMPLEMENTATION_DOMAIN_PROFILE" in os.environ
        original = os.environ.get("IMPLEMENTATION_DOMAIN_PROFILE")
        os.environ["IMPLEMENTATION_DOMAIN_PROFILE"] = str(value)
        try:
            yield
        finally:
            if had:
                os.environ["IMPLEMENTATION_DOMAIN_PROFILE"] = original
            else:
                os.environ.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)

    name = f"experimental_impl_engine_probe_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(name, ENGINE_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # `implementation_engine.py` reads its profile via a plain
    # `from impl_domain_profile import PROFILE` -- a regular import
    # statement, cached in `sys.modules["impl_domain_profile"]` the first
    # time ANY test in this process imports it. Left cached, every
    # subsequent fresh engine load here would silently reuse the FIRST
    # profile ever resolved, no matter what `IMPLEMENTATION_DOMAIN_PROFILE`
    # says -- measured directly this session (all fourteen leaves read back
    # identical before this pop was added). Popped before and after: before,
    # so this load re-resolves under the env set below; after, so a LATER
    # regular `import implementation_engine` elsewhere in the process is not
    # left holding a profile this test happened to set last.
    for cached in ("impl_domain_profile", "impl_domain_profile_host"):
        sys.modules.pop(cached, None)
    try:
        with _env(profile_path):
            spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
        for cached in ("impl_domain_profile", "impl_domain_profile_host"):
            sys.modules.pop(cached, None)
    return module


def _write_scratch_profile(tmp_dir: Path, mutated_src: str) -> Path:
    """A scratch copy of `impl_profile.py`, `_SKILL` re-anchored to the REAL
    skill directory so `kit.root`/`cli.path`/`documents[0].directory` still
    resolve to the shipped skill, and only the ONE leaf under test differs."""
    real_skill_dir = REAL_PROFILE.resolve().parent
    anchored = mutated_src.replace(
        "_SKILL = Path(__file__).resolve().parent",
        f"_SKILL = Path({str(real_skill_dir)!r})")
    scratch_profile = tmp_dir / "impl_profile.py"
    scratch_profile.write_text(anchored, encoding="utf-8")
    return scratch_profile


#: leaf -> (old literal, new literal, reader attribute on the fresh engine
#: module, expected-old-value, expected-new-value-check). Each old literal is
#: asserted to occur EXACTLY ONCE in the real profile source (anchor
#: discipline) before the substitution runs.
MUTATIONS: dict[str, tuple[str, str, str]] = {
    "provenance.claim_key": (
        '"claim_key": "experiments",', '"claim_key": "claims",', "CLAIM_KEY"),
    "provenance.authored_init_sentence": (
        '"Each module declares the sections and experiments it "',
        '"Each module names what it establishes in "', "AUTHORED_INIT_SENTENCE"),
    "findings.locus_key": (
        '"locus_key": "experiments",', '"locus_key": "loci",', "LOCUS_KEY"),
    "findings.remedy_locus_key": (
        '"remedy_locus_key": "remedy_experiments",',
        '"remedy_locus_key": "remedy_loci",', "REMEDY_LOCUS_KEY"),
    "findings.notation_keys": (
        '"locus": "experiments",', '"locus": "loci",', "NOTATION_KEYS"),
    # Cut 3 slice C (`the-second-document-verified-on-its-own-terms`,
    # design.md D3): the resolver now validates every `citation_pattern`'s
    # group count. The mutation replaces the WHOLE two-line literal (both
    # raw-string halves) with a single-line, still-three-group pattern --
    # the old two-branch-only replacement left the THIRD (unedited)
    # branch's own group in place, producing a 1-group pattern that the
    # resolver now refuses outright before this test's own fresh-import
    # ever runs.
    "findings.citation_pattern": (
        'r"Exps?\\.?\\s*\\(?(\\d+)\\)?|Experiment\\.?\\s*\\(?(\\d+)\\)?|"\n'
        '            r"Experimentos?\\s*\\((\\d+)\\)"',
        'r"Zzs?\\.?\\s*\\(?(\\d+)\\)?|Zzk\\.?\\s*\\(?(\\d+)\\)?|Zzq\\s*\\((\\d+)\\)"',
        "CITATION_PATTERN"),
    "vocabulary.subject_singular": (
        '"subject_singular": "experiment",', '"subject_singular": "claim",',
        "SUBJECT_SINGULAR"),
    "vocabulary.subject_plural": (
        '"subject_plural": "experiments",', '"subject_plural": "claims",',
        "SUBJECT_PLURAL"),
    "vocabulary.subject_singular_es": (
        '"subject_singular_es": "experimento",',
        '"subject_singular_es": "afirmación",', "SUBJECT_SINGULAR_ES"),
    "vocabulary.subject_plural_es": (
        '"subject_plural_es": "experimentos",',
        '"subject_plural_es": "afirmaciones",', "SUBJECT_PLURAL_ES"),
    "vocabulary.subject_collective": (
        '"subject_collective": "experimentation",',
        '"subject_collective": "claims",', "SUBJECT_COLLECTIVE"),
    "vocabulary.subject_collective_es": (
        '"subject_collective_es": "experimentación",',
        '"subject_collective_es": "afirmación",', "SUBJECT_COLLECTIVE_ES"),
    "vocabulary.artifact_noun": (
        '"artifact_noun": "protocol",', '"artifact_noun": "method",',
        "ARTIFACT_NOUN"),
    "documents.label": (
        '"label": "experiments",', '"label": "document",', "DOCUMENTS_LABEL"),
}


class PerLeafChangeMutationTests(unittest.TestCase):
    """X2: fourteen of the fifteen change-mutable leaves, each a real
    scratch mutation reaching a real fresh import of the engine, never a
    monkeypatch of an already-imported module's attribute."""

    def test_every_leaf_moves_its_own_reader_constant(self):
        real_src = REAL_PROFILE.read_text(encoding="utf-8")
        baseline = _fresh_engine_under(REAL_PROFILE)

        for leaf, (old, new, attr) in MUTATIONS.items():
            with self.subTest(leaf=leaf):
                # Anchor discipline (design.md D8): the OLD spelling occurs
                # exactly once in the real source, and the NEW spelling not
                # at all -- an ambiguous anchor is not a mutation that can
                # run unambiguously.
                self.assertEqual(
                    real_src.count(old), 1,
                    f"{leaf}: expected the OLD spelling exactly once, found "
                    f"{real_src.count(old)}")
                self.assertEqual(
                    real_src.count(new), 0,
                    f"{leaf}: the NEW spelling already appears before any "
                    "mutation -- anchor invalid")

                mutated_src = real_src.replace(old, new, 1)

                with tempfile.TemporaryDirectory() as scratch_dir:
                    scratch_profile = _write_scratch_profile(
                        Path(scratch_dir), mutated_src)
                    scratch_src = scratch_profile.read_text(encoding="utf-8")
                    self.assertEqual(scratch_src.count(old), 0)
                    self.assertEqual(scratch_src.count(new), 1)

                    mutated = _fresh_engine_under(scratch_profile)

                old_value = getattr(baseline, attr)
                new_value = getattr(mutated, attr)
                self.assertNotEqual(
                    old_value, new_value,
                    f"{leaf}: mutating the profile leaf did not move "
                    f"{attr} -- expected a real change, measured none")


if __name__ == "__main__":
    unittest.main()
