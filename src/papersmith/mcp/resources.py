"""MCP resources: read-only ambient context over fixed URIs.

Resources never take a caller-supplied path, so there is no traversal surface
here; each URI maps to one known reader under the bound workspace. The runs
reader redacts the ledger's ``command`` field, which can embed a
``--consent <token>`` operand (``executor.py`` records the command verbatim).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..core import fs
from .bridge import ChildPlan, redact, run_plan
from .registry import ToolRefusal

RUNS_TAIL_LIMIT = 50


@dataclass(frozen=True)
class ResourceSpec:
    uri: str
    name: str
    description: str
    mime_type: str
    reader: Callable[[Path], str]


def _child_text(plan: ChildPlan, workspace: Path) -> str:
    result = run_plan(plan, workspace)
    if result.timed_out:
        raise ToolRefusal("RESOURCE_TIMEOUT", f"{plan.tokens[0]} timed out")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ToolRefusal(
            "RESOURCE_UNAVAILABLE",
            f"{plan.tokens[0]} exited {result.returncode}: {detail[-1] if detail else 'no detail'}",
        )
    return result.stdout


def _read_status(workspace: Path) -> str:
    return _child_text(ChildPlan("cli", ("status", "--json", str(workspace))), workspace)


def _read_config(workspace: Path) -> str:
    text = fs.read_text(workspace / "papersmith.yaml")
    if text is None:
        raise ToolRefusal("RESOURCE_UNAVAILABLE", "papersmith.yaml is absent or unreadable")
    return redact(text)


def _read_runs(workspace: Path) -> str:
    path = workspace / ".papersmith" / "runs_ledger.jsonl"
    text = fs.read_text(path)
    if text is None:
        return "[]"
    lines = [line for line in text.splitlines() if line.strip()]
    events: list[object] = []
    for line in lines[-RUNS_TAIL_LIMIT:]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            events.append({"status": "invalid"})
            continue
        if isinstance(event, dict):
            event = dict(event)
            if isinstance(event.get("command"), str):
                event["command"] = redact(event["command"])
            else:
                event = json.loads(redact(json.dumps(event)))
        events.append(event)
    return json.dumps(events, indent=2, sort_keys=True)


def _read_paper(argv: list[str], workspace: Path) -> str:
    script = workspace / "skills" / "paper-writing" / "scripts" / "paper_cli.py"
    return _child_text(ChildPlan("paper", tuple([str(script), *argv])), workspace)


def _read_blocks(workspace: Path) -> str:
    return _read_paper(["status"], workspace)


def _read_plan(workspace: Path) -> str:
    return _read_paper(["plan"], workspace)


def _read_contract(workspace: Path) -> str:
    return _read_paper(["contract"], workspace)


def _read_refs(workspace: Path) -> str:
    text = fs.read_text(workspace / "paper" / "refs.bib")
    if text is None:
        raise ToolRefusal("RESOURCE_UNAVAILABLE", "paper/refs.bib is absent or unreadable")
    return text


RESOURCES: tuple[ResourceSpec, ...] = (
    ResourceSpec(
        "papersmith://workspace/status",
        "Workspace status",
        "Machine-readable workspace snapshot (`papersmith status --json`).",
        "application/json",
        _read_status,
    ),
    ResourceSpec(
        "papersmith://workspace/config",
        "Workspace configuration",
        "The workspace's own `papersmith.yaml` (secret-shaped values redacted).",
        "application/yaml",
        _read_config,
    ),
    ResourceSpec(
        "papersmith://workspace/runs",
        "Runs ledger tail",
        "The last runs recorded in `.papersmith/runs_ledger.jsonl`, with `command` redacted.",
        "application/json",
        _read_runs,
    ),
    ResourceSpec(
        "papersmith://paper/blocks",
        "Paper block table",
        "The paper's block table (`paper_cli status`).",
        "application/json",
        _read_blocks,
    ),
    ResourceSpec(
        "papersmith://paper/contract",
        "Section contract",
        "The section corpus contract (`paper_cli contract`).",
        "application/json",
        _read_contract,
    ),
    ResourceSpec(
        "papersmith://paper/plan",
        "Paper plan",
        "Guidance classes, declaration/fact fill state, provenance state (`paper_cli plan`).",
        "application/json",
        _read_plan,
    ),
    ResourceSpec(
        "papersmith://paper/refs",
        "Bibliography",
        "The paper's own `paper/refs.bib`.",
        "text/x-bibtex",
        _read_refs,
    ),
)

RESOURCES_BY_URI: dict[str, ResourceSpec] = {spec.uri: spec for spec in RESOURCES}


def read_resource(uri: str, workspace: Path) -> ResourceSpec:
    """Resolve a resource spec, refusing anything not on the fixed table."""
    spec = RESOURCES_BY_URI.get(uri)
    if spec is None:
        raise ToolRefusal("RESOURCE_UNKNOWN", f"no resource named {uri!r}")
    return spec
