#!/usr/bin/env python3
"""proposal-implementation: deterministic workspace, migration and fidelity checks.

Standard library only, keyless, offline. Target code is never imported or
executed: provenance is read statically with `ast`.

Commands
    env     create/verify the target repository's own virtualenv
    plan    read-only migration plan (structure drift -> file moves)
    apply   execute an approved plan as a single, separate commit
    verify  layout compliance + revision fidelity of an existing implementation

Every command emits one JSON object on stdout. Exit code 0 means the command
ran; read `status` to learn whether the repository is compliant. Exit code 2
means a guard refused to run.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import venv
from pathlib import Path

# The forge root: <root>/.claude/skills/proposal-implementations/scripts/implementation_cli.py
FORGE_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = FORGE_ROOT / "implementations"

# The two files this module is allowed to path-import from the forge's
# `remote-execution` skill. `remote_execution_state()` reads `ledger.py`
# alone; `remote_execution_jobs_state()` (design #744 section 9) reads
# `remote_cli.py`, which itself loads `jobfolder.py`, `adapter.py`,
# `packer.py`, `credentials.py` and `shard_io.py` — every one of the eight
# modules the skill's own `*_module_names_no_service` guard family already
# holds to naming no service. `adapters/kaggle.py`, the ONE module that
# skill lets name a service, is never imported by `remote_cli.py` itself at
# module scope — it is reached only by the CLI's own lazy, per-command
# dispatch, which neither function below ever calls — so this widening
# still never puts a service name within this file's reach.
REMOTE_EXECUTION_LEDGER_SCRIPT = (
    FORGE_ROOT / ".claude" / "skills" / "remote-execution" / "scripts" / "ledger.py"
)
REMOTE_EXECUTION_CLI_SCRIPT = (
    FORGE_ROOT / ".claude" / "skills" / "remote-execution" / "scripts" / "remote_cli.py"
)

PRODUCT_DIRS = ("Notebooks", "Data", "Results", "Models")

#: Where a tracked `.py` may live. Anything else is a stray module.
#:
#: `tools/` is here for the same reason the benchmark is a sibling package, and
#: the argument has the same shape: a script that launches or operates a run has
#: nowhere else to go. It cannot live in the method's package — it implements no
#: equation, so it could only sit there by declaring a `__provenance__` it has no
#: right to, and a falsified stamp empties the one check that keeps the code tied
#: to the mathematics. It cannot live in the benchmark's package — that one trains
#: and measures, and operating a service is neither. And it cannot stay untracked,
#: because then the configuration of a run that costs hours lives on one disk and
#: no later session can reproduce how it was launched.
#:
#: A named place and not an amnesty: a script loose at the top of the repository
#: is still a stray. And nothing in `tools/` is ever asked for a provenance,
#: because the scan only recurses into `src/<Package>/` — which is what keeps a
#: launcher from being able to claim it implements something.
SOURCE_ROOTS = ("src/", "tests/", "tools/")

# A reorganization is "large" when the user can no longer review it, and what a user
# reviews is a list of decisions: this file goes there, this folder is renamed, this
# reference is rewritten. Eight of those you read and decide on; forty you approve
# without reading, and the authorization stops being one.
#
# The files a rename carries are deliberately NOT counted. Renaming a folder holding
# two hundred files is one decision, not two hundred: git moves the subtree atomically
# and one command puts it back. Counting them measures blast radius and calls it
# reviewability, which forces a separate session for a change the user reads in a
# single line. What the rename really costs is its reference rewrites — each one edits
# the inside of a file and can be wrong on its own — and those are counted.
LARGE_PLAN_DECISIONS = 15

IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ipynb_checkpoints",
    ".mypy_cache", ".ruff_cache", ".idea", ".vscode", "node_modules", ".codegraph",
}

ROOT_KEEP = {
    "README.md", "README.rst", "README.txt", "LICENSE", "LICENSE.md", "NOTICE",
    ".gitignore", ".gitattributes", ".python-version", "pyproject.toml",
    "setup.py", "setup.cfg", "tox.ini", "MANIFEST.in", "Makefile",
    "requirements.txt", "requirements-dev.txt", "environment.yml",
    "poetry.lock", "uv.lock", "CITATION.cff", "CHANGELOG.md",
    "AGENTS.md", "CLAUDE.md", ".gitkeep",
}

NOTEBOOK_EXT = {".ipynb"}
DATA_EXT = {".csv", ".tsv", ".parquet", ".npz", ".npy", ".arrow", ".feather", ".xlsx", ".mat"}
MODEL_EXT = {".pkl", ".pt", ".pth", ".joblib", ".onnx", ".ckpt", ".safetensors", ".h5", ".hdf5"}
RESULT_EXT = {".png", ".jpg", ".jpeg", ".svg", ".eps"}


class Refused(Exception):
    """A guard refused to run. Nothing was modified."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------
# git helpers
# --------------------------------------------------------------------------

def git(target: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=target, capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise Refused("GIT_FAILED", f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def tracked_files(target: Path) -> list[str]:
    out = git(target, "ls-files", "-z")
    return [p for p in out.split("\0") if p]


#: The first bytes of a Git LFS pointer. A pointer is a few hundred bytes of text
#: standing where a large file is declared to be; anything that opens it as data
#: gets a parse error that names the format it expected and not the reason.
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/"


#: The agreements of every gate live in the product folder, so they travel with
#: the work and get read by the next session rather than remembered by it. Which
#: file holds them is found by shape and never by name.
#:
#: This was a fixed `AGREEMENTS.md` for one commit, and that was wrong in the way
#: this whole file exists to catch: a repository already had its checklist under a
#: different name, 159 items settled by hand, and the check reported `absent` over
#: it and invented a second one beside it. Naming the file is deciding for the
#: repository, and then reading only the name you decided is asserting an absence
#: you never went looking for.
AGREEMENTS_GLOB = "*.md"

#: A checklist item. Anything else on the line is the item's text, verbatim.
AGREEMENT_LINE = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$")

#: A bullet: a marker followed by whitespace. `**bold**` is not one, which is why
#: this exists — a file that records a reverted agreement in prose was reported as
#: three malformed items, and the paragraph that explains a reversal is exactly the
#: kind of writing this file needs to allow.
BULLET_LINE = re.compile(r"^\s*[-*]\s+\S")


def agreements_state(target: Path, name: str) -> dict:
    """What was settled in conversation, and what of it has not reached the code.

    Agreements are what this flow loses. They are reached at a gate, they live in
    nobody's file, and by the time the code is being written the only record is a
    memory that re-decides freely — usually while implementing, when something
    turns out to be awkward and the substitution looks like tidiness rather than
    like a decision that was the user's to make.

    The rule to write them down existed in prose with nothing to hold it, which is
    the same shape as the defect it describes. This is the artefact. It is
    deliberately not a plan of work: a checklist derived from how the agent intends
    to build can be completed in full while an agreed thing never happens, and
    nothing anywhere will say so.

    Absence is a state and not a failure — a repository whose flow never reached a
    gate has nothing to record. It is reported either way, because a check that
    speaks only on failure teaches nobody what it was watching.

    **Found by shape, never by name.** Every markdown file at the top of the
    product folder is read, and one holding checklist items is a checklist. A
    fixed filename would decide for the repository and then report `absent` over
    whatever the repository actually called it — which is not a missing file, it
    is an absence nobody went looking for, dressed as a finding.
    """
    product = target / name
    files = sorted(p for p in product.glob(AGREEMENTS_GLOB) if p.is_file()) \
        if product.is_dir() else []

    open_items: list[str] = []
    settled = 0
    unparsed: list[str] = []
    holding: list[str] = []
    for path in files:
        items_here = 0
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.rstrip()
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = AGREEMENT_LINE.match(line)
            if not match:
            # A line that is neither blank, a heading, nor a checklist item. Left
            # silent it would be an agreement nobody counts, which is the failure
            # this file exists to prevent, one level down.
            #
                # A bullet is a marker followed by whitespace. Testing the first
                # character alone read every `**bold**` paragraph as a malformed
                # agreement, and a check that fires on ordinary prose is one
                # people stop reading — costlier than the case it was guarding.
                if BULLET_LINE.match(line):
                    unparsed.append(f"{path.name}: {line.strip()}")
                continue
            items_here += 1
            if match.group("mark") == " ":
                open_items.append(match.group("text"))
            else:
                settled += 1
        # A markdown file with no checklist items is a document, not a checklist.
        # Only what actually holds agreements is reported as holding them, and the
        # unparsed lines of a file that turned out to hold none go with it.
        if items_here:
            holding.append(str(path.relative_to(target)))
        else:
            unparsed = [u for u in unparsed if not u.startswith(f"{path.name}: ")]

    if not holding:
        return {"status": "absent", "holders": [], "searched": f"{name}/*.md",
                "open": [], "settled": 0, "unparsed": [],
                "note": "no markdown file in the product folder holds checklist "
                        "items; if a gate happened, its agreements were lost"}

    return {
        "status": "open" if open_items or unparsed else "settled",
        "holders": holding,
        "searched": f"{name}/*.md",
        "open": open_items,
        "settled": settled,
        "unparsed": unparsed,
    }


#: What a search has to say about itself before its answer means anything. Each
#: one is a way a search silently stops being an experiment and becomes a number
#: somebody picked, and each was walked into rather than foreseen.
SEARCH_DECLARATION = {
    "what": "which free scalar this chooses",
    "requiredScale": "the scale its answer needs, declared apart from the one it "
                     "is running at — with only one of them, a value found at "
                     "pilot scale and the configuration agree with each other and "
                     "everything reads as finished",
    "role": "the material role it reads. Choosing by outcome on the material the "
            "verdict rests on makes the verdict report a decision it already made",
    "tieRule": "how a tie is broken, written down. Inheriting it from `max` leaves "
               "the first element winning by accident, and where the objective is "
               "flat the accident is what chooses",
}


#: The declared shape of each `search` field, the same way `DISTRIBUTION_SHAPE`
#: declares `distribution`'s. `requiredScale` is a scale along named axes, so it
#: is a mapping and never a bare number: `30` cannot say whether it means epochs,
#: seeds or runs, and there is no axis to project a cost along. Without this
#: table the field was accepted on bare truthiness and the arithmetic downstream
#: iterated a scalar, which ended the process on a traceback instead of a result.
SEARCH_SHAPE = {
    "what": str,
    "requiredScale": dict,
    "role": str,
    "tieRule": str,
}


def _search_answered(search: dict, field: str) -> bool:
    """True when `field` carries a real answer of its declared shape.

    Same rule `_distribution_answered` applies: a container answers by
    existing, a scalar answers only non-blank, and neither is trusted until
    the value's own type is confirmed first.
    """
    if field not in search:
        return False
    value = search[field]
    expected = SEARCH_SHAPE[field]
    if not isinstance(value, expected):
        return False
    return value != "" if expected is str else True


def _search_malformed(search: dict, field: str) -> bool:
    """True when the key is present but its value is not the declared shape.

    A third thing, neither answered nor missing: reporting a scalar
    `requiredScale` as absent would tell whoever wrote it to declare a field
    they already declared, and reporting it as answered is what crashed.
    """
    return field in search and not isinstance(search[field], SEARCH_SHAPE[field])


def declared_required_scale(search: dict) -> dict:
    """The declared scale a cost may be projected towards, or nothing.

    Takes what `search_state` reported rather than the raw contract, so the
    shape has already been ruled on by the time the arithmetic sees it. A
    value of any other shape yields `{}`, which the forecast already knows how
    to answer — and it is reported as malformed beside the forecast, so the
    empty answer is never the only thing said about it.
    """
    declared = (search.get("declared") or {}).get("requiredScale")
    return dict(declared) if isinstance(declared, dict) else {}


#: A token in prose that looks like something in the code: dotted, underscored or
#: shouted. A bare lowercase word is an English word far more often than a symbol,
#: and reporting those would bury the ones that matter.
PROSE_SYMBOL = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
                          r"|[A-Z][A-Z0-9_]{2,}"
                          r"|[a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")

#: Endings that make a token a filename rather than a symbol. Prose names files
#: constantly, and dotted-and-underscored is exactly what a filename looks like.
FILE_SUFFIXES = (".py", ".md", ".json", ".jsonl", ".ipynb", ".txt", ".toml",
                 ".yaml", ".yml", ".csv", ".cfg", ".pdf", ".png", ".npz")


def prose_of(path: Path) -> list[tuple[int, str]]:
    """The prose of a file — docstrings and comments — and never its code.

    Reading the whole text would report a revision sitting in a `__provenance__`
    literal, which is code and is checked where it belongs. What this wants is the
    sentences: the places where a claim ages without anything failing.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".md":
        return list(enumerate(text.splitlines(), 1))
    if path.suffix == ".ipynb":
        try:
            cells = json.loads(text).get("cells") or []
        except json.JSONDecodeError:
            return []
        lines = []
        for cell in cells:
            body = "".join(cell.get("source") or [])
            if cell.get("cell_type") == "markdown":
                lines += list(enumerate(body.splitlines(), 1))
            else:
                lines += [(n, ln) for n, ln in enumerate(body.splitlines(), 1)
                          if ln.lstrip().startswith("#")]
        return lines

    found: list[tuple[int, str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                start = getattr(node, "lineno", 0)
                found += [(start + i, ln) for i, ln in enumerate(doc.splitlines())]
    found += [(n, ln) for n, ln in enumerate(text.splitlines(), 1)
              if ln.lstrip().startswith("#")]
    return found


def prose_state(target: Path, revision: str | None,
                source_root: Path | None = None) -> dict:
    """Claims in prose that stopped being true, where nothing else would notice.

    Every other check here reads a declaration or a file. These read sentences —
    the docstrings and comments that say what the code does — and a sentence ages
    without anything failing. A rename leaves the old symbol named in the
    paragraph beside it; a new revision leaves the old one named in a heading that
    still says which revision was verified.

    Two kinds, and only the two that can be settled without interpreting anyone:

    `staleRevisions` — a managed revision named in prose that is not the current
    one. The pattern is derived from the revision handed in, never hardcoded, so
    nothing here has to know a naming convention. A historical mention is
    legitimate and common — "the bound r16 adopted" is a fact about when — so this
    is reported and never drifts a status: telling the two apart is a reading, and
    a check that guessed would spend its credibility on the wrong ones.

    `unresolvedSymbols` — a token in prose shaped like a symbol that resolves to
    nothing under `src/`. This is what a rename leaves behind. A configuration key
    quoted the same way will show up too; that is a small, honest cost for
    catching the paragraph that still names a constant nobody kept.

    What neither can do is judge a claim about behaviour. "Nothing here is
    modified" ages exactly the same way and cannot be checked without parsing an
    assertion out of a sentence — in whichever language its author wrote it.
    """
    revisions: list[dict] = []
    unresolved: list[dict] = []
    if not target.is_dir():
        return {"staleRevisions": revisions, "unresolvedSymbols": unresolved}

    # Every name any module under the source root defines, plus the module paths
    # themselves. The root is a parameter because the same reading is worth having
    # over this skill's own directory: a rename here leaves the old symbol named
    # in `SKILL.md` and in the asset templates, and that is the identical failure
    # this catches in a target — found by hand twice before it was a check.
    known: set[str] = set()
    source = source_root if source_root is not None else target / "src"
    for file in sorted(source.rglob("*.py")) if source.is_dir() else []:
        if "__pycache__" in file.parts:
            continue
        parts = file.relative_to(source).with_suffix("").parts
        dotted = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        known.add(dotted)
        known.add(parts[-1])
        try:
            tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                known.add(node.name)
                known.add(f"{dotted}.{node.name}")
                known.add(f"{parts[-1]}.{node.name}")
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                known.add(node.id)
                known.add(f"{parts[-1]}.{node.id}")
            elif isinstance(node, ast.arg):
                known.add(node.arg)

    pattern = None
    if revision:
        stem = re.sub(r"\d+", r"\\d+", re.escape(Path(revision).name))
        pattern = re.compile(stem)

    for file in sorted(target.rglob("*")):
        # Hidden *inside* the target, not hidden anywhere in the absolute path. The
        # first version tested every part, so pointing this at a directory living
        # under a dotted one — `.claude/skills/…`, say — silently skipped every
        # file and reported nothing found. It read as a clean tree and was a check
        # that never ran.
        inside = file.relative_to(target)
        if (not file.is_file() or file.suffix not in (".py", ".md", ".ipynb")
                or any(p.startswith(".") for p in inside.parts)
                or "__pycache__" in inside.parts):
            continue
        relative = str(inside)
        for number, line in prose_of(file):
            if pattern:
                for named in pattern.findall(line):
                    if named != Path(revision).name:
                        revisions.append({"file": relative, "line": number,
                                          "named": named, "current": Path(revision).name})
            for token in PROSE_SYMBOL.findall(line):
                # A filename is not a symbol. `report.md` and `test_audit.py` are
                # dotted and underscored like one, and reporting them would bury
                # the renames this exists to catch under the repository's own
                # file list.
                if Path(token).suffix in FILE_SUFFIXES:
                    continue
                if token not in known and token.split(".")[0] not in known:
                    unresolved.append({"file": relative, "line": number,
                                       "symbol": token})
    return {"staleRevisions": revisions, "unresolvedSymbols": unresolved}


#: What a distributed run has to say about itself. Each is a way a split stops
#: being one experiment and becomes several wearing one table.
DISTRIBUTION_DECLARATION = {
    "axis": "what a shard is a subset of. It may be anything the repository "
            "divides by, and it may never be one the ladder compares along: "
            "every rung subtracts two arms, so splitting there puts that "
            "subtraction across a hardware boundary and credits a mechanism "
            "with what the machine did",
    "poolable": "the measurements that mean the same thing wherever they were "
                "taken, so they may be pooled across shards",
    "perEnvironment": "the measurements that describe the machine that produced "
                      "them, which are read one machine at a time — averaging "
                      "them across two yields a number that describes neither",
    "perRun": "the measurements that vary from one run to the next even holding "
             "everything else fixed, so reading them one machine at a time "
             "would claim a stability across runs that was never measured",
    "identicalAcrossShards": "what every shard must agree on. A difference there "
                             "is a different experiment rather than different "
                             "hardware, so the merge refuses instead of averaging",
}


#: The declared shape of each `distribution` field. A container answers by
#: existing, even empty; a scalar answers only non-blank. Neither branch is
#: trusted until the value's own type is confirmed first — that confirmation
#: is what keeps a malformed value from being read as either.
DISTRIBUTION_SHAPE = {
    "axis": str,
    "poolable": list,
    "perEnvironment": list,
    "perRun": list,
    "identicalAcrossShards": list,
}


def _distribution_answered(dist: dict, field: str) -> bool:
    """True when `field` carries a real answer of its declared shape.

    A container answers by existing, even empty — a replication run can
    measure that nothing belongs in it. A scalar answers only non-blank: an
    empty string carries no measurement, so it reads the same as never having
    been filled in.
    """
    if field not in dist:
        return False
    value = dist[field]
    expected = DISTRIBUTION_SHAPE[field]
    if not isinstance(value, expected):
        return False
    return value != "" if expected is str else True


def _distribution_malformed(dist: dict, field: str) -> bool:
    """True when the key is present but its value is not the declared shape.

    Checked before `_distribution_answered` is trusted anywhere: a string
    typo'd where a list belongs must never be smuggled in as either
    present-and-empty or plainly missing — it is its own, third thing.
    """
    return field in dist and not isinstance(dist[field], DISTRIBUTION_SHAPE[field])


def _distribution_list(dist: dict, field: str) -> list:
    """The declared list for `field`, or empty if it is missing or malformed.

    A malformed value must not be coerced into the partition —
    `list("accuracy")` would silently read eight letters as eight dimensions.
    """
    value = dist.get(field)
    return list(value) if isinstance(value, list) else []


def _projected_cost(reduction: dict, target_scale: dict) -> dict | None:
    """What the full run would cost, scaled from what the pilot measured.

    A projection from data, not an estimate. The pilot already ran and its
    duration is in the record; what the campaign costs is that, multiplied by how
    much larger the declared scale is along each axis the pilot ran short on.

    Reported and never gated. Whether a projected cost is too much is the user's
    call, and a threshold invented here would be this skill deciding how long
    somebody else's afternoon is worth.
    """
    ran = reduction.get("seconds") or reduction.get("wallSeconds")
    if not target_scale:
        return {"projectedSeconds": None,
                "reason": "the record declares no target scale, so there is "
                          "nothing to project towards"}
    if not ran:
        # Said rather than left empty. A silent `None` reads as "the cost is
        # fine" to anyone skimming, when it means the record never wrote down how
        # long it took — and the whole point of projecting from a measurement is
        # that somebody kept the measurement.
        return {"projectedSeconds": None,
                "reason": "the record carries no duration for the run that "
                          "produced it, so the only honest projection is none; "
                          "record the wall time beside the scale and this fills in"}
    factor = 1.0
    for key, wanted in target_scale.items():
        have = _scale_of(reduction.get(key))
        want = _scale_of(wanted)
        if have and want:
            factor *= want / have
    return {"measuredSeconds": ran, "factor": round(factor, 2),
            "projectedSeconds": round(ran * factor)}


def distribution_state(contract: dict, dimensions: dict,
                       merged: dict | None = None,
                       declaration_status: str = "declared") -> dict:
    """Whether a run split across machines says enough about itself to be one run.

    Three obligations, and each one's prohibition is what keeps this general.

    **The axis may be anything except a comparison.** This refuses `arm` and asks
    nothing else of it. A repository divides by whatever its repetitions are made
    of, and this has no notion of what that is — requiring a particular one would
    make the check work for the repository it was written against and no other.
    What it does know is that the arms are compared, because the declaration
    names them, and a split along a comparison is the one that cannot be undone
    by any amount of care afterwards.

    **The partition must be exhaustive and disjoint.** Every declared dimension
    belongs to exactly one of three: pooled, read one machine at a time, or read
    one run at a time. In none of them, and it is silently dropped — a column
    nobody notices is gone. In more than one, and there are two answers to one
    question. Which dimension is which is the repository's to say; this never
    learns what any of them measures, and the names in a finding are echoed
    from the declaration rather than written here.

    **A field's presence and its shape are checked before its truth.** A key
    that is absent is missing; a key present with a value of the wrong shape is
    `malformed` — a third thing, never smuggled in as either missing or
    answered. Among fields of the right shape, a container answers by existing,
    even empty; a scalar answers only non-blank.

    **Shards agree on what they said had to agree.** Where a merge record exists,
    a disagreement is reported and the merge is refused, never averaged.

    Absence is `none`. Most repositories run on one machine and have nothing to
    declare, and demanding a declaration from them would be inventing a problem.

    **`declaration_status` distinguishes silence from absence** — see
    `search_state`'s note on the same parameter; both readers face the same
    collapse in `resolve_benchmark_declaration`'s `{}` and need the same escape
    from it.
    """
    dist = contract.get("distribution")
    if not dist:
        if declaration_status in ("absent", "undeclared"):
            return {"status": declaration_status, "declared": {}, "missing": [],
                    "malformed": [], "axisIsAComparison": False,
                    "unpartitioned": [], "inBothHalves": [], "notADimension": [],
                    "shardsDisagree": [],
                    "note": "no benchmark declaration to read a distribution "
                            "from yet"}
        return {"status": "none", "declared": {}, "missing": [], "malformed": [],
                "axisIsAComparison": False, "unpartitioned": [],
                "inBothHalves": [], "notADimension": [], "shardsDisagree": [],
                "note": "no distribution declared; a run on one machine has "
                        "nothing to split and nothing to say about splitting it"}

    missing = [{"field": field, "reason": reason}
               for field, reason in DISTRIBUTION_DECLARATION.items()
               if not _distribution_answered(dist, field)
               and not _distribution_malformed(dist, field)]

    malformed = [{"field": field, "expected": DISTRIBUTION_SHAPE[field].__name__,
                 "found": type(dist[field]).__name__}
                for field in DISTRIBUTION_DECLARATION
                if _distribution_malformed(dist, field)]

    # The only axis this refuses, and it refuses it by name because the name is
    # its own: `arms` is part of the declaration schema, so what the ladder
    # compares along is something this can know without learning a vocabulary.
    axis_is_comparison = dist.get("axis") == "arm"

    poolable = _distribution_list(dist, "poolable")
    per_environment = _distribution_list(dist, "perEnvironment")
    per_run = _distribution_list(dist, "perRun")
    groups = (set(poolable), set(per_environment), set(per_run))
    declared = groups[0] | groups[1] | groups[2]
    unpartitioned = sorted(d for d in dimensions if d not in declared)
    in_both = sorted(set.union(
        groups[0] & groups[1], groups[0] & groups[2], groups[1] & groups[2]))
    not_a_dimension = sorted(d for d in declared if d not in dimensions)

    disagree = sorted(row.get("field") for row in (merged or {}).get("disagreements") or [])

    clean = (not missing and not malformed and not axis_is_comparison
             and not unpartitioned and not in_both and not not_a_dimension
             and not disagree)
    return {
        "status": "ok" if clean else "incomplete",
        "declared": dict(dist),
        "missing": missing,
        "malformed": malformed,
        "axisIsAComparison": axis_is_comparison,
        "unpartitioned": unpartitioned,
        "inBothHalves": in_both,
        "notADimension": not_a_dimension,
        "shardsDisagree": disagree,
        "shardsArrived": list((merged or {}).get("shardsArrived") or []),
    }


def search_state(contract: dict, declared_records: list,
                 product: Path | None = None,
                 declaration_status: str = "declared") -> dict:
    """Whether a declared search says enough about itself to be an experiment.

    A search is an experiment and gets declared as one. Three things it needs are
    invisible until somebody walks into them: a scale of its own, a material role
    of its own, and a tie rule that was written rather than inherited. Nothing
    here knows what is being searched — the declaration does — and no tool is
    named, because which search a problem wants is the problem's business.

    Absence is `none` and not a failure: most repositories search nothing. What
    makes the declaration bite is `undeclaredRecords` — a search leaves an
    artefact where the records live, so it has to be named there, and naming it is
    the moment somebody has to say what the thing is.

    **And the declared record is checked against the disk, not against the other
    declaration.** Comparing the two declarations verifies that somebody wrote the
    same string twice; it says nothing about where the search actually writes. A
    path with a directory doubled in it satisfied both declarations perfectly and
    put the record one level below where anyone would look for it — observed, and
    only after the search had already run there. `recordFound` is the answer to
    the filesystem's question, and it is reported whatever it says.

    The limit, stated rather than papered over: this cannot check that the role is
    disjoint from the verdict's, because it does not know the material. It can
    only require that the role be named, which is what puts the question in front
    of whoever writes it.

    **`declaration_status` distinguishes silence from absence.** `contract` alone
    cannot: `resolve_benchmark_declaration` returns `{}` for both `"absent"` (no
    `src/<Package>_Benchmark/` at all) and `"undeclared"` (a directory with
    nothing readable in it, or a scaffold every block of which is still blank),
    and a caller that only hands over the empty dict has already thrown that
    distinction away. The default, `"declared"`, is for callers that already know
    a real declaration was found and are asking only whether *this* target names a
    search — the ordinary case, and every direct unit test of this function.
    """
    search = contract.get("search")
    if not search:
        if declaration_status in ("absent", "undeclared"):
            return {"status": declaration_status, "declared": {}, "missing": [],
                    "malformed": [],
                    "recordNotDeclared": None, "recordFound": None,
                    "strayRecords": [],
                    "note": "no benchmark declaration to read a search from yet"}
        return {"status": "none", "declared": {}, "missing": [], "malformed": [],
                "recordNotDeclared": None, "recordFound": None, "strayRecords": [],
                "note": "no search declared; `undeclaredRecords` is what would "
                        "surface one that left an artefact"}

    missing = [{"field": field, "reason": reason}
               for field, reason in SEARCH_DECLARATION.items()
               if not _search_answered(search, field)
               and not _search_malformed(search, field)]

    # A value of the wrong shape is reported as itself. Folding it into
    # `missing` would ask for a field that is already there, and folding it
    # into the answered set is what let a scalar reach the arithmetic.
    malformed = [{"field": field,
                  "expected": SEARCH_SHAPE[field].__name__,
                  "found": type(search[field]).__name__}
                 for field in SEARCH_DECLARATION
                 if _search_malformed(search, field)]

    # The join between the two declarations: a search that writes a record and
    # never names it there is a second experiment arriving unaccounted for, which
    # is the whole reason `records` exists.
    record = search.get("record")
    covered = record is None or any(
        record == entry or record.startswith(entry.rstrip("/") + "/")
        for entry in declared_records)

    # The join against reality. `None` means there was nothing to check: no record
    # declared, or no product folder handed in. False means the search declares a
    # record and nothing is there — which is either a search that has not run or a
    # search writing somewhere else, and `strayRecords` tells the two apart by
    # looking for that filename anywhere under the product.
    found = None
    stray: list[str] = []
    if record and product is not None and product.is_dir():
        expected = product / record
        found = expected.is_file()
        if not found:
            stray = [str(p.relative_to(product))
                     for p in sorted(product.rglob(Path(record).name))
                     if p.is_file()]

    return {
        "status": ("ok" if not missing and not malformed and covered
                   and found is not False else "incomplete"),
        "declared": dict(search),
        "recordFound": found,
        "strayRecords": stray,
        "missing": missing,
        "malformed": malformed,
        "recordNotDeclared": None if covered else record,
    }


def search_cost_forecast(reduction: dict, required_scale: dict) -> dict | None:
    """What the declared search would cost, projected from what was actually measured.

    `requiredScale` is a search's own declaration of how large its run has to be,
    kept apart from the scale a pilot happens to be running at for exactly one
    reason: they are not the same number, and reading only one of them lets it
    stand in for both. `_projected_cost` already knows how to scale a measured
    duration by a declared target — the piece missing was pointing it at this
    declaration instead of the benchmark's, so this does exactly that and adds
    nothing to the arithmetic.

    Reported, never gated, for the reason `_projected_cost` already gives:
    whether the projected cost is worth paying is the user's call.
    """
    if not required_scale:
        return {"projectedSeconds": None,
                "reason": "the search declares no required scale, so there is "
                          "nothing to project towards"}
    forecast = dict(_projected_cost(reduction, required_scale) or {})
    # The gap that makes this worth computing at all: a search whose declared
    # scale sits above what actually produced the numbers on hand is a search
    # about to run under a configuration nobody has measured anything at, and
    # arithmetic alone will not say so unless it is asked to name the gap.
    above = {
        key: {"declared": _scale_of(wanted), "measuredAt": _scale_of(reduction.get(key))}
        for key, wanted in required_scale.items()
        if _scale_of(wanted) is not None
        and _scale_of(reduction.get(key)) is not None
        and _scale_of(wanted) > _scale_of(reduction.get(key))
    }
    if above:
        forecast["aboveMeasuredScale"] = above
    return forecast


def records_state(target: Path, name: str, contract: dict) -> tuple[list, list]:
    """What the run left where its records live, against what the contract names.

    Every other check here can only fire on something somebody wrote down, which
    means the repository most likely to be running an experiment nobody accounted
    for is exactly the one where they all stay quiet. This is the same net
    `undeclaredDrawings` casts over figures, cast over what a run writes: a whole
    second experiment — its own scale, its own material role, its output feeding
    every later run — arrives as a file in `Results/` and nothing asks about it.

    Format-agnostic on purpose. Filtering to `.json` would hand a silent pass to
    every repository that records in `.csv`, `.parquet` or `.npz`, and silent is
    the failure this exists to prevent. A repository that archives figures here
    declares the directory once, and that declaration shows in the echo — opting
    out of file-by-file accounting is then a visible decision rather than a gap.

    Scoped to `Results/` and not to the whole product, because `Models/` holds one
    artefact per checkpoint by the layout's own design: reporting sixty manifests
    as undeclared would be a finding nobody reads, in any repository.

    It says a file is unaccounted for. It cannot say the file is a second
    experiment — what it does is force the question, which is the point at which
    somebody has to write down what the thing is.
    """
    declared = list(contract.get("records") or [])
    product = target / name
    results = product / "Results"
    if not results.is_dir():
        return declared, []

    covered = [(product / entry).resolve() for entry in declared]
    undeclared = []
    for path in sorted(results.rglob("*")):
        if not path.is_file() or any(part.startswith(".") for part in path.parts):
            continue
        resolved = path.resolve()
        if any(resolved == c or c in resolved.parents for c in covered):
            continue
        undeclared.append(str(path.relative_to(product)))
    return declared, undeclared


def prior_work_state(target: Path, package: str) -> dict:
    """Which packages of prior work changed, and whether the change reaches the run.

    "The baseline is used as it is" is one of the strongest rules here and nothing
    verified it. Prior work sits under `src/` beside the method and its benchmark,
    and every check walked past it: not in the structure, not in the provenance, not
    in the stamp. It could be edited in any session and the next one would open a
    repository that says nothing happened.

    Two questions, and reporting only the first is what makes a check get ignored.
    *Did it change* is a fact and belongs in the report whatever the answer. *Does it
    reach the run* is what decides whether anyone has to act: the benchmark imports
    from prior work — that is what makes it a comparison — so a change to a module an
    arm imports moves what that arm computes, while a change to a training loop the
    benchmark never calls moves nothing here and may still matter to prior work's own
    notebooks.

    **Everything about what is there comes from the disk.** *Does this module exist,
    and does an arm import it* are the filesystem's questions, and answering them
    with the index makes a file that is ignored-but-used disappear: Git says nothing
    about an ignored path, so a prior-work module that runs on every call would be
    reported as absent and the whole check would come back clean. That is the same
    confusion as reading "not added yet" and "deliberately excluded" off one list.

    Git answers exactly one question, the one only it can: *is this in the record,
    and does it differ from it*. Its silence is never read as "nothing here" —
    `recordStatus` says whether it could answer at all, so an unavailable record
    cannot pass for a clean one.

    Uncommitted only, and deliberately. Prior work that a repository legitimately
    owns and evolves would leave a committed diff for good, and a check that is red
    for good is a check nobody reads. What this catches is the edit sitting in the
    tree right now, before it enters the history — which is where the flow can still
    say "that belongs in a session of its own" and be heard.
    """
    source = target / "src"
    empty = {"status": "none", "packages": [], "modules": [], "imported": [],
             "untrackedImported": [], "modified": [], "reaching": [],
             "recordStatus": "not-asked"}
    if not source.is_dir():
        return empty

    ours = {package, f"{package}_Benchmark"}
    prior = sorted(d.name for d in source.iterdir()
                   if d.is_dir() and d.name not in ours and not d.name.startswith("."))
    if not prior:
        return empty

    # From the disk. Every prior-work module that is present, whatever the ignore
    # rules say about it.
    modules = sorted(
        str(f.relative_to(target))
        for name in prior
        for f in (source / name).rglob("*.py")
        if "__pycache__" not in f.parts
    )

    # What the method and its benchmark import from prior work, by top-level module.
    imported: set[str] = set()
    for name in ours:
        root = source / name
        if not root.is_dir():
            continue
        for file in sorted(root.rglob("*.py")):
            if "__pycache__" in file.parts:
                continue
            try:
                tree = ast.parse(file.read_text(encoding="utf-8"))
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
                elif isinstance(node, ast.Import):
                    imported.update(a.name for a in node.names)

    def reached(relative: str) -> bool:
        """True when a module on disk is one the method or its benchmark imports."""
        parts = Path(relative).relative_to("src").with_suffix("").parts
        dotted = ".".join(parts)
        package_form = ".".join(parts[:-1]) if parts[-1] == "__init__" else dotted
        return any(m == dotted or m == package_form or m.startswith(package_form + ".")
                   for m in imported)

    # Also from the disk: which of those present modules an arm actually reaches.
    # This is a standing fact about the tree, not a consequence of anything having
    # changed, so it is computed over every module rather than over a diff.
    reaches = [m for m in modules if reached(m)]

    # The one question only the record can answer. Asked last, and allowed to fail.
    try:
        porcelain = git(target, "status", "--porcelain", "--", "src", check=False)
        tracked = set(tracked_files(target))
        record = "read"
    except Refused:
        porcelain, tracked, record = "", set(), "unavailable"

    modified = sorted({
        line[3:].strip().strip('"')
        for line in porcelain.splitlines()
        if line[3:].strip().strip('"').startswith(tuple(f"src/{p}/" for p in prior))
    }) if record == "read" else []

    # Present, imported by an arm, and outside the record. Ignored or merely never
    # added — the difference is the ignore rules' business and not this check's.
    # What matters is that an arm computes with something nobody else receives, so
    # the comparison cannot be reproduced from the record alone.
    untracked_imported = ([m for m in reaches if m not in tracked]
                          if record == "read" else [])

    reaching = [p for p in modified if reached(p)]
    if record == "unavailable":
        status = "unknown"
    elif reaching or untracked_imported:
        status = "reaching"
    elif modified:
        status = "modified"
    else:
        status = "clean"

    notes = ["Prior work is used as it is; correcting it belongs to a session of its own."]
    if reaching:
        notes.append("`reaching` names changed modules the method or its benchmark "
                     "imports, so those arms no longer compute what the record holds.")
    if untracked_imported:
        notes.append("`untrackedImported` names modules an arm computes with that are "
                     "not in the record: present on this disk and nowhere else, so "
                     "nobody can reproduce the comparison from what was committed.")
    if record == "unavailable":
        notes.append("The record could not be read, so nothing here says whether prior "
                     "work changed — `unknown` is that absence, never a clean answer.")

    return {
        "status": status,
        "packages": prior,
        "modules": modules,
        "imported": reaches,
        "untrackedImported": untracked_imported,
        "modified": modified,
        "reaching": reaching,
        "recordStatus": record,
        "note": " ".join(notes),
    }


def lfs_state(target: Path) -> dict:
    """Which files are placeholders, and what fetching them would cost.

    Cloning with the smudge filter skipped is already the rule — pointers are enough
    to reorganize a repository, and materializing gigabytes to move them around burns
    a quota that does not come back. What was missing is saying so. A four-kilobyte
    text file sitting where a model checkpoint is expected fails at load time with an
    error about the file format, and the reason is nowhere near the symptom.

    Nothing here fetches anything. The quota is the user's, spending it is their
    decision, and the command that would do it is reported rather than run.
    """
    attributes = target / ".gitattributes"
    if not attributes.exists():
        return {"status": "none", "patterns": []}

    patterns = [line.split()[0] for line in attributes.read_text(
        encoding="utf-8", errors="replace").splitlines()
        if "filter=lfs" in line and line.split()]
    if not patterns:
        return {"status": "none", "patterns": []}

    pointers, materialized = [], 0
    for path in target.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = str(path.relative_to(target))
        if not any(fnmatch.fnmatch(relative, p) or fnmatch.fnmatch(path.name, p)
                   for p in patterns):
            continue
        try:
            head = path.open("rb").read(256)
        except OSError:
            continue
        if head.startswith(LFS_POINTER_PREFIX):
            # The pointer states the real file's size. Reading it is what turns
            # "some files are missing" into a number the user can weigh.
            declared = 0
            for line in head.decode("utf-8", "replace").splitlines():
                if line.startswith("size "):
                    declared = int(line.split()[1]) if line.split()[1].isdigit() else 0
            pointers.append({"path": relative, "bytes": declared})
        else:
            materialized += 1

    total = sum(p["bytes"] for p in pointers)
    return {
        "status": "pointers" if pointers else "materialized",
        "patterns": patterns,
        "pointerCount": len(pointers),
        "materializedCount": materialized,
        "bytesToFetch": total,
        "humanBytesToFetch": f"{total / 1024**3:.2f} GiB" if total else "0",
        "pointers": sorted(pointers, key=lambda p: -p["bytes"])[:20],
        "truncated": max(0, len(pointers) - 20),
        # Reported, never run.
        "fetchCommand": "git lfs pull --include=" + ",".join(f'"{p}"' for p in patterns),
        "note": ("These files are placeholders of a few hundred bytes. Anything that "
                 "opens one as data fails with an error about its format rather than "
                 "about its absence, so treat them as missing material: the flow reads "
                 "none of them."),
        # The tempting workaround does not exist, and believing it does is worse than
        # knowing the cost. GitHub counts every download against the repository
        # owner's bandwidth — the command below, the browser's download button, even a
        # source archive that happens to contain LFS objects. The free allowance is
        # 1 GiB a month. There is no route that avoids it.
        "quota": ("Every download counts against the repository owner's LFS bandwidth, "
                  "by any route: the command below, the web interface's download "
                  "button, or a source archive containing these objects. Clicking "
                  "download in a browser costs exactly the same as fetching them here."),
        # Where the material might come from instead — read from the repository's own
        # code, not guessed. Weights fetched from a drive, unpacked from an archive or
        # produced by training do not touch the quota at all.
        "insteadOfFetching": ("Before spending it, check what `probe` reports under "
                              "`acquisition`: material this repository downloads, "
                              "clones or unpacks by itself costs nothing, and anything "
                              "training produced can be produced again."),
    }


def present_files(target: Path) -> list[str]:
    """What the repository actually holds, minus what it deliberately ignores.

    The index is the wrong enumerator for an inspection. A file that exists, is not
    ignored and is doing real work stays invisible until somebody commits it — so a
    misplaced module is reported after it has entered the history rather than before,
    which is the opposite of useful.

    Two questions were being answered by one list, and they are different: *does this
    exist* is answered by the disk, and *is this part of the record* is answered by
    the ignore rules. Both are local; nothing here reaches a remote.
    """
    candidates = [
        path for path in sorted(target.rglob("*"))
        if path.is_file() and not any(part in IGNORED_DIRS or part == ".git"
                                      for part in path.relative_to(target).parts)
    ]
    if not candidates:
        return []
    relative = [str(path.relative_to(target)) for path in candidates]
    # One call rather than one per file; `check-ignore` reads the same rules git
    # itself does, including any nested .gitignore.
    proc = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"], cwd=target,
        input="\0".join(relative), capture_output=True, text=True,
    )
    ignored = {p for p in proc.stdout.split("\0") if p}
    return [p for p in relative if p not in ignored]


def require_clean_worktree(target: Path) -> None:
    if git(target, "status", "--porcelain").strip():
        raise Refused(
            "DIRTY_WORKTREE",
            "The target working tree has uncommitted or untracked changes. "
            "Commit or stash them first; this skill never mutates a dirty repository.",
        )


# --------------------------------------------------------------------------
# guards
# --------------------------------------------------------------------------

def resolve_target(raw: str) -> Path:
    target = Path(raw).expanduser().resolve()
    try:
        target.relative_to(WORKSPACE.resolve())
    except ValueError:
        raise Refused(
            "OUTSIDE_WORKSPACE",
            f"Target must live under {WORKSPACE}. Clone the repository there first — "
            "the forge's own environment is never a workspace for generated code.",
        )
    if not (target / ".git").exists():
        raise Refused("NOT_A_GIT_REPO", f"{target} is not a git repository.")
    return target


def require_non_forge_interpreter() -> None:
    prefix = Path(sys.prefix).resolve()
    try:
        prefix.relative_to((FORGE_ROOT / ".claude").resolve())
    except ValueError:
        return
    raise Refused(
        "FORGE_INTERPRETER",
        "This process is running inside one of the forge's own virtualenvs. "
        "Re-run with a system interpreter so the target venv never inherits it.",
    )


def validate_name(name: str) -> str:
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        raise Refused("INVALID_NAME", f"Name {name!r} must be alphanumeric (- and _ allowed).")
    return name


def package_name(name: str) -> str:
    """The importable form of the name.

    A hyphen is legal in a directory but not in a Python identifier, so
    `Example-Method/` pairs with `src/Example_Method/`. The correspondence the layout
    exists to make visible survives; `import Example-Method` would not.
    """
    return name.replace("-", "_")


# --------------------------------------------------------------------------
# layout model
# --------------------------------------------------------------------------

def expected_dirs(name: str, with_data: bool) -> list[str]:
    dirs = [f"{name}/{d}" for d in PRODUCT_DIRS if d != "Data" or with_data]
    dirs += [f"src/{package_name(name)}", "tests"]
    return dirs


def in_place(path: str, name: str) -> bool:
    """True when the file already sits somewhere the layout accepts."""
    prefixes = (f"{name}/", "src/", "tests/", "docs/", ".github/")
    return path.startswith(prefixes)


def detect_product_dir(target: Path, name: str, paths: list[str]) -> str | None:
    """Find an existing product folder that only has the wrong name.

    A repository that already groups Notebooks/Results/Models under one folder
    is structurally compliant — it is the *name* that breaks the
    `<Name>/` <-> `src/<Name>/` correspondence. Renaming that one folder
    preserves every subtree; reclassifying its files file-by-file would flatten
    them and collide. Only an unambiguous single candidate is proposed.
    """
    candidates = {
        Path(p).parts[0] for p in paths
        if len(Path(p).parts) > 2 and Path(p).parts[1] in PRODUCT_DIRS
    }
    candidates -= {name, package_name(name), "src", "tests", "docs", *IGNORED_DIRS}
    return candidates.pop() if len(candidates) == 1 else None


TEXT_EXT = {".py", ".ipynb", ".md", ".rst", ".txt", ".toml", ".cfg", ".ini",
            ".yaml", ".yml", ".json", ".sh"}

# `<folder>/<Category>` written inside source, notebooks or docs. Anchored so a
# longer path segment (`.../Images/Results`) does not match on its tail.
REFERENCE_RE = re.compile(
    r"(?<![\w.-])([A-Za-z][A-Za-z0-9_-]*)/(" + "|".join(PRODUCT_DIRS) + r")(?![A-Za-z0-9_])"
)

# A folder used as a single path segment: `root / "Images"`. This never contains
# a slash, so the pattern above cannot see it, yet it is the form that actually
# breaks at runtime after a rename.
PATH_JOIN_RE = re.compile(r"/\s*[\"']([A-Za-z][A-Za-z0-9_-]*)[\"']")

# The same thing chained onto a category: `root / "Alpha" / "Results"`. Requiring
# the category keeps optional dataset probes (`root / "data" / "SomeSet"`) out.
PATH_CHAIN_RE = re.compile(
    r"[\"']([A-Za-z][A-Za-z0-9_-]*)[\"']\s*/\s*[\"'](" + "|".join(PRODUCT_DIRS) + r")[\"']"
)


def text_files(target: Path, paths: list[str]) -> list[str]:
    return [p for p in paths if Path(p).suffix.lower() in TEXT_EXT]


def read_text(target: Path, rel: str) -> str | None:
    try:
        return (target / rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def prefix_mappings(renames: list[dict], moves: list[dict]) -> list[tuple[str, str]]:
    """Every `old prefix -> new prefix` a migration implies.

    A rename gives one directly. Moves give one too, and forgetting them breaks
    exactly as much: after `Alpha/Results/x.csv -> <Name>/Results/x.csv`, code
    addressing `Alpha/Results` points nowhere. The prefix is derived by
    stripping the longest common suffix, so a move that only nests a folder
    deeper yields `Results -> <Name>/Results`, not a bare rename.
    """
    mappings: dict[str, set[str]] = {}
    for rename in renames:
        mappings.setdefault(rename["from"], set()).add(rename["to"])

    for move in moves:
        source, dest = Path(move["from"]).parts, Path(move["to"]).parts
        common = 0
        while (common < min(len(source), len(dest))
               and source[-1 - common] == dest[-1 - common]):
            common += 1
        keep = max(1, len(source) - common)
        mappings.setdefault("/".join(source[:keep]), set()).add(
            "/".join(dest[:len(dest) - len(source) + keep])
        )

    # An ambiguous prefix (two destinations) is left alone: rewriting it would
    # have to guess, and a wrong rewrite is worse than a reported one.
    return sorted((old, next(iter(new))) for old, new in mappings.items() if len(new) == 1)


def reference_pattern(needle: str, kind: str, anchored: bool) -> re.Pattern:
    """Match `needle`, anchored to a path boundary only when nesting demands it.

    Two mappings behave differently. A pure rename (`Images -> <Name>`) is safe
    to replace anywhere: the new value cannot contain the old one, so a nested
    occurrence such as a URL `.../blob/main/Images/Notebooks/` is a genuine hit
    and must be rewritten. A nesting mapping (`Results -> <Name>/Results`) must
    be anchored, or `Images/Results/` becomes `Images/<Name>/Results/`.
    """
    if kind == "path prefix" and anchored:
        return re.compile(r"(?<![\w./-])" + re.escape(needle))
    return re.compile(re.escape(needle))


def is_nesting(old: str, new: str) -> bool:
    """True when the new prefix merely nests the old one deeper."""
    return new.endswith(f"/{old}")


def scan_reference_updates(target: Path, mappings: list[tuple[str, str]],
                           paths: list[str]) -> list[dict]:
    """Files naming an old path that the migration is about to invalidate."""
    updates: list[dict] = []
    for old, new in mappings:
        if old == new:
            continue
        patterns = [(f"{old}/", f"{new}/", "path prefix")]
        # Only a pure one-segment rename is safe to rewrite in quoted form;
        # substituting a multi-segment path into a quoted literal would match
        # unrelated strings.
        if "/" not in old and "/" not in new:
            patterns += [(f'"{old}"', f'"{new}"', "quoted path segment"),
                         (f"'{old}'", f"'{new}'", "quoted path segment")]
        for rel in text_files(target, paths):
            content = read_text(target, rel)
            if not content:
                continue
            for needle, replacement, kind in patterns:
                anchored = is_nesting(old, new)
                hits = len(reference_pattern(needle, kind, anchored).findall(content))
                if hits:
                    updates.append({
                        "file": rel,
                        "occurrences": hits,
                        "kind": kind,
                        "anchored": anchored,
                        "replace": needle,
                        "with": replacement,
                    })
    return updates


def scan_stale_references(target: Path, name: str, paths: list[str]) -> list[dict]:
    """Textual `<folder>/<Category>` paths under a parent that does not exist.

    Deliberately narrow. A quoted single segment (`root / "data"`) is NOT
    flagged: fallback probes for optional dataset roots are legitimately absent,
    so treating every missing directory as breakage buries the real finding.
    That form is still rewritten during a rename, where the exact old name is
    known and the user approves the list first.
    """
    def resolves(folder: str, category: str) -> bool:
        """An empty directory is not a destination: the content it named is gone.

        `git mv` leaves the old parents behind as empty shells, so existence
        alone would report a broken path as healthy.
        """
        directory = target / folder / category
        if not directory.is_dir():
            return False
        return any(entry.name != ".gitkeep" for entry in directory.iterdir())

    stale: list[dict] = []
    for rel in text_files(target, paths):
        content = read_text(target, rel)
        if not content:
            continue
        pairs = {(m.group(1), m.group(2)) for m in REFERENCE_RE.finditer(content)}
        pairs |= {(m.group(1), m.group(2)) for m in PATH_CHAIN_RE.finditer(content)}
        broken = sorted(f"{folder}/{category}" for folder, category in pairs
                        if folder != name and not resolves(folder, category))
        if broken:
            stale.append({"file": rel, "references": broken})
    return stale


def classify(path: str, name: str, product_dir: str | None = None) -> tuple[str | None, str]:
    """Return (destination, reason). destination None means keep in place."""
    parts = Path(path).parts
    if parts[0] in IGNORED_DIRS:
        return None, "ignored"
    if product_dir and parts[0] == product_dir:
        return None, "carried by the product folder rename"
    if in_place(path, name):
        return None, "already inside an accepted root"

    # A file already inside a category folder keeps that category and its
    # subtree, whatever its extension says. A .csv under Results/ is a result.
    for index, part in enumerate(parts[:-1]):
        if part in PRODUCT_DIRS:
            tail = "/".join(parts[index + 1:])
            return f"{name}/{part}/{tail}", f"already organized under {part}/"

    basename = Path(path).name
    ext = Path(path).suffix.lower()
    depth = len(parts) - 1

    if depth == 0 and basename in ROOT_KEEP:
        return None, "repository metadata stays at the root"
    if ext in NOTEBOOK_EXT:
        return f"{name}/Notebooks/{basename}", "notebook"
    if ext in DATA_EXT:
        return f"{name}/Data/{basename}", "dataset"
    if ext in MODEL_EXT:
        return f"{name}/Models/{basename}", "trained artifact"
    if ext in RESULT_EXT:
        return f"{name}/Results/{basename}", "result artifact"
    if ext == ".py":
        package = "legacy" if depth == 0 else parts[0]
        return f"src/{package}/{path if depth == 0 else str(Path(*parts[1:]))}", (
            "pre-existing implementation moves into its own package under src/"
        )
    if ext in {".md", ".rst", ".txt"}:
        return None, "documentation stays where it is"
    return "", "unclassified"


def dir_exists_after(target: Path, rel: str, renames: list[dict], name: str) -> bool:
    """Does `rel` exist, or will it once the renames run?"""
    if (target / rel).is_dir():
        return True
    for rename in renames:
        if rel == rename["to"] or rel.startswith(f"{rename['to']}/"):
            source = rename["from"] + rel[len(rename["to"]):]
            if (target / source).is_dir():
                return True
    return False


PROBE_NOTEBOOK = "probe.ipynb"
PROBE_RESULTS = "Probe_results.json"
BENCHMARK_MODULE = "benchmark.py"
BASELINE_SOURCE_EXT = {".py", ".ipynb", ".r", ".m", ".jl", ".cpp", ".cu"}

# Array backends, read statically. A module that computes with numpy cannot be
# trained: there is no autograd and nothing to put on a device, so a benchmark
# against a trained baseline has nothing to run. The conversion is therefore the
# first thing to settle once the implementation is faithful, not an optimization
# to consider later.
TENSOR_BACKENDS = {"torch": "torch", "jax": "jax", "tensorflow": "tensorflow"}


def imported_modules(path: Path) -> set[str]:
    """Top-level module names a file imports, without importing anything itself."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def method_imports(path: Path, package: str, stems: set[str]) -> set[str]:
    """Which modules OF THE METHOD this file imports, by stem.

    `imported_modules` answers at top-level granularity, and that is the wrong
    resolution here: every file of the benchmark imports the method's package, so
    at that resolution every harness looks like it calls everything. The question
    is which parts of it.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            parts = node.module.split(".")
            if parts[0] != package:
                continue
            if len(parts) > 1:
                found.add(parts[1])
            else:
                # `from <package> import <name>` names a submodule too, and only the
                # directory can say whether it does: the same statement is how a plain
                # symbol is imported.
                found.update(a.name for a in node.names if a.name in stems)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == package and len(parts) > 1:
                    found.add(parts[1])
    return found & stems


def benchmark_reach(target: Path, package: str, bench_package: str) -> set[str]:
    """Which modules of the method the benchmark actually calls.

    Transitively, and that is not a refinement but the difference between a useful
    finding and one that gets ignored: one module of the method is routinely reached
    through another that uses it, never named by the harness at all, and a
    direct-import check would report it missing on every faithful repository there is.
    """
    method, bench = target / "src" / package, target / "src" / bench_package
    if not method.is_dir() or not bench.is_dir():
        return set()
    paths = {f.stem: f for f in sorted(method.rglob("*.py")) if f.name != "__init__.py"}
    stems = set(paths)
    if not stems:
        return set()
    edges = {stem: method_imports(path, package, stems) for stem, path in paths.items()}

    frontier: set[str] = set()
    for file in sorted(bench.rglob("*.py")):
        frontier |= method_imports(file, package, stems)
    reached: set[str] = set()
    while frontier:
        stem = frontier.pop()
        if stem in reached:
            continue
        reached.add(stem)
        frontier |= edges.get(stem, set()) - reached
    return reached


def unreached_mathematics(modules: list[dict], declaration: dict,
                          reached: set[str]) -> list[dict]:
    """Modules carrying sections the arms declare, that the harness never calls.

    This is the join nothing else in the flow crosses. `verify` reads the method's
    provenance and the bench's declaration as two separate documents, and both can be
    impeccable while an arm reimplements the equation instead of calling it: the module
    still declares its sections, the arm still declares the same ones, and the two
    never meet. That is not hypothetical — it is how an arm ran a whole campaign
    computing a simplified form of a term it declared, with every check reporting clean.

    It stays silent about mathematics no arm claims. A method may legitimately carry
    more than a given comparison exercises, and a check that demanded every module be
    called would fire on that and teach the reader to skip it.
    """
    arms = declaration.get("arms") or {}
    claimants: dict[str, list[str]] = {}
    for arm, spec in arms.items():
        if not isinstance(spec, dict):
            continue
        for section in spec.get("sections", []) or []:
            claimants.setdefault(str(section), []).append(str(arm))

    unreached = []
    for module in modules:
        if Path(module["module"]).stem in reached:
            continue
        declared_by = sorted({arm for section in module.get("sections", [])
                              for arm in claimants.get(str(section), [])})
        if not declared_by:
            continue
        unreached.append({
            "module": module["module"],
            "sections": module.get("sections", []),
            # What the arm claims to exercise and does not, named at the resolution
            # the reader can act on: the equation, not the section it lives in.
            "equations": module.get("equations", []),
            "declaredBy": declared_by,
        })
    return unreached


def benchmark_unfaithfulness(target: Path, name: str) -> list[dict]:
    """The same crossing `verify` makes, for callers that do not enumerate modules."""
    package = package_name(name)
    bench_package = f"{package}_Benchmark"
    root = target / "src" / package
    resolved = resolve_benchmark_declaration(target, name)
    if not root.is_dir() or resolved["status"] != "declared":
        return []
    declaration = resolved["contract"]
    modules = []
    for file in sorted(root.rglob("*.py")):
        if file.name == "__init__.py":
            continue
        prov = read_provenance(file)
        if prov is None or "__error__" in prov:
            continue
        modules.append({"module": str(file.relative_to(target)),
                        "sections": prov.get("sections", []),
                        "equations": prov.get("equations", [])})
    return unreached_mathematics(
        modules, declaration, benchmark_reach(target, package, bench_package))


def backend_state(target: Path, name: str) -> dict:
    """Which array backend the implementation and its tests actually compute with.

    Reported per file, because a half-converted implementation is the dangerous
    state: the modules train and the tests still assert over numpy, so the suite
    passes while measuring something the trained model never touched.
    """
    package = target / "src" / package_name(name)
    tests = target / "tests"
    numpy_files: list[str] = []
    tensor_files: list[str] = []
    for root in (package, tests):
        if not root.is_dir():
            continue
        for file in sorted(root.rglob("*.py")):
            modules = imported_modules(file)
            rel = str(file.relative_to(target))
            if modules & set(TENSOR_BACKENDS):
                tensor_files.append(rel)
            elif "numpy" in modules:
                numpy_files.append(rel)
    if not numpy_files and not tensor_files:
        state = "unknown"
    elif numpy_files and tensor_files:
        state = "mixed"
    elif tensor_files:
        state = "tensor"
    else:
        state = "numpy"
    return {
        "state": state,
        "numpyFiles": numpy_files,
        "tensorFiles": tensor_files,
        # Only a tensor backend can be trained, so only that state can be benchmarked.
        "trainable": state == "tensor",
    }


def previous_implementations(target: Path, name: str) -> list[str]:
    """Packages under `src/` that are not ours.

    The layout rule keeps pre-existing code in its own package and never merges it
    into `src/<Package>/`, precisely so the work that was already here survives the
    reorganization intact. Whatever is left over is the baseline a probe compares
    against — it is found by reading the tree, not by remembering that it was there.
    """
    # Case-folded: on a case-insensitive filesystem `src/Method` and `src/METHOD` are one
    # directory, so an exact comparison would hand our own package back as somebody
    # else's baseline. On a case-sensitive one they are two, but a package differing
    # from ours only in case is a naming accident rather than prior work.
    ours = package_name(name).casefold()
    src = target / "src"
    if not src.is_dir():
        return []
    return sorted(
        entry.name for entry in src.iterdir()
        if entry.is_dir() and entry.name.casefold() != ours
        and entry.name not in IGNORED_DIRS
        # Any source at all: a baseline is somebody else's prior work and may be
        # notebooks, R or MATLAB. Requiring Python would make it invisible.
        and any(child.is_file() and child.suffix.lower() in BASELINE_SOURCE_EXT
                for child in entry.rglob("*"))
    )


def probe_state(target: Path, name: str, revision: str | None) -> dict:
    """Whether a probe already ran here, and whether it still describes this revision.

    The result file is the whole record. A summary naming an older revision is stale
    by inspection, so nothing has to be stored to know it: the artifact carries the
    reduction it was obtained under, and a number that cannot be read together with
    its reduction is a number that will be misquoted.
    """
    results = target / name / "Results" / PROBE_RESULTS
    if not results.exists():
        return {"status": "absent"}
    try:
        recorded = json.loads(results.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        return {"status": "unreadable", "detail": str(error)[:200]}
    against = recorded.get("revision")
    rows = recorded.get("comparison")
    if not isinstance(rows, (list, dict)):
        return {"status": "unreadable",
                "detail": "comparison is neither a list nor a mapping"}
    if not revision:
        # Without a revision to compare against, staleness cannot be established.
        # Reporting "stale" here would assert a state nobody checked.
        status = "unknown"
    else:
        status = "current" if against == revision else "stale"

    # Scale, not only revision. A record obtained below the scale the protocol
    # declares is neither absent nor done: it is a pilot, and calling it done is how
    # a point estimate gets quoted as a result. The reduction was always read and
    # returned here; nothing looked at it.
    reduction = recorded.get("reduction") or {}
    target_scale = recorded.get("targetScale") or {}
    below = {
        key: {"ran": _scale_of(reduction.get(key)), "declared": _scale_of(value)}
        for key, value in target_scale.items()
        if _scale_of(reduction.get(key)) is not None
        and _scale_of(value) is not None
        and _scale_of(reduction.get(key)) < _scale_of(value)
    }
    if status == "current" and below:
        status = "piloted"

    return {
        "status": status,
        "revision": against,
        "expectedRevision": revision,
        "reduction": reduction,
        "targetScale": target_scale or None,
        "belowTargetScale": below or None,
        # What the full run would cost, from what the pilot actually took rather
        # than from anybody's memory of it. Divided by the shards the repository
        # declares, when it declares any — a projection and never a threshold:
        # whether that cost is worth splitting is not a question this can answer,
        # and a number reported is what lets somebody else answer it.
        "projectedCost": _projected_cost(reduction, target_scale),
        "labels": sorted(rows) if isinstance(rows, dict) else
                  [row.get("dimension") for row in rows if isinstance(row, dict)],
    }


# Names that mark a string literal as naming a dataset or task, used to read the
# baseline's own vocabulary instead of matching against a list of datasets someone
# thought of in advance.
ENVIRONMENT_HINTS = ("dataset", "datasets", "data", "task", "tasks", "benchmark",
                     "benchmarks", "domain", "domains", "corpus")

# Function names that mean "this is where the data comes from". The wiring needs an
# entry point, not a dataset name: a task name says what was measured, a loader says
# how to measure it again.
DATA_ENTRY_HINTS = ("load", "loader", "dataset", "datasets", "split", "splits",
                    "fetch", "read_data", "get_data", "prepare")

# How prior work gets hold of what it trains on. Reading this is what separates "the
# material is not in the repository" — true and useless — from "here is what fetches
# it", which is the difference between an environment being unavailable and merely
# being absent until something runs.
ACQUISITION_PATTERNS = (
    (r"download\s*=\s*True", "downloads itself"),
    (r"\bgdown\b", "fetched with gdown"),
    (r"git\s+clone|\"clone\"", "cloned from a repository"),
    (r"\bwget\b|\bcurl\b", "fetched over the network"),
    (r"https?://[^\s\"']{6,}", "names a remote source"),
    (r"zipfile|tarfile|extractall", "unpacked from an archive"),
    # Any absolute path outside the repository: a hosted runtime, a cluster scratch,
    # a mounted share. Naming the platforms instead would only catch the two this was
    # written against.
    (r"[\"'](/(?!Users|home\b)[A-Za-z][\w./-]{4,})[\"']", "read from a path outside the repository"),
)

# The list above is fixed and therefore partial: a repository fetching through a cloud
# SDK, a data-versioning tool or a hosting client matches none of it. That is
# survivable only because an empty reading is reported as a miss rather than as an
# absence — see `foundNothingFor`.


def notebook_sources(path: Path) -> list[str]:
    """The code cells of a notebook, as plain text.

    Notebooks are where prior experiments were actually run, so they are read like any
    other source rather than counted as documentation. A cell may hold shell magics
    that no parser accepts, so callers treat this as text and parse what they can.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return []
    cells = document.get("cells")
    if not isinstance(cells, list):
        return []
    sources = []
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            body = cell.get("source")
            sources.append("".join(body) if isinstance(body, list) else str(body or ""))
    return sources


def acquisition_evidence(text: str, where: str) -> list[dict]:
    """What this text shows about how material is obtained."""
    found = []
    for pattern, meaning in ACQUISITION_PATTERNS:
        if re.search(pattern, text):
            found.append({"how": meaning, "seenIn": where})
    return found


def _module_aliases(tree: ast.Module) -> dict[str, str]:
    """Names in this file that refer to an imported *module*, not to an instance.

    This is the distinction that decides whether the reading is useful. An attribute
    of an imported `models` module names an architecture; the same attribute access on
    an instance names nothing — and matching on the holder alone cannot tell them
    apart, so it buries the real names under every method call in the file.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _names_a_dataset(text: str) -> bool:
    """Whether a string literal reads as the name of a dataset rather than a word.

    A hyphen or a second capital is what separates a task name from `classes`,
    `labels` and `Dataset`. Deliberately not a list of known datasets: the baseline
    names its own tasks, and may name ones nobody here has heard of.
    """
    return len(text) > 4 and ("-" in text or sum(c.isupper() for c in text) >= 2)


def baseline_environment(target: Path, baselines: list[str], name_of_ours: str = "") -> dict:
    """What the prior work already trains on: its backbones, its datasets, its weights.

    A comparison is only common if both sides meet in one environment, and the one that
    already has meaning is the baseline's — it is where its results were obtained.
    Reading it beats offering a list: a list is somebody's guess about the field, this
    is what the repository does.

    Everything is read statically. Nothing here knows which datasets exist in the
    world; it knows how code names them.
    """
    backbones: dict[str, str] = {}
    datasets: dict[str, str] = {}
    entry_points: list[dict] = []
    weights: list[str] = []
    notebooks: list[str] = []
    acquisition: list[dict] = []

    # Notebooks that are not the proposal's are where the prior experiments were
    # actually run. They name the data the published results came from, so they are
    # read alongside the package rather than treated as documentation.
    ours = f"{name_of_ours}/" if name_of_ours else None
    for notebook in sorted(target.rglob("*.ipynb")):
        rel = str(notebook.relative_to(target))
        if any(part.startswith(".") for part in notebook.parts):
            continue
        if ours and rel.startswith(ours):
            continue  # the proposal's own notebooks are not prior work
        notebooks.append(rel)
        # Read them, do not merely list them. A package can resolve a directory it
        # never creates; what creates it usually lives here, and a reading that stops
        # at the package concludes the material is unobtainable while the thing that
        # obtains it sits one file away.
        for cell in notebook_sources(notebook):
            acquisition.extend(acquisition_evidence(cell, rel))
            try:
                tree = ast.parse(cell)
            except SyntaxError:
                continue  # shell magics and fragments: read as text above, not here
            aliases = _module_aliases(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and isinstance(node.func.value, ast.Name):
                    origin = aliases.get(node.func.value.id, "")
                    if origin.endswith("models"):
                        backbones.setdefault(node.func.attr, rel)
                    elif origin.endswith("datasets"):
                        datasets.setdefault(node.func.attr, rel)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and any(hint in node.name.lower() for hint in DATA_ENTRY_HINTS):
                    entry_points.append({"function": node.name, "seenIn": rel,
                                         "line": node.lineno,
                                         "args": [a.arg for a in node.args.args][:6]})

    for baseline in baselines:
        root = target / "src" / baseline
        if not root.is_dir():
            continue
        for file in sorted(root.rglob("*.py")):
            rel = str(file.relative_to(target))
            try:
                tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            acquisition.extend(acquisition_evidence(file.read_text(encoding="utf-8",
                                                                    errors="ignore"), rel))
            aliases = _module_aliases(tree)
            for node in ast.walk(tree):
                # An entry point is what the wiring can call; a dataset name is only
                # what to call it about.
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and any(hint in node.name.lower() for hint in DATA_ENTRY_HINTS):
                    entry_points.append({"function": node.name, "seenIn": rel,
                                         "line": node.lineno,
                                         "args": [a.arg for a in node.args.args][:6]})
                # Only an attribute of an imported module, and only when called:
                # an architecture from an imported module, never a method on an object.
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and isinstance(node.func.value, ast.Name):
                    origin = aliases.get(node.func.value.id, "")
                    if origin.endswith("models"):
                        backbones.setdefault(node.func.attr, rel)
                    elif origin.endswith("datasets"):
                        datasets.setdefault(node.func.attr, rel)
                elif isinstance(node, ast.Assign):
                    targets = [n.id.lower() for n in node.targets if isinstance(n, ast.Name)]
                    if any(hint in name for name in targets for hint in ENVIRONMENT_HINTS):
                        for literal in ast.walk(node.value):
                            if isinstance(literal, ast.Constant) \
                                    and isinstance(literal.value, str) \
                                    and _names_a_dataset(literal.value):
                                datasets.setdefault(literal.value, rel)

    # Trained weights the prior work left behind name their own backbone and task.
    for product in target.glob("*/Models/**/*"):
        if product.is_file() and product.suffix.lower() in MODEL_EXT:
            weights.append(product.name)

    # An empty list must not read as "this baseline has no data layer". The reading is
    # a heuristic over English word-stems, so it misses a plausible variant (`CORPORA`
    # against the stem `corpus`) and misses anything named in another language
    # entirely. Saying what was looked for turns a silent miss into a question the
    # user can answer in one line.
    missed = [kind for kind, found in
              (("backbones", backbones), ("datasets", datasets),
               ("dataEntryPoints", entry_points), ("notebooks", notebooks),
               # Included deliberately: an empty acquisition reading is exactly the
               # one that must never be mistaken for "this cannot be obtained".
               ("acquisition", acquisition))
              if not found]
    return {
        "backbones": [{"name": n, "seenIn": w} for n, w in sorted(backbones.items())],
        "datasets": [{"name": n, "seenIn": w} for n, w in sorted(datasets.items())],
        "dataEntryPoints": entry_points[:12],
        "notebooks": notebooks[:12],
        # Never conclude the material cannot be obtained without this in hand.
        "acquisition": [dict(s) for s in {tuple(sorted(a.items())) for a in acquisition}][:12],
        "weights": sorted(weights)[:12],
        "discovered": bool(backbones or datasets or weights or entry_points),
        "foundNothingFor": missed,
        "readBy": {
            "backbones": "a called attribute of an imported models module",
            "datasets": f"a name-shaped string assigned to a variable whose name "
                        f"contains one of {list(ENVIRONMENT_HINTS)}",
            "dataEntryPoints": f"a function whose name contains one of "
                               f"{list(DATA_ENTRY_HINTS)}",
            "notebooks": "any .ipynb outside the proposal's own product directory",
            "acquisition": "a fixed and therefore partial set of patterns: a download "
                           "flag, a fetch tool, a clone, an archive, a URL, an absolute "
                           "path outside the repository. A cloud SDK or a "
                           "data-versioning tool matches none of them.",
        },
        "note": "These are heuristics over English word-stems. Where `foundNothingFor` "
                "names a kind, ask the user to point at it rather than concluding the "
                "baseline has none — a repository written in another language, or "
                "using its own vocabulary, is invisible to this reading and not "
                "missing anything." if missed else "",
    }


def wiring_proposal(target: Path, name: str, baselines: list[str]) -> dict:
    """A draft of how each implementation would become a trainable model.

    This is a proposal, never a decision. The harness knows how to train and measure;
    it cannot know what makes *this* method trainable — which modules carry the terms,
    where a backbone enters, what the classifier head predicts over. That is the
    user's mathematics, so it is read, drafted, and handed back to be completed.

    Every module already declares what it implements in `__provenance__`, so the draft
    is assembled from the repository rather than guessed, and nothing here needs to
    know what the method is about.
    """
    package = target / "src" / package_name(name)
    modules = []
    for file in sorted(package.glob("*.py")) if package.is_dir() else []:
        if file.name == "__init__.py":
            continue
        provenance = read_provenance(file) or {}
        modules.append({
            "module": f"src/{package_name(name)}/{file.name}",
            "sections": provenance.get("sections", []),
            "equations": provenance.get("equations", []),
            "invariants": provenance.get("invariants", []),
        })

    baseline_modules = []
    for baseline in baselines:
        root = target / "src" / baseline
        baseline_modules.append({
            "package": baseline,
            "files": sorted(str(f.relative_to(target)) for f in root.rglob("*.py"))[:20],
            "provenance": "absent — this package predates the managed lineage",
        })

    return {
        "status": "draft",
        "instruction": "Complete both builders, then the harness trains and measures "
                       "them in one common setting. Nothing runs until you do: a "
                       "builder left empty is reported as not applicable, never as a "
                       "result.",
        "new": {
            "package": f"src/{package_name(name)}",
            "modules": modules,
            "needs": ["which module(s) carry the trainable terms",
                      "where the backbone's features enter them",
                      "what the classifier head is and what it predicts over"],
        },
        "baseline": {
            "candidates": baseline_modules,
            "needs": ["the entry point that builds its model",
                      "whether it runs under the common reduction unedited — if it "
                      "cannot, that is a not-applicable with a reason, and the "
                      "baseline is never modified to make a comparison possible"],
        },
        "offer": {
            "fromBaseline": baseline_environment(target, baselines, name),
            "note": "Start from what the baseline already trains on: that is where its "
                    "results were obtained, so it is the environment a comparison "
                    "means something in. If that setting is too heavy to screen with, "
                    "say so and let the user name a lighter one — a forge for papers "
                    "cannot know which models or datasets are reasonable for a field "
                    "it has not read, and suggesting from a list would be guessing.",
        },
    }


def cmd_probe(args) -> dict:
    """Report what stands between this repository and a benchmark, and run nothing.

    Order matters and is reported as `nextStep`. A comparison needs something to
    compare against, so that is asked first: without a baseline the backend is nobody's
    business — numpy is where the mathematics is proved and may be exactly where this
    proposal belongs. With a baseline, an implementation computing with numpy cannot be
    trained at all, so the conversion is settled before the comparison is discussed;
    proposing a benchmark first would ask the user to approve a run that cannot happen.

    Five checks stand between a trainable repository and the offer to run, and the
    order among them is settled rather than a preference:

    A benchmark declaration that names nothing yet comes first, ahead of everything
    else here, because every other check on this list reads that same declaration.
    An arm that never calls its own mathematics is read from `arms`; a record a
    search should have written is read from `search`; a report in drift is read
    from `report`. None of them can tell a repository that has not started
    declaring from one that declared and got it wrong, and answering any of them
    before this one would tell the reader to fix a report, or a fork, that nobody
    has written the first word about yet. An arm computing mathematics it does not
    declare comes next, because correcting it changes what the arm computes — which
    changes what any later step would find — so anything read before that
    correction is read from a configuration about to change under it. A submission
    already pending on a remote worker comes next: a submission sent under broken
    wiring is already answering the wrong question, so the wiring is settled first,
    but once it is sound, an answer already on its way outranks everything else a
    repository could be told to do — offering to run again would spend real quota a
    second time on a question the first submission is already answering. A declared
    search whose record is absent comes next: a run whose governing value has not
    yet been chosen has no configuration at all, which is a narrower failure than a
    wrong report and a cheaper one to catch before the machine time is spent. The
    report comes last, because a report in drift still describes a sound run —
    wrongly, which costs a sentence to fix rather than the campaign.
    """
    target = resolve_target(args.target)
    name = validate_name(args.name)
    backend = backend_state(target, name)
    baselines = previous_implementations(target, name)
    state = probe_state(target, name, args.revision)

    # Nothing to compare against is checked first, and on purpose. numpy is a stage,
    # not a defect: it is where the mathematics is proved, with no optimizer to mask a
    # wrong formula, and for a proposal nobody is going to train it can be the last
    # stage. The conversion exists to make a comparison possible — asking for it when
    # there is nothing to compare would demand work with no purpose and read as though
    # the implementation were unfinished when it is done.
    if not baselines:
        next_step = "nothing-to-compare"
    elif not backend["trainable"]:
        next_step = "convert"
    elif state["status"] == "piloted":
        # Neither absent nor done. The flow reports the scale precisely and leaves the
        # question open: the pilot is where somebody looks, adds a test, moves a
        # proportion and runs it short again, and a menu closes that door.
        next_step = "piloted"
    elif state["status"] == "current":
        next_step = "already-benchmarked"
    else:
        next_step = "benchmark"

    # Five things are read before the run is offered, and in this order.
    #
    # A benchmark declaration with nothing answered in it comes first, ahead of
    # even the wiring check. `unreachedModules` (below) is computed *from* the
    # declaration's own `arms` block: with nothing declared it is always empty,
    # so `wiring-first` can never fire on its own in this state — reading it
    # first here would only ever find silence and let a blank scaffold fall
    # through to the checks after it, which do have something to say and say
    # it misleadingly. `report_state` already reports its own `"undeclared"`
    # the moment nothing has been answered, and without this rung that already
    # reaches the run offer through `report-first` — the wrong rung, because
    # nothing about a document disagreeing with a run is true yet; nobody has
    # written a report to disagree with. This rung is the honest one for that
    # state, and it takes the whole ladder ahead of everything built on top of
    # a declaration.
    #
    # An arm that never calls the mathematics it declares comes next, because it
    # is the only defect here that makes the run itself meaningless: every
    # number would come from an arm that was not computing what the table says
    # it computed, and no amount of repetitions fixes that.
    #
    # A submission already pending on a remote worker comes next. Once the
    # wiring is sound, an answer already on its way outranks a missing search
    # value and a report in drift alike: offering the run again would ask for a
    # second submission of a question the first one is already answering,
    # spending real quota nothing here can get back. Reused, not recomputed —
    # see `remote_execution_state()`'s own docstring for why a second fold of
    # the ledger was rejected.
    #
    # A declared search whose record is absent comes next. A configuration whose
    # governing scalar has not yet been chosen is not a configuration — nothing about
    # what "trainable" or "benchmark" means changes, but the run about to be offered
    # would have to invent a value it was never handed, silently or otherwise. That is
    # worse than a report in drift and cheaper to catch before it runs.
    #
    # The report comes last — a report in drift describes a sound run wrongly, which
    # costs a sentence rather than the campaign, but still must not be printed with
    # the authority of thirty repetitions behind it.
    resolved = resolve_benchmark_declaration(target, name)
    unfaithful = benchmark_unfaithfulness(target, name)
    remote = remote_execution_state(target, name, package_name(name))
    report = report_state(target, name, package_name(name))
    search = search_state(
        resolved["contract"],
        list((report.get("declared") or {}).get("records") or []),
        target / name, declaration_status=resolved["status"])
    if next_step in ("benchmark", "piloted") and resolved["status"] in (
            "absent", "undeclared"):
        next_step = "declare-first"
    elif next_step in ("benchmark", "piloted") and unfaithful:
        next_step = "wiring-first"
    # `drift` and `unreliable` are deliberately excluded: neither is fixed by
    # waiting. `drift` means the submission's source moved out from under it,
    # or a stale result already arrived — that needs `remote_cli reconcile`,
    # not a poll. `unreliable` means a line of the log could not even be
    # read, so nothing about what is or is not pending can be trusted yet.
    # Only `pending` names a submission a wait can actually resolve.
    elif next_step in ("benchmark", "piloted") and remote["status"] == "pending":
        next_step = "poll-first"
    elif next_step in ("benchmark", "piloted") and search["recordFound"] is False:
        next_step = "search-first"
    elif next_step in ("benchmark", "piloted") and report["status"] != "ok":
        next_step = "report-first"

    proposal = wiring_proposal(target, name, baselines) if next_step == "benchmark" else None
    # The harness is a module of the benchmark package, not a file beside a
    # notebook: `.py` outside `SOURCE_ROOTS` is a stray module, `wiring.py` has to
    # sit next to it, and `declared_dimension_names` and `benchmark_reach` both
    # read only under `src/<Package>_Benchmark/`. Looking beside the notebooks
    # reported `harness: null` on a target that had followed doctrine exactly.
    harness = target / "src" / f"{package_name(name)}_Benchmark" / BENCHMARK_MODULE
    notebook = target / name / "Notebooks" / PROBE_NOTEBOOK
    return {
        "status": "ok",
        "target": str(target),
        "name": name,
        "backend": backend,
        "baselines": baselines,
        "comparable": bool(baselines),
        "harness": str(harness.relative_to(target)) if harness.exists() else None,
        "notebook": str(notebook.relative_to(target)) if notebook.exists() else None,
        "results": state,
        "report": report,
        # Named here as well as in `verify`, because this is where the run is offered
        # and a reason not to offer it belongs beside the offer. The forecast rides
        # alongside the declaration it is projected from, rather than in `results`,
        # because what it costs is a property of the search and not of the pilot.
        # The declared scale is passed on only when it is a mapping. `search`
        # has already reported a value of any other shape as malformed, and a
        # forecast projected from a scale nobody can name an axis of would be a
        # number invented to fill the field.
        "search": {**search,
                   "costForecast": search_cost_forecast(
                       state.get("reduction") or {},
                       declared_required_scale(search))},
        "unreachedModules": unfaithful,
        # A static fact, reported and never gating: see `notebook_coupling`.
        "coupling": coupling_state(target, name, package_name(name)),
        # What went out to a remote worker (the ledger), plus what job
        # folders exist right now (the filesystem) — reported, never
        # resolved, and never a submission. See `remote_execution_jobs_state`.
        "remoteExecution": {
            **remote,
            **remote_execution_jobs_state(target),
        },
        "nextStep": next_step,
        "wiring": proposal,
        # `probe` looks and reports; it never runs anything itself.
        "kind": "read-only",
    }


class NameRefused(Exception):
    """The name the user typed cannot become a directory and a package."""


def normalize_name(raw: str) -> dict:
    """Turn whatever the user typed into the `<Name>/` + `src/<Package>/` pair.

    The user types `deep set`, `DEEP-SET` or `deepSet` and means the same thing.
    Splitting happens on any separator and on a lower-to-upper boundary; an all-caps
    token of two or more letters is an acronym and survives untouched, because
    lowercasing an acronym renames the method rather than tidying the folder.
    """
    text = (raw or "").strip()
    if not text:
        raise NameRefused("NAME_EMPTY")
    # Split first on explicit separators, then inside each piece on camel boundaries.
    tokens: list[str] = []
    for piece in re.split(r"[\s\-_]+", text):
        if not piece:
            continue
        tokens.extend(re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", piece))
    if not tokens:
        raise NameRefused("NAME_HAS_NO_WORDS")
    for token in tokens:
        if not token.isalnum():
            raise NameRefused(f"NAME_NOT_ALPHANUMERIC:{token}")
    if tokens[0][0].isdigit():
        raise NameRefused("NAME_STARTS_WITH_DIGIT")
    parts = [token if token.isupper() and len(token) >= 2 else token.capitalize()
             for token in tokens]
    return {"input": raw, "directory": "-".join(parts), "package": "_".join(parts)}


def cmd_name(args) -> dict:
    """Report the normalized pair so the agent can show it before writing anything."""
    try:
        resolved = normalize_name(args.name)
    except NameRefused as refused:
        code, _, detail = str(refused).partition(":")
        raise Refused(code, detail or f"{args.name!r} cannot become a package name")
    return {"status": "ok", **resolved}


def plan_scale(plan: dict, target: Path) -> dict:
    """Whether the plan is still something the user can read before approving it.

    `apply` is allowed to run either way — this only tells the agent which gate to
    open: apply the moves now, or hand the user a prompt for a separate session.

    `carriedFiles` is reported because knowing a rename sweeps thirty-seven files is
    worth saying out loud, but it is not a limit: see the note on LARGE_PLAN_DECISIONS.
    """
    moves = len(plan.get("moves", []))
    renames = len(plan.get("renames", []))
    references = len(plan.get("referenceUpdates", []))
    decisions = moves + renames + references

    carried = {move["from"] for move in plan.get("moves", [])}
    for rename in plan.get("renames", []):
        prefix = f"{rename['from'].rstrip('/')}/"
        carried.update(path for path in tracked_files(target) if path.startswith(prefix))

    return {
        "decisionCount": decisions,
        "breakdown": {"moves": moves, "renames": renames, "referenceUpdates": references},
        "carriedFiles": len(carried),
        "limit": LARGE_PLAN_DECISIONS,
        "scale": "large" if decisions > LARGE_PLAN_DECISIONS else "reviewable",
    }


def build_plan(target: Path, name: str) -> dict:
    paths = tracked_files(target)
    product_dir = detect_product_dir(target, name, paths)
    renames = (
        [{"from": product_dir, "to": name,
          "reason": "product folder has the right shape but the wrong name; "
                    "renaming preserves every subtree"}]
        if product_dir else []
    )

    moves: list[dict] = []
    unclassified: list[str] = []
    for path in paths:
        dest, reason = classify(path, name, product_dir)
        if dest is None:
            continue
        if dest == "":
            unclassified.append(path)
            continue
        if dest == path:
            continue
        moves.append({"from": path, "to": dest, "reason": reason})

    # Two kinds of destination clash, both fatal: onto an existing file, and two
    # moves onto each other. The second one silently destroys files.
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for move in moves:
        if move["to"] in seen:
            collisions.append(move["to"])
        seen[move["to"]] = move["from"]
    # A rename onto an existing path is the same class of clash: `git mv A B`
    # with B present does not rename, it moves A *inside* B.
    occupied = {r["to"] for r in renames if (target / r["to"]).exists()}
    conflicts = sorted({m["to"] for m in moves if (target / m["to"]).exists()}
                       | set(collisions) | occupied)

    with_data = dir_exists_after(target, f"{name}/Data", renames, name) or any(
        m["to"].startswith(f"{name}/Data/") for m in moves
    )
    missing = [d for d in expected_dirs(name, with_data)
               if not dir_exists_after(target, d, renames, name)]
    gaps = scaffold_gaps(target, name)

    plan = {
        "command": "plan",
        "target": str(target),
        "name": name,
        # Same definition of compliant as `verify`: layout AND scaffold. A repo
        # missing pyproject.toml is not compliant just because nothing moves.
        # Conflicts and unclassified files count too: `apply` refuses on both,
        # so calling that tree compliant would report as settled exactly the
        # situation the next command is about to stop on.
        "status": ("compliant"
                   if not moves and not renames and not missing and not gaps
                   and not conflicts and not unclassified
                   else "drift"),
        "renames": renames,
        "createDirs": missing,
        "moves": moves,
        "referenceUpdates": scan_reference_updates(
            target, prefix_mappings(renames, moves), paths),
        "conflicts": conflicts,
        "unclassified": unclassified,
        "scaffoldFiles": gaps,
    }
    plan["reorganization"] = plan_scale(plan, target)
    return plan


def pytest_anchor_missing(target: Path) -> bool:
    """A pyproject.toml without `pythonpath` cannot run the suite offline.

    Presence of the file is not enough: without [tool.pytest.ini_options] and
    `pythonpath = ["src"]`, importing the package needs an install step, so the
    invariant tests fail with ModuleNotFoundError instead of running.
    """
    pyproject = target / "pyproject.toml"
    if not pyproject.exists():
        return True
    text = pyproject.read_text(encoding="utf-8", errors="replace")
    return "[tool.pytest.ini_options]" not in text or "pythonpath" not in text


def well_formed(declared: object) -> list[dict]:
    """Every entry must be a mapping carrying an id, or nothing downstream holds.

    `id` is the key the whole audit bridge is addressed by: the evidence test,
    the remedy test, the admissibility verdict and the handoff item are all
    named after it. An entry without one cannot be ruled on, so reading the file
    as if it declared nothing would be the worst answer available — it reports
    `audit: none`, which is what a repository with no findings at all reports.
    """
    if not isinstance(declared, list):
        raise Refused("MALFORMED_FINDINGS",
                      "tests/findings.py assigns FINDINGS something that is not a list.")
    for index, finding in enumerate(declared):
        if not isinstance(finding, dict):
            raise Refused("MALFORMED_FINDINGS",
                          f"FINDINGS[{index}] is not a mapping, so it declares nothing "
                          "this command can rule on.")
        if not isinstance(finding.get("id"), str) or not finding["id"].strip():
            raise Refused("MALFORMED_FINDINGS",
                          f"FINDINGS[{index}] carries no `id`; the evidence test, the "
                          "remedy test and the admissibility verdict are all addressed "
                          "by it, so nothing about this finding can be checked.")
    return declared


def read_findings(target: Path) -> list[dict]:
    """The declared audit findings, read statically from tests/findings.py."""
    path = target / "tests" / "findings.py"
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        # The file exists, so somebody declared findings here. Reading it as an
        # empty list would answer `audit: none` — indistinguishable from a
        # repository that has been audited and found nothing.
        raise Refused("MALFORMED_FINDINGS",
                      f"tests/findings.py cannot be parsed: {exc}") from exc
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "FINDINGS" for t in node.targets
        ):
            try:
                declared = ast.literal_eval(node.value)
            except ValueError as exc:
                raise Refused("MALFORMED_FINDINGS",
                              "FINDINGS is not a literal, so it cannot be read without "
                              "executing the target's code.") from exc
            return well_formed(declared)
    return []


IGNORE_ENTRIES = (".venv/", "__pycache__/", ".ipynb_checkpoints/")


def ignore_gaps(target: Path) -> list[str]:
    """Entries the target's own .gitignore must carry.

    The skill creates a virtualenv inside the target, so it owns keeping it out
    of the index. A repository scaffolded from scratch has no .gitignore at all,
    and one `git add -A` commits the entire site-packages tree — measured at
    5935 files and 98 MB before this check existed. A clone only escapes it by
    inheriting an ignore file that happens to cover .venv.
    """
    path = target / ".gitignore"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    return [entry for entry in IGNORE_ENTRIES if entry.rstrip("/") not in text]


def scaffold_gaps(target: Path, name: str) -> list[str]:
    wanted = [f"src/{package_name(name)}/__init__.py",
              f"src/{package_name(name)}_Benchmark/__init__.py",
              "tests/test_smoke.py",
              "tests/findings.py", "tests/test_audit.py", "tests/test_remedies.py",
              f"{name}/Notebooks/verification.ipynb"]
    gaps = [w for w in wanted if not (target / w).exists()]
    if pytest_anchor_missing(target):
        gaps.insert(0, "pyproject.toml [tool.pytest.ini_options] pythonpath")
    missing_ignores = ignore_gaps(target)
    if missing_ignores:
        gaps.insert(0, f".gitignore ({', '.join(missing_ignores)})")
    return gaps


# --------------------------------------------------------------------------
# provenance (static, never imports target code)
# --------------------------------------------------------------------------

def read_provenance(path: Path) -> dict | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return {"__error__": f"unparsable: {exc}"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__provenance__" for t in node.targets
        ):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return {"__error__": "__provenance__ is not a literal"}
    return None


def proposals_root() -> Path:
    """Where managed revisions live.

    Overridable so the forge's own tests can drive the skill from a neutral
    fixture instead of somebody's research. A paper forge must not have its test
    suite depend on one paper.
    """
    override = os.environ.get("IMPLEMENTATION_PROPOSALS")
    return Path(override) if override else FORGE_ROOT / "proposals"


def revision_source(revision: str | None) -> str | None:
    """The bound revision's text, read from the proposals directory."""
    if not revision:
        return None
    path = proposals_root() / revision
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def latest_revision(like: str | None) -> str | None:
    """The newest managed revision of the same family as `like`.

    Everything else here compares a bench against a revision somebody typed at
    the command line. That check is only armed when the caller happens to type
    the right one: hand it the revision the bench is already bound to and it
    agrees with itself, whatever else has since landed under `proposals/`. The
    field was called `latestRevision` and was an echo of the argument.

    So the newest is discovered, not asserted. The family pattern is derived
    from a name that arrived as data — the bench's own declared revision, or a
    module's provenance — exactly the way `prose_state` derives its own, and
    for the same reason: nothing here may know a naming convention. A forge
    whose revisions are `draft-4.md` is served by the identical code.

    The ordering is on the digits as integers, not on the string, or `r9` would
    outrank `r10` and the check would report a newer revision as older — silent,
    and in the direction that approves. Names with more than one number order on
    the tuple, left to right. A name with no digits at all has no family and no
    successor to find, and says so by returning `None`.
    """
    if not like:
        return None
    name = Path(like).name
    if not re.search(r"\d", name):
        return None
    # `re.escape` leaves digits alone and escapes the suffix's dot, so the only
    # thing turned into a wildcard is a run of digits. Anchored: a family is
    # matched whole, never as a substring of a longer name.
    stem = re.sub(r"\d+", r"(\\d+)", re.escape(name))
    family = re.compile("^" + stem + "$")
    root = proposals_root()
    if not root.is_dir():
        return None
    best: tuple[tuple[int, ...], str] | None = None
    for candidate in sorted(root.iterdir()):
        if not candidate.is_file():
            continue
        found = family.match(candidate.name)
        if not found:
            continue
        key = tuple(int(group) for group in found.groups())
        if best is None or key > best[0]:
            best = (key, candidate.name)
    return best[1] if best else None


# How a paper labels an equation, and the only place this skill decides it.
# A tag is whatever the author put between the braces: `3.1`, `A.2`, `B.10`.
# Every reader — `admit`, this compatibility audit, `compose` and `handoff` —
# reads it through this one pattern. Two of them used to carry a digits-only
# copy of their own, which ruled a citation absent from a document that
# carries it, and gave that false reason to whoever was reading.
TAG_RE = re.compile(r"\\tag\{([^}]+)\}")


def remedy_compatibility(findings: list[dict], revision: str | None) -> dict:
    """Is each remedy expressible inside the proposal as it stands?

    A correction that is sound in isolation is still half a remedy if it cites
    an equation that does not exist, leans on notation the document never
    defines, or quietly introduces symbols of its own. Those are not defects to
    be validated away by a sweep — they are decisions that belong to the
    deliberation, and the skill must not report them as settled.

    Every finding declares `uses` (notation the remedy relies on, which must
    appear verbatim in the revision) and `introduces` (notation it would add).
    A non-empty `introduces` is not a failure: it is a remedy that cannot be
    called complete until the deliberation accepts the new notation.
    """
    source = revision_source(revision)
    if source is None:
        return {"status": "unknown", "reason": f"revision {revision!r} not readable",
                "unknownEquations": [], "undefinedNotation": [], "introducesNotation": []}

    tags = set(TAG_RE.findall(source))
    unknown_equations: list[str] = []
    undefined_notation: list[str] = []
    introduces: list[str] = []

    for finding in findings:
        for field in ("equations", "remedy_equations"):
            missing = [e for e in finding.get(field, []) if e not in tags]
            if missing:
                unknown_equations.append(f"{finding['id']}.{field}: {missing}")
        absent = [s for s in finding.get("uses", []) if s not in source]
        if absent:
            undefined_notation.append(f"{finding['id']}: {absent}")
        if not finding.get("uses"):
            undefined_notation.append(f"{finding['id']}: declares no notation at all")
        if finding.get("introduces"):
            introduces.append(f"{finding['id']}: {finding['introduces']}")

    if unknown_equations or undefined_notation:
        status = "incompatible"
    elif introduces:
        status = "needs-deliberation"
    else:
        status = "ok"
    return {"status": status, "unknownEquations": unknown_equations,
            "undefinedNotation": undefined_notation, "introducesNotation": introduces}


def remedies_without_control(tests_dir: Path, package: str) -> list[str]:
    """Remedy tests that never exercise the formulation they are correcting.

    A remedy test measures a proposed replacement. If it never also exercises
    the declared formulation, nothing in it can distinguish a real improvement
    from a measurement that would pass whatever it was handed — and a check
    incapable of going red reads exactly like a check that went green.

    The control is the other pole: the declared form must be shown to fail the
    same criterion the remedy satisfies. Requiring the test to call into the
    package is the machine-checkable part of that.
    """
    missing: list[str] = []
    if not tests_dir.is_dir():
        return missing
    for file in sorted(tests_dir.glob("test_remedies*.py")):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (SyntaxError, UnicodeDecodeError):
            continue
        declared = {
            alias.name for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").split(".")[0] == package
            for alias in node.names
        }
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_remedy_"):
                continue
            called = {
                inner.func.id for inner in ast.walk(node)
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            }
            if not called & declared:
                missing.append(node.name)
    return missing


def trivial_assertions(tests_dir: Path) -> list[str]:
    """Assertions that cannot fail, and therefore prove nothing.

    Two shapes are caught: asserting a truthy constant, and comparing an
    expression with itself. The second is the dangerous one — it reads exactly
    like a real check. `adaptation(w) == adaptation(w)` survived three full
    rounds of the battery, green every time, until it was read by hand.

    A suite is only fail-closed if its assertions can actually fail.
    """
    # Self-comparison is scanned everywhere, not only inside `assert`: the one
    # that got through fed a counter — `hits += f(w) == f(w)` — and the assert
    # on that counter was perfectly legitimate. Looking only at assertions finds
    # the comfortable case, not the dangerous one.
    # `!=` is exempt: `x != x` is the standard NaN test, not a mistake.
    always_true = (ast.Eq, ast.Is, ast.LtE, ast.GtE, ast.Lt, ast.Gt, ast.IsNot)
    trivial: list[str] = []
    if not tests_dir.is_dir():
        return trivial
    for file in sorted(tests_dir.rglob("test_*.py")):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                if isinstance(node.test, ast.Constant) and node.test.value:
                    trivial.append(f"{file.name}:{node.lineno}: asserts a constant")
            elif isinstance(node, ast.Compare) and len(node.comparators) == 1:
                if (isinstance(node.ops[0], always_true)
                        and ast.dump(node.left) == ast.dump(node.comparators[0])):
                    trivial.append(
                        f"{file.name}:{node.lineno}: compares an expression with itself")
    return trivial


#: The line an executed report prints so its evidence can be tied to the code that
#: produced it. `execution_count` proves a cell ran once; it says nothing about what
#: it ran against, and a report that ran once and was never re-run stays green while
#: the code moves out from under it.
DIGEST_MARKER = "SOURCES-SHA256"


#: What the benchmark package declares instead of `__provenance__`. It implements no
#: equation, so provenance would be a lie; but without any declaration nobody can
#: answer the question a new revision immediately raises — does this change oblige the
#: bench to change?
BENCHMARK_DECLARATION = "__benchmark__"

#: What the benchmark declares about the document a human reads, rather than about
#: the numbers it produces. Everything else in this file checks that the run was
#: sound; without this, nothing checks that the report of it is.
#:
#: It is a declaration and not a list of names in this file, and that is the whole
#: point: `verify` must not learn what a metric is called in somebody's field. The
#: target says which functions render, which produce conclusions, and which way each
#: dimension wins; the checks below read only that.
#:
#:     "report": {
#:         "renderers":   ["tables.render", "harness.render_panorama"],
#:         "conclusions": ["tables.conclusion", "tables.conclusion_rungs"],
#:         "figures":     ["figures.curves", "latent.grid"],
#:         "dimensions":  {"accuracy": "higher", "seconds": "lower"},
#:     }
#:
#: `figures` is what lets the check below ask whether a picture was actually shown
#: without knowing one word about how anybody draws. Naming the drawing calls is the
#: target's job for the same reason naming the renderers is: a check that guessed at
#: plotting libraries would be a check that learned somebody's toolchain, and would
#: go silent the moment a repository used a different one.
REPORT_KEY = "report"

#: A decimal with two or more places in prose is a measurement somebody typed. One
#: place, or a bare integer, is usually structure — a count of panels, a section
#: number — and flagging those would train the reader to ignore the check.
PROSE_NUMBER = re.compile(r"\d+[.,]\d{2,}")


def _dotted_calls(source: str) -> list[str]:
    """Every `module.function` and bare `function` called in one cell."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                names.append(f"{func.value.id}.{func.attr}")
            # `(root / "report.txt").write_text(...)` has an expression on the left,
            # so the dotted form never appears. The bare attribute is added too:
            # a call is still a call when what it is called on was computed.
            names.append(func.attr)
        elif isinstance(func, ast.Name):
            names.append(func.id)
    return names


def _notebook_cells(path: Path) -> list[dict]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return []
    cells = document.get("cells")
    return cells if isinstance(cells, list) else []


def _source_of(cell: dict) -> str:
    source = cell.get("source")
    return "".join(source) if isinstance(source, list) else str(source or "")


def _produced(cell: dict) -> dict:
    """What a cell actually emitted, as opposed to what its code says it emits.

    Every other reading of a notebook in this file goes to the *sources*: which
    calls appear, which numbers are typed in prose. Two questions cannot be
    answered there, and both are ways a cell reports nothing while looking like it
    reported something:

    * it computed a measurement and never showed it, and
    * it drew a figure and emitted a *description* of the figure.

    The second is the quiet one. A cell that displays a figure object without the
    runtime's image formatter registered emits `<Figure size ...>` as plain text:
    the cell ran, raised nothing, produced an output, and shows the reader a line
    of prose where the picture belongs. `execution_count` says it ran and the
    error list is empty, so nothing that reads only those two can see it.

    Returns the MIME types the cell displayed, the plain-text payloads it wrote,
    whether it printed anything, and whether it emitted anything at all.
    """
    mimes: set[str] = set()
    bare: list[str] = []
    shown: list[str] = []
    streamed = False
    for output in cell.get("outputs") or []:
        if not isinstance(output, dict):
            continue
        kind = output.get("output_type")
        if kind == "stream":
            streamed = True
            text = output.get("text")
            shown.append("".join(text) if isinstance(text, list) else str(text or ""))
        elif kind in ("display_data", "execute_result"):
            data = output.get("data")
            if isinstance(data, dict):
                mimes.update(str(key) for key in data)
                plain = data.get("text/plain")
                # Judged per output and never across the cell, because a rich
                # rendering carries a `text/plain` repr *beside* it as a fallback:
                # a displayed Markdown block stores `<IPython…Markdown object>`
                # next to its `text/markdown`, and reading the cell as a whole
                # would call every one of those a figure that never rendered.
                # What names the defect is an output the runtime could render no
                # other way — plain text and nothing else.
                if plain is not None and set(data) == {"text/plain"}:
                    bare.append("".join(plain) if isinstance(plain, list)
                                else str(plain))
                for key in ("text/markdown", "text/plain"):
                    payload = data.get(key)
                    if payload is not None:
                        shown.append("".join(payload) if isinstance(payload, list)
                                     else str(payload))
                        break
        elif kind == "error":
            # An error is its own finding, reported by `notebook_execution`. Left
            # unmarked here it would also read as a cell that showed nothing, and
            # one defect would be reported as two.
            return {"mimes": set(), "bare": [], "shown": "", "streamed": True,
                    "any": True, "errored": True}
    return {"mimes": mimes, "bare": bare, "shown": "\n".join(shown),
            "streamed": streamed, "any": bool(mimes or streamed), "errored": False}


#: A number a cell put in front of a reader: a decimal, or a count over a total
#: like `7/10`. Integers alone are left out — a year, a seed or a count of rows is
#: not a measurement, and treating every digit as one would make the check below
#: fire on any sentence that mentions how many transfers there are.
MEASUREMENT = re.compile(r"\d+\.\d+|\b\d+/\d+\b")

#: How many of its table's measurements a conclusion may restate before it stops
#: concluding and starts re-rendering. The number is not arbitrary: a conclusion
#: exists to say what the table cannot — who is ahead and what that rests on — and
#: naming the value it rests on is part of saying it. One or two values is a
#: conclusion showing its evidence. Three or more is the table again, in prose,
#: which is the duplication rule with a sentence in front of it.
RESTATED_LIMIT = 2


def _shows_image(produced: dict) -> bool:
    """Whether the cell emitted a picture rather than a sentence describing one."""
    return any(mime.startswith("image/") for mime in produced["mimes"])


#: An output that is nothing but an object's repr: `<Figure size 640x480 with 6
#: Axes>`, `[<Line2D object at 0x10a…>]`. It means something was displayed and the
#: runtime had no formatter for its type, so the reader got a *description* of the
#: thing where the thing belongs.
#:
#: This matches the shape of the output, and that is the whole point of it. Every
#: other way to catch this failure has to know who draws — and a check that knows
#: one plotting library is a check that goes silent for every repository using
#: another. Nothing here names a library, and nothing here has to.
OBJECT_REPR = re.compile(r"^\[?\s*<[A-Za-z_][\w.]*[^\n]*>\s*\]?$")


def _described(produced: dict) -> str | None:
    """The output that describes an object instead of showing it, if there is one.

    Independent of any declaration, which is what makes it worth having: the
    declared-drawing check below can only fire in a repository that wrote its
    drawing calls down, and the repository most likely to ship this defect is
    exactly the one that never did.
    """
    for text in produced["bare"]:
        stripped = text.strip()
        if stripped and OBJECT_REPR.match(stripped):
            return stripped[:120]
    return None


#: Read inside the target's own interpreter, because both questions below need the
#: real values and neither can be answered from the text of the file. A constant
#: built by a comprehension has no literal to compare, and a conclusion that cannot
#: come out different can only be caught by making it try.
#:
#: It imports the target's benchmark package and nothing of this skill, runs in the
#: target's virtualenv, and prints one JSON object. It never writes.
INTROSPECT = r'''
import importlib, json, random, sys

package = sys.argv[1]
record = sys.argv[2]
config = importlib.import_module(f"{package}_Benchmark.config")
declaration = importlib.import_module(f"{package}_Benchmark")
contract = getattr(declaration, "__benchmark__", {}).get("report", {})

def frozen(value):
    """A collection as a comparable set, or nothing if it is not one."""
    if isinstance(value, (list, tuple, set)) and value:
        try:
            return frozenset(value)
        except TypeError:
            return None
    return None

# Constants that are a proper subset of another constant: a selection somebody
# wrote out. Legitimate when the rule that fixed it looks at no outcome — and that
# is a claim a human makes, so it is declared rather than inferred.
values = {n: frozen(getattr(config, n)) for n in dir(config) if n.isupper()}
values = {n: v for n, v in values.items() if v}
subsets = []
for name, value in sorted(values.items()):
    for other, whole in sorted(values.items()):
        if name != other and value < whole:
            subsets.append({"constant": name, "of": other, "size": len(value),
                            "whole": len(whole)})
            break

# A conclusion that says the same thing about different numbers is tied to nothing.
# Its input is permuted rather than replaced, so the shapes and the keys survive and
# only the correspondence between them moves.
def shuffled(value, rng):
    if isinstance(value, list):
        copy = [shuffled(v, rng) for v in value]
        rng.shuffle(copy)
        return copy
    if isinstance(value, dict):
        # Keys keep their own values. Moving a value to another key changes the
        # *shape* of the record, and a conclusion that then raises would be
        # reported as untied when it was only handed something malformed. What has
        # to move is the numbers, not the structure they hang from.
        return {k: shuffled(v, rng) for k, v in value.items()}
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return type(value)(value * rng.uniform(1.5, 4.0) + rng.uniform(1.0, 5.0))
    return value

# One entry point and not a list of functions, because guessing at signatures is
# how a check ends up reporting "could not exercise" and being read as a pass. The
# target wires its own conclusions behind one call that takes the record and gives
# back {label: text}; this only has to invoke it twice.
inert = []
entry = contract.get("conclusionEntry")
payload = json.load(open(record, encoding="utf-8")) if record else {}
if not entry:
    inert.append({"conclusion": "*", "reason": "el contrato no declara conclusionEntry"})
elif not payload:
    inert.append({"conclusion": entry, "reason": "sin registro sobre el que probar"})
else:
    module_name, _, function_name = entry.rpartition(".")
    try:
        module = importlib.import_module(f"{package}_Benchmark.{module_name}")
        produce = getattr(module, function_name)
        rng = random.Random(0)
        first = produce(payload)
        second = produce(shuffled(payload, rng))
    except Exception as exc:
        inert.append({"conclusion": entry, "reason": f"no se pudo ejercitar: {exc}"})
    else:
        for label in sorted(set(first) | set(second)):
            if first.get(label) == second.get(label):
                inert.append({"conclusion": label,
                              "reason": "el texto no cambia cuando cambian los números"})

print(json.dumps({"subsets": subsets, "inertConclusions": inert}))
'''


def introspect(target: Path, package: str, record: Path | None) -> dict:
    """Run the two live checks inside the target's interpreter, or say why not.

    Never the forge's: the whole isolation rule of this skill, and here it is also
    the only interpreter where the target's own package imports at all.
    """
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    interpreter = target / ".venv" / bin_dir / ("python.exe" if os.name == "nt"
                                                else "python")
    if not interpreter.exists():
        return {"status": "unavailable",
                "detail": f"no hay intérprete en {interpreter}: corré `env` primero"}
    proc = subprocess.run(
        [str(interpreter), "-c", INTROSPECT, package,
         str(record) if record and record.exists() else ""],
        capture_output=True, text=True, cwd=str(target),
        env={**os.environ, "PYTHONPATH": str(target / "src")},
    )
    if proc.returncode != 0:
        return {"status": "unavailable",
                "detail": (proc.stderr.strip().splitlines() or ["falló sin mensaje"])[-1]}
    try:
        return {"status": "ok", **json.loads(proc.stdout or "{}")}
    except json.JSONDecodeError:
        return {"status": "unavailable", "detail": "salida ilegible del intérprete"}


def report_contract(target: Path, name: str) -> dict:
    """What the benchmark declares about its own report, or nothing."""
    contract = resolve_benchmark_declaration(target, name)["contract"].get(REPORT_KEY)
    return contract if isinstance(contract, dict) else {}


def report_state(target: Path, name: str, package: str) -> dict:
    """Whether the document a human reads obeys the rules the numbers already do.

    Each finding below is a way a report can be wrong while every number behind it
    is right:

    `proseNumbers`      a measurement typed into prose. It cannot be recomputed, so
                        it survives the run that contradicts it. It catches a
                        hand-written conclusion, a caption
                        left over from an earlier campaign, and a figure the text
                        already disagrees with.
    `duplicated`        the same measurement rendered twice. Two renderings of one
                        number are two things that can drift apart, and the reader
                        has no way to know which one moved.
    `unframed`          a table with nothing before it saying what it measures and
                        which direction wins. A reader should not have to reverse
                        engineer the direction of a column.
    `unconcluded`       a table with no conclusion after it, or one that is a string
                        literal rather than a computed statement. A conclusion typed
                        by hand is the `proseNumbers` failure wearing a sentence.
    `undeclared`        a dimension rendered whose direction the package never
                        declared, so nothing could have checked its framing.
    `unrendered`        a cell that computed a declared measurement and emitted
                        nothing. The number exists and no reader ever sees it.
    `describedNotShown` a cell that emitted a description of a figure instead of
                        the picture. This is the one that hides best: the cell ran,
                        raised nothing, produced an output, and every check that
                        reads `execution_count` and the error list calls it green.
                        Reachable two ways — through a declared drawing call, and
                        through the shape of the output alone.
    `undeclaredDrawings` a cell that showed a picture no declared call could have
                        drawn, so `figures` is short by that call.

    The last three are the only ones that read what a cell *produced* rather than
    what its code says. Everything else here can be answered from the sources, and
    a defect that only exists in the outputs was invisible to all of it.

    `undeclaredDrawings` is what keeps the other two honest. A finding that fires
    only on a declared call is not a net, it is a courtesy: the repository most
    likely to ship a figure that never rendered is the one that never wrote its
    drawing calls down, and there the check would be silent and the report green.
    So an undeclared drawing is itself a finding, and the shape-of-the-output route
    into `describedNotShown` fires with no declaration at all.

    Nothing here judges whether a conclusion is *correct*. That would need to know
    what the numbers mean, which is exactly what this file may not know.
    """
    contract = report_contract(target, name)
    renderers = set(contract.get("renderers") or [])
    conclusions = set(contract.get("conclusions") or [])
    drawings = set(contract.get("figures") or [])
    dimensions = dict(contract.get("dimensions") or {})
    # One declared call that states, for a dimension, which value would count as
    # the good one. An entry point rather than a list of targets, for the same
    # reason `conclusionEntry` is one: what a good value looks like is a fact about
    # somebody's field, and a check that enumerated the kinds — a chance level, a
    # unit interval, a distance that should fall — would have learned that field.
    # Here it only asks whether the section says it, never what it says.
    #
    # It also has to be *computed*. A target typed into prose goes stale exactly
    # like a measurement typed into prose: the day the class count changes, the
    # sentence keeps naming the old chance. That is the same defect `proseNumbers`
    # exists for, wearing an objective instead of a result.
    aim = contract.get("objectiveEntry")

    root = target / name / "Notebooks"
    notebooks = sorted(root.glob("*.ipynb")) if root.is_dir() else []

    # Which notebooks no longer match the code. Every finding below is read off
    # what a notebook *emitted*, so on a stale one it describes the run that
    # happened and not the code that is there now — and a reader who takes it for
    # a live defect goes and fixes something already fixed, or fixes it a second
    # way. Both halves were already computed and reported, in two different places
    # in this output, and nobody crossed them; `fromStaleNotebook` is that join.
    #
    # Anything that is not `executed`, rather than `stale-sources` alone. The
    # status ladder is exclusive and `stale-sources` sits at the top of it: a
    # notebook is only compared against the current digest once it is known to
    # have run clean, so one with an unexecuted cell is called `stale` and stops
    # there — its sources can differ in everything and the name never changes.
    # Naming only the top rung therefore dropped the mark exactly where the
    # notebook was *more* out of date and not less, which is the one direction
    # this could go wrong in: a half-run notebook measured against other code
    # reported its findings as live.
    stale = {r["notebook"] for r in notebooks_state(target, name, package)["reports"]
             if r["status"] != "executed"}
    if not contract:
        # `report_contract` alone cannot tell "no Benchmark package at all" from
        # "one exists and simply names no report" — both read as `{}`. Asking
        # the resolver directly, only on this already-empty path, recovers the
        # distinction without report_contract growing a status of its own (see
        # `resolve_benchmark_declaration`'s docstring on why it keeps its
        # narrow `-> dict` job).
        absent = resolve_benchmark_declaration(target, name)["status"] == "absent"
        return {
            "status": "absent" if absent else "undeclared",
            "detail": ("no Benchmark package declares anything yet" if absent else
                       f"src/{package}_Benchmark/__init__.py declares no "
                       f"{BENCHMARK_DECLARATION}[{REPORT_KEY!r}], so nothing states "
                       f"which calls render and which conclude, and no check below "
                       f"could run without guessing at somebody's field"),
            "notebooks": [str(p.relative_to(target)) for p in notebooks],
        }

    prose_numbers: list[dict] = []
    duplicated: list[dict] = []
    unframed: list[dict] = []
    unconcluded: list[dict] = []
    undeclared: set[str] = set()
    unaimed: list[dict] = []
    unrendered: list[dict] = []
    described_not_shown: list[dict] = []
    undeclared_drawings: list[dict] = []
    restated: list[dict] = []

    for notebook in notebooks:
        cells = _notebook_cells(notebook)
        rel = str(notebook.relative_to(target))
        seen: dict[str, int] = {}
        # The measurements the most recent table put on screen, and which cell put
        # them there. Reset per notebook so a conclusion is never matched against a
        # table from a different document.
        table_numbers: set[str] = set()
        table_cell: int | None = None

        for index, cell in enumerate(cells):
            source = _source_of(cell)
            if cell.get("cell_type") == "markdown":
                for match in PROSE_NUMBER.finditer(source):
                    line = source[:match.start()].count("\n") + 1
                    prose_numbers.append({"notebook": rel, "cell": index,
                                          "line": line, "value": match.group(0)})
                continue
            if cell.get("cell_type") != "code":
                continue

            calls = _dotted_calls(source)
            # Two readings of the same list, and the difference is the whole point
            # of keeping both. `renderings` counts what the cell actually printed,
            # repeats included; `rendered` is the distinct set, which is what the
            # dimension and output checks below want. Collapsing to the set before
            # counting made a cell that printed the same table twice look like a
            # cell that printed one — and that is exactly the shape "one cell, one
            # measurement" exists to catch.
            renderings = [c for c in calls if c in renderers]
            rendered = sorted(set(renderings))
            drawn = sorted(set(c for c in calls if c in drawings))

            # A cell that writes to disk is the record, and the record is supposed
            # to hold everything the notebook showed. Counting it as a second
            # reading would make the one file a later session depends on look like
            # the defect, and the only way to satisfy the check would be to stop
            # writing it.
            writes_record = any(call.endswith(("write_text", "write_bytes", "write"))
                                for call in calls)

            # The only reading in this file that goes to what a cell produced.
            # Skipped when the cell never ran: an unexecuted notebook is already
            # `validation`'s finding, and repeating it here as one report defect
            # per cell would bury the ones that are about the report.
            if cell.get("execution_count") is not None:
                produced = _produced(cell)
                shows_image = _shows_image(produced)
                if not produced["errored"]:
                    # Two ways in, and only one of them needs the contract. A cell
                    # that emitted a description of an object where a picture
                    # belongs is a defect whoever drew it, and the output says so
                    # on its own. That second route is the one that matters: a
                    # check reachable only through a declared call goes quiet in
                    # precisely the repository that never declared one.
                    described = _described(produced)
                    # Two routes, and the first needs no contract: an output the
                    # runtime could only render as plain text is a description of
                    # the object whatever the cell was supposed to draw. The
                    # second is the declared one, and it still reads the cell as a
                    # whole — a declared drawing call that produced no picture
                    # anywhere in its cell drew nothing a reader can see.
                    if described is not None or (drawn and not shows_image):
                        described_not_shown.append({
                            "notebook": rel, "cell": index,
                            "drawing": ", ".join(drawn) or "<sin declarar>",
                            "emitted": sorted(produced["mimes"])
                                       or (["texto"] if produced["streamed"] else []),
                            # The repr itself when that is what gave it away, so
                            # the reader sees the sentence that stood in for the
                            # picture rather than being told one exists.
                            "description": described,
                        })
                    # A picture came out of a call the contract never named, so
                    # `figures` is short by that call and every check that reads it
                    # was blind to this cell. Reported rather than inferred: which
                    # of these calls draws is a claim about the package, and the
                    # package is where it gets declared.
                    if shows_image and not drawn:
                        # Dotted calls only. The bare ones are `len`, `print`,
                        # `float` and the method names already counted with their
                        # receiver, and a finding that hands back thirty-four
                        # entries is one nobody reads to the end.
                        undeclared_drawings.append({
                            "notebook": rel, "cell": index,
                            "calls": sorted(set(c for c in calls
                                                if "." in c
                                                and c not in renderers
                                                and c not in conclusions)),
                        })
                    if rendered and not writes_record and not produced["any"]:
                        unrendered.append({"notebook": rel, "cell": index,
                                           "rendering": ", ".join(rendered)})

                    # A conclusion that says the table again. Every other reading
                    # of duplication compares one rendering with another; this one
                    # crosses from a rendering to the sentence about it, which is
                    # where the same measurement most easily ends up living twice.
                    # It can only be asked of what the cells *emitted*: the number
                    # is not in either source, it is in both outputs.
                    concluded = sorted(set(c for c in calls if c in conclusions))
                    if rendered and not writes_record:
                        table_numbers = set(MEASUREMENT.findall(produced["shown"]))
                    elif concluded and table_numbers:
                        repeated = table_numbers & set(
                            MEASUREMENT.findall(produced["shown"]))
                        if len(repeated) > RESTATED_LIMIT:
                            restated.append({
                                "notebook": rel, "cell": index,
                                "conclusion": ", ".join(concluded),
                                "table": table_cell,
                                "repeated": sorted(repeated)[:8],
                                "count": len(repeated),
                            })
                    if rendered and not writes_record:
                        table_cell = index

            if not rendered:
                continue

            # Which declared dimensions this rendering names, so the same table is
            # recognised as the same table wherever it is printed.
            named = sorted(d for d in dimensions
                           if f'"{d}"' in source or f"'{d}'" in source)
            if not writes_record:
                for key in named or ["<sin dimensión>"]:
                    for call in rendered:
                        signature = f"{call}({key})"
                        if signature in seen:
                            duplicated.append({"notebook": rel, "cell": index,
                                               "first": seen[signature],
                                               "rendering": signature})
                        else:
                            seen[signature] = index

                if len(renderings) > 1:
                    duplicated.append({"notebook": rel, "cell": index,
                                       # Lo que la celda imprimió, con repeticiones:
                                       # `a + a` es el caso que el conjunto perdía.
                                       "rendering": " + ".join(sorted(renderings)),
                                       "reason": "más de una medición en una celda"})

            # A section may legitimately render more than once before it concludes,
            # and the rule that forbids two measurements in one cell is what makes
            # that shape necessary rather than sloppy. A ratio's numerator and its
            # denominator are the clearest case: neither may be reported alone —
            # one falling is alignment or collapse and only the pair tells them
            # apart — so they are two tables under one framing with one conclusion
            # that reads both. Demanding a heading between them, or a conclusion
            # after each, would force either the cell this file already refuses or
            # a conclusion drawn from half a reading.
            #
            # So both questions are asked of the *section* rather than of the
            # adjacent cell: walking back over sibling renderings to find the
            # framing, and forward over them to find the conclusion. What the
            # checks still guarantee is unchanged — a section that frames nothing,
            # or that never concludes, is caught exactly as before.
            def _sibling_rendering(cell_at: dict) -> bool:
                """Another table of this same section, rather than other work.

                The computed objective counts as framing and not as other work: a
                framing has a written half and a computed one, and the value to aim
                for belongs to the second because it must not be typed.
                """
                if cell_at.get("cell_type") != "code":
                    return False
                sibling = _dotted_calls(_source_of(cell_at))
                if aim and aim in sibling and not any(c in renderers for c in sibling):
                    return True
                return (any(c in renderers for c in sibling)
                        and not any(c in conclusions for c in sibling))

            back = index - 1
            while back >= 0 and _sibling_rendering(cells[back]):
                back -= 1
            frame = next((cells[step] for step in range(back, -1, -1)
                          if cells[step].get("cell_type") == "markdown"), None)
            gap = any(cells[step].get("cell_type") == "code"
                      for step in range(back, -1, -1)
                      if _dotted_calls(_source_of(cells[step])))
            if frame is None or not _source_of(frame).strip():
                unframed.append({"notebook": rel, "cell": index,
                                 "rendering": ", ".join(sorted(set(rendered)))})
            elif gap and back >= 0 and cells[back].get("cell_type") != "markdown":
                unframed.append({"notebook": rel, "cell": index,
                                 "rendering": ", ".join(sorted(set(rendered))),
                                 "reason": "la explicación no está inmediatamente antes"})

            # Whether the section says what value would count as the good one. A
            # direction is not a target: «higher is better» tells a reader which
            # way to look and nothing about where to stop, and somebody who does
            # not already know the metric learns nothing from it. Asked of the
            # section, over the same walk-back that finds the framing, because the
            # objective belongs to the framing.
            aimed = bool(aim) and any(
                aim in _dotted_calls(_source_of(cells[step]))
                for step in range(back, index)
                if cells[step].get("cell_type") == "code")
            # The cell that writes the record is exempt, for the same reason it is
            # exempt from the duplication rule: it is the file, not a reading. It
            # renders everything the notebook showed in order to store it, and
            # asking it to state an objective would put one sentence in front of a
            # dozen unrelated tables.
            if not aimed and not writes_record:
                unaimed.append({
                    "notebook": rel, "cell": index,
                    "rendering": ", ".join(sorted(set(rendered))),
                    # An absent declaration is the reason, not an excuse. Silence
                    # here would make a package that declares no objective at all
                    # indistinguishable from one whose objectives are all stated.
                    "reason": ("el contrato no declara objectiveEntry" if not aim
                               else "la sección no dice qué valor se busca"),
                })

            concluded = any(c in conclusions for c in calls)
            forward = index + 1
            while not concluded and forward < len(cells):
                follower = cells[forward]
                if follower.get("cell_type") == "markdown":
                    # The next framing opens another section, so this one closed
                    # without concluding.
                    break
                if follower.get("cell_type") == "code":
                    ahead = _dotted_calls(_source_of(follower))
                    if any(c in conclusions for c in ahead):
                        concluded = True
                        break
                    if not any(c in renderers for c in ahead):
                        break
                forward += 1
            if not concluded:
                unconcluded.append({"notebook": rel, "cell": index,
                                    "rendering": ", ".join(sorted(set(rendered)))})

    # The two that need real values. A constant built by a comprehension has no
    # literal to compare, and a conclusion that cannot come out different can only
    # be caught by making it try.
    fixed = dict(contract.get("selections") or {})
    record = next((p for p in sorted((target / name).rglob("*.json"))
                   if p.name in (contract.get("record") or "latent.json")), None)
    declared_records, undeclared_records = records_state(target, name, contract)
    live = introspect(target, package, record)
    written_selections = [
        {**row, "rule": None} for row in live.get("subsets", [])
        if row["constant"] not in fixed
    ]
    inert = live.get("inertConclusions", [])

    # A term correctly implemented and multiplied by something tiny produces a
    # column of near-zeros that reads like a result. `contribution` on its own —
    # the numerator, with no denominator beside it — cannot tell "the term
    # commanded nothing" from "the term was scaled to nothing", and both print
    # small. The rule to report each component's share existed in prose only, and
    # a repository shipped the numerator alone with the verification green.
    #
    # What is checked is the declaration, never the meaning: nothing here may
    # learn what a term of somebody's objective is called. The package names its
    # components and the dimension that carries their share; this asks whether
    # each one is actually recorded, and whether a package with more than one
    # component declares a share at all.
    components = contract.get("components") or {}
    terms = list(components.get("terms") or [])
    share = components.get("share")
    unrecorded = [t for t in terms if t not in dimensions]
    if share and share not in dimensions:
        unrecorded.append(share)
    if len(terms) > 1 and not share:
        shareless = [{"terms": terms,
                      "reason": "más de un término y ningún `share` declarado: la "
                                "parte de cada uno no se puede leer del registro"}]
    elif not components:
        shareless = [{"terms": [],
                      "reason": "el contrato no declara `components`; sin ellos nadie "
                                "puede decir si un término no hizo nada o no pesó nada"}]
    else:
        shareless = []

    findings = {"proseNumbers": prose_numbers, "duplicated": duplicated,
                "unframed": unframed, "unconcluded": unconcluded,
                "undeclared": sorted(undeclared),
                # The two halves of the share check. `componentsNotRecorded` is a
                # declared term the record never carries; `componentsWithoutShare`
                # is the absence of the declaration itself, reported as its own
                # reason rather than passed over in silence.
                "componentsNotRecorded": sorted(unrecorded),
                "componentsWithoutShare": shareless,
                # What the run left where its records live and nothing declared.
                # Every other check fires only on something somebody wrote down,
                # so the repository running an experiment nobody accounted for is
                # exactly the one where they all stay quiet.
                "undeclaredRecords": undeclared_records,
                # A measurement computed and never shown, and a figure that came
                # out as a sentence describing a figure. Both are cells that ran
                # clean and reported nothing, which is why no check that reads
                # `execution_count` and the error list has ever caught one.
                # Una sección que muestra una medición y nunca dice contra qué
                # se la compara. La dirección sola no alcanza: dice para qué lado
                # mirar y nada sobre dónde termina lo bueno.
                "unaimed": unaimed,
                "unrendered": unrendered,
                "describedNotShown": described_not_shown,
                # A cell that showed a picture no declared call could have drawn.
                # It is what keeps the two findings above from being a courtesy:
                # without it, a package that declares no `figures` is indistinguishable
                # from a package whose figures are all fine.
                "undeclaredDrawings": undeclared_drawings,
                # A conclusion that restated its own table instead of concluding
                # from it. `duplicated` compares renderings with renderings and
                # cannot see this one: the second copy is not a rendering, it is a
                # sentence, and the number lives only in what both cells emitted.
                "restated": restated,
                # A subset written by hand is a selection nobody had to justify.
                # It is legitimate when the rule that fixed it looks at no outcome,
                # and that is a claim a human makes — so it is declared in the
                # contract rather than inferred from the shape of a list.
                "writtenSelections": written_selections,
                # `trivialAssertions` for the report: a conclusion that says the
                # same thing about different numbers is tied to nothing, exactly
                # as an assertion that cannot fail proves nothing.
                "inertConclusions": inert}
    # Stamp every finding that names a notebook with whether that notebook still
    # matches the code. Written here rather than at each site so a check added
    # later cannot forget it, and so the flag can never disagree with the
    # staleness the same run reports two keys away.
    for rows in findings.values():
        for row in rows:
            if isinstance(row, dict) and row.get("notebook") in stale:
                row["fromStaleNotebook"] = True

    clean = all(not value for value in findings.values())
    status = "ok" if clean else "drift"
    if live.get("status") != "ok":
        # An unavailable check is never a pass. Two of the findings could not be
        # looked for, and saying `ok` would report their absence as their answer.
        status = "incomplete" if clean else "drift"
    return {"status": status,
            "live": live.get("status"),
            "liveDetail": live.get("detail"),
            "declared": {"renderers": sorted(renderers),
                         "conclusions": sorted(conclusions),
                         # Echoed even when empty, so "declares no drawing calls"
                         # cannot be read as "draws nothing". Nothing here can tell
                         # the two apart, and leaving the key out would let an
                         # undeclared figure pass as an absent one.
                         "figures": sorted(drawings),
                         "dimensions": dimensions,
                         # Echoed even when empty, for the same reason `figures`
                         # is: "declares no components" must not read as "has one
                         # term". `componentsWithoutShare` is what makes the empty
                         # case cost something.
                         "components": components,
                         # Echoed even when empty, like `figures`: "declares no
                         # records" must not read as "writes none". A directory
                         # here is allowed and shows, so opting out of
                         # file-by-file accounting is a visible decision.
                         "records": declared_records,
                         "selections": fixed},
            "notebooks": [str(p.relative_to(target)) for p in notebooks],
            **findings}


def read_declaration(path: Path, name: str) -> dict | None:
    """A module-level literal, read without importing anything."""
    if not path.exists():
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return {"__error__": f"unparsable: {exc}"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return {"__error__": f"{name} is not a literal"}
    return None


#: The six top-level blocks the kit's scaffold writes (see
#: `assets/kit/src_benchmark/__init__.py`), and the value each one carries when
#: nobody has answered it yet: `""` for the lone scalar, `{}` for the five
#: containers. Named once here so "blank" has one definition every reader of
#: the resolver's `"declared"`/`"undeclared"` split shares, rather than each
#: caller inventing its own idea of empty.
BENCHMARK_BLOCKS = {
    "revision": "", "premises": {}, "arms": {},
    "search": {}, "report": {}, "distribution": {},
}


def _declaration_is_blank(contract: dict) -> bool:
    """True when every block is present at its empty value — a scaffold
    nobody has written into yet, not a declaration with content.

    Emptiness means something different at this level than it does inside a
    single block: `distribution_state` already treats `perEnvironment: []` as
    an answered, measured result, because a repository can legitimately
    measure that a field is empty. No repository ever means "I measured that
    the whole `distribution` block is empty" the same way — a blank *block* is
    unambiguously unanswered, never a result. So this checks truthiness at the
    block level on purpose, the mirror image of the field-level rule.
    """
    return not any(contract.get(block) for block in BENCHMARK_BLOCKS)


def resolve_benchmark_declaration(target: Path, name: str) -> dict:
    """The one place every reader gets `__benchmark__` from.

    Six call sites once read this contract each their own way. Two of them —
    `unreached_mathematics`'s caller and `verify`'s `benchmark` block —
    checked both `__init__.py` and `config.py`; the other four checked
    `__init__.py` alone. A declaration written in `config.py` only then
    passed for two readers and read as absent for the rest — a split
    verdict from a single declaration. This is the same shape
    `resolve_submission_ledger` closed for the ledger in `remote_cli.py`:
    there is no second, ad hoc way left to spell "the declaration" that a
    later call site could reinvent and drift from the other five.

    `status` is one of three: `"absent"` (no `src/<Package>_Benchmark/`
    directory at all — nothing could have declared anything), `"undeclared"`
    (the directory exists but neither `__init__.py` nor `config.py` binds
    `__benchmark__` to a readable literal — **or one does, and every block it
    binds is at its empty value**), or `"declared"` (found, parsed, and at
    least one block answered). `path` names which candidate file supplied it,
    relative to `target`, or `None` when nothing did. `detail` explains an
    `"undeclared"` result — the parse error from whichever file raised one, a
    generic note when neither names the literal at all, or a note that the
    literal parsed but named nothing — and is `None` for the other two
    statuses. `contract` is the declaration dict when `declared`, `{}`
    otherwise, so every caller that used to write `read_declaration(...) or
    {}` keeps receiving exactly the same shape: `search_state`,
    `distribution_state` and `report_contract` change nothing about what they
    are handed or what they return.

    **A blank literal is `"undeclared"`, not `"declared"`.** The kit's scaffold
    (`assets/kit/src_benchmark/__init__.py`) writes a `__benchmark__` that
    parses cleanly — six blocks, each at its empty value — the moment a
    target is materialized, before anybody has answered a single one. Treating
    a successful parse alone as `"declared"` would make that scaffold read as
    a finished declaration on the day it is created, which is the defect this
    resolver exists to close, reintroduced through the fix that writes the
    file. `_declaration_is_blank` is what keeps the two apart: parsing is
    necessary for `"declared"`, never sufficient.

    Searched in the same order the two already-correct sites used:
    `__init__.py` first, `config.py` second. The first candidate that binds
    the name to anything at all — a parsed dict or a caught parse error —
    wins; a candidate that does not bind the name is skipped, never treated
    as "declares nothing".
    """
    package = package_name(name)
    bench_root = target / "src" / f"{package}_Benchmark"
    if not bench_root.is_dir():
        return {"status": "absent", "path": None, "detail": None, "contract": {}}
    declaration = None
    found = None
    for candidate in ("__init__.py", "config.py"):
        path = bench_root / candidate
        result = read_declaration(path, BENCHMARK_DECLARATION)
        if result is not None:
            declaration, found = result, path
            break
    if declaration is None:
        return {
            "status": "undeclared", "path": None,
            "detail": f"no {BENCHMARK_DECLARATION} in __init__.py or config.py: "
                      "nothing says which sections its arms exercise",
            "contract": {},
        }
    if "__error__" in declaration:
        return {"status": "undeclared", "path": str(found.relative_to(target)),
                "detail": declaration["__error__"], "contract": {}}
    if _declaration_is_blank(declaration):
        return {
            "status": "undeclared", "path": str(found.relative_to(target)),
            "detail": f"{BENCHMARK_DECLARATION} parses, but every block is "
                      "still at its empty value: no arm, search, report or "
                      "distribution has been answered yet",
            "contract": {},
        }
    return {"status": "declared", "path": str(found.relative_to(target)),
            "detail": None, "contract": declaration}


def declared_dimension_names(target: Path, package: str) -> list[str] | None:
    """The shard-level dimension names a target declares, read without importing.

    `distribution_state` needs names and never directions, so this walks only
    `ast.Dict.keys` of a module-level `DIMENSIONS = {...}` — never
    `ast.literal_eval`, which raises the moment a value is a bare name like
    `HIGHER` rather than a literal (`config.py` writes exactly that: each
    dimension's direction is `HIGHER`/`LOWER`/`DESCRIPTIVE`, three module
    constants, not literals `ast.literal_eval` can evaluate). Reading the
    keys and never the values sidesteps that, and is also the honest read:
    only names are needed here.

    Searched in `config.py` first — where a materialized target keeps its
    own shard contract — then `benchmark.py`, where the kit's own template
    defines it; the first candidate that binds `DIMENSIONS` to a dict wins.

    `None` means the universe could not be determined: neither file binds
    the name, the assignment is unparsable, or `DIMENSIONS` is bound to
    something other than a dict literal. Every one of those collapses to the
    same `None` rather than `[]`, because `[]` reads as "this target
    declares zero dimensions" — trivially exhaustive, and a name bound to a
    call or a list is not a declaration of zero dimensions, it is a
    declaration this reading cannot make sense of.
    """
    bench_root = target / "src" / f"{package}_Benchmark"
    for candidate in ("config.py", "benchmark.py"):
        path = bench_root / candidate
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if not (isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "DIMENSIONS" for t in node.targets
            )):
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            return [key.value for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)]
    return None


def revision_sections(source: str | None) -> dict[str, str]:
    """Each numbered section of a revision, keyed by its number, hashed by content.

    Sections are what modules declare, so sections are the unit a drift report has to
    speak in. Anything before the first numbered heading belongs to no section and is
    ignored rather than attributed to one.
    """
    if not source:
        return {}
    sections: dict[str, list[str]] = {}
    current = None
    for line in source.splitlines():
        heading = re.match(r"^#{1,6}\s+(\d+)[.)]?\s", line)
        if heading:
            current = heading.group(1)
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {number: hashlib.sha256("\n".join(body).encode("utf-8")).hexdigest()
            for number, body in sections.items()}


def changed_sections(old: str | None, new: str | None) -> list[str]:
    """Which numbered sections differ between two revisions, added and removed too."""
    before, after = revision_sections(old), revision_sections(new)
    if not before or not after:
        return []
    numbers = set(before) | set(after)
    return sorted((n for n in numbers if before.get(n) != after.get(n)),
                  key=lambda n: (len(n), n))


def _scale_of(value: object) -> int | None:
    """How much of something a record names: a count, or the size of a list of them.

    The two knobs that separate a pilot from a campaign are of both kinds — a number
    of epochs and a list of seeds — and the comparison is the same either way.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return None


def source_digest(target: Path, package: str) -> str:
    """One hash over everything a report's claims depend on.

    Modification times cannot serve here: a clone rewrites all of them with the
    checkout time and the ordering is gone. Content can, and the skill already
    settles the same question this way for the revision behind an admissibility
    ruling — the ruling stores the revision's digest and `verify` recomputes it.
    """
    digest = hashlib.sha256()
    # All of `src/`, and nothing else. The boundary is the claim: a report depends
    # on the code the run executes, and on nothing else.
    #
    # Naming the packages one by one failed in both directions, and both were
    # observed rather than imagined. It left out prior work, which the benchmark
    # imports — moving what an arm computes left every notebook reporting
    # `executed` over stale numbers, and the separate session that goes and fixes
    # prior work and comes back is precisely the case that triggers it. And it
    # pulled in `tests/`, which no notebook imports: adding any test at all marked
    # every report in the repository stale and asked for the campaign to be re-run
    # to restamp a hash.
    #
    # The benchmark package stays in, now by living under `src/` rather than by
    # being named, and for the same reason as before: it renders the tables and
    # writes the conclusions. Leaving it out let a conclusion be corrected in code
    # while the record kept asserting the old one, with everything green.
    #
    # `package` no longer selects what is covered. It stays in the signature
    # because the two halves must be callable alike — see `report_digest.py` in
    # the kit, which the forge tests against this one over the same tree.
    root = target / "src"
    if root.is_dir():
        for file in sorted(root.rglob("*.py")):
            if "__pycache__" in file.parts:
                continue
            digest.update(str(file.relative_to(target)).encode("utf-8"))
            digest.update(file.read_bytes())
    return digest.hexdigest()


def notebook_execution(path: Path) -> dict:
    """Was the notebook run, or is the file merely present?

    Existence proves nothing: a template copied into place is indistinguishable
    from an executed report. The .ipynb records its own state — every code cell
    carries an `execution_count`, null until it runs, and an `outputs` list that
    keeps any error it raised. So the question is answerable without executing
    anything, and answering it is the difference between a report and a claim.
    """
    if not path.exists():
        return {"status": "missing", "codeCells": 0, "unexecuted": [], "errors": []}
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"status": "unreadable", "detail": str(exc)[:160],
                "codeCells": 0, "unexecuted": [], "errors": []}

    # `or []` rather than a default: nbformat writes an explicit null for an
    # absent list often enough, and a crash here would answer nothing at all
    # about a notebook whose only fault is being written that way.
    code_cells = [
        (index, cell) for index, cell in enumerate(notebook.get("cells") or [])
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
        and "".join(cell.get("source") or []).strip()
    ]
    unexecuted = [index for index, cell in code_cells if cell.get("execution_count") is None]
    errors = [
        f"cell {index}: {output.get('ename', 'error')}"
        for index, cell in code_cells
        for output in (cell.get("outputs") or [])
        if isinstance(output, dict) and output.get("output_type") == "error"
    ]

    # The digest the report printed when it ran, if it printed one.
    recorded = None
    for _, cell in code_cells:
        for output in (cell.get("outputs") or []):
            if not isinstance(output, dict):
                continue
            text = "".join(output.get("text") or [])
            if DIGEST_MARKER in text:
                recorded = text.split(DIGEST_MARKER, 1)[1].strip().split()[0]

    if not code_cells:
        status = "empty"
    elif errors:
        status = "errored"
    elif unexecuted:
        status = "stale"
    else:
        status = "executed"
    return {"status": status, "codeCells": len(code_cells),
            "unexecuted": unexecuted, "errors": errors, "recordedDigest": recorded}


def _module_scope_statements(tree: ast.Module):
    """Every statement this cell executes at its own scope, walking into
    control-flow blocks (`if`/`for`/`while`/`with`/`try`) but never into a
    function or class body — that opens a scope of its own and binds no name
    a later cell could read.
    """
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue  # its own name is bound above; its body opens a new scope
        for field in ("body", "orelse", "finalbody", "handlers"):
            stack.extend(getattr(node, field, None) or [])


def _assigned_names(target: ast.expr) -> list[str]:
    """Every plain name a target actually binds. `a[0] = x` and `a.b = x`
    rebind nothing a later cell can read by name — only a bare `Name`, and the
    names inside a tuple or list unpacking, do.
    """
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_assigned_names(
                element.value if isinstance(element, ast.Starred) else element))
        return names
    return []


def _cell_bindings(statement: ast.AST) -> list[tuple[str, ast.expr | None]]:
    """Every name one statement binds, paired with the expression whose
    reconstructibility decides whether the binding could be redone from the
    notebook's own text. `None` marks a binding with no expression to weigh —
    a definition, an import, an annotation with no value — which needs
    nothing executed and is never coupled.
    """
    if isinstance(statement, ast.Assign):
        value = statement.value
        return [(n, value) for target in statement.targets
                for n in _assigned_names(target)]
    if isinstance(statement, (ast.AnnAssign, ast.AugAssign)):
        return [(n, statement.value) for n in _assigned_names(statement.target)]
    if isinstance(statement, ast.For):
        return [(n, statement.iter) for n in _assigned_names(statement.target)]
    if isinstance(statement, ast.With):
        return [(n, item.context_expr) for item in statement.items
                if item.optional_vars is not None
                for n in _assigned_names(item.optional_vars)]
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [(statement.name, None)]
    if isinstance(statement, ast.Import):
        return [(a.asname or a.name.split(".")[0], None) for a in statement.names]
    if isinstance(statement, ast.ImportFrom):
        return [(a.asname or a.name, None) for a in statement.names]
    return []


def _resolved_call_name(call: ast.Call, aliases: dict[str, str]) -> str | None:
    """The call's `module.function` name, only when the receiver genuinely
    names an imported module — never an attribute of an arbitrary instance,
    which the vocabulary could not have named in the first place.
    """
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        origin = aliases.get(func.value.id)
        return f"{origin.rsplit('.', 1)[-1]}.{func.attr}" if origin else None
    if isinstance(func, ast.Name):
        return aliases.get(func.id)
    return None


def _is_literal(node: ast.expr) -> bool:
    """Whether this expression is its own reconstruction: nothing runs to
    produce it, the notebook's own text already is it."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _is_literal(node.operand)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and _is_literal(k) for k in node.keys) \
            and all(_is_literal(v) for v in node.values)
    return False


#: The read half of the exact shape `_is_reporting_cell` already recognizes
#: on the write side (`write_text`/`write_bytes`/`write`/`dump`) — a call to
#: one of these, taking no argument of its own, reads back bytes the run
#: already persisted rather than computing anything (T12b, design #744
#: section 8, correcting the false positive a real notebook exposed).
_RECORD_READ_METHODS = ("read_text", "read_bytes")


def _reads_persisted_record(node: ast.expr) -> bool:
    """A call to a canonical file-read method with no argument of its own.

    What the call is *applied to* — the path expression it reads from — is a
    separate node `ast.walk` visits and checks on its own; this only says
    that the read step itself adds no work, exactly as a zero-argument call
    already counts as reconstructible everywhere else in this guard.
    """
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _RECORD_READ_METHODS
            and not node.args and not node.keywords)


def _comprehension_locals(expr: ast.expr) -> frozenset[str]:
    """Names bound by a comprehension's own `for` target anywhere inside
    this expression — `line` in `[json.loads(line) for line in ...]`.

    A comprehension's loop variable is manufactured and consumed entirely
    within the same expression; reading it back is not a dependency on
    anything outside the binding being checked, so it never by itself makes
    that binding non-reconstructible.
    """
    names: set[str] = set()
    for node in ast.walk(expr):
        if isinstance(node, ast.comprehension):
            names.update(_target_names(node.target))
    return frozenset(names)


def _target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for elt in target.elts:
            names.update(_target_names(elt))
        return names
    return set()


def _reconstructible_arg(node: ast.expr, local_names: frozenset[str]) -> bool:
    """Whether one call argument costs nothing to redo: a literal, a read of
    already-persisted bytes, or a name manufactured by the same expression's
    own comprehension — never a name read from somewhere else."""
    return (_is_literal(node) or _reads_persisted_record(node)
            or (isinstance(node, ast.Name) and node.id in local_names))


def _reconstructible_call(call: ast.Call,
                           local_names: frozenset[str] = frozenset()) -> bool:
    """A call built entirely from literals, from a read of already-persisted
    bytes, or from its own comprehension's loop variable is a constructor or
    a record read, not a dependency: retyping the line reproduces it
    exactly, whatever it is named — the whitelist is by shape, never by a
    list of blessed names.
    """
    return all(_reconstructible_arg(a, local_names) for a in call.args) \
        and all(_reconstructible_arg(kw.value, local_names) for kw in call.keywords)


def _reconstructible(expr: ast.expr | None, aliases: dict[str, str],
                      vocabulary: set[str]) -> bool:
    """Whether this binding could be redone without executing anything the
    report itself does not already name — the false-positive guard that is
    the whole point of the check (design #744 section 8, step 5).

    A read of already-persisted bytes (T12b's addition) is exempted the same
    way a literal constructor already was: reading back what a run left on
    disk costs nothing to redo, whatever the call happens to be named —
    never by matching a path string against the report contract's `record`
    or `records` entries, which a path built from an imported config symbol
    (`config.RESULTS / "runs.jsonl"`) could never match without executing
    the target's own code, something this guard deliberately never does.
    """
    if expr is None:
        return True
    local_names = _comprehension_locals(expr)
    for node in ast.walk(expr):
        if isinstance(node, ast.Call) \
                and _resolved_call_name(node, aliases) not in vocabulary \
                and not _reconstructible_call(node, local_names):
            return False
    return True


def _is_reporting_cell(tree: ast.Module, aliases: dict[str, str], vocabulary: set[str],
                       record_name: str | None) -> bool:
    """Whether this cell calls a declared entry or writes the declared
    record — the two shapes design #744 section 8, step 2 names as
    reporting."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _resolved_call_name(node, aliases) in vocabulary:
            return True
    if not record_name:
        return False
    literal_present = any(
        isinstance(node, ast.Constant) and isinstance(node.value, str)
        and record_name in node.value
        for node in ast.walk(tree))
    return literal_present and any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("write_text", "write_bytes", "write", "dump")
        for node in ast.walk(tree))


def notebook_coupling(path: Path, contract: dict) -> dict:
    """A reporting cell reading a name a non-reporting cell could not have
    reconstructed without running a call the report itself never named.

    Static, and it never gates — nothing here changes an exit status, and no
    caller may make it do so. The five steps of design #744 section 8:

    1. The vocabulary is `report_contract()`'s own `renderers`, `conclusions`
       and `figures`, plus its `record` path.
    2. A cell is *reporting* iff it calls a declared entry — resolved through
       `_module_aliases`, so a call counts only when its receiver genuinely
       names an imported module — or writes the declared record.
    3. Every binding in the notebook is indexed by name, in cell order.
    4. Each reporting cell's free reads are resolved to their latest prior
       binding.
    5. A read is coupled iff that binding sits in a non-reporting cell whose
       expression contains a call outside the vocabulary that is not a
       literal constructor — the one shape that costs a re-run: a binding
       that cannot be rebuilt without executing something the report never
       declared.

       T12b widens what counts as reconstructible in step 5, without adding
       a name-based allow-list: a call to `read_text`/`read_bytes` with no
       argument of its own is exempted the same way a zero-argument call
       already was, and a comprehension's own loop variable no longer makes
       its enclosing call non-reconstructible, since that name is
       manufactured and consumed inside the same expression. Both are shape
       rules, not a list of blessed names — see `_reconstructible_arg` and
       `_comprehension_locals`. A call that merely *reconstructs an object*
       from already-read data (`Reduction(**summary["reduction"])`) is
       deliberately left uncovered: it is not itself a read, and widening
       the exemption to cover it would need to reason transitively about
       where its arguments came from, which this guard does not do.
    """
    vocabulary = (set(contract.get("renderers") or [])
                  | set(contract.get("conclusions") or [])
                  | set(contract.get("figures") or []))
    record_name = contract.get("record") or "latent.json"

    code_cells = [(index, cell) for index, cell in enumerate(_notebook_cells(path))
                  if isinstance(cell, dict) and cell.get("cell_type") == "code"]
    trees: dict[int, ast.Module] = {}
    for index, cell in code_cells:
        try:
            trees[index] = ast.parse(_source_of(cell))
        except (SyntaxError, ValueError):
            continue

    aliases: dict[str, str] = {}
    for tree in trees.values():
        aliases.update(_module_aliases(tree))

    reporting = {index: _is_reporting_cell(tree, aliases, vocabulary, record_name)
                 for index, tree in trees.items()}

    # name -> every (cell index, binding expression) that name was bound at,
    # in cell order — step 3.
    bindings: dict[str, list[tuple[int, ast.expr | None]]] = {}
    bound_in_cell: dict[int, set[str]] = {}
    for index, tree in trees.items():
        names_here: set[str] = set()
        for statement in _module_scope_statements(tree):
            for name, expr in _cell_bindings(statement):
                bindings.setdefault(name, []).append((index, expr))
                names_here.add(name)
        bound_in_cell[index] = names_here

    seen: set[tuple[str, int, int]] = set()
    couplings: list[dict] = []
    for index, tree in trees.items():
        if not reporting.get(index):
            continue
        own_names = bound_in_cell.get(index, set())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)):
                continue
            if node.id in own_names:
                continue  # bound within this same cell — step 4
            prior = [(i, expr) for i, expr in bindings.get(node.id, []) if i < index]
            if not prior:
                continue
            bound_in, expr = max(prior, key=lambda pair: pair[0])
            if reporting.get(bound_in):
                continue  # the false-positive guard only concerns a setup cell
            if _reconstructible(expr, aliases, vocabulary):
                continue
            key = (node.id, bound_in, index)
            if key in seen:
                continue
            seen.add(key)
            couplings.append({"name": node.id, "boundIn": bound_in, "readIn": index})

    return {"coupled": bool(couplings), "couplings": couplings}


def notebooks_state(target: Path, name: str, package: str) -> dict:
    """Every notebook of the product, and whether its evidence is still current.

    Reading one file with a reserved name leaves every other notebook unchecked:
    they could be unexecuted, or full of errors, and the validation would still
    report `ok`. And `executed` alone answers the wrong question — it says a cell
    ran once, not that it ran against this code.
    """
    root = target / name / "Notebooks"
    current = source_digest(target, package)
    contract = report_contract(target, name)
    reports = []
    for notebook in sorted(root.glob("*.ipynb")) if root.is_dir() else []:
        state = notebook_execution(notebook)
        recorded = state.get("recordedDigest")
        if state["status"] == "executed" and recorded and recorded != current:
            state["status"] = "stale-sources"
        state["notebook"] = str(notebook.relative_to(target))
        state["sourcesMatch"] = None if not recorded else recorded == current
        # Static, and it never gates: it names the same fact `verify` and
        # `probe` echo, nowhere close to `status` above.
        state["coupling"] = notebook_coupling(notebook, contract)
        reports.append(state)
    return {
        "sourcesDigest": current,
        "reports": reports,
        # An executed report that never stamped what it ran against cannot be told
        # apart from a relic, so it is named — and it counts. Naming it and then
        # reporting `ok` anyway said the quiet part twice: the skill knows the
        # difference cannot be told and passes it regardless, which is the same
        # failure as a green suite whose red was never reachable.
        "unstamped": [r["notebook"] for r in reports
                      if r["status"] == "executed" and r["sourcesMatch"] is None],
        "status": "ok" if reports and all(
            r["status"] == "executed" and r["sourcesMatch"] for r in reports) else "drift",
    }


def coupling_state(target: Path, name: str, package: str) -> dict:
    """Whether any notebook of this product has a reporting cell reading a
    name only reconstructible by re-running a non-reporting cell's call.

    Read-only, and it never gates a status this repository reports anywhere:
    see `notebook_coupling`.
    """
    reports = notebooks_state(target, name, package)["reports"]
    return {"coupled": any(r["coupling"]["coupled"] for r in reports),
            "notebooks": {r["notebook"]: r["coupling"] for r in reports}}


def test_function_names(tests_dir: Path) -> set[str]:
    names: set[str] = set()
    if not tests_dir.is_dir():
        return names
    for file in sorted(tests_dir.rglob("test_*.py")):
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
    return names


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_env(args: argparse.Namespace) -> dict:
    require_non_forge_interpreter()
    target = resolve_target(args.target)
    venv_dir = target / ".venv"
    created = False
    if not (venv_dir / "pyvenv.cfg").exists():
        if args.python:
            proc = subprocess.run(
                [args.python, "-m", "venv", str(venv_dir)], capture_output=True, text=True,
            )
            if proc.returncode != 0:
                raise Refused("VENV_FAILED", proc.stderr.strip() or "venv creation failed")
        else:
            venv.EnvBuilder(with_pip=True, clear=False).create(venv_dir)
        created = True
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    interpreter = venv_dir / bin_dir / ("python.exe" if os.name == "nt" else "python")
    pip = venv_dir / bin_dir / ("pip.exe" if os.name == "nt" else "pip")
    version = subprocess.run(
        [str(interpreter), "--version"], capture_output=True, text=True,
    ).stdout.strip()
    return {
        "command": "env",
        "target": str(target),
        "status": "created" if created else "present",
        "pythonVersion": version,
        "interpreter": str(interpreter),
        "pip": str(pip),
        "nextCommand": f"{pip} install -r {SKILL_ROOT / 'assets' / 'requirements-dev.txt'}",
        # Reported here because this is the command that runs first after a clone,
        # which is exactly when a repository full of placeholders looks complete.
        "lfs": lfs_state(target),
        "note": "Run every target command through this interpreter. Never the forge's.",
    }


def cmd_plan(args: argparse.Namespace) -> dict:
    target = resolve_target(args.target)
    name = validate_name(args.name)
    require_clean_worktree(target)
    return build_plan(target, name)


def cmd_apply(args: argparse.Namespace) -> dict:
    target = resolve_target(args.target)
    name = validate_name(args.name)
    require_clean_worktree(target)

    approved = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    if approved.get("target") != str(target) or approved.get("name") != name:
        raise Refused("PLAN_MISMATCH", "The approved plan was produced for a different target or name.")

    current = build_plan(target, name)
    # `referenceUpdates` belongs in this comparison as much as the moves do: a
    # commit that only edits a file's *contents* leaves renames, moves and
    # createDirs identical, so nothing would refuse — and `apply` would then
    # rewrite a file the user never saw in the list they approved.
    if any(current[key] != approved.get(key)
           for key in ("renames", "moves", "createDirs", "referenceUpdates")):
        raise Refused(
            "PLAN_STALE",
            "The repository changed since the plan was approved. Re-run `plan` and get approval again.",
        )
    if current["conflicts"]:
        raise Refused(
            "DESTINATION_CONFLICT",
            f"Destinations clash (existing file, or two sources onto one path): {current['conflicts']}. "
            "Applying would overwrite. Resolve with the user first.",
        )
    if current["unclassified"]:
        raise Refused(
            "UNCLASSIFIED_FILES",
            f"No rule covers: {current['unclassified']}. Ask where they belong; never guess.",
        )

    try:
        migrate(target, current)
    except Exception as failure:  # noqa: BLE001 - the repository must not stay half-migrated
        # The tree was verified clean before any mutation, so discarding the
        # partial work restores exactly the reviewed starting point.
        git(target, "reset", "-q", "--hard", check=False)
        git(target, "clean", "-qfd", check=False)
        raise Refused(
            "APPLY_ABORTED",
            f"{failure}. Nothing was committed and the working tree was restored "
            "to its pre-migration state; re-run `plan` to see the current situation.",
        ) from failure

    head = git(target, "rev-parse", "HEAD").strip()
    return {
        "command": "apply",
        "target": str(target),
        "name": name,
        "status": "applied",
        "commit": head,
        "renamed": current["renames"],
        "referencesRewritten": current["referenceUpdates"],
        "moved": len(current["moves"]),
        "createdDirs": current["createDirs"],
        "note": "Structure only. Revert this single commit to undo the whole migration.",
    }


def migrate(target: Path, current: dict) -> None:
    """Perform the whole migration. Any failure leaves it to the caller to undo."""
    # Renames first: createDirs and moves were computed against the post-rename tree.
    for rename in current["renames"]:
        git(target, "mv", rename["from"], rename["to"])
    # A rename that leaves notebooks and modules pointing at the old path is an
    # unfinished migration, so the references move in the same transaction.
    for update in current["referenceUpdates"]:
        # The plan lists pre-rename paths; the rename already happened above.
        rel = update["file"]
        for rename in current["renames"]:
            if rel == rename["from"] or rel.startswith(f"{rename['from']}/"):
                rel = rename["to"] + rel[len(rename["from"]):]
        file = target / rel
        pattern = reference_pattern(update["replace"], update["kind"], update["anchored"])
        file.write_text(
            pattern.sub(update["with"].replace("\\", r"\\"),
                        file.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
    # Before anything can be committed: the virtualenv this skill is about to
    # create must never enter the index.
    missing_ignores = ignore_gaps(target)
    if missing_ignores:
        ignore_file = target / ".gitignore"
        existing = ignore_file.read_text(encoding="utf-8") if ignore_file.exists() else ""
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        ignore_file.write_text(
            existing + prefix
            + "\n# Created by proposal-implementation: the target's own environment\n"
            + "\n".join(missing_ignores) + "\n",
            encoding="utf-8",
        )

    for rel in current["createDirs"]:
        directory = target / rel
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".gitkeep").touch()
    for move in current["moves"]:
        (target / move["to"]).parent.mkdir(parents=True, exist_ok=True)
        git(target, "mv", move["from"], move["to"])

    # git does not track directories, so a move leaves the old ones behind as
    # empty shells. They make a vanished path look like it still exists.
    emptied = sorted({str(Path(m["from"]).parent) for m in current["moves"]},
                     key=len, reverse=True)
    for rel in emptied:
        directory = target / rel
        while directory != target and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
            directory = directory.parent

    git(target, "add", "-A")
    git(target, "commit", "-m",
        f"chore(structure): normalize repository layout for {current['name']}")


CITATION_RE = re.compile(r"Ecs?\.?\s*\(?(\d+)\)?|Eq\.?\s*\(?(\d+)\)?|Ecuaciones?\s*\((\d+)\)")


def finding_impact(finding: dict, source: str) -> dict:
    """How far into the proposal a remedy would reach.

    Three measurements, all read from the document rather than judged: how many
    equations the remedy rewrites, how much notation it adds, and how often the
    rest of the text cites those equations. A change that touches one equation
    nobody else refers to, adding nothing, is local. Anything else carries
    implications the deliberation has to weigh with time, not inline.
    """
    equations = finding.get("remedy_equations", [])
    citations = 0
    for match in CITATION_RE.finditer(source):
        number = match.group(1) or match.group(2) or match.group(3)
        if number in equations:
            citations += 1
    introduces = len(finding.get("introduces", []))
    local = len(equations) <= 1 and introduces == 0 and citations <= 1
    return {"equations": len(equations), "introducesNotation": introduces,
            "citedElsewhere": citations, "class": "local" if local else "structural"}


def adoption_state(finding: dict, source: str) -> dict:
    """Has the revision taken this remedy in?

    Inference is textual, so it is built to fail toward `open`. The reliable
    signal is the disappearance of what the remedy replaces — a literal that is
    in the document today. If that text is gone but nothing recognizable took
    its place, the equation changed in a way this cannot read, and it says so
    instead of claiming adoption.
    """
    markers = finding.get("adoption") or {}
    absent, expect = markers.get("absent"), markers.get("expect") or []
    if not absent:
        return {"state": "unknown", "reason": "the finding declares no adoption marker"}
    if absent in source:
        return {"state": "open", "reason": "the text the remedy replaces is still there"}
    matched = [candidate for candidate in expect if candidate in source]
    if matched:
        return {"state": "adopted", "matched": matched}
    return {"state": "changed-unrecognized",
            "reason": "the replaced text is gone but no expected form was found; "
                      "confirm by hand before treating it as adopted"}


def declared_invariants(package_dir: Path) -> set[str]:
    """Every invariant the implementation's modules claim."""
    invariants: set[str] = set()
    if not package_dir.is_dir():
        return invariants
    for file in sorted(package_dir.rglob("*.py")):
        if file.name == "__init__.py":
            continue
        provenance = read_provenance(file)
        if provenance and "__error__" not in provenance:
            invariants.update(provenance.get("invariants", []))
    return invariants


def migration_state(target: Path, findings: list[dict], source: str | None,
                    package: str) -> dict:
    """What an adopted remedy still owes.

    Once the deliberation publishes a remedy, it stops being a proposal: it is
    the formulation. Leaving it in the remedy suite would keep reporting a
    defect the document no longer has, and would leave its claim outside the
    contract every other claim of the proposal is held to.

    So an adopted finding must have moved: its remedy test retired, the claim
    living in the invariant suite, and the invariant declared by the module that
    now implements it. The skill checks the move happened; writing it is the
    agent's work, as with any other code.
    """
    if source is None:
        return {"status": "unknown", "pending": [],
                "reason": "the revision could not be read"}

    tests = test_function_names(target / "tests")
    declared = declared_invariants(target / "src" / package)
    pending: list[str] = []

    for finding in findings:
        if adoption_state(finding, source).get("state") != "adopted":
            continue
        invariant = finding.get("becomes_invariant")
        if not invariant:
            pending.append(f"{finding['id']}: adopted, but declares no invariant to become")
            continue
        owed = []
        if f"test_remedy_{finding['id']}" in tests:
            owed.append("its remedy test is still in place")
        if f"test_{invariant}" not in tests:
            owed.append(f"test_{invariant} is missing from the invariant suite")
        if invariant not in declared:
            owed.append(f"no module declares {invariant} in __provenance__")
        if owed:
            pending.append(f"{finding['id']} -> {invariant}: " + "; ".join(owed))

    return {"status": "pending" if pending else "clear", "pending": pending}


def cmd_handoff(args: argparse.Namespace) -> dict:
    """Hand the open findings to the deliberation, sized by their reach.

    A local remedy travels as an agenda item to settle inline. A structural one
    does not: it goes back as a prompt for a session of its own, because a
    change that adds notation or rewrites an equation the rest of the document
    leans on deserves unhurried deliberation, not a decision taken while
    finishing something else.
    """
    target = resolve_target(args.target)
    source = revision_source(args.revision)
    if source is None:
        raise Refused("REVISION_UNREADABLE",
                      f"{args.revision!r} is not readable; nothing can be handed off.")

    inline, deferred, settled = [], [], []
    for finding in read_findings(target):
        impact = finding_impact(finding, source)
        adoption = adoption_state(finding, source)
        item = {"id": finding["id"], "kind": finding.get("kind"),
                "status": finding.get("status"), "rate": finding.get("rate"),
                "equations": finding.get("equations"),
                "remedyEquations": finding.get("remedy_equations"),
                "introduces": finding.get("introduces", []),
                "impact": impact, "adoption": adoption,
                "statement": finding.get("statement"), "remedy": finding.get("remedy")}
        if adoption["state"] == "adopted":
            settled.append(item)
        elif (impact["class"] == "local" and finding.get("remedy_block")
                and finding.get("remedy_equations")):
            # Local and written out: hand the deliberation a request it can act
            # on. The locus travels as the equation's own tag rather than as a
            # quote of the text being corrected — a bare fragment like a symbol
            # and its value occurs in prose as readily as in the equation, and
            # the resolver then lands on a neighbour. The tag is the document's
            # label for that equation, so it names the one the finding rewrites.
            #
            # The corrected text is not attached here. It has to be substituted
            # into whatever entry the resolver returns, which only the caller
            # knows; `compose` does that once the entry is in hand.
            item["deliberation"] = {
                "instruction": finding.get("remedy"),
                "selectedEntryId": f"\\tag{{{finding['remedy_equations'][0]}}}",
                "compose": {"command": "compose", "finding": finding["id"],
                            "entryTextFrom": "RESOLVE_TARGET.text"},
            }
            inline.append(item)
        else:
            if impact["class"] == "local" and not finding.get("remedy_equations"):
                # Local by measurement only because it names no equation at all.
                # There is no locus to resolve in the document, so there is
                # nothing the deliberation could be asked to replace.
                reason = ("Este hallazgo mide como local, pero no declara qué ecuación "
                          "reescribiría (`remedy_equations` está vacío), así que no hay "
                          "un locus que resolver en el documento.")
                item["deferredBecause"] = "remedy-locus-missing"
            elif impact["class"] == "local":
                # Local reach, but nobody wrote the corrected block. Deferring is
                # the honest outcome; saying "not local" here would be false.
                reason = ("Este cambio es de alcance local, pero el hallazgo no trae el "
                          "bloque corregido escrito (`remedy_block`). La redacción de la "
                          "matemática es la decisión, y no se infiere de la prosa.")
                item["deferredBecause"] = "remedy-text-missing"
            else:
                reason = (
                    f"Este cambio NO es local: reescribe {impact['equations']} ecuación(es), "
                    f"agrega {impact['introducesNotation']} símbolo(s) de notación y toca "
                    f"ecuaciones citadas {impact['citedElsewhere']} vez/veces en el resto del "
                    "documento. Merece una sesión propia.")
                item["deferredBecause"] = "structural-reach"
            item["prompt"] = (
                f"Deliberar sobre {args.revision}: {finding['id']}.\n\n"
                f"{reason}\n\n"
                f"DEFECTO ({finding.get('kind')}, {finding.get('status')} — "
                f"{finding.get('rate')}):\n{finding.get('statement')}\n\n"
                f"CORRECCIÓN PROPUESTA (validada, no adoptada):\n{finding.get('remedy')}\n\n"
                f"NOTACIÓN QUE AGREGARÍA: {', '.join(finding.get('introduces', [])) or 'ninguna'}\n"
                f"ECUACIONES A TOCAR: {', '.join(finding.get('remedy_equations', []))}")
            deferred.append(item)

    return {
        "command": "handoff",
        "target": str(target),
        "revision": args.revision,
        "status": "clear" if not inline and not deferred else "pending",
        "settleInline": inline,
        "deferToOwnSession": deferred,
        "alreadyAdopted": [i["id"] for i in settled],
        "note": "This skill proposes; proposal-deliberation decides and publishes.",
    }


DISPLAY_BLOCK_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)


def cmd_compose(args: argparse.Namespace) -> dict:
    """Rewrite one resolved entry so a finding's remedy takes its place.

    The deliberation replaces a whole entry, and an entry is usually more than
    the equation at issue. Composing the new text therefore means substituting
    inside it, never handing back the bare block: doing that would delete every
    neighbouring line the entry happens to carry.

    The equation's own `\\tag{n}` is the identity used to find it. That is the
    document's label for it, so the substitution lands on the equation the
    finding names rather than on whatever happens to look similar.
    """
    target = resolve_target(args.target)
    findings = {f["id"]: f for f in read_findings(target)}
    finding = findings.get(args.finding)
    if finding is None:
        raise Refused("NO_SUCH_FINDING",
                      f"{args.finding!r} is not among {sorted(findings)}.")

    block = finding.get("remedy_block")
    if not block:
        raise Refused("NO_REMEDY_BLOCK",
                      f"{args.finding} declares no remedy_block; its correction was "
                      "never written, so there is nothing to compose.")

    entry = sys.stdin.read() if args.entry_text == "-" else args.entry_text
    if not entry.strip():
        raise Refused("EMPTY_ENTRY", "The resolved entry text is empty.")

    tags = TAG_RE.findall(block)
    if len(set(tags)) != 1:
        raise Refused("AMBIGUOUS_REMEDY_TAG",
                      f"remedy_block must carry exactly one equation tag, found {tags}.")
    tag = tags[0]

    matches = [m for m in DISPLAY_BLOCK_RE.finditer(entry) if tag in TAG_RE.findall(m.group(0))]
    if len(matches) != 1:
        raise Refused("TAG_NOT_UNIQUE_IN_ENTRY",
                      f"equation ({tag}) appears in {len(matches)} display blocks of the "
                      "resolved entry; the locus is not the one the remedy corrects.")

    composed = entry[:matches[0].start()] + block + entry[matches[0].end():]
    if composed == entry:
        raise Refused("COMPOSITION_IS_A_NO_OP",
                      "The composed text equals the current text; nothing would change.")

    absent = (finding.get("adoption") or {}).get("absent")
    if absent and absent in composed:
        raise Refused("REMEDY_LEAVES_THE_DEFECT",
                      f"The composed text still carries {absent!r}, which the remedy "
                      "declares it removes.")

    return {"command": "compose", "finding": args.finding, "equation": tag,
            "replacementText": composed}


def cmd_admit(args: argparse.Namespace) -> dict:
    """Rule on each remedy's admissibility, before anything is measured.

    Efficacy is the second question. Measuring a remedy that cites an equation
    the revision lacks, or leans on notation it never defines, produces numbers
    that look like evidence for something that should never have reached the
    bench — and the rigour of the sweep ends up lending it credibility.

    Writes the verdict into the target so the remedy suite can refuse to run
    without it. Only the verdict travels: the proposal's text stays in the forge.
    """
    target = resolve_target(args.target)
    source = revision_source(args.revision)
    if source is None:
        raise Refused("REVISION_UNREADABLE",
                      f"{args.revision!r} is not readable under {FORGE_ROOT / 'proposals'}; "
                      "admissibility cannot be ruled on and no remedy may be measured.")

    tags = set(TAG_RE.findall(source))
    findings = read_findings(target)
    if not findings:
        raise Refused("NO_FINDINGS", "tests/findings.py declares no finding to rule on.")

    verdicts = {}
    for finding in findings:
        reasons = []
        for field in ("equations", "remedy_equations"):
            missing = [e for e in finding.get(field, []) if e not in tags]
            if missing:
                reasons.append(f"{field} cites equations absent from the revision: {missing}")
        marker = (finding.get("adoption") or {}).get("absent")
        if not marker:
            reasons.append("declares no adoption marker, so adoption could never be read back")
        elif marker not in source:
            # A marker that does not describe the document today is meaningless:
            # its absence later would be indistinguishable from adoption.
            reasons.append("its adoption marker is not present in the revision, so the "
                           "finding does not describe this document")
        if not finding.get("uses"):
            reasons.append("declares no notation, so compatibility cannot be ruled on")
        else:
            absent = [s for s in finding["uses"] if s not in source]
            if absent:
                reasons.append(f"relies on notation the revision does not define: {absent}")
        adoption = adoption_state(finding, source)
        verdicts[finding["id"]] = {
            "admissible": not reasons,
            "reasons": reasons,
            # A remedy already taken into the revision no longer introduces
            # anything: the deliberation settled that when it published.
            "introduces": [] if adoption["state"] == "adopted" else finding.get("introduces", []),
            "adoption": adoption,
            "impact": finding_impact(finding, source),
        }

    record = {
        "revision": args.revision,
        "revisionSha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "findings": verdicts,
    }
    path = target / "tests" / "admissibility.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    inadmissible = sorted(i for i, v in verdicts.items() if not v["admissible"])
    return {
        "command": "admit",
        "target": str(target),
        "revision": args.revision,
        "status": "inadmissible" if inadmissible else "admitted",
        "admitted": sorted(i for i, v in verdicts.items() if v["admissible"]),
        "inadmissible": {i: verdicts[i]["reasons"] for i in inadmissible},
        "introducesNotation": {i: v["introduces"] for i, v in verdicts.items() if v["introduces"]},
        "record": str(path.relative_to(target)),
        "note": "Only admitted remedies may be measured. Efficacy comes after this.",
    }


def admissibility_record(target: Path, revision: str | None) -> dict:
    """The verdict on file, and whether it still applies to the bound revision."""
    path = target / "tests" / "admissibility.json"
    if not path.exists():
        return {"status": "missing", "detail": "no ruling; no remedy may be measured"}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"status": "unreadable", "detail": "the ruling cannot be parsed"}
    source = revision_source(revision)
    if source is not None:
        current = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if record.get("revisionSha256") != current:
            return {"status": "stale",
                    "detail": f"ruled against {record.get('revision')}, "
                              f"whose bytes no longer match"}
    return {"status": "present", "revision": record.get("revision"),
            "findings": record.get("findings", {})}


def _load_remote_execution_ledger():
    """Path-import the forge's ledger module, and only that module.

    Reusing an already-loaded copy under a fixed `sys.modules` key matters for
    the same reason it matters in `remote-execution/scripts/packer.py`'s own
    loader: `LedgerState` is a dataclass, and two separately exec'd copies of
    the same source file produce two distinct classes with the same name — an
    `isinstance` check made against one copy would silently fail against an
    instance the other built, even though the source is byte-identical.
    """
    module_name = "remote_execution_ledger"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, REMOTE_EXECUTION_LEDGER_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def remote_execution_state(target: Path, name: str, package: str) -> dict:
    """What went out to a remote worker, what came back, and what changed since.

    Reads exactly one module of the forge's `remote-execution` skill —
    `ledger.py` — and never `adapter.py` or anything under `adapters/`, which
    is the one place that skill lets a service be named. Reimplementing the
    fold in here instead was rejected for the reason a second copy of any
    rule is rejected everywhere else in this file: two definitions of
    `fromStaleSubmission` is the shim-drift risk, and the whole point of the
    classification is that exactly one thing decides it.

    Absent, not zero, when there is nothing to read: the skill may not be
    installed, or this target may simply never have submitted anything —
    every target that predates this check is in exactly that second state,
    so `verify` stays clean on all of them without anyone touching a target
    at all.

    Reports and never resolves. `drift` names a submission the source has
    moved past — in flight, or already returned and quarantined rather than
    merged. `unreliable` names a log this check could not fully read. Neither
    case cancels a job, adopts a result, or repairs a line; that is
    `remote_cli reconcile`'s territory, run by a human, never by `verify`.

    `workers` is a count, never a name. A worker id is a service account's
    username, and printing one here would falsify SKILL.md's own surviving
    sentence — "No service is named here, and none should be" — the moment
    somebody ran this command.
    """
    if not REMOTE_EXECUTION_LEDGER_SCRIPT.is_file():
        return {"status": "absent"}

    ledger_path = target / name / ".remote-execution" / "ledger.jsonl"
    if not ledger_path.is_file():
        return {"status": "absent"}

    ledger = _load_remote_execution_ledger()
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    # A callable, not a computed value: `fold()` only pays for `source_digest()`
    # once per call, and never at all when the log holds nothing pending to
    # judge against it.
    state = ledger.fold(lines, live_digest=lambda: source_digest(target, package))

    pending = sum(1 for e in state.entrypoints.values() if e.state == "pending")
    returned = sum(1 for e in state.entrypoints.values() if e.state == "returned")
    errored = sum(1 for e in state.entrypoints.values() if e.state == "errored")
    # A quarantined result counted once per arrival, not once per entrypoint:
    # `fromStaleSubmission` below already collapses to one entry per
    # entrypoint, and collapsing here too would hide a second stale result
    # landing for the same entrypoint.
    quarantined = sum(1 for v in state.verdicts.values() if v == "fromStaleSubmission")
    workers = len({event.get("worker") for event in state.by_id.values()})

    if state.unreadable_lines > 0:
        status = "unreliable"
    elif state.stale_in_flight or state.from_stale_submission:
        status = "drift"
    elif pending:
        status = "pending"
    else:
        status = "ok"

    return {
        "status": status,
        "ledger": str(ledger_path.relative_to(target)),
        "sent": len(state.by_id),
        "pending": pending,
        "returned": returned,
        "errored": errored,
        "staleInFlight": list(state.stale_in_flight),
        "fromStaleSubmission": list(state.from_stale_submission),
        "quarantined": quarantined,
        "unreadableLines": state.unreadable_lines,
        "workers": workers,
    }


def _load_remote_execution_cli():
    """Path-import `remote_cli.py`, reusing an already-loaded copy the same
    way `_load_remote_execution_ledger()` does above, and for the same
    correctness reason: `remote_cli.py` itself re-exports `JOBFOLDER` as one
    of its own module attributes, and a second, separately exec'd copy
    would hand back a `JobFolder`/`JobFolderError` pair this module's own
    `except` clauses could never `isinstance`-match against.
    """
    module_name = "remote_execution_cli"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, REMOTE_EXECUTION_CLI_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _discovered_job_folders(target: Path, rcli) -> list[Path]:
    """Every `<target>/tools/<service>/<job-name>/` directory that holds a
    `run-config.json` — the job-folder shape `remote_cli.guard_entrypoint()`
    admits (design #744 section 5). Sorted for determinism. `<service>` is
    read only to walk the tree; `remote_execution_jobs_state()` below never
    carries it past a count.
    """
    tools_dir = target / rcli.TOOLS_DIRNAME
    if not tools_dir.is_dir():
        return []
    found: list[Path] = []
    for service_dir in sorted(p for p in tools_dir.iterdir() if p.is_dir()):
        for job_dir in sorted(p for p in service_dir.iterdir() if p.is_dir()):
            if (job_dir / rcli.RUN_CONFIG_FILENAME).is_file():
                found.append(job_dir)
    return found


def remote_execution_jobs_state(target: Path) -> dict:
    """`probe`'s own job-folder fact (design #744 section 9): what job
    folders exist on disk right now, reported alongside
    `remote_execution_state()`'s ledger-derived fields under the same
    `remoteExecution` key in `cmd_probe`. Reports and never resolves —
    exactly `remote_execution_state()`'s own discipline, extended to a
    second source of fact. States nothing about whether anything was ever
    submitted; a job folder can exist and have never been run at all.

    `<service>` is read only to walk `<target>/tools/`, and is dropped to a
    count (`services`) before this function ever returns — the same rule
    `remote_execution_state()` already applies to `workers`.

    Staleness is read through `remote_cli.JOBFOLDER.read()` alone — the
    single reader design #744 section 4 mandates — never recomputed here.

    **The `None` conflation, made visible rather than passed through.**
    `remote_cli._job_folder_staleness()` returns `None` for two different
    situations: an entrypoint with no job folder at all (correct — nothing
    to report), and a `run-config.json` `JOBFOLDER.read()` cannot make
    sense of (a real defect, silently tolerated one layer up so an
    already-lenient command does not become stricter — see that
    function's own docstring). That tolerance is right for `submit`/
    `status`/`fetch`/`reconcile`, each of which is routing an ENTRYPOINT
    that may or may not sit beside a job folder at all.

    This function is never in that situation: every directory it hands to
    `JOBFOLDER.read()` was already found BECAUSE it holds a
    `run-config.json` (`_discovered_job_folders()` above only walks
    directories where that file exists). So a `JobFolderError` here can
    only mean the second case — an unreadable or invalid config — never
    the first, and folding it into `None`/omission the way the CLI-layer
    helper does would be wrong here specifically: `probe`'s output is read
    by a human, and a blank cell reads as "nothing wrong" when the truth
    is "this job's configuration is broken and staleness could not even be
    attempted." So this job is reported anyway, with
    `staleness: {"status": "unreadable", "reason": <str(exc)>}` — a
    verdict distinct from the git-related `"unknown"` `_staleness_for()`
    already reports, because the two causes call for different fixes: one
    means "check the repository's git history," the other means "check
    this job's own `run-config.json`."

    **`smokeReady`, and why it routes through `remote_cli.cmd_readiness()`
    rather than reimplementing it.** T11's `readiness()` binds a smoke
    verdict to `(job, commit, worker)` with no clock — the exact question
    this fact wants answered, except `probe` has no caller-supplied worker
    to ask about (it is read-only and takes no `--worker`). Reimplementing
    just the `result == "pass" and commit == pinned` half here would be
    the second, drift-prone copy of a rule `readiness()` already owns.
    Instead, the worker is derived from the job's OWN latest smoke record
    (via `remote_cli.latest_smoke_event()`, the same lookup
    `cmd_readiness()` itself uses) and handed back to
    `cmd_readiness(job_dir, worker=<that worker>)` — the worker-equality
    clause becomes tautological, but the pass/commit comparison genuinely
    runs through T11's own function, not a second copy of it. The worker
    itself is never reported: `smokeReady` is keyed by job name (already
    exposed via `jobs` above), never by worker.
    """
    if not REMOTE_EXECUTION_CLI_SCRIPT.is_file():
        return {"jobs": [], "services": 0, "smokeReady": {}}

    target = Path(target).resolve()
    rcli = _load_remote_execution_cli()
    job_dirs = _discovered_job_folders(target, rcli)
    services = len({job_dir.parent.name for job_dir in job_dirs})

    jobs: list[dict] = []
    smoke_ready: dict[str, bool] = {}
    for job_dir in job_dirs:
        try:
            job_folder = rcli.JOBFOLDER.read(job_dir)
        except rcli.JOBFOLDER.JobFolderError as exc:
            jobs.append({
                "job": job_dir.name,
                "product": None,
                "staleness": {"status": "unreadable", "reason": str(exc)},
            })
            continue

        run_config = job_folder.run_config
        job_name = run_config.get("jobName", job_dir.name)
        product = run_config.get("product")
        jobs.append({
            "job": job_name,
            "product": product,
            "staleness": dict(job_folder.staleness),
        })

        if not isinstance(product, str) or not product:
            smoke_ready[job_name] = False
            continue
        smoke_ledger_path = target / product / rcli.LEDGER_DIRNAME / rcli.SMOKE_LEDGER_FILENAME
        latest = rcli.latest_smoke_event(smoke_ledger_path, job_name)
        worker = latest.get("worker") if latest else None
        if not isinstance(worker, str) or not worker:
            smoke_ready[job_name] = False
            continue
        readiness = rcli.cmd_readiness(job_dir=job_dir, worker=worker)
        smoke_ready[job_name] = bool(readiness["ready"])

    return {"jobs": jobs, "services": services, "smokeReady": smoke_ready}


def cmd_verify(args: argparse.Namespace) -> dict:
    target = resolve_target(args.target)
    name = validate_name(args.name)

    # From the disk, not from the index: a misplaced module is worth reporting before
    # it enters the history, not after. See `present_files`.
    paths = present_files(target)
    with_data = (target / name / "Data").is_dir()
    missing_dirs = [d for d in expected_dirs(name, with_data) if not (target / d).is_dir()]
    # The same ignore list `classify` uses. Without it a tracked virtualenv
    # reports thousands of stray modules and buries the one that matters.
    stray = [
        p for p in paths
        if p.endswith(".py") and not p.startswith(SOURCE_ROOTS)
        and Path(p).parts[0] not in IGNORED_DIRS and Path(p).name != "setup.py"
    ]
    # Static check, nothing is executed: does anything still address a product
    # folder that no longer exists?
    stale_refs = scan_stale_references(target, name, paths)
    structure_ok = (not missing_dirs and not stray and not stale_refs
                    and not scaffold_gaps(target, name))

    package = target / "src" / package_name(name)
    modules: list[dict] = []
    missing_provenance: list[str] = []
    declared_invariants: set[str] = set()
    for file in sorted(package.rglob("*.py")) if package.is_dir() else []:
        rel = str(file.relative_to(target))
        if file.name == "__init__.py":
            continue
        prov = read_provenance(file)
        if prov is None or "__error__" in prov:
            missing_provenance.append(rel)
            continue
        declared_invariants.update(prov.get("invariants", []))
        modules.append({
            "module": rel,
            "revision": prov.get("revision"),
            "sections": prov.get("sections", []),
            "equations": prov.get("equations", []),
            "invariants": prov.get("invariants", []),
        })

    # Which revision everything below is measured against. An explicit `--revision`
    # is obeyed as given — a caller pinning one is answering this question, not
    # asking it. Otherwise it is DISCOVERED, and only then does the field named
    # `latestRevision` mean what it says. The family is derived from a name that
    # arrived as data: the bench's own declared revision first, since that is the
    # binding the check exists to age, and a module's provenance when no bench has
    # declared one yet. Both are names this code was handed, never ones it knows.
    resolved = resolve_benchmark_declaration(target, name)
    declared_revision = (resolved["contract"] or {}).get("revision") \
        if resolved["status"] == "declared" else None
    family = declared_revision or next(
        (m["revision"] for m in modules if m.get("revision")), None)
    discovered = latest_revision(family)
    revision = args.revision or discovered

    for module in modules:
        module["stale"] = bool(revision) and module["revision"] != revision

    tests = test_function_names(target / "tests")
    untested = sorted(i for i in declared_invariants if f"test_{i}" not in tests)
    stale = [m["module"] for m in modules if m["stale"]]

    # What actually changed, rather than "the revision string is different".
    # Marking every module stale because one equation moved tells the reader there is
    # work to do and nothing about where, which is the part they have to find anyway.
    target_source = revision_source(revision) if revision else None
    drift_detail = []
    for module in modules:
        if not module["stale"]:
            continue
        moved = changed_sections(revision_source(module["revision"]), target_source)
        touched = sorted(set(module["sections"]) & set(moved), key=lambda n: (len(n), n))
        drift_detail.append({
            "module": module["module"],
            "declaredRevision": module["revision"],
            "changedSections": moved,
            # A module whose own sections are untouched is bound to an older revision
            # and implements nothing that moved: re-binding it is bookkeeping, not
            # mathematics, and saying so is what keeps the two apart.
            "touchedSections": touched,
            "reason": "sections it declares have changed" if touched
                      else "bound to an older revision, but none of its sections moved",
        })

    # The bench declares no provenance — it implements no equation — but it does
    # declare which revision it was built against and which sections each arm
    # exercises, so a changed section can name the arms it reaches.
    bench_package = f"{package_name(name)}_Benchmark"
    unreached: list[dict] = []
    if resolved["status"] == "absent":
        benchmark = {"status": "absent", "package": f"src/{bench_package}"}
    elif resolved["status"] == "undeclared":
        benchmark = {"status": "undeclared", "package": f"src/{bench_package}",
                     "detail": resolved["detail"]}
    else:
        declaration = resolved["contract"]
        built_against = declaration.get("revision")
        moved = changed_sections(revision_source(built_against), target_source)
        arms = declaration.get("arms") or {}
        reached = {arm: sorted(set(spec.get("sections", [])) & set(moved),
                               key=lambda n: (len(n), n))
                   for arm, spec in arms.items()
                   if isinstance(spec, dict) and set(spec.get("sections", [])) & set(moved)}
        unreached = unreached_mathematics(
            modules, declaration,
            benchmark_reach(target, package_name(name), bench_package))
        stale_revision = bool(revision) and built_against != revision
        benchmark = {
            # An arm that never calls what it claims outranks an arm built against an
            # older revision: the first says the experiment is not measuring what it
            # reports, the second only that it was measured earlier. Both stay visible.
            "status": "unfaithful" if unreached else "stale" if stale_revision else "ok",
            "package": f"src/{bench_package}",
            "revision": built_against,
            "staleRevision": stale_revision,
            "changedSections": moved,
            "armsReached": reached or None,
            "unreachedModules": unreached,
        }

    # The audit bridge: a defect in the mathematics is only reported when its
    # evidence AND the validation of its proposed correction both exist.
    findings = read_findings(target)
    without_evidence = sorted(f["id"] for f in findings if f"test_finding_{f['id']}" not in tests)
    without_remedy = sorted(f["id"] for f in findings if not f.get("remedy"))
    unvalidated = sorted(f["id"] for f in findings if f"test_remedy_{f['id']}" not in tests)
    # The resolved revision, not the argument: these three ask what the proposal
    # says as it stands now, and answering them against a revision nobody named
    # left them permanently unknown on every ordinary invocation.
    compatibility = remedy_compatibility(findings, revision)
    ruling = admissibility_record(target, revision)
    uncontrolled = remedies_without_control(target / "tests", package_name(name))
    source = revision_source(revision)
    migration = migration_state(target, findings, source, package_name(name))
    unruled = sorted(f["id"] for f in findings
                     if f["id"] not in ruling.get("findings", {})) if findings else []
    if not findings:
        audit_status = "none"
    elif without_evidence or without_remedy or unvalidated:
        audit_status = "incomplete"
    elif ruling["status"] != "present" or unruled or uncontrolled:
        audit_status = "incomplete"
    elif migration["status"] == "pending":
        # An adopted remedy still sitting in the remedy suite would keep
        # reporting a defect the revision no longer has.
        audit_status = "incomplete"
    elif compatibility["status"] in {"incompatible", "unknown"}:
        audit_status = "incomplete"
    elif compatibility["status"] == "needs-deliberation":
        audit_status = "needs-deliberation"
    else:
        audit_status = "ok"

    smoke_present = (target / "tests" / "test_smoke.py").exists()
    report = report_state(target, name, package_name(name))
    notebooks = notebooks_state(target, name, package_name(name))
    trivial = trivial_assertions(target / "tests")

    # The shard contract, not the report: the report also renders
    # latent-analysis quantities (e.g. `geometry.ratio`, `domainSeparability`)
    # that never sit on a shard, and demanding a partition classification for
    # those is a category error, not a missing declaration. `None` here means
    # the universe itself could not be determined, and that is never read as
    # "declares zero dimensions" — see `declared_dimension_names`.
    dimension_names = declared_dimension_names(target, package_name(name))
    distribution = distribution_state(
        resolved["contract"],
        dimension_names if dimension_names is not None else {},
        declaration_status=resolved["status"])
    distribution["dimensionSource"] = (
        sorted(dimension_names) if dimension_names is not None else None)
    if dimension_names is None and distribution["status"] not in (
            "none", "absent", "undeclared"):
        distribution["note"] = (
            "no DIMENSIONS dict literal found in config.py or benchmark.py "
            f"under src/{package_name(name)}_Benchmark; the partition could "
            "not be checked for exhaustiveness, so an empty unpartitioned "
            "here is not evidence the split is complete")

    # `unknown` now means the newest could not be established at all — no argument
    # and nothing on disk to discover from. It used to mean only that nobody typed
    # one, which is the ordinary case and left the check silent by default.
    if not revision:
        fidelity_status = "unknown"
    elif stale or missing_provenance or untested or unreached:
        # A bench built against an older revision does not drift fidelity — that is a
        # state, and the flow surfaces it as one. An arm claiming mathematics it never
        # calls is a defect, and a defect that stays inside `benchmark` while the
        # headline reads `ok` is the silence this check exists to break.
        fidelity_status = "drift"
    else:
        fidelity_status = "ok"

    return {
        "command": "verify",
        "target": str(target),
        "name": name,
        "structure": {
            "status": "ok" if structure_ok else "drift",
            "missingDirs": missing_dirs,
            "strayModules": stray,
            "staleReferences": stale_refs,
            "scaffoldGaps": scaffold_gaps(target, name),
        },
        "priorWork": prior_work_state(target, package_name(name)),
        "agreements": agreements_state(target, name),
        # Reported whatever it says, and it drifts nothing: a historical mention
        # of an older revision is legitimate, and a configuration key quoted like
        # a symbol is not a defect. These are facts for a reader, not verdicts.
        "prose": prose_state(target, revision),
        "search": search_state(
            resolved["contract"],
            list((report.get("declared") or {}).get("records") or []),
            target / name, declaration_status=resolved["status"]),
        "distribution": distribution,
        "remoteExecution": remote_execution_state(target, name, package_name(name)),
        # A static fact, reported and never gating: see `notebook_coupling`.
        "coupling": coupling_state(target, name, package_name(name)),
        "fidelity": {
            "status": fidelity_status,
            "latestRevision": revision,
            # How that name was arrived at, so a reader never has to guess whether
            # a green fidelity was checked against the newest revision or against
            # whichever one the caller happened to name.
            "revisionSource": "argument" if args.revision else (
                "discovered" if discovered else "none"),
            "staleModules": stale,
            "drift": drift_detail,
            "benchmark": benchmark,
            "missingProvenance": missing_provenance,
            "invariantsWithoutTest": untested,
            "modules": modules,
        },
        "lfs": lfs_state(target),
        # Whether the document a human reads obeys the rules the numbers already do.
        # Every other section here checks that the run was sound; a run can be sound
        # and its report still assert the opposite, which is worse than no report.
        "report": report,
        "audit": {
            "status": audit_status,
            "findings": [
                {"id": f["id"], "kind": f.get("kind"), "status": f.get("status"),
                 "rate": f.get("rate"), "equations": f.get("equations"),
                 "remedyEquations": f.get("remedy_equations")}
                for f in findings
            ],
            "findingsWithoutEvidence": without_evidence,
            "findingsWithoutRemedy": without_remedy,
            # A local remedy nobody wrote out is not a defect in the audit, but
            # it is the difference between a change that settles inline and one
            # that costs a session. Reported so it is a decision, not a silence.
            "localRemediesNotWritten": [
                f["id"] for f in findings
                if finding_impact(f, source or "")["class"] == "local"
                and not f.get("remedy_block")
                and adoption_state(f, source or "")["state"] != "adopted"
            ],
            "remediesWithoutValidation": unvalidated,
            "remediesWithoutControl": uncontrolled,
            "migration": migration,
            "admissibility": {"status": ruling["status"],
                              "detail": ruling.get("detail"),
                              "unruled": unruled},
            "compatibility": compatibility,
        },
        "validation": {
            # Every notebook of the product, not one with a reserved name, and each
            # one measured against the code it claims to report on.
            "status": ("ok" if smoke_present and notebooks["status"] == "ok"
                       and not trivial else "incomplete"),
            "smokeTest": smoke_present,
            "invariantTests": sorted(t for t in tests if t.startswith("test_")),
            "trivialAssertions": trivial,
            "notebook": next((r for r in notebooks["reports"]
                              if r["notebook"].endswith("verification.ipynb")),
                             {"status": "missing", "codeCells": 0,
                              "unexecuted": [], "errors": []}),
            "notebooks": notebooks,
        },
    }


COMMANDS = {"env": cmd_env, "name": cmd_name, "plan": cmd_plan, "apply": cmd_apply,
            "admit": cmd_admit, "handoff": cmd_handoff, "compose": cmd_compose,
            "probe": cmd_probe,
            "verify": cmd_verify}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="implementation_cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in COMMANDS:
        p = sub.add_parser(name)
        if name == "name":
            # Normalizing a name needs no repository: it runs before one exists.
            p.add_argument("--name", required=True, help="the name as the user typed it")
            continue
        p.add_argument("--target", required=True, help="cloned repository under implementations/")
        if name == "env":
            p.add_argument("--python", default=None,
                           help="interpreter to build the venv from (default: this one). "
                                "The layout templates assume 3.10+")
        elif name == "compose":
            # Composition reads the findings and the entry, nothing layout-shaped.
            p.add_argument("--finding", required=True, help="id of the finding to compose")
            p.add_argument("--entry-text", required=True,
                           help="the resolved entry's current text, or - to read stdin")
        else:
            p.add_argument("--name", required=True, help="package name chosen by the user")
        if name == "apply":
            p.add_argument("--plan", required=True, help="path to the approved plan JSON")
        if name in {"verify", "admit", "handoff", "probe"}:
            p.add_argument("--revision", default=None,
                           help="pin the revision to check against; "
                                "omit it and verify discovers the newest of "
                                "the family the bench declares")

    args = parser.parse_args(argv)
    try:
        result = COMMANDS[args.command](args)
    except Refused as refused:
        json.dump({"status": "refused", "code": refused.code, "detail": refused.detail},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
