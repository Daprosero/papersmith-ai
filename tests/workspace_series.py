"""Shared fixtures for the from-scratch workspace e2e series.

Every module in the series begins by generating a workspace with the real
``papersmith init`` command, so what the tests exercise is the product a user
receives, never the repository's own checkout. Boundaries are faked the same
way the paper journey does it (see ``test_cli_paper_e2e.py``): stubbed
download/extract, a symlinked ``node_modules`` instead of ``npm install``, a
demo git target instead of notebook execution, and no network anywhere.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from papersmith.cli import main
from papersmith.core import ingest as ingest_module

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PDF = REPO_ROOT / "tests" / "fixtures" / "e2e" / "paper.pdf"
CANNED_MD = REPO_ROOT / "tests" / "fixtures" / "research-concept-r01.md"

# Minimal 1x1 transparent PNG (68 bytes) for the stubbed figure file.
FAKE_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def make_workspace(base: Path, name: str = "series-ws", *, remote: str = "local",
                   title: str = "Series Paper", topic: str = "series testing") -> Path:
    """Generate a workspace through the real CLI and return its path."""
    workspace = Path(base) / name
    rc = main(
        [
            "init",
            str(workspace),
            "--title",
            title,
            "--topic",
            topic,
            "--remote",
            remote,
            "--no-npm",
        ]
    )
    assert rc == 0, f"init failed with exit {rc}"
    return workspace


def capture(args) -> tuple[int, str, str]:
    """Run ``main(args)`` in-process and return ``(rc, stdout, stderr)``."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(args))
    return rc, out.getvalue(), err.getvalue()


def link_node_modules(workspace: Path) -> Path:
    """Symlink the prebuilt root install into the workspace (no npm install)."""
    src = REPO_ROOT / "node_modules"
    dst = workspace / "node_modules"
    if dst.is_symlink() or dst.exists():
        return dst
    if src.is_dir():
        dst.symlink_to(src, target_is_directory=True)
    return dst


@contextlib.contextmanager
def stub_extract():
    """Stub download + Marker extract: the canned ``.md`` plus one figure.

    Patches ``papersmith.core.ingest._download`` (no network) and
    ``papersmith.core.ingest.run_script`` (no Marker/surya weights).
    """
    canned_text = CANNED_MD.read_text(encoding="utf-8")

    def _fake_download(url: str, destination: Path) -> None:
        Path(destination).write_bytes(b"%PDF-1.4 stub\n%%EOF\n")

    def _fake_run(root, script, args, **kwargs):
        root = Path(root)
        slug = Path(args[0]).stem
        paper_dir = root / "guidance" / "reference-papers" / slug
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / f"{slug}.md").write_text(canned_text, encoding="utf-8")
        (paper_dir / "_page_1_Figure_1.png").write_bytes(FAKE_PNG)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="ingested\n", stderr="")

    with (
        mock.patch.object(ingest_module, "_download", side_effect=_fake_download),
        mock.patch.object(ingest_module, "run_script", side_effect=_fake_run),
    ):
        yield


def make_demo_target(workspace: Path, name: str = "demo") -> Path:
    """Create a minimal git-backed implementation target for probe/verify."""
    target = workspace / "implementations" / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["src"]\n', encoding="utf-8"
    )
    (target / "README.md").write_text("# Demo target\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    subprocess.run(["git", "-C", str(target), "config", "user.email", "series@test.com"], check=True)
    subprocess.run(["git", "-C", str(target), "config", "user.name", "series"], check=True)
    subprocess.run(["git", "-C", str(target), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(target), "commit", "-qm", "init demo target"], check=True)
    return target


#: Domain-profile overrides are a deliberate launcher feature; a suite that
#: drives the *shipped* defaults must not inherit another module's ambient
#: override (``test_implementation_domain_mutation`` sets one at import time).
PROFILE_OVERRIDES = ("IMPLEMENTATION_DOMAIN_PROFILE", "DELIBERATION_DOMAIN_PROFILE")


def run_workspace_script(workspace: Path, script: str, args: list[str], *,
                         timeout: float = 60) -> subprocess.CompletedProcess[str]:
    """Run a workspace-relative skill script with the current interpreter."""
    path = workspace / script
    assert path.is_file(), f"missing workspace script: {path}"
    env = {key: value for key, value in os.environ.items()
           if key not in PROFILE_OVERRIDES}
    return subprocess.run(
        [sys.executable, str(path), *args],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_node(script: Path, request: str, *, workspace: Path,
             timeout: float = 120) -> subprocess.CompletedProcess[str]:
    """Run a workspace node entry point with a keyless, domain-pinned environment."""
    node = shutil.which("node")
    assert node, "node is required for this leg; install Node.js >= 20"
    env = {key: value for key, value in os.environ.items()
           if key not in PROFILE_OVERRIDES and "ANTHROPIC" not in key
           and "OPENAI" not in key}
    env["PROPOSAL_DELIBERATION_PROJECT_ROOT"] = str(workspace)
    return subprocess.run(
        [node, str(script), request],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def new_tmp(case) -> Path:
    """Temporary directory owned by a ``unittest.TestCase``."""
    holder = tempfile.TemporaryDirectory()
    case.addCleanup(holder.cleanup)
    return Path(holder.name)
