"""Path confinement and the fixed resource allowlist."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_series import build_workspace, call_many, resource_read, tool_call

from papersmith.mcp.resources import RESOURCES_BY_URI


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return build_workspace(tmp_path_factory.mktemp("mcp-confinement"))


def _code(response: dict) -> str:
    return response["result"]["structuredContent"]["code"]


def test_init_cannot_escape_with_a_relative_path(workspace: Path) -> None:
    responses = call_many(
        workspace, [tool_call("papersmith.workspace_init", {"name": "../escape"})]
    )
    assert responses[0]["result"]["isError"] is True
    assert _code(responses[0]) == "WORKSPACE_ESCAPE"


def test_init_cannot_escape_with_an_absolute_path(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    responses = call_many(
        workspace, [tool_call("papersmith.workspace_init", {"name": str(outside)})]
    )
    assert _code(responses[0]) == "WORKSPACE_ESCAPE"
    assert not outside.exists()


def test_ingest_refuses_a_source_outside_the_workspace(workspace: Path) -> None:
    responses = call_many(
        workspace, [tool_call("papersmith.ingest_add", {"source": "../../etc/passwd"})]
    )
    assert _code(responses[0]) == "WORKSPACE_ESCAPE"


def test_a_paper_path_flag_is_confined(workspace: Path) -> None:
    responses = call_many(
        workspace, [tool_call("papersmith.paper_status", {"paper": "/etc"})]
    )
    assert _code(responses[0]) == "WORKSPACE_ESCAPE"


def test_unknown_resource_is_refused(workspace: Path) -> None:
    responses = call_many(workspace, [resource_read("papersmith://workspace/../etc/passwd")])
    assert responses[0]["error"]["code"] == -32602
    assert responses[0]["error"]["data"]["code"] == "RESOURCE_UNKNOWN"


def test_the_resource_table_never_names_a_secret_location() -> None:
    uris = " ".join(RESOURCES_BY_URI)
    assert ".env" not in uris
    assert "kaggle" not in uris
    assert "store" not in uris
