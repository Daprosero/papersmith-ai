"""The shared implementation core: its guards, and the wall against domain names.

`.claude/skills/_core/implementation/` is what every implementation skill needs
and none of them owns. Three of the things it holds -- the workspace guard, the
dirty-worktree guard, and the migration's prefix mapping -- had NO test before
this file: replacing each with a permissive stub left all 1440 tests green, which
is the same signal as deleting them. They are shared now, so a silent break would
reach every skill that imports them rather than just the one that wrote them.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORE = REPOSITORY_ROOT / ".claude/skills/_core/implementation"
sys.path.insert(0, str(CORE))

import impl_availability  # noqa: E402
import impl_execution_strategy  # noqa: E402
import impl_gitops  # noqa: E402
import impl_guards  # noqa: E402
import impl_layout  # noqa: E402
import impl_position  # noqa: E402
import impl_references  # noqa: E402
import impl_refusals  # noqa: E402

CLI_SCRIPT = REPOSITORY_ROOT / ".claude/skills/proposal-implementation/scripts/implementation_cli.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class WorkspaceGuardTests(unittest.TestCase):
    """`resolve_target` is the only thing between generated code and the forge."""

    def setUp(self) -> None:
        impl_layout.WORKSPACE.mkdir(parents=True, exist_ok=True)
        self.inside = Path(tempfile.mkdtemp(prefix="_core_guard_",
                                            dir=impl_layout.WORKSPACE))
        self.addCleanup(shutil.rmtree, self.inside, True)
        self.outside = Path(tempfile.mkdtemp(prefix="_core_guard_outside_"))
        self.addCleanup(shutil.rmtree, self.outside, True)

    def test_a_target_outside_the_workspace_is_refused(self):
        _git(self.outside, "init", "-q")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.resolve_target(str(self.outside))
        self.assertEqual(caught.exception.code, "OUTSIDE_WORKSPACE")

    def test_a_directory_that_is_not_a_repository_is_refused(self):
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.resolve_target(str(self.inside))
        self.assertEqual(caught.exception.code, "NOT_A_GIT_REPO")

    def test_a_repository_inside_the_workspace_resolves(self):
        _git(self.inside, "init", "-q")
        self.assertEqual(impl_guards.resolve_target(str(self.inside)),
                         self.inside.resolve())


class DirtyWorktreeGuardTests(unittest.TestCase):
    """Never mutate a repository whose state the user has not committed."""

    def setUp(self) -> None:
        impl_layout.WORKSPACE.mkdir(parents=True, exist_ok=True)
        self.repo = Path(tempfile.mkdtemp(prefix="_core_dirty_",
                                          dir=impl_layout.WORKSPACE))
        self.addCleanup(shutil.rmtree, self.repo, True)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "a.txt").write_text("one\n")
        _git(self.repo, "add", "a.txt")
        _git(self.repo, "commit", "-qm", "one")

    def test_a_clean_worktree_passes(self):
        self.assertIsNone(impl_guards.require_clean_worktree(self.repo))

    def test_an_uncommitted_change_is_refused(self):
        (self.repo / "a.txt").write_text("two\n")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.require_clean_worktree(self.repo)
        self.assertEqual(caught.exception.code, "DIRTY_WORKTREE")

    def test_an_untracked_file_is_refused_too(self):
        """Untracked counts: a migration that overwrites one destroys it."""
        (self.repo / "b.txt").write_text("new\n")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.require_clean_worktree(self.repo)
        self.assertEqual(caught.exception.code, "DIRTY_WORKTREE")

    # ---------------------------------------------------------------- ledger
    # The guard exists so the skill never clobbers somebody else's uncommitted
    # work. Its OWN append-only ledger is not that, and counting it deadlocked
    # the commands: every ledger-appending command left the tree dirty, so the
    # next clean-requiring one refused. Measured on a scratch target -- one
    # step ran, the second refused with the ledger as the only porcelain entry.

    def _ledger(self, product="Prod"):
        path = self.repo / product / ".implementation" / "position.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def test_an_appended_ledger_alone_does_not_make_the_tree_dirty(self):
        ledger = self._ledger()
        ledger.write_text('{"kind": "step"}\n')
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "ledger")
        ledger.write_text('{"kind": "step"}\n{"kind": "step"}\n')
        self.assertIsNone(impl_guards.require_clean_worktree(self.repo))

    def test_an_untracked_ledger_does_not_make_the_tree_dirty_either(self):
        """Whether the ledger is committed is a separate, open question. The
        guard must answer the same way under both, or a repository that
        ignores it and one that commits it would disagree about whether a
        command may run.

        The product directory is committed first on purpose. Git collapses an
        untracked tree to its topmost new directory, so a product that exists
        only as this ledger reports `?? Prod/` and never names the ledger at
        all -- see the test below, which locks that case deliberately.
        """
        product = self.repo / "Prod"
        product.mkdir()
        (product / "kept.txt").write_text("real\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "product")
        self._ledger().write_text('{"kind": "step"}\n')
        self.assertIsNone(impl_guards.require_clean_worktree(self.repo))

    def test_a_wholly_untracked_product_directory_is_still_refused(self):
        """Measured, not assumed: git reports `?? Prod/` when nothing under
        the product is tracked yet, so the ledger is never named. Refusing is
        the right answer -- an entire new directory is real uncommitted work,
        whatever it happens to contain.
        """
        self._ledger().write_text('{"kind": "step"}\n')
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.require_clean_worktree(self.repo)
        self.assertEqual(caught.exception.code, "DIRTY_WORKTREE")

    def test_real_work_beside_a_dirty_ledger_is_still_refused(self):
        self._ledger().write_text('{"kind": "step"}\n')
        (self.repo / "a.txt").write_text("two\n")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.require_clean_worktree(self.repo)
        self.assertEqual(caught.exception.code, "DIRTY_WORKTREE")

    def test_a_path_merely_starting_with_the_ledger_name_is_not_excused(self):
        """Component match, never substring: `.implementationX/` is somebody
        else's directory that happens to share a prefix.
        """
        sibling = self.repo / ".implementationX"
        sibling.mkdir()
        (sibling / "note.txt").write_text("mine\n")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.require_clean_worktree(self.repo)
        self.assertEqual(caught.exception.code, "DIRTY_WORKTREE")

    def test_a_rename_out_of_the_ledger_directory_is_not_excused(self):
        """Both sides, because a half-matched rename moves real work."""
        ledger = self._ledger()
        ledger.write_text('{"kind": "step"}\n')
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "ledger")
        moved = self.repo / "escaped.jsonl"
        ledger.rename(moved)
        _git(self.repo, "add", "-A")
        with self.assertRaises(impl_refusals.Refused) as caught:
            impl_guards.require_clean_worktree(self.repo)
        self.assertEqual(caught.exception.code, "DIRTY_WORKTREE")


class PrefixMappingTests(unittest.TestCase):
    """Moves break paths exactly as renames do, and the mapping is what fixes them."""

    def test_a_rename_maps_directly(self):
        self.assertEqual(
            impl_references.prefix_mappings([{"from": "Alpha", "to": "Beta"}], []),
            [("Alpha", "Beta")])

    def test_a_move_that_only_nests_yields_the_nesting_prefix(self):
        """`Cat/x.csv -> Name/Cat/x.csv` means `Cat -> Name/Cat`, not a rename."""
        self.assertEqual(
            impl_references.prefix_mappings(
                [], [{"from": "Cat/x.csv", "to": "Name/Cat/x.csv"}]),
            [("Cat", "Name/Cat")])

    def test_an_ambiguous_prefix_is_dropped_rather_than_guessed(self):
        """Two destinations for one prefix: a wrong rewrite beats no rewrite."""
        self.assertEqual(
            impl_references.prefix_mappings(
                [{"from": "Alpha", "to": "Beta"}, {"from": "Alpha", "to": "Gamma"}], []),
            [])


class CoreNamesNoDomainTests(unittest.TestCase):
    """The core that names one domain is a core only one skill can use.

    Read from the CLI that owns them rather than restated here, so a skill that
    adds a product directory is held to the same wall without editing this test.
    """

    @staticmethod
    def _cli_module():
        spec = importlib.util.spec_from_file_location("impl_cli_for_lock", CLI_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_no_core_file_names_a_product_directory_or_source_root(self):
        cli = self._cli_module()
        owned = {*cli.PRODUCT_DIRS, *(root.rstrip("/") for root in cli.SOURCE_ROOTS)}
        self.assertGreater(len(owned), 3, "the CLI declares no layout to be held to")
        leaks = []
        for path in sorted(CORE.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for name in sorted(owned):
                if name in text:
                    leaks.append(f"{path.name} names {name!r}")
        self.assertEqual(leaks, [], "the core must take these from its caller")

    def test_the_core_resolves_the_repository_root_it_actually_lives_in(self):
        """`parents[4]` is a count, and a count is silent when a file moves.

        It happens to be the same five components the CLI walked before this
        core existed -- a coincidence of two directory names, not a rule.
        """
        self.assertEqual(impl_layout.FORGE_ROOT, REPOSITORY_ROOT)
        self.assertTrue((impl_layout.FORGE_ROOT / ".claude").is_dir())
        self.assertEqual(impl_layout.WORKSPACE,
                         REPOSITORY_ROOT / "implementations")


class UnbackedTickTests(unittest.TestCase):
    """A tick nobody measured is an assertion; a blank box nobody measured is
    not. `derive()` could not tell them apart.

    Measured before this key existed: an item with `mark="x"` and a witness
    this invocation carries no evidence for produced `derived=None,
    satisfied=None, disagrees=False` -- byte for byte the same result as the
    identical item with `mark=" "`. Every reader downstream therefore read the
    unbacked claim and the honest silence as one state.

    `disagrees` cannot be the place this is caught, and deliberately is not:
    it compares a mark against a measurement, and the whole defect is that
    there is no measurement to compare against.
    """

    def _one(self, mark, evidence):
        items = [{"ordinal": 1, "mark": mark, "text": "step",
                  "witness": {"kind": "shard", "operand": "s0"}}]
        return impl_position.derive(items, evidence)[0]

    def test_an_unmeasured_tick_and_an_unmeasured_blank_are_no_longer_identical(self):
        """The finding, stated as the comparison that produced it."""
        ticked = self._one("x", {})
        blank = self._one(" ", {})

        self.assertIsNone(ticked["satisfied"])
        self.assertIsNone(blank["satisfied"])
        self.assertTrue(ticked["unbacked"])
        self.assertFalse(blank["unbacked"])
        self.assertNotEqual(ticked, blank)

    def test_an_unbacked_tick_is_not_reported_as_a_disagreement(self):
        """An `x` over nothing contradicts no measurement -- there is none to
        contradict. Folding this into `disagrees` would claim evidence that
        says otherwise, which is a different and untrue statement."""
        self.assertFalse(self._one("x", {})["disagrees"])

    def test_a_measured_tick_is_never_unbacked_whichever_way_it_reads(self):
        """The pole. Without it `unbacked` could be firing on every ticked
        item and nothing here would notice."""
        agreeing = self._one("x", {"shardsArrived": ["s0"]})
        self.assertIs(agreeing["satisfied"], True)
        self.assertFalse(agreeing["unbacked"])
        self.assertFalse(agreeing["disagrees"])

        contradicted = self._one("x", {"shardsArrived": ["other"]})
        self.assertIs(contradicted["satisfied"], False)
        self.assertFalse(contradicted["unbacked"],
                         "a measurement that says otherwise is a disagreement, "
                         "not an unbacked assertion")
        self.assertTrue(contradicted["disagrees"])

    def test_a_leveled_item_off_the_ladder_is_unbacked_too(self):
        """`satisfied is None` reaches a leveled item by a second route -- a
        rung was derived but this pass's target names none -- and a tick over
        that is exactly as unbacked as a tick over no evidence at all."""
        items = [{"ordinal": 1, "mark": "x", "text": "step",
                  "witness": {"kind": "shard", "operand": "s0",
                              "twostate": False}}]
        result = impl_position.derive(
            items, {"shardsArrived": ["s0"], "levels": ["one", "two"]})[0]

        self.assertEqual(result["derived"], "two")
        self.assertIsNone(result["satisfied"], "no targetLevel to compare against")
        self.assertTrue(result["unbacked"])


class ShardCurrencyTests(unittest.TestCase):
    """An arrived shard was trusted without asking what code produced it.

    Measured before this: `evidence={"shardsArrived": ["s00"]}` placed a
    leveled `@shard` item on the TOP rung, on the strength of a folder
    existing. `_derive_notebook_level` beside it already refuses to attribute
    a rung until the report says it read current sources -- "we have not
    looked with current eyes" -- and the two were asymmetric with nothing to
    justify it.

    `shardsCurrent` is the caller's answer to the same question for shards.
    The forge never learns which stamp field carries a shard's code identity;
    the repository names it and the caller does the comparing, so everything
    here is a list of names this module was handed.
    """

    LEVELS = ["one", "two", "three"]

    def _item(self, twostate):
        return [{"ordinal": 1, "mark": " ", "text": "step",
                 "witness": {"kind": "shard", "operand": "s0",
                             "twostate": twostate}}]

    def _derive(self, twostate, evidence):
        return impl_position.derive(
            self._item(twostate), {"levels": self.LEVELS,
                                   "targetLevel": "three", **evidence})[0]

    def test_no_currency_declared_leaves_arrival_deciding_exactly_as_before(self):
        """The compatibility half, and the one that must not move: a target
        that never named a stamp field has said nothing this could check, and
        an absent `shardsCurrent` therefore has to read exactly as it did
        before the key existed."""
        two_state = self._derive(True, {"shardsArrived": ["s0"]})
        self.assertIs(two_state["derived"], True)

        leveled = self._derive(False, {"shardsArrived": ["s0"]})
        self.assertEqual(leveled["derived"], "three")

    def test_an_arrived_and_current_shard_reads_as_it_always_did(self):
        """The pole for the two tests below: declaring the field changes
        nothing at all for a shard that answers it."""
        evidence = {"shardsArrived": ["s0"], "shardsCurrent": ["s0"]}
        self.assertIs(self._derive(True, evidence)["derived"], True)
        self.assertEqual(self._derive(False, evidence)["derived"], "three")

    def test_an_arrived_but_stale_shard_is_unmeasured_and_never_the_floor(self):
        """The finding. `None` and the floor rung are different facts: the
        floor says a step has not started, and this shard demonstrably ran --
        we simply cannot say it ran this code."""
        evidence = {"shardsArrived": ["s0"], "shardsCurrent": []}
        self.assertIsNone(self._derive(True, evidence)["derived"])

        leveled = self._derive(False, evidence)
        self.assertIsNone(leveled["derived"])
        self.assertNotEqual(leveled["derived"], self.LEVELS[0])

    def test_a_shard_that_never_arrived_is_still_definitely_not_there(self):
        """Currency answers a question about a shard that came back. One that
        never came back is answered by arrival alone, as before -- `False`
        two-state, the floor rung leveled, both definite."""
        evidence = {"shardsArrived": ["other"], "shardsCurrent": ["other"]}
        self.assertIs(self._derive(True, evidence)["derived"], False)
        self.assertEqual(self._derive(False, evidence)["derived"], self.LEVELS[0])

    def test_the_currency_it_used_is_named_in_measured_by(self):
        """A verdict a reader cannot trace back to what produced it is a
        verdict they have to take on faith."""
        with_currency = self._derive(
            True, {"shardsArrived": ["s0"], "shardsCurrent": ["s0"]})
        self.assertIn("shardsCurrent", with_currency["measuredBy"])
        without = self._derive(True, {"shardsArrived": ["s0"]})
        self.assertNotIn("shardsCurrent", without["measuredBy"])


class RecordCurrencyTests(unittest.TestCase):
    """A record found on disk was trusted without asking what code produced
    it -- `ShardCurrencyTests`'s own finding, one level up: `@shard` already
    reads currency, `@record` did not. A `ceilings.json` written by code this
    repository has since moved past used to tick its rung today, on the
    strength of `search.recordFound` alone.

    `recordCurrent` is `search_state()`'s answer to the identical question
    for a record: `None` when the target never declared `search.currentWhen`
    (the default, unchanged); otherwise a real `True`/`False`, computed by
    reading the record's own file at that declared dotted path and comparing
    it against the digest of the code as it stands. This module never learns
    which stamp field carries a record's code identity or reads a file
    itself -- it only reads the dict `search_state()` was already handed.
    """

    def _item(self):
        return [{"ordinal": 1, "mark": " ", "text": "step",
                 "witness": {"kind": "record", "operand": None}}]

    def _derive(self, evidence):
        return impl_position.derive(self._item(), evidence)[0]

    def test_no_currency_declared_leaves_arrival_deciding_exactly_as_before(self):
        """The compatibility half, and the one that must not move: a target
        that never named a stamp field has said nothing this could check,
        and an absent `recordCurrent` therefore has to read exactly as it
        did before the key existed."""
        result = self._derive({"search": {"recordFound": True}, "requiredScale": {}})
        self.assertIs(result["derived"], True)

    def test_a_found_and_current_record_reads_as_it_always_did(self):
        """The pole for the test below: declaring the field changes nothing
        at all for a record that answers it."""
        evidence = {"search": {"recordFound": True, "recordCurrent": True},
                    "requiredScale": {}}
        self.assertIs(self._derive(evidence)["derived"], True)

    def test_a_found_but_stale_record_is_unmeasured_and_never_false(self):
        """The finding. A record written by code this repository has since
        moved past cannot attribute a tick to anything the current code
        did -- `None`, not `False`: the file exists, we simply cannot say
        it speaks for this code."""
        evidence = {"search": {"recordFound": True, "recordCurrent": False},
                    "requiredScale": {}}
        self.assertIsNone(self._derive(evidence)["derived"])

    def test_a_record_that_never_arrived_is_still_definitely_not_there(self):
        """Currency answers a question about a record that was found. One
        that was never found is answered by `recordFound` alone, as before
        -- definite `False`, whatever `recordCurrent` says."""
        evidence = {"search": {"recordFound": False, "recordCurrent": False},
                    "requiredScale": {}}
        self.assertIs(self._derive(evidence)["derived"], False)

    def test_currency_composes_with_required_scale(self):
        """A current record still has to satisfy a declared scale --
        currency answers "whose code wrote this", never "how much of it"."""
        short = {"search": {"recordFound": True, "recordCurrent": True,
                            "scaleSatisfied": False},
                 "requiredScale": {"seeds": 30}}
        self.assertIs(self._derive(short)["derived"], False)

        met = {"search": {"recordFound": True, "recordCurrent": True,
                          "scaleSatisfied": True},
               "requiredScale": {"seeds": 30}}
        self.assertIs(self._derive(met)["derived"], True)

    def test_the_currency_it_used_is_named_in_measured_by(self):
        with_currency = self._derive(
            {"search": {"recordFound": True, "recordCurrent": True},
             "requiredScale": {}})
        self.assertIn("recordCurrent", with_currency["measuredBy"])
        without = self._derive(
            {"search": {"recordFound": True}, "requiredScale": {}})
        self.assertNotIn("recordCurrent", without["measuredBy"])


class NamedRecordLevelTests(unittest.TestCase):
    """`@record:level <name>` -- design D2/D4: `_derive_record_level` routes
    a NAMED operand through the identical `_record_scale_level` arithmetic
    the `search` block's own bare `@record:level` already uses, fed
    `evidence["records"][name]` (`named_records_state()`'s own shape,
    `implementation_cli.py`) instead of `evidence["search"]`.
    """

    LEVELS = ["floor", "pilot", "full"]

    def _item(self, operand):
        return [{"ordinal": 1, "mark": " ", "text": "reach the record",
                 "witness": {"kind": "record", "operand": operand,
                             "twostate": False}}]

    def _derive(self, operand, evidence):
        return impl_position.derive(
            self._item(operand), {"levels": self.LEVELS, **evidence})[0]

    def test_a_named_record_absent_from_declared_records_derives_none_not_false(self):
        """The spec requirement, stated as arithmetic: a name absent from a
        declared `__records__` is `None` (unmeasured), never `False` -- the
        same doctrine an unlisted `@notebook` path already reads."""
        result = self._derive("main", {"records": {}})
        self.assertIsNone(result["derived"])

    def test_a_named_record_not_found_reads_the_floor(self):
        evidence = {"records": {"main": {
            "recordFound": False, "recordCurrent": None,
            "scaleSatisfied": None, "requiredScale": {}}}}
        result = self._derive("main", evidence)
        self.assertEqual(result["derived"], "floor")

    def test_a_named_record_at_full_declared_scale_reads_the_top(self):
        evidence = {"records": {"main": {
            "recordFound": True, "recordCurrent": None,
            "scaleSatisfied": True, "requiredScale": {"seeds": 3}}}}
        result = self._derive("main", evidence)
        self.assertEqual(result["derived"], "full")

    def test_a_named_record_short_of_declared_scale_reads_one_rung_under_the_top(self):
        evidence = {"records": {"main": {
            "recordFound": True, "recordCurrent": None,
            "scaleSatisfied": False, "requiredScale": {"seeds": 30}}}}
        result = self._derive("main", evidence)
        self.assertEqual(result["derived"], "pilot")

    def test_a_bare_operand_less_leveled_record_still_reads_the_search_block(self):
        """`operand is None` -- the grammar that predates `__records__`
        entirely -- keeps the byte-identical search-block fallthrough (spec
        "existing instances keep working"), even when `evidence["records"]`
        carries entries a caller could have routed through instead."""
        evidence = {"search": {"recordFound": True}, "requiredScale": {},
                    "records": {"main": {"recordFound": False, "recordCurrent": None,
                                        "scaleSatisfied": None, "requiredScale": {}}}}
        result = self._derive(None, evidence)
        self.assertEqual(result["derived"], "full")

    def test_a_named_record_and_the_search_block_read_independently(self):
        """Two different facts under one kind: the named entry disagrees
        with the search block, and each `@record:level` item reads only its
        own operand's evidence."""
        evidence = {
            "search": {"recordFound": False}, "requiredScale": {},
            "records": {"main": {"recordFound": True, "recordCurrent": None,
                                 "scaleSatisfied": True, "requiredScale": {}}}}
        named = self._derive("main", evidence)
        bare = self._derive(None, evidence)
        self.assertEqual(named["derived"], "full")
        self.assertEqual(bare["derived"], "floor")

    def test_the_operand_it_read_is_named_in_measured_by(self):
        evidence = {"records": {"main": {
            "recordFound": True, "recordCurrent": None,
            "scaleSatisfied": True, "requiredScale": {}}}}
        result = self._derive("main", evidence)
        self.assertIn("main", result["measuredBy"])

    # --- B3's required mutation: measured_by binding, never discarded -----

    def test_a_named_records_measured_by_names_its_own_binding_never_the_bare_one(self):
        """**Required mutation lock** (design D2, "three explicit bindings").
        `derive`'s own bare `@record:level` branch and `_derive_record_level`
        both call the identical `_record_scale_level`, each passing its OWN
        `measured_by` string -- swapping which string binds to which call
        site is the mutation this proves against: a weaker lock that only
        asserted the returned RUNG (never `measuredBy`) would survive that
        swap silently, since both bindings compute the identical rung
        arithmetic and would still return the same rung either way."""
        evidence = {"search": {"recordFound": True}, "requiredScale": {},
                    "records": {"main": {"recordFound": True, "recordCurrent": None,
                                         "scaleSatisfied": True, "requiredScale": {}}}}
        named = self._derive("main", evidence)
        bare = self._derive(None, evidence)
        self.assertEqual(named["measuredBy"],
                         "records[main].recordFound+scaleSatisfied")
        self.assertEqual(bare["measuredBy"], "search.recordFound+scaleSatisfied")
        self.assertNotEqual(named["measuredBy"], bare["measuredBy"])

    def test_derive_notebook_level_reports_its_own_measured_by_unchanged(self):
        """B3's other call site: the notebook-level path still returns
        `_derive_notebook_level`'s own fixed string, byte-identical to
        before this refactor -- proving the newly-threaded `measured_by`
        kwarg did not leak the record binding's string into this deriver."""
        evidence = {"notebooks": {"reports": [
            {"notebook": "n.ipynb", "status": "executed", "sourcesMatch": True}]},
                    "search": {"recordFound": True}, "requiredScale": {}}
        rung, measured_by = impl_position._derive_notebook_level(
            evidence, "n.ipynb", self.LEVELS)
        self.assertEqual(rung, "full")
        self.assertEqual(
            measured_by,
            "notebooks.reports[n.ipynb].sourcesMatch+search.scaleSatisfied")


class StepDeriveTests(unittest.TestCase):
    """`_derive_step` -- design "One field on the existing `step` event, not
    a sibling kind": a plain dict reader over `evidence["stepVerdicts"][operand]`,
    the same shape `_derive_rehearsal` already has against `smokeReady`.
    Digest currency and the ledger fold are the caller's job
    (`_step_verdicts`, `implementation_cli.py`); this module learns no path,
    no ledger, no digest math -- `_derive_shard`'s stated layering, one level
    up.
    """

    def _item(self, twostate=True):
        return [{"ordinal": 1, "mark": " ", "text": "run the suite",
                 "witness": {"kind": "step", "operand": "run_suite",
                             "twostate": twostate}}]

    def _derive(self, evidence):
        return impl_position.derive(self._item(), evidence)[0]

    def test_step_joins_witness_kinds_and_operand_required_kinds(self):
        """`@step <name>` is operand-required, the same class as
        `notebook`/`rehearsal`/`shard` -- never the operand-less `record`."""
        self.assertIn("step", impl_position.WITNESS_KINDS)
        self.assertIn("step", impl_position.OPERAND_REQUIRED_KINDS)

    def test_a_step_never_run_derives_unmeasured(self):
        """No key for the operand in `stepVerdicts` -- either the step never
        ran, or the ledger holds no `kind: "step"` event for it at all."""
        self.assertIsNone(self._derive({"stepVerdicts": {}})["derived"])

    def test_a_returned_and_current_step_derives_true(self):
        evidence = {"stepVerdicts": {"run_suite": True}}
        self.assertIs(self._derive(evidence)["derived"], True)

    def test_a_raised_step_derives_false_never_none(self):
        """The mutation this locks against: a dict reader that special-cases
        `False` into `None` (treating "the suite failed" as "unmeasured") is
        exactly the collapse this revision's derivers refuse elsewhere --
        `derive()`'s own docstring names it for the leveled arm; this is the
        two-state twin of that same trap."""
        evidence = {"stepVerdicts": {"run_suite": False}}
        self.assertIs(self._derive(evidence)["derived"], False)

    def test_a_stale_step_derives_unmeasured_not_false(self):
        """`_step_verdicts` (`implementation_cli.py`) folds a stale digest to
        `None` before this reader ever sees it -- `_derive_step` merely
        preserves whatever tri-state its caller already decided, same as
        `stepVerdicts` holding no key at all."""
        evidence = {"stepVerdicts": {"run_suite": None}}
        self.assertIsNone(self._derive(evidence)["derived"])

    def test_the_operand_it_read_is_named_in_measured_by(self):
        evidence = {"stepVerdicts": {"run_suite": True}}
        self.assertIn("run_suite", self._derive(evidence)["measuredBy"])


class WitnessNotLevelableTests(unittest.TestCase):
    """`derive()`'s lookup guard -- design "The guard lives at the lookup,
    not as a fourth special case": one shared `.get()`-based resolver at both
    `_DERIVERS[kind]` and `_LEVEL_DERIVERS[kind]`, replacing a bare subscript
    that raised an uncaught `KeyError` for any kind missing from the table it
    hit.

    **Reachability, honestly** (design, verbatim): the leveled arm is
    reachable from real markdown -- `@step:level <name>`, since `"step"`
    joins `WITNESS_KINDS` with no `_LEVEL_DERIVERS` entry. The two-state arm
    is reachable only from a direct `derive()` call built by hand:
    `parse_items` (`implementation_cli.py`) never emits an item whose kind is
    not in `WITNESS_KINDS`, and every `WITNESS_KINDS` member besides
    `record` (special-cased above the lookup) now has a `_DERIVERS` entry.
    That test is structural insurance against a future kind added to
    `WITNESS_KINDS` without a matching deriver, not a claim that today's
    grammar can reach it.
    """

    def test_a_leveled_step_item_is_refused_not_a_keyerror(self):
        """The scenario the spec names directly: `@step:level <name>` has no
        rung to report. Mutation: reverting the `.get()` guard to a bare
        `_LEVEL_DERIVERS[kind]` subscript raises an uncaught `KeyError`
        instead of a classified `Refused` -- this assertion only passes
        against the caught, classified exception, and its `detail` must
        still name a kind that DOES carry a rung."""
        item = [{"ordinal": 1, "mark": " ", "text": "run the suite",
                 "witness": {"kind": "step", "operand": "run_suite",
                             "twostate": False}}]
        with self.assertRaises(impl_refusals.Refused) as ctx:
            impl_position.derive(item, {"levels": ["one", "two"],
                                        "targetLevel": "two"})
        self.assertEqual(ctx.exception.code, "POSITION_WITNESS_NOT_LEVELABLE")
        self.assertIn("notebook", ctx.exception.detail)

    def test_the_two_state_lookup_guard_is_structural_not_markdown_reachable(self):
        """Every real kind (`record` special-cased, `notebook`/`rehearsal`/
        `shard`/`step` all present in `_DERIVERS`) already resolves on the
        two-state arm -- this constructs the one input `parse_items` could
        never produce, to prove the same guard exists there too."""
        item = [{"ordinal": 1, "mark": " ", "text": "step",
                 "witness": {"kind": "not_a_real_kind", "operand": "x",
                             "twostate": True}}]
        with self.assertRaises(impl_refusals.Refused) as ctx:
            impl_position.derive(item, {})
        self.assertEqual(ctx.exception.code, "POSITION_WITNESS_NOT_LEVELABLE")


class AttainedLevelTests(unittest.TestCase):
    """`attained_level()` — which rung the evidence currently REACHES, as
    opposed to the rung a header says a pass AIMS at.

    Those are two different facts and the position grammar carried only one
    field for them. The predicate is defined against `derive` itself, exactly
    as the rung-skip rule already was: the highest rung at which every leveled
    item grades `satisfied is True`. Nothing here re-implements that
    arithmetic, so "attained" means precisely what "satisfied" means one level
    down, and it means it for whatever witness kinds exist tomorrow too.

    The ladder names are this suite's own invention. The core holds no rung
    vocabulary — only the ordered list a target declared.
    """

    LADDER = ["one", "two", "three"]

    def _shard_item(self):
        return [{"ordinal": 1, "mark": " ", "text": "distribute",
                 "witness": {"kind": "shard", "operand": "s1",
                             "twostate": False}}]

    def _evidence(self, **overrides):
        evidence = {"levels": list(self.LADDER), "shardsArrived": None,
                    "shardsCurrent": None}
        evidence.update(overrides)
        return evidence

    def test_an_unmeasured_leveled_item_attains_no_rung_at_all(self):
        """Not even the floor. `derived is None` means nobody looked, and the
        floor is a reading like any other — folding "we did not look" into it
        is the exact collapse `derive` refuses one level down."""
        self.assertIsNone(
            impl_position.attained_level(self._shard_item(), self._evidence()))

    def test_the_highest_rung_every_leveled_item_reaches_is_the_answer(self):
        """A shard answer that arrived puts the witness on the floor rung, and
        the floor is where attainment stops — the rung above is not reached
        just because the ladder has one."""
        self.assertEqual(
            impl_position.attained_level(
                self._shard_item(), self._evidence(shardsArrived=[])),
            "one")

    def test_attainment_is_the_weakest_leveled_item_not_the_strongest(self):
        """Two leveled items, one measured and one not. A predicate that
        reported the best rung anybody reached would answer `'one'` here and
        exempt a whole rung on the strength of a witness that says nothing."""
        items = self._shard_item() + [
            {"ordinal": 2, "mark": " ", "text": "rehearse",
             "witness": {"kind": "rehearsal", "operand": "job-a",
                         "twostate": False}}]
        self.assertIsNone(
            impl_position.attained_level(items, self._evidence(shardsArrived=[])))

    def test_two_state_items_never_hold_a_rung_back(self):
        """They are graded without the ladder and read identically at every
        rung, so they carry no information about which one was reached — the
        same exclusion the rung-skip rule states for itself. An unsatisfied
        two-state item beside a satisfied leveled one must not drag attainment
        to `None`, or whole-sequence completeness would be wearing this
        predicate's name."""
        items = self._shard_item() + [
            {"ordinal": 2, "mark": " ", "text": "rehearse",
             "witness": {"kind": "rehearsal", "operand": "job-a",
                         "twostate": True}}]
        self.assertEqual(
            impl_position.attained_level(items, self._evidence(shardsArrived=[])),
            "one")

    def test_a_sequence_with_no_leveled_item_attains_the_whole_ladder(self):
        """Vacuous truth, and deliberately so: with nothing that could fail to
        reach a rung, every rung grades attained and the answer is the top.
        This is what keeps a two-state-only target exactly as unconstrained by
        the rung rule as it was before the rule existed."""
        items = [{"ordinal": 1, "mark": " ", "text": "rehearse",
                  "witness": {"kind": "rehearsal", "operand": "job-a",
                              "twostate": True}}]
        self.assertEqual(
            impl_position.attained_level(items, self._evidence()), "three")

    def test_a_target_with_no_declared_ladder_attains_nothing(self):
        """`levels == []` is not a ladder with one rung on it; it is the
        absence of a ladder, and there is no name to answer with."""
        self.assertIsNone(
            impl_position.attained_level(
                self._shard_item(), self._evidence(levels=[])))

    def test_the_caller_s_own_target_level_does_not_change_the_answer(self):
        """Attainment is a property of the evidence, never of the pass reading
        it. `derive` grades `satisfied` against `evidence["targetLevel"]`, so a
        predicate that forgot to override it per candidate rung would report
        whatever the caller happened to be aiming at."""
        for aim in (None, "one", "two", "three"):
            with self.subTest(targetLevel=aim):
                self.assertEqual(
                    impl_position.attained_level(
                        self._shard_item(),
                        self._evidence(shardsArrived=[], targetLevel=aim)),
                    "one")


class LaunchAvailableTests(unittest.TestCase):
    """The one rule `cmd_gate` and the state-derived action menu's publisher
    must agree on (spec "One shared availability rule"), exercised over
    hand-built facts rather than a real target -- the shape this module
    itself takes as arguments, nothing more.
    """

    #: Item 1 already ticked (a record witness, unrelated to the job under
    #: test); item 2 names the job's own rehearsal witness, reached and
    #: ticked. Every test starts from this fully-satisfied shape and moves
    #: exactly one fact away from it.
    SEQUENCE = [
        {"ordinal": 1, "mark": "x", "witness": {"kind": "record", "operand": None}},
        {"ordinal": 2, "mark": "x", "witness": {"kind": "rehearsal", "operand": "job-a"}},
    ]

    def _call(self, **overrides):
        facts = {"status": "complete", "unbacked": [], "disagreements": [],
                 "sequence": self.SEQUENCE, "ready": True, "job": "job-a",
                 "shards_declared": True,
                 # A ladder too short for the rung threshold to apply at
                 # all (spec "reachability preconditions") — every test in
                 # this class predates the rung threshold and asserts facts
                 # about the six checks above it; overriding `levels`/
                 # `attained_level` explicitly is how the threshold's own
                 # tests, below, opt into it.
                 "levels": [], "attained_level": None}
        facts.update(overrides)
        return impl_availability.launch_available(**facts)

    def test_an_absent_position_refuses(self):
        verdict = self._call(status="absent")
        self.assertFalse(verdict["available"])
        self.assertEqual(verdict["code"], "POSITION_ABSENT")

    def test_a_stale_position_refuses(self):
        verdict = self._call(status="stale")
        self.assertEqual(verdict["code"], "POSITION_STALE")

    def test_an_unbacked_tick_refuses_and_names_its_ordinal(self):
        verdict = self._call(unbacked=[{"ordinal": 1}])
        self.assertEqual(verdict["code"], "POSITION_UNBACKED")
        self.assertEqual(verdict["facts"]["unbackedOrdinals"], [1])

    def test_a_shard_tick_with_nothing_declared_refuses_the_honest_code(self):
        """The finding this change closes: a ticked `@shard` item whose
        location nobody declared is not `POSITION_UNBACKED` -- that code
        means "a witness was measured and found silent", and here nothing
        was ever measured at all.
        """
        verdict = self._call(
            unbacked=[{"ordinal": 1, "witness": {"kind": "shard", "operand": "s0"}}],
            shards_declared=False)
        self.assertEqual(verdict["code"], "POSITION_SHARDS_UNDECLARED")
        self.assertEqual(verdict["facts"]["undeclaredOrdinals"], [1])

    def test_a_shard_tick_with_a_declaration_still_reads_unbacked(self):
        """The same shard-kind unbacked item, `shards_declared=True`: a
        location WAS resolved and this particular tick still came back
        unmeasured (e.g. arrived but not current) -- a different fact, and
        it keeps the general code."""
        verdict = self._call(
            unbacked=[{"ordinal": 1, "witness": {"kind": "shard", "operand": "s0"}}],
            shards_declared=True)
        self.assertEqual(verdict["code"], "POSITION_UNBACKED")
        self.assertEqual(verdict["facts"]["unbackedOrdinals"], [1])

    def test_a_non_shard_unbacked_item_outranks_an_undeclared_shard_tick(self):
        """Mixed causes in one sequence: a real, general unbacked item (any
        other witness kind) is reported first, even while an undeclared
        `@shard` tick sits beside it -- the more general honesty problem
        is never masked by the narrower one."""
        verdict = self._call(
            unbacked=[
                {"ordinal": 1, "witness": {"kind": "notebook", "operand": "n"}},
                {"ordinal": 2, "witness": {"kind": "shard", "operand": "s0"}},
            ],
            shards_declared=False)
        self.assertEqual(verdict["code"], "POSITION_UNBACKED")
        self.assertEqual(verdict["facts"]["unbackedOrdinals"], [1])

    def test_a_disagreeing_item_refuses_position_disagrees(self):
        """The reproduced incident: a ticked item whose `derive()` verdict
        disagrees with the mark must refuse, not pass through as reached.
        """
        verdict = self._call(disagreements=[{"ordinal": 2}])
        self.assertFalse(verdict["available"])
        self.assertEqual(verdict["code"], "POSITION_DISAGREES")
        self.assertEqual(verdict["facts"]["disagreeingOrdinals"], [2])

    def test_omitting_disagreements_raises_typeerror(self):
        """A caller that forgets to pass `disagreements` must fail loudly at
        the call, never silently treat every item as agreeing. Calling the
        module function directly, bypassing `_call`'s own base facts.
        """
        facts = {"status": "complete", "unbacked": [], "sequence": self.SEQUENCE,
                 "ready": True, "job": "job-a"}
        with self.assertRaises(TypeError):
            impl_availability.launch_available(**facts)

    def test_readiness_never_measured_refuses_not_ready(self):
        """The row a tri-state mutation would silently drop: `ready=None`
        (never measured) must refuse exactly as `ready=False` (measured
        and failing) does. A mutation that narrows the check to `ready is
        False` alone would let this fall through as if it were ready --
        the two are different facts and this rule may not conflate them.
        """
        verdict = self._call(ready=None)
        self.assertEqual(verdict["code"], "NOT_READY")

    def test_readiness_measured_and_failing_refuses_too(self):
        verdict = self._call(ready=False)
        self.assertEqual(verdict["code"], "NOT_READY")

    def test_no_sequence_item_names_the_job_refuses_sequence_not_reached(self):
        verdict = self._call(job="job-missing")
        self.assertEqual(verdict["code"], "SEQUENCE_NOT_REACHED")
        self.assertEqual(verdict["facts"]["reason"], "no_witness")

    def test_an_earlier_open_item_refuses_sequence_not_reached(self):
        sequence = [
            {"ordinal": 1, "mark": " ", "witness": {"kind": "record", "operand": None}},
            {"ordinal": 2, "mark": "x", "witness": {"kind": "rehearsal", "operand": "job-a"}},
        ]
        verdict = self._call(sequence=sequence)
        self.assertEqual(verdict["code"], "SEQUENCE_NOT_REACHED")
        self.assertEqual(verdict["facts"]["reason"], "earlier_open")
        self.assertEqual(verdict["facts"]["earliestOpenOrdinal"], 1)
        self.assertEqual(verdict["facts"]["jobOrdinal"], 2)

    def test_every_fact_in_agreement_is_available(self):
        verdict = self._call()
        self.assertTrue(verdict["available"])
        self.assertIsNone(verdict["code"])
        self.assertEqual(verdict["facts"]["jobOrdinal"], 2)

    def test_omitting_levels_raises_typeerror(self):
        """No default, the identical doctrine `disagreements` already keeps:
        a caller that forgets `levels` fails the call itself, rather than
        silently exempting every launch from the rung threshold."""
        facts = {"status": "complete", "unbacked": [], "disagreements": [],
                 "sequence": self.SEQUENCE, "ready": True, "job": "job-a",
                 "shards_declared": True, "attained_level": None}
        with self.assertRaises(TypeError):
            impl_availability.launch_available(**facts)

    def test_omitting_attained_level_raises_typeerror(self):
        facts = {"status": "complete", "unbacked": [], "disagreements": [],
                 "sequence": self.SEQUENCE, "ready": True, "job": "job-a",
                 "shards_declared": True, "levels": []}
        with self.assertRaises(TypeError):
            impl_availability.launch_available(**facts)

    # --- the rung threshold (spec "launch-rung-gate") -----------------------

    def test_below_floor_attainment_on_a_three_rung_ladder_refuses(self):
        verdict = self._call(levels=["floor", "pilot", "full"], attained_level=None)
        self.assertFalse(verdict["available"])
        self.assertEqual(verdict["code"], "RUNG_NOT_ATTAINED")
        self.assertEqual(verdict["facts"]["requiredLevel"], "pilot")
        self.assertIsNone(verdict["facts"]["attainedLevel"])

    def test_floor_attainment_on_a_three_rung_ladder_still_refuses(self):
        """The floor itself is below `levels[-2]` ("pilot") on a three-rung
        ladder -- reaching the floor is not reaching the rung the launch
        requires."""
        verdict = self._call(levels=["floor", "pilot", "full"], attained_level="floor")
        self.assertEqual(verdict["code"], "RUNG_NOT_ATTAINED")

    def test_pilot_attainment_on_a_three_rung_ladder_is_sufficient(self):
        verdict = self._call(levels=["floor", "pilot", "full"], attained_level="pilot")
        self.assertTrue(verdict["available"])

    def test_floor_attainment_on_a_two_rung_ladder_is_sufficient(self):
        """A two-rung ladder is NOT exempt from the check -- there
        `levels[-2]` coincides with `levels[0]`, so reaching the floor is
        already reaching the rung the check demands (spec scenario "floor
        attainment on a two-rung ladder is sufficient")."""
        verdict = self._call(levels=["floor", "full"], attained_level="floor")
        self.assertTrue(verdict["available"])

    def test_no_attainment_on_a_two_rung_ladder_refuses(self):
        verdict = self._call(levels=["floor", "full"], attained_level=None)
        self.assertEqual(verdict["code"], "RUNG_NOT_ATTAINED")
        self.assertEqual(verdict["facts"]["requiredLevel"], "floor")

    def test_a_ladder_with_fewer_than_two_rungs_is_structurally_unreachable(self):
        """`len(levels) < 2`: no predecessor rung exists for a launch to
        have missed, so the check does not apply at all, even with
        `attained_level=None` -- the identical doctrine
        `_skipped_rung_detail` already keeps for a ladder too short to name
        a predecessor."""
        verdict = self._call(levels=["only"], attained_level=None)
        self.assertTrue(verdict["available"])

    def test_an_unknown_attained_level_is_read_as_off_the_ladder(self):
        """`attained_level` naming a rung absent from `levels` (a ladder
        that shrank since it was last read, most plausibly) is read
        identically to `None` -- off the ladder is off the ladder, never a
        crash and never a silent pass."""
        verdict = self._call(
            levels=["floor", "pilot", "full"], attained_level="retired-rung")
        self.assertEqual(verdict["code"], "RUNG_NOT_ATTAINED")

    def test_vacuous_attainment_at_the_top_rung_is_sufficient(self):
        """A sequence with zero leveled items attains the ladder's top rung
        vacuously (`impl_position.attained_level`'s own doctrine, unchanged
        by this rule) -- passed through here as an ordinary `attained_level`
        value, this check adds nothing new for that state and a launch
        proceeds exactly as it would for any other rung at or above the
        floor."""
        verdict = self._call(levels=["floor", "pilot", "full"], attained_level="full")
        self.assertTrue(verdict["available"])

    def test_an_existing_refusal_keeps_its_code_once_levels_and_attained_level_are_supplied(self):
        """**Required mutation lock** (design "last position cannot move an
        existing verdict"). A call that refuses `NOT_READY` today must keep
        refusing `NOT_READY` once a below-floor `levels`/`attained_level`
        pair is also supplied -- proving the rung threshold truly runs
        LAST and cannot move a verdict an earlier check already reached. A
        weaker lock that only asserted `RUNG_NOT_ATTAINED` fires when
        nothing else is wrong would survive the rung check being moved
        ahead of `NOT_READY` by mistake; this one would not, because it
        would then observe `RUNG_NOT_ATTAINED` where it asserts `NOT_READY`.
        """
        verdict = self._call(
            ready=None, levels=["floor", "pilot", "full"], attained_level=None)
        self.assertEqual(verdict["code"], "NOT_READY")

    def test_sequence_not_reached_outranks_rung_not_attained_too(self):
        """The same proof one check further down the ladder: an earlier
        open item refuses `SEQUENCE_NOT_REACHED` even with a below-floor
        `levels`/`attained_level` pair supplied alongside it."""
        sequence = [
            {"ordinal": 1, "mark": " ", "witness": {"kind": "record", "operand": None}},
            {"ordinal": 2, "mark": "x", "witness": {"kind": "rehearsal", "operand": "job-a"}},
        ]
        verdict = self._call(
            sequence=sequence, levels=["floor", "pilot", "full"], attained_level=None)
        self.assertEqual(verdict["code"], "SEQUENCE_NOT_REACHED")


class PositionHonestTests(unittest.TestCase):
    """`impl_availability.position_honest` -- the honesty prefix extracted
    from `cmd_close`'s own former hand-rolled ladder (D2, `a-pilot-is-the-
    whole-flow-validated`) and shared, unchanged, with `launch_available`
    above. Table-driven over every one of its five outcomes, in the order
    the function itself checks them.
    """

    def _honest(self, **overrides):
        facts = {"status": "complete", "unbacked": [], "disagreements": [],
                 "shards_declared": True}
        facts.update(overrides)
        return impl_availability.position_honest(**facts)

    def test_the_five_outcomes_in_the_order_the_ladder_checks_them(self):
        cases = [
            ("absent status",
             {"status": "absent"}, "POSITION_ABSENT", {}),
            ("stale status",
             {"status": "stale"}, "POSITION_STALE", {}),
            ("a real unbacked tick",
             {"unbacked": [{"ordinal": 3, "witness": {"kind": "notebook", "operand": "n"}}]},
             "POSITION_UNBACKED", {"unbackedOrdinals": [3]}),
            ("an undeclared shard tick",
             {"unbacked": [{"ordinal": 4, "witness": {"kind": "shard", "operand": "s0"}}],
              "shards_declared": False},
             "POSITION_SHARDS_UNDECLARED", {"undeclaredOrdinals": [4]}),
            ("a disagreeing item",
             {"disagreements": [{"ordinal": 5}]},
             "POSITION_DISAGREES", {"disagreeingOrdinals": [5]}),
        ]
        for label, overrides, code, facts in cases:
            with self.subTest(label):
                verdict = self._honest(**overrides)
                self.assertFalse(verdict["honest"])
                self.assertEqual(verdict["code"], code)
                self.assertEqual(verdict["facts"], facts)

    def test_nothing_wrong_reads_honest(self):
        verdict = self._honest()
        self.assertTrue(verdict["honest"])
        self.assertIsNone(verdict["code"])
        self.assertEqual(verdict["facts"], {})

    def test_status_outranks_every_other_check(self):
        """`absent`/`stale` short-circuit before the unbacked/shard/
        disagreement checks even run -- an unbacked or disagreeing item
        beside an absent status must never surface the narrower code."""
        verdict = self._honest(
            status="absent",
            unbacked=[{"ordinal": 1, "witness": {"kind": "shard", "operand": "s0"}}],
            shards_declared=False,
            disagreements=[{"ordinal": 2}])
        self.assertEqual(verdict["code"], "POSITION_ABSENT")

    def test_omitting_shards_declared_raises_typeerror(self):
        """No default, the identical doctrine `disagreements` already
        keeps: a caller that forgets this keyword fails the call itself,
        never silently reads every shard tick as backed."""
        with self.assertRaises(TypeError):
            impl_availability.position_honest(
                status="complete", unbacked=[], disagreements=[])


class LaunchAvailableNoUpwardImportsTests(unittest.TestCase):
    """The forge names no target vocabulary in `_core/implementation/`, and
    the same discipline applies one layer up: this module may not import
    the caller-side modules its two callers live in either.
    """

    FORBIDDEN_ROOTS = {"proposal-implementation", "remote-execution",
                       "kaggle-accounts", "implementation_cli", "adapter",
                       "kaggle"}

    def test_imports_no_caller_side_module(self):
        tree = ast.parse((CORE / "impl_availability.py").read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        self.assertTrue(
            roots.isdisjoint(self.FORBIDDEN_ROOTS),
            f"impl_availability.py imports {roots & self.FORBIDDEN_ROOTS}, "
            "naming a caller's own layout from inside the shared core")


class ClassifyRemoteNecessityTests(unittest.TestCase):
    """`impl_execution_strategy.classify_remote_necessity()` -- the pure
    5-rule ladder (design D3, `the-pilot-decides-the-remote-strategy`),
    exercised over hand-built facts, exactly `LaunchAvailableTests`'s
    own discipline for `impl_availability.launch_available` above.
    """

    def _classify(self, *, job: dict | None = None,
                   results_status: str = "piloted",
                   cost_forecast: dict | None = None) -> dict:
        row = job or {"job": "job-a", "accelerator": None,
                       "localBudget": None, "smokeReady": False}
        return impl_execution_strategy.classify_remote_necessity(
            jobs=[row], results_status=results_status, cost_forecast=cost_forecast)

    def _verdict(self, **kwargs) -> dict:
        return self._classify(**kwargs)["jobs"]["job-a"]

    # -- rule 1: results already current --------------------------------

    def test_results_current_is_local_sufficient_regardless_of_other_facts(self):
        """Mutation-proven: deleting rule 1's short-circuit must turn
        this red -- verified below, then reverted. A job that would
        otherwise be `must-remote` on accelerator alone still resolves
        `local-sufficient` here, because rule 1 runs first and returns.
        """
        job = {"job": "job-a", "accelerator": {"kind": "cuda", "architectures": ["sm_90"]},
               "localBudget": None, "smokeReady": False}
        verdict = self._verdict(job=job, results_status="current")
        self.assertEqual(verdict, {"necessity": "local-sufficient", "reason": "results.current"})

    # -- rule 2: accelerator declared ------------------------------------

    def test_declared_accelerator_is_must_remote(self):
        job = {"job": "job-a", "accelerator": {"kind": "cuda", "architectures": ["sm_90"]},
               "localBudget": None, "smokeReady": False}
        verdict = self._verdict(job=job, results_status="piloted")
        self.assertEqual(verdict, {"necessity": "must-remote", "reason": "accelerator.declared"})

    # -- rules 3-4: budget vs. projected cost -----------------------------

    def test_projected_cost_above_budget_is_must_remote(self):
        """Mutation-proven: inverting rule 3's `>` must turn this red --
        verified below, then reverted.
        """
        job = {"job": "job-a", "accelerator": None, "localBudget": {"seconds": 100},
               "smokeReady": False}
        verdict = self._verdict(
            job=job, results_status="piloted", cost_forecast={"projectedSeconds": 200})
        self.assertEqual(verdict, {"necessity": "must-remote", "reason": "budget.exceeded"})

    def test_projected_cost_within_budget_is_local_sufficient(self):
        job = {"job": "job-a", "accelerator": None, "localBudget": {"seconds": 200},
               "smokeReady": False}
        verdict = self._verdict(
            job=job, results_status="piloted", cost_forecast={"projectedSeconds": 100})
        self.assertEqual(verdict, {"necessity": "local-sufficient", "reason": "budget.within"})

    def test_projected_cost_equal_to_budget_is_local_sufficient(self):
        """The boundary rule 3's `>` (never `>=`) decides: equal cost does
        not exceed its own budget.
        """
        job = {"job": "job-a", "accelerator": None, "localBudget": {"seconds": 150},
               "smokeReady": False}
        verdict = self._verdict(
            job=job, results_status="piloted", cost_forecast={"projectedSeconds": 150})
        self.assertEqual(verdict, {"necessity": "local-sufficient", "reason": "budget.within"})

    # -- rule 5: the facts do not decide -----------------------------------

    def test_undeclared_budget_with_a_forecast_is_optional(self):
        """Mutation-proven: making rule 5 fall through to
        `local-sufficient` must turn this (and the two tests below) red
        -- verified below, then reverted.
        """
        verdict = self._verdict(
            results_status="piloted", cost_forecast={"projectedSeconds": 100})
        self.assertEqual(verdict, {"necessity": "optional", "reason": "budget.undeclared"})

    def test_declared_budget_with_no_forecast_is_optional(self):
        job = {"job": "job-a", "accelerator": None, "localBudget": {"seconds": 100},
               "smokeReady": False}
        verdict = self._verdict(job=job, results_status="piloted", cost_forecast=None)
        self.assertEqual(verdict, {"necessity": "optional", "reason": "forecast.unprojectable"})

    def test_declared_budget_with_an_unprojectable_forecast_is_optional(self):
        """`cost_forecast` given but its own `projectedSeconds` is `None`
        -- `search_cost_forecast()`'s own shape when nothing was ever
        measured to project from.
        """
        job = {"job": "job-a", "accelerator": None, "localBudget": {"seconds": 100},
               "smokeReady": False}
        verdict = self._verdict(
            job=job, results_status="piloted",
            cost_forecast={"projectedSeconds": None, "reason": "no target scale declared"})
        self.assertEqual(verdict, {"necessity": "optional", "reason": "forecast.unprojectable"})

    def test_unmeasured_results_outranks_an_undeclared_budget(self):
        verdict = self._verdict(results_status="absent", cost_forecast=None)
        self.assertEqual(verdict, {"necessity": "optional", "reason": "results.unmeasured"})

    def test_unreadable_results_is_also_unmeasured(self):
        verdict = self._verdict(results_status="unreadable", cost_forecast=None)
        self.assertEqual(verdict, {"necessity": "optional", "reason": "results.unmeasured"})

    def test_stale_results_is_not_treated_as_unmeasured(self):
        """`stale` means a real measurement exists, against the wrong
        revision -- distinct from never having measured at all.
        """
        verdict = self._verdict(results_status="stale", cost_forecast=None)
        self.assertEqual(verdict, {"necessity": "optional", "reason": "budget.undeclared"})

    # -- keyword-only, no defaults ------------------------------------------

    def test_omitting_results_status_raises_typeerror(self):
        """Mutation-proven: giving `results_status` a default value must
        turn this red -- verified below, then reverted.
        """
        with self.assertRaises(TypeError):
            impl_execution_strategy.classify_remote_necessity(
                jobs=[{"job": "job-a", "accelerator": None,
                       "localBudget": None, "smokeReady": False}],
                cost_forecast=None)

    def test_omitting_cost_forecast_raises_typeerror(self):
        with self.assertRaises(TypeError):
            impl_execution_strategy.classify_remote_necessity(
                jobs=[{"job": "job-a", "accelerator": None,
                       "localBudget": None, "smokeReady": False}],
                results_status="piloted")

    def test_omitting_jobs_raises_typeerror(self):
        with self.assertRaises(TypeError):
            impl_execution_strategy.classify_remote_necessity(
                results_status="piloted", cost_forecast=None)

    # -- multi-job summary ---------------------------------------------------

    def test_summary_counts_each_verdict_class(self):
        jobs = [
            {"job": "current", "accelerator": None, "localBudget": None, "smokeReady": False},
            {"job": "accel", "accelerator": {"kind": "cuda", "architectures": ["sm_90"]},
             "localBudget": None, "smokeReady": False},
            {"job": "undeclared", "accelerator": None, "localBudget": None, "smokeReady": False},
        ]
        result = impl_execution_strategy.classify_remote_necessity(
            jobs=jobs, results_status="current", cost_forecast=None)
        # `results_status` is shared across every job in one call (it is a
        # fact about the target's record, not about any one job) -- so all
        # three resolve `results.current` here regardless of their own
        # accelerator/budget fields. A second call with a non-`current`
        # status below is what actually reaches the accelerator/budget
        # rules for the mixed-summary assertion.
        self.assertEqual(result["summary"],
                         {"mustRemote": 0, "localSufficient": 3, "optional": 0})

        result = impl_execution_strategy.classify_remote_necessity(
            jobs=jobs, results_status="piloted", cost_forecast=None)
        self.assertEqual(result["summary"],
                         {"mustRemote": 1, "localSufficient": 0, "optional": 2})
        self.assertEqual(result["jobs"]["accel"]["necessity"], "must-remote")


class ExecutionStrategyNoUpwardImportsTests(unittest.TestCase):
    """The same discipline `LaunchAvailableNoUpwardImportsTests` already
    holds for `impl_availability.py`, extended to its new sibling: the
    shared core may not import a caller-side module.
    """

    FORBIDDEN_ROOTS = {"proposal-implementation", "remote-execution",
                       "kaggle-accounts", "implementation_cli", "adapter",
                       "kaggle"}

    def test_imports_no_caller_side_module(self):
        tree = ast.parse((CORE / "impl_execution_strategy.py").read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        self.assertTrue(
            roots.isdisjoint(self.FORBIDDEN_ROOTS),
            f"impl_execution_strategy.py imports {roots & self.FORBIDDEN_ROOTS}, "
            "naming a caller's own layout from inside the shared core")


class OperandRequiredKindsTests(unittest.TestCase):
    """The one fact `_resolve_discuss_about` (implementation_cli.py) reads
    to decide which bare `--about <kind>` calls it may refuse.
    """

    def test_record_is_excluded_the_rest_are_required(self):
        self.assertEqual(impl_position.OPERAND_REQUIRED_KINDS,
                         frozenset({"notebook", "rehearsal", "shard", "step"}))
        self.assertNotIn("record", impl_position.OPERAND_REQUIRED_KINDS)
        self.assertTrue(
            impl_position.OPERAND_REQUIRED_KINDS <= impl_position.WITNESS_KINDS)


class LocateHeadingsTests(unittest.TestCase):
    """`impl_position.locate_headings` (design "the placer" -- the one new
    primitive `settle`, implementation_cli.py, needs beyond the three it
    reuses unchanged: `splice`, `write_spliced`, `digest_bytes`).
    """

    def test_one_occurrence_returns_one_span_at_the_first_non_blank_line(self):
        data = b"## Heading\n\n- item\n"
        spans = impl_position.locate_headings(data, "## Heading")
        self.assertEqual(spans, [{"start": 12, "end": 12}])
        self.assertEqual(data[12:], b"- item\n")

    def test_no_occurrence_returns_an_empty_list_never_a_refusal(self):
        data = b"## Heading\n\n- item\n"
        self.assertEqual(impl_position.locate_headings(data, "## Nowhere"), [])

    def test_two_occurrences_return_two_spans(self):
        data = b"## H\ntext\n\n## H\nmore\n"
        spans = impl_position.locate_headings(data, "## H")
        self.assertEqual(len(spans), 2)
        self.assertNotEqual(spans[0]["start"], spans[1]["start"])

    def test_a_substring_heading_is_not_a_match(self):
        """Measured on the real reference holder this module's own
        `BLOCK_CLOSE` docstring already cites: `## Figures — phase 1` and
        `## Figures — phase 2` both contain `## Figures`, so a substring
        rule would already pick the wrong one of two on that document.
        """
        data = "## Figures — phase 1\ntext\n## Figures — phase 2\nmore\n".encode("utf-8")
        self.assertEqual(impl_position.locate_headings(data, "## Figures"), [])
        self.assertEqual(
            len(impl_position.locate_headings(data, "## Figures — phase 1")), 1)

    def test_a_fenced_heading_as_the_sole_hit_is_excluded(self):
        """The one way an unfenced rule would land a placement inside a
        code fence instead of the document's own prose (design decision
        "Fenced regions"): a heading-shaped line that only ever occurs
        inside a fenced block must report zero hits, not one inside the
        fence.
        """
        data = b"```\n# X\n```\ntext\n"
        self.assertEqual(impl_position.locate_headings(data, "# X"), [])

    def test_a_fenced_and_an_unfenced_hit_both_report_only_the_real_one(self):
        data = b"```\n## H\n```\n## H\nreal content\n"
        spans = impl_position.locate_headings(data, "## H")
        self.assertEqual(len(spans), 1)
        self.assertEqual(data[spans[0]["start"]:], b"real content\n")

    def test_heading_at_end_of_file_with_no_trailing_newline_inserts_at_len_data(self):
        data = b"## Heading"
        spans = impl_position.locate_headings(data, "## Heading")
        self.assertEqual(spans, [{"start": len(data), "end": len(data)}])

    def test_blank_lines_after_the_heading_are_skipped_not_counted(self):
        data = b"## Heading\n\n\n- item\n"
        spans = impl_position.locate_headings(data, "## Heading")
        self.assertEqual(len(spans), 1)
        self.assertEqual(data[spans[0]["start"]:], b"- item\n")

    def test_splicing_a_zero_width_span_inserts_without_replacing(self):
        """The whole reason a span is zero-width (design decision
        "Insertion point"): `splice` with `start == end` inserts the new
        block and leaves every other byte, before and after, untouched.
        """
        data = b"## Heading\n\n- item\n"
        span = impl_position.locate_headings(data, "## Heading")[0]
        spliced = impl_position.splice(data, b"- [ ] new item\n", span)
        self.assertEqual(spliced, b"## Heading\n\n- [ ] new item\n- item\n")

    # --- prose-first sections (defect measured 2026-08-29 against the
    # operator's real AGREED.md: 17 `## ` sections, 15 open with a bullet,
    # 2 open with prose -- the first real `settle` landed its bullet
    # between the heading and the paragraph that introduces the section) ---

    def test_a_section_that_opens_with_prose_inserts_before_the_first_bullet(self):
        """`heading / blank / prose / blank / bullets` is a real shape, not
        only `heading / blank / bullets`. The insertion point must be
        immediately before the first `- [` line, not the first non-blank
        line -- landing ahead of the prose that explains the section is
        the exact defect a real `settle` call produced.
        """
        data = (b"## The trials search\n\n"
                b"Agreed 2026-08-26/27, while replacing the grid engine.\n\n"
                b"- [x] first item\n"
                b"- [x] second item\n")
        spans = impl_position.locate_headings(data, "## The trials search")
        self.assertEqual(len(spans), 1)
        self.assertEqual(data[spans[0]["start"]:],
                         b"- [x] first item\n- [x] second item\n")

    def test_a_bullets_first_section_is_unchanged_by_the_prose_skip(self):
        """Must not regress: a section that already opens with a bullet
        keeps landing at that first bullet, exactly as before.
        """
        data = b"## Heading\n\n- [ ] first item\n- [ ] second item\n"
        spans = impl_position.locate_headings(data, "## Heading")
        self.assertEqual(len(spans), 1)
        self.assertEqual(data[spans[0]["start"]:],
                         b"- [ ] first item\n- [ ] second item\n")

    def test_a_bullet_less_section_falls_back_to_the_first_non_blank_line(self):
        """Must not regress: a section with prose and NO bullet at all --
        bounded by the next heading -- inserts at the first non-blank
        line, the same place it always did.
        """
        data = (b"## Heading\n\n"
                b"Only prose, never a checklist item, in this section.\n\n"
                b"## Next Heading\n\n- [ ] unrelated item\n")
        spans = impl_position.locate_headings(data, "## Heading")
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            data[spans[0]["start"]:],
            b"Only prose, never a checklist item, in this section.\n\n"
            b"## Next Heading\n\n- [ ] unrelated item\n")

    def test_a_bullet_less_section_at_end_of_file_falls_back_the_same_way(self):
        """The EOF half of the same must-not-regress guarantee: no bullet,
        no following heading either -- still the first non-blank line.
        """
        data = b"## Heading\n\nOnly prose, and the file ends here.\n"
        spans = impl_position.locate_headings(data, "## Heading")
        self.assertEqual(len(spans), 1)
        self.assertEqual(data[spans[0]["start"]:],
                         b"Only prose, and the file ends here.\n")


class DigestBytesTests(unittest.TestCase):
    """`impl_position.digest_bytes` is the one primitive the holder
    document's compare-and-swap builds on (design decision 2); it has no
    caller-specific behavior of its own, so it is exercised directly here.
    """

    def test_identical_bytes_digest_identically(self):
        self.assertEqual(
            impl_position.digest_bytes(b"same content"),
            impl_position.digest_bytes(b"same content"))

    def test_different_bytes_digest_differently(self):
        self.assertNotEqual(
            impl_position.digest_bytes(b"one"),
            impl_position.digest_bytes(b"two"))

    def test_absent_path_digests_as_empty_bytes(self):
        """A candidate holder that does not exist on disk is treated as
        empty, never as a distinct "absent" sentinel -- the same shape
        `write_spliced` itself falls back to when `path` does not exist.
        """
        self.assertEqual(impl_position.digest_bytes(b""),
                         hashlib.sha256(b"").hexdigest())


class WriteSplicedCasTests(unittest.TestCase):
    """`write_spliced`'s compare-and-swap (design decision 2): a required
    `expect_digest` re-checked against `path`'s own current bytes,
    immediately before anything is written.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "AGREED.md"
        self.path.write_bytes(b"original content\n")

    def test_matching_pre_image_writes_normally(self):
        digest = impl_position.digest_bytes(self.path.read_bytes())
        impl_position.write_spliced(self.path, b"new content\n", expect_digest=digest)
        self.assertEqual(self.path.read_bytes(), b"new content\n")

    def test_omitting_expect_digest_raises_typeerror(self):
        with self.assertRaises(TypeError):
            impl_position.write_spliced(self.path, b"new content\n")

    def test_a_changed_pre_image_refuses_and_leaves_the_file_untouched(self):
        """Mutation A (design decision 2, "a file changed between reads"):
        the digest captured at location time no longer matches what is on
        disk at write time. Refuses `POSITION_HOLDER_MOVED`; the on-disk
        bytes are byte-identical before and after the refused call.
        """
        stale_digest = impl_position.digest_bytes(b"stale pre-image, never on disk")
        before = self.path.read_bytes()
        with self.assertRaises(impl_refusals.Refused) as ctx:
            impl_position.write_spliced(self.path, b"new content\n",
                                        expect_digest=stale_digest)
        self.assertEqual(ctx.exception.code, "POSITION_HOLDER_MOVED")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
