"""MCP protocol layer for ``papersmith mcp serve``.

The transport is stdio: UTF-8 JSON-RPC 2.0, newline-delimited, one message per
line, no embedded newlines (MCP specification revision 2026-07-28). Revision
2025-11-25 is accepted for compatibility; any other requested revision is
refused with ``-32022`` carrying the supported list.

Nothing in this module — and nothing in the server package — may write to
stdout except the framing produced here.
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_REVISION = "2026-07-28"
SUPPORTED_REVISIONS: tuple[str, ...] = ("2026-07-28", "2025-11-25")

META_PREFIX = "io.modelcontextprotocol/"
META_PROTOCOL_VERSION = META_PREFIX + "protocolVersion"
META_CLIENT_INFO = META_PREFIX + "clientInfo"
META_CLIENT_CAPABILITIES = META_PREFIX + "clientCapabilities"
META_SERVER_INFO = META_PREFIX + "serverInfo"

# JSON-RPC 2.0 standard error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# MCP: unsupported protocol version.
UNSUPPORTED_PROTOCOL_VERSION = -32022

DISCOVER_CACHE_TTL_MS = 3_600_000
DISCOVER_CACHE_SCOPE = "public"


class ProtocolError(Exception):
    """A JSON-RPC error the transport must return to the peer."""

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def envelope(self, request_id: Any) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}


def encode(message: dict[str, Any]) -> str:
    """Serialize one message to a single newline-free line."""
    text = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    if "\n" in text or "\r" in text:
        raise ProtocolError(INTERNAL_ERROR, "encoded message contains a newline")
    return text


def decode(line: str) -> dict[str, Any]:
    """Parse one transport line into a JSON-RPC 2.0 message object."""
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(PARSE_ERROR, f"invalid JSON: {exc.msg}") from None
    if not isinstance(message, dict):
        raise ProtocolError(INVALID_REQUEST, "message must be a JSON object")
    if message.get("jsonrpc") != "2.0":
        raise ProtocolError(INVALID_REQUEST, 'jsonrpc must be "2.0"')
    return message


def success(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def requested_version(params: Any) -> str | None:
    """Read the peer's requested revision from ``_meta`` or ``initialize``."""
    if not isinstance(params, dict):
        return None
    meta = params.get("_meta")
    if isinstance(meta, dict) and isinstance(meta.get(META_PROTOCOL_VERSION), str):
        return meta[META_PROTOCOL_VERSION]
    if isinstance(params.get("protocolVersion"), str):
        return params["protocolVersion"]
    return None


def negotiate(params: Any) -> str:
    """Return the negotiated revision, or refuse an unsupported one."""
    requested = requested_version(params)
    if requested is None:
        return PROTOCOL_REVISION
    if requested in SUPPORTED_REVISIONS:
        return requested
    raise ProtocolError(
        UNSUPPORTED_PROTOCOL_VERSION,
        "Unsupported protocol version",
        {"supported": list(SUPPORTED_REVISIONS), "requested": requested},
    )


def server_info(name: str, version: str) -> dict[str, str]:
    return {"name": name, "version": version}


def discover_result(
    *, name: str, version: str, capabilities: dict[str, Any], instructions: str
) -> dict[str, Any]:
    return {
        "resultType": "complete",
        "supportedVersions": list(SUPPORTED_REVISIONS),
        "capabilities": capabilities,
        "_meta": {META_SERVER_INFO: server_info(name, version)},
        "instructions": instructions,
        "ttlMs": DISCOVER_CACHE_TTL_MS,
        "cacheScope": DISCOVER_CACHE_SCOPE,
    }


def initialize_result(
    *, revision: str, name: str, version: str, capabilities: dict[str, Any]
) -> dict[str, Any]:
    return {
        "protocolVersion": revision,
        "capabilities": capabilities,
        "serverInfo": server_info(name, version),
    }


def text_content(text: str) -> dict[str, str]:
    return {"type": "text", "text": text}


def tool_result(
    content: list[dict[str, Any]],
    *,
    structured: Any | None = None,
    is_error: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "resultType": "complete",
        "content": content,
        "isError": is_error,
    }
    if structured is not None:
        result["structuredContent"] = structured
    return result
