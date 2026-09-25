"""Cut 1 (`the-engine-leaves-its-skill`): the domain-profile resolver the
moved engine fails closed without, and the launcher's own promise that it
exposes none of the engine's attributes.

Mirrors `skills/_core/deliberation/engine/domain-profile.ts`'s own
resolver-property tests, ported to the shape design.md D3 settles on for
Python: `IMPLEMENTATION_DOMAIN_PROFILE`, six named refusal codes,
`ImplementationProfileError(RuntimeError)` -- never `Refused`/`NameRefused`,
because `reachable_refusal_codes()` (`tests/test_proposal_implementation.py`)
walks every `*.py` under `_core/implementation/` for exactly those two
constructors and pins `len(...) == 112`; six `Refused`s in a core module
would move that unrelated pin.

Phase 1 (RED first, tasks.md): at the moment this file is first run, neither
`impl_domain_profile.py` nor the launcher's own `??=`-style default exist yet
-- every test below is expected to fail on collection/execution, not pass.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Mapping

from domain_profile import seeded_profile  # noqa: E402  (tests/ on path)

FORGE = Path(__file__).resolve().parents[1]
RESOLVER = FORGE / "skills/_core/implementation/impl_domain_profile.py"
LAUNCHER = FORGE / "skills/proposal-implementation/scripts/implementation_cli.py"
ENGINE_DIR = FORGE / "skills/_core/implementation/engine"

_ENV_VAR = "IMPLEMENTATION_DOMAIN_PROFILE"

#: A minimal, syntactically complete `objective` literal for fixture
#: profiles that are not themselves testing `objective`'s own validation --
#: real content is irrelevant to those tests, only completeness is, and this
#: keeps every unrelated refusal-code fixture from tripping the (now
#: required) `objective` check before it ever reaches the code under test.
_VALID_OBJECTIVE_SRC = (
    "{'purpose': 'p', 'arrival': 'a', 'humanStops': ['h'], "
    "'stages': [{'stage': 's', 'establishes': 'e', 'behindWhen': 'b'}]}")

def _cut2_fields_src(tmp_dir: Path) -> str:
    """Cut 2 (`the-domain-crosses-the-seam`, design.md D1) grew the
    resolver's required-leaf set past Cut 1's `kit`/`cli`/`objective`. This
    is that growth as a literal source fragment, spliced into every
    hand-written Cut-1 fixture below that is testing `kit`/`cli`/`objective`
    specifically and would otherwise trip `..._INCOMPLETE` on an unrelated
    missing Cut-2 leaf before ever reaching the behaviour under test."""
    documents_dir = tmp_dir / "proposals"
    return (
        "'provenance': {'claim_key': 'equations', "
        "'authored_init_sentence': 'x'}, "
        "'findings': {'locus_key': 'equations', "
        "'remedy_locus_key': 'remedy_equations', "
        "'notation_keys': {'locus': 'equations', "
        "'remedyLocus': 'remedyEquations', 'unknown': 'unknownEquations'}, "
        # Slice C (design.md D3): the resolver now validates every
        # `citation_pattern`'s group count, top-level included -- this
        # placeholder must carry exactly three capturing groups or every
        # unrelated leaf test spliced with this fragment would trip the
        # NEW `..._INVALID_CITATION_PATTERN` refusal before reaching the
        # behaviour it actually tests.
        "'citation_pattern': r'x(\\d+)|y(\\d+)|z(\\d+)'}, "
        "'vocabulary': {'subject_singular': 'equation', "
        "'subject_plural': 'equations', 'subject_singular_es': 'ecuación', "
        "'subject_plural_es': 'ecuaciones', "
        "'subject_collective': 'mathematics', "
        "'subject_collective_es': 'matemática', "
        "'artifact_noun': 'formulation', "
        "'names': ['equation', 'equations', 'ecuación', 'ecuaciones', "
        "'mathematics', 'matemática', 'formulation']}, "
        f"'documents': [{{'directory': Path({str(documents_dir)!r}), "
        "'label': 'proposal', 'dataset_marker': None, "
        f"'block_locator': {_block_locator()!r}, "
        # `the-agreement-nothing-computes` (Slice D, design.md D5, R1
        # resolved 5d42dd7): a single-document splice has no OTHER label
        # to cross against -- `None` here, the leaf's own legal declared
        # absence.
        "'cross_citation': None}]")


_counter = itertools.count()


@contextlib.contextmanager
def _env(value):
    """Sets or removes `IMPLEMENTATION_DOMAIN_PROFILE` for the block, then
    restores whatever this process had before -- never `patch.dict`, which
    cannot express "absent" as cleanly as an explicit pop/restore pair."""
    had = _ENV_VAR in os.environ
    original = os.environ.get(_ENV_VAR)
    if value is None:
        os.environ.pop(_ENV_VAR, None)
    else:
        os.environ[_ENV_VAR] = value
    try:
        yield
    finally:
        if had:
            os.environ[_ENV_VAR] = original
        else:
            os.environ.pop(_ENV_VAR, None)


def _fresh_resolver_load(env_value):
    """One fresh, uncached `exec_module` of the resolver under a controlled
    env -- the resolver validates and raises at IMPORT time (module-level
    `PROFILE = _resolve()`), so this either returns a live module or lets
    the resolver's own exception propagate to the caller."""
    name = f"impl_domain_profile_probe_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(name, RESOLVER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        with _env(env_value):
            spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


class ProfileResolverRefusalTests(unittest.TestCase):
    """The six named refusal codes (design.md D3), each proven by one
    mutation of the profile-resolution inputs -- never asserted by shape
    alone. In-process, fresh `importlib` per case, exactly `CoreNamesNoDomain
    Tests._cli_module()`'s own pattern."""

    def _profile_file(self, tmp_dir: Path, body: str) -> Path:
        profile_file = tmp_dir / "impl_profile.py"
        profile_file.write_text(body, encoding="utf-8")
        return profile_file

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-refusal-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_unset_refuses_required(self):
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(None)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_REQUIRED", str(ctx.exception))

    def test_empty_string_refuses_required(self):
        """Empty is not merely falsy-and-ignored -- it is refused under the
        same code as unset, never silently treated as "no override"."""
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load("")
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_REQUIRED", str(ctx.exception))

    def test_relative_path_refuses_not_absolute(self):
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load("relative/impl_profile.py")
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_NOT_ABSOLUTE", str(ctx.exception))

    def test_absent_file_refuses_unreadable(self):
        tmp_dir = self._tmp_dir()
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(tmp_dir / "does-not-exist.py"))
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_UNREADABLE", str(ctx.exception))

    def test_a_file_that_raises_on_exec_refuses_unreadable(self):
        """`spec_from_file_location` succeeding is not the same as the
        module executing cleanly -- a profile file that itself raises must
        be caught and re-raised under the resolver's own named code, never
        left as the profile file's raw exception."""
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(
            tmp_dir, "raise RuntimeError('the profile file itself is broken')\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_UNREADABLE", str(ctx.exception))

    def test_no_profile_export_refuses_invalid(self):
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(tmp_dir, "NOT_PROFILE = 1\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID", str(ctx.exception))

    def test_a_non_mapping_profile_refuses_invalid(self):
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(tmp_dir, "PROFILE = ['not', 'a', 'mapping']\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID", str(ctx.exception))

    def test_a_missing_nested_key_refuses_incomplete_and_names_it(self):
        """The `artifact: {}` lesson (design.md D3): a present-but-empty
        `kit` must be named by its missing LEAF, `kit.root`, never by the
        top-level key alone -- a top-level-only check passes this
        vacuously."""
        tmp_dir = self._tmp_dir()
        real_cli = str(LAUNCHER)
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            "PROFILE = {'kit': {}, "
            f"'cli': {{'path': Path({real_cli!r})}}, "
            f"'objective': {_VALID_OBJECTIVE_SRC}}}\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("kit.root", message)
        self.assertNotIn("'kit'", message, "must name the leaf, not the section")

    def test_a_top_level_only_key_still_refuses_incomplete(self):
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(tmp_dir, "PROFILE = {}\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("kit.root", message)
        self.assertIn("cli.path", message)
        self.assertIn("objective", message)

    def test_a_relative_kit_root_refuses_unsafe_path(self):
        tmp_dir = self._tmp_dir()
        real_cli = str(LAUNCHER)
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            "PROFILE = {'kit': {'root': Path('relative/kit/root')}, "
            f"'cli': {{'path': Path({real_cli!r})}}, "
            f"'objective': {_VALID_OBJECTIVE_SRC}, "
            f"{_cut2_fields_src(tmp_dir)}}}\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_UNSAFE_PATH", message)
        self.assertIn("kit.root", message)

    def test_a_nonexistent_absolute_kit_root_refuses_unsafe_path(self):
        """Absolute alone is not safe -- today this scatters into 19
        unrelated missing-asset failures under the 19 `SKILL_ROOT` readers;
        validating it here turns that into one named refusal (design.md
        D3)."""
        tmp_dir = self._tmp_dir()
        real_cli = str(LAUNCHER)
        missing = tmp_dir / "does-not-exist-either"
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            f"PROFILE = {{'kit': {{'root': Path({str(missing)!r})}}, "
            f"'cli': {{'path': Path({real_cli!r})}}, "
            f"'objective': {_VALID_OBJECTIVE_SRC}, "
            f"{_cut2_fields_src(tmp_dir)}}}\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_UNSAFE_PATH", message)
        self.assertIn("kit.root", message)

    def test_a_valid_profile_resolves_cleanly(self):
        """The positive control every refusal test above is a mutation OF:
        a complete, absolute, existing profile loads with no error and
        exposes `PROFILE` as a mapping carrying exactly what was declared."""
        tmp_dir = self._tmp_dir()
        real_cli = str(LAUNCHER)
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            f"PROFILE = {{'kit': {{'root': Path({str(tmp_dir)!r})}}, "
            f"'cli': {{'path': Path({real_cli!r})}}, "
            f"'objective': {_VALID_OBJECTIVE_SRC}, "
            f"{_cut2_fields_src(tmp_dir)}}}\n")
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(Path(module.PROFILE["kit"]["root"]), tmp_dir)
        self.assertEqual(Path(module.PROFILE["cli"]["path"]), LAUNCHER)
        self.assertEqual(module.PROFILE["objective"]["purpose"], "p")


class ObjectiveProfileFieldTests(unittest.TestCase):
    """The Cut-1 field set's third member (operator ruling, task 7.5):
    `objective`, validated exactly as `domain-profile.ts`'s own
    `OBJECTIVE_REQUIRED`/`stagesIncomplete` pair -- top-level presence,
    nested required-key completeness, and `stages: []` ruled out
    separately, since a bare-presence check alone would pass it
    vacuously."""

    def _profile_file(self, tmp_dir: Path, body: str) -> Path:
        profile_file = tmp_dir / "impl_profile.py"
        profile_file.write_text(body, encoding="utf-8")
        return profile_file

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-objective-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _kit_cli(self, tmp_dir: Path) -> str:
        real_cli = str(LAUNCHER)
        return (f"'kit': {{'root': {str(tmp_dir)!r}}}, "
               f"'cli': {{'path': Path({real_cli!r})}}, "
               f"{_cut2_fields_src(tmp_dir)}")

    def test_a_missing_objective_refuses_incomplete_and_names_it(self):
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            f"PROFILE = {{{self._kit_cli(tmp_dir)}}}\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("objective", message)

    def test_a_missing_objective_leaf_refuses_incomplete_and_names_it(self):
        """The `artifact: {}` lesson, applied to `objective` too: a
        present-but-incomplete `objective` is named by its missing LEAF."""
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            f"PROFILE = {{{self._kit_cli(tmp_dir)}, "
            "'objective': {'purpose': 'p', 'arrival': 'a', "
            "'stages': [{'stage': 's', 'establishes': 'e', "
            "'behindWhen': 'b'}]}}\n")  # humanStops omitted
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("objective.humanStops", message)

    def test_empty_stages_refuses_incomplete(self):
        """`stages: []` passes a bare presence check vacuously -- a north
        with no stages is not a north (domain-profile.ts's own
        `stagesIncomplete` lesson, mirrored exactly)."""
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            f"PROFILE = {{{self._kit_cli(tmp_dir)}, "
            "'objective': {'purpose': 'p', 'arrival': 'a', "
            "'humanStops': ['h'], 'stages': []}}\n")
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("objective.stages", message)

    def test_a_stage_missing_a_required_key_refuses_incomplete(self):
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            f"PROFILE = {{{self._kit_cli(tmp_dir)}, "
            "'objective': {'purpose': 'p', 'arrival': 'a', "
            "'humanStops': ['h'], "
            "'stages': [{'stage': 's', 'establishes': 'e'}]}}\n")  # no behindWhen
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("objective.stages", message)

    def test_a_complete_objective_resolves_cleanly(self):
        tmp_dir = self._tmp_dir()
        profile_file = self._profile_file(
            tmp_dir,
            "from pathlib import Path\n"
            f"PROFILE = {{{self._kit_cli(tmp_dir)}, "
            f"'objective': {_VALID_OBJECTIVE_SRC}}}\n")
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(module.PROFILE["objective"]["purpose"], "p")
        self.assertEqual(len(module.PROFILE["objective"]["stages"]), 1)


class SetdefaultOverrideTests(unittest.TestCase):
    """The launcher's own `os.environ.setdefault` (design.md D1): an
    explicit `IMPLEMENTATION_DOMAIN_PROFILE` in the child's environment is a
    deliberate override and must win over the launcher's own default --
    mirroring the `??=` semantics `proposal-deliberation/cli.mjs` uses,
    including for the empty string, which stays empty and is refused
    (`ProfileResolverRefusalTests.test_empty_string_refuses_required`).

    Proven via a real subprocess against a tmpdir fixture profile, never a
    monkeypatch: the launcher's `setdefault` call and the engine's own
    `_resolve()` both run in the CHILD process, invisible to an in-process
    patch of this test's own `os.environ` (recorded scar: monkeypatching a
    module attribute has zero effect on a subprocess).
    """

    def test_an_explicit_override_wins_and_its_own_kit_root_is_what_fails(self):
        """The fixture's `kit.root` is deliberately unsafe (nonexistent), so
        a subprocess that used the launcher's own default would succeed --
        and one that honoured the override fails, naming exactly the
        fixture's own path in its refusal. That the fixture's path appears
        at all is the proof the override reached the child process; that it
        is what fails is the proof it was not silently ignored."""
        fixture_dir = Path(tempfile.mkdtemp(prefix="profile-override-"))
        self.addCleanup(shutil.rmtree, fixture_dir, ignore_errors=True)
        missing_root = fixture_dir / "kit-root-does-not-exist"
        profile_file = fixture_dir / "impl_profile.py"
        profile_file.write_text(
            "from pathlib import Path\n"
            f"PROFILE = {{'kit': {{'root': Path({str(missing_root)!r})}}, "
            f"'cli': {{'path': Path({str(LAUNCHER)!r})}}, "
            f"'objective': {_VALID_OBJECTIVE_SRC}, "
            f"{_cut2_fields_src(fixture_dir)}}}\n",
            encoding="utf-8")

        env = dict(os.environ)
        env[_ENV_VAR] = str(profile_file)
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), "verify", "--target",
             "/tmp/does-not-matter", "--name", "Method"],
            capture_output=True, text=True, env=env)

        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_UNSAFE_PATH", proc.stderr)
        self.assertIn(str(profile_file), proc.stderr)

    def test_unset_falls_back_to_the_launchers_own_default_and_runs(self):
        """The companion control: with the variable absent from the child's
        environment entirely, the launcher's own `setdefault` supplies the
        skill's own profile and the command dispatches normally -- the
        baseline every other subprocess test in this suite already relies
        on, made explicit here."""
        env = dict(os.environ)
        env.pop(_ENV_VAR, None)
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), "verify", "--target",
             "/tmp/_implementation_profile_unset_probe_does_not_exist",
             "--name", "Method"],
            capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("IMPLEMENTATION_DOMAIN_PROFILE", proc.stdout + proc.stderr)


class LauncherExposesNoEngineAttributeTests(unittest.TestCase):
    """D1's pin against silent re-aliasing: `sys.modules[__name__] = _engine`
    would make `import implementation_cli as impl` yield the engine's own
    attributes again, invisibly. This asserts the launcher's OWN module
    namespace -- loaded exactly as `CoreNamesNoDomainTests._cli_module()`
    loads the CLI -- carries none of the engine's public surface."""

    @staticmethod
    def _launcher_module():
        spec = importlib.util.spec_from_file_location(
            "impl_launcher_for_alias_pin", LAUNCHER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_the_launcher_exposes_no_engine_attribute(self):
        launcher = self._launcher_module()
        for name in ("COMMANDS", "CLI_PATH", "SKILL_ROOT", "main"):
            with self.subTest(attribute=name):
                self.assertFalse(
                    hasattr(launcher, name),
                    f"the launcher module carries {name!r} -- it has been "
                    "aliased to the engine rather than merely handing over "
                    "to it")


#: Cut 2 (`the-domain-crosses-the-seam`): the sixteen dotted leaves design.md
#: D1 names, each a validated resolver leaf. `vocabulary.names` is included
#: here (Phase 1 is RED-first for all sixteen) even though the resolver does
#: not require it until S13 -- design.md D7's own landing order, confirmed
#: by task 2.5: "`vocabulary.names` case stays red until S13".
_CUT2_LEAVES: tuple[str, ...] = (
    "provenance.claim_key",
    "provenance.authored_init_sentence",
    "findings.locus_key",
    "findings.remedy_locus_key",
    "findings.notation_keys",
    "findings.citation_pattern",
    "vocabulary.subject_singular",
    "vocabulary.subject_plural",
    "vocabulary.subject_singular_es",
    "vocabulary.subject_plural_es",
    "vocabulary.subject_collective",
    "vocabulary.subject_collective_es",
    "vocabulary.artifact_noun",
    "vocabulary.names",
    # Cut 3 (`a-revision-is-two-documents`, design.md D4): `documents` is a
    # LIST, validated per index -- the single declared document's own leaves
    # are named `documents[0].directory`/`documents[0].label`, never the bare
    # `documents.directory`/`documents.label` this tuple carried through
    # Cut 2. `_without_leaf` below special-cases this indexed shape.
    "documents[0].directory",
    "documents[0].label",
    # `a-data-directory-somebody-can-owe` (B1, design.md D1): its own tier,
    # never a member of `_DOCUMENT_VOCABULARY_LEAVES` -- appended after
    # `label` so this generic per-leaf walk also proves index 0's own case;
    # `DatasetMarkerLeafOwnTierTests` below proves the OTHER index.
    "documents[0].dataset_marker",
    # `the-agreement-nothing-computes` (Slice D, design.md D1/R2): its own
    # required, non-nullable tier -- appended after `dataset_marker` so
    # this generic per-leaf walk also proves index 0's own whole-leaf case;
    # `BlockLocatorLeafOwnTierTests` below proves the sub-key shape.
    "documents[0].block_locator",
    # `the-agreement-nothing-computes` (Slice D, design.md D5/R1): its own
    # required (but NULLABLE) tier, appended right after `block_locator` --
    # `_without_leaf` deletes the KEY entirely here, never merely sets it to
    # `None` (which is a legal declared value, not an omission); this
    # generic per-leaf walk proves index 0's own whole-leaf-omitted case,
    # `CrossCitationLeafOwnTierTests` below proves the sub-key shape and the
    # `None`-is-legal positive control.
    "documents[0].cross_citation",
    # `the-holder-each-skill-declares` (design.md D1, tasks.md 1.2): an 8th
    # top-level `holder` section, three leaves -- `filename`, `headings`,
    # `scaffold`. A plain top-level `section.key` shape, exactly like
    # `kit.root`/`cli.path` -- `_without_leaf` needs no indexed branch for
    # these. Appended here (task 1.2, RED): `_cut2_profile` already
    # declares the section (task 1.1, behaviour-free), but naming these
    # three dotted leaves in this walk is itself the RED step -- no
    # requirement enforces `holder.*`'s presence until task 1.3 lands, so
    # each of the three now fails `test_each_cut2_leaf_refuses_incomplete_
    # and_names_itself` until 1.3's GREEN.
    "holder.filename",
    "holder.headings",
    "holder.scaffold",
)

#: `vocabulary.names` is declared at S13 (design.md D7), not S2 -- so a
#: helper that builds a COMPLETE profile without it is what S2-S12's tests
#: exercise, and one WITH it is what S13 onward exercises.
_CITATION_PATTERN_SRC = (
    r"Ecs?\.?\s*\(?(\d+)\)?|Eq\.?\s*\(?(\d+)\)?|Ecuaciones?\s*\((\d+)\)")

#: `the-agreement-nothing-computes` (Slice D, design.md D1/R2): every
#: `documents[N]` entry this file constructs now needs a complete, valid
#: `block_locator` -- required and non-nullable. A fresh literal at each
#: construction site (never one shared mutable reference), matching this
#: file's own convention.
def _block_locator() -> dict:
    return {
        "pattern": r"\\tag\{([^}]+)\}",
        "block_pattern": r"(?s)\$\$.*?\$\$",
        "identity": "\\tag{{{value}}}",
    }


#: `the-agreement-nothing-computes` (Slice D, design.md D5/R1): a
#: `documents[N].cross_citation` mapping resolving against `target` --
#: `target` must name ANOTHER declared entry's own `label`, never the
#: entry's own (a self-reference refuses `..._UNKNOWN_CROSS_DOCUMENT`,
#: `CrossCitationShapeValidationTests` below). The identifier class mirrors
#: `reference-experimental.ts::IDENTIFIER` exactly (design.md D5).
def _cross_citation(target: str) -> dict:
    return {
        "pattern": r"\[claims:([A-Za-z0-9][A-Za-z0-9._-]*)\]",
        "resolves_against": target,
    }


def _cut2_profile(tmp_dir: Path, *, with_names: bool = True) -> dict:
    """The complete Cut-2 field set (design.md's Interfaces/Contracts
    block), built as real Python objects -- never hand-serialized text --
    so removing one leaf for a refusal case is one `del`, not sixteen
    hand-written fixture bodies."""
    profile = {
        "kit": {"root": tmp_dir},
        "cli": {"path": LAUNCHER},
        "objective": {
            "purpose": "p", "arrival": "a", "humanStops": ["h"],
            "stages": [{"stage": "s", "establishes": "e", "behindWhen": "b"}],
        },
        "provenance": {
            "claim_key": "equations",
            "authored_init_sentence": (
                "Each module declares the sections and equations it "
                "implements in\n`__provenance__`, and every invariant "
                "listed there has a matching\ntest under tests/.\n"),
        },
        "findings": {
            "locus_key": "equations",
            "remedy_locus_key": "remedy_equations",
            "notation_keys": {
                "locus": "equations",
                "remedyLocus": "remedyEquations",
                "unknown": "unknownEquations",
            },
            "citation_pattern": _CITATION_PATTERN_SRC,
        },
        "vocabulary": {
            "subject_singular": "equation",
            "subject_plural": "equations",
            "subject_singular_es": "ecuación",
            "subject_plural_es": "ecuaciones",
            "subject_collective": "mathematics",
            "subject_collective_es": "matemática",
            "artifact_noun": "formulation",
        },
        # Cut 3 (`a-revision-is-two-documents`, design.md D4): `documents` is
        # a LIST. One entry here, so every derived byte
        # (`DOCUMENTS_DIRECTORY`/`DOCUMENTS_LABEL`) is unchanged from Cut 2's
        # scalar shape.
        "documents": [
            {"directory": tmp_dir / "proposals", "label": "proposal",
             # B1 (`a-data-directory-somebody-can-owe`, design.md D1):
             # required, own tier, nullable -- `None` here since this
             # fixture's own tests are not testing the dataset demand.
             "dataset_marker": None,
             # `the-agreement-nothing-computes` (Slice D, design.md D1/R2):
             # required, own tier, non-nullable.
             "block_locator": _block_locator(),
             # `the-agreement-nothing-computes` (Slice D, design.md D5/R1):
             # required, own tier, NULLABLE -- `None` here: this single-
             # document splice has no OTHER declared label to cross
             # against.
             "cross_citation": None},
        ],
        # `the-holder-each-skill-declares` (design.md D1/D4): the 8th
        # top-level `PROFILE` section -- the checklist holder this fixture
        # declares its own name for. Phase 1 lands this leaf before the
        # requirement that enforces it exists (tasks.md 1.1); the filename
        # here is a legal placeholder, not either shipped skill's own name.
        "holder": {
            "filename": "Fixture_AGREED.md",
            "headings": ("# Agreed", "## Ladder"),
            "scaffold": "# Agreed\n\n## Ladder\n",
        },
    }
    if with_names:
        profile["vocabulary"]["names"] = [
            "equation", "equations", "ecuación", "ecuaciones",
            "mathematics", "matemática", "formulation",
        ]
    return profile


def _to_profile_source(value) -> str:
    """Serializes a profile dict back to Python source for a fixture file.
    `Path` gets its own branch (its `repr()` is not directly constructible
    without the same import this fixture already carries); everything else
    -- str, list, nested dict -- goes through the ordinary `repr()`."""
    if isinstance(value, Mapping):
        items = ", ".join(
            f"{key!r}: {_to_profile_source(val)}" for key, val in value.items())
        return "{" + items + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_to_profile_source(item) for item in value) + "]"
    if isinstance(value, Path):
        return f"Path({str(value)!r})"
    return repr(value)


_INDEXED_LEAF_RE = re.compile(
    r"^documents\[(\d+)\]\.(directory|label|dataset_marker|block_locator"
    r"|cross_citation)$")


def _without_leaf(profile: dict, dotted: str) -> dict:
    """Removes one dotted leaf from a deep copy of `profile`. Cut 3
    (design.md D4): `documents[N].directory`/`documents[N].label` name an
    entry INSIDE the `documents` list, never a top-level dict key -- handled
    as its own branch rather than `dotted.split(".", 1)`, which would look
    for a literal `documents[0]` section key that does not exist.
    `dataset_marker` (B1, `a-data-directory-somebody-can-owe`) joins the
    same indexed shape."""
    clone = copy.deepcopy(profile)
    indexed = _INDEXED_LEAF_RE.match(dotted)
    if indexed:
        index, key = int(indexed.group(1)), indexed.group(2)
        del clone["documents"][index][key]
        return clone
    section, key = dotted.split(".", 1)
    del clone[section][key]
    return clone


def _write_profile(tmp_dir: Path, profile: dict) -> Path:
    profile_file = tmp_dir / "impl_profile.py"
    profile_file.write_text(
        "from pathlib import Path\n"
        f"PROFILE = {_to_profile_source(profile)}\n",
        encoding="utf-8")
    return profile_file


class DomainFieldLeafRefusalTests(unittest.TestCase):
    """Phase 1 (RED first, tasks.md): one `..._INCOMPLETE` case per Cut-2
    leaf, each naming the exact dotted leaf -- never its section alone,
    the same `artifact: {}` lesson `ProfileResolverRefusalTests` already
    proves for Cut 1's three fields. At the moment this class first runs
    (S1), the resolver validates none of these sixteen, so every one of
    them is expected to stay RED (no exception raised) until its own S-step
    lands (S2 onward); `vocabulary.names` specifically stays red through
    S12 and only turns green at S13 (design.md D7)."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-domain-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_each_cut2_leaf_refuses_incomplete_and_names_itself(self):
        for dotted in _CUT2_LEAVES:
            with self.subTest(leaf=dotted):
                tmp_dir = self._tmp_dir()
                full = _cut2_profile(tmp_dir)
                incomplete = _without_leaf(full, dotted)
                profile_file = _write_profile(tmp_dir, incomplete)
                with self.assertRaises(RuntimeError) as ctx:
                    _fresh_resolver_load(str(profile_file))
                message = str(ctx.exception)
                self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
                self.assertIn(dotted, message)

    def test_the_complete_cut2_profile_resolves_cleanly(self):
        """The positive control every refusal case above is a mutation OF."""
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(module.PROFILE["provenance"]["claim_key"], "equations")
        self.assertEqual(
            module.PROFILE["findings"]["remedy_locus_key"], "remedy_equations")
        self.assertEqual(module.PROFILE["vocabulary"]["artifact_noun"], "formulation")
        self.assertEqual(module.PROFILE["documents"][0]["label"], "proposal")


class HolderShapeValidationTests(unittest.TestCase):
    """`the-holder-each-skill-declares` (design.md D1/D4, tasks.md 1.2): the
    holder leaf's own shape, validated at resolve time --
    `IMPLEMENTATION_DOMAIN_PROFILE_INVALID_HOLDER`, joining the
    `..._INVALID_CITATION_PATTERN`/`..._INVALID_BLOCK_LOCATOR`/
    `..._INVALID_CROSS_CITATION_PATTERN` family (`BlockLocatorShapeValidationTests`
    above is this class's own precedent). Two tiers: (1) the threat-matrix
    row-1 adversarial filenames (design.md's Threat Matrix, "Documentation-
    like paths"), one `subTest` each; (2) the scaffold/heading agreement
    `locate_headings` itself enforces (`impl_position.py:366-389`) --
    stripped-line-equal, outside a fenced region -- proven RED-first in
    both directions design.md D4 calls out: absent from the scaffold
    entirely, present only inside a fence, present only as a substring."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-holder-shape-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _profile_with_holder(self, tmp_dir: Path, holder: dict) -> dict:
        full = _cut2_profile(tmp_dir)
        full["holder"] = holder
        return full

    def _assert_invalid_holder(self, tmp_dir: Path, full: dict, *, contains: str):
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_HOLDER", message)
        self.assertIn(contains, message)

    def test_adversarial_filenames_each_refuse_invalid_holder(self):
        adversarial = (
            "../x.md", "/etc/x.md", "a/b.md", "", ".", "..", "x.md\n",
            "AGREED\x00.md", "x.sh", "AGREED",
        )
        for filename in adversarial:
            with self.subTest(filename=filename):
                tmp_dir = self._tmp_dir()
                holder = {
                    "filename": filename,
                    "headings": ("# Agreed", "## Ladder"),
                    "scaffold": "# Agreed\n\n## Ladder\n",
                }
                full = self._profile_with_holder(tmp_dir, holder)
                self._assert_invalid_holder(tmp_dir, full, contains="holder.filename")

    def test_a_heading_absent_from_the_scaffold_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        holder = {
            "filename": "AGREED.md",
            "headings": ("# Agreed", "## Nope"),
            "scaffold": "# Agreed\n\n## Ladder\n",
        }
        full = self._profile_with_holder(tmp_dir, holder)
        self._assert_invalid_holder(tmp_dir, full, contains="## Nope")

    def test_a_heading_present_only_inside_a_fence_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        holder = {
            "filename": "AGREED.md",
            "headings": ("# Agreed", "## Ladder"),
            "scaffold": "# Agreed\n\n```\n## Ladder\n```\n",
        }
        full = self._profile_with_holder(tmp_dir, holder)
        self._assert_invalid_holder(tmp_dir, full, contains="## Ladder")

    def test_a_heading_present_only_as_a_substring_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        holder = {
            "filename": "AGREED.md",
            "headings": ("# Agreed", "## Ladder"),
            "scaffold": "# Agreed\n\n## Ladder Extended\n",
        }
        full = self._profile_with_holder(tmp_dir, holder)
        self._assert_invalid_holder(tmp_dir, full, contains="## Ladder")

    def test_a_complete_holder_leaf_resolves_cleanly(self):
        """The positive control every refusal case above is a mutation OF."""
        tmp_dir = self._tmp_dir()
        holder = {
            "filename": "AGREED.md",
            "headings": ("# Agreed", "## Ladder"),
            "scaffold": "# Agreed\n\n## Ladder\n",
        }
        full = self._profile_with_holder(tmp_dir, holder)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(module.PROFILE["holder"]["filename"], "AGREED.md")


class DocumentsDirectoryOwnTierTests(unittest.TestCase):
    """M3 (design.md): `documents[N].directory` cannot join `_REQUIRED_NESTED`
    -- that tuple's `..._UNSAFE_PATH` walk requires `.exists()`, and a
    non-existent `documents[0].directory` (a clone with no `proposals/` yet)
    must import fine. Threat-matrix RED test (Path traversal via profile,
    tasks.md 2.3): relative refuses `UNSAFE_PATH`, naming the indexed leaf
    (Cut 3, design.md D4); non-existent absolute imports fine."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-documents-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_a_relative_documents_directory_refuses_unsafe_path(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        full["documents"][0]["directory"] = Path("relative/proposals")
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_UNSAFE_PATH", message)
        self.assertIn("documents[0].directory", message)

    def test_a_nonexistent_absolute_documents_directory_imports_fine(self):
        """The whole point of M3: a clone with no `proposals/` yet must not
        be refused at import -- five reported absences would become one
        fatal refusal, a behavioural delta the seal's `*-e0` cases would
        catch."""
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        self.assertFalse(full["documents"][0]["directory"].exists())
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertFalse(Path(module.PROFILE["documents"][0]["directory"]).exists())


class DatasetMarkerLeafOwnTierTests(unittest.TestCase):
    """B1 (`a-data-directory-somebody-can-owe`, design.md D1, tasks.md
    1.1): `documents[N].dataset_marker` is its OWN required tier, appended
    right after the `label` check -- never a member of
    `_DOCUMENT_VOCABULARY_LEAVES`, which is all-or-nothing over five leaves
    unrelated to this one. Per-INDEX case, both directions: index 0 alone
    (`_CUT2_LEAVES`, above) is not enough to prove the walk runs per entry,
    so this class also proves index 1, and the positive controls (`None`
    and a real string both pass)."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-dataset-marker-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_a_second_documents_missing_dataset_marker_refuses_by_indexed_name(self):
        tmp_dir = self._tmp_dir()
        full = _two_document_profile(tmp_dir)
        del full["documents"][1]["dataset_marker"]
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("documents[1].dataset_marker", message)

    def test_none_is_a_valid_declaration_and_passes(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        self.assertIsNone(full["documents"][0]["dataset_marker"])
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertIsNone(module.PROFILE["documents"][0]["dataset_marker"])

    def test_a_declared_marker_string_passes(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        full["documents"][0]["dataset_marker"] = "**Dataset:**"
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(
            module.PROFILE["documents"][0]["dataset_marker"], "**Dataset:**")


class BlockLocatorLeafOwnTierTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D1, R2 resolved
    5d42dd7, tasks.md 1.1/1.3): `documents[N].block_locator` is its OWN
    required, non-nullable tier, appended right after `dataset_marker` --
    a missing LEAF refuses naming `documents[N].block_locator` alone; a
    missing SUB-KEY refuses at its own exact indexed sub-path
    (`documents[1].block_locator.identity`), never the bare parent leaf.
    Exercised against a SYNTHETIC scratch profile (never a shipped one --
    both shipped profiles declare a complete `block_locator` on every
    entry, so neither can exercise an omission), one entry complete, the
    sibling entry omitting exactly one sub-key at a time -- proving the
    omitting entry borrows neither the other entry's locator nor falls
    back to the engine's `TAG_RE`/`DISPLAY_BLOCK_RE` constants (spec
    `implementation-per-document-vocabulary`, scenario "A missing sub-key
    refuses at its exact indexed path")."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-block-locator-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_a_missing_leaf_refuses_naming_the_bare_leaf(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        del full["documents"][0]["block_locator"]
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("documents[0].block_locator", message)

    def test_a_missing_subkey_refuses_at_its_exact_indexed_subpath(self):
        for sub_key in ("pattern", "block_pattern", "identity"):
            with self.subTest(sub_key=sub_key):
                tmp_dir = self._tmp_dir()
                full = _two_document_profile(tmp_dir)
                del full["documents"][1]["block_locator"][sub_key]
                profile_file = _write_profile(tmp_dir, full)
                with self.assertRaises(RuntimeError) as ctx:
                    _fresh_resolver_load(str(profile_file))
                message = str(ctx.exception)
                self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
                self.assertIn(f"documents[1].block_locator.{sub_key}", message)
                # Neither borrows the sibling entry's locator nor falls
                # back silently: the resolver refuses outright, so no
                # value for the omitting entry is ever produced at all.
                self.assertNotIn("documents[0].block_locator", message)

    def test_a_complete_locator_passes_and_is_returned_verbatim(self):
        """The positive control every refusal case above is a mutation OF."""
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(
            module.PROFILE["documents"][0]["block_locator"], _block_locator())


#: A pattern with 0, 2, or 3 capturing groups -- the block locator's own
#: reader takes exactly one value, so all three counts must refuse,
#: including 3 (the case existing so nobody copies `citation_pattern`'s
#: own three-group rule here by habit).
_ZERO_GROUP_PATTERN = r"\\tag\{[^}]+\}"
_TWO_GROUP_PATTERN = r"\\tag\{([^}]+)\}-(\d+)"
_THREE_GROUP_PATTERN = r"\\tag\{([^}]+)\}-(\d+)-(\d+)"


class BlockLocatorShapeValidationTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D1, tasks.md
    1.4/1.5): the locator's own shape, validated at resolve time --
    `IMPLEMENTATION_DOMAIN_PROFILE_INVALID_BLOCK_LOCATOR`, naming the
    exact indexed sub-path, for an uncompilable `pattern`, a `pattern`
    with other than exactly one capturing group (0, 2, or 3 -- 3
    deliberately included so `citation_pattern`'s own rule is not copied
    here), and an `identity` whose `string.Formatter().parse` yields
    other than exactly one field named `value`."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-block-shape-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _profile_with_locator(self, tmp_dir: Path, locator: dict) -> dict:
        full = _cut2_profile(tmp_dir)
        full["documents"][0]["block_locator"] = locator
        return full

    def test_an_uncompilable_pattern_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        locator = {**_block_locator(), "pattern": r"\\tag\{([^}]+"}  # unbalanced paren
        full = self._profile_with_locator(tmp_dir, locator)
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_BLOCK_LOCATOR", message)
        self.assertIn("documents[0].block_locator.pattern", message)

    def test_pattern_group_counts_other_than_one_refuse_by_name(self):
        for count, pattern in (
            (0, _ZERO_GROUP_PATTERN), (2, _TWO_GROUP_PATTERN),
            (3, _THREE_GROUP_PATTERN),
        ):
            with self.subTest(group_count=count):
                tmp_dir = self._tmp_dir()
                locator = {**_block_locator(), "pattern": pattern}
                full = self._profile_with_locator(tmp_dir, locator)
                profile_file = _write_profile(tmp_dir, full)
                with self.assertRaises(RuntimeError) as ctx:
                    _fresh_resolver_load(str(profile_file))
                message = str(ctx.exception)
                self.assertIn(
                    "IMPLEMENTATION_DOMAIN_PROFILE_INVALID_BLOCK_LOCATOR", message)
                self.assertIn("documents[0].block_locator.pattern", message)
                self.assertIn(str(count), message)

    def test_an_uncompilable_block_pattern_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        locator = {**_block_locator(), "block_pattern": r"(?s)\$\$.*?\$\$("}
        full = self._profile_with_locator(tmp_dir, locator)
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_BLOCK_LOCATOR", message)
        self.assertIn("documents[0].block_locator.block_pattern", message)

    def test_identity_with_zero_fields_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        locator = {**_block_locator(), "identity": "no fields at all"}
        full = self._profile_with_locator(tmp_dir, locator)
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_BLOCK_LOCATOR", message)
        self.assertIn("documents[0].block_locator.identity", message)

    def test_identity_with_two_fields_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        locator = {**_block_locator(), "identity": "{value}{other}"}
        full = self._profile_with_locator(tmp_dir, locator)
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_BLOCK_LOCATOR", message)
        self.assertIn("documents[0].block_locator.identity", message)

    def test_identity_with_a_field_not_named_value_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        locator = {**_block_locator(), "identity": "{}"}
        full = self._profile_with_locator(tmp_dir, locator)
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_BLOCK_LOCATOR", message)
        self.assertIn("documents[0].block_locator.identity", message)


class CrossCitationLeafOwnTierTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D5, R1 resolved
    5d42dd7, tasks.md 2.2/2.5): `documents[N].cross_citation` is its OWN
    required tier, appended right after `block_locator` -- a missing LEAF
    refuses naming `documents[N].cross_citation` alone; a leaf DECLARED as a
    mapping but missing a sub-key refuses at its own exact indexed sub-path
    (`documents[1].cross_citation.resolves_against`), never the bare parent
    leaf. Unlike `block_locator`, the leaf's own VALUE may be the literal
    `None` -- a real declared state, not an omission (spec
    `implementation-per-document-vocabulary`, "An explicit `None` is
    accepted and crosses nothing")."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-cross-citation-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_a_missing_leaf_refuses_naming_the_bare_leaf(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        del full["documents"][0]["cross_citation"]
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("documents[0].cross_citation", message)

    def test_a_missing_subkey_refuses_at_its_exact_indexed_subpath(self):
        for sub_key in ("pattern", "resolves_against"):
            with self.subTest(sub_key=sub_key):
                tmp_dir = self._tmp_dir()
                full = _two_document_profile(tmp_dir)
                del full["documents"][1]["cross_citation"][sub_key]
                profile_file = _write_profile(tmp_dir, full)
                with self.assertRaises(RuntimeError) as ctx:
                    _fresh_resolver_load(str(profile_file))
                message = str(ctx.exception)
                self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
                self.assertIn(f"documents[1].cross_citation.{sub_key}", message)
                self.assertNotIn("documents[0].cross_citation", message)

    def test_none_is_a_valid_declaration_and_passes(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        self.assertIsNone(full["documents"][0]["cross_citation"])
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertIsNone(module.PROFILE["documents"][0]["cross_citation"])

    def test_a_complete_crossing_passes_and_is_returned_verbatim(self):
        """The positive control every refusal case above is a mutation OF."""
        tmp_dir = self._tmp_dir()
        full = _two_document_profile(tmp_dir)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(
            module.PROFILE["documents"][1]["cross_citation"],
            _cross_citation("proposal"))


#: A pattern with 0 or 2 capturing groups -- the crossing's own reader
#: takes exactly one value (design.md D5, same reasoning as `block_locator`'s
#: own group-count rule).
_ZERO_GROUP_CROSSING_PATTERN = r"\[claims:[A-Za-z0-9]+\]"
_TWO_GROUP_CROSSING_PATTERN = r"\[claims:([A-Za-z0-9]+)\]-(\d+)"


class CrossCitationShapeValidationTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md D5, tasks.md
    2.3/2.4): the crossing's own shape, validated at resolve time --
    `IMPLEMENTATION_DOMAIN_PROFILE_INVALID_CROSS_CITATION_PATTERN` for an
    uncompilable `pattern` or one with other than exactly one capturing
    group, `IMPLEMENTATION_DOMAIN_PROFILE_UNKNOWN_CROSS_DOCUMENT` for a
    `resolves_against` naming no declared label or naming its own entry.
    Exercised against a two-document profile: `documents[0]` (label
    `"proposal"`) is the one under test here, `documents[1]` (label
    `"document-one"`) supplies the OTHER declared label a crossing can
    legally resolve against."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-cross-shape-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _profile_with_crossing(self, tmp_dir: Path, crossing: dict) -> dict:
        full = _two_document_profile(tmp_dir)
        full["documents"][0]["cross_citation"] = crossing
        return full

    def test_an_uncompilable_pattern_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        crossing = {**_cross_citation("document-one"),
                    "pattern": r"\[claims:([A-Za-z0-9"}  # unbalanced bracket
        full = self._profile_with_crossing(tmp_dir, crossing)
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn(
            "IMPLEMENTATION_DOMAIN_PROFILE_INVALID_CROSS_CITATION_PATTERN", message)
        self.assertIn("documents[0].cross_citation.pattern", message)

    def test_pattern_group_counts_other_than_one_refuse_by_name(self):
        for count, pattern in (
            (0, _ZERO_GROUP_CROSSING_PATTERN), (2, _TWO_GROUP_CROSSING_PATTERN),
        ):
            with self.subTest(group_count=count):
                tmp_dir = self._tmp_dir()
                crossing = {**_cross_citation("document-one"), "pattern": pattern}
                full = self._profile_with_crossing(tmp_dir, crossing)
                profile_file = _write_profile(tmp_dir, full)
                with self.assertRaises(RuntimeError) as ctx:
                    _fresh_resolver_load(str(profile_file))
                message = str(ctx.exception)
                self.assertIn(
                    "IMPLEMENTATION_DOMAIN_PROFILE_INVALID_CROSS_CITATION_PATTERN",
                    message)
                self.assertIn("documents[0].cross_citation.pattern", message)
                self.assertIn(str(count), message)

    def test_resolves_against_naming_an_undeclared_label_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        crossing = _cross_citation("no-such-label")
        full = self._profile_with_crossing(tmp_dir, crossing)
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_UNKNOWN_CROSS_DOCUMENT", message)
        self.assertIn("documents[0].cross_citation.resolves_against", message)

    def test_resolves_against_naming_its_own_entry_refuses_by_name(self):
        """`documents[0]`'s own label is `"proposal"` -- a crossing naming
        that same label resolves against itself, which crosses nothing."""
        tmp_dir = self._tmp_dir()
        crossing = _cross_citation("proposal")
        full = self._profile_with_crossing(tmp_dir, crossing)
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_UNKNOWN_CROSS_DOCUMENT", message)
        self.assertIn("documents[0].cross_citation.resolves_against", message)

    def test_a_valid_crossing_resolves_and_is_used(self):
        """The positive control every refusal case above is a mutation OF."""
        tmp_dir = self._tmp_dir()
        crossing = _cross_citation("document-one")
        full = self._profile_with_crossing(tmp_dir, crossing)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(module.PROFILE["documents"][0]["cross_citation"], crossing)


class DocumentsDirectoryEnvironmentOverrideTests(unittest.TestCase):
    """Threat-matrix RED test (design.md, Environment-variable routing,
    task 9.2): `IMPLEMENTATION_PROPOSALS` must still win over
    `documents.directory` -- `proposals_root()`'s override check runs
    BEFORE the profile-supplied default, exactly as it did in Cut 1 for the
    hardcoded `FORGE_ROOT / "proposals"`. Proven via a real subprocess
    against a Cut-2-complete fixture profile whose `documents.directory`
    deliberately points somewhere else, never a monkeypatch (recorded
    scar: patching a module attribute has zero effect on a subprocess).

    A prior version of this test drove `admit` with an out-of-workspace
    target and asserted only `assertNotIn("REVISION_UNREADABLE", ...)`.
    Measured: that target trips `OUTSIDE_WORKSPACE` before `revision_source`
    is ever called, so the assertion held with the override deleted outright
    (`proposals_root` rewritten to always return `DOCUMENTS[index]["directory"]`)
    -- neither directory's text was ever read. This version calls
    `revision_source` itself, in a real subprocess carrying the real env
    var, and asserts on the CONTENT the fixture plants distinguishably in
    each directory.
    """

    def test_the_env_override_wins_over_documents_directory(self):
        fixture_dir = Path(tempfile.mkdtemp(prefix="documents-directory-override-"))
        self.addCleanup(shutil.rmtree, fixture_dir, ignore_errors=True)
        profile_documents_dir = fixture_dir / "not-the-real-proposals-dir"
        profile_documents_dir.mkdir()
        env_documents_dir = fixture_dir / "the-real-proposals-dir"
        env_documents_dir.mkdir()
        revision_name = "seal-2.md"
        env_text = "the env-routed revision text\n"
        (env_documents_dir / revision_name).write_text(env_text, encoding="utf-8")
        (profile_documents_dir / revision_name).write_text(
            "the profile-routed revision text (must not be read)\n",
            encoding="utf-8")

        full = _cut2_profile(fixture_dir)
        full["documents"][0]["directory"] = profile_documents_dir
        profile_file = _write_profile(fixture_dir, full)

        env = dict(os.environ)
        env[_ENV_VAR] = str(profile_file)
        env["IMPLEMENTATION_PROPOSALS"] = str(env_documents_dir)
        probe = (
            "import sys, json\n"
            f"sys.path.insert(0, {str(ENGINE_DIR)!r})\n"
            "import implementation_engine as engine\n"
            f"print(json.dumps(engine.revision_source({revision_name!r})))\n"
        )
        proc = subprocess.run([sys.executable, "-c", probe],
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            json.loads(proc.stdout), env_text,
            "the env override did not win: revision_source read the "
            "profile-routed directory's content instead")


#: Cut 3 slice C (design.md D1): the five per-document claim-vocabulary
#: leaves a `documents[N]` entry may declare, overlaying the top-level
#: `provenance.*`/`findings.*` scalars. All-or-nothing per entry.
_DOCUMENT_VOCAB_LEAVES: tuple[str, ...] = (
    "claim_key", "locus_key", "remedy_locus_key", "notation_keys",
    "citation_pattern",
)

_TWO_GROUP_CITATION_PATTERN = r"Foo\((\d+)\)|Bar(\d+)"
_FOUR_GROUP_CITATION_PATTERN = r"Foo\((\d+)\)|Bar(\d+)|Baz(\d+)|Qux(\d+)"


def _document_one_overlay() -> dict:
    """A complete, per-document vocabulary overlay, deliberately distinct
    from `_cut2_profile`'s document-0 top-level values (design.md D1/D6)."""
    return {
        "claim_key": "propositions",
        "locus_key": "propositions",
        "remedy_locus_key": "remedy_propositions",
        "notation_keys": {
            "locus": "propositions",
            "remedyLocus": "remedyPropositions",
            "unknown": "unknownPropositions",
        },
        "citation_pattern": (
            r"Props?\.?\s*\(?(\d+)\)?|Prop\.?\s*\(?(\d+)\)?|"
            r"Propositions?\s*\((\d+)\)"),
    }


def _two_document_profile(tmp_dir: Path, *, document_one_overlay: dict | None = None) -> dict:
    """`_cut2_profile`'s single-document profile, with a second entry
    appended -- optionally carrying its own per-document vocabulary
    overlay. The appended entry declares a real, valid crossing back at
    document 0's own label (`"proposal"`) -- design.md D5/R1's own
    required tier -- so every existing test built on this helper that is
    not itself exercising `cross_citation` stays a mutation of a COMPLETE
    profile, never one that happens to pass because the leaf was silently
    absent."""
    profile = _cut2_profile(tmp_dir)
    entry: dict = {"directory": tmp_dir / "documents-1", "label": "document-one",
                   "dataset_marker": None, "block_locator": _block_locator(),
                   "cross_citation": _cross_citation("proposal")}
    if document_one_overlay is not None:
        entry.update(document_one_overlay)
    profile["documents"].append(entry)
    return profile


class DocumentVocabularyOverlayTests(unittest.TestCase):
    """Phase 1, C1 (design.md D1/D3): the resolver's all-or-nothing
    per-entry overlay tier -- an entry declaring ANY of the five leaves
    must declare ALL five, or the partial overlay is refused naming each
    missing leaf by its exact indexed path (spec
    `implementation-per-document-vocabulary`)."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-doc-vocab-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_declaring_only_one_leaf_refuses_incomplete_naming_it(self):
        """Each subTest declares a COMPLETE overlay minus exactly one leaf
        (Y1's own mutation shape: delete one leaf at a time from a declared
        overlay) -- the refusal names that ONE missing leaf."""
        for leaf in _DOCUMENT_VOCAB_LEAVES:
            with self.subTest(leaf=leaf):
                tmp_dir = self._tmp_dir()
                overlay = _document_one_overlay()
                del overlay[leaf]
                full = _two_document_profile(tmp_dir, document_one_overlay=overlay)
                profile_file = _write_profile(tmp_dir, full)
                with self.assertRaises(RuntimeError) as ctx:
                    _fresh_resolver_load(str(profile_file))
                message = str(ctx.exception)
                self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
                self.assertIn(f"documents[1].{leaf}", message)

    def test_declaring_none_of_the_five_resolves_without_refusal(self):
        """Spec 'A Per-Document Vocabulary Leaf Overlays, Never Replaces,
        The Top-Level One': a document declaring none of the five leaves
        resolves unchanged, no `provenance.*`/`findings.*` edit required."""
        tmp_dir = self._tmp_dir()
        full = _two_document_profile(tmp_dir)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(len(module.PROFILE["documents"]), 2)
        for leaf in _DOCUMENT_VOCAB_LEAVES:
            self.assertNotIn(leaf, module.PROFILE["documents"][1])

    def test_a_complete_overlay_resolves_with_its_own_values(self):
        tmp_dir = self._tmp_dir()
        overlay = _document_one_overlay()
        full = _two_document_profile(tmp_dir, document_one_overlay=overlay)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(module.PROFILE["documents"][1]["claim_key"], "propositions")
        self.assertEqual(
            module.PROFILE["documents"][1]["notation_keys"]["remedyLocus"],
            "remedyPropositions")

    def test_document_one_missing_override_does_not_borrow_document_zeros(self):
        """Spec 'No Document's Vocabulary Is Inferred From Another
        Document's': document 0 declares its own overlay, document 1
        declares none -- document 1's entry carries none of the five
        leaves at all, so nothing could be read off it but the top-level
        fallback."""
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        full["documents"][0].update(_document_one_overlay())
        full["documents"].append(
            {"directory": tmp_dir / "documents-1", "label": "document-one",
             "dataset_marker": None, "block_locator": _block_locator(),
             "cross_citation": _cross_citation("proposal")})
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(module.PROFILE["documents"][0]["claim_key"], "propositions")
        for leaf in _DOCUMENT_VOCAB_LEAVES:
            self.assertNotIn(leaf, module.PROFILE["documents"][1])


class NotationKeysShapeOverlayTests(unittest.TestCase):
    """Phase 1, C1 (design.md D3, tier 2): a declared `notation_keys`
    overlay must carry all three engine-read sub-keys, refused by its
    exact indexed sub-path when incomplete."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-notation-shape-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_missing_notation_subkey_refuses_naming_it(self):
        for sub_key in ("locus", "remedyLocus", "unknown"):
            with self.subTest(sub_key=sub_key):
                tmp_dir = self._tmp_dir()
                overlay = _document_one_overlay()
                del overlay["notation_keys"][sub_key]
                full = _two_document_profile(tmp_dir, document_one_overlay=overlay)
                profile_file = _write_profile(tmp_dir, full)
                with self.assertRaises(RuntimeError) as ctx:
                    _fresh_resolver_load(str(profile_file))
                message = str(ctx.exception)
                self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
                self.assertIn(f"documents[1].notation_keys.{sub_key}", message)


class CitationPatternGroupCountTests(unittest.TestCase):
    """Phase 1, C1 (design.md D3, tier 3): `citation_pattern`'s group count
    is validated at resolve time, wherever it resolves -- the top-level
    fallback AND every declared overlay (spec
    `implementation-per-document-vocabulary`)."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-citation-count-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def test_top_level_two_group_pattern_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        full["findings"]["citation_pattern"] = _TWO_GROUP_CITATION_PATTERN
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_CITATION_PATTERN", message)
        self.assertIn("findings.citation_pattern", message)
        self.assertIn("2", message)

    def test_top_level_four_group_pattern_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        full["findings"]["citation_pattern"] = _FOUR_GROUP_CITATION_PATTERN
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_CITATION_PATTERN", message)
        self.assertIn("findings.citation_pattern", message)
        self.assertIn("4", message)

    def test_overlay_two_group_pattern_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        overlay = _document_one_overlay()
        overlay["citation_pattern"] = _TWO_GROUP_CITATION_PATTERN
        full = _two_document_profile(tmp_dir, document_one_overlay=overlay)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_CITATION_PATTERN", message)
        self.assertIn("documents[1].citation_pattern", message)
        self.assertIn("2", message)

    def test_overlay_four_group_pattern_refuses_by_name(self):
        tmp_dir = self._tmp_dir()
        overlay = _document_one_overlay()
        overlay["citation_pattern"] = _FOUR_GROUP_CITATION_PATTERN
        full = _two_document_profile(tmp_dir, document_one_overlay=overlay)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INVALID_CITATION_PATTERN", message)
        self.assertIn("documents[1].citation_pattern", message)
        self.assertIn("4", message)

    def test_a_three_group_pattern_passes(self):
        """The positive control every refusal case above is a mutation OF."""
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        (tmp_dir / "proposals").mkdir()
        profile_file = _write_profile(tmp_dir, full)
        module = _fresh_resolver_load(str(profile_file))
        self.assertEqual(
            module.PROFILE["findings"]["citation_pattern"], _CITATION_PATTERN_SRC)


class IndexedDocumentsLeafRefusalTests(unittest.TestCase):
    """Cut 3 (`a-revision-is-two-documents`, Phase 1, tasks.md 1.1): `documents`
    becomes a list, validated per index (design.md D4) -- a missing or
    malformed leaf is named by its exact indexed path (`documents[1].directory`),
    never the bare field name. At this commit the resolver has not yet
    changed: `documents` is still validated as a single top-level mapping
    (`_REQUIRED_PRESENCE`'s `("documents", "label")` pair, `_REQUIRED_ABSOLUTE_ONLY`'s
    `("documents", "directory")` pair), so every case below is expected to
    stay RED until Phase 2 lands the per-entry walk."""

    def _tmp_dir(self) -> Path:
        tmp_dir = Path(tempfile.mkdtemp(prefix="impl-profile-documents-list-"))
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        return tmp_dir

    def _two_document_profile(self, tmp_dir: Path) -> dict:
        full = _cut2_profile(tmp_dir)
        full["documents"] = [
            {"directory": tmp_dir / "documents-0", "label": "label-0",
             "dataset_marker": None},
            {"directory": tmp_dir / "documents-1", "label": "label-1",
             "dataset_marker": None},
        ]
        return full

    def test_a_second_documents_missing_directory_refuses_by_indexed_name(self):
        tmp_dir = self._tmp_dir()
        full = self._two_document_profile(tmp_dir)
        del full["documents"][1]["directory"]
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("documents[1].directory", message)

    def test_the_first_documents_missing_label_refuses_by_indexed_name(self):
        tmp_dir = self._tmp_dir()
        full = self._two_document_profile(tmp_dir)
        del full["documents"][0]["label"]
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("documents[0].label", message)

    def test_an_empty_documents_list_refuses_incomplete_naming_index_zero(self):
        tmp_dir = self._tmp_dir()
        full = _cut2_profile(tmp_dir)
        full["documents"] = []
        profile_file = _write_profile(tmp_dir, full)
        with self.assertRaises(RuntimeError) as ctx:
            _fresh_resolver_load(str(profile_file))
        message = str(ctx.exception)
        self.assertIn("IMPLEMENTATION_DOMAIN_PROFILE_INCOMPLETE", message)
        self.assertIn("documents[0]", message)


class DocumentVocabularyZeroDeltaTests(unittest.TestCase):
    """Task 1.5 (design.md D2): with no overlay declared, the four module-
    level scalars re-derived through `document_vocabulary(0)`, plus
    `CITATION_RE`, must be byte-identical to the pre-re-derivation
    `PROFILE[...]` reads -- asserted directly against the real, no-overlay
    shipped profile (`proposal-implementation`), never inferred."""

    @staticmethod
    def _engine_module():
        engine_dir = FORGE / "skills/_core/implementation/engine"
        real_profile = FORGE / "skills/proposal-implementation/impl_profile.py"
        if str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))
        spec = importlib.util.spec_from_file_location(
            "impl_engine_zero_delta_probe", engine_dir / "implementation_engine.py")
        module = importlib.util.module_from_spec(spec)
        with seeded_profile(real_profile):
            spec.loader.exec_module(module)
        return module

    def test_the_five_scalars_equal_the_top_level_profile_values(self):
        engine = self._engine_module()
        self.assertNotIn("claim_key", engine.DOCUMENTS[0])
        self.assertEqual(engine.CLAIM_KEY, engine.PROFILE["provenance"]["claim_key"])
        self.assertEqual(engine.LOCUS_KEY, engine.PROFILE["findings"]["locus_key"])
        self.assertEqual(
            engine.REMEDY_LOCUS_KEY, engine.PROFILE["findings"]["remedy_locus_key"])
        self.assertEqual(engine.NOTATION_KEYS, engine.PROFILE["findings"]["notation_keys"])
        self.assertEqual(
            engine.CITATION_RE.pattern, engine.PROFILE["findings"]["citation_pattern"])


class DocumentVocabularyIndependenceTests(unittest.TestCase):
    """Task 1.10/1.11 (spec `implementation-per-document-vocabulary`,
    Requirement "No Document's Vocabulary Is Inferred From Another
    Document's"): `document_vocabulary(index)` never reads another index's
    own entry -- proven by an in-process `PROFILE` substitution and a
    direct call, never a subprocess (this exercises the function's own
    arithmetic, not a CLI dispatch, so an in-process substitution is not
    the "monkeypatch has zero effect on a subprocess" scar)."""

    @staticmethod
    def _engine_module():
        engine_dir = FORGE / "skills/_core/implementation/engine"
        real_profile = FORGE / "skills/proposal-implementation/impl_profile.py"
        if str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))
        spec = importlib.util.spec_from_file_location(
            "impl_engine_doc_vocab_independence_probe",
            engine_dir / "implementation_engine.py")
        module = importlib.util.module_from_spec(spec)
        with seeded_profile(real_profile):
            spec.loader.exec_module(module)
        return module

    def test_document_one_with_no_overlay_never_reads_document_zeros(self):
        engine = self._engine_module()
        original_profile = engine.PROFILE
        try:
            engine.PROFILE = {
                **original_profile,
                "documents": [
                    {**original_profile["documents"][0],
                     "claim_key": "claims-zero", "locus_key": "loci-zero",
                     "remedy_locus_key": "remedy-loci-zero",
                     "notation_keys": {"locus": "l", "remedyLocus": "r", "unknown": "u"},
                     "citation_pattern": r"Z\((\d+)\)|Z(\d+)|Zz(\d+)"},
                    {"directory": Path("/scratch/doc1"), "label": "doc1"},
                ],
                "provenance": {**original_profile["provenance"],
                              "claim_key": "top-level-claim"},
            }
            self.assertEqual(
                engine.document_vocabulary(1)["claim_key"], "top-level-claim",
                "document 1 with no overlay must resolve to the top-level "
                "fallback, never document 0's own declared overlay")
        finally:
            engine.PROFILE = original_profile


if __name__ == "__main__":
    unittest.main()
