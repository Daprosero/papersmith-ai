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
        self.assertEqual(sorted(payload["code"]), ["check-report", "roster"])

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

VALID_REPORT = """# Audit: a subject, one surface

## Ranked findings

### F1. A set restated in more places than it is derived

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: doctrine wrong
- Code side: `engine/host.mjs:320`
- Doctrine side: `SKILL.md:243`
- Detail: the running host names more members than the table does.

## Not adjudicable

### F2. A declared value with no consumer anywhere

- Move: 0
- Evidence: CONFIRMED by execution
- Adjudication: not adjudicable
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
