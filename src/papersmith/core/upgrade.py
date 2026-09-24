"""Synchronize framework-owned files into an existing workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..errors import SourceError, UserError
from ..generators import (
    UNSYNCHRONIZED,
    apply_generated,
    context_for_workspace,
    read_workspace_version,
    render_files,
)
from ..kit import resolve_and_validate
from ..schema import validate_tools
from . import config, fs, manifest

#: Dynamic rendered outputs — one file per discovered skill, so their membership
#: cannot be enumerated by a static list. Only paths under these prefixes that
#: were previously baselined are ever removed (see :func:`_orphaned`).
DYNAMIC_PREFIXES = (".opencode/commands/", ".claude/commands/")


def _contained(relpath: str) -> bool:
    """True when a stored key is a plain workspace-relative path.

    The manifest is data, so anything that is not a normal relative path — an
    absolute key, a ``..`` segment, or a NUL byte — is refused before it can be
    joined and unlinked. This check is lexical and total: it cannot itself raise.
    """
    if not relpath or relpath.startswith("/") or "\x00" in relpath:
        return False
    return ".." not in relpath.split("/")


def _orphaned(root: Path, previous_managed: set[str], current_render: set[str]) -> list[str]:
    """Baselined dynamic paths that are no longer derivable.

    The exact predicate: a path qualifies only when it is in ``previous_managed``
    (the stored manifest — it was this tool's own output), it starts with a
    declared dynamic prefix, it is absent from ``current_render``, and it is a
    contained relative path inside ``root``.

    A file under those prefixes that was never baselined is deliberately
    preserved: it is not this tool's output, so deleting it would lose user data.
    Static entrypoints never match a prefix and are never removable here.

    A stored-manifest key is data, not a trusted path. It is validated lexically
    first and only then resolved, so a crafted key is refused rather than
    resolved: a symlink loop, a NUL byte or an out-of-workspace target can never
    turn ``upgrade`` into a file-deletion primitive.
    """
    anchor = root.resolve()
    eligible: list[str] = []
    for path in previous_managed:
        if not path.startswith(DYNAMIC_PREFIXES) or path in current_render:
            continue
        if not _contained(path):
            continue
        try:
            inside = (root / path).resolve().is_relative_to(anchor)
        except (OSError, ValueError, RuntimeError):
            inside = False
        if inside:
            eligible.append(path)
    return sorted(eligible)


def _copy_if_needed(workspace: Path, kit_root: Path, relpath: str, *, force: bool,
                    unsynchronized: list[str]) -> bool:
    """Synchronize one kit file; return whether it was written.

    A destination that cannot be written — a FIFO a copy would block on, a
    directory, an unsearchable parent — is appended to ``unsynchronized``
    instead of aborting a run that has already synchronized earlier files.
    """
    source = kit_root / relpath
    destination = workspace / relpath
    if not fs.is_regular_file(source):
        raise SourceError(f"kit manifest names a missing source file: {source}")
    if manifest.is_preserved(relpath):
        return False
    if not force:
        # A guarded hash, not a bare one: a regular file whose mode denies the
        # read makes ``sha256_file`` raise, and this runs inside the repair
        # command, after earlier kit files have already been written.
        current = manifest.sha256_if_readable(destination)
        if current is not None and current == manifest.sha256_if_readable(source):
            return False
    if not manifest.copy_kit_file(kit_root, relpath, workspace):
        unsynchronized.append(relpath)
        return False
    return True


def upgrade(workspace: str | Path = ".", *, tools: Sequence[str] | None = None,
            force: bool = False) -> dict:
    root = Path(workspace).expanduser().resolve()
    stored = manifest.load_manifest(root)
    if stored is None:
        raise UserError(f"not a papersmith workspace: missing {root / '.papersmith/manifest.json'}")

    kit_root = resolve_and_validate()
    kit_files = manifest.kit_files(kit_root)
    version = manifest.kit_version(kit_root)
    workspace_config = config.load_workspace_config(root)
    active_tools = validate_tools(list(tools) if tools is not None else workspace_config["active_tools"])
    changed: list[str] = []
    preserved: list[str] = []
    unsynchronized: list[str] = []

    for relpath in sorted(kit_files):
        if manifest.is_preserved(relpath):
            preserved.append(relpath)
            continue
        if _copy_if_needed(root, kit_root, relpath, force=force,
                           unsynchronized=unsynchronized):
            changed.append(relpath)

    if tools is not None:
        workspace_config["active_tools"] = active_tools
    workspace_config["updated_at"] = config.utc_timestamp()
    config.write_json(root / ".papersmith" / "config.json", workspace_config)

    # Rendered files are framework-owned projections. Context is read after
    # raw agent/config files have been synchronized so the new roster appears.
    context = context_for_workspace(root)
    generated = apply_generated(root, context, active_tools, skipped=unsynchronized)
    for relpath in generated:
        if relpath not in changed:
            changed.append(relpath)

    # Remove previously-baselined dynamic outputs that stopped being derivable
    # (a workspace-local skill that was removed or renamed). The baseline is the
    # stored manifest loaded at the top of this run, before this run rewrites it
    # below — reading it afterwards would compare the new baseline with itself
    # and find nothing.
    current_render = set(render_files(root, context, active_tools))
    deliverable = manifest.synchronized_paths(root, kit_root, context, active_tools)
    removed: list[str] = []
    stranded: list[str] = []
    for relpath in _orphaned(root, set(stored["files"]), current_render):
        target = root / relpath
        if not fs.exists(target):
            # Already gone. Nothing to delete and nothing to retry: recording it
            # as stranded would re-mark it on every run, and a marker the live
            # map can never show is drift that no upgrade can ever clear.
            removed.append(relpath)
            continue
        if not fs.is_regular_file(target):
            # Present but not something this run will delete — a directory, or a
            # FIFO the user left there. Reported and retried; removing it clears
            # the report.
            stranded.append(relpath)
            continue
        try:
            target.unlink()
        except OSError:
            # A read-only parent or a refusing filesystem must not abort the run
            # after the workspace has already been synchronized; the path is
            # reported below instead, and a later run retries it.
            stranded.append(relpath)
            continue
        removed.append(relpath)

    # The marker is a managed path like any other, so it takes the same gate on
    # both sides: reading a FIFO would block, and writing one would block too —
    # in the command whose whole job is to repair a damaged workspace.
    if read_workspace_version(root, "") != version:
        if fs.write_text(root / ".papersmith" / "version", version + "\n"):
            changed.append(".papersmith/version")
        else:
            unsynchronized.append(".papersmith/version")

    framework_files = manifest.workspace_framework_files(root, kit_root)
    for relpath in stranded:
        # Keep an undeletable path in the baseline. It is not part of the current
        # framework set, so recording it makes ``status`` and ``audit`` report it
        # as drift and lets a later upgrade retry the removal; dropping it would
        # strand the file untracked forever.
        target = root / relpath
        framework_files[relpath] = manifest.sha256_if_readable(target) or UNSYNCHRONIZED
    for relpath in deliverable:
        # Every managed path this run was responsible for must be accounted for
        # in the baseline. ``workspace_framework_files`` omits any path it cannot
        # hash — non-regular, never written, or written but still unreadable (a
        # write-only file) — and an omission on both sides of ``status``'s
        # comparison is a false "no drift". Sweeping the whole managed universe,
        # rather than only the paths reported as unsynchronized, is what makes
        # this total: a write can succeed and still leave the path unhashable.
        if relpath not in framework_files:
            framework_files[relpath] = UNSYNCHRONIZED
    manifest.write_manifest(root, version, framework_files, kind="workspace")
    return {
        "workspace": str(root),
        "version": version,
        "active_tools": active_tools,
        "changed_files": changed,
        "preserved_files": preserved,
        "removed": removed,
        "stranded": stranded,
        "unsynchronized": unsynchronized,
    }


def register(subparsers) -> None:
    parser = subparsers.add_parser("upgrade", help="synchronize framework files in a workspace")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--tools", default=None, help="replace active runtime generators")
    parser.add_argument("--force", action="store_true", help="force framework-file writes")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    tools = None
    if args.tools is not None:
        tools = [item.strip() for item in args.tools.split(",") if item.strip()]
    result = upgrade(args.directory, tools=tools, force=args.force)
    print(f"Upgraded papersmith workspace: {result['workspace']}")
    print(f"Framework version: {result['version']}; changed files: {len(result['changed_files'])}")
    for relpath in result["unsynchronized"]:
        print(f"Warning: could not write '{relpath}'; it stays reported as drift")
    return 0
