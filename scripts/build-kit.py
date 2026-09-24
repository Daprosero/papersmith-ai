#!/usr/bin/env python3
"""Assemble the bundled kit at ``src/papersmith/_kit`` and its kit-manifest.

Run from a papersmith-ai checkout. The kit is the snapshot of framework files
(``skills/``, agent definitions, ``guidance/paper-guide/``, provisioning
scripts, manifests) that ``papersmith init`` copies into new workspaces and
``papersmith upgrade`` re-syncs. It is regenerated automatically by the build
hook in ``setup.py``, so ``pipx install .`` always ships a fresh one.

Stdlib only; imports the package from ``src/`` for its manifest contract.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
KIT = SRC / "papersmith" / "_kit"

sys.path.insert(0, str(SRC))

import papersmith  # noqa: E402
from papersmith.core import manifest  # noqa: E402


def assemble(quiet: bool = False) -> None:
    files = manifest.walk_kit_files(ROOT)
    if not any(rel.startswith("skills/") for rel in files):
        raise SystemExit(f"refusing to build a kit without skills/ files from {ROOT}")

    if KIT.exists():
        shutil.rmtree(KIT)
    KIT.mkdir(parents=True)
    for relpath in sorted(files):
        src = ROOT / relpath
        dst = KIT / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    manifest.write_manifest(KIT, papersmith.__version__, files, kind="kit")
    if not quiet:
        print(f"kit: {len(files)} files -> {KIT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="print nothing on success")
    args = parser.parse_args()
    assemble(quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
