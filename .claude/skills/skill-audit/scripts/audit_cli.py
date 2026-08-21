#!/usr/bin/env python3
"""The mechanism behind `skill-audit`: derive both halves of a closed set.

Stdlib only, no venv, no network. Every subcommand writes JSON to stdout with
sorted keys and returns an integer status, so a caller can hold the output to a
schema instead of to a paragraph.

Two exit codes carry two different meanings and are never merged. `0` means the
tool looked and is reporting what it saw, findings included. `2` means it could
not look: the probe would not run, the recipe was unreadable, or the extraction
matched nothing. An empty result and an inability to produce a result are not
the same claim, and a tool that spells them the same way turns a broken probe
into a page of confident findings.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

#: Cardinal words a document might use to state the size of a list. Digits are
#: matched separately. Nothing above twelve is included: past that, prose
#: overwhelmingly switches to digits, and admitting the long tail buys noise.
CARDINALS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

#: A numeral wearing one of these is not claiming to size anything, and a check
#: that fired on it would be noise. Noise gets exempted until the check means
#: nothing, so the exemption is declared here once rather than grown case by
#: case. Measured need: a neighbouring engine's own header says "~63 TS files"
#: and "roughly 0.72s" two lines apart.
HEDGES = ("~", "about", "approximately", "around", "roughly", "nearly",
          "almost", "at least", "at most", "up to", "over", "under",
          "more than", "fewer than", "some", "several", "or so")

_CARDINAL_RE = re.compile(
    r"\b(" + "|".join(CARDINALS) + r"|\d{1,3})\b", re.IGNORECASE)


class Unprobeable(Exception):
    """The tool could not look. Distinct from having looked and found nothing.

    Raised rather than returned, and mapped to exit `2` at the boundary, so that
    no code path can accidentally hand an empty set to a comparison as though it
    were an observation.
    """


# --------------------------------------------------------------------------
# Documented side. Nothing in this section may reference the producer: not the
# probe, not `subprocess`, not a constant borrowed from either. The soundness
# gate in `tests/test_skill_audit.py` parses these functions' syntax trees and
# fails on any such reference, because "it structurally cannot" is a claim and
# claims are what this skill is for.
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


def doctrine_side(text, site):
    """The documented half of a surface, parsed out of one table.

    `site` is a recipe entry, never a roster. It names the table's header line
    and the column to read, and it may claim the table is a *complement* set —
    a table of the members that are deliberately outside the main flow. Such a
    claim is honoured only if the recipe also quotes the heading verbatim and
    that heading is found in the text, so the editorial judgement is falsifiable
    by renaming the heading.

    Returns `(members, note)`. A site with no parseable table returns no members
    and the note `no-closed-roster`, which is a first-class result: the finding
    is that this subject states its set in prose.
    """
    header = site.get("table")
    if not header:
        return [], "no-closed-roster"

    tables = markdown_table_rows(text, header)
    rows = [row for table in tables for row in table]
    if not rows:
        return [], "no-closed-roster"

    scope = site.get("scope")
    if scope:
        heading = site.get("headingVerbatim")
        if not heading:
            return [], "scope-claimed-without-heading"
        if heading not in text.splitlines():
            return [], "heading-not-found"

    column = site.get("column", 0)
    members = []
    for row in rows:
        if column >= len(row):
            continue
        members.append(row[column].strip().strip("`").strip())
    return [member for member in members if member], scope or "closed"


def bullet_run_length(lines, start):
    """How many top-level bullets the list beginning at `lines[start]` holds.

    A bullet's continuation lines are indented and its items may be separated by
    blank lines, so the run ends at the first non-blank line that is neither a
    top-level bullet nor indented. Counted rather than assumed: the enumeration
    a reader believes follows a numeral is frequently longer than the reader
    thinks, because a long indented item hides the next bullet below the fold.
    """
    count = 0
    index = start
    while index < len(lines):
        line = lines[index]
        if line.strip() == "":
            index += 1
            continue
        if line.startswith("- ") or line.startswith("* "):
            count += 1
            index += 1
            continue
        if line[:1] in (" ", "\t"):
            index += 1
            continue
        break
    return count


def table_run_length(lines, start):
    """How many data rows the table beginning at `lines[start]` holds."""
    index = start + 2  # header line, then the separator
    count = 0
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        count += 1
        index += 1
    return count if count else 0


def enumeration_after(lines, index):
    """The enumeration immediately below `lines[index]`, if there is one.

    "Immediately" means at most one blank line away. A numeral separated from a
    list by a paragraph is not claiming to size that list, and treating it as
    though it were is how a check earns its first exemption.
    """
    probe = index + 1
    blanks = 0
    while probe < len(lines) and lines[probe].strip() == "":
        blanks += 1
        if blanks > 1:
            return None
        probe += 1
    if probe >= len(lines):
        return None
    line = lines[probe]
    if line.startswith("- ") or line.startswith("* "):
        return probe, bullet_run_length(lines, probe)
    if line.lstrip().startswith("|"):
        return probe, table_run_length(lines, probe)
    return None


def numeral_mismatches(path):
    """Unhedged numerals that state a size the enumeration beneath them denies.

    Only two positions are read: a line that ends with a colon, which is prose
    introducing the list below it, and a markdown heading. Both are places a
    numeral is making a claim about what follows rather than mentioning a
    quantity in passing. Everything else is left alone deliberately — a rule
    that fires on every number in a document is a rule nobody keeps.

    Each mismatch names the numeral's line and the enumeration's line, because a
    finding that names one half is a candidate.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    findings = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        is_heading = stripped.startswith("#")
        if not is_heading and not stripped.endswith(":"):
            continue
        if stripped.startswith("|") or stripped.startswith("- "):
            continue
        for match in _CARDINAL_RE.finditer(stripped):
            token = match.group(1)
            before = stripped[:match.start()].lower()
            if any(hedge in before[-24:] for hedge in HEDGES):
                continue
            value = CARDINALS.get(token.lower())
            if value is None:
                value = int(token)
            found = enumeration_after(lines, index)
            if found is None:
                continue
            enumeration_line, counted = found
            if counted and counted != value:
                findings.append({
                    "counted": counted,
                    "enumerationLine": enumeration_line + 1,
                    "numeral": token,
                    "numeralLine": index + 1,
                    "path": str(path),
                    "stated": value,
                })
    return findings


# --------------------------------------------------------------------------
# Code side. This is where the producer lives, kept below a clear line so the
# syntax-tree gate above has something unambiguous to guard.
# --------------------------------------------------------------------------

def probe_code_side(recipe, subject, timeout=30):
    """The running subject's own roster, taken out of its own refusal.

    The subject is driven as a real process with a nonce it cannot accept, and
    the accepted set is read from the message it produces in its own words. No
    source of the subject is parsed, so there is no second parser to drift from
    the first, and the subject may be written in any language.

    `stream` and `exit` come from the recipe rather than being fixed here,
    because the two probes genuinely differ: a Node host writes its refusal as
    JSON to stdout and exits `1`, while `argparse` writes `invalid choice` to
    stderr and exits `2`. One hardcoded contract would fit neither.
    """
    argv = list(recipe["argv"])
    if not argv or not all(isinstance(part, str) for part in argv):
        raise Unprobeable("the recipe's argv must be a list of strings")

    subject = Path(subject).resolve()
    where = subject
    if recipe.get("cwd"):
        where = (subject / recipe["cwd"]).resolve()
        if subject != where and subject not in where.parents:
            raise Unprobeable(
                f"the recipe's cwd {recipe['cwd']!r} resolves outside --subject")
    if not where.is_dir():
        raise Unprobeable(f"the recipe's cwd does not exist: {where}")

    try:
        # `shell=False` and argv as a list, never a string: a recipe carrying a
        # semicolon must reach the subject as one literal argument, not as two
        # commands. There is no shell in this path to interpret it.
        completed = subprocess.run(
            argv, cwd=str(where), shell=False,
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise Unprobeable(f"the recipe's argv[0] is not executable: {error}")
    except subprocess.TimeoutExpired:
        raise Unprobeable(
            f"the subject did not answer within {timeout}s; a probe that hangs "
            "is an inability to look, never an empty roster")

    expected = recipe.get("exit", "any")
    if expected != "any" and completed.returncode != expected:
        raise Unprobeable(
            f"the subject exited {completed.returncode}, not the {expected} the "
            "recipe expects; the refusal path was probably not reached")

    stream = recipe.get("stream", "stdout")
    text = completed.stdout if stream == "stdout" else completed.stderr
    pattern = re.compile(recipe["extract"])
    match = pattern.search(text)
    if match is None:
        raise Unprobeable(
            "the recipe's extract matched nothing in the subject's "
            f"{stream}; returning an empty roster here would make every "
            f"documented row a phantom. Saw: {text.strip()[:400]!r}")

    raw = match.group("roster")
    members = [part.strip().strip("'\"`") for part in raw.split(recipe.get("split", ", "))]
    members = [member for member in members if member]
    if not members:
        raise Unprobeable(
            "the extraction matched but yielded no members, which is the same "
            "inability to look wearing a different shape")
    return members


def build_parser():
    """Every subcommand this tool declares.

    Read by the self-audit through `argparse`'s own refusal rather than from a
    list beside it, so a subcommand that ships without a documented row is a
    red rather than a discovery.
    """
    parser = argparse.ArgumentParser(
        prog="audit_cli.py",
        description="Derive both halves of a closed set and compare them.")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    roster = commands.add_parser(
        "roster", help="derive a subject's closed set from code and from docs")
    roster.add_argument("--subject", required=True,
                        help="the subject's root directory")
    roster.add_argument("--probe-spec", required=True,
                        help="the JSON recipe describing how to derive it")
    roster.add_argument("--timeout", type=int, default=30,
                        help="seconds before a hanging subject is exit 2")

    report = commands.add_parser(
        "check-report", help="validate a damage report against the shape")
    report.add_argument("report", help="the report file to validate")

    return parser


def emit(payload):
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def run_roster(args):
    """Not yet implemented; ships in the roster slice of this change.

    Refusing loudly with the reason is deliberate. A subcommand that answered
    `{}` and exited `0` while doing nothing would be a green result with no
    observation behind it, which is the fourth failure mode in this skill's own
    doctrine.
    """
    del args
    emit({"error": "roster is declared but not yet implemented",
          "status": "unimplemented"})
    return 2


def run_check_report(args):
    """Not yet implemented; ships in the report slice of this change."""
    del args
    emit({"error": "check-report is declared but not yet implemented",
          "status": "unimplemented"})
    return 2


DISPATCH = {
    "roster": run_roster,
    "check-report": run_check_report,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    try:
        return DISPATCH[args.command](args)
    except Unprobeable as error:
        emit({"error": str(error), "status": "unprobeable"})
        return 2


if __name__ == "__main__":
    sys.exit(main())
