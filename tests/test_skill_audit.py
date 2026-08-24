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
import hashlib
import json
import os
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
STAGES_HEADER = "| Stage | Models | Demands |"

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


#: The stage-2 skip reason `check-report` accepts as the degenerate,
#: nothing-reachable exemption from driving. Copied here rather than
#: imported, exactly like every other fixture literal in this file: a
#: fixture importing the value it is meant to check against would make the
#: check vacuous.
DRIVE_STAGE_RESERVED_SKIP = "no reachable surface (stage 1)"

#: The one `## Undecidable` entry every fixture below carries alongside the
#: reserved stage-2 skip. Non-empty, and its sole entry's `- Kind:` is
#: `no-closed-roster` -- the exact measurement `check-report`'s hardening
#: demands before it will honour the reserved skip at all.
UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY = (
    "- Kind: no-closed-roster\n"
    "- Rung: readers\n")


def stage_outcomes_block(overrides=None,
                         default="skipped: not exercised by this fixture"):
    """Render `## Stage outcomes` from the real stages table in `SKILL.md`,
    never from a list hand-typed inside this file.

    `overrides` maps a stage id (as the table names it) to the outcome text
    that stage's row carries; any stage the roster names but `overrides`
    does not is rendered with `default`. This is the mechanism the design
    calls for so a stage inserted into the table propagates to every
    fixture through one helper, rather than through four hand-edited
    literal blocks that guarantee the same breakage at the next insertion.
    """
    cli = audit_cli_module()
    roster = cli.stage_roster(doctrine_text())
    overrides = overrides or {}
    lines = ["## Stage outcomes", ""]
    for stage_id, _ in roster:
        lines.append(f"- Stage: {stage_id}: {overrides.get(stage_id, default)}")
    return "\n".join(lines) + "\n"


def move_outcomes_block(overrides=None,
                        default="skipped: not exercised by this fixture"):
    """Render `## Move outcomes` from the real moves table in `SKILL.md`,
    never from a list hand-typed inside this file. W1's exact pattern for
    `stage_outcomes_block`, applied to moves: a move inserted into the
    table (Move 10, here) propagates to every fixture through this one
    helper, rather than through every hand-edited literal block that
    guarantees the same breakage at the next insertion.
    """
    cli = audit_cli_module()
    roster = cli.move_roster(doctrine_text())
    overrides = overrides or {}
    lines = ["## Move outcomes", ""]
    for move_id in roster:
        lines.append(f"- Move: {move_id}: {overrides.get(move_id, default)}")
    return "\n".join(lines) + "\n"


def report_with_integrity(body, schema=None):
    """Prepend `## Report integrity` to a report fixture's `body`, right
    after its title line, with a `- Self-digest:` computed through the
    shipped `report_self_digest()` -- never hand-typed, and never a shipped
    report copied and hand-edited. Mirrors `stage_outcomes_block`'s own
    discipline: build fixtures in a box, through the mechanism under test,
    not beside it.

    `schema` defaults to the shipped `REPORT_SCHEMA_VERSION`; a caller
    testing the predates/postdates path passes an explicit older or newer
    integer, or omits the whole section by not calling this at all.
    """
    cli = audit_cli_module()
    version = cli.REPORT_SCHEMA_VERSION if schema is None else schema
    lines = body.splitlines(keepends=True)
    insert_at = 1
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    placeholder = ("## Report integrity\n\n"
                  f"- Schema: skill-audit-report/{version}\n"
                  "- Self-digest: sha256:0\n\n")
    draft = "".join(lines[:insert_at]) + placeholder + "".join(lines[insert_at:])
    digest = cli.report_self_digest(draft)
    return draft.replace("- Self-digest: sha256:0\n",
                         f"- Self-digest: {digest}\n", 1)


def resign(text):
    """Recompute and re-stamp a report fixture's own `- Self-digest:` after
    a test has mutated some unrelated part of its body, so the specific
    shape violation under test is never buried under an incidental digest
    mismatch the mutation happened to cause.

    Never used to build a tamper-detection fixture itself: those construct
    their own deliberate mismatch and must not be resigned back into
    agreement -- that would be testing nothing.
    """
    cli = audit_cli_module()
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if re.match(r"^-\s*Self-digest:\s*\S+\s*$", line.strip()):
            lines[index] = "- Self-digest: sha256:0"
            digest = cli.report_self_digest("\n".join(lines))
            lines[index] = f"- Self-digest: {digest}"
            return "\n".join(lines)
    raise AssertionError(
        "resign() called on text with no '- Self-digest:' line to replace")


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
        # `os` arrived with the `driver` step-kind's constructed environment:
        # `os.environ` is read to build a child env from declared *names*
        # intersected with `DRIVER_ENV_ALLOWLIST`, never passed wholesale.
        # `uuid` arrived with the ignorance control gate's seeded marker, a
        # nonce that must never collide with a real driver's own output.
        permitted = {"__future__", "argparse", "fnmatch", "hashlib", "json",
                     "os", "pathlib", "re", "shutil", "subprocess", "sys",
                     "uuid"}
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
            sorted(numbered), list(range(0, 11)),
            "the table must carry exactly one row per move 0 through 10, with no "
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


#: `## How the moves fail`'s own header -- read the same way every other
#: documented table in this file is, never restated as a hand-typed list of
#: rows beside it.
HOW_MOVES_FAIL_HEADER = "| Failure | Requirement |"


class RemoteRungSmokeRuleTests(unittest.TestCase):
    """The smoke rule: one row in `## How the moves fail`, service-blind.

    No new `REPORT_SHAPE` key, no new heading -- that table is already
    "each of these has already cost a phase; each is a requirement, not a
    caveat," which is exactly what this is.
    """

    def _rows(self):
        tables = markdown_table_rows(doctrine_text(), HOW_MOVES_FAIL_HEADER)
        self.assertEqual(len(tables), 1, "one 'How the moves fail' table, exactly")
        return tables[0]

    def test_a_row_demands_the_smoke_block_over_a_full_run(self):
        rows = self._rows()
        matches = [row for row in rows
                  if "run.smoke" in row[1] and "run-config.json" in row[1]]
        self.assertEqual(
            len(matches), 1,
            f"expected exactly one row demanding the run.smoke block; found "
            f"{len(matches)} in {rows}")
        requirement = matches[0][1]
        self.assertIn("smoke_module", requirement)
        self.assertIn("smoke_function", requirement)

    def test_the_smoke_rule_declares_no_epoch_or_pilot_scale_dial(self):
        rows = self._rows()
        matches = [row for row in rows if "run.smoke" in row[1]]
        self.assertEqual(len(matches), 1)
        requirement = matches[0][1]
        self.assertIn(
            "no epoch or pilot-scale dial", requirement,
            "the smoke rule must state, in its own words, that it "
            "introduces no epoch or pilot-scale dial")

    def test_the_smoke_vocabulary_stays_off_the_forge_floor(self):
        for word in ("smoke", "job", "mode", "run-config.json", "module",
                     "function", "kwargs", "requiredEvidence"):
            with self.subTest(word=word):
                self.assertNotIn(word.lower(), FORGE_VOCABULARY_FLOOR)


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
#:
#: A cleanup proof walks the box's own subtree, never the whole of this
#: directory, which is a working area holding gigabytes of unrelated sibling
#: work. The two walks answer the identical question — a path can only sit
#: under a box if it sits under that box — but the wide one sha256s every
#: unrelated file only to discard it, and two runs walking the same shared tree
#: contend over it.
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

        Scoped to shipped source (`.md`/`.py`/`.json`), the same filter
        `test_no_floor_word_appears_in_the_skill_itself` above already
        uses, and for the same reason: an unfiltered `rglob("*")` also
        matches compiled bytecode under `__pycache__/` -- present only
        AFTER a subprocess has actually run this skill's own CLI once (this
        test's own `roster_json` call above does exactly that), so this
        failure is intermittent by nature: absent on a clean checkout,
        present on a second run. `.pyc` magic bytes are not valid UTF-8
        (measured: 0x61 under Python 3.9, 0xCB under 3.12 -- both fail
        `str.decode`), and this test's subject is what the auditor's own
        SOURCE restates, never what a bytecode cache happens to contain.
        Catching the decode error instead of scoping the glob would let a
        genuinely unreadable SHIPPED file pass unnoticed, which is not the
        same lesson.
        """
        _, payload = roster_json(PD_SPEC, PD)
        auditor = sorted(
            path for path in SKILL_ROOT.rglob("*")
            if path.is_file() and path.suffix in (".md", ".py", ".json"))
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
                         ["check-report", "reading-diff", "roster",
                          "sensitivity", "structure", "walkthrough"])

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

#: `VALID_REPORT`'s stage-outcome text, by stage id -- the reserved skip on
#: stage 2 and the renumbered reasons on 3-5. Fed through
#: `stage_outcomes_block` rather than hand-typed as a `## Stage outcomes`
#: block, so a stage inserted into the real table shifts this fixture along
#: with it instead of leaving a stale, unrenumbered literal behind.
VALID_REPORT_STAGE_OVERRIDES = {
    "0": "ran",
    "1": "ran",
    "2": f"skipped: {DRIVE_STAGE_RESERVED_SKIP}",
    "3": "skipped: no blind reading pair compared in this pass",
    "4": "skipped: no differential drive run in this pass",
    "5": "skipped: no transcript partition run in this pass",
}

#: `VALID_REPORT`'s move-outcome text, by move id. Fed through
#: `move_outcomes_block` rather than hand-typed as a `## Move outcomes`
#: block, so a move inserted into the real table (Move 10, W10) propagates
#: to this fixture automatically instead of leaving a stale literal behind.
VALID_REPORT_MOVE_OVERRIDES = {
    "0": "ran",
    "1": "skipped: no from-zero build declared for this surface",
    "2": "skipped: not driven from disk in this pass",
    "3": "skipped: no external boundary crossed in this pass",
    "4": "skipped: no installed dependency read in this pass",
    "5": "skipped: no live probe attempted, no consent sought",
    "6": "skipped: no lock inverted in this pass",
    "7": "skipped: single-harness count only, not compared",
    "8": "skipped: no ordered user-mode flow driven in this pass",
    "9": "skipped: no supplied reading pair compared in this pass",
    "textual": "ran",
}

#: The body `VALID_REPORT` is built from, before `## Report integrity` is
#: prepended and a fresh self-digest is stamped through the shipped
#: function. Kept as its own name because a handful of fixtures below need
#: to graft onto this exact shape without inheriting a *second*, unrelated
#: fixture's self-digest.
VALID_REPORT_BODY = f"""# Audit: a subject, one surface

## Frozen

- Digest: {VALID_REPORT_DIGEST}
- Subject: a subject, one surface
- Exclude: (none)

{move_outcomes_block(VALID_REPORT_MOVE_OVERRIDES)}
{stage_outcomes_block(VALID_REPORT_STAGE_OVERRIDES)}
## Ranked findings

### F1. A set restated in more places than it is derived

- Move: 0
- Evidence: CONFIRMED by execution
- Found by: one
- Adjudication: doctrine wrong
- Digest: {VALID_REPORT_DIGEST}
- Code side: `engine/host.mjs:320`
- Doctrine side: `SKILL.md:243`
- Detail: the running host names more members than the table does.

## Not adjudicable

### F2. A declared value with no consumer anywhere

- Move: 0
- Evidence: CONFIRMED by execution
- Found by: one
- Adjudication: not adjudicable
- Digest: {VALID_REPORT_DIGEST}
- Code side: `engine/metrics.ts:3`
- Doctrine side: `engine/host.mjs:319`
- Detail: build-or-delete, and the choice costs something either way.

## Undecidable

{UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY}
## Computed-value provenance

## Disputed severity

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

#: `VALID_REPORT_BODY`, with `## Report integrity` prepended and a real,
#: freshly-computed self-digest -- never hand-typed. Every test below that
#: mutates this text and expects anything other than `tampered` must route
#: the mutated text through `resign()` first (most `check()` helpers below
#: do this once, for every caller, rather than at each call site).
VALID_REPORT = report_with_integrity(VALID_REPORT_BODY)


class ReportShapeTests(BoxMixin, unittest.TestCase):
    """A shape enforced only by prose is a hand-maintained roster.

    Which is the class this skill exists to find, so the shape is enforced by a
    process that exits non-zero.
    """

    def check(self, text, name="report.md"):
        box = getattr(self, "_box", None) or self.make_box("report")
        self._box = box
        path = self.write(box, name, resign(text))
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
            "stage-outcomes": ("## Stage outcomes", "## Stage progress"),
            "undecidable": ("## Undecidable", "## Undecided"),
            "not-adjudicable": ("## Not adjudicable", "## Not applicable"),
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


class FoundByTests(BoxMixin, unittest.TestCase):
    """`- Found by:` is the independence axis, held to no default exactly
    the way `- Evidence:` is: a missing marker is never read as `one`, the
    one value that would make an uncorroborated finding read as
    corroborated without anybody having said so.
    """

    def check(self, text, name="report.md"):
        box = getattr(self, "_box", None) or self.make_box("found_by")
        self._box = box
        path = self.write(box, name, resign(text))
        result = run_cli("check-report", str(path))
        return result, json.loads(result.stdout)

    def test_finding_without_found_by_is_rejected(self):
        result, payload = self.check(VALID_REPORT, name="baseline.md")
        self.assertEqual(
            result.returncode, 0,
            "the baseline fixture must itself be valid before this test "
            f"removes anything from it: {payload}")
        broken = VALID_REPORT.replace("- Found by: one\n", "", 1)
        result, payload = self.check(broken, name="missing-found-by.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"] if v["item"] == "found-by"]
        self.assertTrue(
            any("F1" in v["where"] for v in violations),
            f"a finding with no '- Found by:' line must be rejected and "
            f"must name the finding: {violations}")

    def test_found_by_accepts_both_one_not_compared(self):
        for value in ("both", "one", "not-compared"):
            with self.subTest(value=value):
                text = VALID_REPORT.replace(
                    "- Found by: one\n", f"- Found by: {value}\n", 1)
                result, payload = self.check(text, name=f"found-by-{value}.md")
                self.assertEqual(result.returncode, 0, payload)

    def test_found_by_rejects_unknown_value(self):
        text = VALID_REPORT.replace(
            "- Found by: one\n", "- Found by: mostly\n", 1)
        result, payload = self.check(text, name="found-by-unknown.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertIn("found-by", [v["item"] for v in payload["violations"]])


class SeverityVocabularyTests(unittest.TestCase):
    """No severity ladder anywhere in the skill directory.

    A closed vocabulary stated by hand inside the validator -- `CRITICAL`,
    `WARNING`, `SUGGESTION` -- is the exact defect class this skill exists
    to find. `## Disputed severity` records both positions verbatim instead,
    with no ranking of its own.
    """

    LADDER = re.compile(r"CRITICAL|WARNING|SUGGESTION", re.IGNORECASE)
    BARE_WORD = re.compile(r"severity", re.IGNORECASE)
    ALLOWED_PHRASE = re.compile(r"disputed[ _-]severity", re.IGNORECASE)

    def _offenders(self):
        offenders = []
        shipped = sorted(
            path for path in SKILL_ROOT.rglob("*")
            if path.is_file() and path.suffix in (".md", ".py", ".json"))
        self.assertNotEqual(shipped, [], "no shipped files found to check")
        for path in shipped:
            for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1):
                if self.LADDER.search(line):
                    offenders.append((path.name, lineno, line.strip()))
                    continue
                remainder = self.ALLOWED_PHRASE.sub("", line)
                if self.BARE_WORD.search(remainder):
                    offenders.append((path.name, lineno, line.strip()))
        return offenders

    def test_only_the_disputed_severity_axis_carries_the_word(self):
        self.assertEqual(
            self._offenders(), [],
            "the only occurrences of severity vocabulary in the skill "
            "directory may be the 'Disputed severity' heading and its "
            "REPORT_SHAPE marker; a standalone ladder word is the exact "
            "defect class this skill exists to find")


class DisputedSeverityTests(BoxMixin, unittest.TestCase):
    """`## Disputed severity` demands nothing when empty -- `VALID_REPORT`
    already proves an empty section is accepted. Non-empty means exactly
    two `- Position:` lines per dispute, each carrying a `file:line`
    citation, verbatim, with no ranking.
    """

    def check(self, text, name="report.md"):
        box = getattr(self, "_box", None) or self.make_box("disputed")
        self._box = box
        path = self.write(box, name, resign(text))
        result = run_cli("check-report", str(path))
        return result, json.loads(result.stdout)

    def _insert(self, block):
        needle = "## Disputed severity\n\n## Clean, stated as results"
        self.assertIn(needle, VALID_REPORT,
                     "the fixture's own shape must carry an empty "
                     "'## Disputed severity' section to graft onto")
        return VALID_REPORT.replace(
            needle, f"## Disputed severity\n\n{block}\n"
                    "## Clean, stated as results", 1)

    def test_an_unpaired_position_is_rejected(self):
        text = self._insert(
            "- Position: Drive A calls this blocking, per "
            "`engine/host.mjs:320`.\n")
        result, payload = self.check(text, name="unpaired.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertIn("disputed-severity",
                      [v["item"] for v in payload["violations"]])

    def test_a_position_with_no_citation_is_rejected(self):
        text = self._insert(
            "- Position: Drive A calls this blocking.\n"
            "- Position: Drive B calls this cosmetic, per `SKILL.md:243`.\n")
        result, payload = self.check(text, name="no-citation.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertIn("disputed-severity",
                      [v["item"] for v in payload["violations"]])

    def test_two_positions_each_with_a_citation_is_accepted(self):
        text = self._insert(
            "- Position: Drive A calls this blocking, per "
            "`engine/host.mjs:320`.\n"
            "- Position: Drive B calls this cosmetic, per `SKILL.md:243`.\n")
        result, payload = self.check(text, name="paired.md")
        self.assertEqual(result.returncode, 0, payload)


class ForbiddenSupportTests(BoxMixin, unittest.TestCase):
    """Four things a report may never lean on, each of which cost a phase here."""

    def check(self, text, name):
        box = getattr(self, "_box", None) or self.make_box("support")
        self._box = box
        result = run_cli(
            "check-report", str(self.write(box, name, resign(text))))
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
#: list held inside the tool: this fixture's synthetic move exists nowhere in
#: `audit_cli.py`, and the requirement still appears. Numbered far past any
#: move this skill will ever ship rather than one past the last real one: a
#: fixture numbered `last + 1` collides the next time a move is added, and it
#: has already had to be renumbered twice, each time silently proving less
#: than it claimed until someone noticed.
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
| 9. Compare two supplied readings of one prose surface by mechanical diff, and never let the comparison close | `reading-diff` | `tests/test_skill_audit.py` |
| 97. A move that exists only in this fixture, to prove the roster is derived and never hardcoded | `doctrine` | `tests/test_skill_audit.py` |
| Read every artifact's opening paragraphs against its own frontmatter and its own shipped files | `doctrine` | no lock — irreducibly textual, and carried anyway |
"""


class MoveOutcomesTests(BoxMixin, unittest.TestCase):
    """`## Move outcomes` is enforced against a roster derived from
    `SKILL.md`'s own moves table, never a literal list inside the tool.
    """

    def check(self, text, name="report.md", extra=()):
        box = getattr(self, "_box", None) or self.make_box("move-outcomes")
        self._box = box
        path = self.write(box, name, resign(text))
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
        """A move that exists only in a fixture file, never in
        `audit_cli.py`, is still required — proof the roster comes from
        parsing the table this run was pointed at, not from a literal held
        inside the tool.
        """
        box = self.make_box("derived-roster")
        self._box = box
        moves_path = self.write(box, "moves.md", MOVES_TABLE_PLUS_ONE)
        # VALID_REPORT's `## Move outcomes` carries moves 0-9 and `textual`
        # only; it names nothing for the fixture's move 97.
        result, payload = self.check(
            VALID_REPORT, name="missing-move-97.md",
            extra=("--moves", str(moves_path)))
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "move-outcomes"]
        self.assertTrue(
            any("move 97" in v["detail"] for v in violations),
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
        path = self.write(box, name, resign(text))
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
        return report_with_integrity(f"""# Audit: a subject, re-derived

## Frozen

- Digest: {digest}
- Subject: {subject}
- Exclude: (none)

{move_outcomes_block(VALID_REPORT_MOVE_OVERRIDES)}
{stage_outcomes_block(VALID_REPORT_STAGE_OVERRIDES)}
## Ranked findings

### F1. A finding for the re-derivation fixture

- Move: 0
- Evidence: CONFIRMED by execution
- Found by: not-compared
- Adjudication: doctrine wrong
- Digest: {digest}
- Code side: `a.py:1`
- Doctrine side: `SKILL.md:1`
- Detail: only the subject-level digest is under test here.

## Not adjudicable

## Undecidable

{UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY}
## Computed-value provenance

## Disputed severity

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
""")

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


class ReportIntegrityGateTests(BoxMixin, unittest.TestCase):
    """W9: a report carries a self-digest, distinctly named from the
    subject's own `## Frozen` digest, and `check-report` classifies every
    report into exactly one of `valid` / `tampered` / `predates the
    schema` -- never a fourth outcome, and never a collapse of the last
    two into one.
    """

    def check(self, text, name="report.md"):
        """Deliberately never resigns: every test here is about the gate
        itself, so a digest mismatch (or absence) must reach `check-report`
        exactly as constructed.
        """
        box = getattr(self, "_box", None) or self.make_box("identity")
        self._box = box
        path = self.write(box, name, text)
        result = run_cli("check-report", str(path))
        try:
            return result, json.loads(result.stdout)
        except json.JSONDecodeError:
            raise AssertionError(f"not JSON: {result.stdout!r} / {result.stderr!r}")

    # -- valid ------------------------------------------------------------

    def test_a_freshly_signed_report_is_valid(self):
        result, payload = self.check(VALID_REPORT, name="valid.md")
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["violations"], [])

    # -- predates the schema -----------------------------------------------

    def test_no_section_at_all_predates_the_schema(self):
        result, payload = self.check(VALID_REPORT_BODY, name="no-section.md")
        self.assertEqual(result.returncode, 2, payload)
        self.assertEqual(payload["status"], "predates-the-schema")
        self.assertNotIn("violations", payload)

    def test_an_empty_section_predates_the_schema(self):
        lines = VALID_REPORT_BODY.splitlines(keepends=True)
        text = "".join(lines[:2]) + "## Report integrity\n\n" + "".join(lines[2:])
        result, payload = self.check(text, name="empty-section.md")
        self.assertEqual(result.returncode, 2, payload)
        self.assertEqual(payload["status"], "predates-the-schema")

    def test_the_predates_refusal_names_the_remedy(self):
        result, payload = self.check(VALID_REPORT_BODY, name="predates-remedy.md")
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("supersede", payload["error"].lower())
        self.assertIn("read it by hand", payload["error"].lower())

    def test_an_older_schema_version_predates_the_schema(self):
        text = report_with_integrity(VALID_REPORT_BODY, schema=0)
        result, payload = self.check(text, name="older-schema.md")
        self.assertEqual(result.returncode, 2, payload)
        self.assertEqual(payload["status"], "predates-the-schema")
        self.assertIn("supersede", payload["error"].lower())

    def test_a_newer_schema_version_postdates_the_schema(self):
        text = report_with_integrity(VALID_REPORT_BODY, schema=999)
        result, payload = self.check(text, name="newer-schema.md")
        self.assertEqual(result.returncode, 2, payload)
        self.assertEqual(payload["status"], "postdates-the-schema")

    # -- tampered -----------------------------------------------------------

    def test_a_digest_mismatch_is_tampered_never_predates(self):
        broken = VALID_REPORT.replace(
            "the running host names more members than the table does.",
            "the running host names FEWER members than the table does.", 1)
        self.assertNotEqual(broken, VALID_REPORT, "the mutation must land")
        result, payload = self.check(broken, name="digest-mismatch.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertNotIn("status", payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "report-integrity"]
        self.assertTrue(violations, payload)

    def test_the_tampered_refusal_names_the_remedy_and_never_a_repair(self):
        broken = VALID_REPORT.replace(
            "the running host names more members than the table does.",
            "a mutated sentence with a different digest entirely.", 1)
        result, payload = self.check(broken, name="tampered-remedy.md")
        self.assertEqual(result.returncode, 1, payload)
        detail = payload["violations"][0]["detail"].lower()
        self.assertIn("superseded", detail)
        self.assertIn("do not", detail)

    def test_schema_present_self_digest_absent_is_tampered_not_predates(self):
        """The reconciliation's load-bearing case: deleting only the
        `- Self-digest:` line must not buy escape into the unjudged
        `predates-the-schema` bucket.
        """
        digest_line = next(
            line for line in VALID_REPORT.splitlines()
            if line.strip().startswith("- Self-digest:"))
        broken = VALID_REPORT.replace(digest_line + "\n", "", 1)
        self.assertNotEqual(broken, VALID_REPORT)
        result, payload = self.check(broken, name="schema-only.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertNotIn("status", payload)
        self.assertIn("report-integrity", [v["item"] for v in payload["violations"]])
        detail = payload["violations"][0]["detail"].lower()
        self.assertIn("tampered", detail)
        self.assertIn("not predates-the-schema", detail)

    def test_self_digest_present_schema_absent_is_tampered_not_predates(self):
        """The mirror case: deleting only `- Schema:` is the same defect."""
        schema_line = next(
            line for line in VALID_REPORT.splitlines()
            if line.strip().startswith("- Schema:"))
        broken = VALID_REPORT.replace(schema_line + "\n", "", 1)
        self.assertNotEqual(broken, VALID_REPORT)
        result, payload = self.check(broken, name="digest-only.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertNotIn("status", payload)
        self.assertIn("report-integrity", [v["item"] for v in payload["violations"]])

    def test_two_self_digest_lines_is_unprobeable(self):
        digest_line = next(
            line for line in VALID_REPORT.splitlines()
            if line.strip().startswith("- Self-digest:"))
        broken = VALID_REPORT.replace(
            digest_line, digest_line + "\n" + digest_line, 1)
        result, payload = self.check(broken, name="duplicated-digest.md")
        self.assertEqual(result.returncode, 2, payload)
        self.assertEqual(payload["status"], "unprobeable")
        self.assertIn("which one is the claim", payload["error"])

    def test_no_repair_or_recompute_flag_exists(self):
        flags = subcommand_surface(CLI, "build_parser").get("check-report", ())
        for flag in flags:
            with self.subTest(flag=flag):
                self.assertNotRegex(
                    flag.lower(), r"repair|recompute|resign|fix",
                    "check-report must expose no flag that recomputes or "
                    "rewrites a stored '- Self-digest:' in place")

    # -- canonicalization / exclusion ---------------------------------------

    def test_digest_excludes_its_own_line_regardless_of_its_value(self):
        cli = audit_cli_module()
        original_digest = cli.report_self_digest(VALID_REPORT)
        digest_line = next(
            line for line in VALID_REPORT.splitlines()
            if line.strip().startswith("- Self-digest:"))
        swapped = VALID_REPORT.replace(
            digest_line, "- Self-digest: sha256:" + "f" * 64, 1)
        self.assertEqual(
            cli.report_self_digest(swapped), original_digest,
            "the self-digest line's own value must never affect the "
            "digest computed over the rest of the report")

    def test_blanking_the_line_instead_of_removing_it_changes_the_digest(self):
        """Q9 step 4 is load-bearing: a blanked '- Self-digest:' line no
        longer matches the exclusion pattern at all, so it stays inside
        the hashed content and the digest must move.
        """
        cli = audit_cli_module()
        digest_line = next(
            line for line in VALID_REPORT.splitlines()
            if line.strip().startswith("- Self-digest:"))
        blanked = VALID_REPORT.replace(digest_line, "- Self-digest:", 1)
        self.assertNotEqual(
            cli.report_self_digest(blanked), cli.report_self_digest(VALID_REPORT))

    def test_trailing_newline_drift_does_not_change_the_digest(self):
        cli = audit_cli_module()
        self.assertEqual(
            cli.report_self_digest(VALID_REPORT),
            cli.report_self_digest(VALID_REPORT + "\n\n\n"))

    def test_crlf_drift_does_not_change_the_digest(self):
        cli = audit_cli_module()
        crlf = VALID_REPORT.replace("\n", "\r\n")
        self.assertEqual(
            cli.report_self_digest(VALID_REPORT), cli.report_self_digest(crlf))

    # -- position -------------------------------------------------------------

    def test_report_integrity_must_be_the_first_heading(self):
        lines = VALID_REPORT.splitlines(keepends=True)
        integrity_start = next(
            i for i, line in enumerate(lines) if line.strip() == "## Report integrity")
        integrity_end = next(
            i for i in range(integrity_start + 1, len(lines))
            if lines[i].startswith("## "))
        section = "".join(lines[integrity_start:integrity_end])
        rest = "".join(lines[:integrity_start]) + "".join(lines[integrity_end:])
        # Graft the whole '## Report integrity' block in immediately after
        # '## Frozen', instead of before it -- still present, still a
        # single well-formed section, just not first.
        moved = rest.replace(
            "## Frozen\n\n", "## Frozen\n\n" + section + "\n", 1)
        self.assertNotEqual(moved, VALID_REPORT)
        text = resign(moved)
        result, payload = self.check(text, name="misplaced.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "report-integrity"]
        self.assertTrue(
            any("first" in v["detail"] for v in violations), violations)

    # -- inversion: the only reachability proof ------------------------------

    def test_inversion_one_character_change_is_caught_and_restore_confirmed(self):
        cli = audit_cli_module()
        box = self.make_box("inversion")
        path = self.write(box, "report.md", VALID_REPORT)
        original_sha256 = hashlib.sha256(
            path.read_bytes()).hexdigest()

        mutated = VALID_REPORT.replace(
            "the running host names more members than the table does.",
            "the running host names more members than the table doet.", 1)
        self.assertNotEqual(mutated, VALID_REPORT, "the one-character edit must land")
        path.write_text(mutated, encoding="utf-8")
        result = run_cli("check-report", str(path))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "report-integrity"]
        self.assertTrue(violations, "the one-character mutation must be caught")

        # Restore by the exact inverse of the edit just made, confirmed by
        # content digest -- never a blind rewrite and never `git checkout
        # --`, which cannot distinguish a reverted mutation from work never
        # made. This file is a test fixture, not a git-tracked path, so the
        # inverse here is the literal inverse text edit plus a sha256
        # equality check against the pre-mutation bytes.
        path.write_text(VALID_REPORT, encoding="utf-8")
        restored_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(restored_sha256, original_sha256)
        result = run_cli("check-report", str(path))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["violations"], [])


class SchemaVersionDerivationTests(unittest.TestCase):
    """`SKILL.md` states the current schema version once, in prose; a lock
    holds `REPORT_SCHEMA_VERSION` to that exact sentence -- the same
    discipline `stage_model_total`'s own derivation lock already
    established for "Six model runs, total".
    """

    def test_the_stated_version_matches_the_constant(self):
        cli = audit_cli_module()
        match = re.search(r"skill-audit-report/(\d+)", doctrine_text())
        self.assertIsNotNone(
            match, "SKILL.md must state the current schema version somewhere")
        self.assertEqual(int(match.group(1)), cli.REPORT_SCHEMA_VERSION)


#: The network clause, wherever it appears -- captured up to its own
#: sentence-ending period so the lock can inspect what qualifies it
#: without caring about the surrounding prose.
NETWORK_CLAUSE = re.compile(r"no network\b[^.]*\.")


def driver_declaring_recipes():
    """Recipes under `references/probes/*.json` that declare a `driver`
    step, derived by grepping each file's raw text for the literal step
    kind -- never a hand-typed list of which recipe happens to hold one
    today. The lock below reads this as a set; it never reads its length.
    """
    return [path for path in sorted(PROBES.glob("*.json"))
            if '"kind": "driver"' in path.read_text(encoding="utf-8")]


class NetworkClauseDerivationTests(unittest.TestCase):
    """`SKILL.md`'s frontmatter `description` and `audit_cli.py`'s module
    docstring each state a network clause; this locks both, independently,
    to whether any shipped recipe under `references/probes/*.json`
    declares a `"kind": "driver"` step -- the same discipline
    `SchemaVersionDerivationTests` already established for the schema
    version sentence, and `test_the_model_count_sentence_names_the_derived_sum`
    established for the model-count sentence: read the real doctrine back
    and check it against a derived condition, never a mirrored literal.
    The lock reads only the set-level boolean; it never asserts which
    subcommand the clause must name (`skill-audit.first-run.json` serves
    `walkthrough`, and that mapping is not derivable from this recipe set).
    """

    def _assert_site(self, text, site_name):
        drivers = driver_declaring_recipes()
        clause = NETWORK_CLAUSE.search(text)
        self.assertIsNotNone(
            clause, f"{site_name} carries no network clause at all")
        if drivers:
            self.assertIn(
                "driver", clause.group(0),
                f"{site_name} states an unqualified 'no network' while "
                f"{drivers[0].name} declares a driver step")

    def test_skill_md_network_clause_matches_the_derived_condition(self):
        self._assert_site(doctrine_text(), "SKILL.md")

    def test_audit_cli_network_clause_matches_the_derived_condition(self):
        self._assert_site(audit_cli_module().__doc__, "audit_cli.py")


class HistoricalReportRecordTests(unittest.TestCase):
    """The historical `audit-proposal-deliberation-operations.md` report is
    a record, never a fixture: `9ffcda9`'s falsification of it -- adding a
    stage row and an `## Undecidable` entry it never had, so it would keep
    validating under a schema change -- is reverted, pinned, and never
    retro-fitted with `## Report integrity`.
    """

    #: `sha256` of the report's content at `9ffcda9~1`, i.e. before W1's
    #: falsifying edit -- confirmed at apply time against
    #: `git show 9ffcda9~1:<path>` and pinned here so any future edit at
    #: all, including a well-meant retro-fit of `## Report integrity`,
    #: turns this test red.
    PRE_FALSIFICATION_SHA256 = (
        "a3f01c3596f51126f6569b8b945e260fad0227be97c74a7bbf5893308d370719")

    def test_the_report_is_byte_identical_to_its_pre_falsification_content(self):
        actual = hashlib.sha256(REPORT.read_bytes()).hexdigest()
        self.assertEqual(
            actual, self.PRE_FALSIFICATION_SHA256,
            "a report is a record; supersede it, do not edit it -- this "
            "includes adding '## Report integrity' after the fact")

    def test_no_other_archived_report_carries_both_frozen_and_findings(self):
        """W9's own enumeration, re-verified: exactly one file under
        `openspec/changes/**/*.md` carries both `## Frozen` and
        `## Ranked findings` -- the one already known and reverted above.
        A hit beyond that one would need its own row in the design before
        this unit could be considered complete; finding a second one here
        is itself the discovery, not a silent pass.
        """
        hits = []
        for path in sorted((FORGE / "openspec" / "changes").rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            if "## Frozen" in text.splitlines() and \
                    "## Ranked findings" in text.splitlines():
                hits.append(path)
        self.assertEqual(hits, [REPORT])


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
                # [W4] The one `structure` invocation now drives a real
                # external `claude -p` process; `claude -p` is not
                # reproducible run to run (accepted in the design's own
                # risk register), so a genuine inability to look (e.g. a
                # bounded timeout, exit 2) is an honest outcome here
                # alongside 0/1, for this one command only -- never a
                # crash, and this is a documented invocation genuinely
                # *running*, not standing in for one.
                #
                # [W10] The one `sensitivity` invocation points at this
                # skill's own layout, which declares no computed-value
                # table of its own -- the honest, deterministic
                # "no-closed-roster" result, exit 2, documented as such in
                # usage.md rather than papered over with a fixture.
                if "structure" in invocation:
                    allowed = (0, 1, 2)
                elif "sensitivity" in invocation:
                    allowed = (2,)
                else:
                    allowed = (0, 1)
                self.assertIn(
                    result.returncode, allowed,
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

    def test_the_shipped_report_is_classified_as_predating_the_shape(self):
        """W9: this report was written before `## Report integrity`
        existed, and commit `9ffcda9`'s edit adding a stage row and an
        `## Undecidable` entry to it -- so it would keep validating under
        a schema change -- is reverted. A record and a fixture cannot be
        the same file: this one is now a record, classified `predates the
        schema`, never held to perpetual current-schema validity.

        Strictly stronger than the assertion it replaces: it fails if the
        classification silently drifts to `valid` (a retro-fitted marker)
        or to `tampered` (the era fact colliding with the tamper fact),
        not only if the report stops parsing.
        """
        result = run_cli("check-report", str(REPORT))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2, payload)
        self.assertEqual(payload["status"], "predates-the-schema", payload)
        self.assertNotIn(
            "violations", payload,
            "a report that was not judged must not carry a judgment's own "
            "vocabulary")

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

        `run_box_step` and `ignorance_control_gate` joined the exemption
        with the `driver` step-kind: both write only inside the box
        `run_structure` already owns (a driver step's `cwd`, and the
        ignorance control gate's own seeded marker), never into the
        subject, and `test_a_structure_run_leaves_the_subject_and_its_
        ground_untouched` above is what actually proves that, by bytes.

        `run_sensitivity`, `materialize_subject_copy`, `vary_by_absence`,
        and `restore_exact_bytes` joined the exemption with Move 10: each
        writes only inside `run_sensitivity`'s own box (the subject copy
        Move 10 perturbs), never into the subject, and
        `test_a_sensitivity_run_leaves_the_subject_untouched` below is
        what actually proves that, by bytes.
        """
        box_lifecycle_exemption = {
            "run_structure", "run_walkthrough", "erase_box",
            "run_box_step", "ignorance_control_gate", "run_sensitivity",
            "materialize_subject_copy", "vary_by_absence",
            "restore_exact_bytes"}
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

{move_outcomes_block(VALID_REPORT_MOVE_OVERRIDES)}
{stage_outcomes_block(VALID_REPORT_STAGE_OVERRIDES)}
## Ranked findings

### F1. A finding whose own digest disagrees with the frozen one

- Move: 0
- Evidence: CONFIRMED by execution
- Found by: not-compared
- Adjudication: doctrine wrong
- Digest: {digest_b}
- Code side: `a.py:1`
- Doctrine side: `SKILL.md:1`
- Detail: planted for this test -- the two digests are deliberately unequal.

## Not adjudicable

## Undecidable

{UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY}
## Computed-value provenance

## Disputed severity

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
        path = self.write(box, "mismatch.md", report_with_integrity(report))
        result = run_cli("check-report", str(path))
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"] if v["item"] == "frozen"]
        self.assertTrue(
            any("F1" in v["where"] for v in violations),
            f"a finding's digest disagreeing with '## Frozen' must be "
            f"rejected and must name the finding: {violations}")


#: The canonical env-var name the lock below checks each of the three
#: sites against -- never imported by the sites themselves. Each of
#: `FrozenPayloadTests.test_structure_payload_carries_frozen`,
#: `StructureSelfProbeTests.test_the_shipped_recipe_drives_a_real_external_process`,
#: and `SKILL.md`'s own obligation text hardcodes this name as its own
#: literal, so the three can drift independently and the lock is the
#: thing that would notice. The bare-uppercase-noun-phrase shape follows
#: `IMPLEMENTATION_PROPOSALS` in `tests/test_proposal_implementation.py`.
LIVE_DRIVER_ENV_VAR = "SKILL_AUDIT_LIVE_DRIVER"


class LiveDriverGateNameLockTests(unittest.TestCase):
    """The opt-in gate's env-var name is pinned identical across the three
    sites that must agree on it: `FrozenPayloadTests
    .test_structure_payload_carries_frozen`'s own `os.environ` read,
    `StructureSelfProbeTests
    .test_the_shipped_recipe_drives_a_real_external_process`'s own
    `os.environ` read, and `SKILL.md`'s recorded obligation text. A rename
    at exactly one site breaks this lock, naming that site -- the same
    discipline `SchemaVersionDerivationTests` established for a numeral,
    applied here to a literal name instead.
    """

    def test_the_gate_name_is_identical_across_all_three_sites(self):
        frozen_src = function_source(
            Path(__file__), "test_structure_payload_carries_frozen")
        selfprobe_src = function_source(
            Path(__file__),
            "test_the_shipped_recipe_drives_a_real_external_process")
        doctrine = doctrine_text()

        self.assertIn(
            LIVE_DRIVER_ENV_VAR, frozen_src,
            "test_structure_payload_carries_frozen does not read "
            f"{LIVE_DRIVER_ENV_VAR}")
        self.assertIn(
            LIVE_DRIVER_ENV_VAR, selfprobe_src,
            "test_the_shipped_recipe_drives_a_real_external_process does "
            f"not read {LIVE_DRIVER_ENV_VAR}")
        self.assertIn(
            LIVE_DRIVER_ENV_VAR, doctrine,
            f"SKILL.md does not record the obligation to run with "
            f"{LIVE_DRIVER_ENV_VAR}=1")


class FrozenPayloadTests(unittest.TestCase):
    """`frozen` travels in every subcommand's own payload, not only
    `roster`'s. Driven for real, against this skill's own shipped recipes,
    never through a fixture built only for this assertion.
    """

    def test_roster_payload_carries_frozen(self):
        _, payload = roster_json(SELF_SPEC, SKILL_ROOT)
        self._assert_frozen_shape(payload)

    def test_structure_payload_carries_frozen(self):
        """[W4] Still driven for real, against the shipped recipe -- which
        now invokes a real external `claude -p` driver, not reproducible
        run to run (accepted in the design's own risk register). An
        `Unprobeable` payload carries no `frozen` key at all: it is a
        different shape, an inability to look, not a verdict. Either
        honest outcome is accepted here; only a crash is not.
        """
        # Opt-in gate, new to this repository -- there is no
        # `skipUnless`/decorator precedent for it here, only the plain
        # `self.skipTest` mechanics this class already uses for an
        # `Unprobeable` result. The literal name is hardcoded (not shared
        # via a Python constant) so this site, its sibling below, and
        # SKILL.md's own recorded obligation can drift independently, and
        # `LiveDriverGateNameLockTests` catches it if they do.
        if not os.environ.get("SKILL_AUDIT_LIVE_DRIVER"):
            self.skipTest(
                "spawns a real external `claude -p` process; opt in with "
                "SKILL_AUDIT_LIVE_DRIVER=1")
        result, payload = structure_json(
            STRUCTURE_SPEC, SKILL_ROOT, repo=FORGE, extra=("--timeout", "45"))
        if result.returncode == 2:
            self.assertIn("error", payload)
            return
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

    def structure_script_box(self, name):
        """A box for a fixture's own build/escape script, outside both
        `subject` and the `_skill_audit_*` namespace `make_box` cleans up
        globally. See `build_script`'s docstring for why both matter.
        """
        box = BOXES / f"_structure_scripts_{name}"
        if box.exists():
            self._erase_structure_box(box)
        box.mkdir(parents=True)
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

        Lives in a box that is a *sibling* of `subject`, never inside it.
        The from-zero side may never reference the subject at all -- not
        even by accident, through a fixture's own script sitting inside the
        directory the audit is comparing against. Placing the script beside
        `subject` instead of inside it keeps that soundness condition real
        rather than exempting the test fixtures from it.

        Housed under the `_structure_scripts_` namespace, cleaned up via
        `_erase_structure_box` rather than `make_box`: `make_box`'s own
        cleanup asserts the *entire* `_skill_audit_*` namespace is empty at
        each box's turn, an invariant written for exactly one box per test.
        A second `_skill_audit_*` box would trip that assertion on the
        first of the two cleanups to run, for a reason that has nothing to
        do with either box actually leaking.
        """
        # `scripts-{short}` rather than `{short}_scripts`, and a distinct
        # `_structure_scripts_` prefix rather than `_skill_audit_`: the
        # literal-scan refusal checks for the subject's own path as a
        # *substring*, so nothing derived from `short` may sit immediately
        # after the same prefix subject's own box used.
        short = subject.name.removeprefix("_skill_audit_")
        scripts = self.structure_script_box(short)
        lines = ["import pathlib, sys", "root = pathlib.Path(sys.argv[1])"]
        for relative, content in files.items():
            lines.append(
                f"(root / {relative!r}).parent.mkdir(parents=True, exist_ok=True)")
            lines.append(
                f"(root / {relative!r}).write_text({content!r}, encoding='utf-8')")
        return self.write(scripts, "build.py", "\n".join(lines) + "\n")

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
        box = self.structure_box(surface)
        subject = self.make_subject(
            "escape_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        # The escape script lives in a sibling box, never inside `subject`
        # -- the from-zero side may not reference the subject at all, so
        # the escape has to reach it by relative navigation from the box
        # (its own cwd), exactly the shape a real accidental escape would
        # take, never by an argv part that literally spells the subject's
        # path out.
        escape_script = self.write(
            self.structure_script_box("escape"), "escape.py",
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[1]).write_text('escaped', encoding='utf-8')\n")
        steps = [["python3", str(escape_script),
                  f"../{subject.name}/escaped.txt"]]
        self.assertEqual(box.parent, subject.parent,
                         "the relative escape below assumes box and subject "
                         "are siblings under implementations/")
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
        after = audit_cli_module().tree_digest(box)
        self.assertEqual(
            after, {},
            "the box must be content-empty in a fresh walk of its own "
            "subtree -- the same proof every other box's cleanup uses in "
            "this file, never `git status`")
        self.assertFalse(box.exists())


class DriverStepKindTests(StructureBoxMixin, unittest.TestCase):
    """The `driver` step-kind, the from-zero side's subject-reference
    refusal, and the ignorance control gate that precedes both.
    """

    def test_an_unknown_step_kind_is_unprobeable(self):
        surface = "unknown_kind"
        self.structure_box(surface)
        subject = self.make_subject(
            "unknown_kind_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        steps = [{"kind": "mystery", "argv": ["mkdir", "-p", "{box}/build"]}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("mystery", payload["error"])

    def test_a_driver_step_builds_from_zero_and_agrees(self):
        surface = "driver_happy"
        self.structure_box(surface)
        subject = self.make_subject(
            "driver_happy_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        source = self.write(
            self.structure_script_box("driver_source"), "a.txt", "x\n")
        steps = [
            {"kind": "driver", "argv": ["mkdir", "-p", "{box}/build"],
             "env": ["PATH"], "brief": "stand up the build root"},
            ["cp", str(source), "{box}/build/a.txt"],
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["outcome"], "agree")

    def test_a_driver_step_populates_the_ignorance_block(self):
        """The enforceable half of `## User drive`, machine-emitted: a
        report transcribes this rather than narrating it.
        """
        surface = "driver_ignorance"
        self.structure_box(surface)
        subject = self.make_subject(
            "driver_ignorance_subject", declared=["a.txt"],
            disk_files={"a.txt": "x\n"})
        source = self.write(
            self.structure_script_box("driver_ignorance_source"), "a.txt", "x\n")
        steps = [
            {"kind": "driver", "argv": ["mkdir", "-p", "{box}/build"],
             "env": ["PATH"]},
            ["cp", str(source), "{box}/build/a.txt"],
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        ignorance = payload["ignorance"]
        self.assertEqual(ignorance["controlGate"], "passed")
        self.assertEqual(ignorance["argv"], ["mkdir", "-p", f"{payload['containment']['box']}/build"])
        self.assertEqual(ignorance["envNames"], ["PATH"])
        self.assertTrue(ignorance["argv0RealPath"].startswith("/"))
        self.assertTrue(ignorance["boxDigestBefore"].startswith("sha256:"))
        self.assertTrue(ignorance["boxDigestAfter"].startswith("sha256:"))
        self.assertNotEqual(
            ignorance["boxDigestBefore"], ignorance["boxDigestAfter"],
            "the box held nothing before the driver ran and its own build "
            "directory after; the two digests must disagree")

    def test_an_exec_only_recipe_emits_no_driver_in_the_ignorance_block(self):
        surface = "no_driver"
        self.structure_box(surface)
        subject = self.make_subject(
            "no_driver_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        script = self.build_script(subject, {"a.txt": "x\n"})
        spec = self.make_recipe(
            subject, surface, [["python3", str(script), "{box}/build"]])
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        ignorance = payload["ignorance"]
        self.assertEqual(ignorance["controlGate"], "passed")
        self.assertIsNone(ignorance["argv"])
        self.assertEqual(ignorance["envNames"], [])

    def test_a_step_naming_the_subject_token_is_refused(self):
        surface = "subject_token"
        self.structure_box(surface)
        subject = self.make_subject(
            "subject_token_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        steps = [{"kind": "driver", "argv": ["echo", "{subject}"], "env": []}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("subject-reference", payload["error"])

    def test_a_step_with_the_subjects_literal_path_is_refused(self):
        """The exact shape of the tar recipe's own defect: no `{subject}`
        token anywhere, the path spelled out by hand instead.
        """
        surface = "subject_literal"
        self.structure_box(surface)
        subject = self.make_subject(
            "subject_literal_subject", declared=["a.txt"],
            disk_files={"a.txt": "x\n"})
        steps = [["echo", f"HEAD:{subject.relative_to(FORGE).as_posix()}"]]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("subject-reference", payload["error"])

    def test_a_git_step_naming_a_different_path_still_runs(self):
        """Only a step referencing *the subject* is refused. A `git`
        command naming somewhere else entirely -- not through the token,
        not by a literal match -- is an ordinary from-zero step.
        """
        surface = "git_elsewhere"
        self.structure_box(surface)
        subject = self.make_subject(
            "git_elsewhere_subject", declared=["a.txt"],
            disk_files={"a.txt": "x\n"})
        source = self.write(
            self.structure_script_box("git_elsewhere_source"), "a.txt", "x\n")
        steps = [
            {"kind": "driver",
             "argv": ["git", "-C", "{repoRoot}", "rev-parse", "--show-toplevel"],
             "env": ["PATH"]},
            {"kind": "driver", "argv": ["mkdir", "-p", "{box}/build"],
             "env": ["PATH"]},
            ["cp", str(source), "{box}/build/a.txt"],
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["outcome"], "agree")

    def test_an_env_name_outside_the_allowlist_is_refused(self):
        surface = "env_outside"
        self.structure_box(surface)
        subject = self.make_subject(
            "env_outside_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        steps = [{"kind": "driver", "argv": ["mkdir", "-p", "{box}/build"],
                  "env": ["PATH", "SSH_AUTH_SOCK"]}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("SSH_AUTH_SOCK", payload["error"])

    def test_driver_argv0_inside_the_repo_but_outside_the_subject_is_refused(self):
        surface = "driver_repo_local"
        self.structure_box(surface)
        subject = self.make_subject(
            "driver_repo_local_subject", declared=["a.txt"],
            disk_files={"a.txt": "x\n"})
        scripts = self.structure_script_box("driver_repo_local")
        local_driver = scripts / "local_driver.sh"
        local_driver.write_text(
            "#!/bin/sh\nmkdir -p \"$1\"\n", encoding="utf-8")
        local_driver.chmod(0o755)
        steps = [{"kind": "driver", "argv": [str(local_driver), "{box}/build"],
                  "env": ["PATH"]}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("driver-not-external", payload["error"])

    def test_driver_cwd_escaping_the_box_is_refused(self):
        surface = "driver_cwd_escape"
        self.structure_box(surface)
        subject = self.make_subject(
            "driver_cwd_escape_subject", declared=["a.txt"],
            disk_files={"a.txt": "x\n"})
        steps = [{"kind": "driver", "argv": ["mkdir", "-p", "build"],
                  "cwd": "../..", "env": ["PATH"]}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("driver.cwd", payload["error"])

    def test_ignorance_control_gate_stalls_when_exclude_hides_the_seed(self):
        """The control is `exclude`-aware, which is what makes it more
        than ceremony: an `exclude` broad enough to hide the seed would
        make every box look empty and the ignorance claim true by
        construction. `["*"]` is exactly that pattern.
        """
        surface = "control_gate_blind"
        self.structure_box(surface)
        subject = self.make_subject(
            "control_gate_blind_subject", declared=["a.txt"],
            disk_files={"a.txt": "x\n"})
        steps = [{"kind": "driver", "argv": ["mkdir", "-p", "{box}/build"],
                  "env": ["PATH"]}]
        # Excludes only the control gate's own seed directory -- never `["*"]`,
        # which would also blind `disk_set`/`declared_set` and trip the
        # unrelated "zero members" refusal before the gate is ever reached.
        spec = self.make_recipe(
            subject, surface, steps, exclude=["__audit_ignorance_control__/*"])
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("ignorance-control-stalled", payload["error"])

    def test_user_is_allowlisted(self):
        """W4: `USER` joined `DRIVER_ENV_ALLOWLIST` -- declaring it must
        never be refused as out-of-allowlist.
        """
        surface = "user_allowlisted"
        self.structure_box(surface)
        subject = self.make_subject(
            "user_allowlisted_subject", declared=["a.txt"],
            disk_files={"a.txt": "x\n"})
        source = self.write(
            self.structure_script_box("user_allowlisted"), "a.txt", "x\n")
        steps = [
            {"kind": "driver", "argv": ["mkdir", "-p", "{box}/build"],
             "env": ["PATH", "USER"]},
            ["cp", str(source), "{box}/build/a.txt"],
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(sorted(payload["ignorance"]["envNames"]),
                         ["PATH", "USER"])

    def test_out_of_allowlist_refusal_names_the_measurement(self):
        surface = "env_measurement"
        self.structure_box(surface)
        subject = self.make_subject(
            "env_measurement_subject", declared=["a.txt"],
            disk_files={"a.txt": "x\n"})
        steps = [{"kind": "driver", "argv": ["mkdir", "-p", "{box}/build"],
                  "env": ["PATH", "SSH_AUTH_SOCK"]}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("env -i", payload["error"])

    def test_declared_but_absent_env_name_appears_in_env_missing(self):
        """A name declared but not present in the parent process must be
        transcribed, sorted, into `envMissing` -- never silently dropped.
        """
        surface = "env_missing"
        self.structure_box(surface)
        subject = self.make_subject(
            "env_missing_subject", declared=["a.txt"], disk_files={"a.txt": "x\n"})
        source = self.write(
            self.structure_script_box("env_missing"), "a.txt", "x\n")
        steps = [
            {"kind": "driver", "argv": ["mkdir", "-p", "{box}/build"],
             "env": ["PATH", "TERM"]},
            ["cp", str(source), "{box}/build/a.txt"],
        ]
        spec = self.make_recipe(subject, surface, steps)
        saved = os.environ.pop("TERM", None)
        try:
            result, payload = structure_json(spec, subject, repo=FORGE)
        finally:
            if saved is not None:
                os.environ["TERM"] = saved
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["ignorance"]["envMissing"], ["TERM"])

    def test_a_brief_naming_a_declared_path_is_refused(self):
        """A driver step's argv naming a literal the subject's own declared
        file table lists is refused, `kind=brief-names-the-shape` -- never
        recorded, never driven.
        """
        surface = "brief_names_shape"
        self.structure_box(surface)
        subject = self.make_subject(
            "brief_names_shape_subject", declared=["only-mentioned-here.txt"],
            disk_files={"only-mentioned-here.txt": "x\n"})
        steps = [{"kind": "driver",
                  "argv": ["echo", "go read only-mentioned-here.txt"],
                  "env": ["PATH"]}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("brief-names-the-shape", payload["error"])
        self.assertIn("only-mentioned-here.txt", payload["error"])

    def test_a_problem_shaped_brief_naming_no_subject_file_passes(self):
        surface = "brief_problem_shaped"
        self.structure_box(surface)
        subject = self.make_subject(
            "brief_problem_shaped_subject", declared=["only-mentioned-here.txt"],
            disk_files={"only-mentioned-here.txt": "x\n"})
        source = self.write(
            self.structure_script_box("brief_problem_shaped"), "a.txt", "x\n")
        steps = [
            {"kind": "driver",
             "argv": ["echo", "audit a tool against its own documentation"],
             "cwd": "build", "env": ["PATH"]},
            ["cp", str(source), "{box}/build/only-mentioned-here.txt"],
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)

    def test_the_forbidden_roster_widens_when_the_subject_declares_a_new_row(self):
        """Proof of derivation, never a hand-list: a row added to the
        subject's own declared table is refused in the brief without any
        edit to the guard itself.
        """
        surface = "brief_roster_derived"
        self.structure_box(surface)
        subject = self.make_subject(
            "brief_roster_derived_subject",
            declared=["a.txt", "a-brand-new-declared-row.txt"],
            disk_files={"a.txt": "x\n", "a-brand-new-declared-row.txt": "x\n"})
        steps = [{"kind": "driver",
                  "argv": ["echo", "mentions a-brand-new-declared-row.txt"],
                  "env": ["PATH"]}]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = structure_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("brief-names-the-shape", payload["error"])
        self.assertIn("a-brand-new-declared-row.txt", payload["error"])


class DriverArgvRecipeTests(unittest.TestCase):
    """W4: the shipped recipe's `fromZero` is a driver invocation, and the
    skill still names no CLI of its own.
    """

    def test_the_shipped_recipe_declares_no_git_archive_or_tar(self):
        recipe = json.loads(STRUCTURE_SPEC.read_text(encoding="utf-8"))
        for step in recipe["fromZero"]["steps"]:
            argv = step["argv"] if isinstance(step, dict) else step
            with self.subTest(argv=argv):
                self.assertTrue(
                    all(part not in ("git", "archive", "tar") for part in argv),
                    "the recipe's fromZero side must no longer be a copy "
                    f"operation: {argv}")

    def test_the_shipped_recipe_declares_a_driver_step(self):
        recipe = json.loads(STRUCTURE_SPEC.read_text(encoding="utf-8"))
        steps = recipe["fromZero"]["steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["kind"], "driver")
        self.assertEqual(steps[0]["argv"][0], "claude")

    def test_the_skill_names_no_vendor_cli(self):
        """The skill itself declares no default driver; the recipe alone
        names one. Grepped for common vendor CLI names in `audit_cli.py`'s
        own source -- never in the recipe, which is where a declaration
        belongs.
        """
        source = CLI.read_text(encoding="utf-8")
        for vendor in ("codex", "opencode", '"claude"', "'claude'"):
            with self.subTest(vendor=vendor):
                self.assertNotIn(vendor, source)

    def test_the_declared_argv0_resolves_outside_repo_and_subject(self):
        """The externality check stays a predicate, never a pinned value:
        no version string of the resolved `claude` binary is hard-coded
        anywhere in `audit_cli.py` or the shipped recipe.
        """
        cli = audit_cli_module()
        real = cli.shutil.which("claude")
        self.assertIsNotNone(real, "this environment has no `claude` on PATH")
        resolved = Path(real).resolve()
        self.assertFalse(FORGE in resolved.parents or resolved == FORGE)
        self.assertFalse(SKILL_ROOT in resolved.parents or resolved == SKILL_ROOT)
        source = CLI.read_text(encoding="utf-8")
        recipe_text = STRUCTURE_SPEC.read_text(encoding="utf-8")
        version_marker = re.search(r"\d+\.\d+\.\d+", str(resolved.parent.name))
        if version_marker:
            self.assertNotIn(version_marker.group(0), source)
            self.assertNotIn(version_marker.group(0), recipe_text)


class StructureSelfProbeTests(unittest.TestCase):
    """The shipped recipe, pointed at the auditor's own layout.

    Uncommitted work in this slice legitimately reads as `builder-broken`
    against `HEAD`; that is documented as accurate, not papered over.
    """

    def test_the_shipped_recipe_drives_a_real_external_process(self):
        """[W4] The shipped recipe's `fromZero.steps` is now one `driver`
        step invoking the real, external `claude -p` CLI with a
        problem-only brief -- never a copy operation, and never a step
        naming the subject by its own path. `claude -p` is not
        reproducible run to run (accepted in the design's own risk
        register), so this test holds only what is true on every run:

        - the old `subject-reference` refusal (the tar recipe's own
          defect) never fires again -- that class of failure is gone;
        - the result is one of two honest outcomes: a real `structure`
          verdict (exit 0, `outcome` a real arithmetic result) or a
          genuine inability to look (exit 2, e.g. a bounded timeout) --
          never a crash, and never the old copy-recipe's defect;
        - a sibling skill is never touched, whichever of the two holds.

        Bounded at 45s for the driver step itself (`--timeout`), well
        under `run_cli`'s own 90s ceiling for this one invocation.
        """
        # Opt-in gate, new to this repository -- see
        # `FrozenPayloadTests.test_structure_payload_carries_frozen` for
        # why the literal name is hardcoded here rather than shared.
        if not os.environ.get("SKILL_AUDIT_LIVE_DRIVER"):
            self.skipTest(
                "spawns a real external `claude -p` process; opt in with "
                "SKILL_AUDIT_LIVE_DRIVER=1")
        cli = audit_cli_module()
        before = {name: cli.tree_digest(SKILL_ROOT.parent / name)
                 for name in SIBLING_SKILLS_TO_CHECK}
        result = run_cli("structure", "--subject", str(SKILL_ROOT),
                         "--spec", str(STRUCTURE_SPEC), "--repo-root", str(FORGE),
                         "--timeout", "45", timeout=90)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise AssertionError(
                f"structure exited {result.returncode} without JSON on "
                f"stdout.\nstdout={result.stdout!r}\nstderr={result.stderr!r}")
        after = {name: cli.tree_digest(SKILL_ROOT.parent / name)
                for name in SIBLING_SKILLS_TO_CHECK}
        self.assertEqual(
            before, after,
            "structure reads the subject and builds its own box; it must "
            "never touch a sibling skill, whatever the driver did")
        if result.returncode == 0:
            self.assertIn(payload["outcome"], STRUCTURE_OUTCOMES, payload)
        else:
            self.assertEqual(result.returncode, 2, payload)
            self.assertNotIn(
                "subject-reference", payload.get("error", ""),
                "the old tar recipe's defect must never fire again")


# ==========================================================================
# `the-audit-that-runs-what-it-claims`, Slice 3 -- `walkthrough`: an ordered
# recipe run against one shared box, exiting `0` for any verdict including a
# stall and `2` only when the flow itself could not be entered.
# ==========================================================================

STRUCTURE_OUTCOMES = ("agree", "disk-stale", "builder-broken",
                      "document-wrong", "three-way-divergence")

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
        after = audit_cli_module().tree_digest(box)
        self.assertEqual(
            after, {},
            "the box must be content-empty in a fresh walk of its own "
            "subtree -- the same proof every other box's cleanup uses in "
            "this file, never `git status`")
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


class WalkthroughStepRoleTests(WalkthroughBoxMixin, unittest.TestCase):
    """A step's `kind` defaults to `"gate"`; a `"setup"` step asserts nothing
    about the subject and must never be counted among gates that passed. A
    failing setup step names itself, not the subject, and exits `2` as
    `setup-failed` -- a void run has no unchecked gates, it has no run.
    """

    def test_passing_setup_step_not_counted_as_passed_gate(self):
        surface = "setup_passes"
        self.walkthrough_box(surface)
        subject = self.make_box("setup_passes_subject")
        steps = [
            {"argv": ["python3", "-c", "pass"], "role": "setup",
             "name": "stand up a fixture"},
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "a real gate"},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIsNone(payload["stall"], payload)
        self.assertEqual(payload["steps"][0]["outcome"], "setup-ok")
        self.assertEqual(payload["steps"][0]["role"], "setup")
        self.assertEqual(payload["steps"][1]["outcome"], "passed")
        self.assertEqual(payload["steps"][1]["role"], "gate")
        self.assertEqual(
            payload["gates"], {"declared": 1, "passed": 1},
            "the setup step must never be counted as a declared or passed "
            "gate")

    def test_failing_setup_step_exits_2_as_setup_failed_never_stalled(self):
        surface = "setup_fails"
        self.walkthrough_box(surface)
        subject = self.make_box("setup_fails_subject")
        steps = [
            {"argv": ["python3", "-c", "import sys; sys.exit(1)"],
             "role": "setup", "name": "a fixture that never stands up"},
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "never reached"},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertEqual(payload["status"], "setup-failed")
        self.assertEqual(payload["index"], 0)
        self.assertEqual(payload["name"], "a fixture that never stands up")
        self.assertIn("setup", payload["detail"])
        self.assertIsNone(
            payload["stall"],
            "a void run has no unchecked gates, it has no run")
        self.assertEqual(payload["unreached"], [])

    def test_setup_step_declaring_expect_is_unprobeable(self):
        """A real gate step keeps the recipe out of the separate
        no-bare-setup guard, so a failure here can only come from the
        expect-on-setup check itself, not from an unrelated overlapping one.
        """
        surface = "setup_with_expect"
        self.walkthrough_box(surface)
        subject = self.make_box("setup_with_expect_subject")
        steps = [
            {"argv": ["python3", "-c", "pass"], "expect": {"exit": 0},
             "role": "setup", "name": "asserts something anyway"},
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "a real gate, unreachable"},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("wrong label", payload["error"])

    def test_recipe_of_only_setup_steps_is_unprobeable(self):
        surface = "only_setup"
        self.walkthrough_box(surface)
        subject = self.make_box("only_setup_subject")
        steps = [
            {"argv": ["python3", "-c", "pass"], "role": "setup",
             "name": "stand up a fixture"},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("no gates", payload["error"])

    def test_role_defaults_to_gate_when_omitted(self):
        """Backward compatibility: a step with no `kind` behaves exactly as
        today -- it is a gate, counted in `gates.declared` and
        `gates.passed`.
        """
        surface = "kind_omitted"
        self.walkthrough_box(surface)
        subject = self.make_box("kind_omitted_subject")
        steps = [
            {"argv": ["python3", "-c", "import sys; sys.exit(0)"],
             "expect": {"exit": 0}, "name": "no kind declared"},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["steps"][0]["role"], "gate")
        self.assertEqual(payload["gates"], {"declared": 1, "passed": 1})

    def test_gates_counts_only_gate_kind_across_a_mixed_stall(self):
        """A failing gate after a passing setup step still reports the
        correct `declared`/`passed` split -- the setup step never inflates
        either count.
        """
        surface = "mixed_stall"
        self.walkthrough_box(surface)
        subject = self.make_box("mixed_stall_subject")
        steps = [
            {"argv": ["python3", "-c", "pass"], "role": "setup",
             "name": "stand up a fixture"},
            {"argv": ["python3", "-c", "import sys; sys.exit(1)"],
             "expect": {"exit": 0}, "name": "a real gate that stalls"},
        ]
        spec = self.make_recipe(subject, surface, steps)
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIsNotNone(payload["stall"], payload)
        self.assertEqual(payload["gates"], {"declared": 1, "passed": 0})


# ==========================================================================
# `the-audit-that-escalates-what-it-cannot-decide`, Slice 3 -- every note
# kind classified by a totality-checked partition, and an escalatable kind
# routed to a zero-model `candidateGates` probe before any reader is
# reached. `note()`/`stalled()` are the only ways an entry enters `notes[]`
# or a walkthrough `stall`, so the totality lock can scan their own call
# sites instead of trusting a second, hand-maintained roster.
# ==========================================================================

class EscalationPartitionTests(unittest.TestCase):
    """`ESCALATION_BUCKETS` classifies every `"kind":` a note can carry into
    exactly one of three buckets. A scan of literal `"kind":` strings would
    miss `run_roster`'s own `note(kind, ...)` call at its doctrine-status
    site, which passes a variable, not a constant -- and it would wrongly
    catch `stalled()`'s dicts, whose `kind` is a verdict, never an
    undecidability. So the totality lock (a) reads every kind `note()` can
    actually emit -- constant strings passed to `note()`, plus every kind
    named in `DOCTRINE_SIDE_NOTES` -- and holds each to exactly one bucket,
    and (c) refuses any note-shaped dict literal -- one carrying both a
    a `"kind"` key at all, since one word means one thing here --
    anywhere outside those two constructors. That last clause is what makes
    the totality total: a kind emitted by hand-building a note-shaped dict
    cannot be classified, and the lock fires on the bypass itself rather
    than trusting a second roster to have been updated.
    """

    def _module_tree(self):
        return ast.parse(CLI.read_text(encoding="utf-8"))

    def _function_def(self, tree, name):
        return next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == name), None)

    def _emitted_kinds(self, tree):
        kinds = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "note"):
                arg = node.args[0] if node.args else None
                for keyword in node.keywords:
                    if keyword.arg == "kind":
                        arg = keyword.value
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    kinds.add(arg.value)
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name)
                            and t.id == "DOCTRINE_SIDE_NOTES"
                            for t in node.targets)
                    and isinstance(node.value, ast.Dict)):
                for value in node.value.values:
                    if not isinstance(value, ast.Tuple) or not value.elts:
                        continue
                    first = value.elts[0]
                    if isinstance(first, ast.Constant) and isinstance(
                            first.value, str):
                        kinds.add(first.value)
        return kinds

    def test_every_emitted_kind_is_classified_in_exactly_one_bucket(self):
        cli = audit_cli_module()
        tree = self._module_tree()
        emitted = self._emitted_kinds(tree)
        self.assertTrue(
            emitted, "no kind was recovered from note() call sites at all; "
            "this test would pass on an empty partition by accident")
        buckets = cli.ESCALATION_BUCKETS
        classified = {}
        for bucket, kinds in buckets.items():
            for kind in kinds:
                classified.setdefault(kind, []).append(bucket)
        unclassified = sorted(kind for kind in emitted
                              if kind not in classified)
        self.assertEqual(
            unclassified, [],
            f"ESCALATION_BUCKETS classifies no bucket for: {unclassified}")
        multiply_classified = {kind: buckets for kind, buckets in
                               classified.items() if len(buckets) > 1}
        self.assertEqual(
            multiply_classified, {},
            f"a kind appears in more than one bucket: {multiply_classified}")

    def test_no_dict_literal_carries_a_kind_outside_note_and_stalled(self):
        tree = self._module_tree()
        note_def = self._function_def(tree, "note")
        stalled_def = self._function_def(tree, "stalled")
        self.assertIsNotNone(note_def, "audit_cli.py defines no note()")
        self.assertIsNotNone(stalled_def, "audit_cli.py defines no stalled()")
        exempt = set(ast.walk(note_def)) | set(ast.walk(stalled_def))
        offenders = []
        for node in ast.walk(tree):
            if node in exempt or not isinstance(node, ast.Dict):
                continue
            keys = {key.value for key in node.keys
                   if isinstance(key, ast.Constant)
                   and isinstance(key.value, str)}
            if "kind" in keys:
                offenders.append(node.lineno)
        self.assertEqual(
            offenders, [],
            f"a dict literal carrying a 'kind' key exists outside "
            f"note()/stalled() at line(s) {offenders}; one word means "
            f"one thing here, and every note enters through note()")

    def test_consequence_kind_not_independently_escalated(self):
        """Spec scenario: a `comparison-not-run` note produced solely
        because its originating surface was already escalatable must never
        appear in the escalatable list as a second, independent entry.
        """
        _, payload = roster_json(PD_SPEC, PD)
        self.assertIn(
            "comparison-not-run", [n["kind"] for n in payload["notes"]],
            "the fixture must actually produce a comparison-not-run note "
            "for this test to say anything")
        escalatable_kinds = [n["kind"] for n in payload["escalatable"]]
        self.assertNotIn(
            "comparison-not-run", escalatable_kinds,
            "comparison-not-run is a consequence, never independently "
            f"escalated: {escalatable_kinds}")
        self.assertTrue(
            escalatable_kinds,
            "the same fixture's no-closed-roster notes must still be "
            "escalatable, or this test cannot distinguish 'excluded "
            "correctly' from 'the list is just empty'")


class EscalationHintTests(unittest.TestCase):
    """Every escalatable note gains an `escalation` hint naming the
    zero-model probe able to decide it -- `rung: "probe"` only when the
    emitting recipe already declares `probe: "refusal"`, `"readers"`
    otherwise.
    """

    def test_probe_rung_selected_when_recipe_declares_refusal_probe(self):
        _, payload = roster_json(PD_SPEC, PD)
        self.assertTrue(payload["escalatable"], payload)
        for entry in payload["escalatable"]:
            with self.subTest(kind=entry["kind"]):
                self.assertEqual(entry["escalation"]["rung"], "probe")
                self.assertEqual(entry["escalation"]["needs"], "candidates")
                self.assertIsNotNone(entry["escalation"]["refusal"])

    def test_readers_rung_selected_when_recipe_declares_no_refusal_probe(self):
        cli = audit_cli_module()
        box = BOXES / "_skill_audit_escalation_readers"
        try:
            box.mkdir(parents=True, exist_ok=True)
            (box / "PROSE.md").write_text(
                "The set is ALPHA and BETA, stated in prose.\n",
                encoding="utf-8")
            spec = box / "recipe.json"
            spec.write_text(json.dumps({
                "surface": "s", "probe": "none",
                "doctrineSites": [{"path": "PROSE.md"}]}), encoding="utf-8")
            _, payload = roster_json(spec, box)
            self.assertTrue(payload["escalatable"], payload)
            for entry in payload["escalatable"]:
                with self.subTest(kind=entry["kind"]):
                    self.assertEqual(entry["escalation"]["rung"], "readers")
                    self.assertIsNone(entry["escalation"]["needs"])
                    self.assertIsNone(entry["escalation"]["refusal"])
        finally:
            for path in sorted(box.rglob("*"), reverse=True):
                path.unlink()
            box.rmdir()


class GateTokenTests(unittest.TestCase):
    """`{candidate}` is a fourth token, valid only inside
    `candidateGates.argv`; `STRUCTURE_TOKENS` is untouched.
    """

    def test_gate_tokens_is_structure_tokens_plus_candidate(self):
        cli = audit_cli_module()
        self.assertEqual(
            cli.GATE_TOKENS, cli.STRUCTURE_TOKENS | {"candidate"})

    def test_the_four_gate_tokens_interpolate(self):
        cli = audit_cli_module()
        result = cli.interpolate_gate_token(
            "{repoRoot}-{subject}-{box}-{candidate}",
            Path("/r"), Path("/s"), Path("/b"), "--alpha")
        self.assertEqual(result, "/r-/s-/b---alpha")

    def test_an_unknown_gate_token_is_unprobeable(self):
        cli = audit_cli_module()
        with self.assertRaises(cli.Unprobeable):
            cli.interpolate_gate_token(
                "{mystery}", Path("/r"), Path("/s"), Path("/b"), "--alpha")


class ControlGateTests(WalkthroughBoxMixin, unittest.TestCase):
    """`candidateGates` expands one declared `refusal` into an inverted
    control gate, first, then one gate per candidate. A live channel proves
    every candidate; a dead channel stalls at the control's own index and
    leaves every candidate `unreached` -- no candidate is ever reported
    accepted against a channel not proven capable of refusing.
    """

    def _flag_cli(self, box, name, refuses):
        """A subject that writes a refusal to stderr for an unknown flag,
        or never refuses at all, per `refuses`.
        """
        body = (
            "import sys\n"
            "known = {'--alpha', '--beta'}\n"
            "flag = sys.argv[1]\n")
        if refuses:
            body += (
                "if flag not in known:\n"
                "    sys.stderr.write('unrecognized arguments: ' + flag + "
                "'\\n')\n"
                "    sys.exit(2)\n")
        body += "print('accepted ' + flag)\n"
        self.write(box, name, body)

    def test_live_refusal_channel_control_passes(self):
        surface = "control_live"
        self.walkthrough_box(surface)
        subject = self.make_box("control_live_subject")
        self._flag_cli(subject, "flagcli.py", refuses=True)
        spec = subject / "walkthrough.json"
        spec.write_text(json.dumps({
            "surface": surface,
            "candidateGates": {
                "refusal": "unrecognized arguments",
                "argv": ["python3", "{subject}/flagcli.py", "{candidate}"],
                "candidates": ["--alpha", "--beta"],
            },
        }, indent=2), encoding="utf-8")
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIsNone(payload["stall"], payload)
        outcomes = [step["outcome"] for step in payload["steps"]]
        self.assertEqual(
            outcomes, ["passed", "passed", "passed"],
            "the control and both candidates must all pass on a live "
            "refusal channel")

    def test_dead_refusal_channel_stalls_at_control_candidates_unreached(self):
        surface = "control_dead"
        self.walkthrough_box(surface)
        subject = self.make_box("control_dead_subject")
        self._flag_cli(subject, "silentcli.py", refuses=False)
        spec = subject / "walkthrough.json"
        spec.write_text(json.dumps({
            "surface": surface,
            "candidateGates": {
                "refusal": "unrecognized arguments",
                "argv": ["python3", "{subject}/silentcli.py", "{candidate}"],
                "candidates": ["--alpha", "--beta"],
            },
        }, indent=2), encoding="utf-8")
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(
            payload["stall"]["index"], 0,
            "a program that never refuses stalls at the control's own "
            "index, not at a candidate")
        self.assertEqual(
            payload["unreached"], [1, 2],
            "every candidate must go unreached once the control itself "
            "could not be proven live")
        accepted = [step for step in payload["steps"][1:]
                   if step["outcome"] == "passed"]
        self.assertEqual(
            accepted, [],
            "a program that silently ignores unknown flags must never "
            "have a candidate reported as accepted")

    def test_candidategates_unknown_token_exits_2(self):
        surface = "unknown_token"
        self.walkthrough_box(surface)
        subject = self.make_box("unknown_token_subject")
        spec = subject / "walkthrough.json"
        spec.write_text(json.dumps({
            "surface": surface,
            "candidateGates": {
                "refusal": "unrecognized arguments",
                "argv": ["python3", "{mystery}/x.py", "{candidate}"],
                "candidates": ["--alpha"],
            },
        }, indent=2), encoding="utf-8")
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("unknown token", payload["error"])

    def test_candidate_with_shell_metacharacter_reaches_argv_literally(self):
        surface = "candidate_metachar"
        self.walkthrough_box(surface)
        subject = self.make_box("candidate_metachar_subject")
        self.write(subject, "echo_argv.py",
                  "import sys\n"
                  "arg = sys.argv[1]\n"
                  "if arg == '__AUDIT_CONTROL_NONCE__':\n"
                  "    sys.stderr.write('REFUSED: nonce not recognized\\n')\n"
                  "print('ARGV:' + arg)\n")
        marker = subject / "INJECTED"
        spec = subject / "walkthrough.json"
        spec.write_text(json.dumps({
            "surface": surface,
            "candidateGates": {
                "refusal": "REFUSED: nonce not recognized",
                "argv": ["python3", "{subject}/echo_argv.py", "{candidate}"],
                "candidates": ["; touch INJECTED #"],
            },
        }, indent=2), encoding="utf-8")
        result, payload = walkthrough_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["steps"][0]["outcome"], "passed",
                         "the control must pass so the candidate actually "
                         f"runs: {payload}")
        self.assertFalse(
            marker.exists(),
            "a shell metacharacter in a candidate must never reach a "
            "shell; it must arrive as one literal argv element")

    def test_documented_flag_surface_rerouted_not_read(self):
        """MOTIVATING CASE: a `no-closed-roster` note over a prose-stated
        flag list does not become a reading task. Each flag it names is
        driven as a real `walkthrough` gate instead, before any reader is
        ever invoked -- the half-caught case from the proposal, closed end
        to end.
        """
        box = self.make_box("documented_flags")
        self._flag_cli(box, "flagcli.py", refuses=True)
        self.write(box, "PROSE.md",
                  "The flags this tool accepts are `--alpha` and `--beta`, "
                  "stated here in prose rather than in a table.\n")
        roster_spec = self.recipe(
            box, surface="flags", probe="refusal",
            argv=["python3", "flagcli.py", "__AUDIT_NONCE__"], cwd=".",
            stream="stderr", exit=2,
            extract=r"unrecognized arguments: (?P<roster>.+)$", split=", ",
            doctrineSites=[{"path": "PROSE.md"}])
        result, payload = roster_json(roster_spec, box)
        self.assertEqual(result.returncode, 0, payload)
        no_closed = [n for n in payload["notes"]
                    if n["kind"] == "no-closed-roster"]
        self.assertTrue(no_closed, "the prose site must report no-closed-roster")
        escalatable = [n for n in payload["escalatable"]
                      if n["kind"] == "no-closed-roster"]
        self.assertTrue(escalatable, payload["escalatable"])
        self.assertEqual(escalatable[0]["escalation"]["rung"], "probe")

        # The model never reads PROSE.md for a verdict; it proposes the two
        # flags it names as candidates, and the tool decides by driving
        # them as real walkthrough gates -- no reader is ever invoked.
        proposed_candidates = ["--alpha", "--beta"]
        surface = "documented_flags_walk"
        self.walkthrough_box(surface)
        spec = box / "walkthrough.json"
        spec.write_text(json.dumps({
            "surface": surface,
            "candidateGates": {
                "refusal": "unrecognized arguments",
                "argv": ["python3", "{subject}/flagcli.py", "{candidate}"],
                "candidates": proposed_candidates,
            },
        }, indent=2), encoding="utf-8")
        walk_result, walk_payload = walkthrough_json(spec, box, repo=FORGE)
        self.assertEqual(walk_result.returncode, 0, walk_payload)
        self.assertIsNone(walk_payload["stall"], walk_payload)
        self.assertEqual(
            len(walk_payload["steps"]), 3,
            "the control gate plus one gate per documented flag")
        self.assertTrue(
            all(step["outcome"] == "passed" for step in walk_payload["steps"]),
            f"every documented flag must be driven as a real gate: "
            f"{walk_payload['steps']}")


# ==========================================================================
# Slice 6 (commit 4) -- `reading-diff`: a subcommand, not a flag and not a
# recipe field, comparing exactly two supplied readings of one prose surface
# by mechanical diff. Four independent barriers keep it away from
# `closed_seen`, the one boolean `run_roster` ever assigns `True` -- a
# supplied reading may propose a candidate; it may never close a comparison.
# ==========================================================================

class ReadingDiffTests(BoxMixin, unittest.TestCase):
    """`reading-diff` never sets `closed_seen`. Two readers agreeing proves
    the prose has one reading, never that it is closed, and `comparison`
    stays the literal `"not-run"` for a surface compared this way,
    permanently.
    """

    def _reading(self, box, name, surface, members, reader):
        return self.write(box, name, json.dumps({
            "surface": surface, "site": name, "members": members,
            "reader": reader}))

    def _run(self, surface, path_a, path_b):
        result = run_cli("reading-diff", "--surface", surface,
                         "--reading", str(path_a), "--reading", str(path_b))
        try:
            return result, json.loads(result.stdout)
        except json.JSONDecodeError:
            raise AssertionError(
                f"reading-diff exited {result.returncode} without JSON on "
                f"stdout.\nstdout={result.stdout!r}\nstderr={result.stderr!r}")

    def test_two_readers_agree_reports_single_reading(self):
        """Spec scenario: two readers agree."""
        box = self.make_box("reading_diff_agree")
        a = self._reading(box, "a.json", "flags",
                          ["--alpha", "--beta"], "reader-a")
        b = self._reading(box, "b.json", "flags",
                          ["--beta", "--alpha"], "reader-b")
        result, payload = self._run("flags", a, b)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["agreement"], "single-reading")
        self.assertEqual(payload["shared"], ["--alpha", "--beta"])
        self.assertEqual(payload["onlyIn"], {"a": [], "b": []})
        self.assertEqual(payload["comparison"], "not-run")
        self.assertEqual(payload["surface"], "flags")

    def test_divergent_readings_report_shared_and_only_in(self):
        box = self.make_box("reading_diff_divergent")
        a = self._reading(box, "a.json", "flags",
                          ["--alpha", "--beta"], "reader-a")
        b = self._reading(box, "b.json", "flags",
                          ["--beta", "--gamma"], "reader-b")
        result, payload = self._run("flags", a, b)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["agreement"], "divergent")
        self.assertEqual(payload["shared"], ["--beta"])
        self.assertEqual(payload["onlyIn"], {"a": ["--alpha"], "b": ["--gamma"]})
        self.assertEqual(payload["comparison"], "not-run")

    def test_a_count_of_readings_other_than_two_is_unprobeable(self):
        box = self.make_box("reading_diff_arity")
        a = self._reading(box, "a.json", "flags", ["--alpha"], "reader-a")
        result = run_cli("reading-diff", "--surface", "flags",
                         "--reading", str(a))
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "unprobeable")
        self.assertIn("exactly two", payload["error"])

    def test_payload_carries_a_frozen_digest_of_the_two_readings(self):
        box = self.make_box("reading_diff_frozen")
        a = self._reading(box, "a.json", "flags", ["--alpha"], "reader-a")
        b = self._reading(box, "b.json", "flags", ["--alpha"], "reader-b")
        _, payload = self._run("flags", a, b)
        self.assertIn("frozen", payload, f"payload carries no frozen: {payload}")
        frozen = payload["frozen"]
        self.assertEqual(set(frozen), {"digest", "exclude", "subject"})
        self.assertTrue(frozen["digest"].startswith("sha256:"), frozen)

    def test_comparison_field_is_literal_not_run(self):
        """B3, asserted as a constant, not a computed value: a scan for the
        string `"not-run"` anywhere in the function would also match a
        variable holding a computed verdict. Reading the emitted dict
        literal's own AST node distinguishes a constant from an expression.
        """
        tree = ast.parse(CLI.read_text(encoding="utf-8"))
        definition = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "run_reading_diff"),
            None)
        self.assertIsNotNone(definition, "audit_cli.py defines no run_reading_diff")
        emit_calls = [node for node in ast.walk(definition)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id == "emit"]
        self.assertEqual(len(emit_calls), 1,
                         "run_reading_diff must emit exactly once")
        dict_arg = emit_calls[0].args[0]
        self.assertIsInstance(dict_arg, ast.Dict)
        value = None
        for key, val in zip(dict_arg.keys, dict_arg.values):
            if isinstance(key, ast.Constant) and key.value == "comparison":
                value = val
        self.assertIsInstance(
            value, ast.Constant,
            "comparison must be a literal constant, never a computed "
            "expression -- a supplied reading may never make this field "
            "say anything but not-run")
        self.assertEqual(value.value, "not-run")

    def test_run_reading_diff_never_calls_doctrine_side_probe_code_side_or_finish(self):
        """B1, the AST lock: `run_reading_diff`'s own syntax subtree may
        never reference `doctrine_side`, `probe_code_side`, or `finish` --
        not a call, not an attribute, not a name -- because any of those
        would be the one path a supplied reading could reach `closed_seen`
        through.
        """
        tree = ast.parse(CLI.read_text(encoding="utf-8"))
        definition = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "run_reading_diff"),
            None)
        self.assertIsNotNone(definition, "audit_cli.py defines no run_reading_diff")
        forbidden = {"doctrine_side", "probe_code_side", "finish"}
        found = set()
        for node in ast.walk(definition):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
        offenders = forbidden & found
        self.assertEqual(
            offenders, set(),
            f"run_reading_diff reaches for {sorted(offenders)}; a supplied "
            "reading must never reach the one function that writes "
            "closed_seen")

    def test_closed_seen_assigned_at_exactly_one_site_fed_only_by_doctrine_side(self):
        """B2, the load-bearing barrier, held as a structural confirmation
        rather than assumed: `closed_seen = True` must occur at exactly one
        site in the whole module, that site must live inside `run_roster`,
        and the `if` that gates it must compare a name fed by `doctrine_side`'s
        own return value -- never a name a supplied reading could set.
        """
        tree = ast.parse(CLI.read_text(encoding="utf-8"))
        sites = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "closed_seen"
                    for t in node.targets)
            and isinstance(node.value, ast.Constant)
            and node.value.value is True]
        self.assertEqual(
            len(sites), 1,
            f"closed_seen = True must be assigned at exactly one site; "
            f"found {len(sites)}")

        run_roster_def = next(
            (n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "run_roster"), None)
        self.assertIsNotNone(run_roster_def, "audit_cli.py defines no run_roster")
        self.assertIn(
            sites[0], list(ast.walk(run_roster_def)),
            "the sole closed_seen = True site must live inside run_roster")

        parents = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        def ancestors(node):
            while node in parents:
                node = parents[node]
                yield node

        enclosing_if = next(
            (a for a in ancestors(sites[0]) if isinstance(a, ast.If)), None)
        self.assertIsNotNone(
            enclosing_if, "closed_seen = True must be gated by an if")
        self.assertIsInstance(enclosing_if.test, ast.Compare)
        self.assertIsInstance(enclosing_if.test.ops[0], ast.Eq)
        compared = enclosing_if.test.left
        self.assertIsInstance(
            compared, ast.Name,
            "the gate must compare a plain name, not an expression")
        status_name = compared.id

        fed_by_doctrine_side = any(
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "doctrine_side"
            and any(isinstance(t, ast.Tuple)
                    and any(isinstance(elt, ast.Name) and elt.id == status_name
                            for elt in t.elts)
                    for t in node.targets)
            for node in ast.walk(run_roster_def))
        self.assertTrue(
            fed_by_doctrine_side,
            f"{status_name!r}, compared by closed_seen's own guard, must "
            "itself be assigned from doctrine_side's own return value -- "
            "never from anything a supplied reading could set")

    def test_reading_superset_of_code_side_yields_no_unregistered_key(self):
        """B4, behavioural: a reading naming a strict superset of a real
        code side must never make `reading-diff` claim an `unregistered`
        verdict -- not even an empty one, which would read as "checked and
        found none" rather than "never checked at all". Driven as the real
        subcommand, never through a fixture standing in for it.
        """
        box = self.make_box("reading_diff_superset")
        real_code_side = ["roster", "check-report", "structure",
                          "walkthrough", "reading-diff"]
        superset = real_code_side + ["not-a-real-subcommand"]
        a = self._reading(box, "a.json", "subcommands", superset, "reader-a")
        b = self._reading(box, "b.json", "subcommands", superset, "reader-b")
        result, payload = self._run("subcommands", a, b)
        self.assertEqual(result.returncode, 0, payload)
        self.assertNotIn(
            "unregistered", payload,
            "reading-diff must never carry an unregistered key at all -- a "
            "supplied reading is a hypothesis, never a closed verdict")


class StageOutcomesTests(BoxMixin, unittest.TestCase):
    """`## Stage outcomes` mirrors `## Move outcomes` exactly, derived from a
    stages table in `SKILL.md` rather than a list hand-written inside the
    tool. Only a `ran` row demands the artifact its own `Demands` cell
    names; a `skipped` row demands nothing, which is what lets a
    zero-model audit stay valid.
    """

    def check(self, text, name="report.md"):
        box = getattr(self, "_box", None) or self.make_box("stage-outcomes")
        self._box = box
        path = self.write(box, name, resign(text))
        result = run_cli("check-report", str(path))
        return result, json.loads(result.stdout)

    def test_a_complete_roster_of_stage_outcomes_is_accepted(self):
        result, payload = self.check(VALID_REPORT)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["violations"], [])

    def test_a_stage_missing_its_row_is_named(self):
        broken = VALID_REPORT.replace(
            "- Stage: 4: skipped: no differential drive run in this pass\n",
            "", 1)
        result, payload = self.check(broken, name="missing-stage-4.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "stage-outcomes"]
        self.assertTrue(
            any("4" in v["detail"] for v in violations),
            f"removing stage 4's row must name stage 4: {violations}")

    def test_a_skipped_stage_row_with_an_empty_reason_is_rejected(self):
        broken = VALID_REPORT.replace(
            "- Stage: 5: skipped: no transcript partition run in this pass\n",
            "- Stage: 5: skipped:\n", 1)
        result, payload = self.check(broken, name="empty-stage-reason.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "stage-outcomes"]
        self.assertTrue(
            any("5" in v["detail"] for v in violations),
            f"an empty reason must still name stage 5: {violations}")

    def test_ran_stage_without_artifact_is_rejected(self):
        """Spec scenario: stage 3 declared `ran` with no `## Reading diff`
        section is rejected, naming stage 3.
        """
        broken = VALID_REPORT.replace(
            "- Stage: 3: skipped: no blind reading pair compared in this "
            "pass\n",
            "- Stage: 3: ran\n", 1)
        result, payload = self.check(broken, name="stage3-ran-no-artifact.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "reading-diff"]
        self.assertTrue(
            any("3" in v["detail"] for v in violations),
            f"stage 3 declared ran with no '## Reading diff' must be "
            f"rejected and must name stage 3: {violations}")

    def test_stage_two_ran_without_user_drive_artifact_is_rejected(self):
        """The `user-drive` conditional artifact, demanded structurally the
        same way `reading-diff` and `drives` already are: stage 2 declared
        `ran` with no `## User drive` section is rejected, naming stage 2.
        """
        broken = VALID_REPORT.replace(
            f"- Stage: 2: skipped: {DRIVE_STAGE_RESERVED_SKIP}\n",
            "- Stage: 2: ran\n", 1)
        result, payload = self.check(broken, name="stage2-ran-no-drive.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "user-drive"]
        self.assertTrue(
            any("2" in v["detail"] for v in violations),
            f"stage 2 declared ran with no '## User drive' must be "
            f"rejected and must name stage 2: {violations}")

    def test_zero_model_audit_is_valid(self):
        """[LOCK] Spec scenario: stages 0-1 `ran`, stage 2 `skipped` under
        the one reserved reason, stages 3-5 `skipped: <reason>` -- accepted.
        `VALID_REPORT` is already exactly this shape. Inverted immediately
        below by declaring stage 3 `ran` in the same fixture without its
        artifact, and confirmed rejected -- the inversion is
        `test_ran_stage_without_artifact_is_rejected` above, run against a
        `.replace()` of this same baseline text, and restoration is
        implicit: `VALID_REPORT` itself is never mutated, only a derived
        string is.
        """
        result, payload = self.check(VALID_REPORT, name="zero-model.md")
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["violations"], [])

    def test_stage_two_skip_reason_other_than_reserved_is_driver_required(self):
        """Spec scenario: a reachable-surface report cannot skip stage 2 for
        any reason of its own choosing. Any text other than the one reserved
        literal is rejected as `driver-required`, never accepted as
        equivalent -- even a reason that reads plausibly.
        """
        broken = VALID_REPORT.replace(
            f"- Stage: 2: skipped: {DRIVE_STAGE_RESERVED_SKIP}\n",
            "- Stage: 2: skipped: too expensive to drive this pass\n", 1)
        result, payload = self.check(broken, name="stage2-wrong-reason.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "driver-required"]
        self.assertTrue(
            any("2" in v["detail"] for v in violations),
            f"a non-reserved stage-2 skip reason must be rejected as "
            f"driver-required: {violations}")

    def test_stage_two_reserved_skip_with_empty_undecidable_is_rejected(self):
        """The gap the reconciliation found: design's per-entry check is
        vacuously true over an *empty* `## Undecidable` section, because a
        cleanly-decided surface never enters that section at all. A report
        claiming the reserved skip while `## Undecidable` carries no entries
        at all must still be rejected as `driver-required` -- the section
        being non-empty is part of the measurement, not a formality.
        """
        broken = VALID_REPORT.replace(
            f"{UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY}\n## Computed-value provenance\n\n## Disputed severity",
            "## Disputed severity", 1)
        self.assertNotEqual(broken, VALID_REPORT, "the graft must land")
        result, payload = self.check(broken, name="stage2-empty-undecidable.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "driver-required"]
        self.assertTrue(
            any("2" in v["detail"] for v in violations),
            f"the reserved skip over an empty '## Undecidable' must still "
            f"be rejected: {violations}")

    def test_stage_3_asymmetry_rejects_skill_less_finding_against_subject(self):
        broken = VALID_REPORT.replace(
            "- Detail: the running host names more members than the table "
            "does.\n",
            "- Detail: the running host names more members than the table "
            "does.\n"
            "- Drive: skill-less\n"
            "- Target: subject\n", 1)
        result, payload = self.check(broken, name="drives-asymmetry.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"] if v["item"] == "drives"]
        self.assertTrue(
            any("F1" in v["where"] for v in violations),
            f"a finding attributed to the skill-less drive naming the "
            f"subject as its target must be rejected: {violations}")

    def test_a_skill_less_finding_targeting_its_own_box_is_accepted(self):
        text = VALID_REPORT.replace(
            "- Detail: the running host names more members than the table "
            "does.\n",
            "- Detail: the running host names more members than the table "
            "does.\n"
            "- Drive: skill-less\n"
            "- Target: box\n", 1)
        result, payload = self.check(text, name="skill-less-own-box.md")
        self.assertEqual(result.returncode, 0, payload)

    def test_undecidable_kind_must_be_one_the_tool_can_emit(self):
        """The partition is enforced on the way in, not only on the way out.

        `EscalationPartitionTests` makes the partition total over what this
        tool emits. A report is written by hand, so a surface can be declared
        undecidable under a reason the tool has no way to produce, and a
        closed set with teeth on one side only is the shape this skill
        exists to find. A kind that is real but sits in a different bucket
        is refused for the same reason a made-up one is: a consequence is
        not a cause, and it has no prose left to re-read.
        """
        for invented in ("a-reason-nobody-emits", "comparison-not-run"):
            with self.subTest(kind=invented):
                text = VALID_REPORT.replace(
                    f"{UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY}\n## Computed-value provenance\n\n## Disputed severity",
                    f"{UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY}\n"
                    f"- Kind: {invented}\n"
                    "- Rung: readers\n\n"
                    "## Computed-value provenance\n\n"
                    "## Disputed severity", 1)
                self.assertNotEqual(text, VALID_REPORT, "the graft must land")
                result, payload = self.check(
                    text, name=f"undecidable-{invented}.md")
                self.assertEqual(result.returncode, 1, payload)
                self.assertIn(
                    "undecidable",
                    [v["item"] for v in payload["violations"]],
                    "a kind this tool cannot emit as escalatable must be "
                    "refused where the report claims it")

    def test_undecidable_probe_rung_requires_its_move_to_have_run(self):
        """Cross-section rule: an `## Undecidable` entry claiming
        `- Rung: probe` must name a move whose own `## Move outcomes` row
        is `ran`. `VALID_REPORT`'s move 9 is `skipped`, so naming it here
        is rejected; declaring move 9 `ran` in the same fixture is accepted.
        """
        with_entry = VALID_REPORT.replace(
            f"{UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY}\n## Computed-value provenance\n\n## Disputed severity",
            f"{UNDECIDABLE_NO_CLOSED_ROSTER_ENTRY}\n"
            "- Kind: no-closed-roster\n"
            "- Rung: probe\n"
            "- Probe: 9\n\n"
            "## Computed-value provenance\n\n"
            "## Disputed severity", 1)
        self.assertNotEqual(with_entry, VALID_REPORT, "the graft must land")

        result, payload = self.check(
            with_entry, name="undecidable-probe-move-skipped.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertIn("undecidable", [v["item"] for v in payload["violations"]])

        move_ran = with_entry.replace(
            "- Move: 9: skipped: no supplied reading pair compared in this "
            "pass\n",
            "- Move: 9: ran\n", 1)
        result, payload = self.check(
            move_ran, name="undecidable-probe-move-ran.md")
        self.assertEqual(result.returncode, 0, payload)

    def test_not_adjudicable_finding_under_ranked_findings_is_rejected(self):
        """Cross-section rule, mirrored: a `not adjudicable` finding cannot
        have two homes. `VALID_REPORT`'s F1 sits under '## Ranked findings'
        with adjudication `doctrine wrong`; promoting its adjudication to
        `not adjudicable` without moving it is rejected.
        """
        broken = VALID_REPORT.replace(
            "- Adjudication: doctrine wrong\n",
            "- Adjudication: not adjudicable\n", 1)
        result, payload = self.check(broken, name="not-adjudicable-wrong-home.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "not-adjudicable"]
        self.assertTrue(
            any("F1" in v["where"] for v in violations),
            f"F1's promoted adjudication must be rejected and must name "
            f"F1: {violations}")

    def test_finding_under_not_adjudicable_with_other_verdict_is_rejected(self):
        """The reverse mismatch: F2 sits under '## Not adjudicable' with
        adjudication `not adjudicable`; demoting its adjudication without
        moving it out of that section is rejected too.
        """
        broken = VALID_REPORT.replace(
            "- Adjudication: not adjudicable\n",
            "- Adjudication: doctrine wrong\n", 1)
        result, payload = self.check(broken, name="ranked-in-not-adjudicable.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "not-adjudicable"]
        self.assertTrue(
            any("F2" in v["where"] for v in violations),
            f"F2's demoted adjudication must be rejected and must name "
            f"F2: {violations}")

    def test_a_not_adjudicable_finding_still_needs_exactly_one_repair_unit(self):
        """`repair_unit_rows` enforcement already covers every finding, this
        included -- confirmed here rather than assumed, since W7 folds
        `not adjudicable` findings into the same coverage.
        """
        broken = VALID_REPORT.replace(
            "| Build or delete the unread declared value | F2 | 0 |\n", "", 1)
        self.assertNotEqual(broken, VALID_REPORT, "the graft must land")
        result, payload = self.check(broken, name="not-adjudicable-no-unit.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "repair-units"]
        self.assertTrue(
            any("F2" in v["detail"] for v in violations),
            f"F2 losing its repair unit must be rejected: {violations}")

    def test_stage_roster_reads_a_synthetic_table_never_a_hardcoded_list(self):
        """The roster comes from parsing whatever table it is given, not
        from a list held inside the tool -- proven with a synthetic stage
        no real `SKILL.md` will ever carry. Numbered far past any real
        stage, per the same renumbering lesson the moves fixture already
        paid for: this fixture's assertion matches `'stage 97'`, never a
        bare numeral as a substring.
        """
        cli = audit_cli_module()
        synthetic = ("| Stage | Models | Demands |\n"
                    "| --- | --- | --- |\n"
                    "| 97. A stage that exists only in this fixture | 0 | "
                    "`frozen` |\n")
        roster = cli.stage_roster(synthetic)
        self.assertEqual(roster, [("97", "frozen")])

    def test_a_stages_row_with_no_leading_digit_is_unprobeable(self):
        """No `textual` escape valve here, unlike the moves table: every
        stage row must carry a leading digit or the table is unprobeable.
        """
        cli = audit_cli_module()
        bad = ("| Stage | Models | Demands |\n"
              "| --- | --- | --- |\n"
              "| Textual stage, no digit | 0 | `frozen` |\n")
        with self.assertRaises(cli.Unprobeable):
            cli.stage_roster(bad)

    def test_a_stages_row_naming_an_unknown_report_shape_key_is_unprobeable(self):
        cli = audit_cli_module()
        bad = ("| Stage | Models | Demands |\n"
              "| --- | --- | --- |\n"
              "| 0. Freeze the subject | 0 | `not-a-real-key` |\n")
        with self.assertRaises(cli.Unprobeable):
            cli.stage_roster(bad)

    def test_the_real_stages_table_derives_stages_0_through_5(self):
        cli = audit_cli_module()
        roster = cli.stage_roster(doctrine_text())
        self.assertEqual(
            [stage_id for stage_id, _ in roster],
            ["0", "1", "2", "3", "4", "5"])
        self.assertEqual(
            dict(roster),
            {"0": "frozen", "1": "undecidable", "2": "user-drive",
             "3": "reading-diff", "4": "drives", "5": "found-by"})

    def _with_stage_two_agreed(self, report, post_drive_overrides=None):
        """`VALID_REPORT` with stage 2 promoted to `ran` and a minimal
        `## User drive` section declaring `agree`, for the post-drive
        gating tests below. `post_drive_overrides` maps a stage id to the
        row text it should carry instead of `VALID_REPORT_STAGE_OVERRIDES`'
        default for that id.
        """
        cli = audit_cli_module()
        text = report.replace(
            f"- Stage: 2: skipped: {cli.DRIVE_STAGE_RESERVED_SKIP}\n",
            "- Stage: 2: ran\n", 1)
        text = text.replace(
            "## Ranked findings",
            "## User drive\n\n"
            "- Outcome: agree\n"
            f"- Digest: {VALID_REPORT_DIGEST}\n\n"
            f"{cli.USER_DRIVE_DECLARED_HEADING}\n\n"
            "- Whether the model behind argv[0] already knew this "
            "subject's shape from training data is not measured here, "
            "stated as an assumption.\n\n"
            "## Ranked findings", 1)
        for stage_id, outcome in (post_drive_overrides or {}).items():
            needle = f"- Stage: {stage_id}: {VALID_REPORT_STAGE_OVERRIDES[stage_id]}\n"
            self.assertIn(needle, text, "the graft's anchor must be present")
            text = text.replace(needle, f"- Stage: {stage_id}: {outcome}\n", 1)
        return text

    def test_post_drive_offered_declined_is_accepted_after_agreement(self):
        text = self._with_stage_two_agreed(
            VALID_REPORT, {"3": "skipped: offered, declined"})
        result, payload = self.check(text, name="post-drive-offered-agreed.md")
        self.assertEqual(result.returncode, 0, payload)

    def test_post_drive_offered_declined_without_agreement_is_rejected(self):
        broken = VALID_REPORT.replace(
            "- Stage: 3: skipped: no blind reading pair compared in this "
            "pass\n",
            "- Stage: 3: skipped: offered, declined\n", 1)
        result, payload = self.check(
            broken, name="post-drive-offered-no-agreement.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "reading-diff"]
        self.assertTrue(
            any("3" in v["detail"] for v in violations),
            f"an unagreed offered/declined stage 3 must be rejected and "
            f"must name stage 3: {violations}")

    def test_post_drive_offered_declined_needs_the_agree_outcome_specifically(self):
        """Stage 2 `ran` is not enough on its own -- the drive must have
        reached `agree`, not merely have been attempted.
        """
        text = self._with_stage_two_agreed(
            VALID_REPORT, {"4": "skipped: offered, declined"})
        text = text.replace("- Outcome: agree\n", "- Outcome: disk-stale\n", 1)
        result, payload = self.check(text, name="post-drive-offered-not-agree.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"] if v["item"] == "drives"]
        self.assertTrue(
            any("4" in v["detail"] for v in violations),
            f"a stage-2 outcome short of agree must still reject the "
            f"offered/declined text on stage 4: {violations}")

    def test_stage_two_own_row_can_never_read_offered_declined(self):
        cli = audit_cli_module()
        broken = VALID_REPORT.replace(
            f"- Stage: 2: skipped: {cli.DRIVE_STAGE_RESERVED_SKIP}\n",
            "- Stage: 2: skipped: offered, declined\n", 1)
        result, payload = self.check(broken, name="stage2-offered-declined.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"]
                     if v["item"] == "driver-required"]
        self.assertTrue(
            any("2" in v["detail"] for v in violations),
            f"stage 2's own row must never read offered/declined: {violations}")

    def test_stage_two_ran_with_full_user_drive_content_is_accepted(self):
        """[LOCK] The grounded baseline every inversion below mutates."""
        text = self._with_stage_two_agreed(VALID_REPORT)
        result, payload = self.check(text, name="user-drive-complete.md")
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["violations"], [])

    def test_user_drive_digest_disagreeing_with_frozen_is_rejected(self):
        text = self._with_stage_two_agreed(VALID_REPORT)
        broken = text.replace(
            f"- Digest: {VALID_REPORT_DIGEST}\n\n"
            f"{audit_cli_module().USER_DRIVE_DECLARED_HEADING}",
            f"- Digest: sha256:{'0' * 64}\n\n"
            f"{audit_cli_module().USER_DRIVE_DECLARED_HEADING}", 1)
        self.assertNotEqual(broken, text, "the graft must land")
        result, payload = self.check(broken, name="user-drive-digest-mismatch.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"] if v["item"] == "user-drive"]
        self.assertTrue(
            any("Digest" in v["detail"] for v in violations),
            f"a '## User drive' digest disagreeing with '## Frozen' must "
            f"be rejected: {violations}")

    def test_user_drive_missing_digest_is_rejected(self):
        # `VALID_REPORT_DIGEST` also appears in `## Frozen` and in every
        # finding, so the replace is anchored on the immediately preceding
        # `- Outcome: agree` line, unique to `## User drive`.
        text = self._with_stage_two_agreed(VALID_REPORT)
        broken = text.replace(
            f"- Outcome: agree\n- Digest: {VALID_REPORT_DIGEST}\n",
            "- Outcome: agree\n", 1)
        self.assertNotEqual(broken, text, "the graft must land")
        result, payload = self.check(broken, name="user-drive-no-digest.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertIn("user-drive", [v["item"] for v in payload["violations"]])

    def test_user_drive_empty_declared_only_section_is_rejected(self):
        cli = audit_cli_module()
        text = self._with_stage_two_agreed(VALID_REPORT)
        broken = text.replace(
            "- Whether the model behind argv[0] already knew this "
            "subject's shape from training data is not measured here, "
            "stated as an assumption.\n\n",
            "", 1)
        self.assertNotEqual(broken, text, "the graft must land")
        self.assertIn(cli.USER_DRIVE_DECLARED_HEADING, broken,
                      "the bare heading must survive; only its content is removed")
        result, payload = self.check(broken, name="user-drive-empty-declared.md")
        self.assertEqual(result.returncode, 1, payload)
        violations = [v for v in payload["violations"] if v["item"] == "user-drive"]
        self.assertTrue(
            any("Declared" in v["detail"] for v in violations),
            f"an empty declared-only section must be rejected: {violations}")

    def test_user_drive_missing_declared_only_heading_is_rejected(self):
        cli = audit_cli_module()
        text = self._with_stage_two_agreed(VALID_REPORT)
        broken = text.replace(f"{cli.USER_DRIVE_DECLARED_HEADING}\n\n", "", 1)
        self.assertNotEqual(broken, text, "the graft must land")
        result, payload = self.check(broken, name="user-drive-no-declared-heading.md")
        self.assertEqual(result.returncode, 1, payload)
        self.assertIn("user-drive", [v["item"] for v in payload["violations"]])

    def test_stage_model_total_sums_a_synthetic_table(self):
        cli = audit_cli_module()
        synthetic = ("| Stage | Models | Demands |\n"
                    "| --- | --- | --- |\n"
                    "| 0. Zero-model stage | 0 | `frozen` |\n"
                    "| 1. Three-model stage | 3 | `undecidable` |\n")
        self.assertEqual(cli.stage_model_total(synthetic), 3)

    def test_a_stages_models_cell_that_is_not_an_integer_is_unprobeable(self):
        cli = audit_cli_module()
        bad = ("| Stage | Models | Demands |\n"
              "| --- | --- | --- |\n"
              "| 0. Not a number | many | `frozen` |\n")
        with self.assertRaises(cli.Unprobeable):
            cli.stage_model_total(bad)

    def test_the_model_count_sentence_names_the_derived_sum(self):
        """[LOCK] "N model runs, total" and its own per-stage breakdown are
        read back from `SKILL.md`'s prose and checked against the stages
        table's own `Models` column, never the reverse. Without the
        breakdown half, correcting the leading numeral by hand would leave
        the sentence's second half free to rot independently -- so both
        halves are asserted, grounded in the real doctrine, never in a
        mirrored literal.
        """
        cli = audit_cli_module()
        text = doctrine_text()
        total = cli.stage_model_total(text)

        numeral = re.search(r"\b(\w+) model runs, total\b", text)
        self.assertIsNotNone(
            numeral, "SKILL.md carries no 'N model runs, total' sentence")
        word = numeral.group(1).lower()
        self.assertIn(word, cli.CARDINALS, f"{word!r} is not a known cardinal")
        self.assertEqual(
            cli.CARDINALS[word], total,
            f"the sentence says {word!r} but the stages table's Models "
            f"column sums to {total}")

        tables = markdown_table_rows(text, STAGES_HEADER)
        self.assertEqual(len(tables), 1, "one stages table, exactly")
        for row in tables[0]:
            stage_match = re.match(r"^(\d+)\b", row[0]) if row else None
            if not stage_match:
                continue
            stage_id = stage_match.group(1)
            models = int(row[1].strip())
            if models == 0:
                continue
            breakdown = re.search(rf"\b(\w+) for stage {stage_id}\b", text)
            self.assertIsNotNone(
                breakdown,
                f"the sentence's breakdown names no cardinal for stage "
                f"{stage_id}, which the table gives {models} Models")
            breakdown_word = breakdown.group(1).lower()
            self.assertEqual(
                cli.CARDINALS.get(breakdown_word), models,
                f"stage {stage_id} has {models} Models but the sentence's "
                f"breakdown says {breakdown_word!r}")


# ==========================================================================
# W10 -- `sensitivity`: does a declared computed value actually track the
# declared input it claims to depend on? Move 1 run twice, under two
# different inputs, pointed at products instead of guards.
# ==========================================================================

SENSITIVITY_SPEC = PROBES / "skill-audit.sensitivity.json"


def sensitivity_json(spec, subject, repo=FORGE, extra=()):
    """Drive `sensitivity` as a process and parse what it wrote to stdout."""
    result = run_cli("sensitivity", "--subject", str(subject),
                     "--spec", str(spec), "--repo-root", str(repo), *extra)
    try:
        return result, json.loads(result.stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"sensitivity exited {result.returncode} without JSON on "
            f"stdout.\nstdout={result.stdout!r}\nstderr={result.stderr!r}")


class SensitivityBoxMixin(BoxMixin):
    """Fixtures for `sensitivity`: a subject declaring a results table and
    a real producer script, plus the box `sensitivity` builds fresh under
    `implementations/`.
    """

    def sensitivity_box(self, surface):
        box = BOXES / f"_sensitivity_{surface}"
        self.addCleanup(self._erase_sensitivity_box, box)
        return box

    def _erase_sensitivity_box(self, box):
        if not box.exists():
            return
        for path in sorted(box.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        box.rmdir()

    def make_sensitivity_subject(self, name, initial_value, data_files, producer):
        subject = self.make_box(name)
        self.write(subject, "RESULTS.md",
                  f"| Metric | Value |\n| --- | --- |\n| rows | {initial_value} |\n")
        for relative, content in data_files.items():
            self.write(subject, f"data/{relative}", content)
        self.write(subject, "run.py", producer)
        return subject

    def make_recipe(self, subject, surface, argv=None, exclude=()):
        spec = subject / "sensitivity.json"
        spec.write_text(json.dumps({
            "surface": surface,
            "declared": {"path": "RESULTS.md", "table": "| Metric | Value |",
                        "column": 1},
            "disk": {"root": "data"},
            "argv": argv or ["python3", "{subject}/run.py"],
            "cwd": ".",
            "env": ["PATH"],
            "exclude": list(exclude),
        }, indent=2), encoding="utf-8")
        return spec


#: A producer that never touches its own box at all -- the control-stall
#: fixture. Silence, not a refusal: it exits 0 having read and written
#: nothing, so the declared site's values never move from the shipped
#: fixture's own initial state.
STALLED_PRODUCER = "pass\n"

#: A producer that writes the identical literal regardless of what its box
#: holds -- half 1 of the load-bearing inversion.
HARDCODED_PRODUCER = (
    "import pathlib\n"
    "pathlib.Path('RESULTS.md').write_text(\n"
    "    '| Metric | Value |\\n| --- | --- |\\n| rows | 42 |\\n',\n"
    "    encoding='utf-8')\n")

#: A producer that genuinely counts lines under its own `data/` -- half 2
#: of the same inversion, the identical value computed from the identical
#: input.
COMPUTED_PRODUCER = (
    "import pathlib\n"
    "total = 0\n"
    "data_dir = pathlib.Path('data')\n"
    "if data_dir.is_dir():\n"
    "    for f in sorted(data_dir.rglob('*')):\n"
    "        if f.is_file():\n"
    "            total += len(f.read_text(encoding='utf-8').splitlines())\n"
    "pathlib.Path('RESULTS.md').write_text(\n"
    "    f'| Metric | Value |\\n| --- | --- |\\n| rows | {total} |\\n',\n"
    "    encoding='utf-8')\n")


class SensitivityInversionTests(SensitivityBoxMixin, unittest.TestCase):
    """The load-bearing proof, in two halves: a probe that fires on
    everything is as useless as one that fires on nothing.
    """

    def test_half_one_a_hardcoded_value_is_reported_not_adjudicable(self):
        surface = "hardcoded"
        self.sensitivity_box(surface)
        subject = self.make_sensitivity_subject(
            "hardcoded_subject", initial_value=999,
            data_files={"a.txt": "one\ntwo\nthree\n", "b.txt": "four\nfive\n"},
            producer=HARDCODED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["control"], "passed")
        self.assertIn("rows", payload["notAdjudicable"])
        for outcome in payload["matrix"]["rows"].values():
            self.assertEqual(outcome, "unchanged", payload["matrix"])

    def test_half_two_the_identical_value_genuinely_computed_is_silent(self):
        """Same fixture shape, producer changed to compute the same value
        from the same input. Without this half, half one proves nothing.
        """
        surface = "computed"
        self.sensitivity_box(surface)
        subject = self.make_sensitivity_subject(
            "computed_subject", initial_value=999,
            data_files={"a.txt": "one\ntwo\nthree\n", "b.txt": "four\nfive\n"},
            producer=COMPUTED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["control"], "passed")
        self.assertNotIn("rows", payload["notAdjudicable"])
        self.assertTrue(
            any(outcome == "moved"
               for outcome in payload["matrix"]["rows"].values()),
            payload["matrix"])


class SensitivityControlGateTests(SensitivityBoxMixin, unittest.TestCase):
    """The inverted control: proof a producer reads its own box before any
    per-input `unchanged` cell is allowed to mean anything.
    """

    def test_a_producer_that_never_reads_its_box_stalls_the_control(self):
        surface = "stalled"
        self.sensitivity_box(surface)
        subject = self.make_sensitivity_subject(
            "stalled_subject", initial_value=7,
            data_files={"a.txt": "one\n"}, producer=STALLED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("sensitivity-control-stalled", payload["error"])
        self.assertIn("never read", payload["error"].lower())
        self.assertIn("typed in", payload["error"].lower())

    def test_a_producer_that_does_read_its_box_passes_the_control(self):
        """Proof the stall test above is not asserting a constant."""
        surface = "control_passes"
        self.sensitivity_box(surface)
        subject = self.make_sensitivity_subject(
            "control_passes_subject", initial_value=999,
            data_files={"a.txt": "one\ntwo\n"}, producer=COMPUTED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["control"], "passed")


class SensitivityDeclarationTests(SensitivityBoxMixin, unittest.TestCase):
    """Candidate pairs derive from the subject's own declaration alone."""

    def test_a_subject_declaring_no_computed_values_is_a_first_class_result(self):
        surface = "no_declaration"
        self.sensitivity_box(surface)
        subject = self.make_box("no_declaration_subject")
        self.write(subject, "RESULTS.md", "Nothing here but prose.\n")
        self.write(subject, "data/a.txt", "x\n")
        self.write(subject, "run.py", HARDCODED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertEqual(payload["notes"][0]["kind"], "no-closed-roster")
        self.assertEqual(payload["matrix"], {})

    def test_a_differently_labelled_subject_needs_no_guard_edit(self):
        """Proof of derivation, never a hand-list: a subject naming its
        computed value something this suite has never used before is
        still picked up correctly, with zero edits anywhere in
        `audit_cli.py` -- the roster lives only in the subject's own table.
        """
        surface = "differently_labelled"
        self.sensitivity_box(surface)
        subject = self.make_box("differently_labelled_subject")
        self.write(subject, "RESULTS.md",
                  "| Metric | Value |\n| --- | --- |\n"
                  "| a-name-never-used-elsewhere-in-this-suite | 999 |\n")
        self.write(subject, "data/a.txt", "one\ntwo\n")
        self.write(subject, "run.py", (
            "import pathlib\n"
            "total = len(pathlib.Path('data/a.txt').read_text("
            "encoding='utf-8').splitlines())\n"
            "pathlib.Path('RESULTS.md').write_text(\n"
            "    '| Metric | Value |\\n| --- | --- |\\n'\n"
            "    f'| a-name-never-used-elsewhere-in-this-suite | {total} |\\n',\n"
            "    encoding='utf-8')\n"))
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIn("a-name-never-used-elsewhere-in-this-suite",
                      payload["matrix"])


class SensitivityCapTests(SensitivityBoxMixin, unittest.TestCase):
    """A count cap, never a wall-clock budget; overflow named, not dropped."""

    def test_more_than_the_cap_is_named_in_unchecked(self):
        surface = "cap"
        self.sensitivity_box(surface)
        data_files = {f"f{i}.txt": f"line{i}\n" for i in range(6)}
        subject = self.make_sensitivity_subject(
            "cap_subject", initial_value=999, data_files=data_files,
            producer=COMPUTED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertEqual(payload["inputsTotal"], 6)
        self.assertEqual(len(payload["inputsVaried"]), 4)
        self.assertEqual(len(payload["inputsUnchecked"]), 2)
        self.assertEqual(
            sorted(payload["inputsVaried"] + payload["inputsUnchecked"]),
            sorted(f"data/f{i}.txt" for i in range(6)))

    def test_cap_selection_is_deterministic_across_runs(self):
        surface = "cap_determinism"
        self.sensitivity_box(surface)
        data_files = {f"f{i}.txt": f"line{i}\n" for i in range(6)}
        subject = self.make_sensitivity_subject(
            "cap_determinism_subject", initial_value=999,
            data_files=data_files, producer=COMPUTED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result1, payload1 = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result1.returncode, 0, payload1)
        result2, payload2 = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result2.returncode, 0, payload2)
        self.assertEqual(payload1["inputsVaried"], payload2["inputsVaried"])


class SensitivityThresholdTests(SensitivityBoxMixin, unittest.TestCase):
    def test_unchanged_for_one_input_and_moved_for_another_is_not_a_finding(self):
        surface = "threshold"
        self.sensitivity_box(surface)
        # Reads only a.txt; b.txt is declared but never touched.
        producer = (
            "import pathlib\n"
            "total = 0\n"
            "a = pathlib.Path('data/a.txt')\n"
            "if a.is_file():\n"
            "    total = len(a.read_text(encoding='utf-8').splitlines())\n"
            "pathlib.Path('RESULTS.md').write_text(\n"
            "    f'| Metric | Value |\\n| --- | --- |\\n| rows | {total} |\\n',\n"
            "    encoding='utf-8')\n")
        subject = self.make_sensitivity_subject(
            "threshold_subject", initial_value=999,
            data_files={"a.txt": "one\ntwo\nthree\n", "b.txt": "four\n"},
            producer=producer)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertNotIn(
            "rows", payload["notAdjudicable"],
            "unchanged for one input out of two must not cross the "
            "threshold; the matrix is published, not the accusation")
        self.assertEqual(payload["matrix"]["rows"]["data/a.txt"], "moved")
        self.assertEqual(payload["matrix"]["rows"]["data/b.txt"], "unchanged")


class SensitivityRestoreTests(SensitivityBoxMixin, unittest.TestCase):
    """Restore discipline inherited from Move 6, verbatim: `sha256` before,
    remove, drive, write the exact bytes back, `sha256` again.
    """

    def test_a_restore_mismatch_halts_the_sweep(self):
        """A producer that recreates a removed input as a directory,
        instead of leaving it absent, makes the write-back fail
        structurally -- caught, never silent, and the sweep halts rather
        than attempting anything further.
        """
        surface = "restore_mismatch"
        self.sensitivity_box(surface)
        producer = (
            "import pathlib\n"
            "removed = pathlib.Path('data/a.txt')\n"
            "if not removed.exists():\n"
            "    removed.mkdir(parents=True)\n"
            "pathlib.Path('RESULTS.md').write_text(\n"
            "    '| Metric | Value |\\n| --- | --- |\\n| rows | 1 |\\n',\n"
            "    encoding='utf-8')\n")
        subject = self.make_sensitivity_subject(
            "restore_mismatch_subject", initial_value=999,
            data_files={"a.txt": "one\n"}, producer=producer)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("sensitivity-restore-failed", payload["error"])

    def test_a_producer_writing_into_the_real_subject_is_refused(self):
        surface = "escape"
        self.sensitivity_box(surface)
        subject = self.make_sensitivity_subject(
            "escape_subject", initial_value=999,
            data_files={"a.txt": "one\n"}, producer="pass\n")
        # Escape by relative navigation from the copy's own cwd, exactly
        # the shape a real accidental escape would take -- the copy sits
        # at implementations/_sensitivity_<surface>/subject, two levels
        # below implementations/ itself, a sibling of the real subject.
        escape_producer = (
            "import pathlib\n"
            f"pathlib.Path('../../{subject.name}/escaped.txt').write_text("
            "'escaped', encoding='utf-8')\n"
            "pathlib.Path('RESULTS.md').write_text(\n"
            "    '| Metric | Value |\\n| --- | --- |\\n| rows | 1 |\\n',\n"
            "    encoding='utf-8')\n")
        self.write(subject, "run.py", escape_producer)
        spec = self.make_recipe(subject, surface)
        escaped = subject / "escaped.txt"
        self.addCleanup(lambda: escaped.unlink() if escaped.exists() else None)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn("build-escaped-the-box", payload["error"])


class SensitivityBoxLifecycleTests(SensitivityBoxMixin, unittest.TestCase):
    def test_a_non_empty_box_is_refused_and_left_untouched(self):
        surface = "occupied"
        box = self.sensitivity_box(surface)
        box.mkdir(parents=True, exist_ok=True)
        (box / "stranger.txt").write_text("already here\n", encoding="utf-8")
        subject = self.make_sensitivity_subject(
            "occupied_subject", initial_value=999,
            data_files={"a.txt": "one\n"}, producer=COMPUTED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 2, payload)
        self.assertIn(str(box), payload["error"])
        self.assertTrue((box / "stranger.txt").exists(),
                        "a box that was not ours to adopt must be left alone")

    def test_cleanup_is_proven_by_content_never_by_git_status(self):
        surface = "cleanup_proof"
        box = self.sensitivity_box(surface)
        subject = self.make_sensitivity_subject(
            "cleanup_subject", initial_value=999,
            data_files={"a.txt": "one\n"}, producer=COMPUTED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        after = audit_cli_module().tree_digest(box)
        self.assertEqual(
            after, {},
            "the box must be content-empty in a fresh walk of its own "
            "subtree, never proven by `git status`")
        self.assertFalse(box.exists())

    def test_a_sensitivity_run_leaves_the_subject_untouched(self):
        """The proof `SuiteIntegrityTests`'s write-verb lock cannot itself
        provide: `run_sensitivity`, `materialize_subject_copy`,
        `vary_by_absence`, and `restore_exact_bytes` all write, but only
        ever inside the box this run owns. Driven for real, against the
        real subcommand, comparing the subject's own tree by bytes.
        """
        surface = "untouched"
        self.sensitivity_box(surface)
        subject = self.make_sensitivity_subject(
            "untouched_subject", initial_value=999,
            data_files={"a.txt": "one\ntwo\n", "b.txt": "three\n"},
            producer=COMPUTED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        cli = audit_cli_module()
        before = cli.tree_digest(subject)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        after = cli.tree_digest(subject)
        self.assertEqual(before, after,
                         "sensitivity perturbs a copy; the real subject "
                         "must be byte-identical before and after")


class SensitivityMoveRosterTests(unittest.TestCase):
    """Move 10 arrives in the required move-outcome roster by derivation,
    not by a code change: `\\d+` already parsed `10` before this unit
    existed.
    """

    def test_move_10_is_in_the_derived_roster(self):
        cli = audit_cli_module()
        self.assertIn("10", cli.move_roster(doctrine_text()))

    def test_move_10_costs_zero_model_runs(self):
        """Move 10 is a move, not a stage: the stages table, and the
        derived model-count sentence, are both untouched by this unit."""
        cli = audit_cli_module()
        roster = dict(cli.stage_roster(doctrine_text()))
        self.assertNotIn("computed-value-provenance", roster.values())


class SensitivityAdjudicationTests(SensitivityBoxMixin, unittest.TestCase):
    """W10's own reconciled deviation: `artefact wrong` is never emitted
    by Move 10, though it remains a valid adjudication for other moves.
    """

    def test_artefact_wrong_remains_in_the_closed_set(self):
        cli = audit_cli_module()
        self.assertIn("artefact wrong", cli.ADJUDICATIONS)

    def test_move_10_emits_not_adjudicable_only(self):
        """Measured against a planted hardcoded-value fixture: the
        payload itself carries no adjudication field at all -- that
        judgment belongs to whoever authors the report from
        `notAdjudicable`, and this test fixes the vocabulary available to
        them for a Move 10 "did not move" fact to one member, not to
        convention.
        """
        surface = "adjudication_only"
        self.sensitivity_box(surface)
        subject = self.make_sensitivity_subject(
            "adjudication_only_subject", initial_value=999,
            data_files={"a.txt": "one\n", "b.txt": "two\n"},
            producer=HARDCODED_PRODUCER)
        spec = self.make_recipe(subject, surface)
        result, payload = sensitivity_json(spec, subject, repo=FORGE)
        self.assertEqual(result.returncode, 0, payload)
        self.assertIn("rows", payload["notAdjudicable"])
        self.assertNotIn("adjudication", payload)
