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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from fnmatch import fnmatch
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


def tree_digest(root, exclude=()):
    """A sorted `path -> sha256` map over every file under `root`.

    The sole helper in this module allowed to walk a filesystem tree.
    `structure`'s on-disk and from-zero sides are this function's output, and
    so is every box's before/after proof of containment. `SingleWalkTests` in
    `tests/test_skill_audit.py` reads this file's own syntax tree and asserts
    that `rglob`, `walk`, `iterdir`, `scandir`, and `glob` occur nowhere else
    in `audit_cli.py`, so a second walk added later -- by this module or by
    the follow-up change's `manifest` -- turns that lock red rather than
    quietly drifting from this one.

    Paths are POSIX-relative to `root`, files only: a directory holds no
    content of its own to hash, and comparing directory sets would let an
    empty, newly created folder pass as agreement. `exclude` is a tuple of
    `fnmatch` patterns matched against the relative path; there is no
    built-in default, because a default would be a hidden narrowing of the
    domain a recipe declares.
    """
    digest = {}
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(fnmatch(relative, pattern) for pattern in exclude):
            continue
        digest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def frozen_digest(root, exclude=()):
    """One stable `sha256` summary over `tree_digest`'s own sorted map.

    Calls `tree_digest` rather than walking a second time -- `SingleWalkTests`
    holds every walk name to inside `tree_digest` alone, so a second walk
    here would turn that lock red rather than quietly drift beside it. The
    digest embeds one `path sha256` line per file, sorted by path, so two
    runs over the same tree with the same `exclude` always agree, and a
    file added, removed, or changed always disagrees.

    A summary hash, not the per-file map itself: a report cannot embed
    hundreds of lines of per-file hashes and stay reviewable, so the report
    carries this one digest plus the `exclude` list needed to re-derive it --
    the recipe for the hash, not the hash's own working.
    """
    files = tree_digest(root, exclude)
    lines = "\n".join(f"{path} {files[path]}" for path in sorted(files))
    return "sha256:" + hashlib.sha256(lines.encode("utf-8")).hexdigest()


#: Only these three tokens interpolate inside a `structure` recipe's
#: `fromZero.steps`, each resolved absolutely by the tool rather than taken
#: from the recipe string. Any other `{...}` is refused rather than passed
#: through as a literal brace, so a recipe cannot quietly widen what a step
#: may reach.
STRUCTURE_TOKENS = {"repoRoot", "subject", "box"}

_TOKEN_RE = re.compile(r"\{([a-zA-Z]+)\}")


def interpolate_token(text, repo, subject, box):
    """Substitute `{repoRoot}`, `{subject}`, and `{box}` inside one argv part.

    Every other `{token}` shape is a recipe naming something this tool never
    declared, and is refused before a process is ever started.
    """
    def replace(match):
        token = match.group(1)
        if token not in STRUCTURE_TOKENS:
            raise Unprobeable(
                f"the recipe's step names an unknown token {{{token}}}; only "
                f"{sorted(STRUCTURE_TOKENS)} interpolate")
        return {"repoRoot": str(repo), "subject": str(subject),
                "box": str(box)}[token]
    return _TOKEN_RE.sub(replace, text)


#: `{candidate}` is a fourth token, valid only inside `candidateGates.argv`.
#: `STRUCTURE_TOKENS` is untouched, so a plain `walkthrough` step's own argv
#: still resolves through `interpolate_token` alone and cannot reach for a
#: candidate it never declared.
GATE_TOKENS = STRUCTURE_TOKENS | {"candidate"}


def interpolate_gate_token(text, repo, subject, box, candidate):
    """Substitute `{repoRoot}`, `{subject}`, `{box}`, and `{candidate}`
    inside one `candidateGates.argv` part. Mirrors `interpolate_token`,
    scoped to the one recipe block where a fourth token is legal.
    """
    def replace(match):
        token = match.group(1)
        if token not in GATE_TOKENS:
            raise Unprobeable(
                f"the recipe's candidateGates.argv names an unknown token "
                f"{{{token}}}; only {sorted(GATE_TOKENS)} interpolate")
        return {"repoRoot": str(repo), "subject": str(subject),
                "box": str(box), "candidate": candidate}[token]
    return _TOKEN_RE.sub(replace, text)


#: Only `{repoRoot}` and `{box}` interpolate inside a `fromZero.steps`
#: entry -- never `{subject}`. The from-zero side is meant to build a
#: comparison *target*, never to reference the producer it will be compared
#: against; refusing the token at the interpolation layer is the structural
#: half of that soundness condition. `assert_no_subject_reference` below is
#: the other half, for a recipe that embeds the subject's path directly
#: rather than through the token -- the exact shape of the tar recipe this
#: change replaces (`git archive HEAD:.claude/skills/skill-audit`, no
#: `{subject}` token in sight).
FROM_ZERO_TOKENS = STRUCTURE_TOKENS - {"subject"}

#: The step-kind vocabulary a `fromZero.steps` dict element may declare. A
#: bare list stays kind `exec`, run exactly as before -- no existing recipe
#: or fixture changes shape. `driver` is the one new kind: it additionally
#: resolves `cwd` under the box, constructs an environment from declared
#: names, and proves `argv[0]`'s real path is external. An unknown `kind`
#: is `Unprobeable`, the same treatment `interpolate_token` already gives
#: an unknown `{token}`.
BOX_STEP_KINDS = ("exec", "driver")

#: Environment variable *names* a `driver` step may ask to inherit from the
#: parent process. Names only: the child's environment is constructed from
#: this allowlist, never copied from `os.environ` wholesale, and only the
#: names travel into the report -- values never do.
DRIVER_ENV_ALLOWLIST = ("HOME", "LANG", "LC_ALL", "PATH", "TERM", "TMPDIR")

#: The directory namespace the ignorance control gate seeds a from-zero box
#: with, before trusting that box was ever empty. Absurd and namespaced so
#: it can never collide with a real driver's own output.
IGNORANCE_CONTROL_DIR = "__audit_ignorance_control__"


def interpolate_from_zero_token(text, repo, box):
    """Substitute `{repoRoot}` and `{box}` inside one `fromZero.steps` part.

    Never `{subject}`: the from-zero side may not reference the producer it
    exists to be compared against, so that token is refused here
    structurally rather than by convention -- the same discipline
    `interpolate_token` already gives a token it never declared.
    """
    def replace(match):
        token = match.group(1)
        if token == "subject":
            raise Unprobeable(
                "kind=subject-reference: a fromZero step's argv names "
                "{subject}; the from-zero side may never reference the "
                "producer it exists to be compared against")
        if token not in FROM_ZERO_TOKENS:
            raise Unprobeable(
                f"the recipe's step names an unknown token {{{token}}}; only "
                f"{sorted(FROM_ZERO_TOKENS)} interpolate")
        return {"repoRoot": str(repo), "box": str(box)}[token]
    return _TOKEN_RE.sub(replace, text)


def assert_no_subject_reference(text, subject, repo):
    """Refuse an interpolated `fromZero` part that names the subject by its
    absolute or repo-relative path, even when no `{subject}` token was used
    to get there.

    This is what actually catches the tar recipe's own defect: its argv
    never used `{subject}`, it spelled the path out by hand
    (`HEAD:.claude/skills/skill-audit`). Refusing the token alone would
    have missed it.
    """
    subject_abs = str(subject)
    try:
        subject_rel = subject.relative_to(repo).as_posix()
    except ValueError:
        subject_rel = None
    if subject_abs in text or (subject_rel and subject_rel in text):
        raise Unprobeable(
            "kind=subject-reference: a fromZero step's argv names the "
            f"subject ({subject_abs!r}); the from-zero side may never "
            "reference the producer it exists to be compared against")


def run_box_step(step, repo, subject, box, timeout):
    """One `fromZero` build step, run inside the box with no shell.

    Mirrors `probe_code_side`'s discipline: argv as a list of strings,
    `shell=False`, a hang becomes exit `2` rather than a wait forever, and a
    nonzero exit from the build itself is an inability to build from-zero,
    never an empty from-zero side.

    A bare list is kind `exec`, unchanged from before this change. A dict
    must declare a `kind` from `BOX_STEP_KINDS`; `driver` additionally
    resolves `cwd` under the box (refusing an occupied one), builds a
    constructed environment from `env`'s declared names intersected with
    `DRIVER_ENV_ALLOWLIST`, and proves `argv[0]`'s real path sits outside
    both the repository and the subject. Every part of every step, either
    kind, is interpolated through `FROM_ZERO_TOKENS` alone and scanned for
    a literal reference to the subject.

    Returns a small info dict -- `run_structure` transcribes a `driver`
    step's own info into the report-facing `ignorance` block; an `exec`
    step returns only `{"stepKind": "exec"}`, carrying nothing to
    transcribe. Keyed `stepKind`, never `kind`: `EscalationPartitionTests`
    holds `"kind"` to exactly one meaning across this module -- a note's or
    a stall's own classification, produced solely by `note()` and
    `stalled()` -- and a second dict literal carrying that key anywhere
    else is refused structurally, on sight, regardless of what it means.
    This step-kind value is a different word wearing the same spelling by
    accident; the fix is to stop sharing the spelling, not to carve an
    exception into the lock.
    """
    if isinstance(step, list):
        kind, raw_argv, cwd_spec, env_spec = "exec", step, None, None
    elif isinstance(step, dict):
        kind = step.get("kind", "exec")
        if kind not in BOX_STEP_KINDS:
            raise Unprobeable(
                f"a fromZero step names kind {kind!r}, which is not one of "
                f"{BOX_STEP_KINDS}")
        raw_argv = step.get("argv")
        cwd_spec = step.get("cwd")
        env_spec = step.get("env")
    else:
        raise Unprobeable("a fromZero step must be a list or a dict")

    if not raw_argv or not all(isinstance(part, str) for part in raw_argv):
        raise Unprobeable("a fromZero step's argv must be a list of strings")

    argv = [interpolate_from_zero_token(part, repo, box) for part in raw_argv]
    for part in argv:
        assert_no_subject_reference(part, subject, repo)

    step_cwd = box
    if cwd_spec:
        step_cwd = resolve_under(cwd_spec, box, "driver.cwd")
        if not box_empty_or_absent(step_cwd):
            raise Unprobeable(
                f"a fromZero driver step's cwd is not empty: {step_cwd}; "
                "an occupied box is never silently adopted")
        step_cwd.mkdir(parents=True, exist_ok=True)

    child_env = None
    info = {"stepKind": kind}
    if kind == "driver":
        names = env_spec or []
        unknown = sorted(set(names) - set(DRIVER_ENV_ALLOWLIST))
        if unknown:
            raise Unprobeable(
                f"a fromZero driver step names env {unknown}, outside "
                f"{sorted(DRIVER_ENV_ALLOWLIST)}")
        child_env = {name: os.environ[name] for name in names
                    if name in os.environ}
        real_path = shutil.which(argv[0], path=child_env.get("PATH"))
        if not real_path:
            raise Unprobeable(
                f"a fromZero driver step's argv[0] is not executable: "
                f"{argv[0]!r}")
        real = Path(real_path).resolve()
        inside_repo = real == repo or repo in real.parents
        inside_subject = real == subject or subject in real.parents
        if inside_repo or inside_subject:
            raise Unprobeable(
                f"kind=driver-not-external: {argv[0]!r} resolves to {real}, "
                "inside the repository or the subject; a driver shipped "
                "inside what it audits is not external")
        info.update({"argv": list(argv), "argv0RealPath": str(real),
                    "cwd": str(step_cwd), "envNames": sorted(names)})

    try:
        completed = subprocess.run(
            argv, cwd=str(step_cwd), shell=False, env=child_env,
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise Unprobeable(f"a fromZero step's argv[0] is not executable: {error}")
    except subprocess.TimeoutExpired:
        raise Unprobeable(
            f"a fromZero step did not answer within {timeout}s; a build that "
            "hangs is an inability to look, never an empty from-zero side")
    if completed.returncode != 0:
        raise Unprobeable(
            f"a fromZero step exited {completed.returncode}: "
            f"{completed.stderr.strip()[:400]}")
    return info


def ignorance_control_gate(box, exclude):
    """Prove the from-zero box's own emptiness detector can see
    contamination, before trusting that emptiness at all.

    Modelled on `candidate_gate_steps`'s inverted control: seed a nonce the
    tool generates, demand `tree_digest` name it, erase, demand it read
    empty again. An `exclude` broad enough to hide the seed -- `["*"]`, or
    anything that over-matches -- would make every box look empty and the
    ignorance claim true by construction, indistinguishable from its own
    absence; proving the detector sees the seed first is what makes this a
    control rather than ceremony.
    """
    nonce = uuid.uuid4().hex
    relative = f"{IGNORANCE_CONTROL_DIR}/{nonce}.txt"
    marker = box / IGNORANCE_CONTROL_DIR / f"{nonce}.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(nonce, encoding="utf-8")
    seeded = tree_digest(box, exclude)
    if relative not in seeded:
        raise Unprobeable(
            "kind=ignorance-control-stalled: the box's own emptiness "
            f"detector did not see a seeded marker at {relative!r}; every "
            "from-zero conclusion downstream is unreached until the "
            "detector can prove it sees contamination")
    erase_box(box)
    box.mkdir(parents=True, exist_ok=True)
    if not box_empty_or_absent(box, exclude):
        raise Unprobeable(
            "kind=ignorance-control-stalled: the box did not read empty "
            "immediately after being re-erased")
    return "passed"


def box_empty_or_absent(box, exclude=()):
    """Whether a box holds no files, proven by content.

    Never by `git status`: `git status --porcelain` over an ignored tree is
    empty by construction, so it can only ever agree, and it would report a
    box that still has files sitting inside it as clean.
    """
    return tree_digest(box, exclude) == {}


def erase_box(box):
    """Remove a box entirely.

    `shutil.rmtree` rather than a hand-rolled walk, so `tree_digest` stays the
    one place in this module allowed to walk a filesystem tree.
    """
    if box.exists():
        shutil.rmtree(box)


def resolve_under(raw, base, label):
    """A recipe-declared root, resolved under `base` and refused if it climbs
    out -- the same discipline `resolve_site` and `probe_code_side`'s `cwd`
    both apply to every other recipe-declared path in this module.
    """
    raw = raw or "."
    parts = Path(raw).parts
    if Path(raw).is_absolute() or ".." in parts:
        raise Unprobeable(f"the recipe's {label} must stay under its root: {raw!r}")
    resolved = (base / raw).resolve()
    if base != resolved and base not in resolved.parents:
        raise Unprobeable(f"the recipe's {label} resolves outside its root: {raw!r}")
    return resolved


#: The only place a `doctrine_side` status becomes a note's `kind`. Hoisted
#: out of `run_roster`'s own inline dict so `note()` can be the single
#: producer of every entry in `notes[]`: a status this map does not name
#: cannot reach `notes[]` at all, which is what lets `ESCALATION_BUCKETS` be
#: checked against `note()`'s own call sites instead of against a second,
#: hand-maintained roster.
DOCTRINE_SIDE_NOTES = {
    "complement": (
        "no-closed-roster",
        "this table is a deliberate subset, so it supports the phantom "
        "direction and never the unregistered one"),
    "no-closed-roster": (
        "no-closed-roster",
        "the set is stated in prose or in another language here, and "
        "prose is what the documented side may not be read out of"),
    "heading-not-found": (
        "heading-not-found",
        "the recipe claims a scope for this table but its quoted heading "
        "is not on disk, so the claim is refused rather than trusted"),
    "scope-claimed-without-heading": (
        "scope-claimed-without-heading",
        "a scope claim with no quoted heading is unfalsifiable"),
}


def note(kind, detail, path, searched):
    """The only way an entry enters `notes[]`.

    A literal scan for `"kind":` strings cannot classify what this module
    emits: `run_roster` writes `"kind": kind` from a variable, which hides
    three of the four escalatable kinds from any such scan. Routing every
    entry through this one constructor instead means the totality lock in
    `EscalationPartitionTests` can scan `note()`'s own call sites for the
    kinds it actually passes, and can refuse -- as a structural fact, not a
    convention -- any dict literal elsewhere that carries a `"kind"` key at
    all.
    """
    return {"detail": detail, "kind": kind, "path": path, "searched": searched}


#: Every kind `note()` can emit, or that `DOCTRINE_SIDE_NOTES` names,
#: partitioned into exactly one bucket. Escalatable: prose exists but could
#: not be derived, and a zero-model probe may still decide it. Consequence:
#: produced only because an escalatable note already fired on the same
#: surface, and never escalated a second time on its own. Deterministic
#: exclusion: a shape or a spelling with no prose behind it to re-read, so
#: escalating it would send a reader after a surface that has nothing to
#: read. `EscalationPartitionTests` holds this constant to the emission
#: sites the same way `FORBIDDEN_SUPPORT` and `ADJUDICATIONS` are held to
#: theirs -- never a second hand-maintained roster.
ESCALATION_BUCKETS = {
    "escalatable": (
        "no-closed-roster", "heading-not-found",
        "scope-claimed-without-heading",
        "no derivation available for this surface"),
    "consequence": ("comparison-not-run",),
    "deterministic-exclusion": ("shape-not-walkable", "case-only-divergence"),
}


def escalation_hint(recipe):
    """The zero-model-probe hint attached to every escalatable note.

    Rung one -- `"probe"` -- is selected only when the emitting recipe
    already declares `probe: "refusal"`: the tool already holds, at
    `recipe["extract"]`, the exact pattern a `candidateGates` control gate
    needs. Move 8 (`walkthrough`) is the mechanism a `probe` rung's
    candidates are driven through. Every other recipe gets rung
    `"readers"`: a two-reader comparison is required before any candidate
    may be proposed at all.
    """
    if recipe.get("probe") == "refusal":
        return {"needs": "candidates", "probe": "8",
                "refusal": recipe.get("extract"), "rung": "probe"}
    return {"needs": None, "probe": None, "refusal": None, "rung": "readers"}


#: Shapes a declared cell can carry that the walk helper can never produce.
#: Expanding one of these against the disk would let the declared side build
#: the very set it is meant to be checked against; counting it as a
#: divergence would blame the disk for a spelling. Neither happens here: the
#: cell is set aside in `notes` instead.
_GLOB_CHARS = set("*?[]")


def normalize_declared_paths(raw_members):
    """Declared path cells, normalised for comparison against a walk.

    POSIX separators, a leading `./` stripped, no trailing slash, case
    preserved, sets compared sorted. A cell whose shape the walk can never
    produce -- a trailing slash, an absolute path, a `..` segment, a glob
    character, or a backslash -- is set aside as `shape-not-walkable` rather
    than normalised, and excluded from every side of the comparison.
    """
    normalised = set()
    notes = []
    for raw in raw_members:
        reason = None
        if raw.endswith("/"):
            reason = "the cell ends with a trailing slash"
        elif "\\" in raw:
            reason = "the cell contains a backslash"
        elif any(char in raw for char in _GLOB_CHARS):
            reason = "the cell contains a glob character"
        elif Path(raw).is_absolute():
            reason = "the cell is an absolute path"
        elif ".." in Path(raw).parts:
            reason = "the cell contains a `..` segment"
        if reason:
            notes.append(note(
                "shape-not-walkable",
                f"{reason}, so it is excluded from every side rather than "
                "expanded against the disk",
                raw, None))
            continue
        cleaned = raw[2:] if raw.startswith("./") else raw
        normalised.add(cleaned)
    return normalised, notes


def case_only_divergences(label_a, set_a, label_b, set_b):
    """Members that agree only case-insensitively, named but never folded.

    Folding them would treat a spelling difference as agreement. Leaving them
    unfolded means such a pair still surfaces as a divergence on the
    arithmetic side, and this note explains why rather than leaving the
    reader to guess.
    """
    lower_b = {}
    for member in set_b:
        lower_b.setdefault(member.lower(), []).append(member)
    found = []
    for member in set_a:
        if member in set_b:
            continue
        for other in lower_b.get(member.lower(), []):
            found.append(note(
                "case-only-divergence",
                f"{label_a} names {member!r}; {label_b} names "
                f"{other!r}, matching only case-insensitively",
                member, None))
    return found


def structure_outcome(declared, disk, from_zero):
    """The arithmetic adjudication: which side, if any, is the odd one out.

    `ADJUDICATIONS` is untouched -- this is a different vocabulary, for a
    different question. Mapping one of these outcomes to a `doctrine wrong` /
    `artefact wrong` verdict is a doctrine decision the auditor makes when it
    writes the report, not something this function does.
    """
    union = declared | disk | from_zero
    only_in = {
        "declared": sorted(declared - disk - from_zero),
        "disk": sorted(disk - declared - from_zero),
        "fromZero": sorted(from_zero - declared - disk),
    }
    missing_from = {
        "declared": sorted(union - declared),
        "disk": sorted(union - disk),
        "fromZero": sorted(union - from_zero),
    }
    if declared == disk == from_zero:
        outcome = "agree"
    elif declared == from_zero:
        outcome = "disk-stale"
    elif declared == disk:
        outcome = "builder-broken"
    elif disk == from_zero:
        outcome = "document-wrong"
    else:
        outcome = "three-way-divergence"
    return outcome, only_in, missing_from


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
    report.add_argument(
        "--moves", default=None,
        help="override path to the doctrine file whose moves table the "
             "move-outcome roster is derived from (default: this skill's own "
             "SKILL.md, resolved relative to this script)")
    report.add_argument(
        "--subject", default=None,
        help="re-derive the '## Frozen' digest from this path and compare "
             "it; without it the payload carries rederived: false and only "
             "finding-vs-'## Frozen' consistency is checked")

    structure = commands.add_parser(
        "structure",
        help="derive declared, on-disk, and from-zero structure and "
             "adjudicate which side is wrong")
    structure.add_argument("--subject", required=True,
                           help="the subject's root directory")
    structure.add_argument("--spec", required=True,
                           help="the JSON recipe describing the declared, "
                                "disk, and fromZero sides")
    structure.add_argument("--repo-root", default=".",
                           help="the root the box and {repoRoot} token "
                                "resolve under")
    structure.add_argument("--timeout", type=int, default=30,
                           help="seconds before a hanging build step is exit 2")

    walkthrough = commands.add_parser(
        "walkthrough",
        help="drive a recipe's ordered sequence against a real, shared box "
             "and name the index where it stalls")
    walkthrough.add_argument("--subject", required=True,
                             help="the subject's root directory")
    walkthrough.add_argument("--spec", required=True,
                             help="the JSON recipe describing the ordered "
                                  "sequence of steps")
    walkthrough.add_argument("--repo-root", default=".",
                             help="the root the box and {repoRoot} token "
                                  "resolve under")
    walkthrough.add_argument("--timeout", type=int, default=30,
                             help="seconds before a hanging step is a stall "
                                  "of kind timeout")

    reading_diff = commands.add_parser(
        "reading-diff",
        help="compare two supplied readings of one prose surface by "
             "mechanical diff; never sets closed_seen")
    reading_diff.add_argument("--surface", required=True,
                              help="the surface name recorded in the payload")
    reading_diff.add_argument(
        "--reading", action="append", default=[],
        help="a reading file; declare this flag exactly twice")

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
        notes.append(note(
            "no derivation available for this surface",
            "the subject exposes neither a refusal message nor a parser, "
            "so neither language-independent probe applies",
            str(spec_path), f"{spec_path}:1-1"))
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
        kind, detail = DOCTRINE_SIDE_NOTES[status]
        notes.append(note(kind, detail, str(path), span))

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
        notes.append(note(
            "comparison-not-run",
            "no site yielded a closed roster, so the unregistered direction "
            "is not computed; reporting every accepted member as "
            "undocumented would invent one finding per member and none of "
            "them would be about this subject",
            str(subject), f"{subject}:1-1"))
    unregistered = sorted(set(code) - doctrine) if closed_seen else []
    phantom = sorted(doctrine - set(code))
    return finish(code, sorted(doctrine), notes, unregistered, phantom,
                  comparison, recipe, subject, repo, duplicated)


def finish(code, doctrine, notes, unregistered, phantom, comparison,
           recipe, subject, repo, duplicated=None):
    mismatches = []
    for site in recipe.get("numeralPaths", []):
        mismatches.extend(numeral_mismatches(resolve_site(site, subject, repo)))
    exclude = tuple(recipe.get("exclude", ()))
    escalatable = [dict(entry, escalation=escalation_hint(recipe))
                  for entry in notes
                  if entry["kind"] in ESCALATION_BUCKETS["escalatable"]]
    emit({
        "code": code,
        "comparison": comparison,
        "doctrine": doctrine,
        "duplicated": duplicated or [],
        "escalatable": escalatable,
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "notes": notes,
        "numeralMismatch": mismatches,
        "phantom": phantom,
        "surface": recipe.get("surface", ""),
        "unregistered": unregistered,
    })
    return 0


def run_structure(args):
    """Derive declared, on-disk, and from-zero, and adjudicate arithmetically.

    Exit `0` for any verdict, including a three-way divergence. Exit `2` when
    a side cannot be derived, when the box is not ours to adopt, or when the
    build wrote outside the box -- none of those is a finding, each is an
    inability to look.
    """
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no structure recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the structure recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    surface = recipe.get("surface", "")
    if not surface:
        raise Unprobeable("the recipe names no surface to box the build under")
    exclude = tuple(recipe.get("exclude", ()))

    declared_site = recipe.get("declared", {})
    declared_path = resolve_site(declared_site, subject, repo)
    declared_text = read_site(declared_path)
    raw_members, _ = doctrine_side(declared_text, declared_site)
    declared_set, notes = normalize_declared_paths(raw_members)
    if not declared_set:
        raise Unprobeable(
            "the declared side normalises to zero members; an empty declared "
            "side would report the entire disk as builder-broken")

    disk_root = resolve_under(recipe.get("disk", {}).get("root"), subject,
                              "disk.root")
    if not disk_root.is_dir():
        raise Unprobeable(f"the recipe's disk.root does not exist: {disk_root}")
    disk_set = set(tree_digest(disk_root, exclude))
    if not disk_set:
        raise Unprobeable(
            "the on-disk side normalises to zero members; an empty on-disk "
            "side would report the entire declared side as disk-stale")

    from_zero_spec = recipe.get("fromZero", {})
    steps = from_zero_spec.get("steps", [])
    if not steps:
        raise Unprobeable("the recipe declares no fromZero.steps to build from")

    box = repo / "implementations" / f"_structure_{surface}"
    before_empty = box_empty_or_absent(box)
    if not before_empty:
        raise Unprobeable(
            f"a non-empty box already occupies {box}; remove it by hand "
            "before running structure again -- an occupied box is never "
            "silently adopted")
    box.mkdir(parents=True, exist_ok=True)

    try:
        control_gate = ignorance_control_gate(box, exclude)
        box_digest_before = frozen_digest(box, exclude)
        subject_before = tree_digest(subject, exclude)
        step_infos = [run_box_step(step, repo, subject, box, args.timeout)
                     for step in steps]
        box_digest_after = frozen_digest(box, exclude)

        from_zero_root = resolve_under(
            from_zero_spec.get("root"), box, "fromZero.root")

        subject_after = tree_digest(subject, exclude)
        if subject_before != subject_after:
            changed = sorted(
                p for p in set(subject_before) | set(subject_after)
                if subject_before.get(p) != subject_after.get(p))
            raise Unprobeable(
                "kind=build-escaped-the-box: the fromZero build changed the "
                f"subject at {changed}; a build writing outside its box is an "
                "inability to look, never a finding, because the tool cannot "
                "tell an intended write from an escape")

        if not from_zero_root.is_dir():
            raise Unprobeable(
                "the recipe's fromZero.root does not exist after the build: "
                f"{from_zero_root}")
        from_zero_set = set(tree_digest(from_zero_root, exclude))
        if not from_zero_set:
            raise Unprobeable(
                "the from-zero side normalises to zero members; an empty "
                "from-zero side would report the entire disk as "
                "builder-broken")
    finally:
        erase_box(box)

    after_removed = box_empty_or_absent(box)

    notes = notes + (
        case_only_divergences("declared", declared_set, "disk", disk_set)
        + case_only_divergences("declared", declared_set, "fromZero", from_zero_set)
        + case_only_divergences("disk", disk_set, "fromZero", from_zero_set))

    outcome, only_in, missing_from = structure_outcome(
        declared_set, disk_set, from_zero_set)

    # The enforceable half of `## User drive`, machine-emitted rather than
    # narrated: whichever step actually declared `kind: driver` is the one
    # whose argv/cwd/env-names/real-path a report transcribes. A recipe
    # built entirely from `exec` steps carries no driver step at all, and
    # `driver` stays `None` -- `## User drive`'s required content is what
    # demands one exist when stage 2 is declared `ran`, not this payload.
    driver_info = next(
        (info for info in step_infos if info.get("stepKind") == "driver"),
        None)

    emit({
        "containment": {"afterRemoved": after_removed, "beforeEmpty": before_empty,
                        "box": str(box)},
        "escalatable": [dict(entry, escalation=escalation_hint(recipe))
                       for entry in notes
                       if entry["kind"] in ESCALATION_BUCKETS["escalatable"]],
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "ignorance": {
            "argv": driver_info.get("argv") if driver_info else None,
            "argv0RealPath": driver_info.get("argv0RealPath") if driver_info else None,
            "boxDigestAfter": box_digest_after,
            "boxDigestBefore": box_digest_before,
            "controlGate": control_gate,
            "cwd": driver_info.get("cwd") if driver_info else None,
            "envNames": driver_info.get("envNames") if driver_info else [],
        },
        "missingFrom": missing_from,
        "notes": notes,
        "onlyIn": only_in,
        "outcome": outcome,
        "sides": {"declared": sorted(declared_set), "disk": sorted(disk_set),
                 "fromZero": sorted(from_zero_set)},
        "surface": surface,
    })
    return 0


#: The `expect` keys a walkthrough step may declare. `exit` defaults to
#: `"any"`, which asserts nothing on its own -- `declares_expectation` treats
#: an `expect` naming only `exit: any` the same as no `expect` at all, because
#: functionally the two are identical: a gate that always matches whatever it
#: sees is not a gate.
STEP_EXPECT_KEYS = ("exit", "stdout", "stderr", "absent")


def declares_expectation(expect):
    """Whether a walkthrough step's `expect` asserts anything at all.

    A step whose `expect` is missing, empty, or names only `exit: "any"`
    with nothing else declares no expectation, and `run_walkthrough` refuses
    it as `Unprobeable` before ever running the step's command.
    """
    if not expect:
        return False
    if expect.get("exit", "any") != "any":
        return True
    return any(key in expect for key in STEP_EXPECT_KEYS[1:])


def step_matches_expect(expect, returncode, stdout, stderr):
    """Whether one step's real observation matches its own declared `expect`.

    Every declared part of `expect` must hold for the step to be `passed`,
    whatever its exit code -- a step matching its own documented refusal is a
    pass, not a stall. Called only once `declares_expectation` has confirmed
    `expect` asserts something; an `expect` asserting nothing never reaches
    here.
    """
    exit_expect = expect.get("exit", "any")
    if exit_expect == "nonzero":
        if returncode == 0:
            return False
    elif exit_expect != "any" and returncode != exit_expect:
        return False
    if "stdout" in expect and not re.search(expect["stdout"], stdout):
        return False
    if "stderr" in expect and not re.search(expect["stderr"], stderr):
        return False
    if "absent" in expect and re.search(expect["absent"], stdout + stderr):
        return False
    return True


def stalled(kind, index, detail):
    """A walkthrough verdict's own `stall` dict.

    `kind` here is a verdict about *how* a step failed to match its own
    `expect` -- `"missing-executable"`, `"timeout"`, `"contradiction"` --
    never an undecidability. Kept apart from `note()` so a totality lock
    over `notes[]`'s kinds never has to tell a verdict from an unread
    surface by guessing; it simply never looks inside `stalled()` at all.
    """
    return {"detail": detail, "index": index, "kind": kind}


#: The one absurd nonce the `candidateGates` control gate is driven with --
#: a value no real flag or subcommand could ever collide with, so what the
#: subject does with it is a fact about the refusal channel itself, never
#: about a real candidate.
CANDIDATE_GATE_CONTROL_NONCE = "__AUDIT_CONTROL_NONCE__"


def candidate_gate_steps(spec, repo, subject, box):
    """Expand one `candidateGates` block into concrete walkthrough steps:
    one inverted control gate, first, then one gate per candidate.

    One declared `refusal` derives both expectations, so nothing about the
    refusal pattern is restated. The control's own expectation is
    deliberately inverted -- it demands the refusal be *present* -- so a
    channel that never refuses stalls at the control's own index and
    leaves every candidate `unreached` through the walkthrough machinery
    that already exists, no special case and no new branch. No candidate is
    ever reported accepted against a channel not proven capable of
    refusing.
    """
    if not spec:
        return []
    refusal = spec["refusal"]
    raw_argv = spec["argv"]
    candidates = spec["candidates"]

    def gate_argv(candidate):
        return [interpolate_gate_token(part, repo, subject, box, candidate)
               for part in raw_argv]

    steps = [{
        "argv": gate_argv(CANDIDATE_GATE_CONTROL_NONCE),
        "expect": {"exit": "any", "stderr": refusal},
        "role": "gate",
        "name": "candidateGates control: the refusal channel is live",
    }]
    for candidate in candidates:
        steps.append({
            "argv": gate_argv(candidate),
            "expect": {"exit": "any", "absent": refusal},
            "role": "gate",
            "name": f"candidateGates candidate {candidate!r} must not be refused",
        })
    return steps


def run_walkthrough(args):
    """Drive a recipe's ordered sequence against one shared box, and name the
    index where it stalls.

    Exit `0` for any verdict, including a stall: a stall is a finding on its
    own, never an inability to look. Exit `2` only when the flow itself could
    not be entered -- a step declaring no expectation, the very first step's
    own command missing, or a `role: "setup"` step failing, all mean there is
    nothing to report on yet.

    Each step declares `role: "setup" | "gate"`, defaulting to `"gate"`
    (precedent: `"reset": true`). A setup step stands up a fixture and
    asserts nothing about the subject -- it must declare no `expect`, is
    never counted among gates that passed, and its failure is reported
    directly as `"setup-failed"` (never `"stalled"`, never routed through
    `Unprobeable`, whose fixed shape cannot name an index): a void run has no
    unchecked gates, it has no run. A recipe with no `"gate"` step at all
    asserts nothing about the subject either, and is refused before it runs.

    One box for the whole sequence, state accumulating as a user's would; a
    step may declare `"reset": true` to demand a fresh, empty box from that
    point on. The box lives at `{repoRoot}/implementations/_walkthrough_
    {surface}`, created only if empty or absent, and removed in a `finally`
    whose absence is proven by `tree_digest`, exactly like `structure`'s box.
    """
    spec_path = Path(args.spec)
    if not spec_path.is_file():
        raise Unprobeable(f"no walkthrough recipe at {spec_path}")
    try:
        recipe = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Unprobeable(f"the walkthrough recipe is unreadable: {error}")

    subject = Path(args.subject).resolve()
    repo = Path(args.repo_root).resolve()
    surface = recipe.get("surface", "")
    if not surface:
        raise Unprobeable("the recipe names no surface to box the sequence under")
    box = repo / "implementations" / f"_walkthrough_{surface}"
    steps_spec = list(recipe.get("steps", [])) + candidate_gate_steps(
        recipe.get("candidateGates"), repo, subject, box)
    if not steps_spec:
        raise Unprobeable("the recipe declares no steps to walk through")
    if not any(step.get("role", "gate") == "gate" for step in steps_spec):
        raise Unprobeable(
            "the recipe declares no gates to walk through; a walkthrough of "
            "only setup steps asserts nothing about the subject")
    exclude = tuple(recipe.get("exclude", ()))

    before_empty = box_empty_or_absent(box)
    if not before_empty:
        raise Unprobeable(
            f"a non-empty box already occupies {box}; remove it by hand "
            "before running walkthrough again -- an occupied box is never "
            "silently adopted")
    box.mkdir(parents=True, exist_ok=True)

    steps_report = []
    stall = None
    setup_failure = None
    try:
        for index, step in enumerate(steps_spec):
            name = step.get("name", f"step {index}")
            role = step.get("role", "gate")

            if stall is not None:
                steps_report.append({
                    "expected": step.get("expect"), "index": index,
                    "role": role, "name": name, "observed": None,
                    "outcome": "unreached"})
                continue

            expect = step.get("expect")
            if role == "setup":
                if declares_expectation(expect):
                    raise Unprobeable(
                        f"step {index} ({name!r}) is role 'setup' but "
                        "declares an expectation; a setup step asserting "
                        "something about the subject is a gate wearing the "
                        "wrong label")
            elif not declares_expectation(expect):
                raise Unprobeable(
                    f"step {index} ({name!r}) declares no expectation; a "
                    "gate that asserts nothing is not a gate")

            if step.get("reset"):
                erase_box(box)
                box.mkdir(parents=True, exist_ok=True)

            raw_argv = step.get("argv") or []
            if not raw_argv or not all(isinstance(part, str) for part in raw_argv):
                raise Unprobeable(
                    f"step {index} ({name!r})'s argv must be a non-empty "
                    "list of strings")
            argv = [interpolate_token(part, repo, subject, box) for part in raw_argv]

            step_cwd = box
            if step.get("cwd"):
                step_cwd = resolve_under(step["cwd"], box, "step.cwd")

            try:
                completed = subprocess.run(
                    argv, cwd=str(step_cwd), shell=False,
                    capture_output=True, text=True, timeout=args.timeout)
            except FileNotFoundError as error:
                if role == "setup":
                    setup_failure = {
                        "detail": f"setup step {index} ({name!r})'s argv[0] "
                                  f"is not executable: {error}",
                        "index": index, "name": name}
                    break
                if index == 0:
                    raise Unprobeable(
                        f"step 0's argv[0] is not executable: {error}; the "
                        "flow was never entered")
                stall = stalled(
                    "missing-executable", index,
                    f"step {index} ({name!r})'s argv[0] is not executable: "
                    f"{error}")
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": None, "outcome": "stalled"})
                continue
            except subprocess.TimeoutExpired:
                if role == "setup":
                    setup_failure = {
                        "detail": f"setup step {index} ({name!r}) did not "
                                  f"answer within {args.timeout}s",
                        "index": index, "name": name}
                    break
                stall = stalled(
                    "timeout", index,
                    f"step {index} ({name!r}) did not answer within "
                    f"{args.timeout}s")
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": None, "outcome": "stalled"})
                continue

            observed = {"exit": completed.returncode,
                       "stderr": completed.stderr, "stdout": completed.stdout}

            if role == "setup":
                if completed.returncode != 0:
                    setup_failure = {
                        "detail": f"setup step {index} ({name!r}) exited "
                                  f"{completed.returncode}",
                        "index": index, "name": name}
                    break
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": observed,
                    "outcome": "setup-ok"})
                continue

            if step_matches_expect(expect, completed.returncode,
                                   completed.stdout, completed.stderr):
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": observed, "outcome": "passed"})
            else:
                stall = stalled(
                    "contradiction", index,
                    f"step {index} ({name!r})'s observation contradicted "
                    "its own expect")
                steps_report.append({
                    "expected": expect, "index": index, "role": role,
                    "name": name, "observed": observed, "outcome": "stalled"})
    finally:
        erase_box(box)

    if setup_failure is not None:
        # A void run has no unchecked gates, it has no run: `stall` and
        # `unreached` stay at their never-ran values rather than the
        # partial `steps_report` built so far. Emitted directly, not
        # through `Unprobeable`, whose fixed `{"error", "status"}` shape
        # cannot name which step failed.
        emit({
            "detail": setup_failure["detail"],
            "index": setup_failure["index"],
            "name": setup_failure["name"],
            "stall": None,
            "status": "setup-failed",
            "unreached": [],
        })
        return 2

    after_removed = box_empty_or_absent(box)
    unreached = [entry["index"] for entry in steps_report
                if entry["outcome"] == "unreached"]
    gates_declared = sum(1 for step in steps_spec
                         if step.get("role", "gate") == "gate")
    gates_passed = sum(1 for entry in steps_report
                       if entry["role"] == "gate" and entry["outcome"] == "passed")

    emit({
        "containment": {"afterRemoved": after_removed, "beforeEmpty": before_empty,
                        "box": str(box)},
        "frozen": {"digest": frozen_digest(subject, exclude),
                   "exclude": list(exclude), "subject": str(subject)},
        "gates": {"declared": gates_declared, "passed": gates_passed},
        "stall": stall,
        "steps": steps_report,
        "surface": surface,
        "unreached": unreached,
    })
    return 0


#: `reading-diff`'s own stated epistemic limit, carried in every payload it
#: emits regardless of verdict. Two readers agreeing proves the prose has
#: **one reading**, never that it is closed -- a weaker and different claim,
#: and this string is what stops a report from quietly upgrading one into
#: the other by copying the output without its limit.
READING_DIFF_LIMIT = (
    "agreement between two readers proves the prose has one reading, "
    "never that it is closed; comparison stays not-run for this surface, "
    "permanently")


def reading_pair_digest(paths):
    """One stable `sha256` summary over the exact bytes of the two supplied
    reading files -- the same per-path idiom `frozen_digest` uses, scoped to
    these two files rather than to a directory tree.

    `reading-diff` has no subject directory to walk: the two reading files
    are the bytes the comparison is about. So this reads each file directly
    rather than calling `tree_digest`, which stays the only walker in this
    module per `SingleWalkTests`.
    """
    ordered = sorted(paths, key=str)
    lines = "\n".join(
        f"{path} {hashlib.sha256(path.read_bytes()).hexdigest()}"
        for path in ordered)
    return "sha256:" + hashlib.sha256(lines.encode("utf-8")).hexdigest()


def run_reading_diff(args):
    """Compare exactly two supplied readings of one prose surface by
    mechanical diff, and report agreement or divergence.

    A subcommand, never a flag or a recipe field: either of those would
    route a supplied reading back through `run_roster`, the one function
    that ever assigns `closed_seen = True`. This function never calls
    `doctrine_side`, `probe_code_side`, or `finish` -- asserted over its own
    syntax tree by `ReadingDiffTests` -- so a reading of prose can propose
    candidates, and can never itself close a comparison.

    `comparison` is emitted as the literal `"not-run"`, always: two readers
    agreeing proves the prose has one reading, never that it is closed.
    And when a supplied reading names a strict superset of some real code
    side, the payload still carries no `"unregistered"` key at all -- not an
    empty one, which would read as "checked and found none" rather than
    "never checked".

    Exit `0` for either verdict -- agreement or divergence. Exit `2` only
    when the tool could not look: not exactly two `--reading` flags, a
    reading file that cannot be read, or a reading with no non-empty
    `members` list.
    """
    readings = args.reading or []
    if len(readings) != 2:
        raise Unprobeable(
            f"reading-diff takes exactly two --reading flags; got "
            f"{len(readings)}")

    paths = [Path(raw) for raw in readings]
    member_sets = []
    for path in paths:
        if not path.is_file():
            raise Unprobeable(f"no reading file at {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise Unprobeable(f"the reading file is unreadable: {error}")
        members = data.get("members")
        if not isinstance(members, list) or not members:
            raise Unprobeable(
                f"the reading file at {path} declares no non-empty "
                "members list")
        member_sets.append({str(member) for member in members})

    set_a, set_b = member_sets
    shared = sorted(set_a & set_b)
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    agreement = "single-reading" if not only_a and not only_b else "divergent"

    emit({
        "agreement": agreement,
        "candidates": shared,
        "comparison": "not-run",
        "frozen": {"digest": reading_pair_digest(paths), "exclude": [],
                   "subject": "|".join(str(path) for path in paths)},
        "limit": READING_DIFF_LIMIT,
        "onlyIn": {"a": only_a, "b": only_b},
        "shared": shared,
        "surface": args.surface,
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
    "disputed-severity": "## Disputed severity",
    "drives": "## Drives",
    "evidence-marker": "- Evidence:",
    "falsifier": "## Falsifier",
    "found-by": "- Found by:",
    "frozen": "## Frozen",
    "move-number": "- Move:",
    "move-outcomes": "## Move outcomes",
    "not-adjudicable": "## Not adjudicable",
    "ranked-findings": "## Ranked findings",
    "reading-diff": "## Reading diff",
    "repair-units": "## Repair units",
    "stage-outcomes": "## Stage outcomes",
    "unchecked-section": "## Unchecked",
    "undecidable": "## Undecidable",
    "user-drive": "## User drive",
}

#: Every stage's own not-run value for the `REPORT_SHAPE` field it demands,
#: keyed by the same `REPORT_SHAPE` key the stages table names in its
#: `Demands` cell. Stage 4's row names `found-by`; while that stage is
#: `skipped`, `- Found by: not-compared` is the honest default every other
#: finding already carries, and only a `ran` stage-4 row tightens what is
#: accepted, per the marker's own shape rather than a second hand-written
#: rule.
FIELD_NOT_RUN = {"found-by": "not-compared"}

#: The header of the moves table this skill's own `SKILL.md` carries. Read
#: with the same `markdown_table_rows` the documented side of every other
#: comparison uses, so a report's required move-outcome roster comes from
#: parsing that table rather than from a list held here -- a hand-written
#: roster in the validator would ship the exact defect this skill exists to
#: find.
MOVES_TABLE_HEADER = "| Move | Ships as | Lock |"

#: `## Move outcomes` rows: `- Move: <id>: ran` or `- Move: <id>: skipped:
#: <reason>`. `<id>` is either a move's number or the literal `textual`, for
#: the one row the moves table carries with no leading digit.
MOVE_OUTCOME_ROW = re.compile(
    r"^-\s*Move:\s*(\d+|textual)\s*:\s*(ran|skipped:\s*.*)$")

#: `## Repair units` header. A table naming, per unit, the findings it groups
#: and its own changed-line forecast -- distinct from grouping by move or by
#: adjudication.
REPAIR_UNITS_HEADER = "| Unit | Findings | Changed lines |"


def move_roster(text):
    """The move-outcome roster a report must carry, derived from one moves
    table rather than listed by hand.

    Every numbered row becomes its own number, as a string; the one row this
    table carries with no leading digit becomes the literal `textual`. Raises
    rather than returning an empty roster when the table cannot be found or
    is not singular, because a roster silently empty would let every report
    pass by accident.
    """
    tables = markdown_table_rows(text, MOVES_TABLE_HEADER)
    if len(tables) != 1:
        raise Unprobeable(
            f"expected exactly one {MOVES_TABLE_HEADER!r} table to derive "
            f"the required move-outcome roster from; found {len(tables)}")
    roster = []
    for row in tables[0]:
        match = re.match(r"^(\d+)\b", row[0]) if row else None
        roster.append(match.group(1) if match else "textual")
    return roster


def resolve_moves_doctrine(override):
    """The path `check-report` reads the moves table from.

    Defaults to this skill's own `SKILL.md`, resolved relative to this
    script rather than to the caller's working directory, so the roster a
    report is held to is always this skill's own doctrine unless the caller
    names another file explicitly.
    """
    path = Path(override) if override else Path(__file__).resolve().parent.parent / "SKILL.md"
    if not path.is_file():
        raise Unprobeable(f"no moves-table doctrine file at {path}")
    return path


def move_outcome_rows(lines):
    """Every `- Move: <id>: ran|skipped: <reason>` row under `## Move
    outcomes`, as `{id: outcome}`. Reads only inside that section, so a
    finding's own `- Move: <n>` marker elsewhere in the report is never
    mistaken for an outcome row.
    """
    rows = {}
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Move outcomes":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = MOVE_OUTCOME_ROW.match(stripped)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


#: The header of the stages table this skill's own `SKILL.md` carries. Read
#: the same way `MOVES_TABLE_HEADER` is, so `## Stage outcomes`'s required
#: roster -- and which items are conditional on it -- comes from parsing
#: that table rather than from a list held here. Unlike the moves table
#: there is no `textual` escape valve: every row must carry a leading digit
#: and a `REPORT_SHAPE` key, or the table is `Unprobeable`.
STAGES_TABLE_HEADER = "| Stage | Models | Demands |"

#: `## Stage outcomes` rows: `- Stage: <id>: ran` or
#: `- Stage: <id>: skipped: <reason>`. Mirrors `MOVE_OUTCOME_ROW` exactly.
STAGE_OUTCOME_ROW = re.compile(
    r"^-\s*Stage:\s*(\d+)\s*:\s*(ran|skipped:\s*.*)$")

#: The one skip reason the `user-drive` stage may ever carry. An audit never
#: reports on a subject without driving it -- the zero-model path is never a
#: caller's shortcut to assert, so this literal is the only text
#: `run_check_report` accepts, and only when the measurement it names
#: (`## Undecidable` non-empty, every entry `no-closed-roster`) actually
#: holds. Any other stage-2 skip reason is `driver-required`.
DRIVE_STAGE_RESERVED_SKIP = "no reachable surface (stage 1)"

#: The one skip reason a post-drive stage (numbered after the `user-drive`
#: stage) may carry -- "available, the operator chose not to take it" --
#: legal only once the drive itself reached agreement. Any other stage's
#: `skipped:` text is untouched by this rule; it is unconditional and free.
POST_DRIVE_OFFERED_SKIP = "offered, declined"

#: A `## User drive` section's own `- Outcome:` line -- the one field W5
#: needs before W6 specifies the rest of that section's required content.
#: Read only inside the section, exactly like `frozen_section_fields`.
USER_DRIVE_OUTCOME_LINE = re.compile(r"^-\s*Outcome:\s*(.+?)\s*$")


def user_drive_outcome(lines):
    """The `## User drive` section's own `- Outcome:` value, or `None` if
    the section carries no such line.
    """
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## User drive":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = USER_DRIVE_OUTCOME_LINE.match(stripped)
        if match:
            return match.group(1)
    return None


#: `## User drive`'s own `- Digest:` line, held to `## Frozen`'s declared
#: digest exactly like every finding's own `- Digest:` already is: proof
#: the driven-audit narrative is about the same subject state as the rest
#: of the report.
USER_DRIVE_DIGEST_LINE = re.compile(r"^-\s*Digest:\s*(\S+)\s*$")

#: The heading under which `## User drive` states what the drive did *not*
#: prove -- training-data exposure, contact between drives, "genuinely
#: ignorant" versus "was not shown the file". A bare heading with nothing
#: under it is the same claim as an absent one: a drive that believes it
#: proved everything has misread what it did.
USER_DRIVE_DECLARED_HEADING = "### Declared, not proven"


def user_drive_digest(lines):
    """`## User drive`'s own `- Digest:` value, or `None` if the section
    carries no such line. Mirrors `frozen_section_fields`'s `- Digest:`
    field, reading only inside the section.
    """
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## User drive":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = USER_DRIVE_DIGEST_LINE.match(stripped)
        if match:
            return match.group(1)
    return None


def user_drive_declared_only_nonempty(lines):
    """Whether `## User drive`'s `### Declared, not proven` subsection
    carries at least one non-empty line beneath it, before the next
    heading of either level.
    """
    in_user_drive = False
    in_declared = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## User drive":
            in_user_drive = True
            continue
        if in_user_drive and stripped.startswith("## "):
            break
        if not in_user_drive:
            continue
        if stripped == USER_DRIVE_DECLARED_HEADING:
            in_declared = True
            continue
        if in_declared and stripped.startswith("#"):
            break
        if in_declared and stripped:
            return True
    return False


def stage_roster(text):
    """The `(stage id, REPORT_SHAPE key)` roster a report's stage table
    demands, derived from one stages table rather than listed by hand --
    mirrors `move_roster`, except every row must carry a leading digit and
    a known `REPORT_SHAPE` key: there is no `textual` escape valve here,
    and an unknown key would let a stages table quietly invent an
    enforcement the tool never checks.
    """
    tables = markdown_table_rows(text, STAGES_TABLE_HEADER)
    if len(tables) != 1:
        raise Unprobeable(
            f"expected exactly one {STAGES_TABLE_HEADER!r} table to derive "
            f"the required stage-outcome roster from; found {len(tables)}")
    roster = []
    for row in tables[0]:
        match = re.match(r"^(\d+)\b", row[0]) if row else None
        if not match:
            raise Unprobeable(
                f"a stages-table row carries no leading digit: {row!r}")
        if len(row) < 3:
            raise Unprobeable(
                f"a stages-table row is not three cells: {row!r}")
        key = row[2].strip("`")
        if key not in REPORT_SHAPE:
            raise Unprobeable(
                f"stage {match.group(1)} names {key!r} in its Demands "
                "cell, which is not a REPORT_SHAPE key")
        roster.append((match.group(1), key))
    return roster


def stage_model_total(text):
    """The stages table's `Models` column, summed -- the figure the
    doctrine's own "N model runs, total" sentence must name.

    Parsed the same way every other documented side in this module is,
    with `markdown_table_rows`, never a second hand-maintained figure held
    beside the table it describes. The lock over the sentence itself lives
    in `tests/test_skill_audit.py`, not here: `check-report` validates
    reports, and this sentence is the skill's own doctrine, the same home
    `stage_roster`'s own derivation test already occupies.
    """
    tables = markdown_table_rows(text, STAGES_TABLE_HEADER)
    if len(tables) != 1:
        raise Unprobeable(
            f"expected exactly one {STAGES_TABLE_HEADER!r} table to sum "
            f"Models from; found {len(tables)}")
    total = 0
    for row in tables[0]:
        if len(row) < 2:
            raise Unprobeable(f"a stages-table row is not three cells: {row!r}")
        try:
            total += int(row[1].strip())
        except ValueError:
            raise Unprobeable(
                f"a stages-table row's Models cell is not an integer: "
                f"{row!r}")
    return total


def resolve_stages_doctrine():
    """The path the stages table is always read from.

    Unlike `resolve_moves_doctrine`, there is no override flag: every
    fixture that exercises `--moves` to prove the move-outcome roster is
    derived rather than hardcoded carries no stages table of its own, and
    coupling stage derivation to that same override would make those
    fixtures `Unprobeable` for a reason unrelated to what they test. The
    stages table always comes from this skill's own `SKILL.md`.
    """
    return resolve_moves_doctrine(None)


def stage_outcome_rows(lines):
    """Every `- Stage: <id>: ran|skipped: <reason>` row under
    `## Stage outcomes`, as `{id: outcome}` -- mirrors `move_outcome_rows`
    exactly, reading only inside that section.
    """
    rows = {}
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Stage outcomes":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = STAGE_OUTCOME_ROW.match(stripped)
        if match:
            rows[match.group(1)] = match.group(2)
    return rows


#: `## Undecidable` entry field lines. Each entry starts with `- Kind:`;
#: `- Rung:` and, only when the rung is `probe`, `- Probe: <move>` follow
#: it, up to the next `- Kind:` or the end of the section.
UNDECIDABLE_KIND_LINE = re.compile(r"^-\s*Kind:\s*(.+?)\s*$")
UNDECIDABLE_RUNG_LINE = re.compile(r"^-\s*Rung:\s*(probe|readers)\s*$")
UNDECIDABLE_PROBE_LINE = re.compile(r"^-\s*Probe:\s*(\d+)\s*$")


def undecidable_entries(lines):
    """Every `## Undecidable` entry, each `{surfaceKind, rung, probe}` -- `probe`
    is `None` unless the entry's own rung is `probe`. Read only inside
    that section, exactly like `frozen_section_fields` and
    `move_outcome_rows`, so prose elsewhere in the report is never
    mistaken for a recorded entry.
    """
    entries = []
    in_section = False
    current = None
    for line in lines:
        stripped = line.strip()
        if stripped == "## Undecidable":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        kind_match = UNDECIDABLE_KIND_LINE.match(stripped)
        if kind_match:
            # Not `"kind"`: that key is reserved to `note()`'s reason and
            # `stalled()`'s verdict, and `EscalationPartitionTests` refuses
            # any other dict literal that carries it.
            current = {"surfaceKind": kind_match.group(1),
                      "rung": None, "probe": None}
            entries.append(current)
            continue
        if current is None:
            continue
        rung_match = UNDECIDABLE_RUNG_LINE.match(stripped)
        if rung_match:
            current["rung"] = rung_match.group(1)
            continue
        probe_match = UNDECIDABLE_PROBE_LINE.match(stripped)
        if probe_match:
            current["probe"] = probe_match.group(1)
    return entries


ADJUDICATIONS = ("doctrine wrong", "artefact wrong", "not adjudicable")

#: `- Found by:`'s closed set -- the independence axis, distinct from
#: `- Evidence:`'s obtained axis. Enforced with no default, exactly like
#: `- Evidence:`: a missing marker is never read as `one`, any more than a
#: missing evidence marker is read as confirmed.
FOUND_BY_VALUES = ("both", "one", "not-compared")

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


def repair_unit_rows(text):
    """The `## Repair units` table's rows, or `None` if no such table exists.

    Distinct from `## Changed-line forecast`, which sizes the fix by remedy,
    never by the hand-off-able group a downstream change would take whole.
    """
    tables = markdown_table_rows(text, REPAIR_UNITS_HEADER)
    if len(tables) != 1:
        return None
    return tables[0]


#: `## Frozen`'s own three fields: `- Digest:`, `- Subject:`, `- Exclude:`.
#: Self-describing, so re-deriving the digest needs no out-of-band argument
#: beyond `--subject` -- the exclude list travels with the report itself.
FROZEN_FIELD_ROW = re.compile(r"^-\s*(Digest|Subject|Exclude):\s*(.*)$")


def frozen_section_fields(lines):
    """The `- Digest:`, `- Subject:`, and `- Exclude:` lines under
    `## Frozen`, read only inside that section -- exactly like
    `move_outcome_rows` -- so a finding's own citation of a digest elsewhere
    in the report is never mistaken for the run's own frozen fields.
    """
    fields = {}
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Frozen":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = FROZEN_FIELD_ROW.match(stripped)
        if match:
            fields[match.group(1).lower()] = match.group(2).strip()
    return fields


#: A `- Position:` line under `## Disputed severity`. The section is a bare
#: heading -- an empty one demands nothing, because a surface nobody looked
#: at and a surface both drives agreed on must not read the same way (R6).
POSITION_LINE = re.compile(r"^-\s*Position:\s*.+$")


def disputed_severity_positions(lines):
    """`- Position:` lines under `## Disputed severity`, and whether the
    section carries any content at all beyond the bare heading.

    Read only inside the section, exactly like `frozen_section_fields` and
    `move_outcome_rows`, so a finding's own prose elsewhere in the report is
    never mistaken for a recorded position.
    """
    positions = []
    in_section = False
    has_content = False
    for line in lines:
        stripped = line.strip()
        if stripped == "## Disputed severity":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        if stripped:
            has_content = True
        if POSITION_LINE.match(stripped):
            positions.append(stripped)
    return has_content, positions


def parse_exclude_field(value):
    """`- Exclude:`'s rendered value, back into the tuple `frozen_digest`
    accepts. `(none)` -- the shape `## Frozen` renders when the list is
    empty -- becomes the empty tuple; anything else is a comma-separated
    list of `fnmatch` patterns.
    """
    if not value or value == "(none)":
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


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

    # Both doctrine tables are resolved up front: the moves table for
    # `## Move outcomes` below, and the stages table for which
    # `REPORT_SHAPE` items are conditional at all. Unprobeable propagates
    # from either: a missing or unparseable table is an inability to look,
    # not a pass.
    moves_path = resolve_moves_doctrine(getattr(args, "moves", None))
    required_moves = move_roster(moves_path.read_text(encoding="utf-8"))
    required_stages = stage_roster(
        resolve_stages_doctrine().read_text(encoding="utf-8"))

    # An item is conditional exactly when the stages table names it in a
    # `Demands` cell -- derived from `required_stages` rather than a second
    # hand-written set, so a stage added to the table without its own
    # `REPORT_SHAPE` key changes nothing here and a stage naming an
    # existing key is exempted from the unconditional sweep automatically.
    conditional_items = {key for _, key in required_stages}

    for item, marker in REPORT_SHAPE.items():
        if item in conditional_items:
            continue
        if marker.startswith("## ") and marker not in lines:
            fail(item, f"the report carries no {marker!r} section",
                 f"{path}:1")

    # `--subject` is optional: without it, `rederived` stays `false`, borrowing
    # `comparison: not-run`'s idiom rather than silently weakening the check,
    # and only a finding's own digest is held to `## Frozen`'s declared one.
    frozen = frozen_section_fields(lines)
    rederived = False
    if getattr(args, "subject", None) and frozen.get("digest"):
        actual = frozen_digest(
            Path(args.subject).resolve(),
            parse_exclude_field(frozen.get("exclude", "(none)")))
        rederived = True
        if actual != frozen["digest"]:
            fail("frozen",
                 f"the subject at {args.subject!r} re-derives to {actual}, "
                 f"which disagrees with '## Frozen''s declared digest "
                 f"{frozen['digest']}", f"{path}:1")

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

        found_by = re.search(r"^- Found by:\s*(.+?)\s*$", body, re.MULTILINE)
        if not found_by or found_by.group(1) not in FOUND_BY_VALUES:
            fail("found-by",
                 "every finding carries `- Found by: both | one | "
                 "not-compared`, and there is no default: a missing marker "
                 "is never read as `one`", where)

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

        digest = re.search(r"^- Digest:\s*(\S+)\s*$", body, re.MULTILINE)
        if digest and frozen.get("digest") and digest.group(1) != frozen["digest"]:
            fail("frozen",
                 f"finding {finding['label']}'s digest {digest.group(1)} "
                 f"disagrees with '## Frozen''s declared digest "
                 f"{frozen['digest']}", where)

        # The differential drive's asymmetry, enforced structurally: the
        # skill-less drive never ran the skill's own machinery, so a
        # finding attributed to it can never make a claim with the subject
        # itself as its target -- that pairing is a category error
        # regardless of whether the differential-drive stage is declared
        # ran or skipped in this report.
        drive = re.search(r"^- Drive:\s*(.+?)\s*$", body, re.MULTILINE)
        target = re.search(r"^- Target:\s*(.+?)\s*$", body, re.MULTILINE)
        if (drive and target and drive.group(1) == "skill-less"
                and target.group(1) == "subject"):
            fail("drives",
                 f"finding {finding['label']} attributes itself to the "
                 "skill-less drive while naming the subject as its "
                 "target; that drive never ran the skill's own machinery "
                 "and cannot make a claim with the subject as its target",
                 where)

    if findings and not confirmed:
        head = [line for line in lines[:6] if line.strip()]
        if not any(NO_CONFIRMED_DECLARATION in line for line in head):
            fail("evidence-marker",
                 "no finding is CONFIRMED by execution, so the report must say "
                 f"so in its first line: {NO_CONFIRMED_DECLARATION!r}",
                 f"{path}:1")

    # `## Disputed severity` is a bare heading: an empty section demands
    # nothing, because a surface nobody looked at and a surface both drives
    # agreed on must not read the same way. Non-empty means each dispute is
    # recorded as exactly two `- Position:` lines, each citing `file:line`,
    # verbatim -- no ranking, no ladder of any kind.
    has_disputes, dispute_positions = disputed_severity_positions(lines)
    if has_disputes:
        if not dispute_positions or len(dispute_positions) % 2 != 0:
            fail("disputed-severity",
                 "'## Disputed severity' records each dispute as exactly "
                 "two '- Position:' lines; found an unpaired count "
                 f"({len(dispute_positions)})", f"{path}:1")
        for position in dispute_positions:
            if not CITATION.search(position):
                fail("disputed-severity",
                     f"a '- Position:' line carries no `file:line` "
                     f"citation, verbatim: {position!r}", f"{path}:1")

    # Every move required by the moves table this run is pointed at -- this
    # skill's own SKILL.md by default -- needs its own row in `## Move
    # outcomes`, `ran` or `skipped` with a reason.
    outcomes = move_outcome_rows(lines)
    for move in required_moves:
        outcome = outcomes.get(move)
        if outcome is None:
            fail("move-outcomes",
                 f"move {move} has no row in '## Move outcomes'; every move "
                 "the moves table names must be `ran` or `skipped: <reason>`, "
                 "never absent", f"{path}:1")
        elif outcome.startswith("skipped:") and not outcome.split(":", 1)[1].strip():
            fail("move-outcomes",
                 f"move {move}'s row is `skipped` with an empty reason; a "
                 "move attempted zero times must say why", f"{path}:1")

    # Every stage the stages table names needs its own row in `## Stage
    # outcomes`, `ran` or `skipped` with a reason -- mirrors the move-
    # outcomes check exactly. Only a `ran` row then demands the artifact
    # its own `Demands` cell names: a `## ` marker means a required
    # section, a `- ` marker means the field's declared not-run value is
    # no longer accepted anywhere in the report.
    stage_outcomes = stage_outcome_rows(lines)
    for stage_id, key in required_stages:
        outcome = stage_outcomes.get(stage_id)
        if outcome is None:
            fail("stage-outcomes",
                 f"stage {stage_id} has no row in '## Stage outcomes'; "
                 "every stage the stages table names must be `ran` or "
                 "`skipped: <reason>`, never absent", f"{path}:1")
            continue
        if outcome.startswith("skipped:") and not outcome.split(":", 1)[1].strip():
            fail("stage-outcomes",
                 f"stage {stage_id}'s row is `skipped` with an empty "
                 "reason; a stage attempted zero times must say why",
                 f"{path}:1")
            continue
        if outcome != "ran":
            continue
        marker = REPORT_SHAPE[key]
        if marker.startswith("## "):
            if marker not in lines:
                fail(key,
                     f"stage {stage_id} is declared ran, so the report "
                     f"must carry {marker!r}", f"{path}:1")
            elif key == "user-drive":
                # The enforceable half: `## User drive`'s own `- Digest:`
                # must agree with `## Frozen`'s, exactly as every finding's
                # own `- Digest:` already must -- proof the driven-audit
                # narrative is about the same subject state as the rest of
                # the report.
                drive_digest = user_drive_digest(lines)
                if not drive_digest or (frozen.get("digest")
                                        and drive_digest != frozen["digest"]):
                    fail(key,
                         "'## User drive' carries no '- Digest:' agreeing "
                         f"with '## Frozen''s declared digest "
                         f"{frozen.get('digest')!r}", f"{path}:1")
                # The declared-only half: stated, never implied as proof.
                # A drive claiming to have proven everything has misread
                # what it did, so an empty column is refused the same as
                # an absent one.
                if not user_drive_declared_only_nonempty(lines):
                    fail(key,
                         "'## User drive' carries no non-empty "
                         f"{USER_DRIVE_DECLARED_HEADING!r} content; the "
                         "declared-only column must be stated, never "
                         "implied as proof", f"{path}:1")
        else:
            not_run_value = FIELD_NOT_RUN.get(key)
            if not_run_value:
                for finding in findings:
                    body = "\n".join(finding["text"])
                    field = re.search(r"^- Found by:\s*(.+?)\s*$", body,
                                      re.MULTILINE)
                    if field and field.group(1) == not_run_value:
                        fail(key,
                             f"stage {stage_id} is declared ran, so "
                             f"finding {finding['label']}'s "
                             f"'- Found by: {not_run_value}' is no longer "
                             "accepted",
                             f"{path}:{finding['line']} {finding['label']}")

    # The binding ruling: an audit never reports on a subject without
    # driving it. Derived structurally -- the `user-drive` stage id is
    # whichever row in `required_stages` names that key, never a hardcoded
    # `"2"` -- so a future renumbering moves this check along with the
    # table it reads, exactly like every other stage check above.
    drive_stage_id = next(
        (stage_id for stage_id, key in required_stages if key == "user-drive"),
        None)
    if drive_stage_id is not None:
        drive_outcome = stage_outcomes.get(drive_stage_id)
        if drive_outcome is not None and drive_outcome.startswith("skipped:"):
            drive_reason = drive_outcome.split(":", 1)[1].strip()
            if drive_reason != DRIVE_STAGE_RESERVED_SKIP:
                fail("driver-required",
                     f"stage {drive_stage_id}'s row reads "
                     f"'skipped: {drive_reason}'; an audit never reports "
                     "on a subject without driving it, and the only "
                     f"accepted skip reason is {DRIVE_STAGE_RESERVED_SKIP!r}",
                     f"{path}:1")
            else:
                undecidable_id = next(
                    (stage_id for stage_id, key in required_stages
                     if key == "undecidable"), None)
                stage1_ran = (undecidable_id is not None
                             and stage_outcomes.get(undecidable_id) == "ran")
                entries = undecidable_entries(lines)
                all_no_closed_roster = bool(entries) and all(
                    entry["surfaceKind"] == "no-closed-roster"
                    for entry in entries)
                if not (stage1_ran and all_no_closed_roster):
                    fail("driver-required",
                         f"stage {drive_stage_id}'s row reads "
                         f"'skipped: {DRIVE_STAGE_RESERVED_SKIP}', which is "
                         "only valid when stage 1 ran and '## Undecidable' "
                         "is non-empty with every entry's '- Kind:' reading "
                         "'no-closed-roster'; an empty '## Undecidable' is "
                         "not the same claim as one full of them",
                         f"{path}:1")

        # `skipped: offered, declined` is the one skip text legal only
        # after the drive itself reached agreement -- equivalence reached
        # is what makes the question worth asking. Scoped to stages
        # numbered *after* the drive stage, derived the same way, never a
        # hardcoded "3, 4, 5": stage 2's own row already cannot carry this
        # text at all, since it must equal `DRIVE_STAGE_RESERVED_SKIP`
        # exactly or fail as `driver-required` above.
        drive_agreed = (stage_outcomes.get(drive_stage_id) == "ran"
                       and user_drive_outcome(lines) == "agree")
        for stage_id, key in required_stages:
            if int(stage_id) <= int(drive_stage_id):
                continue
            outcome = stage_outcomes.get(stage_id)
            if not outcome or not outcome.startswith("skipped:"):
                continue
            if outcome.split(":", 1)[1].strip() != POST_DRIVE_OFFERED_SKIP:
                continue
            if not drive_agreed:
                fail(key,
                     f"stage {stage_id}'s row reads "
                     f"'skipped: {POST_DRIVE_OFFERED_SKIP}', which is legal "
                     f"only once stage {drive_stage_id} reads `ran` and "
                     "'## User drive''s own '- Outcome:' reads `agree`; "
                     "no question was asked here", f"{path}:1")

    # The one cross-section rule: an `## Undecidable` entry claiming
    # `- Rung: probe` must name a move whose own `## Move outcomes` row is
    # `ran`. Declaring a probe was the answer and then skipping the move it
    # names is refused, structurally.
    for entry in undecidable_entries(lines):
        # The partition is total over what this tool emits, held by
        # `EscalationPartitionTests`. A report is written by hand, so the same
        # closed set has to be enforced on the way in as well; otherwise a
        # surface can be declared undecidable under a reason that exists
        # nowhere, and `## Undecidable` stops meaning what the tool means.
        if entry["surfaceKind"] not in ESCALATION_BUCKETS["escalatable"]:
            fail("undecidable",
                 f"an '## Undecidable' entry names kind "
                 f"{entry['surfaceKind']!r}, which is not one this tool can "
                 "emit as escalatable; only a surface the tool could not "
                 "decide belongs here", f"{path}:1")
        if entry["rung"] != "probe":
            continue
        probe_move = entry["probe"]
        if not probe_move or outcomes.get(probe_move) != "ran":
            fail("undecidable",
                 "an '## Undecidable' entry claims rung `probe` naming "
                 f"move {probe_move!r}, but that move's '## Move outcomes' "
                 "row is not `ran`; a probe cannot be the answer for a "
                 "move that never ran", f"{path}:1")

    # `## Repair units`: every `### F<n>.` block belongs to exactly one unit,
    # and each unit's own changed-line forecast is an integer.
    finding_labels = {finding["label"] for finding in findings}
    units = repair_unit_rows(text)
    if units is not None:
        coverage = {}
        for row in units:
            unit = row[0] if row else ""
            findings_cell = row[1] if len(row) > 1 else ""
            forecast_cell = row[2] if len(row) > 2 else ""
            labels = [label.strip() for label in findings_cell.split(",")
                     if label.strip()]
            if not labels:
                fail("repair-units",
                     f"repair unit {unit!r} names no finding", f"{path}:1")
            for label in labels:
                if label not in finding_labels:
                    fail("repair-units",
                         f"repair unit {unit!r} names {label!r}, which "
                         "matches no finding in this report", f"{path}:1")
                    continue
                coverage[label] = coverage.get(label, 0) + 1
            if not re.fullmatch(r"-?\d+", forecast_cell.strip()):
                fail("repair-units",
                     f"repair unit {unit!r} carries a non-integer "
                     f"changed-line forecast: {forecast_cell!r}", f"{path}:1")
        for label in sorted(finding_labels):
            count = coverage.get(label, 0)
            if count != 1:
                fail("repair-units",
                     f"finding {label} is named by {count} repair units, not "
                     "exactly one", f"{path}:1")
    elif "## Repair units" in lines:
        fail("repair-units",
             f"the report carries '## Repair units' but no "
             f"{REPAIR_UNITS_HEADER!r} table beneath it", f"{path}:1")

    for index, line in enumerate(lines, start=1):
        for item, (pattern, detail) in FORBIDDEN_SUPPORT.items():
            if not pattern.search(line):
                continue
            if item == "single-harness-count" and all(
                    harness.search(line) for harness in BOTH_HARNESSES):
                continue
            fail(item, detail, f"{path}:{index}")

    emit({"rederived": rederived, "violations": sorted(
        violations, key=lambda v: (v["item"], v["where"]))})
    return 1 if violations else 0


DISPATCH = {
    "roster": run_roster,
    "check-report": run_check_report,
    "structure": run_structure,
    "walkthrough": run_walkthrough,
    "reading-diff": run_reading_diff,
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
