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

import ast
import re
from pathlib import Path

#: Words a hosted SERVICE owns: the service itself, and the hardware it rents.
#: Any research project at all could rent them, which is why they sit in a half
#: of their own. One skill in this forge ships an adapter for exactly that
#: service, so the suite that tests the adapter names it constantly and
#: legitimately — measured, hundreds of times in one file. Guarded on every
#: surface the forge SHIPS; exempt under `tests/`, where guarding it would mean
#: exempting the file that most needs the word, which is not a guard.
FORGE_SERVICE_VOCABULARY = ("kaggle", "t4")

#: A target's SCIENCE words: quantities one research project's method names.
#: A target owns them, and ordinary English owns them too, and no regex can
#: tell the two apart. On the surfaces the forge SHIPS the ban is cheap and
#: already paid — doctrine, the usage reference, the kit and the scripts speak
#: in one deliberate voice and can simply choose another word. Under `tests/`
#: it is not cheap. Measured, when this split was written: six uses in the
#: suites with nothing to do with any target — a bulk download whose size a
#: remote job decides, git's own word for what a `fetch --dry-run` still moves,
#: and a 90-second bound on one subprocess. One of the six is a test METHOD
#: NAME. Guarding these here would fail legitimate usage rather than catch a
#: leak, which is the argument `TargetVocabularyLeakTests` already makes for
#: its own modules. Exempt under `tests/`, and the exemption is measured there
#: rather than assumed, so the day the number goes to zero somebody can
#: reconsider.
FORGE_TARGET_DOMAIN_WORDS = ("ceiling", "ramp", "transfer", "latent")

#: A target's PROPER NOUNS: the names one research project's products wear.
#: They mean nothing in ordinary English, so a hit is a leak every time and
#: there is no legitimate usage to exempt anywhere. Guarded on every surface
#: the forge writes, `tests/` included. This is the half that makes the split
#: worth having: the whole suite tree was left unscanned because ONE word in
#: ONE file needed an exemption, and these went unscanned with it.
FORGE_TARGET_PROPER_NOUNS = ("creda", "milcreda")

#: Words a target owns that the forge is forbidden to borrow — the floor the
#: derived guards stand on. Being a fixed list, it can only ever hold leaks
#: somebody already found; that is why the derived rules exist beside it rather
#: than instead of it, and why a word here may never be admitted to a skill's
#: own lexicon of words it owns outright.
#:
#: Composed from the three halves rather than restated, for the reason this
#: whole module exists: a fourth spelling of the same eight words is how the
#: floor drifts from the split that is supposed to describe it.
FORGE_VOCABULARY_FLOOR = (FORGE_SERVICE_VOCABULARY
                          + FORGE_TARGET_DOMAIN_WORDS
                          + FORGE_TARGET_PROPER_NOUNS)

#: This module, and the directory it shares with the suites.
DEFINITION_MODULE = Path(__file__).resolve()
SUITE_ROOT = DEFINITION_MODULE.parent


def suite_modules() -> list:
    """Every Python module under `tests/`, derived from the directory.

    `*.py` and not `test_*.py`: a leak — or a second spelling of the floor —
    parked in a helper module beside the suites counts exactly the same, and a
    roster that only looked at files named like suites would not see it.

    `.mjs` is deliberately out of this roster. The Node side's fixtures are
    derived from a DECLARED domain profile whose whole job is to name its
    domain, so what a scan finds there is a different question with a different
    answer, not this one repeated.
    """
    return sorted(SUITE_ROOT.glob("*.py"))


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


def scannable_suite_text(source: str) -> str:
    """`source` with every word-NAMING string literal blanked out.

    A guard that forbids a word has to be able to spell it. The floor above,
    `TARGET_LITERALS` in `test_remote_execution.py`, every `for leaked in (...)`
    list and the planted-leak fixtures all name the words they watch, and a rule
    that called those leaks would be a rule that could not be written down at
    all. So the surface this guard widened to has to let the mechanism through.

    Exempted by SHAPE, never by a list of line numbers — which is a list that
    goes stale the next time anything is inserted above it. The shape: a string
    literal whose ENTIRE value is one word on the floor is a word being NAMED,
    quoted as data for some rule to iterate over. Everything else is a word
    being USED — a sentence that contains it, an identifier built from it, a
    comment, a docstring. Quoting does not buy an exemption on its own: a
    sentence that names a target inside a string literal is still a leak, and
    still caught.

    The hosted-service fixtures (a `/…/input/…` path, an environment variable)
    need no shape exemption at all. They are exempt one level up, because
    `FORGE_SERVICE_VOCABULARY` is not guarded on this surface — which is the
    point of splitting the floor rather than the tree.

    Blanked to spaces rather than deleted, and over the UTF-8 BYTES of each line
    rather than its characters, because `ast` reports `col_offset` as a byte
    offset and these modules' prose is full of em dashes. Same-length spaces
    keep every later offset on the line valid, so the spans can be applied in
    any order.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source.lower()
    named = {word.lower() for word in FORGE_VOCABULARY_FLOOR}
    lines = [line.encode("utf-8") for line in source.splitlines()]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value.strip().lower() not in named:
            continue
        first, last = node.lineno - 1, node.end_lineno - 1
        for index in range(first, last + 1):
            start = node.col_offset if index == first else 0
            end = node.end_col_offset if index == last else len(lines[index])
            lines[index] = (lines[index][:start]
                            + b" " * (end - start)
                            + lines[index][end:])
    return "\n".join(line.decode("utf-8") for line in lines).lower()
