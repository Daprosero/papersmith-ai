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
    `MIL-CREDA/` pairs with `src/MIL_CREDA/`. The correspondence the layout
    exists to make visible survives; `import MIL-CREDA` would not.
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

    return {
        "command": "plan",
        "target": str(target),
        "name": name,
        # Same definition of compliant as `verify`: layout AND scaffold. A repo
        # missing pyproject.toml is not compliant just because nothing moves.
        "status": ("compliant"
                   if not moves and not renames and not missing and not gaps
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


def read_findings(target: Path) -> list[dict]:
    """The declared audit findings, read statically from tests/findings.py."""
    path = target / "tests" / "findings.py"
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "FINDINGS" for t in node.targets
        ):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return []
    return []


def scaffold_gaps(target: Path, name: str) -> list[str]:
    wanted = [f"src/{package_name(name)}/__init__.py", "tests/test_smoke.py",
              "tests/findings.py", "tests/test_audit.py", "tests/test_remedies.py",
              f"{name}/Notebooks/verification.ipynb"]
    gaps = [w for w in wanted if not (target / w).exists()]
    if pytest_anchor_missing(target):
        gaps.insert(0, "pyproject.toml [tool.pytest.ini_options] pythonpath")
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

    code_cells = [
        (index, cell) for index, cell in enumerate(notebook.get("cells", []))
        if cell.get("cell_type") == "code" and "".join(cell.get("source", [])).strip()
    ]
    unexecuted = [index for index, cell in code_cells if cell.get("execution_count") is None]
    errors = [
        f"cell {index}: {output.get('ename', 'error')}"
        for index, cell in code_cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "error"
    ]

    if not code_cells:
        status = "empty"
    elif errors:
        status = "errored"
    elif unexecuted:
        status = "stale"
    else:
        status = "executed"
    return {"status": status, "codeCells": len(code_cells),
            "unexecuted": unexecuted, "errors": errors}


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
    if any(current[key] != approved.get(key) for key in ("renames", "moves", "createDirs")):
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


def cmd_verify(args: argparse.Namespace) -> dict:
    target = resolve_target(args.target)
    name = validate_name(args.name)

    paths = tracked_files(target)
    with_data = (target / name / "Data").is_dir()
    missing_dirs = [d for d in expected_dirs(name, with_data) if not (target / d).is_dir()]
    stray = [
        p for p in paths
        if p.endswith(".py") and not p.startswith(("src/", "tests/")) and Path(p).name != "setup.py"
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

    # The audit bridge: a defect in the mathematics is only reported when its
    # evidence AND the validation of its proposed correction both exist.
    findings = read_findings(target)
    without_evidence = sorted(f["id"] for f in findings if f"test_finding_{f['id']}" not in tests)
    without_remedy = sorted(f["id"] for f in findings if not f.get("remedy"))
    unvalidated = sorted(f["id"] for f in findings if f"test_remedy_{f['id']}" not in tests)
    audit_status = "none" if not findings else (
        "incomplete" if without_evidence or without_remedy or unvalidated else "ok")

    smoke_present = (target / "tests" / "test_smoke.py").exists()
    notebook = notebook_execution(target / name / "Notebooks" / "verification.ipynb")

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
            "missingProvenance": missing_provenance,
            "invariantsWithoutTest": untested,
            "modules": modules,
        },
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
            "remediesWithoutValidation": unvalidated,
        },
        "validation": {
            "status": "ok" if smoke_present and notebook["status"] == "executed" else "incomplete",
            "smokeTest": smoke_present,
            "invariantTests": sorted(t for t in tests if t.startswith("test_")),
            "notebook": notebook,
        },
    }


COMMANDS = {"env": cmd_env, "plan": cmd_plan, "apply": cmd_apply, "verify": cmd_verify}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="implementation_cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("--target", required=True, help="cloned repository under implementations/")
        if name == "env":
            p.add_argument("--python", default=None,
                           help="interpreter to build the venv from (default: this one). "
                                "The layout templates assume 3.10+")
        else:
            p.add_argument("--name", required=True, help="package name chosen by the user")
        if name == "apply":
            p.add_argument("--plan", required=True, help="path to the approved plan JSON")
        if name == "verify":
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
