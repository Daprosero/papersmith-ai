"""A real client handshake over stdio, start to finish."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_series import (
    build_workspace,
    call_many,
    request,
    resource_read,
    serve,
    tool_call,
)


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return build_workspace(tmp_path_factory.mktemp("mcp-e2e"))


def test_full_handshake_and_capability_discovery(workspace: Path) -> None:
    responses = call_many(
        workspace,
        [
            request("server/discover", {}, 1),
            request("tools/list", {}, 2),
            request("resources/list", {}, 3),
            resource_read("papersmith://workspace/status", 4),
        ],
    )
    assert responses[0]["result"]["resultType"] == "complete"
    assert responses[0]["result"]["supportedVersions"]
    tools = responses[1]["result"]["tools"]
    assert {tool["name"] for tool in tools} >= {
        "papersmith.workspace_status",
        "papersmith.paper_status",
    }
    uris = {entry["uri"] for entry in responses[2]["result"]["resources"]}
    assert uris >= {"papersmith://workspace/status", "papersmith://paper/blocks"}
    contents = responses[3]["result"]["contents"][0]
    assert contents["mimeType"] == "application/json"
    assert json.loads(contents["text"])["workspace"]


def test_workspace_defaults_to_the_process_directory(workspace: Path) -> None:
    responses, completed = serve(
        workspace, [tool_call("papersmith.workspace_status")], explicit_workspace=False
    )
    assert completed.returncode == 0
    assert responses[0]["result"]["isError"] is False


def test_the_server_exits_cleanly_when_stdin_closes(workspace: Path) -> None:
    _, completed = serve(workspace, [request("ping")])
    assert completed.returncode == 0
    assert completed.stderr == ""


def test_init_actually_creates_a_workspace_under_the_bound_root(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path, name="parent-ws")
    responses = call_many(
        workspace,
        [tool_call("papersmith.workspace_init", {"name": "child", "title": "Child"}, 1)],
    )
    assert responses[0]["result"]["isError"] is False
    assert (workspace / "child" / "papersmith.yaml").is_file()
    assert (workspace / "child" / ".papersmith" / "manifest.json").is_file()
