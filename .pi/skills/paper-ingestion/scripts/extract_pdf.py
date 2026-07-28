#!/usr/bin/env python3
"""Create deterministic, auditable normalized artifacts for one PDF.

This lite extractor preserves raw machine-readable evidence. It intentionally does
not reconstruct mathematical notation, structured tables, or visual content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import fitz  # PyMuPDF
import yaml


DEFAULT_CONFIGURATION: dict[str, Any] = {
    "page_render_dpi": 200,
    "confidence_threshold": 0.85,
    "extract": {
        "text": True,
        "figures": True,
        "tables": True,
        "equations": True,
    },
}
SUPPORTED_INGESTION_KEYS = {
    "model_profile",
    "page_render_dpi",
    "confidence_threshold",
    "source_roots",
    "extract",
}
MANIFEST_SCHEMA_REFERENCE = "https://papersmith.ai/schemas/papersmith-manifest-v1.1.schema.json"
# This exact set is also encoded in schemas/papersmith-config.schema.json.
# It is the union of ECMAScript and Python whitespace handling so configuration
# validity does not depend on the validator runtime.
CONFIGURATION_WHITESPACE_CODEPOINTS = frozenset(
    character
    for start, end in (
        (0x0009, 0x000D),
        (0x001C, 0x0020),
        (0x0085, 0x0085),
        (0x00A0, 0x00A0),
        (0x1680, 0x1680),
        (0x2000, 0x200A),
        (0x2028, 0x2029),
        (0x202F, 0x202F),
        (0x205F, 0x205F),
        (0x3000, 0x3000),
        (0xFEFF, 0xFEFF),
    )
    for character in map(chr, range(start, end + 1))
)


def has_configuration_content(value: str) -> bool:
    """Return whether a string contains a non-configured-whitespace code point."""
    return any(character not in CONFIGURATION_WHITESPACE_CODEPOINTS for character in value)



class TransactionRecoveryError(RuntimeError):
    """A failed rollback whose prior artifacts remain available for manual recovery."""

    def __init__(self, recovery_dir: Path, restore_error: Exception) -> None:
        self.recovery_dir = recovery_dir
        self.restore_error = restore_error
        super().__init__(
            "Transactional promotion failed and automatic restoration also failed. "
            f"Previous artifacts remain preserved for recovery at: {recovery_dir}"
        )

MATH_MARKER = re.compile(r"[=∈≤≥≈≠∑∏√∞±×÷^_]|\\(?:frac|sum|prod|sqrt)")
FORMAL_EQUATION = re.compile(
    r"^[A-Za-zΑ-ω][\wα-ωΑ-Ω]*(?:\([^)]*\))?\s*(?:=|∈|≤|≥|≈|≠)\s*\S"
)
TRAILING_EQUATION_NUMBER = re.compile(r"\s*\(\d+\)\s*$")
TRAILING_OPERATOR = re.compile(r"(?:=|∈|≤|≥|≈|≠|\+|-|×|÷|\^|_|,|\\)$")
FIGURE_CAPTION = re.compile(r"^\s*(?:Figure|Fig\.)\s*\d+[.:].*\S\s*$", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def interaction_required(source: Path, markdown_path: Path) -> dict[str, object]:
    """Describe a blocked re-ingestion without touching document artifacts."""
    return {
        "status": "interaction_required",
        "reason": "normalized_markdown_exists",
        "documents": [{
            "pdf": str(source),
            "markdown": str(markdown_path),
        }],
        "required_action": "Obtain explicit approval, then re-run this document with --force.",
    }


def find_configuration(source: Path, explicit_config: Path | None) -> Path | None:
    """Prefer an explicit config, then a config beside/above the source or cwd."""
    if explicit_config is not None:
        return explicit_config.resolve()

    searched: set[Path] = set()
    for start in (source.parent, Path.cwd()):
        for directory in (start, *start.parents):
            candidate = directory / "papersmith.yaml"
            if candidate in searched:
                continue
            searched.add(candidate)
            if candidate.is_file():
                return candidate
    return None


def configuration_error(message: str) -> None:
    raise SystemExit(f"Invalid papersmith.yaml: {message}")


def validate_optional_ingestion_settings(paper_ingestion: dict[str, Any]) -> None:
    """Validate supported project-level fields even when extraction does not use them."""
    if "model_profile" in paper_ingestion:
        model_profile = paper_ingestion["model_profile"]
        if not isinstance(model_profile, str) or not has_configuration_content(model_profile):
            configuration_error("paper_ingestion.model_profile must contain a non-whitespace character")
    if "source_roots" in paper_ingestion:
        source_roots = paper_ingestion["source_roots"]
        if not isinstance(source_roots, list) or not source_roots:
            configuration_error("paper_ingestion.source_roots must be a non-empty list of paths")
        if any(not isinstance(root, str) or not has_configuration_content(root) for root in source_roots):
            configuration_error("paper_ingestion.source_roots entries must contain a non-whitespace character")


def load_configuration(source: Path, explicit_config: Path | None) -> tuple[dict[str, Any], Path | None]:
    """Load only the documented papersmith configuration; reject loose values."""
    configuration = {
        "page_render_dpi": DEFAULT_CONFIGURATION["page_render_dpi"],
        "confidence_threshold": DEFAULT_CONFIGURATION["confidence_threshold"],
        "extract": dict(DEFAULT_CONFIGURATION["extract"]),
    }
    config_path = find_configuration(source, explicit_config)
    if config_path is None:
        return configuration, None
    if not config_path.is_file():
        raise SystemExit(f"Configuration not found: {config_path}")

    try:
        with config_path.open(encoding="utf-8") as config_file:
            loaded = yaml.safe_load(config_file)
    except yaml.YAMLError as error:
        configuration_error(f"YAML could not be parsed ({error})")

    if not isinstance(loaded, dict) or not loaded:
        configuration_error("root must be a non-empty mapping containing 'paper_ingestion'")
    unknown_root_keys = set(loaded) - {"paper_ingestion"}
    if unknown_root_keys:
        configuration_error(f"unsupported root key(s): {', '.join(sorted(unknown_root_keys))}")
    if "paper_ingestion" not in loaded or not isinstance(loaded["paper_ingestion"], dict):
        configuration_error("field 'paper_ingestion' must be a mapping")

    paper_ingestion = loaded["paper_ingestion"]
    unknown_keys = set(paper_ingestion) - SUPPORTED_INGESTION_KEYS
    if unknown_keys:
        configuration_error(f"unsupported paper_ingestion key(s): {', '.join(sorted(unknown_keys))}")
    validate_optional_ingestion_settings(paper_ingestion)

    dpi = paper_ingestion.get("page_render_dpi", configuration["page_render_dpi"])
    threshold = paper_ingestion.get("confidence_threshold", configuration["confidence_threshold"])
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi <= 0:
        configuration_error("paper_ingestion.page_render_dpi must be a positive integer")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        configuration_error("paper_ingestion.confidence_threshold must be a number from 0 through 1")
    configuration["page_render_dpi"] = dpi
    configuration["confidence_threshold"] = float(threshold)

    configured_extract = paper_ingestion.get("extract", {})
    if not isinstance(configured_extract, dict):
        configuration_error("paper_ingestion.extract must be a mapping")
    unknown_extract_keys = set(configured_extract) - set(configuration["extract"])
    if unknown_extract_keys:
        configuration_error(
            f"unsupported paper_ingestion.extract key(s): {', '.join(sorted(unknown_extract_keys))}"
        )
    for name in configuration["extract"]:
        value = configured_extract.get(name, configuration["extract"][name])
        if not isinstance(value, bool):
            configuration_error(f"paper_ingestion.extract.{name} must be a boolean")
        configuration["extract"][name] = value
    return configuration, config_path


def is_strong_equation(raw_text: str) -> bool:
    """Recognize complete one-line equations without rewriting their notation."""
    expression = TRAILING_EQUATION_NUMBER.sub("", raw_text.strip())
    if not FORMAL_EQUATION.match(expression):
        return False
    if TRAILING_OPERATOR.search(expression):
        return False
    return expression.count("(") == expression.count(")") and "�" not in expression


def equation_candidates(text: str, page_number: int, page_image: str) -> list[dict[str, Any]]:
    """Return exact line-level mathematical evidence in a stable page order."""
    candidates: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or not MATH_MARKER.search(raw_line):
            continue
        strong = is_strong_equation(raw_line)
        sequence = len(candidates) + 1
        candidate_id = f"page-{page_number:03d}-equation-{sequence:03d}"
        candidates.append({
            "id": candidate_id,
            "raw_text": raw_line,
            "provenance": {
                "page": page_number,
                "page_image": page_image,
            },
            "confidence": 0.98 if strong else 0.45,
            "status": "raw_text_preserved" if strong else "review_required",
            "review_required": not strong,
        })
    return candidates


def textual_figure_captions(text: str) -> list[str]:
    """Return captions as exact page-level text evidence, never image associations."""
    return [line for line in text.splitlines() if FIGURE_CAPTION.match(line)]


def embedded_figures(page: fitz.Page, page_number: int, page_image: str) -> list[dict[str, Any]]:
    """Describe images from PyMuPDF metadata and page provenance only."""
    figures: list[dict[str, Any]] = []
    for image_index, image in enumerate(page.get_images(full=True), start=1):
        xref, smask, width, height, bits_per_component, colorspace, *_ = image
        figures.append({
            "id": f"page-{page_number:03d}-image-{image_index:03d}",
            "provenance": {
                "page": page_number,
                "page_image": page_image,
            },
            "metadata": {
                "xref": xref,
                "smask": smask,
                "width": width,
                "height": height,
                "bits_per_component": bits_per_component,
                "colorspace": colorspace,
            },
            "confidence": 0.5,
            "status": "review_required",
            "review_required": True,
        })
    return figures


def page_confidence(text: str, equations: list[dict[str, Any]], figures: list[dict[str, Any]]) -> tuple[float, str]:
    """Compute conservative confidence from available extraction evidence only."""
    confidence = 0.95 if text else 0.5
    notes: list[str] = []
    if not text:
        notes.append("No machine-readable text was extracted.")
    if any(candidate["review_required"] for candidate in equations):
        confidence = min(confidence, 0.65)
        notes.append("One or more equation candidates are ambiguous in raw extraction.")
    if figures:
        confidence = min(confidence, 0.75)
        notes.append("Embedded images require visual review; captions remain page-level text evidence only.")
    if not notes:
        notes.append("Machine-readable text was preserved with page-image provenance.")
    return confidence, " ".join(notes)


def markdown_code_block(raw_text: str) -> list[str]:
    delimiter = "```"
    while delimiter in raw_text:
        delimiter += "`"
    return [delimiter, raw_text, delimiter]


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def transactional_replace(
    stage_dir: Path,
    destinations: list[tuple[Path, Path]],
    verifier: Callable[[], None] | None = None,
) -> None:
    """Promote a staged artifact set, retaining recovery material on rollback failure."""
    # Backups must not live below ``stage_dir``: its normal cleanup would otherwise
    # delete the only copy of prior artifacts if restoration itself fails.
    recovery_dir = stage_dir.parent / f".{stage_dir.name}.recovery"
    recovery_dir.mkdir()
    previous: list[tuple[Path, Path]] = []
    promoted: list[Path] = []
    succeeded = False
    try:
        for _, destination in destinations:
            if destination.exists() or destination.is_symlink():
                backup = recovery_dir / destination.name
                os.replace(destination, backup)
                previous.append((destination, backup))
        for staged, destination in destinations:
            os.replace(staged, destination)
            promoted.append(destination)
        if verifier is not None:
            verifier()
        succeeded = True
    except Exception as promotion_error:
        try:
            for destination in reversed(promoted):
                remove_path(destination)
            for destination, backup in reversed(previous):
                if destination.exists() or destination.is_symlink():
                    remove_path(destination)
                os.replace(backup, destination)
        except Exception as restore_error:
            # Deliberately retain every backup. The raised path is actionable even
            # when only a subset of the prior set still needs restoration.
            raise TransactionRecoveryError(recovery_dir, restore_error) from promotion_error
        raise
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
        if succeeded or not recovery_dir.exists() or not any(recovery_dir.iterdir()):
            shutil.rmtree(recovery_dir, ignore_errors=True)


def verify_artifact_set(
    markdown_path: Path,
    manifest_path: Path,
    assets_dir: Path,
    document_name: str,
    expected_page_count: int,
    source_hash: str,
) -> None:
    """Verify that all three artifact kinds agree before reporting success."""
    if not markdown_path.is_file() or not manifest_path.is_file() or not assets_dir.is_dir():
        raise RuntimeError("artifact set is incomplete")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"manifest cannot be read: {error}") from error
    if manifest.get("schema_version") != "1.1" or manifest.get("source_sha256") != source_hash:
        raise RuntimeError("manifest provenance is inconsistent")
    pages = manifest.get("pages")
    if not isinstance(pages, list) or len(pages) != expected_page_count:
        raise RuntimeError("manifest page count is inconsistent")
    expected_assets = {f"page-{index:03d}.png" for index in range(1, expected_page_count + 1)}
    actual_assets = {
        path.relative_to(assets_dir).as_posix()
        for path in assets_dir.rglob("*") if path.is_file()
    }
    if actual_assets != expected_assets:
        raise RuntimeError("rendered page assets are incomplete or contain obsolete files")
    expected_images = {f"{document_name}-assets/{asset}" for asset in expected_assets}
    if {page.get("image") for page in pages if isinstance(page, dict)} != expected_images:
        raise RuntimeError("manifest page-image provenance is inconsistent")


def main() -> int:
    args = parse_args()
    source = args.pdf.resolve()
    if source.suffix.lower() != ".pdf" or not source.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")

    output_dir = args.output_dir.resolve()
    document_name = source.stem
    markdown_path = output_dir / f"{document_name}.md"
    manifest_path = output_dir / f"{document_name}.manifest.json"
    assets_dir = output_dir / f"{document_name}-assets"

    # This sentinel precedes configuration loading and every artifact-creating
    # operation. A blocked re-ingestion must not create or mutate normalized data.
    if markdown_path.exists() and not args.force:
        print(json.dumps(interaction_required(source, markdown_path)))
        return 2

    configuration, config_path = load_configuration(source, args.config)
    dpi = args.dpi if args.dpi is not None else configuration["page_render_dpi"]
    if dpi <= 0:
        raise SystemExit("--dpi must be a positive integer")
    extraction = configuration["extract"]
    source_hash = sha256(source)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=f".{document_name}.stage-", dir=output_dir.parent))
    staged_markdown = stage_dir / markdown_path.name
    staged_manifest = stage_dir / manifest_path.name
    staged_assets = stage_dir / assets_dir.name
    staged_assets.mkdir()

    try:
        scale = dpi / 72
        matrix = fitz.Matrix(scale, scale)
        pages: list[dict[str, Any]] = []
        all_equations: list[dict[str, Any]] = []
        all_figures: list[dict[str, Any]] = []
        markdown = [
            f"# {document_name}",
            "",
            "## Source",
            f"- PDF: `{source}`",
            f"- Source SHA-256: `{source_hash}`",
            f"- Rendered pages: pending at {dpi} DPI (PyMuPDF).",
            f"- Confidence threshold: {configuration['confidence_threshold']:.2f}.",
            "- Table policy: lite evidence only. Possible tables are retained only as exact raw page text and rendered page images; no rows, columns, cells, or inferred values are extracted.",
            "- Equation policy: equation candidates retain exact raw extracted text; this extractor does not synthesize LaTeX.",
            "",
        ]

        with fitz.open(source) as pdf:
            page_count = len(pdf)
            for index, page in enumerate(pdf, start=1):
                image_path = staged_assets / f"page-{index:03d}.png"
                page.get_pixmap(matrix=matrix, alpha=False).save(image_path)
                image_reference = f"{assets_dir.name}/{image_path.name}"
                # Table-lite, equation, and caption evidence depend on exact page text even
                # when general prose-text output is disabled.
                raw_text = page.get_text("text") if any(extraction.values()) else ""
                # raw_text is table-lite evidence. Preserve it exactly as returned
                # by PyMuPDF; do not strip or normalize before storage.
                captions = textual_figure_captions(raw_text) if extraction["figures"] else []
                equations = equation_candidates(raw_text, index, image_reference) if extraction["equations"] else []
                figures = embedded_figures(page, index, image_reference) if extraction["figures"] else []
                confidence, confidence_notes = page_confidence(raw_text, equations, figures)
                confidence_status = (
                    "acceptable" if confidence >= configuration["confidence_threshold"] else "review_required"
                )
                pages.append({
                    "page": index,
                    "image": image_reference,
                    "raw_text": raw_text,
                    "text_characters": len(raw_text),
                    "confidence": confidence,
                    "confidence_status": confidence_status,
                    "confidence_notes": confidence_notes,
                    "textual_figure_captions": captions,
                    "equation_ids": [candidate["id"] for candidate in equations],
                    "figure_ids": [figure["id"] for figure in figures],
                })
                all_equations.extend(equations)
                all_figures.extend(figures)

                markdown.extend([f"## Page {index}", f"![Page {index}]({image_reference})", ""])
                confidence_statement = (
                    f"- **Confidence:** {confidence:.2f} (below the configured "
                    f"{configuration['confidence_threshold']:.2f} threshold; human review required)."
                    if confidence_status == "review_required"
                    else f"- **Confidence:** {confidence:.2f} (meets the configured threshold)."
                )
                markdown.extend([
                    "### Extraction assessment",
                    confidence_statement,
                    f"- {confidence_notes}",
                    "",
                ])
                if extraction["text"] or extraction["tables"]:
                    markdown.extend(["### Raw extracted text"])
                    if extraction["tables"] and not extraction["text"]:
                        markdown.append("_Preserved as table-lite evidence despite general text extraction being disabled._")
                    if raw_text:
                        markdown.extend([*markdown_code_block(raw_text), ""])
                    else:
                        markdown.extend(["_No machine-readable text extracted; inspect the page image._", ""])
                else:
                    markdown.extend(["### Raw extracted text", "_Disabled by papersmith.yaml._", ""])
                if captions:
                    markdown.extend(["### Textual figure-caption evidence"])
                    for caption in captions:
                        markdown.append(f"- {caption}")
                    markdown.extend([
                        "- Captions are page-level text evidence and are not associated with embedded images.",
                        "",
                    ])
                if equations:
                    markdown.extend(["### Equation candidates"])
                    for candidate in equations:
                        markdown.extend([
                            f"- `{candidate['id']}` — {candidate['status']} "
                            f"(confidence {candidate['confidence']:.2f}; page {index}).",
                            *markdown_code_block(candidate["raw_text"]),
                        ])
                    markdown.append("")
                if figures:
                    markdown.extend(["### Embedded images"])
                    for figure in figures:
                        dimensions = figure["metadata"]
                        markdown.append(
                            f"- `{figure['id']}` — embedded image metadata: "
                            f"{dimensions['width']} × {dimensions['height']} px, "
                            f"xref {dimensions['xref']}; visual review required."
                        )
                    markdown.append("")

        markdown[5] = f"- Rendered pages: {page_count} at {dpi} DPI (PyMuPDF)."
        table_mode = "lite_evidence_only" if extraction["tables"] else "disabled"
        manifest = {
            "$schema": MANIFEST_SCHEMA_REFERENCE,
            "schema_version": "1.1",
            "source_pdf": str(source),
            "source_sha256": source_hash,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "renderer": "PyMuPDF",
            "render_dpi": dpi,
            "page_count": page_count,
            "pages": pages,
            "review_required_pages": [
                page["page"] for page in pages if page["confidence_status"] == "review_required"
            ],
            "confidence_threshold": configuration["confidence_threshold"],
            "confidence_method": (
                "Deterministic confidence from raw PyMuPDF text, equation-candidate ambiguity, "
                "and review-required embedded images; rendered page images retain provenance."
            ),
            "extraction_configuration": extraction,
            "configuration_path": str(config_path) if config_path else None,
            "equations": all_equations,
            "figures": all_figures,
            "tables": {
                "enabled": extraction["tables"],
                "mode": table_mode,
                "evidence": ["exact_raw_page_text", "rendered_page_images"] if extraction["tables"] else [],
                "review_required": extraction["tables"],
            },
        }
        staged_markdown.write_text("\n".join(markdown), encoding="utf-8")
        staged_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        verify_artifact_set(
            staged_markdown,
            staged_manifest,
            staged_assets,
            document_name,
            page_count,
            source_hash,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        transactional_replace(
            stage_dir,
            [
                (staged_markdown, markdown_path),
                (staged_manifest, manifest_path),
                (staged_assets, assets_dir),
            ],
            verifier=lambda: verify_artifact_set(
                markdown_path,
                manifest_path,
                assets_dir,
                document_name,
                page_count,
                source_hash,
            ),
        )
    except Exception:
        if stage_dir.exists():
            shutil.rmtree(stage_dir, ignore_errors=True)
        raise

    review_required_evidence = [
        candidate["id"] for candidate in all_equations if candidate["review_required"]
    ] + [figure["id"] for figure in all_figures if figure["review_required"]]
    print(json.dumps({
        "status": "success",
        "markdown": str(markdown_path),
        "manifest": str(manifest_path),
        "table_mode": table_mode,
        "review_required_pages": manifest["review_required_pages"],
        "review_required_evidence": review_required_evidence,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
