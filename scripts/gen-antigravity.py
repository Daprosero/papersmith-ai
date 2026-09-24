#!/usr/bin/env python3
"""Generate or check the Antigravity projection for a papersmith workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from papersmith.errors import PapersmithError  # noqa: E402
from papersmith.generators import apply_generated, check_generated  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=Path, help="workspace root")
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args(argv)
    try:
        root = args.root.expanduser().resolve()
        if args.check:
            drifted = check_generated(root, tools=("antigravity",))
            if drifted:
                print("drift: " + ", ".join(drifted))
                return 3
            print("antigravity: clean")
            return 0
        changed = apply_generated(root, tools=("antigravity",))
        print(f"antigravity: generated ({len(changed)} changed)")
        return 0
    except PapersmithError as exc:
        print(f"gen-antigravity: error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
