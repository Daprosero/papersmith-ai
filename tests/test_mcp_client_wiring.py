"""Integration: the wiring `print-config` emits actually drives a real client.

The other suites launch the server directly. This one starts from the snippet a
user is told to paste, resolves the same command, and then speaks the protocol
one message at a time -- so the documented wiring is what gets tested, and an
out-of-order or unsolicited response is a failure rather than a silent skip.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from mcp_client import MCPClient
from mcp_series import build_workspace, run_cli, scripts_env


@pytest.fixture(scope="module")
def workspace(tmp_path_factory) -> Path:
    return build_workspace(tmp_path_factory.mktemp("mcp-wiring"))


def _snippet(workspace: Path) -> dict:
    completed = run_cli("mcp", "print-config", "--workspace", str(workspace))
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)["mcpServers"]["papersmith"]


def _argv(server: dict) -> list[str]:
    """Resolve the snippet's command, keeping its arguments exactly as written."""
    found = shutil.which(server["command"])
    if found:
        return [found, *server["args"]]
    sibling = Path(sys.executable).parent / server["command"]
    if sibling.exists():
        return [str(sibling), *server["args"]]
    return [sys.executable, "-m", "papersmith.cli", *server["args"]]


def test_print_config_names_the_serve_command_for_the_bound_workspace(workspace: Path) -> None:
    server = _snippet(workspace)
    assert server["command"] == "papersmith"
    assert server["args"] == ["mcp", "serve", "--workspace", str(workspace)]


def test_the_wired_command_completes_a_full_client_session(workspace: Path) -> None:
    server = _snippet(workspace)
    client = MCPClient(_argv(server), cwd=workspace, env=scripts_env())
    try:
        initialized = client.result(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "wiring-test", "version": "1.0.0"},
            },
        )
        assert initialized["protocolVersion"] == "2025-11-25"
        assert initialized["serverInfo"]["name"] == "papersmith"

        client.notify("notifications/initialized")

        discover = client.result("server/discover", {})
        assert discover["resultType"] == "complete"
        assert discover["supportedVersions"]

        tools = client.result("tools/list", {})
        names = {tool["name"] for tool in tools["tools"]}
        assert {"papersmith.workspace_status", "papersmith.paper_validate"} <= names

        resources = client.result("resources/list", {})
        uris = {entry["uri"] for entry in resources["resources"]}
        assert "papersmith://workspace/status" in uris

        contents = client.read_resource("papersmith://workspace/status")["contents"][0]
        assert contents["mimeType"] == "application/json"
        assert json.loads(contents["text"])["workspace"]

        status = client.call_tool("papersmith.workspace_status")
        assert status["isError"] is False
        assert status["structuredContent"]["workspace"]

        assert client.unsolicited == []
    finally:
        returncode = client.close()

    assert returncode == 0
    assert client.stderr_text() == ""


def test_a_notification_is_never_answered_and_an_error_does_not_kill_the_session(
    workspace: Path,
) -> None:
    server = _snippet(workspace)
    client = MCPClient(_argv(server), cwd=workspace, env=scripts_env())
    try:
        client.notify("notifications/initialized")
        # If the notification had been answered, `request` would read that
        # response first and fail on the id mismatch.
        assert client.result("ping") == {}

        failure = client.request("does/not/exist")
        assert failure["error"]["code"] == -32601

        # The transport survives a bad call.
        assert client.result("ping") == {}
        assert client.unsolicited == []
    finally:
        client.close()


def test_the_client_rejects_a_stray_response(tmp_path: Path) -> None:
    """Prove the client's ordering guard is load-bearing.

    A fake server that answers a notification with a response -- exactly what
    the real server must never do -- has to make the client fail.
    """
    code = (
        "import sys, json\n"
        "for line in sys.stdin:\n"
        "    message = json.loads(line)\n"
        "    stray = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'stray'}}\n"
        "    sys.stdout.write(json.dumps(stray) + '\\n')\n"
        "    sys.stdout.flush()\n"
    )
    client = MCPClient([sys.executable, "-c", code], cwd=tmp_path, env=scripts_env())
    try:
        client.notify("notifications/initialized")
        with pytest.raises(AssertionError, match="arrived while waiting"):
            client.request("ping")
    finally:
        client.close()


def test_tools_list_and_resources_list_match_the_inspect_catalog(workspace: Path) -> None:
    catalog = json.loads(run_cli("mcp", "inspect").stdout)
    server = _snippet(workspace)
    client = MCPClient(_argv(server), cwd=workspace, env=scripts_env())
    try:
        tools = client.result("tools/list")["tools"]
        resources = client.result("resources/list")["resources"]
    finally:
        client.close()

    # `mcp inspect` is what docs are generated from, so it must describe the
    # live server exactly -- names, order included.
    assert [tool["name"] for tool in tools] == [tool["name"] for tool in catalog["tools"]]
    assert [entry["uri"] for entry in resources] == [
        entry["uri"] for entry in catalog["resources"]
    ]
