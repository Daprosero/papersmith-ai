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


def required_move_ids(rows=None) -> list[str]:
    """The move-outcome roster a report must carry, read the same way
    `check-report` reads it: one numbered row becomes its own number, the one
    unnumbered row becomes the literal `textual`. Never a list held in this
    file — that would restate the same roster `move_roster` derives.
    """
    ids = []
    for row in rows if rows is not None else moves_rows():
        match = re.match(r"^(\d+)\b", row[0])
        ids.append(match.group(1) if match else "textual")
    return ids


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
        #
        # `hashlib` and `fnmatch` arrived with `tree_digest`: a sha256 per file
        # and a glob-pattern exclude, both stdlib and both load-bearing for the
        # walk this skill is allowed exactly one of. `shutil` arrived with the
        # box lifecycle: `shutil.rmtree` removes a box in one call, so the
        # walk-restriction lock never has to carve out an exception for a
        # hand-rolled recursive delete written beside `tree_digest`.
        permitted = {"__future__", "argparse", "fnmatch", "hashlib", "json",
                     "pathlib", "re", "shutil", "subprocess", "sys"}
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
            sorted(numbered), list(range(0, 9)),
            "the table must carry exactly one row per move 0 through 8, with no "
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


class SuiteIntegrityTests(unittest.TestCase):
    """This one file cannot silently disable its own tests.

    A duplicate top-level class name makes Python bind the name to whichever
    definition runs last; every earlier class's tests vanish with no error
    from `unittest`'s own discovery, which only ever sees the surviving name.
    A duplicate `test_` method name inside one class has the same silent
    effect, one method at a time. Scope: this file, `tests/test_skill_audit.py`,
    and only this file -- it says nothing about any other test module in this
    repository.
    """

    def _module_tree(self):
        return ast.parse(Path(__file__).read_text(encoding="utf-8"))

    def test_no_duplicate_top_level_class_name(self):
        names = [node.name for node in self._module_tree().body
                if isinstance(node, ast.ClassDef)]
        seen = set()
        duplicates = sorted({name for name in names
                             if name in seen or seen.add(name)})
        self.assertEqual(
            duplicates, [],
            f"a top-level class name repeats in {Path(__file__).name}, "
            f"silently discarding an earlier class's tests: {duplicates}")

    def test_no_duplicate_test_method_name_within_a_class(self):
        offenders = []
        for node in self._module_tree().body:
            if not isinstance(node, ast.ClassDef):
                continue
            method_names = [item.name for item in node.body
                            if isinstance(item, ast.FunctionDef)
                            and item.name.startswith("test_")]
            seen = set()
            for name in method_names:
                if name in seen:
                    offenders.append(f"{node.name}.{name}")
                seen.add(name)
        self.assertEqual(
            offenders, [],
            f"a test_ method name repeats within one class, and the later "
            f"definition silently wins over the earlier: {sorted(offenders)}")


if __name__ == "__main__":
    unittest.main()


# ==========================================================================
# Slice 2 — `roster`: the code side is a process, the documented side is a
# table, and inability to look never wears the same exit code as absence of
# findings.
# ==========================================================================

PD = FORGE / ".claude" / "skills" / "proposal-deliberation"
PD_SPEC = PROBES / "proposal-deliberation.accepted-operations.json"
SELF_SPEC = PROBES / "skill-audit.subcommands.json"

#: Boxes live here and never in the system temporary directory. `implementations`
#: is gitignored, which is exactly why their removal is proven by listing content
#: rather than by `git status` — porcelain over an ignored tree is empty by
#: construction and would report a box that is still sitting there as cleaned.
BOXES = FORGE / "implementations"

#: The producer, declared. The documented side of any comparison may not name
#: these: not call them, not import them, not borrow a constant from them. A
#: declared set rather than an inferred one, because the comparison's domain has
#: to be closed before the comparison runs.
PRODUCER_NAMES = ("subprocess", "probe_code_side")

#: The functions that make up the documented side of every comparison this tool
#: performs. The gate is applied to each.
DOCTRINE_DERIVATION = ("doctrine_side", "markdown_table_rows",
                       "numeral_mismatches", "bullet_run_length",
                       "table_run_length", "enumeration_after",
                       "is_size_claim", "restatement_of")


def audit_cli_module():
    sys.path.insert(0, str(CLI.parent))
    import audit_cli
    return audit_cli


def roster_json(spec, subject, repo=FORGE, extra=()):
    """Drive `roster` as a process and parse what it wrote to stdout."""
    result = run_cli("roster", "--subject", str(subject),
                     "--probe-spec", str(spec), "--repo-root", str(repo), *extra)
    try:
        return result, json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"roster exited {result.returncode} without JSON on stdout.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}")


def function_source(path, name):
    """The exact bytes of one function definition, for byte-identity checks."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = text.splitlines(keepends=True)
            return "".join(lines[node.lineno - 1:node.end_lineno])
    raise AssertionError(f"{path.name} defines no {name}")


class BoxMixin:
    """A throwaway directory, contained and proven gone.

    Under `implementations/_<name>`, never `/tmp`, and its removal is confirmed
    by asking the filesystem what is there rather than by asking version control,
    which cannot see an ignored tree at all.
    """

    def make_box(self, name):
        box = BOXES / f"_skill_audit_{name}"
        self.assertEqual(
            box.parent, BOXES,
            "a box must sit directly under implementations/, never elsewhere")
        if box.exists():
            self._erase(box)
        box.mkdir(parents=True)
        self.addCleanup(self._prove_erased, box)
        return box

    def _erase(self, box):
        for path in sorted(box.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        box.rmdir()

    def _prove_erased(self, box):
        if box.exists():
            self._erase(box)
        remaining = sorted(str(p) for p in BOXES.glob("_skill_audit_*"))
        self.assertEqual(
            remaining, [],
            "a box survived cleanup; its absence is proven by listing content, "
            "never by `git status`, which is empty over an ignored tree")

    def write(self, box, relative, text):
        path = box / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def recipe(self, box, **fields):
        spec = box / "recipe.json"
        spec.write_text(json.dumps(fields, indent=2), encoding="utf-8")
        return spec

    def echo_probe(self, box, members, name="subject.py"):
        """A subject that refuses a nonce and names what it would accept.

        A real process, driven with real argv. A double that replaced a function
        wholesale could not hold any claim about the process it stood in for.
        """
        self.write(box, name, "import sys\n"
                              "print('REFUSED: ' + sys.argv[1] + ' is not one of '\n"
                              "      + ', '.join(sys.argv[2:]))\n"
                              "sys.exit(1)\n")
        return ["python3", name, "__AUDIT_NONCE__", *members]


class RosterExitCodeTests(BoxMixin, unittest.TestCase):
    """D3: inability to look must never share an exit code with no findings.

    An empty code side yields `unregistered` empty and `phantom` holding every
    documented row — a broken probe wearing a finding's clothes, and the fourth
    failure mode in its most dangerous form.
    """

    def test_a_verdict_with_findings_still_exits_zero(self):
        box = self.make_box("exit_findings")
        argv = self.echo_probe(box, ["ALPHA", "BETA"])
        self.write(box, "DOC.md",
                   "| Op | Use |\n| --- | --- |\n| `ALPHA` | a |\n| `GHOST` | b |\n")
        spec = self.recipe(
            box, surface="s", probe="refusal", argv=argv, cwd=".",
            stream="stdout", exit=1,
            extract=r"is not one of (?P<roster>.+)$", split=", ",
            doctrineSites=[{"path": "DOC.md", "table": "| Op | Use |",
                            "column": 0}])
        result, payload = roster_json(spec, box)
        self.assertEqual(result.returncode, 0,
                         "findings are a verdict, and a verdict exits 0")
        self.assertEqual(payload["phantom"], ["GHOST"])
        self.assertEqual(payload["unregistered"], ["BETA"])

    def test_an_extraction_matching_nothing_exits_two(self):
        box = self.make_box("exit_nomatch")
        argv = self.echo_probe(box, ["ALPHA"])
        spec = self.recipe(
            box, surface="s", probe="refusal", argv=argv, cwd=".",
            stream="stdout", exit=1,
            extract=r"this phrase is nowhere (?P<roster>.+)$", split=", ",
            doctrineSites=[])
        result, payload = roster_json(spec, box)
        self.assertEqual(result.returncode, 2,
                         "an extraction that matched nothing is an inability "
                         "to look, not an empty roster")
        self.assertEqual(payload["status"], "unprobeable")
        self.assertNotIn("code", payload,
                         "no code side may be reported when none was derived")

    def test_the_two_exit_codes_are_distinguishable(self):
        box = self.make_box("exit_distinct")
        argv = self.echo_probe(box, ["ALPHA"])
        good = self.recipe(
            box, surface="s", probe="refusal", argv=argv, cwd=".",
            stream="stdout", exit=1,
            extract=r"is not one of (?P<roster>.+)$", split=", ",
            doctrineSites=[])
        looked = run_cli("roster", "--subject", str(box),
                         "--probe-spec", str(good), "--repo-root", str(FORGE))
        blind = run_cli("roster", "--subject", str(box),
                        "--probe-spec", str(box / "absent.json"),
                        "--repo-root", str(FORGE))
        self.assertNotEqual(
            looked.returncode, blind.returncode,
            "looking and being unable to look must not share an exit code")
        self.assertEqual((looked.returncode, blind.returncode), (0, 2))


class RefusalProbeTests(unittest.TestCase):
    """Move 2, against the live subject on disk.

    The subject is driven as a subprocess with a token it cannot accept, and its
    own refusal is the roster. No source of the subject is parsed, so there is no
    second parser to drift from the first.
    """

    def test_the_refusal_yields_the_accepted_set(self):
        result, payload = roster_json(PD_SPEC, PD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            len(payload["code"]), 9,
            f"the running host names its own accepted set: {payload['code']}")
        for name in payload["code"]:
            with self.subTest(name=name):
                self.assertRegex(name, r"^[A-Z][A-Z_]+$")

    def test_no_operation_name_appears_as_a_literal_in_the_auditor(self):
        """The auditor restates nothing it derives.

        The needles come from the executed probe, never from a list written
        here, so this cannot pass by agreeing with a stale copy of the set.
        """
        _, payload = roster_json(PD_SPEC, PD)
        auditor = sorted(path for path in SKILL_ROOT.rglob("*")
                         if path.is_file())
        auditor.append(Path(__file__))
        for path in auditor:
            text = path.read_text(encoding="utf-8")
            for name in payload["code"]:
                with self.subTest(path=path.name, name=name):
                    self.assertNotIn(
                        name, text,
                        f"{path.name} restates {name!r}; a roster written down "
                        "is a roster that drifts")

    def test_the_probe_writes_nothing_into_the_subject(self):
        """`validateRequest` is `run()`'s first statement, so the refusal
        precedes every write. Claimed by the design; measured here."""
        before = {p: p.stat().st_mtime_ns for p in PD.rglob("*") if p.is_file()}
        roster_json(PD_SPEC, PD)
        after = {p: p.stat().st_mtime_ns for p in PD.rglob("*") if p.is_file()}
        self.assertEqual(before, after,
                         "the probe touched the subject it was auditing")


class TokenPresenceTests(BoxMixin, unittest.TestCase):
    """The guard fires when the token is present, not when it is absent.

    A probe that omits the key entirely produces no refusal at all, and the
    honest report of that is "the probe yielded nothing" — never an accepted set
    that happens to be empty.
    """

    def test_a_probe_that_produces_no_refusal_yields_nothing(self):
        box = self.make_box("token_absent")
        self.write(box, "quiet.py", "import sys\nsys.exit(0)\n")
        spec = self.recipe(
            box, surface="s", probe="refusal",
            argv=["python3", "quiet.py"], cwd=".", stream="stdout", exit=0,
            extract=r"is not one of (?P<roster>.+)$", split=", ",
            doctrineSites=[])
        result, payload = roster_json(spec, box)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "unprobeable")
        self.assertIn("matched nothing", payload["error"])

    def test_the_live_host_is_silent_when_the_key_is_omitted(self):
        """Measured against the real subject, per `cli.mjs:319`: the guard reads
        `operation !== undefined && ...`, so an omitted key is not refused."""
        recipe = json.loads(PD_SPEC.read_text(encoding="utf-8"))
        argv = list(recipe["argv"])
        argv[-1] = '{"instruction":"probe"}'
        completed = subprocess.run(argv, cwd=str(PD), shell=False,
                                   capture_output=True, text=True, timeout=60)
        self.assertNotIn(
            "is not one of", completed.stdout + completed.stderr,
            "omitting the key must not produce a refusal; a probe built on "
            "token-absence would recover no roster at all")


class SelfAuditSubcommandRosterTests(unittest.TestCase):
    """The auditor's own subcommand surface, taken from argparse's refusal.

    Move 0 pointed back at the tool. Nothing else in this repository reads the
    documented side of this surface, so without it a subparser could ship with
    no row and a row could outlive its subparser.
    """

    def test_the_subcommand_roster_reports_three_sets_and_no_boolean(self):
        result, payload = roster_json(SELF_SPEC, SKILL_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        for key in ("code", "doctrine", "unregistered", "phantom",
                    "duplicated", "numeralMismatch", "notes"):
            with self.subTest(key=key):
                self.assertIn(key, payload)
        self.assertEqual(payload["unregistered"], [])
        self.assertEqual(payload["phantom"], [])
        self.assertEqual(sorted(payload["code"]),
                         ["check-report", "roster", "structure", "walkthrough"])

    def test_the_roster_comes_from_argparse_and_not_from_a_list(self):
        _, payload = roster_json(SELF_SPEC, SKILL_ROOT)
        declared = sorted(subcommand_surface(CLI, "build_parser"))
        self.assertEqual(sorted(payload["code"]), declared,
                         "the executed refusal and the parser must agree")


class ClosureClaimTests(BoxMixin, unittest.TestCase):
    """D2: a documented table is a roster site only if it claims closure, and
    the claim is checked against disk.

    Without this the auditor's first output on its first subject would be a
    screenful of confident nonsense: `## Other engine operations` is a complement
    set, and diffing it against the full runtime roster invents a finding for
    every operation it deliberately omits.
    """

    def _complement_box(self, name, heading):
        box = self.make_box(name)
        argv = self.echo_probe(box, ["ALPHA", "BETA", "GAMMA", "DELTA"])
        self.write(box, "DOC.md",
                   f"{heading}\n\n| Op | Use |\n| --- | --- |\n"
                   "| `ALPHA` | a |\n| `BETA` | b |\n")
        return box, argv

    def test_an_honoured_complement_claim_invents_no_unregistered_rows(self):
        box, argv = self._complement_box("scope_ok", "## Other engine operations")
        spec = self.recipe(
            box, surface="s", probe="refusal", argv=argv, cwd=".",
            stream="stdout", exit=1,
            extract=r"is not one of (?P<roster>.+)$", split=", ",
            doctrineSites=[{"path": "DOC.md", "table": "| Op | Use |",
                            "column": 0, "scope": "complement",
                            "headingVerbatim": "## Other engine operations"}])
        result, payload = roster_json(spec, box)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            payload["unregistered"], [],
            "a complement table omits members on purpose; calling those "
            "omissions unregistered is the auditor inventing findings")
        self.assertEqual(payload["phantom"], [],
                         "every complement row is really accepted")

    def test_a_scope_claim_whose_heading_is_not_on_disk_is_refused(self):
        box, argv = self._complement_box("scope_bad", "## Engine operations")
        spec = self.recipe(
            box, surface="s", probe="refusal", argv=argv, cwd=".",
            stream="stdout", exit=1,
            extract=r"is not one of (?P<roster>.+)$", split=", ",
            doctrineSites=[{"path": "DOC.md", "table": "| Op | Use |",
                            "column": 0, "scope": "complement",
                            "headingVerbatim": "## Other engine operations"}])
        result, payload = roster_json(spec, box)
        self.assertEqual(result.returncode, 0)
        kinds = [note["kind"] for note in payload["notes"]]
        self.assertIn(
            "heading-not-found", kinds,
            "the editorial judgement is falsifiable: rename the heading and "
            f"the claim stops being honoured. notes={payload['notes']}")


class NoClosedRosterTests(unittest.TestCase):
    """"There is no closed roster here" is a result, not an error.

    On the first subject all of its documented sites emit it: SKILL.md carries a
    complement, `references/usage.md` states the set in prose, and the surface
    test restates it as a JavaScript array. That is the finding the proposal
    predicted survives.
    """

    def test_every_documented_site_of_the_first_subject_reports_it(self):
        result, payload = roster_json(PD_SPEC, PD)
        self.assertEqual(result.returncode, 0,
                         "no-closed-roster is a verdict, not a failure")
        notes = [n for n in payload["notes"] if n["kind"] == "no-closed-roster"]
        self.assertEqual(
            len(notes), 3,
            f"expected all three documented sites to report it: {payload['notes']}")
        for note in notes:
            with self.subTest(path=note["path"]):
                self.assertRegex(
                    note["searched"], r".+:\d+-\d+$",
                    "the result must name the range that was searched")

    def test_a_prose_site_reports_it_against_a_planted_fixture(self):
        """The needle is proven absent from the fixture's own name first.

        One lock in this repository's history went green because the string it
        searched for was sitting in the filename it searched. The precondition
        is asserted before the assertion, and the ordering is itself enforced by
        `PlantedFixtureDisciplineTests`.
        """
        box = BOXES / "_skill_audit_planted_prose"
        try:
            box.mkdir(parents=True, exist_ok=True)
            needle = "no-closed-roster"
            fixture = box / "site.md"
            self.assertNotIn(
                needle, str(fixture),
                "the fixture's own path carries the needle, so a match would "
                "prove nothing about what the tool produced")
            fixture.write_text("The set is ALPHA, BETA and GAMMA, in prose.\n",
                               encoding="utf-8")
            (box / "subject.py").write_text(
                "import sys\n"
                "print('is not one of ' + ', '.join(['ALPHA', 'BETA']))\n"
                "sys.exit(1)\n", encoding="utf-8")
            (box / "recipe.json").write_text(json.dumps({
                "surface": "s", "probe": "refusal",
                "argv": ["python3", "subject.py"], "cwd": ".",
                "stream": "stdout", "exit": 1,
                "extract": r"is not one of (?P<roster>.+)$", "split": ", ",
                "doctrineSites": [{"path": "site.md", "table": None}]}),
                encoding="utf-8")
            _, payload = roster_json(box / "recipe.json", box)
            self.assertIn(needle, [note["kind"] for note in payload["notes"]])
        finally:
            for path in sorted(box.rglob("*"), reverse=True):
                path.unlink()
            box.rmdir()
            self.assertFalse(box.exists(), "the box survived its own cleanup")

    def test_the_surface_is_not_reported_clean(self):
        _, payload = roster_json(PD_SPEC, PD)
        self.assertNotEqual(
            payload["notes"], [],
            "a surface with no closed roster anywhere is not a clean surface")
        self.assertEqual(
            payload["comparison"], "not-run",
            "with no closed documented side there is nothing to compare, and "
            "reporting nine unregistered rows would be the same invented "
            "finding the complement check exists to prevent")


class NoDerivationTests(BoxMixin, unittest.TestCase):
    """A surface with neither probe is reported, never passed over."""

    def test_a_surface_with_no_probe_is_a_first_class_result(self):
        box = self.make_box("no_derivation")
        spec = self.recipe(box, surface="s", probe="none", doctrineSites=[])
        result, payload = roster_json(spec, box)
        self.assertEqual(result.returncode, 0)
        self.assertIn("no derivation available for this surface",
                      [note["kind"] for note in payload["notes"]])
        self.assertEqual(payload["comparison"], "not-run")


class SoundnessGateTests(unittest.TestCase):
    """Condition 1, mechanised: the documented side never names the producer.

    Forbidding only a call for *contents* is not enough. The precedent this is
    modelled on derives file contents from doctrine but takes its element set
    from the producer — `tests/test_proposal_implementation.py:267` is
    `for gap in impl.scaffold_gaps(box, name):`, a producer call deciding which
    paths exist, under a docstring at `:240` claiming a doctrine-faithful target.
    A comparison built that way cannot see an element missing from both sides,
    which is the one defect the comparison exists to catch. So any reference of
    any kind is refused: a call, an import, or a borrowed constant.
    """

    def _references(self, name):
        tree = ast.parse(CLI.read_text(encoding="utf-8"))
        definition = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == name), None)
        self.assertIsNotNone(definition, f"audit_cli.py defines no {name}")
        found = set()
        for node in ast.walk(definition):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
                if isinstance(node.value, ast.Name):
                    found.add(node.value.id)
            elif isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
                found.update(a.name for a in node.names)
        return found

    def test_no_doctrine_derivation_names_the_producer(self):
        for function in DOCTRINE_DERIVATION:
            referenced = self._references(function)
            for producer in PRODUCER_NAMES:
                with self.subTest(function=function, producer=producer):
                    self.assertNotIn(
                        producer, referenced,
                        f"{function} names {producer!r}; the documented side "
                        "may not reach for the producer, not even to decide "
                        "which elements to build")

    def test_the_precedent_this_gate_is_modelled_on_would_fail_it(self):
        """The gate has a subject, and the subject is a real function.

        A gate proven only against a fixture is a gate that has never met the
        shape it was written for.
        """
        source = function_source(ORIGINAL_HELPERS, "doctrine_scaffold")
        self.assertIn(
            "impl.scaffold_gaps", source,
            "the precedent takes its element set from the producer, which is "
            "the exact shape this gate refuses")


class ThreeSetsTests(BoxMixin, unittest.TestCase):
    """Condition 3: three sets, never a boolean.

    They are different defects with different remedies, and each is proven
    non-empty on its own rather than by one fixture that happens to fire all of
    them at once.
    """

    def _run(self, name, code_members, doc_members):
        box = self.make_box(name)
        argv = self.echo_probe(box, code_members)
        rows = "".join(f"| `{m}` | x |\n" for m in doc_members)
        self.write(box, "DOC.md", f"| Op | Use |\n| --- | --- |\n{rows}")
        spec = self.recipe(
            box, surface="s", probe="refusal", argv=argv, cwd=".",
            stream="stdout", exit=1,
            extract=r"is not one of (?P<roster>.+)$", split=", ",
            doctrineSites=[{"path": "DOC.md", "table": "| Op | Use |",
                            "column": 0}])
        return roster_json(spec, box)[1]

    def test_unregistered_populates_alone(self):
        payload = self._run("set_unreg", ["ALPHA", "BETA"], ["ALPHA"])
        self.assertEqual(payload["unregistered"], ["BETA"])
        self.assertEqual(payload["phantom"], [])

    def test_phantom_populates_alone(self):
        payload = self._run("set_phantom", ["ALPHA"], ["ALPHA", "GHOST"])
        self.assertEqual(payload["phantom"], ["GHOST"])
        self.assertEqual(payload["unregistered"], [])

    def test_the_verdict_is_never_a_boolean(self):
        payload = self._run("set_shape", ["ALPHA"], ["ALPHA"])
        for absent in ("pass", "ok", "valid", "clean"):
            with self.subTest(key=absent):
                self.assertNotIn(absent, payload)


class DuplicatedTests(unittest.TestCase):
    """A set restated by hand is reported even when every restatement agrees.

    Agreement today is not derivation. This repository's own history records a
    stale operation name that survived precisely because every restatement of it
    agreed with the stale one.
    """

    def test_the_first_subject_has_more_than_one_hand_restatement(self):
        _, payload = roster_json(PD_SPEC, PD)
        self.assertGreaterEqual(
            len(payload["duplicated"]), 2,
            f"a set restated in one place is not duplicated: {payload['duplicated']}")
        for site in payload["duplicated"]:
            with self.subTest(path=site["path"]):
                self.assertGreaterEqual(site["line"], 1)
                self.assertNotEqual(site["members"], [])

    def test_agreement_does_not_excuse_a_restatement(self):
        _, payload = roster_json(PD_SPEC, PD)
        restated = {m for site in payload["duplicated"] for m in site["members"]}
        self.assertTrue(
            restated <= set(payload["code"]),
            "every restatement here agrees with the running code, and every "
            "one of them is still reported")


class NumeralCheckTests(BoxMixin, unittest.TestCase):
    """A numeral above a list, held to the list.

    Hedged numerals are excluded on measured need: a neighbouring engine's own
    header says "~63 TS files" and "roughly 0.72s" two lines apart, and a check
    firing on those is noise. Noise gets exempted until the check means nothing.
    """

    def test_a_hedged_numeral_is_not_a_claim(self):
        box = self.make_box("numeral_hedged")
        path = self.write(box, "hedged.md",
                          "This host compiles the engine's ~63 TS files, at\n"
                          "roughly 0.72s per process. There are about three:\n\n"
                          "- alpha\n- beta\n- gamma\n- delta\n")
        self.assertEqual(
            audit_cli_module().numeral_mismatches(path), [],
            "a hedged numeral states an estimate, not a size")

    def test_an_unhedged_numeral_above_a_longer_list_is_a_finding(self):
        box = self.make_box("numeral_plain")
        path = self.write(box, "plain.md",
                          "The modules are these three:\n\n"
                          "- alpha\n- beta\n- gamma\n- delta\n")
        found = audit_cli_module().numeral_mismatches(path)
        self.assertEqual(len(found), 1, found)
        self.assertEqual((found[0]["stated"], found[0]["counted"]), (3, 4))

    def test_the_live_target_names_both_halves_at_file_and_line(self):
        """Move 2, on a real document: a skill that says three above a list of
        more than three, in the repository as it stands."""
        found = audit_cli_module().numeral_mismatches(
            FORGE / ".claude" / "skills" / "remote-execution" / "SKILL.md")
        self.assertEqual(len(found), 1, found)
        finding = found[0]
        self.assertEqual(finding["numeralLine"], 19)
        self.assertEqual(finding["stated"], 3)
        self.assertGreater(
            finding["counted"], finding["stated"],
            "the list beneath the numeral is longer than the numeral claims")
        self.assertGreater(finding["enumerationLine"], finding["numeralLine"],
                           "a finding names both halves, each at its own line")

    def test_a_continuation_line_does_not_end_the_list_it_belongs_to(self):
        """The reason the live count is what it is, isolated.

        A long indented item hides the next bullet below the fold, and an
        enumeration counted by eye stops at the fold. This is the difference
        between the count a reader reports and the count a machine reports.
        """
        box = self.make_box("numeral_fold")
        path = self.write(box, "fold.md",
                          "The parts are these two:\n\n"
                          "- alpha\n" + "  continued\n" * 40 + "\n- beta\n\n- gamma\n")
        found = audit_cli_module().numeral_mismatches(path)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["counted"], 3)


class SubprocessCompositionTests(BoxMixin, unittest.TestCase):
    """The one applicable row of the threat matrix.

    `roster` executes argv a recipe supplies, so the recipe is the boundary.
    """

    def test_a_cwd_escaping_the_subject_is_refused(self):
        box = self.make_box("threat_cwd")
        argv = self.echo_probe(box, ["ALPHA"])
        spec = self.recipe(
            box, surface="s", probe="refusal", argv=argv, cwd="../..",
            stream="stdout", exit=1,
            extract=r"is not one of (?P<roster>.+)$", split=", ",
            doctrineSites=[])
        result, payload = roster_json(spec, box)
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside --subject", payload["error"])

    def test_a_metacharacter_crosses_as_one_literal_argument(self):
        box = self.make_box("threat_shell")
        payload_arg = "ALPHA; touch pwned"
        self.write(box, "subject.py",
                   "import sys\n"
                   "print('is not one of ' + '|'.join(sys.argv[1:]))\n"
                   "sys.exit(1)\n")
        spec = self.recipe(
            box, surface="s", probe="refusal",
            argv=["python3", "subject.py", payload_arg], cwd=".",
            stream="stdout", exit=1,
            extract=r"is not one of (?P<roster>.+)$", split="|",
            doctrineSites=[])
        result, parsed = roster_json(spec, box)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            parsed["code"], [payload_arg],
            "argv is a list and there is no shell in the path, so a semicolon "
            "is a character in an argument and never a command separator")
        self.assertFalse((box / "pwned").exists(),
                         "the metacharacter was interpreted")

    def test_a_hanging_subject_times_out_into_exit_two(self):
        box = self.make_box("threat_hang")
        self.write(box, "hang.py", "import time\ntime.sleep(120)\n")
        spec = self.recipe(
            box, surface="s", probe="refusal",
            argv=["python3", "hang.py"], cwd=".", stream="stdout", exit=1,
            extract=r"is not one of (?P<roster>.+)$", split=", ",
            doctrineSites=[])
        result, payload = roster_json(spec, box, extra=("--timeout", "2"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("did not answer", payload["error"])


class PlantedFixtureDisciplineTests(unittest.TestCase):
    """A lock must not pass off its own fixture's name.

    One in this repository's history went green because the needle it searched
    for was sitting in the fixture's filename. Every lock here that matches a
    needle against generated output is named `..._against_a_planted_fixture`, and
    this meta-lock reads their syntax trees to confirm the precondition is
    asserted first.
    """

    def _planted(self):
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        return [node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name.endswith("_against_a_planted_fixture")]

    def test_there_is_at_least_one_planted_fixture_lock_to_govern(self):
        self.assertNotEqual(
            self._planted(), [],
            "a discipline with no subject is a rule nobody keeps")

    def test_every_planted_lock_clears_its_fixture_name_first(self):
        for definition in self._planted():
            calls = [node.func.attr for node in ast.walk(definition)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute)
                     and node.func.attr in ("assertIn", "assertNotIn")]
            with self.subTest(lock=definition.name):
                self.assertNotEqual(calls, [], "no membership assertion found")
                self.assertEqual(
                    calls[0], "assertNotIn",
                    f"{definition.name} looks for its needle before proving the "
                    "needle is absent from the fixture's own name")


class ReachabilityTests(BoxMixin, unittest.TestCase):
    """A fixture that cannot reach the guarded branch fails as unreachable.

    An assertion over a branch the fixture never enters is unfalsifiable, and an
    unfalsifiable assertion passes.
    """

    def assert_branch_reached(self, payload, kind):
        kinds = [note["kind"] for note in payload["notes"]]
        if kind not in kinds:
            self.fail(f"unreachable: the fixture never entered the {kind!r} "
                      f"branch, so any assertion about it is unfalsifiable. "
                      f"Branches actually entered: {kinds}")

    def test_the_guarded_branch_is_proven_entered_before_it_is_asserted_on(self):
        _, payload = roster_json(PD_SPEC, PD)
        self.assert_branch_reached(payload, "no-closed-roster")

    def test_a_fixture_that_misses_the_branch_fails_rather_than_passes(self):
        with self.assertRaises(self.failureException) as raised:
            self.assert_branch_reached({"notes": []}, "no-closed-roster")
        self.assertIn("unreachable", str(raised.exception))


class CopiedHelperFidelityTests(unittest.TestCase):
    """The copies are byte-identical to their originals.

    Copied and not shared: sharing means editing a seventy-five-class suite from
    inside a change about a different skill. The price of copying is drift, and
    this is where drift is paid for — as a red, not as a later discovery.
    """

    COPIES = {
        "markdown_table_rows": (Path(__file__), CLI),
        "returned_keys": (Path(__file__),),
        "dict_literal_keys": (Path(__file__),),
        "subcommand_surface": (Path(__file__),),
    }

    def test_every_copy_is_byte_identical_to_its_original(self):
        for helper, locations in self.COPIES.items():
            original = function_source(ORIGINAL_HELPERS, helper)
            for path in locations:
                with self.subTest(helper=helper, path=path.name):
                    self.assertEqual(
                        function_source(path, helper), original,
                        f"{helper} has drifted between "
                        f"{ORIGINAL_HELPERS.name} and {path.name}; both "
                        "locations must be edited together")


# ==========================================================================
# Slice 4 — `check-report`: the report shape is enforced by a process, not by
# the paragraph that describes it.
# ==========================================================================

#: The digest `VALID_REPORT`'s `## Frozen` names, and the one every finding
#: below cites. Not re-derived from any real subject -- this fixture is never
#: driven with `--subject`, so only finding-vs-`## Frozen` consistency is
#: exercised, and any two agreeing 64-hex strings would do.
VALID_REPORT_DIGEST = "sha256:0a9752e7848b79dee5a2b48d478a7b7bad19d7db119a54d7bb034f4a4e3191be"

VALID_REPORT = f"""# Audit: a subject, one surface

## Frozen

- Digest: {VALID_REPORT_DIGEST}
- Subject: a subject, one surface
- Exclude: (none)

## Move outcomes

- Move: 0: ran
- Move: 1: skipped: no from-zero build declared for this surface
- Move: 2: skipped: not driven from disk in this pass
- Move: 3: skipped: no external boundary crossed in this pass
- Move: 4: skipped: no installed dependency read in this pass
- Move: 5: skipped: no live probe attempted, no consent sought
- Move: 6: skipped: no lock inverted in this pass
- Move: 7: skipped: single-harness count only, not compared
- Move: 8: skipped: no ordered user-mode flow driven in this pass
- Move: textual: ran

## Ranked findings

### F1. A set restated in more places than it is derived

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Digest: {VALID_REPORT_DIGEST}
- Code side: `engine/host.mjs:320`
- Doctrine side: `SKILL.md:243`
- Detail: the running host names more members than the table does.

## Not adjudicable

### F2. A declared value with no consumer anywhere

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: not adjudicable
- Digest: {VALID_REPORT_DIGEST}
- Code side: `engine/metrics.ts:3`
- Doctrine side: `engine/host.mjs:319`
- Detail: build-or-delete, and the choice costs something either way.

## Clean, stated as results

- The refusal path writes nothing - enumerated by driving the host from an
  empty directory, observed that directory empty before and after.

## Unchecked

- The error-code surface - never enumerated, and not claimed clean.

## Falsifier

Rename the quoted heading and the scope claim stops being honoured.

## Changed-line forecast

| Remedy | Changed lines |
| --- | --- |
| One table, one derivation | 40 |

## Repair units

| Unit | Findings | Changed lines |
| --- | --- | --- |
| One table, one derivation | F1 | 40 |
| Build or delete the unread declared value | F2 | 0 |
"""


class ReportShapeTests(BoxMixin, unittest.TestCase):
    """A shape enforced only by prose is a hand-maintained roster.

    Which is the class this skill exists to find, so the shape is enforced by a
    process that exits non-zero.
    """

    def check(self, text, name="report.md"):
        box = getattr(self, "_box", None) or self.make_box("report")
        self._box = box
        path = self.write(box, name, text)
        result = run_cli("check-report", str(path))
        return result, json.loads(result.stdout)

    def test_a_complete_report_is_accepted(self):
        result, payload = self.check(VALID_REPORT)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["violations"], [])

    def test_an_unreadable_report_is_exit_two_and_not_exit_one(self):
        result = run_cli("check-report", str(BOXES / "_absent" / "nope.md"))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2, payload)
        self.assertNotEqual(
            result.returncode, 1,
            "being unable to read a report is not the same as reading an "
            "invalid one, and the two must not share an exit code")

    def test_every_required_item_is_rejected_when_absent(self):
        removals = {
            "ranked-findings": ("## Ranked findings", "## Nothing here"),
            "clean-section": ("## Clean, stated as results", "## Tidy"),
            "unchecked-section": ("## Unchecked", "## Unlooked"),
            "falsifier": ("## Falsifier", "## Postscript"),
            "changed-line-forecast": ("## Changed-line forecast", "## Notes"),
            "move-number": ("- Move: 0\n- Evidence: CONFIRMED", "- Evidence: CONFIRMED"),
            "adjudication": ("- Adjudication: doctrine wrong\n", ""),
            "move-outcomes": ("## Move outcomes", "## Move states"),
            "repair-units": ("## Repair units", "## Units of nothing"),
            "frozen": ("## Frozen", "## Solidified"),
        }
        for item, (needle, replacement) in removals.items():
            with self.subTest(item=item):
                result, payload = self.check(
                    VALID_REPORT.replace(needle, replacement, 1),
                    name=f"missing-{item}.md")
                self.assertEqual(result.returncode, 1, payload)
                self.assertIn(
                    item, [v["item"] for v in payload["violations"]],
                    f"removing {item} must name {item}: {payload['violations']}")

    def test_a_finding_naming_one_half_is_a_candidate_not_a_finding(self):
        broken = VALID_REPORT.replace("- Doctrine side: `SKILL.md:243`\n", "", 1)
        result, payload = self.check(broken, name="one-half.md")
        self.assertEqual(result.returncode, 1)
        violation = next(v for v in payload["violations"]
                         if v["item"] == "ranked-findings")
        self.assertIn("candidate", violation["detail"])
        self.assertIn("F1", violation["where"])

    def test_a_marker_free_finding_is_rejected_against_a_planted_fixture(self):
        needle = "CONFIRMED by execution"
        name = "planted-no-marker.md"
        self.assertNotIn(
            needle, name,
            "the fixture's own name carries the needle, so a match would prove "
            "nothing about what the tool read")
        broken = VALID_REPORT.replace("- Evidence: CONFIRMED by execution\n", "", 1)
        result, payload = self.check(broken, name=name)
        self.assertEqual(result.returncode, 1)
        self.assertIn("evidence-marker",
                      [v["item"] for v in payload["violations"]])

    def test_an_entirely_read_only_report_must_say_so_first(self):
        readonly = VALID_REPORT.replace("CONFIRMED by execution", "read-only")
        result, payload = self.check(readonly, name="readonly.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertIn("evidence-marker",
                      [v["item"] for v in payload["violations"]])
        declared = readonly.replace(
            "# Audit: a subject, one surface\n",
            "# Audit: a subject, one surface\n\n"
            "No finding in this report is CONFIRMED by execution.\n", 1)
        result, payload = self.check(declared, name="readonly-declared.md")
        self.assertEqual(result.returncode, 0, payload)


class ForbiddenSupportTests(BoxMixin, unittest.TestCase):
    """Four things a report may never lean on, each of which cost a phase here."""

    def check(self, text, name):
        box = getattr(self, "_box", None) or self.make_box("support")
        self._box = box
        result = run_cli("check-report", str(self.write(box, name, text)))
        return result, json.loads(result.stdout)

    def _reject(self, item, line, name):
        text = VALID_REPORT.replace(
            "## Falsifier", f"{line}\n\n## Falsifier", 1)
        result, payload = self.check(text, name)
        self.assertEqual(result.returncode, 1, payload)
        violation = next(
            (v for v in payload["violations"] if v["item"] == item), None)
        self.assertIsNotNone(
            violation, f"expected {item}: {payload['violations']}")
        return violation

    def test_a_green_suite_is_never_evidence(self):
        self._reject("green-suite",
                     "- The surface is sound - the suite passed.", "green.md")

    def test_containment_by_porcelain_is_rejected_and_names_the_manifest(self):
        violation = self._reject(
            "porcelain-containment",
            "- The target was untouched - `git status --porcelain` was empty.",
            "porcelain.md")
        self.assertIn(
            "manifest", violation["detail"],
            "the rejection must name the evidence that would work, because "
            "porcelain over an ignored tree is empty by construction")

    def test_a_live_request_is_not_a_receipt(self):
        self._reject(
            "request-as-receipt",
            "- The adapter works - a live GET returned 200.", "get.md")

    def test_one_harness_never_reports_a_repository_wide_count(self):
        self._reject(
            "single-harness-count",
            "- The repository has 954 tests, from `unittest discover` alone.",
            "harness.md")


#: A moves table carrying one move beyond what `SKILL.md` currently declares.
#: Used only through `--moves`, never by editing the real file, to prove the
#: roster `check-report` requires is read out of a table rather than out of a
#: list held inside the tool: this fixture's tenth move exists nowhere in
#: `audit_cli.py`, and the requirement still appears.
MOVES_TABLE_PLUS_ONE = """| Move | Ships as | Lock |
| --- | --- | --- |
| 0. Enumerate a closed surface from both sides, and never begin by reviewing a diff | `roster` | `tests/test_skill_audit.py` |
| 1. Build the expected artifact from the documentation alone, then diff it against the producer's output | `roster` | `tests/test_skill_audit.py` |
| 2. Drive the subject as it exists on disk, never only a fixture built from the same document | `roster` | `tests/test_skill_audit.py` |
| 3. Fake every external boundary and assert on what crossed it, never dial it | `doctrine` | `tests/test_skill_audit.py` |
| 4. Read an installed dependency as text; importing a service client authenticates it | `doctrine` | `tests/test_skill_audit.py` |
| 5. Probe live only with consent, read-only, and scope the result to the environment | `doctrine` | `tests/test_skill_audit.py` |
| 6. Invert every lock the audit leans on, and watch it fire | `doctrine` | `tests/test_skill_audit.py` |
| 7. Compare per-harness test counts before and after; a count that did not rise is a finding | `doctrine` | `tests/test_skill_audit.py` |
| 8. Drive the whole documented flow in order, against one real shared box, and name the first step that breaks its own declared expectation | `walkthrough` | `tests/test_skill_audit.py` |
| 9. A move that exists only in this fixture, to prove the roster is derived and never hardcoded | `doctrine` | `tests/test_skill_audit.py` |
| Read every artifact's opening paragraphs against its own frontmatter and its own shipped files | `doctrine` | no lock — irreducibly textual, and carried anyway |
"""


class MoveOutcomesTests(BoxMixin, unittest.TestCase):
    """`## Move outcomes` is enforced against a roster derived from
    `SKILL.md`'s own moves table, never a literal list inside the tool.
    """

    def check(self, text, name="report.md", extra=()):
        box = getattr(self, "_box", None) or self.make_box("move-outcomes")
        self._box = box
        path = self.write(box, name, text)
        result = run_cli("check-report", str(path), *extra)
        return result, json.loads(result.stdout)

    def test_a_complete_roster_of_move_outcomes_is_accepted(self):
        result, payload = self.check(VALID_REPORT)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["violations"], [])

    def test_a_move_missing_its_row_is_named(self):
        broken = VALID_REPORT.replace(
            "- Move: 3: skipped: no external boundary crossed in this pass\n",
            "", 1)
        result, payload = self.check(broken, name="missing-move-3.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "move-outcomes"]
        self.assertTrue(
            any("3" in v["detail"] for v in violations),
            f"removing move 3's row must name move 3: {violations}")

    def test_a_skipped_row_with_an_empty_reason_is_rejected(self):
        broken = VALID_REPORT.replace(
            "- Move: 7: skipped: single-harness count only, not compared\n",
            "- Move: 7: skipped:\n", 1)
        result, payload = self.check(broken, name="empty-reason.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "move-outcomes"]
        self.assertTrue(
            any("7" in v["detail"] for v in violations),
            f"an empty reason must still name move 7: {violations}")

    def test_the_required_roster_is_derived_from_the_moves_table_not_a_list(self):
        """A tenth move that exists only in a fixture file, never in
        `audit_cli.py`, is still required — proof the roster comes from
        parsing the table this run was pointed at, not from a literal held
        inside the tool.
        """
        box = self.make_box("derived-roster")
        self._box = box
        moves_path = self.write(box, "moves.md", MOVES_TABLE_PLUS_ONE)
        # VALID_REPORT's `## Move outcomes` carries moves 0-8 and `textual`
        # only; it names nothing for the fixture's move 9.
        result, payload = self.check(
            VALID_REPORT, name="missing-move-9.md",
            extra=("--moves", str(moves_path)))
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "move-outcomes"]
        self.assertTrue(
            any("9" in v["detail"] for v in violations),
            f"a move present only in the fixture table must still be "
            f"required: {violations}")


class RepairUnitsTests(BoxMixin, unittest.TestCase):
    """`## Repair units` groups findings into units a downstream change can
    take whole; every finding belongs to exactly one, and every forecast is
    an integer.
    """

    def check(self, text, name="report.md"):
        box = getattr(self, "_box", None) or self.make_box("repair-units")
        self._box = box
        path = self.write(box, name, text)
        result = run_cli("check-report", str(path))
        return result, json.loads(result.stdout)

    def test_a_complete_grouping_is_accepted(self):
        result, payload = self.check(VALID_REPORT)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["violations"], [])

    def test_a_finding_named_by_no_unit_is_rejected(self):
        broken = VALID_REPORT.replace(
            "| Build or delete the unread declared value | F2 | 0 |\n", "", 1)
        result, payload = self.check(broken, name="uncovered-f2.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "repair-units"]
        self.assertTrue(
            any("F2" in v["detail"] for v in violations),
            f"a finding covered by no unit must be named: {violations}")

    def test_a_non_integer_forecast_is_rejected(self):
        broken = VALID_REPORT.replace(
            "| One table, one derivation | F1 | 40 |",
            "| One table, one derivation | F1 | forty |", 1)
        result, payload = self.check(broken, name="non-integer-forecast.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "repair-units"]
        self.assertTrue(
            any("forty" in v["detail"] for v in violations),
            f"a non-integer forecast must be named: {violations}")

    def test_a_unit_naming_an_unknown_finding_is_rejected(self):
        broken = VALID_REPORT.replace(
            "| One table, one derivation | F1 | 40 |",
            "| One table, one derivation | F9 | 40 |", 1)
        result, payload = self.check(broken, name="unknown-finding.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "repair-units"]
        self.assertTrue(
            any("F9" in v["detail"] for v in violations),
            f"a unit naming an unknown finding must be rejected: {violations}")


class CheckReportSubjectTests(BoxMixin, unittest.TestCase):
    """`check-report --subject` re-derives `## Frozen`'s digest from disk.

    Without the flag, `rederived` stays `false`, borrowing `comparison:
    not-run`'s own idiom rather than silently weakening the check -- the
    omission is reported, never hidden. The report file itself is written
    beside the subject directory, never inside it, so re-deriving the
    subject's digest never hashes the report that cites it.
    """

    def _report(self, digest, subject):
        return f"""# Audit: a subject, re-derived

## Frozen

- Digest: {digest}
- Subject: {subject}
- Exclude: (none)

## Move outcomes

- Move: 0: ran
- Move: 1: skipped: no from-zero build declared for this surface
- Move: 2: skipped: not driven from disk in this pass
- Move: 3: skipped: no external boundary crossed in this pass
- Move: 4: skipped: no installed dependency read in this pass
- Move: 5: skipped: no live probe attempted, no consent sought
- Move: 6: skipped: no lock inverted in this pass
- Move: 7: skipped: single-harness count only, not compared
- Move: 8: skipped: no ordered user-mode flow driven in this pass
- Move: textual: ran

## Ranked findings

### F1. A finding for the re-derivation fixture

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Digest: {digest}
- Code side: `a.py:1`
- Doctrine side: `SKILL.md:1`
- Detail: only the subject-level digest is under test here.

## Clean, stated as results

- Nothing else was checked in this fixture.

## Unchecked

- Everything outside this one finding.

## Falsifier

A changed subject byte would change the re-derived digest.

## Changed-line forecast

| Remedy | Changed lines |
| --- | --- |
| N/A | 0 |

## Repair units

| Unit | Findings | Changed lines |
| --- | --- | --- |
| N/A | F1 | 0 |
"""

    def test_subject_flag_omitted_reports_rederived_false(self):
        box = self.make_box("subject_omitted")
        subject = box / "subject"
        self.write(subject, "a.txt", "alpha\n")
        digest = audit_cli_module().frozen_digest(subject)
        path = self.write(box, "report.md", self._report(digest, str(subject)))
        result = run_cli("check-report", str(path))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIs(
            payload["rederived"], False,
            "omitting --subject must report rederived: false, never "
            "silently pass as though the disk had been checked")

    def test_matching_subject_is_accepted_and_rederived_true(self):
        box = self.make_box("subject_match")
        subject = box / "subject"
        self.write(subject, "a.txt", "alpha\n")
        digest = audit_cli_module().frozen_digest(subject)
        path = self.write(box, "report.md", self._report(digest, str(subject)))
        result = run_cli("check-report", str(path), "--subject", str(subject))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIs(payload["rederived"], True)
        self.assertEqual(payload["violations"], [])

    def test_mismatched_subject_is_rejected(self):
        box = self.make_box("subject_mismatch")
        subject = box / "subject"
        self.write(subject, "a.txt", "alpha\n")
        stale_digest = audit_cli_module().frozen_digest(subject)
        # The subject changes after the digest was taken, so `## Frozen`'s
        # value is now stale relative to the disk `--subject` re-derives from.
        (subject / "a.txt").write_text("mutated\n", encoding="utf-8")
        path = self.write(box, "report.md", self._report(stale_digest, str(subject)))
        result = run_cli("check-report", str(path), "--subject", str(subject))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1, payload)
        self.assertIs(payload["rederived"], True)
        violations = [v for v in payload["violations"] if v["item"] == "frozen"]
        self.assertNotEqual(
            violations, [],
            f"a subject changed since '## Frozen' was written must be "
            f"rejected: {payload['violations']}")


class ReportSchemaSelfDescriptionTests(unittest.TestCase):
    """Every field the tool requires has a documented row, and the reverse.

    Three sets, both directions. Without this the report shape would be a
    roster restated in two places, which is what the tool is pointed at other
    people's documents to find.
    """

    def _sides(self):
        code = set(dict_literal_keys(CLI, "REPORT_SHAPE"))
        tables = markdown_table_rows(doctrine_text(), REPORT_HEADER)
        self.assertEqual(len(tables), 1, "one report-shape table, exactly")
        return code, {row[0].strip("`") for row in tables[0]}

    def test_no_required_field_is_undocumented(self):
        code, documented = self._sides()
        self.assertEqual(
            sorted(code - documented), [],
            "check-report requires a field with no row in the shape table")

    def test_no_documented_row_lacks_a_required_field(self):
        code, documented = self._sides()
        self.assertEqual(
            sorted(documented - code),
            [],
            "the shape table documents a field check-report never enforces")


class UsageReferenceTests(unittest.TestCase):
    """Every documented invocation is one that actually runs."""

    def test_the_reference_exists_and_covers_every_shipped_subcommand(self):
        self.assertTrue(USAGE_MD.is_file(), "references/usage.md does not exist")
        text = USAGE_MD.read_text(encoding="utf-8")
        for command in sorted(subcommand_surface(CLI, "build_parser")):
            with self.subTest(command=command):
                self.assertIn(f"audit_cli.py {command}", text,
                              f"{command} ships with no worked invocation")

    def test_every_documented_invocation_runs(self):
        text = USAGE_MD.read_text(encoding="utf-8")
        invocations = re.findall(r"^\$ python3 (\S+audit_cli\.py .+)$",
                                 text, re.MULTILINE)
        self.assertNotEqual(invocations, [],
                            "a reference with no runnable invocation is prose")
        for invocation in invocations:
            with self.subTest(invocation=invocation):
                result = subprocess.run(
                    [sys.executable, *invocation.split()], cwd=str(FORGE),
                    shell=False, capture_output=True, text=True, timeout=120)
                self.assertIn(
                    result.returncode, (0, 1),
                    f"a documented invocation must run: {result.stderr[:300]}")
                json.loads(result.stdout)


# ==========================================================================
# Slice 5 — the first damage report. Report only; the audited subject is not
# touched, and the wall between reporting and repairing is the product.
# ==========================================================================

REPORT = (FORGE / "openspec" / "changes" / "the-skill-that-audits-the-others"
          / "audit-proposal-deliberation-operations.md")

#: Not a private copy. This slice deletes the one that used to live here and
#: imports the shipped `tree_digest` instead -- the same function `structure`
#: derives its on-disk and from-zero sides from, and `SingleWalkTests` locks
#: it as the only place in `audit_cli.py` allowed to walk a filesystem tree.
tree_digest = audit_cli_module().tree_digest


class FirstDamageReportTests(unittest.TestCase):
    """The auditor ships an audit. Without one it is the orphan class it
    exists to find."""

    def test_the_shipped_report_validates(self):
        result = run_cli("check-report", str(REPORT))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0,
                         f"the shipped report does not validate: {payload}")
        self.assertEqual(payload["violations"], [])

    def test_the_report_carries_both_required_kinds_of_finding(self):
        text = REPORT.read_text(encoding="utf-8")
        self.assertIn("- Evidence: CONFIRMED by execution", text,
                      "a report with nothing confirmed tells the reader "
                      "nothing they could not have read for themselves")
        self.assertIn("- Adjudication: not adjudicable", text,
                      "the half-with-no-other-half outcome is a required "
                      "result, not a softer verdict")

    def test_the_report_names_every_hand_restated_location(self):
        """The executed set is the deciding evidence, and the report has to
        show where the hand-written copies live."""
        _, payload = roster_json(PD_SPEC, PD)
        text = REPORT.read_text(encoding="utf-8")
        self.assertNotEqual(payload["duplicated"], [])
        for site in payload["duplicated"]:
            name = Path(site["path"]).name
            with self.subTest(site=name):
                self.assertIn(name, text,
                              f"{name} restates the set and the report is "
                              "silent about it")


class NothingWasRepairedTests(unittest.TestCase):
    """`mutations: 0`. The wall between reporting and repairing is the product.

    Even a one-line `phantom` deletion is not made here: an audit that repairs
    what it finds is an audit whose findings nobody reviewed.
    """

    def test_a_full_audit_leaves_the_subject_byte_identical(self):
        before = tree_digest(PD)
        self.assertGreater(len(before), 10, "the subject tree looks empty")
        roster_json(PD_SPEC, PD)
        run_cli("check-report", str(REPORT))
        after = tree_digest(PD)
        self.assertEqual(
            sorted(set(before) - set(after)), [], "a file was removed")
        self.assertEqual(
            sorted(set(after) - set(before)), [], "a file was added")
        self.assertEqual(
            [p for p in before if before[p] != after.get(p)], [],
            "a file under the audited subject changed; the audit reports and "
            "repairs nothing, so any difference here is a defect in the audit")

    def test_a_structure_run_leaves_the_subject_and_its_ground_untouched(self):
        """The exemption in the lock below, held by bytes instead of by prose.

        `structure` is the only subcommand that writes at all, so it is the
        only one that could repair what it audits. The static lock below can
        say which functions write; it cannot say where. This drives the real
        subcommand against the real subject and answers that question the
        only way it can be answered: by comparing the tree to itself.

        The borrowed ground is checked too. A box that outlives its run is a
        mutation with a delay on it.
        """
        ground = FORGE / "implementations"
        occupants = lambda: sorted(e.name for e in ground.iterdir()) \
            if ground.is_dir() else []
        before, occupied_before = tree_digest(SKILL_ROOT), occupants()
        self.assertIn(
            "scripts/audit_cli.py", before,
            "the walk did not see the subject's own script, so a tree that "
            "compares equal afterwards would prove nothing")
        structure_json(STRUCTURE_SPEC, SKILL_ROOT, repo=FORGE)
        after = tree_digest(SKILL_ROOT)
        self.assertEqual(
            sorted(set(before) - set(after)), [], "a file was removed")
        self.assertEqual(
            sorted(set(after) - set(before)), [], "a file was added")
        self.assertEqual(
            [q for q in before if before[q] != after.get(q)], [],
            "structure changed a file under the audited subject; the audit "
            "reports and repairs nothing, so any difference here is a defect "
            "in the audit")
        self.assertEqual(
            occupants(), occupied_before,
            "structure left its box behind; the ground it borrows must look "
            "the same afterwards")

    def test_a_walkthrough_run_leaves_the_subject_and_its_ground_untouched(self):
        """The exemption in the lock below, held by bytes instead of by prose.

        `walkthrough` is the other subcommand that writes at all, alongside
        `structure`, so it is the other one that could repair what it audits.
        The static lock below can say which functions write; it cannot say
        where. This drives the real subcommand, with the real shipped
        first-run recipe, against the real subject, and answers that
        question the only way it can be answered: by comparing the tree to
        itself.

        The borrowed ground is checked too. A box that outlives its run is a
        mutation with a delay on it.
        """
        ground = FORGE / "implementations"
        occupants = lambda: sorted(e.name for e in ground.iterdir()) \
            if ground.is_dir() else []
        before, occupied_before = tree_digest(SKILL_ROOT), occupants()
        self.assertIn(
            "scripts/audit_cli.py", before,
            "the walk did not see the subject's own script, so a tree that "
            "compares equal afterwards would prove nothing")
        walkthrough_json(WALKTHROUGH_SPEC, SKILL_ROOT, repo=FORGE)
        after = tree_digest(SKILL_ROOT)
        self.assertEqual(
            sorted(set(before) - set(after)), [], "a file was removed")
        self.assertEqual(
            sorted(set(after) - set(before)), [], "a file was added")
        self.assertEqual(
            [q for q in before if before[q] != after.get(q)], [],
            "walkthrough changed a file under the audited subject; the audit "
            "reports and repairs nothing, so any difference here is a defect "
            "in the audit")
        self.assertEqual(
            occupants(), occupied_before,
            "walkthrough left its box behind; the ground it borrows must "
            "look the same afterwards")

    def test_the_auditor_names_no_write_into_the_audited_subject(self):
        """`roster` and `check-report` write nothing, anywhere, and still don't.

        The box lifecycle is the exception, and it is named function by
        function: `run_structure` and `run_walkthrough` each create their
        own box and `erase_box` removes either. Every other function in
        every `.py` file this skill ships writes nothing at all.

        What this lock cannot see is where an exempt function writes, and an
        exemption whose limit lives only in a docstring is a claim with
        nothing behind it. The limit is held by the two tests above, each
        driving the real subcommand and reading the subject's bytes off disk.
        """
        box_lifecycle_exemption = {"run_structure", "run_walkthrough", "erase_box"}
        for path in sorted(SKILL_ROOT.rglob("*")):
            if not path.is_file() or path.suffix != ".py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for definition in ast.walk(tree):
                if not isinstance(definition, ast.FunctionDef) \
                        or definition.name in box_lifecycle_exemption:
                    continue
                written = {node.func.attr for node in ast.walk(definition)
                          if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Attribute)}
                for verb in ("write_text", "write_bytes", "mkdir", "unlink",
                             "rmdir", "rename", "replace", "rmtree"):
                    with self.subTest(path=path.name, function=definition.name,
                                      verb=verb):
                        self.assertNotIn(
                            verb, written,
                            f"{path.name}:{definition.name} calls {verb}; only "
                            f"{sorted(box_lifecycle_exemption)} may write, and "
                            "only inside its own box, never into the subject")


# ==========================================================================
# `the-audit-that-runs-what-it-claims`, Slice 2 -- `structure`: three
# independently derived sides (declared, on-disk, from-zero) and one
# arithmetic adjudication, built on the one walk helper this module is ever
# allowed to have.
# ==========================================================================

STRUCTURE_SPEC = PROBES / "skill-audit.structure.json"

#: Every sibling skill directory except this one and the excluded name below,
#: discovered rather than listed by hand -- a hardcoded roster of skills is
#: exactly the defect class this tool exists to find.
#:
#: One name is excluded: it holds roughly a gigabyte of binary assets, and
#: hashing it twice per test would make this lock prohibitively slow without
#: adding any assurance the other siblings don't already provide.
_SELF_PROBE_EXCLUDED_SIBLING = "paper-ingestion"
SIBLING_SKILLS_TO_CHECK = tuple(sorted(
    entry.name for entry in SKILL_ROOT.parent.iterdir()
    if entry.is_dir() and entry.name != SKILL_ROOT.name
    and entry.name != _SELF_PROBE_EXCLUDED_SIBLING))


def structure_json(spec, subject, repo=FORGE, extra=()):
    """Drive `structure` as a process and parse what it wrote to stdout."""
    result = run_cli("structure", "--subject", str(subject),
                     "--spec", str(spec), "--repo-root", str(repo), *extra)
    try:
        return result, json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"structure exited {result.returncode} without JSON on stdout.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}")


class TreeDigestTests(BoxMixin, unittest.TestCase):
    """The one path->sha256 walk, used by `structure`'s three sides and by
    every box's cleanup proof.
    """

    def test_the_digest_is_sorted_path_to_sha256_over_files_only(self):
        box = self.make_box("digest_basic")
        self.write(box, "a.txt", "alpha\n")
        self.write(box, "sub/b.txt", "beta\n")
        (box / "emptydir").mkdir()
        digest = audit_cli_module().tree_digest(box)
        self.assertEqual(sorted(digest), ["a.txt", "sub/b.txt"],
                         "a directory holds no content of its own to hash, "
                         "so it is never a member of the digest")
        self.assertEqual(len(digest["a.txt"]), 64,
                         "sha256 hexdigests are 64 hex characters")

    def test_one_changed_byte_changes_the_digest(self):
        box = self.make_box("digest_change")
        path = self.write(box, "a.txt", "alpha\n")
        before = audit_cli_module().tree_digest(box)
        path.write_text("Alpha\n", encoding="utf-8")
        after = audit_cli_module().tree_digest(box)
        self.assertNotEqual(before["a.txt"], after["a.txt"])

    def test_an_excluded_pattern_is_never_a_member(self):
        box = self.make_box("digest_exclude")
        self.write(box, "keep.py", "print(1)\n")
        self.write(box, "__pycache__/keep.cpython-39.pyc", "junk")
        digest = audit_cli_module().tree_digest(box, exclude=("__pycache__/*",))
        self.assertEqual(sorted(digest), ["keep.py"])

    def test_a_missing_root_digests_as_empty_rather_than_raising(self):
        digest = audit_cli_module().tree_digest(BOXES / "_skill_audit_never_made")
        self.assertEqual(digest, {},
                         "a box not yet created is content-empty, not an error")


class SingleWalkTests(unittest.TestCase):
    """The manifest contract's second clause, mechanised.

    Scope: `audit_cli.py`, and only that one file. `rglob`, `os.walk`,
    `iterdir`, `scandir`, and `glob` may appear inside `tree_digest` and
    nowhere else in it -- not in `structure`'s box lifecycle, not in
    `roster`, not anywhere. This is what turns a second walk added by the
    follow-up change's `manifest` into a red rather than a silent duplicate.
    It says nothing about `tests/test_skill_audit.py` or any other file in
    this repository.
    """

    WALK_NAMES = ("rglob", "walk", "iterdir", "scandir", "glob")

    def test_the_walk_names_appear_only_inside_tree_digest(self):
        tree = ast.parse(CLI.read_text(encoding="utf-8"))
        function_bodies = {
            node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)}
        self.assertIn(
            "tree_digest", function_bodies,
            "audit_cli.py defines no tree_digest to scope this lock to")
        inside_tree_digest = set(ast.walk(function_bodies["tree_digest"]))
        offenders = []
        for node in ast.walk(tree):
            if node in inside_tree_digest:
                continue
            name = node.attr if isinstance(node, ast.Attribute) else (
                node.id if isinstance(node, ast.Name) else None)
            if name in self.WALK_NAMES:
                offenders.append(name)
        self.assertEqual(
            offenders, [],
            "a walk name appears outside tree_digest in audit_cli.py: "
            f"{offenders}")


class FrozenDigestTests(BoxMixin, unittest.TestCase):
    """One stable summary hash over `tree_digest`'s own map -- never a second
    walk, and never a per-file map a report could not stay reviewable while
    embedding.
    """

    def test_stable_digest_for_same_tree(self):
        box = self.make_box("frozen_stable")
        self.write(box, "a.txt", "alpha\n")
        self.write(box, "sub/b.txt", "beta\n")
        cli = audit_cli_module()
        first = cli.frozen_digest(box)
        second = cli.frozen_digest(box)
        self.assertEqual(first, second,
                         "two runs over an unchanged tree must agree")
        self.assertTrue(first.startswith("sha256:"),
                        f"the digest names its own algorithm: {first!r}")

    def test_digest_changes_with_exclusion(self):
        box = self.make_box("frozen_exclude")
        self.write(box, "keep.py", "print(1)\n")
        self.write(box, "__pycache__/keep.cpython-39.pyc", "junk")
        cli = audit_cli_module()
        with_junk = cli.frozen_digest(box)
        without_junk = cli.frozen_digest(box, exclude=("__pycache__/*",))
        self.assertNotEqual(
            with_junk, without_junk,
            "excluding a member must change the digest -- two runs that "
            "disagree only about a stray excluded file must not agree by "
            "accident")

    def test_finding_digest_mismatch_rejected(self):
        cli = audit_cli_module()
        box = self.make_box("frozen_mismatch")
        digest_a = cli.frozen_digest(box)
        digest_b = "sha256:" + "0" * 64
        self.assertNotEqual(digest_a, digest_b)
        report = f"""# Audit: a mismatch fixture

## Frozen

- Digest: {digest_a}
- Subject: {box}
- Exclude: (none)

## Move outcomes

- Move: 0: ran
- Move: 1: skipped: no from-zero build declared for this surface
- Move: 2: skipped: not driven from disk in this pass
- Move: 3: skipped: no external boundary crossed in this pass
- Move: 4: skipped: no installed dependency read in this pass
- Move: 5: skipped: no live probe attempted, no consent sought
- Move: 6: skipped: no lock inverted in this pass
- Move: 7: skipped: single-harness count only, not compared
- Move: 8: skipped: no ordered user-mode flow driven in this pass
- Move: textual: ran

## Ranked findings

### F1. A finding whose own digest disagrees with the frozen one

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Digest: {digest_b}
- Code side: `a.py:1`
- Doctrine side: `SKILL.md:1`
- Detail: planted for this test -- the two digests are deliberately unequal.

## Clean, stated as results

- Nothing else was checked in this fixture.

## Unchecked

- Everything outside this one planted finding.

## Falsifier

Making the finding's digest agree with '## Frozen' would remove the rejection.

## Changed-line forecast

| Remedy | Changed lines |
| --- | --- |
| N/A | 0 |

## Repair units

| Unit | Findings | Changed lines |
| --- | --- | --- |
| N/A | F1 | 0 |
"""
        path = self.write(box, "mismatch.md", report)
        result = run_cli("check-report", str(path))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"] if v["item"] == "frozen"]
        self.assertTrue(
            any("F1" in v["where"] for v in violations),
            f"a finding's digest disagreeing with '## Frozen' must be "
            f"rejected and must name the finding: {violations}")


class FrozenPayloadTests(unittest.TestCase):
    """`frozen` travels in every subcommand's own payload, not only
    `roster`'s. Driven for real, against this skill's own shipped recipes,
    never through a fixture built only for this assertion.
    """

    def test_roster_payload_carries_frozen(self):
        _, payload = roster_json(SELF_SPEC, SKILL_ROOT)
        self._assert_frozen_shape(payload)

    def test_structure_payload_carries_frozen(self):
        _, payload = structure_json(STRUCTURE_SPEC, SKILL_ROOT, repo=FORGE)
        self._assert_frozen_shape(payload)

    def test_walkthrough_payload_carries_frozen(self):
        _, payload = walkthrough_json(WALKTHROUGH_SPEC, SKILL_ROOT, repo=FORGE)
        self._assert_frozen_shape(payload)

    def _assert_frozen_shape(self, payload):
        self.assertIn("frozen", payload, f"payload carries no frozen: {payload}")
        frozen = payload["frozen"]
        self.assertEqual(set(frozen), {"digest", "exclude", "subject"})
        self.assertTrue(
            frozen["digest"].startswith("sha256:"),
            f"the digest names its own algorithm: {frozen}")
        self.assertEqual(Path(frozen["subject"]), SKILL_ROOT.resolve())


class TokenInterpolationTests(unittest.TestCase):
    """Only `{repoRoot}`, `{subject}`, and `{box}` interpolate."""

    def test_the_three_named_tokens_interpolate(self):
        cli = audit_cli_module()
        result = cli.interpolate_token(
            "{repoRoot}-x-{subject}-y-{box}",
            Path("/r"), Path("/s"), Path("/b"))
        self.assertEqual(result, "/r-x-/s-y-/b")

    def test_an_unknown_token_is_unprobeable(self):
        cli = audit_cli_module()
        with self.assertRaises(cli.Unprobeable):
            cli.interpolate_token("{mystery}", Path("/r"), Path("/s"), Path("/b"))


class StructureNormalisationTests(unittest.TestCase):
    """One normalisation, applied to every declared cell before comparison."""

    def test_posix_relative_dot_slash_stripped_case_preserved(self):
        cli = audit_cli_module()
        normalised, notes = cli.normalize_declared_paths(["./a/b.txt", "C.txt"])
        self.assertEqual(normalised, {"a/b.txt", "C.txt"})
        self.assertEqual(notes, [])

    def test_shape_not_walkable_cells_are_set_aside_from_every_side(self):
        cli = audit_cli_module()
        raw = ["trailing/", "/absolute", "../up", "glob*.md", "back\\slash"]
        normalised, notes = cli.normalize_declared_paths(raw)
        self.assertEqual(normalised, set(),
                         "none of these shapes may be expanded against the disk")
        self.assertEqual(len(notes), len(raw))
        self.assertTrue(all(note["kind"] == "shape-not-walkable" for note in notes))

    def test_case_only_divergence_is_noted_and_never_folded(self):
        cli = audit_cli_module()
        found = cli.case_only_divergences(
            "declared", {"README.md"}, "disk", {"readme.md"})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], "case-only-divergence")

    def test_an_exact_match_is_not_a_case_only_divergence(self):
        cli = audit_cli_module()
        self.assertEqual(
            cli.case_only_divergences("declared", {"a.txt"}, "disk", {"a.txt"}), [])


class StructureOutcomeArithmeticTests(unittest.TestCase):
    """The arithmetic adjudication, and `ADJUDICATIONS` left untouched."""

    def test_all_three_agree(self):
        outcome, *_ = audit_cli_module().structure_outcome({"a"}, {"a"}, {"a"})
        self.assertEqual(outcome, "agree")

    def test_disk_stale_when_declared_and_from_zero_agree(self):
        outcome, *_ = audit_cli_module().structure_outcome(
            {"a", "b"}, {"a"}, {"a", "b"})
        self.assertEqual(outcome, "disk-stale")

    def test_builder_broken_when_declared_and_disk_agree(self):
        outcome, *_ = audit_cli_module().structure_outcome(
            {"a", "b"}, {"a", "b"}, {"a"})
        self.assertEqual(outcome, "builder-broken")

    def test_document_wrong_when_disk_and_from_zero_agree(self):
        outcome, *_ = audit_cli_module().structure_outcome(
            {"a"}, {"a", "b"}, {"a", "b"})
        self.assertEqual(outcome, "document-wrong")

    def test_three_way_divergence_when_all_three_differ(self):
        outcome, *_ = audit_cli_module().structure_outcome({"a"}, {"b"}, {"c"})
        self.assertEqual(outcome, "three-way-divergence")

    def test_no_outcome_is_smuggled_into_adjudications(self):
        cli = audit_cli_module()
        for outcome in ("agree", "disk-stale", "builder-broken",
                        "document-wrong", "three-way-divergence"):
            with self.subTest(outcome=outcome):
                self.assertNotIn(outcome, cli.ADJUDICATIONS)
        self.assertEqual(len(cli.ADJUDICATIONS), 3,
                         "structure adds no fourth ADJUDICATIONS value")

    def test_only_in_and_missing_from_are_sets_never_booleans(self):
        _, only_in, missing_from = audit_cli_module().structure_outcome(
            {"a"}, {"b"}, {"c"})
        for payload in (only_in, missing_from):
            for side in ("declared", "disk", "fromZero"):
                with self.subTest(side=side):
                    self.assertIsInstance(payload[side], list)


class StructureBoxMixin(BoxMixin):
    """Fixtures for `structure`'s three sides: a subject the audit walks
    directly, plus a box the audit builds fresh under `implementations/`.
    """

    def structure_box(self, surface):
        box = BOXES / f"_structure_{surface}"
        self.addCleanup(self._erase_structure_box, box)
        return box

    def _erase_structure_box(self, box):
        if not box.exists():
            return
        for path in sorted(box.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        box.rmdir()

    def make_subject(self, name, declared, disk_files):
        subject = self.make_box(name)
        rows = "".join(f"| `{path}` | x |\n" for path in declared)
        self.write(subject, "STRUCTURE.md",
                  f"| Path | Holds |\n| --- | --- |\n{rows}")
        for relative, content in disk_files.items():
            self.write(subject, f"content/{relative}", content)
        return subject

    def build_script(self, subject, files):
        """A build step's script: writes `files` byte-identically under
        whatever root it is called with, so the arithmetic tests exercise
        agreement or divergence deliberately rather than by accident.
        """
        lines = ["import pathlib, sys", "root = pathlib.Path(sys.argv[1])"]
        for relative, content in files.items():
            lines.append(
                f"(root / {relative!r}).parent.mkdir(parents=True, exist_ok=True)")
            lines.append(
                f"(root / {relative!r}).write_text({content!r}, encoding='utf-8')")
        return self.write(subject, "build.py", "\n".join(lines) + "\n")

    def make_recipe(self, subject, surface, steps, exclude=()):
        spec = subject / "structure.json"
        spec.write_text(json.dumps({
            "surface": surface,
            "declared": {"path": "STRUCTURE.md", "table": "| Path | Holds |",
                        "column": 0},
            "disk": {"root": "content"},
            "fromZero": {"root": "build", "steps": steps},
            "exclude": list(exclude),
        }, indent=2), encoding="utf-8")
        return spec


class StructureOutcomeIntegrationTests(StructureBoxMixin, unittest.TestCase):
    """All three outcomes, over a real subprocess and a real box."""

    def _run(self, name, declared, disk_files, from_zero_files):
        surface = f"outcome_{name}"
        self.structure_box(surface)
        subject = self.make_subject(name, declared, disk_files)
        script = self.build_script(subject, from_zero_files)
        steps = [["python3", str(script), "{box}/build"]]
        spec = self.make_recipe(subject, surface, steps)
        return structure_json(spec, subject, repo=FORGE)

    def test_disk_stale(self):
        result, payload = self._run(
            "disk_stale",
            declared=["a.txt", "b.txt"],
            disk_files={"a.txt": "one\n"},
            from_zero_files={"a.txt": "one\n", "b.txt": "two\n"})
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["outcome"], "disk-stale")

    def test_builder_broken(self):
        result, payload = self._run(
            "builder_broken",
            declared=["a.txt", "b.txt"],
            disk_files={"a.txt": "one\n", "b.txt": "two\n"},
            from_zero_files={"a.txt": "one\n"})
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["outcome"], "builder-broken")

    def test_document_wrong(self):
        result, payload = self._run(
            "document_wrong",
            declared=["a.txt"],
            disk_files={"a.txt": "one\n", "b.txt": "two\n"},
            from_zero_files={"a.txt": "one\n", "b.txt": "two\n"})
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["outcome"], "document-wrong")

    def test_three_way_divergence(self):
        result, payload = self._run(
            "three_way",
            declared=["a.txt"],
            disk_files={"b.txt": "two\n"},
            from_zero_files={"c.txt": "three\n"})
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["outcome"], "three-way-divergence")

    def test_all_three_agree(self):
        result, payload = self._run(
            "agree", declared=["a.txt"], disk_files={"a.txt": "one\n"},
            from_zero_files={"a.txt": "one\n"})
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["outcome"], "agree")
        self.assertTrue(payload["containment"]["afterRemoved"])
        self.assertTrue(payload["containment"]["beforeEmpty"])


class StructureBoxLifecycleTests(StructureBoxMixin, unittest.TestCase):
    """The box: adopted only empty, escape is exit 2, cleanup by content."""

    def test_a_non_empty_box_is_refused_and_left_untouched(self):
        surface = "occupied"
        box = self.structure_box(surface)
        box.mkdir(parents=True, exist_ok=True)
        (box / "stranger.txt").write_text("already here\n", encoding="utf-8")
        subject = self.make_subject(
            "occupied_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        script = self.build_script(subject, {"a.txt": "x\n"})
        spec = self.make_recipe(subject, surface,
                                [["python3", str(script), "{box}/build"]])
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn(str(box), payload["error"])
        self.assertTrue((box / "stranger.txt").exists(),
                        "a box that was not ours to adopt must be left alone")

    def test_a_build_that_writes_outside_the_box_is_exit_two(self):
        surface = "escape"
        self.structure_box(surface)
        subject = self.make_subject(
            "escape_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        escape_script = self.write(
            subject, "escape.py",
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[1]).write_text('escaped', encoding='utf-8')\n")
        steps = [["python3", str(escape_script), "{subject}/escaped.txt"]]
        spec = self.make_recipe(subject, surface, steps)
        escaped = subject / "escaped.txt"
        self.addCleanup(lambda: escaped.unlink() if escaped.exists() else None)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("build-escaped-the-box", payload["error"])
        self.assertIn("escaped.txt", payload["error"])

    def test_an_unknown_token_in_a_step_is_exit_two(self):
        surface = "unknown_token"
        self.structure_box(surface)
        subject = self.make_subject(
            "token_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        spec = self.make_recipe(subject, surface, [["echo", "{mystery}"]])
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("unknown token", payload["error"])

    def test_an_empty_declared_side_is_unprobeable_never_a_finding(self):
        surface = "empty_declared"
        self.structure_box(surface)
        subject = self.make_box("empty_declared_subject")
        self.write(subject, "STRUCTURE.md", "| Path | Holds |\n| --- | --- |\n")
        self.write(subject, "content/a.txt", "x\n")
        script = self.build_script(subject, {"a.txt": "x\n"})
        spec = self.make_recipe(subject, surface,
                                [["python3", str(script), "{box}/build"]])
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("zero members", payload["error"])
        self.assertNotIn("finding", payload["error"])

    def test_cleanup_is_proven_by_content_never_by_git_status(self):
        surface = "cleanup_proof"
        box = self.structure_box(surface)
        subject = self.make_subject(
            "cleanup_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        script = self.build_script(subject, {"a.txt": "x\n"})
        spec = self.make_recipe(subject, surface,
                                [["python3", str(script), "{box}/build"]])
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        after = audit_cli_module().tree_digest(BOXES)
        self.assertEqual(
            [p for p in after if p.startswith(f"_structure_{surface}/")], [],
            "the box's paths must be absent from a fresh content walk of "
            "implementations/ -- the same proof every other box's cleanup "
            "uses in this file, never `git status`")
        self.assertFalse(box.exists())


class StructureSelfProbeTests(unittest.TestCase):
    """The shipped recipe, pointed at the auditor's own layout.

    Uncommitted work in this slice legitimately reads as `builder-broken`
    against `HEAD`; that is documented as accurate, not papered over.
    """

    def test_the_shipped_recipe_runs_and_touches_no_sibling_skill(self):
        cli = audit_cli_module()
        before = {name: cli.tree_digest(SKILL_ROOT.parent / name)
                 for name in SIBLING_SKILLS_TO_CHECK}
        result, payload = structure_json(STRUCTURE_SPEC, SKILL_ROOT, repo=FORGE)
        after = {name: cli.tree_digest(SKILL_ROOT.parent / name)
                for name in SIBLING_SKILLS_TO_CHECK}
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(
            before, after,
            "structure reads the subject and builds its own box; it must "
            "never touch a sibling skill")
        self.assertIn(payload["outcome"],
                      ("agree", "disk-stale", "builder-broken",
                       "document-wrong", "three-way-divergence"))


# ==========================================================================
# `the-audit-that-runs-what-it-claims`, Slice 3 -- `walkthrough`: an ordered
# recipe run against one shared box, exiting `0` for any verdict including a
# stall and `2` only when the flow itself could not be entered.
# ==========================================================================

WALKTHROUGH_SPEC = PROBES / "skill-audit.first-run.json"


def walkthrough_json(spec, subject, repo=FORGE, extra=()):
    """Drive `walkthrough` as a process and parse what it wrote to stdout."""
    result = run_cli("walkthrough", "--subject", str(subject),
                     "--spec", str(spec), "--repo-root", str(repo), *extra)
    try:
        return result, json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"walkthrough exited {result.returncode} without JSON on stdout.\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}")


class WalkthroughBoxMixin(BoxMixin):
    """Fixtures for `walkthrough`: one shared box for an ordered sequence,
    under `implementations/`, never the system temporary directory.
    """

    def walkthrough_box(self, surface):
        box = BOXES / f"_walkthrough_{surface}"
        self.addCleanup(self._erase_walkthrough_box, box)
        return box

    def _erase_walkthrough_box(self, box):
        if not box.exists():
            return
        for path in sorted(box.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        box.rmdir()

    def make_recipe(self, subject, surface, steps):
        spec = subject / "walkthrough.json"
        spec.write_text(
            json.dumps({"surface": surface, "steps": steps}, indent=2),
            encoding="utf-8")
        return spec


class WalkthroughStepShapeTests(WalkthroughBoxMixin, unittest.TestCase):
    """A step declaring no expectation is not a gate. A missing command at
    index 0 means the flow was never entered; after index 0, a documented
    command that is not there is a fact about the flow, not an inability.
    """

    def test_a_step_with_no_expectation_is_unprobeable(self):
        surface = "no_expect"
        self.walkthrough_box(surface)
        subject = self.make_box("no_expect_subject")
        spec = self.make_recipe(subject, surface, [
            {"argv": ["python3", "-c", "print(1)"], "name": "silent step"}])
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("no expectation", payload["error"])

    def test_an_expect_with_only_exit_any_is_still_no_expectation(self):
        """`exit: any` alone asserts nothing; declaring it changes nothing."""
        surface = "exit_any_only"
        self.walkthrough_box(surface)
        subject = self.make_box("exit_any_only_subject")
        spec = self.make_recipe(subject, surface, [
            {"argv": ["python3", "-c", "print(1)"], "expect": {"exit": "any"},
             "name": "asserts nothing"}])
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("no expectation", payload["error"])

    def test_a_missing_command_at_index_zero_is_unprobeable(self):
        surface = "missing_zero"
        self.walkthrough_box(surface)
        subject = self.make_box("missing_zero_subject")
        spec = self.make_recipe(subject, surface, [
            {"argv": ["definitely-not-a-real-binary-xyz"],
             "expect": {"exit": 0}, "name": "ghost"}])
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("not executable", payload["error"])

    def test_a_missing_command_after_index_zero_is_a_stall(self):
        surface = "missing_later"
        self.walkthrough_box(surface)
        subject = self.make_box("missing_later_subject")
        spec = self.make_recipe(subject, surface, [
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "first"},
            {"argv": ["definitely-not-a-real-binary-xyz"],
             "expect": {"exit": 0}, "name": "ghost"}])
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIsNotNone(payload["stall"], payload)
        self.assertEqual(payload["stall"]["index"], 1)
        self.assertEqual(payload["stall"]["kind"], "missing-executable")


class WalkthroughStallTests(WalkthroughBoxMixin, unittest.TestCase):
    """The stall is the first observation contradicting its own `expect`,
    never the first non-zero exit. Every later gate lands in `## Unchecked`.
    """

    def test_a_stall_mid_sequence_names_its_index_and_leaves_later_gates_unreached(self):
        surface = "stall_mid"
        self.walkthrough_box(surface)
        subject = self.make_box("stall_mid_subject")
        steps = [
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "step0"},
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "step1"},
            {"argv": ["python3", "-c", "import sys; sys.exit(1)"],
             "expect": {"exit": 0}, "name": "step2 stalls"},
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "step3"},
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "step4"},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["stall"]["index"], 2)
        self.assertEqual(payload["unreached"], [3, 4],
                         "every gate at or after the stall is unreached")
        outcomes = {step["index"]: step["outcome"] for step in payload["steps"]}
        self.assertEqual(outcomes[0], "passed")
        self.assertEqual(outcomes[1], "passed")
        self.assertEqual(outcomes[2], "stalled")
        self.assertEqual(outcomes[3], "unreached")
        self.assertEqual(outcomes[4], "unreached")

    def test_a_step_matching_its_own_expect_passes_whatever_its_exit_code(self):
        """A documented refusal is a pass, not a stall."""
        surface = "documented_refusal"
        self.walkthrough_box(surface)
        subject = self.make_box("documented_refusal_subject")
        steps = [{"argv": ["python3", "-c", "import sys; sys.exit(3)"],
                  "expect": {"exit": 3}, "name": "expected refusal"}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIsNone(payload["stall"], payload)
        self.assertEqual(payload["steps"][0]["outcome"], "passed")

    def test_a_step_whose_stdout_does_not_match_its_expectation_stalls(self):
        surface = "stdout_mismatch"
        self.walkthrough_box(surface)
        subject = self.make_box("stdout_mismatch_subject")
        steps = [{"argv": ["python3", "-c", "print('nope')"],
                  "expect": {"exit": 0, "stdout": "yes"},
                  "name": "prints something else"}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["stall"]["index"], 0)
        self.assertEqual(payload["stall"]["kind"], "contradiction")

    def test_a_hanging_step_is_a_stall_of_kind_timeout(self):
        surface = "timeout"
        self.walkthrough_box(surface)
        subject = self.make_box("timeout_subject")
        steps = [{"argv": ["python3", "-c", "import time; time.sleep(5)"],
                  "expect": {"exit": 0}, "name": "hangs"}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(
            spec, subject, repo=FORGE, extra=("--timeout", "1"))
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["stall"]["kind"], "timeout")
        self.assertEqual(payload["stall"]["index"], 0)

    def test_exit_is_zero_for_any_verdict_never_two_for_a_stall(self):
        surface = "exit_zero_verdict"
        self.walkthrough_box(surface)
        subject = self.make_box("exit_zero_verdict_subject")
        steps = [{"argv": ["python3", "-c", "import sys; sys.exit(9)"],
                  "expect": {"exit": 0}, "name": "stalls"}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(
            result.returncode, 0,
            "a stall is a finding on its own, never an inability to look")
        self.assertIsNotNone(payload["stall"])


class WalkthroughBoxSharingTests(WalkthroughBoxMixin, unittest.TestCase):
    """One box for the whole sequence, state accumulating; `reset: true`
    demands a fresh, empty box for that one step onward.
    """

    def test_one_box_is_shared_across_the_whole_sequence(self):
        surface = "shared_state"
        self.walkthrough_box(surface)
        subject = self.make_box("shared_state_subject")
        steps = [
            {"argv": ["python3", "-c",
                     "open('marker.txt', 'w').write('hello')"],
             "expect": {"exit": 0}, "name": "write a marker"},
            {"argv": ["python3", "-c",
                     "import sys\n"
                     "content = open('marker.txt').read()\n"
                     "sys.exit(0 if content == 'hello' else 1)"],
             "expect": {"exit": 0},
             "name": "read the marker the previous step wrote"},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIsNone(payload["stall"], payload)
        self.assertEqual(payload["steps"][1]["outcome"], "passed")

    def test_reset_true_gets_a_fresh_empty_box(self):
        surface = "reset_step"
        self.walkthrough_box(surface)
        subject = self.make_box("reset_step_subject")
        steps = [
            {"argv": ["python3", "-c",
                     "open('marker.txt', 'w').write('hello')"],
             "expect": {"exit": 0}, "name": "write a marker"},
            {"argv": ["python3", "-c",
                     "import os, sys\n"
                     "sys.exit(0 if not os.path.exists('marker.txt') else 1)"],
             "expect": {"exit": 0}, "name": "the marker is gone after reset",
             "reset": True},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIsNone(payload["stall"], payload)
        self.assertEqual(payload["steps"][1]["outcome"], "passed")

    def test_a_non_empty_box_is_refused_and_left_untouched(self):
        surface = "occupied"
        box = self.walkthrough_box(surface)
        box.mkdir(parents=True, exist_ok=True)
        (box / "stranger.txt").write_text("already here\n", encoding="utf-8")
        subject = self.make_box("occupied_subject")
        steps = [{"argv": ["python3", "-c", "pass"], "expect": {"exit": 0},
                  "name": "no-op"}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn(str(box), payload["error"])
        self.assertTrue((box / "stranger.txt").exists(),
                        "a box that was not ours to adopt must be left alone")

    def test_cleanup_is_proven_by_content_never_by_git_status(self):
        surface = "cleanup_proof"
        box = self.walkthrough_box(surface)
        subject = self.make_box("cleanup_proof_subject")
        steps = [{"argv": ["python3", "-c", "pass"], "expect": {"exit": 0},
                  "name": "no-op"}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        after = audit_cli_module().tree_digest(BOXES)
        self.assertEqual(
            [p for p in after if p.startswith(f"_walkthrough_{surface}/")], [],
            "the box's paths must be absent from a fresh content walk of "
            "implementations/ -- the same proof every other box's cleanup "
            "uses in this file, never `git status`")
        self.assertFalse(box.exists())


class WalkthroughSelfProbeTests(unittest.TestCase):
    """The shipped first-run recipe, pointed at the auditor's own layout."""

    def test_the_shipped_recipe_runs_and_touches_no_sibling_skill(self):
        cli = audit_cli_module()
        before = {name: cli.tree_digest(SKILL_ROOT.parent / name)
                 for name in SIBLING_SKILLS_TO_CHECK}
        result, payload = walkthrough_json(WALKTHROUGH_SPEC, SKILL_ROOT, repo=FORGE)
        after = {name: cli.tree_digest(SKILL_ROOT.parent / name)
                for name in SIBLING_SKILLS_TO_CHECK}
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(
            before, after,
            "walkthrough reads the subject and builds its own box; it must "
            "never touch a sibling skill")
        self.assertIsNone(
            payload["stall"],
            f"the shipped worked invocation is documented as a clean run: "
            f"{payload}")
