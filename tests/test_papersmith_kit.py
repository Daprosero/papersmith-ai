"""Kit resolution, framework-file filtering, and the preservation contract."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith import __version__
from papersmith.core import manifest
from papersmith.errors import SourceError
from papersmith.kit import resolve_and_validate, resolve_kit_root, validate_kit_root


def _write_tree(root: Path, spec: dict[str, str]) -> Path:
    for rel, content in spec.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


def _make_checkout(tmp_path: Path) -> Path:
    return _write_tree(
        tmp_path / "checkout",
        {
            "skills/paper-ingestion/SKILL.md": "# ingestion\n",
            "skills/kaggle-accounts/SKILL.md": "# accounts\n",
            "skills/kaggle-accounts/store/accounts.json": '{"secret": true}\n',
            "skills/kaggle-accounts/store/.gitignore": "*\n",
            "skills/paper-ingestion/.venv/pyvenv.cfg": "junk\n",
            "skills/paper-ingestion/__pycache__/mod.pyc": "junk\n",
            "skills/paper-ingestion/.hidden.md": "junk\n",
            "scripts/setup_env.py": "# env\n",
            "scripts/setup-harnesses.sh": "#!/usr/bin/env bash\n",
            "CLAUDE.md": "# claude\n",
            "guidance/paper-guide/venue.md": "# venue\n",
            ".claude/agents/paper-ingestion.md": "# agent\n",
            "package.json": '{"version": "0.1.0"}\n',
            "requirements.txt": "kagglesdk==0.1.37\n",
        },
    )


class KitTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name)

    def set_env(self, name: str, value: str) -> None:
        patcher = mock.patch.dict(os.environ, {name: value})
        patcher.start()
        self.addCleanup(patcher.stop)

    def clear_env(self, name: str) -> None:
        had = name in os.environ
        old = os.environ.pop(name, None)
        def restore():
            if had:
                os.environ[name] = old
            else:
                os.environ.pop(name, None)
        self.addCleanup(restore)

    def test_env_override_wins(self) -> None:
        tmp_path = self.new_tmp()
        checkout = _make_checkout(tmp_path)
        self.set_env("PAPERSMITH_KIT_ROOT", str(checkout))
        resolved = resolve_kit_root(start_file=tmp_path / "elsewhere" / "pkg" / "kit.py")
        assert resolved == checkout

    def test_dev_checkout_detection(self) -> None:
        tmp_path = self.new_tmp()
        checkout = _make_checkout(tmp_path)
        fake_module = checkout / "src" / "papersmith" / "kit.py"
        resolved = resolve_kit_root(start_file=fake_module)
        assert resolved == checkout

    def test_bundled_fallback(self) -> None:
        tmp_path = self.new_tmp()
        self.clear_env("PAPERSMITH_KIT_ROOT")
        fake_module = tmp_path / "site" / "papersmith" / "kit.py"
        resolved = resolve_kit_root(start_file=fake_module)
        assert resolved == tmp_path / "site" / "papersmith" / "_kit"

    def test_invalid_kit_root_refused(self) -> None:
        tmp_path = self.new_tmp()
        empty = tmp_path / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(SourceError, "no skills/"):
            validate_kit_root(empty)

    def test_resolve_and_validate_raises_on_bad_env(self) -> None:
        tmp_path = self.new_tmp()
        bad = tmp_path / "bad"
        bad.mkdir()
        self.set_env("PAPERSMITH_KIT_ROOT", str(bad))
        with self.assertRaises(SourceError):
            resolve_and_validate(start_file=tmp_path / "x" / "kit.py")

    def test_walk_kit_files_filters(self) -> None:
        tmp_path = self.new_tmp()
        checkout = _make_checkout(tmp_path)
        files = manifest.walk_kit_files(checkout)
        assert "skills/paper-ingestion/SKILL.md" in files
        assert "skills/kaggle-accounts/store/.gitignore" in files
        assert "skills/kaggle-accounts/store/accounts.json" not in files
        assert "skills/paper-ingestion/.venv/pyvenv.cfg" not in files
        assert "skills/paper-ingestion/__pycache__/mod.pyc" not in files
        assert "skills/paper-ingestion/.hidden.md" not in files
        assert "scripts/setup_env.py" in files
        assert "scripts/setup-harnesses.sh" in files
        assert "package.json" in files
        assert "requirements.txt" in files
        assert "guidance/paper-guide/venue.md" in files
        assert ".claude/agents/paper-ingestion.md" in files
        assert "CLAUDE.md" not in files  # rendered per workspace, not shipped raw

    def test_is_preserved(self) -> None:
        for relpath, preserved in [
            ("guidance/paper-guide/venue.md", True),
            ("guidance", True),
            ("proposals/drafts/x.md", True),
            ("implementations/foo/src/a.py", True),
            ("kaggle-inbox/job1/out.json", True),
            ("journal/2026-08.md", True),
            ("DECISIONS.md", True),
            ("papersmith.yaml", True),
            ("README.md", True),
            (".env", True),
            (".env.local", True),
            ("skills/paper-ingestion/SKILL.md", False),
            ("CLAUDE.md", False),
            ("scripts/setup_env.py", False),
            ("package.json", False),
            ("guidance2/x", False),
        ]:
            with self.subTest(relpath=relpath):
                assert manifest.is_preserved(relpath) is preserved

    def test_sha256_stable_and_distinct(self) -> None:
        tmp_path = self.new_tmp()
        file_a = tmp_path / "a.txt"
        file_a.write_text("same")
        file_b = tmp_path / "b.txt"
        file_b.write_text("same")
        file_c = tmp_path / "c.txt"
        file_c.write_text("different")
        assert manifest.sha256_file(file_a) == manifest.sha256_file(file_b)
        assert manifest.sha256_file(file_a) != manifest.sha256_file(file_c)
        assert manifest.sha256_file(file_a) == manifest.sha256_bytes(b"same")

    def test_kit_manifest_roundtrip(self) -> None:
        tmp_path = self.new_tmp()
        files = {"skills/a/SKILL.md": "hash-a", "package.json": "hash-b"}
        manifest.write_manifest(tmp_path, "1.2.3", files, kind="kit")
        path = tmp_path / "kit-manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["kind"] == "kit"
        assert data["version"] == "1.2.3"
        assert data["files"] == dict(sorted(files.items()))
        loaded = manifest.load_kit_manifest(tmp_path)
        assert loaded == data
        assert manifest.kit_version(tmp_path) == "1.2.3"
        assert manifest.kit_files(tmp_path) == files

    def test_kit_version_from_package_json(self) -> None:
        tmp_path = self.new_tmp()
        checkout = _make_checkout(tmp_path)
        assert manifest.kit_files(checkout)  # computed live, no kit-manifest
        assert manifest.kit_version(checkout) == "0.1.0"

    def test_corrupted_kit_manifest_refused(self) -> None:
        tmp_path = self.new_tmp()
        (tmp_path / "kit-manifest.json").write_text("{not json")
        from papersmith.errors import UserError

        with self.assertRaisesRegex(UserError, "corrupted kit manifest"):
            manifest.load_kit_manifest(tmp_path)

    def test_build_kit_end_to_end(self) -> None:
        """build-kit.py must assemble the bundled _kit from the real repo."""
        import subprocess
        import sys

        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "build-kit.py")],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        kit_dir = root / "src" / "papersmith" / "_kit"
        assert (kit_dir / "skills" / "paper-ingestion" / "SKILL.md").is_file()
        assert not (kit_dir / "skills" / "kaggle-accounts" / "store" / "accounts.json").exists()
        data = json.loads((kit_dir / "kit-manifest.json").read_text(encoding="utf-8"))
        assert data["kind"] == "kit"
        assert data["version"] == __version__
        assert "skills/skill-audit/scripts/audit_cli.py" in data["files"]
        assert "scripts/setup-harnesses.sh" in data["files"]
        assert (kit_dir / "scripts" / "setup-harnesses.sh").is_file()
        # every hashed file must exist and match its hash
        for relpath, digest in data["files"].items():
            assert (kit_dir / relpath).is_file(), relpath
            assert manifest.sha256_file(kit_dir / relpath) == digest, relpath
