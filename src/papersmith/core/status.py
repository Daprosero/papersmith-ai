"""Collect a comprehensive but best-effort workspace status snapshot."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .. import __version__
from ..bridges.node import call_engine, ensure_node_engine
from ..bridges.python import run_script
from ..errors import PapersmithError, UserError
from ..generators import read_workspace_version
from ..kit import resolve_and_validate
from . import config, fs, manifest


def _read_ledger(root: Path) -> list[dict[str, Any]]:
    """Best-effort: a damaged ledger is reported as absent, not as a crash."""
    text = fs.read_text(root / ".papersmith" / "runs_ledger.jsonl")
    if text is None:
        return []
    entries: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            entries.append({"line": number, "status": "invalid"})
            continue
        if isinstance(value, dict):
            entries.append(value)
        else:
            entries.append({"line": number, "status": "invalid"})
    return entries


def _proposal_status(root: Path) -> dict[str, Any]:
    try:
        ensure_node_engine(root)
        response = call_engine(root, [{"operation": "STATUS"}], timeout=30)[0]
        latest = response.get("latest")
        stage = "none"
        if isinstance(latest, str):
            # ``latest`` comes from the engine, so it is data, not a trusted
            # path: gate the probes instead of letting a damaged tree abort.
            if fs.is_regular_file(root / "proposals" / "deliberated" / latest):
                stage = "deliberated"
            elif fs.is_regular_file(root / "proposals" / "accepted" / latest):
                stage = "accepted"
            else:
                stage = "draft"
        return {
            "revision_id": latest,
            "lifecycle_stage": stage,
            "managed_revisions": response.get("managedRevisions", []),
            "multiple_active": response.get("multipleActive", False),
            "non_managed_files": response.get("nonManagedFiles", []),
            "source": "proposal-deliberation",
        }
    except PapersmithError as exc:
        return {
            "revision_id": None,
            "lifecycle_stage": "unavailable",
            "source": "filesystem-fallback",
            "warning": str(exc),
        }


def _implementation_status(root: Path) -> list[dict[str, Any]]:
    directory = root / "implementations"
    if not fs.is_dir(directory):
        return []
    try:
        candidates = sorted(directory.iterdir())
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for path in candidates:
        if path.name.startswith(".") or path.name == ".gitkeep":
            continue
        if not fs.is_dir(path):
            continue
        tests_dir = path / "tests"
        try:
            test_files = len(list(tests_dir.glob("test_*.py"))) if fs.is_dir(tests_dir) else 0
        except OSError:
            test_files = 0
        entries.append({
            "name": path.name,
            "path": path.relative_to(root).as_posix(),
            "has_pyproject": fs.is_regular_file(path / "pyproject.toml"),
            "has_src": fs.is_dir(path / "src"),
            "test_files": test_files,
        })
    return entries


def _account_status(root: Path) -> dict[str, Any]:
    script = root / "skills" / "kaggle-accounts" / "scripts" / "accounts_cli.py"
    if not fs.is_regular_file(script):
        return {"available": False, "count": 0, "warning": "accounts skill is missing"}
    try:
        result = run_script(root, script, ["list", "--json"], timeout=30)
    except PapersmithError as exc:
        return {"available": False, "count": 0, "warning": str(exc)}
    if result.returncode:
        return {"available": False, "count": 0, "warning": (result.stderr or result.stdout).strip()}
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"available": False, "count": 0, "warning": "accounts CLI returned invalid JSON"}
    if isinstance(payload, list):
        return {"available": True, "count": len(payload)}
    if isinstance(payload, dict):
        accounts = payload.get("accounts")
        if isinstance(accounts, list):
            return {"available": True, "count": len(accounts), "healthy": payload.get("healthy")}
        return {"available": True, "count": 0, "keys": sorted(payload)}
    return {"available": True, "count": 0}


def _inbox_status(root: Path) -> dict[str, Any]:
    """Best-effort: an unreadable inbox is reported as empty, not as a crash."""
    inbox = root / "kaggle-inbox"
    if not fs.is_dir(inbox):
        return {"files": 0, "job_directories": 0}
    try:
        files = [p for p in inbox.rglob("*")
                 if fs.is_regular_file(p) and p.name != ".gitkeep"]
    except OSError:
        files = []
    try:
        jobs = [p for p in inbox.iterdir()
                if fs.is_dir(p) and not p.name.startswith(".")]
    except OSError:
        jobs = []
    return {"files": len(files), "job_directories": len(jobs)}


def _runtime_status(root: Path) -> dict[str, Any]:
    import os
    import sys
    node = shutil.which("node") is not None
    micromamba = fs.is_regular_file(root / ".micromamba" / "bin" / "micromamba") or shutil.which("micromamba") is not None
    llama = shutil.which("llama-server") is not None or os.environ.get("LLAMA_CPP_BINARY") is not None
    return {
        "node": node,
        "micromamba": micromamba,
        "llama_server": llama,
        "python_version": sys.version.split()[0],
    }


def status(workspace: str | Path = ".") -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    stored = manifest.load_manifest(root)
    if stored is None:
        raise UserError(f"not a papersmith workspace: missing {root / '.papersmith/manifest.json'}")
    workspace_config = config.load_workspace_config(root)
    yaml = config.load_papersmith_yaml(root)
    kit_root = resolve_and_validate()
    kit_version = manifest.kit_version(kit_root)
    workspace_version = read_workspace_version(root, "unknown")
    current_files = manifest.workspace_framework_files(root, kit_root)
    stored_files = stored.get("files", {})
    drifted = sorted({
        path for path in set(current_files) | set(stored_files)
        if current_files.get(path) != stored_files.get(path)
    })
    ledger = _read_ledger(root)
    failed_runs = [entry for entry in ledger if entry.get("exit") not in (None, 0)]
    return {
        "workspace": str(root),
        "project_name": workspace_config["project_name"],
        "title": yaml.get("title"),
        "framework": {
            "installed_cli_version": __version__,
            "kit_version": kit_version,
            "workspace_version": workspace_version,
            "version_match": workspace_version == kit_version,
            "drifted_files": drifted,
        },
        "runtimes": _runtime_status(root),
        "proposal": _proposal_status(root),
        "implementations": _implementation_status(root),
        "tests": {
            "recorded_runs": len(ledger),
            "failed_runs": len(failed_runs),
            "last_run": ledger[-1] if ledger else None,
        },
        "remote": {
            "active_target": workspace_config["execution_engine"]["active_compute_target"],
            "active_profile": workspace_config["execution_engine"]["active_profile"],
            "recorded_runs": len(ledger),
            "failed_runs": len(failed_runs),
        },
        "accounts": _account_status(root),
        "inbox": _inbox_status(root),
    }


def print_human(snapshot: dict[str, Any]) -> None:
    framework = snapshot["framework"]
    proposal = snapshot["proposal"]
    runtimes = snapshot.get("runtimes", {})
    print(f"Workspace: {snapshot['project_name']} ({snapshot['workspace']})")
    print(
        f"Framework: kit {framework['kit_version']}; workspace {framework['workspace_version']}; "
        f"CLI {framework['installed_cli_version']}"
    )
    print("Framework drift: " + (", ".join(framework["drifted_files"]) if framework["drifted_files"] else "none"))
    if runtimes:
        node_status = "OK" if runtimes.get("node") else "Missing"
        llama_status = "OK" if runtimes.get("llama_server") else "Missing"
        print(f"Runtimes: Python {runtimes.get('python_version')}; Node {node_status}; OCR Engine {llama_status}")
    print(f"Proposal: {proposal.get('revision_id') or 'none'} ({proposal.get('lifecycle_stage')})")
    print(f"Implementations: {len(snapshot['implementations'])}")
    print(f"Recorded runs: {snapshot['tests']['recorded_runs']} ({snapshot['tests']['failed_runs']} failed)")
    print(f"Accounts: {snapshot['accounts']['count']}")
    print(f"Inbox: {snapshot['inbox']['files']} files in {snapshot['inbox']['job_directories']} job directories")



def register(subparsers) -> None:
    parser = subparsers.add_parser("status", help="show comprehensive workspace status")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    snapshot = status(args.directory)
    if args.as_json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print_human(snapshot)
    return 0
