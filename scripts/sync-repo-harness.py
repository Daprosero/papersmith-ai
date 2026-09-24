#!/usr/bin/env python3
"""Project the generated harness surfaces into this checkout.

The generators cannot run at the repository root -- there is no
``.papersmith/config.json`` here, so ``context_for_workspace`` refuses (see
``generators.context_for_workspace``). This script therefore builds a throwaway
workspace with the real ``papersmith init``, renders the projection there, and
copies only the context-independent artifacts back into the checkout:
``.opencode/commands/``, ``.opencode/plugins/``, and ``.claude/commands/``.

``opencode.json`` and the root routing docs are deliberately NOT copied: they
are context-dependent (they carry the workspace name/version) and at the root
they are hand-maintained.

Run directly -- there is intentionally no ``package.json`` script for this:

    python scripts/sync-repo-harness.py [--check]

``package.json`` is a ``KIT_ENTRIES`` member copied into every workspace
(``core/manifest.py``), while this script ships nowhere, so a repo-only npm
script would dangle in every generated workspace.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from papersmith.core import init as init_module  # noqa: E402
from papersmith.errors import PapersmithError  # noqa: E402
from papersmith.generators import apply_generated, context_for_workspace  # noqa: E402

#: ``(workspace-relative directory, checkout-relative directory)`` pairs that are
#: context-independent and therefore safe to project verbatim.
PROJECTION = (
    (".opencode/commands", ".opencode/commands"),
    (".opencode/plugins", ".opencode/plugins"),
    (".claude/commands", ".claude/commands"),
)
GENERATED_TOOLS = ("opencode", "claude")


def _render(holder: Path) -> tuple[Path, list[str]]:
    """Build a throwaway workspace and return it plus its skip warnings."""
    workspace = holder / "workspace"
    init_module.initialize(workspace, remote="local", run_npm=False)
    skipped: list[str] = []
    apply_generated(workspace, context_for_workspace(workspace), GENERATED_TOOLS, warnings=skipped)
    return workspace, skipped


def _expected(workspace: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for source_rel, target_rel in PROJECTION:
        source = workspace / source_rel
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*")):
            if path.is_file():
                relative = path.relative_to(source).as_posix()
                files[f"{target_rel}/{relative}"] = path.read_text(encoding="utf-8")
    return files


def _orphans(expected: dict[str, str]) -> list[str]:
    found: list[str] = []
    for _, target_rel in PROJECTION:
        directory = ROOT / target_rel
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            relative = f"{target_rel}/{path.relative_to(directory).as_posix()}"
            if relative not in expected:
                found.append(relative)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args(argv)
    try:
        with tempfile.TemporaryDirectory() as holder:
            workspace, skipped = _render(Path(holder))
            for message in skipped:
                print(message, file=sys.stderr)
            expected = _expected(workspace)
            drift = [
                relative
                for relative, content in expected.items()
                if not (ROOT / relative).is_file()
                or (ROOT / relative).read_text(encoding="utf-8") != content
            ]
            drift.extend(_orphans(expected))
            if args.check:
                if drift:
                    print("drift: " + ", ".join(sorted(drift)))
                    return 3
                print(f"harness projection: clean ({len(expected)} files)")
                return 0
            written = 0
            for relative, content in expected.items():
                path = ROOT / relative
                if not path.is_file() or path.read_text(encoding="utf-8") != content:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                    written += 1
            print(f"harness projection: synced ({written} of {len(expected)} changed)")
            return 0
    except PapersmithError as exc:
        print(f"sync-repo-harness: error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
