"""Name normalization and reorganization scale — the two v2 gates that are code.

The rest of the v2 flow is orchestration and lives in SKILL.md, where a test cannot
reach it. These two are decisions the CLI makes on its own, so they are pinned here:
what the user types becomes a directory/package pair deterministically, and a plan
declares whether the user can still review it.
"""

import json
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

def _cell(kind, text):
    cell = {"cell_type": kind, "metadata": {}, "source": [text]}
    if kind == "code":
        cell |= {"execution_count": 1, "outputs": []}
    return cell


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
        "        'dimensions': {'accuracy': 'higher', 'seconds': 'lower'},\n"
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
        _cell("code", "print(tables.render(runs, 'accuracy', reduction))\n"
                      "print(tables.conclusion(runs, 'accuracy', reduction))"),
    ]

    def test_a_well_formed_report_passes_every_static_check(self):
        state = self.state(self.WELL_FORMED)
        for finding in ("proseNumbers", "duplicated", "unframed", "unconcluded"):
            self.assertEqual(state[finding], [], f"{finding}: {state[finding]}")

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
