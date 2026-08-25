from __future__ import annotations

import re
from impl_refusals import NameRefused, Refused


def validate_name(name: str) -> str:
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        raise Refused("INVALID_NAME", f"Name {name!r} must be alphanumeric (- and _ allowed).")
    return name


def package_name(name: str) -> str:
    """The importable form of the name.

    A hyphen is legal in a directory but not in a Python identifier, so
    `Example-Method/` pairs with `<sources>/Example_Method/`. The correspondence the layout
    exists to make visible survives; `import Example-Method` would not.
    """
    return name.replace("-", "_")


def normalize_name(raw: str) -> dict:
    """Turn whatever the user typed into the `<Name>/` + `<sources>/<Package>/` pair.

    The user types `deep set`, `DEEP-SET` or `deepSet` and means the same thing.
    Splitting happens on any separator and on a lower-to-upper boundary; an all-caps
    token of two or more letters is an acronym and survives untouched, because
    lowercasing an acronym renames the method rather than tidying the folder.
    """
    text = (raw or "").strip()
    if not text:
        raise NameRefused("NAME_EMPTY")
    # Split first on explicit separators, then inside each piece on camel boundaries.
    tokens: list[str] = []
    for piece in re.split(r"[\s\-_]+", text):
        if not piece:
            continue
        tokens.extend(re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", piece))
    if not tokens:
        raise NameRefused("NAME_HAS_NO_WORDS")
    for token in tokens:
        if not token.isalnum():
            raise NameRefused(f"NAME_NOT_ALPHANUMERIC:{token}")
    if tokens[0][0].isdigit():
        raise NameRefused("NAME_STARTS_WITH_DIGIT")
    parts = [token if token.isupper() and len(token) >= 2 else token.capitalize()
             for token in tokens]
    return {"input": raw, "directory": "-".join(parts), "package": "_".join(parts)}
