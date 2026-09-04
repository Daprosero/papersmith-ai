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
import shlex
import subprocess
import sys
import time
import venv
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]

# The shared implementation core.
#
# Everything under `_core/implementation/` is what every implementation skill
# needs and none of them owns: the guards that refuse a target outside the
# workspace or a dirty worktree, the git and LFS readers, name normalisation,
# and the reference remapping a migration depends on. None of it knows what is
# being implemented, which is why a sibling skill can import it rather than copy
# it. What IS specific -- product directories, source roots, what survives at the
# root -- stays below in this file and is handed to the core where it is needed.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_core" / "implementation"))
from impl_layout import FORGE_ROOT, WORKSPACE, IGNORED_DIRS, LFS_POINTER_PREFIX, TEXT_EXT  # noqa: E402
from impl_refusals import NameRefused, Refused  # noqa: E402
from impl_gitops import git, lfs_state, present_files, read_text, text_files, tracked_files  # noqa: E402
from impl_guards import require_clean_worktree, require_non_forge_interpreter, resolve_target  # noqa: E402
from impl_naming import normalize_name, package_name, validate_name  # noqa: E402
from impl_references import (is_nesting, prefix_mappings, reference_pattern,  # noqa: E402
                             scan_reference_updates, scan_stale_references)
import impl_availability  # noqa: E402
import impl_execution_strategy  # noqa: E402
import impl_position  # noqa: E402
import impl_steps  # noqa: E402

# The three files this module is allowed to path-import from the forge's
# `remote-execution` skill. `remote_execution_state()` reads `ledger.py`
# alone; `cmd_verify`'s `--shards` branch reads `shard_io.py` alone, which is
# stdlib-only, defines no class and names no service; and
# `remote_execution_jobs_state()` (design #744 section 9) reads
# `remote_cli.py`, which itself loads `jobfolder.py`, `adapter.py`,
# `packer.py`, `credentials.py` and `shard_io.py` — every one of the eight
# modules the skill's own `*_module_names_no_service` guard family already
# holds to naming no service. The one module under `adapters/` that skill
# lets name a service is never imported by `remote_cli.py` itself at module
# scope — it is reached only by the CLI's own lazy, per-command dispatch,
# which neither function below ever calls — so this widening still never
# puts a service name within this file's reach. That module is named here by
# what it is rather than by its filename: this file is scanned by the forge's
# own vocabulary guard, and a guard whose surface is prose cannot carry a
# hole for prose. `remote-execution`'s `*_module_names_no_service` family is
# where that audit fact is pinned.
REMOTE_EXECUTION_LEDGER_SCRIPT = (
    FORGE_ROOT / ".claude" / "skills" / "remote-execution" / "scripts" / "ledger.py"
)
REMOTE_EXECUTION_CLI_SCRIPT = (
    FORGE_ROOT / ".claude" / "skills" / "remote-execution" / "scripts" / "remote_cli.py"
)
REMOTE_EXECUTION_SHARD_IO_SCRIPT = (
    FORGE_ROOT / ".claude" / "skills" / "remote-execution" / "scripts" / "shard_io.py"
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



# --------------------------------------------------------------------------
# git helpers
# --------------------------------------------------------------------------




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
#:
#: The trailing group is optional and scoped strictly to the shape `settle`
#: writes (design D4, spec Group 3): a backticked `` `test_<id>` `` at the
#: very end of the line, mirroring `impl_position.WITNESS_RE`'s own
#: end-anchored convention one module over. A bare line, with or without a
#: mark, parses byte-for-byte as it always has -- the group only ever
#: matches when the line's own tail happens to have that exact shape.
#: Measured, not assumed (design D4's own open question): a scan of the
#: reference target's `AGREED.md` for a pre-existing line already ending in
#: a backticked `test_...` found zero hits across 114 checklist lines, so
#: this token form ships rather than the HTML-comment fallback D4 held in
#: reserve.
AGREEMENT_LINE = re.compile(
    r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)"
    r"(?:\s+`(?P<witness>test_[A-Za-z0-9_]+)`)?\s*$")

#: A bullet: a marker followed by whitespace. `**bold**` is not one, which is why
#: this exists — a file that records a reverted agreement in prose was reported as
#: three malformed items, and the paragraph that explains a reversal is exactly the
#: kind of writing this file needs to allow.
BULLET_LINE = re.compile(r"^\s*[-*]\s+\S")


def _agreement_scan_text(data: bytes) -> str:
    """The document's decoded text, with the position block's own byte span
    excised — what `agreements_state` and `_agreement_collides` both scan.

    One cause, one fix. Measured by construction with a minimal isolated
    fixture (never by reading a target's own file): 2 real agreement
    bullets plus a 3-item position block reported `open: 5`, not 2 — the
    block's own sequence items, `- [ ] N. ...`, are exactly `AGREEMENT_LINE`
    (line 153)'s shape, and nothing excluded the block's byte span from
    either scanner. `_agreement_collides` reads the identical shape, which
    is why an item's own located line always "collided" with itself: the
    two symptoms are one cause and are repaired by the same excision.
    `impl_position.locate_block`'s own docstring stated this exclusion
    before it was true of anything but the two HTML-comment delimiters —
    corrected alongside this fix, not left standing beside it.

    The injected `b"\\n"` at the excision point is load-bearing, not
    cosmetic. `data[:start] + data[end:]` alone can concatenate the last
    partial line before the block with the first partial line after it
    into one line neither of them was — a fabricated bullet if the merged
    text happens to shape one, silent corruption rather than a raised
    error. Slicing, never `re.sub` or `str.replace`, for the identical
    backslash-interpretation reason `impl_position.splice`'s own docstring
    gives.

    A block that will not locate (`Refused`, e.g. a malformed opener or
    more than one delimiter) is caught here, not propagated: `agreements_state`
    is total today and reports absence as a state rather than raising, and a
    document whose position block cannot be located is scanned in full —
    the exact behavior both callers already had before this function
    existed. The residual is unobservable, not merely tolerated: the same
    document raises through `position_state` in the same `verify` call, so
    a malformed block is never silently invisible end to end.
    """
    try:
        block = impl_position.locate_block(data)
    except Refused:
        return data.decode("utf-8")
    if block is None:
        return data.decode("utf-8")
    return (data[:block["start"]] + b"\n" + data[block["end"]:]).decode("utf-8")


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

    **A located position block never counts as an agreement.** Its own
    sequence items are excluded before this scan sees a single line
    (`_agreement_scan_text`, above); a holder whose only checklist items
    are position lines therefore reports `absent`, not `open` — the same
    fact `position_state` already reports separately, so it is never lost.

    **The witness dimension, nested under `witness` (design D7, spec Group
    4).** Three states, none collapsing into another: `unwitnessed` (the
    line carries no `` `test_<id>` `` token at all -- reported, never a
    failure), `unmeasured` (a token is declared but this run could not, or
    would not, call it a contradiction), `disagrees` (declared, `tests/` is
    readable and fully parsed, the mark is `x`, and `test_<id>` is absent
    from `test_function_names(...)`).

    **This CLI runs no test, ever** — `test_function_names` is an `ast`
    walk, nothing here executes a suite. Finding `test_<id>` among the
    collected names proves only that a function by that name exists; it is
    never read as "the test passed", so that case reads `unmeasured`, the
    same as a token this run could not evaluate at all. Only a *definite
    absence* — a fully-parsed `tests/` that does not contain the declared
    function — is strong enough to call `disagrees`. `unmeasured` also
    covers `tests/` missing entirely or `unparsable_tests(...)` non-empty:
    the collector silently skips a file that fails `ast.parse`, so "absent"
    and "unreadable" are genuinely indistinguishable, which is exactly what
    `unmeasured` denotes.

    **One-directional, unlike `impl_position.derive()`.** An unticked
    agreement whose declared witness function already exists is never
    `disagrees` — `settle` always writes `[ ]`, and the symmetric rule
    would flag every freshly settled agreement whose test already exists.

    **`summary` is present on every branch, including `absent`** (`"0 of 0
    witnessed"`), the same uniform-key-set doctrine `position_state`
    states for itself. Silence is never how this reports "nothing is
    declared" — see `cmd_verify`'s own contract.
    """
    product = target / name
    files = sorted(p for p in product.glob(AGREEMENTS_GLOB) if p.is_file()) \
        if product.is_dir() else []

    # Computed once per call, never per item: whether `tests/` at the
    # target's own root (the same directory `cmd_verify`'s own
    # `test_function_names(target / "tests")` already reads) is even
    # readable at all. A witness token cannot be told apart from a
    # contradicted one when the collector itself could not run.
    tests_dir = target / "tests"
    tests_readable = tests_dir.is_dir() and not unparsable_tests(tests_dir)
    tested_names = test_function_names(tests_dir) if tests_readable else set()

    open_items: list[str] = []
    settled = 0
    unparsed: list[str] = []
    holding: list[str] = []
    unwitnessed: list[str] = []
    unmeasured: list[str] = []
    disagrees: list[str] = []
    total_items = 0
    for path in files:
        items_here = 0
        for raw in _agreement_scan_text(path.read_bytes()).splitlines():
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
            total_items += 1
            text = match.group("text")
            mark = match.group("mark")
            witness = match.group("witness")
            if mark == " ":
                open_items.append(text)
            else:
                settled += 1
            if not witness:
                unwitnessed.append(text)
            elif (tests_readable and mark in ("x", "X")
                  and witness not in tested_names):
                disagrees.append(text)
            else:
                unmeasured.append(text)
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
                        "items; if a gate happened, its agreements were lost",
                "witness": {"unwitnessed": [], "unmeasured": [], "disagrees": [],
                           "summary": "0 of 0 witnessed"}}

    witnessed = len(unmeasured) + len(disagrees)
    return {
        "status": "open" if open_items or unparsed else "settled",
        "holders": holding,
        "searched": f"{name}/*.md",
        "open": open_items,
        "settled": settled,
        "unparsed": unparsed,
        "note": None,
        "witness": {
            "unwitnessed": unwitnessed,
            "unmeasured": unmeasured,
            "disagrees": disagrees,
            "summary": f"{witnessed} of {total_items} witnessed",
        },
    }


def position_state(target: Path, name: str, evidence: dict,
                   revision: str | None, source: str | None) -> dict:
    """The execution sequence's current state, read from `<Name>/AGREED.md`.

    Every mark reported here is derived, never read as an asserted claim —
    see `impl_position.derive`. `evidence` is a plain dict of already-computed
    states (the search, the notebooks, the job readiness and, when given, the
    arrived shards), so this function reads no filesystem itself beyond
    locating which markdown file, if any, holds the block.

    Uniform key set on every branch, `absent` included: a caller that reads
    `position["sequence"]` on a target that never reached a gate must not
    special-case the one status where the key would otherwise be missing —
    `returned_keys`'s agreement rule (test_proposal_implementation.py:161-164).

    Reported and never gating, exactly like `agreements_state` beside it: a
    target with items still open is a not-yet-ready state, not a failure, and
    neither `verify` nor `probe`'s own exit status is touched by anything this
    returns. The one exception is a malformed block — `locate_block` and
    `parse_items` raise `Refused` for that, the same class `MALFORMED_FINDINGS`
    already is for `read_findings` (line 2151), and `main()`'s existing
    `except Refused` turns it into exit 2 for every command that reads one.
    """
    empty = {
        "status": "absent", "holder": None, "revision": None,
        "revisionSha256": None, "boundTo": "unknown",
        "sequence": [], "disagreements": [], "unmeasured": [],
        # Every item whose box is ticked and whose witness nothing measured
        # -- an assertion, not a reading. Its own list beside `disagreements`
        # rather than folded into it, because a disagreement names a
        # measurement that says otherwise and this one has none to name; see
        # `impl_position.derive`'s docstring.
        "unbacked": [],
        "lastGate": None, "lastClose": None,
        # PR10 (the-position-nobody-holds, level grammar): the rung this
        # pass is aiming at, read straight off the block's own header --
        # `None` on every branch that never located a block, since there is
        # no pass to name a target for.
        "targetLevel": None,
        # And the other fact, which the header cannot carry: the rung the
        # EVIDENCE reaches (`impl_position.attained_level`). An aim above what
        # is attained is legitimate -- it is how a pass climbs -- so the two
        # only mean something read side by side, and until this key existed
        # only one of them was ever visible. A recorded rung standing over
        # nothing attained was reported nowhere at all, while the much smaller
        # incident of a tick over nothing measured had `unbacked` to itself;
        # the gap is now readable without tripping a refusal to find it.
        "attainedLevel": None,
    }
    product = target / name
    if not product.is_dir():
        return empty

    # Found by shape, exactly like `agreements_state` two functions up: every
    # markdown file at the top of the product folder is a candidate holder,
    # never a fixed filename that would decide for the repository.
    holders = []
    for path in sorted(p for p in product.glob("*.md") if p.is_file()):
        block = impl_position.locate_block(path.read_bytes())
        if block is not None:
            holders.append((path, block))

    if not holders:
        return empty
    if len(holders) > 1:
        raise Refused(
            "POSITION_HOLDER_AMBIGUOUS",
            "more than one markdown file under "
            f"{product.relative_to(target)}/ carries a `<!-- position -->` "
            "block; only one may hold the section this reads.")

    path, block = holders[0]
    items = impl_position.parse_items(block["body"])
    # `evidence` is copied, never mutated in place: a caller (`cmd_gate`,
    # `cmd_discuss`) that built it once and keeps reading it after this call
    # must not find a `targetLevel` key it never put there itself.
    evidence = {**evidence, "targetLevel": block["target"]}
    derived = impl_position.derive(items, evidence)

    events = impl_position.read_events(product / ".implementation" / "position.jsonl")
    last_gate = next((e for e in reversed(events) if e.get("kind") == "gate"), None)
    last_close = next((e for e in reversed(events) if e.get("kind") == "close"), None)

    sequence, disagreements, unmeasured, unbacked = [], [], [], []
    for item, result in zip(items, derived):
        entry = {
            "ordinal": item["ordinal"], "mark": item["mark"],
            "derived": result["derived"], "twostate": result["twostate"],
            "satisfied": result["satisfied"], "witness": item["witness"],
            "measuredBy": result["measuredBy"], "disagrees": result["disagrees"],
            "unbacked": result["unbacked"],
            "text": item["text"],
        }
        sequence.append(entry)
        if result["disagrees"]:
            disagreements.append(entry)
        if result["derived"] is None:
            unmeasured.append(entry)
        # An item can be both unmeasured and unbacked -- it is unbacked only
        # BECAUSE it is unmeasured -- so it appears in both lists rather than
        # in whichever one is tested first. `unmeasured` answers "what could
        # not be read"; `unbacked` answers "what was claimed anyway", and a
        # reader looking for the second must not have to know the first.
        if result["unbacked"]:
            unbacked.append(entry)

    # The same staleness rule `admissibility_record` already applies (line
    # 4815-4821): a revision's *content* hash, not its name, is what a header
    # is bound to. Neither `revision` nor `source` resolved this invocation
    # (probe without `--revision`, most commonly) reports `unknown` rather
    # than guessing at a hash nobody could compute.
    if not revision or not source:
        bound_to = "unknown"
    else:
        current_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
        bound_to = "current" if block["revisionSha256"] == current_sha else "stale"

    if bound_to == "stale":
        status = "stale"
    elif any(item["mark"] == " " for item in items) or disagreements:
        status = "open"
    else:
        status = "complete"

    return {
        "status": status, "holder": str(path.relative_to(target)),
        "revision": block["revision"], "revisionSha256": block["revisionSha256"],
        "boundTo": bound_to, "sequence": sequence,
        "disagreements": disagreements, "unmeasured": unmeasured,
        "unbacked": unbacked,
        "lastGate": last_gate, "lastClose": last_close,
        "targetLevel": block["target"],
        # Derived from the same `evidence` the marks above were, and pointedly
        # not from `derived`'s own `satisfied` column: that column is graded
        # against the header's aim, so reading attainment off it would be
        # reading the aim back again.
        "attainedLevel": impl_position.attained_level(items, evidence),
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


#: What a search MAY say about itself, and is never asked to -- held apart
#: from `SEARCH_DECLARATION` above for the identical reason
#: `DISTRIBUTION_OPTIONAL` is held apart from `DISTRIBUTION_DECLARATION`: the
#: required set is what goes `missing` when unanswered, and a key added
#: there would declare every existing target incomplete for a question
#: nobody had asked it yet.
SEARCH_OPTIONAL = {
    "record": "the path, relative to the product folder, of the artefact this "
              "search writes -- the one key `search_state` reads before any "
              "of the required four, and the only one whose absence is "
              "silent rather than reported. Undeclared, `search.recordFound` "
              "answers `null` on every run forever, so a ticked `@record` "
              "witness has nothing to back it and reads `POSITION_UNBACKED`; "
              "a leveled `@record:level` witness derives no rung at all, "
              "which sinks `position.attainedLevel` to `null` and answers "
              "every launch `RUNG_NOT_ATTAINED`; and `probe`'s own "
              "`search-first` rung fires on every call, since a declared "
              "`requiredScale` can never be satisfied by a record nothing "
              "was told to look for -- telling the operator to run a search "
              "they may already have run. The forge never guesses the "
              "filename: a default here would make it answer a question the "
              "target never asked, and `undeclaredRecords` would then report "
              "the real artefact as unaccounted for beside the invented one",
    "currentWhen": "a dotted path into the record's own file naming where it "
                   "wrote down the identity of the code that produced it -- "
                   "`distribution.currentWhen`'s own idiom, one level up "
                   "from a shard. Arrival says the record's file exists, "
                   "never which code wrote it, so without this a found "
                   "record is trusted on the strength of being present. "
                   "The forge never guesses the field: the repository "
                   "names it and the forge only compares the value there "
                   "against the digest of the code as it stands",
}


#: The declared shape of each `search` field, required and optional alike --
#: the same way `DISTRIBUTION_SHAPE` declares `distribution`'s. `requiredScale`
#: is a scale along named axes, so it is a mapping and never a bare number:
#: `30` cannot say whether it means epochs, seeds or runs, and there is no
#: axis to project a cost along. Without this table the field was accepted on
#: bare truthiness and the arithmetic downstream iterated a scalar, which
#: ended the process on a traceback instead of a result.
SEARCH_SHAPE = {
    "what": str,
    # A path, so a string. Without an entry here the key was accepted on
    # bare truthiness and a list reached `product / record`, which is the
    # same shape defect `requiredScale` was added to this table for.
    "record": str,
    "requiredScale": dict,
    "role": str,
    "tieRule": str,
    "currentWhen": str,
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


def _record_scale(expected: Path | None, axes: dict) -> dict:
    """The record's own reported scale, read only under the axis names
    `requiredScale` itself declares, at either of two shapes.

    No axis vocabulary is forge-known: whichever names `requiredScale`
    declares are exactly the names looked up here, so a record naming its
    scale under any other key is read as answering none of them — never
    guessed at, never learned from one target and applied to the next.

    What the declaration declares is the axis *names*; it never declared a
    depth, and reading only the top level assumed one. A record written by a
    run comparing several things groups its result by whatever it compared —
    one group per family — and the declared axes sit inside each group, so
    the top-level read finds nothing and a search that ran at full declared
    scale reports back as one that has not run. So the flat shape is tried
    first and answers exactly as it always did; only when it answers nothing
    is the record read as groups, and only when that nesting is structurally
    unambiguous: every top-level value a mapping, and every one of those
    carrying every declared axis. One value that is not a mapping, one group
    silent on one axis, an empty record — all `{}`, as before.

    This learns no target's vocabulary. The rule is structural and identical
    for every target: it names nothing, recognises nothing, and asks only
    whether the record is uniformly grouped, which either holds or does not.
    The alternative — a declaration field naming where the axes live — would
    make every record already on disk unreadable until its own repository
    was edited, and this forge does not reach into those.

    Where groups disagree on an axis the weakest is what is reported: a
    record satisfies a requirement only if every part of it does, so the
    minimum is the honest reading — taken per axis, never per group, and
    never averaged into a number no group ran at.
    """
    if expected is None or not axes or not expected.is_file():
        return {}
    try:
        payload = json.loads(expected.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    flat = {axis: payload[axis] for axis in axes if axis in payload}
    if flat:
        return flat
    groups = list(payload.values())
    if not groups or not all(isinstance(group, dict) for group in groups):
        return {}
    if not all(axis in group for group in groups for axis in axes):
        return {}
    return {axis: min((group[axis] for group in groups), key=_scale_rank)
            for axis in axes}


def _scale_rank(value: object) -> tuple[int, int]:
    """How weak a scale reads, ordered so the weakest sorts first.

    A value `_scale_of` cannot measure at all is weaker than any it can: it
    proves nothing about how large the run was, and reporting the measurable
    sibling instead would hand `_scale_satisfied` a number no group vouched
    for. Below that, smaller is weaker, which is what `_scale_of` already
    means.
    """
    scale = _scale_of(value)
    return (0, 0) if scale is None else (1, scale)


def _scale_satisfied(record_scale: dict, required_scale: dict) -> bool | None:
    """Tri-state: whether the record's own scale meets what was declared.

    `None` when the record names none of the declared axes at all — an
    unprovable precondition, not a satisfied one, the same doctrine
    `_verify_commit_reachable` already applies to a question that could not
    be asked. `False` when it names some axes but not every declared one, or
    names every one and falls short on at least one. `True` only when every
    declared axis is present and each meets or exceeds its requirement.
    """
    if not record_scale:
        return None
    if set(record_scale) != set(required_scale):
        return False
    return all(
        _scale_of(record_scale[axis]) is not None
        and _scale_of(required_scale[axis]) is not None
        and _scale_of(record_scale[axis]) >= _scale_of(required_scale[axis])
        for axis in required_scale
    )


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


#: What a distributed run MAY say about itself, and is never asked to. Held
#: apart from `DISTRIBUTION_DECLARATION` above rather than mixed into it,
#: because that dict is the required set: every field in it that goes
#: unanswered is reported `missing` and the whole block reads `incomplete`.
#: A key added there would declare every existing target incomplete for
#: never having answered a question nobody had asked them yet, which is a
#: worse lie than the silence it replaces.
#:
#: Optional, and still schema: a value of the wrong shape is `malformed`
#: here exactly as it is above, because a target that DID answer deserves to
#: be told its answer is unreadable rather than have it quietly ignored.
DISTRIBUTION_OPTIONAL = {
    "currentWhen": "a dotted path into a shard's own stamp naming where that "
                   "shard recorded the identity of the code that produced it. "
                   "Arrival says a shard folder exists, never which code wrote "
                   "it, so without this a returned shard is trusted on the "
                   "strength of being present. The forge never guesses the "
                   "field: the repository names it and the forge only compares "
                   "the value there against the digest of the code as it "
                   "stands, the same division `identicalAcrossShards` already "
                   "keeps",
    "shardsRoot": "where a split campaign's returned shards land, so that a "
                  "command with no `--shards` flag of its own -- `gate`, "
                  "`close`, `discuss`, `probe` -- measures a `@shard` witness "
                  "against the same directory `position`/`verify`'s own "
                  "`--shards` would, rather than reading it as unmeasured "
                  "forever. The forge never invents this directory: the "
                  "repository names it once and every reader compares against "
                  "the identical answer",
}


#: The declared shape of each `distribution` field, required and optional
#: alike. A container answers by existing, even empty; a scalar answers only
#: non-blank. Neither branch is trusted until the value's own type is
#: confirmed first — that confirmation is what keeps a malformed value from
#: being read as either.
DISTRIBUTION_SHAPE = {
    "axis": str,
    "poolable": list,
    "perEnvironment": list,
    "perRun": list,
    "identicalAcrossShards": list,
    "currentWhen": str,
    "shardsRoot": str,
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


#: Returned by `_stamp_at` for a path the stamp does not hold, so that a
#: stamp carrying a literal `null` there is never confused with one that
#: carries nothing. A private sentinel rather than `None`, because the whole
#: point of the lookup is telling those two apart.
_STAMP_ABSENT = object()


def _stamp_at(stamp: dict, dotted: str):
    """The value a shard's own stamp holds at a dotted path, or `_STAMP_ABSENT`.

    Dotted because a stamp is a document a repository shaped, not a flat
    table: whatever it keeps its code identity under may well sit one level
    down beside the rest of what that run recorded. Every segment must
    resolve through a mapping — a path that runs into a list, a scalar or a
    missing key answers absent rather than raising, since a stamp this
    cannot read is a stamp that did not answer, which is a state and not a
    crash.
    """
    current = stamp
    for segment in dotted.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _STAMP_ABSENT
        current = current[segment]
    return current


def _shards_current(shards: list, dist: dict | None, digest: str) -> list | None:
    """Which arrived shards say they were produced by the code as it stands.

    `None` — not `[]` — when the repository declared no `currentWhen`. The
    two are opposite answers: `[]` says every shard was asked and none of
    them speaks for this code, while `None` says nobody was asked, because
    the forge holds no name for the field that would answer and inventing
    one on a repository's behalf is the one thing it must not do (see
    `DISTRIBUTION_OPTIONAL`). `impl_position` reads that difference directly:
    `None` leaves arrival alone deciding, exactly as it did before this key
    existed.

    A shard whose stamp carries nothing at the declared path is left out. It
    is tempting to read a silent stamp as "probably fine" — it is the same
    temptation as reading an unstamped notebook as current, and
    `notebooks_state` already refuses it for the same reason: a stamp that
    cannot answer the question is not evidence that the answer is yes.

    `digest` is the caller's already-computed current source digest — the
    identical value `notebooks_state` compares a report's own stamp against
    (`source_digest`), never a second one derived here, or a shard and a
    notebook could disagree about what "current" means in one report.
    """
    declared = (dist or {}).get("currentWhen")
    if not isinstance(declared, str) or not declared:
        return None
    return [entry["shard"] for entry in shards
            if _stamp_at(entry.get("stamp") or {}, declared) == digest]


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
                    "shardsDisagree": [], "shardsArrived": [],
                    "note": "no benchmark declaration to read a distribution "
                            "from yet"}
        return {"status": "none", "declared": {}, "missing": [], "malformed": [],
                "axisIsAComparison": False, "unpartitioned": [],
                "inBothHalves": [], "notADimension": [], "shardsDisagree": [],
                "shardsArrived": [],
                "note": "no distribution declared; a run on one machine has "
                        "nothing to split and nothing to say about splitting it"}

    missing = [{"field": field, "reason": reason}
               for field, reason in DISTRIBUTION_DECLARATION.items()
               if not _distribution_answered(dist, field)
               and not _distribution_malformed(dist, field)]

    # The optional field is scanned for shape and never for presence: a
    # target that answered it badly hears about it, and one that never
    # answered it at all is not `missing` anything.
    malformed = [{"field": field, "expected": DISTRIBUTION_SHAPE[field].__name__,
                 "found": type(dist[field]).__name__}
                for field in (*DISTRIBUTION_DECLARATION, *DISTRIBUTION_OPTIONAL)
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
        # Every branch reports every key, including this one and the two shard
        # keys above. A key that appears on some branches and not others
        # vanishes for exactly the callers that took the early ones, and
        # nothing downstream can tell an absent key from an absent answer.
        # `None` here is the honest note for a distribution that was read:
        # there is nothing to explain away.
        "note": None,
    }


def _record_current(expected: Path | None, current_when, digest: str | None) -> bool | None:
    """Whether the record found at `expected` says it was produced by the
    code as it stands -- `_shards_current`'s own doctrine (see that
    function's docstring), one level up from a shard.

    `None` is the sentinel that means "nothing to check", and it means that
    for exactly one reason: `current_when` (`search.currentWhen`) is not a
    real string. That is the ONLY branch this returns `None` from, so
    `_derive_record` can read `recordCurrent is None` as "not declared" and
    nothing else -- the identical contract `_shards_current` keeps for a
    shard by returning `None` only when `distribution.currentWhen` is
    absent, never when a declared check merely came back negative.

    Declared, this always resolves to a real `True`/`False`: the record's
    own JSON is read at the declared dotted path (absent, unparsable, or the
    path itself missing all read the same as a value that fails to match)
    and compared against `digest`. A `False` here composes with
    `impl_position._derive_record`'s own doctrine that a definite mismatch
    and an unreadable stamp are graded identically -- both collapse to
    `None` (unmeasured), never `False`, at the witness itself; see that
    function's own docstring for why.
    """
    if not isinstance(current_when, str) or not current_when:
        return None
    if expected is None or not expected.is_file():
        return False
    try:
        stamp = json.loads(expected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    value = _stamp_at(stamp if isinstance(stamp, dict) else {}, current_when)
    if value is _STAMP_ABSENT:
        return False
    return value == digest


def search_state(contract: dict, declared_records: list,
                 product: Path | None = None,
                 declaration_status: str = "declared",
                 digest: str | None = None) -> dict:
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
                    "recordCurrent": None,
                    "strayRecords": [], "recordScale": {}, "scaleSatisfied": None,
                    "note": "no benchmark declaration to read a search from yet"}
        return {"status": "none", "declared": {}, "missing": [], "malformed": [],
                "recordNotDeclared": None, "recordFound": None,
                "recordCurrent": None, "strayRecords": [],
                "recordScale": {}, "scaleSatisfied": None,
                "note": "no search declared; `undeclaredRecords` is what would "
                        "surface one that left an artefact"}

    missing = [{"field": field, "reason": reason}
               for field, reason in SEARCH_DECLARATION.items()
               if not _search_answered(search, field)
               and not _search_malformed(search, field)]

    # A value of the wrong shape is reported as itself. Folding it into
    # `missing` would ask for a field that is already there, and folding it
    # into the answered set is what let a scalar reach the arithmetic.
    # `SEARCH_OPTIONAL` is scanned for shape and never for presence, the same
    # rule `distribution_state` already keeps for its own optional fields: a
    # target that answered `currentWhen` badly hears about it, and one that
    # never answered it at all is not `missing` anything.
    malformed = [{"field": field,
                  "expected": SEARCH_SHAPE[field].__name__,
                  "found": type(search[field]).__name__}
                 for field in (*SEARCH_DECLARATION, *SEARCH_OPTIONAL)
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
    expected = None
    if record and product is not None and product.is_dir():
        expected = product / record
        found = expected.is_file()
        if not found:
            stray = [str(p.relative_to(product))
                     for p in sorted(product.rglob(Path(record).name))
                     if p.is_file()]

    # The declaration is the fact: whatever axis names `requiredScale` uses
    # are the only names read back off the record. A value of the wrong
    # shape is already reported as `malformed` above and contributes no axes
    # here, so a scalar `requiredScale` cannot silently answer `scaleSatisfied`.
    required_scale = search.get("requiredScale") \
        if isinstance(search.get("requiredScale"), dict) else {}
    record_scale = _record_scale(expected, required_scale)
    scale_satisfied = (_scale_satisfied(record_scale, required_scale)
                       if required_scale else None)

    # `None` whenever `currentWhen` is not a real string -- undeclared, or
    # declared with the wrong shape (already reported in `malformed` above,
    # and contributing no comparison here for the identical reason a
    # malformed `requiredScale` contributes no axes). `_record_current`
    # itself never raises on a missing/unparsable record; see its own
    # docstring for why the only `None` this ever returns is "not declared".
    record_current = _record_current(
        expected,
        search.get("currentWhen") if isinstance(search.get("currentWhen"), str) else None,
        digest)

    return {
        "status": ("ok" if not missing and not malformed and covered
                   and found is not False else "incomplete"),
        "declared": dict(search),
        "recordFound": found,
        # `impl_position._derive_record`'s own currency check, computed here
        # rather than at the witness: this is the only layer that knows both
        # the record's own on-disk bytes and the digest of the code as it
        # stands. See `_record_current`'s docstring for the three-valued
        # contract.
        "recordCurrent": record_current,
        "strayRecords": stray,
        "missing": missing,
        "malformed": malformed,
        "recordNotDeclared": None if covered else record,
        # `null` when the record names none of the declared axes — see
        # `_scale_satisfied`. Reported beside the declaration, never folded
        # into `status`, so a below-scale record is still `"ok"` here and the
        # caller (`probe`'s ladder) is what turns it into `search-first`.
        "recordScale": record_scale,
        "scaleSatisfied": scale_satisfied,
    }


def named_records_state(target: Path, name: str, records: dict, digest: str) -> dict:
    """`evidence["records"]`: `{name: {recordFound, recordCurrent,
    scaleSatisfied, requiredScale}}`, one entry per `__records__` declaration
    -- design D4, assembled from the identical primitives `search_state`
    already reuses for the `search` block's own record (`_record_scale`,
    `_scale_satisfied`, `_record_current`), never a new measurement of any
    kind ("no deriver opens a file" doctrine). `_derive_record_level`
    (`impl_position.py`) reads this dict's own entries through the identical
    `_record_scale_level` arithmetic the `search` block's own bare
    `@record:level` already uses, so an addressed record and the search's
    own share one arithmetic rather than a second one drifting beside it.

    Each entry's `path` is resolved relative to the product folder
    (`target/name`), the identical layout `search_state`'s own `record`
    field already resolves against. A declared entry naming no file yet, or
    naming one of the wrong shape, reads `recordFound: False` (or `None`
    when the product folder does not exist at all), exactly as an absent
    search record does; a non-dict entry is skipped entirely, the same
    silent-rather-than-crashing rule `resolve_records_declaration` already
    applies one layer up.

    `recordCurrent` reads `entry.get("currentWhen")` through the identical
    `_record_current` primitive `search_state` uses -- always `None` today,
    since `__records__`'s own declared shape carries no `currentWhen` key
    (design's own "Recorded, not fixed here" note: `_record_scale_level`
    reads no currency at all), but computed generically here rather than
    hardcoded, so a target that adds the key by hand is read rather than
    silently ignored.
    """
    product = target / name
    state: dict = {}
    for record_name, entry in records.items():
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        required_scale = entry.get("requiredScale") \
            if isinstance(entry.get("requiredScale"), dict) else {}
        found = None
        expected = None
        if isinstance(path, str) and path and product.is_dir():
            expected = product / path
            found = expected.is_file()
        record_scale = _record_scale(expected, required_scale)
        scale_satisfied = (_scale_satisfied(record_scale, required_scale)
                           if required_scale else None)
        record_current = _record_current(
            expected,
            entry.get("currentWhen") if isinstance(entry.get("currentWhen"), str) else None,
            digest)
        state[record_name] = {
            "recordFound": found,
            "recordCurrent": record_current,
            "scaleSatisfied": scale_satisfied,
            "requiredScale": required_scale,
        }
    return state


def undeclared_optional_state(search: dict, distribution: dict) -> list[dict]:
    """Every optional key a DECLARED `search` or `distribution` block left
    unanswered, named beside the exact consequence its absence carries.

    `SEARCH_OPTIONAL`/`DISTRIBUTION_OPTIONAL` are scanned for shape only,
    never presence, at `search_state`/`distribution_state` themselves --
    both docstrings state it directly, and for the identical reason: a
    required key added there would declare every existing target
    incomplete for a question nobody had asked it yet. That restraint is
    correct and stays. What was missing is the OTHER half: a target that
    never learns the key exists cannot decide to answer it either, and the
    comment naming it sits only in the kit's own source, never in
    anything `verify` prints. This reads what `search_state`/
    `distribution_state` already computed -- `declared`, the raw section
    dict, copied verbatim only when a real block was found -- and never
    touches the filesystem or the contract itself a second time.

    **Reported, never demanded.** A target with no search, or no split
    run, is asked nothing here either: `search["declared"]`/
    `distribution["declared"]` are empty exactly when `contract.get(
    "search"/"distribution")` was falsy, the same gate `search_state`/
    `distribution_state` open with. Forcing an answer from a target with
    nothing to answer would be the forge deciding for the target -- the
    one thing this whole file refuses to do.
    """
    entries: list[dict] = []
    if search.get("declared"):
        for field, consequence in SEARCH_OPTIONAL.items():
            if field not in search["declared"]:
                entries.append({"section": "search", "field": field,
                                "consequence": consequence})
    if distribution.get("declared"):
        for field, consequence in DISTRIBUTION_OPTIONAL.items():
            if field not in distribution["declared"]:
                entries.append({"section": "distribution", "field": field,
                                "consequence": consequence})
    return entries


#: What a repository gives up by leaving `__levels__` empty, written out
#: rather than labelled. `undeclaredOptional`'s entries earn their place by
#: naming the cost of an absence, never the absence itself, and this follows
#: them: an entry reading "no ladder is declared" would restate the key's own
#: name and leave a reader who has never seen a rung exactly where they
#: started. Four facts, each one read off code in this file or beside it --
#: `_skipped_rung_detail`'s empty-ladder exit, `impl_position.attained_level`'s
#: `[]` answer, `cmd_position`'s `POSITION_LEVELS_UNDECLARED`, and the
#: `if declared_levels and ...` that guards `POSITION_TARGET_LEVEL_UNKNOWN`.
LADDER_UNDECLARED_CONSEQUENCE = (
    "no rung exists for another to sit above, so the whole ordering "
    "discipline of the position section is switched off for this repository. "
    "`POSITION_RUNG_SKIPPED` -- the refusal that stops a pass sealing at a "
    "rung whose predecessor the evidence has not reached -- can never fire, "
    "because an empty ladder has no predecessor to put the question to. "
    "`position.attainedLevel` stays `null` on every run, since there is no "
    "rung name to answer \"which one does the evidence currently reach\" "
    "with, and a reader gets no answer rather than a low one. Every item in "
    "the sequence is two-state, reached or not: a `:level`-marked witness "
    "cannot be written at all (`POSITION_LEVELS_UNDECLARED` refuses it), so "
    "a step that got part of the way -- a record found but short of its own "
    "declared scale -- is recorded as reached or as nothing, with no rung in "
    "between for it to rest on. And a header's own `--target-level` accepts "
    "any word typed at it, since `POSITION_TARGET_LEVEL_UNKNOWN` compares a "
    "named rung against a declared vocabulary and there is none to compare "
    "against. Declaring an ordered `__levels__`, in this repository's own "
    "words, is what turns all four back on."
)


def undeclared_ladder_state(target: Path, name: str,
                            levels: list[str]) -> dict | None:
    """The rung ladder this target never named, beside what naming none costs
    it -- or `None` when it named one.

    The gap this closes is the one `__steps__` does not have. Run a step
    against an empty `__steps__` and `STEPS_UNDECLARED` refuses and publishes
    the question, so nobody keeps an empty one by accident. An empty
    `__levels__` is demanded by nothing at all:
    `POSITION_LEVELS_UNDECLARED` fires only once a `:level`-marked witness
    already exists in the sequence, and a target that never writes one is
    never asked for a rung; `_skipped_rung_detail` answers `None` before it
    grades anything at all when `levels` is empty; and the call sites of
    `resolve_levels_declaration` pour the answer straight into
    `evidence["levels"]`, where `[]` and
    a ladder that was read are the same value. A repository scaffolded from
    zero therefore has no rungs, is asked for none, and cannot be reached by
    the rung discipline at all -- and until this existed, nothing said so.

    **Reported, never demanded.** A target with genuinely no rungs is a
    legitimate resting state, the same way an unanswered optional field is,
    and refusing one would be the forge deciding a repository's own
    vocabulary for it -- the one thing `resolve_levels_declaration`'s own
    docstring exists to refuse. This never gates and never raises.

    **Its own key rather than an `undeclaredOptional` entry.** Those are
    `{section, field, consequence}`: a field inside a DECLARED
    `search`/`distribution` block. `__levels__` is a module-level literal
    held apart from `__benchmark__` on purpose, so it sits in no section and
    names no field, and borrowing that shape would mean writing a `section`
    that does not exist. Top-level in `cmd_verify`'s return for the
    constraint that decided `toDiscuss`'s and `undeclaredOptional`'s own
    placement: `returned_keys` reads dict-literal keys at the top level of a
    function's own return, so a key nested anywhere at all ships invisible to
    `VerifyStatusRosterTests`.

    **A target with nowhere to write it is asked nothing**, the identical
    restraint `undeclared_optional_state` keeps for a repository with no
    search: no benchmark package, or a package carrying neither file
    `resolve_levels_declaration` reads, is not a repository that left a
    question unanswered -- `structure.scaffoldGaps` already names the file it
    is missing, and saying it twice would turn one gap into two findings.

    `levels` is passed in rather than resolved here, from the same
    `resolve_levels_declaration` call `verify` already makes for the position
    evidence: two reads of one declaration in one command is how the two come
    to disagree about what the target declared.
    """
    if levels:
        return None
    bench_root = target / "src" / f"{package_name(name)}_Benchmark"
    if not bench_root.is_dir():
        return None
    # The file that WOULD carry it, chosen in the order
    # `resolve_levels_declaration` reads them, so the path named here is the
    # one a reader's own declaration would actually be found at.
    holder = next((candidate for candidate in ("__init__.py", "config.py")
                   if (bench_root / candidate).is_file()), None)
    if holder is None:
        return None
    return {"declaration": LEVELS_DECLARATION,
            "path": (bench_root / holder).relative_to(target).as_posix(),
            "consequence": LADDER_UNDECLARED_CONSEQUENCE}


#: What a repository gives up when its ladder and its sequence cannot meet,
#: written out for the identical reason `LADDER_UNDECLARED_CONSEQUENCE` is: a
#: reader handed "the ladder is unreachable" learns the key's own name and
#: nothing else. A format string rather than a constant, because the two exits
#: are only actionable once the actual rungs are named -- "declare at most
#: three rungs" is advice, `"declare at most three"` beside the four this
#: target wrote is a decision somebody can take.
LADDER_UNREACHABLE_CONSEQUENCE = (
    "no launch can ever be authorized for any job in this sequence. "
    "`launch_available` floors a launch at {required!r} -- the rung below "
    "the top of the declared ladder -- and reads `position.attainedLevel`, "
    "which is the highest rung at which EVERY leveled item grades satisfied. "
    "The leveled item{plural} at ordinal {ordinals} can never grade satisfied "
    "above {bound!r}, whatever runs: a `@rehearsal` witness reads "
    "`smokeReady`, which is two-valued, so a rehearsal that passed proves the "
    "floor plus one rung and never more -- full scale is `@record`'s or "
    "`@shard`'s evidence to speak to. So the gate answers `RUNG_NOT_ATTAINED` "
    "on every call, naming a rung nothing that can run will reach, and the "
    "top rungs of this ladder can never be sealed at either. Two exits, both "
    "the target's own to take: declare a `{declaration}` of at most three "
    "rungs, so the launch floor sits at or below what a rehearsal proves; or "
    "drop the `:level` marker from that item and record it two-state -- the "
    "grammar's own default -- since a two-state item is graded without the "
    "ladder and holds no rung down. The forge changes neither on its own: a "
    "floor that moved with whatever the sequence happens to contain would let "
    "ADDING a leveled item quietly LOWER the launch threshold for every other "
    "item beside it."
)


def unreachable_ladder_state(items: list[dict], levels: list[str]) -> dict | None:
    """The declared ladder no evidence in this sequence can ever climb far
    enough to open a launch on -- or `None` when it can.

    `undeclared_ladder_state`'s own shape, placement and restraint (design
    D8), one fact over: that one reports a ladder nobody named, this one a
    ladder named longer than the sequence beside it can reach.

    **The gap.** `_derive_rehearsal_level` bounds a leveled `@rehearsal`
    item at index 1 and `launch_available` floors a launch at
    `levels[-2]`, and each is right on its own. Composed, they are
    unsatisfiable from four rungs up: one leveled `@rehearsal` anywhere in
    the sequence pins `attained_level` at index 1 forever, and
    `RUNG_NOT_ATTAINED` then answers every launch with a rung nothing that
    can run will reach. The operator is told which rung was not attained --
    true, and unanswerable.

    **Reported, never repaired.** The other closure on offer was to lower
    the gate's own floor to `min(len(levels) - 2, the highest attainable)`,
    and it is rejected: that floor would then be a function of what the
    sequence happens to hold, so writing one more leveled `@rehearsal` item
    would LOWER the launch threshold for every other item beside it. A gate
    a sequence can weaken by growing is strictly worse than one that will
    not open, because only the second is visible.

    **Below two rungs, nothing is reported**: `launch_available` skips the
    rung threshold entirely there -- there is no predecessor rung for a
    launch to have missed -- so a finding would name a gate that does not
    exist. The identical "structurally unreachable" restraint
    `_skipped_rung_detail` already keeps for a ladder too short to name a
    predecessor.

    `items` is the sequence `position_state` already parsed and `levels` the
    ladder `verify` already resolved; nothing here opens a file or measures
    anything, so this can never disagree with the marks reported beside it.
    """
    if len(levels) < 2:
        return None
    bound = impl_position.attainable_rung(items, levels)
    floor_index = len(levels) - 2
    highest_index = impl_position.level_index(levels, bound)
    if highest_index is None or highest_index >= floor_index:
        return None
    # Which items actually hold the bound down, so a reader has something to
    # change rather than a whole sequence to re-read. Only the ones AT the
    # minimum: naming every leveled item would name two that reach the top
    # beside the one that does not.
    capped = [{"ordinal": item["ordinal"], "witness": item["witness"]}
              for item in items
              if not item["witness"].get("twostate", True)
              and impl_position.highest_rung(
                  item["witness"]["kind"], levels) == highest_index]
    ordinals = ", ".join(str(row["ordinal"]) for row in capped)
    return {
        "declaration": LEVELS_DECLARATION,
        "levels": list(levels),
        "requiredLevel": levels[floor_index],
        "highestAttainable": bound,
        "cappedBy": capped,
        "consequence": LADDER_UNREACHABLE_CONSEQUENCE.format(
            required=levels[floor_index], bound=bound,
            ordinals=ordinals, plural="s" if len(capped) > 1 else "",
            declaration=LEVELS_DECLARATION),
    }


#: What a repository gives up by leaving `__records__` empty, written out for
#: the identical reason `LADDER_UNDECLARED_CONSEQUENCE` is: an absence read as
#: "no records are declared" restates the key's own name, and a reader who
#: has never seen a named record is left exactly where they started.
RECORDS_UNDECLARED_CONSEQUENCE = (
    "no name exists for a leveled `@record:level <name>` witness to "
    "address, so the only rung a leveled record item can reach is the "
    "`search` block's own -- a bare `@record:level` with no operand, "
    "unchanged since before this declaration existed. A named "
    "`@record:level <name>` witness written into the sequence anyway "
    "derives `None` (unmeasured), never a rung: `position` refuses "
    "`POSITION_RECORD_UNKNOWN` before it ever writes a mark from that "
    "state, so `verify` and `probe`, which never refuse, only ever read the "
    "already-refused case as `unmeasured` -- never as a wrongly-satisfied "
    "one. Declaring `__records__`, in this repository's own words, is what "
    "gives a named witness something to reach."
)


def undeclared_records_state(target: Path, name: str, records: dict) -> dict | None:
    """The named records this target never declared, beside what naming none
    costs it -- `undeclared_ladder_state`'s own shape and placement (design
    D8), one declaration over.

    **Reported, never demanded.** A target with genuinely no named records is
    a legitimate resting state, the same way an empty `__levels__` is: no
    `@record:level <name>` witness is ever forced into existence by this
    report, and refusing an absence would be the forge deciding a
    repository's own vocabulary for it.

    **Its own key rather than an `undeclaredOptional` entry**, for the
    identical reason `undeclared_ladder_state` gives: `__records__` is a
    module-level literal held apart from `__benchmark__`, so it sits in no
    section and names no field, and borrowing that shape would mean writing
    a `section` that does not exist.

    **A target with nowhere to write it is asked nothing**, the identical
    restraint `undeclared_ladder_state` keeps: no benchmark package, or a
    package carrying neither file `resolve_records_declaration` reads, is
    not a repository that left a question unanswered --
    `structure.scaffoldGaps` already names the file it is missing.

    `records` is passed in rather than resolved here, from the same
    `resolve_records_declaration` call `verify` already makes for the
    position evidence -- two reads of one declaration in one command is how
    the two come to disagree about what the target declared.
    """
    if records:
        return None
    bench_root = target / "src" / f"{package_name(name)}_Benchmark"
    if not bench_root.is_dir():
        return None
    holder = next((candidate for candidate in ("__init__.py", "config.py")
                   if (bench_root / candidate).is_file()), None)
    if holder is None:
        return None
    return {"declaration": RECORDS_DECLARATION,
            "path": (bench_root / holder).relative_to(target).as_posix(),
            "consequence": RECORDS_UNDECLARED_CONSEQUENCE}


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





# --------------------------------------------------------------------------
# guards
# --------------------------------------------------------------------------





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


#: What a repository gives up by leaving `arms` empty, written out rather
#: than labelled -- `LADDER_UNDECLARED_CONSEQUENCE`'s own doctrine, one block
#: over. A format string, because the file the declaration belongs in and the
#: number of modules that go uncrossed are what make the sentence checkable
#: instead of general.
ARMS_UNDECLARED_CONSEQUENCE = (
    "{count} module{plural} under `src/{package}/` declare{verb} the sections "
    "of a proposal, and no arm claims any of them: `{path}` names `arms` "
    "empty. `unreachedModules` is the one join this flow makes between the "
    "method's own provenance and the bench's declaration -- the two documents "
    "can both be impeccable while an arm reimplements an equation instead of "
    "calling it, and only crossing them says so. It is built FROM `arms`, so "
    "with none declared it answers `[]` on every run whatever those modules "
    "hold and whatever the harness calls; `armsReached` answers `null` for "
    "the same reason; `fidelity.benchmark.status` can never read "
    "`unfaithful`, and `fidelity.status` can never be driven to `drift` by "
    "an unreached module; and `probe`'s own `wiring-first` rung -- the answer "
    "that publishes the draft of how each module becomes trainable -- can "
    "never be reached. Declaring one entry per arm, naming the sections it "
    "exercises, is what turns all four back on. Reported and never demanded: "
    "a repository with one arm and nothing to compare is a legitimate resting "
    "state, and which comparison it runs is not the forge's to decide."
)


def undeclared_arms_note(target: Path, name: str, declaration: dict,
                         modules: list[dict]) -> str | None:
    """Why `unreachedModules` came back empty, when the reason is that no arm
    was declared -- or `None` when there is nothing to explain away.

    `distribution.note`'s own shape and placement (see `cmd_verify`, where a
    missing `DIMENSIONS` literal is named so an empty `unpartitioned` is not
    read as evidence the split is complete), applied to the other side of the
    same silence. `unreached_mathematics`'s docstring calls itself "the join
    nothing else in the flow crosses"; an empty `arms` switches that join off
    entirely, and until this existed nothing said so.

    **Silent when there is nothing to cross.** A repository whose modules
    declare no sections at all has no crossing to lose, and
    `fidelity.missingProvenance` already names a module that declares
    nothing. Reporting here too would turn one gap into two findings -- the
    identical restraint `undeclared_ladder_state` keeps for a target with no
    benchmark package.

    `declaration` and `modules` are both passed in, from the reads `verify`
    already made: two reads of one declaration in one command is how the two
    come to disagree about what the target declared.
    """
    if declaration.get("arms"):
        return None
    claimable = [module for module in modules if module.get("sections")]
    if not claimable:
        return None
    package = package_name(name)
    holder = f"src/{package}_Benchmark/__init__.py"
    return ARMS_UNDECLARED_CONSEQUENCE.format(
        count=len(claimable), plural="" if len(claimable) == 1 else "s",
        verb="s" if len(claimable) == 1 else "", package=package, path=holder)


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
    # worse than a report in drift and cheaper to catch before it runs. A record
    # present but silent about the declared scale — or short of it — shares
    # this same remedy (Decision 12): `scaleSatisfied` short of `true` is not
    # a chosen configuration either, and `null` (the record names none of the
    # declared axes) is an unprovable precondition, not a satisfied one.
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
        target / name, declaration_status=resolved["status"],
        digest=source_digest(target, package_name(name)))
    # Computed once and reused for the `remoteExecution` merge below, rather
    # than called twice for the same answer.
    jobs = remote_execution_jobs_state(target)
    # `probe` takes no `--shards` of its own, but a target that declared
    # `distribution.shardsRoot` still gets a real shard answer here --
    # `_resolve_shard_evidence` is the identical fallback
    # `_position_write_evidence` applies for `gate`/`close`/`discuss`.
    # Undeclared, both stay `None`: `@shard` reports `unmeasured`, never a
    # false "did not arrive" (see `impl_position.derive`'s own docstring).
    shards_arrived, shards_current = _resolve_shard_evidence(
        target, name, resolved["contract"], None)
    probe_digest = source_digest(target, package_name(name))
    # Read once and handed to both readers below: `position_state` derives
    # the sequence from it, and `pilot_completeness_state` grades the flow
    # against the identical dict. Two evidence builds inside one command is
    # how two answers come to disagree about the same repository.
    probe_evidence = {
        "search": search, "requiredScale": declared_required_scale(search),
        "notebooks": notebooks_state(target, name, package_name(name)),
        "smokeReady": jobs["smokeReady"], "shardsArrived": shards_arrived,
        "shardsCurrent": shards_current,
        "levels": resolve_levels_declaration(target, name),
        "stepVerdicts": _step_verdicts(target, name),
        # Design B5 (evidence wiring is three sites): the identical
        # `named_records_state` call `_position_write_evidence` and
        # `cmd_verify`'s own inline dict make, so `probe` never reports
        # `unmeasured` for a `@record:level <name>` witness while `gate`
        # (which reads `_position_write_evidence`) reports it satisfied.
        "records": named_records_state(
            target, name, resolve_records_declaration(target, name),
            probe_digest)}
    # Hoisted above the ladder rather than computed after it, because two of
    # its rungs read the flow's own state. The evidence itself is unchanged;
    # only the order in which this function builds it is.
    position = position_state(
        target, name, probe_evidence, args.revision,
        revision_source(args.revision) if args.revision else None)
    pilot = pilot_completeness_state(
        resolve_steps_declaration(target, name), position["sequence"],
        probe_evidence)
    # Which of the flow's own steps still owes a decision about how it is
    # carried out in the full run. Never "which are open": a step nobody has
    # asked about yet appears in no open bucket either, and reading that as
    # decided is silence taken for consent.
    answered = _answered_discussions(target, name)
    pilot_undecided = [
        row["step"] for row in pilot["steps"]
        if _pilot_decision_question(target, name, row["step"]) not in answered]
    if next_step in ("benchmark", "piloted") and resolved["status"] in (
            "absent", "undeclared"):
        next_step = "declare-first"
    # Immediately after `declare-first` (Decision 12): introspection is
    # meaningless before something is declared, so declaration keeps the top
    # of the ladder. Read only when `live` was actually attempted — `None`
    # means `report_state` never got there (report itself undeclared), and
    # that state already has its own, more specific rung below.
    elif next_step in ("benchmark", "piloted") and report.get("live") == (
            "undeclared"):
        # An entry nobody declared is a gap in the declaration, and the rung
        # for that already exists one line above. Routing it to `env-first`
        # would name the interpreter for something the interpreter did not do.
        next_step = "declare-first"
    elif next_step in ("benchmark", "piloted") and report.get("live") not in (
            None, "ok"):
        next_step = "env-first"
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
    # The declared flow itself, read before the search record and after the
    # submission already out. A submission already sent keeps its place at the
    # top of this half of the ladder for the reason it always had -- an answer
    # on its way outranks anything this repository could be told to start --
    # but everything BELOW it is about spending machine time that has not been
    # spent yet, and the pilot comes before the scale.
    #
    # Measured, and the defect that named this rung: a target declaring six
    # ordered steps had run the second and nothing else, six of its seven
    # notebooks carried zero executed cells and zero outputs, and this ladder
    # answered `search-first` -- whose published question offers to continue
    # toward the declared scale. That rung's own condition ("the record is
    # absent or short") was true; it is simply a different fact from "the flow
    # was validated at pilot", and nothing had been produced for anybody to
    # read. A question that offers the expensive run at that point is an
    # invitation to say yes.
    elif next_step in ("benchmark", "piloted") and (
            pilot["status"] == "incomplete"):
        next_step = "pilot-first"
    # And what a finished pilot unlocks is NOT permission to launch. The flow
    # returns to its first step and each one owes its own decision about how
    # it is carried out in the full run; only once every one of those is on
    # the record does the ladder fall through to the rung that offers the
    # declared scale. `offer --answer` is not that mechanism and is not
    # borrowed for it: it records one closed yes/no per call, and this is one
    # decision per step. `discuss` already buckets by exact question text, so
    # N steps are N independently-retiring buckets with no second approval
    # surface built beside it.
    elif next_step in ("benchmark", "piloted") and (
            pilot["status"] == "complete" and pilot_undecided):
        next_step = "pilot-decisions"
    elif next_step in ("benchmark", "piloted") and (
            search["recordFound"] is False
            or (declared_required_scale(search)
                and search["scaleSatisfied"] is not True)):
        next_step = "search-first"
    elif next_step in ("benchmark", "piloted") and report["status"] != "ok":
        next_step = "report-first"

    # The roster decides, never a literal. This line read `if next_step ==
    # "benchmark"`, and `wiring-first` is assigned by an override twenty lines
    # above it -- so at the one answer that names an arm declaring mathematics
    # it never calls, the draft of how each module becomes trainable came back
    # `None` and whoever was driving the CLI composed the wiring plan in prose.
    # `benchmark` keeps it (it is the raw material the run offer is built from,
    # and nothing is unreached there); `wiring-first` gains it, because the
    # state it describes IS the thing blocking.
    proposal = (wiring_proposal(target, name, baselines)
                if PROBE_NEXT_STEPS[next_step]["wiring"] else None)
    # The harness's name is read from the target's own declaration
    # (`resolve_harness_status`), never assumed from a filename: a fixed
    # convention here reported `harness: null` on a target that had followed
    # doctrine exactly but named its module something else.
    harness_status = resolve_harness_status(target, name, package_name(name))
    notebook = target / name / "Notebooks" / PROBE_NOTEBOOK
    # Computed once and reused for both `search.costForecast` below and the
    # classification call: the exact same projection, never a second one
    # (design D3, `the-pilot-decides-the-remote-strategy`).
    cost_forecast = search_cost_forecast(
        state.get("reduction") or {}, declared_required_scale(search))
    # `classify_remote_necessity` never inspects `smokeReady` today (see its
    # own docstring), but it is folded into each row anyway so the shape
    # handed to it matches the one the row's own producer documents.
    necessity = impl_execution_strategy.classify_remote_necessity(
        jobs=[{**job, "smokeReady": jobs["smokeReady"].get(job["job"], False)}
              for job in jobs["jobs"]],
        results_status=state["status"],
        cost_forecast=cost_forecast)
    # What this answer publishes, decided by `PROBE_NEXT_STEPS` rather than by
    # a literal. The line this replaces fired on `next_step == "piloted"` and
    # on nothing else, so every other answer -- `search-first` above all, which
    # launches a search -- named a step and published no way to take it, and
    # whoever was driving the CLI composed the question in prose. Two of the
    # eleven answers publish nothing, and the roster is where they say so.
    #
    # The declared scale is the only fact either experiment question reads, and
    # only ever the DECLARED one: the achieved count climbs on every poll while
    # the decision has not changed, and embedding it would open a new,
    # never-to-be-revisited `discuss` bucket on every call (the stability rule
    # `_piloted_discuss_entry` already documents).
    publication = next_step_publication(
        target, name, next_step,
        {"declared": (state.get("belowTargetScale") or {})
         if next_step == "piloted"
         else (declared_required_scale(search) or {}),
         # The two facts `declare-first` is assigned from, threaded through
         # rather than recomputed: its published sentence names the state that
         # actually routed there, and a second read here could disagree with
         # the branch above that published it.
         "declarationStatus": resolved["status"],
         "live": report.get("live"),
         # The two facts the flow rungs publish, threaded through rather than
         # recomputed: a second read here could disagree with the branch that
         # published it, the same discipline `declarationStatus` states.
         "incomplete": pilot["incomplete"],
         "notebooks": [row["notebook"] for row in pilot["steps"]
                       if row["notebook"]]})
    # `toDiscuss` carries the question-shaped publications only -- a command
    # this flow can name completely is not a question anybody answers, and
    # putting one in a discussion list would open a bucket nothing retires.
    # Computed unconditionally as a list so the key's shape never varies with
    # state, the same discipline `verify`'s `toDiscuss` already keeps.
    to_discuss = (
        [{key: value for key, value in publication.items() if key != "kind"}]
        if publication and publication["kind"] == "question" else []
    )
    # The per-step pass, appended after the rung's own question rather than
    # replacing it: the first entry says what state the flow is in and where
    # its outputs are, and one entry per still-undecided step follows, each in
    # its own `discuss` bucket. This is the one answer whose `toDiscuss` is
    # longer than its `resolve`, and the roster's `publish` shape (one dict)
    # is why the per-step half lives here rather than inside it.
    if next_step == "pilot-decisions":
        to_discuss += [_pilot_decision_entry(target, name, step)
                       for step in pilot_undecided]
    return {
        "status": "ok",
        "target": str(target),
        "name": name,
        "backend": backend,
        "baselines": baselines,
        "comparable": bool(baselines),
        "harnessStatus": harness_status,
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
        "search": {**search, "costForecast": cost_forecast},
        "unreachedModules": unfaithful,
        # A static fact, reported and never gating: see `notebook_coupling`.
        "coupling": coupling_state(target, name, package_name(name)),
        # A static fact, reported and never gating: see `position_state`.
        "position": position,
        # Whether the ordered flow this target declared has actually run at
        # pilot, step by step. Two rungs read it (`pilot-first`,
        # `pilot-decisions`); it is reported beside them because "which steps
        # are still short" is exactly what a reader needs in order to act on
        # either answer. See `pilot_completeness_state`.
        "pilotCompleteness": pilot,
        # What went out to a remote worker (the ledger), plus what job
        # folders exist right now (the filesystem), plus — purely additive,
        # this slice refuses nothing on it — whether each job classifies as
        # needing a remote worker at all. See `remote_execution_jobs_state`
        # and `impl_execution_strategy.classify_remote_necessity`.
        "remoteExecution": {
            **remote,
            **jobs,
            "necessity": necessity,
        },
        "nextStep": next_step,
        # What to do about that answer, published by the engine rather than
        # composed by whoever reads it. `null` only where the roster declares
        # the step terminal -- a step that names no work, not a step nobody
        # decided about. The identical shape a refused payload's own `resolve`
        # carries, deliberately: one publication shape, wherever this engine
        # reaches a point somebody has to act on.
        "resolve": ({key: value for key, value in publication.items()
                     if key in ("kind", "question", "command")}
                    if publication else None),
        "toDiscuss": to_discuss,
        "wiring": proposal,
        # `probe` looks and reports; it never runs anything itself.
        "kind": "read-only",
    }




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
    """The declared audit findings, read statically from tests/findings.py.

    Both assignment forms, for the reason `read_declaration` states in full:
    `FINDINGS: list[dict] = [...]` is `ast.AnnAssign`, and a reader walking
    only `ast.Assign` sees nothing there. The consequence is worse here than
    anywhere else this class appears — the comment below already says why an
    empty list is the wrong answer for an unparsable file, and an annotated
    declaration produced exactly that answer, silently, for a repository
    whose findings were sitting in the file the whole time. A bare `FINDINGS:
    list[dict]` with no value declares nothing and is skipped, never read as
    an audit that found nothing.
    """
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
            value = node.value
        elif (isinstance(node, ast.AnnAssign)
              and isinstance(node.target, ast.Name)
              and node.target.id == "FINDINGS"):
            if node.value is None:
                continue
            value = node.value
        else:
            continue
        try:
            declared = ast.literal_eval(value)
        except ValueError as exc:
            raise Refused("MALFORMED_FINDINGS",
                          "FINDINGS is not a literal, so it cannot be read without "
                          "executing the target's code.") from exc
        return well_formed(declared)
    return []


#: `.implementation/` joins them because this skill writes a ledger there and
#: that ledger carries launch authorizations. Committed, an approval travels
#: in a clone: it authorizes no different work, being bound to
#: `(commit, entrypoint, units, worker)`, but it travels. The cost is real
#: and is stated under "What this skill has not written down" -- the same
#: file also carries the deliberation itself now (`discuss`, `settle`), and
#: that half IS project history a clone would want.
IGNORE_ENTRIES = (".venv/", "__pycache__/", ".ipynb_checkpoints/",
                  ".implementation/")


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


def scaffold_destinations(name: str) -> list[str]:
    """The eleven file paths a `materialize --stage scaffold` writes.

    Pulled out of `scaffold_gaps` so the writer and the gap-reporter read one
    list rather than two: `scaffold_gaps` reports which of these are missing
    (plus the two merge anchors, which are not paths in this sense at all —
    see `scaffold_gaps`'s own docstring-equivalent comment below), and
    `materialize --stage scaffold` copies exactly these into a target.
    """
    return [f"src/{package_name(name)}/__init__.py",
            f"src/{package_name(name)}_Benchmark/__init__.py",
            # The seal every notebook stamps by importing, rather than by
            # hashing a tree of its own. It belongs inside the package because
            # `_here()` reads the repository off its own path as `parents[1]`,
            # and because producing the report is what the bench package does.
            f"src/{package_name(name)}_Benchmark/report_digest.py",
            "tests/test_smoke.py",
            # `conftest.py`, `sweep.py` and `admissibility.py` are not tests and
            # were never asked for, so a scaffold built from exactly this list
            # could not be collected: `test_audit.py` and `test_remedies.py`
            # below both open by importing them. `admissibility.py` fixes its
            # own destination — its RULING_PATH resolves beside itself, which is
            # where `admit` writes the ruling.
            "tests/findings.py", "tests/conftest.py", "tests/sweep.py",
            "tests/admissibility.py",
            "tests/test_audit.py", "tests/test_remedies.py",
            f"{name}/Notebooks/verification.ipynb"]


def scaffold_gaps(target: Path, name: str) -> list[str]:
    gaps = [w for w in scaffold_destinations(name) if not (target / w).exists()]
    if pytest_anchor_missing(target):
        gaps.insert(0, "pyproject.toml [tool.pytest.ini_options] pythonpath")
    missing_ignores = ignore_gaps(target)
    if missing_ignores:
        gaps.insert(0, f".gitignore ({', '.join(missing_ignores)})")
    return gaps


def object_destinations(name: str) -> list[str]:
    """The three file paths a `materialize --stage objects` writes.

    SKILL.md step 9's table, made concrete. `module.py` is the kit's own
    filename — not a per-object name — matching `MaterializeWritesStageOneTests
    .STAGE_TWO`, which already fixes `src/<Package>/module.py` as the literal
    path a stage-two write lands on.
    """
    package = package_name(name)
    return [f"src/{package}/module.py", "tests/test_invariants.py",
            "tests/test_synthetic.py"]


def object_gaps(target: Path, name: str) -> list[str]:
    return [w for w in object_destinations(name) if not (target / w).exists()]


def object_kit_source(destination: str, name: str) -> Path | None:
    package = package_name(name)
    mapping = {
        f"src/{package}/module.py": SKILL_ROOT / "assets" / "kit" / "src" / "module.py",
        "tests/test_invariants.py":
            SKILL_ROOT / "assets" / "kit" / "tests" / "test_invariants.py",
        "tests/test_synthetic.py":
            SKILL_ROOT / "assets" / "kit" / "tests" / "test_synthetic.py",
    }
    return mapping.get(destination)


def harness_destinations(name: str) -> list[str]:
    """The three file paths a `materialize --stage harness` writes: SKILL.md's
    harness-wiring table, made concrete. `wiring.py` is deliberately absent —
    SKILL.md states it is bespoke-authored, never kit-sourced, and stays out
    of every stage.
    """
    package = package_name(name)
    return [f"src/{package}_Benchmark/benchmark.py",
            f"src/{package}_Benchmark/verdict.py",
            f"{name}/Notebooks/probe.ipynb"]


def harness_gaps(target: Path, name: str) -> list[str]:
    return [w for w in harness_destinations(name) if not (target / w).exists()]


def harness_kit_source(destination: str, name: str) -> Path | None:
    package = package_name(name)
    mapping = {
        f"src/{package}_Benchmark/benchmark.py":
            SKILL_ROOT / "assets" / "kit" / "nb" / "benchmark.py",
        f"src/{package}_Benchmark/verdict.py":
            SKILL_ROOT / "assets" / "kit" / "nb" / "verdict.py",
        f"{name}/Notebooks/probe.ipynb":
            SKILL_ROOT / "assets" / "kit" / "nb" / "probe.ipynb",
    }
    return mapping.get(destination)


def all_kit_destinations(name: str) -> list[str]:
    """Every kit destination across all three stages — the domain
    `--authored`/`--adopt` are scoped to (`NOT_A_KIT_DESTINATION`). Eleven
    scaffold + three objects + three harness = seventeen, matching the
    design's own count.
    """
    return [*scaffold_destinations(name), *object_destinations(name),
            *harness_destinations(name)]


# --------------------------------------------------------------------------
# materialize — the engine writes the scaffold; the receipt is the only
# mechanism. See design #the-skill-materializes-not-the-agent.
# --------------------------------------------------------------------------

#: Where the receipt lives, relative to a target's root. `.implementation/`
#: is already git-ignored (`IGNORE_ENTRIES`) and already excused from the
#: dirty-worktree check (`_is_own_bookkeeping`), so this file inherits both
#: properties rather than needing either built for it.
MATERIALIZATION_RECEIPT = Path(".implementation") / "materialization.json"

#: The kit template each copied scaffold destination is written from, keyed
#: by the destination path a `{Name}`-parameterized target resolves to. The
#: one entry with no kit source (`src/<Package>/__init__.py`) is authored by
#: this engine directly — step 9 has written no module yet, so it exports
#: none — and is looked up as `None`, never a missing key.
def scaffold_kit_source(destination: str, name: str) -> Path | None:
    package = package_name(name)
    mapping = {
        f"src/{package}_Benchmark/__init__.py":
            SKILL_ROOT / "assets" / "kit" / "src_benchmark" / "__init__.py",
        f"src/{package}_Benchmark/report_digest.py":
            SKILL_ROOT / "assets" / "kit" / "nb" / "report_digest.py",
        "tests/test_smoke.py": SKILL_ROOT / "assets" / "kit" / "tests" / "test_smoke.py",
        "tests/findings.py": SKILL_ROOT / "assets" / "kit" / "tests" / "findings.py",
        "tests/conftest.py": SKILL_ROOT / "assets" / "kit" / "tests" / "conftest.py",
        "tests/sweep.py": SKILL_ROOT / "assets" / "kit" / "tests" / "sweep.py",
        "tests/admissibility.py": SKILL_ROOT / "assets" / "kit" / "tests" / "admissibility.py",
        "tests/test_audit.py": SKILL_ROOT / "assets" / "kit" / "tests" / "test_audit.py",
        "tests/test_remedies.py": SKILL_ROOT / "assets" / "kit" / "tests" / "test_remedies.py",
        f"{name}/Notebooks/verification.ipynb":
            SKILL_ROOT / "assets" / "kit" / "nb" / "verification.ipynb",
    }
    return mapping.get(destination)


def authored_package_init(name: str) -> str:
    """`src/<Package>/__init__.py`'s content: authored, never copied.

    Exports the target's own modules, and step 9 has written none of them
    yet, so it exports nothing.
    """
    return (f'"""Reference implementation of the {name} formulation.\n\n'
            "Each module declares the sections and equations it implements in\n"
            "`__provenance__`, and every invariant listed there has a matching\n"
            "test under tests/.\n"
            '"""\n\n'
            "__all__ = []\n")


def writable_at_scaffold_time(source: str) -> bool:
    """Whether a substituted template is a file the scaffold stage may write.

    The discriminator between the two stages, and it is mechanical rather
    than a list the kit could fall out of step with. A template that still
    carries a `{{TOKEN}}` where an identifier has to be does not parse, and
    the tokens left in it — `{{FUNCTION_NAME}}`, `{{INVARIANT_ID}}`,
    `{{EXPECTATION}}` — are answers to the object map step 8 approves.
    Nothing could have answered them at scaffold time.

    Substituting dummy identifiers instead would be worse: the result
    parses, collects and *passes* while asserting nothing.
    """
    try:
        ast.parse(source)
    except SyntaxError:
        return False
    return True


def scaffold_substitute_body(text: str, name: str, seed: str) -> str:
    """The two tokens `materialize --stage scaffold` answers: `{{PKG}}` and
    `{{SEED}}`. Every other token a template still carries after this belongs
    to a later step and is left standing — see `writable_at_scaffold_time`.
    """
    return text.replace("{{PKG}}", package_name(name)).replace("{{SEED}}", seed)


def read_materialization_receipt(target: Path) -> dict:
    path = target / MATERIALIZATION_RECEIPT
    if not path.exists():
        return {"version": 1, "name": None, "entries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_materialization_receipt(target: Path, receipt: dict) -> None:
    """Atomic replace, written last — after every file of the stage has
    landed. An aborted run leaves no receipt entry for that invocation."""
    path = target / MATERIALIZATION_RECEIPT
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def receipt_entry(receipt: dict, path: str) -> dict | None:
    return next((e for e in receipt["entries"] if e["path"] == path), None)


def set_receipt_entry(receipt: dict, entry: dict) -> None:
    """Replace the entry for `entry['path']` in place; append if absent.

    Keeps a second stage's entries beside the first's rather than truncating
    them, and lets a stale entry (the file it names no longer exists) be
    replaced by a fresh one on the next successful write of that path.
    """
    entries = receipt["entries"]
    for index, existing in enumerate(entries):
        if existing["path"] == entry["path"]:
            entries[index] = entry
            return
    entries.append(entry)


def _kit_structure_gaps(target: Path, destinations: list[str]) -> dict:
    """`SCAFFOLD_DRIFT` / `UNRECORDED_SCAFFOLD`, generalized over any one
    stage's own destination list — never a merge anchor, whose correctness is
    re-derived presence (`ignore_gaps`/`pytest_anchor_missing`), not a hash,
    and never a destination absent from disk, which is a gap the stage's own
    `*_gaps` reports, not drift or an unrecorded write.

    One function shared by `scaffold_structure_gaps`, `object_structure_gaps`
    and `harness_structure_gaps`: the three stages' destination sets are
    disjoint paths, so a receipt entry keyed by path is unambiguous across
    all of them without needing to also check the entry's own `stage` field.
    """
    receipt = read_materialization_receipt(target)
    entries = {e["path"]: e for e in receipt["entries"]}
    drift: list[str] = []
    unrecorded: list[str] = []
    for destination in destinations:
        full = target / destination
        if not full.exists():
            continue
        entry = entries.get(destination)
        if entry is None:
            unrecorded.append(destination)
            continue
        current_sha256 = hashlib.sha256(full.read_bytes()).hexdigest()
        if current_sha256 != entry.get("writtenSha256"):
            drift.append(destination)
    return {"drift": sorted(drift), "unrecorded": sorted(unrecorded)}


def scaffold_structure_gaps(target: Path, name: str) -> dict:
    """`SCAFFOLD_DRIFT` / `UNRECORDED_SCAFFOLD` over the eleven scaffold
    destinations only — never the two merge anchors, whose correctness is
    re-derived presence (`ignore_gaps`/`pytest_anchor_missing`), not a hash,
    and never a destination absent from disk, which is a gap `scaffold_gaps`
    already reports, not drift or an unrecorded write.
    """
    return _kit_structure_gaps(target, scaffold_destinations(name))


def object_structure_gaps(target: Path, name: str) -> dict:
    """`SCAFFOLD_DRIFT` / `UNRECORDED_SCAFFOLD` over the three `objects`
    destinations only. Named `object_structure_gaps`, not folded into
    `scaffold_structure_gaps`, because the two stages' destinations are
    different files reported under different `structure` keys
    (`objectDrift`/`unrecordedObjects` vs `scaffoldDrift`/`unrecordedScaffold`)
    — `scaffold_gaps`/`scaffold_structure_gaps` stay scoped to the eleven, as
    every existing caller and test already assumes.
    """
    return _kit_structure_gaps(target, object_destinations(name))


def harness_structure_gaps(target: Path, name: str) -> dict:
    """`SCAFFOLD_DRIFT` / `UNRECORDED_SCAFFOLD` over the three `harness`
    destinations only — see `object_structure_gaps` for why this is a
    sibling function rather than a widening of the scaffold one."""
    return _kit_structure_gaps(target, harness_destinations(name))


# --------------------------------------------------------------------------
# provenance (static, never imports target code)
# --------------------------------------------------------------------------

def read_provenance(path: Path) -> dict | None:
    """The module's own `__provenance__`, read without importing it.

    Both assignment forms, for the reason `read_declaration` states in full:
    `__provenance__: dict = {...}` is `ast.AnnAssign`, and a reader walking
    only `ast.Assign` answers `None` for it — which every caller here reads
    as "this module declares no provenance at all", the exact opposite of
    what the file says. A bare `__provenance__: dict` with no value declares
    nothing and is skipped rather than reported as absent-with-an-error.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return {"__error__": f"unparsable: {exc}"}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__provenance__" for t in node.targets
        ):
            value = node.value
        elif (isinstance(node, ast.AnnAssign)
              and isinstance(node.target, ast.Name)
              and node.target.id == "__provenance__"):
            if node.value is None:
                continue
            value = node.value
        else:
            continue
        try:
            return ast.literal_eval(value)
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


#: The first bytes a published revision carries, and the only fact about a
#: managed artifact a TypeScript producer and a Python reader can agree on
#: without either importing the other's conventions.
#:
#: The deliberation skill writes it and its own store compares
#: `bytes.subarray(0, MARKER.length)` — a leading prefix, byte for byte, never a
#: mention further down and never a decoded string. It is read here the same way.
MANAGED_ARTIFACT_MARKER = b"<!-- proposal-workspace:artifact:v1 -->\n"


def revision_source(revision: str | None) -> str | None:
    """The bound revision's text, read from the proposals directory."""
    if not revision:
        return None
    path = proposals_root() / revision
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def is_managed_artifact(path: Path) -> bool:
    """Whether a file carries the publisher's marker as its very first bytes.

    Read as bytes and compared as a leading prefix, which is what the producing
    side does. Decoding first would make an unreadable file an exception instead
    of an answer, and searching for the marker anywhere in the text would count a
    document that merely quotes it — that is precisely the file this excludes.
    """
    try:
        with path.open("rb") as handle:
            return handle.read(len(MANAGED_ARTIFACT_MARKER)) == MANAGED_ARTIFACT_MARKER
    except OSError:
        return False


def revision_discovery(like: str | None) -> dict:
    """The newest revision of the same family as `like`, and what was passed over.

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

    A family is not the same question as a publication, and that is the second
    reader this had to be reconciled with. The deliberation skill publishes a
    revision by writing an artifact marker as the file's first bytes, and refuses
    to consider anything without it; this side took the highest digits it could
    find. So a draft, an export or a copy dropped into the same directory became
    "the latest" here while deliberation still named the published one, and every
    module was reported stale against a document nobody ever published.

    The discriminator is therefore the marker and never a filename shape —
    teaching this side the other's naming rule would be a third copy of a
    convention that already has two, and would cost the independence the
    paragraph above promises. If ANY candidate in the family carries the marker
    the directory is marker-owned and only marked candidates are eligible, with
    the rest named in `nonManaged`. If none does, resolution is exactly what it
    was and `markerOwned` says so, which is what keeps a hand-authored family
    working.

    A tie on the digit tuple is real — `draft-1.md` and `draft-01.md` are one
    family and one key — and it is reported in `tied` rather than decided in
    silence, mirroring the multiple-active notion the other resolver already
    surfaces. The deterministic pick is preserved: moving it would move a
    resolution nobody asked to move.

    Reported, never refused. `verify` is a reader, and a stray file in a
    directory must not be able to stop the whole check.
    """
    empty = {"revision": None, "markerOwned": False, "nonManaged": [], "tied": []}
    if not like:
        return empty
    name = Path(like).name
    if not re.search(r"\d", name):
        return empty
    # `re.escape` leaves digits alone and escapes the suffix's dot, so the only
    # thing turned into a wildcard is a run of digits. Anchored: a family is
    # matched whole, never as a substring of a longer name.
    stem = re.sub(r"\d+", r"(\\d+)", re.escape(name))
    family = re.compile("^" + stem + "$")
    root = proposals_root()
    if not root.is_dir():
        return empty

    candidates: list[tuple[tuple[int, ...], str, bool]] = []
    for candidate in sorted(root.iterdir()):
        if not candidate.is_file():
            continue
        found = family.match(candidate.name)
        if not found:
            continue
        candidates.append((tuple(int(group) for group in found.groups()),
                           candidate.name, is_managed_artifact(candidate)))

    marker_owned = any(managed for _, _, managed in candidates)
    eligible = [c for c in candidates if c[2]] if marker_owned else candidates
    non_managed = sorted(nm for _, nm, managed in candidates
                         if marker_owned and not managed)
    if not eligible:
        return {**empty, "markerOwned": marker_owned, "nonManaged": non_managed}

    best = max(key for key, _, _ in eligible)
    # Insertion order is `sorted(root.iterdir())`, so the first of a tie is the
    # same one the strictly-greater comparison used to keep.
    tied = [candidate for key, candidate, _ in eligible if key == best]
    return {
        "revision": tied[0],
        "markerOwned": marker_owned,
        "nonManaged": non_managed,
        "tied": tied if len(tied) > 1 else [],
    }


def latest_revision(like: str | None) -> str | None:
    """The discovered revision alone, for the readers that only want the name."""
    return revision_discovery(like)["revision"]


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
#:         "renderers":   ["tables.render", "tables.render_summary"],
#:         "conclusions": ["tables.conclusion", "tables.conclusion_scale"],
#:         "figures":     ["figures.curves", "figures.grid"],
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
#: fire on any sentence that mentions how many runs there are.
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
import importlib, importlib.util, json, random, sys

package = sys.argv[1]
record = sys.argv[2]
entry_module = sys.argv[3] if len(sys.argv) > 3 else ""
# Executed first, and uncaught on purpose: `config` is pure Python and imports
# fine with nothing installed, which is exactly what answered `ok` on an empty
# venv. The declared entry module is what actually pulls the runtime in, so
# its own `ModuleNotFoundError` is the truthful liveness verdict — letting it
# raise here surfaces through this process's own non-zero exit and stderr,
# read verbatim by the caller, rather than being paraphrased.
if entry_module:
    importlib.import_module(entry_module)
# Which module the constants below are read from. `config.py` is optional
# everywhere else in this engine -- `resolve_benchmark_declaration`,
# `resolve_levels_declaration` and `declared_dimension_names` each fall back to
# another file and not one of them calls its absence a failure -- and the kit
# ships no `config.py` at all. This line used to import it unconditionally, so a
# repository built exactly as the kit prescribes raised `ModuleNotFoundError`
# here, reported `unavailable`, and was routed to `env-first`: the one rung whose
# exit is a command, and that command installs packages. It could never have
# created a module.
#
# Resolved the way `declared_dimension_names` already resolves the same
# question -- `config` first, where a target keeps its own contract, then
# `benchmark`, where the kit's own template defines it. Looked up rather than
# tried, so a `ModuleNotFoundError` raised INSIDE either file still propagates
# untouched and still reads as the unavailability it is; only the absence of the
# file itself is answered, and it is answered by name rather than by blaming the
# interpreter.
constants_holder = next(
    (candidate for candidate in (f"{package}_Benchmark.config",
                                 f"{package}_Benchmark.benchmark")
     if importlib.util.find_spec(candidate) is not None), None)
config = importlib.import_module(constants_holder) if constants_holder else None
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
values = ({n: frozen(getattr(config, n)) for n in dir(config) if n.isupper()}
          if config is not None else {})
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

print(json.dumps({"subsets": subsets, "inertConclusions": inert,
                  # Named, never inferred from an empty `subsets`: a check that
                  # had nowhere to look must not report its silence as an answer.
                  "constants": "read" if constants_holder else "absent",
                  "constantsHolder": constants_holder}))
'''


def resolve_entry_module(target: Path, name: str, package: str) -> str:
    """The dotted module whose import actually pulls the target's runtime in.

    `None` when the declaration does not name one, and never a guess.

    It used to fall back to the forge's own filename convention, and that
    fallback is what made an undeclared entry look like a broken environment:
    the guessed module does not exist, importing it fails, and liveness
    reported the failure of the guess as the failure of the interpreter. A
    target whose harness carries any other name got told to repair an
    environment that was working.

    `resolve_harness_status` below already refuses to guess for exactly this
    reason and answers `undeclared` instead. This is its sibling and now
    answers the same way, so one absence produces one fact rather than two.
    """
    contract = resolve_benchmark_declaration(target, name)["contract"]
    return (contract.get("entry") or {}).get("module") or None


def resolve_harness_status(target: Path, name: str, package: str) -> dict:
    """Where the target's own declaration says its harness module lives.

    Reads `entry.module` from the benchmark declaration and looks only for
    the file that dotted module resolves to on disk. The kit's own scaffold
    filename convention is never read here, and never as a second fallback
    to reach for — a second hardcoded name beside the first would be the
    same defect twice, which is why `probe` used to report `harness: null`
    for a target that had named its harness anything else.

    Three states, and they answer three different questions:

    - `"undeclared"`: `entry.module` is empty. Nothing has been declared to
      look for, so this says nothing about whether the target's tree holds a
      harness file under some other name — silence is not absence.
    - `"declaredMissing"`: a module is declared and no file sits where that
      declaration says. `declaredModule` and `searchedPath` are both named,
      because a refusal that does not say where it looked cannot be acted on.
    - present: the file exists at the declared location. `path` carries it,
      relative to `target`.
    """
    contract = resolve_benchmark_declaration(target, name)["contract"]
    entry = contract.get("entry") or {}
    declared = entry.get("module")
    function = entry.get("function")
    function = function if isinstance(function, str) and function else None
    if not declared:
        # One absence, one fact: `entry.module` undeclared already has its own
        # status, and naming the function beside it would turn one gap into two
        # findings -- `undeclared_ladder_state`'s own restraint.
        return {"status": "undeclared", "declaredModule": None,
                "declaredFunction": None, "path": None, "searchedPath": None,
                "note": None}
    # The one value in `entry` nothing in this file reads -- `.module` is read
    # twice and `.function` nowhere. That is not a stray declaration: the kit
    # names it for `generate-job --run-function`, which `remote_cli` declares
    # `required=True`, so the value is genuinely needed at the one handoff
    # SKILL.md's own seam table publishes. What was missing is that a target
    # could answer `module`, leave `function` blank, hear about it nowhere, and
    # reach a required flag with nothing to type into it.
    note = None if function else (
        "`entry.function` is blank. Nothing in this skill reads it, so no "
        "check here fails on it -- but the remote-execution handoff does: "
        "`generate-job --run-function` is a required argument with no "
        "default, and this declaration is where its value is supposed to "
        "come from. Name the callable inside "
        f"{declared!r} that a run enters through.")
    searched = target / "src" / Path(*declared.split(".")).with_suffix(".py")
    if searched.is_file():
        return {"status": "present", "declaredModule": declared,
                "declaredFunction": function,
                "path": str(searched.relative_to(target)), "searchedPath": None,
                "note": note}
    return {"status": "declaredMissing", "declaredModule": declared,
            "declaredFunction": function, "path": None,
            "searchedPath": str(searched.relative_to(target)), "note": note}


def target_interpreter(target: Path) -> Path:
    """The target repository's own interpreter — the only one this skill's
    isolation rule permits target code to run under.

    One spelling, because three call sites needed it and a path spelled three
    times is a path that eventually differs in one of them. `introspect` runs
    it, `env` builds it, and `target_python_version` reads what it is; the
    Windows branch is here rather than repeated at each.
    """
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    return target / ".venv" / bin_dir / ("python.exe" if os.name == "nt"
                                         else "python")


def target_python_version(target: Path) -> str | None:
    """What version that interpreter is, read off `pyvenv.cfg` rather than run.

    Static, like every other reading in this file: `notebooks_state` is called
    three times inside one `verify`, and spawning an interpreter each time to
    ask it a question its own config file already answers would be paying a
    process for a string. `pyvenv.cfg`'s `version` is written by `venv` at
    creation and is the same three-component string the interpreter reports as
    `sys.version.split()[0]` — which is what a kernel stamps into a notebook.

    `version_info` is read as a fallback because newer CPythons write that key
    (`3.12.13.final.0`) beside or instead of `version`; only its first three
    components are kept, so the two spellings compare as one.

    `None` when there is no venv, no config, or nothing parsable in it. Never a
    guess: a comparison against a version nobody could read is not a comparison.
    """
    config = target / ".venv" / "pyvenv.cfg"
    if not config.exists():
        return None
    values: dict[str, str] = {}
    for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()
    for key in ("version", "version_info"):
        raw = values.get(key)
        if raw:
            parts = raw.split(".")
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                return ".".join(parts[:3])
    return None


def introspect(target: Path, package: str, record: Path | None,
               entry_module: str = "") -> dict:
    """Run the two live checks inside the target's interpreter, or say why not.

    Never the forge's: the whole isolation rule of this skill, and here it is also
    the only interpreter where the target's own package imports at all.

    `entry_module` is executed FIRST, inside the subprocess, before the two
    checks below ever run. Reporting `live` from `config` importing cleanly
    was the exact defect measured: `config` is pure Python and imports fine on
    an empty venv, so an environment where nothing had been installed still
    answered `ok`. The entry module is what actually pulls the target's
    runtime in, so its own `ModuleNotFoundError` — surfaced through this
    subprocess's non-zero exit and quoted verbatim from its last stderr line,
    never paraphrased — is the truthful verdict.
    """
    if not entry_module:
        # Nothing declared which module carries the runtime, so there is
        # nothing to execute and no verdict about the interpreter to give.
        # Answering `unavailable` here would blame an environment that was
        # never asked a question.
        return {"status": "undeclared",
                "detail": "the benchmark declaration names no `entry.module`, "
                          "so there is nothing to import; declare it and this "
                          "becomes a reading about the interpreter"}

    interpreter = target_interpreter(target)
    if not interpreter.exists():
        return {"status": "unavailable",
                "detail": f"no hay intérprete en {interpreter}: corré `env` primero"}
    proc = subprocess.run(
        [str(interpreter), "-c", INTROSPECT, package,
         str(record) if record and record.exists() else "", entry_module],
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
                        declared. `unframed` asks whether a paragraph precedes
                        the table, never what it says, so the only place a
                        direction is written down is `report.dimensions` — and
                        a column missing from it is one no reader is ever told
                        which way wins. Every check that reads that mapping
                        (`componentsNotRecorded`, and the key the duplication
                        rule buckets a rendering under) is blind to it too.
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
    # The OTHER declaration of the same columns: the module's own `DIMENSIONS`
    # literal, which the kit's `benchmark.py` ships and a materialized target
    # keeps in `config.py`. `report.dimensions` says which way each one wins,
    # and the two are written by hand in two files -- so one can carry a column
    # the other never names, and until this crossed them nothing said so.
    #
    # `None` (neither file binds the name, or it is bound to something no
    # reading can make sense of) is NOT an empty universe: it means the
    # question could not be put, and `declared_dimension_names`' own docstring
    # keeps the two apart for exactly this reason. Read as `()` here, so a
    # target with nowhere to declare a universe is asked nothing -- the same
    # restraint `undeclared_ladder_state` keeps one file over.
    universe = declared_dimension_names(target, package) or ()
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
            # The complement of the line above, read off the same source with
            # the same literal idiom: a column this cell renders that the
            # module's own universe carries and the report contract does not.
            # Scoped to `universe` rather than to every string literal in the
            # cell, because which strings are dimensions is the package's claim
            # and not this file's guess -- the one thing that would make this a
            # finding about somebody else's vocabulary.
            undeclared.update(d for d in universe
                              if d not in dimensions
                              and (f'"{d}"' in source or f"'{d}'" in source))
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
    # No default: a report that declares no record has no record, and guessing a
    # filename here would make the forge answer a question the target never
    # asked. `""` rather than `None` because the membership test below reads the
    # declared name as text, and `p.name in None` raises.
    record = next((p for p in sorted((target / name).rglob("*.json"))
                   if p.name in (contract.get("record") or "")), None)
    declared_records, undeclared_records = records_state(target, name, contract)
    live = introspect(target, package, record, resolve_entry_module(target, name, package))
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
            # Which module `writtenSelections` was actually derived from, and
            # whether there was one at all. `"absent"` is not routed anywhere and
            # deliberately does not move `status`: it is reachable only when the
            # declared entry module imported cleanly (or this key would not exist)
            # while neither `config.py` nor `benchmark.py` sits in the benchmark
            # package -- and a missing `benchmark.py` is already a harness gap
            # `harness_gaps` reports by name. A second rung for the same fact
            # would be one fact answered twice. What it buys is that
            # `writtenSelections: []` can be read: "nothing is written out" and
            # "there was nowhere to look" no longer print the same.
            "constants": live.get("constants"),
            "constantsHolder": live.get("constantsHolder"),
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
    """A module-level literal, read without importing anything.

    Accepts both a plain assignment (`NAME = value`, `ast.Assign`) and an
    annotated one (`NAME: type = value`, `ast.AnnAssign`) — a type annotation
    does not change what a declaration says. The kit's own scaffold writes
    `__levels__` in the annotated form (`assets/kit/src_benchmark/__init__.py`),
    and a reader that only recognized `ast.Assign` never saw it: a target
    using the scaffold the skill itself ships declared a ladder the skill
    could not read. A bare annotation with no value (`NAME: type`, no `=`) has
    `node.value is None` under `ast.AnnAssign` and declares nothing — read as
    absent, never as an error or an empty literal.
    """
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
            value = node.value
        elif (isinstance(node, ast.AnnAssign)
              and isinstance(node.target, ast.Name) and node.target.id == name):
            if node.value is None:
                continue
            value = node.value
        else:
            continue
        try:
            return ast.literal_eval(value)
        except ValueError:
            return {"__error__": f"{name} is not a literal"}
    return None


#: The seven top-level blocks the kit's scaffold writes (see
#: `assets/kit/src_benchmark/__init__.py`), and the value each one carries when
#: nobody has answered it yet: `""` for the lone scalar, `{}` for the six
#: containers. Named once here so "blank" has one definition every reader of
#: the resolver's `"declared"`/`"undeclared"` split shares, rather than each
#: caller inventing its own idea of empty.
BENCHMARK_BLOCKS = {
    "revision": "", "premises": {}, "arms": {},
    "search": {}, "report": {}, "distribution": {},
    "entry": {"module": "", "function": ""},
}


def _declaration_is_blank(contract: dict) -> bool:
    """True when every block is present at its empty value — a scaffold
    nobody has written into yet, not a declaration with content.

    Emptiness means something different at this level than it does inside a
    single block: `distribution_state` already treats `perEnvironment: []` as
    an answered, measured result, because a repository can legitimately
    measure that a field is empty. No repository ever means "I measured that
    the whole `distribution` block is empty" the same way — a blank *block* is
    unambiguously unanswered, never a result.

    Compared against `BENCHMARK_BLOCKS`' own template value rather than bare
    truthiness, because `entry`'s blank value is `{"module": "", "function":
    ""}` — a non-empty dict, unlike every other block's `{}` or `""`. Bare
    truthiness would read that dict as an answer nobody gave, the moment a
    target is first materialized.
    """
    return all(contract.get(block, value) == value
               for block, value in BENCHMARK_BLOCKS.items())


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
    parses cleanly — seven blocks, each at its empty value — the moment a
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


#: The name PR10 (`the-position-nobody-holds`, level grammar) reads an
#: ordered ladder from — a second, independent top-level literal beside
#: `__benchmark__`, never a new field inside it.
LEVELS_DECLARATION = "__levels__"


def resolve_levels_declaration(target: Path, name: str) -> list[str]:
    """The ordered rung ladder `__levels__` names, or `[]` when nothing does.

    Read the same way `resolve_benchmark_declaration` reads `__benchmark__`
    (`__init__.py` first, then `config.py`), but held apart from it rather
    than added as an eighth block: `_declaration_is_blank`'s "seven blocks"
    is `__benchmark__`'s own invariant, and a target may name its ladder long
    before it answers a single one of those seven — or never answer any of
    them at all, on a repository whose position items are entirely two-state
    and therefore need no ladder read here at all. Held apart for the same
    reason `search`'s `requiredScale` is declared apart from the scale it is
    running at (`SEARCH_DECLARATION`'s own docstring): folding the two
    together would let one silently gate the other.

    Exists for generality, not to avoid naming a service:
    `remote-execution/SKILL.md`'s own containment rule (only one named
    adapter file may name a remote service) is about *where* a service name
    may be written, not whether the forge may know one exists at all — a
    fixed forge-owned rung vocabulary would not by itself violate that rule.
    This module still declares no rung name of its own, because a repository
    that never sends work anywhere still has a ladder (its own, possibly a
    single rung), and one fixed forge-wide vocabulary would not fit it — the
    same generality `SEARCH_DECLARATION` and `WITNESS_KINDS` already keep for
    their own vocabularies. See `level_index`'s own docstring in
    `impl_position.py` for the arithmetic this ladder feeds.

    A value of any shape other than a list is read as nothing declared
    (`[]`), the same silent-rather-than-crashing rule `declared_dimension_names`
    already applies to a `DIMENSIONS` bound to something other than a dict.
    """
    package = package_name(name)
    bench_root = target / "src" / f"{package}_Benchmark"
    if not bench_root.is_dir():
        return []
    for candidate in ("__init__.py", "config.py"):
        result = read_declaration(bench_root / candidate, LEVELS_DECLARATION)
        if isinstance(result, list):
            return [str(level) for level in result]
        if result is not None:
            return []
    return []


#: A third top-level literal, held apart from `__benchmark__` for the same
#: reason `LEVELS_DECLARATION` is: `step` names a callable to RUN, not
#: something `resolve_benchmark_declaration`'s seven-block "declared"/
#: "undeclared" verdict is about, and `_declaration_is_blank` must never
#: learn an eighth shape to compare against.
STEPS_DECLARATION = "__steps__"


def resolve_steps_declaration(target: Path, name: str) -> dict:
    """The `{name: {module, function}}` map `__steps__` names, or `{}` when
    nothing does.

    Read exactly the way `resolve_levels_declaration` reads `__levels__`
    (`__init__.py` first, then `config.py`, `ast`-only, no import) and held
    just as apart from `__benchmark__`: a target may declare a step long
    before it has answered a single one of `__benchmark__`'s seven blocks,
    or never answer any of them at all on a repository whose only work is
    local. Each entry carries the same `{module, function}` shape
    `__benchmark__["entry"]` already uses — mirrored on purpose, not shared,
    because a step and the harness entry are resolved by two different
    processes (this one, statically, for the name; the target's own
    interpreter, dynamically, for the callable) and a single shared literal
    would blur that split.

    A value of any shape other than a dict is read as nothing declared
    (`{}`), the same silent-rather-than-crashing rule
    `resolve_levels_declaration` already applies to a non-list `__levels__`.
    `cmd_step` is the only reader that ever inspects one entry's own shape
    (missing `module`/`function` is `STEP_MALFORMED`); this function only
    ever answers "declared, or not", never validates what it found.
    """
    package = package_name(name)
    bench_root = target / "src" / f"{package}_Benchmark"
    if not bench_root.is_dir():
        return {}
    for candidate in ("__init__.py", "config.py"):
        result = read_declaration(bench_root / candidate, STEPS_DECLARATION)
        if isinstance(result, dict):
            return result
        if result is not None:
            return {}
    return {}


#: A fourth top-level literal, held apart from `__benchmark__` for the
#: identical reason `STEPS_DECLARATION` is: a named record's own found/scale
#: state is measured by the `search`/`records` join (`named_records_state`),
#: never routed through `_declaration_is_blank`'s seven-block
#: "declared"/"undeclared" verdict.
RECORDS_DECLARATION = "__records__"


def resolve_records_declaration(target: Path, name: str) -> dict:
    """The `{name: {path, requiredScale}}` map `__records__` names, or `{}`
    when nothing does.

    Read exactly the way `resolve_steps_declaration` reads `__steps__`
    (`__init__.py` first, then `config.py`, `ast`-only, no import) and held
    just as apart from `__benchmark__`: a target may name a record long
    before it has answered a single one of `__benchmark__`'s seven blocks,
    or never answer any of them at all on a repository whose only leveled
    `@record:level` witness is the bare, operand-less one.

    A value of any shape other than a dict is read as nothing declared
    (`{}`), the same silent-rather-than-crashing rule
    `resolve_steps_declaration` already applies to a non-dict `__steps__`.
    This function only ever answers "declared, or not", never validates
    what one entry's own shape carries -- `named_records_state` is the one
    reader that opens an entry, and it reads defensively rather than
    trusting this resolver to have ruled on it.
    """
    package = package_name(name)
    bench_root = target / "src" / f"{package}_Benchmark"
    if not bench_root.is_dir():
        return {}
    for candidate in ("__init__.py", "config.py"):
        result = read_declaration(bench_root / candidate, RECORDS_DECLARATION)
        if isinstance(result, dict):
            return result
        if result is not None:
            return {}
    return {}


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

    Both assignment forms are read, for the reason `read_declaration` states
    in full: `DIMENSIONS: dict = {...}` is `ast.AnnAssign`, and a reader
    walking only `ast.Assign` answered `None` for it — "the universe could
    not be determined" over a file that determines it on the line being
    looked at. A bare `DIMENSIONS: dict` with no value binds nothing and is
    skipped.
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
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "DIMENSIONS" for t in node.targets
            ):
                value = node.value
            elif (isinstance(node, ast.AnnAssign)
                  and isinstance(node.target, ast.Name)
                  and node.target.id == "DIMENSIONS"):
                if node.value is None:
                    continue
                value = node.value
            else:
                continue
            if not isinstance(value, ast.Dict):
                continue
            return [key.value for key in value.keys
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


#: What `source_digest` compared, carried beside every status that depends on
#: it. `stale-sources` proves the tree moved since a notebook ran; it does NOT
#: prove the change touched anything that notebook imports, because the
#: comparison never asked. Two notebooks importing disjoint modules report this
#: identically, and a reader who saw them differ would infer a distinction the
#: digest never computes.
DIGEST_SCOPE = (
    "every .py under src/, never this notebook's own import closure: a "
    "stale-sources status proves the tree moved since this notebook ran, not "
    "that this notebook's own claims are affected. Clearing it means "
    "re-executing the notebook -- re-running the stamp cell alone would print "
    "a current digest over outputs that were never re-run."
)


def source_digest(target: Path, package: str) -> str:
    """One hash over everything a report's claims depend on.

    Modification times cannot serve here: a clone rewrites all of them with the
    checkout time and the ordering is gone. Content can, and the skill already
    settles the same question this way for the revision behind an admissibility
    ruling — the ruling stores the revision's digest and `verify` recomputes it.

    Sibling to `suite_digest`, below, and never merged into it: this answers
    whether a REPORT speaks for the code that produced it (`src/` alone); a
    suite run additionally depends on `tests/` and the environment
    declaration, which is exactly what `suite_digest` covers instead.
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
    # Two further attempts are recorded here so a fourth is refused by reading
    # rather than rediscovered by trying.
    #
    # A stamper lives in every target, not here. Eighteen copies of
    # `report_digest.py` sit under `implementations/` -- one in the product's
    # own `src/`, seventeen frozen inside shard clones. Changing the algorithm
    # in the forge moves the VERIFIER and never those stampers, so every
    # notebook of every existing product would read `stale-sources` at once:
    # the defect under repair, in every product at once. Two locks hold that
    # boundary -- a pinned literal digest and a whole-AST comparison against a
    # source -- and the lock test states the mechanism itself.
    #
    # And `stamp()` once demanded arguments. The first notebook that did not
    # use exactly the same names as the rest failed to stamp and was reported
    # stale. A per-notebook digest needs the stamp to know which notebook
    # prints it, which is that same failure wearing a new name.
    #
    # `package` no longer selects what is covered. It stays in the signature
    # because the two halves must be callable alike — see `report_digest.py` in
    # the kit, which the forge tests against this one over the same tree.
    #
    # NOT `suite_digest`, below, and never merged into it: this answers
    # whether a REPORT speaks for the code that produced it; `suite_digest`
    # answers whether a SUITE RUN witnessed the code, tests, and environment
    # declaration as they stand now. Folding the two into one function would
    # make either caller pay for a scope it never asked for — a notebook
    # report never reads `tests/`, and a suite run always does.
    root = target / "src"
    if root.is_dir():
        for file in sorted(root.rglob("*.py")):
            if "__pycache__" in file.parts:
                continue
            digest.update(str(file.relative_to(target)).encode("utf-8"))
            digest.update(file.read_bytes())
    return digest.hexdigest()


#: Five Python-ecosystem-standard, target-agnostic manifest paths
#: `suite_digest` folds in beside `src/` and `tests/` -- no target's own
#: vocabulary is read here, the same discipline `WITNESS_KINDS`
#: (`impl_position.py`) keeps one level down for evidence classes. Each is
#: folded through `impl_position.current_file_digest`/`ABSENT_FILE_DIGEST`,
#: never a branching skip, so a manifest declared later moves the digest
#: exactly as one edited does.
SUITE_ENVIRONMENT_MANIFESTS = (
    "requirements.txt", "pyproject.toml", "setup.cfg", "tox.ini", "pytest.ini",
)


def suite_digest(target: Path) -> str:
    """One hash over everything a `step`'s suite run depends on: `src/`,
    `tests/`, and the environment declaration that decides what runs
    against them.

    **Deliberately not `source_digest`, above, and never merged into it.**
    `source_digest` answers "does this report speak for the code that
    produced it" and is scoped to `src/` alone by hard-won incident (its own
    docstring: pulling in `tests/` marked every notebook report stale the
    moment any test changed at all, with no notebook ever importing
    `tests/`). `suite_digest` answers the opposite-shaped question -- "did
    the suite that just ran witness the code, the tests, and the
    environment declaration as they stand now" -- and a suite run DOES
    depend on `tests/`, so the two functions cannot share a scope without
    one of them paying for a boundary it never asked for.

    Walks `*.py` under both `src/` and `tests/` -- `unparsable_tests`'s own
    `rglob("*.py")`, not `test_function_names`'s narrower `test_*.py`.
    Measured: the narrower glob excludes `conftest.py`, which a suite run
    depends on exactly as much as any `test_*.py` file it collects fixtures
    for. `__pycache__` is skipped, the same exclusion `source_digest` keeps.
    Then folds in `SUITE_ENVIRONMENT_MANIFESTS`, each through
    `impl_position.current_file_digest`/`ABSENT_FILE_DIGEST` -- one
    `is_file()` test producing a value whether the file exists or not,
    never a branching skip, so declaring a manifest later moves this digest
    exactly as creating any other tracked file does.
    """
    digest = hashlib.sha256()
    for subdir in ("src", "tests"):
        root = target / subdir
        if root.is_dir():
            for file in sorted(root.rglob("*.py")):
                if "__pycache__" in file.parts:
                    continue
                digest.update(str(file.relative_to(target)).encode("utf-8"))
                digest.update(file.read_bytes())
    for name in SUITE_ENVIRONMENT_MANIFESTS:
        digest.update(name.encode("utf-8"))
        digest.update(
            impl_position.current_file_digest(target / name).encode("utf-8"))
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
        return {"status": "missing", "codeCells": 0, "unexecuted": [],
                "errors": [], "executedBy": None}
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"status": "unreadable", "detail": str(exc)[:160],
                "codeCells": 0, "unexecuted": [], "errors": [],
                "executedBy": None}

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

    # Which interpreter actually ran this, in the notebook's own words.
    # `metadata.language_info.version` is written by the kernel on execution
    # and reflects the process that ran the cells -- NOT the kernelspec the
    # file names, which is a label the launcher resolves at start time and
    # which routinely resolves somewhere else entirely (see
    # `notebooks_state`'s `interpreterMatch`). Measured by executing one
    # notebook twice through the same `jupyter nbconvert` and varying only
    # PATH: the field came back 3.12.13 and 3.9.6.
    language_info = (notebook.get("metadata") or {}).get("language_info")
    executed_by = None
    if isinstance(language_info, dict):
        version = language_info.get("version")
        if isinstance(version, str) and version.strip():
            executed_by = version.strip()

    if not code_cells:
        status = "empty"
    elif errors:
        status = "errored"
    elif unexecuted:
        status = "stale"
    else:
        status = "executed"
    return {"status": status, "codeCells": len(code_cells),
            "unexecuted": unexecuted, "errors": errors, "recordedDigest": recorded,
            "executedBy": executed_by}


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
    # No default, for the same reason: `_is_reporting_cell` is typed `str | None`
    # and answers `False` for anything falsy, so an undeclared record classifies
    # as "not a record cell" instead of as somebody else's filename.
    record_name = contract.get("record")

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

    `sourcesMatch` and `interpreterMatch` are two different questions and both
    have to be asked. The first is whether the notebook ran against this code;
    the second is whether it ran under the interpreter this skill's isolation
    rule requires — and the obvious way to execute a notebook gets the second
    one wrong silently. A kernelspec is a NAME the launcher resolves when the
    kernel starts, and the ordinary `python3` kernelspec's `argv` begins with a
    bare `python`, resolved off `PATH`. So running `<target>/.venv/bin/python
    -m jupyter nbconvert --execute` does not put that venv's `bin` on `PATH`
    and the cells run under whatever `python` was already first there. Measured
    on a real target: a suite passing 297/297 standalone produced fifteen
    failures inside the notebook, and nothing in the failure text named an
    interpreter. `interpreterMatch` is what makes that visible.

    It is REPORTED and never drifts `status` on its own. A wrong interpreter is
    not a wrong number — it is a reason to distrust the numbers, and which one
    of those a reader is looking at is exactly what a folded status destroys.
    `None` is unmeasured throughout: a notebook whose metadata names no version,
    or a target with no venv to compare against, has not been checked and never
    reads as checked.
    """
    root = target / name / "Notebooks"
    current = source_digest(target, package)
    interpreter_version = target_python_version(target)
    contract = report_contract(target, name)
    reports = []
    for notebook in sorted(root.glob("*.ipynb")) if root.is_dir() else []:
        state = notebook_execution(notebook)
        recorded = state.get("recordedDigest")
        if state["status"] == "executed" and recorded and recorded != current:
            state["status"] = "stale-sources"
        state["notebook"] = str(notebook.relative_to(target))
        state["sourcesMatch"] = None if not recorded else recorded == current
        state["interpreterMatch"] = (
            None if not interpreter_version or not state.get("executedBy")
            else state["executedBy"] == interpreter_version)
        # Static, and it never gates: it names the same fact `verify` and
        # `probe` echo, nowhere close to `status` above.
        state["coupling"] = notebook_coupling(notebook, contract)
        # The boundary travels WITH the status, where a reader meets it,
        # rather than in a docstring they will not open.
        state["digestScope"] = DIGEST_SCOPE
        reports.append(state)
    return {
        "sourcesDigest": current,
        # What the target's own interpreter is, beside the digest of its own
        # sources: the two facts every report below is measured against, said
        # once where a reader meets them rather than inferred from the
        # per-report verdicts.
        "interpreterVersion": interpreter_version,
        "reports": reports,
        # An executed report that ran under something other than the target's
        # own interpreter. Named for the same reason `unstamped` is: the
        # skill's isolation rule is the one rule nothing could check, so a
        # notebook that broke it looked exactly like one that kept it.
        # Reported, never gating -- see the docstring.
        "foreignInterpreter": [r["notebook"] for r in reports
                               if r["interpreterMatch"] is False],
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


def unparsable_tests(tests_dir: Path) -> list[str]:
    """Every file under `tests/` that does not survive `ast.parse`.

    A sibling rather than a change to the collector above, which keeps its
    signature and both of its callers: the invariant pairing reads a set of test
    names and has no business also carrying this.

    The collector swallows `SyntaxError` and moves to the next file, which is
    right for what it collects and silent about what it skipped — a directory
    holding one broken file returns exactly the empty set a directory holding
    one silent file returns. `read_provenance` already refuses that silence for
    modules, reporting an unparsable one as `__error__`; this was the last
    reader that did not. A file under `tests/` that cannot be parsed cannot be
    collected either, so the fact belongs in the report rather than in the gap
    between two readers.

    Paths are named as the target sees them, the way `strayModules` and
    `scaffoldGaps` name theirs.
    """
    if not tests_dir.is_dir():
        return []
    broken: list[str] = []
    for file in sorted(tests_dir.rglob("*.py")):
        try:
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (SyntaxError, UnicodeDecodeError):
            broken.append(str(file.relative_to(tests_dir.parent)))
    return broken


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def manifest_provisioning(target: Path) -> dict:
    """Which of the target's own declared manifests `env` will hand to pip.

    Every filename checked here is one `ROOT_KEEP` already enumerates — the
    forge names the manifest, never a package inside it. Two are honoured as
    `-r` requirement files, an editable install is added when a build
    descriptor exists, and `environment.yml` — a conda manifest a venv cannot
    read — is named `unhonoured` with its reason rather than passed over in
    silence. An empty `rows` still carries `absentNote`, so "checked and found
    nothing" cannot be mistaken for "never checked".
    """
    rows: list[dict] = []
    args: list[str] = []
    for candidate in ("requirements.txt", "requirements-dev.txt"):
        path = target / candidate
        if path.exists():
            rows.append({"name": candidate, "status": "honoured"})
            args += ["-r", str(path)]
    if any((target / marker).exists()
           for marker in ("pyproject.toml", "setup.py", "setup.cfg")):
        found = next(marker for marker in ("pyproject.toml", "setup.py", "setup.cfg")
                     if (target / marker).exists())
        rows.append({"name": found, "status": "honoured"})
        args += ["-e", str(target)]
    if (target / "environment.yml").exists():
        rows.append({
            "name": "environment.yml", "status": "unhonoured",
            "reason": "a conda manifest; the venv this flow provisions installs "
                      "with pip and cannot read it",
        })
    result = {"rows": rows, "args": args}
    if not rows:
        result["absentNote"] = (
            f"{target} declares no manifest among {sorted(ROOT_KEEP & {'requirements.txt', 'requirements-dev.txt', 'pyproject.toml', 'setup.py', 'setup.cfg', 'environment.yml'})}"
            "; nextCommand installs only the forge's own dev requirements"
        )
    return result


# The floor THIS skill's own layout templates need, independent of anything
# a target declares. `--help` used to claim "The layout templates assume
# 3.10+" and nothing checked it: a 3.9.6 interpreter built a venv and
# reported `status: "created"` with no warning at all.
SKILL_PYTHON_FLOOR: tuple[int, int] = (3, 10)

_VERSION_NUMBER_RE = re.compile(r"(\d+)\.(\d+)")


def _parse_python_version(text: str) -> tuple[int, int] | None:
    """The `(major, minor)` pair out of a `python --version` style report
    (`"Python 3.12.13"`) or a PEP 440 lower-bound specifier (`">=3.11"`) --
    the same shape either way, just the first `X.Y` this finds.
    """
    match = _VERSION_NUMBER_RE.search(text)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)))


def _target_declared_python_floor(target: Path) -> tuple[int, int] | None:
    """The target's own declared `python_requires` LOWER bound, read from
    `setup.cfg` (`[options] python_requires`) or `pyproject.toml`'s PEP 621
    `requires-python`, whichever exists — `None` when neither declares one.
    Only the lower bound is read; an upper bound or an exclusion range is
    not this skill's concern, only "how low can the interpreter go".
    """
    setup_cfg = target / "setup.cfg"
    if setup_cfg.is_file():
        import configparser

        parser = configparser.ConfigParser()
        try:
            parser.read_string(setup_cfg.read_text(encoding="utf-8"))
            requires = parser.get("options", "python_requires", fallback=None)
        except configparser.Error:
            requires = None
        if requires:
            parsed = _parse_python_version(requires)
            if parsed is not None:
                return parsed
    pyproject = target / "pyproject.toml"
    if pyproject.is_file():
        match = re.search(
            r'requires-python\s*=\s*"[^"]*?(\d+\.\d+)',
            pyproject.read_text(encoding="utf-8"),
        )
        if match:
            parsed = _parse_python_version(match.group(1))
            if parsed is not None:
                return parsed
    return None


def _python_floor(target: Path) -> tuple[tuple[int, int], str]:
    """The EFFECTIVE floor: the higher of this skill's own floor and the
    target's declared one, with a source label naming which one won —
    `Refused` must be able to name both the floor and its source, never
    just a bare version number a reader has to guess the origin of.
    """
    declared = _target_declared_python_floor(target)
    if declared is not None and declared > SKILL_PYTHON_FLOOR:
        return declared, "target declaration"
    return SKILL_PYTHON_FLOOR, "skill default"


def _probe_python_version(python: str) -> tuple[int, int] | None:
    """`<python> --version`, `shell=False` with a list argv exactly like the
    `venv` invocation below — no string interpolation, so a `--python`
    value containing shell metacharacters is passed as one literal argv
    element and fails as a missing executable, never as a shell expansion.
    `None` when the interpreter cannot even be launched; that failure
    surfaces at the real `venv` invocation, never invented here.
    """
    try:
        proc = subprocess.run([python, "--version"], capture_output=True, text=True)
    except OSError:
        return None
    return _parse_python_version(proc.stdout or proc.stderr)


def _refuse_if_below_floor(
    version: tuple[int, int] | None, floor: tuple[int, int], source: str,
) -> None:
    if version is None or version >= floor:
        return
    raise Refused(
        "PYTHON_BELOW_FLOOR",
        f"interpreter reports Python {version[0]}.{version[1]}, below the "
        f"effective floor {floor[0]}.{floor[1]} ({source}). Provision a "
        f"newer interpreter with --python.",
    )


def cmd_env(args: argparse.Namespace) -> dict:
    require_non_forge_interpreter()
    target = resolve_target(args.target)
    venv_dir = target / ".venv"
    floor, floor_source = _python_floor(target)
    interpreter = target_interpreter(target)
    pip = interpreter.parent / ("pip.exe" if os.name == "nt" else "pip")
    created = False
    if not (venv_dir / "pyvenv.cfg").exists():
        # Check site 1: BEFORE spending the work of building a venv from an
        # under-floor interpreter, which the reuse-path check below could
        # only ever discover AFTER — leaving a useless venv on disk.
        if args.python:
            _refuse_if_below_floor(_probe_python_version(args.python), floor, floor_source)
            proc = subprocess.run(
                [args.python, "-m", "venv", str(venv_dir)], capture_output=True, text=True,
            )
            if proc.returncode != 0:
                raise Refused("VENV_FAILED", proc.stderr.strip() or "venv creation failed")
        else:
            venv.EnvBuilder(with_pip=True, clear=False).create(venv_dir)
        created = True
        # Python 3.12 dropped setuptools from `ensurepip`: a fresh venv's
        # `pip` has no PEP 517 build backend at all, and `nextCommand`
        # below ends in an editable install (`pip install -e <target>`)
        # that needs exactly one. Measured: a freshly built 3.12 venv fails
        # that editable step with `BackendUnavailable: Cannot import
        # 'setuptools.build_meta'` while every non-editable requirement
        # installs fine — this venv promises a command it cannot run on its
        # own. Seeding here is what makes the promise true; existing venvs
        # on this machine already carry setuptools as a transitive build
        # dependency, so this is specific to a FRESH venv, not every venv.
        seed = subprocess.run(
            [str(pip), "install", "setuptools", "wheel"], capture_output=True, text=True,
        )
        if seed.returncode != 0:
            raise Refused(
                "VENV_FAILED",
                seed.stderr.strip() or "could not seed the build backend "
                "(setuptools, wheel) this venv's own nextCommand needs",
            )
    version = subprocess.run(
        [str(interpreter), "--version"], capture_output=True, text=True,
    ).stdout.strip()
    # Check site 2: AFTER the interpreter is known for certain — the reuse
    # path (`status: "present"`) never runs site 1 at all (nothing is built
    # on that path), so this is the only site that can see an EXISTING
    # under-floor venv, and it is the last check before this command would
    # otherwise report success.
    _refuse_if_below_floor(_parse_python_version(version), floor, floor_source)
    # One invocation, forge dev-reqs first and every honoured target manifest
    # last (Decision 8): joint resolution surfaces a real conflict as pip's own
    # error instead of a later, silently shadowed pin, and target-last means the
    # target's own pins are what that conflict is reported against.
    manifests = manifest_provisioning(target)
    next_command = [str(pip), "install", "-r",
                    str(SKILL_ROOT / "assets" / "requirements-dev.txt"), *manifests["args"]]
    return {
        "command": "env",
        "target": str(target),
        "status": "created" if created else "present",
        "pythonVersion": version,
        "interpreter": str(interpreter),
        "pip": str(pip),
        "nextCommand": " ".join(next_command),
        "manifests": manifests,
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
    _require_no_open_defect(target, name)
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
    name = validate_name(args.name)
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

    # Diagnostic and costless (design decision 7): a new report key, never a
    # gate on this command itself -- `handoff` reads the identical
    # `impl_position.open_defects` derivation `_require_no_open_defect`
    # refuses on, so a defect blocking `step`/`gate`/`offer`/`close`/
    # `settle`/`apply`/`admit` stays visible here rather than silent.
    ledger_path = target / name / ".implementation" / "position.jsonl"
    events = impl_position.read_events(ledger_path)
    open_defects = impl_position.open_defects(events, FORGE_ROOT)

    return {
        "command": "handoff",
        "target": str(target),
        "revision": args.revision,
        "status": "clear" if not inline and not deferred else "pending",
        "settleInline": inline,
        "deferToOwnSession": deferred,
        "alreadyAdopted": [i["id"] for i in settled],
        "openDefects": [{"file": e.get("file"), "session": e.get("session"),
                         "detail": e.get("detail"), "at": e.get("at")}
                        for e in open_defects],
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
    name = validate_name(args.name)
    _require_no_open_defect(target, name)
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


def _load_remote_execution_shard_io():
    """Path-import `shard_io.py`, and only that module.

    Loaded directly rather than reached through `_load_remote_execution_cli()`
    and its re-exported `SHARD_IO`. Reusing the already-authorized import would
    be one line shorter and would drag `jobfolder.py`, `adapter.py`,
    `packer.py`, `credentials.py` and a service-adapter dispatch surface into a
    read-only checker that runs on every target — including every target that
    sends work nowhere at all. `shard_io.py` is stdlib-only and names no
    service, and its own docstring says it is the half that belongs to a forge
    serving more than one paper.

    No `sys.modules` key, unlike the two loaders above. Both of those cache
    because a second, separately exec'd copy would hand back a class the
    `isinstance` and `except` clauses here could never match. `shard_io.py`
    defines no class and no exception at all — it is two functions over dicts —
    so that argument does not apply, and this is called at most once per
    process anyway.
    """
    spec = importlib.util.spec_from_file_location(
        "remote_execution_shard_io", REMOTE_EXECUTION_SHARD_IO_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
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


def _campaign_identity(target: Path, rcli) -> dict:
    """The campaign-identifying fact `propose` freezes into its own
    `campaign` field, and `_verify_gate_proposal` (below) re-derives fresh
    at every `gate` call to detect drift (design D4, `the-pilot-decides-
    the-remote-strategy`) -- the proposal's OWN staleness keys, structurally
    distinct from `_AUTHORIZATION_BINDING_KEYS`' seven original ones (never
    `entrypoint`, never `positionStatus`; a single job's transient failure
    moves neither `commit` nor `jobSet` here, which is the whole retry
    guarantee).

    `jobSet` -- every job name `_discovered_job_folders()` currently finds,
    sorted for determinism -- moves the moment a job folder is added or
    removed, exactly the second half of the design's own stated trigger.

    `commit` -- the single pin every discovered job folder's own
    `run-config.json` currently agrees on, or `None` when they disagree.
    `None` is a reported fact, never a picked winner: two genuinely
    different disagreeing states could otherwise be flattened onto the
    same fabricated value and compare equal by accident. `None` never
    does that -- an unchanged disagreement re-derives the identical `None`
    both times, and only an actual disk change (a job's declared commit
    moving, or a job folder appearing/disappearing) ever moves this
    result at all.

    Never argv, never a second, independently-written copy: `propose` and
    `gate` both call this exact function over the SAME live disk state
    `_discovered_job_folders()` and `JOBFOLDER.read()` already expose
    elsewhere in this file, the same single-shared-rule discipline
    `impl_availability.launch_available` enforces one layer down.
    """
    job_names: list[str] = []
    commits: set = set()
    for job_dir in _discovered_job_folders(target, rcli):
        try:
            run_config = rcli.JOBFOLDER.read(job_dir).run_config
        except rcli.JOBFOLDER.JobFolderError:
            continue
        job_names.append(run_config.get("jobName", job_dir.name))
        commits.add(run_config.get("commit"))
    commit = next(iter(commits)) if len(commits) == 1 else None
    return {"commit": commit, "jobSet": sorted(job_names)}


def _proposal_digest(events: list, campaign: dict) -> str | None:
    """The digest of the NEWEST `proposal` event on this target's ledger
    whose OWN frozen `campaign` equals `campaign` -- the CURRENT, freshly
    re-derived `_campaign_identity()` -- or `None` when none does (design
    D4, "the digest of the newest proposal event ... whose campaign
    identity matches"). Read only by `_authorization_binding` (offer/mint
    time), to bind a freshly minted token to whichever campaign proposal
    is CURRENTLY live for this target -- never filtered by job name: a
    campaign proposal covers every job it names, and every one of those
    jobs' tokens bind to the SAME proposal, the same way `gate --unit`
    already authorizes the whole campaign rather than one job's slice of
    it. A job the bound proposal does NOT name is exactly what
    `GATE_PROPOSAL_MISMATCH` (below) exists to catch -- not filtered out
    here, or that refusal would never be reachable.

    Filtering by CURRENT campaign match (not merely "the newest proposal,
    period") also means a token is never minted against a proposal that
    is ALREADY stale the instant it is minted: if disk has drifted since
    the newest proposal was published, this returns `None` for that
    proposal (it is not the CURRENT campaign any more) rather than
    binding a token that would fail `GATE_PROPOSAL_STALE` before ever
    being presented once.

    `_verify_gate_proposal` (gate/verify time, below) never calls this: it
    looks the proposal event up by the token's OWN recorded digest instead,
    never re-derives a fresh one -- a token minted against a given
    proposal stays checked against exactly that proposal, never silently
    upgraded to a newer one. That is what keeps a same-campaign retry
    (spec "proposal survives a same-campaign retry") working with no
    re-propose: the bound proposal digest never moves under a token that
    has not been re-minted, even though a FRESH mint (a retry's `offer`
    call) would resolve to the identical digest again as long as the
    campaign identity has not moved.
    """
    for event in reversed(events):
        if event.get("kind") == "proposal" and event.get("campaign") == campaign:
            return event.get("digest")
    return None


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

    **`accelerator`/`localBudget`, read out of the same open `run_config`
    this loop already holds** (design D3, `the-pilot-decides-the-remote-
    strategy`): both are optional, additive blocks `jobfolder.
    build_run_config()` writes only when the target declared them, and
    both are carried through verbatim — `None` when absent, never a
    default. This is the one and only place either is read for
    `classify_remote_necessity()` (`impl_execution_strategy.py`); no
    caller opens `run-config.json` a second time to get them.

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
                "accelerator": None,
                "localBudget": None,
            })
            continue

        run_config = job_folder.run_config
        job_name = run_config.get("jobName", job_dir.name)
        product = run_config.get("product")
        # Read out of the SAME open `run_config` this loop already holds
        # (design D3, `the-pilot-decides-the-remote-strategy`): never a
        # second `JOBFOLDER.read()`. Both are additive, optional blocks
        # `jobfolder.build_run_config()` writes only when the target
        # declared them; absent here, exactly as they are absent there.
        jobs.append({
            "job": job_name,
            "product": product,
            "staleness": dict(job_folder.staleness),
            "accelerator": run_config.get("accelerator"),
            "localBudget": run_config.get("localBudget"),
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


def _now_iso8601() -> str:
    """UTC, exactly the shape `remote-execution/scripts/ledger.py`'s own
    `_now()` already writes (`time.strftime(..., time.gmtime())`, line 117)
    — one format for "when" across the forge, not a second one this file
    invents beside it.
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _resolve_shard_evidence(
        target: Path, name: str, contract: dict,
        shards_root: str | None) -> tuple[list | None, list | None]:
    """`(shardsArrived, shardsCurrent)` for any caller that needs the
    identical answer `_position_write_evidence` derives -- factored out so
    `cmd_probe`, the one reader of a `@shard` witness that never routed
    through that function, computes this the same way rather than its own,
    permanently-`None` copy.

    `shards_root`, when given, is the caller's own explicit override --
    `position`/`verify`'s own `--shards` flag. `None` falls back to the
    target's own declared `distribution.shardsRoot` (`DISTRIBUTION_
    OPTIONAL`): a relative path is resolved against `target`, cwd-
    independent by construction, unlike an explicit `--shards` value, which
    `Path()` reads exactly as typed. Neither declared: both `shards_arrived`
    and `shards_current` stay `None`, exactly as before this key existed.

    A shard location, once declared, is read by every caller equally --
    there is no second, narrower declaration for `probe` alone or `gate`
    alone. A repository names one directory; every reader compares against
    that same answer.
    """
    resolved_root = shards_root
    if resolved_root is None:
        declared = ((contract or {}).get("distribution") or {}).get("shardsRoot")
        if isinstance(declared, str) and declared:
            candidate = Path(declared)
            resolved_root = str(candidate if candidate.is_absolute()
                                else target / candidate)
    if not resolved_root:
        return None, None
    shard_io = _load_remote_execution_shard_io()
    shards = shard_io.read_shards(Path(resolved_root))
    shards_arrived = [entry["shard"] for entry in shards]
    # The same currency read `verify --shards` makes, computed the same way
    # from the same two inputs. A writer that skipped it would tick a
    # `@shard` witness on a shard that arrived from code the repository has
    # since moved past -- and `position` is the one command that writes
    # those marks down, so the reader would then be trusting a mark the
    # writer had never checked.
    shards_current = _shards_current(
        shards, (contract or {}).get("distribution") or {},
        source_digest(target, package_name(name)))
    return shards_arrived, shards_current


def _skipped_rung_detail(
        items: list[dict], evidence: dict, levels: list[str],
        target_level: str) -> str | None:
    """Why this pass skips a rung, or `None` when it skips none: **to seal at
    rung N, every leveled item must already grade as satisfied at rung N-1.**

    Returns the refusal's detail rather than raising it, and the caller raises.
    `GatingRefusalRosterTests` walks a gating command's own body for the
    `Refused` literals it carries, and a code raised one call deep in a helper
    is invisible to that walk -- so a rule this heavy would have entered the
    engine with nobody having classified it. The refusal is kept where the
    roster can see it; the reasoning is kept here, where it belongs.

    The three checks above this one ask whether a rung was named, whether the
    target declared it, and whether a leveled witness has a ladder to stand on.
    None of them asks whether the rung *below* the named one was ever reached,
    so a header could jump straight from the floor to the top of a target's own
    ladder -- and the rung being skipped is exactly the one whose whole purpose
    is proving the flow runs before anything is spent further up.

    **Derived from state, never from history.** The obvious rule -- "was there
    a prior pass at the rung below" -- reads the position ledger, and a target
    that has never run this command has no ledger at all: the check would pass
    vacuously on precisely the repositories it exists to stop, which is worse
    than no check, because it looks like one. So the question is put to the
    evidence instead, and put to it through `impl_position.derive` itself,
    re-graded at the previous rung rather than by a second arithmetic beside
    it: whatever "satisfied at rung N-1" means for a witness, it means the same
    thing here as it does when the mark is written.

    **Aim and attainment are two facts, and the header carries only the
    first.** `target=` states what a pass AIMS at, legitimately one rung above
    what has been reached -- otherwise no pass could ever climb. An earlier
    revision of this rule exempted any seal at or below the rung the header
    recorded, reading that field as what had already been REACHED and using it
    as a floor. Nothing ever lowered it, so a rung that outlived its evidence
    did not go stale: it switched this guard off for itself, permanently, and a
    switched-off guard is indistinguishable from a green one. The exemption now
    reads `impl_position.attained_level` -- the evidence's own answer -- and the
    header is not consulted here at all.

    Three boundaries, each of them a decision rather than a fallout:

    - **The first rung has no predecessor** (`target_index == 0`), so nothing is
      checked there. A repository where nothing has run yet must still be able
      to start, or the ladder has no bottom step. This is also what keeps the
      earlier revision's decision 2 alive under a rule that no longer reads the
      header: *`position` is the instrument that measures, and an instrument
      that refuses to take a reading because the reading is bad hides the
      regression it exists to report.* An operator whose evidence has collapsed
      is never cornered, because the floor is always sealable and demoting the
      header to it is the honest reading; and the refusal that sends them there
      names every item that came up short, so the regression is reported louder
      than the old exemption's silent success ever reported it.
    - **Where a pass came from is not consulted.** A retreat and a re-seal are
      seals like any other: landing on rung N asserts that N-1 is reached
      whether the pass climbed to N, stayed at N, or fell back to it. Only
      `target_level` and the evidence decide, so there is no direction a skip
      could be laundered through.
    - **Two-state items do not participate.** Their verdict is computed without
      the ladder and is identical at every rung (`derive`: `satisfied` *is*
      `derived` for them), so they carry no information about which rung was
      reached. Folding them in would refuse a legitimate advance because some
      unrelated boolean step is still open -- whole-sequence completeness
      wearing this rule's name. Their own ordering is already held, within a
      rung, by `impl_availability.launch_available`'s `SEQUENCE_NOT_REACHED`.
    - **An unmeasured leveled item is not attainment.** `satisfied is None`
      means nobody looked, and "we did not look" is not "it has been reached" --
      the same distinction `derive` keeps one level down by refusing to fold
      `None` into the floor rung. This is also what separates this rule from a
      cheaper one that merely counts positions on the ladder: a single-step
      advance is refused too when the step below it is not shown attained.

    A target that declares no ladder (`levels == []`) reaches none of this: it
    has no rungs, so it has no progression to enforce, and `level_index` would
    answer `None` for every name anyway.
    """
    target_index = impl_position.level_index(levels, target_level)
    if not levels or not target_index:
        # `not target_index` covers both `None` (a name off the ladder -- an
        # undeclared ladder cannot be climbed, and a declared one already
        # refused an unknown rung above) and `0` (the floor, which has no
        # predecessor to attain).
        return None
    attained = impl_position.attained_level(items, evidence)
    attained_index = impl_position.level_index(levels, attained)
    if attained_index is not None and target_index <= attained_index + 1:
        return None
    # Reached only when the rung directly below the aim is NOT attained, since
    # `attained_level` is by definition the highest rung every leveled item
    # grades satisfied at: `target_index > attained_index + 1` puts `previous`
    # strictly above it, and `attained is None` puts every rung above it. So
    # `short` is never empty here, and the sentence below never names an empty
    # set -- it is the same grading, re-read one rung down for the item names
    # the refusal has to carry.
    previous = levels[target_index - 1]
    graded = impl_position.derive(items, {**evidence, "targetLevel": previous})
    short = [(item, result) for item, result in zip(items, graded)
            if not result["twostate"] and result["satisfied"] is not True]
    named = "; ".join(
        f"item {item['ordinal']} reached "
        + (f"{result['derived']!r}" if result["derived"] is not None
          else "nothing measurable")
        for item, result in short)
    return (
        f"--target-level {target_level!r} sits above {previous!r} on this "
        f"target's own declared ladder, and {previous!r} is not attained by "
        f"the evidence as it stands ({named}); the evidence currently attains "
        + (f"{attained!r}" if attained is not None else "no rung at all")
        + ". A position names the rung it aims at, and an aim reaches at most "
        "one rung above what is attained -- whichever rung the header happens "
        "to record now.")


def _step_operand_detail(items: list[dict], steps: dict) -> str | None:
    """Why an `@step` witness in this sequence cannot be measured, or
    `None` when every one names a step this target's own `__steps__`
    actually declares -- `_skipped_rung_detail`'s own shape, above, for the
    identical reason: returns the refusal's detail rather than raising it,
    so `POSITION_STEP_UNKNOWN` stays visible to `raised_refusal_codes` at
    the one call site (inside `cmd_position`) that raises it, not buried
    one call deep in a helper `GatingRefusalRosterTests`'s walk cannot see.

    `parse_items` (`impl_position.py`) validates only the witness KIND --
    that `"step"` is a member of `WITNESS_KINDS` -- never the operand
    string against this target's own declared steps. An `@step nosuch`
    item reaches here unblocked, and without this check would silently
    derive `unmeasured` forever (`_derive_step`'s own missing-operand
    branch), never telling anyone the name was never declared at all.

    Assumes `steps` is non-empty: the caller raises `STEPS_UNDECLARED`
    first (design "Second arm: reuse `STEPS_UNDECLARED` verbatim") when it
    is not -- the identical fact `cmd_step` itself already raises that
    code for, no new classification needed.
    """
    unknown = sorted({
        item["witness"]["operand"] for item in items
        if item["witness"]["kind"] == "step"
        and item["witness"]["operand"] not in steps})
    if not unknown:
        return None
    return (
        f"{unknown!r} names a step this target's __steps__ does not "
        f"declare ({sorted(steps)!r}); an `@step` witness must name one "
        "of them.")


def _record_operand_detail(items: list[dict], records: dict) -> str | None:
    """Why a leveled `@record:level <name>` witness in this sequence cannot
    be measured, or `None` when every one names a record this target's own
    `__records__` actually declares -- `_step_operand_detail`'s own shape,
    above, for the identical reason: returns the refusal's detail rather
    than raising it, so `POSITION_RECORD_UNKNOWN` stays visible to
    `raised_refusal_codes` at the one call site (inside `cmd_position`) that
    raises it, not buried one call deep in a helper `GatingRefusalRosterTests`'s
    walk cannot see.

    **One code covers two facts** (design D6): `__records__` declares
    nothing at all, and `__records__` declares others but not this name.
    `unknown` is built the identical way either way -- a name absent from
    `records` -- so no second code (a `RECORDS_UNDECLARED` mirroring
    `STEPS_UNDECLARED`) is needed; the detail below distinguishes the two
    readings for a human, the classification does not need to.

    Only a LEVELED `@record:level <name>` witness carrying a non-empty
    operand is checked here: a bare, operand-less `@record` (two-state, by
    `OPERAND_REQUIRED_KINDS`'s own exclusion) and a leveled `@record:level`
    with no operand at all (the grammar that predates `__records__`) still
    derive against the `search` block, unchanged -- this check has nothing
    to say about either one, the identical restraint `derive()`'s own
    record branch keeps (`impl_position.py`).
    """
    unknown = sorted({
        item["witness"]["operand"] for item in items
        if item["witness"]["kind"] == "record"
        and not item["witness"].get("twostate", True)
        and item["witness"]["operand"]
        and item["witness"]["operand"] not in records})
    if not unknown:
        return None
    if not records:
        return (
            f"{unknown!r} names a record, and this target's __records__ "
            "declares none at all; declare it there before a leveled "
            "`@record:level <name>` witness can address it.")
    return (
        f"{unknown!r} names a record this target's __records__ does not "
        f"declare ({sorted(records)!r}); a leveled `@record:level <name>` "
        "witness must name one of them.")


def _record_shape_detail(items: list[dict], records: dict) -> str | None:
    """Why an ADDRESSED `__records__` entry cannot be read at all, or `None`
    when every addressed one carries the shape `named_records_state`
    expects -- `_record_operand_detail`'s own shape, one question further in,
    and `cmd_step`'s `STEP_MALFORMED` one literal over.

    `POSITION_RECORD_UNKNOWN` above checks membership in the raw dict and
    nothing else, so a declared entry of ANY shape passes it. Two shapes
    reach here, and each fails a different way downstream:

    - **Not a mapping at all.** `named_records_state` skips it entirely, so
      `evidence["records"]` carries no entry for the name while the refusal
      above has already agreed the name is declared. The reader and the
      refusal disagree about the same name and nothing crosses them.
    - **A mapping with no usable `path`.** The entry survives, and
      `named_records_state` answers `recordFound: None` forever, since the
      only branch that can look at a file is guarded on `path` being a
      non-empty string.

    Either way a ticked witness becomes `POSITION_UNBACKED` and a leveled one
    derives no rung, sinking `attained_level` -- and neither says the
    declaration is the cause. `STEP_MALFORMED` already refuses exactly this
    for `__steps__`; there was no sibling here.

    **Only entries a witness in THIS sequence addresses**, the identical
    narrowing `cmd_step` keeps by refusing the step it was asked to run
    rather than auditing every `__steps__` entry. A repository may carry a
    half-written entry it has not wired a witness to yet, and refusing every
    position write until every entry is finished would be the forge deciding
    when a declaration is done.

    Returns the detail and never raises, for the reason
    `_record_operand_detail` states in full: a code raised one call deep in a
    helper is invisible to `raised_refusal_codes`' walk over the `cmd_*`
    body, so a refusal this heavy would enter the engine unclassified.
    """
    broken = []
    for operand in sorted({
            item["witness"]["operand"] for item in items
            if item["witness"]["kind"] == "record"
            and not item["witness"].get("twostate", True)
            and item["witness"]["operand"]
            and item["witness"]["operand"] in records}):
        entry = records[operand]
        if not isinstance(entry, dict):
            broken.append(
                f"{operand!r} is declared as {type(entry).__name__}, not a "
                "mapping: the reader that measures a named record skips a "
                "non-mapping entry entirely, so this name reads as declared "
                "here and as absent there")
        elif not isinstance(entry.get("path"), str) or not entry.get("path"):
            broken.append(
                f"{operand!r} declares no usable `path` (found "
                f"{entry.get('path')!r}, and the keys present are "
                f"{sorted(entry)!r}): without one, nothing can be looked "
                "for, and the witness derives unmeasured on every run")
    if not broken:
        return None
    return ("; ".join(broken) + ". A `@record:level <name>` witness "
            "addresses one __records__ entry, and an entry it cannot read "
            "is a declaration nobody can measure against.")


def _step_verdicts(target: Path, name: str) -> dict:
    """`evidence["stepVerdicts"]` for every caller that reads an `@step`
    witness -- `_position_write_evidence`, `cmd_probe`'s inline dict, and
    `cmd_verify`'s inline dict, the identical three-caller shape
    `_resolve_shard_evidence`, above, already keeps for `@shard`. Design
    "All three evidence builders share one fold": the proposal named only
    `_position_write_evidence`; wiring just that one function would leave
    `probe` and `verify` reporting `unmeasured` forever while `gate`
    reports satisfied -- two places disagreeing about "the suite is
    green", the same defect this codebase already refuses for a `@shard`
    witness read only through `probe`'s own, permanently-`None` copy.

    Folds `kind: "step"` events from `.implementation/position.jsonl`,
    latest wins by ledger order (later events override earlier ones for
    the same step name, never reordered by content). Short-circuits to
    `{}` when the ledger holds no `kind: "step"` event at all: a fresh
    `suite_digest(target)` is a real filesystem walk, and a target that
    never ran `step` has nothing here worth paying for it.

    **Digest is compared before outcome is read** (spec "The Ledger
    Carries Currency, Old Events Read Safely"): a latest event whose
    recorded `suiteDigest` no longer matches a fresh `suite_digest(target)`
    folds to `None` regardless of whether its `outcome` was `"returned"`
    or `"raised"` -- a stale measurement is unmeasured, never a `False`
    asserting the suite fails now about code nobody ran under. A
    pre-change event with no `suiteDigest` key at all reads identically:
    `.get("suiteDigest")` is `None`, which can never equal a real hex
    digest, so it folds to `None` exactly like a stale one -- never
    raising, never `True`. This function reads the ledger and compares
    digests; it does not itself decide what a `True`/`False`/`None`
    verdict MEANS to a witness -- that reading is `_derive_step`'s
    (`impl_position.py`), a plain dict reader one layer up.
    """
    events = impl_position.read_events(
        target / name / ".implementation" / "position.jsonl")
    step_events = [event for event in events
                  if event.get("kind") == "step" and event.get("step")]
    if not step_events:
        return {}
    latest: dict[str, dict] = {}
    for event in step_events:
        latest[event["step"]] = event
    live_digest = suite_digest(target)
    verdicts: dict[str, bool | None] = {}
    for step_name, event in latest.items():
        if event.get("suiteDigest") != live_digest:
            verdicts[step_name] = None
        elif event.get("outcome") == "returned":
            verdicts[step_name] = True
        elif event.get("outcome") == "raised":
            verdicts[step_name] = False
        else:
            verdicts[step_name] = None
    return verdicts


def _flow_steps(steps: dict) -> list[tuple[str, int]]:
    """The declared flow, in the order the target declared it: every
    `__steps__` entry carrying an integer `advances` ordinal, sorted by it.

    **An entry without an ordinal is outside the flow, and that is the
    target's own statement, not this reader's guess.** `cmd_step` runs such
    an entry ungated for exactly that reason -- "an ordering nobody declared
    is not one this command invents" -- so an entry that never claimed a
    position in the sequence cannot be a position the sequence is waiting on.
    Folding them in would report a finished flow unfinished forever, for
    every step a repository keeps beside the ordering rather than inside it.

    **A non-integer ordinal declares no position either.** `cmd_step` already
    refuses `STEP_MALFORMED` for one at the moment it would run; this reader
    never raises (it is called from three reporting paths), so it drops the
    entry rather than sorting a string against an int and crashing a command
    whose whole job is to report. `bool` is excluded even though
    `isinstance(True, int)` holds, the same shape defect `_numeric`
    (`impl_execution_strategy`) already refuses to read as a number.

    Ties break on the step's own name, so two entries claiming one ordinal
    still produce one deterministic order rather than a dict-insertion order
    that moves when the target's file is re-spelled.
    """
    ordered: list[tuple[str, int]] = []
    for step_name, entry in steps.items():
        if not isinstance(entry, dict):
            continue
        advances = entry.get("advances")
        if isinstance(advances, bool) or not isinstance(advances, int):
            continue
        ordered.append((step_name, advances))
    return sorted(ordered, key=lambda pair: (pair[1], pair[0]))


def pilot_completeness_state(steps: dict, sequence: list[dict],
                             evidence: dict) -> dict:
    """Whether the ordered flow this target declared has actually run at
    pilot -- `{"status", "steps", "incomplete"}`, and never a refusal.

    The measured defect this exists for: a target declaring six ordered steps
    had run the second of them and nothing else; six of its seven notebooks
    carried zero executed cells and zero outputs; and `probe` answered the
    rung that offers the declared scale anyway. That rung fires on "the search
    record is absent", which is a different fact from "the flow was validated
    at pilot", and the ladder was reading the wrong one. Nothing had been
    produced for anybody to read, and a question that offers the expensive run
    at that point is an invitation to say yes.

    Two facts per step, and only two:

    - **It ran and returned.** `@step <name>` is already the witness that
      reads exactly that (`impl_position._derive_step` over
      `evidence["stepVerdicts"]`, which `_step_verdicts` folds from the
      ledger and expires against a live `suite_digest`). `None` --
      never run, a stale digest, an event from before digests were
      recorded -- is "not shown", never a pass: the same refusal to fold
      unmeasured into attainment that `_skipped_rung_detail` states one
      rung up.
    - **The notebook it owes, when it owes one, is executed against these
      sources.** `@notebook <path>` is already the witness that reads exactly
      that (`status == "executed"` and `sourcesMatch is True`).

    **How the notebook is known, and why nothing new is declared for it.**
    The forge must never read the target's own Python to find which file a
    step executes. It does not have to: `advances` is the target saying which
    position item a step produces evidence for, and that item already names
    its own witness. So the notebook a step owes is the operand of the
    sequence item at that step's ordinal, whenever that item's witness kind is
    `notebook` -- a link the target already writes, in the vocabulary it
    already uses. A second declaration beside it would be one more thing that
    can disagree with the first.

    **Both halves are graded through `impl_position.derive`, never by a
    second arithmetic beside it** -- the discipline `_skipped_rung_detail`
    already keeps ("whatever satisfied means for a witness, it means the same
    thing here as it does when the mark is written"), and the same synthetic-
    item shape `cmd_discuss` already hands it. So this predicate can never
    disagree with what a tick in the sequence asserts.

    **Both probes are built two-state, however the sequence item declared
    itself, and that is the decision this rule turns on.** A leveled
    `@notebook` witness grades a RUNG, and every rung above the floor is
    evidence only a full-scale run can produce (`_derive_notebook_level`
    reads the record's own scale behind the report). Read that way a pilot
    could never complete, the rung waiting on completeness would never lift,
    and the flow would deadlock on the very evidence it is withholding
    permission to go and get. What a pilot genuinely produces is the
    executed-and-current fact, so that is what is asked for -- and because
    the probe carries `twostate: True`, `evidence["targetLevel"]` is never
    consulted for it at all.

    **An item whose witness is not a notebook adds nothing.** A `@record` or
    `@shard` witness is full-scale evidence by construction -- a record must
    meet its own declared scale, and a pilot campaign leaves no shard at all
    -- so demanding either here would deadlock the flow on evidence the pilot
    cannot produce. The step's own verdict is the whole predicate there.

    **A flow nobody declared is not an incomplete one.** `status` is
    `"undeclared"` when no entry carries an ordinal, and every caller reads
    that as "this rule does not apply" -- a target that never opted into an
    ordering keeps exactly the ladder it always had.

    Pure: no I/O, no filesystem walk, no ledger read. `steps` is
    `resolve_steps_declaration`'s own return, `sequence` is
    `position_state`'s, and `evidence` is the position evidence dict every
    caller already builds -- the same restraint `classify_remote_necessity`
    keeps, so two callers asking this question cannot answer it differently.
    """
    flow = _flow_steps(steps)
    if not flow:
        return {"status": "undeclared", "steps": [], "incomplete": []}
    by_ordinal = {item["ordinal"]: item for item in sequence
                  if isinstance(item.get("ordinal"), int)}
    rows = []
    for step_name, advances in flow:
        witness = (by_ordinal.get(advances) or {}).get("witness") or {}
        notebook = (witness.get("operand")
                    if witness.get("kind") == "notebook" else None)
        probes = [{"witness": {"kind": "step", "operand": step_name,
                               "twostate": True}, "mark": " "}]
        if notebook:
            probes.append({"witness": {"kind": "notebook", "operand": notebook,
                                       "twostate": True}, "mark": " "})
        graded = impl_position.derive(probes, evidence)
        ran = graded[0]["satisfied"]
        current = graded[1]["satisfied"] if notebook else None
        rows.append({
            "step": step_name, "advances": advances, "ran": ran,
            "notebook": notebook, "notebookCurrent": current,
            "complete": ran is True and (notebook is None or current is True),
        })
    incomplete = [row["step"] for row in rows if not row["complete"]]
    return {"status": "incomplete" if incomplete else "complete",
            "steps": rows, "incomplete": incomplete}


def _position_write_evidence(
        target: Path, name: str, shards_root: str | None = None) -> dict:
    """The same evidence shape `position_state` is handed through `probe`
    (2069-2075): search, its declared required scale, the notebooks, the
    jobs' `smokeReady`, and a shard answer whenever one is resolvable —
    either `shards_root` names one directly, or the target's own declared
    `distribution.shardsRoot` does (`_resolve_shard_evidence`).

    `discuss`, `gate` and `close` declare no `--shards` flag at all
    (`main()`, ~6333), so their callers always pass `shards_root=None` here
    — but that no longer means `@shard` reads `unmeasured` for them: once a
    target declares `shardsRoot`, this function resolves it for every one
    of them exactly as `position --shards <dir>` would have, and a tick
    written from real evidence stays checkable everywhere that evidence is
    read, not only at the one command that happened to carry the flag.
    `probe` reaches the identical answer through `_resolve_shard_evidence`
    directly, since it builds this evidence shape inline rather than
    calling this function (see that helper's own docstring for why).

    `position` is different: `main()` gives it `--shards` (~6320), and a
    caller MUST thread `getattr(args, "shards", None)` through here rather
    than let it fall back silently, or an explicit flag stops overriding
    anything — `_resolve_shard_evidence` only reaches for the declaration
    when `shards_root` itself is `None`, so a `--shards <dir>` passed here
    always wins, exactly as before this fallback existed (see
    `impl_position.derive`'s own docstring for why `None` must never become
    `False` instead).
    """
    resolved = resolve_benchmark_declaration(target, name)
    report = report_state(target, name, package_name(name))
    search = search_state(
        resolved["contract"],
        list((report.get("declared") or {}).get("records") or []),
        target / name, declaration_status=resolved["status"],
        digest=source_digest(target, package_name(name)))
    shards_arrived, shards_current = _resolve_shard_evidence(
        target, name, resolved["contract"], shards_root)
    # One call, both fields read from it (design D3): `cmd_gate` needs the
    # SAME `jobs` rows `probe` classifies from, never a second walk of
    # `_discovered_job_folders()` computing its own answer.
    jobs = remote_execution_jobs_state(target)
    digest = source_digest(target, package_name(name))
    return {
        "search": search, "requiredScale": declared_required_scale(search),
        "notebooks": notebooks_state(target, name, package_name(name)),
        "smokeReady": jobs["smokeReady"],
        "jobs": jobs["jobs"],
        "shardsArrived": shards_arrived,
        "shardsCurrent": shards_current,
        "levels": resolve_levels_declaration(target, name),
        "stepVerdicts": _step_verdicts(target, name),
        # Design B5 (evidence wiring is three sites): the same
        # `named_records_state` call `cmd_probe`'s and `cmd_verify`'s own
        # inline evidence dicts make below, so a `@record:level <name>`
        # witness reads the identical answer wherever it is measured.
        "records": named_records_state(
            target, name, resolve_records_declaration(target, name), digest),
    }


#: What a freshly discovered, never-agreed-on step's item text reads until a
#: human writes the real sentence. The tool names no content for a step it
#: only found on disk: deciding what a step MEANS is the discussion's job,
#: never `--reconcile`'s (design §3.3, "the tool never writes a sentence
#: about what a step means").
POSITION_PLACEHOLDER_TEXT = "TODO: describe this step."


def _chosen_holder(target: Path, name: str, product: Path) -> Path:
    """Which markdown file receives a FRESH block, chosen from
    `agreements_state`'s own already-computed `holders` — never a fixed
    filename, and never a guess between two candidates.

    Shared by `--sequence`'s fresh install and `--reconcile`'s fresh
    reconstruction: both write into a product folder that carries no
    position block yet, and both refuse the identical way when there is
    nothing to append into, or more than one candidate to choose from
    (`agreements_state`'s own doctrine that the tool never invents a
    checklist file, 140-145).
    """
    holding = [target / h for h in agreements_state(target, name)["holders"]]
    if not holding:
        raise Refused(
            "POSITION_HOLDER_ABSENT",
            f"no markdown file under {product.relative_to(target)}/ holds "
            "checklist items; the position section is never written into "
            "a file this command invents.")
    if len(holding) > 1:
        raise Refused(
            "POSITION_HOLDER_AMBIGUOUS",
            f"{len(holding)} markdown files under {product.relative_to(target)}/ "
            "hold checklist items and none yet carries a position block; "
            "which one should receive it is not decidable without a human "
            "choosing.")
    return holding[0]


def _reconcile_discovered_witnesses(target: Path, name: str, args: argparse.Namespace) -> list:
    """Every witness `--reconcile` can build from what the target already
    has, in the order design §3.3 names them: the declared `@record`, one
    `@rehearsal` per discovered job folder, one `@notebook` per
    `Notebooks/*.ipynb` in name order, one `@shard` per arrived shard when
    `--shards` is given.

    Every source read here is one `_position_write_evidence` (or `verify`'s
    own `--shards` handling) already measures against, on purpose: a step
    reconciliation discovers is a step the very next `verify` can actually
    derive a tick for, which is what keeps a reconciled target from reading
    mostly `unmeasured` (design §11's falsifier).

    Every discovered witness is two-state (`"twostate": True`), the same
    default the markdown grammar itself keeps: reconciliation discovers
    *that a step exists*, never what a human means by it, and a leveled
    reading is a decision only a human declaring `:level` on the item text
    afterward can make (design §3.3, "the tool never writes a sentence
    about what a step means" -- the same restraint extended to whether a
    step has rungs at all).
    """
    product = target / name
    witnesses: list[dict] = []

    resolved = resolve_benchmark_declaration(target, name)
    if (resolved["contract"].get("search") or {}).get("record"):
        witnesses.append({"kind": "record", "operand": None, "twostate": True})

    rcli = _load_remote_execution_cli()
    for job_dir in _discovered_job_folders(target, rcli):
        try:
            job_name = rcli.JOBFOLDER.read(job_dir).run_config.get(
                "jobName", job_dir.name)
        except rcli.JOBFOLDER.JobFolderError:
            job_name = job_dir.name
        witnesses.append({"kind": "rehearsal", "operand": job_name, "twostate": True})

    notebooks_root = product / "Notebooks"
    if notebooks_root.is_dir():
        for notebook in sorted(notebooks_root.glob("*.ipynb")):
            witnesses.append({"kind": "notebook",
                              "operand": str(notebook.relative_to(product)),
                              "twostate": True})

    shards_root = getattr(args, "shards", None)
    if shards_root:
        shard_io = _load_remote_execution_shard_io()
        for entry in sorted(shard_io.read_shards(Path(shards_root)),
                            key=lambda e: e["shard"]):
            witnesses.append({"kind": "shard", "operand": entry["shard"], "twostate": True})

    return witnesses


def cmd_position(args: argparse.Namespace) -> dict:
    """The only writer into `<Name>/AGREED.md`'s position section.

    Three write modes:

    **No flag — REFRESH.** The block already there has its marks re-derived
    against current evidence and nothing else about it changes: not the
    item text, not their order, not which witness each one names. Only
    `mark` is ever mutated in place, so byte preservation of everything
    else follows from never touching it, the same discipline `splice`
    documents for the bytes around the block.

    **`--sequence` — INSTALL.** A fresh, ordered sequence read from stdin
    JSON (`- to read stdin`, the convention `cmd_compose`'s `--entry-text`
    already uses) becomes the block. Refused as `POSITION_BLOCK_EXISTS`
    unless `--replace` says the caller means to overwrite what is there.
    The declared `{text, witness}` pairs are round-tripped through
    `render()` + `parse_items()` immediately rather than trusted as typed:
    the same grammar that validates a hand-authored block validates one
    this command is about to write, so a malformed `--sequence` is refused
    here rather than surfacing later at the next `verify`.

    **`--reconcile` — RECONSTRUCTION.** Builds a sequence from what the
    target already has (`_reconcile_discovered_witnesses`) and merges it
    with whatever block already exists, **by witness identity**
    (kind+operand): an existing item keeps its text and its order exactly,
    and only a witness with no match among the existing items is appended,
    with `POSITION_PLACEHOLDER_TEXT` standing in for the sentence a human
    has not written yet. Safe to run repeatedly — a second `--reconcile`
    against an unchanged target appends nothing (spec "Reconstruction From
    an Existing Target").

    **The holder, found by shape for a refresh or a reconcile against an
    existing block** — exactly `position_state`'s own rule (`>1 candidate
    carrying a block` is `POSITION_HOLDER_AMBIGUOUS`, the same code,
    because a delimiter this module owns appearing twice is an ambiguous
    document regardless of which command is reading it). **For a fresh
    install or a fresh reconcile**, chosen by `_chosen_holder`.

    **`status: "unchanged"` skips the write entirely.** Comparing the
    complete item list — witness, text, mark, and count — old vs new, plus
    `(revision, revisionSha256, targetLevel)`, but never `derivedAt`, which
    would differ on every single call and defeat the comparison: a refresh
    that finds nothing to flip and nothing to rebind, or a reconcile that
    discovers nothing new, leaves the file and the ledger untouched. Writing
    a fresh `derivedAt` over marks nobody re-measured would claim work
    happened that did not; `status: "written"` is reserved for a call that
    actually changed something. A fresh install is never `"unchanged"`: the
    block itself is new content, not a no-op, whatever its derived marks
    turn out to be.

    **`--target-level` (PR10, level grammar): the rung this pass is aiming
    at, sticky across a refresh.** Required only when there is no existing
    block to inherit one from; otherwise a caller that never restates it
    keeps whatever a prior write already recorded, the same way a bare
    refresh never asks a caller to retype item text nobody changed. Refused
    `POSITION_TARGET_LEVEL_UNKNOWN` when the target names something
    `__levels__` never declared, and `POSITION_LEVELS_UNDECLARED` when the
    sequence carries a `:level`-marked (leveled) witness but no ladder is
    declared at all. A mark then means "reached the
    level this pass asks for", read from `satisfied`, never `derived`
    directly — see `impl_position.derive`'s own docstring for the two-state
    vs leveled distinction a witness's `:level` marker declares.
    """
    if args.sequence is not None and args.reconcile:
        raise Refused(
            "POSITION_SEQUENCE_AND_RECONCILE",
            "--sequence installs an explicit sequence and --reconcile "
            "builds one from what the target already has; only one of the "
            "two names this call's sequence.")

    target = resolve_target(args.target)
    name = validate_name(args.name)
    product = target / name

    source = revision_source(args.revision)
    if source is None:
        raise Refused(
            "REVISION_UNREADABLE",
            f"{args.revision!r} is not readable under {FORGE_ROOT / 'proposals'}; "
            "the position header cannot be bound to a revision.")
    revision_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()

    # Found by shape, exactly like `agreements_state` and `position_state`:
    # every markdown file at the top of the product folder is a candidate,
    # never a fixed filename.
    md_files = sorted(p for p in product.glob("*.md") if p.is_file()) \
        if product.is_dir() else []
    # Explicit loop, not a comprehension over a fresh `path.read_bytes()`
    # per branch (design decision 2, "Capture"): `data` is bound exactly
    # once per candidate and BOTH the block search and the pre-image
    # digest read it back, so "the bytes a block's offsets were located
    # against" is literally the same object `holder_digests` records a
    # hash of -- never a second, later read that could already disagree.
    # A candidate that carries no block yet still gets a digest: a fresh
    # `--sequence`/`--reconcile` install may choose exactly such a file
    # below (`_chosen_holder`), and `write_spliced`'s own re-check needs a
    # pre-image for that path too.
    # `allow_legacy=True`: `position` is the one place a block written by
    # the prior boolean-only grammar can be seen at all, so it can be
    # rewritten -- see `locate_block`'s own docstring. `verify`/`probe`/
    # `position_state`'s read side pass no such flag and keep refusing.
    holder_digests: dict[Path, str] = {}
    holders_with_block = []
    for path in md_files:
        data = path.read_bytes()
        holder_digests[path] = impl_position.digest_bytes(data)
        block = impl_position.locate_block(data, allow_legacy=True)
        if block is not None:
            holders_with_block.append((path, block))
    if len(holders_with_block) > 1:
        raise Refused(
            "POSITION_HOLDER_AMBIGUOUS",
            f"more than one markdown file under {product.relative_to(target)}/ "
            "carries a `<!-- position -->` block; only one may hold the "
            "section this writes.")
    existing_path, existing_block = (
        holders_with_block[0] if holders_with_block else (None, None))

    # `target` is filled in below, once every branch has produced `items` and
    # the section is confirmed actually about to be measured or written (the
    # `existing_block is None` "nothing to refresh" branch returns before
    # ever needing one). `"__pending__"` here is a placeholder for the
    # `--sequence` branch's own round-trip validation `render()` call only,
    # which checks witness/item grammar, never a rung's legitimacy -- its
    # output is parsed straight back into `items` and the header itself is
    # discarded and rebuilt below with the real value.
    header = {"revision": args.revision, "revisionSha256": revision_sha256,
              "derivedAt": _now_iso8601(), "session": args.session,
              "target": "__pending__"}
    structure_changed = False

    if args.sequence is not None:
        if existing_block is not None and not args.replace:
            raise Refused(
                "POSITION_BLOCK_EXISTS",
                f"{existing_path.relative_to(target)} already carries a "
                "position block; pass --replace to overwrite it.")
        raw = sys.stdin.read() if args.sequence == "-" else args.sequence
        try:
            declared = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise Refused("POSITION_SEQUENCE_UNREADABLE",
                          f"--sequence is not valid JSON: {exc}") from exc
        if not isinstance(declared, list) or not declared:
            raise Refused("POSITION_SEQUENCE_EMPTY",
                          "--sequence must be a non-empty JSON array of "
                          "{text, witness} entries.")
        items = []
        for ordinal, entry in enumerate(declared, start=1):
            if not isinstance(entry, dict):
                raise Refused("POSITION_SEQUENCE_UNREADABLE",
                              f"--sequence[{ordinal - 1}] is not a mapping "
                              "of {text, witness}.")
            witness = entry.get("witness") or {}
            items.append({
                "ordinal": ordinal, "mark": " ",
                "text": str(entry.get("text", "")).strip(),
                "witness": {"kind": witness.get("kind"),
                           "operand": witness.get("operand"),
                           # Two-state unless the declared entry opts in --
                           # the same default the markdown grammar itself
                           # keeps (`WITNESS_RE`'s own docstring).
                           "twostate": bool(witness.get("twostate", True))},
            })
        # See docstring: validated by the reader that already validates a
        # hand-authored block, not by a second, parallel set of checks.
        rendered = impl_position.render(header, items)
        items = impl_position.parse_items(
            impl_position.locate_block(rendered.encode("utf-8"))["body"])
        target_path = existing_path or _chosen_holder(target, name, product)
    elif args.reconcile:
        existing = (impl_position.parse_items(existing_block["body"])
                   if existing_block else [])
        known = {(item["witness"]["kind"], item["witness"]["operand"])
                for item in existing}
        appended = []
        for witness in _reconcile_discovered_witnesses(target, name, args):
            key = (witness["kind"], witness["operand"])
            if key in known:
                continue
            known.add(key)
            appended.append({"mark": " ", "text": POSITION_PLACEHOLDER_TEXT,
                             "witness": witness})
        structure_changed = bool(appended)
        items = existing + appended
        for ordinal, item in enumerate(items, start=1):
            item["ordinal"] = ordinal
        target_path = existing_path or _chosen_holder(target, name, product)
    elif existing_block is None:
        # Nothing to refresh is a state, not a failure -- the same doctrine
        # `agreements_state` and `position_state` already report absence
        # with: a target whose flow never reached a gate has nothing to
        # record, and asking it to refresh reports that rather than refusing.
        return {
            "command": "position", "target": str(target), "name": name,
            "status": "absent", "holder": None, "wrote": [], "left": [],
            "unmeasured": [], "unbacked": [], "sequence": [],
            "revision": args.revision,
            "revisionSha256": revision_sha256, "targetLevel": None,
        }
    else:
        items = impl_position.parse_items(existing_block["body"])
        target_path = existing_path

    # PR10 (the-position-nobody-holds, level grammar): the rung this pass is
    # aiming at. `--target-level` is optional and sticky -- refreshing an
    # existing block reuses its own recorded target unless a caller
    # explicitly names a new one, the same way `--revision` is required on
    # every call but a bare refresh does not otherwise ask a caller to
    # restate facts a prior write already recorded. Only a genuinely fresh
    # header (no existing block to inherit one from) requires it explicitly.
    declared_levels = resolve_levels_declaration(target, name)
    target_level = getattr(args, "target_level", None) or (
        existing_block["target"] if existing_block is not None else None)
    if target_level is None:
        raise Refused(
            "POSITION_TARGET_LEVEL_REQUIRED",
            "no --target-level was given and no existing block's header "
            "names one to reuse; a fresh position header cannot be written "
            "without stating which rung this pass is aiming at.")
    if declared_levels and target_level not in declared_levels:
        raise Refused(
            "POSITION_TARGET_LEVEL_UNKNOWN",
            f"--target-level {target_level!r} is not one of this target's "
            f"own declared levels ({declared_levels!r}); __levels__ names "
            "the only vocabulary a header's target may use.")
    if not declared_levels and any(
            not item["witness"].get("twostate", True) for item in items):
        raise Refused(
            "POSITION_LEVELS_UNDECLARED",
            "a leveled (non-two-state) witness exists in this sequence but "
            "__levels__ declares no ladder; a rung cannot be reached "
            "against a ladder nobody named.")
    # Trap 1's verified placement (design D5): BEFORE `_skipped_rung_detail`
    # is ever called, and therefore before `evidence` is even built --
    # `_record_operand_detail` needs only `items` and this target's own
    # `__records__`. An unknown record name derives `None`
    # (`_derive_record_level`), which sinks `attained_level`; placed after
    # `_skipped_rung_detail` instead (mirroring `@step`'s own position,
    # which has no such trap because a two-state item never reaches
    # `attained_level`), `POSITION_RUNG_SKIPPED` would fire first for any
    # `--target-level` above the floor and this refusal would become
    # unreachable there -- reachable only at the floor, where
    # `_skipped_rung_detail` never intervenes regardless of order.
    declared_records = resolve_records_declaration(target, name)
    record_detail = _record_operand_detail(items, declared_records)
    if record_detail is not None:
        raise Refused("POSITION_RECORD_UNKNOWN", record_detail)
    # Immediately after the membership check and therefore still ahead of
    # `_skipped_rung_detail`, for the identical trap-1 reason (design D5): a
    # malformed entry derives `None` too, which sinks `attained_level`, so a
    # check placed after the rung guard would answer `POSITION_RUNG_SKIPPED`
    # first for any `--target-level` above the floor and be reachable only at
    # the floor. What reaches it: a name that IS a key of `__records__` -- or
    # the refusal above would have fired -- whose entry the reader cannot use.
    record_shape = _record_shape_detail(items, declared_records)
    if record_shape is not None:
        raise Refused("POSITION_RECORD_MALFORMED", record_shape)
    header["target"] = target_level

    evidence = _position_write_evidence(target, name, getattr(args, "shards", None))
    evidence["targetLevel"] = target_level
    # Read before a single mark is derived, and so before a single byte is
    # written: the three checks above decide whether the rung NAMED is a legal
    # name, and this one decides whether the rung is legally REACHABLE from
    # where the evidence currently stands.
    skipped = _skipped_rung_detail(
        items, evidence, declared_levels, target_level)
    if skipped is not None:
        raise Refused("POSITION_RUNG_SKIPPED", skipped)
    # `@step` operand validity, read fresh here rather than by `parse_items`
    # (which validates only the witness KIND, never this string): an unknown
    # step name must never silently derive `unmeasured` forever (spec
    # "Unknown Step Operand Is A Classified, Roster-Visible Refusal").
    steps = resolve_steps_declaration(target, name)
    if not steps and any(item["witness"]["kind"] == "step" for item in items):
        raise Refused(
            "STEPS_UNDECLARED",
            f"{name} declares no __steps__ at all; nothing here names a "
            "callable this command could run.")
    step_detail = _step_operand_detail(items, steps)
    if step_detail is not None:
        raise Refused("POSITION_STEP_UNKNOWN", step_detail)
    derived = impl_position.derive(items, evidence)
    wrote, left, unmeasured, unbacked = [], [], [], []
    for item, result in zip(items, derived):
        # Read off the mark as it stood on disk, BEFORE the loop below can
        # rewrite it. It never can, for exactly these items -- an unmeasured
        # witness is `continue`d over and its mark survives the refresh
        # untouched -- which is precisely why a tick here has to be named:
        # a refresh corrects a contradicted mark and leaves an unbacked one
        # exactly where it was.
        if result["unbacked"]:
            unbacked.append(item["ordinal"])
        if result["derived"] is None:
            unmeasured.append(item["ordinal"])
            left.append(item["ordinal"])
            continue
        # Tick decisions read `satisfied`, never `derived` directly: for a
        # two-state item the two are the same value, but for a leveled item
        # `derived` is the rung reached (a string) and `satisfied` is
        # whether that rung is at or above this pass's own target -- the
        # value that actually means "reached the level this pass asks for".
        new_mark = "x" if result["satisfied"] else " "
        if new_mark != item["mark"]:
            wrote.append(item["ordinal"])
        else:
            left.append(item["ordinal"])
        item["mark"] = new_mark

    unchanged = (
        args.sequence is None and not structure_changed
        and existing_block is not None
        and existing_block["revision"] == args.revision
        and existing_block["revisionSha256"] == revision_sha256
        and existing_block["target"] == target_level
        and not wrote
    )

    sequence = [{
        "ordinal": item["ordinal"], "mark": item["mark"],
        "witness": item["witness"], "text": item["text"],
        "derived": result["derived"], "twostate": result["twostate"],
        "satisfied": result["satisfied"], "disagrees": result["disagrees"],
        "unbacked": result["unbacked"],
    } for item, result in zip(items, derived)]

    if unchanged:
        return {
            "command": "position", "target": str(target), "name": name,
            "status": "unchanged",
            "holder": str(target_path.relative_to(target)),
            "wrote": [], "left": left, "unmeasured": unmeasured,
            "unbacked": unbacked,
            "sequence": sequence, "revision": existing_block["revision"],
            "revisionSha256": existing_block["revisionSha256"],
            "targetLevel": target_level,
        }

    before_bytes = target_path.read_bytes() if target_path.exists() else b""
    new_block = impl_position.render(header, items).encode("utf-8")
    spliced = impl_position.splice(before_bytes, new_block, existing_block)
    # The pre-image digest captured at the SAME read that located
    # `existing_block`'s own offsets above -- never a digest of
    # `before_bytes`, which is itself a second, later read and exactly
    # the read a stale-offset corruption would have already used. A
    # candidate `write_spliced` never saw during the holder search (a
    # brand-new file `_chosen_holder` could in principle name) falls back
    # to the empty digest, matching `write_spliced`'s own absent-path rule.
    impl_position.write_spliced(
        target_path, spliced,
        expect_digest=holder_digests.get(target_path, impl_position.digest_bytes(b"")))
    impl_position.append_event(
        product / ".implementation" / "position.jsonl",
        {"kind": "position", "session": args.session, "revision": args.revision,
         "revisionSha256": revision_sha256, "targetLevel": target_level,
         "holder": str(target_path.relative_to(target)),
         "wrote": wrote, "left": left, "at": header["derivedAt"]})

    return {
        "command": "position", "target": str(target), "name": name,
        "status": "written", "holder": str(target_path.relative_to(target)),
        "wrote": wrote, "left": left, "unmeasured": unmeasured,
        "unbacked": unbacked,
        "sequence": sequence, "revision": args.revision,
        "revisionSha256": revision_sha256, "targetLevel": target_level,
    }


def _agreement_collides(target: Path, name: str, operand: str | None) -> list[str]:
    """Every existing checklist item, anywhere in the product folder's
    markdown, whose text names the same operand this witness does.

    Computed fresh on every call, over `AGREEMENT_LINE`/`AGREEMENTS_GLOB`
    directly -- never through `agreements_state`, which collapses a
    settled item down to a bare count and keeps only an open item's text.
    A collision search needs the text of every item, settled or not, so it
    reads the files itself rather than asking a function that already threw
    half of them away.

    Both this function and `agreements_state` now read through the same
    `_agreement_scan_text` excision, so an item's own located line, inside
    a position block, is never scanned here either -- the self-match a
    caller `--about`-ing its own sequence item used to get, measured with
    a fixture whose operand is a substring of its own rendered witness
    token. Reading through the shared excision, not calling
    `agreements_state` directly, is what keeps this function's own
    contract (settled items included, open items too) unchanged.
    """
    if not operand:
        return []
    product = target / name
    if not product.is_dir():
        return []
    collides: list[str] = []
    for path in sorted(p for p in product.glob(AGREEMENTS_GLOB) if p.is_file()):
        for raw in _agreement_scan_text(path.read_bytes()).splitlines():
            match = AGREEMENT_LINE.match(raw.rstrip())
            if match and operand in match.group("text"):
                collides.append(match.group("text"))
    return collides


def _resolve_discuss_about(raw: str, position: dict) -> dict:
    """`--about <ordinal|witness>`: a caller names a step either by its
    number in the current sequence, or by a bare witness spec ("kind" or
    "kind operand") when there is no sequence item yet to number (design
    §3.3). Never both -- a witness spec is never itself all-digits, so the
    two are unambiguous on sight.

    A bare `kind` with no operand, for a kind `_agreement_collides` needs
    an operand to search with, is refused rather than silently accepted.
    Measured with a fixture built to discriminate `--about notebook
    <path>` (operand present, one real collision found) from `--about
    notebook` (operand absent) -- before this refusal, both returned
    successfully and only the second one's `collides` was always `[]`,
    indistinguishable from a search that genuinely found nothing. `record`
    is excluded (`impl_position.OPERAND_REQUIRED_KINDS`): it is the one
    `WITNESS_KINDS` member legitimately operand-less.
    """
    if raw.isdigit():
        ordinal = int(raw)
        item = next((i for i in position["sequence"] if i["ordinal"] == ordinal), None)
        if item is None:
            raise Refused(
                "DISCUSS_ABOUT_NOT_FOUND",
                f"no sequence item numbered {ordinal}; the position section "
                f"holds {len(position['sequence'])} item(s).")
        return {"ordinal": ordinal, "kind": item["witness"]["kind"],
                "operand": item["witness"]["operand"],
                "twostate": item["witness"].get("twostate", True)}
    parts = raw.split(None, 1)
    kind = parts[0]
    operand = parts[1] if len(parts) > 1 else None
    if kind not in impl_position.WITNESS_KINDS:
        raise Refused(
            "POSITION_WITNESS_UNKNOWN_KIND",
            f"--about names unknown witness kind {kind!r}; expected one of "
            f"{sorted(impl_position.WITNESS_KINDS)}")
    if kind in impl_position.OPERAND_REQUIRED_KINDS and not operand:
        raise Refused(
            "DISCUSS_ABOUT_OPERAND_REQUIRED",
            f"--about {kind!r} requires an operand ('--about \"{kind} <name>\"'); "
            "without one, the collision search this call would otherwise run "
            "cannot know what to search for, and a caller reading an empty "
            "`collides` back would wrongly believe it ran.")
    # A bare witness spec (no existing sequence item to read a marker off
    # of) carries no `:level` information of its own; two-state is the same
    # default the grammar itself keeps for an unmarked witness.
    return {"ordinal": None, "kind": kind, "operand": operand, "twostate": True}


def _discuss_command(target: Path, name: str, *, about: str, question: str,
                     answer: str | None = None) -> str:
    """The one directly runnable `discuss` command string every publication
    point this change adds routes through (design D2; spec "reuses the
    identical `shlex.quote` discipline as Half 1"): every embedded value is
    escaped with `shlex.quote`, never a naive interpolation or single-quote
    wrapping. `expand-contract`'s own hardcoded command (`cmd_offer`, above)
    survives with a different, single-quoted construction only because its
    fixed text carries no apostrophe -- left alone, out of scope, rather
    than migrated to this builder.
    """
    parts = ["implementation_cli.py", "discuss",
             "--target", str(target), "--name", name,
             "--about", about, "--question", question]
    if answer is not None:
        parts += ["--answer", answer]
    return " ".join(shlex.quote(part) for part in parts)


def _cli_command(*parts: str) -> str:
    """One directly runnable `implementation_cli.py` invocation.

    The same `shlex.quote` discipline `_discuss_command` keeps, generalized:
    every publication point this file has now publishes a command a reader
    pastes unedited, and a naive interpolation is how one of them stops being
    that the first time a path carries a space.
    """
    return " ".join(shlex.quote(str(part))
                    for part in ("implementation_cli.py", *parts))


def _about_arg(about: dict) -> str:
    """Round-trips a ledger event's `about` dict back into the `--about
    <ordinal|witness>` spelling `_resolve_discuss_about` reads (design D1's
    shared `_discuss_command` needs one caller-agnostic form). Never an
    ordinal: an ordinal names a position-sequence slot that may not exist,
    or may no longer mean the same thing, by the time a retirement command
    is actually run -- the bare witness spec is stable across a
    `--reconcile` renumber the same way `_settle_discussed_events`'s own
    identity match already is.
    """
    kind = about.get("kind") or "record"
    operand = about.get("operand")
    return f"{kind} {operand}" if operand else kind


def _local_remedy_discuss_entry(target: Path, name: str, finding_id: str) -> dict:
    """One `toDiscuss` entry for one `audit.localRemediesNotWritten` finding
    id (design D1's new top-level publication surface; spec Domain B,
    "Verify publishes one discuss command per unwritten local remedy
    finding"). Question text derives from the finding id alone (design D5's
    stable source for this site) -- never a count, never anything that
    varies between calls while the same finding is still unwritten.
    """
    question = (f"finding {finding_id!r}'s local remedy is not written; "
                "write it now, or record why it is deliberately deferred, "
                "and why?")
    return {
        "about": {"kind": "record", "operand": finding_id},
        "question": question,
        "command": _discuss_command(
            target, name, about=f"record {finding_id}", question=question),
    }


def _piloted_discuss_entry(target: Path, name: str, below: dict) -> dict:
    """The one `toDiscuss` entry `cmd_probe` publishes when `nextStep` is
    `piloted` (design D1's new top-level publication surface; spec "Probe's
    `piloted` status publishes a specific, runnable discuss command").

    Question text derives from the target/name pair and each axis's
    DECLARED scale alone -- `below[axis]["declared"]`, sorted by axis name
    (design D5's stable source for this site). `below[axis]["ran"]` (the
    currently-achieved count) is never read here: it climbs on every poll
    while the pilot-vs-declared-scale decision has not changed, and
    embedding it would open a new, never-to-be-revisited `discuss` bucket
    on every call (spec's stability requirement, Test Obligation #7).
    """
    axes = ", ".join(
        f"{axis}={below[axis]['declared']!r}" for axis in sorted(below))
    question = (
        f"{name} (target {target}) ran a pilot below its declared scale "
        f"({axes}); accept the pilot's scale as final, or continue toward "
        "the declared scale?")
    return {
        "about": {"kind": "record", "operand": None},
        "question": question,
        "command": _discuss_command(
            target, name, about="record", question=question),
    }


#: The choice the standing rule keeps open wherever the flow reaches the point
#: of running experiments. One spelling, because three steps ask it and a
#: sentence written three times is a sentence that eventually differs in one of
#: them.
NEXT_STEP_EXPERIMENT_CHOICE = ("continue the flow toward the declared scale, "
                               "or complement the experiments first?")

#: The choice at a step whose work is a repair rather than a run. Same
#: discipline as `_local_remedy_discuss_entry`'s own sentence, which is where
#: this wording comes from: an act, or a recorded reason for not taking it.
NEXT_STEP_REPAIR_CHOICE = ("do it now, or record why it is deliberately "
                           "deferred, and why?")

#: The three kinds a `nextStep` can be, and the only three. `terminal` is a
#: decision, not an absence: a step that names no work publishes nothing and
#: SAYS so, exactly as an `INVOCATION_DEFECT` refusal does one lock over.
NEXT_STEP_TERMINAL = "terminal"
NEXT_STEP_REPAIR = "repair"
NEXT_STEP_EXPERIMENT = "experiment"


def _next_step_question_entry(target: Path, name: str, question: str) -> dict:
    """One published question, in the shape `toDiscuss` already carries.

    `about` is the identical `(record, None)` identity `_piloted_discuss_entry`
    has always used, so a question published here lands in the same bucket
    reader and the same `--about record` spelling; buckets are by exact
    question text (`_open_discussions`), so each step's own wording keeps its
    own bucket without a second identity being invented for it.
    """
    return {
        "kind": "question",
        "about": {"kind": "record", "operand": None},
        "question": question,
        "command": _discuss_command(
            target, name, about="record", question=question),
    }


def _benchmark_publication(target: Path, name: str, facts: dict) -> dict:
    """`benchmark` -- the offer to run. The wiring draft rides in `wiring`
    (the roster says so); this is the question that must be open beside it."""
    return _next_step_question_entry(
        target, name,
        f"{name} (target {target}) is ready to be wired and run, and the "
        "wiring draft is published beside this question; "
        + NEXT_STEP_EXPERIMENT_CHOICE)


def _search_first_publication(target: Path, name: str, facts: dict) -> dict:
    """`search-first` -- the defect that named this lock. A search is an
    experiment, declared as one, and launching it is exactly the point the
    standing rule asks about. Question text derives from the DECLARED scale
    alone, the same stability rule `_piloted_discuss_entry` documents: the
    achieved count climbs on every poll while the decision has not changed."""
    declared = facts.get("declared") or {}
    axes = ", ".join(f"{axis}={declared[axis]!r}" for axis in sorted(declared))
    return _next_step_question_entry(
        target, name,
        f"{name} (target {target}) declares a search whose record is absent "
        f"or short of the scale it declares for itself ({axes}); "
        + NEXT_STEP_EXPERIMENT_CHOICE)


def _piloted_publication(target: Path, name: str, facts: dict) -> dict:
    """`piloted` -- the one publication that already existed. Its payload is
    produced by the unchanged `_piloted_discuss_entry`, byte for byte: the
    question text is pinned by its own stability proof and this lock may not
    move it."""
    return {"kind": "question",
            **_piloted_discuss_entry(target, name, facts.get("declared") or {})}


def _convert_publication(target: Path, name: str, facts: dict) -> dict:
    return _next_step_question_entry(
        target, name,
        f"{name} (target {target}) computes with an array backend that "
        "cannot be trained, so no comparison can run at all; "
        + NEXT_STEP_REPAIR_CHOICE)


def _declare_first_publication(target: Path, name: str, facts: dict) -> dict:
    """Which of the three states actually routed here, said as itself.

    `declare-first` is assigned from two different conditions in `cmd_probe`,
    and this sentence described one of them. `resolved["status"]` being
    `"absent"` is no benchmark package at all -- "has a benchmark declaration"
    is false. `report.live == "undeclared"` is a blank `entry.module` and
    nothing else, over a declaration that may name six blocks fully -- "names
    nothing yet" is false there too, and the reader is sent to re-read a
    declaration whose only gap is one field.

    `facts` carries both, computed once by `cmd_probe` from the same two reads
    it branched on: a fact recomputed here is a fact that can disagree with the
    branch that published it.
    """
    if facts.get("declarationStatus") == "absent":
        state = ("declares no benchmark package at all, and every later "
                 "reading is read from one")
    elif facts.get("live") == "undeclared":
        state = ("has a benchmark declaration whose `entry.module` is blank, "
                 "so nothing names the module that pulls its runtime in and "
                 "no reading about the interpreter is possible")
    else:
        state = ("has a benchmark declaration that names nothing yet, and "
                 "every later reading is read from it")
    return _next_step_question_entry(
        target, name, f"{name} (target {target}) {state}; "
        + NEXT_STEP_REPAIR_CHOICE)


def _env_first_publication(target: Path, name: str, facts: dict) -> dict:
    """The one step whose exit the engine can name completely. `env` reports
    the target's own declared manifests beside the forge's dev requirements,
    and the fix here is provisioning rather than code -- so this publishes the
    command rather than a question nobody has to decide."""
    return {"kind": "command",
            "command": _cli_command("env", "--target", str(target))}


def _wiring_first_publication(target: Path, name: str, facts: dict) -> dict:
    """`wiring-first` -- the step whose payload was withheld. The draft of how
    each module becomes trainable is attached (roster: `wiring`), and this is
    the question that goes with it."""
    return _next_step_question_entry(
        target, name,
        f"{name} (target {target}) declares mathematics no arm reaches, and "
        "the wiring draft is published beside this question; "
        + NEXT_STEP_REPAIR_CHOICE)


def _poll_first_publication(target: Path, name: str, facts: dict) -> dict:
    """No runnable command: a `poll` names a submission id, and
    `remote_execution_state` deliberately reports counts rather than ids or
    worker names. So the engine publishes the decision instead of a command it
    would have to invent an argument for."""
    return _next_step_question_entry(
        target, name,
        f"{name} (target {target}) has a submission already out whose answer "
        "has not returned; wait for it before anything else is offered, or "
        "reconcile the ledger, and why?")


def _report_first_publication(target: Path, name: str, facts: dict) -> dict:
    return _next_step_question_entry(
        target, name,
        f"{name} (target {target}) has a report that does not yet agree with "
        "the run it describes; " + NEXT_STEP_REPAIR_CHOICE)


def _pilot_first_publication(target: Path, name: str, facts: dict) -> dict:
    """`pilot-first` -- the flow's own steps that have not finished at pilot,
    named one by one.

    Named rather than counted, and the shape is `POSITION_RUNG_SKIPPED`'s own
    detail: a reader handed "the pilot is incomplete" learns a verdict and
    nothing they can act on, while a reader handed the step names knows
    exactly which `step` invocations are still owed.

    **This sentence must not offer the declared scale**, and that is the
    entire point of the rung. `NEXT_STEP_EXPERIMENT_CHOICE` asks whether to
    continue toward the declared scale; asking it here would offer the
    expensive run at the one state where nothing has been produced for
    anybody to read. The repair choice is the honest one: run the steps the
    flow already agreed to, or record why the flow is deliberately deferred.
    """
    missing = list(facts.get("incomplete") or [])
    named = ", ".join(repr(step) for step in missing)
    plural = "s" if len(missing) != 1 else ""
    return _next_step_question_entry(
        target, name,
        f"{name} (target {target}) declares an ordered flow whose step{plural} "
        f"{named} {'have' if len(missing) != 1 else 'has'} not finished at "
        "pilot -- each still owes a run that returned, and the ones whose own "
        "sequence item names a notebook still owe that notebook executed "
        "against these sources, because the outputs are what anybody reads to "
        "know the agreed thing is there; " + NEXT_STEP_REPAIR_CHOICE)


def _pilot_decision_question(target: Path, name: str, step: str) -> str:
    """The exact text of one step's own decision question, and the only
    construction of it.

    Buckets are by exact trimmed text (`_discussion_buckets`), so this string
    IS the bucket key: a second spelling anywhere would open a second,
    never-retiring bucket for a decision somebody already made. It is derived
    from the target, the name and the step alone -- never from a count, a
    scale or an achieved figure, all of which move while the decision has not
    changed (the stability rule `_piloted_discuss_entry` documents).
    """
    return (f"{name} (target {target}) has finished step {step!r} of its "
            "declared flow at pilot; how is that step carried out in the full "
            "run -- on a remote worker, or locally -- and why?")


def _pilot_decision_entry(target: Path, name: str, step: str) -> dict:
    """One step's decision, in the shape `toDiscuss` already carries, minus
    the `kind` key every other entry in that list also drops."""
    entry = _next_step_question_entry(
        target, name, _pilot_decision_question(target, name, step))
    return {key: value for key, value in entry.items() if key != "kind"}


def _pilot_decisions_publication(target: Path, name: str, facts: dict) -> dict:
    """`pilot-decisions` -- the pass itself, published beside the per-step
    questions `cmd_probe` appends to `toDiscuss`.

    The owner's rule, in order: the flow runs as it stands at pilot, which
    proves it runs; the notebooks run, which proves it shows what was agreed;
    and only then does the flow return to its first step, one step at a time,
    with a decision per step about how the full run carries it. So what a
    finished pilot unlocks is the start of that pass -- never permission to
    launch, and never a single yes/no at the end.

    Where the outputs are is named here rather than left to the reader, since
    reading them is the act this question is waiting on. The paths are the
    target's own declared operands, read out of its own sequence.
    """
    notebooks = list(facts.get("notebooks") or [])
    where = (" its outputs are at " + ", ".join(notebooks) + "; "
             if notebooks else " ")
    return _next_step_question_entry(
        target, name,
        f"{name} (target {target}) has finished every step of its declared "
        f"flow at pilot and{where}"
        "the flow now returns to its first step: each step owes its own "
        "decision about how the full run carries it, and those questions are "
        "published beside this one; " + NEXT_STEP_REPAIR_CHOICE)


#: Every value `cmd_probe`'s ladder can assign to `next_step`, and what each
#: one publishes. The roster exists because the condition it replaces was one
#: literal -- `next_step == "piloted"` -- so `search-first`, which launches a
#: search, reported a word and published nothing; adding a second literal
#: beside the first would have reproduced that defect one value later.
#:
#: `kind` is read for what the question asks. `wiring` is read for whether the
#: `wiring_proposal` draft belongs in the payload: it had exactly one call site,
#: guarded on `benchmark`, and `wiring-first` is set by an override that runs
#: BEFORE that guard -- so the one answer naming missing wiring withheld the
#: draft of how to wire it. `publish` is `None` only where `kind` is terminal,
#: and `NextStepPublicationRosterTests` holds that join.
PROBE_NEXT_STEPS: dict[str, dict] = {
    # Terminal. Flow B says to ask the user and invent no work for either, so
    # a publication here would be inventing exactly the work Flow B refuses --
    # the same reason `NextStepSectionCoverageTests` withholds their SKILL.md
    # sections. `piloted` is deliberately NOT among them: its own rule keeps a
    # question open, and an open question is work.
    "nothing-to-compare": {"kind": NEXT_STEP_TERMINAL, "wiring": False,
                           "publish": None},
    "already-benchmarked": {"kind": NEXT_STEP_TERMINAL, "wiring": False,
                            "publish": None},

    # Repairs: work whose cost is already settled -- a person's attention, or
    # a run the flow already agreed to. Never an offer of the declared scale,
    # which is what separates this kind from `experiment` below.
    "convert": {"kind": NEXT_STEP_REPAIR, "wiring": False,
                "publish": _convert_publication},
    "declare-first": {"kind": NEXT_STEP_REPAIR, "wiring": False,
                      "publish": _declare_first_publication},
    "env-first": {"kind": NEXT_STEP_REPAIR, "wiring": False,
                  "publish": _env_first_publication},
    "wiring-first": {"kind": NEXT_STEP_REPAIR, "wiring": True,
                     "publish": _wiring_first_publication},
    "poll-first": {"kind": NEXT_STEP_REPAIR, "wiring": False,
                   "publish": _poll_first_publication},
    "report-first": {"kind": NEXT_STEP_REPAIR, "wiring": False,
                     "publish": _report_first_publication},
    # The declared flow, before and after it has finished at pilot. Repairs
    # rather than experiments, and the distinction is not "does a machine
    # run": running the remaining steps of an already-agreed flow, and
    # deciding how the full run carries each one, are both work whose cost
    # was settled when the step was declared. What makes an answer an
    # EXPERIMENT here is that it OFFERS the declared scale and must therefore
    # ask the standing rule's flow question -- and these two exist precisely
    # to withhold that offer until the pilot has run and every step has been
    # decided.
    "pilot-first": {"kind": NEXT_STEP_REPAIR, "wiring": False,
                    "publish": _pilot_first_publication},
    "pilot-decisions": {"kind": NEXT_STEP_REPAIR, "wiring": False,
                        "publish": _pilot_decisions_publication},

    # Experiments: the three answers that spend machine time, and therefore the
    # three the standing rule's flow question belongs at. `search-first`
    # launches a search, which declares a scale of its own and is an experiment
    # by this skill's own hard rule; `benchmark` is the offer to run; `piloted`
    # is a run already made below the scale it declared.
    "search-first": {"kind": NEXT_STEP_EXPERIMENT, "wiring": False,
                     "publish": _search_first_publication},
    "benchmark": {"kind": NEXT_STEP_EXPERIMENT, "wiring": True,
                  "publish": _benchmark_publication},
    "piloted": {"kind": NEXT_STEP_EXPERIMENT, "wiring": False,
                "publish": _piloted_publication},
}


def next_step_publication(target: Path, name: str, next_step: str,
                          facts: dict) -> dict | None:
    """What `next_step` publishes, or `None` when the roster declares it
    terminal. Raises `KeyError` on an unrostered value rather than returning
    `None`: a step nobody classified must fail loudly here, never read as a
    step that legitimately names no work."""
    entry = PROBE_NEXT_STEPS[next_step]
    if entry["publish"] is None:
        return None
    return entry["publish"](target, name, facts)


def _discussion_buckets(target: Path, name: str) -> dict[str, dict]:
    """Every `discuss` bucket in this target's ledger: exact trimmed question
    text -> the LAST event in ledger order that carries it.

    One fold, two readers (`_open_discussions` and `_answered_discussions`
    below), for the reason this codebase already states about every other
    shared derivation: two spellings of one fold is how two commands come to
    disagree about the same ledger. Both readers need the identical bucketing
    rule -- by exact trimmed text, never by witness identity, since every
    entry a published question writes shares the same operand-less `record`
    identity -- and the identical last-wins rule, never "any event answered
    this", which would let a stale answer sit in front of a fresh re-ask.

    Ledger (append) order decides, never a comparison of `at`, which is
    second-granularity and can tie. Insertion order is preserved in
    first-asked order: re-assigning an existing key updates its value in
    place and never moves the key.
    """
    events = impl_position.read_events(
        target / name / ".implementation" / "position.jsonl")
    buckets: dict[str, dict] = {}
    for event in events:
        if event.get("kind") != "discuss":
            continue
        text = (event.get("asked") or "").strip()
        if not text:
            continue
        buckets[text] = event
    return buckets


def _answered_discussions(target: Path, name: str) -> set[str]:
    """Every distinct `discuss` question text whose LAST occurrence in ledger
    order carries a non-blank answer -- `_open_discussions`'s exact
    complement over the same fold.

    A pass that asks one question per item needs this, and cannot get it from
    `_open_discussions`: a question nobody has asked yet appears in neither
    list, so reading "not open" as "decided" would treat every item that was
    never asked about as already settled -- silence read as consent, which is
    the one reading this whole surface exists to refuse.
    """
    return {text for text, event in _discussion_buckets(target, name).items()
            if (event.get("answered") or "").strip()}


def _open_discussions(target: Path, name: str) -> list[dict]:
    """Every distinct `discuss` question text whose LAST occurrence in
    ledger order carries no answer (spec Domain A, "Bucketing is by exact
    trimmed question text, never by witness identity"; "A bucket's state is
    the LAST event in ledger order, never a per-event reading, never
    answered-once").

    Grouped by `asked.strip()`, never by `(about.kind, about.operand)` --
    `_settle_discussed_events` (below) groups by that identity for its own,
    narrower purpose, and reusing it here would let one answer silently
    mark every other distinct question answered too: all 27 live `discuss`
    events measured on the reference target share the identical witness
    identity `(kind="record", operand=None)`.

    A bucket's open/answered state is read from the event that occurs LAST
    in `impl_position.read_events`'s own file (append) order -- never a
    comparison of `at`, which is second-granularity and can tie, and never
    "any answered event satisfies this" (answered-once would silently
    accept a stale answer sitting behind a fresh, unanswered re-ask).
    Because grouping is by exact text, a later, differently-worded
    clarification forms its own, independent bucket and can never enter an
    already-answered one -- the doctrine `settle`'s own
    `SETTLE_DISCUSSION_UNANSWERED` ("ANY answered event satisfies this,
    never newest-wins") protects under identity grouping is preserved here
    by construction, not by a second rule.

    Returned in first-asked order (plain dict insertion order: re-assigning
    an existing key updates its value in place, it never moves the key) --
    deterministic across identical ledgers, never a live re-sort.
    """
    return [
        {"asked": text, "about": event.get("about") or {}}
        for text, event in _discussion_buckets(target, name).items()
        if not (event.get("answered") or "").strip()
    ]


def cmd_discuss(args: argparse.Namespace) -> dict:
    """Discussion as an operation with a return value (design §3.3).

    Replaces the prose at `SKILL.md`'s AGREEMENTS doctrine telling the agent
    to name a collision with an existing agreement and wait for the user:
    prose cannot be held to a return statement, so this makes "I asked" a
    fact with a ledger line instead. It never gates -- there is no refusal
    here for a question left unanswered, only a reported `status`.

    `--question -` and `--answer -` both read stdin the same way
    `cmd_compose`'s `--entry-text` already does; giving both `-` at once is
    refused rather than silently reading one and leaving the other blank.
    """
    target = resolve_target(args.target)
    name = validate_name(args.name)

    if args.question == "-" and args.answer == "-":
        raise Refused(
            "DISCUSS_STDIN_CONFLICT",
            "--question and --answer cannot both read stdin in one call; "
            "pass at most one of them as -.")

    evidence = _position_write_evidence(target, name)
    position = position_state(target, name, evidence, None, None)
    about = _resolve_discuss_about(args.about, position)

    question = sys.stdin.read() if args.question == "-" else args.question
    question = question.strip()
    if not question:
        raise Refused("DISCUSS_EMPTY_QUESTION",
                      "discuss requires a non-blank question.")

    answer = None
    if args.answer is not None:
        raw_answer = sys.stdin.read() if args.answer == "-" else args.answer
        answer = raw_answer.strip() or None

    synthetic_item = {"witness": {"kind": about["kind"], "operand": about["operand"],
                                  "twostate": about["twostate"]},
                      "mark": " "}
    # `position` already located the block (if any) and knows this pass's own
    # target; `evidence` itself was built before that, so `targetLevel` is
    # threaded in here rather than recomputed a second way.
    evidence = {**evidence, "targetLevel": position.get("targetLevel")}
    measured = impl_position.derive([synthetic_item], evidence)[0]["derived"]
    collides = _agreement_collides(target, name, about["operand"])
    # An operand-less witness (`record`, the only one `_resolve_discuss_about`
    # still lets through with none) means the search literally could not run
    # -- `[]` alone would read exactly like "ran and found nothing", the same
    # false confidence `agreements_state`'s own `absent` doctrine refuses to
    # give a repository with no checklist at all.
    collision_search = "performed" if about["operand"] else "unperformed"

    status = "answered" if answer else "open"
    recorded_at = _now_iso8601()
    impl_position.append_event(
        target / name / ".implementation" / "position.jsonl",
        {"kind": "discuss", "about": about, "asked": question,
         "answered": answer, "status": status, "at": recorded_at})

    return {
        "command": "discuss", "target": str(target), "name": name,
        "status": status, "about": about, "measured": measured,
        "collides": collides, "collisionSearch": collision_search,
        "asked": question, "answered": answer,
        "recordedAt": recorded_at,
    }


def _settle_discussed_events(target: Path, name: str, about: dict) -> list[dict]:
    """Every `discuss` ledger event whose `about` names the identical
    witness identity `(kind, operand)` this call was given, oldest first.

    Matched by identity, never by ordinal (design "Discussion match"): a
    sequence renumbers across `--reconcile` calls, but the witness pair a
    step actually names does not, and `--reconcile` itself already matches
    existing items the same way. `status` is deliberately not filtered
    here -- `settle` needs to tell "never discussed" apart from
    "discussed, never answered", and folding that distinction into this
    helper would make the caller's own two refusal codes indistinguishable
    from one read.
    """
    events = impl_position.read_events(
        target / name / ".implementation" / "position.jsonl")
    return [event for event in events
            if event.get("kind") == "discuss"
            and isinstance(event.get("about"), dict)
            and event["about"].get("kind") == about["kind"]
            and event["about"].get("operand") == about["operand"]]


def _render_settled_line(text: str, witness: str | None, *,
                          raw_line: bytes | None = None) -> bytes:
    """The one construction of a settled checklist line's bytes, called
    only from `cmd_settle` -- the sole write path a witness token has
    (design D5, spec Group 5: "no other CLI surface edits one";
    `AgreementWitnessSingleWritePathTests` holds this by an `ast` walk of
    the whole CLI, the same discipline D3 already uses for
    `impl_availability`'s call-site sets). `cmd_settle` calls this from
    both of its own modes; the lock's own `ast` walk asserts the calling
    FUNCTION, not the call count, so a second call site inside the same
    function was never what it guarded.

    **Placing a NEW item** (`raw_line=None`, `cmd_settle`'s create path):
    builds `- [ ] {text}` from scratch. Byte-identical to the pre-witness
    grammar when `witness` is falsy, so every existing caller that never
    passes `--witness` keeps writing exactly the line it always wrote.
    Always `[ ]`: this branch never authors a tick, witness or no witness.

    **Attaching a witness to an EXISTING line** (`raw_line` given,
    `cmd_settle --attach`'s path, design "attach, not place"): `text` is
    ignored entirely. `raw_line` is the located line's own bytes, taken
    verbatim from disk by `_locate_settled_text`, never reconstructed from
    a regex-captured group -- reconstructing `- [ ] {text}` the way the
    create branch does would silently normalize whatever the original
    line's own bullet character, internal spacing or mark case happened to
    be, and the design's own "byte-identical afterward, only the witness
    is added" requirement holds only because this branch never parses and
    rebuilds; it only appends. The trailing newline is preserved exactly
    as `raw_line` carried one, or not, at end of file -- the witness token
    is inserted before it, never after.
    """
    if raw_line is not None:
        has_newline = raw_line.endswith(b"\n")
        body = raw_line[:-1] if has_newline else raw_line
        if witness:
            body += f" `{witness}`".encode("utf-8")
        return body + (b"\n" if has_newline else b"")
    if witness:
        return f"- [ ] {text} `{witness}`\n".encode("utf-8")
    return f"- [ ] {text}\n".encode("utf-8")


def _render_done_line(raw_line: bytes) -> bytes:
    """The one construction of a ticked checklist line's bytes, called only
    from `cmd_settle`'s own `--done` path -- the mirror of `_render_settled_
    line`'s `--attach` branch, one mark over. `raw_line` is the located
    line's own bytes, taken verbatim from disk by `_locate_settled_text`,
    never reconstructed from a regex-captured group: rebuilding
    `- [x] {text}` from scratch would silently normalize whatever the
    original line's own bullet character, internal spacing, or trailing
    witness token happened to be, the identical restraint `_render_settled_
    line` already keeps for the identical reason.

    Only the ONE byte inside the checklist mark's own brackets moves, at
    the position `AGREEMENT_LINE`'s own `mark` group actually matched --
    never a fixed offset, so a `*` bullet, extra leading whitespace, or a
    witness token already appended can never shift which byte this writes
    over. Every byte before and after that single position round-trips
    through `str`/`bytes` unchanged, because nothing else in the line is
    parsed or rebuilt -- only located.
    """
    has_newline = raw_line.endswith(b"\n")
    body = raw_line[:-1] if has_newline else raw_line
    decoded = body.decode("utf-8")
    located = AGREEMENT_LINE.match(decoded)
    start, end = located.span("mark")
    new_body = (decoded[:start] + "x" + decoded[end:]).encode("utf-8")
    return new_body + (b"\n" if has_newline else b"")


def _locate_settled_text(data: bytes, text: str) -> list[dict]:
    """Every full-line byte span in `data` whose `AGREEMENT_LINE` match has
    a `text` group exactly equal to `text` -- the search space
    `settle --attach` locates a witness attachment against, matched by
    exact text the same way `locate_headings` matches `--under` by exact
    heading equality (design "attach, not place").

    **Found by shape, not narrowed by fencing.** Mirrors
    `agreements_state`'s own doctrine (line 220): no fenced-code exclusion,
    unlike `locate_headings`. `agreements_state` itself never excludes a
    fenced region from its own scan, so a checklist-shaped line inside one
    is already counted as an ordinary agreement today -- a line this
    function can attach a witness to is exactly a line `agreements_state`
    already counts, never a narrower set that would make the two disagree
    about what "settled" means.

    Byte-offset bookkeeping mirrors `locate_headings`
    (`impl_position.py:268`): `data.split(b"\\n")` loses every newline
    byte it split on, so it is put back per line (except a true final line
    with none) before offsets are summed. Unlike `locate_headings`'s
    zero-width insertion points, each returned span is the WHOLE matching
    line, its own trailing newline included when it has one -- this span
    is meant to be REPLACED by `impl_position.splice`, not opened.

    The position block's own byte span, when one locates cleanly, is
    excluded first -- the identical exclusion `_agreement_scan_text`
    already applies before `agreements_state` and `_agreement_collides`
    ever see a line, so a position sequence item's own `- [ ] N. ...`
    (exactly `AGREEMENT_LINE`'s shape) is never mistaken for a settled
    agreement here either. A block that will not locate is caught, not
    propagated -- the same residual `_agreement_scan_text`'s own docstring
    already accepts: the identical document raises through
    `position_state` in the same `verify` call, so a malformed block is
    never silently invisible end to end.

    Returns a list, never raises -- the same "the caller owns both counts"
    doctrine `locate_headings` already states for itself: zero hits and
    more than one are both read off this list's own length by
    `cmd_settle`, which names its own refusal codes over them
    (`SETTLE_TEXT_ABSENT` / `SETTLE_TEXT_AMBIGUOUS`).
    """
    try:
        block = impl_position.locate_block(data)
    except Refused:
        block = None
    block_start = block["start"] if block else None
    block_end = block["end"] if block else None

    parts = data.split(b"\n")
    count = len(parts)
    lines = [parts[i] + (b"\n" if i < count - 1 else b"") for i in range(count)]

    spans: list[dict] = []
    offset = 0
    for line in lines:
        start = offset
        end = offset + len(line)
        offset = end
        if block_start is not None and start < block_end and end > block_start:
            continue
        decoded = line.decode("utf-8").rstrip()
        match = AGREEMENT_LINE.match(decoded)
        if match and match.group("text") == text:
            spans.append({"start": start, "end": end})
    return spans


#: Every `## <Heading>` section's own body in a document, keyed by the
#: heading's exact stripped text -- `settle --remove`'s own reading of
#: `## Reversed`, matched by exact equality the identical way `--under`
#: already is (`locate_headings`'s own docstring: a substring rule already
#: picks the wrong one of two sections on a real document). `(?m)` so `^`
#: anchors every line, never only the string's start; `re.S` so a body
#: spanning several lines is captured whole, up to the next `## ` heading
#: or the end of the document. Deliberately ignorant of fenced regions,
#: unlike `locate_headings`: this reads an existing paragraph, it never
#: places anything inside one, so the one failure mode fencing exclusion
#: guards against -- landing a NEW insertion inside a fence -- cannot
#: happen here.
_SECTION_BODY = re.compile(r"(?m)^##[ \t]+(?P<heading>.+?)[ \t]*$(?P<body>.*?)(?=^##[ \t]|\Z)",
                          re.S)

#: A bold-quoted span inside a section body: `**"..."**`, `re.S` so a
#: quote that happens to wrap across a line inside the paragraph is still
#: captured whole. Mirrors `BULLET_LINE`'s own comment on why `**bold**`
#: is deliberately not treated as a checklist item -- this is the reverse
#: reading of the identical fact: prose the agreement scanner already
#: ignores is exactly the shape `## Reversed` uses to name what it turned
#: over.
_BOLD_QUOTE = re.compile(r'\*\*"(?P<quote>.*?)"\*\*', re.S)

#: The two ways a truncated quote may end (design "the guard removal must
#: pass", see `cmd_settle`'s own docstring): the three-dot form and the
#: single Unicode ellipsis character. Checked longest-appropriate first is
#: unnecessary here -- neither is a prefix of the other -- but both must be
#: tried, since a human writing the `Reversed` paragraph by hand types
#: whichever their editor or habit produces.
_TRUNCATION_MARKS = ("...", "…")


def _reversed_section_quotes(data: bytes) -> list[str]:
    """Every bold-quoted span found under a literal `## Reversed` heading
    anywhere in `data`, whitespace-collapsed and stripped. Never raises --
    a document with no such heading, or one whose body quotes nothing,
    simply contributes an empty list, the same "the caller owns the
    count" doctrine `_locate_settled_text` already states for itself one
    function up.

    Only the SOURCE quote is normalized (internal whitespace runs
    collapsed to one space) -- never the caller's own `--text`, which is
    compared exactly as `_locate_settled_text` already located it. A bold
    quote that happens to wrap across a markdown line inside the
    `Reversed` paragraph must still read as the identical span a quote
    typed on one line would; `--text` itself carries no such wrapping to
    begin with, since it is either one `argparse` token or one exact
    checklist line's own text.
    """
    text = data.decode("utf-8")
    quotes: list[str] = []
    for section in _SECTION_BODY.finditer(text):
        if section.group("heading").strip() != "Reversed":
            continue
        for match in _BOLD_QUOTE.finditer(section.group("body")):
            quotes.append(re.sub(r"\s+", " ", match.group("quote")).strip())
    return quotes


def _reversed_quote_matches_text(data: bytes, text: str) -> bool:
    """Whether `text` is quoted (bold, under `## Reversed`, possibly
    truncated) anywhere in `data` -- the single predicate `--remove`'s own
    guard evaluates (design "the guard removal must pass").

    A quote matches by exact equality, or -- since a long agreement is
    plausible to elide in prose -- by prefix: the quote ends in one of
    `_TRUNCATION_MARKS`, and what precedes the mark is a non-empty,
    EXACT prefix of `text`. The mark alone proves nothing; a truncated
    quote whose visible prefix does not actually match `text` is not
    accepted merely for ending in "..." -- that would let an unrelated
    reversed paragraph that happens to trail off authorize deleting an
    agreement it never named. See `cmd_settle`'s own docstring for why
    this guard exists at all, and why prefix matching -- not substring or
    fuzzy matching -- is the line drawn.
    """
    for quote in _reversed_section_quotes(data):
        if quote == text:
            return True
        for mark in _TRUNCATION_MARKS:
            if quote.endswith(mark):
                prefix = quote[: -len(mark)]
                if prefix and text.startswith(prefix):
                    return True
    return False


def _reversed_section_body_spans(data: bytes) -> list[dict]:
    """Every `## Reversed` heading's own body byte span in `data`: from
    immediately after the heading line through the byte before the next
    `## ` heading, or through the end of the document when none follows.

    Located by the identical `_SECTION_BODY` regex `_reversed_section_quotes`
    already reads with -- never a second, parallel heading-matcher, so the
    two can never disagree about where `## Reversed` starts or ends.
    `_SECTION_BODY`'s own `re.Match` offsets are CHARACTER offsets; `data`
    may hold multi-byte UTF-8 (a real `Reversed` paragraph already does, in
    its own em dash and ellipsis), so each boundary is converted to a byte
    offset by encoding the text up to it, the identical technique
    `cmd_settle`'s `--reverse` path needs because `impl_position.splice`
    only ever operates on bytes.

    Deliberately NOT `impl_position.locate_headings`: that function's own
    insertion point is the section's first CHECKLIST item, skipping past
    any introductory prose -- exactly wrong here. Measured against a real
    adopting target's own `## Reversed` section: its body opens with a
    prose paragraph (not a checklist item), so `locate_headings` would walk
    past every existing reversal entry looking for the first checklist-
    shaped line, and find one -- the position block's own `- [x] 1. ...`
    sequence item, sitting inside this same section. Reusing that offset
    would splice a new reversal entry between the position block's own
    opening comment and its first item, corrupting a structure this
    function must never enter.

    Zero hits, or more than one, are both read off this list's own length
    by the caller, which reuses `SETTLE_HEADING_ABSENT` / `SETTLE_HEADING_
    AMBIGUOUS` over them -- the identical codes the create path already
    raises for a heading occurring zero or more than once anywhere across
    the candidate holders; here the search is scoped to the one holder
    `_locate_settled_text` already narrowed the call to, the same single-
    file scope `_reversed_quote_matches_text` already reads its own quotes
    within.

    Deliberately ignorant of fenced regions, the same restraint
    `_SECTION_BODY`'s own docstring already states for itself: this
    function reads which section is `## Reversed`, by exact heading
    equality, off the SAME regex `_reversed_section_quotes` already trusts
    for that reading, so the two never drift apart over a document neither
    one owns.
    """
    text = data.decode("utf-8")
    spans: list[dict] = []
    for section in _SECTION_BODY.finditer(text):
        if section.group("heading").strip() != "Reversed":
            continue
        start = len(text[: section.start("body")].encode("utf-8"))
        end = len(text[: section.end("body")].encode("utf-8"))
        spans.append({"start": start, "end": end})
    return spans


def _render_reversed_entry(raw_line: bytes, paragraph: str) -> bytes:
    """The one construction of a `## Reversed` entry's own bytes, called
    only from `cmd_settle`'s `--reverse` path -- the identical single-
    write-path discipline `_render_settled_line` already holds for a
    settled line (design D5, spec Group 5), extended to the entry that
    explains why one was turned over. `AgreementWitnessSingleWritePathTests`
    holds this one too, by the same `ast` call-site walk.

    The bold quote is DERIVED from `raw_line` -- the located line's own
    bytes, taken verbatim from disk by `_locate_settled_text`, read through
    `AGREEMENT_LINE`'s own `text` group the identical way `--attach`'s own
    `located.group("text")` already reads it -- never reconstructed from
    `--text` itself. The two are guaranteed equal the moment a span is
    found at all (`_locate_settled_text` only ever returns a span whose
    captured `text` group already equals the caller's `--text` exactly),
    but deriving from the line keeps this function honest about WHERE the
    quote actually comes from, the identical restraint `_render_settled_
    line`'s own `--attach` branch already argues for itself: a caller-typed
    value is never what gets quoted back into the record. One concrete
    difference this buys: a witness token already bound to the located
    line (`` `test_id` ``) is excluded from the quote, because
    `AGREEMENT_LINE` captures it in its own separate group -- reconstructing
    from `--text` alone could never have carried it in the first place, but
    reading the wrong group could have.

    `paragraph` is placed verbatim, one space after the closing `**` --
    the shape every existing hand-written `Reversed` entry on a real
    adopting target already uses. The caller's own reasoning for the
    reversal is never authored here (see `cmd_settle`'s own docstring,
    "The guard removal must pass": the engine validates and performs the
    one write, it does not decide WHY an agreement was turned over).
    Returns bytes ending in a blank line (`\\n\\n`), never a single `\\n`:
    `cmd_settle` inserts this entry as a zero-width splice immediately
    before whatever already follows it (a position block, a later heading,
    or nothing at end of file), and that boundary supplies no separator of
    its own.
    """
    located = AGREEMENT_LINE.match(raw_line.decode("utf-8").rstrip())
    quote = located.group("text")
    return f'**"{quote}"** {paragraph}\n\n'.encode("utf-8")


def cmd_settle(args: argparse.Namespace) -> dict:
    """Place one settled agreement, and only one, under a caller-named
    heading (design "the placer" -- the third and last piece of "We
    discuss an idea, it gets embodied, then you come in, and the skill
    binds you so that it is placed in the contract") -- OR, with
    `--attach`, bind a witness onto a line already placed, matched by its
    exact `--text` (design "attach, not place") -- OR, with `--remove`,
    delete a line already placed, matched the identical way (design "the
    eraser") -- OR, with `--reverse`, write a NEW `## Reversed` entry and
    delete that same line in ONE call (design "a reversal is one write")
    -- OR, with `--done`, flip an already-settled line's own mark from
    `[ ]` to `[x]`, matched the identical way once more (design "the tick
    this class closes"). All five modes go through this one command; there
    is still no second write path.

    The agent drafts the discussion and a proposed sentence; the create
    path validates, refuses, and performs the one write. It never authors:
    the text placed is `--text`, verbatim, and the mark it writes is
    always `[ ]`, never `[x]` -- a tick would assert the code already
    carries something a human has not yet reviewed as reached. `--attach`
    writes no new text and no new mark at all: it locates an existing line
    by its own text and appends a witness token to it, leaving the mark
    exactly as it already was -- a ticked item stays ticked, an open one
    stays open. `--remove` writes nothing at all: it deletes the located
    line's own bytes outright, including its trailing newline, and
    touches no other byte in the document -- see `_reversed_quote_matches_text`,
    below, for the guard that decides whether it may. `--done` writes no
    new text either: it locates an existing line by its own text and
    flips the ONE byte inside its checklist mark's own brackets, from
    ` ` to `x` -- the text, any witness token it already carries, and
    every other byte in the holder file are unchanged (`_render_done_
    line`, below).

    **`--done` is the last member of a class this programme already
    closes the rest of.** Editing an agreement's own text is `--reverse`
    (which explains why) followed by a fresh placement; moving one between
    sections is `--remove` (once explained) followed by a placement under
    the new heading. Both are compositions of verbs this file already had.
    Ticking one had no composition at all: nothing --attach, --remove or
    --reverse can do, alone or chained, ever changes a mark from `[ ]` to
    `[x]`. `--done` closes that gap; it is not a sixth primitive bolted on
    beside the other four, it is the one verb the other four's own
    compositions could never reach.

    **Why marking done requires a witness -- decided, not merely
    present.** A tick asserts the work named by this line is DONE. Every
    other guard in this command exists to make sure some assertion this
    file writes rests on something (`SETTLE_NOT_DISCUSSED`: nothing is
    PLACED without having been discussed; `SETTLE_NOT_REVERSED`: nothing
    is REMOVED without having been explained). `--done` states the
    identical discipline one level further in: nothing is marked DONE
    without a witness -- a `` `test_<id>` `` token naming exactly what
    would show the work was reached -- already bound to it. `settle
    --attach` already exists to put one there; refusing `SETTLE_NOT_
    WITNESSED` costs the caller nothing it did not already have a command
    for. The alternative -- letting `--done` tick an unwitnessed line --
    would make this command author the one assertion it has refused to
    author since the create path's own docstring line above: "a tick
    would assert the code already carries something a human has not yet
    reviewed as reached." An unwitnessed tick reviews nothing; it is a
    human's plain assertion with a command's authority behind it.

    **Measured against the weighing this decision requires, not assumed.**
    A real adopting target's `AGREED.md` carries agreements ticked with no
    witness at all -- irreducible arguments (a design tradeoff, a scoping
    decision) that no test could ever contradict, because nothing about
    them is executable. A guard requiring a witness cannot mark THOSE done
    through this command, ever -- and that is read here as correct, not as
    a gap needing an escape hatch. Two reasons, not one: first, an
    argument is not the kind of claim `[x]` was ever meant to certify in
    this file's own grammar -- `disagrees`/`unmeasured` (`agreements_
    state`, above) only exist for a claim a witness token could measure,
    and an unwitnessed line already reports `unwitnessed`, a state this
    file treats as legitimate and permanent, never as an error. Second,
    the "unsupported, never technically prevented" doctrine this same
    file already states for hand-typing a witness token (`--witness`'s
    own CLI help, `usage.md`) already covers exactly this case: a human
    may still tick an irreducible argument by hand, the identical way
    those existing lines were ticked, and `verify`/`close` evaluate a
    hand-ticked mark exactly the same as one this command would have
    written. An escape flag on `--done` would not add a capability this
    programme lacks; it would only let an AUTOMATED call assert "done"
    over an argument nobody can measure, the one assertion this guard
    exists to keep a human, not a command, responsible for.

    **Un-ticking does not belong in this change.** `--done` closes a
    measured gap: no composition of the other four modes could ever
    produce a tick. The inverse has no equivalent gap to close -- a human
    can already un-tick a line by hand today, the same "unsupported,
    never technically prevented" doctrine that already governs every
    hand edit this file does not itself perform, and nothing measured
    against a real target found a ticked-in-error agreement this command
    needed to correct. Un-ticking is also not this guard's mirror image:
    `--done` asserts a fact came true and rests that assertion on a
    witness; retracting a tick asserts a PRIOR assertion was wrong, which
    is closer in shape to `--reverse` (a written admission that something
    changed) than to any read this command already performs -- it would
    need its own guard, arguably its own required explanation, designed
    on its own terms rather than inherited from `--done`'s. Left open,
    not overlooked.

    **Why `--reverse` exists at all, and why it is not merely
    `--remove` with extra steps.** `--remove` shipped guarded by
    `SETTLE_NOT_REVERSED`: refused unless the document's own `## Reversed`
    section ALREADY quotes the exact text being deleted. Measured after
    shipping it: nothing could ever satisfy that guard except a hand
    edit, because `settle` places `- [ ] {text}` checklist bullets, and a
    `## Reversed` entry is bold-quoted prose in a different shape -- no
    existing command could write one. The guard was correct; the gap was
    that satisfying it required the one practice this whole programme
    exists to eliminate. `--reverse` closes that gap by writing the entry
    and performing the deletion in the SAME call, so the explanation and
    the erasure land together or not at all -- see "One transaction,
    never two separate writes," below, for how that atomicity is actually
    achieved with no new write primitive beneath `impl_position.write_
    spliced`'s own existing compare-and-swap.

    **One transaction, never two separate writes.** Both the new `##
    Reversed` entry and the deleted line are folded into ONE `spliced`
    bytes value, computed entirely from the SAME pre-image `data`, before
    the single shared `impl_position.write_spliced` call at the bottom of
    this function ever runs. There is no intermediate state where one
    edit has landed on disk and the other has not: either both changes are
    present in the one written file, or the compare-and-swap itself
    refused (`POSITION_HOLDER_MOVED`) and NEITHER is. Composing the two
    edits reuses `impl_position.splice` twice over the SAME original
    bytes -- once (with `block=None`) purely to borrow its own blank-line
    normalization ahead of wherever the entry lands, and once more to
    apply both the resulting insertion and the deletion as ordinary
    located spans -- rather than hand-rolling a second blank-line rule
    that could drift from the one `splice` already keeps for every other
    caller that appends with `block=None`.

    **Where the entry goes: appended last, in the section's own existing
    order.** Measured against a real adopting target's `## Reversed`
    section (2026-08-31): its four entries read oldest first, the newest
    -- explicitly dated -- last, immediately before the position block
    that closes the section. `--reverse` follows that same order: the new
    entry is always inserted immediately before the position block, when
    the located `## Reversed` section holds one, or at the section's own
    end (immediately before the next `## ` heading, or end of document)
    when it does not. Never first: a reversal explains something that
    JUST happened, in a document a human reads top to bottom, and a
    freshly-turned-over agreement prepended ahead of three-year-old ones
    would misstate which is recent. See `_reversed_section_body_spans`,
    above, for why this is deliberately NOT `impl_position.locate_
    headings` -- that function's own insertion point would land inside
    the position block itself on a document shaped like the real one just
    measured.

    **What happens when the section already quotes the text -- decided,
    not deferred.** Measured on that same real target (2026-08-31): one of
    its four existing `## Reversed` entries already quotes a checklist
    line that is STILL PRESENT, ticked, under its own heading -- written
    by hand before `--reverse` existed, with the deletion never performed.
    `--reverse` refuses `SETTLE_ALREADY_REVERSED` in this state rather
    than writing a SECOND explanation beside the first: the document
    would otherwise carry two quotes of the same retired agreement, one
    of them redundant the moment it lands. `--remove` remains the
    reachable command for exactly this state -- its own guard
    (`_reversed_quote_matches_text`) is ALREADY satisfied, because the
    explanation already exists; only the deletion is still pending. This
    is not `--remove` left in as decoration: it is the one legitimate path
    for an already-explained-but-undeleted agreement, a state this
    codebase's own adopted target carries today.

    **What happens when `## Reversed` does not exist at all in a holder --
    refused, not authored.** `--reverse` reuses `SETTLE_HEADING_ABSENT`
    (the identical code the create path already raises for a missing
    `--under` heading) rather than inventing the section. The create
    path's own restraint already applies here: `settle` places items UNDER
    a heading, it never authors headings, and a freshly-invented `##
    Reversed` section would need its own preamble prose -- the real
    target's own preamble ("Written rather than deleted...") is exactly
    the kind of scoped, once-per-target writing this command has never
    performed for any OTHER heading either. A human adds the heading (and
    whatever preamble the target wants) once, the same one-time step
    `--under` already requires for any other missing heading.

    **Why `--attach` skips the discussion precondition -- decided, not
    inherited from where the check happened to sit.** `SETTLE_NOT_DISCUSSED`
    / `SETTLE_DISCUSSION_UNANSWERED` exist so that no agreement is PLACED
    without having been discussed first. A line `--attach` matches was, by
    construction, already placed by a prior `settle` call -- it already
    passed that gate once, the moment it was written. Binding a witness
    onto it afterward is not placing a new agreement; it is recording, for
    an agreement that already exists, which test now measures it. Requiring
    a fresh `discuss` per already-settled line would be ceremony with
    nothing behind it: the discussion this precondition protects already
    happened, and re-enacting it item by item for a batch of settled lines
    would not produce a single new fact this command could check. If a
    future caller finds a real need to re-litigate an already-settled
    agreement, that is a different action than attaching a witness to it,
    and belongs behind its own gate, not this one.

    **The guard removal must pass -- decided, not merely present.**
    Deleting a settled agreement is the single most destructive write this
    command can make: unlike `--attach` (adds a token) or the create path
    (adds a line), nothing `--remove` deletes is recoverable from anything
    `settle` itself ever wrote. The guard is not invented for this
    command; it is inherited from the document's own stated convention --
    the `## Reversed` section's own preamble already says, in prose,
    "Written rather than deleted: an agreement that was turned over is
    part of the record, and removing it would lose exactly what this file
    exists to keep." `--remove` therefore refuses `SETTLE_NOT_REVERSED`
    unless the EXACT text it would delete is already quoted, bold, under a
    `## Reversed` heading somewhere in the same holder file the line
    itself lives in (`_reversed_quote_matches_text`, above). This forces
    the write that explains WHY an agreement was turned over to exist
    BEFORE the write that erases it can happen -- the identical ordering
    the discussion gate already enforces one level up on the create path
    (nothing is placed before it was discussed; nothing is removed before
    it was explained), and `--remove` deliberately cannot author that
    explanation itself, the same restraint `--supersedes`'s own "stated
    gap" already states below for the create path's own narrative.

    Matched by an exact bold quote, or a quote truncated with a trailing
    ellipsis (`...` or `…`) whose visible prefix is an exact prefix of
    `--text`: measured against a real adopting target's own `Reversed`
    paragraphs, which quote every reversed agreement in full as of this
    writing, but a long agreement is plausible to elide in prose, and a
    guard that only ever accepted an exact full quote would refuse a
    caller whose reversal note is perfectly good and merely trims a long
    sentence's tail. A prefix match proves the identical fact an exact
    match proves -- that a human wrote,
    in this document, that this specific agreement (identified by its own
    opening words) was turned over -- so it is accepted; a substring or
    fuzzy match is not, because either would let an unrelated `Reversed`
    paragraph that merely shares some words authorize deleting an
    agreement it never actually reversed. This is deliberately narrower
    than `--supersedes`'s own collision check: that flag only ever records,
    in the ledger, that a NEW placement collides with an old one, and
    already documents (see "The stated gap, left open on purpose" below)
    that it never verifies the document itself says so. `--remove` closes
    that identical gap for deletion, because deletion has no ledger
    fallback the way a placement's own `collides` list does -- once the
    line is gone, `agreements_state` can no longer even report it once
    existed.

    Checked in refusing-costs-nothing order, the same discipline `cmd_gate`
    already states for itself: pure-argv shape first (including which mode
    this call is even in), then whether a discussion actually happened
    (create path only), then where the write would even go, then whether
    the located line is already done or already reversed (`--done` /
    `--reverse` paths only), then whether it collides with something
    already on record (create path only), then whether a witness or a
    removal is already bound or already explained in the document
    (`--attach` / `--remove` paths only).

    1. `SETTLE_STDIN_CONFLICT` -- `--text -` and `--supersedes -` cannot
       both read stdin in the same call.
    2. `SETTLE_EMPTY_TEXT` -- a blank `--text` is refused before anything
       else is read from disk.
    3. `SETTLE_ATTACH_CONFLICT` -- `--attach` combined with `--under` or
       `--supersedes`: neither names anything in this mode (there is no
       new item to place under a heading, and nothing new to collide with),
       and silently ignoring a flag the caller bothered to type would be
       exactly the kind of surprise `SETTLE_STDIN_CONFLICT` already refuses
       one level up.
    4. `SETTLE_REMOVE_CONFLICT` -- `--remove` combined with `--attach`,
       `--under`, `--supersedes`, or `--witness`: `--remove` is one of
       four other, mutually exclusive modes (never both `--attach` and
       `--remove` in one call), places nothing new (`--under`,
       `--supersedes` do not apply, the identical reasoning
       `SETTLE_ATTACH_CONFLICT` already gives), and writes no witness
       token at all -- the line is deleted, not edited, so a `--witness`
       the caller bothered to type would otherwise be silently ignored,
       the same surprise every other conflict code in this list already
       refuses.
    5. `SETTLE_REVERSE_CONFLICT` -- either `--reverse` combined with
       `--attach`, `--remove`, `--under`, `--supersedes`, or `--witness`
       (the identical reasoning `SETTLE_REMOVE_CONFLICT` already gives,
       extended to a fourth mutually exclusive mode: `--reverse` deletes
       the line, so `--witness` binds nothing; it writes no new item
       under a heading, so `--under` and `--supersedes` do not apply), OR
       `--paragraph` given WITHOUT `--reverse` -- that flag feeds a `##
       Reversed` entry only `--reverse` ever writes, so giving it in any
       other mode is the identical unused-flag surprise this whole list
       already refuses rather than silently ignores.
    6. `SETTLE_DONE_CONFLICT` -- `--done` combined with `--attach`,
       `--remove`, `--reverse`, `--under`, `--supersedes`, `--witness` or
       `--paragraph` -- the identical reasoning `SETTLE_REVERSE_CONFLICT`
       already gives, extended to a fifth mutually exclusive mode:
       `--done` places nothing new (`--under`, `--supersedes` do not
       apply), writes no new witness token (`--witness` binds one
       separately, by `--attach`, before this mode may ever reach it) and
       writes no `## Reversed` entry (`--paragraph` does not apply).
    7. `SETTLE_WITNESS_REQUIRED` -- `--attach` without `--witness`: binding
       a witness is the entire point of this mode, so an `--attach` call
       carrying none has nothing to do.
    8. `SETTLE_PARAGRAPH_REQUIRED` -- `--reverse` without a non-blank
       `--paragraph`: writing a NEW `## Reversed` entry is the entire
       point of this mode, and the engine never authors the reasoning
       behind one (see "Why `--reverse` exists at all," above) -- an
       `--reverse` call carrying no paragraph has nothing to explain with.
    9. `SETTLE_UNDER_REQUIRED` / `SETTLE_ABOUT_REQUIRED` -- the create path
       (none of `--attach`, `--remove`, `--reverse` or `--done`) still
       needs both; `argparse` no longer enforces either as unconditionally
       required, because the other four modes need neither, so this
       command enforces them itself once it knows which mode it is in.
    10. `SETTLE_WITNESS_MALFORMED` -- an optional `--witness test_<id>`
        (design D5, spec Group 3) that does not match `AGREEMENT_LINE`'s own
        trailing-token grammar (`test_[A-Za-z0-9_]+`). Refused before the
        write, not silently swallowed into plain text: a malformed value
        would otherwise round-trip as inert prose, and a caller who typed
        `--witness` believing it bound something would never learn it did
        not. Checked in every mode that can still reach it (`--remove`,
        `--reverse` and `--done` already refused `SETTLE_REMOVE_CONFLICT` /
        `SETTLE_REVERSE_CONFLICT` / `SETTLE_DONE_CONFLICT` above if
        `--witness` was given at all).
    11. `SETTLE_NOT_DISCUSSED` / `SETTLE_DISCUSSION_UNANSWERED` -- create
        path only (see "Why `--attach` skips..." above; the identical
        reasoning excuses `--remove`, `--reverse` and `--done`, none of
        which places anything new). `--about` is resolved the identical way
        `discuss`'s own `--about` already is (`_resolve_discuss_about`),
        then matched against the ledger by witness identity: ANY answered
        event satisfies this, never newest-wins (design "Discussion
        match") -- a later clarifying question must never retroactively
        erase an earlier answer, which would teach a caller not to ask
        one.
    12. `SETTLE_HOLDER_ABSENT` -- `agreements_state`'s own already-computed
        `holders` is the candidate set; a target with none has nowhere this
        command may write (or, for `--remove`/`--reverse`/`--done`, nothing
        to delete from or flip), and it never invents a file, the same
        doctrine `_chosen_holder` already states for a fresh position
        block. Checked in every mode.
    13. Create path: `SETTLE_HEADING_ABSENT` / `SETTLE_HEADING_AMBIGUOUS` --
        every holder's own `impl_position.locate_headings` hits, concatenated
        across all of them: zero, or more than one anywhere (two hits in
        one holder and one hit apiece in two holders read identically) --
        the caller owns both counts, because the locator itself never
        refuses (see its own docstring for why).
        `--attach`, `--remove`, `--reverse` AND `--done` paths: `SETTLE_TEXT_
        ABSENT` / `SETTLE_TEXT_AMBIGUOUS` -- the identical discipline, one
        level down, and the identical helper (`_locate_settled_text`) all
        four modes call: every holder's own hits for the exact `--text`,
        concatenated; zero or more than one refuses the same way, for the
        same reason -- which existing line receives the witness, is
        deleted, is reversed, or is marked done, is not decidable without
        a human choosing when more than one line reads identically.
        Reused, not minted twice: none of `--remove`, `--reverse` or
        `--done` mints a code of its own here.
    14. `--reverse` path only, checked after the text search narrows to one
        holder's own bytes: `SETTLE_ALREADY_REVERSED` -- see "What happens
        when the section already quotes the text," above -- THEN
        `SETTLE_HEADING_ABSENT` / `SETTLE_HEADING_AMBIGUOUS` over
        `_reversed_section_body_spans(data)`, scoped to that one holder
        (never aggregated across all of them the way the create path's own
        `--under` search is, because by this point the search already
        knows which single holder the located line lives in) -- see "Where
        the entry goes," above. Reused codes, not minted twice: the create
        path already names both for a missing or ambiguous heading; this
        is the identical vocabulary applied to a heading this mode reads
        rather than places under.
    15. `--done` path only, checked after the identical text search
        narrows to one holder's own bytes: `SETTLE_ALREADY_DONE` -- the
        located line's own mark is already `x` or `X` -- THEN `SETTLE_NOT_
        WITNESSED` -- the located line carries no `` `test_<id>` `` token
        (see "Why marking done requires a witness," above, for the full
        argument). Checked in this order, not the reverse: an already-done
        line is refused on that fact alone, regardless of whether it also
        happens to carry a witness, the identical "state check before
        precondition check" ordering `--reverse`'s own `SETTLE_ALREADY_
        REVERSED` (14, above) already keeps ahead of its own heading
        checks.
    16. Create path only: `SETTLE_COLLIDES_UNNAMED` / `SETTLE_SUPERSEDES_UNKNOWN`
        -- the same `_agreement_collides` `discuss` already repairs
        (excludes the position block's own item lines), run over the
        witness's own operand. A caller naming a superseded item must name
        one actually IN that computed list -- an unchecked string would be
        a rubber stamp on a supersession this command cannot itself verify
        happened in the document.
    17. `--attach` path only: `SETTLE_ALREADY_WITNESSED` -- the one located
        line already carries a `` `test_<id>` `` token. `--attach` never
        replaces one; there is no separate flag that does, so the only way
        to change an existing witness today is the same "unsupported,
        never technically prevented" doctrine hand-typing already carries
        (see `--witness`'s own help) -- adding a silent-replace path here
        would let one automated call quietly overwrite a binding another
        call, or a human, put there on purpose.
    18. `--remove` path only: `SETTLE_NOT_REVERSED` -- the located line's
        own exact text is not quoted (bold, possibly truncated) under any
        `## Reversed` heading in the same holder file. See "The guard
        removal must pass," above, for the full argument. The mirror image
        of `--reverse`'s own `SETTLE_ALREADY_REVERSED` (14, above): one
        refuses until the explanation exists, the other refuses once it
        already does.

    **The witness this places is a separate identity from `--about`.**
    `--about` names the *position* witness this placement discusses and
    matches against the ledger; `--witness`, when given, is the *agreement's
    own* `test_<id>` in the declared-invariants suite, persisted into the
    written line so `agreements_state` can read it back without consulting
    the ledger. `_resolve_discuss_about` cannot itself carry a `test_<id>`
    -- it raises `POSITION_WITNESS_UNKNOWN_KIND` for anything outside
    `impl_position.WITNESS_KINDS`, which `test_<id>` is not a member of and
    never becomes one; `--witness` is why this command needs no such
    member. Omitted, the written line stays exactly as it always was.
    `--attach` never resolves `--about` at all (it is not even required in
    that mode) -- there is no discussion gate left to check it against, so
    resolving it would validate a value this call never uses for anything.

    `POSITION_HOLDER_MOVED` is reused, not minted fresh: it already names a
    holder document's own compare-and-swap failure, and a placement's own
    pre-image digest is exactly that same fact one level down --
    `write_spliced` raises it unchanged. Reused identically for `--attach`.

    **The stated gap, left open on purpose.** `--supersedes` names the
    superseded item in the ledger event only. The document itself shows no
    supersession until a human writes the `Reversed` paragraph -- the
    alternative was letting this command author that narrative on its own,
    the identical restraint `POSITION_PLACEHOLDER_TEXT`'s own docstring
    already states for what a discovered step means. `settle` checks that
    a name was given and that it is real; it does not, and cannot, check
    that the document was actually updated to say so.
    """
    target = resolve_target(args.target)
    name = validate_name(args.name)
    _require_no_open_defect(target, name)

    if args.text == "-" and args.supersedes == "-":
        raise Refused(
            "SETTLE_STDIN_CONFLICT",
            "--text and --supersedes cannot both read stdin in one call; "
            "pass at most one of them as -.")

    text = sys.stdin.read() if args.text == "-" else args.text
    text = text.strip()
    if not text:
        raise Refused("SETTLE_EMPTY_TEXT", "settle requires non-blank --text.")

    attach = bool(getattr(args, "attach", False))
    remove = bool(getattr(args, "remove", False))
    reverse = bool(getattr(args, "reverse", False))
    done = bool(getattr(args, "done", False))

    if attach and (args.under or args.supersedes is not None):
        raise Refused(
            "SETTLE_ATTACH_CONFLICT",
            "--attach binds a witness onto a line already placed; --under "
            "(where a NEW item goes) and --supersedes (what a NEW item "
            "collides with) do not apply and must be omitted.")

    witness = getattr(args, "witness", None)
    witness = witness.strip() if witness else None
    if remove and (attach or args.under or args.supersedes is not None or witness):
        raise Refused(
            "SETTLE_REMOVE_CONFLICT",
            "--remove deletes a line already placed; --attach (a second, "
            "mutually exclusive mode), --under and --supersedes (what a "
            "NEW item needs), and --witness (nothing is written, so there "
            "is no token to bind) do not apply and must be omitted.")
    paragraph = getattr(args, "paragraph", None)
    paragraph = paragraph.strip() if paragraph else None
    if reverse and (attach or remove or args.under or args.supersedes is not None
                    or witness):
        raise Refused(
            "SETTLE_REVERSE_CONFLICT",
            "--reverse writes the ## Reversed entry and deletes the "
            "settled line in one call; --attach and --remove (two other, "
            "mutually exclusive modes), --under and --supersedes (what a "
            "NEW item needs), and --witness (nothing is written to the "
            "deleted line, so there is no token to bind) do not apply and "
            "must be omitted.")
    if done and (attach or remove or reverse or args.under
                 or args.supersedes is not None or witness or paragraph):
        raise Refused(
            "SETTLE_DONE_CONFLICT",
            "--done flips an already-settled line's own mark to done; "
            "--attach, --remove and --reverse (three other, mutually "
            "exclusive modes), --under and --supersedes (what a NEW item "
            "needs), --witness (bound separately, by --attach, before a "
            "line may ever be marked done through this command) and "
            "--paragraph (only --reverse ever writes one) do not apply "
            "and must be omitted.")
    if paragraph and not reverse:
        raise Refused(
            "SETTLE_REVERSE_CONFLICT",
            "--paragraph supplies the prose a NEW ## Reversed entry is "
            "written with, and only --reverse ever writes one; it does "
            "not apply -- and must be omitted -- in every other mode.")
    if attach and not witness:
        raise Refused(
            "SETTLE_WITNESS_REQUIRED",
            "--attach binds a witness onto an already-settled line; "
            "--witness is the whole point of this mode and cannot be "
            "omitted.")
    if reverse and not paragraph:
        raise Refused(
            "SETTLE_PARAGRAPH_REQUIRED",
            "--reverse writes a NEW ## Reversed entry, and the engine "
            "never authors the reasoning behind one -- --paragraph is the "
            "caller's own explanation of why the agreement was turned "
            "over and cannot be omitted or blank.")
    if not attach and not remove and not reverse and not done:
        if not args.under:
            raise Refused(
                "SETTLE_UNDER_REQUIRED",
                "--under is required to place a new item; it names where "
                "the write goes and has no default. Omit it only together "
                "with --attach, --remove, --reverse or --done, none of "
                "which places a new item under a heading.")
        if not args.about:
            raise Refused(
                "SETTLE_ABOUT_REQUIRED",
                "--about is required to place a new item; it names the "
                "discussion this placement is bound to. Omit it only "
                "together with --attach, --remove, --reverse or --done, "
                "none of which places anything new.")
    if witness and not re.fullmatch(r"test_[A-Za-z0-9_]+", witness):
        raise Refused(
            "SETTLE_WITNESS_MALFORMED",
            f"--witness {witness!r} does not match the grammar's own "
            "`test_<id>` shape (test_[A-Za-z0-9_]+); a value that does not "
            "match would round-trip as inert trailing text, never as a "
            "witness `agreements_state` can read back.")

    about = None
    if not attach and not remove and not reverse and not done:
        evidence = _position_write_evidence(target, name)
        position = position_state(target, name, evidence, None, None)
        about = _resolve_discuss_about(args.about, position)

        discussed = _settle_discussed_events(target, name, about)
        if not discussed:
            raise Refused(
                "SETTLE_NOT_DISCUSSED",
                f"no discuss event names witness identity "
                f"(kind={about['kind']!r}, operand={about['operand']!r}); a "
                "placement must be discussed before it is placed.")
        if not any(event.get("status") == "answered" for event in discussed):
            raise Refused(
                "SETTLE_DISCUSSION_UNANSWERED",
                f"{len(discussed)} discuss event(s) name this witness "
                "identity and none carries status \"answered\"; an open "
                "question is not yet a settled agreement.")

    holders = agreements_state(target, name)["holders"]
    if not holders:
        raise Refused(
            "SETTLE_HOLDER_ABSENT",
            f"no markdown file under {name}/ holds checklist items; "
            "settle never invents a file to write into.")

    heading = None
    supersedes = None
    collides: list[str] = []

    if attach:
        candidates: list[tuple[Path, bytes, dict]] = []
        for holder in holders:
            holder_path = target / holder
            holder_data = holder_path.read_bytes()
            for span in _locate_settled_text(holder_data, text):
                candidates.append((holder_path, holder_data, span))

        if not candidates:
            raise Refused(
                "SETTLE_TEXT_ABSENT",
                f"{text!r} matches no existing checklist line across "
                f"{len(holders)} holder(s) under {name}/.")
        if len(candidates) > 1:
            raise Refused(
                "SETTLE_TEXT_AMBIGUOUS",
                f"{text!r} matches {len(candidates)} existing checklist "
                f"lines across {name}/'s holder(s); which one receives the "
                "witness is not decidable without a human choosing.")
        target_path, data, span = candidates[0]

        raw_line = data[span["start"]:span["end"]]
        located = AGREEMENT_LINE.match(raw_line.decode("utf-8").rstrip())
        if located.group("witness"):
            raise Refused(
                "SETTLE_ALREADY_WITNESSED",
                f"{text!r} already carries witness "
                f"{located.group('witness')!r}; --attach never replaces "
                "one.")

        new_line = _render_settled_line(text, witness, raw_line=raw_line)
        spliced = impl_position.splice(data, new_line, span)
    elif remove:
        candidates: list[tuple[Path, bytes, dict]] = []
        for holder in holders:
            holder_path = target / holder
            holder_data = holder_path.read_bytes()
            for span in _locate_settled_text(holder_data, text):
                candidates.append((holder_path, holder_data, span))

        if not candidates:
            raise Refused(
                "SETTLE_TEXT_ABSENT",
                f"{text!r} matches no existing checklist line across "
                f"{len(holders)} holder(s) under {name}/.")
        if len(candidates) > 1:
            raise Refused(
                "SETTLE_TEXT_AMBIGUOUS",
                f"{text!r} matches {len(candidates)} existing checklist "
                f"lines across {name}/'s holder(s); which one this call "
                "removes is not decidable without a human choosing.")
        target_path, data, span = candidates[0]

        if not _reversed_quote_matches_text(data, text):
            raise Refused(
                "SETTLE_NOT_REVERSED",
                f"{text!r} is not quoted (bold, under a ## Reversed "
                f"heading) anywhere in {target_path.name}; --remove only "
                "deletes an agreement the document's own Reversed section "
                "already explains turning over -- write that paragraph "
                "first, the same discipline SETTLE_NOT_DISCUSSED already "
                "enforces one level up for the create path.")

        spliced = impl_position.splice(data, b"", span)
    elif reverse:
        candidates: list[tuple[Path, bytes, dict]] = []
        for holder in holders:
            holder_path = target / holder
            holder_data = holder_path.read_bytes()
            for span in _locate_settled_text(holder_data, text):
                candidates.append((holder_path, holder_data, span))

        if not candidates:
            raise Refused(
                "SETTLE_TEXT_ABSENT",
                f"{text!r} matches no existing checklist line across "
                f"{len(holders)} holder(s) under {name}/.")
        if len(candidates) > 1:
            raise Refused(
                "SETTLE_TEXT_AMBIGUOUS",
                f"{text!r} matches {len(candidates)} existing checklist "
                f"lines across {name}/'s holder(s); which one this call "
                "reverses is not decidable without a human choosing.")
        target_path, data, span = candidates[0]

        if _reversed_quote_matches_text(data, text):
            raise Refused(
                "SETTLE_ALREADY_REVERSED",
                f"{text!r} is already quoted (bold, under a ## Reversed "
                f"heading) in {target_path.name}; --reverse writes a NEW "
                "explanation together with the deletion, and would "
                "duplicate one the document already has. The explanation "
                "already exists -- what is missing is only the deletion, "
                "which plain --remove performs on its own.")

        reversed_spans = _reversed_section_body_spans(data)
        if not reversed_spans:
            raise Refused(
                "SETTLE_HEADING_ABSENT",
                f"'## Reversed' occurs in none of {target_path.name}'s own "
                "headings; --reverse places its entry under an existing "
                "'## Reversed' section and never invents one, the "
                "identical restraint the create path's own --under "
                "already keeps for a heading it is given.")
        if len(reversed_spans) > 1:
            raise Refused(
                "SETTLE_HEADING_AMBIGUOUS",
                f"'## Reversed' occurs {len(reversed_spans)} times in "
                f"{target_path.name}; which one receives this entry is "
                "not decidable without a human choosing.")
        body_start, body_end = reversed_spans[0]["start"], reversed_spans[0]["end"]

        try:
            position_block = impl_position.locate_block(data)
        except Refused:
            position_block = None
        if position_block is not None and body_start <= position_block["start"] < body_end:
            boundary = position_block["start"]
        else:
            boundary = body_end

        raw_line = data[span["start"]:span["end"]]
        entry = _render_reversed_entry(raw_line, paragraph)
        prefixed = impl_position.splice(data[:boundary], entry, None)
        insertion = prefixed[boundary:]

        edits = sorted(
            [(span, b""), ({"start": boundary, "end": boundary}, insertion)],
            key=lambda edit: edit[0]["start"], reverse=True)
        spliced = data
        for edit_span, new_bytes in edits:
            spliced = impl_position.splice(spliced, new_bytes, edit_span)
    elif done:
        candidates: list[tuple[Path, bytes, dict]] = []
        for holder in holders:
            holder_path = target / holder
            holder_data = holder_path.read_bytes()
            for span in _locate_settled_text(holder_data, text):
                candidates.append((holder_path, holder_data, span))

        if not candidates:
            raise Refused(
                "SETTLE_TEXT_ABSENT",
                f"{text!r} matches no existing checklist line across "
                f"{len(holders)} holder(s) under {name}/.")
        if len(candidates) > 1:
            raise Refused(
                "SETTLE_TEXT_AMBIGUOUS",
                f"{text!r} matches {len(candidates)} existing checklist "
                f"lines across {name}/'s holder(s); which one this call "
                "marks done is not decidable without a human choosing.")
        target_path, data, span = candidates[0]

        raw_line = data[span["start"]:span["end"]]
        located = AGREEMENT_LINE.match(raw_line.decode("utf-8").rstrip())
        if located.group("mark") in ("x", "X"):
            raise Refused(
                "SETTLE_ALREADY_DONE",
                f"{text!r} is already marked done "
                f"(`[{located.group('mark')}]`); --done never re-ticks an "
                "already-ticked line.")
        if not located.group("witness"):
            raise Refused(
                "SETTLE_NOT_WITNESSED",
                f"{text!r} carries no witness token; --done refuses to "
                "mark an agreement done that names nothing a test could "
                "contradict -- bind one first with `settle --attach "
                "--witness test_<id>`.")

        new_line = _render_done_line(raw_line)
        spliced = impl_position.splice(data, new_line, span)
    else:
        heading = args.under.strip()
        candidates = []
        for holder in holders:
            holder_path = target / holder
            holder_data = holder_path.read_bytes()
            for span in impl_position.locate_headings(holder_data, heading):
                candidates.append((holder_path, holder_data, span))

        if not candidates:
            raise Refused(
                "SETTLE_HEADING_ABSENT",
                f"{heading!r} occurs in none of {len(holders)} holder(s) "
                f"under {name}/.")
        if len(candidates) > 1:
            raise Refused(
                "SETTLE_HEADING_AMBIGUOUS",
                f"{heading!r} occurs {len(candidates)} times across "
                f"{name}/'s holder(s); which occurrence receives the item "
                "is not decidable without a human choosing.")
        target_path, data, span = candidates[0]

        collides = _agreement_collides(target, name, about["operand"])
        if args.supersedes is not None:
            supersedes = sys.stdin.read() if args.supersedes == "-" else args.supersedes
            supersedes = supersedes.strip()
        if collides and not supersedes:
            colliding_texts = sorted(collides)
            listed = "; ".join(repr(t) for t in colliding_texts)
            collision_question = (
                f"{about['operand']!r} collides with existing agreement(s): "
                f"{listed}. Which one, if any, does this placement "
                "supersede?")
            raise Refused(
                "SETTLE_COLLIDES_UNNAMED",
                "this witness's operand already appears in existing "
                f"agreement(s): {listed}; name the one this placement "
                "supersedes with --supersedes, or the write would "
                "silently duplicate it. Ask which one with:\n" +
                _discuss_command(target, name, about=_about_arg(about),
                                 question=collision_question))
        if supersedes is not None and supersedes not in collides:
            raise Refused(
                "SETTLE_SUPERSEDES_UNKNOWN",
                f"--supersedes {supersedes!r} does not exact-match any of "
                f"the {len(collides)} computed colliding agreement(s).")

        new_line = _render_settled_line(text, witness)
        spliced = impl_position.splice(data, new_line, span)

    pre_digest = impl_position.digest_bytes(data)
    impl_position.write_spliced(target_path, spliced, expect_digest=pre_digest)

    recorded_at = _now_iso8601()
    impl_position.append_event(
        target / name / ".implementation" / "position.jsonl",
        {"kind": "settle", "session": args.session, "about": about,
         "text": text, "under": heading, "witness": witness, "attach": attach,
         "remove": remove, "reverse": reverse, "done": done,
         "paragraph": paragraph,
         "holder": str(target_path.relative_to(target)),
         "supersedes": supersedes, "collides": collides, "at": recorded_at})

    return {
        "command": "settle", "target": str(target), "name": name,
        "status": "written", "holder": str(target_path.relative_to(target)),
        "about": about, "text": text, "under": heading, "witness": witness,
        "attach": attach, "remove": remove, "reverse": reverse, "done": done,
        "paragraph": paragraph, "supersedes": supersedes,
        "collides": collides, "recordedAt": recorded_at,
    }


#: The closed, forge-owned vocabulary an `offer` action's `id` may ever
#: hold (spec "Action shape is closed and forge-owned"). Modelled on
#: `impl_position.WITNESS_KINDS`, not on `probe`'s own scraped `nextStep`
#: literals: this constant IS the roster, and `OfferCommandTests` in
#: `tests/test_proposal_implementation.py` holds the *agreement* between
#: this constant, the publisher's own source (every `"id"` literal it
#: writes), and a runtime action set -- rather than carrying a second,
#: independent copy of the list the way a scraped roster would.
ACTION_IDS = frozenset({"launch", "run-step", "expand-contract"})


def _launch_disagreements(position: dict) -> list:
    """Which of `position["disagreements"]` are a false claim a launch may
    not proceed against -- never the ones that are merely unreconciled.

    `impl_position.derive()`'s `disagrees` fact is bidirectional
    (`satisfied is not None and satisfied != (mark == "x")`), so it fires
    on two measured shapes that are not equally dishonest:

        blank box,  measurement says yes -> satisfied=True   disagrees=True
        ticked box, measurement says no  -> satisfied=False  disagrees=True

    Only the second is a false claim: a box ticked ahead of what its own
    witness actually measured -- the same incident `unbacked` exists to
    catch on the other side of one principle (a tick nothing measured, a
    tick something measured against). The first is work already done whose
    mark has not yet been reconciled (a later `position --reconcile` run
    will tick it) -- a blank box asserts nothing, so it cannot be a false
    assertion, and refusing a launch over it would refuse honesty itself.
    `cmd_gate` and `_offer_launch_action` both call this, once, so neither
    can compute a different answer to the identical question -- the same
    single-shared-rule discipline `impl_availability.launch_available`
    itself exists to enforce one layer down.
    """
    return [item for item in position["disagreements"] if item["mark"] == "x"]


#: The eight fields "the same upcoming launch" reduces to, independently
#: recomputed on both sides of the mint/verify boundary (design decision 3,
#: extended by `the-pilot-decides-the-remote-strategy` decision D4):
#: `_authorization_binding` (below, prospective -- computed at `offer`
#: time) and `_verify_gate_authorization` (below, retrospective -- computed
#: at `gate` time) each build this exact shape from their OWN freshly
#: re-derived facts, never from each other's output and never from a value
#: a ledger record merely repeats back. Held once here so the two
#: derivations cannot drift on which eight keys the digest covers.
#:
#: `proposalDigest` (the 8th, added by D4) is the one exception to "freshly
#: re-derived": `_authorization_binding` derives it fresh at MINT time
#: (`_proposal_digest`, the newest proposal naming this job), but
#: `cmd_gate`'s own `gate_binding` copy (below) is never compared against
#: the record for it -- `_verify_gate_proposal` owns that verification,
#: one layer down, against the RECORD's own frozen value, never a value
#: re-derived here. It is present in `gate_binding` only so the three
#: literals this key set is spelled in stay structurally equal (the
#: structural test this change adds), and it still participates fully in
#: the hash-consistency check below (`own_binding`, built entirely from
#: `record`), which is what protects it from being edited after minting.
#: Three literals must spell this exact key set: this tuple,
#: `_authorization_binding`'s own return, and `cmd_gate`'s inline
#: `gate_binding` dict -- nothing enforced their agreement before this
#: change added a structural test for it.
_AUTHORIZATION_BINDING_KEYS = (
    "jobName", "commit", "entrypoint", "units", "rung",
    "revisionSha256", "positionStatus", "proposalDigest",
)


def _verify_gate_authorization(events: list, token: str, binding: dict) -> dict:
    """The full check behind `gate --authorization <token>` (design "What
    `gate` refuses"), run once, immediately before `append_event`, over
    `binding` -- THIS invocation's own fresh re-derivation of the seven
    live-disk `_AUTHORIZATION_BINDING_KEYS` facts, never the minted event's
    own recorded copy of them. Presence of `--authorization` at all is a
    separate, earlier, pure-argv check (`GATE_AUTHORIZATION_REQUIRED`, at
    the top of `cmd_gate`'s own ladder); by the time this runs, a token
    string exists and this is the only place it is actually verified.
    Returns the matched `record` on success, so a caller can verify the
    proposal it names (`_verify_gate_proposal`, below) without a second
    lookup by token.

    Five refusals, checked in an order that answers a narrower question
    each time (mismatch before stale, so presenting job A's token while
    gating job B says exactly that, rather than blaming the world for
    having moved):

    - `GATE_AUTHORIZATION_UNKNOWN`: no `authorization` event on the ledger
      carries this exact token, OR the event that does no longer re-digests
      to its own `token` under the current 8-key shape, OR it does not
      re-digest under the 8-key shape but genuinely re-digests under the
      pre-`proposalDigest` 7-key shape too -- that last case is
      distinguished as `GATE_AUTHORIZATION_SUPERSEDED` instead (D6,
      below), never silently folded back into `UNKNOWN`.
    - `GATE_AUTHORIZATION_SUPERSEDED`: a legitimate token minted before
      `proposalDigest` joined the binding. Diagnostic only -- see the
      dedicated check below; it refuses exactly as hard as `UNKNOWN` and
      the remedy is identical (re-mint with `offer`).
    - `GATE_AUTHORIZATION_MISMATCH`: a genuine record exists, but it names
      a different job or a different operator-declared unit list than THIS
      invocation's own.
    - `GATE_AUTHORIZATION_STALE`: the record is this invocation's own job
      and units, but the pin, entrypoint, rung, revision or position status
      it was minted against no longer equal what this call just measured.
      Never elapsed time -- `session`/`at` are mint discriminators baked
      into the digest, not a clock this function reads.
    - `GATE_AUTHORIZATION_CONSUMED`: an `authorization-consumed` event
      already names this exact token. Single-use, and never a deletion --
      the ledger keeps the record of what spent it, the same append-only
      rationale `append_event`'s own docstring states.
    """
    record = next(
        (e for e in events
         if e.get("kind") == "authorization" and e.get("token") == token),
        None)
    if record is not None:
        own_binding = {key: record.get(key) for key in _AUTHORIZATION_BINDING_KEYS}
        # `mintOrdinal` is part of the digest payload `_find_or_mint_
        # authorization` hashes (the timestamp-collision fix); it must be
        # folded back in here too, or every genuinely minted token would
        # fail this re-digest and be treated as tampered.
        recomputed = hashlib.sha256(json.dumps(
            {**own_binding, "session": record.get("session"),
             "at": record.get("at"), "mintOrdinal": record.get("mintOrdinal")},
            sort_keys=True).encode("utf-8")).hexdigest()
        if recomputed != record.get("token"):
            # D6: an 8-key mismatch alone does not mean tampered -- a
            # legitimate pre-change token was minted over 7 keys and can
            # never satisfy an 8-key recompute now that `proposalDigest`
            # exists. Distinguish it with a SECOND hash, over a payload
            # this function already has: if the record carries no
            # `proposalDigest` key AT ALL (never merely `null` -- a
            # post-change record with no proposal at mint time still
            # stores the key, set to `null`, and its ORIGINAL digest was
            # computed WITH that key present) and the 7-key recompute
            # (the exact shape that predates this key) matches the
            # record's own token, this is a measurement, not a guess: an
            # editor who merely deleted `proposalDigest` from a
            # post-change event would fail the 7-key recompute too,
            # because that event's token was originally digested WITH
            # the key. Diagnostic only -- both codes refuse identically
            # hard, and the remedy is always re-minting with `offer`,
            # never editing a stored event to fit the new shape.
            if "proposalDigest" not in record:
                seven_key_binding = {
                    key: value for key, value in own_binding.items()
                    if key != "proposalDigest"}
                seven_key_recomputed = hashlib.sha256(json.dumps(
                    {**seven_key_binding, "session": record.get("session"),
                     "at": record.get("at"),
                     "mintOrdinal": record.get("mintOrdinal")},
                    sort_keys=True).encode("utf-8")).hexdigest()
                if seven_key_recomputed == record.get("token"):
                    raise Refused(
                        "GATE_AUTHORIZATION_SUPERSEDED",
                        f"token {token!r} was minted before `proposalDigest` "
                        "joined the authorization binding, and re-digests "
                        "correctly under the 7-key shape that predates this "
                        "contract -- a legitimate pre-change token, not a "
                        "tampered one, but refused exactly as hard: "
                        "publish a fresh authorization with `offer`.")
            record = None
    if record is None:
        raise Refused(
            "GATE_AUTHORIZATION_UNKNOWN",
            f"no authorization event on this target's ledger vouches for "
            f"token {token!r} -- either nothing minted it, or the event "
            "that once did has been edited since and no longer re-digests "
            "to its own token. Publish (or re-publish) with `offer` first.")
    if (record["jobName"] != binding["jobName"]
            or record["units"] != binding["units"]):
        raise Refused(
            "GATE_AUTHORIZATION_MISMATCH",
            f"token {token!r} was minted for job {record['jobName']!r} with "
            f"units {record['units']!r}, not this invocation's own job "
            f"{binding['jobName']!r} with units {binding['units']!r} -- a "
            "token authorizes one exact launch, never a different one.")
    if any(record[key] != binding[key] for key in
           ("commit", "entrypoint", "rung", "revisionSha256", "positionStatus")):
        raise Refused(
            "GATE_AUTHORIZATION_STALE",
            f"token {token!r} was minted against a pin, entrypoint, rung, "
            "revision or position status that no longer match what this "
            "gate call just re-derived -- a fact this launch depends on "
            "moved, never merely elapsed time. Publish a fresh "
            "authorization with `offer`.")
    if any(e.get("kind") == "authorization-consumed" and e.get("token") == token
           for e in events):
        raise Refused(
            "GATE_AUTHORIZATION_CONSUMED",
            f"token {token!r} already authorized one successful `gate` "
            "call and cannot be reused -- single-use, and never a "
            "deletion. Publish a fresh authorization with `offer`.")
    return record


def _verify_gate_proposal(events: list, job: str, record: dict, campaign: dict) -> None:
    """The campaign-proposal precondition (design D4, spec domain
    `submission-proposal`), run immediately after `_verify_gate_authorization`
    and before the `gate`/`authorization-consumed` events are appended --
    never at the top of the ladder, and never over a `record` this
    invocation has not already proven genuine and current.

    Three refusals, checked in an order that answers a narrower question
    each time -- exactly the same discipline `_verify_gate_authorization`
    already keeps for its own four:

    - `GATE_PROPOSAL_UNKNOWN`: `record`'s own `proposalDigest` is `None`
      (a genuine token, minted while no proposal covered this job yet), or
      no `proposal` event on the ledger carries that digest, or the event
      that does no longer re-digests to its own `digest` -- edited after
      publishing, so it cannot be trusted even though the string still
      matches. All three are the same honest answer: nothing here vouches
      for a campaign proposal behind this launch.
    - `GATE_PROPOSAL_MISMATCH`: a genuine, current proposal exists -- but
      it does not name THIS job in its own `jobs` list. A proposal
      authorizes only the jobs it explicitly names, never every job on
      the target.
    - `GATE_PROPOSAL_STALE`: the proposal is genuine and names this job,
      but its OWN frozen `campaign` (`commit`, `jobSet`) no longer equals
      `campaign` -- `_campaign_identity()` re-derived fresh, THIS instant,
      from live disk. The pin moved, or a job folder was added or removed,
      since `propose` last ran. Deliberately never `entrypoint` or
      `positionStatus` (those are `_AUTHORIZATION_BINDING_KEYS`' own
      staleness keys, not the proposal's) -- a transient per-job failure
      moves neither, which is the whole "survives a same-campaign retry"
      guarantee (spec, domain `submission-proposal`).

    No `GATE_PROPOSAL_CONSUMED`: deliberately absent. A campaign proposal
    is multi-use by definition; nothing here ever marks one spent.
    """
    proposal_digest = record.get("proposalDigest")
    proposal = None
    if proposal_digest is not None:
        candidate = next(
            (e for e in events
             if e.get("kind") == "proposal" and e.get("digest") == proposal_digest),
            None)
        if candidate is not None:
            payload = {key: value for key, value in candidate.items()
                       if key not in ("kind", "digest")}
            recomputed = hashlib.sha256(json.dumps(
                payload, sort_keys=True).encode("utf-8")).hexdigest()
            if recomputed == candidate.get("digest"):
                proposal = candidate
    if proposal is None:
        raise Refused(
            "GATE_PROPOSAL_UNKNOWN",
            "the authorization token names no campaign proposal this "
            "target's ledger still vouches for -- either the token was "
            "minted before any proposal covered this job, or the proposal "
            "event that once did has been edited since and no longer "
            "re-digests to its own digest. Publish a campaign proposal "
            "with `propose` first.")
    if job not in (proposal.get("jobs") or []):
        raise Refused(
            "GATE_PROPOSAL_MISMATCH",
            f"the bound proposal names {proposal.get('jobs')!r}, not job "
            f"{job!r} -- a proposal authorizes only the jobs it explicitly "
            "names, never every job on the target.")
    if proposal.get("campaign") != campaign:
        raise Refused(
            "GATE_PROPOSAL_STALE",
            "the proposal's own campaign identity (commit, job set) no "
            "longer matches what this gate call just re-derived from live "
            "disk -- the pin moved, or a job folder was added or removed, "
            "since `propose` last ran. Publish a fresh proposal with "
            "`propose`.")


def _verify_optional_election(job: str, necessity: str, elected: list | None) -> None:
    """The human-election precondition (design D5, spec "Optional
    Classification Requires Explicit Human Election"), run immediately
    after `_verify_gate_proposal` and before the `gate` event is appended.

    `gate` authorizes exactly one job (`args.job`) per call, so "the unit
    this invocation concerns" is that one job, never the opaque `--unit`
    work-unit list `campaign_consent_token()` binds separately. Two
    refusals:

    - `GATE_ELECTION_REQUIRED`: `job` classifies `optional`
      (`classify_remote_necessity`'s own verdict -- the recorded facts do
      not decide, never "you may skip it") and this invocation's own
      `--elect` does not name it. There is no default and no
      `--elect-all`: an election is argv, per invocation, never stored and
      reused (design D5, "the operator's standing rule").
    - `GATE_ELECTION_MISMATCH`: `--elect` names a job other than the one
      this call is gating, or names this job while it does NOT classify
      `optional` -- electing something that was never in question is its
      own kind of mistake, refused rather than silently accepted.
    """
    elected = list(elected or [])
    if necessity == "optional" and job not in elected:
        raise Refused(
            "GATE_ELECTION_REQUIRED",
            f"job {job!r} classifies `optional` (the recorded facts do not "
            "decide whether it needs a remote worker) and this invocation "
            f"names no `--elect {job}` -- an optional job never launches "
            "without an explicit human election, made fresh on every "
            "gate call, never read back from an earlier one.")
    for name in elected:
        if name != job or necessity != "optional":
            raise Refused(
                "GATE_ELECTION_MISMATCH",
                f"--elect {name!r} does not name job {job!r} classifying "
                "`optional` on this invocation -- an election names "
                "exactly the one job this gate call is about to authorize, "
                "and only when its own necessity verdict is `optional`; "
                "electing an unrelated job, or a job the facts already "
                "decide, is refused rather than silently accepted.")


def cmd_propose(args: argparse.Namespace) -> dict:
    """The campaign proposal (design D4, spec domain `submission-
    proposal`): one `kind: "proposal"` event scoped to a whole CAMPAIGN,
    never a single job -- matching `gate --unit`'s own campaign scope, and
    named every job it covers, its intended workers, its dependency edges
    and a human-authored rationale, exactly the four facts the spec's own
    "One Proposal Per Campaign" requirement names.

    Multi-use by design: calling `propose` again appends a FRESH proposal
    event rather than editing or replacing the last one (the ledger's own
    append-only discipline, `append_event`'s own rationale) -- there is no
    mint-if-absent here, unlike `offer`'s authorization tokens, because a
    proposal is never consumed and reusing an unconsumed one is exactly
    the point (spec "proposal survives a same-campaign retry"). The newest
    proposal naming a given job is the one `_authorization_binding` binds
    a freshly minted token to (`_proposal_digest`); older ones are simply
    superseded by a later proposal naming the same job, never deleted.

    `--job` (repeatable, required) is the human-declared subset of
    currently discovered job folders THIS proposal actually authorizes --
    checked at `gate` time for job MEMBERSHIP (`GATE_PROPOSAL_MISMATCH`).
    `campaign` (`commit`, `jobSet`), by contrast, is never argv: it is
    `_campaign_identity()`'s own live-disk snapshot of EVERY job folder
    currently discovered, re-derived identically at `gate` time to detect
    drift (`GATE_PROPOSAL_STALE`) -- the two are deliberately different
    facts, checked in that order because they answer narrower questions
    in turn (design "What `gate` refuses").

    `--rationale` is required and non-blank, the same discipline `gate`'s
    own `--justification` already keeps: a human-legible reason, recorded
    on the transition, never inferred from a general "go ahead".
    """
    target = resolve_target(args.target)
    name = validate_name(args.name)

    rationale = sys.stdin.read() if args.rationale == "-" else args.rationale
    rationale = rationale.strip()
    if not rationale:
        raise Refused(
            "EMPTY_RATIONALE",
            "propose requires a non-blank rationale: a human-legible "
            "reason for this campaign, recorded on the transition, never "
            "inferred from a general 'go ahead' -- the same discipline "
            "`gate`'s own --justification already keeps.")

    ledger_path = target / name / ".implementation" / "position.jsonl"
    events = impl_position.read_events(ledger_path)

    rcli = _load_remote_execution_cli()
    campaign = _campaign_identity(target, rcli)

    depends_on = []
    for edge in (args.depends_on or []):
        job, _, dependency = edge.partition(":")
        depends_on.append({"job": job, "on": dependency})

    propose_ordinal = sum(1 for e in events if e.get("kind") == "proposal")
    recorded_at = _now_iso8601()
    # `mintOrdinal`'s exact rationale (`_find_or_mint_authorization`'s own
    # docstring): `_now_iso8601()` has second-level precision, so an
    # identical payload published twice inside the same second and the
    # same session would otherwise digest identically. `proposeOrdinal`
    # closes it here the same way, disk-derived and monotonic.
    payload = {
        "jobs": list(args.jobs), "workers": list(args.workers),
        "dependsOn": depends_on, "rationale": rationale,
        "campaign": campaign, "session": args.session, "at": recorded_at,
        "proposeOrdinal": propose_ordinal,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    event = {"kind": "proposal", "digest": digest, **payload}
    impl_position.append_event(ledger_path, event)

    return {
        "command": "propose", "target": str(target), "name": name,
        "status": "recorded", "digest": digest, **payload,
    }


def cmd_gate(args: argparse.Namespace) -> dict:
    """The launch authorization record (design §4, domain launch-authorization).

    Binds `smokeReady`'s already-measured pass/fail to a human-drafted,
    non-blank justification and appends the pair as one `gate` event -- the
    record `remote_cli._verify_launch_authorization()` reads back before a
    non-rehearsal `submit` may run. Prints no token: the whole
    point of this mechanism is that a caller cannot mint the record by
    computing a digest over its own argv (design §4.1) -- it can only exist
    because a rehearsal already ran and was recorded, read back here
    through `remote_execution_jobs_state()`'s own `smokeReady`.

    `--unit`, repeatable, authorizes a CAMPAIGN launch instead of a
    single-send one (PR8, `the-position-nobody-holds` -- design revision:
    PR7 exempted campaign mode entirely, on the mistaken premise that no
    ordered unit list was knowable at gate time; it is knowable, it is the
    exact list the caller intends to pass `submit --unit ...`, the same
    list `distribute --unit ...` already mints its own consent token
    against). It binds the exact ordered list a later `submit --unit ...`
    will carry -- the SAME derivation `remote_cli.campaign_consent_token()`
    already uses for consent, never a second one invented for this record.
    `--worker` and `--unit` are mutually exclusive here, mirroring
    `remote_cli.cmd_submit()`'s own rule: campaign mode has no single named
    account for `--worker` to authorize (`packer.distribute()` spreads
    across every healthy account instead), so a campaign record's own
    `worker` field is always `None` -- exactly what a campaign `submit`
    invocation's own binding always is, and what
    `_verify_launch_authorization()` therefore matches against.

    Checked in refusing-costs-nothing order: the `--worker`/`--unit`
    conflict and the justification first (both pure argv, no I/O at all),
    then whether `--authorization` was given at all (also pure argv --
    `GATE_AUTHORIZATION_REQUIRED`), then the revision, then whether a
    position section exists and is current to reach a rung in, then
    whether every tick already in it was derived rather than asserted
    (`POSITION_UNBACKED`), then the un-forgeable readiness measurement,
    then whether the rung this job's witness names has actually been
    reached -- a launch that skips a rung is refused and the hole is
    visible. Only once every one of those stands does the PRESENTED
    token itself get verified (`_verify_gate_authorization`, design
    "What `gate` refuses"), immediately before the record is appended --
    the four-code check (`GATE_AUTHORIZATION_UNKNOWN`/`_MISMATCH`/
    `_STALE`/`_CONSUMED`) runs last because it is the only one that needs
    the binding this call is about to record, and running it any earlier
    would mean re-deriving that binding twice.
    """
    target = resolve_target(args.target)
    name = validate_name(args.name)
    _require_no_open_defect(target, name)

    if args.units and args.worker is not None:
        raise Refused(
            "GATE_WORKER_UNIT_CONFLICT",
            "--worker and --unit are mutually exclusive: campaign mode "
            "(--unit) authorizes the ordered unit list a later `submit "
            "--unit ...` will carry, and that launch names no single "
            "account -- the same reason `submit` itself refuses --worker "
            "together with --unit.")
    if not args.units and args.worker is None:
        raise Refused(
            "GATE_WORKER_REQUIRED",
            "gate requires --worker unless --unit authorizes a campaign: "
            "a single-send or rehearsal launch names exactly one account, "
            "and there is no auto-select shape for gate to authorize -- an "
            "auto-selected submit invocation (no --worker) can never match "
            "any gate record.")

    justification = sys.stdin.read() if args.justification == "-" else args.justification
    justification = justification.strip()
    if not justification:
        raise Refused(
            "EMPTY_JUSTIFICATION",
            "gate requires a non-blank justification: a human-legible reason "
            "for this launch, recorded on the transition, never inferred "
            "from a general 'go ahead'.")

    if args.authorization is None:
        raise Refused(
            "GATE_AUTHORIZATION_REQUIRED",
            "gate requires --authorization: a token minted by a prior "
            "`offer` publish over this exact launch's binding (job, pin, "
            "entrypoint, units, rung, revision, position status). There is "
            "no default and no override -- a launch is authorized by a "
            "distinct, engine-authored, prior act, never by omission. Run "
            "`offer` first and pass the token its `launch` action's "
            "`binding.authorization` names.")

    source = revision_source(args.revision)
    if source is None:
        raise Refused(
            "REVISION_UNREADABLE",
            f"{args.revision!r} is not readable under {FORGE_ROOT / 'proposals'}; "
            "a gate cannot be recorded against a revision that cannot be read.")
    revision_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()

    evidence = _position_write_evidence(target, name)
    position = position_state(target, name, evidence, args.revision, source)
    smoke_ready = evidence["smokeReady"]
    verdict = impl_availability.launch_available(
        status=position["status"], unbacked=position["unbacked"],
        disagreements=_launch_disagreements(position),
        sequence=position["sequence"], ready=smoke_ready.get(args.job),
        job=args.job, shards_declared=evidence["shardsArrived"] is not None,
        levels=evidence["levels"], attained_level=position["attainedLevel"])
    if not verdict["available"]:
        code, facts = verdict["code"], verdict["facts"]
        if code == "POSITION_ABSENT":
            raise Refused(
                "POSITION_ABSENT",
                "no position section has been derived for this target; run "
                "`position` (--sequence or --reconcile) before a launch can be "
                "gated against it.")
        if code == "POSITION_STALE":
            raise Refused(
                "POSITION_STALE",
                "the position section is bound to a revision whose bytes no "
                "longer match; run `position` again before gating a launch "
                "against it.")
        if code == "POSITION_UNBACKED":
            # Ordered after stale/absent and before `NOT_READY` on purpose. The
            # two above are about whether there is a position to read at all;
            # this one is about whether the position that IS there says only
            # what somebody measured. A gate whose entire premise is that the
            # recorded sequence is honest cannot pass over a step asserted by a
            # hand-typed `x` whose witness nothing has ever looked at -- that is
            # the same forgery `NOT_READY` exists to refuse one rung further
            # down, and refusing it here costs nothing but a list this call
            # already computed.
            raise Refused(
                "POSITION_UNBACKED",
                "item(s) "
                f"{', '.join(str(o) for o in facts['unbackedOrdinals'])} "
                "in the position section are ticked and their witnesses were "
                "never measured; a launch is not authorized against an assertion "
                "nobody checked. Run `position` (with `--shards` if a shard "
                "witness needs it) so every tick is derived, or blank the mark "
                "until its evidence exists.")
        if code == "POSITION_SHARDS_UNDECLARED":
            # A distinct fact from `POSITION_UNBACKED`, not a narrower
            # spelling of it: this item's tick is not unmeasured because a
            # declared location was checked and found silent -- nothing was
            # ever told where to look at all. `gate` has no `--shards` flag
            # of its own, so the only exit here is the target's own
            # declaration; naming that, rather than repeating `POSITION_
            # UNBACKED`'s "run position with --shards", is the entire point
            # of this code.
            raise Refused(
                "POSITION_SHARDS_UNDECLARED",
                "item(s) "
                f"{', '.join(str(o) for o in facts['undeclaredOrdinals'])} "
                "in the position section carry a `@shard` witness, and "
                "nothing named where a returned shard lands -- this target "
                "declares no `distribution.shardsRoot` (see "
                "`assets/kit/src_benchmark/__init__.py`'s `distribution` "
                "comment). A launch is not authorized against a witness "
                "nothing can check at all -- ticked, so the mark asserts what "
                "was never measured, or blank and leveled, so it holds "
                "attainment below every rung; declare `shardsRoot` once, or run "
                "`position --shards <dir>` against an explicit directory "
                "before gating a launch.")
        if code == "POSITION_DISAGREES":
            # Ordered immediately after `POSITION_UNBACKED`, same rationale:
            # both are honesty checks over what the sequence records, not
            # over whether the world is ready. A ticked item whose own
            # witness disagrees with the mark is not "reached", regardless
            # of what its box says -- the reproduced incident this refusal
            # closes (`mark=x`, `derive()` verdict `disagrees=True`) reached
            # `available: True` before this check existed.
            raise Refused(
                "POSITION_DISAGREES",
                "item(s) "
                f"{', '.join(str(o) for o in facts['disagreeingOrdinals'])} "
                "in the position section are ticked but their own witness "
                "disagrees with the mark; a launch is not authorized against "
                "a tick that contradicts its own measurement. Run `position` "
                "again so the mark and the measurement agree.")
        if code == "NOT_READY":
            raise Refused(
                "NOT_READY",
                f"job {args.job!r} has no passing rehearsal recorded at its "
                "current pin (`remote_execution_jobs_state()['smokeReady']` is "
                "not True); a rehearsal must actually run and be recorded "
                "before this launch can be authorized -- readiness cannot be "
                "asserted, only measured.")
        if code == "SEQUENCE_NOT_REACHED":
            if facts["reason"] == "no_witness":
                raise Refused(
                    "SEQUENCE_NOT_REACHED",
                    f"no sequence item names `@rehearsal {args.job}` as its "
                    "witness; gate only authorizes a launch the sequence "
                    "already names.")
            raise Refused(
                "SEQUENCE_NOT_REACHED",
                f"item {facts['earliestOpenOrdinal']} in the sequence is not "
                f"yet ticked; item {facts['jobOrdinal']} (`@rehearsal "
                f"{args.job}`) cannot be gated ahead of it -- a launch that "
                "skips a rung is refused.")
        # code == "RUNG_NOT_ATTAINED" (spec "launch-rung-gate", checked
        # strictly last by `launch_available` -- see that function's own
        # docstring for why nothing above this branch could ever move).
        raise Refused(
            "RUNG_NOT_ATTAINED",
            f"job {args.job!r}'s witness sits on a declared rung ladder "
            f"({facts['levels']!r}), and the evidence currently attains "
            + (f"{facts['attainedLevel']!r}" if facts["attainedLevel"] is not None
               else "no rung at all")
            + f", short of {facts['requiredLevel']!r} -- the rung this "
            "launch requires. A launch is not authorized below the "
            "ladder's own floor for attainment; run `position` again once "
            f"the evidence reaches {facts['requiredLevel']!r}.")

    rcli = _load_remote_execution_cli()
    job_dir = run_config = None
    for candidate in _discovered_job_folders(target, rcli):
        try:
            candidate_config = rcli.JOBFOLDER.read(candidate).run_config
        except rcli.JOBFOLDER.JobFolderError:
            continue
        if candidate_config.get("jobName", candidate.name) == args.job:
            job_dir, run_config = candidate, candidate_config
            break
    if job_dir is None:
        # `smoke_ready.get(args.job) is True` above already requires this job
        # to have been discovered and read successfully -- reaching here
        # would mean the filesystem changed between those two reads.
        raise Refused(
            "NOT_READY",
            f"job {args.job!r} passed its readiness check but could no "
            "longer be located on disk; nothing to record a launch against.")

    commit = run_config.get("commit")
    entrypoint = str((job_dir / rcli.JOBFOLDER.RUNNER_FILENAME).relative_to(target))
    if args.units:
        # Campaign form: the operator-declared ordered list this record
        # authorizes, hashed IN THE GIVEN ORDER by `campaign_consent_
        # token()` too -- never sorted, never deduplicated, never read back
        # from `run_config`, which never carries a campaign's dynamically
        # distributed per-worker assignment (that split is `packer.
        # distribute()`'s own decision at dispatch time, made after consent
        # and authorization are both already given -- not anyone's to
        # authorize in advance).
        units = list(args.units)
        worker = None
    else:
        # Single-send / rehearsal form: a job folder's own declared,
        # static `units` field -- unrelated to a campaign's ordered
        # `--unit` list, and empty on every job folder this forge
        # generates today (no job-folder schema field named `units`
        # exists), matching the empty binding a single-send `submit`
        # invocation always carries.
        units = list(run_config.get("units") or [])
        worker = args.worker

    # The full authorization check (design "What `gate` refuses"), over
    # THIS invocation's own fresh re-derivation -- `rung` is the identical
    # `jobOrdinal` fact `_offer_launch_action` bound when it minted, read
    # off the SAME verdict this call already computed above, never
    # recomputed a second, possibly-drifting way.
    ledger_path = target / name / ".implementation" / "position.jsonl"
    events = impl_position.read_events(ledger_path)
    # `campaign` (design D4) is computed here, before `gate_binding`, so
    # the SAME snapshot both feeds `gate_binding`'s own `proposalDigest`
    # entry (below) and `_verify_gate_proposal`'s fresh STALE comparison
    # -- never two separately re-derived copies inside one `gate` call.
    campaign = _campaign_identity(target, rcli)
    gate_binding = {
        "jobName": args.job, "commit": commit, "entrypoint": entrypoint,
        "units": units, "rung": verdict["facts"]["jobOrdinal"],
        "revisionSha256": revision_sha256, "positionStatus": position["status"],
        # `proposalDigest` is present here only so this literal's key set
        # matches `_AUTHORIZATION_BINDING_KEYS` (the structural test this
        # change adds); `_verify_gate_authorization` never compares it
        # against the record -- `_verify_gate_proposal` (below) owns that
        # verification, against the record's own frozen value, never this
        # freshly re-derived one (see the comment beside
        # `_AUTHORIZATION_BINDING_KEYS` itself).
        "proposalDigest": _proposal_digest(events, campaign),
    }
    record = _verify_gate_authorization(events, args.authorization, gate_binding)

    _verify_gate_proposal(events, args.job, record, campaign)

    # The classification this job's own facts decide (design D3,
    # `the-pilot-decides-the-remote-strategy`), computed the same
    # already-tolerated way `cmd_probe` computes it -- one `search`/
    # `probe_state`/`search_cost_forecast` call this command did not
    # already need for anything else, over the SAME `run_config` this
    # loop already opened, never a second `JOBFOLDER.read()`.
    gate_resolved = resolve_benchmark_declaration(target, name)
    gate_report = report_state(target, name, package_name(name))
    gate_search = search_state(
        gate_resolved["contract"],
        list((gate_report.get("declared") or {}).get("records") or []),
        target / name, declaration_status=gate_resolved["status"],
        digest=source_digest(target, package_name(name)))
    gate_state = probe_state(target, name, args.revision)
    gate_cost_forecast = search_cost_forecast(
        gate_state.get("reduction") or {}, declared_required_scale(gate_search))
    gate_necessity = impl_execution_strategy.classify_remote_necessity(
        jobs=[{"job": args.job, "accelerator": run_config.get("accelerator"),
               "localBudget": run_config.get("localBudget"),
               "smokeReady": smoke_ready.get(args.job, False)}],
        results_status=gate_state["status"], cost_forecast=gate_cost_forecast)
    necessity_verdict = gate_necessity["jobs"][args.job]["necessity"]
    _verify_optional_election(args.job, necessity_verdict, args.elected)

    recorded_at = _now_iso8601()
    elected = list(args.elected or [])
    event = {
        "kind": "gate", "jobName": args.job, "worker": worker,
        "commit": commit, "revision": args.revision,
        "revisionSha256": revision_sha256, "entrypoint": entrypoint,
        "units": units, "justification": justification,
        "session": args.session, "at": recorded_at,
        # Additive (design D5): a fact of this transition, read by
        # nobody in this change -- `remote_cli`'s own fold selects on
        # `kind == "gate"` and ignores unknown fields.
        "elected": elected,
    }
    impl_position.append_event(ledger_path, event)
    # Single-use, appended alongside the `gate` event it authorizes -- never
    # a deletion of the `authorization` event itself (`append_event`'s own
    # append-only rationale). A LATER gate call presenting the same token
    # will fold this event in `_verify_gate_authorization` and refuse
    # `GATE_AUTHORIZATION_CONSUMED`.
    impl_position.append_event(ledger_path, {
        "kind": "authorization-consumed", "token": args.authorization,
        "session": args.session, "at": recorded_at,
    })

    return {
        "command": "gate", "target": str(target), "name": name,
        "status": "recorded", "job": args.job, "worker": worker,
        "commit": commit, "revision": args.revision,
        "revisionSha256": revision_sha256, "entrypoint": entrypoint,
        "units": units, "justification": justification,
        "session": args.session, "readiness": True, "recordedAt": recorded_at,
        "elected": elected,
    }


def _offer_launch_action(target, name, args, rcli, position, evidence, job_dir):
    """One `launch` action for `job_dir`, or `None` when it is absent.

    Absence has three, unrelated causes, and none of them is an error:
    the shared rule says this job's launch is not available yet; the job
    folder's own `run-config.json` names no `commit` to launch against; or
    the job names a `service` no reporter answers for (the registry was
    never given one under that name, or the one it was given could not
    read what is on disk right now -- see `adapter.py`'s fourth registry
    for the contract every registered reporter keeps). Every one of the
    three is silence, matching requirement 4: unavailable is omitted,
    never disabled-with-a-reason.
    """
    try:
        run_config = rcli.JOBFOLDER.read(job_dir).run_config
    except rcli.JOBFOLDER.JobFolderError:
        return None
    job_name = run_config.get("jobName", job_dir.name)

    verdict = impl_availability.launch_available(
        status=position["status"], unbacked=position["unbacked"],
        disagreements=_launch_disagreements(position),
        sequence=position["sequence"],
        ready=evidence["smokeReady"].get(job_name), job=job_name,
        shards_declared=evidence["shardsArrived"] is not None,
        levels=evidence["levels"], attained_level=position["attainedLevel"])
    if not verdict["available"]:
        return None

    commit = run_config.get("commit")
    if not commit:
        return None

    service = run_config.get("service")
    if not service:
        return None
    # The identical dynamic-load path every other `remote_cli` command
    # uses to reach a backend by name (design threat matrix, "Dynamic
    # module load driven by file content"): `_BACKEND_NAME_RE` plus
    # `relative_to(adapters_dir)`, unchanged, never a path built here.
    rcli._load_backend_module(service)
    reporter = rcli.ADAPTER.resolve_declared_capacity(service)
    if reporter is None:
        return None
    capacity = reporter()
    if capacity is None:
        return None
    workers, per_worker = capacity

    entrypoint = str((job_dir / rcli.JOBFOLDER.RUNNER_FILENAME).relative_to(target))
    # Operator-declared, never engine-substituted (design decision 3,
    # "operator-declared unit list is preserved"): `--unit` at `offer` is
    # the SAME ordered list a later `gate --unit ...` and `submit --unit
    # ...` will carry, so the token minted for this binding covers exactly
    # that list. Falling back to the job folder's own static `units` field
    # (unrelated to a campaign, empty on every job folder this forge
    # generates) only when the operator declares none, which keeps the
    # single-send shape this action has always published. `gate_flags`
    # mirrors `remote_cli.py`'s own campaign-vs-single-send command text
    # (`campaign_consent_token()`'s caller) so a caller who declares a
    # campaign here is handed a command shaped like the record that will
    # actually authorize it, never `--worker <account>`, which `gate`'s own
    # mutual exclusivity would refuse for a campaign.
    if args.units:
        units = list(args.units)
        gate_flags = " ".join(f"--unit {unit!r}" for unit in units)
    else:
        units = list(run_config.get("units") or [])
        gate_flags = "--worker <account>"

    return {
        "id": "launch",
        "command": (
            "implementation_cli.py gate "
            f"--target {target} --name {name} --revision {args.revision} "
            f"--session {args.session} --job {job_name} {gate_flags} "
            "--justification -"
        ),
        "establishes": f"records launch authorization for job {job_name!r}",
        "binding": {
            "workers": workers, "perWorker": per_worker,
            "declaredCapacity": workers * per_worker,
            "job": job_name, "commit": commit, "entrypoint": entrypoint,
            "units": units, "rung": verdict["facts"]["jobOrdinal"],
        },
    }


def _authorization_binding(action: dict, revision_sha256: str, position_status: str,
                           events: list, campaign: dict) -> dict:
    """The identity two mints of the SAME upcoming launch must agree on
    (design decision 3, "mint-if-absent") -- everything the engine itself
    re-derives about what is about to be launched, and nothing an agent's
    own argv could vary independently.

    `worker` is deliberately absent. `_offer_launch_action`'s published
    command names `--worker <account>` as a placeholder because the engine
    cannot derive which account a single-send `submit` will actually name
    at publish time -- binding it here would require guessing an account or
    minting one token per account, and this mechanism does neither. The
    account is bound later, by the `gate` event itself, which
    `remote_cli._verify_launch_authorization()` already matches against
    separately -- this token does not authorize a particular account, only
    the job/pin/entrypoint/units/rung/revision/position/proposal shape of
    the launch. `justification` is likewise absent: it is authored at gate
    time from argv, and digesting it would make the token partly
    argv-derivable -- the exact defect class this mechanism exists to
    close.

    `proposalDigest` (design D4, `the-pilot-decides-the-remote-strategy`)
    is engine-derived here too, from `events` and `campaign` (the SAME
    `_campaign_identity()` snapshot `cmd_offer` computed once for every
    action this call publishes) -- the newest CURRENTLY-matching
    `proposal` event (`_proposal_digest`), never filtered by job name:
    every job a campaign proposal names binds to the SAME proposal, the
    same way `gate --unit` already authorizes the whole campaign, not one
    job's slice of it. Never from argv; there is no `--proposal` flag
    anywhere in this file.
    """
    binding = action["binding"]
    return {
        "jobName": binding["job"], "commit": binding["commit"],
        "entrypoint": binding["entrypoint"], "units": list(binding["units"]),
        "rung": binding["rung"], "revisionSha256": revision_sha256,
        "positionStatus": position_status,
        "proposalDigest": _proposal_digest(events, campaign),
    }


def _find_or_mint_authorization(ledger_path: Path, events: list, binding: dict,
                                session: str, at: str) -> str:
    """The authorization token for `binding`: an existing unconsumed one if
    the ledger already carries one, or a freshly minted one appended now
    (design decision 3, "mint-if-absent, not mint-on-every-publish" -- the
    same discipline `cmd_close`'s own `prior_close` lookup already uses. A
    repeat `offer` publish over unchanged state therefore appends no second
    `authorization` event, matching the roster's narrowed "no second
    *offer* event" prose).

    The token is `sha256(json.dumps(payload, sort_keys=True))` over
    `binding` plus `session` and `at` -- the same canonical digest form
    `cmd_close` already uses for `positionDigest`. It is a digest, never a
    secret: `offer` and `gate` run as separate one-shot processes, so
    nothing stored in a file an agent reads could be kept secret from that
    same agent. What a later `gate --authorization <token>` checks is
    publication -- does an engine-authored ledger event exist that binds
    THIS exact re-derived state -- never knowledge of a value; forging the
    digest is free and useless without the matching event.

    `session`/`at` are mint discriminators baked into the digest, never
    compared against a clock: they are what lets a SECOND, distinct
    authorization exist for an otherwise-unchanged binding once the first
    has been consumed (`kind: "authorization-consumed"`, appended by a
    later `gate`, Slice 2B) -- excluded here so a stale but still-unconsumed
    mint is found and reused rather than duplicated.

    `mintOrdinal` is a THIRD discriminator, additive to `session`/`at`
    (Slice 2B, closing a defect Slice 2A's own apply session flagged rather
    than fixed out of scope). `_now_iso8601()` has SECOND-level precision:
    verified by execution, an identical `binding` + identical `session` +
    identical wall-clock second reproduces the IDENTICAL digest. So a
    caller who consumes a token and then re-publishes with `offer` again,
    inside the same second and the same session, would otherwise re-mint
    the exact token that was just consumed -- `gate` would then refuse a
    genuinely fresh authorization as `GATE_AUTHORIZATION_CONSUMED`. Fails
    CLOSED, not open (it can never authorize anything extra), but it is a
    real defect, not a hypothetical one. `mintOrdinal` -- the count of
    every PRIOR `authorization` event already on this exact ledger,
    regardless of binding -- closes it without touching `_now_iso8601()`
    (a pre-existing, forge-wide, shared timestamp convention this mechanism
    does not own) and without comparing anything to a clock: each mint
    appends exactly one `authorization` event before any later mint could
    ever read the ledger again, so the count strictly increases across
    mints and can never repeat. It is also deterministic and disk-derived
    -- replaying the identical ledger from disk always reproduces the
    identical ordinal, unlike a wall clock or a random value.
    """
    consumed = {e["token"] for e in events if e.get("kind") == "authorization-consumed"}
    existing = next(
        (e for e in reversed(events)
         if e.get("kind") == "authorization" and e.get("token") not in consumed
         and all(e.get(key) == value for key, value in binding.items())),
        None)
    if existing is not None:
        return existing["token"]

    mint_ordinal = sum(1 for e in events if e.get("kind") == "authorization")
    payload = {**binding, "session": session, "at": at, "mintOrdinal": mint_ordinal}
    token = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    event = {"kind": "authorization", "token": token, **payload}
    impl_position.append_event(ledger_path, event)
    events.append(event)
    return token


def cmd_offer(args: argparse.Namespace) -> dict:
    """The state-derived action menu: a closed set of what may happen next,
    published only when THIS call supplies an answer to the question this
    branch asks: continue the flow as it stands, or change the experiment
    contract first?

    Records the answer as one `kind: "offer"` event -- the fifth ledger-
    appending command, named after its own event kind the same way
    `position`/`discuss`/`gate`/`close`/`step` already are. The answer is
    a closed token (`yes`/`no`), never free text, and is checked as a
    coded `Refused` rather than an argparse `choices=` list so a bad token
    prints the identical JSON refusal shape every other refusal here
    prints, not `argparse`'s own usage text.

    **`--answer` is a precondition of this call, never a lookup into
    history.** Refuses before publishing anything, in refusing-costs-
    nothing order: `OFFER_UNANSWERED` first (pure argv, no ledger read at
    all) when `--answer` is omitted, then the token check (also pure
    argv), then the revision (I/O). No prior `offer` event's `answer`
    field is ever read to satisfy an omitted `--answer` -- not the newest,
    not any -- so the refusal is identical whether the ledger holds no
    `offer` event, one, or many. Both checks sit above `resolve_target`/
    `revision_source`, and that position is itself the proof: nothing
    below either check could have been consulted before it fires.

    **The appended event is write-only history** (see the comment at the
    `impl_position.append_event` call below): once written, no code path
    under `.claude/skills/**/*.py` ever reads a `kind: "offer"` event's
    fields back into a later decision.

    **`launch` is one per available job**, decided by the identical shared
    rule `gate` itself calls (`impl_availability.launch_available` --
    requirement 5, "no drift between callers": both call the same symbol,
    so their verdicts cannot disagree by construction). `run-step` is
    present iff the supplied token is `yes`; `expand-contract` iff it is
    `no` -- the two describe only what that branch establishes, in branch
    language, and name no specific experiment, notebook or run: which
    ones run and in what order is this proposal's own decision, never
    this command's to narrate.

    **Every published `launch` action carries a minted authorization**
    (design decision 3), a `binding.authorization` digest computed from the
    engine's own re-derived binding facts, never from this call's argv
    alone. Minting is mint-if-absent, not mint-on-every-publish: it runs on
    EVERY call -- `actions` is rebuilt on every call -- but appends a fresh
    `kind: "authorization"` event only when the ledger holds no unconsumed
    one for that exact binding already; a repeat publish over unchanged
    state therefore mints nothing new and republishes the same token.
    `--unit` (repeatable) is the operator-declared ordered list that
    binding covers for a campaign launch instead of a single-send one; the
    engine never substitutes one of its own.

    **The published `command` string now carries `--authorization
    <token>`** (Slice 2B), appended after minting once the token is known.
    `gate` accepts the flag as of this slice, so the command is directly
    runnable rather than one that would refuse `GATE_AUTHORIZATION_REQUIRED`
    on its own advice.
    """
    if args.answer is None:
        raise Refused(
            "OFFER_UNANSWERED",
            "no --answer was supplied on this call; pass --answer yes|no "
            "before an action set can be published. A prior call's answer "
            "is never read back to satisfy this one -- the refusal is "
            "identical whether the ledger holds no offer event at all, "
            "one, or many.")
    if args.answer not in {"yes", "no"}:
        raise Refused(
            "OFFER_ANSWER_NOT_A_TOKEN",
            f"--answer {args.answer!r} is not one of the two closed tokens "
            "yes/no; the offer answer is never free text.")

    target = resolve_target(args.target)
    name = validate_name(args.name)
    _require_no_open_defect(target, name)

    source = revision_source(args.revision)
    if source is None:
        raise Refused(
            "REVISION_UNREADABLE",
            f"{args.revision!r} is not readable under {FORGE_ROOT / 'proposals'}; "
            "offer cannot publish an action set against a revision that "
            "cannot be read.")
    revision_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()

    ledger_path = target / name / ".implementation" / "position.jsonl"
    events = impl_position.read_events(ledger_path)

    evidence = _position_write_evidence(target, name)
    position = position_state(target, name, evidence, args.revision, source)
    rcli = _load_remote_execution_cli()

    actions = []
    for job_dir in _discovered_job_folders(target, rcli):
        action = _offer_launch_action(target, name, args, rcli, position, evidence, job_dir)
        if action is not None:
            actions.append(action)

    answer = args.answer
    if answer == "yes":
        actions.append({
            "id": "run-step",
            "command": (
                "implementation_cli.py step "
                f"--target {target} --name {name} --session {args.session} "
                "--step <step id>"
            ),
            "establishes": "runs the next declared step of the flow this "
                          "call is continuing",
            "binding": {},
        })
    else:
        # Repoints a live harmful write (measured incident: an agent that
        # followed this branch verbatim ran a published `position
        # --reconcile` and appended a real sequence item for a notebook the
        # sequence had never named -- the operator meant this branch as a
        # conversation about what the experiment contract should still
        # add, never a write of its own). `discuss` publishes the
        # conversation instead: it appends only a `discuss` ledger event,
        # never touches `AGREED.md` (spec "expand-contract publishes a
        # runnable command").
        #
        # No `--session` here (design "expand-contract target"): `discuss`
        # is the one write-adjacent command `main()` registers with no
        # `--session` flag at all (only `position`/`gate`/`offer`/
        # `close`/`step` take one). Copying the old string's
        # `--session {args.session}` forward would publish a command
        # argparse refuses outright -- see
        # `OfferCommandTests.test_expand_contract_command_string_is_runnable_and_writes_nothing`,
        # which runs this exact string as a subprocess rather than merely
        # reading it, specifically to catch that trap.
        #
        # `--about record` names the operand-less witness kind: this
        # branch asks what the contract should still add in general, not
        # about one already-declared notebook, rehearsal or shard.
        actions.append({
            "id": "expand-contract",
            "command": (
                "implementation_cli.py discuss "
                f"--target {target} --name {name} --about record "
                "--question 'what should the experiment contract still "
                "add before a campaign may be gated?'"
            ),
            "establishes": "asks what the experiment contract should "
                          "still add before a campaign may be gated, "
                          "recorded as an open discussion rather than a "
                          "write",
            "binding": {},
        })

    recorded_at = _now_iso8601()

    # Mint-if-absent (design decision 3): every published `launch` action's
    # binding gets the authorization token that covers it -- minted now
    # only when no unconsumed one already exists for that exact binding.
    # Runs on every call: `actions` (and therefore what needs an
    # authorization) is rebuilt every time `offer` is called. `campaign`
    # (design D4) is computed ONCE here, shared by every action's own
    # `proposalDigest` lookup -- the same live-disk snapshot every job's
    # token binds to, never a second, possibly-drifting derivation per job.
    campaign = _campaign_identity(target, rcli)
    for action in actions:
        if action["id"] != "launch":
            continue
        binding = _authorization_binding(
            action, revision_sha256, position["status"], events, campaign)
        token = _find_or_mint_authorization(
            ledger_path, events, binding, args.session, recorded_at)
        action["binding"]["authorization"] = token
        # `gate` (Slice 2B) now accepts `--authorization`, so the published
        # command is directly runnable rather than describing one that
        # would refuse `GATE_AUTHORIZATION_REQUIRED` on its own advice.
        # Appended, never interpolated earlier: the token is only known
        # once minting above has run.
        action["command"] += f" --authorization {token!r}"

    # The `offer` event is write-only history (spec "The offer event is
    # documented write-only history"): once this event is appended, no
    # code path under `.claude/skills/**/*.py` ever reads a `kind: "offer"`
    # event's fields back into any later decision -- unlike `gate`/
    # `close`/`step`/`position`, whose events ARE read by later calls.
    # This event exists only as a record of what was asked, by which
    # session, against which revision, and what was published at that
    # moment; the next `offer` call never consults it.
    impl_position.append_event(ledger_path, {
        "kind": "offer", "answer": answer, "revision": args.revision,
        "revisionSha256": revision_sha256,
        "actions": actions, "session": args.session, "at": recorded_at,
    })

    return {
        "command": "offer", "target": str(target), "name": name,
        "status": "recorded", "answer": answer, "revision": args.revision,
        "revisionSha256": revision_sha256,
        "actions": actions, "session": args.session, "recordedAt": recorded_at,
    }


def cmd_close(args: argparse.Namespace) -> dict:
    """The finishing precondition (design §3.3): writing the position
    becomes a precondition of finishing, not a courtesy. `close` refuses
    while a transition has been made and not recorded -- the section never
    generated, bound to a revision that has moved on, ticked over a
    witness nothing could measure, or contradicted by its own measured
    evidence -- and names which one, rather than always succeeding. The
    ladder itself is `impl_availability.position_honest`, the identical
    rule `gate` calls first (through `launch_available`) -- one order, one
    set of codes, never a second refusal ladder this command writes for
    itself.

    **`AGREEMENT_DISAGREES` is a second, independent axis (spec Group 3).**
    A ticked `AGREEMENTS.md`-style checklist item whose declared
    `test_<id>` witness is absent from a fully-parsed `tests/` is refused
    here, after the position ladder and before the refresh -- the only
    place in the whole CLI this ever gates, since `verify`/`probe` only
    ever report it.

    **Checked against the position exactly as recorded, BEFORE the refresh
    that follows.** Refreshing first would silently correct a disagreement
    by rewriting the very mark this refusal exists to catch, which would
    make `POSITION_DISAGREES` unreachable by construction -- `derive()`'s
    own three-valued rule ties every disagreement to a definite verdict a
    refresh would flip on the spot. So the check comes first, over the file
    exactly as it stood when this call began.

    **The refresh that follows a clean check does not only ever ADD
    ticks.** It calls `cmd_position` again, whose own refresh loop writes
    `" "` back over a mark whose witness is now measured and dissatisfied
    -- the loop `continue`s only past a witness still unmeasured, never
    past one that came back a definite `False`. That case cannot reach
    here: the disagreement check immediately above already refused it one
    step earlier, over the position exactly as it stood before any refresh
    ran. So the refresh genuinely can only add ticks *from this point
    forward*, but not because clearing a mark is impossible in general --
    "a caller can never close over marks it never re-derived".

    **`DISCUSSION_UNANSWERED` proves a decision reached the record, never
    that the operator authored it.** The ledger holds an answer; it holds
    nothing about whose it was. An agent can open a question and answer it
    itself, and no check here or downstream can tell that apart from a
    person answering -- the CLI cannot know who typed. Stated rather than
    softened, because a refusal whose name is broader than what it proves
    is read as the wider guarantee by everyone who did not write it.
    """
    target = resolve_target(args.target)
    name = validate_name(args.name)
    _require_no_open_defect(target, name)
    product = target / name

    source = revision_source(args.revision)
    if source is None:
        raise Refused(
            "REVISION_UNREADABLE",
            f"{args.revision!r} is not readable under {FORGE_ROOT / 'proposals'}; "
            "close cannot require a position true against a revision that "
            "cannot be read.")
    revision_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()

    evidence = _position_write_evidence(target, name)
    before = position_state(target, name, evidence, args.revision, source)
    honesty = impl_availability.position_honest(
        status=before["status"], unbacked=before["unbacked"],
        disagreements=before["disagreements"],
        shards_declared=evidence["shardsArrived"] is not None)
    if not honesty["honest"]:
        code, facts = honesty["code"], honesty["facts"]
        if code == "POSITION_ABSENT":
            raise Refused(
                "POSITION_ABSENT",
                "no position section has ever been generated for this target; "
                "run `position` (--sequence or --reconcile) before close can "
                "require it true.")
        if code == "POSITION_STALE":
            raise Refused(
                "POSITION_STALE",
                "the position section is bound to a revision whose bytes no "
                "longer match this one; run `position` again to rebind it "
                "before close can require it current.")
        if code == "POSITION_UNBACKED":
            raise Refused(
                "POSITION_UNBACKED",
                "item(s) "
                f"{', '.join(str(o) for o in facts['unbackedOrdinals'])} "
                "in the position section are ticked and their witnesses were "
                "never measured; close requires the position to be true, not "
                "merely written -- run `position` (with `--shards` if a shard "
                "witness needs it) so every tick is derived, or blank the "
                "mark until its evidence exists.")
        if code == "POSITION_SHARDS_UNDECLARED":
            raise Refused(
                "POSITION_SHARDS_UNDECLARED",
                "item(s) "
                f"{', '.join(str(o) for o in facts['undeclaredOrdinals'])} "
                "in the position section carry a `@shard` witness, and "
                "nothing named where a returned shard lands -- neither an "
                "explicit `--shards <dir>` at `position` nor this target's "
                "own declared `distribution.shardsRoot` (see "
                "`assets/kit/src_benchmark/__init__.py`'s `distribution` "
                "comment). The tick is not unmeasured because nothing was "
                "found; it is unmeasured because nothing was ever told where "
                "to look. Declare `shardsRoot` once, or run `position "
                "--shards <dir>` to tick it against an explicit directory.")
        # code == "POSITION_DISAGREES"
        raise Refused(
            "POSITION_DISAGREES",
            f"{len(facts['disagreeingOrdinals'])} item(s) disagree with "
            "their own measured evidence; close requires the position to be "
            "true, not merely written -- run `position` to see and correct "
            "them, never close over a contradiction.")

    # A second, independent axis from the position ladder above: an
    # AGREEMENTS.md-style checklist item, ticked, whose own declared
    # `test_<id>` witness (spec Group 3) is absent from a fully-parsed
    # `tests/` -- a false claim the same shape as `POSITION_DISAGREES`, one
    # level up. Reported by `verify`/`probe` and gated nowhere but here
    # (spec "Gating stays at close"), so this is the one and only place the
    # CLI ever refuses on it.
    agreements = agreements_state(target, name)
    agreement_disagreements = agreements["witness"]["disagrees"]
    if agreement_disagreements:
        raise Refused(
            "AGREEMENT_DISAGREES",
            "agreement(s) "
            f"{'; '.join(repr(t) for t in agreement_disagreements)} "
            "are ticked and their declared witness function is absent from "
            "a fully-parsed tests/; close requires every ticked agreement's "
            "witness to still name a real function, not merely to have "
            "named one when it was settled.")

    # A third, independent axis (spec Domain A `close-discussion-gate`,
    # this change): the record proves a decision reached it, never that the
    # operator authored it -- an agent can open a question and answer it
    # itself, and nothing downstream can tell. `_open_discussions` buckets
    # by exact trimmed question text and reads only the LAST event in
    # ledger order per bucket (see its own docstring); positioned here,
    # after `AGREEMENT_DISAGREES` and before the refresh below, so the
    # refusal fires before any refresh side effect could run.
    open_discussions = _open_discussions(target, name)
    if open_discussions:
        retirements = "\n".join(
            _discuss_command(target, name, about=_about_arg(item["about"]),
                             question=item["asked"], answer="<answer text>")
            for item in open_discussions)
        raise Refused(
            "DISCUSSION_UNANSWERED",
            "discussion(s) "
            f"{'; '.join(repr(item['asked']) for item in open_discussions)} "
            "were asked and never answered; close requires every opened "
            "discussion to reach a recorded answer, not merely to have "
            "been asked. Retire each with:\n" + retirements)

    # Only unmeasured witnesses can still move here (see docstring): pick up
    # anything that became measurable since the position was last written.
    refresh_args = argparse.Namespace(
        target=args.target, name=args.name, revision=args.revision,
        session=args.session, sequence=None, reconcile=False, replace=False,
        shards=None, target_level=None)
    cmd_position(refresh_args)

    evidence = _position_write_evidence(target, name)
    after = position_state(target, name, evidence, args.revision, source)

    position_digest = hashlib.sha256(
        json.dumps(after["sequence"], sort_keys=True).encode("utf-8")).hexdigest()
    events = impl_position.read_events(product / ".implementation" / "position.jsonl")
    prior_close = next(
        (e for e in reversed(events)
         if e.get("kind") == "close" and e.get("session") == args.session
         and e.get("revisionSha256") == revision_sha256
         and e.get("positionDigest") == position_digest),
        None)
    if prior_close is not None:
        # A second close over the identical, unmoved position closes
        # nothing -- a state, not an error, the sibling deliberation
        # service's own semantics preserved (design §3.3).
        return {
            "command": "close", "status": "not_open", "session": args.session,
            "revision": args.revision, "revisionSha256": revision_sha256,
            "position": after, "recordedAt": prior_close["at"],
        }

    recorded_at = _now_iso8601()
    impl_position.append_event(
        product / ".implementation" / "position.jsonl",
        {"kind": "close", "session": args.session, "revision": args.revision,
         "revisionSha256": revision_sha256, "positionDigest": position_digest,
         "at": recorded_at})

    return {
        "command": "close", "status": "closed", "session": args.session,
        "revision": args.revision, "revisionSha256": revision_sha256,
        "position": after, "recordedAt": recorded_at,
    }


def cmd_step(args: argparse.Namespace) -> dict:
    """Run one declared local step, isolated, under the target's own venv.

    Closes the gap between the isolation rule ("executing a notebook needs
    `PATH`") and any executor for it — before this, that rule was prose a
    target's own steps.py had to obey correctly on its own, with nothing
    checking. `impl_steps.run_step` supplies the isolation (the child's
    `PATH` prefixed by the target's own `.venv/bin`, so a kernelspec's bare
    `python` resolves the right interpreter — the measured motivation:
    297/297 notebooks execute standalone, 15 fail when a bare `python`
    resolves off the wrong environment); the target supplies the callable.

    Runs EXACTLY one named step per invocation. There is no batch or
    sequence flag, and this never consults `probe`'s `nextStep` — a step is
    a unit of isolated execution, not a scheduler.

    Refused in refusing-costs-nothing order, forge-side before target-side:
    `DIRTY_WORKTREE` before anything spawns (a step mutates the target —
    execution counts, cell outputs — so the same guard `plan`/`apply`
    already call applies here, unscoped to migration alone); then
    `STEPS_UNDECLARED` (nothing names any step at all) or `STEP_UNKNOWN`
    (steps exist and this is not one of them) or `STEP_MALFORMED` (the named
    entry is missing `module` or `function`) — all three read statically,
    no import, no subprocess; then `INTERPRETER_ABSENT` (cf.
    `target_interpreter`'s own callers) once a real subprocess is about to
    be spawned. Only past all of those does `impl_steps.run_step` ever run,
    and its own three target-side refusals (`STEP_MODULE_MISSING`/
    `STEP_FUNCTION_MISSING`/`STEP_NOT_CALLABLE`) and `STEP_RUNNER_SILENT`
    propagate unchanged — see its docstring for the full five-row verdict
    state machine.

    Every RESOLVED run — pass or fail — appends exactly one `kind: "step"`
    event to `.implementation/position.jsonl`, carrying `suiteDigest`
    (`suite_digest(target)`, computed fresh at write time); an unresolvable
    step appends nothing, because nothing ran. Written unconditionally,
    regardless of `outcome` — a stale-vs-fresh comparison is exactly as
    meaningful for a suite that just failed as for one that passed, and the
    forge cannot know in advance which steps will raise.

    This reverses "no digest field" only for a step with no self-stamping
    artifact of its own: a notebook already recomputes `source_digest`
    fresh against its own `DIGEST_MARKER` output (`notebooks_state`), so a
    ledger-carried copy there would be redundant and could drift the
    moment the notebook is re-run outside this command. A bare runner step
    — no notebook, no self-stamp — has no other record of what it ran
    against; the ledger line is the only one there is.

    This never touches `gate`: it calls none of `_load_remote_execution_cli`
    or its two siblings, appends a `kind` no `gate` reader ever selects on,
    and reads no `gate` event either. A step's ledger line is invisible to
    `_verify_launch_authorization` by construction, not by convention.
    """
    target = resolve_target(args.target)
    name = validate_name(args.name)
    _require_no_open_defect(target, name)
    require_clean_worktree(target)

    steps = resolve_steps_declaration(target, name)
    if not steps:
        raise Refused(
            "STEPS_UNDECLARED",
            f"{name} declares no __steps__ at all; nothing here names a "
            "callable this command could run.")
    entry = steps.get(args.step)
    if entry is None:
        raise Refused(
            "STEP_UNKNOWN",
            f"{args.step!r} is not among this target's declared steps "
            f"({sorted(steps)!r}).")
    if (not isinstance(entry, dict)
            or not entry.get("module") or not entry.get("function")):
        raise Refused(
            "STEP_MALFORMED",
            f"__steps__[{args.step!r}] does not carry both 'module' and "
            f"'function': {entry!r}")

    # A step that says which rung it advances cannot be run ahead of that
    # rung. The same refusal `cmd_gate` already applies to a launch, applied
    # to local work for the same reason: an ordering that lives only in prose
    # is an ordering nobody is stopped from skipping. Measured -- a pilot
    # search ran through a hand-rolled invocation while the discussion that
    # was supposed to precede every stage had never been held, and nothing in
    # this command had anything to say about it.
    #
    # `advances` is the TARGET's word: this repository names which of its own
    # position items a step produces evidence for, and the forge only compares
    # ordinals. A step that declares none runs ungated, exactly as before --
    # an ordering nobody declared is not one this command invents.
    advances = entry.get("advances")
    if advances is not None:
        if not isinstance(advances, int):
            raise Refused(
                "STEP_MALFORMED",
                f"__steps__[{args.step!r}]['advances'] must be a sequence "
                f"ordinal, not {advances!r}.")
        evidence = _position_write_evidence(target, name)
        position = position_state(target, name, evidence, None, None)
        if position["status"] == "absent":
            raise Refused(
                "POSITION_ABSENT",
                f"{args.step!r} declares it advances item {advances}, but no "
                "position section has been derived for this target; run "
                "`position` first.")
        earlier_open = [item["ordinal"] for item in position["sequence"]
                        if item["ordinal"] < advances and item["mark"] != "x"]
        if earlier_open:
            raise Refused(
                "STEP_SEQUENCE_NOT_REACHED",
                f"item {min(earlier_open)} in the sequence is not yet ticked; "
                f"{args.step!r} advances item {advances} and cannot run ahead "
                "of it -- a step that skips a rung is refused.")

    interpreter = target_interpreter(target)
    if not interpreter.exists():
        raise Refused(
            "INTERPRETER_ABSENT",
            f"no interpreter at {interpreter}: run `env` first.")

    result = impl_steps.run_step(
        interpreter, entry["module"], entry["function"],
        cwd=target, pythonpath=target / "src")

    recorded_at = _now_iso8601()
    event = {
        "kind": "step", "step": args.step,
        "callable": f"{entry['module']}.{entry['function']}",
        "interpreter": str(interpreter),
        "outcome": result["outcome"], "exitStatus": result["exitStatus"],
        "error": result["error"], "session": args.session, "at": recorded_at,
        "suiteDigest": suite_digest(target),
    }
    impl_position.append_event(
        target / name / ".implementation" / "position.jsonl", event)

    return {
        "command": "step", "target": str(target), "name": name,
        "step": args.step, "callable": event["callable"],
        "interpreter": event["interpreter"], "outcome": result["outcome"],
        "exitStatus": result["exitStatus"], "error": result["error"],
        "session": args.session, "recordedAt": recorded_at,
    }


def cmd_defect(args: argparse.Namespace) -> dict:
    """Declare that some forge file is currently broken (design decisions
    1-4, `maintenance-blocks-it-does-not-mix`). `step`, `gate`, `offer`,
    `close`, `settle`, `apply` and `admit` each refuse `FORGE_DEFECT_OPEN`
    while `impl_position.open_defects` reads this declaration as still open
    (`_require_no_open_defect`, design decision 5); `handoff` additionally
    surfaces it.

    Never gated on an already-open defect and calls no `require_clean_
    worktree` (design decision 5): a second declaration while one is open
    must stay possible, and the worktree is likely dirty precisely when
    something is broken. Its own append lands under `.implementation/`,
    which `impl_guards._is_own_bookkeeping` already excuses from
    `DIRTY_WORKTREE` for every command that DOES check it.

    Check order at declaration, each narrower than the one before it
    (`_verify_gate_authorization`'s own ordering discipline): resolve the
    path, non-strict -> containment under `FORGE_ROOT/.claude/skills`
    (`DEFECT_FILE_NOT_FORGE_OWNED`) -> existence as a regular file
    (`DEFECT_FILE_ABSENT`) -> digest. Containment precedes existence on
    purpose -- this command never reports on the existence of anything
    outside `.claude/skills/`.

    `DEFECT_FILE_ABSENT` is design decision 1's whole point: an already-
    absent `--file` is refused, never recorded with `ABSENT_FILE_DIGEST`.
    Recording it would either deadlock (the sentinel compares equal to
    itself at every future check, since the path stays absent) or, if
    clearing were ever special-cased on absence instead, clear on the very
    first check -- the reported bypass. Refusing here keeps both
    unreachable by construction; see `impl_position.open_defects`'s own
    docstring for the comparison this closes.
    """
    target = resolve_target(args.target)
    name = validate_name(args.name)

    resolved = Path(args.file).expanduser().resolve()
    skills_root = (FORGE_ROOT / ".claude" / "skills").resolve()
    try:
        resolved.relative_to(skills_root)
    except ValueError:
        raise Refused(
            "DEFECT_FILE_NOT_FORGE_OWNED",
            f"{resolved} does not live under {skills_root}; a defect can "
            "only be declared against a file this forge itself ships.")
    if not resolved.is_file():
        raise Refused(
            "DEFECT_FILE_ABSENT",
            f"{resolved} is not a regular file; `defect` computes "
            "fileSha256 from --file's live bytes, and there are none here "
            "to measure. The honest reading of a path nobody can find is a "
            "typo or a stale citation -- declare against the file that "
            "fails to find it instead, which exists.")

    forge_relative = resolved.relative_to(FORGE_ROOT.resolve()).as_posix()
    digest = impl_position.current_file_digest(resolved)
    recorded_at = _now_iso8601()
    event = {
        "kind": "defect", "command": "defect", "file": forge_relative,
        "fileSha256": digest, "session": args.session, "at": recorded_at,
    }
    if args.detail:
        event["detail"] = args.detail
    ledger_path = target / name / ".implementation" / "position.jsonl"
    impl_position.append_event(ledger_path, event)

    return {
        "command": "defect", "target": str(target), "name": name,
        "file": forge_relative, "fileSha256": digest,
        "session": args.session, "at": recorded_at,
        "detail": event.get("detail"),
    }


def _require_no_open_defect(target: Path, name: str) -> None:
    """Refuse `FORGE_DEFECT_OPEN` while any declared forge defect for this
    `<target>/<name>` is still open (design decisions 5 and 8,
    `maintenance-blocks-it-does-not-mix`).

    Reads the ledger and re-derives openness through the identical
    `impl_position.open_defects` fold `cmd_handoff` reads for its own
    report, so a refusal here and a surfaced defect there can never
    disagree about what "open" means -- one derivation serves both.

    Called only from `step`, `gate`, `offer`, `close`, `settle`, `apply` and
    `admit`, immediately after `resolve_target`/`validate_name` and before
    `require_clean_worktree` or any other target read -- the earliest point
    at which a ledger path (`<target>/<name>/.implementation/`) exists to
    consult at all. Never called from `defect` itself (declaring a second
    defect while one is open must stay possible) or from any diagnostic
    command (`probe`, `verify`, `position`, `plan`, `compose`, `handoff`,
    `discuss`), which must keep answering while blocked.
    """
    ledger_path = target / name / ".implementation" / "position.jsonl"
    events = impl_position.read_events(ledger_path)
    open_defects = impl_position.open_defects(events, FORGE_ROOT)
    if open_defects:
        files = sorted({event.get("file") for event in open_defects})
        raise Refused(
            "FORGE_DEFECT_OPEN",
            f"{len(files)} forge file(s) carry an open, un-cleared defect "
            f"declaration blocking this command: {files}. A defect clears "
            "only when the named file's current bytes no longer match the "
            "digest recorded against it -- fix the file (or, if it was "
            "moved or deleted, that absence itself clears it) and retry, "
            "or run `handoff` to see every open defect's file, session and "
            "detail.")


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
    stale_refs = scan_stale_references(target, name, paths,
                                       (REFERENCE_RE, PATH_CHAIN_RE))
    # Gating, not merely reported. A file under `tests/` that cannot be parsed
    # cannot be collected, and `structure.status: "ok"` printed beside it is the
    # same silence as a headline reading `ok` beside a benchmark it had just
    # called `undeclared`.
    unparsable = unparsable_tests(target / "tests")
    # The receipt-backed half: whether the destinations `materialize` writes
    # still match what it wrote (SCAFFOLD_DRIFT), and whether one of them
    # exists with no receipt entry explaining it (UNRECORDED_SCAFFOLD). Scoped
    # to the eleven scaffold destinations only — the anchors' correctness is
    # re-derived presence, already covered by `scaffold_gaps` above. The
    # `objects` and `harness` stages get their own sibling checks, over their
    # own three destinations each, so all seventeen kit destinations are
    # accounted for — never only the eleven scaffold ones.
    scaffold_recorded = scaffold_structure_gaps(target, name)
    object_recorded = object_structure_gaps(target, name)
    harness_recorded = harness_structure_gaps(target, name)
    structure_ok = (not missing_dirs and not stray and not stale_refs
                    and not unparsable
                    and not scaffold_gaps(target, name)
                    and not scaffold_recorded["drift"]
                    and not scaffold_recorded["unrecorded"]
                    and not object_gaps(target, name)
                    and not object_recorded["drift"]
                    and not object_recorded["unrecorded"]
                    and not harness_gaps(target, name)
                    and not harness_recorded["drift"]
                    and not harness_recorded["unrecorded"])

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
    discovery = revision_discovery(family)
    discovered = discovery["revision"]
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
        # `note` on every branch, `distribution_state`'s own rule: a key that
        # appears on some branches and not others vanishes for exactly the
        # callers that took the early ones. `None` here and one line below is
        # the honest answer -- `status` already carries the word, and
        # `structure.scaffoldGaps` already names the file that is missing, so
        # a second sentence would be one fact answered twice.
        benchmark = {"status": "absent", "package": f"src/{bench_package}",
                     "note": None}
    elif resolved["status"] == "undeclared":
        benchmark = {"status": "undeclared", "package": f"src/{bench_package}",
                     "detail": resolved["detail"], "note": None}
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
            # Why `unreachedModules` is empty, where the reason is that no arm
            # was declared to cross the modules against. Without it, "no arm
            # reimplements what it claims" and "nobody declared an arm" print
            # the same empty list.
            "note": undeclared_arms_note(target, name, declaration, modules),
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

    # The shard contract, not the report: a report also renders quantities that
    # never sit on a shard — derived readings computed once over everything a
    # campaign produced — and demanding a partition classification for those is
    # a category error, not a missing declaration. `None` here means
    # the universe itself could not be determined, and that is never read as
    # "declares zero dimensions" — see `declared_dimension_names`.
    dimension_names = declared_dimension_names(target, package_name(name))
    # The shard directory is optional and read only when it is given. Omitted,
    # `merged` stays `None` and `distribution_state` answers exactly what it
    # answered before this flag existed.
    #
    # `getattr` rather than `args.shards`: ten call sites in the suite build an
    # `argparse.Namespace` by hand, and an optional flag must not turn each of
    # them into an edit. The cost — a mis-wired flag name would read as an
    # omitted one — is paid off by the cross-join test, which invokes the real
    # parser rather than a hand-built namespace.
    merged = None
    shards_root = getattr(args, "shards", None)
    if shards_root:
        shard_io = _load_remote_execution_shard_io()
        shards = shard_io.read_shards(Path(shards_root))
        distribution_declaration = (
            (resolved["contract"] or {}).get("distribution") or {})
        fields = list(distribution_declaration.get("identicalAcrossShards") or [])
        # Each shard's own stamp, kept rather than thrown away with the rest
        # of the entry. `read_shards` already returns it, and it is the only
        # thing that can say which code a shard reports on -- arrival says a
        # folder exists. `source_digest` is reused verbatim, not recomputed:
        # `notebooks_state` compares a report's stamp against that exact
        # value, and two answers to "what is current" inside one `verify`
        # would be worse than none.
        merged = {"disagreements": shard_io.disagreements(shards, fields),
                  "shardsArrived": [entry["shard"] for entry in shards],
                  "shardsCurrent": _shards_current(
                      shards, distribution_declaration,
                      source_digest(target, package_name(name)))}
    distribution = distribution_state(
        resolved["contract"],
        dimension_names if dimension_names is not None else {},
        merged=merged,
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
    elif resolved["status"] == "undeclared":
        # The four conditions above are all about a declaration that exists. None
        # of them can fire for one that has said nothing yet — `unreached` is only
        # ever computed inside the `declared` branch — so a target with real
        # provenance and every invariant tested reported `ok` with
        # `benchmark.status: "undeclared"` printed directly underneath it, and a
        # reader who acts on the headline stops there. The word is the one the
        # nested block already uses, so the two cannot be read as different facts.
        #
        # `absent` is deliberately not folded in: a target with no Benchmark
        # package has nothing to be unfaithful to, and `structure.scaffoldGaps`
        # already names the file it is missing.
        fidelity_status = "undeclared"
    else:
        fidelity_status = "ok"

    # Computed once and reused for `"search"` below, rather than called twice
    # for the same answer. `position_state`'s evidence is a plain dict of
    # already-computed states (design §3.1) — nothing here is measured a
    # second time, only handed to a reader that derives ticks from it.
    search = search_state(
        resolved["contract"],
        list((report.get("declared") or {}).get("records") or []),
        target / name, declaration_status=resolved["status"],
        digest=source_digest(target, package_name(name)))
    # Read once and used twice: the position evidence below grades every
    # leveled item against this ladder, and `undeclaredLadder` reports the
    # case where there is none. Two calls for one declaration inside one
    # command is how the two answers come to disagree about what the target
    # declared.
    levels = resolve_levels_declaration(target, name)
    # Read once and used twice, the identical constraint `levels` above
    # states for itself: the position evidence below and `undeclaredRecords`
    # (return, below) must read the same declaration or the two can disagree
    # about what the target declared.
    declared_records = resolve_records_declaration(target, name)
    verify_digest = source_digest(target, package_name(name))
    position = position_state(
        target, name,
        {"search": search, "requiredScale": declared_required_scale(search),
         "notebooks": notebooks,
         "smokeReady": remote_execution_jobs_state(target)["smokeReady"],
         "shardsArrived": merged["shardsArrived"] if merged else None,
         "shardsCurrent": merged["shardsCurrent"] if merged else None,
         "levels": levels,
         "stepVerdicts": _step_verdicts(target, name),
         # Design B5 (evidence wiring is three sites): the identical
         # `named_records_state` call `_position_write_evidence` and
         # `cmd_probe`'s own inline dict make, so `verify` never reports
         # `unmeasured` for a `@record:level <name>` witness while `gate`
         # reports it satisfied.
         "records": named_records_state(
             target, name, declared_records, verify_digest)},
        revision, target_source)

    # Computed once, before the return, and reused both inside `audit`
    # (the bare id list) and at the top level (`toDiscuss`, one runnable
    # command per id) -- design D1's new publication surface, spec Domain
    # B "Verify publishes one discuss command per unwritten local remedy
    # finding". Never `prose.staleRevisions`/`unresolvedSymbols` or
    # `agreements.witness.unwitnessed`: both are excluded on their own
    # documented semantics (spec), not by oversight.
    local_remedies_not_written = [
        f["id"] for f in findings
        if finding_impact(f, source or "")["class"] == "local"
        and not f.get("remedy_block")
        and adoption_state(f, source or "")["state"] != "adopted"
    ]
    to_discuss = [_local_remedy_discuss_entry(target, name, finding_id)
                  for finding_id in local_remedies_not_written]

    return {
        "command": "verify",
        "target": str(target),
        "name": name,
        "structure": {
            "status": "ok" if structure_ok else "drift",
            "missingDirs": missing_dirs,
            "strayModules": stray,
            "unparsableTests": unparsable,
            "staleReferences": stale_refs,
            "scaffoldGaps": scaffold_gaps(target, name),
            "scaffoldDrift": scaffold_recorded["drift"],
            "unrecordedScaffold": scaffold_recorded["unrecorded"],
            "objectGaps": object_gaps(target, name),
            "objectDrift": object_recorded["drift"],
            "unrecordedObjects": object_recorded["unrecorded"],
            "harnessGaps": harness_gaps(target, name),
            "harnessDrift": harness_recorded["drift"],
            "unrecordedHarness": harness_recorded["unrecorded"],
        },
        "priorWork": prior_work_state(target, package_name(name)),
        "agreements": agreements_state(target, name),
        # A static fact, reported and never gating, exactly like `coupling`
        # below: see `position_state`.
        "position": position,
        # Reported whatever it says, and it drifts nothing: a historical mention
        # of an older revision is legitimate, and a configuration key quoted like
        # a symbol is not a defect. These are facts for a reader, not verdicts.
        "prose": prose_state(target, revision),
        "search": search,
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
            # What discovery could and could not consider, so a reader never has
            # to guess why a file sitting in `proposals/` was passed over. All
            # three are reported and none of them gates: `verify` reads.
            "markerOwned": discovery["markerOwned"],
            "nonManagedCandidates": discovery["nonManaged"],
            "revisionTie": discovery["tied"],
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
            "localRemediesNotWritten": local_remedies_not_written,
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
        # New top-level key (design D1), never nested under `audit`:
        # `returned_keys` reads dict literals at the top level of a
        # function's own return, so a key buried inside `audit` would ship
        # undocumented and invisible to `VerifyStatusRosterTests`. One
        # entry per `audit.localRemediesNotWritten` id -- see
        # `_local_remedy_discuss_entry`.
        "toDiscuss": to_discuss,
        # Gap 1, "nothing the forge offers stays invisible": the identical
        # constraint that decided `toDiscuss`'s own placement, above --
        # top-level, never nested under `search`/`distribution`, or the
        # entry ships invisible to the same roster test. See
        # `undeclared_optional_state`'s own docstring for why this is
        # reported and never demanded.
        "undeclaredOptional": undeclared_optional_state(search, distribution),
        # The same gap, one declaration over: `__levels__` is the one thing
        # the forge offers that nothing ever asks a target for, and an empty
        # one takes the whole rung discipline out of reach silently. Its own
        # top-level key rather than an `undeclaredOptional` entry -- a
        # module-level literal sits in no `section` and names no `field`, so
        # borrowing that shape would mean writing a section that does not
        # exist. See `undeclared_ladder_state`'s own docstring for why this
        # is reported and never demanded.
        "undeclaredLadder": undeclared_ladder_state(target, name, levels),
        # The other half of the same declaration, and the one `undeclaredLadder`
        # cannot reach: a ladder that WAS named, long enough that the sequence
        # beside it can never climb to the launch floor. Top-level for the
        # identical `returned_keys` constraint, and absent from `probe` for the
        # identical reason -- it names no work about to be run.
        "unreachableLadder": unreachable_ladder_state(
            position["sequence"], levels),
        # The same gap, one declaration over: `__records__` is the other
        # thing the forge offers that nothing ever asks a target for. Its
        # own top-level key rather than an `undeclaredOptional` entry, for
        # the identical reason `undeclaredLadder`'s own is -- see
        # `undeclared_records_state`'s own docstring.
        "undeclaredRecords": undeclared_records_state(target, name, declared_records),
    }


def _crashing_forge_file(exc: BaseException) -> Path | None:
    """The forge module that owns a crash, chosen from `exc`'s own traceback
    (design decision 6, `maintenance-blocks-it-does-not-mix`): walk every
    frame from `exc.__traceback__` toward where it was raised and keep the
    LAST one whose `co_filename` resolves under `FORGE_ROOT/.claude/skills`
    -- never the deepest frame outright, because the deepest frame can be
    stdlib (a mocked callable's own `side_effect` raise, for one), and the
    forge frame that called into it is the one actually responsible. `None`
    when no frame ever qualifies, so a caller with nothing to name records
    nothing rather than guessing.
    """
    skills_root = (FORGE_ROOT / ".claude" / "skills").resolve()
    qualifying = None
    frame = exc.__traceback__
    while frame is not None:
        candidate = Path(frame.tb_frame.f_code.co_filename).resolve()
        try:
            candidate.relative_to(skills_root)
        except ValueError:
            pass
        else:
            qualifying = candidate
        frame = frame.tb_next
    return qualifying


def _record_engine_defect(args: argparse.Namespace, exc: BaseException) -> None:
    """Auto-append one `kind: "defect"` event for a crash `main()` did not
    expect (design decision 6): any exception that reaches `main()`'s
    dispatch other than `Refused` is, by definition, a forge-side bug, and
    this needs no agent cooperation to notice or declare it first.

    `target`/`name` are read with `getattr(..., None)` rather than assumed
    present: `env` never gets a `--name` and `name` never gets a `--target`,
    so neither has a `<target>/<name>/.implementation/` ledger path to
    write into at all -- a stated limit this does not close, see SKILL.md.
    `session` is read the same way and, when absent (`apply` and `admit`
    take none), the key is OMITTED from the event, never written as `null`
    -- the identical discipline `cmd_defect`'s own `detail` already keeps.

    Called only from `main()`'s own guard, itself wrapped in its own
    `try/except Exception: pass` -- a failure in here must never replace
    the original traceback with one about this function instead.
    """
    target_raw = getattr(args, "target", None)
    name_raw = getattr(args, "name", None)
    if target_raw is None or name_raw is None:
        return
    crashing_file = _crashing_forge_file(exc)
    if crashing_file is None:
        return

    forge_relative = crashing_file.relative_to(FORGE_ROOT.resolve()).as_posix()
    digest = impl_position.current_file_digest(crashing_file)
    event = {
        "kind": "defect", "command": args.command, "file": forge_relative,
        "fileSha256": digest, "at": _now_iso8601(),
        "detail": f"{type(exc).__name__}: {exc}",
    }
    session = getattr(args, "session", None)
    if session is not None:
        event["session"] = session

    ledger_path = (Path(target_raw).expanduser().resolve() / name_raw
                   / ".implementation" / "position.jsonl")
    impl_position.append_event(ledger_path, event)
def _materialize_plan_gate(target: Path, name: str, plan_path: str) -> None:
    """The exact pattern `cmd_apply` runs: `PLAN_MISMATCH` when the approved
    plan was produced for a different target/name, `PLAN_STALE` when the
    repository's structure has moved since approval. `materialize --stage`
    reuses it rather than minting a second gate over the same fact.
    """
    approved = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    if approved.get("target") != str(target) or approved.get("name") != name:
        raise Refused("PLAN_MISMATCH",
                      "The approved plan was produced for a different target or name.")
    current = build_plan(target, name)
    if any(current[key] != approved.get(key)
           for key in ("renames", "moves", "createDirs", "referenceUpdates")):
        raise Refused(
            "PLAN_STALE",
            "The repository changed since the plan was approved. Re-run `plan` and get approval again.",
        )


def _materialize_scaffold_destinations(target: Path, name: str) -> list[str]:
    """The stage's destination set: `scaffold_destinations` minus whatever
    already exists on disk. A path already present is never a destination,
    so it can never conflict — see design D1. Factored out so a test can
    monkeypatch this one seam to simulate a destination appearing between set
    computation and the write loop, without weakening the real preflight.
    """
    return [d for d in scaffold_destinations(name) if not (target / d).exists()]


def _stage_scaffold(target: Path, name: str, seed: str) -> dict:
    package_init = f"src/{package_name(name)}/__init__.py"
    destinations = _materialize_scaffold_destinations(target, name)

    bodies: dict[str, str] = {}
    for destination in destinations:
        if destination == package_init:
            continue
        source = scaffold_kit_source(destination, name)
        body = scaffold_substitute_body(
            source.read_text(encoding="utf-8"), name, seed)
        if destination.endswith(".py") and not writable_at_scaffold_time(body):
            raise Refused(
                "STAGE_CANNOT_ANSWER",
                f"{destination} still carries an unresolved token after "
                "scaffold-time substitution; its answer belongs to a later step.",
            )
        bodies[destination] = body

    # Preflight, over the same set the write loop is about to use: a path
    # that appeared here since `_materialize_scaffold_destinations` computed
    # the set is the one genuine race this command can hit, and it refuses
    # the whole stage before a single byte lands.
    conflicts = [d for d in destinations if (target / d).exists()]
    if conflicts:
        raise Refused(
            "DESTINATION_CONFLICT",
            f"Destinations clash (existing file): {conflicts}. Materializing "
            "would overwrite. Resolve with the user first.",
        )

    written: list[str] = []
    try:
        for destination in destinations:
            full = target / destination
            full.parent.mkdir(parents=True, exist_ok=True)
            body = (authored_package_init(name) if destination == package_init
                    else bodies[destination])
            full.write_text(body, encoding="utf-8")
            written.append(destination)

        anchors = _materialize_scaffold_anchors(target, name)
    except Exception as failure:  # noqa: BLE001 - the tree must not stay half-written
        # `require_clean_worktree` proved the tree clean before this ran, so
        # discarding everything just written restores exactly that state.
        git(target, "reset", "-q", "--hard", check=False)
        git(target, "clean", "-qfd", check=False)
        raise Refused(
            "APPLY_ABORTED",
            f"{failure}. Nothing was recorded; the working tree was restored "
            "to its pre-materialize state; re-run `plan` to see the current situation.",
        ) from failure

    recorded_at = _now_iso8601()
    receipt = read_materialization_receipt(target)
    receipt["name"] = name
    for destination in written:
        full = target / destination
        source = scaffold_kit_source(destination, name)
        set_receipt_entry(receipt, {
            "path": destination,
            "kind": "materialized",
            "stage": "scaffold",
            "kitSource": (str(source.relative_to(SKILL_ROOT)) if source else None),
            "sourceSha256": (hashlib.sha256(source.read_bytes()).hexdigest()
                             if source else None),
            "writtenSha256": hashlib.sha256(full.read_bytes()).hexdigest(),
            "substitutions": {"PKG": package_name(name), "SEED": seed},
            "recordedAt": recorded_at,
        })
    for anchor in anchors:
        set_receipt_entry(receipt, anchor)
    write_materialization_receipt(target, receipt)

    return {
        "command": "materialize", "mode": "stage", "stage": "scaffold",
        "target": str(target), "name": name,
        "status": "materialized",
        "written": written,
        "anchors": [a["path"] for a in anchors],
        "note": "The receipt is git-ignored under .implementation/ and is "
                "the only record of what this command wrote.",
    }


#: Mirrors what a fresh `pyproject.toml` looks like when a target has none
#: yet — the same content `materialize.py` has always written, restated here
#: rather than imported so this file never depends on the harness for its own
#: production path (`test_the_production_engine_never_reaches_the_harness`).
_DEFAULT_PYPROJECT = (
    "[build-system]\n"
    'requires = ["setuptools>=68"]\n'
    'build-backend = "setuptools.build_meta"\n\n'
    "[project]\n"
    'name = "{distribution}"\n'
    'version = "0.1.0"\n'
    'requires-python = ">=3.9"\n'
    'dependencies = ["numpy>=1.24"]\n\n'
    "[tool.setuptools.packages.find]\n"
    'where = ["src"]\n'
)


def _materialize_scaffold_anchors(target: Path, name: str) -> list[dict]:
    """Merge the two anchors into whatever the target already has, never
    writing over it — see design D4. Anchors get `kind: "anchor"` receipt
    entries, no byte seal: a user editing `.gitignore` afterwards is not
    drift, and their correctness check is re-derived presence.
    """
    entries: list[dict] = []
    recorded_at = _now_iso8601()

    missing_ignores = ignore_gaps(target)
    if missing_ignores:
        ignore_file = target / ".gitignore"
        existing = ignore_file.read_text(encoding="utf-8") if ignore_file.exists() else ""
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        ignore_file.write_text(
            existing + prefix + "".join(f"{entry}\n" for entry in missing_ignores),
            encoding="utf-8",
        )
        entries.append({"path": ".gitignore", "kind": "anchor", "stage": "scaffold",
                        "added": missing_ignores, "recordedAt": recorded_at})

    if pytest_anchor_missing(target):
        pyproject = target / "pyproject.toml"
        distribution = package_name(name).lower().replace("_", "-")
        text = (pyproject.read_text(encoding="utf-8") if pyproject.exists()
                else _DEFAULT_PYPROJECT.format(distribution=distribution))
        if "[tool.pytest.ini_options]" not in text:
            text += ('\n[tool.pytest.ini_options]\n'
                     'testpaths = ["tests"]\n'
                     'pythonpath = ["src"]\n')
        pyproject.write_text(text, encoding="utf-8")
        entries.append({
            "path": "pyproject.toml", "kind": "anchor", "stage": "scaffold",
            "added": ["[tool.pytest.ini_options] pythonpath"], "recordedAt": recorded_at,
        })

    return entries


def _materialize_object_destinations(target: Path, name: str) -> list[str]:
    """The `objects` stage's own destination set: `object_destinations` minus
    whatever already exists on disk — the identical seam
    `_materialize_scaffold_destinations` gives the scaffold stage, kept as a
    separate function per stage so a test can monkeypatch one without
    touching the others.
    """
    return [d for d in object_destinations(name) if not (target / d).exists()]


def _materialize_harness_destinations(target: Path, name: str) -> list[str]:
    """The `harness` stage's own destination set — see
    `_materialize_object_destinations`."""
    return [d for d in harness_destinations(name) if not (target / d).exists()]


def harness_substitute_body(text: str, name: str) -> str:
    """The one token a harness template might carry: `{{PKG}}`. None of the
    three do today — `benchmark.py`/`verdict.py` carry no token at all, and
    `probe.ipynb`'s tokens (`{{SEEDS}}`, `{{DATASET}}`, `{{EPOCHS}}`, ...) are
    answered by a later step, not this one, and are left standing on purpose,
    the same way `verification.ipynb`'s remaining tokens are. Substituting
    `{{PKG}}` regardless is harmless and keeps this stage exercising the same
    substitution path scaffold and objects do, rather than skipping it.
    """
    return text.replace("{{PKG}}", package_name(name))


def _write_kit_stage(target: Path, name: str, stage: str, destinations: list[str],
                     bodies: dict[str, str], kit_source_fn) -> dict:
    """The write-conflict-preflight / write-loop / abort / receipt sequence
    shared by the `objects` and `harness` stages — the same shape
    `_stage_scaffold` established for `scaffold`, factored out once a second
    and third stage needed it rather than tripled by copy. `_stage_scaffold`
    keeps its own inlined copy: it alone carries the anchor merge and the
    authored `__init__.py` special case, neither of which `objects`/`harness`
    have.

    Deliberately carries no `writable_at_scaffold_time`/`ast.parse` gate —
    see `_stage_objects`'s own docstring for why applying scaffold's gate
    here would make a stage refuse unconditionally, forever.
    """
    conflicts = [d for d in destinations if (target / d).exists()]
    if conflicts:
        raise Refused(
            "DESTINATION_CONFLICT",
            f"Destinations clash (existing file): {conflicts}. Materializing "
            "would overwrite. Resolve with the user first.",
        )

    written: list[str] = []
    try:
        for destination in destinations:
            full = target / destination
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(bodies[destination], encoding="utf-8")
            written.append(destination)
    except Exception as failure:  # noqa: BLE001 - the tree must not stay half-written
        # `require_clean_worktree` proved the tree clean before this ran, so
        # discarding everything just written restores exactly that state.
        git(target, "reset", "-q", "--hard", check=False)
        git(target, "clean", "-qfd", check=False)
        raise Refused(
            "APPLY_ABORTED",
            f"{failure}. Nothing was recorded; the working tree was restored "
            "to its pre-materialize state; re-run `plan` to see the current situation.",
        ) from failure

    recorded_at = _now_iso8601()
    receipt = read_materialization_receipt(target)
    receipt["name"] = name
    for destination in written:
        full = target / destination
        source = kit_source_fn(destination, name)
        set_receipt_entry(receipt, {
            "path": destination,
            "kind": "materialized",
            "stage": stage,
            "kitSource": (str(source.relative_to(SKILL_ROOT)) if source else None),
            "sourceSha256": (hashlib.sha256(source.read_bytes()).hexdigest()
                             if source else None),
            "writtenSha256": hashlib.sha256(full.read_bytes()).hexdigest(),
            "recordedAt": recorded_at,
        })
    write_materialization_receipt(target, receipt)

    return {
        "command": "materialize", "mode": "stage", "stage": stage,
        "target": str(target), "name": name,
        "status": "materialized",
        "written": written,
        "note": "The receipt is git-ignored under .implementation/ and is "
                "the only record of what this command wrote.",
    }


def _stage_objects(target: Path, name: str, seed: str) -> dict:
    """Writes the three step-9 kit destinations as raw, `{{PKG}}`/`{{SEED}}`-
    substituted templates — deliberately NOT gated by
    `writable_at_scaffold_time`.

    Unlike scaffold's eleven, all three of these templates carry tokens
    (`{{FUNCTION_NAME}}`, `{{INVARIANT_ID}}`, `{{EXPECTATION}}`, ...) sitting
    inside Python identifiers that only step 9's own authoring can answer —
    no CLI flag supplies them, and none should, since answering them IS the
    mathematics step 9 exists to write (confirmed:
    `MaterializeWritesStageOneTests` already establishes these three do not
    survive `ast.parse` after only `{{PKG}}`/`{{SEED}}` are substituted).
    Applying scaffold's `ast.parse` gate here would make this stage refuse
    `STAGE_CANNOT_ANSWER` unconditionally, forever — a refusal no invocation
    could ever satisfy. So these three are written as scaffolding for the
    agent to author over, exactly the destinations `--authored` (design
    decision D2) was built to release the seal on afterward.

    Gated on the step-8 object map having been approved and recorded:
    SKILL.md step 8 requires `revision`/`premises` to be written into
    `src/<Package>_Benchmark/__init__.py` before any step-9 code, and
    `resolve_benchmark_declaration` is the one place that fact is already
    read from disk — reused rather than inventing a second way to ask it.
    """
    declared = resolve_benchmark_declaration(target, name)
    contract = declared["contract"]
    # The two blocks the message names, asked for by name. This gated on
    # `status != "declared"`, and that status is `"undeclared"` only when
    # `_declaration_is_blank` holds -- when ALL SEVEN blocks still carry their
    # scaffold value. So a declaration answering any single one of them opened
    # this gate, and `search` is exactly the block a target can answer long
    # before step 8: measured with `revision: ""`, `premises: {}` and only
    # `search` written, the status is `"declared"`, the gate opened, and the
    # refusal's own sentence described the state that was true and did not
    # refuse. The name of the code and this function's own docstring both say
    # the object map is what is gated on, so the check moved to the message
    # rather than the other way round.
    unwritten = [block for block in ("revision", "premises")
                 if not contract.get(block)]
    if declared["status"] != "declared" or unwritten:
        # Named one by one, never as "revision/premises": a refusal that lists
        # a block already fully written sends somebody to re-read what is
        # already right. On an absent or blank declaration both are unwritten
        # and the sentence reads as it always did.
        raise Refused(
            "OBJECT_MAP_NOT_APPROVED",
            "The step-8 object map has not been approved yet: "
            f"src/{package_name(name)}_Benchmark/__init__.py declares no "
            + " and no ".join(unwritten or ["revision", "premises"])
            + ". --stage objects writes scaffolding for step "
            "9's authoring, not before that approval is recorded.",
        )

    destinations = _materialize_object_destinations(target, name)
    bodies = {
        destination: scaffold_substitute_body(
            object_kit_source(destination, name).read_text(encoding="utf-8"),
            name, seed)
        for destination in destinations
    }
    return _write_kit_stage(target, name, "objects", destinations, bodies,
                            object_kit_source)


def _stage_harness(target: Path, name: str) -> dict:
    """`benchmark.py`/`verdict.py` carry no unresolved token at all;
    `probe.ipynb` carries several (`{{DATASET}}`, `{{EPOCHS}}`, ...) left
    standing on purpose — it is never `.py`, so no `ast.parse` gate ever
    reaches it, the same way `verification.ipynb` is exempt in the scaffold
    stage. `{{SEED}}` itself is not among them (`probe.ipynb` carries
    `{{SEEDS}}`, a distinct token this stage does not answer), so unlike
    scaffold/objects this stage needs no `--seed`.
    """
    destinations = _materialize_harness_destinations(target, name)
    bodies = {
        destination: harness_substitute_body(
            harness_kit_source(destination, name).read_text(encoding="utf-8"), name)
        for destination in destinations
    }
    return _write_kit_stage(target, name, "harness", destinations, bodies,
                            harness_kit_source)


def _kit_destination_stage(path: str, name: str) -> str | None:
    """Which stage's destination list `path` belongs to, or `None` outside
    all three. Used so `--adopt`'s receipt entry records the stage it
    actually adopted into rather than a hardcoded one."""
    if path in scaffold_destinations(name):
        return "scaffold"
    if path in object_destinations(name):
        return "objects"
    if path in harness_destinations(name):
        return "harness"
    return None


def _materialize_authored(target: Path, name: str, path: str) -> dict:
    if path not in all_kit_destinations(name):
        raise Refused("NOT_A_KIT_DESTINATION",
                      f"{path} is not one of this stage's kit destinations.")
    full = target / path
    if not full.exists():
        raise Refused("MATERIALIZE_PATH_ABSENT",
                      f"{path} does not exist; there is nothing to declare authored.")
    receipt = read_materialization_receipt(target)
    entry = receipt_entry(receipt, path)
    if entry is None:
        raise Refused("NO_RECEIPT_ENTRY",
                      f"{path} carries no receipt entry; the engine never wrote "
                      "it, so there is no seal to release. Use --adopt instead.")

    new_sha256 = hashlib.sha256(full.read_bytes()).hexdigest()
    entry = dict(entry)
    entry["kind"] = "authored"
    entry["writtenSha256"] = new_sha256
    entry["recordedAt"] = _now_iso8601()
    set_receipt_entry(receipt, entry)
    write_materialization_receipt(target, receipt)

    return {"command": "materialize", "mode": "authored", "target": str(target),
            "name": name, "path": path, "status": "authored",
            "writtenSha256": new_sha256}


def _materialize_adopt(target: Path, name: str, path: str) -> dict:
    if path not in all_kit_destinations(name):
        raise Refused("NOT_A_KIT_DESTINATION",
                      f"{path} is not one of this stage's kit destinations.")
    full = target / path
    if not full.exists():
        raise Refused("MATERIALIZE_PATH_ABSENT",
                      f"{path} does not exist; there is nothing to adopt.")
    receipt = read_materialization_receipt(target)
    if receipt_entry(receipt, path) is not None:
        raise Refused("ALREADY_RECORDED",
                      f"{path} already carries a receipt entry; adoption is not "
                      "a re-seal. Use --authored to release a drifted seal.")

    new_sha256 = hashlib.sha256(full.read_bytes()).hexdigest()
    set_receipt_entry(receipt, {
        "path": path, "kind": "adopted", "stage": _kit_destination_stage(path, name),
        "writtenSha256": new_sha256, "recordedAt": _now_iso8601(),
        # Stated where the operator reads it: adoption records who is
        # responsible for the bytes, not that the bytes came from the kit.
        # For an adopted destination the guarantee is "the record names who
        # wrote them", not "the engine owns the bytes" -- not equivalent
        # protection to a `materialized` entry, and `kind` is what keeps the
        # two distinguishable forever.
        "guarantee": "the record names who wrote them, not that the engine owns the bytes",
    })
    write_materialization_receipt(target, receipt)

    return {"command": "materialize", "mode": "adopt", "target": str(target),
            "name": name, "path": path, "status": "adopted",
            "writtenSha256": new_sha256,
            "guarantee": "the record names who wrote them, not that the engine owns the bytes"}


def cmd_materialize(args: argparse.Namespace) -> dict:
    target = resolve_target(args.target)
    name = validate_name(args.name)
    _require_no_open_defect(target, name)

    modes_given = [flag for flag in ("stage", "authored", "adopt")
                  if getattr(args, flag, None)]
    if not modes_given:
        raise Refused("MATERIALIZE_MODE_REQUIRED",
                      "Exactly one of --stage, --authored, --adopt is required.")
    if len(modes_given) > 1:
        raise Refused("MATERIALIZE_MODE_CONFLICT",
                      f"--{'/--'.join(modes_given)} were given together; the "
                      "three modes are mutually exclusive.")

    if args.stage:
        # The writer: plan-gated, clean worktree required -- files land on
        # disk and the receipt is written last, atomically.
        require_clean_worktree(target)
        if not args.plan:
            raise Refused("PLAN_REQUIRED", "--stage requires --plan <approved plan JSON>.")
        _materialize_plan_gate(target, name, args.plan)
        # `--seed` substitutes `{{SEED}}`, and only `scaffold`/`objects`
        # templates carry that token (`tests/test_smoke.py`,
        # `tests/test_synthetic.py`); `harness`'s three carry `{{SEEDS}}`
        # instead, a distinct token this command never answers, so demanding
        # `--seed` there would be a decorative requirement with no effect.
        if args.stage in ("scaffold", "objects") and not args.seed:
            raise Refused("SEED_REQUIRED", f"--stage {args.stage} requires --seed.")
        if args.stage == "scaffold":
            return _stage_scaffold(target, name, args.seed)
        if args.stage == "objects":
            return _stage_objects(target, name, args.seed)
        return _stage_harness(target, name)

    # `--authored`/`--adopt`: ledger-only, no file write, no plan gate and
    # deliberately no clean-worktree requirement -- the file the agent just
    # authored is by definition an uncommitted modification. Precedent:
    # `_is_own_bookkeeping` in `_core/implementation/impl_guards.py`.
    if args.authored:
        return _materialize_authored(target, name, args.authored)
    return _materialize_adopt(target, name, args.adopt)


#: The commands that refuse on the repository's own state rather than only on
#: what was typed: every one of them reads the target before it will proceed,
#: and every one can stop a session dead. `GatingRefusalRosterTests` walks
#: exactly these functions for the codes they raise, so adding a command here
#: forces its refusals through the roster below.
#:
#: `position` is here for the reason the criterion states rather than by
#: history: it reads the target before it will write, and every one of its
#: refusals stops a session -- `POSITION_HOLDER_AMBIGUOUS` and
#: `POSITION_LEVELS_UNDECLARED` sat outside this roster and therefore reached
#: their reader as a bare code, which is the exact defect the roster exists to
#: make impossible. It is also the only place `POSITION_RUNG_SKIPPED` can be
#: raised: the rung is decided where the header is sealed, not where a later
#: command reads it back.
GATING_COMMANDS = ("apply", "admit", "gate", "offer", "close", "step",
                   "settle", "materialize", "position")

#: The caller typed something the caller can retype. The detail already names
#: the flag, the token or the mutual exclusion, so nothing is published beside
#: it: a `resolve` key on every refusal is the shape a reader learns to skip,
#: which is how a real one stops being read.
INVOCATION_DEFECT = "invocation"

#: Nothing the caller can type clears this. Somebody has to act on the
#: repository, and the engine says what -- as a command that runs unedited, or
#: as the question a human answers. This is the half that was missing: fifty-
#: four of the fifty-six codes reached a reader as a bare code, `POSITION_
#: DISAGREES` among them, and the agent driving the CLI composed the next
#: question in prose. A harness that must sit above that agent cannot leave the
#: next act to it.
WORK_STATE = "work-state"

#: Every refusal raised inside a gating command, classified by one derivable
#: test: **can the caller clear it by changing the invocation alone, without
#: touching the repository?**
#:
#: The "already" codes (`SETTLE_ALREADY_DONE`, `_ALREADY_WITNESSED`,
#: `_ALREADY_REVERSED`) sit on the invocation side and the reading is worth
#: stating: the repository is already in the state the call asked for, so
#: nothing in it has to change -- what has to change is the call, or the
#: decision to make it at all. `SETTLE_TEXT_ABSENT` is invocation for the same
#: reason `SETTLE_TEXT_AMBIGUOUS` is not: a more exact `--text` reaches the
#: intended line, while two lines that both match exactly cannot be told apart
#: by any argument this command accepts.
GATING_REFUSALS: dict[str, str] = {
    # --- apply -------------------------------------------------------------
    "PLAN_MISMATCH": INVOCATION_DEFECT,      # point --plan at the right file
    "PLAN_STALE": WORK_STATE,                # the repository moved; re-plan
    "DESTINATION_CONFLICT": WORK_STATE,      # a human decides where they go
    "UNCLASSIFIED_FILES": WORK_STATE,        # a human says where they belong
    "APPLY_ABORTED": WORK_STATE,             # the tree was restored; re-plan
    # --- admit -------------------------------------------------------------
    "REVISION_UNREADABLE": INVOCATION_DEFECT,  # name a revision that reads
    "NO_FINDINGS": WORK_STATE,               # the findings have to be written
    # --- gate --------------------------------------------------------------
    "GATE_WORKER_UNIT_CONFLICT": INVOCATION_DEFECT,
    "GATE_WORKER_REQUIRED": INVOCATION_DEFECT,
    "EMPTY_JUSTIFICATION": INVOCATION_DEFECT,
    # No token exists to pass: one is minted by a prior `offer` publish, which
    # is an act on the ledger. The arguable one -- the detail does name a flag
    # -- and it is a work state because naming the flag is not the same as
    # being able to fill it.
    "GATE_AUTHORIZATION_REQUIRED": WORK_STATE,
    "SEQUENCE_NOT_REACHED": WORK_STATE,
    "NOT_READY": WORK_STATE,
    # A rung is declared in the target's own `__levels__`, not in any
    # argument `gate` accepts -- no flag names one; clearing this means the
    # evidence actually reaching the rung the ladder requires.
    "RUNG_NOT_ATTAINED": WORK_STATE,
    "POSITION_ABSENT": WORK_STATE,
    "POSITION_STALE": WORK_STATE,
    "POSITION_UNBACKED": WORK_STATE,
    "POSITION_SHARDS_UNDECLARED": WORK_STATE,
    "POSITION_DISAGREES": WORK_STATE,
    # --- close -------------------------------------------------------------
    "AGREEMENT_DISAGREES": WORK_STATE,
    "DISCUSSION_UNANSWERED": WORK_STATE,
    # --- step --------------------------------------------------------------
    "STEPS_UNDECLARED": WORK_STATE,          # the target declares them
    "STEP_UNKNOWN": INVOCATION_DEFECT,       # the detail lists the real ones
    "STEP_MALFORMED": WORK_STATE,            # the declaration is wrong
    "INTERPRETER_ABSENT": WORK_STATE,        # run `env`
    "STEP_SEQUENCE_NOT_REACHED": WORK_STATE,
    # --- offer -------------------------------------------------------------
    "OFFER_UNANSWERED": INVOCATION_DEFECT,
    "OFFER_ANSWER_NOT_A_TOKEN": INVOCATION_DEFECT,
    # --- settle ------------------------------------------------------------
    "SETTLE_STDIN_CONFLICT": INVOCATION_DEFECT,
    "SETTLE_EMPTY_TEXT": INVOCATION_DEFECT,
    "SETTLE_ATTACH_CONFLICT": INVOCATION_DEFECT,
    "SETTLE_REMOVE_CONFLICT": INVOCATION_DEFECT,
    "SETTLE_REVERSE_CONFLICT": INVOCATION_DEFECT,
    "SETTLE_DONE_CONFLICT": INVOCATION_DEFECT,
    "SETTLE_WITNESS_REQUIRED": INVOCATION_DEFECT,
    "SETTLE_PARAGRAPH_REQUIRED": INVOCATION_DEFECT,
    "SETTLE_UNDER_REQUIRED": INVOCATION_DEFECT,
    "SETTLE_ABOUT_REQUIRED": INVOCATION_DEFECT,
    "SETTLE_WITNESS_MALFORMED": INVOCATION_DEFECT,
    "SETTLE_SUPERSEDES_UNKNOWN": INVOCATION_DEFECT,
    "SETTLE_TEXT_ABSENT": INVOCATION_DEFECT,
    "SETTLE_ALREADY_WITNESSED": INVOCATION_DEFECT,
    "SETTLE_ALREADY_DONE": INVOCATION_DEFECT,
    "SETTLE_ALREADY_REVERSED": INVOCATION_DEFECT,
    "SETTLE_NOT_DISCUSSED": WORK_STATE,
    "SETTLE_DISCUSSION_UNANSWERED": WORK_STATE,
    "SETTLE_HOLDER_ABSENT": WORK_STATE,
    "SETTLE_TEXT_AMBIGUOUS": WORK_STATE,
    "SETTLE_NOT_REVERSED": WORK_STATE,
    "SETTLE_HEADING_ABSENT": WORK_STATE,
    "SETTLE_HEADING_AMBIGUOUS": WORK_STATE,
    "SETTLE_COLLIDES_UNNAMED": WORK_STATE,
    "SETTLE_NOT_WITNESSED": WORK_STATE,
    # --- materialize -------------------------------------------------------
    "MATERIALIZE_MODE_REQUIRED": INVOCATION_DEFECT,
    "MATERIALIZE_MODE_CONFLICT": INVOCATION_DEFECT,
    "PLAN_REQUIRED": INVOCATION_DEFECT,
    "SEED_REQUIRED": INVOCATION_DEFECT,
    # --- position ----------------------------------------------------------
    "POSITION_SEQUENCE_AND_RECONCILE": INVOCATION_DEFECT,  # drop one of the two
    "POSITION_SEQUENCE_UNREADABLE": INVOCATION_DEFECT,     # fix the JSON typed
    "POSITION_SEQUENCE_EMPTY": INVOCATION_DEFECT,          # pass a real sequence
    "POSITION_BLOCK_EXISTS": INVOCATION_DEFECT,            # pass --replace
    # The second arguable one, and it lands the other side of the line from
    # `GATE_AUTHORIZATION_REQUIRED`: the rung names are the target's own, so a
    # caller may have to go read `__levels__` before typing one -- but reading
    # is not acting, nothing in the repository has to change, and the same call
    # with the flag added goes through. `POSITION_ABSENT`'s own resolution
    # already publishes that reading as a question, at the command that can
    # answer it.
    "POSITION_TARGET_LEVEL_REQUIRED": INVOCATION_DEFECT,
    "POSITION_TARGET_LEVEL_UNKNOWN": INVOCATION_DEFECT,    # the detail lists them
    # A ladder is declared in the target's own benchmark package, so no
    # argument this command accepts can supply one.
    "POSITION_LEVELS_UNDECLARED": WORK_STATE,
    # Two files carry the block; which one holds the section is a decision
    # about the documents, and no flag names a holder.
    "POSITION_HOLDER_AMBIGUOUS": WORK_STATE,
    # Nothing about the invocation clears a skipped rung: the work the rung
    # below asks for has to actually happen, and until it does every spelling
    # of the call is refused. So the exit published is the rung this target CAN
    # seal next, read from its own ladder.
    "POSITION_RUNG_SKIPPED": WORK_STATE,
    # An `@step` operand names a position ITEM's declared step, and that
    # declaration lives in AGREED.md, not in any argument `position` accepts
    # -- no flag names a step; clearing this means editing the document or
    # declaring the step in `__steps__` (design "The new refusal is a work
    # state, raised in `cmd_position`", a measured correction to the
    # proposal's `INVOCATION_DEFECT`).
    "POSITION_STEP_UNKNOWN": WORK_STATE,
    # A named entry lives in the target's own `__records__`, not in any
    # argument `position` accepts -- no flag names a record; clearing this
    # means declaring the entry, the identical reasoning
    # `POSITION_STEP_UNKNOWN` states just above.
    "POSITION_RECORD_UNKNOWN": WORK_STATE,
    # The shape half of the same declaration. A work state for the identical
    # reason: nothing in the invocation can fix an entry the target wrote.
    "POSITION_RECORD_MALFORMED": WORK_STATE,
}


def _refusal_target_args(args) -> list[str]:
    """`--target <t> --name <n>`, read off the call being refused."""
    return ["--target", str(getattr(args, "target", "")),
            "--name", str(getattr(args, "name", ""))]


def _refusal_position_command(args, *extra: str) -> str:
    """The `position` invocation that re-derives the block this refusal read.

    `--session` is not decoration: `position` requires it, so a published
    command that dropped it would refuse on its own advice. Every gating
    command that can raise a position code carries `--session` itself, and the
    caller's own is reused rather than invented.
    """
    parts = ["position", *_refusal_target_args(args),
             "--session", str(getattr(args, "session", "") or "")]
    if getattr(args, "revision", None):
        parts += ["--revision", str(args.revision)]
    return _cli_command(*parts, *extra)


def _refusal_question(args, question: str) -> dict:
    """A published question, and the `discuss` command that opens it.

    `--about` is the caller's own when the refused command carries one
    (`settle` does), and the bare `record` bucket otherwise -- the same
    identity every other publication point in this file uses.
    """
    about = getattr(args, "about", None)
    return {
        "kind": "question",
        "question": question,
        "command": _discuss_command(
            Path(str(getattr(args, "target", ""))),
            str(getattr(args, "name", "")),
            about=str(about) if about else "record", question=question),
    }


def _refusal_command(command: str) -> dict:
    return {"kind": "command", "command": command}


def _resolve_position_disagrees(args) -> dict:
    """The code from the incident, and the only resolution named rather than
    derived: a tick whose own witness disagrees is a measurement that has to be
    taken again, so the verification notebook is re-executed and `position`
    re-read.

    `PATH` is the whole point of the first half and dropping it is the obvious
    mistake -- a notebook names a kernelspec, not an interpreter, and the
    ordinary `python3` kernelspec's `argv` begins with a bare `python` resolved
    off `PATH` when the kernel starts. Every part is built from what the engine
    already holds: the target path it was given, `target_interpreter`, and
    `PROBE_NOTEBOOK`. No target-specific string can enter this file through it.
    """
    target = Path(str(getattr(args, "target", "")))
    interpreter = target_interpreter(target)
    execution = " ".join(shlex.quote(part) for part in (
        f"PATH={interpreter.parent}:$PATH", str(interpreter), "-m", "jupyter",
        "nbconvert", "--to", "notebook", "--execute", "--inplace",
        str(target / str(getattr(args, "name", "")) / "Notebooks" / PROBE_NOTEBOOK)))
    return _refusal_command(
        f"{execution} && {_refusal_position_command(args)}")


def _position_attained_level(target: Path, name: str) -> str | None:
    """The rung the evidence reaches, rebuilt at the moment of refusal from
    `target`/`name` alone: the `except Refused` chokepoint is handed nothing
    but `args`, so the fact is re-read here rather than threaded out of the
    command that already had it. Nothing raises on the way out -- a resolution
    that failed while being built would cost the reader both it and the
    refusal it explains.

    This replaced a reader of the block's own recorded rung, which had no
    caller left once the resolution stopped publishing `recorded + 1`: reading
    the header, this builder answered a refusal about an over-reaching aim by
    naming a rung one higher still.

    `shards_root` is deliberately not threaded through from `args`. The refusal
    being answered was raised against evidence `cmd_position` built with
    whatever `--shards` it was given, and this rebuild sees only the target's
    own declared `distribution.shardsRoot` -- so an explicit `--shards` that
    named a directory the declaration does not can make this read LOWER than
    the one that refused. Lower is the safe direction: it publishes a rung at
    or below the one that would go through, never above it, and the published
    command is run by the operator, who can name their own directory again.
    """
    product = target / name
    if not product.is_dir():
        return None
    try:
        # Found by shape, exactly as `position_state` finds it and for the
        # same reason: no fixed filename decides which markdown file holds the
        # block, here or anywhere else in this file. First block wins, and
        # ambiguity is not re-refused -- this builder answers a refusal that
        # already happened, and `POSITION_HOLDER_AMBIGUOUS` is the code for
        # that fact when it is the one being reported.
        for path in sorted(product.glob("*.md")):
            if not path.is_file():
                continue
            block = impl_position.locate_block(path.read_bytes(),
                                               allow_legacy=True)
            if block is None:
                continue
            return impl_position.attained_level(
                impl_position.parse_items(block["body"]),
                _position_write_evidence(target, name))
    except Exception:
        # Deliberately every one of them: a block that will not parse, a
        # benchmark package that will not import, a declaration that refuses.
        # Each is a fact the refusal being built already carries or the next
        # command will raise on its own; none is worth costing the reader the
        # refusal itself, and the caller below simply names no rung when this
        # answers nothing.
        return None
    return None


def _resolve_position_rung_skipped(args) -> dict:
    """The rung this target can seal next, and the question of what has to run
    before the one above it can be claimed.

    A question rather than a command, for the reason `POSITION_ABSENT`'s own
    resolution states: the command that would clear this is the one that
    refused, and publishing the caller's own call back to them is advice that
    refuses on its own advice. What can be named concretely is the next rung --
    one above what the evidence currently ATTAINS, or the floor when it attains
    nothing -- so that is what the question carries, together with the seal
    command for it.

    Read from attainment and never from the header, the same separation the
    refusal itself is built on. Reading the block's recorded rung, this would
    publish the rung above whatever was last AIMED at -- and on exactly the
    repository this refusal fires for, that rung is refused for the identical
    reason the call being answered was. A resolution that refuses on its own
    advice is the one thing this builder exists not to be.

    Every rung name here is read off the target's own `__levels__` at the
    moment of refusal. The forge holds no rung vocabulary of its own (see
    `resolve_levels_declaration`), so when a ladder cannot be read at all the
    question still asks the same thing and simply names no rung, rather than
    inventing one on the repository's behalf.
    """
    target = Path(str(getattr(args, "target", "")))
    name = str(getattr(args, "name", ""))
    levels = resolve_levels_declaration(target, name)
    attained = impl_position.level_index(
        levels, _position_attained_level(target, name))
    following = None
    if levels:
        following = levels[0] if attained is None else levels[
            min(attained + 1, len(levels) - 1)]
    named = (
        f" The next rung this target can seal is {following!r}: run `"
        + _refusal_position_command(args, "--target-level", following) + "`."
        if following else "")
    return _refusal_question(
        args,
        "this pass aims at a rung whose predecessor on the target's own "
        "ladder is not attained by anything measurable now, and a position "
        "never skips a rung going forward; what has to run before the rung "
        "above it can be claimed, and why?" + named)


def _resolve_position_step_unknown(args) -> dict:
    """The steps this target's own `__steps__` actually declares, or the
    fact that it declares none at all, read fresh at the moment of
    refusal (`_resolve_position_rung_skipped`'s own pattern: re-derive from
    `target`/`name` rather than thread the specific unknown operand through
    `args`, which carries none).

    A question, never a command: no flag this command accepts can name a
    step, and clearing this means either editing AGREED.md's `@step`
    operand or adding an entry to `__steps__` -- both decisions only a
    human can make.
    """
    target = Path(str(getattr(args, "target", "")))
    name = str(getattr(args, "name", ""))
    steps = resolve_steps_declaration(target, name)
    named = (f" This target currently declares: {sorted(steps)!r}."
             if steps else " This target currently declares no __steps__ at all.")
    return _refusal_question(
        args,
        "an `@step` witness in this position sequence names a step this "
        "target's __steps__ does not declare; which callable should it "
        "name, and does __steps__ need a new entry first?" + named)


def _resolve_rung_not_attained(args) -> dict:
    """The rung this launch requires, read fresh at the moment of refusal
    from the target's own `__levels__` -- `_resolve_position_rung_skipped`'s
    own pattern (attainment, never a header, and never invented), applied to
    the gate-time floor (`levels[-2]`) instead of `position`'s own
    predecessor rung.

    A question, never a command: the command that would clear this is the
    one that just refused, and republishing the caller's own call back to
    them is advice that refuses on its own advice.
    """
    target = Path(str(getattr(args, "target", "")))
    name = str(getattr(args, "name", ""))
    levels = resolve_levels_declaration(target, name)
    attained = _position_attained_level(target, name)
    floor = levels[len(levels) - 2] if len(levels) >= 2 else None
    named = f" This launch requires {floor!r}." if floor is not None else ""
    return _refusal_question(
        args,
        "this job's witness sits on a declared rung ladder, and the "
        "evidence does not yet attain the rung a launch requires (the "
        "refusal detail names it); the evidence currently attains "
        + (f"{attained!r}" if attained is not None else "no rung at all")
        + ". What has to run before that rung is reached, and why?" + named)


def _resolve_position_record_unknown(args) -> dict:
    """The records this target's own `__records__` actually declares, or the
    fact that it declares none at all, read fresh at the moment of refusal
    (`_resolve_position_step_unknown`'s own pattern: re-derive from
    `target`/`name` rather than thread the specific unknown operand through
    `args`, which carries none).

    A question, never a command: no flag this command accepts can name a
    record, and clearing this means either editing AGREED.md's
    `@record:level` operand or adding an entry to `__records__` -- both
    decisions only a human can make.
    """
    target = Path(str(getattr(args, "target", "")))
    name = str(getattr(args, "name", ""))
    records = resolve_records_declaration(target, name)
    named = (f" This target currently declares: {sorted(records)!r}."
             if records else " This target currently declares no __records__ at all.")
    return _refusal_question(
        args,
        "a leveled `@record:level` witness in this position sequence names "
        "a record this target's __records__ does not declare; which named "
        "record should it address, and does __records__ need a new entry "
        "first?" + named)


#: One builder per work state. Every one of them is reached only by its own
#: code, and every one publishes something a reader runs unedited -- a code
#: with nothing real to publish is a misclassification, not an empty field, and
#: `GatingRefusalRosterTests` asserts the content rather than the key.
_WORK_STATE_RESOLUTIONS = {
    "PLAN_STALE": lambda args: _refusal_command(
        _cli_command("plan", *_refusal_target_args(args))),
    "APPLY_ABORTED": lambda args: _refusal_command(
        _cli_command("plan", *_refusal_target_args(args))),
    "DESTINATION_CONFLICT": lambda args: _refusal_question(
        args, "the reorganization has destinations that clash -- an existing "
              "file, or two sources onto one path (the refusal detail names "
              "them); where does each one belong, and why?"),
    "UNCLASSIFIED_FILES": lambda args: _refusal_question(
        args, "the reorganization covers files no rule classifies (the "
              "refusal detail names them); where does each one belong, and "
              "why?"),
    "NO_FINDINGS": lambda args: _refusal_question(
        args, "tests/findings.py declares no finding to rule on; write the "
              "findings now, or record why admissibility is deferred, and "
              "why?"),
    "GATE_AUTHORIZATION_REQUIRED": lambda args: _refusal_question(
        args, "this launch carries no authorization, and one is minted only "
              "by a prior `offer` publish over exactly this binding; does "
              "every declared pilot run before this campaign is gated? Answer "
              "here, then run `offer --answer <yes|no>` and pass the token "
              "its launch action names."),
    "SEQUENCE_NOT_REACHED": lambda args: _refusal_question(
        args, "this launch is not the next rung of the position sequence (the "
              "refusal detail names which item is open); do that rung's work "
              "now, or re-derive the sequence, and why?"),
    "STEP_SEQUENCE_NOT_REACHED": lambda args: _refusal_question(
        args, "this step is not the next rung of the position sequence (the "
              "refusal detail names which item is open); do that rung's work "
              "now, or re-derive the sequence, and why?"),
    "NOT_READY": lambda args: _refusal_question(
        args, "this job has no passing rehearsal recorded at the commit it is "
              "pinned to, and readiness is measured rather than asserted; "
              "rehearse it through the remote-execution skill now, or record "
              "why the launch is deferred, and why?"),
    "RUNG_NOT_ATTAINED": _resolve_rung_not_attained,
    # A question rather than a command, and measured rather than assumed: the
    # published `position --reconcile` was RUN, and it refused
    # `POSITION_TARGET_LEVEL_REQUIRED` -- a fresh header cannot be written
    # without stating which rung the pass is aiming at, and only the target's
    # own `__levels__` name the rungs. So the open decision is published, with
    # the command that takes it, rather than a command that would refuse on its
    # own advice. The refresh codes below keep a plain command because they
    # inherit the existing block's own target level.
    "POSITION_ABSENT": lambda args: _refusal_question(
        args, "no position section has been derived for this target, and a "
              "fresh one cannot be written without naming the rung this pass "
              "aims at; which of the target's own declared `__levels__` is "
              "it? Then run `"
              + _refusal_position_command(args, "--reconcile", "--target-level")
              + " <rung>`."),
    "POSITION_STALE": lambda args: _refusal_command(
        _refusal_position_command(args)),
    "POSITION_UNBACKED": lambda args: _refusal_command(
        _refusal_position_command(args)),
    "POSITION_SHARDS_UNDECLARED": lambda args: _refusal_question(
        args, "a ticked item's witness is a shard and nothing names where a "
              "returned shard lands; declare `distribution.shardsRoot` in the "
              "benchmark package now, or name the directory to measure "
              "against, and why?"),
    "POSITION_DISAGREES": _resolve_position_disagrees,
    "POSITION_RUNG_SKIPPED": _resolve_position_rung_skipped,
    "POSITION_STEP_UNKNOWN": _resolve_position_step_unknown,
    "POSITION_RECORD_UNKNOWN": _resolve_position_record_unknown,
    "POSITION_RECORD_MALFORMED": lambda args: _refusal_question(
        args, "a leveled `@record:level <name>` witness addresses a "
              "__records__ entry the reader cannot use -- not a mapping, or "
              "a mapping with no `path` string (the refusal detail names "
              "which); write the entry as `{\"path\": ..., "
              "\"requiredScale\": {...}}` now, or say why that record is "
              "not addressable yet, and why?"),
    "POSITION_LEVELS_UNDECLARED": lambda args: _refusal_question(
        args, "an item in this sequence is marked as reaching a rung and the "
              "target's benchmark package declares no `__levels__` ladder for "
              "it to reach; which rungs does this target climb, in order, and "
              "why?"),
    "POSITION_HOLDER_AMBIGUOUS": lambda args: _refusal_question(
        args, "more than one markdown file under this product carries a "
              "`<!-- position -->` block, and no argument this command takes "
              "can tell them apart; which file holds the section, and should "
              "the other block be removed, and why?"),
    "AGREEMENT_DISAGREES": lambda args: _refusal_question(
        args, "a ticked agreement names a witness function that is absent "
              "from a fully-parsed tests/ (the refusal detail names it); "
              "restore the witness now, or reverse the agreement, and why?"),
    "DISCUSSION_UNANSWERED": lambda args: _refusal_question(
        args, "discussion(s) were opened here and never answered, and the "
              "refusal detail carries the exact retirement command for each; "
              "answer them now, or record why they stay open, and why?"),
    "STEPS_UNDECLARED": lambda args: _refusal_question(
        args, "this target declares no __steps__ at all, so nothing here "
              "names a callable to run; declare them now, or record why the "
              "work runs outside this command, and why?"),
    "STEP_MALFORMED": lambda args: _refusal_question(
        args, "the declared step does not carry what a step declaration needs "
              "(the refusal detail names what is missing or wrong); correct "
              "the declaration now, or record why the step is deferred, and "
              "why?"),
    "INTERPRETER_ABSENT": lambda args: _refusal_command(
        _cli_command("env", "--target", str(getattr(args, "target", "")))),
    "SETTLE_NOT_DISCUSSED": lambda args: _refusal_question(
        args, "this placement was never discussed, and a placement is "
              "discussed before it is placed; what is being agreed here, and "
              "why?"),
    "SETTLE_DISCUSSION_UNANSWERED": lambda args: _refusal_question(
        args, "this placement's discussion was asked and never answered, and "
              "an open question is not yet a settled agreement; what is the "
              "answer, and why?"),
    "SETTLE_HOLDER_ABSENT": lambda args: _refusal_question(
        args, "no markdown file under this product holds checklist items, and "
              "settle never invents a file to write into; which file holds "
              "the agreements, and why?"),
    "SETTLE_TEXT_AMBIGUOUS": lambda args: _refusal_question(
        args, "this text matches more than one existing checklist line, and "
              "no argument this command takes can tell them apart; which line "
              "is meant, or should the duplicates be reconciled first, and "
              "why?"),
    "SETTLE_NOT_REVERSED": lambda args: _refusal_question(
        args, "this agreement is not explained under a '## Reversed' heading, "
              "and the engine never authors that reasoning; why is it being "
              "turned over? Write that explanation with `settle --reverse "
              "--paragraph <reasoning>`."),
    "SETTLE_HEADING_ABSENT": lambda args: _refusal_question(
        args, "the heading this write goes under occurs in none of the "
              "product's holders, and settle never invents one; which "
              "existing heading holds it, or should the holder gain that "
              "heading first, and why?"),
    "SETTLE_HEADING_AMBIGUOUS": lambda args: _refusal_question(
        args, "the heading this write goes under occurs more than once, and "
              "no argument this command takes can tell the occurrences apart; "
              "which one receives it, or should the duplicates be reconciled "
              "first, and why?"),
    "SETTLE_COLLIDES_UNNAMED": lambda args: _refusal_question(
        args, "this placement's operand already appears in existing "
              "agreement(s) (the refusal detail names them); which one, if "
              "any, does it supersede, and why?"),
    "SETTLE_NOT_WITNESSED": lambda args: _refusal_question(
        args, "this agreement names nothing a test could contradict, and a "
              "line is not marked done until it does; which `test_<id>` "
              "witnesses it? Bind it with `settle --attach --witness "
              "test_<id>` before marking it done."),
}


def refusal_resolution(code: str, args) -> dict | None:
    """What clears `code`, or `None` when nothing has to be published.

    Read at the one `except Refused` every refusal in this engine passes
    through, so a code is answered once rather than at each of the hundred and
    sixty-five sites that raise one. `None` on three separate grounds, all of
    them deliberate: the code is an invocation defect (its detail already names
    the flag), the code belongs to a command outside `GATING_COMMANDS` (this
    roster is the gating commands' own and never hands a resolution to a
    refusal it was not classified for), or `args` is not a shape this can read.

    Never raises. A crash inside a refusal handler would turn a clean exit 2
    into a traceback, and the reader would lose both the refusal and the
    resolution -- so the whole build is guarded, and a resolution that could
    not be built is simply not published.
    """
    if GATING_REFUSALS.get(code) != WORK_STATE:
        return None
    builder = _WORK_STATE_RESOLUTIONS.get(code)
    if builder is None:                     # unreachable while the roster test
        return None                         # holds; not a licence to omit one
    try:
        return builder(args)
    except Exception:                       # noqa: BLE001 -- see the docstring
        return None


COMMANDS = {"env": cmd_env, "name": cmd_name, "plan": cmd_plan, "apply": cmd_apply,
            "admit": cmd_admit, "handoff": cmd_handoff, "compose": cmd_compose,
            "probe": cmd_probe,
            "verify": cmd_verify,
            "position": cmd_position,
            "discuss": cmd_discuss,
            "propose": cmd_propose,
            "gate": cmd_gate,
            "offer": cmd_offer,
            "close": cmd_close,
            "step": cmd_step,
            "settle": cmd_settle,
            "defect": cmd_defect,
            "materialize": cmd_materialize}


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
                                "Refused below 3.10, or the target's own declared "
                                "python_requires floor, whichever is higher.")
        elif name == "compose":
            # Composition reads the findings and the entry, nothing layout-shaped.
            p.add_argument("--finding", required=True, help="id of the finding to compose")
            p.add_argument("--entry-text", required=True,
                           help="the resolved entry's current text, or - to read stdin")
        else:
            p.add_argument("--name", required=True, help="package name chosen by the user")
        if name == "apply":
            p.add_argument("--plan", required=True, help="path to the approved plan JSON")
        if name in {"verify", "position"}:
            # `admit`, `handoff`, `discuss`, `gate`, `close` and `probe`
            # carry no `--shards` flag of their own, and giving them one
            # they ignore would be a promise this file does not keep. That
            # no longer means they read no shard directory at all, though:
            # once a target declares `distribution.shardsRoot`
            # (`DISTRIBUTION_OPTIONAL`), `_position_write_evidence` and
            # `_resolve_shard_evidence` resolve it for every one of them, so
            # `@shard` reads a real answer everywhere the declaration is
            # read, not only at the one command that happens to carry this
            # flag. Undeclared, `@shard` still reads `unmeasured` for them,
            # exactly as before this fallback existed. `position` DOES
            # thread `--shards` into every write mode, not only `--reconcile`
            # — a bare refresh or `--sequence` install with `--shards` also
            # measures any `@shard` witness already in the block, the same
            # evidence `--reconcile` uses to both discover and measure; an
            # explicit `--shards` here always overrides the declaration.
            # `verify`'s own `--shards` stays explicit-only, deliberately: it
            # is a report over whichever directory an operator names, not a
            # gate the declaration should widen on its own.
            p.add_argument("--shards", default=None,
                           help="a directory of returned shards; each "
                                "subdirectory holds a shard.json stamp. For "
                                "verify, reports which declared-identical "
                                "fields the shards disagree on, and which "
                                "shards arrived. For position, measures every "
                                "@shard witness against the same directory "
                                "(refresh, --sequence install and --reconcile "
                                "alike); --reconcile additionally discovers "
                                "one @shard witness per arrived shard")
        if name in {"verify", "admit", "handoff", "probe", "position", "gate",
                   "offer", "close"}:
            p.add_argument("--revision", default=None,
                           help="pin the revision to check against; "
                                "omit it and verify discovers the newest of "
                                "the family the bench declares. admit, "
                                "handoff, position, gate, offer and close "
                                "discover nothing and refuse "
                                "REVISION_UNREADABLE if it is missing or "
                                "unreadable")
        if name in {"position", "propose", "gate", "offer", "close", "step",
                   "settle", "defect"}:
            p.add_argument("--session", required=True,
                           help="identity stamped into the ledger event(s) "
                                "this call appends, and into the block's "
                                "header for position")
        if name == "position":
            p.add_argument("--sequence", default=None,
                           help="install a fresh section: an ordered JSON "
                                "array of {text, witness:{kind,operand,"
                                "twostate}}, or - to read stdin. witness."
                                "twostate defaults to true (two-state) when "
                                "omitted -- pass false to opt a witness into "
                                "the declared level ladder. Omitted, "
                                "position refreshes the marks of whatever "
                                "block is already there")
            p.add_argument("--replace", action="store_true",
                           help="with --sequence, overwrite an existing "
                                "position block instead of refusing "
                                "POSITION_BLOCK_EXISTS")
            p.add_argument("--reconcile", action="store_true",
                           help="reconstruct the sequence from what the "
                                "target already has: the declared record, "
                                "discovered job folders, Notebooks/*.ipynb "
                                "and, with --shards, arrived shards. "
                                "Existing items are matched by witness "
                                "identity and kept untouched; only unmatched "
                                "steps are appended")
            p.add_argument("--target-level", default=None,
                           help="the rung this pass is aiming at, one of "
                                "this target's own __levels__ (see the "
                                "benchmark package's __init__.py/config.py). "
                                "Required only for a fresh header with no "
                                "existing block to inherit one from; a "
                                "refresh reuses the existing block's own "
                                "target when this is omitted. A mark then "
                                "means \"reached the level this pass asks "
                                "for\" for a leveled (`:level`-marked) "
                                "witness; a two-state witness ignores it "
                                "entirely and is satisfied or not on its "
                                "own")
        if name == "discuss":
            p.add_argument("--about", required=True,
                           help="an ordinal in the position sequence, or a "
                                "bare witness spec ('kind' or 'kind operand')")
            p.add_argument("--question", required=True,
                           help="the question text, or - to read stdin")
            p.add_argument("--answer", default=None,
                           help="the answer text, or - to read stdin; omit "
                                "to leave the discussion open")
        if name == "propose":
            p.add_argument("--job", dest="jobs", action="append", required=True,
                           help="repeatable, at least one: a job this "
                                "campaign proposal covers. Checked at "
                                "`gate` time for job membership -- distinct "
                                "from `campaign.jobSet`, the full live-disk "
                                "job-folder inventory `_campaign_identity()` "
                                "snapshots for staleness detection, never "
                                "argv-declared")
            p.add_argument("--worker", dest="workers", action="append", required=True,
                           help="repeatable, at least one: an intended "
                                "worker account for this campaign. Recorded "
                                "write-only history, like `offer`'s own "
                                "`answer`; read by nobody in this change")
            p.add_argument("--depends-on", dest="depends_on", action="append",
                           default=None,
                           help="repeatable, optional: one dependency edge "
                                "as 'job:dependency' (job depends on "
                                "dependency). Omit for a campaign with no "
                                "ordering constraints")
            p.add_argument("--rationale", required=True,
                           help="the campaign rationale text, or - to read "
                                "stdin; refused EMPTY_RATIONALE if it is "
                                "blank -- the same discipline `gate`'s own "
                                "--justification already keeps")
        if name == "gate":
            p.add_argument("--job", required=True,
                           help="the job name a `@rehearsal` witness names")
            p.add_argument("--worker", default=None,
                           help="the account this launch is being authorized "
                                "for; required unless --unit authorizes a "
                                "campaign instead, and refused together with "
                                "--unit -- a campaign has no single named "
                                "account")
            p.add_argument("--unit", dest="units", action="append", default=None,
                           help="repeatable: authorize a CAMPAIGN launch "
                                "instead of a single-send one, binding the "
                                "exact ordered unit list a later `submit "
                                "--unit ...` will carry -- the same "
                                "derivation remote_cli's own consent token "
                                "uses. Mutually exclusive with --worker")
            p.add_argument("--justification", required=True,
                           help="the launch justification text, or - to read "
                                "stdin; refused if it is blank")
            p.add_argument("--authorization", default=None,
                           help="a token minted by a prior `offer` publish "
                                "over this exact launch's binding (job, "
                                "pin, entrypoint, units, rung, revision, "
                                "position status) -- required, no default. "
                                "Refused GATE_AUTHORIZATION_REQUIRED when "
                                "omitted, _UNKNOWN when no ledger record "
                                "vouches for it, _MISMATCH when it was "
                                "minted for a different job or unit list, "
                                "_STALE when a bound fact has since moved "
                                "(never merely elapsed time), _CONSUMED "
                                "when it already authorized one successful "
                                "gate call")
            p.add_argument("--elect", dest="elected", action="append", default=None,
                           help="repeatable: elects --job for launch "
                                "despite its own facts not deciding "
                                "necessity. Required (and must name "
                                "exactly --job) when --job classifies "
                                "`optional`; refused "
                                "GATE_ELECTION_REQUIRED when omitted, "
                                "GATE_ELECTION_MISMATCH when --elect names "
                                "a different job, or names --job while it "
                                "does not classify `optional`. Never "
                                "stored and reused -- argv, every call")
        if name == "offer":
            p.add_argument("--answer", default=None,
                           help="yes or no, answering whether every declared "
                                "pilot runs before a campaign is gated; "
                                "checked as a coded refusal, never argparse "
                                "choices, so a bad token prints the same "
                                "JSON refusal shape every other refusal "
                                "here does. Required on EVERY call -- never "
                                "read back from a prior offer event, "
                                "refused OFFER_UNANSWERED when omitted, "
                                "regardless of what any earlier call "
                                "recorded")
            p.add_argument("--unit", dest="units", action="append", default=None,
                           help="repeatable: the ordered unit list a `launch` "
                                "action is about to authorize a CAMPAIGN for "
                                "instead of a single-send one -- the SAME "
                                "list a later `gate --unit ...` and `submit "
                                "--unit ...` will carry. Every published "
                                "`launch` action's binding is minted against "
                                "exactly this operator-declared list; the "
                                "engine never substitutes one of its own. "
                                "Omit it for a single-send launch")
        if name == "step":
            p.add_argument("--step", required=True,
                           help="the declared __steps__ entry to run; no "
                                "flag runs more than one")
        if name == "settle":
            # No --revision: settle binds to no revision, and a flag it
            # ignores would be a promise this file does not keep (design
            # "settle takes --session").
            p.add_argument("--about", default=None,
                           help="an ordinal in the position sequence, or a "
                                "bare witness spec ('kind' or 'kind "
                                "operand') -- the identical shape discuss's "
                                "own --about takes, matched against an "
                                "answered discuss event by witness identity "
                                "(kind, operand). Required unless --attach "
                                "or --remove is given (refused "
                                "SETTLE_ABOUT_REQUIRED); neither mode ever "
                                "resolves or requires it -- there is no "
                                "discussion gate left to check it against")
            p.add_argument("--text", required=True,
                           help="without --attach/--remove: the "
                                "caller-authored agreement text, or - to "
                                "read stdin; written verbatim as one "
                                "unticked `- [ ]` line -- never authored or "
                                "ticked by this command. With --attach: the "
                                "EXACT existing text of an already-settled "
                                "line this call attaches --witness to. "
                                "With --remove: the EXACT existing text of "
                                "an already-settled line this call deletes "
                                "outright. Both modes match by exact "
                                "equality against AGREEMENT_LINE's own text "
                                "group -- refused SETTLE_TEXT_ABSENT or "
                                "SETTLE_TEXT_AMBIGUOUS when it matches zero "
                                "or more than one line; --remove additionally "
                                "refuses SETTLE_NOT_REVERSED unless that "
                                "exact text is already quoted, bold, under "
                                "a ## Reversed heading in the same holder "
                                "file")
            p.add_argument("--under", default=None,
                           help="the exact heading line this item is "
                                "placed under, hash marks included (e.g. "
                                "'## Ladder'); refused SETTLE_HEADING_ABSENT "
                                "or SETTLE_HEADING_AMBIGUOUS when it occurs "
                                "zero or more than one time across the "
                                "product's holder file(s). Required unless "
                                "--attach or --remove is given (refused "
                                "SETTLE_UNDER_REQUIRED); refused "
                                "SETTLE_ATTACH_CONFLICT if given together "
                                "with --attach, or SETTLE_REMOVE_CONFLICT "
                                "if given together with --remove -- neither "
                                "mode places anything new and so neither "
                                "names a heading")
            p.add_argument("--supersedes", default=None,
                           help="the exact text of an existing colliding "
                                "agreement this placement supersedes, or - "
                                "to read stdin; required when the new "
                                "item's witness collides with an existing "
                                "one, recorded in the ledger event only -- "
                                "the document itself still needs a "
                                "human-written Reversed paragraph to show "
                                "the supersession. Refused "
                                "SETTLE_ATTACH_CONFLICT if given together "
                                "with --attach, or SETTLE_REMOVE_CONFLICT "
                                "if given together with --remove -- neither "
                                "mode places anything new and so neither "
                                "collides with anything")
            p.add_argument("--witness", default=None,
                           help="test_<id> naming this agreement's own "
                                "function in the declared-invariants suite "
                                "-- a separate identity from --about, which "
                                "names the position witness this placement "
                                "discusses. Persisted verbatim into the "
                                "written line as a trailing "
                                "`` `test_<id>` `` token. Without --attach: "
                                "optional; omitted, the line stays "
                                "byte-identical to the pre-witness grammar. "
                                "With --attach: required (refused "
                                "SETTLE_WITNESS_REQUIRED if omitted -- "
                                "binding a witness is the whole point of "
                                "that mode); refused SETTLE_ALREADY_WITNESSED "
                                "if the located line already carries one -- "
                                "--attach never replaces one. With --remove: "
                                "refused SETTLE_REMOVE_CONFLICT if given at "
                                "all -- the line is deleted outright, so "
                                "there is no witness token left to bind. "
                                "Refused SETTLE_WITNESS_MALFORMED in every "
                                "mode that reaches this check if given and "
                                "not test_[A-Za-z0-9_]+. settle is the only "
                                "command that ever writes this token -- "
                                "there is no patch or edit subcommand, and "
                                "hand-typing one into the file is "
                                "unsupported (evaluated exactly like a "
                                "skill-written one by verify, never "
                                "technically prevented)")
            p.add_argument("--attach", action="store_true",
                           help="bind --witness onto a line ALREADY "
                                "settled, matched by its exact --text, "
                                "instead of placing a new `- [ ]` line "
                                "(design 'attach, not place'). The mark "
                                "is never touched -- a ticked item stays "
                                "ticked, an open one stays open; only the "
                                "witness token is added. Skips the "
                                "discussion precondition entirely (see "
                                "cmd_settle's own docstring for why): a "
                                "line this matches was already placed by a "
                                "prior settle call, so it was already "
                                "discussed once. --under and --supersedes "
                                "do not apply with --attach and are refused "
                                "SETTLE_ATTACH_CONFLICT if given. Refused "
                                "SETTLE_REMOVE_CONFLICT if given together "
                                "with --remove -- the two write modes are "
                                "mutually exclusive; --attach combined with "
                                "--reverse or --done is refused SETTLE_"
                                "REVERSE_CONFLICT / SETTLE_DONE_CONFLICT "
                                "instead, checked on that other flag's own "
                                "side")
            p.add_argument("--remove", action="store_true",
                           help="delete a line ALREADY settled outright, "
                                "matched by its exact --text, instead of "
                                "placing or attaching anything (design "
                                "'the eraser'). Refused SETTLE_NOT_REVERSED "
                                "unless that exact text is already quoted, "
                                "bold, under a ## Reversed heading in the "
                                "same holder file (see cmd_settle's own "
                                "docstring, 'The guard removal must pass', "
                                "for the full argument) -- deleting a "
                                "settled agreement is the one destructive "
                                "write this command can make, and it is "
                                "refused until the document itself already "
                                "explains why. This remains the reachable "
                                "command when that explanation was ALREADY "
                                "written -- by hand, or by a prior "
                                "--reverse call -- and only the deletion is "
                                "still pending; --reverse itself refuses "
                                "SETTLE_ALREADY_REVERSED rather than write a "
                                "second explanation over an existing one. "
                                "Skips the discussion precondition for the "
                                "identical reason --attach does: a line "
                                "this matches was already discussed once, "
                                "when it was first placed. --under, "
                                "--supersedes and --witness do not apply "
                                "with --remove and are refused "
                                "SETTLE_REMOVE_CONFLICT if given, and so "
                                "are --attach and --reverse themselves; "
                                "--done combined with --remove is refused "
                                "SETTLE_DONE_CONFLICT instead, checked on "
                                "--done's own side")
            p.add_argument("--reverse", action="store_true",
                           help="one transaction that WRITES a new ## "
                                "Reversed entry and DELETES the settled "
                                "line matched by its exact --text, instead "
                                "of requiring the two as separate steps "
                                "(design 'a reversal is one write'). The "
                                "bold quote is derived from the located "
                                "line itself, never retyped by the caller; "
                                "--paragraph supplies the caller-authored "
                                "prose that follows it and is required "
                                "(refused SETTLE_PARAGRAPH_REQUIRED if "
                                "omitted or blank -- the engine never "
                                "authors the reasoning). Refused "
                                "SETTLE_TEXT_ABSENT / SETTLE_TEXT_AMBIGUOUS "
                                "the identical way --attach and --remove "
                                "already are; refused SETTLE_HEADING_ABSENT "
                                "/ SETTLE_HEADING_AMBIGUOUS if the holder "
                                "carries zero or more than one '## "
                                "Reversed' heading -- this mode places its "
                                "entry under an EXISTING heading and never "
                                "invents one. Refused SETTLE_ALREADY_"
                                "REVERSED if the exact text is already "
                                "quoted there (use plain --remove instead "
                                "-- the explanation already exists). "
                                "Skips the discussion precondition for the "
                                "identical reason --attach and --remove "
                                "do. --under, --supersedes and --witness do "
                                "not apply and are refused SETTLE_REVERSE_"
                                "CONFLICT if given, and so are --attach and "
                                "--remove themselves; --done combined with "
                                "--reverse is refused SETTLE_DONE_CONFLICT "
                                "instead, checked on --done's own side")
            p.add_argument("--paragraph", default=None,
                           help="the caller-authored prose placed after the "
                                "derived bold quote in a new ## Reversed "
                                "entry; required with --reverse (refused "
                                "SETTLE_PARAGRAPH_REQUIRED if omitted or "
                                "blank), and ignored -- refused SETTLE_"
                                "REVERSE_CONFLICT if given at all -- in "
                                "every other mode, since none of them write "
                                "one")
            p.add_argument("--done", action="store_true",
                           help="flip an already-settled line's own mark "
                                "from `[ ]` to `[x]`, matched by its exact "
                                "--text, instead of placing, attaching or "
                                "removing anything (design 'the tick this "
                                "class closes'). Refused SETTLE_NOT_"
                                "WITNESSED unless the located line already "
                                "carries a `` `test_<id>` `` token -- a "
                                "tick asserts the work is done, and this "
                                "command refuses to author that assertion "
                                "for a line nobody can point a test at; "
                                "bind one first with `settle --attach`. "
                                "Refused SETTLE_ALREADY_DONE if the located "
                                "line's own mark is already `x` or `X`. "
                                "--under, --supersedes, --witness and "
                                "--paragraph do not apply with --done and "
                                "are refused SETTLE_DONE_CONFLICT if given, "
                                "and so are --attach, --remove and "
                                "--reverse themselves")
        if name == "defect":
            p.add_argument("--file", required=True,
                           help="path to the forge file this declares "
                                "broken; must resolve under "
                                ".claude/skills/. Refused "
                                "DEFECT_FILE_NOT_FORGE_OWNED outside that "
                                "tree, DEFECT_FILE_ABSENT if it is not a "
                                "regular file -- containment is checked "
                                "before existence")
            p.add_argument("--detail", default=None,
                           help="free text describing what is broken; "
                                "omitted from the ledger event entirely "
                                "(never written as null) when not given")
        if name == "materialize":
            p.add_argument(
                "--stage", choices=["scaffold", "objects", "harness"], default=None,
                help="write one stage's kit destinations over an approved, "
                     "structurally-compliant target. 'scaffold' and "
                     "'objects' require --plan and --seed; 'objects' also "
                     "refuses OBJECT_MAP_NOT_APPROVED until the step-8 "
                     "declaration is recorded. 'harness' requires --plan "
                     "only -- its templates carry no {{SEED}} token. "
                     "Mutually "
                     "exclusive with --authored/--adopt")
            p.add_argument(
                "--authored", default=None, metavar="PATH",
                help="release the drift seal on one receipt-recorded "
                     "destination after the agent authored over it: no file "
                     "write, no plan gate, a dirty tree is fine. Refuses "
                     "NO_RECEIPT_ENTRY if the engine never wrote that path "
                     "(use --adopt instead). Mutually exclusive with "
                     "--stage/--adopt")
            p.add_argument(
                "--adopt", default=None, metavar="PATH",
                help="record an unrecorded kit destination's current bytes "
                     "into the receipt as adopted. Degrades the guarantee: "
                     "the record names who is responsible for the bytes, "
                     "never that they came from the kit. Refuses "
                     "ALREADY_RECORDED on a path the receipt already carries "
                     "(use --authored instead). Mutually exclusive with "
                     "--stage/--authored")
            p.add_argument(
                "--plan", default=None,
                help="path to the approved plan JSON; required with --stage")
            p.add_argument(
                "--seed", default=None,
                help="the suite's fixed seed, substituted into {{SEED}}; "
                     "required with --stage scaffold")

    args = parser.parse_args(argv)
    try:
        result = COMMANDS[args.command](args)
    except Refused as refused:             # unchanged: exit 2, appends nothing
        # The one place every refusal in this engine reaches a reader, and so
        # the one place the roster is read. `resolve` is present exactly when
        # `GATING_REFUSALS` calls the code a work state -- somebody has to act
        # on the repository, and this says what -- and absent otherwise, so its
        # presence is itself the classification rather than a field to skim.
        payload = {"status": "refused", "code": refused.code,
                   "detail": refused.detail}
        resolution = refusal_resolution(refused.code, args)
        if resolution is not None:
            payload["resolve"] = resolution
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 2
    except Exception:                      # NOT BaseException -- Refused(Exception) is
                                            # caught above, so this ordering is load-
                                            # bearing: KeyboardInterrupt/SystemExit must
                                            # never be read as a forge-side defect
                                            # (design decision 6,
                                            # maintenance-blocks-it-does-not-mix)
        try:
            _record_engine_defect(args, sys.exc_info()[1])
        except Exception:
            pass                            # a failing recorder must stay invisible
        raise                              # the original propagates unchanged
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
