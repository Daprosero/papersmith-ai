"""Focused unit tests for the Kaggle credential store.

These cover the deterministic logic in ``accounts_cli.py`` — credential file
parsing, the store round-trip, alias rules, and the git-ignore precondition —
without touching the network. Validation itself is stubbed; what it does against
the live API is proven by adding a real credential, not by a unit test.

Run with any Python 3.10+ (the script is stdlib-only):
    python3 -m unittest tests.test_kaggle_accounts
"""
from __future__ import annotations

import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / ".claude/skills/kaggle-accounts/scripts/accounts_cli.py"
SPEC = importlib.util.spec_from_file_location("accounts_cli", SCRIPT)
assert SPEC and SPEC.loader
ACCOUNTS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ACCOUNTS
SPEC.loader.exec_module(ACCOUNTS)


def write_credential(folder: Path, name: str, **fields: object) -> Path:
    path = folder / name
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


class ReadCredentialFileTests(unittest.TestCase):
    def test_reads_username_and_key_from_a_kaggle_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_credential(Path(tmp), "kaggle.json", username=" diego ", key=" abc123 ")
            self.assertEqual(ACCOUNTS.read_credential_file(str(path)), ("diego", "abc123"))

    def test_rejects_a_missing_file(self) -> None:
        with self.assertRaisesRegex(ACCOUNTS.CredentialError, "not found"):
            ACCOUNTS.read_credential_file("/nonexistent/kaggle.json")

    def test_rejects_unparseable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kaggle.json"
            path.write_text("not json at all", encoding="utf-8")
            with self.assertRaisesRegex(ACCOUNTS.CredentialError, "not valid JSON"):
                ACCOUNTS.read_credential_file(str(path))

    def test_rejects_a_json_object_missing_either_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            no_key = write_credential(Path(tmp), "a.json", username="diego")
            no_user = write_credential(Path(tmp), "b.json", key="abc123")
            blank = write_credential(Path(tmp), "c.json", username="diego", key="   ")
            for path, expected in ((no_key, "'key'"), (no_user, "'username'"), (blank, "'key'")):
                with self.assertRaisesRegex(ACCOUNTS.CredentialError, expected):
                    ACCOUNTS.read_credential_file(str(path))


class StoreTests(unittest.TestCase):
    def test_a_missing_store_reads_as_empty_rather_than_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ACCOUNTS.load_store(Path(tmp) / "accounts.json")
            self.assertEqual(store["accounts"], [])

    def test_a_corrupt_store_fails_closed_instead_of_reading_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            path.write_text("{ truncated", encoding="utf-8")
            with self.assertRaisesRegex(ACCOUNTS.StoreError, "not valid JSON"):
                ACCOUNTS.load_store(path)

    def test_a_store_without_an_accounts_list_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            path.write_text(json.dumps({"version": 1}), encoding="utf-8")
            with self.assertRaisesRegex(ACCOUNTS.StoreError, "credential store"):
                ACCOUNTS.load_store(path)

    def test_saving_round_trips_and_leaves_the_file_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store" / "accounts.json"
            (path.parent).mkdir()
            (path.parent / ".gitignore").write_text("*\n", encoding="utf-8")
            written = {
                "version": 1,
                "accounts": [{"alias": "personal", "username": "diego", "key": "abc123"}],
            }
            ACCOUNTS.save_store(written, path)
            self.assertEqual(ACCOUNTS.load_store(path)["accounts"], written["accounts"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_saving_leaves_no_temporary_file_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            (Path(tmp) / ".gitignore").write_text("*\n", encoding="utf-8")
            ACCOUNTS.save_store({"version": 1, "accounts": []}, path)
            self.assertEqual([p.name for p in Path(tmp).iterdir() if p.name.startswith(".accounts-")], [])


class IgnorePreconditionTests(unittest.TestCase):
    """The store sits inside the repo, so the ignore rule is the protection."""

    def test_the_real_store_path_is_ignored_by_git(self) -> None:
        # Guards the arrangement itself: if the .gitignore ever stops covering
        # the store, this fails here rather than in a commit that leaks a token.
        ACCOUNTS.assert_ignored(ACCOUNTS.STORE_PATH)

    def test_writing_is_refused_where_git_would_track_the_file(self) -> None:
        tracked = REPOSITORY_ROOT / "tests" / "not-a-real-store.json"
        with self.assertRaisesRegex(ACCOUNTS.StoreError, "would track"):
            ACCOUNTS.assert_ignored(tracked)
        self.assertFalse(tracked.exists())


class DiscoverTests(unittest.TestCase):
    """Adding is a pick, so something has to enumerate the choices first."""

    def test_finds_kaggle_json_files_and_names_the_account_in_each(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_credential(Path(tmp), "kaggle.json", username="diego", key="K1")
            write_credential(Path(tmp), "kaggle (1).json", username="milab", key="K2")
            found = ACCOUNTS.discover_credentials([tmp])
            self.assertEqual(sorted(e["username"] for e in found), ["diego", "milab"])
            self.assertTrue(all(e["problem"] is None for e in found))

    def test_reports_an_unreadable_candidate_instead_of_hiding_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "kaggle.json").write_text("garbage", encoding="utf-8")
            (entry,) = ACCOUNTS.discover_credentials([tmp])
            self.assertIsNone(entry["username"])
            self.assertIn("not valid JSON", entry["problem"])

    def test_ignores_unrelated_json_and_missing_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_credential(Path(tmp), "settings.json", username="diego", key="K1")
            self.assertEqual(ACCOUNTS.discover_credentials([tmp, tmp + "/nope"]), [])

    def test_the_same_file_reached_twice_is_offered_once(self) -> None:
        # Two search folders can resolve to the same place; the same credential
        # listed twice would read as two accounts to add.
        with tempfile.TemporaryDirectory() as tmp:
            write_credential(Path(tmp), "kaggle.json", username="diego", key="K1")
            found = ACCOUNTS.discover_credentials([tmp, tmp + "/"])
            self.assertEqual(len(found), 1)

    def test_never_carries_the_key_out_of_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_credential(Path(tmp), "kaggle.json", username="diego", key="SECRET")
            self.assertNotIn("SECRET", json.dumps(ACCOUNTS.discover_credentials([tmp])))


class InteractiveEntryTests(unittest.TestCase):
    """The way in when no file exists — and the one place it must not work."""

    def test_refuses_when_stdin_is_not_a_terminal(self) -> None:
        # Run from an agent's shell there is nobody to type and nothing to
        # suppress the echo, so it must fail rather than find a way.
        with self.assertRaisesRegex(ACCOUNTS.UsageError, "real terminal"):
            ACCOUNTS.read_credential_interactively()

    def test_there_is_no_flag_that_takes_a_key_on_the_command_line(self) -> None:
        # A secret in argv is in the process list and the shell history. If this
        # ever fails, someone added the convenience that undoes the whole design.
        source = Path(ACCOUNTS.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"--key"', source)


class AliasTests(unittest.TestCase):
    def test_accepts_ordinary_kaggle_usernames_as_aliases(self) -> None:
        for alias in ("diego", "diego-lab", "diego_2", "d.p"):
            self.assertTrue(ACCOUNTS.ALIAS_PATTERN.match(alias), alias)

    def test_rejects_aliases_that_would_be_ambiguous_or_unusable(self) -> None:
        for alias in ("", "with space", "slash/es", "a" * 65):
            self.assertFalse(ACCOUNTS.ALIAS_PATTERN.match(alias), alias)


if __name__ == "__main__":
    unittest.main()
