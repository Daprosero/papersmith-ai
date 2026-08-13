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

PRODUCT_DIRS = ("Notebooks", "Data", "Results", "Models")

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

    proposal = wiring_proposal(target, name, baselines) if next_step == "benchmark" else None
    harness = target / name / "Notebooks" / BENCHMARK_MODULE
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
    wanted = [f"src/{package_name(name)}/__init__.py", "tests/test_smoke.py",
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

    tags = set(re.findall(r"\\tag\{(\d+)\}", source))
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
    roots = [target / "src" / package, target / "tests"]
    for root in roots:
        if not root.is_dir():
            continue
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


def notebooks_state(target: Path, name: str, package: str) -> dict:
    """Every notebook of the product, and whether its evidence is still current.

    Reading one file with a reserved name leaves every other notebook unchecked:
    they could be unexecuted, or full of errors, and the validation would still
    report `ok`. And `executed` alone answers the wrong question — it says a cell
    ran once, not that it ran against this code.
    """
    root = target / name / "Notebooks"
    current = source_digest(target, package)
    reports = []
    for notebook in sorted(root.glob("*.ipynb")) if root.is_dir() else []:
        state = notebook_execution(notebook)
        recorded = state.get("recordedDigest")
        if state["status"] == "executed" and recorded and recorded != current:
            state["status"] = "stale-sources"
        state["notebook"] = str(notebook.relative_to(target))
        state["sourcesMatch"] = None if not recorded else recorded == current
        reports.append(state)
    return {
        "sourcesDigest": current,
        "reports": reports,
        # An executed report that never stamped what it ran against cannot be told
        # apart from a relic, so it is named rather than counted as fine.
        "unstamped": [r["notebook"] for r in reports
                      if r["status"] == "executed" and r["sourcesMatch"] is None],
        "status": "ok" if reports and all(
            r["status"] == "executed" for r in reports) else "drift",
    }


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
TAG_RE = re.compile(r"\\tag\{([^}]+)\}")


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

    tags = set(re.findall(r"\\tag\{(\d+)\}", source))
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
        if p.endswith(".py") and not p.startswith(("src/", "tests/"))
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
            "invariants": prov.get("invariants", []),
            "stale": bool(args.revision) and prov.get("revision") != args.revision,
        })

    tests = test_function_names(target / "tests")
    untested = sorted(i for i in declared_invariants if f"test_{i}" not in tests)
    stale = [m["module"] for m in modules if m["stale"]]

    # What actually changed, rather than "the revision string is different".
    # Marking every module stale because one equation moved tells the reader there is
    # work to do and nothing about where, which is the part they have to find anyway.
    target_source = revision_source(args.revision) if args.revision else None
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
    bench_root = target / "src" / bench_package
    declaration = None
    for candidate in ("__init__.py", "config.py"):
        declaration = declaration or read_declaration(bench_root / candidate,
                                                      BENCHMARK_DECLARATION)
    if not bench_root.is_dir():
        benchmark = {"status": "absent", "package": f"src/{bench_package}"}
    elif declaration is None or "__error__" in (declaration or {}):
        benchmark = {"status": "undeclared", "package": f"src/{bench_package}",
                     "detail": (declaration or {}).get(
                         "__error__",
                         f"no {BENCHMARK_DECLARATION} in __init__.py or config.py: "
                         f"nothing says which sections its arms exercise")}
    else:
        built_against = declaration.get("revision")
        moved = changed_sections(revision_source(built_against), target_source)
        arms = declaration.get("arms") or {}
        reached = {arm: sorted(set(spec.get("sections", [])) & set(moved),
                               key=lambda n: (len(n), n))
                   for arm, spec in arms.items()
                   if isinstance(spec, dict) and set(spec.get("sections", [])) & set(moved)}
        benchmark = {
            "status": "stale" if (args.revision and built_against != args.revision)
                      else "ok",
            "package": f"src/{bench_package}",
            "revision": built_against,
            "changedSections": moved,
            "armsReached": reached or None,
        }

    # The audit bridge: a defect in the mathematics is only reported when its
    # evidence AND the validation of its proposed correction both exist.
    findings = read_findings(target)
    without_evidence = sorted(f["id"] for f in findings if f"test_finding_{f['id']}" not in tests)
    without_remedy = sorted(f["id"] for f in findings if not f.get("remedy"))
    unvalidated = sorted(f["id"] for f in findings if f"test_remedy_{f['id']}" not in tests)
    compatibility = remedy_compatibility(findings, args.revision)
    ruling = admissibility_record(target, args.revision)
    uncontrolled = remedies_without_control(target / "tests", package_name(name))
    source = revision_source(args.revision)
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
    notebooks = notebooks_state(target, name, package_name(name))
    trivial = trivial_assertions(target / "tests")

    if not args.revision:
        fidelity_status = "unknown"
    elif stale or missing_provenance or untested:
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
        "fidelity": {
            "status": fidelity_status,
            "latestRevision": args.revision,
            "staleModules": stale,
            "drift": drift_detail,
            "benchmark": benchmark,
            "missingProvenance": missing_provenance,
            "invariantsWithoutTest": untested,
            "modules": modules,
        },
        "lfs": lfs_state(target),
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
            p.add_argument("--revision", default=None, help="latest research-concept-rNN.md")

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
