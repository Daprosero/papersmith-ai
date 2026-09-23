"""High-level aliases over the real proposal-deliberation operations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..core.exit_codes import EXECUTION_ERROR, SUCCESS, USER_ERROR
from ..errors import ExecutionError, PapersmithError, UserError
from .node import call_engine, call_engine_with_acceptance, run_engine_passthrough

ACTION_OPERATIONS = {
    "status": "STATUS",
    "resolve": "RESOLVE_TARGET",
    "plan": "RESOLVE_TARGET",
    "init": "CREATE_INITIAL_REVISION",
    "successor": "CREATE_SUCCESSOR",
    "materialize": "CREATE_SUCCESSOR",
    "withdraw": "WITHDRAW_REVISION",
    "restore": "RESTORE_WITHDRAWN_REVISION",
    "maintenance": "MAINTENANCE",
    "audit": "MAINTENANCE",
}
REAL_OPERATIONS = {
    "STATUS",
    "RESOLVE_TARGET",
    "WITHDRAW_REVISION",
    "RESTORE_WITHDRAWN_REVISION",
    "CREATE_SUCCESSOR",
    "CREATE_INITIAL_REVISION",
    "MAINTENANCE",
    "CHAT_DELIBERATION",
    "CLOSE_DELIBERATION",
}


def _json_file(path: str) -> Any:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UserError(f"invalid JSON request file {path}: {exc}") from None
    return value


def build_request(args) -> dict[str, Any]:
    if args.request is not None:
        try:
            request = json.loads(args.request)
        except json.JSONDecodeError as exc:
            raise UserError(f"--request is not valid JSON: {exc}") from None
        if not isinstance(request, dict):
            raise UserError("--request must contain a JSON object")
        return request
    if args.request_file is not None:
        request = _json_file(args.request_file)
        if not isinstance(request, dict):
            raise UserError("--request-file must contain a JSON object")
        return request
    if args.action is None:
        raise UserError("deliberate requires --action or --request")
    action = args.action
    operation = ACTION_OPERATIONS.get(action, action.upper())
    if operation not in REAL_OPERATIONS:
        raise UserError(f"unsupported deliberate action: {action}")
    request: dict[str, Any] = {"operation": operation}
    if args.instruction is not None:
        request["instruction"] = args.instruction
    elif operation not in {"STATUS", "RESOLVE_TARGET"}:
        raise UserError(f"--instruction is required for deliberate action {action}")
    if args.revision is not None:
        request["sourceFilename"] = args.revision
    if args.query:
        if len(args.query) == 1:
            request["query"] = args.query[0]
        else:
            request["queries"] = [{"query": query} for query in args.query]
    if args.selected_entry_id:
        if len(args.selected_entry_id) == 1:
            request["selectedEntryId"] = args.selected_entry_id[0]
        else:
            request["selectedEntryIds"] = list(args.selected_entry_id)
    if args.decisions is not None:
        decisions = _json_file(args.decisions)
        if not isinstance(decisions, list):
            raise UserError("--decisions must point to a JSON array")
        request["resolvedDecisions"] = decisions
    if args.accept:
        request["acceptSuccessor"] = True
    if args.acceptance_token is not None:
        request["successorAcceptanceToken"] = args.acceptance_token
    if args.withdrawal_operation_id is not None:
        request["withdrawalOperationId"] = args.withdrawal_operation_id
    if args.withdrawal_reason is not None:
        request["withdrawalReason"] = args.withdrawal_reason
    if args.prior_conclusion is not None:
        request["priorConclusion"] = args.prior_conclusion
    return request


def _response_code(responses: list[dict[str, Any]]) -> int:
    for response in responses:
        status = response.get("status")
        if status in {"error", "failed"}:
            return EXECUTION_ERROR
        if status in {"blocked", "ambiguous", "needs-clarification", "refused"}:
            return USER_ERROR
    return SUCCESS


def execute(workspace: str | Path, args) -> int:
    root = Path(workspace).expanduser().resolve()
    if args.serve:
        return run_engine_passthrough(root)
    request = build_request(args)
    operation = request.get("operation")
    if args.accept and operation == "CREATE_SUCCESSOR" and "successorAcceptanceToken" not in request:
        responses = call_engine_with_acceptance(root, request)
    else:
        responses = call_engine(root, [request])
    for response in responses:
        print(json.dumps(response, indent=2, sort_keys=True))
    return _response_code(responses)


def register(subparsers) -> None:
    parser = subparsers.add_parser("deliberate", help="bridge to the proposal deliberation engine")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--action", default=None, help="real operation or supported alias")
    parser.add_argument("--request", default=None, help="raw JSON request object")
    parser.add_argument("--request-file", default=None, help="file containing a raw JSON request object")
    parser.add_argument("--serve", action="store_true", help="run native persistent JSON-lines mode")
    parser.add_argument("--revision", default=None, help="managed source filename")
    parser.add_argument("--instruction", default=None)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--selected-entry-id", action="append", default=[])
    parser.add_argument("--decisions", default=None, help="JSON array of resolved edit decisions")
    parser.add_argument("--accept", action="store_true", help="accept a CREATE_SUCCESSOR preview")
    parser.add_argument("--acceptance-token", default=None)
    parser.add_argument("--withdrawal-operation-id", default=None)
    parser.add_argument("--withdrawal-reason", default=None)
    parser.add_argument("--prior-conclusion", default=None)
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    return execute(args.directory, args)
