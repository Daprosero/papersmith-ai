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
    """A malformed or missing configuration is reported, never silently
    downgraded to "nothing to ingest" — that reads exactly like a healthy
    no-op run and hides the real problem."""

    def _config(self, tmp: str, body: str) -> Path:
        path = Path(tmp) / "papersmith.yaml"
        path.write_text(body, encoding="utf-8")
        return path

    def test_reads_paper_ingestion_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(
                tmp, "paper_ingestion:\n  engine: marker\n  mode: fast\n  strip_references: true\n"
            )
            cfg = EXTRACTOR.load_config(path)
            self.assertEqual(cfg["engine"], "marker")
            self.assertEqual(cfg["mode"], "fast")
            self.assertTrue(cfg["strip_references"])

    def test_missing_file_is_a_config_error(self) -> None:
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.load_config(Path("/no/such/papersmith.yaml"))

    def test_file_without_block_is_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "other_section:\n  key: value\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_unparseable_yaml_is_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  mode: [unclosed\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_scalar_block_is_a_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion: marker\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_unknown_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  mode: turbo\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_unknown_engine_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  engine: docling\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_source_roots_must_be_a_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  source_roots: guidance/papers\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_strip_references_must_be_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._config(tmp, "paper_ingestion:\n  strip_references: sometimes\n")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.load_config(path)

    def test_the_repository_configuration_is_valid(self) -> None:
        cfg = EXTRACTOR.load_config(REPOSITORY_ROOT / "papersmith.yaml")
        self.assertIsInstance(cfg["source_roots"], list)


class _BaseFixture(unittest.TestCase):
    """A `source_base` with topic folders under it, and `REPO_ROOT` pointed at it.

    The script resolves every configured path against `REPO_ROOT`, so a test that
    does not move it would read the real repository and pass or fail for reasons
    that have nothing to do with the fixture.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Resolved: on macOS the temporary directory is reached through a symlink,
        # and the script resolves every path it returns. An unresolved fixture would
        # compare two spellings of the same folder and fail for nothing.
        self.repo = Path(self._tmp.name).resolve()
        self.base = self.repo / "guidance"
        self.base.mkdir()
        self._real_root = EXTRACTOR.REPO_ROOT
        EXTRACTOR.REPO_ROOT = self.repo
        self.addCleanup(lambda: setattr(EXTRACTOR, "REPO_ROOT", self._real_root))
        self.cfg = {"source_base": "guidance"}

    def topic(self, name: str, *pdfs: str) -> Path:
        folder = self.base / name
        folder.mkdir(exist_ok=True)
        for pdf in pdfs:
            (folder / pdf).write_bytes(b"%PDF")
        return folder


class DiscoverSourceRootsTests(_BaseFixture):
    """Resolving what to scan — string paths, missing folders, nothing configured.

    These three moved here when discovery was split out of `find_loose_pdfs`, which
    now receives folders somebody else already validated. Their tests did not move
    with them and sat red for fifteen commits against the old address, while the
    function that took the behaviour over had no tests at all.
    """

    def test_an_explicit_root_given_as_a_string_is_resolved(self) -> None:
        self.topic("extra", "a.pdf")
        roots = EXTRACTOR.discover_source_roots({"source_roots": ["guidance/extra"]})
        self.assertEqual([r.name for r in roots], ["extra"])

    def test_a_nonexistent_explicit_root_is_skipped(self) -> None:
        self.assertEqual(
            EXTRACTOR.discover_source_roots({"source_roots": ["definitely/not/here"]}), [])

    def test_nothing_configured_fails_closed(self) -> None:
        """Descubrir nada en silencio se lee igual que "ya está todo ingerido"."""
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.discover_source_roots({})

    def test_a_base_that_is_not_a_folder_fails_closed(self) -> None:
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.discover_source_roots({"source_base": "no-such-folder"})

    def test_every_child_holding_a_loose_pdf_is_promoted(self) -> None:
        self.topic("datasets", "a.pdf")
        self.topic("new-topic", "b.pdf")
        ingested = self.topic("done")
        (ingested / "x").mkdir()
        (ingested / "x" / "x.pdf").write_bytes(b"%PDF")
        roots = EXTRACTOR.discover_source_roots(self.cfg)
        self.assertEqual(sorted(r.name for r in roots), ["datasets", "new-topic"])


class FindLoosePdfsTests(_BaseFixture):
    def test_returns_only_loose_pdfs_not_already_ingested_ones(self) -> None:
        root = self.topic("papers", "b.pdf", "a.pdf")
        ingested = root / "c"
        ingested.mkdir()
        (ingested / "c.pdf").write_bytes(b"%PDF-c")
        (root / "note.txt").write_text("ignore", encoding="utf-8")
        self.assertEqual([p.name for p in EXTRACTOR.find_loose_pdfs([root])],
                         ["a.pdf", "b.pdf"])

    def test_an_uppercase_extension_is_still_a_pdf(self) -> None:
        root = self.topic("papers", "SHOUTY.PDF")
        self.assertEqual([p.name for p in EXTRACTOR.find_loose_pdfs([root])],
                         ["SHOUTY.PDF"])

    def test_a_directory_named_like_a_pdf_is_not_a_paper(self) -> None:
        root = self.topic("papers")
        (root / "trap.pdf").mkdir()
        self.assertEqual(EXTRACTOR.find_loose_pdfs([root]), [])


class UnfiledPdfsTests(_BaseFixture):
    """El PDF que cae en la base misma, al lado de las carpetas y en ninguna.

    Es el par peor: está pendiente y es invisible. El descubrimiento solo promueve
    HIJAS de la base, así que nadie lo encuentra y la corrida informa que está todo
    ingerido — el silencio exacto contra el que `source_base` falla cerrado.
    """

    def test_a_pdf_beside_the_topic_folders_is_reported(self) -> None:
        self.topic("datasets", "inside.pdf")
        (self.base / "dropped.pdf").write_bytes(b"%PDF")
        self.assertEqual([p.name for p in EXTRACTOR.unfiled_pdfs(self.cfg)],
                         ["dropped.pdf"])

    def test_it_is_never_ingested_where_it_lies(self) -> None:
        """Convertirlo ahí lo volvería un tema propio, y la corrida siguiente lo
        leería como carpeta ya ingerida y lo dejaría ahí para siempre."""
        (self.base / "dropped.pdf").write_bytes(b"%PDF")
        roots = EXTRACTOR.discover_source_roots({**self.cfg, "source_roots": []})
        self.assertEqual(EXTRACTOR.find_loose_pdfs(roots), [])

    def test_a_pdf_inside_a_topic_is_not_unfiled(self) -> None:
        """El otro polo: sin esto, un chequeo que marcara todo no distinguiría nada."""
        self.topic("datasets", "inside.pdf")
        self.assertEqual(EXTRACTOR.unfiled_pdfs(self.cfg), [])

    def test_the_options_are_read_from_the_tree(self) -> None:
        self.topic("datasets")
        self.topic("reference-papers")
        (self.base / ".hidden").mkdir()
        self.assertEqual(EXTRACTOR.filing_options(self.cfg),
                         ["datasets", "reference-papers"])


class FileIntoTests(_BaseFixture):
    def test_filing_moves_it_into_an_existing_topic(self) -> None:
        self.topic("datasets")
        pdf = self.base / "dropped.pdf"
        pdf.write_bytes(b"%PDF")
        landed = EXTRACTOR.file_into(pdf, "datasets", self.cfg)
        self.assertEqual(landed, self.base / "datasets" / "dropped.pdf")
        self.assertFalse(pdf.exists())
        # And now ordinary discovery sees it, which is the point of filing.
        self.assertEqual([p.name for p in
                          EXTRACTOR.find_loose_pdfs(EXTRACTOR.discover_source_roots(self.cfg))],
                         ["dropped.pdf"])

    def test_a_new_topic_is_created(self) -> None:
        pdf = self.base / "dropped.pdf"
        pdf.write_bytes(b"%PDF")
        landed = EXTRACTOR.file_into(pdf, "brand-new", self.cfg)
        self.assertTrue(landed.is_file())

    def test_it_never_displaces_a_paper_already_there(self) -> None:
        """Dos papers distintos bajo un mismo nombre: mover destruiría el primero."""
        self.topic("datasets", "dropped.pdf")
        pdf = self.base / "dropped.pdf"
        pdf.write_bytes(b"%PDF-other")
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.file_into(pdf, "datasets", self.cfg)
        self.assertTrue(pdf.exists(), "el original tiene que seguir donde estaba")

    def test_a_topic_that_escapes_the_base_is_refused(self) -> None:
        pdf = self.base / "dropped.pdf"
        pdf.write_bytes(b"%PDF")
        for folder in ("../outside", "nested/topic", ".hidden", ""):
            with self.assertRaises(EXTRACTOR.ConfigError, msg=folder):
                EXTRACTOR.file_into(pdf, folder, self.cfg)

    def test_only_a_pdf_sitting_in_the_base_can_be_filed(self) -> None:
        """Un PDF que ya está en un tema no es un pendiente sin archivar, y moverlo
        sería reorganizar la biblioteca de alguien sin que lo pidiera."""
        inside = self.topic("datasets", "inside.pdf") / "inside.pdf"
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.file_into(inside, "reference-papers", self.cfg)


class SingleTargetTests(unittest.TestCase):
    """An explicit ``<loose-pdf>`` argument is validated before the engine
    loads, so a mistyped path can never displace a file that is not a paper."""

    def test_accepts_a_loose_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "paper.pdf"
            pdf.write_bytes(b"%PDF-p")
            self.assertEqual(EXTRACTOR.resolve_single_target(str(pdf)), pdf.resolve())

    def test_rejects_a_missing_path(self) -> None:
        with self.assertRaises(EXTRACTOR.ConfigError):
            EXTRACTOR.resolve_single_target("/no/such/paper.pdf")

    def test_rejects_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.resolve_single_target(tmp)

    def test_rejects_a_non_pdf_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes.txt"
            notes.write_text("research notes", encoding="utf-8")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.resolve_single_target(str(notes))

    def test_rejects_an_already_ingested_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "paper"
            folder.mkdir()
            pdf = folder / "paper.pdf"
            pdf.write_bytes(b"%PDF-p")
            with self.assertRaises(EXTRACTOR.ConfigError):
                EXTRACTOR.resolve_single_target(str(pdf))

    def test_is_loose_recognises_the_ingested_layout(self) -> None:
        self.assertTrue(EXTRACTOR.is_loose(Path("/papers/foo.pdf")))
        self.assertFalse(EXTRACTOR.is_loose(Path("/papers/foo/foo.pdf")))


if __name__ == "__main__":
    unittest.main()
