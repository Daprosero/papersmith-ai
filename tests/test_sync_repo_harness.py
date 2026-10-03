"""`scripts/sync-repo-harness.py` projects generated surfaces into the checkout.

The script name carries a hyphen, so it is loaded by path. Every test except the
last redirects the script's ``ROOT`` and ``_render`` to a temporary directory, so
nothing here reads the operator's home directory or the real checkout; the last
one only runs the read-only ``--check`` against the real checkout and needs no
personal context either (it renders into a throwaway workspace).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sync-repo-harness.py"


def _load():
    spec = importlib.util.spec_from_file_location("sync_repo_harness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SyncRepoHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load()
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name).resolve()
        self.workspace = self.tmp / "workspace"
        self.checkout = self.tmp / "checkout"
        self.checkout.mkdir()

    def run_main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        render = mock.patch.object(self.module, "_render",
                                   lambda holder: (self.workspace, []))
        root = mock.patch.object(self.module, "ROOT", self.checkout)
        with render, root, contextlib.redirect_stdout(out):
            code = self.module.main(list(argv))
        return code, out.getvalue()

    def test_projection_includes_the_pi_agents_directory(self) -> None:
        assert (".pi/agents", ".pi/agents") in self.module.PROJECTION
        assert (".pi/extensions", ".pi/extensions") in self.module.PROJECTION

    def test_expected_maps_every_projected_directory_to_checkout_paths(self) -> None:
        _write(self.workspace / ".pi/agents/a.md", "agent")
        _write(self.workspace / ".pi/prompts/p.md", "prompt")
        _write(self.workspace / "unprojected/x.md", "ignored")
        expected = self.module._expected(self.workspace)
        assert expected == {".pi/agents/a.md": "agent", ".pi/prompts/p.md": "prompt"}

    def test_orphans_lists_checkout_files_the_render_no_longer_produces(self) -> None:
        _write(self.checkout / ".pi/agents/kept.md", "x")
        _write(self.checkout / ".pi/agents/stale.md", "x")
        _write(self.checkout / "unprojected/other.md", "x")
        with mock.patch.object(self.module, "ROOT", self.checkout):
            orphans = self.module._orphans({".pi/agents/kept.md": "x"})
        assert orphans == [".pi/agents/stale.md"]

    def test_check_exits_3_on_missing_changed_and_orphan_files(self) -> None:
        _write(self.workspace / ".pi/agents/a.md", "new")
        _write(self.workspace / ".pi/agents/b.md", "same")
        _write(self.checkout / ".pi/agents/b.md", "same")
        _write(self.checkout / ".pi/agents/stale.md", "x")
        code, output = self.run_main("--check")
        assert code == 3
        assert ".pi/agents/a.md" in output and ".pi/agents/stale.md" in output
        assert ".pi/agents/b.md" not in output
        assert not (self.checkout / ".pi/agents/a.md").exists(), "--check must not write"

    def test_check_exits_0_when_the_checkout_matches(self) -> None:
        _write(self.workspace / ".pi/agents/a.md", "same")
        _write(self.checkout / ".pi/agents/a.md", "same")
        code, output = self.run_main("--check")
        assert code == 0 and "clean" in output

    def test_real_checkout_projection_is_clean(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = self.module.main(["--check"])
        assert code == 0, out.getvalue()


if __name__ == "__main__":
    unittest.main()
