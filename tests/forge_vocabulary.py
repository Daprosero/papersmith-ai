"""The words a target owns, written down once for the whole forge.

The forge builds repositories for research projects it is never allowed to know
the name of. It knows only *"the words a target owns"* — never which target —
so the one thing it needs written down is the list of words it may not borrow,
and every guard that enforces that list derives its half from here rather than
respelling it.

Stated in a module of its own rather than in one of the suites, for a reason
the suites themselves argue elsewhere: `tests/test_skill_audit.py` copies four
derivation HELPERS out of `tests/test_proposal_implementation.py` byte for byte
and pays for the drift with `CopiedHelperFidelityTests`, because sharing a
helper means editing a seventy-five-class suite from inside a change about a
different skill. A constant is not that. It carries no logic to review, both
suites need the identical value rather than an equivalent one, and its own
comment has demanded a single spelling since the day it was written. Putting it
in either suite would make one skill's test file the owner of a fact that
belongs to neither.

This module is deliberately not named `test_*.py`. The configured gate
discovers suites by that pattern (`tests/test_forge_gate.py`), so a definition
module here is importable by every suite without becoming one.
"""

import re

#: Words a target owns that the forge is forbidden to borrow — the floor the
#: derived guards stand on. Being a fixed list, it can only ever hold leaks
#: somebody already found; that is why the derived rules exist beside it rather
#: than instead of it, and why a word here may never be admitted to a skill's
#: own lexicon of words it owns outright.
FORGE_VOCABULARY_FLOOR = ("kaggle", "t4", "ceiling", "ramp", "transfer",
                          "creda", "milcreda", "latent")


def leak_pattern(word: str) -> re.Pattern:
    """The pattern that decides whether `word` has leaked into a text.

    Word boundaries and not a bare substring: `arm` alone fires on `warm`,
    `harm` and `alarm`, and a guard that fails on an innocent word is a guard
    the next contributor deletes rather than reads — which leaves the boundary
    it protects with nothing watching it at all.

    The optional plural is not a nicety. A word on the floor names a thing, and
    a thing gets counted and gets written to a file, so a leak arrives as
    `<word>s.json` or as "how many <word>s there are" far more often than as
    the bare singular. Measured, by execution:

        \\bceiling\\b   vs 'ceilings.json' -> no match
        \\bceilings?\\b vs 'ceilings.json' -> match

    `remote-execution`'s `test_shard_io_source_names_no_service_and_no_domain_term`
    has spelled it `s?` since it was written; the rule had never been carried
    to the guard that scans the kit, which is the surface a leak ships from.
    """
    return re.compile(rf"\b{re.escape(word)}s?\b")


def leaks_in(text: str, words=FORGE_VOCABULARY_FLOOR) -> list[str]:
    """Which of `words` appear in `text`, in the order `words` states them.

    Case-folded here rather than at every call site: a leak wearing a target's
    own capitalisation is the same leak, and a guard that each caller had to
    remember to lower is a guard with as many spellings as it has callers.
    """
    lowered = text.lower()
    return [word for word in words if leak_pattern(word).search(lowered)]
