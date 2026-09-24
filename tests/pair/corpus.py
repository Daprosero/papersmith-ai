"""The pair corpus's own fixture builder (Phase 3/4, design.md D9).

Writes `tests/fixtures/two_documents/impl_profile.py` -- a committed
TEMPLATE, never loaded in place -- into a fresh scratch directory per run,
`_SKILL` re-anchored to the REAL skill directory: the same
`_write_scratch_profile` mechanism `test_implementation_domain_mutation.py`
already uses for its own scratch mutation copies (M4, reused not rebuilt).
`_FIXTURE_ROOT` is deliberately left untouched by that re-anchor, so it
resolves to wherever the scratch copy actually lands -- a fresh
`documents[i].directory` pair every run, existence not required (M3).

Two builders: `build()` (the valid two-document profile) and
`build_broken_second_document()` (task 4.2's "resolver per-index refusal"
branch -- `documents[1].directory` removed before `_SKILL` is re-anchored,
anchor discipline asserted first, the same discipline design.md D8 already
requires of every mutation in this suite).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

_HERE = Path(__file__).resolve()
_TESTS_DIR = _HERE.parents[1]
FORGE = _TESTS_DIR.parent
FIXTURE_PROFILE_TEMPLATE = _TESTS_DIR / "fixtures" / "two_documents" / "impl_profile.py"
REAL_SKILL_DIR = FORGE / "skills" / "proposal-implementation"

#: The exact line `tests/fixtures/two_documents/impl_profile.py` carries --
#: replacing it is the whole re-anchoring mechanism, mirroring
#: `test_implementation_domain_mutation.py`'s `_write_scratch_profile`.
_SKILL_ANCHOR = "_SKILL = Path(__file__).resolve().parent"

#: The second document's entry in the template, removed whole (not just its
#: `directory` value) by `build_broken_second_document()` -- proving the
#: resolver's per-index walk names the missing leaf `documents[1].directory`
#: by its own indexed path, never the bare field name.
#: `a-data-directory-somebody-can-owe` (B1): the template's second entry
#: gained a required `dataset_marker` leaf (a fixture edit, not the
#: reaching configuration -- `None` here). `the-agreement-nothing-computes`
#: (Slice D) grew it again with a required `block_locator` leaf, and once
#: more with a required (nullable) `cross_citation` leaf. Both anchors
#: below and their mutated counterparts grew with the template, keeping the
#: same "directory removed, everything else kept" shape the resolver's
#: per-index refusal branch depends on.
_SECOND_DOCUMENT_ENTRY = (
    '{"directory": _FIXTURE_ROOT / "experiments", "label": "experiments",\n'
    '         "dataset_marker": None,\n'
    '         "block_locator": {\n'
    '             "pattern": r"\\\\tag\\{([^}]+)\\}",\n'
    '             "block_pattern": r"(?s)\\$\\$.*?\\$\\$",\n'
    '             "identity": "\\\\tag{{{value}}}",\n'
    '         },\n'
    '         "cross_citation": None}')
_SECOND_DOCUMENT_WITHOUT_DIRECTORY = (
    '{"label": "experiments",\n'
    '         "dataset_marker": None,\n'
    '         "block_locator": {\n'
    '             "pattern": r"\\\\tag\\{([^}]+)\\}",\n'
    '             "block_pattern": r"(?s)\\$\\$.*?\\$\\$",\n'
    '             "identity": "\\\\tag{{{value}}}",\n'
    '         },\n'
    '         "cross_citation": None}')


@dataclasses.dataclass(frozen=True)
class Roots:
    """Duck-typed against `seal.corpus.Roots` for `seal_harness.run_case`.
    Phase 3/4's two pair-corpus cases are target-free (`name`, resolved
    before any repository is touched), so `fixture_a`/`fixture_b`/`fixture_t`
    are never read by either case and are not carried here."""

    root: Path
    profile_path: Path
    #: Read unconditionally by `seal_harness.run_case`/`resolve_argv` even
    #: when a case's own argv never uses `<PROPOSALS>` -- a placeholder
    #: path, not required to exist (M3).
    proposals: Path


def _write(root: Path, source: str) -> Roots:
    root.mkdir(parents=True, exist_ok=True)
    profile_path = root / "impl_profile.py"
    profile_path.write_text(source, encoding="utf-8")
    return Roots(root=root, profile_path=profile_path, proposals=root / "proposals")


def build(root: Path) -> Roots:
    """The valid two-document fixture profile (task 4.2's "DOCUMENTS[1]
    presence" branch): a real subprocess loads a `documents` list of two
    complete entries and runs normally."""
    template_src = FIXTURE_PROFILE_TEMPLATE.read_text(encoding="utf-8")
    assert template_src.count(_SKILL_ANCHOR) == 1, (
        "the fixture profile template's _SKILL anchor line moved or was "
        "duplicated -- the same re-anchoring this builder depends on")
    anchored = template_src.replace(
        _SKILL_ANCHOR, f"_SKILL = Path({str(REAL_SKILL_DIR)!r})")
    return _write(root, anchored)


def build_broken_second_document(root: Path) -> Roots:
    """Task 4.2's "resolver per-index refusal" branch: `documents[1]`'s
    `directory` leaf removed before `_SKILL` is re-anchored. Anchor
    discipline (design.md D8): the OLD spelling occurs exactly once in the
    template and the NEW spelling not at all, asserted before the
    substitution runs -- an anchor that matched is not a mutation that ran."""
    template_src = FIXTURE_PROFILE_TEMPLATE.read_text(encoding="utf-8")
    assert template_src.count(_SECOND_DOCUMENT_ENTRY) == 1, (
        "the fixture profile template's second-document entry moved or was "
        "duplicated -- an ambiguous anchor is not a mutation that can run "
        "unambiguously")
    assert template_src.count(_SECOND_DOCUMENT_WITHOUT_DIRECTORY) == 0, (
        "the mutated spelling already appears in the template before any "
        "mutation -- anchor invalid")
    mutated_src = template_src.replace(
        _SECOND_DOCUMENT_ENTRY, _SECOND_DOCUMENT_WITHOUT_DIRECTORY, 1)
    assert mutated_src.count(_SKILL_ANCHOR) == 1
    anchored = mutated_src.replace(
        _SKILL_ANCHOR, f"_SKILL = Path({str(REAL_SKILL_DIR)!r})")
    return _write(root, anchored)
