"""Typed failures mapped onto the papersmith exit-code contract."""

from __future__ import annotations

from .core.exit_codes import DRIFT_ERROR, EXECUTION_ERROR, SOURCE_ERROR, USER_ERROR


class PapersmithError(Exception):
    """Base failure; subclasses carry the exit code the CLI must return."""

    exit_code = USER_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UserError(PapersmithError):
    exit_code = USER_ERROR


class SourceError(PapersmithError):
    exit_code = SOURCE_ERROR


class DriftError(PapersmithError):
    exit_code = DRIFT_ERROR


class ExecutionError(PapersmithError):
    exit_code = EXECUTION_ERROR
