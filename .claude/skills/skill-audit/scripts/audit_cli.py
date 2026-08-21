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
    a table of the members deliberately outside the main flow. Such a claim is
    honoured only if the recipe also quotes the heading verbatim and that
    heading is found in the text, so the editorial judgement is falsifiable by
    renaming the heading and watching the claim stop being honoured.

    Returns `(members, status)`. A site with no parseable table yields no
    members and `no-closed-roster`, which is a first-class result rather than an
    error: the finding is that this subject states its set in prose, and prose
    is what condition 5 forbids the documented side from being read out of.

    A complement is not a closed roster either. It is a deliberate subset, so it
    can support the `phantom` direction — a documented member with nothing
    behind it — but never the `unregistered` direction, where every member the
    complement omits on purpose would be reported as missing documentation.
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


def restatement_of(text, members, quorum):
    """Where a set is written out by hand, and which of its members are there.

    A place that mentions one member is not restating the set; a place carrying
    at least `quorum` of them is. The quorum comes from the recipe so the
    domain is declared before the search runs rather than tuned afterwards to
    make an inconvenient result go away.

    Returns `(matched, line)` — the members found and the first line any of them
    appears on, so the report can name the restatement at `file:line` instead of
    gesturing at a file.
    """
    lines = text.splitlines()
    matched = []
    first = 0
    for member in members:
        for number, line in enumerate(lines, start=1):
            if member in line:
                matched.append(member)
                if first == 0 or number < first:
                    first = number
                break
    if len(matched) < quorum:
        return [], 0
    return sorted(matched), first


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


def is_size_claim(stripped, end):
    """Whether the numeral ending at `end` is sizing something, or just counting.

    A numeral sizes an enumeration in one of two positions, and in no others:
    ahead of the plural noun it quantifies ("Three modules ...:"), or postposed
    at the end of the lead-in ("the modules are these three:").

    Everything else is a numeral doing a different job, and the two shapes that
    matter here were both found in a real document rather than imagined. An
    ordinal step marker sizes nothing -- `### 2. Build one X per Y` is the
    second step, not two of anything. A distributive sizes nothing either --
    "one X per Y" is a rate, and the singular noun is what says so.

    This is a narrowing of the rule, not an exemption from it. An exemption
    names the case that was inconvenient; this names the grammar a size claim
    has, so a new document that makes the claim is caught without being
    listed here first.
    """
    tail = stripped[end:]
    if tail.strip().rstrip("*_`") in ("", ":"):
        return True
    word = re.match(r"[\s*_]*([A-Za-z`'\"]+)", tail)
    if not word:
        return False
    noun = word.group(1).strip("`'\"")
    return len(noun) > 2 and noun.lower().endswith("s")


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
            if not is_size_claim(stripped, match.end()):
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
    roster.add_argument("--repo-root", default=".",
                        help="the root a site declaring root=repo resolves under")
    roster.add_argument("--timeout", type=int, default=30,
                        help="seconds before a hanging subject is exit 2")

    report = commands.add_parser(
        "check-report", help="validate a damage report against the shape")
    report.add_argument("report", help="the report file to validate")

    return parser


def emit(payload):
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def resolve_site(site, subject, repo):
    """A site's path, under the root the recipe declares and nowhere else.

    Read-only, but still refused if it climbs out: a recipe that can name any
    path on the machine is a recipe that can quietly widen the domain a
    comparison declared.
    """
    root = repo if site.get("root") == "repo" else subject
    relative = site.get("path", "")
    parts = Path(relative).parts
    if not relative or Path(relative).is_absolute() or ".." in parts:
        raise Unprobeable(
            f"a site path must stay under its declared root: {relative!r}")
    return Path(root) / relative


def read_site(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise Unprobeable(f"a documented site could not be read: {error}")


def run_roster(args):
    """Derive both halves of one closed surface and report the difference.

    Exit `0` for any verdict, findings included; exit `2` only when the tool
    could not look. Everything that could make the code side empty raises
    instead of returning, because an empty code side turns every documented row
    into a phantom and prints a broken probe as a page of findings.
    """
    spec_path = Path(args.probe_spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no probe recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the probe recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    notes = []

    if recipe.get("probe") != "refusal":
        notes.append({
            "detail": "the subject exposes neither a refusal message nor a "
                      "parser, so neither language-independent probe applies",
            "kind": "no derivation available for this surface",
            "path": str(spec_path),
            "searched": f"{spec_path}:1-1",
        })
        return finish([], [], notes, [], [], "not-run", recipe, subject, repo)

    code = sorted(set(probe_code_side(recipe, subject, timeout=args.timeout)))

    doctrine = set()
    closed_seen = False
    for site in recipe.get("doctrineSites", []):
        path = resolve_site(site, subject, repo)
        text = read_site(path)
        members, status = doctrine_side(text, site)
        span = f"{path}:1-{max(len(text.splitlines()), 1)}"
        doctrine.update(members)
        if status == "closed":
            closed_seen = True
            continue
        kind = status if status != "complement" else "no-closed-roster"
        detail = {
            "complement": "this table is a deliberate subset, so it supports "
                          "the phantom direction and never the unregistered one",
            "no-closed-roster": "the set is stated in prose or in another "
                                "language here, and prose is what the "
                                "documented side may not be read out of",
            "heading-not-found": "the recipe claims a scope for this table but "
                                 "its quoted heading is not on disk, so the "
                                 "claim is refused rather than trusted",
            "scope-claimed-without-heading": "a scope claim with no quoted "
                                             "heading is unfalsifiable",
        }[status]
        notes.append({"detail": detail, "kind": kind, "path": str(path),
                      "searched": span})

    search = recipe.get("restatementSearch", {})
    duplicated = []
    for site in search.get("paths", []):
        path = resolve_site(site, subject, repo)
        matched, line = restatement_of(read_site(path), code,
                                       search.get("quorum", 2))
        if matched:
            duplicated.append({"line": line, "members": matched,
                               "path": str(path)})
    if len(duplicated) < 2:
        duplicated = []

    comparison = "run" if closed_seen else "not-run"
    if comparison == "not-run":
        notes.append({
            "detail": "no site yielded a closed roster, so the unregistered "
                      "direction is not computed; reporting every accepted "
                      "member as undocumented would invent one finding per "
                      "member and none of them would be about this subject",
            "kind": "comparison-not-run",
            "path": str(subject),
            "searched": f"{subject}:1-1",
        })
    unregistered = sorted(set(code) - doctrine) if closed_seen else []
    phantom = sorted(doctrine - set(code))
    return finish(code, sorted(doctrine), notes, unregistered, phantom,
                  comparison, recipe, subject, repo, duplicated)


def finish(code, doctrine, notes, unregistered, phantom, comparison,
           recipe, subject, repo, duplicated=None):
    mismatches = []
    for site in recipe.get("numeralPaths", []):
        mismatches.extend(numeral_mismatches(resolve_site(site, subject, repo)))
    emit({
        "code": code,
        "comparison": comparison,
        "doctrine": doctrine,
        "duplicated": duplicated or [],
        "notes": notes,
        "numeralMismatch": mismatches,
        "phantom": phantom,
        "surface": recipe.get("surface", ""),
        "unregistered": unregistered,
    })
    return 0


#: Every item a report must carry, with the heading or field that carries it.
#: Held to the shape table in SKILL.md in both directions, so this cannot become
#: a roster restated in two places -- which is the defect the whole tool exists
#: to find, and which a report validator would be the most embarrassing place
#: to ship.
REPORT_SHAPE = {
    "adjudication": "- Adjudication:",
    "changed-line-forecast": "## Changed-line forecast",
    "clean-section": "## Clean, stated as results",
    "evidence-marker": "- Evidence:",
    "falsifier": "## Falsifier",
    "move-number": "- Move:",
    "ranked-findings": "## Ranked findings",
    "unchecked-section": "## Unchecked",
}

ADJUDICATIONS = ("doctrine wrong", "artefact wrong", "not adjudicable")

NO_CONFIRMED_DECLARATION = "No finding in this report is CONFIRMED by execution"

#: Supports a report may never lean on. Each one is a mistake made in this
#: repository, not a hypothetical: a claim resting on any of them says something
#: about the environment, the index, or the mood of a suite, and nothing about
#: the subject.
FORBIDDEN_SUPPORT = {
    "green-suite": (
        re.compile(r"suite (passed|is green)|tests all pass", re.IGNORECASE),
        "greenness is never evidence; name the execution and the observation"),
    "porcelain-containment": (
        re.compile(r"git status", re.IGNORECASE),
        "`git status --porcelain` over an ignored tree is empty by "
        "construction, so it can only ever agree; a content manifest taken "
        "before and after is the evidence that would actually decide this"),
    "request-as-receipt": (
        re.compile(r"live GET|GET returned|request succeeded", re.IGNORECASE),
        "a successful request proves the environment answered, never a fact "
        "about the subject's code"),
    "single-harness-count": (
        re.compile(r"repository[^.\n]*\b\d+\s+tests", re.IGNORECASE),
        "the harnesses are disjoint and no single command runs both, so one "
        "of them cannot report a repository-wide count"),
}

BOTH_HARNESSES = (re.compile(r"unittest", re.IGNORECASE),
                  re.compile(r"npm test|node", re.IGNORECASE))

CITATION = re.compile(r"`[^`\s]+:\d+`")


def report_findings(lines):
    """Every `### F<n>.` block, with the lines that belong to it."""
    blocks = []
    for index, line in enumerate(lines):
        if re.match(r"^### F\d+\.", line.strip()):
            blocks.append({"label": line.strip()[4:].split(".")[0],
                           "line": index + 1, "start": index, "text": []})
        elif blocks and line.startswith("## "):
            blocks[-1]["end"] = index
        elif blocks and "end" not in blocks[-1]:
            blocks[-1]["text"].append(line)
    return blocks


def run_check_report(args):
    """Validate a damage report against the shape, as a process.

    Exit `0` valid, `1` invalid, `2` unreadable. The third is separate for the
    same reason `roster` keeps it separate: a report nobody could open has not
    been judged, and recording it as invalid would be a verdict with nothing
    behind it.
    """
    path = Path(args.report)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        emit({"error": f"the report could not be read: {error}",
              "status": "unreadable"})
        return 2

    lines = text.splitlines()
    violations = []

    def fail(item, detail, where):
        violations.append({"detail": detail, "item": item, "where": where})

    for item, marker in REPORT_SHAPE.items():
        if marker.startswith("## ") and marker not in lines:
            fail(item, f"the report carries no {marker!r} section",
                 f"{path}:1")

    findings = report_findings(lines)
    if not findings:
        fail("ranked-findings", "the report names no finding at all",
             f"{path}:1")

    confirmed = False
    for finding in findings:
        where = f"{path}:{finding['line']} {finding['label']}"
        body = "\n".join(finding["text"])

        move = re.search(r"^- Move:\s*(\d+)\s*$", body, re.MULTILINE)
        if not move:
            fail("move-number",
                 "every finding names the move that found it", where)

        marker = re.search(r"^- Evidence:\s*(.+?)\s*$", body, re.MULTILINE)
        value = marker.group(1) if marker else ""
        if value == "CONFIRMED by execution":
            confirmed = True
        elif value != "read-only":
            fail("evidence-marker",
                 "every finding carries `CONFIRMED by execution` or "
                 "`read-only`, and there is no default: a missing marker is "
                 "never read as confirmed", where)

        verdict = re.search(r"^- Adjudication:\s*(.+?)\s*$", body, re.MULTILINE)
        if not verdict or verdict.group(1) not in ADJUDICATIONS:
            fail("adjudication",
                 "every finding carries exactly one adjudication from "
                 + ", ".join(ADJUDICATIONS), where)

        citations = {c for c in CITATION.findall(body)}
        if len(citations) < 2:
            fail("ranked-findings",
                 "a finding names both halves at `file:line`; naming one half "
                 f"makes it a candidate, not a finding (saw {sorted(citations)})",
                 where)

    if findings and not confirmed:
        head = [line for line in lines[:6] if line.strip()]
        if not any(NO_CONFIRMED_DECLARATION in line for line in head):
            fail("evidence-marker",
                 "no finding is CONFIRMED by execution, so the report must say "
                 f"so in its first line: {NO_CONFIRMED_DECLARATION!r}",
                 f"{path}:1")

    for index, line in enumerate(lines, start=1):
        for item, (pattern, detail) in FORBIDDEN_SUPPORT.items():
            if not pattern.search(line):
                continue
            if item == "single-harness-count" and all(
                    harness.search(line) for harness in BOTH_HARNESSES):
                continue
            fail(item, detail, f"{path}:{index}")

    emit({"violations": sorted(
        violations, key=lambda v: (v["item"], v["where"]))})
    return 1 if violations else 0


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
