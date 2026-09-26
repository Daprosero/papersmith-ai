"""Upgrade tests for source synchronization and protected research state."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith.cli import main
from papersmith.core import config, init as init_module, manifest, upgrade as upgrade_module
from papersmith.errors import UserError


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "paper"
    init_module.initialize(workspace, run_npm=False)
    return workspace


class UpgradeTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        """Scratch directory, resolved -- see BridgesTests.new_tmp for why."""
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name).resolve()

    def set_env(self, name: str, value: str) -> None:
        patcher = mock.patch.dict(os.environ, {name: value})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_upgrade_restores_framework_files_and_preserves_research(self) -> None:
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        skill = workspace / "skills/paper-ingestion/SKILL.md"
        original_skill = skill.read_bytes()
        skill.write_bytes(b"user accidentally changed a framework file\n")

        readme = workspace / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nResearch note.\n", encoding="utf-8")
        yaml = workspace / "papersmith.yaml"
        original_yaml = yaml.read_bytes()
        yaml.write_bytes(original_yaml + b"\n# user configuration comment\n")
        research = workspace / "guidance/paper-guide/local-note.md"
        research.write_text("local guidance", encoding="utf-8")
        agent = workspace / ".claude/agents/paper-ingestion.md"
        agent.write_text(agent.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8")

        result = upgrade_module.upgrade(workspace)

        assert skill.read_bytes() == original_skill
        assert readme.read_text(encoding="utf-8").endswith("Research note.\n")
        assert yaml.read_bytes() == original_yaml + b"\n# user configuration comment\n"
        assert research.read_text(encoding="utf-8") == "local guidance"
        assert not agent.read_text(encoding="utf-8").endswith("local note\n")
        assert "skills/paper-ingestion/SKILL.md" in result["changed_files"]
        assert "README.md" not in result["changed_files"]
        assert "papersmith.yaml" not in result["changed_files"]
        assert "guidance/paper-guide/local-note.md" not in result["changed_files"]

        stored = json.loads((workspace / ".papersmith/manifest.json").read_text())
        expected = manifest.workspace_framework_files(workspace, Path(__file__).parents[1])
        assert stored["files"] == expected

    def test_upgrade_on_an_old_layout_workspaces_journal_and_decisions(self) -> None:
        """R3-preserve-contract-migration-unproved: `journal/**` and
        `DECISIONS.md` were dropped from `PRESERVE_PATTERNS`; nothing proved
        what an OLD-layout workspace's real `journal/` and `DECISIONS.md`
        (from a kit version whose manifest once tracked them) do under
        `upgrade`. MEASURED, not hoped: neither is in `KIT_ENTRIES` nor a
        `DYNAMIC_PREFIXES` orphan target, so `upgrade`'s copy loop and its
        orphan-removal loop never reach them -- both survive on disk with
        their original bytes. They are simply dropped from the REWRITTEN
        manifest's bookkeeping (no longer tracked as drift), never deleted
        or overwritten. No data loss was observed.
        """
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        journal_file = workspace / "journal" / "2024-01-01.md"
        journal_file.parent.mkdir()
        journal_file.write_text("research log entry", encoding="utf-8")
        decisions = workspace / "DECISIONS.md"
        decisions.write_text("# Decisions\n\nUse method X.\n", encoding="utf-8")

        manifest_path = workspace / ".papersmith" / "manifest.json"
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
        stored["files"]["journal/2024-01-01.md"] = manifest.sha256_file(journal_file)
        stored["files"]["DECISIONS.md"] = manifest.sha256_file(decisions)
        manifest_path.write_text(json.dumps(stored), encoding="utf-8")

        result = upgrade_module.upgrade(workspace)

        assert journal_file.read_text(encoding="utf-8") == "research log entry"
        assert decisions.read_text(encoding="utf-8") == "# Decisions\n\nUse method X.\n"
        assert "journal/2024-01-01.md" not in result["removed"]
        assert "DECISIONS.md" not in result["removed"]
        new_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "journal/2024-01-01.md" not in new_manifest["files"]
        assert "DECISIONS.md" not in new_manifest["files"]

    def test_upgrade_delivers_the_harness_projection_script(self) -> None:
        """A workspace made before the script shipped receives it on upgrade."""
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        script = workspace / "scripts" / "setup-harnesses.sh"
        assert script.is_file()
        script.unlink()

        result = upgrade_module.upgrade(workspace)

        assert "scripts/setup-harnesses.sh" in result["changed_files"]
        assert script.is_file()

    def test_upgrade_rebuilds_generated_projections(self) -> None:
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        generated = workspace / "CLAUDE.md"
        generated.write_text("drift\n", encoding="utf-8")
        result = upgrade_module.upgrade(workspace)
        assert generated.read_text(encoding="utf-8") != "drift\n"
        assert "CLAUDE.md" in result["changed_files"]

    def test_upgrade_tools_updates_active_tool_configuration(self) -> None:
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        result = upgrade_module.upgrade(workspace, tools=("claude", "pi"))
        assert result["active_tools"] == ["claude", "pi"]
        assert config.load_workspace_config(workspace)["active_tools"] == ["claude", "pi"]
        assert (workspace / "CLAUDE.md").is_file()
        assert (workspace / "PI.md").is_file()

    def test_upgrade_refuses_missing_manifest(self) -> None:
        tmp_path = self.new_tmp()
        with self.assertRaisesRegex(UserError, "not a papersmith workspace"):
            upgrade_module.upgrade(tmp_path / "not-a-workspace")

    def test_upgrade_refuses_corrupted_manifest(self) -> None:
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        (workspace / ".papersmith/manifest.json").write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(UserError, "corrupted manifest"):
            upgrade_module.upgrade(workspace)

    def test_upgrade_refreshes_version_from_a_new_kit(self) -> None:
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        kit = tmp_path / "kit-0.2"
        for relpath, content in {
            "skills/paper-ingestion/SKILL.md": "# upgraded skill\n",
            "scripts/setup_env.py": "# upgraded env\n",
            ".claude/agents/paper-ingestion.md": "---\nname: paper-ingestion\ndescription: upgraded\n---\n",
            "package.json": '{"version": "0.2.0"}\n',
            "requirements.txt": "kagglesdk==0.1.37\n",
            "CLAUDE.md": "# kit marker\n",
        }.items():
            path = kit / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.set_env("PAPERSMITH_KIT_ROOT", str(kit))

        result = upgrade_module.upgrade(workspace)

        assert result["version"] == "0.2.0"
        assert (workspace / ".papersmith/version").read_text() == "0.2.0\n"
        assert (workspace / "skills/paper-ingestion/SKILL.md").read_text() == "# upgraded skill\n"
        stored = json.loads((workspace / ".papersmith/manifest.json").read_text())
        assert stored["version"] == "0.2.0"

    def _kit_at(self, tmp_path, version: str):
        """A minimal kit whose only interesting property is its version."""
        kit = tmp_path / f"kit-{version}"
        for relpath, content in {
            "skills/paper-ingestion/SKILL.md": "# skill\n",
            "scripts/setup_env.py": "# env\n",
            ".claude/agents/paper-ingestion.md":
                "---\nname: paper-ingestion\ndescription: d\n---\n",
            "package.json": '{"version": "%s"}\n' % version,
            "requirements.txt": "kagglesdk==0.1.37\n",
            "CLAUDE.md": "# kit marker\n",
        }.items():
            path = kit / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.set_env("PAPERSMITH_KIT_ROOT", str(kit))
        return kit

    def test_upgrade_refuses_to_move_a_workspace_backwards(self) -> None:
        """`upgrade` read the kit's version and WROTE it, comparing only for
        equality to decide whether to rewrite the version file. Nothing
        ordered the two, so installing an older kit over a newer workspace
        downgraded it silently and reported the older version as the new
        truth."""
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        self._kit_at(tmp_path, "0.9.0")
        upgrade_module.upgrade(workspace)

        self._kit_at(tmp_path, "0.4.0")
        with self.assertRaises(UserError) as caught:
            upgrade_module.upgrade(workspace)
        message = str(caught.exception)
        self.assertIn("0.4.0", message)
        self.assertIn("0.9.0", message)

    def test_a_downgrade_needs_its_own_permission_not_force(self) -> None:
        """`--force` already means "write even when the bytes match". Letting
        it also mean "yes, go backwards" would make one flag answer two
        unrelated questions, and a caller who wanted a redundant rewrite
        would get a version rollback with it."""
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        self._kit_at(tmp_path, "0.9.0")
        upgrade_module.upgrade(workspace)

        self._kit_at(tmp_path, "0.4.0")
        with self.assertRaises(UserError):
            upgrade_module.upgrade(workspace, force=True)

        result = upgrade_module.upgrade(workspace, allow_downgrade=True)
        assert result["version"] == "0.4.0"

    def test_the_same_version_is_not_a_downgrade(self) -> None:
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        self._kit_at(tmp_path, "0.9.0")
        upgrade_module.upgrade(workspace)
        result = upgrade_module.upgrade(workspace)
        assert result["version"] == "0.9.0"

    def test_a_workspace_with_no_recorded_version_is_never_a_downgrade(self) -> None:
        """A first upgrade has nothing to go backwards FROM, and refusing it
        would make the guard block the case it was never about."""
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        (workspace / ".papersmith" / "version").unlink(missing_ok=True)
        self._kit_at(tmp_path, "0.4.0")
        result = upgrade_module.upgrade(workspace)
        assert result["version"] == "0.4.0"

    def test_versions_that_cannot_be_ordered_refuse_rather_than_guess(self) -> None:
        """The guard's claim is that one version precedes another. When the
        recorded version carries no orderable number that claim cannot be
        made, and writing files under a relationship nobody established is
        the silent behaviour this whole change removes."""
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        (workspace / ".papersmith" / "version").write_text("nightly\n", encoding="utf-8")
        self._kit_at(tmp_path, "0.4.0")
        with self.assertRaises(UserError) as caught:
            upgrade_module.upgrade(workspace)
        self.assertIn("nightly", str(caught.exception))

    def test_force_reports_framework_writes_even_when_content_matches(self) -> None:
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        result = upgrade_module.upgrade(workspace, force=True)
        assert "skills/paper-ingestion/SKILL.md" in result["changed_files"]
        assert "sections/01-materials-and-methods.md" in result["changed_files"]

    def test_cli_routes_allow_downgrade_and_refuses_without_it(self) -> None:
        """A flag the parser declares and nothing carries to the function is
        an option that reads as available and does nothing. The sibling
        test above drives `--tools` and `--force` and never this one, so the
        routing was declared and unexercised."""
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        self._kit_at(tmp_path, "0.9.0")
        upgrade_module.upgrade(workspace)
        self._kit_at(tmp_path, "0.4.0")

        # The CLI reports a refusal as a non-zero exit, not a traceback, so
        # the visible contract is the code AND the workspace left untouched.
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            assert main(["upgrade", str(workspace)]) != 0
        assert (workspace / ".papersmith/version").read_text() == "0.9.0\n"
        assert "0.4.0" in stderr.getvalue()

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert main(["upgrade", str(workspace), "--allow-downgrade"]) == 0
        assert (workspace / ".papersmith/version").read_text() == "0.4.0\n"

    def test_cli_upgrade_routes_directory_and_flags(self) -> None:
        tmp_path = self.new_tmp()
        workspace = _workspace(tmp_path)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert main(["upgrade", str(workspace), "--tools", "claude,pi", "--force"]) == 0
        output = buffer.getvalue()
        assert "Upgraded papersmith workspace" in output
        assert config.load_workspace_config(workspace)["active_tools"] == ["claude", "pi"]
