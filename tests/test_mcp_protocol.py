"""MCP protocol conformance: framing, revision negotiation, dispatch."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from papersmith.mcp import protocol
from papersmith.mcp.server import Server, catalog


def _server(workspace: Path) -> Server:
    return Server(workspace, out=io.StringIO(), err=io.StringIO())


def test_encode_never_emits_a_newline() -> None:
    assert "\n" not in protocol.encode({"text": "line one\nline two"})


def test_decode_rejects_a_non_jsonrpc_message() -> None:
    with pytest.raises(protocol.ProtocolError) as exc:
        protocol.decode('{"id": 1, "method": "ping"}')
    assert exc.value.code == protocol.INVALID_REQUEST


def test_decode_reports_a_parse_error() -> None:
    with pytest.raises(protocol.ProtocolError) as exc:
        protocol.decode("{not json")
    assert exc.value.code == protocol.PARSE_ERROR


def test_negotiate_defaults_to_the_pinned_revision() -> None:
    assert protocol.negotiate({}) == protocol.PROTOCOL_REVISION


def test_negotiate_accepts_the_previous_revision() -> None:
    assert protocol.negotiate({"protocolVersion": "2025-11-25"}) == "2025-11-25"


def test_negotiate_reads_per_request_meta() -> None:
    params = {"_meta": {protocol.META_PROTOCOL_VERSION: "2026-07-28"}}
    assert protocol.negotiate(params) == "2026-07-28"


def test_unsupported_revision_is_refused_with_the_supported_list() -> None:
    with pytest.raises(protocol.ProtocolError) as exc:
        protocol.negotiate({"protocolVersion": "1900-01-01"})
    assert exc.value.code == protocol.UNSUPPORTED_PROTOCOL_VERSION
    assert exc.value.data == {
        "supported": list(protocol.SUPPORTED_REVISIONS),
        "requested": "1900-01-01",
    }


def test_discover_result_shape(tmp_path: Path) -> None:
    response = _server(tmp_path).handle(
        {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}}
    )
    assert response is not None
    result = response["result"]
    assert result["resultType"] == "complete"
    assert result["supportedVersions"] == list(protocol.SUPPORTED_REVISIONS)
    assert result["capabilities"] == {"tools": {}, "resources": {}}
    assert result["_meta"][protocol.META_SERVER_INFO]["name"] == "papersmith"
    assert result["cacheScope"] == "public"


def test_unsupported_version_answers_with_a_jsonrpc_error(tmp_path: Path) -> None:
    response = _server(tmp_path).handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "server/discover",
            "params": {"protocolVersion": "1900-01-01"},
        }
    )
    assert response is not None
    assert response["error"]["code"] == protocol.UNSUPPORTED_PROTOCOL_VERSION
    assert response["error"]["data"]["requested"] == "1900-01-01"


def test_initialize_echoes_the_negotiated_revision(tmp_path: Path) -> None:
    response = _server(tmp_path).handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        }
    )
    assert response is not None
    assert response["result"]["protocolVersion"] == "2025-11-25"
    assert response["result"]["serverInfo"]["name"] == "papersmith"


def test_unknown_method_is_method_not_found(tmp_path: Path) -> None:
    response = _server(tmp_path).handle(
        {"jsonrpc": "2.0", "id": 2, "method": "does/not/exist", "params": {}}
    )
    assert response is not None
    assert response["error"]["code"] == protocol.METHOD_NOT_FOUND


def test_notifications_get_no_response(tmp_path: Path) -> None:
    assert _server(tmp_path).handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ) is None
    assert _server(tmp_path).handle(
        {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}
    ) is None


def test_serve_loop_frames_one_response_per_request(tmp_path: Path) -> None:
    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}) + "\n"
    )
    out = io.StringIO()
    assert _server(tmp_path).serve(stdin, out) == 0
    message = json.loads(out.getvalue().strip())
    assert message["id"] == 1
    assert message["result"] == {}


def test_serve_loop_answers_a_parse_error_without_dying(tmp_path: Path) -> None:
    stdin = io.StringIO(
        "not json\n"
        + json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        + "\n"
    )
    out = io.StringIO()
    _server(tmp_path).serve(stdin, out)
    lines = out.getvalue().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)
    assert json.loads(lines[0])["error"]["code"] == protocol.PARSE_ERROR


def test_catalog_reports_the_pinned_revision() -> None:
    data = catalog()
    assert data["protocol"]["revision"] == protocol.PROTOCOL_REVISION
    assert data["protocol"]["supported"] == list(protocol.SUPPORTED_REVISIONS)
    assert data["tools"]
    assert data["resources"]
