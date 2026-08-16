#!/usr/bin/env python3
"""Kaggle credential store — add, list, remove. Nothing is saved unvalidated.

A Kaggle credential is two fields, ``username`` and ``key``, and Kaggle hands
both to you in a single downloaded ``kaggle.json``. So ``add`` takes the path to
that file rather than the token itself: a secret passed as a file never has to
be typed, pasted, or echoed into a transcript that keeps it forever.

Every credential is proven against the live API before it is stored. An account
that cannot authenticate is worse than an absent one — it does not fail when you
add it, it fails hours later in the middle of a run. Adding accepts several
files at once and treats each independently: the ones that authenticate are
saved, the ones that do not are reported and dropped, and one bad file never
costs you the good ones beside it.

The store lives inside the repository, so a `.gitignore` is the only thing
standing between a token and a public commit. That makes the ignore rule a
**precondition**, not a courtesy: before writing, this asks git whether the
store path is genuinely ignored, and refuses to write if it is not. Checking the
effective answer beats checking that a file exists, because an ignore rule can
be present and still not match.

Keys are write-only from the outside. ``list`` reports aliases and usernames and
never the key, so an agent driving this CLI can offer you a choice of accounts
without the secret ever crossing into its context. Whatever launches the runs
reads the store directly.

Every question this skill asks is a selection, and `discover` is what makes the
add question one: it finds the candidate `kaggle.json` files and says which
account each holds, so the user picks instead of typing a path from memory.

Usage:
    python accounts_cli.py list [--json]
    python accounts_cli.py discover [--json]
    python accounts_cli.py add <kaggle.json> [<kaggle.json>…] [--alias NAME]
    python accounts_cli.py remove <alias> [<alias>…]

Exit codes: 0 success (or nothing to do), 1 at least one credential was
rejected (the rest were saved), 2 usage/store/environment error (nothing was
written).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# .../.claude/skills/kaggle-accounts/scripts/accounts_cli.py -> skill root is parents[1]
SKILL_ROOT = Path(__file__).resolve().parents[1]
STORE_DIR = SKILL_ROOT / "store"
STORE_PATH = STORE_DIR / "accounts.json"

# Any authenticated endpoint proves the credential; this is the cheapest one.
# Kaggle answers 401 both anonymously and with a bad key, so 200 is the only
# thing that means "this credential is real".
VALIDATION_URL = "https://www.kaggle.com/api/v1/competitions/list?page=1"
VALIDATION_TIMEOUT = 20

STORE_VERSION = 1
ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Where a downloaded credential actually lands. Direct children only: walking a
# home directory to find a two-field JSON file is slow, and reading every JSON
# somebody owns to see what is inside it is not a thing to do quietly.
CREDENTIAL_SEARCH_DIRS = ("~/Downloads", "~/Desktop", "~/.kaggle", ".")
CREDENTIAL_GLOB = "kaggle*.json"


class UsageError(Exception):
    """The invocation itself is wrong; nothing was touched."""


class StoreError(Exception):
    """The store cannot be read or cannot be written safely."""


class CredentialError(Exception):
    """One credential was rejected; the rest of the batch still applies."""


# --- store -----------------------------------------------------------------


def load_store(path: Path | None = None) -> dict:
    """Read the store, or return an empty one. Raises `StoreError` if corrupt.

    Fail closed on a malformed file: treating unreadable JSON as "no accounts"
    would make the next `add` overwrite credentials that are still in there.
    """
    path = STORE_PATH if path is None else path
    if not path.exists():
        return {"version": STORE_VERSION, "accounts": []}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise StoreError(f"{path} is not valid JSON: {exc.msg} (line {exc.lineno})")
    except OSError as exc:
        raise StoreError(f"{path} could not be read: {exc.strerror}")
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        raise StoreError(f"{path} is not a credential store (expected an 'accounts' list)")
    for entry in data["accounts"]:
        if not isinstance(entry, dict) or not entry.get("alias") or not entry.get("username"):
            raise StoreError(f"{path} holds an entry with no alias or username")
    return data


def assert_ignored(path: Path) -> None:
    """Refuse to write a secret into a path git would track. Raises `StoreError`.

    The store is deliberately inside the repository, which means the ignore rule
    is the entire protection. So this asks git for the effective answer rather
    than trusting that a `.gitignore` exists — a rule can be present and still
    fail to match the path it was written for.
    """
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            cwd=SKILL_ROOT,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        # No git available: fall back to the weaker check rather than refusing
        # to work outside a checkout.
        if not (path.parent / ".gitignore").exists():
            raise StoreError(
                f"{path.parent}/.gitignore is missing — restore it before storing a token here"
            )
        return
    # 0 = ignored, 1 = not ignored, anything else = git could not answer
    # (not a repository, for instance), which is not evidence of exposure.
    if result.returncode == 1:
        raise StoreError(
            f"git would track {path} — restore {path.parent}/.gitignore before storing a token here"
        )


def save_store(store: dict, path: Path | None = None) -> None:
    """Write the store atomically with owner-only permissions.

    Atomic because a truncated write costs every credential in the file, not
    just the one being added.
    """
    path = STORE_PATH if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_ignored(path)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".accounts-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise StoreError(f"{path} could not be written: {exc.strerror}")


# --- credentials -----------------------------------------------------------


def read_credential_file(raw: str) -> tuple[str, str]:
    """Pull `username` and `key` out of a downloaded `kaggle.json`."""
    path = Path(raw).expanduser()
    if not path.exists():
        raise CredentialError("file not found")
    if path.is_dir():
        raise CredentialError("is a directory, not a kaggle.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError:
        raise CredentialError("not valid JSON — expected the kaggle.json Kaggle downloads")
    except OSError as exc:
        raise CredentialError(f"could not be read: {exc.strerror}")
    if not isinstance(data, dict):
        raise CredentialError("not a kaggle.json (expected a JSON object)")
    username, key = data.get("username"), data.get("key")
    if not isinstance(username, str) or not username.strip():
        raise CredentialError("no 'username' field")
    if not isinstance(key, str) or not key.strip():
        raise CredentialError("no 'key' field")
    return username.strip(), key.strip()


def display_path(path: Path) -> str:
    """`~/Downloads/kaggle.json` rather than the full home path."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def discover_credentials(folders: list[str] | None = None) -> list[dict]:
    """Candidate `kaggle.json` files, each with the account it holds.

    Asking "what is the path?" makes the user go find something the machine can
    see, and a mistyped path is a question asked twice. This finds the
    candidates so the choice can be a selection.

    Reporting the **username** of each file is the part that matters: Kaggle
    names every download `kaggle.json`, so three of them in one folder are
    indistinguishable by filename, and picking between identical names is not a
    choice. The key is read and dropped — it never leaves this process.
    """
    seen: set[Path] = set()
    found: list[dict] = []
    for folder in (folders or CREDENTIAL_SEARCH_DIRS):
        directory = Path(folder).expanduser()
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(CREDENTIAL_GLOB)):
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            entry: dict = {"path": str(path), "display": display_path(path),
                           "username": None, "problem": None}
            try:
                entry["username"], _ = read_credential_file(str(path))
            except CredentialError as exc:
                entry["problem"] = str(exc)
            found.append(entry)
    return found


def validate(username: str, key: str) -> None:
    """Prove the credential against the live API. Raises `CredentialError`.

    A network failure is reported as its own outcome. Discarding a good
    credential because the connection dropped, and saying it was invalid, would
    send the user to regenerate a token that was never the problem.
    """
    token = base64.b64encode(f"{username}:{key}".encode()).decode()
    request = urllib.request.Request(
        VALIDATION_URL,
        headers={"Authorization": f"Basic {token}", "User-Agent": "papersmith-kaggle-accounts"},
    )
    try:
        with urllib.request.urlopen(request, timeout=VALIDATION_TIMEOUT) as response:
            if response.status != 200:
                raise CredentialError(f"Kaggle answered HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise CredentialError("Kaggle rejected it (HTTP 401) — wrong username or expired token")
        if exc.code == 403:
            raise CredentialError("authenticated but forbidden (HTTP 403) — the account is restricted")
        raise CredentialError(f"Kaggle answered HTTP {exc.code}")
    except urllib.error.URLError as exc:
        raise CredentialError(f"could not reach Kaggle to validate it ({exc.reason}) — not saved")
    except TimeoutError:
        raise CredentialError(f"Kaggle did not answer within {VALIDATION_TIMEOUT}s — not saved")


# --- commands --------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    accounts = load_store()["accounts"]
    if args.json:
        print(json.dumps(
            {"accounts": [{"alias": a["alias"], "username": a["username"]} for a in accounts]},
            indent=2,
        ))
        return 0
    if not accounts:
        print("No accounts stored.")
        return 0
    width = max(len(a["alias"]) for a in accounts)
    print(f"{len(accounts)} account(s):")
    for account in sorted(accounts, key=lambda a: a["alias"]):
        print(f"  {account['alias']:<{width}}  {account['username']}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    """List candidate credential files so adding can be a pick, not a path."""
    stored = {a["username"]: a["alias"] for a in load_store()["accounts"]}
    found = discover_credentials()
    for entry in found:
        alias = stored.get(entry["username"] or "")
        entry["storedAs"] = alias
        entry["note"] = (
            entry["problem"] if entry["problem"]
            else f"already stored as {alias!r} — adding it again replaces its key" if alias
            else "not stored yet"
        )
    if args.json:
        print(json.dumps({"candidates": found}, indent=2))
        return 0
    if not found:
        print("No kaggle.json found in " + ", ".join(CREDENTIAL_SEARCH_DIRS) + ".")
        return 0
    width = max(len(e["display"]) for e in found)
    print(f"{len(found)} candidate credential file(s):")
    for entry in found:
        who = entry["username"] or "unreadable"
        print(f"  {entry['display']:<{width}}  {who}  ({entry['note']})")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    if args.alias is not None:
        if len(args.files) != 1:
            raise UsageError("--alias applies to a single file; without it each account is named after its username")
        if not ALIAS_PATTERN.match(args.alias):
            raise UsageError(f"alias {args.alias!r} must be 1-64 chars of letters, digits, dot, dash or underscore")

    store = load_store()
    by_alias = {a["alias"]: a for a in store["accounts"]}
    by_username = {a["username"]: a for a in store["accounts"]}
    saved: list[str] = []
    rejected: list[str] = []

    for raw in args.files:
        try:
            username, key = read_credential_file(raw)
            alias = args.alias or username
            if not ALIAS_PATTERN.match(alias):
                raise CredentialError(f"username {username!r} is not a usable alias; pass --alias")
            existing = by_username.get(username)
            if existing is None and alias in by_alias:
                raise CredentialError(
                    f"alias {alias!r} already belongs to {by_alias[alias]['username']}; pass a different --alias"
                )
            validate(username, key)
        except CredentialError as exc:
            rejected.append(f"{raw} — {exc}")
            continue
        if existing is not None:
            existing["key"] = key
            saved.append(f"{existing['alias']} ({username}) — updated, key replaced")
        else:
            entry = {"alias": alias, "username": username, "key": key}
            store["accounts"].append(entry)
            by_alias[alias] = entry
            by_username[username] = entry
            saved.append(f"{alias} ({username}) — saved")

    if saved:
        save_store(store)
        print(f"Validated and stored {len(saved)} of {len(args.files)}:")
        for line in saved:
            print(f"  {line}")
        print("The kaggle.json files still hold those tokens; delete them once you are done.")
    if rejected:
        print(f"Rejected {len(rejected)}, nothing stored for them:")
        for line in rejected:
            print(f"  {line}")
    return 1 if rejected else 0


def cmd_remove(args: argparse.Namespace) -> int:
    store = load_store()
    present = {a["alias"] for a in store["accounts"]}
    unknown = [alias for alias in args.aliases if alias not in present]
    if unknown:
        # Refuse the whole batch: a typo that silently removes only the aliases
        # it happened to match is a worse outcome than removing nothing.
        raise UsageError(f"no such account: {', '.join(unknown)}")

    targets = set(args.aliases)
    store["accounts"] = [a for a in store["accounts"] if a["alias"] not in targets]
    save_store(store)
    print(f"Removed {len(targets)}: {', '.join(sorted(targets))}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the Kaggle credentials this project uses.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="show stored accounts (never their keys)")
    p_list.add_argument("--json", action="store_true", help="machine-readable output")
    p_list.set_defaults(func=cmd_list)

    p_discover = sub.add_parser("discover", help="find kaggle.json files to offer as choices")
    p_discover.add_argument("--json", action="store_true", help="machine-readable output")
    p_discover.set_defaults(func=cmd_discover)

    p_add = sub.add_parser("add", help="validate one or more kaggle.json files and store what passes")
    p_add.add_argument("files", nargs="+", metavar="kaggle.json")
    p_add.add_argument("--alias", help="name for the account; defaults to its Kaggle username")
    p_add.set_defaults(func=cmd_add)

    p_remove = sub.add_parser("remove", help="delete stored accounts by alias")
    p_remove.add_argument("aliases", nargs="+", metavar="alias")
    p_remove.set_defaults(func=cmd_remove)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (UsageError, StoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
