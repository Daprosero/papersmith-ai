"""WU-7: the MCP documentation is checked against `mcp inspect`.

`mcp inspect` is what the docs are checked against, and the wiring test proves
`inspect` still describes the live server, so a doc that drifts from the tool
surface fails here rather than misinforming a reader.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mcp_series import REPO_ROOT, run_cli

DOC = REPO_ROOT / "docs" / "mcp.md"

#: Named in the document as deliberately NOT exposed, so not tools at all.
DEFERRED_NON_TOOLS = {"papersmith.paper_resolve", "papersmith.paper_render"}

#: Backticked `papersmith.*` tokens that name a file, not a tool.
NON_TOOL_TOKENS = {"papersmith.yaml"}


@pytest.fixture(scope="module")
def text() -> str:
    assert DOC.is_file(), f"missing {DOC}"
    return DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def catalog() -> dict:
    completed = run_cli("mcp", "inspect")
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _json_blocks(text: str) -> list[dict]:
    return [
        json.loads(raw) for raw in re.findall(r"```jsonc?\n(.*?)```", text, re.S)
    ]


def test_every_exposed_tool_is_documented_and_only_deferred_names_are_extra(
    text: str, catalog: dict
) -> None:
    documented = set(re.findall(r"`(papersmith\.[a-z_]+)`", text)) - NON_TOOL_TOKENS
    exposed = {tool["name"] for tool in catalog["tools"]}
    assert exposed <= documented, sorted(exposed - documented)
    assert documented - DEFERRED_NON_TOOLS == exposed, sorted(documented - exposed)
    assert not (exposed & DEFERRED_NON_TOOLS)


def test_every_resource_uri_is_documented(text: str, catalog: dict) -> None:
    documented = set(re.findall(r"`(papersmith://[a-z/]+)`", text))
    expected = {entry["uri"] for entry in catalog["resources"]}
    assert documented == expected, sorted(expected ^ documented)


def test_the_documented_claude_block_matches_print_config(tmp_path: Path) -> None:
    snippet = json.loads(
        run_cli("mcp", "print-config", "--workspace", str(tmp_path)).stdout
    )
    expected = snippet["mcpServers"]["papersmith"]
    blocks = [block for block in _json_blocks(DOC.read_text(encoding="utf-8")) if "mcpServers" in block]
    assert blocks, "the document must show the Claude Code wiring"
    server = blocks[0]["mcpServers"]["papersmith"]
    assert server["command"] == expected["command"]
    assert server["args"][:3] == expected["args"][:3] == ["mcp", "serve", "--workspace"]


def test_the_documented_opencode_block_is_a_local_command(text: str) -> None:
    blocks = [
        block
        for block in _json_blocks(text)
        if "mcp" in block and "mcpServers" not in block
    ]
    assert blocks, "the document must show the OpenCode wiring"
    server = blocks[0]["mcp"]["papersmith"]
    assert server["type"] == "local"
    assert server["command"][:3] == ["papersmith", "mcp", "serve"]


def test_the_document_states_the_pinned_revision_and_its_refusal(text: str) -> None:
    assert "2026-07-28" in text
    assert "2025-11-25" in text
    assert "-32022" in text
