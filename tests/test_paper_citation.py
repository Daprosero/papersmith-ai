"""no-claim-without-a-source-that-holds-it: WU3 (verdict accounting, the
bounded search loop, and regime-dispatched placement).

Same shape `tests/test_paper_evidence.py` already uses: every fixture lives
under a `TemporaryDirectory`, and the mutation tests reuse `_run_against_mutant`
from `tests/paper_mutation.py`.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
SECTIONS_DIR = FORGE_ROOT / "sections"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_block  # noqa: E402
import paper_cli  # noqa: E402
import paper_evidence  # noqa: E402
import paper_scaffold  # noqa: E402
import paper_validate  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_mutation import _run_against_mutant  # noqa: E402


class SatisfiedClaimsTests(unittest.TestCase):
    """`citation-validation`, Requirement: Three Verdicts, `insufficient` Is
    Not Lenient -- `insufficient` and `does-not-hold` are IDENTICAL to the
    accounting, proven by excluding both from the same record set."""

    def test_satisfied_excludes_does_not_hold_and_insufficient(self) -> None:
        # `min_sources=1` here is deliberate: this test proves ONLY the
        # leniency exclusion (does-not-hold/insufficient never satisfy),
        # orthogonal to `the-pdf-arrives-or-the-operator-is-told`'s own
        # distinct-source-count feature -- `DistinctSourceCoverageTests`
        # below owns that.
        records = [
            {"claim": "true-claim", "verdict": "holds", "round": 1, "source_md": "a.md"},
            {"claim": "false-claim", "verdict": "does-not-hold", "round": 1, "source_md": "b.md"},
            {"claim": "unproven-claim", "verdict": "insufficient", "round": 1},
        ]
        satisfied = paper_validate.satisfied_claims(records, min_sources=1)
        self.assertEqual(satisfied, {"true-claim"})


class PlantedCitationTests(unittest.TestCase):
    """proposal.md, "The proof that matters": a citation whose source does
    not support its claim is rejected BY EXECUTION, and the opposite pole
    (a genuinely-holding citation) holds in the SAME run."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.source = Path(self._tmp.name) / "ingested.md"
        self.source.write_text(
            "The method achieves 91.2% accuracy on the held-out test split. "
            "No ablation of the regularization term was performed in this study.\n",
            encoding="utf-8",
        )

    def test_a_planted_false_citation_does_not_hold_while_a_true_one_holds(self) -> None:
        true_span = paper_evidence.EvidenceSpan.locate(self.source, "achieves 91.2% accuracy")
        true_verdict = paper_evidence.Verdict.holds(true_span)
        true_record = paper_evidence.EvidenceRecord.from_verdict(
            block_id="results.claim", regime="discovery", claim="the method achieves 91.2% accuracy",
            cite_key="true1", identifier="10.1/t", resolver="openalex", metadata_digest="d1",
            verdict=true_verdict, round=1,
        )

        # The plant: the source's OWN words say the opposite of this claim
        # -- "no ablation... was performed" -- so the located span is real,
        # byte for byte, and still does not support "an ablation was
        # performed". This is the failure this whole change exists to catch.
        false_span = paper_evidence.EvidenceSpan.locate(
            self.source, "No ablation of the regularization term was performed"
        )
        false_verdict = paper_evidence.Verdict.does_not_hold(false_span)
        false_record = paper_evidence.EvidenceRecord.from_verdict(
            block_id="results.claim", regime="discovery",
            claim="an ablation of the regularization term was performed",
            cite_key="false1", identifier="10.1/f", resolver="openalex", metadata_digest="d2",
            verdict=false_verdict, round=1,
        )

        self.assertEqual(true_record.verdict, "holds")
        self.assertEqual(false_record.verdict, "does-not-hold")

        # `min_sources=1`: this test's own proof is planted-vs-true
        # classification, not distinct-source counting (owned separately by
        # `DistinctSourceCoverageTests` below).
        satisfied = paper_validate.satisfied_claims(
            [true_record.to_json(), false_record.to_json()], min_sources=1,
        )
        self.assertIn("the method achieves 91.2% accuracy", satisfied)
        self.assertNotIn("an ablation of the regularization term was performed", satisfied)


class SpanlessVerdictMutationTests(unittest.TestCase):
    """m3 (design.md, Testing Strategy, Mutations table): `Verdict.holds`
    accepting `span=None` must turn the spanless-verdict guard test red --
    reusing WU1's own `test_holds_with_none_span_refuses` as the target,
    since that is exactly the test this guard protects."""

    def test_m3_spanless_holds_guard_disabled_fails_the_guard_test(self) -> None:
        proc = _run_against_mutant(
            'if span is None:\n            raise Refused("VERDICT_SPAN_REQUIRED", '
            '"Verdict.holds() requires a located span")',
            'if False:\n            raise Refused("VERDICT_SPAN_REQUIRED", '
            '"Verdict.holds() requires a located span")',
            "tests.test_paper_evidence.VerdictConstructionTests.test_holds_with_none_span_refuses",
            source_path=SKILL_SCRIPTS / "paper_evidence.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class BoundedLoopTests(unittest.TestCase):
    """`citation-validation`, Requirement: Three Search Rounds Per Block,
    Then Exhaustion."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        paper_block.open_block(self.paper_dir, "target-block", after=None, at_end=True)

    def test_a_block_within_budget_is_written(self) -> None:
        # `min_sources=1`: this test's own proof is the ROUND-BUDGET
        # mechanic (one holds record inside the round budget is enough to
        # stop being "pending"), orthogonal to the distinct-source-count
        # minimum `DistinctSourceCoverageTests` below owns.
        records = [
            {"claim": "c1", "verdict": "does-not-hold", "round": 1},
            {"claim": "c1", "verdict": "holds", "round": 2, "source_md": "a.md"},
        ]
        result = paper_validate.finalize_block(
            self.paper_dir, "target-block", ["c1"], records, b"new body\n", min_sources=1,
        )
        self.assertEqual(result["status"], "written")
        status = paper_block.read_status(self.paper_dir)
        block = next(b for b in status["blocks"] if b["id"] == "target-block")
        self.assertIsNotNone(block)

    def test_a_block_not_yet_exhausted_reports_pending_and_writes_nothing(self) -> None:
        tex_path = paper_block.resolve_main_tex(self.paper_dir)
        pre = tex_path.read_bytes()
        records = [{"claim": "c1", "verdict": "insufficient", "round": 1}]
        result = paper_validate.finalize_block(self.paper_dir, "target-block", ["c1"], records, b"body\n")
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["unsupported"], ["c1"])
        self.assertEqual(tex_path.read_bytes(), pre)

    def test_exhaustion_at_round_three_refuses_and_never_calls_substitute(self) -> None:
        # `min_sources=1`: this test's own proof is the leniency exclusion
        # (`insufficient`/`does-not-hold` never satisfy, however many
        # rounds pass), orthogonal to the distinct-source-count minimum
        # `DistinctSourceCoverageTests` owns -- pinned so the widened-
        # membership mutation below cannot hide behind an unrelated
        # distinct-count shortfall.
        records = [
            {"claim": "c1", "verdict": "insufficient", "round": 1},
            {"claim": "c1", "verdict": "does-not-hold", "round": 2},
            {"claim": "c1", "verdict": "insufficient", "round": 3},
        ]
        original_substitute = paper_block.substitute

        def _spy(*_args, **_kwargs):
            raise AssertionError("paper_block.substitute must never be called on exhaustion")

        paper_block.substitute = _spy
        try:
            with self.assertRaises(Refused) as ctx:
                paper_validate.finalize_block(
                    self.paper_dir, "target-block", ["c1"], records, b"body\n", min_sources=1,
                )
        finally:
            paper_block.substitute = original_substitute
        self.assertEqual(ctx.exception.code, "EVIDENCE_EXHAUSTED")
        self.assertIn("c1", ctx.exception.detail)

    def test_m2_satisfied_set_widened_to_include_insufficient_fails_the_exhaustion_test(self) -> None:
        proc = _run_against_mutant(
            'record["verdict"] == HOLDS',
            'record["verdict"] in (HOLDS, "insufficient")',
            "tests.test_paper_citation.BoundedLoopTests"
            ".test_exhaustion_at_round_three_refuses_and_never_calls_substitute",
            source_path=SKILL_SCRIPTS / "paper_validate.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class DistinctSourceCoverageTests(unittest.TestCase):
    """`the-pdf-arrives-or-the-operator-is-told`, item 2: a claim is
    covered by N sources when N DISTINCT source papers carry a `holds`
    record for it -- never bare record count. Two quotes from the same
    paper must count as ONE source, not two."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.paper_dir = Path(self._tmp.name) / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        paper_block.open_block(self.paper_dir, "target-block", after=None, at_end=True)

    def test_two_quotes_from_one_paper_do_not_satisfy_a_minimum_of_two(self) -> None:
        records = [
            {"claim": "c1", "verdict": "holds", "round": 1, "source_md": "a.md"},
            {"claim": "c1", "verdict": "holds", "round": 1, "source_md": "a.md"},
        ]
        satisfied = paper_validate.satisfied_claims(records, min_sources=2)
        self.assertEqual(satisfied, set())

    def test_two_distinct_papers_satisfy_the_default_minimum(self) -> None:
        records = [
            {"claim": "c1", "verdict": "holds", "round": 1, "source_md": "a.md"},
            {"claim": "c1", "verdict": "holds", "round": 1, "source_md": "b.md"},
        ]
        satisfied = paper_validate.satisfied_claims(records)  # default min = 2
        self.assertEqual(satisfied, {"c1"})

    def test_claim_coverage_reports_required_and_satisfied_per_claim(self) -> None:
        records = [
            {"claim": "c1", "verdict": "holds", "round": 1, "source_md": "a.md"},
            {"claim": "c2", "verdict": "insufficient", "round": 1},
        ]
        coverage = paper_validate.claim_coverage(["c1", "c2"], records)
        self.assertEqual(coverage, [
            {"claim": "c1", "required": 2, "satisfied": 1},
            {"claim": "c2", "required": 2, "satisfied": 0},
        ])

    def test_a_claim_with_one_of_two_sources_refuses_naming_claim_and_shortfall(self) -> None:
        """The decisive test: three `holds` records that all share the
        SAME `source_md` still count as only 1 distinct source against the
        default minimum of 2 -- proven all the way through `finalize_
        block`'s own exhaustion refusal, which must name both the claim
        and its shortfall."""
        records = [
            {"claim": "c1", "verdict": "holds", "round": 1, "source_md": "a.md"},
            {"claim": "c1", "verdict": "holds", "round": 2, "source_md": "a.md"},
            {"claim": "c1", "verdict": "holds", "round": 3, "source_md": "a.md"},
        ]
        with self.assertRaises(Refused) as ctx:
            paper_validate.finalize_block(self.paper_dir, "target-block", ["c1"], records, b"body\n")
        self.assertEqual(ctx.exception.code, "EVIDENCE_EXHAUSTED")
        self.assertIn("c1", ctx.exception.detail)
        self.assertIn("1/2", ctx.exception.detail)

    def test_a_pending_block_also_reports_coverage(self) -> None:
        records = [{"claim": "c1", "verdict": "holds", "round": 1, "source_md": "a.md"}]
        result = paper_validate.finalize_block(self.paper_dir, "target-block", ["c1"], records, b"body\n")
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["coverage"], [{"claim": "c1", "required": 2, "satisfied": 1}])

    def test_m_counting_rows_instead_of_distinct_sources_fails_the_decisive_test(self) -> None:
        proc = _run_against_mutant(
            'sources.setdefault(record["claim"], set()).add(record.get("source_md", ""))',
            'sources.setdefault(record["claim"], []).append(record.get("source_md", ""))',
            "tests.test_paper_citation.DistinctSourceCoverageTests"
            ".test_a_claim_with_one_of_two_sources_refuses_naming_claim_and_shortfall",
            source_path=SKILL_SCRIPTS / "paper_validate.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class PlacementDispatchTests(unittest.TestCase):
    """`citation-placement` spec -- a dispatch table, never one universal
    rule."""

    def test_discovery_citation_at_sentence_end_passes(self) -> None:
        sentence = paper_validate.Sentence(
            text="The estimator converges under mild conditions [1].",
            citations=(paper_validate.Citation("[1]", "sentence-end", False, False),),
        )
        result = paper_validate.validate_placement("discovery", sentence)
        self.assertEqual(result["result"], "pass")

    def test_discovery_citation_mid_sentence_fails(self) -> None:
        sentence = paper_validate.Sentence(
            text="The estimator [1] converges under mild conditions.",
            citations=(paper_validate.Citation("[1]", "mid-sentence", False, False),),
        )
        with self.assertRaises(Refused) as ctx:
            paper_validate.validate_placement("discovery", sentence)
        self.assertEqual(ctx.exception.code, "CITATION_NOT_AT_SENTENCE_END")

    def test_resolution_citation_attached_mid_sentence_passes_the_same_position_that_failed_under_discovery(
        self,
    ) -> None:
        sentence = paper_validate.Sentence(
            text="We compare against the XYZ baseline [1] on the benchmark.",
            citations=(paper_validate.Citation("[1]", "mid-sentence", True, False),),
        )
        result = paper_validate.validate_placement("resolution", sentence)
        self.assertEqual(result["result"], "pass")

    def test_resolution_citation_detached_from_object_fails(self) -> None:
        sentence = paper_validate.Sentence(
            text="We use several baselines in our comparison [1].",
            citations=(paper_validate.Citation("[1]", "sentence-end", False, False),),
        )
        with self.assertRaises(Refused) as ctx:
            paper_validate.validate_placement("resolution", sentence)
        self.assertEqual(ctx.exception.code, "CITATION_DETACHED_FROM_OBJECT")

    def test_noun_phrase_fails_under_discovery(self) -> None:
        sentence = paper_validate.Sentence(
            text="The work in [1] establishes this bound.",
            citations=(paper_validate.Citation("[1]", "mid-sentence", False, True),),
        )
        with self.assertRaises(Refused) as ctx:
            paper_validate.validate_placement("discovery", sentence)
        self.assertEqual(ctx.exception.code, "CITATION_NOUN_PHRASE")

    def test_noun_phrase_passes_under_resolution_when_attached_to_its_object(self) -> None:
        sentence = paper_validate.Sentence(
            text="The XYZ baseline of [1] is used unmodified.",
            citations=(paper_validate.Citation("[1]", "mid-sentence", True, True),),
        )
        result = paper_validate.validate_placement("resolution", sentence)
        self.assertEqual(result["result"], "pass")

    def test_two_citations_in_one_discovery_sentence_fail(self) -> None:
        sentence = paper_validate.Sentence(
            text="Prior work shows both convergence [1] and robustness [2].",
            citations=(
                paper_validate.Citation("[1]", "mid-sentence", False, False),
                paper_validate.Citation("[2]", "sentence-end", False, False),
            ),
        )
        with self.assertRaises(Refused) as ctx:
            paper_validate.validate_placement("discovery", sentence)
        self.assertEqual(ctx.exception.code, "CITATION_MULTI_CLAIM_SENTENCE")

    def test_none_regime_refuses_any_citation(self) -> None:
        sentence = paper_validate.Sentence(
            text="This sentence should carry no citation [1].",
            citations=(paper_validate.Citation("[1]", "sentence-end", False, False),),
        )
        with self.assertRaises(Refused) as ctx:
            paper_validate.validate_placement("none", sentence)
        self.assertEqual(ctx.exception.code, "CITATION_UNDER_NONE_REGIME")

    def test_none_regime_with_no_citation_passes(self) -> None:
        sentence = paper_validate.Sentence(text="No citation needed here.", citations=())
        result = paper_validate.validate_placement("none", sentence)
        self.assertEqual(result["result"], "pass")


class ContractHeaderAbsentTests(unittest.TestCase):
    """A `sections/*.md` file with no front-matter fence refuses
    `CONTRACT_HEADER_ABSENT` rather than a defaulted regime. `design.md`'s
    own "What Breaks" table claimed none of the ten shipped files carried a
    header at design time; measured false on this disk (headers have since
    landed from a sibling change) -- so this suite builds its own
    unheadered fixture rather than asserting anything about the real
    `sections/` tree's current state."""

    def test_a_section_file_with_no_front_matter_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            section = Path(tmp) / "01-materials-and-methods.md"
            section.write_text("# Materials and Methods\n\nNo header here.\n", encoding="utf-8")
            with self.assertRaises(Refused) as ctx:
                paper_validate.read_citations_regime(section, "some-block")
            self.assertEqual(ctx.exception.code, "CONTRACT_HEADER_ABSENT")

    def test_a_headered_fixture_reads_its_own_regime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            section = Path(tmp) / "example.md"
            header = {
                "section": "example", "position": 1,
                "blocks": [{
                    "id": "b1", "requires_facts": [], "requires_declarations": [],
                    "citations": "resolution",
                }],
            }
            section.write_bytes(b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\nbody\n")
            regime = paper_validate.read_citations_regime(section, "b1")
            self.assertEqual(regime, "resolution")


class ValidateCLITests(unittest.TestCase):
    """The `validate` verb wired into `paper_cli.py` -- an end-to-end walk,
    not only library-level calls."""

    def setUp(self) -> None:
        # `resolve_paper_dir` requires `--paper` to resolve inside the real
        # repository root, so the CLI-level walk here uses the same
        # already-gitignored `implementations/` tree
        # `tests/test_paper_writing.py::test_cli_scaffold_verb_runs_and_emits_json`
        # uses, removed afterward -- the one place this class touches the
        # real repo.
        self.root = FORGE_ROOT / "implementations" / f".paper-writing-validate-cli-test-{os.getpid()}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        paper_scaffold.scaffold(self.paper_dir)
        paper_block.open_block(self.paper_dir, "intro.claim", after=None, at_end=True)
        self.source = self.root / "ingested.md"
        self.source.write_text("The dataset holds 12,000 labeled examples.\n", encoding="utf-8")

    def test_validate_cli_submits_evidence_and_reports_satisfied_with_no_body(self) -> None:
        exit_code = paper_cli.main([
            "validate", "--paper", str(self.paper_dir), "--block", "intro.claim",
            "--claim", "the dataset holds 12000 labeled examples",
            "--quote", "holds 12,000 labeled examples", "--source-md", str(self.source),
            "--verdict", "holds", "--cite-key", "d1", "--identifier", "10.1/d",
            "--resolver", "openalex", "--metadata-digest", "abc",
        ])
        self.assertEqual(exit_code, 0)

    def test_validate_cli_writes_the_block_when_satisfied_and_body_given(self) -> None:
        body_path = self.root / "body.tex"
        body_path.write_text("The dataset holds 12{,}000 labeled examples~\\cite{d1}.\n", encoding="utf-8")
        exit_code = paper_cli.main([
            "validate", "--paper", str(self.paper_dir), "--block", "intro.claim",
            "--claim", "the dataset holds 12000 labeled examples",
            "--quote", "holds 12,000 labeled examples", "--source-md", str(self.source),
            "--verdict", "holds", "--cite-key", "d1", "--body", str(body_path),
        ])
        self.assertEqual(exit_code, 0)
        status = paper_block.read_status(self.paper_dir)
        block = next(b for b in status["blocks"] if b["id"] == "intro.claim")
        self.assertIsNotNone(block)

    def test_a_located_quote_without_verdict_refuses_validate_verdict_required(self) -> None:
        exit_code = paper_cli.main([
            "validate", "--paper", str(self.paper_dir), "--block", "intro.claim",
            "--claim", "x", "--quote", "holds 12,000 labeled examples", "--source-md", str(self.source),
        ])
        self.assertEqual(exit_code, 2)

    def test_section_md_reads_the_regime_for_a_submitted_record(self) -> None:
        # cmd_validate's own `_resolve_regime` -- a real production caller
        # of `paper_validate.read_citations_regime`, not only the unit
        # tests that exercise it directly.
        section = self.root / "example.md"
        header = {
            "section": "example", "position": 1,
            "blocks": [{
                "id": "intro.claim", "requires_facts": [], "requires_declarations": [],
                "citations": "resolution",
            }],
        }
        section.write_bytes(b"---\n" + json.dumps(header).encode("utf-8") + b"\n---\nbody\n")
        exit_code = paper_cli.main([
            "validate", "--paper", str(self.paper_dir), "--block", "intro.claim",
            "--claim", "the dataset holds 12000 labeled examples",
            "--quote", "holds 12,000 labeled examples", "--source-md", str(self.source),
            "--verdict", "holds", "--cite-key", "d1", "--section-md", str(section),
        ])
        self.assertEqual(exit_code, 0)
        records = paper_evidence.read_records(self.paper_dir, "intro.claim")
        self.assertEqual(records[-1]["regime"], "resolution")

    def test_section_md_with_no_front_matter_refuses_contract_header_absent_through_the_cli(self) -> None:
        section = self.root / "unheadered.md"
        section.write_text("# No header\n", encoding="utf-8")
        exit_code = paper_cli.main([
            "validate", "--paper", str(self.paper_dir), "--block", "intro.claim",
            "--claim", "x", "--quote", "holds 12,000 labeled examples", "--source-md", str(self.source),
            "--verdict", "holds", "--section-md", str(section),
        ])
        self.assertEqual(exit_code, 2)

    def test_a_paraphrased_quote_refuses_span_not_in_source_through_the_cli(self) -> None:
        exit_code = paper_cli.main([
            "validate", "--paper", str(self.paper_dir), "--block", "intro.claim",
            "--claim", "x", "--quote", "definitely not in the source",
            "--source-md", str(self.source), "--verdict", "holds",
        ])
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
