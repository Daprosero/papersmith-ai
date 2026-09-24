"""``papersmith mcp`` — serve, inspect, and print client configuration.

``serve`` owns stdout: the stdio transport *is* stdout, so this module prints
nothing on that path. ``inspect`` and ``print-config`` are ordinary CLI
commands whose stdout is their result.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..core import fs
from ..errors import UserError
from .server import Server, catalog


def _workspace(raw: str | None) -> Path:
    root = Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()
    if not fs.is_dir(root):
        raise UserError(f"workspace is not a directory: {root}")
    return root


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "mcp", help="serve PaperSmith over the Model Context Protocol"
    )
    commands = parser.add_subparsers(dest="mcp_command", required=True)

    serve = commands.add_parser("serve", help="run the stdio MCP server")
    serve.add_argument(
        "--workspace",
        default=None,
        help="bound workspace root; every tool resolves inside it (default: current directory)",
    )
    serve.add_argument("--transport", choices=("stdio",), default="stdio")
    serve.set_defaults(handler=run_serve)

    inspect = commands.add_parser("inspect", help="print the MCP capability catalog as JSON")
    inspect.set_defaults(handler=run_inspect)

    config = commands.add_parser(
        "print-config", help="print a copy-pasteable MCP client config snippet"
    )
    config.add_argument("--workspace", default=None)
    config.set_defaults(handler=run_print_config)


def run_serve(args) -> int:
    root = _workspace(args.workspace)
    return Server(root).serve()


def run_inspect(args) -> int:
    print(json.dumps(catalog(), indent=2, sort_keys=True))
    return 0


def run_print_config(args) -> int:
    root = _workspace(args.workspace)
    snippet = {
        "mcpServers": {
            "papersmith": {
                "command": "papersmith",
                "args": ["mcp", "serve", "--workspace", str(root)],
            }
        }
    }
    print(json.dumps(snippet, indent=2, sort_keys=True))
    return 0
