"""Cut 3 (`a-revision-is-two-documents`, Phase 3, design.md D9): the
two-document fixture profile -- the instrument without which every pair
branch `documents` becoming a list introduces is a false guard (a branch no
reachable configuration takes cannot be mutation-proven).

**This file is never loaded in place.** `tests/pair/corpus.py`'s `build()`
reads this file's own TEXT and writes a fresh copy into a scratch directory
per run, `_SKILL` re-anchored to the REAL skill directory first -- the same
`_write_scratch_profile` mechanism `test_implementation_domain_mutation.py`
already uses for its own scratch mutation copies (M4, reused not rebuilt).
`_SKILL` is a distinct name from `_FIXTURE_ROOT` on purpose: re-anchoring
replaces only the assignment line just below (so `kit.root`/`cli.path` keep
pointing at the REAL skill's actual files, the same launcher and package
every other fixture profile in this suite resolves against), while
`_FIXTURE_ROOT` is left untouched, so it resolves to wherever the scratch
copy actually lands -- a fresh, unique pair of `documents[i].directory`
paths every run. (`tests/pair/corpus.py` asserts this exact assignment
line occurs exactly once before replacing it -- an ambiguous anchor is not
a mutation that can run unambiguously.)

Every non-`documents` field below is a minimal, syntactically complete
literal -- real content is irrelevant to what this fixture exists to prove
(the per-index resolver walk and a real subprocess's willingness to load a
two-document profile), only completeness is, exactly
`test_implementation_profile.py`'s own `_VALID_OBJECTIVE_SRC` convention.

Sanctioned as a tmpdir fixture profile by `impl_domain_profile._resolve()`'s
own comment: a "must live under FORGE_ROOT" rule "was considered and
rejected" for exactly this case. Not picked up as a third skill by
`test_implementation_domain_lock.py`'s `discover_profiles()`, which globs
`.claude/skills/*/impl_profile.py` only -- this file lives under `tests/`.
"""
from __future__ import annotations

from pathlib import Path

#: Re-anchored to the REAL skill directory by `tests/pair/corpus.py`'s
#: `build()` before this file is ever written to a scratch directory --
#: this exact line is the anchor that mechanism replaces. Left as-is (never
#: loaded in place), this would resolve to the scratch copy's own location,
#: which is wrong for `kit.root`/`cli.path`.
_SKILL = Path(__file__).resolve().parent

#: Deliberately NOT re-anchored: this tracks wherever the scratch copy
#: itself lands, giving `documents[0].directory`/`documents[1].directory`
#: a fresh pair of paths per run. Existence is not required (M3) -- neither
#: subdirectory needs to exist on disk for the resolver to accept it.
_FIXTURE_ROOT = Path(__file__).resolve().parent

_OBJECTIVE_FLOW = {
    "purpose": "prove the two-document pair is representable, nothing more",
    "stages": [
        {"stage": "resolves", "establishes": "a two-document profile imports cleanly",
         "behindWhen": "the resolver has not yet accepted a documents list"},
    ],
    "arrival": "every pair branch this cut introduces is reachable",
    "humanStops": ["none -- this profile is test-only fixture content"],
}

PROFILE = {
    "kit": {"root": _SKILL},
    "cli": {"path": _SKILL / "scripts" / "implementation_cli.py"},
    "objective": _OBJECTIVE_FLOW,
    "provenance": {
        "claim_key": "equations",
        "authored_init_sentence": (
            "Each module declares the sections and equations it implements in\n"
            "`__provenance__`, and every invariant listed there has a matching\n"
            "test under tests/.\n"),
    },
    "findings": {
        "locus_key": "equations",
        "remedy_locus_key": "remedy_equations",
        "notation_keys": {
            "locus": "equations",
            "remedyLocus": "remedyEquations",
            "unknown": "unknownEquations",
        },
        "citation_pattern": (
            r"Ecs?\.?\s*\(?(\d+)\)?|Eq\.?\s*\(?(\d+)\)?|Ecuaciones?\s*\((\d+)\)"),
    },
    "vocabulary": {
        "subject_singular": "equation",
        "subject_plural": "equations",
        "subject_singular_es": "ecuación",
        "subject_plural_es": "ecuaciones",
        "subject_collective": "mathematics",
        "subject_collective_es": "matemática",
        "artifact_noun": "formulation",
        "names": [
            "equation", "equations", "ecuación", "ecuaciones",
            "mathematics", "matemática", "formulation",
        ],
    },
    # Cut 3 (design.md D9): the ONE field this fixture exists for -- a
    # two-entry `documents` list, so every pair branch `len(documents) > 1`
    # introduces has a reachable configuration in this repository.
    "documents": [
        {"directory": _FIXTURE_ROOT / "proposals", "label": "proposal",
         # `a-data-directory-somebody-can-owe` (B1, design.md D10): a
         # fixture edit, not the reaching configuration -- required,
         # `None` here.
         "dataset_marker": None,
         # `the-agreement-nothing-computes` (Slice D, task 2.7/tasks.md
         # "the two new required leaves; invisible to `discover_profiles()`",
         # this file lives under `tests/`, not `.claude/skills/*/`):
         # syntactically complete, real content is irrelevant, exactly this
         # module's own docstring convention.
         "block_locator": {
             "pattern": r"\\tag\{([^}]+)\}",
             "block_pattern": r"(?s)\$\$.*?\$\$",
             "identity": "\\tag{{{value}}}",
         },
         # Nullable (unlike `block_locator`): this fixture proves the
         # per-index resolver walk, not a real crossing -- `None` is a
         # legal declared value and keeps this entry a fixture edit, not a
         # reaching configuration `crossing_state`'s own tests must supply.
         "cross_citation": None},
        {"directory": _FIXTURE_ROOT / "experiments", "label": "experiments",
         "dataset_marker": None,
         "block_locator": {
             "pattern": r"\\tag\{([^}]+)\}",
             "block_pattern": r"(?s)\$\$.*?\$\$",
             "identity": "\\tag{{{value}}}",
         },
         "cross_citation": None},
    ],
    # `the-holder-each-skill-declares` (design.md D1/D4): the 8th top-level
    # `PROFILE` section this fixture must carry, or the suite dies at
    # import once the required-leaf tier lands (tasks.md 1.1). A legal
    # placeholder name, not either shipped skill's own declared filename.
    "holder": {
        "filename": "Fixture_AGREED.md",
        "headings": ("# Agreed", "## Ladder"),
        "scaffold": "# Agreed\n\n## Ladder\n",
    },
}

# Cut 3 slice C (`the-second-document-verified-on-its-own-terms`, design.md
# M6): document 1's own per-document vocabulary overlay -- without it,
# document 1 would inherit `claim_key: "equations"` under D1's fallback,
# and its module scope would equal document 0's, leaving the drift-control
# fixture (`TwoDocumentDriftControlTests`) unable to tell the two apart.
# Applied via a post-hoc `update()` rather than inline in `documents[1]`'s
# own literal above, so `tests/pair/corpus.py`'s existing
# `_SECOND_DOCUMENT_ENTRY` anchor -- the "resolver per-index refusal"
# branch, unrelated to this leaf -- keeps matching that entry's original
# two-key text unedited.
PROFILE["documents"][1].update({
    "claim_key": "experiments",
    "locus_key": "experiments",
    "remedy_locus_key": "remedy_experiments",
    "notation_keys": {
        "locus": "experiments",
        "remedyLocus": "remedyExperiments",
        "unknown": "unknownExperiments",
    },
    "citation_pattern": (
        r"Exps?\.?\s*\(?(\d+)\)?|Experiment\.?\s*\(?(\d+)\)?|"
        r"Experimentos?\s*\((\d+)\)"),
})
