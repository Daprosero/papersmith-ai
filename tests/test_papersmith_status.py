"""Status snapshots remain useful before optional runtimes are installed."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from papersmith.cli import main
from papersmith.core import init as init_module
from papersmith.core import status as status_module


class StatusTests(unittest.TestCase):
    def new_tmp(self) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        return Path(holder.name)

    def test_status_json_reports_versions_and_workspace_inventory(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "status-paper"
        init_module.initialize(workspace, run_npm=False)
        (workspace / "implementations" / "toy" / "tests").mkdir(parents=True)
        (workspace / "implementations" / "toy" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (workspace / "implementations" / "toy" / "tests" / "test_one.py").write_text("", encoding="utf-8")
        (workspace / "kaggle-inbox" / "job-1").mkdir()
        (workspace / "kaggle-inbox" / "job-1" / "metrics.json").write_text("{}", encoding="utf-8")

        snapshot = status_module.status(workspace)

        assert snapshot["project_name"] == "status-paper"
        assert snapshot["framework"]["version_match"] is True
        assert snapshot["framework"]["drifted_files"] == []
        assert snapshot["proposal"]["revision_id"] is None
        assert snapshot["implementations"] == [{
            "name": "toy",
            "path": "implementations/toy",
            "has_pyproject": True,
            "has_src": False,
            "test_files": 1,
        }]
        assert snapshot["inbox"] == {"files": 1, "job_directories": 1}

    def test_status_cli_json_is_machine_readable(self) -> None:
        tmp_path = self.new_tmp()
        workspace = tmp_path / "status-paper"
        init_module.initialize(workspace, run_npm=False)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert main(["status", str(workspace), "--json"]) == 0
        output = json.loads(buffer.getvalue())
        assert output["project_name"] == "status-paper"
