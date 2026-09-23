"""yamllite — a strict YAML-subset parser for papersmith configuration files.

Supported (block style):

* block mappings and sequences, nested by indentation
* compact sequence items that start a mapping (``- key: value``)
* plain scalars with YAML coercion (int, float, ``true``/``false``/``null``)
* single-quoted and double-quoted scalars
* flow sequences of scalars (``[a, b, "c"]``) and empty ``[]`` / ``{}``
* full-line and trailing ``#`` comments

Refused loudly (``YamlliteError`` carries a 1-based line number):

* tabs for indentation
* anchors, aliases, and tags
* block scalars (``|``, ``>``)
* flow collections containing nested collections
* duplicate mapping keys

This is deliberately a subset: papersmith owns the schema of every file it
parses, and a parser that fails loud on the unsupported 5% is safer than one
that silently misreads it.
"""

from __future__ import annotations

__all__ = ["YamlliteError", "loads"]


class YamlliteError(ValueError):
    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


def _strip_comment(text: str) -> str:
    in_single = in_double = False
    for index, char in enumerate(text):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or text[index - 1] in " \t":
                return text[:index].rstrip()
    return text


def _find_colon(text: str, line: int) -> int:
    """Index of the first colon outside quotes, or -1."""
    in_single = in_double = False
    for index, char in enumerate(text):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ":" and not in_single and not in_double:
            return index
    return -1


_DOUBLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


def _parse_quoted(text: str, line: int) -> tuple[str, int]:
    quote = text[0]
    out: list[str] = []
    index = 1
    while index < len(text):
        char = text[index]
        if char == quote:
            if quote == "'" and index + 1 < len(text) and text[index + 1] == "'":
                out.append("'")
                index += 2
                continue
            return "".join(out), index + 1
        if char == "\\" and quote == '"' and index + 1 < len(text):
            out.append(_DOUBLE_ESCAPES.get(text[index + 1], text[index + 1]))
            index += 2
            continue
        out.append(char)
        index += 1
    raise YamlliteError(line, "unterminated quoted scalar")


def _coerce_plain(text: str):
    lowered = text.lower()
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    if lowered in ("null", "~"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _parse_scalar(text: str, line: int):
    text = text.strip()
    if not text:
        return None
    first = text[0]
    if first in ("'", '"'):
        value, rest = _parse_quoted(text, line)
        if rest != len(text):
            raise YamlliteError(line, f"trailing characters after quoted scalar: {text[rest:]!r}")
        return value
    if first in ("&", "*", "!", "%", "@", "`"):
        raise YamlliteError(line, f"unsupported YAML construct: {text!r}")
    return _coerce_plain(text)


def _parse_flow_sequence(text: str, line: int) -> list:
    inner = text[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in inner:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
            continue
        if char in "[{":
            raise YamlliteError(line, "nested flow collections are not supported")
        if char == ",":
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if quote:
        raise YamlliteError(line, "unterminated quote in flow sequence")
    items.append("".join(current).strip())
    result = []
    for item in items:
        if not item:
            raise YamlliteError(line, "empty item in flow sequence")
        result.append(_parse_scalar(item, line))
    return result


class _Line:
    __slots__ = ("number", "indent", "content")

    def __init__(self, number: int, indent: int, content: str) -> None:
        self.number = number
        self.indent = indent
        self.content = content


def _content_lines(text: str) -> list[_Line]:
    """Split into content lines, dropping blanks and full-line comments."""
    lines: list[_Line] = []
    for index, raw in enumerate(text.splitlines()):
        leading = raw[: len(raw) - len(raw.lstrip(" \t"))]
        if "\t" in leading:
            raise YamlliteError(index + 1, "tabs are not allowed for indentation")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        content = _strip_comment(stripped)
        if not content:
            continue
        lines.append(_Line(index + 1, len(leading), content))
    return lines


class _Parser:
    def __init__(self, text: str) -> None:
        self.lines = _content_lines(text)
        self.pos = 0

    def _peek(self) -> _Line | None:
        if self.pos < len(self.lines):
            return self.lines[self.pos]
        return None

    def parse_document(self):
        first = self._peek()
        if first is None:
            return None
        if first.content == "---":
            self.pos += 1
            first = self._peek()
            if first is None:
                return None
        node = self._parse_node(first.indent)
        trailing = self._peek()
        if trailing is not None:
            raise YamlliteError(trailing.number, "unexpected content after document")
        return node

    def _parse_node(self, indent: int):
        line = self._peek()
        if line is None or line.indent != indent:
            raise YamlliteError(line.number if line else 1, "expected content")
        if line.content.startswith("- ") or line.content == "-":
            return self._parse_sequence(indent)
        if line.content.startswith("-"):
            raise YamlliteError(line.number, "sequence items need '- ' (dash and a space)")
        return self._parse_mapping(indent)

    def _parse_mapping(self, indent: int) -> dict:
        result: dict = {}
        self._parse_mapping_pairs(result, indent)
        return result

    def _parse_mapping_pairs(self, result: dict, indent: int) -> None:
        while True:
            line = self._peek()
            if line is None or line.indent < indent:
                return
            if line.indent > indent:
                raise YamlliteError(line.number, "unexpected indentation")
            content = line.content
            if content.startswith("- "):
                raise YamlliteError(line.number, "sequence item where a mapping pair was expected")
            colon = _find_colon(content, line.number)
            if colon < 0:
                raise YamlliteError(line.number, f"expected 'key: value', got {content!r}")
            key = _parse_scalar(content[:colon].strip(), line.number)
            if key is None:
                raise YamlliteError(line.number, "mapping key must not be empty")
            if key in result:
                raise YamlliteError(line.number, f"duplicate key {key!r}")
            self.pos += 1
            rest = content[colon + 1 :].strip()
            if not rest:
                child = self._peek()
                if child is None or child.indent <= indent:
                    result[key] = None
                else:
                    result[key] = self._parse_node(child.indent)
            else:
                result[key] = self._parse_value(rest, line.number)

    def _parse_value(self, text: str, line: int):
        if text == "{}":
            return {}
        if text == "[]":
            return []
        if text.startswith("[") and text.endswith("]"):
            return _parse_flow_sequence(text, line)
        if text.startswith("{") or text.endswith("}"):
            raise YamlliteError(line, f"flow mappings are not supported: {text!r}")
        if text.startswith(("|", ">")):
            raise YamlliteError(line, f"block scalars are not supported: {text!r}")
        return _parse_scalar(text, line)

    def _parse_sequence(self, indent: int) -> list:
        result: list = []
        while True:
            line = self._peek()
            if line is None or line.indent < indent:
                return result
            if line.indent > indent:
                raise YamlliteError(line.number, "unexpected indentation")
            content = line.content
            if not (content.startswith("- ") or content == "-"):
                return result
            self.pos += 1
            item = content[1:].strip()
            if not item:
                child = self._peek()
                if child is None or child.indent <= indent:
                    raise YamlliteError(line.number, "sequence item '-' needs nested content or a value")
                result.append(self._parse_node(child.indent))
                continue
            if _find_colon(item, line.number) >= 0:
                result.append(self._parse_compact_mapping(item, line.number, indent))
            else:
                result.append(self._parse_value(item, line.number))
        return result

    def _parse_compact_mapping(self, item: str, line_number: int, seq_indent: int) -> dict:
        result: dict = {}
        colon = _find_colon(item, line_number)
        key = _parse_scalar(item[:colon].strip(), line_number)
        if key is None:
            raise YamlliteError(line_number, "mapping key must not be empty")
        rest = item[colon + 1 :].strip()
        indent = seq_indent + 2
        if rest:
            result[key] = self._parse_value(rest, line_number)
        else:
            child = self._peek()
            if child is None or child.indent <= indent:
                result[key] = None
            else:
                result[key] = self._parse_node(child.indent)
        self._parse_mapping_pairs(result, indent)
        return result


def loads(text: str):
    """Parse a YAML-subset document; returns mappings as dicts, sequences as
    lists, and scalars as int/float/bool/None/str."""
    return _Parser(text).parse_document()
