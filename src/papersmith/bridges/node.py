"""Bridge to the proposal-deliberation JSON-lines engine."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from ..core import fs
from ..errors import ExecutionError, SourceError, UserError


def node_binary() -> str | None:
    return shutil.which("node")


def engine_path(workspace: Path) -> Path:
    path = workspace / "skills" / "proposal-deliberation" / "cli.mjs"
    if not fs.is_regular_file(path):
        raise SourceError(f"missing deliberation engine: {path}")
    return path


def ensure_node_engine(workspace: Path) -> tuple[str, Path]:
    node = node_binary()
    if node is None:
        raise UserError("node is required for deliberate; install Node.js >=20")
    engine = engine_path(workspace)
    if not fs.is_dir(workspace / "node_modules" / "jiti"):
        raise UserError(
            "workspace node dependencies are missing; run npm install before deliberate"
        )
    return node, engine


def _environment(workspace: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PROPOSAL_DELIBERATION_PROJECT_ROOT"] = str(workspace)
    env.setdefault("PROPOSAL_DELIBERATION_SESSION_ID", "papersmith-cli-session")
    env.setdefault(
        "DELIBERATION_DOMAIN_PROFILE",
        str(workspace / "skills" / "proposal-deliberation" / "profile.ts"),
    )
    return env


def _parse_responses(stdout: str, *, command: list[str]) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExecutionError(f"deliberation engine returned non-JSON output: {line!r}") from exc
        if not isinstance(value, dict):
            raise ExecutionError("deliberation engine response must be a JSON object")
        responses.append(value)
    if not responses:
        raise ExecutionError(f"deliberation engine returned no response: {' '.join(command)}")
    return responses


def call_engine(workspace: Path, requests: Iterable[dict[str, Any]], *, timeout: float = 120) -> list[dict[str, Any]]:
    """Send one or more independent requests through one serve process."""
    node, engine = ensure_node_engine(workspace)
    command = [node, str(engine), "--serve"]
    payload = "".join(json.dumps(request, separators=(",", ":")) + "\n" for request in requests)
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=_environment(workspace),
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecutionError("deliberation engine timed out") from exc
    except OSError as exc:
        raise ExecutionError(f"could not execute node: {exc}") from exc
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "unknown node error").strip()
        raise ExecutionError(f"deliberation engine failed ({completed.returncode}): {detail}")
    return _parse_responses(completed.stdout, command=command)


def call_engine_with_acceptance(workspace: Path, preview: dict[str, Any], *, timeout: float = 120) -> list[dict[str, Any]]:
    """Preview and accept a successor without losing its in-memory token."""
    node, engine = ensure_node_engine(workspace)
    command = [node, str(engine), "--serve"]
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=_environment(workspace),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(json.dumps(preview, separators=(",", ":")) + "\n")
        process.stdin.flush()
        first_line = process.stdout.readline()
        if not first_line:
            stderr = process.stderr.read() if process.stderr else ""
            process.kill()
            raise ExecutionError(f"deliberation preview returned no response: {stderr.strip()}")
        first = _parse_responses(first_line, command=command)[0]
        token = first.get("acceptanceToken") or first.get("successorAcceptanceToken")
        if not isinstance(token, str) or not token:
            process.stdin.close()
            process.wait(timeout=timeout)
            stderr = process.stderr.read() if process.stderr else ""
            if process.returncode:
                raise ExecutionError(f"deliberation engine failed ({process.returncode}): {stderr.strip()}")
            return [first]
        accepted = dict(preview)
        accepted["acceptSuccessor"] = True
        accepted["successorAcceptanceToken"] = token
        process.stdin.write(json.dumps(accepted, separators=(",", ":")) + "\n")
        process.stdin.flush()
        second_line = process.stdout.readline()
        if not second_line:
            process.kill()
            raise ExecutionError("deliberation acceptance returned no response")
        second = _parse_responses(second_line, command=command)[0]
        process.stdin.close()
        process.wait(timeout=timeout)
        if process.returncode:
            stderr = process.stderr.read() if process.stderr else ""
            raise ExecutionError(f"deliberation engine failed ({process.returncode}): {stderr.strip()}")
        return [first, second]
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            process.kill()
        raise ExecutionError("deliberation acceptance timed out") from exc
    except OSError as exc:
        raise ExecutionError(f"could not execute deliberation engine: {exc}") from exc


def run_engine_passthrough(workspace: Path) -> int:
    """Run the engine's native interactive serve mode with inherited stdio."""
    node, engine = ensure_node_engine(workspace)
    try:
        return subprocess.run(
            [node, str(engine), "--serve"],
            cwd=workspace,
            env=_environment(workspace),
            check=False,
        ).returncode
    except OSError as exc:
        raise ExecutionError(f"could not execute deliberation engine: {exc}") from exc
