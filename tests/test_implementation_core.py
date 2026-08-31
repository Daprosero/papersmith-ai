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
                 "shards_declared": True}
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
                         frozenset({"notebook", "rehearsal", "shard"}))
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
