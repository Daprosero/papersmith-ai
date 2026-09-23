"""orphan_sweep: removes fixture directories a killed test run left behind.

Several suites materialize their fixtures inside the live repository rather
than a temp dir, because the code under test resolves its workspace from
`FORGE_ROOT` and offers no override for it. Those suites do clean up after
themselves -- but `addCleanup` never runs when the process is killed, and a
session limit, a timeout or a cancelled agent all kill it. What survives is a
`_<name>_<pid>` directory that the next run reads as real, producing failures
whose message points at the wrong defect entirely.

Two guards make this safe to run while other processes are using the same
checkout, which is how this repository is actually worked:

- **Untracked only.** Anything git tracks is left alone, whatever its name.
  `skills/_core/` is 66 tracked files behind a leading underscore; a
  name-pattern sweep without this guard would delete the shared core.
- **Old only.** A sibling process's fixture is seconds or minutes old. The
  age floor distinguishes an orphan whose owner is dead from a directory
  someone is writing to right now.

Neither guard is an optimization. Dropping either one turns this from a
cleanup into a way to lose work.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]

#: Where suites are known to materialize fixtures inside the live repository.
#: Directories only -- a root absent from disk is skipped, not an error.
SWEEP_ROOTS: tuple[Path, ...] = (
    FORGE_ROOT / "implementations",
    *(FORGE_ROOT / "skills").glob("*/scripts"),
)

#: An orphan's owner is dead; a sibling's fixture is live. One hour is far
#: above any single test's lifetime and far below the gap between sessions.
MIN_AGE_SECONDS = 3600


def _is_untracked(path: Path) -> bool:
    """True when git knows nothing about `path`. Anything tracked is never
    swept -- this is what keeps `skills/_core/` and every other
    legitimately underscore-prefixed tracked path out of reach."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(path)],
        cwd=FORGE_ROOT, capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return False
    # A directory holding tracked children is itself tracked, for our purposes.
    listed = subprocess.run(
        ["git", "ls-files", "--", str(path)],
        cwd=FORGE_ROOT, capture_output=True, text=True,
    )
    return not listed.stdout.strip()


def _age_seconds(path: Path, now: float) -> float:
    return now - path.stat().st_mtime


def sweep(roots: tuple[Path, ...] = SWEEP_ROOTS,
          min_age_seconds: float = MIN_AGE_SECONDS,
          now: float | None = None) -> list[str]:
    """Removes untracked `_`-prefixed entries older than `min_age_seconds`
    under each of `roots`. Returns the paths removed, relative to the forge
    root, so a caller can report what it cleaned rather than doing it
    silently."""
    now = time.time() if now is None else now
    removed: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.glob("_*")):
            if child.name.startswith("__"):      # __pycache__ and friends
                continue
            if not _is_untracked(child):
                continue
            if _age_seconds(child, now) < min_age_seconds:
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            try:
                removed.append(str(child.relative_to(FORGE_ROOT)))
            except ValueError:
                # A root outside the forge (a test's own tempdir). Report the
                # absolute path rather than failing the sweep over cosmetics.
                removed.append(str(child))
    return removed


def sweep_and_report() -> None:
    """`setUpModule` entry point: sweeps, and says what it removed. Silence
    means nothing was left behind, which is the normal case."""
    if os.environ.get("FORGE_SKIP_ORPHAN_SWEEP"):
        return
    for path in sweep():
        print(f"orphan_sweep: removed {path} (left by a killed run)")
