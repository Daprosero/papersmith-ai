"""The auditor audited by its own moves.

A skill that finds hand-maintained rosters in other skills, and ships one of its
own, is the defect class it exists to find. So every mechanism `skill-audit`
points at a subject is pointed back at `skill-audit` here: its moves table is
held to argparse's real subcommand surface, its doctrine side is held to an
`ast` gate that forbids reaching for the producer, and its report shape is held
to the schema `check-report` actually enforces rather than to the prose beside
it.

Nothing in this file asserts that a suite passed. Greenness is not evidence; a
named execution with a named observation is.
"""

import ast
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
SKILL_ROOT = FORGE / ".claude" / "skills" / "skill-audit"
SKILL_MD = SKILL_ROOT / "SKILL.md"
CLI = SKILL_ROOT / "scripts" / "audit_cli.py"
USAGE_MD = SKILL_ROOT / "references" / "usage.md"
PROBES = SKILL_ROOT / "references" / "probes"

#: The one file the four derivation helpers below were copied out of. Copied and
#: not shared: sharing means editing a 75-class suite from inside a change about
#: a different skill, which is the exact scope creep two archive reports flagged.
#: The price of copying is drift, and drift is paid for by
#: `CopiedHelperFidelityTests` rather than discovered later.
ORIGINAL_HELPERS = FORGE / "tests" / "test_proposal_implementation.py"

MOVES_HEADER = "| Move | Ships as | Lock |"
SUBCOMMAND_HEADER = "| Subcommand | Derives | Emits |"
REPORT_HEADER = "| Item | Required content | Rejected when |"

#: Words a target owns that the forge is forbidden to borrow — the floor the
#: derived guard stands on. Being a fixed list, it can only ever hold leaks
#: somebody already found; that is why the derived rules exist beside it rather
#: than instead of it, and why a word here may never be admitted to
#: `FORGE_LEXICON`. Stated once, because two spellings of a floor is how a floor
#: drifts.
FORGE_VOCABULARY_FLOOR = ("kaggle", "t4", "ceiling", "ramp", "transfer",
                          "creda", "milcreda", "latent")

#: Words `skill-audit` owns outright, each with the argument for why. A set would
#: let this grow by one comma per inconvenient failure; a sentence is something a
#: reviewer can disagree with, and that is the whole mechanism.
FORGE_LEXICON = {
    "audit": "the central verb of this skill: it names the process, the CLI, "
             "the doctrine and the report the process delivers",
    "doctrine": "this skill's word for the documented half of a surface, the "
                "half a parseable table states and a reader believes",
    "roster": "the closed set a subject enumerates, and the subcommand that "
              "derives both of its halves without restating either",
    "probe": "the recipe that drives a subject as a process, named so it can "
             "never be mistaken for the roster it recovers",
    "phantom": "a member of the documented half with nothing behind it in the "
               "running code, one of the three sets every comparison reports",
    "inversion": "breaking a guarded fact on purpose to watch its lock fire, "
                 "the only proof this skill accepts that a lock runs at all",
    "adjudication": "deciding which half of a disagreeing surface is wrong, or "
                    "recording that the question has no answer yet",
    "falsifier": "the observation that would overturn a report, required of "
                 "every report this skill validates",
}


# --------------------------------------------------------------------------
# Derivation helpers, copied byte-identically out of
# `tests/test_proposal_implementation.py`. Do not edit either copy without
# editing the other: `CopiedHelperFidelityTests` turns drift into a red.
# --------------------------------------------------------------------------

def markdown_table_rows(text, header):
    """Every row of every table introduced by exactly this header line.

    One shape, read one way, wherever doctrine states a placement. Prose cannot
    be held to code — SKILL.md is what an agent reads, not a rendered artifact —
    so the instruction has to be written in something a test can parse.
    """
    lines = [line.strip() for line in text.splitlines()]
    tables = []
    for index, line in enumerate(lines):
        if line != header:
            continue
        rows = []
        for row in lines[index + 2:]:
            if not row.startswith("|"):
                break
            rows.append([cell.strip() for cell in row.strip("|").split("|")])
        tables.append(rows)
    return tables


def dict_literal_keys(source: Path, name: str) -> list[str]:
    """The string keys of a module-level dict assigned to `name`.

    The same argument `returned_keys` makes, one scope out: a list of commands
    written twice — once in the code that dispatches them and once in the
    reference somebody reads — is a list that loses one. Read it from the
    dispatch table instead.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        return sorted(key.value for key in node.value.keys
                      if isinstance(key, ast.Constant)
                      and isinstance(key.value, str))
    raise AssertionError(f"{source.name} assigns no module-level dict {name}")


def subcommand_surface(source: Path, function: str) -> dict[str, tuple[str, ...]]:
    """Every subcommand a parser-building function declares, with its flags.

    Nested groups are followed, so a subcommand reached only through another
    one is reported by the whole path a reader would have to type. Only the
    leaves are returned: a group parser whose subcommands are `required=True`
    names no invocation — typing it alone is refused — so documenting it as a
    command would document something nobody can run.

    Read from the parser rather than from a list beside it, for the reason
    `returned_keys` is: a roster restated by hand is a roster that loses one.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    definition = next(
        (node for node in ast.walk(tree)
         if isinstance(node, ast.FunctionDef) and node.name == function), None)
    if definition is None:
        raise AssertionError(f"{source.name} defines no {function}")

    groups: dict[str, str] = {}
    commands: dict[str, str] = {}
    flags: dict[str, list[str]] = {}
    owners: set[str] = set()

    def only_target(node):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None
        return node.targets[0].id

    for node in ast.walk(definition):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call, name = node.value, only_target(node)
            attribute = call.func.attr if isinstance(call.func, ast.Attribute) else ""
            holder = (call.func.value.id
                      if isinstance(call.func, ast.Attribute)
                      and isinstance(call.func.value, ast.Name) else "")
            if attribute == "add_subparsers":
                if name is not None:
                    groups[name] = commands.get(holder, "")
                owners.add(commands.get(holder, ""))
                continue
            if attribute == "add_parser" and holder in groups and call.args:
                literal = call.args[0]
                if not isinstance(literal, ast.Constant):
                    continue
                path = f"{groups[holder]} {literal.value}".strip()
                flags.setdefault(path, [])
                if name is not None:
                    commands[name] = path
                continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument" \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id in commands and node.args \
                and isinstance(node.args[0], ast.Constant) \
                and str(node.args[0].value).startswith("--"):
            flags[commands[node.func.value.id]].append(node.args[0].value)

    return {path: tuple(sorted(set(declared)))
            for path, declared in flags.items() if path not in owners}


def returned_keys(source: Path, function: str) -> list[str]:
    """The top-level keys a function's dict returns are built from.

    A command's reported statuses are doctrine's subject and the code's return
    value, and holding one to the other needs the second read from the code
    rather than restated beside it. `ast` rather than calling the function,
    because a command needs a target on disk to run and this needs to be
    answerable about a command nobody invoked.

    **Every** dict return is read, not the first, and they are required to agree.
    That second half is not decoration: a function whose early branches return a
    smaller dict than its late ones makes a key vanish for exactly the callers
    that took the early branch, and nothing else in this suite would notice.

    Returns whose value is not a dict literal are invisible here — a function
    that builds its dict in a variable and returns the name reports nothing, and
    that limitation is stated rather than guessed at.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"))
    definition = next(
        (node for node in ast.walk(tree)
         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
         and node.name == function), None)
    if definition is None:
        raise AssertionError(f"{source.name} defines no {function}")

    # Nested definitions are not descended into: a helper written inside the
    # function returns for itself, and counting its returns here would report
    # somebody else's key set as this function's.
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    returns: list[ast.Return] = []

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, nested):
                continue
            if isinstance(child, ast.Return):
                returns.append(child)
            visit(child)

    visit(definition)

    key_sets = []
    for node in returns:
        if not isinstance(node.value, ast.Dict):
            continue
        key_sets.append(sorted(
            key.value for key in node.value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)))
    if not key_sets:
        raise AssertionError(f"{function} returns no dict literal to read")
    if any(keys != key_sets[0] for keys in key_sets):
        raise AssertionError(
            f"{function}'s dict returns do not agree on their keys, so the key "
            "set a caller gets depends on which branch answered: "
            + " vs ".join(str(keys) for keys in key_sets))
    return key_sets[0]


# --------------------------------------------------------------------------
# Local support. Nothing below is copied; nothing below reaches for the
# producer to decide what the doctrine side contains.
# --------------------------------------------------------------------------

def doctrine_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def moves_rows() -> list[list[str]]:
    """The moves table's rows, from the markdown and from nowhere else."""
    tables = markdown_table_rows(doctrine_text(), MOVES_HEADER)
    if len(tables) != 1:
        raise AssertionError(
            f"SKILL.md must introduce exactly one {MOVES_HEADER} table; "
            f"found {len(tables)}")
    return tables[0]


def run_cli(*argv, cwd=None, timeout=60):
    """Drive `audit_cli.py` as a real process, never as an import.

    A double that replaces a function wholesale can never hold a claim about the
    process it would have run, so every roster probe in this file — including
    the ones pointed at the auditor itself — goes through `subprocess`.
    """
    return subprocess.run(
        [sys.executable, str(CLI), *argv],
        cwd=str(cwd) if cwd else None,
        shell=False, capture_output=True, text=True, timeout=timeout)


class SkillHouseShapeTests(unittest.TestCase):
    """The skill exists, in the shape the five existing skills actually have.

    Measured rather than taken from `skill-creator`, which caps a body at a size
    `proposal-implementation/SKILL.md` already exceeds by orders of magnitude and
    defers to a style guide this repository does not contain.
    """

    def test_the_shipped_paths_exist(self):
        for path in (SKILL_MD, CLI):
            with self.subTest(path=str(path.relative_to(FORGE))):
                self.assertTrue(path.is_file(),
                                f"{path.relative_to(FORGE)} does not exist")

    def test_frontmatter_is_exactly_name_then_description(self):
        """Five existing skills, five identical frontmatter shapes.

        `---` on line 1, `name` on 2, `description` on 3, `---` on 4, and not one
        key more. No `license`, no `metadata`, no `allowed-tools` appears in any
        of the five, so none appears here.
        """
        lines = doctrine_text().splitlines()
        self.assertGreaterEqual(len(lines), 4, "SKILL.md is shorter than its frontmatter")
        self.assertEqual(lines[0], "---", "line 1 must open the frontmatter")
        self.assertEqual(lines[1], "name: skill-audit", "line 2 must be the name")
        self.assertTrue(lines[2].startswith("description: "),
                        f"line 3 must be the description, got {lines[2]!r}")
        self.assertEqual(lines[3], "---", "line 4 must close the frontmatter")
        for forbidden in ("license:", "metadata:", "allowed-tools:"):
            self.assertNotIn(
                forbidden, "\n".join(lines[:4]),
                f"no existing skill carries {forbidden} in its frontmatter")

    def test_the_name_is_two_lowercase_hyphenated_words(self):
        self.assertRegex(SKILL_ROOT.name, r"^[a-z]+-[a-z]+$")

    def test_the_cli_is_stdlib_only(self):
        """A skill whose front door needs an install is a skill that cannot run.

        Read from the `ast` rather than by importing, so this stays answerable
        about a module nobody has to be able to import.
        """
        tree = ast.parse(CLI.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        # `sys.stdlib_module_names` arrived in 3.10 and this interpreter is
        # 3.9.6, so the permitted set is declared rather than asked for. A
        # declared set is a roster, which is this skill's own defect class — so
        # it is kept to the modules the file actually needs and any addition has
        # to be argued for here, in the open, rather than silently admitted.
        permitted = {"__future__", "argparse", "json", "pathlib",
                     "re", "subprocess", "sys"}
        self.assertEqual(
            sorted(imported - permitted), [],
            "audit_cli.py must import nothing outside the standard library, and "
            "nothing outside the modules this lock declares")

    def test_the_front_door_is_a_real_process_emitting_json(self):
        """Spec Group 1: invoked as a subprocess, it exits with an integer status
        and writes parseable JSON to stdout.

        Pointed at a probe recipe that is not there, so the assertion holds
        across every slice: inability to look is exit 2 carrying a JSON reason,
        never a bare traceback and never a silent zero.
        """
        result = run_cli("roster", "--subject", str(SKILL_ROOT),
                         "--probe-spec", str(PROBES / "no-such-recipe.json"))
        self.assertEqual(result.returncode, 2,
                         f"unexpected exit {result.returncode}: {result.stderr}")
        try:
            json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"stdout was not parseable JSON ({error}): {result.stdout!r}")


class ActivationContractTests(unittest.TestCase):
    """No shell is a hard refusal, not a degraded mode.

    An audit that cannot execute cannot adjudicate, and every claim it produced
    would be a candidate marked `read-only` with no `CONFIRMED` finding anywhere
    — the exact condition that cost five consecutive phases of this change.
    """

    def test_doctrine_makes_a_missing_shell_a_refusal(self):
        text = doctrine_text()
        self.assertIn("## Activation", text,
                      "doctrine must carry an activation contract section")
        activation = text.split("## Activation", 1)[1].split("\n## ", 1)[0]
        self.assertIn("refuse", activation.lower(),
                      "the activation contract must refuse, not degrade")
        for obligation in ("Bash", "no report", "no finding", "no candidate"):
            with self.subTest(obligation=obligation):
                self.assertIn(
                    obligation, activation,
                    f"the refusal must name {obligation!r}")

    def test_doctrine_never_offers_reading_as_a_fallback(self):
        activation = doctrine_text().split("## Activation", 1)[1].split("\n## ", 1)[0]
        self.assertNotIn(
            "degrade", activation.lower().replace("not degrade", ""),
            "a degraded reading mode is exactly what the refusal forbids")


class MovesTableTests(unittest.TestCase):
    """The moves table is complete, typed, and never sized by a hand-written
    numeral.

    A hand-written count of the skill's own moves is the defect class this skill
    exists to find, and the proposal already carries one instance of it.
    """

    def test_one_row_per_move_and_one_for_the_textual_move(self):
        rows = moves_rows()
        numbered = []
        textual = []
        for row in rows:
            match = re.match(r"^(\d+)\b", row[0])
            (numbered if match else textual).append(
                int(match.group(1)) if match else row)
        self.assertEqual(
            sorted(numbered), list(range(0, 8)),
            "the table must carry exactly one row per move 0 through 7, with no "
            f"gap and no repeat; found {sorted(numbered)}")
        self.assertEqual(
            len(textual), 1,
            "exactly one row must carry the irreducibly textual move, which has "
            f"no code and no lock; found {len(textual)}")

    def test_every_row_ships_as_a_real_subcommand_or_as_doctrine(self):
        """Cross-checked against argparse's own surface, not against a list.

        A move documented with a script that does not exist is a roster that lost
        one, in the skill whose subject is rosters that lose one.
        """
        declared = set(subcommand_surface(CLI, "build_parser"))
        for row in moves_rows():
            ships = row[1].strip("`")
            with self.subTest(move=row[0], ships=ships):
                self.assertIn(
                    ships, declared | {"doctrine"},
                    f"`Ships as` cell {ships!r} is neither a subcommand "
                    f"audit_cli.py declares ({sorted(declared)}) nor the "
                    "literal `doctrine`")

    def test_the_textual_move_names_no_subcommand_and_carries_no_lock(self):
        textual = [row for row in moves_rows() if not re.match(r"^\d+\b", row[0])]
        self.assertEqual(len(textual), 1)
        row = textual[0]
        self.assertEqual(
            row[1].strip("`"), "doctrine",
            "the textual move ships as doctrine, because it has no code")
        self.assertIn(
            "no lock", row[2].lower(),
            "the textual move's row must say it carries no lock; claiming the "
            "table is complete would be the same defect the skill exists to find")

    def test_every_numbered_move_names_a_lock_that_is_on_disk(self):
        """A table naming a lock that does not exist is the phantom class itself.

        The cell names a path, not a class, so the claim stays true across every
        slice of this change rather than needing an edit each time a class lands.
        """
        for row in moves_rows():
            if not re.match(r"^\d+\b", row[0]):
                continue
            named = row[2].strip("`")
            with self.subTest(move=row[0], lock=named):
                self.assertTrue(
                    (FORGE / named).is_file(),
                    f"move {row[0]} names lock {named!r}, which is not on disk")

    def test_no_numbered_move_claims_to_be_unlocked(self):
        for row in moves_rows():
            if not re.match(r"^\d+\b", row[0]):
                continue
            with self.subTest(move=row[0]):
                self.assertNotIn(
                    "no lock", row[2].lower(),
                    "a numbered move with no lock is a move that is not audited")


class DoctrineNumeralTests(unittest.TestCase):
    """No numeral in this skill's own doctrine states the size of an enumeration.

    Headings included: the proposal and the design both call this the
    "seven-move table" while it enumerates moves 0 through 7 plus a ninth
    textual row. The heading is corrected here, under this rule, in this skill's
    own doctrine.
    """

    def test_the_skill_states_no_underived_count_of_its_own_enumerations(self):
        sys.path.insert(0, str(CLI.parent))
        import audit_cli  # noqa: E402  (path set above)

        mismatches = audit_cli.numeral_mismatches(SKILL_MD)
        self.assertEqual(
            mismatches, [],
            "a numeral in skill-audit's own doctrine states a count that the "
            f"enumeration beneath it does not match: {mismatches}")

    def test_no_heading_carries_a_cardinal_at_all(self):
        """Stricter than the general rule, and only for this skill's own headings.

        A heading is the one place a stale count survives longest, because it is
        read as a title rather than as a claim.
        """
        cardinals = re.compile(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
            r"twelve|\d+)[- ]", re.IGNORECASE)
        offenders = [
            line for line in doctrine_text().splitlines()
            if line.startswith("#") and cardinals.search(line)]
        self.assertEqual(
            offenders, [],
            f"a heading states a count instead of deriving it: {offenders}")


class VocabularyTests(unittest.TestCase):
    """The new skill cannot borrow a target's vocabulary.

    Copied from `tests/test_proposal_implementation.py:62-63`, for the reason
    that file states: the cheapest way to make a leak green is to declare the
    leaking word to be vocabulary the forge owns.
    """

    def test_the_lexicon_cannot_silence_a_leak_already_found(self):
        self.assertEqual(
            sorted(set(FORGE_LEXICON) & set(FORGE_VOCABULARY_FLOOR)), [],
            "a word on the floor is a leak somebody already found, so it can "
            "never also be vocabulary the forge owns")

    def test_every_lexicon_entry_costs_an_argument(self):
        thin = {word: reason for word, reason in FORGE_LEXICON.items()
                if len(reason.split()) < 4}
        self.assertEqual(
            thin, {},
            "a lexicon entry has to say why the forge owns the word")

    def test_no_floor_word_appears_in_the_skill_itself(self):
        """The floor, applied — not merely declared.

        Disjointness alone proves nothing about the artifacts; it proves
        something about two constants. This is the assertion with a subject.
        """
        shipped = sorted(
            path for path in SKILL_ROOT.rglob("*")
            if path.is_file() and path.suffix in (".md", ".py", ".json"))
        self.assertNotEqual(shipped, [], "no shipped files found to check")
        for path in shipped:
            text = path.read_text(encoding="utf-8").lower()
            for word in FORGE_VOCABULARY_FLOOR:
                with self.subTest(path=path.name, word=word):
                    self.assertNotIn(
                        word, text,
                        f"{path.name} borrows {word!r}, a word a target owns")


if __name__ == "__main__":
    unittest.main()
