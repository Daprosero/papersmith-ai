"""`paper_figure_audit.py` — the figure-prose semantic auditor.

Pure-input tests: `audit_semantics` takes strings and dicts, so none of this
needs a paper tree, a manifest on disk, or a toolchain. The wiring that
FEEDS it (the standalone verb, and `verify`'s eighth check through
`paper_coupling_evidence.gather`) is exercised in `test_paper_figure.py`
and `test_paper_writing.py`.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_block  # noqa: E402
import paper_coupling_evidence  # noqa: E402
import paper_figure_audit  # noqa: E402
import paper_scaffold  # noqa: E402
import paper_verify  # noqa: E402

FIGURE_WITH_THREE = (
    "% node: alpha\n"
    "% node: beta\n"
    "% node: gamma\n"
    "\\node[draw] (a) {Alpha};\n"
    "\\node[draw] (b) {Beta};\n"
    "\\draw[->] (a) -- (b);\n"
)

#: A `figure:` obligation shaped exactly as `paper_contract._parse_figure`
#: emits one, so a drift between that shape and this module's reading is a
#: test failure rather than a runtime surprise.
OBLIGATION = {
    "ordered": True,
    "excludes": [],
    "caption_enumerates": False,
    "caption_decodes": False,
    "mandatory": False,
    "components_from": "contributions",
}


def _audit(tex: str, manifest: dict, prose: str, **overrides) -> dict:
    obligation = dict(OBLIGATION)
    obligation.update(overrides.pop("contract_figure", {}) or {})
    contract_figure = overrides.pop("contract_figure_override", obligation)
    return paper_figure_audit.audit_semantics(
        tex=tex,
        manifest=manifest,
        section_text=prose,
        contract_figure=contract_figure,
        expected_components=overrides.pop("expected_components", ["alpha", "beta", "gamma"]),
    )


class NormalizeTests(unittest.TestCase):
    """The comparison folds style away, never meaning."""

    def test_math_delimiters_and_subscripts_do_not_break_a_label_apart(self) -> None:
        self.assertEqual(
            paper_figure_audit.normalize("$F_1$"), paper_figure_audit.normalize("F1"),
        )

    def test_case_and_escaping_are_folded(self) -> None:
        # `_` JOINS (`F_1` is `f1`, never `f 1`), so an escaped underscore is
        # folded the same way rather than becoming a word break.
        self.assertEqual(
            paper_figure_audit.normalize("Deep\\_Net"), paper_figure_audit.normalize("DEEPNET"),
        )
        self.assertEqual(
            paper_figure_audit.normalize("Deep Net"), paper_figure_audit.normalize("deep net"),
        )

    def test_a_command_leaves_its_argument_behind(self) -> None:
        self.assertEqual(paper_figure_audit.normalize("\\textbf{Deep}"), "deep")


class PhantomNodeTests(unittest.TestCase):
    """A manifest component the prose never carries fails the audit."""

    def test_a_component_absent_from_prose_lands_in_unmatched_nodes(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE,
            {"components": ["alpha", "beta", "phantom"]},
            "The pipeline runs alpha and beta end to end.",
            expected_components=["alpha", "beta"],
        )
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["unmatched_nodes"], ["phantom"])
        self.assertTrue(any("phantom" in action for action in report["remediation"]))

    def test_a_decorative_node_is_not_a_phantom_component(self) -> None:
        # The audit's subject is the MANIFEST, never every `\node{}` string:
        # an axis label nobody declares is not a missing component.
        tex = FIGURE_WITH_THREE + "\\node[draw] (axis) {$x$};\n"
        report = _audit(
            tex, {"components": ["alpha", "beta"]}, "alpha and beta",
            expected_components=["alpha", "beta"],
        )
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["unmatched_nodes"], [])
        self.assertIn("$x$", report["evidence"]["node_texts"])


class MissingPipelineStepTests(unittest.TestCase):
    """The `components_from` fact list is a different pair from `check_components`."""

    def test_a_step_absent_from_manifest_and_prose_is_named(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE,
            {"components": ["alpha", "beta"]},
            "alpha and beta, nothing else.",
            expected_components=["alpha", "beta", "gamma"],
        )
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["missing_pipeline_steps"], ["gamma"])

    def test_a_step_present_in_the_prose_alone_is_not_missing(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE,
            {"components": ["alpha", "beta"]},
            "alpha, beta, and the gamma stage that follows them.",
            expected_components=["alpha", "beta", "gamma"],
        )
        self.assertEqual(report["missing_pipeline_steps"], [])
        self.assertEqual(report["verdict"], "pass")


class CleanPassTests(unittest.TestCase):
    """Figure, manifest, contract and prose fully aligned."""

    def test_a_fully_aligned_figure_passes_with_every_list_empty(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE,
            {"components": ["alpha", "beta", "gamma"]},
            "The pipeline runs alpha, then beta, then gamma.",
        )
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["unmatched_nodes"], [])
        self.assertEqual(report["missing_pipeline_steps"], [])
        self.assertEqual(report["label_mismatches"], [])
        self.assertEqual(report["warnings"], [])
        self.assertEqual(sorted(report["matched_nodes"]), ["alpha", "beta", "gamma"])


class LabelParityTests(unittest.TestCase):
    """Acronym drift is a warning, never a failure."""

    def test_an_acronym_the_prose_spells_out_is_a_warning_not_a_failure(self) -> None:
        tex = "% node: CNN\n\\node[draw] (c) {CNN};\n"
        report = paper_figure_audit.audit_semantics(
            tex=tex,
            manifest={"components": ["CNN"]},
            section_text="We train a convolutional neural network end to end.",
            contract_figure=None,
            expected_components=None,
        )
        self.assertEqual(report["label_mismatches"], [{"component": "CNN", "token": "CNN"}])
        self.assertTrue(any("CNN" in warning for warning in report["warnings"]))
        # A naming choice in the prose is not a missing component, and the
        # component comparison itself did run: `pass`, not `unmeasured`.
        self.assertEqual(report["unmatched_nodes"], [])
        self.assertEqual(report["verdict"], "pass")

    def test_a_descriptive_component_absent_from_prose_is_a_failure_not_a_warning(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE,
            {"components": ["alpha", "beta", "invented stage"]},
            "alpha and beta only.",
            expected_components=["alpha", "beta"],
        )
        self.assertEqual(report["verdict"], "fail")
        self.assertIn("invented stage", report["unmatched_nodes"])
        self.assertEqual(report["label_mismatches"], [])


class UnmeasuredTests(unittest.TestCase):
    """`unmeasured` is never folded into `pass` — the false-green guard."""

    def test_no_contract_figure_still_measures_the_components(self) -> None:
        # An unknown binding makes the PIPELINE-STEP comparison unmeasurable,
        # not the component comparison: `verify`'s aggregate path cannot bind
        # a figure id to a block (no such binding is declared anywhere), and
        # poisoning a reached verdict with that gap would be the false-green
        # rule read backwards.
        report = paper_figure_audit.audit_semantics(
            tex=FIGURE_WITH_THREE, manifest={"components": ["alpha", "beta", "gamma"]},
            section_text="alpha beta gamma", contract_figure=None,
        )
        self.assertEqual(report["verdict"], "pass")
        self.assertIsNone(report["unmeasured_reason"])
        self.assertEqual(report["pipeline_steps_reason"], "CONTRACT_FIGURE_ABSENT")
        self.assertEqual(report["missing_pipeline_steps"], [])

    def test_a_contract_with_no_components_from_is_unmeasured(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE, {"components": ["alpha", "beta", "gamma"]}, "alpha beta gamma",
            contract_figure={"components_from": None}, expected_components=None,
        )
        self.assertEqual(report["verdict"], "unmeasured")
        self.assertEqual(report["unmeasured_reason"], "NO_COMPONENTS_FROM")

    def test_an_unresolved_fact_is_unmeasured(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE, {"components": ["alpha", "beta", "gamma"]}, "alpha beta gamma",
            expected_components=None,
        )
        self.assertEqual(report["verdict"], "unmeasured")
        self.assertEqual(report["unmeasured_reason"], "COMPONENTS_FACT_UNRESOLVED")

    def test_a_manifest_with_no_components_is_unmeasured(self) -> None:
        report = _audit(FIGURE_WITH_THREE, {"components": []}, "alpha beta gamma")
        self.assertEqual(report["verdict"], "unmeasured")
        self.assertEqual(report["unmeasured_reason"], "NO_COMPONENTS_DECLARED")

    def test_missing_prose_is_never_a_pass(self) -> None:
        report = _audit(FIGURE_WITH_THREE, {"components": ["alpha", "beta", "gamma"]}, "")
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(sorted(report["unmatched_nodes"]), ["alpha", "beta", "gamma"])


class ExcludedComponentTests(unittest.TestCase):
    """`check_excluded`'s `Refused` becomes a finding, never a CLI refusal."""

    def test_an_excluded_class_present_in_the_manifest_is_a_failure_finding(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE,
            {"components": ["alpha", "beta", "gamma", "dataset overview"]},
            "alpha beta gamma dataset overview",
            contract_figure={"excludes": ["dataset"]},
            expected_components=["alpha", "beta", "gamma"],
        )
        self.assertEqual(report["verdict"], "fail")
        self.assertTrue(any("EXCLUDED_COMPONENT" in action for action in report["remediation"]))

    def test_a_clean_excludes_list_produces_no_finding(self) -> None:
        report = _audit(
            FIGURE_WITH_THREE, {"components": ["alpha", "beta", "gamma"]}, "alpha beta gamma",
            contract_figure={"excludes": ["dataset"]},
        )
        self.assertNotIn("EXCLUDED_COMPONENT", " ".join(report["remediation"]))


class ReportShapeTests(unittest.TestCase):
    """The envelope is `paper_cli`-safe and `paper_verify`-shaped."""

    def test_the_payload_carries_no_status_key(self) -> None:
        # `paper_cli.main` emits `{"status": "ok", ..., **result}` — a result
        # field named `status` would silently override the framework's.
        report = _audit(FIGURE_WITH_THREE, {"components": ["alpha", "beta", "gamma"]}, "alpha beta gamma")
        self.assertNotIn("status", report)

    def test_the_verdict_is_the_closed_paper_verify_vocabulary(self) -> None:
        sys.path.insert(0, str(SKILL_SCRIPTS))
        import paper_verify

        report = _audit(FIGURE_WITH_THREE, {"components": ["alpha", "beta", "gamma"]}, "alpha beta gamma")
        self.assertIn(report["verdict"], paper_verify._VERDICTS)
        self.assertNotIn("WARN", report.values())


class VerifyWiringTests(unittest.TestCase):
    """The eighth `verify` check, end to end through `gather()`.

    This is the wiring the C4 corrective moved out of `paper_verify.py`: the
    invocation lives in `paper_coupling_evidence.gather()` (which may read a
    disk and import the auditor), and what crosses into `paper_verify.py` is
    an already-computed dict.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.paper_dir = root / "paper"
        self.sections_dir = root / "sections"
        self.sections_dir.mkdir(parents=True)
        self._build_paper()

    def _build_paper(self, body: str | None = None) -> None:
        paper_scaffold.scaffold(self.paper_dir)
        paper_block.open_block(self.paper_dir, "methods-body", at_end=True)
        paper_block.substitute(
            self.paper_dir, "methods-body",
            new_body=(body or "The pipeline runs alpha then beta.").encode("utf-8"),
        )
        (self.paper_dir / "couplings.json").write_text(
            json.dumps({"blocks": {"methods-body": {}}}), encoding="utf-8",
        )
        header = {
            "section": "methods", "position": 1,
            "blocks": [{
                "id": "methods-diagram", "requires_facts": [], "requires_declarations": [],
                "citations": "none",
                "figure": {
                    "ordered": True, "excludes": [], "caption_enumerates": False,
                    "caption_decodes": False, "mandatory": False,
                },
            }],
        }
        self._write_section("01-methods", header, body or "The pipeline runs alpha then beta.")
        self._write_figure("methods-figure", ["alpha", "beta"])

    def _write_section(self, stem: str, header: dict, body: str) -> None:
        self.sections_dir.joinpath(f"{stem}.md").write_text(
            "---\n" + json.dumps(header, indent=2) + "\n---\n\n" + body + "\n",
            encoding="utf-8",
        )

    def _write_figure(self, figure_id: str, components: list) -> None:
        figures = self.paper_dir / "Figures"
        figures.mkdir(parents=True, exist_ok=True)
        figures.joinpath(f"{figure_id}.tex").write_text(
            "\n".join(f"% node: {component}" for component in components) + "\n",
            encoding="utf-8",
        )
        figures.joinpath(f"{figure_id}.diagram.json").write_text(
            json.dumps({
                "components": components, "encodings": [],
                "caption": "Figure: " + ", ".join(components) + ".",
            }),
            encoding="utf-8",
        )

    def _evidence(self):
        return paper_coupling_evidence.gather(self.paper_dir, self.sections_dir)

    def _figure_entry(self, report: dict) -> dict:
        return next(entry for entry in report["checks"] if entry["check"] == "figure-semantics")

    def test_a_paper_with_no_figure_reports_no_figure_declared(self) -> None:
        self.sections_dir.joinpath("01-methods.md").unlink()
        self.paper_dir.joinpath("Figures").rename(self.paper_dir / "Figures-gone")

        evidence = self._evidence()

        self.assertIsNone(evidence.figure_semantics)
        entry = self._figure_entry(paper_verify.run(evidence))
        self.assertEqual(entry["verdict"], "unmeasured")
        self.assertEqual(entry["unmeasured_reason"], "NO_FIGURE_DECLARED")

    def test_a_figure_manifest_that_cannot_be_audited_reports_unmeasured(self) -> None:
        # The manifest's `<id>.tex` is removed, so `gather()`'s guard skips
        # it: a figure IS declared on disk, and the eighth check must say the
        # audit could not reach a verdict — never "no figure declared".
        (self.paper_dir / "Figures" / "methods-figure.tex").unlink()

        evidence = self._evidence()

        self.assertEqual(evidence.figure_semantics["verdict"], "unmeasured")
        entry = self._figure_entry(paper_verify.run(evidence))
        self.assertEqual(entry["verdict"], "unmeasured")
        self.assertEqual(entry["unmeasured_reason"], "FIGURE_SEMANTICS_UNMEASURED")

    def test_an_aligned_figure_passes_the_eighth_check(self) -> None:
        evidence = self._evidence()

        self.assertEqual(evidence.figure_semantics["verdict"], "pass")
        entry = self._figure_entry(paper_verify.run(evidence))
        self.assertEqual(entry["verdict"], "pass")
        self.assertIsNone(entry["unmeasured_reason"])

    def test_a_phantom_component_fails_the_eighth_check(self) -> None:
        self._write_figure("methods-figure", ["alpha", "beta", "phantom"])

        evidence = self._evidence()

        self.assertEqual(evidence.figure_semantics["verdict"], "fail")
        entry = self._figure_entry(paper_verify.run(evidence))
        self.assertEqual(entry["verdict"], "fail")
        figures = entry["evidence"]["figures"]
        self.assertIn("phantom", figures["methods-figure"]["unmatched_nodes"])

    def test_the_eighth_check_never_touches_a_path_typed_field(self) -> None:
        # The AST read lock is exercised in `test_paper_writing.py`; this is
        # the behavioural half — the check runs off the dict `gather()`
        # stored, with no `paper_dir`/`sections_dir` access at all.
        source = Path(str(paper_verify.__file__)).read_text(encoding="utf-8")
        self.assertNotIn("evidence.paper_dir", source)
        self.assertNotIn("evidence.sections_dir", source)

    def test_the_existing_seven_checks_are_unchanged(self) -> None:
        report = paper_verify.run(self._evidence())
        self.assertEqual(
            [entry["check"] for entry in report["checks"]],
            [
                "contribution-list", "chain", "gap", "artefacts",
                "future-work", "citations", "contract-currency", "figure-semantics",
            ],
        )


if __name__ == "__main__":
    unittest.main()
