"""`a-leftover-paper-is-offered-before-it-is-lost`: the reuse report (an
already-ingested, `evidence`-classed paper offered before the operator
re-downloads it) and the exhaustion report (a paper that carries a
`does-not-hold` against every open claim in the WHOLE corpus, never one
section alone). Both are read-only, corpus-wide over `paper_evidence.py`
and `paper_guidance.py`, and neither ever deletes anything -- the operator
deletes with their own explicit command.

Same shape `tests/test_paper_evidence.py` already uses: every fixture
lives under a `TemporaryDirectory`, and the mutation tests reuse
`_run_against_mutant` from `tests/paper_mutation.py`.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import paper_cli  # noqa: E402
import paper_evidence  # noqa: E402
import paper_lifecycle  # noqa: E402
import paper_validate  # noqa: E402

sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
from impl_refusals import Refused  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_mutation import _run_against_mutant  # noqa: E402


def _classify_root(guidance_dir: Path, root: str, klass: str | None) -> None:
    root_dir = guidance_dir / root
    root_dir.mkdir(parents=True, exist_ok=True)
    if klass is not None:
        (root_dir / ".paper-writing.json").write_text(
            json.dumps({"class": klass}), encoding="utf-8",
        )


def _ingest_paper(guidance_dir: Path, root: str, folder: str, *, body: str = "A verbatim sentence.\n") -> Path:
    paper_dir = guidance_dir / root / folder
    paper_dir.mkdir(parents=True, exist_ok=True)
    md_path = paper_dir / f"{folder}.md"
    md_path.write_text(f"# {folder}\n\n{body}", encoding="utf-8")
    return md_path


def _build_record(
    *, block_id: str, claim: str, verdict: str, source_md: Path | None = None,
    quote: str = "A verbatim sentence", round_number: int = 1,
) -> paper_evidence.EvidenceRecord:
    if verdict == "insufficient":
        v = paper_evidence.Verdict.insufficient("no source located")
    else:
        span = paper_evidence.EvidenceSpan.locate(source_md, quote)
        v = paper_evidence.Verdict.holds(span) if verdict == "holds" else paper_evidence.Verdict.does_not_hold(span)
    return paper_evidence.EvidenceRecord.from_verdict(
        block_id=block_id, regime="discovery", claim=claim, cite_key="", identifier="",
        resolver="", metadata_digest="", verdict=v, round=round_number,
    )


def _record(**kwargs) -> dict:
    """The JSON-dict shape every real caller actually hands `paper_
    lifecycle.py` -- `paper_evidence.read_records`/`read_all_records`
    return dicts (round-tripped through the JSONL store), never the
    `EvidenceRecord` dataclass itself; pure-function tests below build the
    same shape directly via `.to_json()` rather than a second, looser one."""
    return _build_record(**kwargs).to_json()


def _append(paper_dir: Path, record: dict) -> None:
    """Round-trips `record` (already a `.to_json()` dict, from `_record`
    above) through the real JSONL store exactly the way `validate` does --
    `append_record` takes an `EvidenceRecord`, so this reconstructs one from
    the dict rather than keeping a second code path that writes something
    `read_records` would not itself hand back."""
    stored = paper_evidence.EvidenceRecord(
        block_id=record["block_id"], regime=record["regime"], claim=record["claim"],
        cite_key=record["cite_key"], identifier=record["identifier"], resolver=record["resolver"],
        metadata_digest=record["metadata_digest"], source_md=record["source_md"], quote=record["quote"],
        locator=record["locator"], verdict=record["verdict"], round=record["round"],
    )
    paper_evidence.append_record(paper_dir, stored)


class OpenClaimsTests(unittest.TestCase):
    """`open_claims_for_block`: a claim is open until it has `min_sources`
    DISTINCT `holds` sources -- `does-not-hold` never closes it, and never
    fakes closing it either."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.paper1 = _ingest_paper(self.root / "guidance", "evidence-root", "paper1")
        self.paper2 = _ingest_paper(self.root / "guidance", "evidence-root", "paper2")

    def test_a_block_with_no_records_has_no_open_claims(self) -> None:
        self.assertEqual(paper_lifecycle.open_claims_for_block([]), [])

    def test_a_claim_with_one_holds_source_is_still_open(self) -> None:
        records = [_record(block_id="b", claim="A", verdict="holds", source_md=self.paper1)]
        self.assertEqual(paper_lifecycle.open_claims_for_block(records), ["A"])

    def test_a_claim_with_two_distinct_holds_sources_is_closed(self) -> None:
        records = [
            _record(block_id="b", claim="A", verdict="holds", source_md=self.paper1),
            _record(block_id="b", claim="A", verdict="holds", source_md=self.paper2),
        ]
        self.assertEqual(paper_lifecycle.open_claims_for_block(records), [])

    def test_does_not_hold_alone_never_closes_a_claim(self) -> None:
        records = [
            _record(block_id="b", claim="A", verdict="does-not-hold", source_md=self.paper1),
            _record(block_id="b", claim="A", verdict="does-not-hold", source_md=self.paper2),
        ]
        self.assertEqual(paper_lifecycle.open_claims_for_block(records), ["A"])

    def test_min_sources_is_configurable(self) -> None:
        records = [_record(block_id="b", claim="A", verdict="holds", source_md=self.paper1)]
        self.assertEqual(paper_lifecycle.open_claims_for_block(records, min_sources=1), [])


class ReuseCandidateTests(unittest.TestCase):
    """`SKILL.md` capability A: for a block's open claims, which
    already-ingested, `evidence`-classed papers carry no verdict yet."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.paper_dir = self.root / "paper"
        self.guidance_dir = self.root / "guidance"
        _classify_root(self.guidance_dir, "evidence-root", "evidence")
        self.tested = _ingest_paper(self.guidance_dir, "evidence-root", "tested")
        self.untested = _ingest_paper(self.guidance_dir, "evidence-root", "untested")

    def test_an_untested_evidence_paper_is_a_candidate(self) -> None:
        _append(self.paper_dir, _record(block_id="b", claim="A", verdict="holds", source_md=self.tested))
        report = paper_lifecycle.reuse_report(self.paper_dir, self.guidance_dir, "b")
        self.assertEqual(report["openClaims"], ["A"])
        folders = {p["folder"] for p in report["candidates"]["A"]}
        self.assertIn("untested", folders)
        self.assertNotIn("tested", folders)

    def test_a_does_not_hold_still_leaves_the_paper_a_candidate_for_other_claims(self) -> None:
        # Lifecycle: "does-not-hold -> still a candidate for the others."
        _append(self.paper_dir, _record(block_id="b", claim="A", verdict="does-not-hold", source_md=self.tested))
        _append(self.paper_dir, _record(
            block_id="b", claim="B", verdict="does-not-hold", source_md=self.untested,
        ))
        report = paper_lifecycle.reuse_report(self.paper_dir, self.guidance_dir, "b")
        self.assertEqual(sorted(report["openClaims"]), ["A", "B"])
        folder_by_claim = {
            claim: {p["folder"] for p in papers} for claim, papers in report["candidates"].items()
        }
        # "tested" was rejected for A only -- still a candidate for B.
        self.assertIn("tested", folder_by_claim["B"])
        self.assertNotIn("tested", folder_by_claim["A"])

    def test_a_style_reference_root_paper_is_never_offered_as_a_candidate(self) -> None:
        _classify_root(self.guidance_dir, "style-root", "style-reference")
        _ingest_paper(self.guidance_dir, "style-root", "styled-paper")
        _append(self.paper_dir, _record(block_id="b", claim="A", verdict="holds", source_md=self.tested))
        report = paper_lifecycle.reuse_report(self.paper_dir, self.guidance_dir, "b")
        offered = {p["folder"] for papers in report["candidates"].values() for p in papers}
        self.assertNotIn("styled-paper", offered)

    def test_an_unclassified_root_paper_is_never_offered_as_a_candidate(self) -> None:
        _ingest_paper(self.guidance_dir, "unclassified-root", "mystery-paper")
        _append(self.paper_dir, _record(block_id="b", claim="A", verdict="holds", source_md=self.tested))
        report = paper_lifecycle.reuse_report(self.paper_dir, self.guidance_dir, "b")
        offered = {p["folder"] for papers in report["candidates"].values() for p in papers}
        self.assertNotIn("mystery-paper", offered)

    def test_a_block_never_asked_about_reports_no_open_claims_and_no_candidates(self) -> None:
        report = paper_lifecycle.reuse_report(self.paper_dir, self.guidance_dir, "never-asked")
        self.assertEqual(report, {"block": "never-asked", "openClaims": [], "candidates": {}})

    def test_mutation_dropping_the_evidence_class_guard_offers_style_reference_papers(self) -> None:
        proc = _run_against_mutant(
            'if registry.get(root) != "evidence":\n            continue',
            "if False:\n            continue",
            "tests.test_paper_lifecycle.ReuseCandidateTests"
            ".test_a_style_reference_root_paper_is_never_offered_as_a_candidate",
            source_path=SKILL_SCRIPTS / "paper_lifecycle.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class CorpusOpenClaimsTests(unittest.TestCase):
    """`corpus_open_claims`: every open claim across EVERY block's own
    evidence store -- corpus-wide, never one section's blocks alone."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.paper_dir = self.root / "paper"
        self.guidance_dir = self.root / "guidance"
        self.paper1 = _ingest_paper(self.guidance_dir, "evidence-root", "paper1")

    def test_open_claims_are_unioned_across_two_different_blocks(self) -> None:
        _append(self.paper_dir, _record(block_id="intro.a", claim="A", verdict="holds", source_md=self.paper1))
        _append(self.paper_dir, _record(block_id="results.b", claim="B", verdict="holds", source_md=self.paper1))
        open_claims = paper_lifecycle.corpus_open_claims(self.paper_dir)
        self.assertEqual(
            open_claims,
            [{"block": "intro.a", "claim": "A"}, {"block": "results.b", "claim": "B"}],
        )

    def test_an_empty_store_reports_no_open_claims(self) -> None:
        self.assertEqual(paper_lifecycle.corpus_open_claims(self.paper_dir), [])


class ExhaustionTests(unittest.TestCase):
    """`SKILL.md` capability B: a paper is `exhausted` only when EVERY
    corpus-wide open claim carries a `does-not-hold` from it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.paper_dir = self.root / "paper"
        self.guidance_dir = self.root / "guidance"
        _classify_root(self.guidance_dir, "evidence-root", "evidence")
        self.candidate = _ingest_paper(self.guidance_dir, "evidence-root", "candidate")
        self.other_source = _ingest_paper(self.guidance_dir, "evidence-root", "other-source")

    def _by_folder(self, papers: list) -> dict:
        return {p["folder"]: p for p in papers}

    def test_does_not_hold_on_two_of_three_open_claims_is_not_exhausted(self) -> None:
        """The decisive test: a mutation treating 'some' as 'every' turns
        this red."""
        for claim in ("A", "B", "C"):
            # keep every claim open: one insufficient record each, from
            # some OTHER source, so `open_claims_for_block` sees them.
            _append(self.paper_dir, _record(
                block_id="b", claim=claim, verdict="insufficient",
            ))
        _append(self.paper_dir, _record(block_id="b", claim="A", verdict="does-not-hold", source_md=self.candidate))
        _append(self.paper_dir, _record(block_id="b", claim="B", verdict="does-not-hold", source_md=self.candidate))
        # claim C: candidate has no record at all against it.

        report = paper_lifecycle.exhaustion_report(self.paper_dir, self.guidance_dir)
        self.assertEqual(len(report["openClaims"]), 3)
        by_folder = self._by_folder(report["exhausted"])
        self.assertNotIn("candidate", by_folder)
        active_by_folder = self._by_folder(report["active"])
        self.assertIn("candidate", active_by_folder)
        remaining_claims = {entry["claim"] for entry in active_by_folder["candidate"]["remaining"]}
        self.assertEqual(remaining_claims, {"C"})

    def test_a_paper_with_holds_somewhere_is_never_exhausted(self) -> None:
        for claim in ("A", "B"):
            _append(self.paper_dir, _record(block_id="b", claim=claim, verdict="insufficient"))
        _append(self.paper_dir, _record(block_id="b", claim="A", verdict="does-not-hold", source_md=self.candidate))
        # "B" holds from a second, distinct source too, so it stays open
        # under the default min-sources threshold -- proving this is about
        # the VERDICT existing, never about the claim being closed.
        _append(self.paper_dir, _record(block_id="b", claim="B", verdict="holds", source_md=self.candidate))

        report = paper_lifecycle.exhaustion_report(self.paper_dir, self.guidance_dir)
        by_folder = self._by_folder(report["exhausted"])
        self.assertNotIn("candidate", by_folder)
        active_by_folder = self._by_folder(report["active"])
        self.assertEqual(active_by_folder["candidate"]["reason"], "holds")

    def test_every_open_claim_does_not_hold_is_exhausted(self) -> None:
        for claim in ("A", "B"):
            _append(self.paper_dir, _record(block_id="b", claim=claim, verdict="insufficient"))
            _append(self.paper_dir, _record(
                block_id="b", claim=claim, verdict="does-not-hold", source_md=self.candidate,
            ))
        report = paper_lifecycle.exhaustion_report(self.paper_dir, self.guidance_dir)
        by_folder = self._by_folder(report["exhausted"])
        self.assertIn("candidate", by_folder)
        self.assertEqual(by_folder["candidate"]["remaining"], [])

    def test_an_untested_paper_reports_every_open_claim_as_remaining(self) -> None:
        _append(self.paper_dir, _record(
            block_id="b", claim="A", verdict="does-not-hold", source_md=self.other_source,
        ))
        report = paper_lifecycle.exhaustion_report(self.paper_dir, self.guidance_dir)
        by_folder = self._by_folder(report["exhausted"])
        self.assertNotIn("candidate", by_folder)
        active_by_folder = self._by_folder(report["active"])
        self.assertEqual([r["claim"] for r in active_by_folder["candidate"]["remaining"]], ["A"])

    def test_no_open_claims_anywhere_never_reports_exhaustion_by_vacuous_truth(self) -> None:
        # No evidence records exist at all -- an untested, never-asked-about
        # paper must never be reported exhausted just because the open-claim
        # set happens to be empty.
        report = paper_lifecycle.exhaustion_report(self.paper_dir, self.guidance_dir)
        self.assertEqual(report["openClaims"], [])
        self.assertEqual(report["exhausted"], [])
        by_folder = self._by_folder(report["active"])
        self.assertEqual(by_folder["candidate"]["reason"], "no-open-claims")

    def test_exhaustion_is_corpus_wide_across_two_blocks_never_one_section(self) -> None:
        _append(self.paper_dir, _record(
            block_id="intro.a", claim="A", verdict="does-not-hold", source_md=self.candidate,
        ))
        _append(self.paper_dir, _record(
            block_id="results.b", claim="B", verdict="does-not-hold", source_md=self.candidate,
        ))
        report = paper_lifecycle.exhaustion_report(self.paper_dir, self.guidance_dir)
        self.assertEqual(
            report["openClaims"],
            [{"block": "intro.a", "claim": "A"}, {"block": "results.b", "claim": "B"}],
        )
        by_folder = self._by_folder(report["exhausted"])
        self.assertIn("candidate", by_folder)

    def test_a_style_reference_paper_is_never_listed_in_either_bucket(self) -> None:
        _classify_root(self.guidance_dir, "style-root", "style-reference")
        _ingest_paper(self.guidance_dir, "style-root", "styled-paper")
        report = paper_lifecycle.exhaustion_report(self.paper_dir, self.guidance_dir)
        all_folders = {p["folder"] for p in report["exhausted"] + report["active"]}
        self.assertNotIn("styled-paper", all_folders)

    def test_mutation_some_as_every_wrongly_exhausts_a_partially_rejected_paper(self) -> None:
        """The decisive mutation: `not remaining` (every open claim carries
        a does-not-hold) weakened to `len(remaining) < len(open_claims)`
        (SOME open claim does) must fail
        `test_does_not_hold_on_two_of_three_open_claims_is_not_exhausted`."""
        proc = _run_against_mutant(
            "if open_claims and not remaining:",
            "if open_claims and len(remaining) < len(open_claims):",
            "tests.test_paper_lifecycle.ExhaustionTests"
            ".test_does_not_hold_on_two_of_three_open_claims_is_not_exhausted",
            source_path=SKILL_SCRIPTS / "paper_lifecycle.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_dropping_the_holds_short_circuit_fails_the_never_exhausted_guarantee(self) -> None:
        """The second decisive proof: a paper with `holds` somewhere must
        never fall through into the does-not-hold accounting below --
        removing the `continue` lets `B` (only one holds source, itself
        counted as `remaining` too, since `does_not_hold_pairs` never
        includes it) leak through unexhausted-but-wrongly-reasoned; here we
        prove it by making the branch never short-circuit at all, so the
        holds paper gets re-evaluated as if it had no holds -- with claim A
        `does-not-hold` and claim B never `does-not-hold`, the mutant still
        reports it active, but for the WRONG reason, which this test pins."""
        proc = _run_against_mutant(
            '            active.append({**paper, "exhausted": False, "reason": "holds", "remaining": []})\n'
            "            continue",
            '            active.append({**paper, "exhausted": False, "reason": "holds", "remaining": []})',
            "tests.test_paper_lifecycle.ExhaustionTests"
            ".test_a_paper_with_holds_somewhere_is_never_exhausted",
            source_path=SKILL_SCRIPTS / "paper_lifecycle.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class ReadOnlyTests(unittest.TestCase):
    """Both reports write nothing under any input, including a refusal --
    the same before/after content manifest `PacketReadOnlyTests`
    (`tests/test_paper_writing.py`) already established."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.paper_dir = self.tmp_path / "paper"
        self.guidance_dir = self.tmp_path / "guidance"
        _classify_root(self.guidance_dir, "evidence-root", "evidence")
        self.paper1 = _ingest_paper(self.guidance_dir, "evidence-root", "paper1")
        _append(self.paper_dir, _record(block_id="b", claim="A", verdict="holds", source_md=self.paper1))

    def _manifest(self) -> dict:
        return {
            str(path.relative_to(self.tmp_path)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.tmp_path.rglob("*")) if path.is_file()
        }

    def test_reuse_report_writes_nothing(self) -> None:
        before = self._manifest()
        paper_lifecycle.reuse_report(self.paper_dir, self.guidance_dir, "b")
        paper_lifecycle.reuse_report(self.paper_dir, self.guidance_dir, "never-asked")
        after = self._manifest()
        self.assertEqual(before, after)

    def test_exhaustion_report_writes_nothing(self) -> None:
        before = self._manifest()
        paper_lifecycle.exhaustion_report(self.paper_dir, self.guidance_dir)
        after = self._manifest()
        self.assertEqual(before, after)

    def test_mutation_a_real_write_inside_reuse_report_fails_the_manifest_guard(self) -> None:
        proc = _run_against_mutant(
            "    records = paper_evidence.read_records(paper_dir, block_id)\n"
            "    claims = open_claims_for_block(records, min_sources=min_sources)",
            "    paper_dir.mkdir(parents=True, exist_ok=True)\n"
            "    (paper_dir / 'leaked-by-mutant.txt').write_text('x')\n"
            "    records = paper_evidence.read_records(paper_dir, block_id)\n"
            "    claims = open_claims_for_block(records, min_sources=min_sources)",
            "tests.test_paper_lifecycle.ReadOnlyTests.test_reuse_report_writes_nothing",
            source_path=SKILL_SCRIPTS / "paper_lifecycle.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)

    def test_mutation_a_real_write_inside_exhaustion_report_fails_the_manifest_guard(self) -> None:
        proc = _run_against_mutant(
            "    all_records = paper_evidence.read_all_records(paper_dir)\n"
            "    open_claims = corpus_open_claims(paper_dir, min_sources=min_sources)",
            "    (paper_dir / 'leaked-by-mutant.txt').parent.mkdir(parents=True, exist_ok=True)\n"
            "    (paper_dir / 'leaked-by-mutant.txt').write_text('x')\n"
            "    all_records = paper_evidence.read_all_records(paper_dir)\n"
            "    open_claims = corpus_open_claims(paper_dir, min_sources=min_sources)",
            "tests.test_paper_lifecycle.ReadOnlyTests.test_exhaustion_report_writes_nothing",
            source_path=SKILL_SCRIPTS / "paper_lifecycle.py",
        )
        output = proc.stdout + proc.stderr
        self.assertIn("MUTANT_IMPORTED_OK", output, output)
        self.assertNotEqual(proc.returncode, 0, output)


class CLIWiringTests(unittest.TestCase):
    """`reuse`/`exhaustion` wired end to end into `paper_cli.py`, the same
    real-`implementations/` fixture pattern `FullTextCLITests` already
    uses."""

    def setUp(self) -> None:
        import os
        import shutil
        self.root = FORGE_ROOT / "implementations" / f".paper-writing-lifecycle-cli-test-{os.getpid()}"
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paper_dir = self.root / "paper"
        self.paper_dir.mkdir(parents=True)
        self.guidance_dir = self.root / "guidance"
        _classify_root(self.guidance_dir, "evidence-root", "evidence")
        self.paper1 = _ingest_paper(self.guidance_dir, "evidence-root", "paper1")

    def test_reuse_cli_reports_open_claims_and_candidates(self) -> None:
        exit_code = paper_cli.main([
            "reuse", "--paper", str(self.paper_dir), "--guidance", str(self.guidance_dir), "--block", "b",
        ])
        self.assertEqual(exit_code, 0)

    def test_exhaustion_cli_reports_the_corpus_wide_state(self) -> None:
        _append(self.paper_dir, _record(block_id="b", claim="A", verdict="does-not-hold", source_md=self.paper1))
        exit_code = paper_cli.main([
            "exhaustion", "--paper", str(self.paper_dir), "--guidance", str(self.guidance_dir),
        ])
        self.assertEqual(exit_code, 0)

    def test_reuse_cli_rejects_a_guidance_dir_outside_the_repository(self) -> None:
        exit_code = paper_cli.main([
            "reuse", "--paper", str(self.paper_dir), "--guidance", "/etc", "--block", "b",
        ])
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
