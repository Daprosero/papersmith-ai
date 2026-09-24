"""Strict, deliberately small template rendering for workspace seed files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .core import fs
from .errors import UserError

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def render_template(text: str, context: dict[str, Any]) -> str:
    """Replace ``{{name}}`` placeholders and reject missing values."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise UserError(f"template placeholder has no value: {key}")
        return str(context[key])

    return _PLACEHOLDER.sub(replace, text)


def package_template_path(name: str) -> Path:
    path = Path(__file__).resolve().parent / "templates" / name
    if not fs.is_regular_file(path):
        raise UserError(f"missing papersmith template: {path}")
    return path


def render_package_template(name: str, context: dict[str, Any]) -> str:
    return render_template(package_template_path(name).read_text(encoding="utf-8"), context)
