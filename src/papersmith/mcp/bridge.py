"""The one process seam: every MCP call spawns a child with captured streams.

stdout is the JSON-RPC wire, so a child's stdout is never inherited; stdin is
``DEVNULL`` so a child can never read the wire either. The environment is an
allowlist with *deny-wins* precedence, so a token-shaped variable can never be
forwarded merely because a broader allow prefix matches it.

Token-shaped values are redacted before any child text reaches the wire. The
redaction is deliberately narrow — ``--consent`` operands and token-shaped
key/value pairs — because a "long base64/hex run" rule would silently destroy
the sha256 digests that are legitimate paper output.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..bridges.python import interpreter_for

DEFAULT_TIMEOUT = 120.0
INGEST_TIMEOUT = 3600.0
TIMEOUT_EXIT = 124
SPAWN_EXIT = 125
REDACTED = "<redacted>"

ALLOW_ENV_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "TERM",
        "SHELL",
        "USER",
        "LOGNAME",
        "PWD",
    }
)
ALLOW_ENV_PREFIXES = ("PAPERSMITH_", "DELIBERATION_", "LC_")
DENY_ENV_NAMES = frozenset({"AUTHORIZATION", "KAGGLE_USERNAME", "KAGGLE_KEY"})
DENY_ENV_PREFIXES = ("AWS_", "KAGGLE_")
DENY_ENV_SUFFIXES = (
    "_TOKEN",
    "_KEY",
    "_SECRET",
    "_PASSWORD",
    "_CREDENTIAL",
    "_CREDENTIALS",
)

_CONSENT_RE = re.compile(r"(?i)(--consent[=\s]+)(\S+)")
_TOKENKV_RE = re.compile(
    r"(?i)(\"?(?:token|api[_-]?key|secret|password|authorization|credential)\"?\s*[:=]\s*)(\"?)([^\s\",}]+)"
)


def env_allowed(name: str) -> bool:
    """True when ``name`` may be forwarded to a child. Deny wins over allow."""
    upper = name.upper()
    if upper in DENY_ENV_NAMES:
        return False
    if upper.startswith(DENY_ENV_PREFIXES):
        return False
    if upper.endswith(DENY_ENV_SUFFIXES):
        return False
    if name in ALLOW_ENV_NAMES or upper in ALLOW_ENV_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in ALLOW_ENV_PREFIXES)


def child_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    resolved: Mapping[str, str] = os.environ if source is None else source
    return {key: value for key, value in resolved.items() if env_allowed(key)}


def redact(text: str) -> str:
    """Strip consent operands and token-shaped pairs from child text."""
    if not text:
        return text
    text = _CONSENT_RE.sub(lambda match: match.group(1) + REDACTED, text)
    return _TOKENKV_RE.sub(lambda match: match.group(1) + match.group(2) + REDACTED, text)


@dataclass(frozen=True)
class ChildPlan:
    """A child to spawn: its surface kind, tokens, and timeout."""

    kind: str  # "cli" | "paper"
    tokens: tuple[str, ...]
    timeout: float | None = None


@dataclass
class ChildResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def command_for(plan: ChildPlan, workspace: Path) -> list[str]:
    """The full argv for a plan, including its interpreter."""
    if plan.kind == "cli":
        return [sys.executable, "-m", "papersmith.cli", *plan.tokens]
    if plan.kind == "paper":
        return [*interpreter_for(workspace), *plan.tokens]
    raise ValueError(f"unknown child kind {plan.kind!r}")


def spawn(argv: list[str], *, cwd: Path, timeout: float | None = None) -> ChildResult:
    """Run a child with captured streams and a closed stdin."""
    effective = DEFAULT_TIMEOUT if timeout is None else timeout
    env = child_env()
    # A read-only tool must not litter the user's workspace with bytecode.
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=effective,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _as_text(exc.stdout)
        stderr = _as_text(exc.stderr)
        return ChildResult(argv, TIMEOUT_EXIT, stdout, stderr, timed_out=True)
    except OSError as exc:
        return ChildResult(argv, SPAWN_EXIT, "", f"could not execute {argv[0]}: {exc}")
    return ChildResult(argv, completed.returncode, completed.stdout or "", completed.stderr or "")


def run_plan(plan: ChildPlan, workspace: Path) -> ChildResult:
    return spawn(command_for(plan, workspace), cwd=workspace, timeout=plan.timeout)


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)
