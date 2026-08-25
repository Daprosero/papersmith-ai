"""The shared implementation core: its guards, and the wall against domain names.

`.claude/skills/_core/implementation/` is what every implementation skill needs
and none of them owns. Three of the things it holds -- the workspace guard, the
dirty-worktree guard, and the migration's prefix mapping -- had NO test before
this file: replacing each with a permissive stub left all 1440 tests green, which
is the same signal as deleting them. They are shared now, so a silent break would
reach every skill that imports them rather than just the one that wrote them.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORE = REPOSITORY_ROOT / ".claude/skills/_core/implementation"
sys.path.insert(0, str(CORE))

import impl_gitops  # noqa: E402
import impl_guards  # noqa: E402
import impl_layout  # noqa: E402
import impl_references  # noqa: E402
import impl_refusals  # noqa: E402

CLI_SCRIPT = REPOSITORY_ROOT / ".claude/skills/proposal-implementation/scripts/implementation_cli.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class WorkspaceGuardTests(unittest.TestCase):
    """`resolve_target` is the only thing between generated code and the forge."""

    def setUp(self) -> None:
        impl_layout.WORKSPACE.mkdir(parents=True, exist_ok=True)
        self.inside = Path(tempfile.mkdtemp(prefix="_core_guard_",
                                            dir=impl_layout.WORKSPACE))
        self.addCleanup(shutil.rmtree, self.inside, True)
        self.outside = Path(tempfile.mkdtemp(prefix="_core_guard_outside_"))
        self.addCleanup(shutil.rmtree, self.outside, True)

    def test_a_target_outside_the_workspace_is_refused(self):
        _git(self.outside, "init", "-q")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.resolve_target(str(self.outside))
        self.assertEqual(caught.exception.code, "OUTSIDE_WORKSPACE")

    def test_a_directory_that_is_not_a_repository_is_refused(self):
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.resolve_target(str(self.inside))
        self.assertEqual(caught.exception.code, "NOT_A_GIT_REPO")

    def test_a_repository_inside_the_workspace_resolves(self):
        _git(self.inside, "init", "-q")
        self.assertEqual(impl_guards.resolve_target(str(self.inside)),
                         self.inside.resolve())


class DirtyWorktreeGuardTests(unittest.TestCase):
    """Never mutate a repository whose state the user has not committed."""

    def setUp(self) -> None:
        impl_layout.WORKSPACE.mkdir(parents=True, exist_ok=True)
        self.repo = Path(tempfile.mkdtemp(prefix="_core_dirty_",
                                          dir=impl_layout.WORKSPACE))
        self.addCleanup(shutil.rmtree, self.repo, True)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "a.txt").write_text("one\n")
        _git(self.repo, "add", "a.txt")
        _git(self.repo, "commit", "-qm", "one")

    def test_a_clean_worktree_passes(self):
        self.assertIsNone(impl_guards.require_clean_worktree(self.repo))

    def test_an_uncommitted_change_is_refused(self):
        (self.repo / "a.txt").write_text("two\n")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.require_clean_worktree(self.repo)
        self.assertEqual(caught.exception.code, "DIRTY_WORKTREE")

    def test_an_untracked_file_is_refused_too(self):
        """Untracked counts: a migration that overwrites one destroys it."""
        (self.repo / "b.txt").write_text("new\n")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.require_clean_worktree(self.repo)
        self.assertEqual(caught.exception.code, "DIRTY_WORKTREE")


class PrefixMappingTests(unittest.TestCase):
    """Moves break paths exactly as renames do, and the mapping is what fixes them."""

    def test_a_rename_maps_directly(self):
        self.assertEqual(
            impl_references.prefix_mappings([{"from": "Alpha", "to": "Beta"}], []),
            [("Alpha", "Beta")])

    def test_a_move_that_only_nests_yields_the_nesting_prefix(self):
        """`Cat/x.csv -> Name/Cat/x.csv` means `Cat -> Name/Cat`, not a rename."""
        self.assertEqual(
            impl_references.prefix_mappings(
                [], [{"from": "Cat/x.csv", "to": "Name/Cat/x.csv"}]),
            [("Cat", "Name/Cat")])

    def test_an_ambiguous_prefix_is_dropped_rather_than_guessed(self):
        """Two destinations for one prefix: a wrong rewrite beats no rewrite."""
        self.assertEqual(
            impl_references.prefix_mappings(
                [{"from": "Alpha", "to": "Beta"}, {"from": "Alpha", "to": "Gamma"}], []),
            [])


class CoreNamesNoDomainTests(unittest.TestCase):
    """The core that names one domain is a core only one skill can use.

    Read from the CLI that owns them rather than restated here, so a skill that
    adds a product directory is held to the same wall without editing this test.
    """

    @staticmethod
    def _cli_module():
        spec = importlib.util.spec_from_file_location("impl_cli_for_lock", CLI_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_no_core_file_names_a_product_directory_or_source_root(self):
        cli = self._cli_module()
        owned = {*cli.PRODUCT_DIRS, *(root.rstrip("/") for root in cli.SOURCE_ROOTS)}
        self.assertGreater(len(owned), 3, "the CLI declares no layout to be held to")
        leaks = []
        for path in sorted(CORE.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for name in sorted(owned):
                if name in text:
                    leaks.append(f"{path.name} names {name!r}")
        self.assertEqual(leaks, [], "the core must take these from its caller")

    def test_the_core_resolves_the_repository_root_it_actually_lives_in(self):
        """`parents[4]` is a count, and a count is silent when a file moves.

        It happens to be the same five components the CLI walked before this
        core existed -- a coincidence of two directory names, not a rule.
        """
        self.assertEqual(impl_layout.FORGE_ROOT, REPOSITORY_ROOT)
        self.assertTrue((impl_layout.FORGE_ROOT / ".claude").is_dir())
        self.assertEqual(impl_layout.WORKSPACE,
                         REPOSITORY_ROOT / "implementations")


if __name__ == "__main__":
    unittest.main()
