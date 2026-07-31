from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from copy import deepcopy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz
import jsonschema


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / ".claude/skills/paper-ingestion/scripts/extract_pdf.py"
SPEC = importlib.util.spec_from_file_location("extract_pdf", SCRIPT)
assert SPEC and SPEC.loader
EXTRACTOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EXTRACTOR
SPEC.loader.exec_module(EXTRACTOR)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExtractPdfTestCase(unittest.TestCase):
    def create_pdf(
        self,
        path: Path,
        text: str | list[str] = "Guard test document",
        image: bool = False,
    ) -> None:
        document = fitz.open()
        texts = [text] if isinstance(text, str) else text
        for page_number, page_text in enumerate(texts, start=1):
            page = document.new_page()
            if page_text:
                page.insert_text((72, 72), page_text)
            if image:
                pixel = fitz.Pixmap(fitz.csRGB, 1, 1, b"\xff\x00\x00", False)
                page.insert_image(fitz.Rect(72, 100, 144, 172), pixmap=pixel)
        document.save(path)
        document.close()

    def add_image(self, pdf: Path, color: bytes = b"\x00\x00\xff") -> None:
        document = fitz.open(pdf)
        page = document[0]
        pixel = fitz.Pixmap(fitz.csRGB, 1, 1, color, False)
        page.insert_image(fitz.Rect(180, 100, 252, 172), pixmap=pixel)
        document.save(pdf.with_suffix(".updated.pdf"))
        document.close()
        pdf.with_suffix(".updated.pdf").replace(pdf)

    def run_extractor(self, pdf: Path, output_dir: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(pdf), "--output-dir", str(output_dir), *extra_args],
            check=False,
            capture_output=True,
            text=True,
            cwd=REPOSITORY_ROOT,
        )

    def extract_manifest(self, pdf: Path, output_dir: Path, *extra_args: str) -> tuple[dict[str, object], str]:
        result = self.run_extractor(pdf, output_dir, *extra_args)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((output_dir / f"{pdf.stem}.manifest.json").read_text(encoding="utf-8"))
        markdown = (output_dir / f"{pdf.stem}.md").read_text(encoding="utf-8")
        return manifest, markdown


class ExtractPdfReingestionGuardTests(ExtractPdfTestCase):
    def test_existing_markdown_blocks_the_entire_pipeline_until_forced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "paper.pdf"
            output_dir = temporary_path / "normalized"
            self.create_pdf(pdf_path)

            initial = self.run_extractor(pdf_path, output_dir)
            self.assertEqual(initial.returncode, 0, initial.stderr)

            markdown_path = output_dir / "paper.md"
            manifest_path = output_dir / "paper.manifest.json"
            image_path = output_dir / "paper-assets/page-001.png"
            source_hash = sha256(pdf_path)
            output_hashes = {path: sha256(path) for path in (markdown_path, manifest_path, image_path)}

            blocked = self.run_extractor(pdf_path, output_dir)

            self.assertEqual(blocked.returncode, 2, blocked.stderr)
            result = json.loads(blocked.stdout)
            self.assertEqual(result["status"], "interaction_required")
            self.assertEqual(result["reason"], "normalized_markdown_exists")
            self.assertEqual(result["documents"], [{
                "pdf": str(pdf_path.resolve()),
                "markdown": str(markdown_path.resolve()),
            }])
            self.assertIn("--force", result["required_action"])
            self.assertEqual(sha256(pdf_path), source_hash)
            self.assertEqual({path: sha256(path) for path in output_hashes}, output_hashes)

            forced = self.run_extractor(pdf_path, output_dir, "--force")
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertTrue(markdown_path.is_file())
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(image_path.is_file())
            self.assertEqual(sha256(pdf_path), source_hash)

    def test_forced_shorter_rerun_replaces_asset_directory_without_obsolete_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "shorter.pdf"
            output_dir = temporary_path / "normalized"
            self.create_pdf(pdf_path, ["first page", "second page"])
            self.assertEqual(self.run_extractor(pdf_path, output_dir).returncode, 0)
            assets_dir = output_dir / "shorter-assets"
            self.assertEqual(
                sorted(path.name for path in assets_dir.glob("*.png")),
                ["page-001.png", "page-002.png"],
            )

            self.create_pdf(pdf_path.with_suffix(".replacement.pdf"), "replacement")
            pdf_path.with_suffix(".replacement.pdf").replace(pdf_path)
            forced = self.run_extractor(pdf_path, output_dir, "--force")

            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertEqual(sorted(path.name for path in assets_dir.glob("*.png")), ["page-001.png"])
            manifest = json.loads((output_dir / "shorter.manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["page_count"], 1)

    def test_promotion_failure_restores_previous_complete_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            output_dir = temporary_path / "normalized"
            output_dir.mkdir()
            markdown = output_dir / "paper.md"
            manifest = output_dir / "paper.manifest.json"
            assets = output_dir / "paper-assets"
            assets.mkdir()
            markdown.write_text("previous markdown", encoding="utf-8")
            manifest.write_text('{"previous": true}', encoding="utf-8")
            (assets / "page-001.png").write_bytes(b"previous asset")
            old_hashes = {
                markdown: sha256(markdown),
                manifest: sha256(manifest),
                assets / "page-001.png": sha256(assets / "page-001.png"),
            }

            stage = Path(tempfile.mkdtemp(dir=temporary_path))
            staged_markdown = stage / markdown.name
            staged_manifest = stage / manifest.name
            staged_assets = stage / assets.name
            staged_markdown.write_text("new markdown", encoding="utf-8")
            staged_manifest.write_text('{"new": true}', encoding="utf-8")
            staged_assets.mkdir()
            (staged_assets / "page-001.png").write_bytes(b"new asset")
            real_replace = os.replace
            failed = False

            def fail_manifest_promotion(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
                nonlocal failed
                if Path(source) == staged_manifest and not failed:
                    failed = True
                    raise OSError("injected promotion failure")
                real_replace(source, destination)

            with patch.object(EXTRACTOR.os, "replace", side_effect=fail_manifest_promotion):
                with self.assertRaises(OSError):
                    EXTRACTOR.transactional_replace(
                        stage,
                        [
                            (staged_markdown, markdown),
                            (staged_manifest, manifest),
                            (staged_assets, assets),
                        ],
                    )

            self.assertFalse(stage.exists())
            self.assertEqual({path: sha256(path) for path in old_hashes}, old_hashes)
            self.assertEqual(sorted(path.name for path in assets.iterdir()), ["page-001.png"])

    def test_post_promotion_verification_failure_restores_previous_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            output_dir = temporary_path / "normalized"
            output_dir.mkdir()
            markdown = output_dir / "paper.md"
            manifest = output_dir / "paper.manifest.json"
            assets = output_dir / "paper-assets"
            assets.mkdir()
            markdown.write_text("previous markdown", encoding="utf-8")
            manifest.write_text('{"previous": true}', encoding="utf-8")
            (assets / "page-001.png").write_bytes(b"previous asset")
            old_hashes = {
                markdown: sha256(markdown),
                manifest: sha256(manifest),
                assets / "page-001.png": sha256(assets / "page-001.png"),
            }

            stage = Path(tempfile.mkdtemp(dir=temporary_path))
            staged_markdown = stage / markdown.name
            staged_manifest = stage / manifest.name
            staged_assets = stage / assets.name
            staged_markdown.write_text("new markdown", encoding="utf-8")
            staged_manifest.write_text('{"new": true}', encoding="utf-8")
            staged_assets.mkdir()
            (staged_assets / "page-001.png").write_bytes(b"new asset")

            with self.assertRaisesRegex(RuntimeError, "injected verification failure"):
                EXTRACTOR.transactional_replace(
                    stage,
                    [
                        (staged_markdown, markdown),
                        (staged_manifest, manifest),
                        (staged_assets, assets),
                    ],
                    verifier=lambda: (_ for _ in ()).throw(RuntimeError("injected verification failure")),
                )

            self.assertFalse(stage.exists())
            self.assertEqual({path: sha256(path) for path in old_hashes}, old_hashes)


    def test_promotion_and_restore_failure_preserves_recovery_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            output_dir = temporary_path / "normalized"
            output_dir.mkdir()
            markdown = output_dir / "paper.md"
            manifest = output_dir / "paper.manifest.json"
            assets = output_dir / "paper-assets"
            assets.mkdir()
            markdown.write_text("previous markdown", encoding="utf-8")
            manifest.write_text('{"previous": true}', encoding="utf-8")
            (assets / "page-001.png").write_bytes(b"previous asset")

            stage = Path(tempfile.mkdtemp(dir=temporary_path))
            staged_markdown = stage / markdown.name
            staged_manifest = stage / manifest.name
            staged_assets = stage / assets.name
            staged_markdown.write_text("new markdown", encoding="utf-8")
            staged_manifest.write_text('{"new": true}', encoding="utf-8")
            staged_assets.mkdir()
            (staged_assets / "page-001.png").write_bytes(b"new asset")
            real_replace = os.replace
            failed_promotion = False

            def fail_promotion_and_restore(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
                nonlocal failed_promotion
                source_path = Path(source)
                destination_path = Path(destination)
                if source_path == staged_manifest and not failed_promotion:
                    failed_promotion = True
                    raise OSError("injected promotion failure")
                if source_path.name == markdown.name and ".recovery" in source_path.parent.name and destination_path == markdown:
                    raise OSError("injected restore failure")
                real_replace(source, destination)

            with patch.object(EXTRACTOR.os, "replace", side_effect=fail_promotion_and_restore):
                with self.assertRaises(EXTRACTOR.TransactionRecoveryError) as raised:
                    EXTRACTOR.transactional_replace(
                        stage,
                        [
                            (staged_markdown, markdown),
                            (staged_manifest, manifest),
                            (staged_assets, assets),
                        ],
                    )

            recovery_dir = raised.exception.recovery_dir
            self.assertFalse(stage.exists())
            self.assertTrue(recovery_dir.is_dir())
            self.assertIn(str(recovery_dir), str(raised.exception))
            self.assertEqual((recovery_dir / markdown.name).read_text(encoding="utf-8"), "previous markdown")
            self.assertEqual(manifest.read_text(encoding="utf-8"), '{"previous": true}')
            self.assertEqual((assets / "page-001.png").read_bytes(), b"previous asset")


class ExtractPdfEvidenceTests(ExtractPdfTestCase):
    def test_strong_equation_preserves_exact_raw_text_and_page_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "equation.pdf"
            self.create_pdf(pdf_path, "E = m*c (1)")

            manifest, markdown = self.extract_manifest(pdf_path, temporary_path / "normalized")

            equations = manifest["equations"]
            self.assertEqual(len(equations), 1)
            equation = equations[0]
            self.assertEqual(equation["raw_text"], "E = m*c (1)")
            self.assertEqual(equation["provenance"], {
                "page": 1,
                "page_image": "equation-assets/page-001.png",
            })
            self.assertEqual(equation["status"], "raw_text_preserved")
            self.assertIsInstance(equation["confidence"], float)
            self.assertGreaterEqual(equation["confidence"], 0.95)
            self.assertNotIn("latex", equation)
            self.assertIn("### Equation candidates", markdown)
            self.assertIn("E = m*c (1)", markdown)

    def test_ambiguous_equation_is_a_review_required_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "ambiguous.pdf"
            self.create_pdf(pdf_path, "f(x) =")

            manifest, markdown = self.extract_manifest(pdf_path, temporary_path / "normalized")

            equation = manifest["equations"][0]
            self.assertEqual(equation["raw_text"], "f(x) =")
            self.assertEqual(equation["status"], "review_required")
            self.assertTrue(equation["review_required"])
            self.assertLess(equation["confidence"], manifest["confidence_threshold"])
            self.assertEqual(manifest["review_required_pages"], [1])
            self.assertIn("human review required", markdown)
            self.assertNotIn("$", markdown)
            self.assertNotIn("\\\\[", markdown)

    def test_captions_remain_page_level_evidence_and_never_pair_with_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "captioned.pdf"
            caption = "Figure 1. Textual architecture caption."
            self.create_pdf(pdf_path, caption, image=True)
            self.add_image(pdf_path)

            manifest, markdown = self.extract_manifest(pdf_path, temporary_path / "normalized")

            self.assertEqual(manifest["pages"][0]["textual_figure_captions"], [caption])
            self.assertEqual(len(manifest["figures"]), 2)
            for figure in manifest["figures"]:
                self.assertEqual(figure["status"], "review_required")
                self.assertTrue(figure["review_required"])
                self.assertNotIn("caption_text", figure)
                self.assertNotIn("description", figure)
                self.assertEqual(figure["provenance"]["page"], 1)
                self.assertIn("width", figure["metadata"])
            self.assertEqual(manifest["review_required_pages"], [1])
            self.assertIn(caption, markdown)
            self.assertIn("not associated with embedded images", markdown)

    def test_uncaptioned_embedded_image_requires_visual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "uncaptioned.pdf"
            self.create_pdf(pdf_path, "A page with an image but no figure caption.", image=True)

            manifest, markdown = self.extract_manifest(pdf_path, temporary_path / "normalized")

            figure = manifest["figures"][0]
            self.assertEqual(figure["status"], "review_required")
            self.assertTrue(figure["review_required"])
            self.assertIn("visual review required", markdown)
            self.assertEqual(manifest["review_required_pages"], [1])

    def test_table_mode_is_lite_evidence_only_without_structured_table_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "table.pdf"
            config_path = temporary_path / "papersmith.yaml"
            config_path.write_text(
                "paper_ingestion:\n  extract:\n    text: false\n    figures: false\n    tables: true\n    equations: false\n",
                encoding="utf-8",
            )
            self.create_pdf(pdf_path, "Table 1\nA B\n1 2")

            manifest, markdown = self.extract_manifest(
                pdf_path, temporary_path / "normalized", "--config", str(config_path)
            )

            self.assertEqual(manifest["tables"], {
                "enabled": True,
                "mode": "lite_evidence_only",
                "evidence": ["exact_raw_page_text", "rendered_page_images"],
                "review_required": True,
            })
            self.assertIn("Table policy: lite evidence only", markdown)
            self.assertIn("no rows, columns, cells, or inferred values", markdown)
            self.assertIn("Preserved as table-lite evidence", markdown)
            self.assertIn("Table 1", markdown)
            with fitz.open(pdf_path) as document:
                exact_page_text = document[0].get_text("text")
            self.assertEqual(manifest["pages"][0]["raw_text"], exact_page_text)
            self.assertEqual(manifest["pages"][0]["text_characters"], len(exact_page_text))
            self.assertIn(exact_page_text, markdown)
            self.assertFalse({"rows", "columns", "cells", "values"} & set(manifest["tables"]))


class ExtractPdfConfigurationAndSchemaTests(ExtractPdfTestCase):
    def test_configuration_controls_flags_dpi_and_confidence_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "configured.pdf"
            config_path = temporary_path / "papersmith.yaml"
            config_path.write_text(
                """paper_ingestion:
  page_render_dpi: 72
  confidence_threshold: 0.99
  extract:
    text: false
    figures: false
    tables: false
    equations: false
""",
                encoding="utf-8",
            )
            self.create_pdf(pdf_path, "E = m*c (1)", image=True)

            manifest, markdown = self.extract_manifest(
                pdf_path, temporary_path / "normalized", "--config", str(config_path)
            )

            self.assertEqual(manifest["render_dpi"], 72)
            self.assertEqual(manifest["confidence_threshold"], 0.99)
            self.assertEqual(manifest["extraction_configuration"], {
                "text": False,
                "figures": False,
                "tables": False,
                "equations": False,
            })
            self.assertEqual(manifest["equations"], [])
            self.assertEqual(manifest["figures"], [])
            self.assertEqual(manifest["tables"]["mode"], "disabled")
            self.assertEqual(manifest["pages"][0]["text_characters"], 0)
            self.assertEqual(manifest["review_required_pages"], [1])
            self.assertIn("_Disabled by papersmith.yaml._", markdown)

    def test_invalid_roots_and_unsupported_keys_fail_before_artifacts_are_created(self) -> None:
        invalid_configs = {
            "list-root": "- paper_ingestion\n",
            "unknown-ingestion-key": "paper_ingestion:\n  unsupported: true\n",
            "unknown-extraction-mode": "paper_ingestion:\n  extract:\n    ocr: true\n",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "invalid-config.pdf"
            self.create_pdf(pdf_path)
            for name, content in invalid_configs.items():
                with self.subTest(name=name):
                    config_path = temporary_path / f"{name}.yaml"
                    output_dir = temporary_path / f"{name}-normalized"
                    config_path.write_text(content, encoding="utf-8")
                    result = self.run_extractor(pdf_path, output_dir, "--config", str(config_path))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Invalid papersmith.yaml", result.stderr)
                    self.assertFalse(output_dir.exists())

    def test_schema_and_runtime_share_the_configured_unicode_whitespace_set(self) -> None:
        config_schema = json.loads((REPOSITORY_ROOT / "schemas/papersmith-config.schema.json").read_text())
        whitespace_values = tuple(sorted(EXTRACTOR.CONFIGURATION_WHITESPACE_CODEPOINTS, key=ord))
        configurations = {
            "model-profile": lambda value: {"paper_ingestion": {"model_profile": value}},
            "source-root": lambda value: {"paper_ingestion": {"source_roots": [value]}},
        }

        # This includes every former JSON Schema/Python divergence (U+001C-U+001F,
        # U+0085, and U+FEFF) as well as regular Unicode and non-breaking whitespace.
        self.assertEqual(
            {"\u001c", "\u001d", "\u001e", "\u001f", "\u0085", "\ufeff"}
            - set(whitespace_values),
            set(),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "whitespace-config.pdf"
            self.create_pdf(pdf_path)
            for field, configuration_for in configurations.items():
                for whitespace in whitespace_values:
                    with self.subTest(field=field, whitespace=f"U+{ord(whitespace):04X}"):
                        configuration = configuration_for(whitespace)
                        with self.assertRaises(jsonschema.ValidationError):
                            jsonschema.Draft202012Validator(config_schema).validate(configuration)

                        config_path = temporary_path / f"{field}.yaml"
                        output_dir = temporary_path / f"{field}-normalized"
                        config_path.write_text(json.dumps(configuration), encoding="utf-8")
                        result = self.run_extractor(pdf_path, output_dir, "--config", str(config_path))
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("Invalid papersmith.yaml", result.stderr)
                        self.assertFalse(output_dir.exists())

    def test_schema_and_runtime_accept_non_ascii_model_profile_and_path(self) -> None:
        config_schema = json.loads((REPOSITORY_ROOT / "schemas/papersmith-config.schema.json").read_text())
        configuration = {
            "paper_ingestion": {
                "model_profile": "perfil-研究",
                "source_roots": ["guidance/mañana"],
            }
        }
        jsonschema.Draft202012Validator(config_schema).validate(configuration)

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "unicode-config.pdf"
            config_path = temporary_path / "papersmith.yaml"
            output_dir = temporary_path / "normalized"
            self.create_pdf(pdf_path)
            config_path.write_text(json.dumps(configuration, ensure_ascii=False), encoding="utf-8")

            result = self.run_extractor(pdf_path, output_dir, "--config", str(config_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output_dir / "unicode-config.md").is_file())

    def test_manifest_uses_its_canonical_schema_identifier_and_satisfies_schema(self) -> None:
        config_schema = json.loads((REPOSITORY_ROOT / "schemas/papersmith-config.schema.json").read_text())
        manifest_schema = json.loads(
            (REPOSITORY_ROOT / "schemas/papersmith-manifest-v1.1.schema.json").read_text()
        )
        self.assertEqual(config_schema["$id"], "papersmith-config.schema.json")
        self.assertEqual(
            manifest_schema["$id"],
            "https://papersmith.ai/schemas/papersmith-manifest-v1.1.schema.json",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "schema.pdf"
            self.create_pdf(pdf_path, "Figure 1. A caption.\nE = m*c (1)", image=True)
            manifest, _ = self.extract_manifest(pdf_path, temporary_path / "normalized")
            self.assertEqual(manifest["$schema"], manifest_schema["$id"])
            jsonschema.Draft202012Validator(manifest_schema).validate(manifest)

            caption_association = deepcopy(manifest)
            caption_association["figures"][0]["caption_text"] = "Figure 1. A caption."
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(manifest_schema).validate(caption_association)

            unsafe_figure = deepcopy(manifest)
            unsafe_figure["figures"][0]["review_required"] = False
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(manifest_schema).validate(unsafe_figure)

            structured_table = deepcopy(manifest)
            structured_table["tables"]["rows"] = []
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(manifest_schema).validate(structured_table)



class ExtractPdfDeterminismTests(ExtractPdfTestCase):
    PAGE_COUNT = 8

    def multi_page_pages(self) -> list[str]:
        # Mix strong equations, ambiguous equations, and figure captions so the
        # per-page contributions (equations, figures, markdown, confidence) vary
        # across pages and exercise the deterministic reassembly meaningfully.
        return [
            "Introduction page one with prose text.",
            "E = m*c (1)",
            "f(x) =",
            "Figure 1. Textual architecture caption.",
            "Plain body text for page five.",
            "y = a*x (2)",
            "g(z) <=",
            "Figure 2. Another caption line.",
        ]

    def asset_bytes(self, assets_dir: Path) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in sorted(assets_dir.glob("page-*.png"))
        }

    def strip_processed_at(self, manifest: dict[str, object]) -> dict[str, object]:
        # Only the timestamp legitimately differs between two independent runs.
        without_timestamp = dict(manifest)
        without_timestamp.pop("processed_at", None)
        return without_timestamp

    def test_extraction_is_deterministic_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            pdf_path = temporary_path / "multipage.pdf"
            self.create_pdf(pdf_path, self.multi_page_pages(), image=True)

            first_dir = temporary_path / "first"
            second_dir = temporary_path / "second"

            first = self.run_extractor(pdf_path, first_dir)
            second = self.run_extractor(pdf_path, second_dir)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)

            first_markdown = (first_dir / "multipage.md").read_bytes()
            second_markdown = (second_dir / "multipage.md").read_bytes()
            self.assertEqual(first_markdown, second_markdown)

            first_manifest = json.loads(
                (first_dir / "multipage.manifest.json").read_text(encoding="utf-8")
            )
            second_manifest = json.loads(
                (second_dir / "multipage.manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first_manifest["page_count"], self.PAGE_COUNT)
            self.assertEqual(
                self.strip_processed_at(first_manifest),
                self.strip_processed_at(second_manifest),
            )

            first_assets = self.asset_bytes(first_dir / "multipage-assets")
            second_assets = self.asset_bytes(second_dir / "multipage-assets")
            self.assertEqual(
                sorted(first_assets),
                [f"page-{index:03d}.png" for index in range(1, self.PAGE_COUNT + 1)],
            )
            self.assertEqual(first_assets, second_assets)


if __name__ == "__main__":
    unittest.main()
