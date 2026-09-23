"""Error classification: each child keeps its own contract's vocabulary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import papersmith.mcp.server as server_module
from papersmith.mcp.bridge import ChildPlan, ChildResult, child_env, env_allowed, redact
from papersmith.mcp.registry import ToolSpec, tool_annotations


def _spec(
    surface: str,
    *,
    build=None,
    result_json: bool = False,
) -> ToolSpec:
    if build is None:
        build = lambda arguments, workspace: ChildPlan("cli", ("status",))  # noqa: E731
    return ToolSpec(
        name="papersmith.probe",
        title="Probe",
        description="probe",
        verb="status",
        surface=surface,
        annotations=tool_annotations(
            "Probe", read_only=True, destructive=False, open_world=False
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        build=build,
        result_json=result_json,
    )


def _stub(monkeypatch, result: ChildResult) -> None:
    monkeypatch.setattr(server_module, "run_plan", lambda plan, workspace: result)


@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [(1, "USER_ERROR"), (2, "SOURCE_ERROR"), (3, "DRIFT_ERROR"), (4, "EXECUTION_ERROR")],
)
def test_cli_child_keeps_the_orchestrator_exit_contract(
    monkeypatch, exit_code: int, expected: str
) -> None:
    _stub(monkeypatch, ChildResult([], exit_code, "", "boom"))
    result = server_module.execute_tool(_spec("cli"), {}, Path("/tmp"))
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == expected
    assert result["structuredContent"]["exit"] == exit_code


def test_skill_child_refusal_name_is_preserved_verbatim(monkeypatch) -> None:
    stdout = json.dumps(
        {"status": "refused", "code": "RESOLVER_UNREACHABLE", "detail": "no route"}
    )
    _stub(monkeypatch, ChildResult([], 2, stdout, ""))
    result = server_module.execute_tool(_spec("paper"), {}, Path("/tmp"))
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "RESOLVER_UNREACHABLE"
    assert result["structuredContent"]["mapped"] == "USER_ERROR"
    assert "RESOLVER_UNREACHABLE" in result["content"][0]["text"]
    assert "SOURCE_ERROR" not in json.dumps(result)


def test_skill_child_refusal_without_a_code_falls_back_to_user_error(monkeypatch) -> None:
    _stub(monkeypatch, ChildResult([], 2, "not json", ""))
    result = server_module.execute_tool(_spec("paper"), {}, Path("/tmp"))
    assert result["structuredContent"]["code"] == "USER_ERROR"


def test_success_returns_structured_content_when_the_child_emits_json(monkeypatch) -> None:
    _stub(monkeypatch, ChildResult([], 0, '{"status": "ok", "blocks": []}', ""))
    result = server_module.execute_tool(_spec("cli", result_json=True), {}, Path("/tmp"))
    assert result["isError"] is False
    assert result["structuredContent"] == {"status": "ok", "blocks": []}


def test_timeout_is_reported_as_a_timeout_not_a_success(monkeypatch) -> None:
    _stub(monkeypatch, ChildResult([], 124, "", "", timed_out=True))
    result = server_module.execute_tool(_spec("cli"), {}, Path("/tmp"))
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "TIMEOUT"


def test_a_tool_refusal_never_spawns_a_child(monkeypatch) -> None:
    from papersmith.mcp.registry import ToolRefusal

    def explode(arguments, workspace):
        raise ToolRefusal("WORKSPACE_ESCAPE", "nope")

    def forbidden(plan, workspace):  # pragma: no cover - must never run
        raise AssertionError("a refused tool must not spawn a child")

    monkeypatch.setattr(server_module, "run_plan", forbidden)
    result = server_module.execute_tool(_spec("cli", build=explode), {}, Path("/tmp"))
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "WORKSPACE_ESCAPE"


def test_redaction_strips_consent_operands_and_token_pairs() -> None:
    text = 'run --consent s3cr3t-token\n{"api_key": "deadbeef", "name": "keep"}'
    cleaned = redact(text)
    assert "s3cr3t-token" not in cleaned
    assert "deadbeef" not in cleaned
    assert "--consent <redacted>" in cleaned
    assert "keep" in cleaned


def test_redaction_keeps_sha256_digests_readable() -> None:
    digest = "a" * 64
    assert digest in redact(f"block digest {digest}")


def test_deny_wins_over_the_allow_prefix() -> None:
    assert env_allowed("PAPERSMITH_TOKEN") is False
    assert env_allowed("PAPERSMITH_KIT_ROOT") is True
    assert env_allowed("KAGGLE_API_TOKEN") is False
    assert env_allowed("AWS_PROFILE") is False
    assert env_allowed("PATH") is True


def test_child_env_drops_tokens_even_when_an_allow_prefix_matches() -> None:
    source = {
        "PATH": "/bin",
        "HOME": "/home/tester",
        "KAGGLE_API_TOKEN": "kaggle-secret",
        "PAPERSMITH_TOKEN": "papersmith-secret",
        "PAPERSMITH_KIT_ROOT": "/kit",
    }
    assert child_env(source) == {
        "PATH": "/bin",
        "HOME": "/home/tester",
        "PAPERSMITH_KIT_ROOT": "/kit",
    }
