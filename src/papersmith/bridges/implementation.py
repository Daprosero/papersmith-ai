"""Bridge to proposal-implementation's real command surface."""

from __future__ import annotations

from pathlib import Path

from ..core.exit_codes import map_child_rc
from ..errors import UserError
from .python import emit_result, run_script

REAL_COMMANDS = {"env", "name", "plan", "apply", "admit", "handoff", "compose", "probe", "verify"}
ALIASES = {"materialize": "apply", "benchmark": "probe"}


def command_args(args) -> tuple[str, list[str]]:
    command = ALIASES.get(args.action, args.action)
    if command not in REAL_COMMANDS:
        raise UserError(f"unsupported implementation action: {args.action}")
    forwarded: list[str] = []
    if command == "name":
        if not args.name:
            raise UserError("implement name requires --name")
        forwarded = ["--name", args.name]
        return command, forwarded
    if not args.target:
        raise UserError(f"implement {args.action} requires --target")
    forwarded.extend(["--target", args.target])
    if command not in {"env", "compose"} and not args.name:
        raise UserError(f"implement {args.action} requires --name")
    if args.name and command != "compose":
        forwarded.extend(["--name", args.name])
    if args.python and command == "env":
        forwarded.extend(["--python", args.python])
    if args.plan and command == "apply":
        forwarded.extend(["--plan", args.plan])
    if command == "apply" and not args.plan:
        raise UserError("implement materialize/apply requires --plan")
    if args.finding and command == "compose":
        forwarded.extend(["--finding", args.finding])
    if args.entry_text and command == "compose":
        forwarded.extend(["--entry-text", args.entry_text])
    if command == "compose" and (not args.finding or args.entry_text is None):
        raise UserError("implement compose requires --finding and --entry-text")
    if args.shards and command == "verify":
        forwarded.extend(["--shards", args.shards])
    if args.revision and command in {"verify", "admit", "handoff", "probe"}:
        forwarded.extend(["--revision", args.revision])
    forwarded.extend(args.extra)
    return command, forwarded


def execute(workspace: str | Path, args) -> int:
    root = Path(workspace).expanduser().resolve()
    command, forwarded = command_args(args)
    result = run_script(
        root,
        "skills/proposal-implementation/scripts/implementation_cli.py",
        [command, *forwarded],
    )
    return emit_result(result)


def register(subparsers) -> None:
    parser = subparsers.add_parser("implement", help="bridge to proposal-implementation")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--action", required=True)
    parser.add_argument("--target", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--plan", default=None)
    parser.add_argument("--finding", default=None)
    parser.add_argument("--entry-text", default=None)
    parser.add_argument("--python", default=None)
    parser.add_argument("--shards", default=None)
    parser.add_argument("--revision", default=None)
    parser.add_argument("extra", nargs="*", help="additional implementation_cli arguments")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    return execute(args.directory, args)
