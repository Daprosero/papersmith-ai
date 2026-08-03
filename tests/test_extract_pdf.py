"""Focused unit tests for the Marker-based paper-ingestion helpers.

These cover the deterministic, pure logic authored in ``extract_pdf.py`` —
reference stripping, config loading, and loose-PDF discovery — without invoking
the heavy Marker/torch/surya stack (whose end-to-end behaviour is validated by
a real ingestion run, not a unit test).

Run with the skill's venv:
    .claude/skills/paper-ingestion/.venv/bin/python -m unittest tests.test_extract_pdf
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / ".claude/skills/paper-ingestion/scripts/extract_pdf.py"
SPEC = importlib.util.spec_from_file_location("extract_pdf", SCRIPT)
assert SPEC and SPEC.loader
EXTRACTOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EXTRACTOR
SPEC.loader.exec_module(EXTRACTOR)


class StripReferencesTests(unittest.TestCase):
    def test_cuts_from_a_references_heading_to_the_end(self) -> None:
        text = "# Paper\n\nBody text.\n\n## References\n\n[1] Foo et al.\n[2] Bar.\n"
        out = EXTRACTOR.strip_references(text)
        self.assertIn("Body text.", out)
        self.assertNotIn("Foo et al.", out)
        self.assertNotIn("References", out)

    def test_handles_numbered_spanish_and_marker_decorated_headings(self) -> None:
        headings = (
            "## 7. References",
            "# Bibliography",
            "## Referencias",
            "### Bibliografía",
            "#### **References**",                              # Marker bold
            '## <span id="page-18-0"></span>**References**',    # Marker anchor + bold
        )
        for heading in headings:
            text = f"Body.\n\n{heading}\n\n[1] cite.\n"
            self.assertNotIn("cite", EXTRACTOR.strip_references(text), heading)

    def test_cuts_at_the_last_heading_when_referenced_mid_body(self) -> None:
        text = "Body mentions the References section.\n\n## References\n\n[1] cite.\n"
        out = EXTRACTOR.strip_references(text)
        self.assertIn("Body mentions the References section.", out)
        self.assertNotIn("[1] cite", out)

    def test_text_without_a_references_heading_is_unchanged(self) -> None:
        text = "# Paper\n\nAll body, no bibliography.\n"
        self.assertEqual(EXTRACTOR.strip_references(text), text)


class LoadConfigTests(unittest.TestCase):
    def test_reads_paper_ingestion_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papersmith.yaml"
            path.write_text(
                "paper_ingestion:\n  engine: marker\n  mode: fast\n  strip_references: true\n",
                encoding="utf-8",
            )
            cfg = EXTRACTOR.load_config(path)
            self.assertEqual(cfg["engine"], "marker")
            self.assertEqual(cfg["mode"], "fast")
            self.assertTrue(cfg["strip_references"])

    def test_missing_file_returns_empty_dict(self) -> None:
        self.assertEqual(EXTRACTOR.load_config(Path("/no/such/papersmith.yaml")), {})

    def test_file_without_block_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papersmith.yaml"
            path.write_text("other_section:\n  key: value\n", encoding="utf-8")
            self.assertEqual(EXTRACTOR.load_config(path), {})


class FindLoosePdfsTests(unittest.TestCase):
    def test_returns_only_loose_pdfs_not_already_ingested_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "papers"
            root.mkdir()
            (root / "b.pdf").write_bytes(b"%PDF-b")            # loose
            (root / "a.pdf").write_bytes(b"%PDF-a")            # loose
            ingested = root / "c"                               # already in its folder
            ingested.mkdir()
            (ingested / "c.pdf").write_bytes(b"%PDF-c")
            (root / "note.txt").write_text("ignore", encoding="utf-8")
            found = EXTRACTOR.find_loose_pdfs([str(root)])
            self.assertEqual([p.name for p in found], ["a.pdf", "b.pdf"])

    def test_nonexistent_root_is_skipped(self) -> None:
        self.assertEqual(EXTRACTOR.find_loose_pdfs(["/definitely/not/here"]), [])

    def test_empty_source_roots_yields_no_pdfs(self) -> None:
        self.assertEqual(EXTRACTOR.find_loose_pdfs([]), [])
        self.assertEqual(EXTRACTOR.find_loose_pdfs(None), [])


if __name__ == "__main__":
    unittest.main()
