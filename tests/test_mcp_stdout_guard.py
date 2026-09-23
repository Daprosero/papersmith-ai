"""The stdout/stdin seam guard, and the mutation proof that it is load-bearing.

stdout carries the JSON-RPC wire, so a child must never inherit it, and stdin
must never be the wire either. If the capture or the ``DEVNULL`` is ever
dropped, these tests fail.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

from mcp_series import build_workspace, request, serve, tool_call

import papersmith.mcp.bridge as bridge


def test_spawn_closes_stdin_and_captures_both_streams(tmp_path: Path, monkeypatch) -> None:
    recorded: dict = {}

    def spy(*args, **kwargs):
        recorded.update(kwargs)
        return original(*args, **kwargs)

    original = subprocess.run
    monkeypatch.setattr(bridge.subprocess, "run", spy)
    bridge.spawn([sys.executable, "-c", "print('hello')"], cwd=tmp_path)

    assert recorded["stdin"] is subprocess.DEVNULL
    assert recorded["capture_output"] is True
    assert recorded["text"] is True


def test_child_stdout_cannot_reach_the_parent(tmp_path: Path) -> None:
    parent_stdout = io.StringIO()
    with contextlib.redirect_stdout(parent_stdout):
        result = bridge.spawn([sys.executable, "-c", "print('LEAK')"], cwd=tmp_path)
    assert "LEAK" in result.stdout
    assert parent_stdout.getvalue() == ""


def test_child_stdin_is_devnull_not_the_parent(tmp_path: Path) -> None:
    code = "import sys; print('eof' if sys.stdin.read() == '' else 'read')"
    result = bridge.spawn([sys.executable, "-c", code], cwd=tmp_path)
    assert result.stdout.strip() == "eof"


def test_children_do_not_litter_the_workspace_with_bytecode(tmp_path: Path) -> None:
    (tmp_path / "probe_module.py").write_text("VALUE = 1\n", encoding="utf-8")
    bridge.spawn([sys.executable, "-c", "import probe_module"], cwd=tmp_path)
    assert not (tmp_path / "__pycache__").exists()


def test_server_stdout_is_only_jsonrpc_even_when_children_print(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    responses, completed = serve(
        workspace,
        [request("tools/list"), tool_call("papersmith.paper_status", request_id=2)],
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert len(responses) == 2
    for line in completed.stdout.splitlines():
        if line.strip():
            json.loads(line)
