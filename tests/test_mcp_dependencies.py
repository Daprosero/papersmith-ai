"""Success criterion #2: the MCP surface adds no runtime dependency."""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"


def test_pyproject_declares_no_runtime_dependencies() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []


def test_requirements_does_not_add_the_mcp_sdk() -> None:
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        assert not line.strip().lower().startswith("mcp")


def test_mcp_package_imports_only_the_stdlib_and_papersmith() -> None:
    for path in (SRC / "papersmith" / "mcp").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root in sys.stdlib_module_names, (path.name, root)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                root = (node.module or "").split(".")[0]
                assert root in sys.stdlib_module_names or root == "papersmith", (
                    path.name,
                    root,
                )
