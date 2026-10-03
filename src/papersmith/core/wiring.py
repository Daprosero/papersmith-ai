"""Per-harness wiring summary printed by ``init`` and ``upgrade``.

Reads the single support matrix (``generators.HARNESS_CAPABILITIES``) and what
is on disk after the run; it decides nothing and writes nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..generators import CAPABILITIES, HARNESS_CAPABILITIES
from .manifest import HARNESS_SKILL_LINKS, LinkReport


def _has_files(directory: Path) -> bool:
    try:
        return any(p.is_file() for p in directory.glob("*.md"))
    except OSError:
        return False


def _skills_state(root: Path, tool: str, report: LinkReport) -> str:
    links = [rel for owner, rel in HARNESS_SKILL_LINKS if owner == tool]
    if any(rel in report.blocked for rel in links):
        return "blocked"
    if any(rel in report.failed for rel in links):
        return "failed"
    canonical = root / "skills"
    for rel in links:
        link = root / rel
        try:
            if not (link.is_symlink() and link.resolve() == canonical.resolve()):
                return "failed"
        except OSError:
            return "failed"
    return "wired"


def summarize(root: Path, tools: Sequence[str], link_report: LinkReport,
              skipped: Sequence[str]) -> dict[str, dict[str, str]]:
    """``{tool: {capability: wired|unsupported|failed|blocked}}`` for ``tools``."""
    result: dict[str, dict[str, str]] = {}
    for tool in tools:
        row: dict[str, str] = {}
        for cap in CAPABILITIES:
            entry = HARNESS_CAPABILITIES[tool][cap]
            if not entry.supported:
                row[cap] = "unsupported"
            elif cap == "skills":
                row[cap] = _skills_state(root, tool, link_report)
            else:
                artifact = entry.artifact or ""
                under = [p for p in skipped
                         if p == artifact or p.startswith(artifact.rstrip("/") + "/")]
                path = root / artifact
                present = path.is_file() if cap == "plugins" else _has_files(path)
                row[cap] = "failed" if under or not present else "wired"
        result[tool] = row
    return result


def format_summary(summary: dict[str, dict[str, str]]) -> list[str]:
    """One short line per harness."""
    return [f"{tool}: " + " ".join(f"{cap}={state}" for cap, state in row.items())
            for tool, row in summary.items()]
