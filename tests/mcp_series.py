"""Shared helpers for the MCP server suite.

Every MCP test drives the real server as a subprocess over stdio, so what is
exercised is the product a client receives, never an in-process shortcut.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from workspace_series import REPO_ROOT, make_workspace

SRC = REPO_ROOT / "src"


def scripts_env() -> dict[str, str]:
    """The child environment, with ``src/`` importable without an install."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + existing if existing else "")
    return env


def serve(
    workspace: Path,
    messages: list[dict],
    *,
    explicit_workspace: bool = True,
    timeout: float = 300.0,
) -> tuple[list[dict], subprocess.CompletedProcess[str]]:
    """Run one server session with ``messages`` and return its responses."""
    payload = "".join(json.dumps(message) + "\n" for message in messages)
    argv = [sys.executable, "-m", "papersmith.cli", "mcp", "serve"]
    if explicit_workspace:
        argv.extend(["--workspace", str(workspace)])
    completed = subprocess.run(
        argv,
        input=payload,
        capture_output=True,
        text=True,
        cwd=str(workspace),
        env=scripts_env(),
        timeout=timeout,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    return responses, completed


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "papersmith.cli", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=scripts_env(),
    )


def tool_call(name: str, arguments: dict | None = None, request_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }


def resource_read(uri: str, request_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "resources/read",
        "params": {"uri": uri},
    }


def request(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    message: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def build_workspace(base: Path, name: str = "mcp-ws") -> Path:
    return make_workspace(base, name=name, remote="local")


def scaffold_paper(workspace: Path) -> None:
    script = workspace / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
    subprocess.run(
        [sys.executable, str(script), "scaffold"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        env=scripts_env(),
        check=False,
    )


def call_many(workspace: Path, messages: list[dict]) -> list[dict]:
    responses, completed = serve(workspace, messages)
    assert completed.returncode == 0, completed.stderr
    assert len(responses) == len(messages), (len(responses), len(messages), completed.stderr)
    return responses


def tree_hash(root: Path) -> str:
    """A content hash of every tracked file under ``root``."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix in (".pyc", ".pyo"):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
