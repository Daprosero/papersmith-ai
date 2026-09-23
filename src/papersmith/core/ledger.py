"""Append-only execution ledger for workspace runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import fs
from .config import utc_timestamp


def path_for(workspace: Path) -> Path:
    return workspace / ".papersmith" / "runs_ledger.jsonl"


def append(workspace: Path, event: dict[str, Any]) -> bool:
    """Record one run, or report that it could not be recorded.

    The ledger is bookkeeping: a damaged ledger — a FIFO a write would block on,
    an unsearchable parent — must not fail a run whose own outcome is already
    decided. Returns False instead, and the run's caller still reports the run.
    """
    path = path_for(workspace)
    record = {"timestamp": utc_timestamp(), **event}
    line = json.dumps(record, sort_keys=True) + "\n"
    if not fs.can_be_written(path):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as output:
            output.write(line)
    except OSError:
        return False
    return True


def read(workspace: Path) -> list[dict[str, Any]]:
    """Best-effort: a damaged ledger reads as empty, not as a crash."""
    text = fs.read_text(path_for(workspace))
    if text is None:
        return []
    result: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            result.append({"status": "invalid"})
            continue
        if isinstance(value, dict):
            result.append(value)
    return result
