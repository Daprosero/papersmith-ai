#!/usr/bin/env python3
"""Paper ingestion via Marker — one self-contained folder per paper.

For each **loose** ``<root>/<stem>.pdf`` (a PDF sitting directly in a source
root), this creates ``<root>/<stem>/``, moves the PDF inside, converts it with
Marker, strips the references/bibliography section, writes each figure as its
own image file, and writes ``<stem>.md`` that references those files. So a
paper's whole footprint lives in one folder: ``pdf + md + figure images``.

A loose PDF = not yet ingested. Once ingested, the PDF lives inside its folder,
so it is no longer loose and is skipped on the next run.

The ``.md`` stays lean (text + LaTeX equations + Markdown tables); figures are
referenced, not embedded — an agent loads a specific figure only when it needs
it. Local and keyless: no API keys and no LLM service.

Usage:
    python extract_pdf.py                 # ingest every loose PDF under source_roots
    python extract_pdf.py <pdf>           # ingest one loose PDF
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

# Apple Silicon (MPS) needs CPU fallback for the handful of ops surya/torch
# do not yet implement on the Metal backend.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import yaml

# .../.claude/skills/paper-ingestion/scripts/extract_pdf.py -> repo root is parents[4]
REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPO_ROOT / "papersmith.yaml"

# A references/bibliography heading (EN or ES). Marker decorates headings with
# bold (**References**), anchor <span> wrappers, and leading numbers, so match
# the heading line, then test its cleaned title text.
_HEADING_LINE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_REFERENCES_TITLE = re.compile(
    r"^(?:\d+\.?\s*)?(?:references|bibliography|referencias|bibliograf[ií]a)\b",
    re.IGNORECASE,
)
_MARKDOWN_DECOR = re.compile(r"[*_`~]|<[^>]+>")


def load_config(path: Path = CONFIG_PATH) -> dict:
    if not path.exists():
        return {}
    with open(path) as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("paper_ingestion", {}) or {}


def find_loose_pdfs(source_roots) -> list[Path]:
    """PDFs sitting directly in a source root (not yet moved into their folder)."""
    pdfs: list[Path] = []
    for root in source_roots or []:
        root_path = (REPO_ROOT / root).resolve()
        if root_path.is_dir():
            pdfs.extend(sorted(root_path.glob("*.pdf")))
    return pdfs


def strip_references(text: str) -> str:
    """Drop everything from the last references/bibliography heading to the end."""
    cut = None
    for m in _HEADING_LINE.finditer(text):
        title = _MARKDOWN_DECOR.sub("", m.group(1)).strip()
        if _REFERENCES_TITLE.match(title):
            cut = m.start()
    if cut is None:
        return text
    return text[:cut].rstrip() + "\n"


def build_converter(mode: str | None):
    """Construct a keyless Marker PDF->markdown converter (models loaded once)."""
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.config.parser import ConfigParser

    cli: dict = {"output_format": "markdown"}
    if mode:
        cli["mode"] = mode
    config_parser = ConfigParser(cli)
    return PdfConverter(
        config=config_parser.generate_config_dict(),
        artifact_dict=create_model_dict(),
        processor_list=config_parser.get_processors(),
        renderer=config_parser.get_renderer(),
        # No llm_service: ingestion stays local/keyless.
    )


def write_figures(images: dict, folder: Path) -> None:
    """Write each Marker figure to its own file in ``folder`` (names match the
    ``![](name)`` references already present in the Markdown)."""
    for name, image in images.items():
        is_png = name.lower().endswith(".png")
        fmt = "PNG" if is_png else "JPEG"
        if fmt == "JPEG" and image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        image.save(folder / name, format=fmt)


def convert_into_folder(converter, pdf_path: Path, strip_refs: bool) -> Path:
    from marker.output import text_from_rendered

    rendered = converter(str(pdf_path))
    text, _ext, images = text_from_rendered(rendered)
    if strip_refs:
        text = strip_references(text)
    folder = pdf_path.parent
    if images:
        write_figures(images, folder)
    md_path = folder / f"{pdf_path.stem}.md"
    md_path.write_text(text, encoding="utf-8")
    return md_path


def ingest_loose(converter, loose_pdf: Path, strip_refs: bool) -> Path:
    """Move a loose PDF into its own folder, then convert it there."""
    folder = loose_pdf.parent / loose_pdf.stem
    folder.mkdir(exist_ok=True)
    dest_pdf = folder / loose_pdf.name
    shutil.move(str(loose_pdf), str(dest_pdf))
    return convert_into_folder(converter, dest_pdf, strip_refs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-paper-folder PDF -> Markdown ingestion (Marker).")
    parser.add_argument("pdf", nargs="?", help="a single loose PDF to ingest")
    args = parser.parse_args()

    cfg = load_config()
    mode = cfg.get("mode")  # None -> Marker auto-selects by device
    strip_refs = bool(cfg.get("strip_references", True))

    if args.pdf:
        targets = [Path(args.pdf).resolve()]
    else:
        targets = find_loose_pdfs(cfg.get("source_roots", []))

    if not targets:
        print("Nothing to ingest: no loose PDFs found (every paper is already in its folder).")
        return 0

    converter = build_converter(mode)
    done: list[str] = []
    for loose_pdf in targets:
        try:
            md_path = ingest_loose(converter, loose_pdf, strip_refs)
            done.append(md_path.parent.name)
        except Exception as exc:  # keep going; report the failure for this file only
            print(f"FAILED {loose_pdf.name}: {exc}", file=sys.stderr)

    if done:
        print(f"Ingested {len(done)}: " + ", ".join(done))
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
