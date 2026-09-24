"""Read and write workspace-owned JSON/YAML configuration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import UserError
from ..schema import validate_config_json, validate_papersmith_yaml
from ..yamllite import YamlliteError, loads
from . import fs


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict:
    if not fs.is_regular_file(path):
        # A FIFO here would block the open forever and a directory would raise,
        # so the gate comes first: both are configuration failures, both typed.
        if fs.exists(path):
            raise UserError(f"corrupted JSON file {path}: not a readable regular file")
        raise UserError(f"missing configuration file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UserError(f"corrupted JSON file {path}: {exc}") from None
    if not isinstance(data, dict):
        raise UserError(f"configuration file {path} must contain a JSON object")
    return data


def write_json(path: Path, data: Any) -> None:
    """Write a workspace config, or raise the typed error the CLI contracts on.

    A bare ``write_text`` on a read-only or non-regular path raised an untyped
    ``PermissionError`` out of commands that had already mutated the workspace.
    """
    if not fs.write_text(path, json.dumps(data, indent=2, sort_keys=False) + "\n"):
        raise UserError(f"could not write {path}")


def load_workspace_config(workspace: Path) -> dict:
    data = read_json(workspace / ".papersmith" / "config.json")
    return validate_config_json(data)


def load_papersmith_yaml(workspace: Path, *, require_compute: bool = True) -> dict:
    path = workspace / "papersmith.yaml"
    if not fs.is_regular_file(path):
        if fs.exists(path):
            raise UserError(f"invalid workspace YAML {path}: not a readable regular file")
        raise UserError(f"missing workspace configuration: {path}")
    try:
        data = loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, YamlliteError) as exc:
        raise UserError(f"invalid workspace YAML {path}: {exc}") from None
    return validate_papersmith_yaml(data, require_compute=require_compute)
