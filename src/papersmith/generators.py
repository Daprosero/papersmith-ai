"""Deterministic runtime-document generators.

Claude's ``.claude/agents`` directory is the workspace SSOT. The generated
entrypoints only route each runtime to that SSOT and the workspace skills; they
intentionally do not fork agent instructions between harnesses.
"""

from __future__ import annotations

import ast
import warnings as _warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import fs
from .core.config import load_papersmith_yaml, load_workspace_config
from .errors import UserError
from .render import render_package_template

ALL_TOOLS = ("claude", "opencode", "pi", "antigravity")

#: Each runtime's *static* entrypoints. Used to answer "is this a known runtime?"
#: and, for a runtime a workspace does not declare, to name that runtime's
#: surplus static files in ``audit``. It is deliberately not a complete
#: rendered-path list and cannot become one: the dynamic
#: ``.opencode/commands/<name>.md``, ``.claude/commands/<name>.md`` and
#: ``.pi/prompts/<name>.md`` files are one per
#: discovered skill. :func:`render_files` is the single authority for
#: the path set.
TOOL_OUTPUTS = {
    "claude": ("CLAUDE.md",),
    "opencode": ("OPENCODE.md",),
    "pi": ("PI.md", ".pi/gentle-ai/persona.json"),
    "antigravity": (".antigravity/rules.md",),
}

#: Baseline marker for a managed path a run could not synchronize or remove.
#: A sha256 digest is 64 hex characters, so this cannot collide with one, and
#: ``workspace_framework_files`` omits such a path from the live map — the
#: comparison therefore always mismatches and ``status`` reports it as drift
#: instead of losing it when the baseline is rewritten.
UNSYNCHRONIZED = "unsynchronized"


def _frontmatter_value(value: str) -> str:
    value = value.strip()
    if value.startswith('"') or value.startswith("'"):
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value.strip("'\"")
        return str(parsed)
    return value


def read_workspace_version(workspace: Path, default: str) -> str:
    """Read ``.papersmith/version`` without ever raising or blocking.

    The marker is a framework-managed path like any other, so it passes the same
    regular-file gate: a FIFO here would block every context derivation, and a
    non-UTF-8 marker would escape as an untyped ``UnicodeDecodeError`` from a
    read whose callers are all fail-soft.
    """
    text = fs.read_text(workspace / ".papersmith" / "version")
    return text.strip() if text and text.strip() else default


def collect_agents(workspace: Path) -> list[dict[str, str]]:
    """Read only agent names/descriptions from the canonical front matter.

    Fail-soft by contract, like :func:`collect_commands`: this runs inside every
    rendered-context derivation, so a damaged or unreadable agent file must not
    break ``status`` or ``audit``. Such a file is reported by name with an empty
    description instead of raising.
    """
    agents: list[dict[str, str]] = []
    agent_dir = workspace / ".claude" / "agents"
    if not fs.is_dir(agent_dir):
        return agents
    try:
        candidates = sorted(agent_dir.glob("*.md"))
    except OSError:
        return agents
    for path in candidates:
        if not fs.is_regular_file(path):
            agents.append({"name": path.stem, "description": ""})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            agents.append({"name": path.stem, "description": ""})
            continue
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            agents.append({"name": path.stem, "description": ""})
            continue
        metadata: dict[str, str] = {}
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = _frontmatter_value(value)
        agents.append({
            "name": metadata.get("name", path.stem),
            "description": metadata.get("description", ""),
        })
    return agents


def _agents_block(workspace: Path) -> str:
    agents = collect_agents(workspace)
    if not agents:
        return "- No specialized agents have been installed yet."
    return "\n".join(
        f"- `{agent['name']}`{(' — ' + agent['description']) if agent['description'] else ''}"
        for agent in agents
    )


COMMAND_TOOLS = ("opencode", "claude", "pi")

#: Where each command tool reads project slash commands from. Pi calls them
#: prompt templates; the body is the same `command.md.tpl` for all three.
COMMAND_PREFIXES = {
    "opencode": ".opencode/commands",
    "claude": ".claude/commands",
    "pi": ".pi/prompts",
}

#: Where each tool reads subagent definitions from. Claude's are the kit's own
#: source files (``.claude/agents``, copied not rendered); the other three are
#: projections :func:`render_files` writes from them.
AGENT_DIRS = {
    "claude": ".claude/agents",
    "opencode": ".opencode/agents",
    "pi": ".pi/agents",
    "antigravity": ".agents/agents",
}

#: The generated safety plugin/extension each tool loads, where it has one.
#: Claude has none: its guard is a documented opt-in hook (docs/guard-hooks.md).
PLUGIN_FILES = {
    "opencode": ".opencode/plugins/refuse-offpath-push.js",
    "pi": ".pi/extensions/refuse-offpath-push.js",
}

CAPABILITIES = ("skills", "commands", "agents", "plugins")


@dataclass(frozen=True)
class Capability:
    """One cell of the support matrix: whether the harness gets it, and where."""

    supported: bool
    artifact: str | None = None  # directory (commands, agents) or file (plugins)


def _build_capabilities() -> dict[str, dict[str, Capability]]:
    """Derived from the same constants :func:`render_files` writes through, so
    a generated output with no entry (or an entry with no output) is a test
    failure rather than silent drift. Every tool in :data:`ALL_TOOLS` is served
    by the ``skills`` symlink roster (``manifest.HARNESS_SKILL_LINKS``); a test
    pins that agreement because ``manifest`` imports this module."""
    matrix: dict[str, dict[str, Capability]] = {}
    for tool in ALL_TOOLS:
        matrix[tool] = {
            "skills": Capability(True),
            "commands": Capability(tool in COMMAND_TOOLS, COMMAND_PREFIXES.get(tool)),
            "agents": Capability(tool in AGENT_DIRS, AGENT_DIRS.get(tool)),
            "plugins": Capability(tool in PLUGIN_FILES, PLUGIN_FILES.get(tool)),
        }
    return matrix


HARNESS_CAPABILITIES = _build_capabilities()

#: Claude tool names to Pi tool names for the `.pi/agents/` projection.
#: `WebSearch`/`WebFetch` have no direct Pi child-tool counterparts: they
#: map onto the MCP gateway (`mcp` for one call, `mcpScript` for batched
#: calls with logic between them), which is what the agent bodies already
#: prefer ("through your own MCP servers first"). Whether the Pi runtime
#: actually hands those tools to a subagent is decided there, not here --
#: this projection only declares the intent. Unknown names pass through
#: lowercased rather than silently dropped, so a new Claude tool shows up
#: verbatim instead of vanishing.
PI_TOOL_MAP = {
    "read": "read",
    "glob": "find",
    "grep": "grep",
    "write": "write",
    "edit": "edit",
    "bash": "bash",
    "websearch": "mcpScript",
    "webfetch": "mcp",
}

#: Claude tool names to the OpenCode permission keys that gate them, for the
#: `.opencode/agents/` projection. OpenCode has no `tools:` allow-list any more
#: (documented as deprecated); a subagent is restricted through `permission`
#: keys with `allow`/`deny` values. `Write` and `Edit` share the single `edit`
#: key, which OpenCode applies to every file modification. `Glob` also grants
#: `list` (directory listing), which is no wider than globbing. A tool absent
#: from this map is never granted: it is skipped with a warning.
OPENCODE_TOOL_PERMISSIONS = {
    "read": ("read",),
    "glob": ("glob", "list"),
    "grep": ("grep",),
    "write": ("edit",),
    "edit": ("edit",),
    "bash": ("bash",),
    "websearch": ("websearch",),
    "webfetch": ("webfetch",),
}

#: Every permission key the projection decides explicitly. A key no source tool
#: grants is written as `deny`, so a read-only agent can never inherit edit,
#: bash, network or sub-agent access from OpenCode's permissive defaults.
OPENCODE_PERMISSION_KEYS = (
    "read", "glob", "grep", "list", "edit", "bash", "webfetch", "websearch", "task",
)


#: Claude tool names to the Antigravity tool names listed in its hooks docs
#: (https://antigravity.google/docs/hooks), for the `.agents/agents/`
#: projection. Antigravity's `tools:` is an explicit allow-list (default
#: empty). `Write` and `Edit` map to the distinct file-write and file-replace
#: tools; `Glob` also grants `list_dir`, which is no wider than globbing. A tool
#: absent from this map is never granted: it is skipped with a note.
ANTIGRAVITY_TOOL_MAP = {
    "read": ("view_file",),
    "glob": ("find_by_name", "list_dir"),
    "grep": ("grep_search",),
    "write": ("write_to_file",),
    "edit": ("replace_file_content", "multi_replace_file_content"),
    "bash": ("run_command",),
    "websearch": ("search_web",),
    "webfetch": ("read_url_content",),
}


def derive_command_description(source: str) -> str:
    """Collapse whitespace, then keep the first sentence.

    Command front matter wants a terse single-line description, while skill
    front matter carries a long ``Trigger: ...`` paragraph. This is the single
    definition of that source-to-derived transform: the emitted value and every
    assertion use it, never the raw multi-sentence source.
    """
    normalized = " ".join(source.split())
    for index, char in enumerate(normalized):
        if char in ".!?":
            following = normalized[index + 1:index + 2]
            if not following or following.isspace():
                return normalized[: index + 1]
    return normalized


def yaml_double_quote(value: str) -> str:
    """Emit ``value`` as a double-quoted YAML scalar."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _skill_command(skill_dir: Path) -> tuple[dict[str, str] | None, str | None]:
    """Return ``(entry, None)`` or ``(None, skip_reason)`` — never raises."""
    name = skill_dir.name
    skill_file = skill_dir / "SKILL.md"
    if not fs.is_regular_file(skill_file):
        return None, "missing SKILL.md"
    try:
        lines = skill_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None, "unreadable SKILL.md"
    if not lines or lines[0].strip() != "---":
        return None, "malformed front matter"
    metadata: dict[str, str] = {}
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = _frontmatter_value(value)
    if not closed:
        return None, "malformed front matter"
    declared = metadata.get("name", "").strip()
    description = metadata.get("description", "").strip()
    if not declared:
        return None, "missing name"
    if declared != name:
        return None, f"name '{declared}' does not match directory '{name}'"
    if not description:
        return None, "missing description"
    return {"name": declared, "description": derive_command_description(description)}, None


def collect_commands(workspace: Path, *,
                     warnings: list[str] | None = None) -> list[dict[str, str]]:
    """Derive one slash command per top-level workspace skill.

    Fail-soft by contract: a skill whose ``SKILL.md`` is missing or whose
    ``name``/``description`` front matter is absent or malformed is skipped with
    a warning, never raised on. ``_``-prefixed directories are engine shelves and
    are skipped silently; nested ``SKILL.md`` files are never command targets.
    """
    commands: list[dict[str, str]] = []
    skills_dir = workspace / "skills"
    if not fs.is_dir(skills_dir):
        return commands
    try:
        skill_dirs = sorted(skills_dir.iterdir())
    except OSError:
        return commands
    skipped: list[str] = []
    for skill_dir in skill_dirs:
        if not fs.is_dir(skill_dir) or skill_dir.name.startswith("_"):
            continue
        entry, reason = _skill_command(skill_dir)
        if entry is None:
            skipped.append(f"skipping skill '{skill_dir.name}': {reason}")
            continue
        commands.append(entry)
    if skipped:
        if warnings is not None:
            warnings.extend(skipped)
        else:
            # One aggregated warning: Python's default filter dedupes by
            # (module, line), and every skip is emitted from this one line, so
            # per-skip warns would silently drop all but the first.
            _warnings.warn("\n".join(skipped), UserWarning, stacklevel=2)
    commands.sort(key=lambda item: item["name"])
    return commands


def _pi_tools_line(value: str) -> str:
    """Map a Claude `tools: A, B` line onto Pi tool names as a YAML list."""
    mapped = [PI_TOOL_MAP.get(item.strip().lower(), item.strip().lower())
              for item in value.split(",") if item.strip()]
    return "tools:\n" + "\n".join(f"  - {name}" for name in mapped)


def _pi_agent_name(metadata: dict[str, str], fallback: str) -> str | None:
    """The output stem, or None when it would escape `.pi/agents/`."""
    name = metadata.get("name", fallback).strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    return name


def _split_agent_source(
    source: str,
) -> tuple[dict[str, str], list[str], list[str], str | None]:
    """Split a Claude agent definition into ``(metadata, meta_lines, body_lines, reason)``.

    ``reason`` is a skip reason when the front matter is missing, unclosed, or
    lacks a ``name``; the other fields are then empty. Never raises.
    """
    lines = source.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, [], [], "malformed front matter"
    metadata: dict[str, str] = {}
    meta_lines: list[str] = []
    rest: list[str] | None = None
    for index, line in enumerate(lines[1:]):
        if line.strip() == "---":
            rest = lines[index + 2:]
            break
        meta_lines.append(line)
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = _frontmatter_value(value)
    if rest is None:
        return {}, [], [], "malformed front matter"
    if "name" not in metadata:
        return {}, [], [], "missing name"
    return metadata, meta_lines, rest, None


def _translate_agent_for_pi(source: str) -> tuple[dict[str, str] | None, str | None]:
    """Project one Claude agent definition onto the Pi agent shape.

    Returns ``({"name": ..., "text": ...}, None)`` or ``(None,
    skip_reason)`` -- never raises. Front matter travels verbatim except
    the `tools:` line, which is mapped through :data:`PI_TOOL_MAP`; the
    body travels verbatim except `.claude/skills/` references, which
    become harness-neutral `skills/` (a symlink in every workspace).
    """
    metadata, meta_lines, rest, reason = _split_agent_source(source)
    if reason:
        return None, reason
    out_lines = []
    for line in meta_lines:
        if ":" in line and line.split(":", 1)[0].strip().lower() == "tools":
            out_lines.append(_pi_tools_line(line.split(":", 1)[1]))
        else:
            out_lines.append(line)
    body = "\n".join(rest).replace(".claude/skills/", "skills/")
    text = "---\n" + "\n".join(out_lines) + "\n---\n" + body
    if not text.endswith("\n"):
        text += "\n"
    return {"name": metadata["name"], "text": text}, None


def _translate_agent_for_opencode(
    source: str,
) -> tuple[dict[str, str] | None, str | None, list[str]]:
    """Project one Claude agent definition onto the OpenCode agent shape.

    Returns ``(entry, None, notes)`` or ``(None, skip_reason, [])`` -- never
    raises. Only ``description`` travels from the source front matter; the
    output adds ``mode: subagent`` and a ``permission`` block derived from the
    source ``tools:`` line through :data:`OPENCODE_TOOL_PERMISSIONS`. Every key
    in :data:`OPENCODE_PERMISSION_KEYS` is written explicitly (``allow`` only
    when a source tool grants it, else ``deny``), and a tool with no mapping is
    never granted and is named in ``notes``. A source with no ``tools:`` line
    inherits every tool in Claude Code, so it gets no ``permission`` block and
    inherits OpenCode's defaults the same way.
    """
    metadata, meta_lines, rest, reason = _split_agent_source(source)
    if reason:
        return None, reason, []
    description = metadata.get("description", "").strip()
    if not description:
        return None, "missing description", []
    notes: list[str] = []
    out = [f"description: {yaml_double_quote(description)}", "mode: subagent"]
    tools_value = next(
        (line.split(":", 1)[1] for line in meta_lines
         if ":" in line and line.split(":", 1)[0].strip().lower() == "tools"),
        None,
    )
    if tools_value is not None:
        granted: set[str] = set()
        for item in tools_value.split(","):
            tool = item.strip()
            if not tool:
                continue
            keys = OPENCODE_TOOL_PERMISSIONS.get(tool.lower())
            if keys is None:
                notes.append(f"tool '{tool}' has no OpenCode permission; not granted")
                continue
            granted.update(keys)
        out.append("permission:")
        out.extend(
            f"  {key}: {'allow' if key in granted else 'deny'}"
            for key in OPENCODE_PERMISSION_KEYS
        )
    body = "\n".join(rest).replace(".claude/skills/", "skills/")
    text = "---\n" + "\n".join(out) + "\n---\n" + body
    if not text.endswith("\n"):
        text += "\n"
    return {"name": metadata["name"], "text": text}, None, notes


def _translate_agent_for_antigravity(
    source: str,
) -> tuple[dict[str, str] | None, str | None, list[str]]:
    """Project one Claude agent definition onto the Antigravity agent shape.

    Returns ``(entry, None, notes)`` or ``(None, skip_reason, [])`` -- never
    raises. The output carries ``name``, ``description``, an explicit ``tools``
    allow-list mapped through :data:`ANTIGRAVITY_TOOL_MAP`, and
    ``commandExecutionPolicy``: ``"sandbox"`` (the documented default) only when
    the agent holds ``run_command``, else the most restrictive value, ``"off"`` (always quoted).
    ``model`` is omitted so it inherits (documented default). A tool with no
    mapping is never granted and is named in ``notes``; a source with no
    ``tools:`` line gets no ``tools`` key, which Antigravity reads as empty.
    """
    metadata, meta_lines, rest, reason = _split_agent_source(source)
    if reason:
        return None, reason, []
    description = metadata.get("description", "").strip()
    if not description:
        return None, "missing description", []
    notes: list[str] = []
    granted: list[str] = []
    tools_value = next(
        (line.split(":", 1)[1] for line in meta_lines
         if ":" in line and line.split(":", 1)[0].strip().lower() == "tools"),
        None,
    )
    for item in (tools_value or "").split(","):
        tool = item.strip()
        if not tool:
            continue
        names = ANTIGRAVITY_TOOL_MAP.get(tool.lower())
        if names is None:
            notes.append(f"tool '{tool}' has no Antigravity tool; not granted")
            continue
        granted.extend(name for name in names if name not in granted)
    out = [f"name: {metadata['name']}", f"description: {yaml_double_quote(description)}"]
    if granted:
        out.append("tools:")
        out.extend(f"  - {name}" for name in granted)
    # Quoted: an unquoted `off` is a boolean in YAML 1.1 parsers.
    policy = "sandbox" if "run_command" in granted else "off"
    out.append(f"commandExecutionPolicy: {yaml_double_quote(policy)}")
    body = "\n".join(rest).replace(".claude/skills/", "skills/")
    text = "---\n" + "\n".join(out) + "\n---\n" + body
    if not text.endswith("\n"):
        text += "\n"
    return {"name": metadata["name"], "text": text}, None, notes


def _collect_projected_agents(
    workspace: Path, translate: Any, *, warnings: list[str] | None,
) -> list[dict[str, str]]:
    """Project every `.claude/agents/*.md` definition through ``translate``.

    ``translate`` returns ``(entry, skip_reason, notes)``. Fail-soft by
    contract, like :func:`collect_commands`: a definition that is not a regular
    file, is unreadable, has missing or malformed front matter, or whose name is
    absent or unsafe is skipped with a warning, never raised on.
    """
    agents: list[dict[str, str]] = []
    agent_dir = workspace / ".claude" / "agents"
    if not fs.is_dir(agent_dir):
        return agents
    try:
        candidates = sorted(agent_dir.glob("*.md"))
    except OSError:
        return agents
    skipped: list[str] = []
    for path in candidates:
        if not fs.is_regular_file(path):
            skipped.append(f"skipping agent '{path.stem}': not a regular file")
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped.append(f"skipping agent '{path.stem}': unreadable")
            continue
        entry, reason, notes = translate(source)
        if entry is None:
            skipped.append(f"skipping agent '{path.stem}': {reason}")
            continue
        name = _pi_agent_name({"name": entry["name"]}, path.stem)
        if name is None:
            skipped.append(f"skipping agent '{path.stem}': unsafe name")
            continue
        skipped.extend(f"agent '{path.stem}': {note}" for note in notes)
        agents.append({"name": name, "text": entry["text"]})
    if skipped:
        if warnings is not None:
            warnings.extend(skipped)
        else:
            _warnings.warn("\n".join(skipped), UserWarning, stacklevel=3)
    agents.sort(key=lambda item: item["name"])
    return agents


def collect_pi_agents(workspace: Path, *,
                      warnings: list[str] | None = None) -> list[dict[str, str]]:
    """Project every `.claude/agents/*.md` definition onto Pi shape."""
    def translate(source: str) -> tuple[dict[str, str] | None, str | None, list[str]]:
        entry, reason = _translate_agent_for_pi(source)
        return entry, reason, []
    return _collect_projected_agents(workspace, translate, warnings=warnings)


def collect_opencode_agents(workspace: Path, *,
                            warnings: list[str] | None = None) -> list[dict[str, str]]:
    """Project every `.claude/agents/*.md` definition onto OpenCode shape."""
    return _collect_projected_agents(workspace, _translate_agent_for_opencode, warnings=warnings)


def collect_antigravity_agents(workspace: Path, *,
                               warnings: list[str] | None = None) -> list[dict[str, str]]:
    """Project every `.claude/agents/*.md` definition onto Antigravity shape."""
    return _collect_projected_agents(workspace, _translate_agent_for_antigravity, warnings=warnings)


def context_for_workspace(workspace: Path) -> dict[str, Any]:
    config = load_workspace_config(workspace)
    yaml = load_papersmith_yaml(workspace)
    return {
        "name": yaml.get("name", config["project_name"]),
        "title": yaml.get("title", config["project_name"]),
        "topic": yaml.get("topic", "unspecified"),
        "version": read_workspace_version(workspace, str(yaml.get("version", "1"))),
        "tools": ", ".join(config["active_tools"]),
        "agents": _agents_block(workspace),
    }


def workspace_tools(workspace: Path) -> tuple[str, ...]:
    """The tool set a workspace declares. The only place this is decided.

    Returns the validated ``active_tools`` from ``.papersmith/config.json``.
    Fail-soft by contract: when that file is absent, unreadable, corrupt, or
    missing/malformed in ``active_tools``, this resolver emits exactly one
    aggregated :class:`UserWarning` and falls back to :data:`ALL_TOOLS`. It never
    raises, so a consumer that only needs the declared set always proceeds.

    That guarantee covers this resolver alone. ``status`` and ``audit`` still
    require a valid workspace config and raise ``UserError`` without one, because
    they read it independently of this fallback.
    """
    config_path = workspace / ".papersmith" / "config.json"
    try:
        return tuple(load_workspace_config(workspace)["active_tools"])
    except (UserError, OSError, UnicodeDecodeError) as exc:
        _warnings.warn(
            f"could not read the declared tool set from {config_path} ({exc}); "
            f"assuming all runtimes: {', '.join(ALL_TOOLS)}",
            UserWarning,
            stacklevel=2,
        )
        return ALL_TOOLS


def _context_with_defaults(context: dict[str, Any]) -> dict[str, Any]:
    result = dict(context)
    result.setdefault("name", "paper-workspace")
    result.setdefault("title", result["name"])
    result.setdefault("topic", "unspecified")
    result.setdefault("version", "0.1.0")
    result.setdefault("tools", ", ".join(ALL_TOOLS))
    result.setdefault("agents", "- No specialized agents have been installed yet.")
    return result


def render_files(workspace: Path, context: dict[str, Any] | None = None,
                 tools: list[str] | tuple[str, ...] = ALL_TOOLS, *,
                 warnings: list[str] | None = None) -> dict[str, str]:
    ctx = _context_with_defaults(context or context_for_workspace(workspace))
    rendered: dict[str, str] = {".gitignore": render_package_template("gitignore.tpl", ctx)}
    templates = {
        "claude": ("CLAUDE.md", "claude.md.tpl"),
        "opencode": ("OPENCODE.md", "opencode.md.tpl"),
        "pi": ("PI.md", "pi.md.tpl"),
        "antigravity": (".antigravity/rules.md", "antigravity-rules.md.tpl"),
    }
    commands: list[dict[str, str]] | None = None
    if any(tool in COMMAND_TOOLS for tool in tools):
        commands = collect_commands(workspace, warnings=warnings)
    pi_agents: list[dict[str, str]] | None = None
    if "pi" in tools:
        pi_agents = collect_pi_agents(workspace, warnings=warnings)
    opencode_agents: list[dict[str, str]] | None = None
    if "opencode" in tools:
        opencode_agents = collect_opencode_agents(workspace, warnings=warnings)
    antigravity_agents: list[dict[str, str]] | None = None
    if "antigravity" in tools:
        antigravity_agents = collect_antigravity_agents(workspace, warnings=warnings)
    for tool in tools:
        if tool not in TOOL_OUTPUTS:
            raise UserError(f"unsupported runtime generator: {tool}")
        output, template = templates[tool]
        rendered[output] = render_package_template(template, ctx)
        if tool == "pi":
            rendered[".pi/gentle-ai/persona.json"] = render_package_template("persona.json.tpl", ctx)
            rendered[PLUGIN_FILES["pi"]] = render_package_template(
                "pi-extension.js.tpl", ctx)
        if tool == "pi" and pi_agents:
            for agent in pi_agents:
                rendered[f"{AGENT_DIRS['pi']}/{agent['name']}.md"] = agent["text"]
        if tool == "opencode" and opencode_agents:
            for agent in opencode_agents:
                rendered[f"{AGENT_DIRS['opencode']}/{agent['name']}.md"] = agent["text"]
        if tool == "antigravity" and antigravity_agents:
            for agent in antigravity_agents:
                rendered[f"{AGENT_DIRS['antigravity']}/{agent['name']}.md"] = agent["text"]
        if tool == "opencode":
            rendered["opencode.json"] = render_package_template("opencode.json.tpl", ctx)
            rendered[PLUGIN_FILES["opencode"]] = render_package_template(
                "opencode-plugin.js.tpl", ctx)
        if tool in COMMAND_TOOLS and commands:
            prefix = COMMAND_PREFIXES[tool]
            for command in commands:
                command_ctx = dict(ctx)
                command_ctx.update({
                    "skill_name": command["name"],
                    "skill_path": f"skills/{command['name']}/SKILL.md",
                    "description_yaml": yaml_double_quote(command["description"]),
                })
                rendered[f"{prefix}/{command['name']}.md"] = render_package_template(
                    "command.md.tpl", command_ctx)
    return rendered


def apply_generated(workspace: Path, context: dict[str, Any] | None = None,
                    tools: list[str] | tuple[str, ...] = ALL_TOOLS, *,
                    warnings: list[str] | None = None,
                    skipped: list[str] | None = None) -> list[str]:
    """Write every rendered file, never blocking on a damaged workspace.

    Every target passes the same regular-file gate the readers use. A rendered
    path occupied by a directory, socket, device, FIFO or dangling symlink is
    reported and skipped rather than opened: a write to a FIFO would block
    forever, and a device would accept unbounded bytes. An unsearchable parent
    is reported too, instead of aborting the run part-way through, after the kit
    copy has already mutated the workspace.

    A skipped path is left exactly as it was and named in ``skipped``, so its
    caller can keep it in the manifest baseline: ``workspace_framework_files``
    omits a path it cannot hash, so a baseline rewritten without it would drop
    the path from both sides of the comparison and ``status`` would report a
    false "no drift".
    """
    changed: list[str] = []
    unsynchronized: list[str] = []
    for relpath, content in render_files(workspace, context, tools, warnings=warnings).items():
        path = workspace / relpath
        encoded = content.encode("utf-8")
        if fs.is_regular_file(path):
            try:
                if path.read_bytes() == encoded:
                    continue
            except OSError:
                pass  # Present but unreadable: try to overwrite it below.
        elif fs.exists(path):
            unsynchronized.append(relpath)
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded)
        except OSError:
            unsynchronized.append(relpath)
            continue
        changed.append(relpath)
    if skipped is not None:
        skipped.extend(unsynchronized)
    if unsynchronized:
        reported = [f"skipping '{relpath}': not written" for relpath in unsynchronized]
        if warnings is not None:
            warnings.extend(reported)
        else:
            # One aggregated warning for the same reason collect_commands emits
            # one: the default filter dedupes by (module, line), so per-path
            # warnings would silently drop all but the first.
            _warnings.warn("\n".join(reported), UserWarning, stacklevel=2)
    return changed


def check_generated(workspace: Path, context: dict[str, Any] | None = None,
                    tools: list[str] | tuple[str, ...] = ALL_TOOLS, *,
                    warnings: list[str] | None = None) -> list[str]:
    """Rendered paths whose on-disk bytes are not verifiably current.

    Anything that is not a readable regular file counts as drift: the same gate
    the readers use, plus a guarded read, so this answers the same way
    ``status`` does for that path instead of raising where ``status`` reports.
    """
    drifted: list[str] = []
    for relpath, content in render_files(workspace, context, tools, warnings=warnings).items():
        path = workspace / relpath
        if not fs.is_regular_file(path):
            drifted.append(relpath)
            continue
        try:
            if path.read_bytes() != content.encode("utf-8"):
                drifted.append(relpath)
        except OSError:
            # A regular file whose mode denies the read: present, but not
            # verifiably current, which is drift.
            drifted.append(relpath)
    return drifted
