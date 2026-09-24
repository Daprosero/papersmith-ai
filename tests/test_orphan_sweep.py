"""The two refusals matter more than the removal.

A sweep that only proves it deletes is the dangerous kind. These tests pin
the two things that must never happen: a tracked path must survive whatever
its name, and a fixture a live sibling process is still writing to must
survive whatever its name. `skills/_core/` is 66 tracked files behind
a leading underscore, and this repository is routinely worked by several
concurrent agents running the same suite.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import orphan_sweep


class SweepRemovesOrphansTests(unittest.TestCase):
    """An untracked, old, underscore-prefixed entry is what a killed run
    leaves behind, and is the only thing this sweep exists to remove."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _aged(self, name: str, age_seconds: float) -> Path:
        path = self.root / name
        path.mkdir()
        (path / "fixture.txt").write_text("left behind")
        stamp = time.time() - age_seconds
        import os
        os.utime(path, (stamp, stamp))
        return path

    def test_an_old_untracked_fixture_is_removed(self) -> None:
        orphan = self._aged("_e2e_step_killed_51945", age_seconds=7200)
        removed = orphan_sweep.sweep(roots=(self.root,), min_age_seconds=3600)
        self.assertFalse(orphan.exists())
        self.assertEqual(len(removed), 1)

    def test_a_fresh_fixture_survives(self) -> None:
        """A sibling process writing right now. Removing this is how a
        cleanup becomes a way to lose someone else's work."""
        live = self._aged("_e2e_step_killed_51945", age_seconds=30)
        orphan_sweep.sweep(roots=(self.root,), min_age_seconds=3600)
        self.assertTrue(live.exists(), "a live sibling's fixture was swept")

    def test_a_dunder_directory_survives(self) -> None:
        cache = self._aged("__pycache__", age_seconds=7200)
        orphan_sweep.sweep(roots=(self.root,), min_age_seconds=3600)
        self.assertTrue(cache.exists())

    def test_an_absent_root_is_not_an_error(self) -> None:
        self.assertEqual(orphan_sweep.sweep(roots=(self.root / "nope",)), [])


class TrackedPathsAreUnreachableTests(unittest.TestCase):
    """The guard that keeps `_core` alive, proven against a real git index
    rather than against the name it happens to have today."""

    def test_a_tracked_underscore_directory_is_never_swept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
            core = repo / "skills" / "_core"
            core.mkdir(parents=True)
            (core / "shared.py").write_text("# tracked\n")
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "core"], cwd=repo, check=True)

            stamp = time.time() - 7200
            import os
            os.utime(core, (stamp, stamp))

            original_root = orphan_sweep.FORGE_ROOT
            orphan_sweep.FORGE_ROOT = repo
            try:
                removed = orphan_sweep.sweep(
                    roots=(repo / "skills",), min_age_seconds=3600,
                )
            finally:
                orphan_sweep.FORGE_ROOT = original_root

            self.assertTrue((core / "shared.py").exists(),
                            "a tracked directory was swept")
            self.assertEqual(removed, [])


class RealRootsAreResolvableTests(unittest.TestCase):
    """`SWEEP_ROOTS` is derived from the tree, so a skill added later is
    covered without anyone remembering to list it."""

    def test_implementations_is_among_the_swept_roots(self) -> None:
        names = {p.name for p in orphan_sweep.SWEEP_ROOTS}
        self.assertIn("implementations", names)

    def test_every_skills_scripts_directory_is_covered(self) -> None:
        derived = set(orphan_sweep.SWEEP_ROOTS)
        on_disk = set((orphan_sweep.FORGE_ROOT / "skills").glob("*/scripts"))
        self.assertTrue(on_disk, "no skill scripts directories found at all")
        self.assertTrue(on_disk <= derived, f"not covered: {on_disk - derived}")


if __name__ == "__main__":
    unittest.main()
