"""Safe subprocess helpers for Python skill entrypoints."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from ..core.exit_codes import map_child_rc
from ..core import fs
from ..errors import ExecutionError, SourceError, UserError


def interpreter_for(workspace: Path, *, prefer_micromamba: bool = False) -> list[str]:
    """Return an argv prefix for the skill's Python runtime.

    Marker and the Kaggle adapter need the project-local ``papersmith``
    environment when it exists. Pure-stdlib skill commands can use the host
    interpreter, which keeps status/audit usable before environment setup.
    """
    mamba = workspace / ".micromamba" / "bin" / "micromamba"
    env_dir = workspace / ".micromamba" / "envs" / "papersmith"
    if prefer_micromamba and fs.is_regular_file(mamba) and fs.is_dir(env_dir):
        return [str(mamba), "run", "-n", "papersmith", "python"]
    return [sys.executable]


def run_script(workspace: Path, script: str | Path, args: Sequence[str] = (), *,
               prefer_micromamba: bool = False, timeout: float | None = None,
               env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run a workspace-relative Python script with list-based argv."""
    root = workspace.expanduser().resolve()
    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = root / script_path
    if not fs.is_regular_file(script_path):
        raise SourceError(f"missing skill script: {script_path}")
    command = interpreter_for(root, prefer_micromamba=prefer_micromamba)
    command.extend([str(script_path), *(str(item) for item in args)])
    child_env = os.environ.copy()
    if env:
        child_env.update(env)
    try:
        return subprocess.run(
            command,
            cwd=root,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecutionError(f"skill command timed out: {' '.join(command)}") from exc
    except OSError as exc:
        raise ExecutionError(f"could not execute skill command {command[0]}: {exc}") from exc


def mapped_returncode(result: subprocess.CompletedProcess[Any]) -> int:
    """Map a child result to the public papersmith exit-code contract."""
    return map_child_rc(result.returncode)


def emit_result(result: subprocess.CompletedProcess[Any]) -> int:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return mapped_returncode(result)
