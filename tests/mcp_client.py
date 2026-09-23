"""A real, bidirectional MCP client for the integration tests.

``mcp_series.serve`` batches every message onto stdin and reads stdout only at
exit. That is enough for conformance but it cannot catch an out-of-order or
unsolicited response, because nothing is matched against anything.

This client writes one message, then reads until the response carrying *that*
id arrives. A response for an id it did not ask for is a hard failure, and
responses to notifications are failures too -- the two mistakes a
fire-and-forget harness silently swallows.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


class MCPClient:
    def __init__(self, argv: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        self._stderr = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        self._process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            text=True,
            bufsize=1,
        )
        self._next_id = 0
        #: Responses that arrived with no outstanding request (should stay empty).
        self.unsolicited: list[dict] = []

    # -- lifecycle --------------------------------------------------------- #

    def __enter__(self) -> "MCPClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> int:
        if self._process.stdin is not None and not self._process.stdin.closed:
            self._process.stdin.close()
        try:
            return self._process.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            self._process.kill()
            return self._process.wait()

    # -- protocol ---------------------------------------------------------- #

    def notify(self, method: str, params: dict | None = None) -> None:
        message: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        request_id = self._next_id
        message: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)
        while True:
            reply = self._read()
            if "id" not in reply:
                # A notification from the server is fine; nothing else is.
                continue
            if reply.get("id") != request_id:
                raise AssertionError(
                    f"response {reply.get('id')!r} arrived while waiting for {request_id!r}: {reply}"
                )
            return reply

    def result(self, method: str, params: dict | None = None) -> dict:
        reply = self.request(method, params)
        assert "error" not in reply, reply["error"]
        return reply["result"]

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return self.result(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )

    def read_resource(self, uri: str) -> dict:
        return self.result("resources/read", {"uri": uri})

    def stderr_text(self) -> str:
        self._stderr.flush()
        position = self._stderr.tell()
        self._stderr.seek(0)
        text = self._stderr.read()
        self._stderr.seek(position)
        return text

    # -- transport --------------------------------------------------------- #

    def _write(self, message: dict) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def _read(self) -> dict:
        assert self._process.stdout is not None
        line = self._process.stdout.readline()
        if line == "":
            raise AssertionError(
                f"server closed stdout early; stderr was:\n{self.stderr_text()}"
            )
        return json.loads(line)
