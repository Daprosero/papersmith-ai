"""Direct interface to the remote-execution skill's CLI."""

from __future__ import annotations

from pathlib import Path

from ..bridges.python import emit_result, run_script
from ..errors import UserError

OPERATION_MAP = {
    "pack": "generate-job",
    "push": "submit",
    "status": "status",
    "pull": "fetch",
    "sync": "reconcile",
}


def command_args(args) -> list[str]:
    operation = OPERATION_MAP.get(args.operation)
    if operation is None:
        raise UserError(f"unsupported remote operation: {args.operation}")
    forwarded = [operation]
    if operation == "generate-job":
        required = {
            "target": args.target,
            "service": args.service,
            "job-name": args.job_name or args.job,
            "product": args.product,
            "repo-url": args.repo_url,
            "repo-ref": args.repo_ref,
            "run-module": args.run_module,
            "run-function": args.run_function,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise UserError(f"remote pack requires: {', '.join('--' + item for item in missing)}")
        for key, value in required.items():
            forwarded.extend([f"--{key}", str(value)])
        for path in args.clone_path:
            forwarded.extend(["--clone-path", path])
        if args.commit:
            forwarded.extend(["--commit", args.commit])
        if args.regenerate:
            forwarded.append("--regenerate")
    elif operation == "submit":
        for key, value in (("target", args.target), ("entrypoint", args.entrypoint), ("backend", args.backend)):
            if not value:
                raise UserError(f"remote push requires --{key}")
            forwarded.extend([f"--{key}", str(value)])
        if args.account:
            forwarded.extend(["--worker", args.account])
        if args.consent:
            forwarded.extend(["--consent", args.consent])
        if args.smoke:
            forwarded.append("--smoke")
        for unit in args.unit:
            forwarded.extend(["--unit", unit])
    elif operation == "status":
        for key, value in (("target", args.target), ("entrypoint", args.entrypoint)):
            if not value:
                raise UserError(f"remote status requires --{key}")
            forwarded.extend([f"--{key}", str(value)])
    elif operation == "fetch":
        for key, value in (("target", args.target), ("entrypoint", args.entrypoint),
                           ("submission-id", args.job or args.submission_id), ("dest", args.dest),
                           ("backend", args.backend)):
            if not value:
                raise UserError(f"remote pull requires --{key}")
            forwarded.extend([f"--{key}", str(value)])
        if args.force:
            forwarded.append("--force")
    elif operation == "reconcile":
        for key, value in (("target", args.target), ("entrypoint", args.entrypoint),
                           ("worker", args.account), ("backend", args.backend)):
            if not value:
                raise UserError(f"remote sync requires --{key}")
            forwarded.extend([f"--{key}", str(value)])
        if args.resolve:
            forwarded.append("--resolve")
    forwarded.extend(args.extra)
    return forwarded


def execute(workspace: str | Path, args) -> int:
    root = Path(workspace).expanduser().resolve()
    command = command_args(args)
    result = run_script(
        root, "skills/remote-execution/scripts/remote_cli.py", command,
        prefer_micromamba=True,
    )
    return emit_result(result)


def register(subparsers) -> None:
    parser = subparsers.add_parser("remote", help="direct remote-execution interface")
    parser.add_argument("operation", choices=tuple(OPERATION_MAP))
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--target", default=None)
    parser.add_argument("--entrypoint", default=None)
    parser.add_argument("--backend", default=None)
    parser.add_argument("--account", default=None)
    parser.add_argument("--job", default=None)
    parser.add_argument("--submission-id", default=None)
    parser.add_argument("--dest", default=None)
    parser.add_argument("--consent", default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--unit", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resolve", action="store_true")
    parser.add_argument("--service", default=None)
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--product", default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--repo-url", default=None)
    parser.add_argument("--repo-ref", default=None)
    parser.add_argument("--run-module", default=None)
    parser.add_argument("--run-function", default=None)
    parser.add_argument("--clone-path", action="append", default=[])
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("extra", nargs="*")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    return execute(args.directory, args)
