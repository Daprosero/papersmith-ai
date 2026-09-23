"""Mutation safety: the stdin refusal and the consent gates.

A non-dry `run` and a `remote push` spend real quota, so both are refused at
the MCP boundary unless a consent token is explicitly supplied. A `--body -`
would read the server's own stdin -- the JSON-RPC wire -- so it is refused for
every verb that accepts a body.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_series import build_workspace, call_many, tool_call

from papersmith.mcp import registry


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return build_workspace(tmp_path_factory.mktemp("mcp-mutation"))


def _code(response: dict) -> str:
    return response["result"]["structuredContent"]["code"]


@pytest.mark.parametrize(
    "name", ["papersmith.paper_substitute", "papersmith.paper_validate"]
)
def test_a_dash_body_is_refused_rather_than_read_from_the_wire(
    workspace: Path, name: str
) -> None:
    arguments = {"block": "intro", "body": "-"}
    responses = call_many(workspace, [tool_call(name, arguments)])
    assert responses[0]["result"]["isError"] is True
    assert _code(responses[0]) == "STDIN_NOT_AVAILABLE_OVER_MCP"


def test_a_non_dry_run_without_consent_is_refused(workspace: Path) -> None:
    responses = call_many(
        workspace,
        [
            tool_call(
                "papersmith.run",
                {"profile": "smoke_and_invariants", "dry_run": False},
            )
        ],
    )
    assert responses[0]["result"]["isError"] is True
    assert _code(responses[0]) == "CONSENT_REQUIRED"


def test_remote_push_without_consent_is_refused(workspace: Path) -> None:
    responses = call_many(
        workspace,
        [
            tool_call(
                "papersmith.remote",
                {
                    "operation": "push",
                    "target": "kaggle-gpu-pool",
                    "entrypoint": "train.py",
                    "backend": "kaggle",
                },
            )
        ],
    )
    assert responses[0]["result"]["isError"] is True
    assert _code(responses[0]) == "CONSENT_REQUIRED"


def test_the_run_guard_allows_a_dry_run_and_a_consented_dispatch(tmp_path: Path) -> None:
    guard = registry._refuse_run_without_consent
    guard({"dry_run": True}, tmp_path)
    guard({}, tmp_path)  # planning is the MCP default
    guard({"dry_run": False, "consent": "token"}, tmp_path)


def test_the_remote_guard_blocks_only_push(tmp_path: Path) -> None:
    guard = registry._refuse_remote_push_without_consent
    guard({"operation": "status"}, tmp_path)
    guard({"operation": "pack"}, tmp_path)
    with pytest.raises(registry.ToolRefusal) as exc:
        guard({"operation": "push"}, tmp_path)
    assert exc.value.code == "CONSENT_REQUIRED"
    guard({"operation": "push", "consent": "token"}, tmp_path)


def test_scaffold_open_and_substitute_round_trip(tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path, name="round-trip")
    body = workspace / "intro.tex"
    body.write_text("An introduction.\n", encoding="utf-8")

    responses = call_many(
        workspace,
        [
            tool_call("papersmith.paper_scaffold", {}, 1),
            tool_call("papersmith.paper_open", {"block": "intro", "at_end": True}, 2),
            tool_call(
                "papersmith.paper_substitute", {"block": "intro", "body": str(body)}, 3
            ),
        ],
    )
    for index, response in enumerate(responses):
        assert response["result"]["isError"] is False, (index, response["result"])

    assert "An introduction." in (workspace / "paper" / "main.tex").read_text(
        encoding="utf-8"
    )
