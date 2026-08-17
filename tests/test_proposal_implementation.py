"""Name normalization and reorganization scale — the two v2 gates that are code.

The rest of the v2 flow is orchestration and lives in SKILL.md, where a test cannot
reach it. These two are decisions the CLI makes on its own, so they are pinned here:
what the user types becomes a directory/package pair deterministically, and a plan
declares whether the user can still review it.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
CLI = FORGE / ".claude/skills/proposal-implementation/scripts/implementation_cli.py"
sys.path.insert(0, str(CLI.parent))
import implementation_cli as impl  # noqa: E402  (path set above)


class NormalizeNameTests(unittest.TestCase):
    def assertPair(self, raw, directory, package):
        resolved = impl.normalize_name(raw)
        self.assertEqual(resolved["directory"], directory, raw)
        self.assertEqual(resolved["package"], package, raw)

    def test_spaces_become_the_separator_pair(self):
        self.assertPair("mil creda", "Mil-Creda", "Mil_Creda")

    def test_an_acronym_survives_untouched(self):
        # Lowercasing MIL-CREDA renames the method, not the folder.
        self.assertPair("MIL-CREDA", "MIL-CREDA", "MIL_CREDA")

    def test_a_mixed_acronym_keeps_only_the_acronym_uppercase(self):
        self.assertPair("MIL creda", "MIL-Creda", "MIL_Creda")

    def test_camel_case_is_split_at_the_boundary(self):
        self.assertPair("milCreda", "Mil-Creda", "Mil_Creda")

    def test_underscores_and_hyphens_are_the_same_separator(self):
        self.assertPair("mil_creda", "Mil-Creda", "Mil_Creda")
        self.assertPair("mil-creda", "Mil-Creda", "Mil_Creda")

    def test_surrounding_and_repeated_whitespace_is_absorbed(self):
        self.assertPair("  mil   creda  ", "Mil-Creda", "Mil_Creda")

    def test_a_single_word_still_produces_both_forms(self):
        self.assertPair("creda", "Creda", "Creda")

    def test_digits_inside_a_word_are_kept(self):
        self.assertPair("creda v2", "Creda-V2", "Creda_V2")

    def test_a_leading_digit_is_refused_because_no_package_may_start_with_one(self):
        with self.assertRaises(impl.NameRefused):
            impl.normalize_name("2creda")

    def test_an_empty_name_is_refused(self):
        for raw in ("", "   ", None):
            with self.assertRaises(impl.NameRefused):
                impl.normalize_name(raw)

    def test_a_name_with_nothing_but_separators_is_refused(self):
        with self.assertRaises(impl.NameRefused):
            impl.normalize_name("-_-")

    def test_the_package_is_always_importable(self):
        for raw in ("mil creda", "MIL-CREDA", "milCreda", "creda v2", "Creda"):
            package = impl.normalize_name(raw)["package"]
            self.assertTrue(package.isidentifier(), f"{raw} -> {package}")

    def test_normalization_is_idempotent(self):
        # Feeding a normalized name back must not drift it.
        for raw in ("mil creda", "MIL-CREDA", "milCreda"):
            once = impl.normalize_name(raw)
            twice = impl.normalize_name(once["directory"])
            self.assertEqual(once["directory"], twice["directory"], raw)
            self.assertEqual(once["package"], twice["package"], raw)


class NameCommandTests(unittest.TestCase):
    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, str(CLI), *args],
                              capture_output=True, text=True, cwd=FORGE)
        return json.loads(proc.stdout or "{}"), proc.returncode

    def test_the_command_needs_no_repository_because_it_runs_before_one_exists(self):
        result, code = self.run_cli("name", "--name", "mil creda")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["directory"], "Mil-Creda")
        self.assertEqual(result["package"], "Mil_Creda")

    def test_an_unusable_name_is_refused_with_a_code_not_a_traceback(self):
        result, code = self.run_cli("name", "--name", "2creda")
        self.assertEqual(code, 2, result)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["code"], "NAME_STARTS_WITH_DIGIT")


class PlanScaleTests(unittest.TestCase):
    """`plan` must say whether its own output is still readable before approval."""

    def scale(self, plan, tracked=()):
        with tempfile.TemporaryDirectory() as box:
            original = impl.tracked_files
            impl.tracked_files = lambda _target: list(tracked)
            try:
                return impl.plan_scale(plan, Path(box))
            finally:
                impl.tracked_files = original

    def test_a_short_list_is_reviewable(self):
        result = self.scale({"moves": [{"from": f"f{n}.py", "to": "src/x.py"} for n in range(4)],
                             "renames": [], "referenceUpdates": []})
        self.assertEqual(result["scale"], "reviewable")
        self.assertEqual(result["decisionCount"], 4)

    def test_crossing_the_decision_limit_makes_it_large(self):
        result = self.scale({"moves": [{"from": f"f{n}.py", "to": "src/x.py"} for n in range(16)],
                             "renames": [], "referenceUpdates": []})
        self.assertEqual(result["scale"], "large")

    def test_a_rename_carrying_many_files_is_still_one_decision(self):
        # The whole point: renaming a folder of 200 files is one line the user reads,
        # not 200. Counting the carried files measures blast radius, not reviewability,
        # and would force a separate session for a trivial change.
        tracked = [f"Images/Results/plot{n}.png" for n in range(200)]
        result = self.scale({"moves": [], "renames": [{"from": "Images", "to": "Creda"}],
                             "referenceUpdates": []}, tracked=tracked)
        self.assertEqual(result["decisionCount"], 1)
        self.assertEqual(result["carriedFiles"], 200)
        self.assertEqual(result["scale"], "reviewable")

    def test_reference_rewrites_are_decisions_because_each_edits_a_file(self):
        # These are what a rename really costs: each one can be wrong on its own.
        result = self.scale({"moves": [], "renames": [{"from": "Images", "to": "Creda"}],
                             "referenceUpdates": [{"file": f"src/m{n}.py"} for n in range(20)]})
        self.assertEqual(result["decisionCount"], 21)
        self.assertEqual(result["scale"], "large")

    def test_the_real_repository_shape_stays_reviewable(self):
        # One rename of a product folder plus six reference rewrites: seven lines.
        tracked = [f"Images/Results/plot{n}.png" for n in range(37)]
        result = self.scale({"moves": [], "renames": [{"from": "Images", "to": "Neutral-Method"}],
                             "referenceUpdates": [{"file": f"src/m{n}.py"} for n in range(6)]},
                            tracked=tracked)
        self.assertEqual(result["decisionCount"], 7)
        self.assertEqual(result["carriedFiles"], 37)
        self.assertEqual(result["scale"], "reviewable")

    def test_the_breakdown_and_limit_travel_with_the_answer(self):
        result = self.scale({"moves": [], "renames": [], "referenceUpdates": []})
        self.assertEqual(result["limit"], impl.LARGE_PLAN_DECISIONS)
        self.assertEqual(result["breakdown"], {"moves": 0, "renames": 0, "referenceUpdates": 0})


if __name__ == "__main__":
    unittest.main()


class ProbeStateTests(unittest.TestCase):
    """The probe reads its own state from the repository, and stores nothing else."""

    def repo(self, packages=(), results=None, name="Creda"):
        box = Path(tempfile.mkdtemp(prefix="pp-probe-"))
        for package in packages:
            (box / "src" / package).mkdir(parents=True)
            (box / "src" / package / "mod.py").write_text("x = 1\n")
        if results is not None:
            out = box / name / "Results"
            out.mkdir(parents=True)
            (out / impl.PROBE_RESULTS).write_text(json.dumps(results))
        return box

    def test_a_run_below_the_declared_scale_is_a_pilot_and_not_a_finished_campaign(self):
        # The reduction was always read and returned here; nothing looked at it, so a
        # point estimate from one repetition reported as a completed benchmark.
        box = self.repo(results={
            "revision": "r05.md", "comparison": [{"dimension": "accuracy"}],
            "reduction": {"epochs": 3, "seeds": [0]},
            "targetScale": {"epochs": 20, "seeds": list(range(30))},
        })
        state = impl.probe_state(box, "Creda", "r05.md")
        self.assertEqual(state["status"], "piloted")
        self.assertEqual(state["belowTargetScale"]["seeds"], {"ran": 1, "declared": 30})

    def test_a_run_at_the_declared_scale_is_finished(self):
        box = self.repo(results={
            "revision": "r05.md", "comparison": [{"dimension": "accuracy"}],
            "reduction": {"epochs": 20, "seeds": list(range(30))},
            "targetScale": {"epochs": 20, "seeds": list(range(30))},
        })
        self.assertEqual(impl.probe_state(box, "Creda", "r05.md")["status"], "current")

    def test_a_record_the_checker_wrote_itself_proves_only_half_the_path(self):
        # The join, crossed. Every test above hands `probe_state` a record this file
        # authored, which verifies the reader and says nothing about whether anything
        # produces one — and that is exactly how a repository ended up with a correct
        # summary at a path nobody opens. So: the contract says where the record goes,
        # and the harness the skill ships has to name that same place.
        root = Path(impl.SKILL_ROOT)
        self.assertIn(impl.PROBE_RESULTS, (root / "SKILL.md").read_text(encoding="utf-8"),
                      "the contract must name the file the probe opens")
        harness = (root / "assets/kit/nb" / impl.BENCHMARK_MODULE).read_text(
            encoding="utf-8")
        self.assertIn("--out", harness,
                      "the harness must write the record, not only compute it")

    def test_a_repository_of_placeholders_is_told_apart_from_a_complete_one(self):
        # A clone that skipped the smudge filter looks finished: the paths are all
        # there and every one of them is a few hundred bytes of text. Whatever opens
        # one fails with an error about the file format, nowhere near the reason.
        box = Path(tempfile.mkdtemp(prefix="pp-lfs-"))
        (box / ".gitattributes").write_text("*.pth filter=lfs diff=lfs merge=lfs -text\n")
        (box / "Models").mkdir()
        (box / "Models" / "placeholder.pth").write_bytes(
            impl.LFS_POINTER_PREFIX + b"v1\noid sha256:abc\nsize 1073741824\n")
        (box / "Models" / "real.pth").write_bytes(b"\x80\x02\x8a\nreal weights")

        state = impl.lfs_state(box)
        self.assertEqual(state["status"], "pointers")
        self.assertEqual(state["pointerCount"], 1)
        self.assertEqual(state["materializedCount"], 1)
        self.assertEqual([p["path"] for p in state["pointers"]], ["Models/placeholder.pth"])
        self.assertIn("git lfs pull", state["fetchCommand"])
        # The pointer declares the real size, so the cost is a number rather than a
        # warning. Fetching this one would spend the whole free monthly allowance.
        self.assertEqual(state["bytesToFetch"], 1073741824)
        self.assertIn("1.00 GiB", state["humanBytesToFetch"])
        # And the tempting workaround must be named as not existing: every route
        # costs the same, the browser's download button included.
        self.assertIn("download button", state["quota"])

    def test_a_repository_with_no_lfs_says_so_rather_than_guessing(self):
        box = Path(tempfile.mkdtemp(prefix="pp-lfs-"))
        self.assertEqual(impl.lfs_state(box)["status"], "none")
        (box / ".gitattributes").write_text("*.md text\n")
        self.assertEqual(impl.lfs_state(box)["status"], "none")

    def test_what_exists_is_inspected_even_before_anybody_commits_it(self):
        # The index is the wrong enumerator: a misplaced module invisible until it is
        # committed gets reported after it has entered the history, which is the
        # opposite of useful. Two questions, two sources — does this exist is the
        # disk's to answer, is this part of the record is the ignore rules'.
        box = Path(tempfile.mkdtemp(prefix="pp-present-"))
        subprocess.run(["git", "init", "-q", str(box)], check=True)
        (box / "src" / "Creda").mkdir(parents=True)
        (box / "Creda" / "Notebooks").mkdir(parents=True)
        stray = box / "Creda" / "Notebooks" / "helper.py"
        stray.write_text("x = 1\n")

        self.assertNotIn("Creda/Notebooks/helper.py", impl.tracked_files(box),
                         "nothing has been committed, so the index cannot know")
        self.assertIn("Creda/Notebooks/helper.py", impl.present_files(box),
                      "but it is on disk and nobody said to ignore it")

        (box / ".gitignore").write_text("Creda/Notebooks/helper.py\n")
        self.assertNotIn("Creda/Notebooks/helper.py", impl.present_files(box),
                         "deliberately ignored is not the same as not yet added")

    def test_a_leftover_package_is_the_baseline_a_probe_compares_against(self):
        box = self.repo(packages=["Creda", "legacy"])
        self.assertEqual(impl.previous_implementations(box, "Creda"), ["legacy"])

    def test_our_own_package_is_never_its_own_baseline(self):
        box = self.repo(packages=["Creda"])
        self.assertEqual(impl.previous_implementations(box, "Creda"), [])

    def test_the_hyphen_form_still_resolves_to_our_package(self):
        # <Name>/ is Mil-Creda, src/<Package>/ is Mil_Creda: the pair must not
        # make the implementation look like somebody else's leftover.
        box = self.repo(packages=["Mil_Creda", "legacy"])
        self.assertEqual(impl.previous_implementations(box, "Mil-Creda"), ["legacy"])

    def test_a_directory_with_no_source_is_not_an_implementation(self):
        box = Path(tempfile.mkdtemp(prefix="pp-probe-"))
        (box / "src" / "assets").mkdir(parents=True)
        (box / "src" / "assets" / "notes.md").write_text("nothing here\n")
        self.assertEqual(impl.previous_implementations(box, "Creda"), [])

    def test_our_own_package_is_not_a_baseline_even_spelled_differently(self):
        # macOS folds case, so src/Creda and src/CREDA are one directory: an exact
        # comparison hands our own package back as somebody else's prior work. On a
        # case-sensitive filesystem they are two, but a package differing from ours
        # only in case is a naming accident, not a baseline.
        box = Path(tempfile.mkdtemp(prefix="pp-probe-"))
        (box / "src" / "CREDA").mkdir(parents=True)
        (box / "src" / "CREDA" / "m.py").write_text("x = 1\n")
        self.assertEqual(impl.previous_implementations(box, "Creda"), [])

    def test_a_baseline_that_is_not_python_is_still_a_baseline(self):
        # Prior work arrives in whatever shape it was written in. Requiring .py
        # would make a notebook or MATLAB baseline invisible to the comparison.
        box = Path(tempfile.mkdtemp(prefix="pp-probe-"))
        for package, filename in (("Creda", "m.py"), ("old_matlab", "run.m"),
                                  ("old_notebooks", "study.ipynb")):
            (box / "src" / package).mkdir(parents=True)
            (box / "src" / package / filename).write_text("x\n")
        self.assertEqual(impl.previous_implementations(box, "Creda"),
                         ["old_matlab", "old_notebooks"])

    def test_no_summary_means_no_probe_has_run(self):
        box = self.repo(packages=["Creda"])
        self.assertEqual(impl.probe_state(box, "Creda", "r16.md")["status"], "absent")

    def test_a_summary_naming_the_current_revision_is_current(self):
        box = self.repo(results={"revision": "r16.md", "reduction": {}, "comparison": []})
        self.assertEqual(impl.probe_state(box, "Creda", "r16.md")["status"], "current")

    def test_without_a_revision_to_compare_it_says_unknown_not_stale(self):
        # Reporting "stale" here would assert a state nobody established.
        box = self.repo(results={"revision": "r16.md", "comparison": []})
        self.assertEqual(impl.probe_state(box, "Creda", None)["status"], "unknown")

    def test_a_malformed_comparison_refuses_instead_of_raising(self):
        # The same defect read_findings carried: malformed input must produce a
        # typed refusal, never a traceback.
        box = self.repo(results={"revision": "r16.md", "comparison": "not a list"})
        self.assertEqual(impl.probe_state(box, "Creda", "r16.md")["status"], "unreadable")

    def test_a_summary_naming_an_older_revision_is_stale_by_inspection(self):
        # Nothing is stored to know this: the artifact carries the revision it
        # was obtained under, so staleness is read, not remembered.
        state = impl.probe_state(
            self.repo(results={"revision": "r13.md", "reduction": {}, "comparison": []}),
            "Creda", "r16.md")
        self.assertEqual(state["status"], "stale")
        self.assertEqual(state["revision"], "r13.md")
        self.assertEqual(state["expectedRevision"], "r16.md")

    def test_an_unreadable_summary_refuses_instead_of_reading_as_absent(self):
        box = self.repo(results={"revision": "r16.md"})
        (box / "Creda" / "Results" / impl.PROBE_RESULTS).write_text("{not json")
        self.assertEqual(impl.probe_state(box, "Creda", "r16.md")["status"], "unreadable")

    def test_the_shipped_notebook_template_carries_its_placeholders(self):
        template = (Path(impl.SKILL_ROOT) / "assets/kit/nb" / impl.PROBE_NOTEBOOK)
        self.assertTrue(template.exists(), "the probe notebook must ship with the kit")
        text = template.read_text(encoding="utf-8")
        for token in ("{{NAME}}", "{{BASELINE}}", "{{REVISION}}", "{{PROBE_RESULTS}}",
                      "{{DATASET}}", "{{SEEDS}}"):
            self.assertIn(token, text, token)
        self.assertIn("screening", text, "the notebook must say it is not a benchmark")
        self.assertIn("stratified", text, "the slice must be stratified, and say why")
        # The notebook must RUN the harness. A notebook that only describes a
        # comparison is a form, and handing back a form is not the capability.
        self.assertIn(impl.BENCHMARK_MODULE, text,
                      "the notebook must drive the benchmark, not describe it")
        self.assertIn("subprocess", text, "it has to actually execute something")
        self.assertIn("parents[1]", text,
                      "the output path must be anchored to the repository, never a "
                      "bare ../ that resolves outside it")


class BackendStateTests(unittest.TestCase):
    """numpy cannot be trained, so the backend decides whether a benchmark can run."""

    def repo(self, package_files=(), test_files=(), name="Creda"):
        box = Path(tempfile.mkdtemp(prefix="pp-backend-"))
        pkg = box / "src" / impl.package_name(name)
        pkg.mkdir(parents=True)
        (box / "tests").mkdir()
        for filename, source in package_files:
            (pkg / filename).write_text(source)
        for filename, source in test_files:
            (box / "tests" / filename).write_text(source)
        return box

    def test_numpy_only_is_not_trainable(self):
        state = impl.backend_state(
            self.repo([("kernel.py", "import numpy as np\n")]), "Creda")
        self.assertEqual(state["state"], "numpy")
        self.assertFalse(state["trainable"])

    def test_torch_is_trainable(self):
        state = impl.backend_state(
            self.repo([("kernel.py", "import torch\n")]), "Creda")
        self.assertEqual(state["state"], "tensor")
        self.assertTrue(state["trainable"])

    def test_a_half_converted_repository_is_mixed_and_not_trainable(self):
        # The dangerous state: modules train while the tests still assert over
        # numpy, so the suite passes while measuring what the model never touched.
        state = impl.backend_state(
            self.repo([("kernel.py", "import torch\n")],
                      [("test_kernel.py", "import numpy as np\n")]), "Creda")
        self.assertEqual(state["state"], "mixed")
        self.assertFalse(state["trainable"])
        self.assertTrue(state["numpyFiles"] and state["tensorFiles"])

    def test_an_unparsable_file_does_not_crash_the_reading(self):
        state = impl.backend_state(
            self.repo([("broken.py", "def (:\n")]), "Creda")
        self.assertEqual(state["state"], "unknown")

    def test_the_benchmark_harness_ships_with_the_kit_and_compiles(self):
        import ast
        harness = Path(impl.SKILL_ROOT) / "assets/kit/nb" / impl.BENCHMARK_MODULE
        self.assertTrue(harness.exists(), "the benchmark must ship with the kit")
        source = harness.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("stratified_indices", source, "the slice must be stratified")
        self.assertIn("stdev", source, "a bare mean over seeds hides what seeds reveal")
        # This test used to require the harness to name resnet18, CIFAR10, CIFAR100
        # and MNIST. It was asserting the defect: a catalogue here dictates the
        # experiment instead of serving it. The opposite is now pinned in
        # InterpreterGuardTests.test_the_harness_names_no_dataset_and_no_backbone_of_its_own.


sys.path.insert(0, str(CLI.parent.parent / "assets/kit/nb"))
import verdict as vd  # noqa: E402


class VerdictTests(unittest.TestCase):
    """Values are not an answer. These rules turn them into one, or refuse to."""

    def spread(self, mean, stdev=0.0, n=10):
        return {"mean": mean, "stdev": stdev, "n": n}

    def test_a_clear_gap_names_the_winner(self):
        result = vd.decide(self.spread(0.60, 0.01), self.spread(0.80, 0.01), vd.HIGHER)
        self.assertEqual(result["winner"], "new")

    def test_direction_decides_who_wins_not_the_larger_number(self):
        # Lower is better for time: the smaller side wins.
        result = vd.decide(self.spread(120.0, 1.0), self.spread(40.0, 1.0), vd.LOWER)
        self.assertEqual(result["winner"], "new")
        result = vd.decide(self.spread(40.0, 1.0), self.spread(120.0, 1.0), vd.LOWER)
        self.assertEqual(result["winner"], "baseline")

    def test_overlapping_means_are_indistinguishable_not_a_win(self):
        # The whole reason several seeds are run. Two bare means always differ at
        # enough decimal places, and calling that a result is reading noise aloud.
        result = vd.decide(self.spread(0.700, 0.05), self.spread(0.702, 0.05), vd.HIGHER)
        self.assertEqual(result["winner"], vd.TIE)

    def test_more_seeds_can_turn_a_tie_into_a_verdict(self):
        # Same means and spread, more repetitions: the standard error shrinks.
        loose = vd.decide(self.spread(0.70, 0.06, n=3), self.spread(0.76, 0.06, n=3), vd.HIGHER)
        tight = vd.decide(self.spread(0.70, 0.06, n=200), self.spread(0.76, 0.06, n=200), vd.HIGHER)
        self.assertEqual(loose["winner"], vd.TIE)
        self.assertEqual(tight["winner"], "new")

    def test_below_the_floor_the_threshold_inverts_so_no_verdict_is_granted(self):
        # One repetition gives a dispersion of zero, hence a threshold of zero, hence
        # a winner on every row from a bare difference — the rule turning into its
        # own opposite exactly where the protection matters most.
        alone = vd.decide(self.spread(0.72, 0.0, n=1), self.spread(0.78, 0.0, n=1), vd.HIGHER)
        self.assertEqual(alone["winner"], vd.UNRESOLVED)
        self.assertAlmostEqual(alone["margin"], 0.06)
        self.assertIn("point estimate", alone["reason"])

    def test_the_measurement_is_still_reported_when_the_verdict_is_withheld(self):
        # Suppressing the table would make the pilot a different program from the
        # campaign, which is the one thing the pilot may not be.
        rows = [{"dimension": "accuracy", "better": vd.HIGHER,
                 "baseline": self.spread(0.72, 0.0, n=1),
                 "new": self.spread(0.78, 0.0, n=1)}]
        rendered = vd.render(vd.judge(rows), {"seeds": 1})
        self.assertIn("0.72", rendered)
        self.assertIn("0.78", rendered)
        self.assertIn("point estimates, not verdicts", rendered)

    def test_a_missing_side_is_not_applicable_never_a_walkover(self):
        self.assertEqual(vd.decide(None, self.spread(0.9), vd.HIGHER)["winner"],
                         vd.NOT_APPLICABLE)
        self.assertEqual(vd.decide(self.spread(0.9), None, vd.HIGHER)["winner"],
                         vd.NOT_APPLICABLE)

    def test_a_descriptive_dimension_is_reported_and_not_contested(self):
        result = vd.decide(self.spread(11_000_000), self.spread(240_000), vd.DESCRIPTIVE)
        self.assertIsNone(result["winner"])

    def test_the_tally_says_where_each_side_wins(self):
        rows = [
            {"dimension": "accuracy", "better": vd.HIGHER,
             "baseline": self.spread(0.60, 0.01), "new": self.spread(0.80, 0.01)},
            {"dimension": "seconds", "better": vd.LOWER,
             "baseline": self.spread(10.0, 0.1), "new": self.spread(40.0, 0.1)},
            {"dimension": "peakMiB", "better": vd.LOWER,
             "baseline": self.spread(100.0, 20.0), "new": self.spread(101.0, 20.0)},
        ]
        counts = vd.tally(vd.judge(rows))
        self.assertEqual(counts["new"], ["accuracy"])
        self.assertEqual(counts["baseline"], ["seconds"])
        self.assertEqual(counts[vd.TIE], ["peakMiB"])

    def test_the_table_carries_the_reduction_and_a_winner_column(self):
        rows = [{"dimension": "accuracy", "better": vd.HIGHER,
                 "baseline": self.spread(0.60, 0.01), "new": self.spread(0.80, 0.01)}]
        text = vd.render(vd.judge(rows), {"setting": "trained", "backbone": "resnet18",
                                          "dataset": "CIFAR10", "seeds": 5,
                                          "revision": "r16.md"})
        for token in ("trained", "resnet18", "CIFAR10", "r16.md", "winner", "new"):
            self.assertIn(token, text, token)

    def test_both_settings_share_these_rules(self):
        # A synthetic sweep and a trained run measure different instruments and
        # answer the same question, so they share one shape and one verdict rule.
        synthetic = {"dimension": "separation d", "better": vd.HIGHER,
                     "baseline": self.spread(4.36, 0.10), "new": self.spread(3.29, 0.10)}
        trained = {"dimension": "accuracy", "better": vd.HIGHER,
                   "baseline": self.spread(0.60, 0.01), "new": self.spread(0.80, 0.01)}
        judged = vd.judge([synthetic, trained])
        self.assertEqual(judged[0]["verdict"]["winner"], "baseline")
        self.assertEqual(judged[1]["verdict"]["winner"], "new")


class WiringProposalTests(unittest.TestCase):
    """The gap where a comparison belongs is a proposal, not a placeholder."""

    def repo(self, modules=(), baseline_files=(), name="Creda"):
        box = Path(tempfile.mkdtemp(prefix="pp-wiring-"))
        pkg = box / "src" / impl.package_name(name)
        pkg.mkdir(parents=True)
        for filename, source in modules:
            (pkg / filename).write_text(source)
        for path in baseline_files:
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("x = 1\n")
        return box

    MODULE = ('__provenance__ = {"revision": "r16.md", "sections": ["5"],\n'
              '                  "equations": ["32", "33"], "invariants": ["bounded"]}\n')

    def test_the_draft_is_assembled_from_provenance_not_guessed(self):
        box = self.repo(modules=[("global_term.py", self.MODULE)],
                        baseline_files=["src/CREDA/models.py"])
        draft = impl.wiring_proposal(box, "Creda", ["CREDA"])
        module = draft["new"]["modules"][0]
        self.assertEqual(module["sections"], ["5"])
        self.assertEqual(module["equations"], ["32", "33"])
        self.assertEqual(module["invariants"], ["bounded"])

    def test_it_says_what_it_needs_from_the_user_rather_than_deciding(self):
        draft = impl.wiring_proposal(self.repo(), "Creda", [])
        self.assertEqual(draft["status"], "draft")
        needs = " ".join(draft["new"]["needs"] + draft["baseline"]["needs"]).lower()
        for asked in ("trainable terms", "backbone", "head", "entry point"):
            self.assertIn(asked, needs, asked)

    def test_the_offer_starts_from_what_the_baseline_already_trains_on(self):
        # Not a list somebody guessed about the field: what this repository does.
        box = self.repo(baseline_files=["src/CREDA/models.py"])
        (box / "src/CREDA/models.py").write_text(
            "from torchvision import models\n"
            "def build():\n"
            "    return models.resnet50(weights=None)\n")
        draft = impl.wiring_proposal(box, "Creda", ["CREDA"])
        found = [b["name"] for b in draft["offer"]["fromBaseline"]["backbones"]]
        self.assertEqual(found, ["resnet50"])
        # Nothing is suggested from a list: a forge for papers cannot know which
        # models are reasonable for a field it has not read.
        self.assertNotIn("lighterAlternatives", draft["offer"])

    def test_the_baseline_is_offered_as_a_candidate_never_as_editable(self):
        box = self.repo(baseline_files=["src/CREDA/models.py", "src/CREDA/train.py"])
        draft = impl.wiring_proposal(box, "Creda", ["CREDA"])
        candidate = draft["baseline"]["candidates"][0]
        self.assertEqual(candidate["package"], "CREDA")
        self.assertEqual(len(candidate["files"]), 2)
        self.assertIn("never modified", " ".join(draft["baseline"]["needs"]))

    def test_the_harness_refuses_without_wiring_instead_of_training_a_bare_backbone(self):
        # The defect this replaces: a placeholder that trained a generic backbone,
        # reported the baseline as not applicable, and produced a table about nothing.
        harness = (Path(impl.SKILL_ROOT) / "assets/kit/nb" / impl.BENCHMARK_MODULE)
        source = harness.read_text(encoding="utf-8")
        self.assertIn("wiring.py is missing", source)
        self.assertIn("SystemExit", source, "a missing wiring must stop the run")
        self.assertNotIn('"baseline": None,', source,
                         "the baseline must never be hardcoded as not applicable")


class BaselineEnvironmentTests(unittest.TestCase):
    """Read the environment the prior results were obtained in, do not assume one."""

    def repo(self, files):
        box = Path(tempfile.mkdtemp(prefix="pp-env-"))
        for path, source in files.items():
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(source)
        return box

    def test_a_called_module_attribute_is_a_backbone(self):
        box = self.repo({"src/CREDA/models.py":
                         "from torchvision import models\n"
                         "net = models.resnet50(weights=None)\n"})
        found = [b["name"] for b in impl.baseline_environment(box, ["CREDA"])["backbones"]]
        self.assertEqual(found, ["resnet50"])

    def test_a_method_call_on_an_instance_is_not_a_backbone(self):
        # The distinction that decides whether the reading is useful at all: matching
        # on the holder alone buries the real names under every .eval() and .to().
        box = self.repo({"src/CREDA/train.py":
                         "def run(model, device):\n"
                         "    model.eval()\n"
                         "    model.to(device)\n"
                         "    model.parameters()\n"})
        self.assertEqual(impl.baseline_environment(box, ["CREDA"])["backbones"], [])

    def test_dataset_names_are_read_from_the_baselines_own_vocabulary(self):
        box = self.repo({"src/CREDA/artifacts.py":
                         'DATASETS = ["MNIST-USPS-SVHN", "Office-Caltech", "ImageCLEF"]\n'})
        found = [d["name"] for d in impl.baseline_environment(box, ["CREDA"])["datasets"]]
        self.assertEqual(found, ["ImageCLEF", "MNIST-USPS-SVHN", "Office-Caltech"])

    def test_ordinary_words_near_a_dataset_variable_are_not_datasets(self):
        box = self.repo({"src/CREDA/train.py":
                         'dataset_keys = ["classes", "labels", "domain", "loader"]\n'})
        self.assertEqual(impl.baseline_environment(box, ["CREDA"])["datasets"], [])

    def test_the_data_entry_points_are_found_because_a_name_is_not_a_loader(self):
        # Naming Office-Caltech says what was measured; load_office_caltech() says
        # how to measure it again. The wiring needs the second one.
        box = self.repo({"src/CREDA/pipeline.py":
                         "def split_stratified(dataset, val_ratio):\n    return dataset\n"
                         "def load_dataset_results(backbone, dataset):\n    return None\n"
                         "def train_model(x):\n    return x\n"})
        found = impl.baseline_environment(box, ["CREDA"])["dataEntryPoints"]
        names = sorted(e["function"] for e in found)
        self.assertEqual(names, ["load_dataset_results", "split_stratified"])
        self.assertIn("dataset", found[0]["args"] + found[1]["args"])

    def test_notebooks_outside_the_proposal_are_prior_experiments(self):
        box = self.repo({"src/CREDA/m.py": "x = 1\n",
                         "CREDA/Notebooks/Results_Generator.ipynb": "{}",
                         "MIL-CREDA/Notebooks/probe.ipynb": "{}"})
        found = impl.baseline_environment(box, ["CREDA"], "MIL-CREDA")["notebooks"]
        self.assertEqual(found, ["CREDA/Notebooks/Results_Generator.ipynb"],
                         "the proposal's own notebooks are not prior work")

    def test_trained_weights_left_behind_are_reported(self):
        box = self.repo({"src/CREDA/m.py": "x = 1\n",
                         "Creda/Models/resnet50/resnet50_ADDA.pth": "binary"})
        self.assertEqual(impl.baseline_environment(box, ["CREDA"])["weights"],
                         ["resnet50_ADDA.pth"])

    def test_an_empty_baseline_says_it_discovered_nothing(self):
        box = self.repo({"src/CREDA/m.py": "x = 1\n"})
        self.assertFalse(impl.baseline_environment(box, ["CREDA"])["discovered"])


class InterpreterGuardTests(unittest.TestCase):
    """The benchmark must run under the repository's own interpreter, or not at all."""

    KIT = None  # set in setUp

    def setUp(self):
        self.KIT = Path(impl.SKILL_ROOT) / "assets/kit/nb"

    def stage(self, root_name="repo"):
        """Lay the harness out where it expects to be: <repo>/<Name>/Notebooks/."""
        box = Path(tempfile.mkdtemp(prefix="pp-interp-"))
        notebooks = box / root_name / "Name" / "Notebooks"
        notebooks.mkdir(parents=True)
        for asset in (impl.BENCHMARK_MODULE, "verdict.py"):
            shutil.copy(self.KIT / asset, notebooks / asset)
        (notebooks / "config.json").write_text("{}")
        return box / root_name, notebooks

    def run_harness(self, notebooks, executable=sys.executable):
        return subprocess.run(
            [executable, impl.BENCHMARK_MODULE, "--config", "config.json",
             "--out", "out.json"],
            cwd=str(notebooks), capture_output=True, text=True)

    def test_a_foreign_interpreter_is_refused_before_anything_is_measured(self):
        # Not hygiene: wall time and peak memory ARE the measurement, so another
        # interpreter measures a different environment correctly and the summary
        # would attribute it to this repository.
        repository, notebooks = self.stage()
        proc = self.run_harness(notebooks)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("refusing to run under", proc.stdout + proc.stderr)
        self.assertFalse((notebooks / "out.json").exists(),
                         "a refused run must not leave a summary behind")

    def test_the_refusal_names_the_interpreter_the_user_should_use(self):
        repository, notebooks = self.stage()
        output = "".join(self.run_harness(notebooks)[1:3] if False else
                         [self.run_harness(notebooks).stdout,
                          self.run_harness(notebooks).stderr])
        self.assertIn(str(repository / ".venv"), output,
                      "a refusal that does not say what to run instead is a dead end")

    def test_the_guard_runs_before_the_missing_wiring_is_reported(self):
        # Order matters: under a foreign interpreter the wiring question is not yet
        # the user's problem, and reporting it first would send them to fix the
        # wrong thing.
        repository, notebooks = self.stage()
        output = self.run_harness(notebooks).stdout + self.run_harness(notebooks).stderr
        self.assertIn("refusing to run under", output)
        self.assertNotIn("wiring.py is missing", output)

    def test_the_contract_and_the_harness_agree_that_it_is_enforced(self):
        source = (self.KIT / impl.BENCHMARK_MODULE).read_text(encoding="utf-8")
        self.assertIn("def environment(", source)
        self.assertIn("sys.prefix", source, "the check must look at the running prefix")
        # The relaxation for notebook services must be a positive test for one, never
        # an inference from a missing virtualenv: a repository where nobody has made
        # one yet also lacks it, and there the guard is exactly right to refuse.
        self.assertIn("def hosted_runtime(", source)
        self.assertNotIn('".venv").is_dir()', source)

    def test_the_harness_names_no_dataset_and_no_backbone_of_its_own(self):
        # A catalogue here would dictate the experiment: the wiring would be forced
        # to pick whichever well-known set the baseline happens to touch, and the
        # "common environment" would be an intersection with somebody's list rather
        # than the environment the prior results came from.
        source = (self.KIT / impl.BENCHMARK_MODULE).read_text(encoding="utf-8")
        for name in ("CIFAR10", "CIFAR100", "MNIST", "torchvision", "resnet18"):
            self.assertNotIn(name, source,
                             f"{name} is named by the harness: the data and the model "
                             f"must come from the wiring")
        self.assertIn("build_data", source, "the data has to arrive from the wiring")


class DiscoveryHonestyTests(unittest.TestCase):
    """An empty reading must announce itself as a miss, never as a clean result."""

    def repo(self, files):
        box = Path(tempfile.mkdtemp(prefix="pp-honest-"))
        for path, source in files.items():
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(source)
        return box

    def test_paths_and_names_are_discovered_not_assumed(self):
        # A different field, a different package, different file names: the reading
        # is over structure, so none of it is anchored to any one repository.
        box = self.repo({"src/LegacyTransformer/corpus_io.py":
                         "from torchvision import models\n"
                         "def load_corpus(name):\n    return None\n"
                         "def prepare_splits(corpus):\n    return corpus\n"
                         "def build():\n    return models.vgg16(weights=None)\n",
                         "LegacyTransformer/Notebooks/Experiments.ipynb": "{}",
                         "Method/Notebooks/mine.ipynb": "{}"})
        env = impl.baseline_environment(box, ["LegacyTransformer"], "Method")
        self.assertEqual([b["name"] for b in env["backbones"]], ["vgg16"])
        self.assertEqual(sorted(e["function"] for e in env["dataEntryPoints"]),
                         ["load_corpus", "prepare_splits"])
        self.assertEqual(env["notebooks"], ["LegacyTransformer/Notebooks/Experiments.ipynb"])

    def test_what_it_could_not_read_is_named_rather_than_returned_empty(self):
        # `CORPORA` misses the stem `corpus`, and a Spanish name misses everything.
        # Returning [] would read as "this baseline has no data layer", which is a
        # conclusion the reading never established.
        box = self.repo({"src/Legacy/io.py":
                         'CORPORA = ["WikiText-103"]\n'
                         "def cargar_datos(x):\n    return x\n"})
        env = impl.baseline_environment(box, ["Legacy"], "Method")
        self.assertIn("datasets", env["foundNothingFor"])
        self.assertIn("dataEntryPoints", env["foundNothingFor"])
        self.assertTrue(env["note"], "a miss with no explanation is indistinguishable "
                                     "from an absence")
        self.assertIn("another language", env["note"])

    def test_it_says_how_it_looked_so_the_user_can_point_at_what_it_missed(self):
        box = self.repo({"src/Legacy/io.py": "x = 1\n"})
        env = impl.baseline_environment(box, ["Legacy"], "Method")
        for kind in ("backbones", "datasets", "dataEntryPoints", "notebooks"):
            self.assertIn(kind, env["readBy"], kind)

    def test_a_full_reading_leaves_the_note_empty(self):
        box = self.repo({"src/Legacy/io.py":
                         "from torchvision import models\n"
                         'DATASETS = ["Some-Task"]\n'
                         "def load_data(x):\n    return x\n"
                         'SOURCE = "https://example.org/corpus.zip"\n'
                         "def build():\n    return models.vgg16()\n",
                         "Legacy/Notebooks/e.ipynb": "{}"})
        env = impl.baseline_environment(box, ["Legacy"], "Method")
        self.assertEqual(env["foundNothingFor"], [])
        self.assertEqual(env["note"], "")


class BackendIsAStageTests(unittest.TestCase):
    """numpy is where the mathematics is proved, not a defect to be fixed."""

    def repo(self, backend="numpy", baseline=False, name="Method"):
        box = Path(tempfile.mkdtemp(prefix="pp-stage-"))
        pkg = box / "src" / impl.package_name(name)
        pkg.mkdir(parents=True)
        (box / "tests").mkdir()
        source = "import torch\n" if backend == "tensor" else "import numpy as np\n"
        (pkg / "k.py").write_text(source)
        (box / "tests" / "test_k.py").write_text(source)
        if baseline:
            (box / "src" / "Prior").mkdir()
            (box / "src" / "Prior" / "m.py").write_text("x = 1\n")
        return box

    def step(self, box, name="Method", revision="r16.md"):
        backend = impl.backend_state(box, name)
        baselines = impl.previous_implementations(box, name)
        state = impl.probe_state(box, name, revision)
        if not baselines:
            return "nothing-to-compare"
        if not backend["trainable"]:
            return "convert"
        return "already-benchmarked" if state["status"] == "current" else "benchmark"

    def test_numpy_without_a_baseline_is_finished_not_unconverted(self):
        # Asking for a conversion here would demand work with no purpose and read as
        # though the implementation were unfinished when it is done.
        self.assertEqual(self.step(self.repo("numpy", baseline=False)),
                         "nothing-to-compare")

    def test_numpy_with_a_baseline_needs_converting_because_it_cannot_train(self):
        self.assertEqual(self.step(self.repo("numpy", baseline=True)), "convert")

    def test_torch_without_a_baseline_is_still_nothing_to_compare(self):
        self.assertEqual(self.step(self.repo("tensor", baseline=False)),
                         "nothing-to-compare")

    def test_the_reading_itself_does_not_care_which_backend_it_finds(self):
        # verify is static: provenance, invariant ids, trivial assertions. Only
        # backend_state looks at numpy or torch, and that is its whole job.
        for backend in ("numpy", "tensor"):
            state = impl.backend_state(self.repo(backend), "Method")
            self.assertEqual(state["state"], backend)
            self.assertEqual(state["trainable"], backend == "tensor")


class AcquisitionTests(unittest.TestCase):
    """Absent until something runs is not the same as impossible to obtain."""

    def repo(self, files):
        box = Path(tempfile.mkdtemp(prefix="pp-acq-"))
        for path, source in files.items():
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(source)
        return box

    def notebook(self, *cells):
        return json.dumps({"cells": [{"cell_type": "code", "source": [c]} for c in cells],
                           "nbformat": 4, "nbformat_minor": 5, "metadata": {}})

    def test_a_notebook_is_read_not_merely_listed(self):
        # The package resolves a directory it never creates; what creates it is here.
        box = self.repo({"src/Prior/paths.py":
                         'def resolve_root():\n    return "/mounted/somewhere"\n',
                         "Prior/Notebooks/Bootstrap.ipynb": self.notebook(
                             'run_command("git", "clone", REPO, str(CACHE))\n'
                             'import gdown\n')})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        how = {a["how"] for a in env["acquisition"]}
        self.assertIn("cloned from a repository", how)
        self.assertIn("fetched with gdown", how)

    def test_a_self_downloading_source_is_recognized_as_obtainable(self):
        box = self.repo({"src/Prior/m.py": "x = 1\n",
                         "Prior/Notebooks/Run.ipynb": self.notebook(
                             'sets = datasets.MNIST(root=R, download=True)\n')})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertIn("downloads itself", {a["how"] for a in env["acquisition"]})

    def test_a_path_outside_the_repository_is_reported_as_what_it_is(self):
        # Reading from somewhere else is a real constraint, and a different one from
        # unobtainable — it says where it runs, not that it cannot.
        box = self.repo({"src/Prior/paths.py": 'P = "/kaggle/input/some-set/images"\n'})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertIn("read from a path outside the repository",
                      {a["how"] for a in env["acquisition"]})

    def test_definitions_inside_a_notebook_count_as_entry_points(self):
        box = self.repo({"src/Prior/m.py": "x = 1\n",
                         "Prior/Notebooks/Run.ipynb": self.notebook(
                             "def load_everything(root):\n    return root\n")})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertEqual([e["function"] for e in env["dataEntryPoints"]],
                         ["load_everything"])

    def test_a_cell_that_cannot_be_parsed_does_not_stop_the_reading(self):
        # Shell magics are ordinary in notebooks and must not silence the rest.
        box = self.repo({"src/Prior/m.py": "x = 1\n",
                         "Prior/Notebooks/Run.ipynb": self.notebook(
                             "!pip install torch\n",
                             'sets = datasets.MNIST(root=R, download=True)\n')})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertIn("downloads itself", {a["how"] for a in env["acquisition"]})


class AcquisitionHonestyTests(unittest.TestCase):
    """The pattern list is fixed, so its silence must never read as an absence."""

    def repo(self, files):
        box = Path(tempfile.mkdtemp(prefix="pp-acqh-"))
        for path, source in files.items():
            full = box / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(source)
        return box

    def test_a_mechanism_the_list_does_not_know_is_reported_as_a_miss(self):
        # A cloud SDK, a data-versioning tool, a hosting client: none are in the list,
        # and returning [] silently is how "we could not read it" becomes "it cannot
        # be obtained" — the mistake this whole reading exists to prevent.
        box = self.repo({"src/Prior/m.py":
                         "import dvc.api\n"
                         'def load():\n    return dvc.api.read("data.csv")\n'})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertEqual(env["acquisition"], [])
        self.assertIn("acquisition", env["foundNothingFor"])

    def test_the_reading_says_it_is_partial_so_the_user_can_point(self):
        box = self.repo({"src/Prior/m.py": "x = 1\n"})
        env = impl.baseline_environment(box, ["Prior"], "Method")
        self.assertIn("partial", env["readBy"]["acquisition"])

    def test_an_absolute_path_outside_the_repository_is_recognized_anywhere(self):
        # Not the two hosted runtimes this was written against: any of them, plus a
        # cluster scratch or a mounted share.
        for path in ("/kaggle/input/some-set/images", "/content/Data/images",
                     "/mnt/shared/corpus", "/gpfs/scratch/experiment"):
            box = self.repo({"src/Prior/paths.py": f'ROOT = "{path}"\n'})
            how = {a["how"] for a in impl.baseline_environment(box, ["Prior"], "M")["acquisition"]}
            self.assertIn("read from a path outside the repository", how, path)

    def test_an_ordinary_relative_path_is_not_mistaken_for_a_mount(self):
        box = self.repo({"src/Prior/paths.py": 'ROOT = "data/images"\n'})
        how = {a["how"] for a in impl.baseline_environment(box, ["Prior"], "M")["acquisition"]}
        self.assertNotIn("read from a path outside the repository", how)


# --------------------------------------------------------------------- el sello

import importlib.util  # noqa: E402

_digest_spec = importlib.util.spec_from_file_location(
    "report_digest",
    FORGE / ".claude/skills/proposal-implementation/assets/kit/nb/report_digest.py",
)
report_digest = importlib.util.module_from_spec(_digest_spec)
_digest_spec.loader.exec_module(report_digest)


class ReportDigestJoinTests(unittest.TestCase):
    """Las dos mitades del sello, corridas sobre el mismo árbol.

    Una la escribe el destino y la otra la recomputa la verificación. Probar cada
    una contra un fixture propio verificaría las dos mitades y nunca la unión, que
    es lo único que el sello es: si dan números distintos, todo informe queda
    marcado como reliquia y nadie sabe por qué.
    """

    def build(self, root: Path) -> None:
        for relative, body in (
            ("src/Method/kernels.py", "K = 1\n"),
            ("src/Method_Benchmark/tables.py", "def render():\n    return 'x'\n"),
            ("src/Method_Benchmark/__init__.py", "__benchmark__ = {}\n"),
            ("tests/test_smoke.py", "def test_ok():\n    assert True\n"),
            ("Method/Notebooks/.gitkeep", ""),
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    def test_both_halves_agree_on_the_same_tree(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            self.assertEqual(report_digest.source_digest(root, "Method"),
                             impl.source_digest(root, "Method"))

    def test_the_benchmark_package_is_inside_what_the_stamp_covers(self):
        """El módulo que escribe las conclusiones cuenta como fuente del informe.

        Dejarlo afuera permitía corregir una conclusión y que el registro siguiera
        afirmando la vieja con la verificación en verde. Rojo alcanzable: si el
        digest ignorara el paquete del banco, este test no distinguiría los dos
        árboles y fallaría.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            before = impl.source_digest(root, "Method")
            (root / "src/Method_Benchmark/tables.py").write_text(
                "def render():\n    return 'y'\n", encoding="utf-8")
            after = impl.source_digest(root, "Method")
            self.assertNotEqual(before, after)
            self.assertNotEqual(report_digest.source_digest(root, "Method"), before)

    def test_prior_work_the_benchmark_imports_is_inside_what_the_stamp_covers(self):
        """Mover lo que computa un brazo tiene que marcar rancio el informe.

        El banco importa del trabajo previo — es lo que lo hace una comparación —
        así que un cambio ahí cambia los números de esos brazos. Nombrando los
        paquetes uno por uno esto quedaba afuera: los cuadernos seguían diciendo
        `executed` sobre resultados viejos, y la sesión aparte que arregla el
        trabajo previo y vuelve es justo la que lo dispara.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            baseline = root / "src/PriorWork/models.py"
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text("LOSS = 1\n", encoding="utf-8")
            before = impl.source_digest(root, "Method")
            baseline.write_text("LOSS = 2\n", encoding="utf-8")
            after = impl.source_digest(root, "Method")
            self.assertNotEqual(before, after)
            self.assertEqual(after, report_digest.source_digest(root, "Method"))

    def test_adding_a_test_does_not_mark_every_report_in_the_repository_stale(self):
        """`tests/` no es de lo que depende un informe: ningún cuaderno lo importa.

        Cubrirlo hacía que agregar cualquier prueba — incluso una sobre el
        trabajo previo, que ningún cuaderno toca — pidiera re-ejecutar la campaña
        entera para re-estampar un hash.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            before = impl.source_digest(root, "Method")
            (root / "tests/test_added_later.py").write_text(
                "def test_new():\n    assert True\n", encoding="utf-8")
            self.assertEqual(impl.source_digest(root, "Method"), before)
            self.assertEqual(report_digest.source_digest(root, "Method"), before)

    def test_the_marker_is_the_one_the_verification_looks_for(self):
        """Otra unión: el destino imprime un prefijo y la verificación lo busca."""
        self.assertEqual(report_digest.MARKER, impl.DIGEST_MARKER)

    def test_the_stamp_needs_no_context_from_the_notebook_that_prints_it(self):
        """Cualquier cuaderno lo llama sin argumentos, incluso el que no comparte
        el molde de los demás.

        La primera versión los pedía, y el primer cuaderno que no definía las
        mismas variables que el resto falló al estampar y quedó informado como
        rancio — el sello dejaba afuera justo al que se salía del molde, que es el
        que más falta hace vigilar.
        """
        import inspect

        signature = inspect.signature(report_digest.stamp)
        for parameter in signature.parameters.values():
            self.assertIsNot(parameter.default, inspect.Parameter.empty,
                             f"stamp() exige {parameter.name} a quien lo llame")

    def test_the_stamp_line_parses_the_way_the_verification_reads_it(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            line = report_digest.stamp(root, "Method")
            recovered = line.split(impl.DIGEST_MARKER, 1)[1].strip().split()[0]
            self.assertEqual(recovered, impl.source_digest(root, "Method"))


# ------------------------------------------------------- el contrato de informe

def _stream(text="salida\n"):
    return {"output_type": "stream", "name": "stdout", "text": [text]}


def _shown(mime, payload="x"):
    return {"output_type": "display_data", "data": {mime: payload}, "metadata": {}}


def _cell(kind, text, outputs=None, executed=True):
    """Una celda, y para las de código lo que dejó al correr.

    El default de una celda de código es haber impreso algo, porque es lo que hace
    un `print`. Una celda ejecutada con la lista de salidas vacía no es un fixture
    neutro: es exactamente el defecto de haber computado una medición y no haberla
    mostrado, y dejarlo como default haría que cada prueba de este archivo lo
    disparara sin querer.
    """
    cell = {"cell_type": kind, "metadata": {}, "source": [text]}
    if kind == "code":
        cell |= {"execution_count": 1 if executed else None,
                 "outputs": [_stream()] if outputs is None else list(outputs)}
    return cell


class PriorWorkTests(unittest.TestCase):
    """"El baseline se usa como está" era la regla más fuerte sin verificar.

    El trabajo previo vive bajo `src/` junto al método y su banco, y todos los
    chequeos pasaban de largo. Se podía editar en cualquier sesión y la siguiente
    abría un repositorio que no decía nada.

    Lo que hace útil el aviso es la segunda pregunta. "Cambió" a secas queda rojo
    para siempre en un repositorio que evoluciona y se deja de leer; "cambió esto,
    que tus brazos importan" es accionable.
    """

    def build(self, root: Path) -> None:
        for relative, body in (
            ("src/Method/kernels.py", "K = 1\n"),
            ("src/Method_Benchmark/__init__.py", "__benchmark__ = {}\n"),
            ("src/Method_Benchmark/wiring.py",
             "from PriorWork.models import Loss\nimport PriorWork.helpers\n"),
            ("src/PriorWork/__init__.py", ""),
            ("src/PriorWork/models.py", "class Loss:\n    scale = 1\n"),
            ("src/PriorWork/helpers.py", "def helper():\n    return 1\n"),
            ("src/PriorWork/training_loop.py", "def train():\n    return 'own'\n"),
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "base"], cwd=root, check=True)

    def state(self, root: Path) -> dict:
        return impl.prior_work_state(root, "Method")

    def test_an_untouched_baseline_is_reported_as_present_and_clean(self):
        """El hecho se informa aunque la respuesta sea que no pasó nada."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            state = self.state(root)
            self.assertEqual(state["status"], "clean")
            self.assertEqual(state["packages"], ["PriorWork"])
            self.assertEqual(state["modified"], [])

    def test_a_change_the_benchmark_imports_is_reported_as_reaching_the_run(self):
        """Mueve lo que computa un brazo: los resultados dejaron de valer."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            (root / "src/PriorWork/models.py").write_text(
                "class Loss:\n    scale = 2\n", encoding="utf-8")
            state = self.state(root)
            self.assertEqual(state["status"], "reaching")
            self.assertEqual(state["reaching"], ["src/PriorWork/models.py"])

    def test_a_change_the_benchmark_never_imports_is_reported_without_alarm(self):
        """Rojo alcanzable: si `reaching` ignorara los imports, esto sería `reaching`.

        El loop de entrenamiento propio del trabajo previo no lo llama el banco.
        Importa para los cuadernos del trabajo previo y no para esta comparación,
        y confundir los dos casos es lo que vuelve el aviso ruido.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            (root / "src/PriorWork/training_loop.py").write_text(
                "def train():\n    return 'changed'\n", encoding="utf-8")
            state = self.state(root)
            self.assertEqual(state["status"], "modified")
            self.assertEqual(state["modified"], ["src/PriorWork/training_loop.py"])
            self.assertEqual(state["reaching"], [])

    def test_a_module_the_ignore_rules_hide_is_still_seen_on_the_disk(self):
        """El caso que obliga a enumerar desde el disco y no desde el índice.

        Git no dice nada de una ruta ignorada. Preguntándole a él *qué hay*, un
        módulo de trabajo previo ignorado pero importado y ejecutado desaparece
        del reporte y todo vuelve `clean` — con un brazo computando con él.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            (root / ".gitignore").write_text("src/PriorWork/secret.py\n", encoding="utf-8")
            (root / "src/PriorWork/secret.py").write_text("SCALE = 3\n", encoding="utf-8")
            (root / "src/Method_Benchmark/wiring.py").write_text(
                "from PriorWork.models import Loss\n"
                "from PriorWork.secret import SCALE\n", encoding="utf-8")

            state = self.state(root)
            self.assertIn("src/PriorWork/secret.py", state["modules"])
            self.assertIn("src/PriorWork/secret.py", state["imported"])
            self.assertEqual(state["untrackedImported"], ["src/PriorWork/secret.py"])
            # Rojo alcanzable: preguntándole al índice esto sería `clean`.
            self.assertEqual(state["status"], "reaching")

    def test_an_unreadable_record_is_unknown_and_never_clean(self):
        """El silencio de git no puede leerse como "no cambió nada"."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative in ("src/Method/kernels.py", "src/PriorWork/models.py"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("X = 1\n", encoding="utf-8")
            # Sin `git init`: no hay registro que consultar.
            state = self.state(root)
            self.assertEqual(state["recordStatus"], "unavailable")
            self.assertEqual(state["status"], "unknown")
            self.assertEqual(state["modules"], ["src/PriorWork/models.py"])

    def test_what_an_arm_imports_is_reported_without_anything_having_changed(self):
        """`imported` es un hecho del árbol, no la consecuencia de un diff.

        El `__init__.py` del paquete cuenta: importar `PriorWork.models` lo
        ejecuta, así que un cambio ahí alcanza al brazo igual que uno en el
        módulo nombrado. El loop de entrenamiento propio del trabajo previo no,
        y esa es la distinción entera.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            state = self.state(root)
            self.assertEqual(state["status"], "clean")
            self.assertIn("src/PriorWork/models.py", state["imported"])
            self.assertIn("src/PriorWork/__init__.py", state["imported"])
            self.assertNotIn("src/PriorWork/training_loop.py", state["imported"])

    def test_the_stamp_moves_even_when_the_change_reaches_no_arm(self):
        """El par que hay que declarar, no descubrir.

        El sello cubre `src/` entero a propósito: se computa dos veces, una en el
        cuaderno y otra en la verificación, y cualquier regla más sutil que un
        directorio es una regla en la que dos implementaciones se desincronizan —
        y un sello cuyas mitades no coinciden no protege nada.

        Así que las dos cosas pasan juntas: ningún brazo cambió de número y el
        informe queda obsoleto igual. Sin decirlo, alguien re-corre una campaña
        por un comentario en trabajo previo que el banco nunca importa.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root)
            before = impl.source_digest(root, "Method")
            (root / "src/PriorWork/training_loop.py").write_text(
                "def train():\n    return 'changed'\n", encoding="utf-8")
            self.assertEqual(self.state(root)["reaching"], [])
            self.assertNotEqual(impl.source_digest(root, "Method"), before)

    def test_a_repository_with_no_prior_work_reports_none_rather_than_clean(self):
        """Sin baseline no hay nada que vigilar, y decir `clean` lo insinuaría."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative in ("src/Method/kernels.py", "src/Method_Benchmark/__init__.py"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("X = 1\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            self.assertEqual(self.state(root)["status"], "none")


class ReportContractTests(unittest.TestCase):
    """Los cinco chequeos estáticos del informe, cada uno con su rojo alcanzable.

    Un chequeo que no puede fallar es el defecto que fue escrito para atrapar, así
    que ninguno se da por bueno sin construir el árbol que lo dispara.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'seconds': 'lower', 'fit': None},\n"
        "    },\n"
        "}\n"
    )

    def build(self, root: Path, cells, declaration=None):
        (root / "src/Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (root / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION if declaration is None else declaration, encoding="utf-8")
        notebooks = root / "Method/Notebooks"
        notebooks.mkdir(parents=True, exist_ok=True)
        (notebooks / "Report.ipynb").write_text(
            json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                        "nbformat_minor": 5}), encoding="utf-8")

    def state(self, cells, declaration=None):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, cells, declaration)
            return impl.report_state(root, "Method", "Method")

    WELL_FORMED = [
        _cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
        # La mitad calculada del encuadre: contra qué valor se compara lo de abajo.
        _cell("code", "print(tables.objective('accuracy'))"),
        _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                      "print(tables.conclusion(runs, 'accuracy', reduction))"),
    ]

    def test_a_well_formed_report_passes_every_static_check(self):
        state = self.state(self.WELL_FORMED)
        for finding in ("proseNumbers", "duplicated", "unframed", "unconcluded"):
            self.assertEqual(state[finding], [], f"{finding}: {state[finding]}")

    def test_a_section_that_never_says_what_value_it_seeks_is_caught(self):
        """Una dirección no es un objetivo.

        «Más alto es mejor» dice para qué lado mirar y nada sobre dónde termina lo
        bueno. Quien no conoce la métrica no aprende nada de eso: le falta el hito
        contra el que se compara — un azar, una cota, un acuerdo entre corridas.
        """
        cells = [_cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                               "print(tables.conclusion(runs, 'accuracy', reduction))")]
        found = self.state(cells)["unaimed"]
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["reason"], "la sección no dice qué valor se busca")

    def test_declaring_no_objective_at_all_is_the_reason_and_not_a_pass(self):
        """La lección de `figures: []`, aplicada antes de repetirla.

        Un hallazgo que solo puede dispararse cuando alguien escribió una clave
        opcional se apaga justo en el paquete que nunca la escribió, y ahí el
        informe sale limpio sin decir en ningún lado qué se busca. La ausencia de
        la declaración es el motivo del hallazgo, no su excusa.
        """
        silent = self.DECLARATION.replace(
            "        'objectiveEntry': 'tables.objective',\n", "")
        found = self.state(self.WELL_FORMED, silent)["unaimed"]
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["reason"], "el contrato no declara objectiveEntry")

    def test_the_objective_is_computed_and_counts_as_framing(self):
        """El valor que se busca no puede ir tipeado: envejece igual que una
        medición tipeada, y el día que cambie una constante la frase va a seguir
        nombrando el hito viejo. Va calculado, y por eso ocupa una celda de código
        entre el párrafo y la tabla — que el chequeo tiene que leer como parte del
        encuadre y no como trabajo ajeno."""
        state = self.state(self.WELL_FORMED)
        self.assertEqual(state["unaimed"], [])
        self.assertEqual(state["unframed"], [])
        self.assertEqual(state["unconcluded"], [])

    def test_the_skill_never_asks_what_the_objective_says(self):
        """El límite que impide que esto aprenda un campo.

        Cualquier texto sirve: si la comprobación distinguiera un azar de una cota
        habría aprendido de qué se trata el experimento, y se apagaría en el
        próximo que mida otra cosa. Solo pregunta si la sección lo dice.
        """
        for texto in ("hacia cero", "por encima del azar", "adentro de sus cotas"):
            with self.subTest(texto=texto):
                cells = [_cell("markdown", "Qué mide: la exactitud."),
                         _cell("code", f"print(tables.objective({texto!r}))"),
                         _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                                       "print(tables.conclusion(runs, 'accuracy', reduction))")]
                self.assertEqual(self.state(cells)["unaimed"], [])

    def test_a_number_typed_into_prose_is_caught(self):
        cells = [_cell("markdown", "La exactitud sube 2,78 puntos."),
                 *self.WELL_FORMED]
        found = self.state(cells)["proseNumbers"]
        self.assertEqual([f["value"] for f in found], ["2,78"])

    def test_one_decimal_place_is_not_treated_as_a_measurement(self):
        """Un entero o un decimal corto suele ser estructura — un número de sección,
        una cantidad de paneles — y marcarlos entrenaría al lector a ignorar el
        chequeo entero."""
        cells = [_cell("markdown", "Son 3 paneles y la seccion 5.1."), *self.WELL_FORMED]
        self.assertEqual(self.state(cells)["proseNumbers"], [])

    def test_the_same_measurement_rendered_twice_is_caught(self):
        cells = [*self.WELL_FORMED,
                 _cell("markdown", "otra vez"),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                               "print(tables.conclusion(runs, 'accuracy', reduction))")]
        self.assertTrue(self.state(cells)["duplicated"])

    def test_two_measurements_in_one_cell_are_caught(self):
        cells = [_cell("markdown", "dos juntas"),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                               "print(harness.render_panorama(summary))\n"
                               "print(tables.conclusion(runs, 'accuracy', reduction))")]
        state = self.state(cells, self.DECLARATION.replace(
            "'renderers': ['tables.render']",
            "'renderers': ['tables.render', 'harness.render_panorama']"))
        self.assertTrue(state["duplicated"])

    def test_the_same_renderer_called_twice_in_one_cell_is_caught(self):
        """El hueco que dejaba pasar el caso más común de todos.

        La comprobación de arriba usa dos renderizadores DISTINTOS, y con eso el
        conteo se hacía sobre el conjunto de llamadas. Dos tablas producidas por
        la misma función colapsaban en una sola entrada y la celda salía limpia —
        que es justo la forma que «una celda, una medición» viene a atajar, y la
        que más aparece: dos lecturas hermanas impresas juntas porque se leen
        juntas.
        """
        cells = [_cell("markdown", "las dos distancias"),
                 _cell("code",
                       "print(tables.render(runs, 'accuracy', reduction))\n"
                       "print(tables.render(runs, 'seconds', reduction))\n"
                       "print(tables.conclusion(runs, 'accuracy', reduction))")]
        found = self.state(cells)["duplicated"]
        self.assertTrue(found, "una celda con dos tablas salió limpia")
        self.assertTrue(any(f.get("reason") == "más de una medición en una celda"
                            for f in found), found)

    def test_one_renderer_called_once_is_not_a_duplicate(self):
        """El verde tiene que seguir siendo alcanzable, o el conteo por
        repeticiones convierte cualquier tabla en un hallazgo."""
        cells = [_cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))")]
        self.assertEqual(self.state(cells)["duplicated"], [])

    def test_a_complementary_pair_shares_one_framing_and_one_conclusion(self):
        """Dos tablas que no se pueden concluir por separado.

        El numerador y el denominador de una razón son el caso claro: una
        distancia que baja puede ser alineación o colapso, y solo el par lo
        distingue. Ponerlas en una celda es el hallazgo de arriba; darle una
        conclusión a cada una sería concluir sobre media lectura. Queda una sola
        forma legítima — dos celdas bajo un encuadre, con una conclusión que lee
        las dos — y el chequeo tiene que admitirla.
        """
        cells = [_cell("markdown", "Las dos distancias, que se leen juntas."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.render(runs, 'seconds', reduction))"),
                 _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))")]
        state = self.state(cells)
        self.assertEqual(state["unframed"], [])
        self.assertEqual(state["unconcluded"], [])
        self.assertEqual(state["duplicated"], [])

    def test_a_section_that_never_concludes_is_still_caught(self):
        """La garantía no se aflojó: mirar la sección en vez de la celda de al lado
        no puede convertir en verde a una sección que nunca concluye."""
        cells = [_cell("markdown", "dos tablas y ninguna conclusión"),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.render(runs, 'seconds', reduction))"),
                 _cell("markdown", "otra sección"),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))")]
        found = self.state(cells)["unconcluded"]
        self.assertEqual(sorted(f["cell"] for f in found), [1, 2], found)

    def test_a_table_with_nothing_explaining_it_is_caught(self):
        cells = [_cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                               "print(tables.conclusion(runs, 'accuracy', reduction))")]
        self.assertTrue(self.state(cells)["unframed"])

    def test_a_table_with_no_computed_conclusion_is_caught(self):
        cells = [_cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))")]
        self.assertTrue(self.state(cells)["unconcluded"])

    def test_a_conclusion_in_the_following_cell_still_counts(self):
        cells = [_cell("markdown", "Qué mide: la exactitud. Más alto es mejor."),
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))"),
                 _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))")]
        self.assertEqual(self.state(cells)["unconcluded"], [])

    def test_the_cell_that_writes_the_record_may_render_everything_again(self):
        """El registro tiene que contener todo lo que el cuaderno mostró. Contarlo
        como segunda lectura haría que el único archivo del que depende una sesión
        posterior sea el defecto, y la forma de aprobar sería dejar de escribirlo."""
        cells = [*self.WELL_FORMED,
                 _cell("markdown", "el registro"),
                 _cell("code", "(root / 'report.txt').write_text("
                               "tables.render(runs, 'accuracy', reduction))")]
        self.assertEqual(self.state(cells)["duplicated"], [])

    def test_without_a_declaration_nothing_is_reported_as_fine(self):
        """No poder buscar algo no es lo mismo que no encontrarlo."""
        state = self.state(self.WELL_FORMED, declaration="__benchmark__ = {}\n")
        self.assertEqual(state["status"], "undeclared")

    def test_an_unavailable_live_check_never_reports_ok(self):
        """Sin intérprete del destino, dos de los chequeos no pudieron correr, y
        decir `ok` informaría su ausencia como su respuesta."""
        state = self.state(self.WELL_FORMED)
        self.assertEqual(state["live"], "unavailable")
        self.assertEqual(state["status"], "incomplete")


# ------------------------------------- lo que una celda produjo, no lo que dice

class AgreementsTests(unittest.TestCase):
    """La regla de escribir los acuerdos existía en prosa y sin nada que la sostenga
    — la misma forma que el defecto que describe.

    Un acuerdo se toma en una compuerta, no vive en ningún archivo, y cuando se
    escribe el código el único registro es una memoria que re-decide sola.
    """

    def write(self, root: Path, body: str) -> dict:
        (root / "Method").mkdir(parents=True, exist_ok=True)
        (root / "Method/AGREEMENTS.md").write_text(body, encoding="utf-8")
        return impl.agreements_state(root, "Method")

    def test_no_file_is_a_state_and_says_what_it_would_have_held(self):
        with tempfile.TemporaryDirectory() as raw:
            state = impl.agreements_state(Path(raw), "Method")
            self.assertEqual(state["status"], "absent")
            self.assertEqual(state["searched"], "Method/*.md")

    def test_an_unticked_item_is_an_agreement_that_never_reached_the_code(self):
        with tempfile.TemporaryDirectory() as raw:
            state = self.write(Path(raw), (
                "# Acuerdos\n\n"
                "- [x] el techo queda en 1 y compartido\n"
                "- [ ] la figura muestra la imagen, no la ruta\n"))
            self.assertEqual(state["status"], "open")
            self.assertEqual(state["open"], ["la figura muestra la imagen, no la ruta"])
            self.assertEqual(state["settled"], 1)

    def test_everything_ticked_settles(self):
        """Rojo alcanzable: si no leyera la marca, esto seguiría `open`."""
        with tempfile.TemporaryDirectory() as raw:
            state = self.write(Path(raw), "- [x] uno\n- [X] dos\n")
            self.assertEqual(state["status"], "settled")
            self.assertEqual(state["settled"], 2)
            self.assertEqual(state["open"], [])

    def test_a_checklist_under_any_name_is_found(self):
        """El caso que motivó esto, y que no probé la primera vez.

        Un repositorio ya tenía su checklist bajo otro nombre, con 159 ítems
        acordados a mano. Con el nombre fijo el chequeo reportaba `absent` encima
        de ella e inventaba una segunda al lado. Eso no es un archivo faltante:
        es una ausencia que nadie fue a buscar, vestida de hallazgo.

        Rojo alcanzable: con `AGREEMENTS.md` fijo, esto da `absent`.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method/AGREED.md").write_text(
                "# Acordado\n\n- [x] el techo queda en uno\n- [ ] la figura inline\n",
                encoding="utf-8")
            state = impl.agreements_state(root, "Method")
            self.assertEqual(state["status"], "open")
            self.assertEqual(state["holders"], ["Method/AGREED.md"])
            self.assertEqual(state["settled"], 1)

    def test_every_checklist_in_the_product_folder_is_counted(self):
        """Dos archivos con acuerdos son dos mitades de un contrato, no uno."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method/AGREED.md").write_text("- [x] uno\n", encoding="utf-8")
            (root / "Method/AGREEMENTS.md").write_text("- [ ] dos\n", encoding="utf-8")
            state = impl.agreements_state(root, "Method")
            self.assertEqual(state["holders"],
                             ["Method/AGREED.md", "Method/AGREEMENTS.md"])
            self.assertEqual(state["settled"], 1)
            self.assertEqual(state["open"], ["dos"])

    def test_a_markdown_file_with_no_items_is_a_document_and_not_a_checklist(self):
        """Un README en la carpeta del producto no es un contrato incumplido."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Method").mkdir(parents=True, exist_ok=True)
            (root / "Method/README.md").write_text(
                "# El método\n\n- una viñeta cualquiera\n- otra\n", encoding="utf-8")
            state = impl.agreements_state(root, "Method")
            self.assertEqual(state["status"], "absent")
            self.assertEqual(state["unparsed"], [])

    def test_prose_is_not_mistaken_for_a_malformed_agreement(self):
        """Un párrafo en negrita no es una viñeta.

        Probando solo el primer carácter, cada `**negrita**` se leía como un
        acuerdo mal escrito. Un archivo que registra un acuerdo revertido lo
        explica en prosa, y esa prosa es justo la que este archivo necesita
        permitir — un chequeo que grita por markdown se deja de leer, que cuesta
        más que el caso que vigilaba.
        """
        with tempfile.TemporaryDirectory() as raw:
            state = self.write(Path(raw), (
                "# Acuerdos\n\n- [x] el techo queda en uno\n\n"
                "## Revertidos\n\n"
                "**\"El techo se fija sin mirar resultados.\"** Revertido al "
                "decidir que cada familia busca el suyo.\n\n"
                "*Una línea en cursiva tampoco es una viñeta.*\n"))
            self.assertEqual(state["unparsed"], [])
            self.assertEqual(state["status"], "settled")
            self.assertEqual(state["settled"], 1)

    def test_a_bullet_that_is_not_a_checklist_item_is_never_counted_as_settled(self):
        """Un acuerdo escrito con el formato equivocado no es un acuerdo cumplido.

        Es la misma falla que el archivo previene, un nivel más abajo: quedaría
        escrito, nadie lo contaría, y el reporte diría que no falta nada.
        """
        with tempfile.TemporaryDirectory() as raw:
            state = self.write(Path(raw), "- [x] uno\n- dos, sin casilla\n")
            self.assertEqual(state["unparsed"], ["AGREEMENTS.md: - dos, sin casilla"])
            self.assertEqual(state["status"], "open")


class SearchIsAnExperimentTests(unittest.TestCase):
    """Una búsqueda es un experimento y se declara como tal.

    Tres cosas que se vuelven invisibles hasta que alguien se choca con ellas:
    escala propia, rol de material propio, y una regla de desempate escrita en vez
    de heredada de `max`. Nada acá sabe qué se busca ni nombra herramienta alguna.
    """

    COMPLETE = {
        "what": "el techo del coeficiente de adaptación, por familia",
        "requiredScale": {"epochs": 20, "seeds": 3},
        "role": "valid",
        "tieRule": "el techo más chico entre los empatados",
        "record": "Results/ceilings.json",
    }

    def test_a_repository_that_searches_nothing_has_nothing_to_declare(self):
        """Ausencia es un estado, no una falla: casi ningún repo busca algo."""
        state = impl.search_state({}, [])
        self.assertEqual(state["status"], "none")
        self.assertIn("undeclaredRecords", state["note"])

    def test_each_missing_piece_is_named_with_why_it_matters(self):
        for field in ("what", "requiredScale", "role", "tieRule"):
            partial = {k: v for k, v in self.COMPLETE.items() if k != field}
            state = impl.search_state({"search": partial}, ["Results/ceilings.json"])
            self.assertEqual(state["status"], "incomplete", field)
            self.assertEqual([m["field"] for m in state["missing"]], [field])
            self.assertTrue(state["missing"][0]["reason"], field)

    def test_a_search_that_writes_a_record_has_to_name_it_among_the_records(self):
        """La junta entre las dos declaraciones.

        Una búsqueda que escribe un archivo y no lo nombra donde se nombran los
        registros es un segundo experimento llegando sin contabilizar, que es
        justamente para lo que existe `records`.
        """
        state = impl.search_state({"search": self.COMPLETE}, ["Results/summary.json"])
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(state["recordNotDeclared"], "Results/ceilings.json")

    def test_a_directory_among_the_records_covers_the_search_record(self):
        state = impl.search_state({"search": self.COMPLETE}, ["Results"])
        self.assertEqual(state["recordNotDeclared"], None)
        self.assertEqual(state["status"], "ok")

    def test_a_complete_declaration_passes(self):
        """Rojo alcanzable: si no leyera la declaración, esto seguiría incompleto."""
        state = impl.search_state({"search": self.COMPLETE}, ["Results/ceilings.json"])
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["missing"], [])
        self.assertEqual(state["declared"]["role"], "valid")

    def test_the_declared_record_is_checked_against_the_disk(self):
        """Comparar las dos declaraciones verifica que alguien escribió el mismo
        texto dos veces, y no dice nada de dónde escribe la búsqueda."""
        with tempfile.TemporaryDirectory() as raw:
            product = Path(raw) / "Method"
            (product / "Results").mkdir(parents=True, exist_ok=True)
            state = impl.search_state({"search": self.COMPLETE},
                                      ["Results/ceilings.json"], product)
            self.assertIs(state["recordFound"], False)
            self.assertEqual(state["status"], "incomplete")

            (product / "Results/ceilings.json").write_text("{}", encoding="utf-8")
            state = impl.search_state({"search": self.COMPLETE},
                                      ["Results/ceilings.json"], product)
            self.assertIs(state["recordFound"], True)
            self.assertEqual(state["status"], "ok")

    def test_a_record_written_one_level_deeper_is_found_and_named(self):
        """El caso que motivó esto, y que las dos declaraciones no podían ver.

        Una ruta con un directorio duplicado satisfacía las dos declaraciones y
        dejaba el registro un nivel por debajo de donde nadie lo iba a buscar. Se
        descubrió después de que la búsqueda ya hubiera escrito ahí.
        """
        with tempfile.TemporaryDirectory() as raw:
            product = Path(raw) / "Method"
            deeper = product / "Results/Benchmark/Benchmark"
            deeper.mkdir(parents=True, exist_ok=True)
            (deeper / "ceilings.json").write_text("{}", encoding="utf-8")

            declaration = {**self.COMPLETE,
                           "record": "Results/Benchmark/ceilings.json"}
            state = impl.search_state({"search": declaration},
                                      ["Results/Benchmark"], product)
            self.assertIs(state["recordFound"], False)
            self.assertEqual(state["strayRecords"],
                             ["Results/Benchmark/Benchmark/ceilings.json"])

    def test_nothing_to_check_is_none_and_never_a_failure(self):
        """Sin carpeta de producto no hay pregunta que hacerle al disco, y `False`
        ahí sería inventar un hallazgo."""
        state = impl.search_state({"search": self.COMPLETE},
                                  ["Results/ceilings.json"])
        self.assertIsNone(state["recordFound"])
        self.assertEqual(state["status"], "ok")

    def test_it_names_no_tool(self):
        """La skill no recomienda con qué buscar: eso depende del problema.

        Un muestreo adaptativo entrega puntos desigualmente muestreados, y la
        skill exige después el paisaje completo para sostener una afirmación de
        escala. Recomendar la herramienta sería empujar una salida que contradice
        sus propias reglas de reporte.
        """
        source = (impl.SEARCH_DECLARATION, impl.search_state.__doc__)
        for tool in ("optuna", "hyperopt", "ray", "skopt", "grid", "bayesian"):
            self.assertNotIn(tool, json.dumps(source[0]).lower())
            self.assertNotIn(tool, (source[1] or "").lower())


class UndeclaredRecordsTests(unittest.TestCase):
    """Lo que la corrida deja escrito donde viven sus registros, o está declarado
    o se reporta.

    Todos los demás chequeos solo pueden dispararse sobre algo que alguien
    escribió, así que el repositorio corriendo un experimento que nadie contabilizó
    es justamente aquel donde todos se quedan callados. Es la misma red que
    `undeclaredDrawings` tiende sobre las figuras, tendida sobre lo que una
    corrida escribe.
    """

    def build(self, root: Path, declared: str) -> dict:
        (root / "src/Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (root / "src/Method_Benchmark/__init__.py").write_text(
            "__benchmark__ = {\n"
            "    'revision': 'r01.md',\n"
            "    'arms': {},\n"
            "    'report': {\n"
            "        'renderers': ['tables.render'],\n"
            "        'conclusions': ['tables.conclusion'],\n"
            "        'objectiveEntry': 'tables.objective',\n"
            "        'components': {'terms': ['fit'], 'share': None},\n"
            "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
            f"{declared}"
            "    },\n"
            "}\n", encoding="utf-8")
        (root / "Method/Notebooks").mkdir(parents=True, exist_ok=True)
        return impl.report_state(root, "Method", "Method")

    def results(self, root: Path, *relatives: str) -> None:
        for relative in relatives:
            path = root / "Method/Results" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

    def test_a_record_nobody_declared_is_named(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.results(root, "summary.json", "Benchmark/ceilings.json")
            state = self.build(root, "        'records': ['Results/summary.json'],\n")
            self.assertEqual(state["undeclaredRecords"],
                             ["Results/Benchmark/ceilings.json"])

    def test_it_does_not_filter_by_format(self):
        """Filtrar por `.json` daría un pase mudo a quien registre en otra cosa.

        Rojo alcanzable: con un filtro de extensión, ninguno de estos tres
        aparecería y el chequeo se quedaría callado justo donde hace falta.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.results(root, "runs.csv", "grid.parquet", "latents.npz")
            state = self.build(root, "        'records': [],\n")
            self.assertEqual(state["undeclaredRecords"],
                             ["Results/grid.parquet", "Results/latents.npz",
                              "Results/runs.csv"])

    def test_declaring_a_directory_covers_it_and_shows_in_the_echo(self):
        """Permitido, y visible: renunciar a la cuenta archivo por archivo es una
        decisión que se ve, no un silencio."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.results(root, "figures/curve.pdf", "figures/grid.pdf",
                         "Benchmark/ceilings.json")
            state = self.build(root, "        'records': ['Results/figures'],\n")
            self.assertEqual(state["undeclaredRecords"],
                             ["Results/Benchmark/ceilings.json"])
            self.assertEqual(state["declared"]["records"], ["Results/figures"])

    def test_the_per_checkpoint_artefacts_of_models_are_never_reported(self):
        """`Models/` guarda uno por checkpoint por diseño del layout.

        Reportar sesenta manifiestos sería un hallazgo que nadie lee, en cualquier
        repositorio — no solo en el que lo motivó.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            models = root / "Method/Models/Benchmark"
            models.mkdir(parents=True, exist_ok=True)
            for i in range(5):
                (models / f"A_M-U_seed{i}.manifest.json").write_text("{}", encoding="utf-8")
            self.results(root, "summary.json")
            state = self.build(root, "        'records': ['Results/summary.json'],\n")
            self.assertEqual(state["undeclaredRecords"], [])

    def test_declaring_everything_leaves_nothing_to_report(self):
        """Rojo alcanzable: si no leyera `records`, esto seguiría reportando."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.results(root, "summary.json", "Benchmark/latent.json")
            state = self.build(
                root,
                "        'records': ['Results/summary.json',\n"
                "                    'Results/Benchmark/latent.json'],\n")
            self.assertEqual(state["undeclaredRecords"], [])


class DistributionTests(unittest.TestCase):
    """A run split across machines, checked without knowing what any of it means.

    Three obligations, and each one's prohibition is the reason it is general:
    the axis must not be a comparison, the partition must be exhaustive, and
    shards must agree on what they said had to agree.
    """

    COMPLETE = {
        "axis": "seed",
        "poolable": ["accuracy"],
        "perEnvironment": ["cost"],
        "identicalAcrossShards": ["revision"],
    }
    DIMENSIONS = {"accuracy": "higher", "cost": "lower"}

    def test_a_repository_that_distributes_nothing_has_nothing_to_declare(self):
        state = impl.distribution_state({}, self.DIMENSIONS)
        self.assertEqual(state["status"], "none")

    def test_sharding_along_a_comparison_is_refused(self):
        """The one axis that is never allowed, because the ladder subtracts along it.

        Every rung compares two arms, so splitting by arm puts that subtraction
        across a hardware boundary and credits a mechanism with what the machine
        did.
        """
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "axis": "arm"}}, self.DIMENSIONS)
        self.assertEqual(state["status"], "incomplete")
        self.assertTrue(state["axisIsAComparison"])

    def test_any_other_axis_is_the_repository_s_business(self):
        """Reachable red: requiring `"seed"` would make this a forge for one paper.

        Another repository shards by subject, by fold, by episode, by patient.
        The skill has no notion of a seed and must not acquire one.
        """
        for axis in ("seed", "subject", "fold", "episode", "patient"):
            state = impl.distribution_state(
                {"distribution": {**self.COMPLETE, "axis": axis}}, self.DIMENSIONS)
            self.assertEqual(state["status"], "ok", axis)

    def test_a_dimension_in_neither_half_is_named(self):
        """Silently dropped, it becomes a column nobody notices is gone."""
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "perEnvironment": []}},
            self.DIMENSIONS)
        self.assertEqual(state["unpartitioned"], ["cost"])
        self.assertEqual(state["status"], "incomplete")

    def test_a_dimension_in_both_halves_is_named(self):
        """Pooled and grouped at once is two answers to one question."""
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "poolable": ["accuracy", "cost"]}},
            self.DIMENSIONS)
        self.assertEqual(state["inBothHalves"], ["cost"])
        self.assertEqual(state["status"], "incomplete")

    def test_a_declared_dimension_that_does_not_exist_is_named(self):
        state = impl.distribution_state(
            {"distribution": {**self.COMPLETE, "poolable": ["accuracy", "ghost"]}},
            self.DIMENSIONS)
        self.assertEqual(state["notADimension"], ["ghost"])

    def test_it_names_no_dimension_of_its_own(self):
        """The offending names are echoed from the repository, never written here.

        A skill that knew `seconds` describes a machine would be a skill that had
        learned one benchmark's vocabulary.
        """
        import json as _json
        source = _json.dumps([impl.DISTRIBUTION_DECLARATION,
                              impl.distribution_state.__doc__]).lower()
        for leaked in ("seconds", "peakmib", "accuracy", "seed", "kaggle", "t4"):
            self.assertNotIn(leaked, source, leaked)

    def test_shards_that_disagree_on_what_must_match_are_reported(self):
        """Refused rather than averaged: a difference there is a different
        experiment, not different hardware."""
        merged = {"shardsArrived": ["a", "b"],
                  "disagreements": [{"field": "revision", "values": {}}]}
        state = impl.distribution_state(
            {"distribution": self.COMPLETE}, self.DIMENSIONS, merged)
        self.assertEqual(state["status"], "incomplete")
        self.assertEqual(state["shardsDisagree"], ["revision"])

    def test_the_forecast_scales_what_the_pilot_measured(self):
        """A projection from data, not an estimate from memory."""
        cost = impl._projected_cost(
            {"seconds": 600, "epochs": 3, "seeds": [0]},
            {"epochs": 20, "seeds": list(range(30))})
        self.assertEqual(cost["factor"], 200.0)
        self.assertEqual(cost["projectedSeconds"], 120000)

    def test_a_forecast_it_cannot_make_says_why(self):
        """A silent `None` reads as "the cost is fine" to anyone skimming.

        It means the record never wrote down how long it took, and the whole
        point of projecting from a measurement is that somebody kept one.
        """
        cost = impl._projected_cost({"epochs": 3}, {"epochs": 20})
        self.assertIsNone(cost["projectedSeconds"])
        self.assertIn("no duration", cost["reason"])

    def test_a_complete_declaration_with_agreeing_shards_passes(self):
        merged = {"shardsArrived": ["a", "b"], "disagreements": []}
        state = impl.distribution_state(
            {"distribution": self.COMPLETE}, self.DIMENSIONS, merged)
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["missing"], [])


class DoctrineAmendmentTests(unittest.TestCase):
    """The record's clause and the launcher's clause governed different things.

    Only the launcher's ever moved. Asserting sentence-one survival alone would
    already pass before the amendment, since that sentence is untouched today —
    the reachable red is the second assertion, so both live in one test.
    """

    SKILL_MD = CLI.parent.parent / "SKILL.md"

    def test_amendment_preserves_sentence_and_revokes_launcher_clause(self):
        text = self.SKILL_MD.read_text(encoding="utf-8")
        self.assertIn(
            "No service is named here, and none should be.", text,
            "the sentence governing what the RECORD names must survive verbatim")
        collapsed = " ".join(text.split())
        self.assertNotIn(
            "belongs in `tools/` for the reasons that section gives", collapsed,
            "the clause governing where the launcher's CODE lives must be revoked")


class ToolsRootTests(unittest.TestCase):
    """`tools/` is where a launcher lives, and it needed a home.

    The same shape of problem the sibling-package rule already solved: a script
    that operates a run cannot sit in the method's package, because it implements
    no equation and could only be there by declaring a `__provenance__` it has no
    right to; it cannot sit in the benchmark's package, because it neither trains
    nor measures; and it cannot stay untracked, because then the configuration of
    a multi-hour campaign lives on one disk and no later session can reproduce
    how it was launched. No place existed, and that absence is the argument.
    """

    def build(self, root: Path, *relatives: str) -> list:
        for relative in ("src/Method/kernels.py", "tests/test_smoke.py", *relatives):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("X = 1\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "base"], cwd=root, check=True)
        paths = impl.present_files(root)
        return [p for p in paths
                if p.endswith(".py")
                and not p.startswith(impl.SOURCE_ROOTS)
                and Path(p).parts[0] not in impl.IGNORED_DIRS
                and Path(p).name != "setup.py"]

    def test_a_launcher_under_tools_is_not_a_stray_module(self):
        """Reachable red: without `tools/` among the roots, this is a stray."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertEqual(self.build(root, "tools/distribute.py"), [])

    def test_a_script_loose_at_the_top_is_still_a_stray_module(self):
        """The permission is a named place, not an amnesty."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertEqual(self.build(root, "run_it.py"), ["run_it.py"])

    def test_a_launcher_is_never_asked_for_a_provenance(self):
        """A launcher implements no equation, so it must never be asked for one.

        Safe by construction rather than by a guard: the provenance scan only
        recurses into `src/<Package>/`. Pinned end to end so a later widening of
        that walk cannot quietly start demanding a stamp `tools/` cannot honestly
        give — the falsified provenance the sibling-package rule exists to prevent.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative, body in (
                ("src/Method/kernels.py",
                 '__provenance__ = {"revision": "r01.md", "sections": ["1"],\n'
                 '                  "equations": ["1"], "invariants": ["holds"]}\n'),
                ("tests/test_invariants.py", "def test_holds():\n    assert True\n"),
                ("tools/distribute.py", "ACCELERATOR = 'X'\n"),
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")

            missing = [str(f.relative_to(root))
                       for f in sorted((root / "src" / "Method").rglob("*.py"))
                       if impl.read_declaration(f, "__provenance__") is None]
            self.assertEqual(missing, [])
            self.assertTrue((root / "tools/distribute.py").exists(),
                            "el lanzador existe y aun asi nadie le pide procedencia")


class ProseTests(unittest.TestCase):
    """Claims in prose that stopped being true, where nothing else would notice.

    Every other check reads a declaration or a file. These read sentences, and a
    sentence ages without anything failing: a rename leaves the old symbol named
    in the paragraph beside it, a new revision leaves the old one in a heading.
    """

    def build(self, root: Path, **files: str) -> None:
        for relative, body in files.items():
            path = root / relative.replace("__", "/")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    def test_a_revision_named_in_prose_that_is_not_the_current_one(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py":
                    '"""Verified against research-concept-r16.md."""\nK = 1\n',
            })
            state = impl.prose_state(root, "research-concept-r17.md")
            self.assertEqual(len(state["staleRevisions"]), 1)
            self.assertEqual(state["staleRevisions"][0]["named"],
                             "research-concept-r16.md")

    def test_the_current_revision_in_prose_is_not_reported(self):
        """Rojo alcanzable: reportarlas todas haría el hallazgo inútil."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py":
                    '"""Verified against research-concept-r17.md."""\nK = 1\n',
            })
            self.assertEqual(
                impl.prose_state(root, "research-concept-r17.md")["staleRevisions"], [])

    def test_the_pattern_comes_from_the_revision_handed_in(self):
        """Nada acá conoce una convención de nombres: se deriva del argumento."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py": '"""Bound to paper-v3.md."""\nK = 1\n',
            })
            state = impl.prose_state(root, "paper-v9.md")
            self.assertEqual(state["staleRevisions"][0]["named"], "paper-v3.md")

    def test_a_symbol_named_in_prose_that_resolves_to_nothing(self):
        """Lo que deja un rename: el párrafo sigue nombrando la constante vieja."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__config.py": "RAMP_CEILING = 1.0\n",
                "src__Method__figures.py":
                    '"""The coefficient is fixed at `LAMBDA_CONST` for every arm."""\n',
            })
            found = impl.prose_state(root, None)["unresolvedSymbols"]
            self.assertEqual([f["symbol"] for f in found], ["LAMBDA_CONST"])

    def test_a_symbol_that_exists_is_not_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__config.py": "RAMP_CEILING = 1.0\n",
                "src__Method__figures.py":
                    '"""Fixed at `RAMP_CEILING` for every arm."""\n',
            })
            self.assertEqual(impl.prose_state(root, None)["unresolvedSymbols"], [])

    def test_a_filename_is_not_mistaken_for_a_symbol(self):
        """Dotted y con guion bajo es exactamente lo que parece un archivo, y la
        prosa nombra archivos todo el tiempo."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py":
                    '"""See `Results_Generator.ipynb` and `requirements.txt`."""\nK = 1\n',
            })
            self.assertEqual(impl.prose_state(root, None)["unresolvedSymbols"], [])

    def test_code_is_not_read_as_prose(self):
        """Una revisión dentro de un literal es código y se chequea en otro lado;
        reportarla acá sería ruido sobre algo que ya tiene su verificación."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.build(root, **{
                "src__Method__kernels.py":
                    '__provenance__ = {"revision": "research-concept-r16.md"}\n',
            })
            self.assertEqual(
                impl.prose_state(root, "research-concept-r17.md")["staleRevisions"], [])


class StaleFindingTests(unittest.TestCase):
    """Un hallazgo del reporte se lee de lo que un cuaderno **emitió**.

    Sobre un cuaderno obsoleto describe la corrida que pasó, no el código que hay
    ahora. Las dos mitades ya se reportaban —el hallazgo y el estado del
    cuaderno— en dos lugares distintos de la misma salida, y nadie las cruzaba.
    Un lector que lo toma por defecto vivo va y arregla algo ya arreglado, o lo
    arregla de una segunda manera.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
        "    },\n"
        "}\n")

    def build(self, root: Path, digest_matches: bool,
              unexecuted: bool = False, errored: bool = False) -> dict:
        (root / "src/Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (root / "src/Method_Benchmark/__init__.py").write_text(
            self.DECLARATION, encoding="utf-8")
        (root / "src/Method").mkdir(parents=True, exist_ok=True)
        (root / "src/Method/kernels.py").write_text("K = 1\n", encoding="utf-8")

        digest = (impl.source_digest(root, "Method") if digest_matches
                  else "0" * 64)
        cells = [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["tables.render()"],
             "outputs": [{"output_type": "stream", "name": "stdout",
                          "text": ["acc 81.5  peor 67.1  piso 0.0\n"]}]},
            {"cell_type": "code", "execution_count": 2, "metadata": {},
             "source": ["tables.conclusion()"],
             "outputs": [{"output_type": "stream", "name": "stdout",
                          "text": ["mejor 81.5, peor 67.1, piso 0.0\n"]}]},
            {"cell_type": "code", "execution_count": 3, "metadata": {},
             "source": [f'print("{impl.DIGEST_MARKER} {digest}")'],
             "outputs": [{"output_type": "stream", "name": "stdout",
                          "text": [f"{impl.DIGEST_MARKER} {digest}\n"]}]},
        ]
        if unexecuted:
            cells.append({"cell_type": "code", "execution_count": None,
                          "metadata": {}, "source": ["tables.render()"],
                          "outputs": []})
        if errored:
            cells.append({"cell_type": "code", "execution_count": 4,
                          "metadata": {}, "source": ["tables.render()"],
                          "outputs": [{"output_type": "error",
                                       "ename": "NameError", "evalue": "tables",
                                       "traceback": []}]})
        nb = root / "Method/Notebooks/report.ipynb"
        nb.parent.mkdir(parents=True, exist_ok=True)
        nb.write_text(json.dumps({"cells": cells, "metadata": {},
                                  "nbformat": 4, "nbformat_minor": 5}),
                      encoding="utf-8")
        return impl.report_state(root, "Method", "Method")

    def test_a_finding_from_a_stale_notebook_says_so(self):
        with tempfile.TemporaryDirectory() as raw:
            state = self.build(Path(raw), digest_matches=False)
            found = state["restated"]
            self.assertTrue(found, "el fixture tiene que producir el hallazgo")
            self.assertTrue(found[0]["fromStaleNotebook"])

    def test_a_finding_from_a_current_notebook_carries_no_flag(self):
        """Rojo alcanzable: marcarlos todos haría la bandera inútil."""
        with tempfile.TemporaryDirectory() as raw:
            state = self.build(Path(raw), digest_matches=True)
            found = state["restated"]
            self.assertTrue(found, "el fixture tiene que producir el hallazgo")
            self.assertNotIn("fromStaleNotebook", found[0])

    def test_a_notebook_too_stale_to_be_called_stale_sources_still_says_so(self):
        """La escalera de estados es excluyente, y esta bandera leía un peldaño.

        Un cuaderno con celdas sin correr se llama `stale` y ahí se queda: nunca
        llega a la comparación de digest, así que sus fuentes pueden diferir en
        todo y el estado no cambia. Filtrar por `stale-sources` entonces pierde la
        marca justo cuando el cuaderno está más desactualizado y no menos —
        corrió a medias *y* contra otro código— que es la única dirección en la
        que este error podía ser peligroso.
        """
        with tempfile.TemporaryDirectory() as raw:
            state = self.build(Path(raw), digest_matches=False, unexecuted=True)
            found = state["restated"]
            self.assertTrue(found, "el fixture tiene que producir el hallazgo")
            self.assertTrue(found[0].get("fromStaleNotebook"))

    def test_a_finding_read_off_a_notebook_that_failed_says_so(self):
        """Un cuaderno con un error corrió parte de sus celdas y abandonó el
        resto, así que lo que emitió describe una corrida que no terminó."""
        with tempfile.TemporaryDirectory() as raw:
            state = self.build(Path(raw), digest_matches=True, errored=True)
            found = state["restated"]
            self.assertTrue(found, "el fixture tiene que producir el hallazgo")
            self.assertTrue(found[0].get("fromStaleNotebook"))


class ComponentShareTests(unittest.TestCase):
    """Un término bien implementado y multiplicado por algo minúsculo da una
    columna de casi-ceros que se lee como resultado.

    `contribution` sola — el numerador, sin denominador al lado — no distingue
    "el término no comandó nada" de "el término fue escalado a nada", y las dos
    imprimen chico. La regla existía en prosa y un repositorio entregó el
    numerador solo con la verificación en verde.

    Lo que se chequea es la declaración, nunca el significado: nada acá puede
    aprender cómo se llama un término del objetivo de alguien.
    """

    BASE = ("__benchmark__ = {\n"
            "    'revision': 'r01.md',\n"
            "    'arms': {},\n"
            "    'report': {\n"
            "        'renderers': ['tables.render'],\n"
            "        'conclusions': ['tables.conclusion'],\n"
            "        'objectiveEntry': 'tables.objective',\n"
            "%s"
            "        'dimensions': %s,\n"
            "    },\n"
            "}\n")

    def state(self, root: Path, components: str, dimensions: str) -> dict:
        (root / "src/Method_Benchmark").mkdir(parents=True, exist_ok=True)
        (root / "src/Method_Benchmark/__init__.py").write_text(
            self.BASE % (components, dimensions), encoding="utf-8")
        (root / "Method/Notebooks").mkdir(parents=True, exist_ok=True)
        return impl.report_state(root, "Method", "Method")

    def test_a_package_that_declares_no_components_is_told_why_that_matters(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            found = self.state(root, "", "{'accuracy': 'higher'}")["componentsWithoutShare"]
            self.assertEqual(len(found), 1)
            self.assertIn("no declara `components`", found[0]["reason"])

    def test_more_than_one_term_and_no_share_is_the_gap_the_rule_is_about(self):
        """Dos términos que se suman y ninguna forma de leer la parte de cada uno."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            found = self.state(
                root,
                "        'components': {'terms': ['fit', 'align'], 'share': None},\n",
                "{'accuracy': 'higher', 'fit': None, 'align': None}",
            )["componentsWithoutShare"]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["terms"], ["fit", "align"])

    def test_a_declared_term_the_record_never_carries_is_named(self):
        """Declararlo y no registrarlo deja la parte sin poder computarse igual."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = self.state(
                root,
                "        'components': {'terms': ['fit', 'align'], 'share': 'alignShare'},\n",
                "{'accuracy': 'higher', 'fit': None}",
            )
            self.assertEqual(state["componentsNotRecorded"], ["align", "alignShare"])

    def test_terms_and_share_both_recorded_raise_nothing(self):
        """Rojo alcanzable: si el chequeo no leyera `dimensions`, esto fallaría."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = self.state(
                root,
                "        'components': {'terms': ['fit', 'align'], 'share': 'alignShare'},\n",
                "{'accuracy': 'higher', 'fit': None, 'align': None, 'alignShare': None}",
            )
            self.assertEqual(state["componentsNotRecorded"], [])
            self.assertEqual(state["componentsWithoutShare"], [])


class CellOutputTests(unittest.TestCase):
    """Los dos chequeos que leen la salida de una celda y no su código.

    Todo lo demás en `report_state` se contesta desde las fuentes. Estos dos no:
    una celda puede correr, no levantar nada, emitir una salida, y no haber
    mostrado nada. `execution_count` dice que corrió y la lista de errores está
    vacía, así que cualquier chequeo que lea solo esas dos la aprueba.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'figures': ['figures.curves'],\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
        "    },\n"
        "}\n"
    )

    FRAME = _cell("markdown", "Qué mide: la exactitud. Más alto es mejor.")
    AIM = _cell("code", "print(tables.objective('accuracy'))")
    TABLE = _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                          "print(tables.conclusion(runs, 'accuracy', reduction))")

    def state(self, cells, declaration=None):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src/Method_Benchmark").mkdir(parents=True)
            (root / "src/Method_Benchmark/__init__.py").write_text(
                declaration or self.DECLARATION, encoding="utf-8")
            notebooks = root / "Method/Notebooks"
            notebooks.mkdir(parents=True)
            (notebooks / "Report.ipynb").write_text(
                json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                            "nbformat_minor": 5}), encoding="utf-8")
            return impl.report_state(root, "Method", "Method")

    def drawing(self, outputs):
        return [_cell("markdown", "La figura muestra las curvas."),
                _cell("code", "figures.curves(path)", outputs=outputs)]

    def test_a_figure_that_came_out_as_a_description_is_caught(self):
        """El defecto real: `display(fig)` sin el formateador registrado emite
        `<Figure size ...>` como texto. La celda corrió, no levantó nada, produjo
        una salida — y le muestra al lector una línea de prosa donde va el dibujo.
        """
        found = self.state(self.drawing([_shown("text/plain", "<Figure size 640x480>")]))
        self.assertEqual(len(found["describedNotShown"]), 1, found["describedNotShown"])
        self.assertEqual(found["describedNotShown"][0]["drawing"], "figures.curves")
        self.assertEqual(found["describedNotShown"][0]["emitted"], ["text/plain"])

    def test_a_figure_that_printed_its_filename_is_caught(self):
        """Guardar y anunciar la ruta es la misma falla con otra ropa: la celda
        informa un nombre de archivo donde debería haber un resultado."""
        found = self.state(self.drawing([_stream("escrita: curves.pdf\n")]))
        self.assertEqual(len(found["describedNotShown"]), 1)
        self.assertEqual(found["describedNotShown"][0]["emitted"], ["texto"])

    def test_a_figure_that_actually_rendered_passes(self):
        """El verde tiene que ser alcanzable, o el rojo de arriba no prueba nada."""
        self.assertEqual(self.state(self.drawing([_shown("image/png")]))["describedNotShown"], [])

    def test_any_image_mime_counts_as_shown(self):
        """Nada acá puede saber en qué formato dibuja alguien. Un SVG es una
        figura mostrada tanto como un PNG, y exigir uno sería aprender la cadena
        de herramientas de un repositorio."""
        for mime in ("image/png", "image/svg+xml", "image/jpeg"):
            with self.subTest(mime=mime):
                self.assertEqual(
                    self.state(self.drawing([_shown(mime)]))["describedNotShown"], [])

    def test_a_measurement_computed_and_never_shown_is_caught(self):
        cells = [self.FRAME,
                 _cell("code", "tabla = tables.render(runs, 'accuracy', reduction)\n"
                               "conclusion = tables.conclusion(runs, 'accuracy', reduction)",
                       outputs=[])]
        found = self.state(cells)["unrendered"]
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["rendering"], "tables.render")

    def test_a_table_that_printed_is_not_reported_as_unrendered(self):
        self.assertEqual(self.state([self.FRAME, self.TABLE])["unrendered"], [])

    def test_the_cell_that_writes_the_record_may_show_nothing(self):
        """Escribir el registro es su trabajo entero. Exigirle una salida visible
        haría que la forma de aprobar sea imprimir el archivo."""
        cells = [self.FRAME, self.TABLE,
                 _cell("markdown", "el registro"),
                 _cell("code", "(root / 'r.txt').write_text("
                               "tables.render(runs, 'accuracy', reduction))",
                       outputs=[])]
        self.assertEqual(self.state(cells)["unrendered"], [])

    def test_an_unexecuted_cell_is_not_a_report_defect(self):
        """Un cuaderno sin ejecutar ya es un hallazgo de `validation`. Repetirlo
        acá como un defecto de informe por celda enterraría a los que sí lo son.
        """
        cells = [self.FRAME,
                 _cell("code", "print(tables.render(runs, 'accuracy', reduction))",
                       outputs=[], executed=False),
                 _cell("markdown", "la figura"),
                 _cell("code", "figures.curves(path)", outputs=[], executed=False)]
        state = self.state(cells)
        self.assertEqual(state["unrendered"], [])
        self.assertEqual(state["describedNotShown"], [])

    def test_a_cell_that_raised_is_reported_once_and_not_twice(self):
        """El error lo informa `notebook_execution`. Sin marcarlo, esta celda
        también leería como una que no mostró nada, y un defecto saldría dos
        veces con dos nombres distintos."""
        error = {"output_type": "error", "ename": "ValueError",
                 "evalue": "x", "traceback": []}
        state = self.state(self.drawing([error]))
        self.assertEqual(state["describedNotShown"], [])

    SILENT = DECLARATION.replace("        'figures': ['figures.curves'],\n", "")

    def test_a_description_is_caught_with_no_declaration_at_all(self):
        """El hallazgo del e2e sobre el repositorio real, convertido en prueba.

        Ese paquete declaraba `renderers` y `conclusions` y ninguna llamada de
        dibujo, así que la comprobación quedaba inerte justo en el repositorio
        cuyo defecto la motivó. Una red que solo se activa cuando alguien escribió
        una clave opcional no es una red. La forma de la salida alcanza: un
        `text/plain` que es el repr de un objeto es una descripción-de-figura la
        haya dibujado quien la haya dibujado, y ahí no se nombra ninguna librería.
        """
        state = self.state(self.drawing([_shown("text/plain", "<Figure size 640x480>")]),
                           self.SILENT)
        self.assertEqual(len(state["describedNotShown"]), 1, state["describedNotShown"])
        found = state["describedNotShown"][0]
        self.assertEqual(found["drawing"], "<sin declarar>")
        self.assertEqual(found["description"], "<Figure size 640x480>")
        self.assertEqual(state["status"], "drift")

    def test_the_repr_of_any_object_reads_as_a_description(self):
        """No hay una lista de librerías acá, y no puede haberla. Lo que delata al
        defecto es que la celda mostró el repr de algo en vez de la cosa."""
        for repr_text in ("<Figure size 640x480 with 6 Axes>",
                          "<matplotlib.axes._axes.Axes object at 0x10a3f>",
                          "[<Line2D object at 0x7fa1>]"):
            with self.subTest(repr_text=repr_text):
                state = self.state(self.drawing([_shown("text/plain", repr_text)]),
                                   self.SILENT)
                self.assertEqual(len(state["describedNotShown"]), 1, repr_text)

    def test_a_rich_rendering_carries_a_repr_beside_it_and_that_is_not_a_defect(self):
        """El falso positivo que el e2e sacó a la luz, y que la suite no cubría.

        Una salida rica guarda su repr de respaldo AL LADO: un Markdown mostrado
        deja `<IPython.core.display.Markdown object>` en `text/plain` junto a su
        `text/markdown`. Esa celda mostró lo que tenía que mostrar. Leer la celda
        entera en vez de cada salida marcaba las once celdas de encabezado del
        repositorio real como figuras que nunca se dibujaron — y once hallazgos
        falsos entierran al verdadero, que es peor que no tener el hallazgo.
        """
        rich = {"output_type": "display_data",
                "data": {"text/markdown": "## Qué mide",
                         "text/plain": "<IPython.core.display.Markdown object>"},
                "metadata": {}}
        state = self.state([self.FRAME, _cell("code", "display(Markdown(texto))",
                                              outputs=[rich])], self.SILENT)
        self.assertEqual(state["describedNotShown"], [])

    def test_ordinary_printed_output_is_not_a_description(self):
        """El rojo de arriba no sirve de nada si una tabla impresa también lo
        dispara: un informe que grita en cada celda se lee salteando."""
        for text in ("accuracy  0.81", "escrita: curves.pdf", "a < b > c"):
            with self.subTest(text=text):
                state = self.state([self.FRAME, _cell("code", "print(resumen)",
                                                      outputs=[_shown("text/plain", text)])],
                                   self.SILENT)
                self.assertEqual(state["describedNotShown"], [], text)

    def test_a_picture_no_declared_call_could_have_drawn_is_a_finding(self):
        """Lo que impide que las dos comprobaciones de arriba sean una cortesía.
        Sin esto, un paquete que no declara `figures` es indistinguible de uno
        cuyas figuras están todas bien — y el informe sale limpio."""
        state = self.state(self.drawing([_shown("image/png")]), self.SILENT)
        self.assertEqual(len(state["undeclaredDrawings"]), 1, state["undeclaredDrawings"])
        self.assertIn("figures.curves", state["undeclaredDrawings"][0]["calls"])
        self.assertEqual(state["status"], "drift")

    def test_a_declared_drawing_that_showed_its_picture_is_not_undeclared(self):
        """El verde tiene que seguir siendo alcanzable declarando, o el hallazgo
        de arriba no pide una declaración: pide que nadie dibuje."""
        state = self.state(self.drawing([_shown("image/png")]))
        self.assertEqual(state["undeclaredDrawings"], [])
        # No `ok`: sin intérprete del target la sonda `live` no corre y el estado
        # queda `incomplete`, que es una limitación del banco y no del hallazgo.
        # Lo que esta prueba defiende es que declarar y mostrar no produce deriva.
        self.assertNotEqual(state["status"], "drift")

    def _table_then_conclusion(self, table_out, conclusion_out):
        return [self.FRAME,
                _cell("code", "print(tables.render(runs, 'accuracy', reduction))",
                      outputs=[_shown("text/plain", table_out)]),
                _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))",
                      outputs=[_shown("text/plain", conclusion_out)])]

    def test_a_conclusion_that_restates_its_own_table_is_caught(self):
        """Encontrado leyendo un informe real, no razonando sobre el código.

        `duplicated` compara un renderizado con otro y no puede ver este caso: la
        segunda copia no es un renderizado, es una frase. Y el número no está en
        ninguna de las dos fuentes — está en lo que las dos celdas emitieron, así
        que solo se ve leyendo las salidas.
        """
        state = self.state(self._table_then_conclusion(
            "A 0.81 · B 0.74 · C 0.69 · D 0.55",
            "Los aciertos: A 0.81, B 0.74, C 0.69, D 0.55."))
        self.assertEqual(len(state["restated"]), 1, state["restated"])
        found = state["restated"][0]
        self.assertEqual(found["table"], 1)
        self.assertEqual(found["count"], 4)
        self.assertEqual(state["status"], "drift")

    def test_a_conclusion_may_name_the_value_it_rests_on(self):
        """El verde tiene que quedar alcanzable, o el hallazgo no pide una
        conclusión: pide una conclusión sin evidencia. Nombrar quién va adelante y
        con cuánto es el trabajo de la conclusión, no una segunda tabla."""
        state = self.state(self._table_then_conclusion(
            "A 0.81 · B 0.74 · C 0.69 · D 0.55",
            "Mejor: **A** con 0.81; peor: D con 0.55."))
        self.assertEqual(state["restated"], [])

    def test_a_conclusion_is_never_matched_against_another_notebook_table(self):
        """El emparejamiento se reinicia por cuaderno. Sin eso, la primera
        conclusión de un cuaderno se compararía contra la última tabla del
        anterior, y el hallazgo señalaría dos celdas que nunca se vieron."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src/Method_Benchmark").mkdir(parents=True)
            (root / "src/Method_Benchmark/__init__.py").write_text(
                self.DECLARATION, encoding="utf-8")
            notebooks = root / "Method/Notebooks"
            notebooks.mkdir(parents=True)
            (notebooks / "A_tabla.ipynb").write_text(json.dumps({
                "cells": [self.FRAME,
                          _cell("code", "print(tables.render(runs, 'accuracy', reduction))",
                                outputs=[_shown("text/plain", "A 0.81 B 0.74 C 0.69")])],
                "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
            (notebooks / "B_conclusion.ipynb").write_text(json.dumps({
                "cells": [self.FRAME,
                          _cell("code", "print(tables.conclusion(runs, 'accuracy', reduction))",
                                outputs=[_shown("text/plain", "A 0.81 B 0.74 C 0.69")])],
                "metadata": {}, "nbformat": 4, "nbformat_minor": 5}), encoding="utf-8")
            state = impl.report_state(root, "Method", "Method")
        self.assertEqual(state["restated"], [])

    def test_the_echo_still_shows_the_key_when_nothing_was_declared(self):
        """Declarar ninguna llamada no es lo mismo que no dibujar, y el eco lo
        tiene que dejar ver en vez de callar."""
        state = self.state([self.FRAME, self.TABLE], self.SILENT)
        self.assertEqual(state["declared"]["figures"], [])

    def test_a_figure_defect_puts_the_whole_report_in_drift(self):
        """Sin esto el hallazgo existiría y no frenaría nada: es el estado del
        informe lo que hace que `probe` conteste `report-first` en vez de ofrecer
        la campaña."""
        state = self.state(self.drawing([_shown("text/plain", "<Figure ...>")]))
        self.assertEqual(state["status"], "drift")


class CellOutputEndToEndTests(unittest.TestCase):
    """El chequeo, desde `argv` hasta el JSON que lee una persona.

    Las pruebas de arriba llaman a `report_state` directo, así que verifican las
    dos mitades y nunca la unión. Esta cruza la junta: arma un repositorio de
    juguete, corre el CLI como proceso, y le pregunta a la herramienta qué ve.

    El objetivo vive bajo `implementations/` porque el guardia lo exige, con un
    nombre que no puede chocar con nada, y se borra pase lo que pase.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {},\n"
        "    'report': {\n"
        "        'renderers': ['tables.render'],\n"
        "        'conclusions': ['tables.conclusion'],\n"
        "        'objectiveEntry': 'tables.objective',\n"
        "        'figures': ['figures.curves'],\n"
        "        'components': {'terms': ['fit'], 'share': None},\n"
        "        'dimensions': {'accuracy': 'higher', 'fit': None},\n"
        "    },\n"
        "}\n"
    )

    def verify_with(self, outputs):
        box = FORGE / "implementations" / f"_e2e_cell_outputs_{os.getpid()}"
        try:
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "Method/Notebooks").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method_Benchmark/__init__.py").write_text(
                self.DECLARATION, encoding="utf-8")
            cells = [_cell("markdown", "La figura muestra las curvas."),
                     _cell("code", "figures.curves(path)", outputs=outputs)]
            (box / "Method/Notebooks/Report.ipynb").write_text(
                json.dumps({"cells": cells, "metadata": {}, "nbformat": 4,
                            "nbformat_minor": 5}), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "verify", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    def test_the_defect_reaches_the_reported_json(self):
        report = self.verify_with(
            [_shown("text/plain", "<Figure size 640x480 with 6 Axes>")])["report"]
        self.assertEqual(report["status"], "drift")
        self.assertEqual([f["drawing"] for f in report["describedNotShown"]],
                         ["figures.curves"])

    def test_a_shown_figure_clears_it(self):
        report = self.verify_with([_shown("image/png")])["report"]
        self.assertEqual(report["describedNotShown"], [])

    def test_the_toy_target_left_nothing_behind(self):
        self.verify_with([_shown("image/png")])
        leftover = list((FORGE / "implementations").glob("_e2e_cell_outputs_*"))
        self.assertEqual(leftover, [], leftover)


# ------------------------------- la junta entre el método y el arnés que lo mide

def _module(revision, sections, equations, imports=""):
    return (f"{imports}"
            f"__provenance__ = {{\n"
            f"    'revision': {revision!r},\n"
            f"    'sections': {sections!r},\n"
            f"    'equations': {equations!r},\n"
            f"    'invariants': [],\n"
            f"}}\n")


class UnreachedMathematicsEndToEndTests(unittest.TestCase):
    """El brazo declara que ejercita una sección y nunca llama a lo que la implementa.

    Es la única junta que ninguna otra comprobación cruzaba. `verify` leía la
    procedencia del método y la declaración del banco como dos documentos separados,
    y los dos pueden estar impecables mientras el brazo reimplementa la ecuación en
    vez de llamarla: el módulo declara sus secciones, el brazo declara las mismas, y
    nunca se encuentran.

    No es hipotético. Así corrió una campaña entera con un brazo calculando una forma
    simplificada del término que declaraba, con todos los chequeos en verde.

    Los módulos del juguete se llaman por su ROL en la prueba y no por ninguna
    matemática. El chequeo es estructural: no sabe qué es una sección ni qué implementa
    un módulo, y un fixture con nombres de un método real sugeriría que sí.
    """

    DECLARATION = (
        "__benchmark__ = {\n"
        "    'revision': 'r01.md',\n"
        "    'arms': {\n"
        "        'floor': {'sections': ['3']},\n"
        "        'full': {'sections': ['3', '5']},\n"
        "    },\n"
        "}\n"
    )

    def verify_with(self, wiring):
        box = FORGE / "implementations" / f"_e2e_unreached_{os.getpid()}"
        try:
            (box / "src/Method").mkdir(parents=True)
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "tests").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
            # Imported by the harness, and the only way the next one is reached.
            (box / "src/Method/called.py").write_text(
                _module("r01.md", ["3"], ["11"],
                        imports="from Method.reached_through import reached_through\n"),
                encoding="utf-8")
            # Reached only through `called`: a direct-import check would call this
            # missing on every faithful repository, so it is pinned here.
            (box / "src/Method/reached_through.py").write_text(
                _module("r01.md", ["3"], ["21"]), encoding="utf-8")
            # The defect: the arms declare sections 3 and 5, and nobody calls it.
            (box / "src/Method/never_called.py").write_text(
                _module("r01.md", ["3", "5"], ["12", "13"]), encoding="utf-8")
            # Mathematics no arm claims. Unreached, and correctly silent.
            (box / "src/Method/unclaimed.py").write_text(
                _module("r01.md", ["9"], ["31"]), encoding="utf-8")

            (box / "src/Method_Benchmark/__init__.py").write_text(
                self.DECLARATION, encoding="utf-8")
            (box / "src/Method_Benchmark/wiring.py").write_text(wiring,
                                                                encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "verify", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    WITHOUT = "from Method.called import called\n"
    WITH = "from Method.called import called\nfrom Method.never_called import total\n"

    def test_a_module_no_arm_calls_is_named_with_its_equations(self):
        fidelity = self.verify_with(self.WITHOUT)["fidelity"]
        unreached = fidelity["benchmark"]["unreachedModules"]
        self.assertEqual([u["module"] for u in unreached], ["src/Method/never_called.py"])
        # The equation, not the section it lives in: that is what a reader acts on.
        self.assertEqual(unreached[0]["equations"], ["12", "13"])
        self.assertEqual(unreached[0]["declaredBy"], ["floor", "full"])

    def test_the_defect_is_not_left_inside_a_headline_that_reads_ok(self):
        """Un defecto que solo vive dentro de `benchmark` mientras `fidelity` dice
        `ok` es exactamente el silencio que este chequeo viene a romper."""
        fidelity = self.verify_with(self.WITHOUT)["fidelity"]
        self.assertEqual(fidelity["benchmark"]["status"], "unfaithful")
        self.assertEqual(fidelity["status"], "drift")

    def test_calling_it_clears_the_finding(self):
        """El otro polo. Sin esto, un chequeo que siempre marca rojo no distingue
        un arnés infiel de uno fiel, y aprobar sería imposible."""
        fidelity = self.verify_with(self.WITH)["fidelity"]
        self.assertEqual(fidelity["benchmark"]["unreachedModules"], [])
        self.assertEqual(fidelity["benchmark"]["status"], "ok")
        self.assertEqual(fidelity["status"], "ok")

    def test_a_module_reached_through_another_is_not_reported(self):
        """`called` importa `reached_through`, así que el arnés la ejercita sin nombrarla.
        Marcarla haría que el hallazgo se ignore en todo repositorio real."""
        unreached = self.verify_with(self.WITHOUT)["fidelity"]["benchmark"]
        self.assertNotIn("src/Method/reached_through.py",
                         [u["module"] for u in unreached["unreachedModules"]])

    def test_mathematics_no_arm_claims_stays_silent(self):
        """Un método puede cargar más de lo que una comparación ejercita. Exigir que
        todo módulo se llame dispararía sobre eso y enseñaría a saltear el hallazgo.

        Se mide sobre el caso que SÍ marca: con `WITH` la lista queda vacía por el
        control y `unclaimed` pasaría aunque nada lo estuviera silenciando.
        """
        unreached = self.verify_with(self.WITHOUT)["fidelity"]["benchmark"]
        reported = [u["module"] for u in unreached["unreachedModules"]]
        self.assertNotIn("src/Method/unclaimed.py", reported)
        self.assertIn("src/Method/never_called.py", reported)

    def probe_with(self, wiring):
        """Un juguete que llega hasta donde se ofrece la corrida.

        Hace falta lo mismo que en cualquier repositorio real para que la pregunta
        exista: algo contra qué comparar, y un backend entrenable. Sin las dos cosas
        `probe` contesta otra cosa mucho antes y la compuerta no se ejercita nunca.
        """
        box = FORGE / "implementations" / f"_e2e_unreached_probe_{os.getpid()}"
        try:
            (box / "src/Method").mkdir(parents=True)
            (box / "src/Method_Benchmark").mkdir(parents=True)
            (box / "src/Prior").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src/Method/__init__.py").write_text("", encoding="utf-8")
            (box / "src/Method/called.py").write_text(
                _module("r01.md", ["3"], ["11"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Method/never_called.py").write_text(
                _module("r01.md", ["3", "5"], ["12", "13"], imports="import torch\n"),
                encoding="utf-8")
            (box / "src/Prior/model.py").write_text("import torch\n", encoding="utf-8")
            (box / "src/Method_Benchmark/__init__.py").write_text(
                self.DECLARATION, encoding="utf-8")
            (box / "src/Method_Benchmark/wiring.py").write_text(wiring, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(CLI), "probe", "--target", str(box),
                 "--name", "Method", "--revision", "r01.md"],
                capture_output=True, text=True, cwd=FORGE)
            return json.loads(proc.stdout or "{}")
        finally:
            shutil.rmtree(box, ignore_errors=True)

    def test_the_run_is_not_offered_while_an_arm_does_not_call_what_it_declares(self):
        """El hallazgo tiene que frenar la campaña, no solo figurar: cada número
        vendría de un brazo que no computa lo que la tabla dice que computó."""
        probe = self.probe_with(self.WITHOUT)
        self.assertEqual(probe["nextStep"], "wiring-first")
        self.assertEqual([u["module"] for u in probe["unreachedModules"]],
                         ["src/Method/never_called.py"])

    def test_the_offer_comes_back_once_the_arm_calls_it(self):
        """El polo de control de la compuerta. Sin él, `wiring-first` podría estar
        frenando por cualquier motivo y la prueba de arriba no lo notaría."""
        probe = self.probe_with(self.WITH)
        self.assertEqual(probe["unreachedModules"], [])
        self.assertNotEqual(probe["nextStep"], "wiring-first")

    def test_the_toy_target_left_nothing_behind(self):
        self.verify_with(self.WITH)
        leftover = list((FORGE / "implementations").glob("_e2e_unreached_*"))
        self.assertEqual(leftover, [], leftover)


class RemoteExecutionLedgerSectionTests(unittest.TestCase):
    """`verify`'s ledger section, read service-blind through `ledger.py` alone.

    A guard you have to go looking for is a guard nobody looks at — that is
    why this section lives inside `verify` rather than a command of its own,
    and it is what these tests hold it to: it reports what was sent, what
    came back, and what changed since, and it never resolves anything and
    never names a worker.
    """

    def _write_ledger(self, target: Path, name: str, lines: list) -> Path:
        ledger_path = target / name / ".remote-execution" / "ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(
            "\n".join(lines) + "\n" if lines else "", encoding="utf-8")
        return ledger_path

    def _minimal_source(self, target: Path) -> None:
        """Enough of `src/` for `source_digest()` to compute over something
        real, so a "stale" fixture is stale against an actual hash and not
        an accident of an empty tree."""
        module = target / "src" / "Method" / "module.py"
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("VALUE = 1\n", encoding="utf-8")

    def test_absent_when_no_remote_execution_skill_present(self):
        """The one state every target predates this section in, and the one
        `verify` must stay safe on without anyone touching a target at all."""
        from unittest import mock

        box = FORGE / "implementations" / f"_re_absent_{os.getpid()}"
        try:
            (box / "src" / "Method").mkdir(parents=True)
            (box / "src" / "Method_Benchmark").mkdir(parents=True)
            (box / "tests").mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(box)], check=True,
                           capture_output=True)
            (box / "src" / "Method" / "__init__.py").write_text("", encoding="utf-8")
            (box / "src" / "Method_Benchmark" / "__init__.py").write_text(
                "__benchmark__ = {}\n", encoding="utf-8")

            missing_script = box / "no-such-skill" / "ledger.py"
            with mock.patch.object(impl, "REMOTE_EXECUTION_LEDGER_SCRIPT", missing_script):
                result = impl.cmd_verify(
                    argparse.Namespace(target=str(box), name="Method", revision=None))
        finally:
            shutil.rmtree(box, ignore_errors=True)

        # The whole of verify, not just the new key: this is the case every
        # existing target is in today, so it is the one that must never crash it.
        self.assertEqual(result["command"], "verify")
        self.assertEqual(result["remoteExecution"], {"status": "absent"})

    def test_absent_when_the_skill_is_present_but_nothing_was_ever_sent(self):
        """Absence of data reads the same as absence of the capability: an
        installed skill with no ledger file for this target has nothing to
        report either, and reporting it as `ok` would claim a fact — that a
        run completed cleanly — nobody has any evidence for."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            state = impl.remote_execution_state(target, "Method", "Method")
            self.assertEqual(state, {"status": "absent"})

    def test_drift_when_a_pending_submission_s_source_has_moved(self):
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            self._write_ledger(target, "Method", [json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:00:00Z",
                "entrypoint": "Method/Notebooks/verification.ipynb",
                "sourceDigest": "0" * 64, "submissionId": "s1", "worker": "w1",
                "requestedCapacity": 1, "grantedCapacity": 1,
            })])
            state = impl.remote_execution_state(target, "Method", "Method")
            self.assertEqual(state["status"], "drift")
            self.assertEqual(state["staleInFlight"],
                            ["Method/Notebooks/verification.ipynb"])
            self.assertEqual(state["fromStaleSubmission"], [])
            self.assertEqual(state["pending"], 1)
            self.assertEqual(state["sent"], 1)

    def test_unreliable_when_a_line_cannot_be_read(self):
        """Reachable only against a log that is otherwise clean: if
        `unreadableLines` did not override an otherwise-`ok` verdict, this
        would read `ok` with the corrupted line silently dropped."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            live = impl.source_digest(target, "Method")
            lines = [json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:00:00Z",
                "entrypoint": "Method/Notebooks/verification.ipynb",
                "sourceDigest": live, "submissionId": "s1", "worker": "w1",
                "requestedCapacity": 1, "grantedCapacity": 1,
            }), json.dumps({
                "kind": "returned", "ts": "2026-08-17T00:05:00Z",
                "submissionId": "s1", "artifactPath": "out/s1", "observedConcurrency": 1,
            }), "{not valid json"]
            self._write_ledger(target, "Method", lines)
            state = impl.remote_execution_state(target, "Method", "Method")
            self.assertEqual(state["unreadableLines"], 1)
            # Otherwise-clean and still `unreliable`: an unread line must
            # outrank a report that would read `ok` without it.
            self.assertEqual(state["returned"], 1)
            self.assertEqual(state["status"], "unreliable")

    def test_a_quarantined_result_is_reported_and_never_treated_as_merged(self):
        """The result from a superseded submission arrives, is named, and
        never promotes its entrypoint's current state to `returned`."""
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            live = impl.source_digest(target, "Method")
            entrypoint = "Method/Notebooks/verification.ipynb"
            lines = [json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:00:00Z",
                "entrypoint": entrypoint, "sourceDigest": live,
                "submissionId": "s1", "worker": "w1",
                "requestedCapacity": 1, "grantedCapacity": 1,
            }), json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:10:00Z",
                "entrypoint": entrypoint, "sourceDigest": live,
                "submissionId": "s2", "worker": "w1",
                "requestedCapacity": 1, "grantedCapacity": 1,
            }), json.dumps({
                # Arrives late, for the superseded submission s1.
                "kind": "returned", "ts": "2026-08-17T00:20:00Z",
                "submissionId": "s1", "artifactPath": "out/s1", "observedConcurrency": 1,
            })]
            self._write_ledger(target, "Method", lines)
            state = impl.remote_execution_state(target, "Method", "Method")
            self.assertEqual(state["quarantined"], 1)
            self.assertEqual(state["fromStaleSubmission"], [entrypoint])
            # s2, the entrypoint's LATEST submission, has no terminal event of
            # its own yet: the quarantined result for s1 must not count here.
            self.assertEqual(state["returned"], 0)
            self.assertEqual(state["pending"], 1)
            self.assertEqual(state["status"], "drift")

    def test_the_section_names_no_service(self):
        """The test the user cares most about: a ledger whose workers carry
        service-shaped usernames must never leak one into the section's JSON,
        and `workers` must be a count. Assert this over the section's full
        JSON dump — asserting field-by-field would let a leak hide in a key
        this test forgot to check."""
        service_shaped_workers = ("kaggle-svc-worker-42", "prod-training-bot-07")
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw)
            self._minimal_source(target)
            live = impl.source_digest(target, "Method")
            lines = [json.dumps({
                "kind": "submitted", "ts": "2026-08-17T00:00:00Z",
                "entrypoint": f"Method/Notebooks/n{i}.ipynb",
                "sourceDigest": live, "submissionId": f"s{i}", "worker": worker,
                "requestedCapacity": 1, "grantedCapacity": 1,
            }) for i, worker in enumerate(service_shaped_workers)]
            self._write_ledger(target, "Method", lines)
            state = impl.remote_execution_state(target, "Method", "Method")

            dumped = json.dumps(state)
            for worker in service_shaped_workers:
                self.assertNotIn(worker, dumped, worker)
            self.assertIsInstance(state["workers"], int)
            self.assertEqual(state["workers"], len(service_shaped_workers))
