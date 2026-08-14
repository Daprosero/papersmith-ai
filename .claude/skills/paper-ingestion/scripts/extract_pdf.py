#!/usr/bin/env python3
"""Paper ingestion via Marker — one self-contained folder per paper.

For each **loose** ``<root>/<stem>.pdf`` (a PDF sitting directly in a source
root), this creates ``<root>/<stem>/``, converts the PDF with Marker, strips the
references/bibliography section, writes each figure as its own image file,
writes ``<stem>.md`` that references those files, and finally moves the PDF in.
So a paper's whole footprint lives in one folder: ``pdf + md + figure images``.

A loose PDF = not yet ingested. Once ingested, the PDF lives inside its folder,
so it is no longer loose and is skipped on the next run.

Ingestion is transactional: conversion happens in a staging directory and the
PDF is moved only once the Markdown and figures are safely in place. A paper
that fails to convert is left **loose**, so the next run retries it instead of
silently reporting "nothing to ingest".

The ``.md`` stays lean (text + LaTeX equations + Markdown tables); figures are
referenced, not embedded — an agent loads a specific figure only when it needs
it. Local and keyless: no API keys and no LLM service.

Source roots are discovered on every run: each folder directly under
``source_base`` that already holds a loose PDF is one, so a new paper folder
needs no configuration edit.

Ingestion *moves* files, so it is never the first thing that runs. ``--list``
answers "what is pending?" without loading a single model, which is what lets
the skill show the findings and get an answer before anything is displaced.

Usage:
    python extract_pdf.py --list          # report the loose PDFs, ingest nothing
    python extract_pdf.py                 # ingest every loose PDF under every source root
    python extract_pdf.py <pdf> [<pdf>…]  # ingest exactly these loose PDFs

Exit codes: 0 success (or nothing to do), 1 at least one paper failed,
2 configuration/usage/environment error (nothing was touched).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

# Apple Silicon (MPS) needs CPU fallback for the handful of ops surya/torch
# do not yet implement on the Metal backend.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import yaml

# .../.claude/skills/paper-ingestion/scripts/extract_pdf.py -> repo root is parents[4]
REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_PATH = REPO_ROOT / "papersmith.yaml"
SETUP_SCRIPT = "./.claude/skills/paper-ingestion/setup.sh"

VALID_MODES = ("fast", "balanced")
VALID_ENGINES = ("marker",)

# A references/bibliography heading (EN or ES). Marker decorates headings with
# bold (**References**), anchor <span> wrappers, and leading numbers, so match
# the heading line, then test its cleaned title text.
_HEADING_LINE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_REFERENCES_TITLE = re.compile(
    r"^(?:\d+\.?\s*)?(?:references|bibliography|referencias|bibliograf[ií]a)\b",
    re.IGNORECASE,
)
_MARKDOWN_DECOR = re.compile(r"[*_`~]|<[^>]+>")


class ConfigError(Exception):
    """The `paper_ingestion` configuration is missing or malformed."""


class EngineError(Exception):
    """The Marker engine is not usable in this environment."""


class IngestionError(Exception):
    """A single paper could not be ingested; the run continues with the rest."""


def load_config(path: Path | None = None) -> dict:
    """Read and validate the `paper_ingestion` block. Raises `ConfigError`.

    Fail closed: a missing file, unparseable YAML, a missing block, or a value
    of the wrong shape is reported instead of being silently treated as "no
    papers to ingest", which is indistinguishable from a healthy no-op.
    """
    path = CONFIG_PATH if path is None else path
    if not path.exists():
        raise ConfigError(f"{path} not found")
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        detail = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        raise ConfigError(f"{path} is not valid YAML: {detail}") from None
    if data is None:
        raise ConfigError(f"{path} is empty")
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a YAML mapping")

    cfg = data.get("paper_ingestion")
    if cfg is None:
        raise ConfigError(f"{path} has no 'paper_ingestion' block")
    if not isinstance(cfg, dict):
        raise ConfigError("'paper_ingestion' must be a mapping of settings")

    engine = cfg.get("engine")
    if engine is not None and engine not in VALID_ENGINES:
        raise ConfigError(f"unknown engine {engine!r}; expected one of {', '.join(VALID_ENGINES)}")

    mode = cfg.get("mode")
    if mode is not None and mode not in VALID_MODES:
        raise ConfigError(f"unknown mode {mode!r}; expected one of {', '.join(VALID_MODES)}")

    strip_refs = cfg.get("strip_references")
    if strip_refs is not None and not isinstance(strip_refs, bool):
        raise ConfigError(f"strip_references must be true or false, got {strip_refs!r}")

    roots = cfg.get("source_roots")
    if roots is not None:
        if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
            raise ConfigError("source_roots must be a list of folder paths")

    base = cfg.get("source_base")
    if base is not None and not isinstance(base, str):
        raise ConfigError(f"source_base must be a folder path, got {base!r}")
    return cfg


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def is_loose(pdf: Path) -> bool:
    """A PDF is loose until it lives inside its own `<stem>/` folder."""
    return pdf.parent.name != pdf.stem


def loose_pdfs_in(folder: Path) -> list[Path]:
    """Loose PDFs sitting directly in `folder` (never a nested folder's)."""
    return sorted(
        entry for entry in folder.iterdir()
        if entry.is_file() and is_pdf(entry) and is_loose(entry)
    )


def discover_source_roots(cfg: dict) -> list[Path]:
    """Resolve the folders to scan: auto-discovered under `source_base`, plus
    any explicit `source_roots`. Raises `ConfigError`.

    A direct child of `source_base` is promoted to a source root only when it
    already holds a loose PDF. Ingestion *moves* files, so that loose PDF is the
    signal that the folder was stocked on purpose — an unrelated folder that
    happens to live under the base is never touched.

    Only one level down: a folder nested inside a root stays invisible, which
    keeps the skill's core rule intact — a subfolder means "paper already
    ingested", not "more papers to find".
    """
    roots: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if path not in seen:
            seen.add(path)
            roots.append(path)

    base = cfg.get("source_base")
    if base:
        base_path = (REPO_ROOT / base).resolve()
        # Fail closed: a base that is not a folder is a typo, and silently
        # discovering nothing would read exactly like "all papers ingested".
        if not base_path.is_dir():
            raise ConfigError(f"source_base {base} is not a folder")
        for child in sorted(base_path.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and loose_pdfs_in(child):
                add(child)

    for root in cfg.get("source_roots") or []:
        root_path = (REPO_ROOT / root).resolve()
        if root_path.is_dir():
            add(root_path)

    if not base and not cfg.get("source_roots"):
        raise ConfigError("no source_base or source_roots configured; nothing can be discovered")
    return roots


def find_loose_pdfs(source_roots: list[Path]) -> list[Path]:
    """PDFs sitting directly in a source root (not yet moved into their folder)."""
    pdfs: list[Path] = []
    for root_path in source_roots:
        pdfs.extend(loose_pdfs_in(root_path))
    return pdfs


def resolve_single_target(raw: str) -> Path:
    """Validate an explicit `<loose-pdf>` argument. Raises `ConfigError`.

    Checked before the engine loads so a mistyped argument never costs a model
    load, and — more importantly — never displaces a file that is not a paper.
    """
    pdf = Path(raw).expanduser().resolve()
    if not pdf.exists():
        raise ConfigError(f"{pdf} does not exist")
    if pdf.is_dir():
        raise ConfigError(f"{pdf} is a directory, not a PDF")
    if not pdf.is_file():
        raise ConfigError(f"{pdf} is not a regular file")
    if not is_pdf(pdf):
        raise ConfigError(f"{pdf.name} is not a PDF")
    if not is_loose(pdf):
        raise ConfigError(
            f"{pdf.name} is already ingested (it lives in {pdf.parent.name}/); "
            "delete that folder to re-ingest"
        )
    return pdf


def page_count(pdf: Path) -> int | None:
    """Page count for the listing, or `None` when it cannot be read.

    Best-effort on purpose. `--list` exists to answer "what is pending?" before
    any model loads, so a PDF whose page tree will not parse is still worth
    showing — without a page count, rather than not at all.
    """
    try:
        import pypdfium2

        doc = pypdfium2.PdfDocument(pdf)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        return None


def print_listing(targets: list[Path]) -> None:
    """Report the pending papers: what would be ingested, and how big each is."""
    print(f"Found {len(targets)} loose PDF(s) pending ingestion:")
    for pdf in targets:
        rel = pdf.relative_to(REPO_ROOT) if pdf.is_relative_to(REPO_ROOT) else pdf
        pages = page_count(pdf)
        print(f"  {rel}" + (f"  ({pages} pages)" if pages is not None else ""))


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
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.config.parser import ConfigParser
    except ImportError as exc:
        raise EngineError(
            f"the Marker engine is not available in this interpreter ({exc}). "
            f"Provision it with {SETUP_SCRIPT} and run the script through "
            ".claude/skills/paper-ingestion/.venv/bin/python"
        ) from None

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


def render_paper(converter, pdf_path: Path, strip_refs: bool, staging: Path) -> None:
    """Convert ``pdf_path`` and write the `.md` + figures into ``staging``."""
    from marker.output import text_from_rendered

    rendered = converter(str(pdf_path))
    text, _ext, images = text_from_rendered(rendered)
    if strip_refs:
        text = strip_references(text)
    if images:
        write_figures(images, staging)
    (staging / f"{pdf_path.stem}.md").write_text(text, encoding="utf-8")


def ingest_loose(converter, loose_pdf: Path, strip_refs: bool) -> Path:
    """Ingest one loose PDF into its own folder, transactionally.

    Conversion happens in a staging directory beside the paper; only when the
    Markdown and figures exist is the destination folder populated and the PDF
    moved in. Any failure leaves the PDF loose and the source root clean, so the
    next run retries the paper instead of skipping it as "already ingested".
    """
    folder = loose_pdf.parent / loose_pdf.stem
    if folder.exists():
        if not folder.is_dir():
            raise IngestionError(f"{folder.name} already exists and is not a folder")
        if any(folder.iterdir()):
            raise IngestionError(
                f"{folder.name}/ already exists and is not empty; "
                "delete that folder to re-ingest this paper"
            )

    # Only a folder this run created may be rolled back; one the operator had
    # already put there is never deleted on our behalf.
    pre_existing = folder.exists()
    staging = Path(tempfile.mkdtemp(prefix=f".{loose_pdf.stem}-ingest-", dir=loose_pdf.parent))
    try:
        render_paper(converter, loose_pdf, strip_refs, staging)
        folder.mkdir(exist_ok=True)
        for produced in sorted(staging.iterdir()):
            shutil.move(str(produced), str(folder / produced.name))
        # The PDF moves last: until it does, the paper is still loose and a
        # retry is a plain re-run.
        shutil.move(str(loose_pdf), str(folder / loose_pdf.name))
    except Exception:
        if not pre_existing:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return folder / f"{loose_pdf.stem}.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-paper-folder PDF -> Markdown ingestion (Marker).")
    parser.add_argument(
        "pdf", nargs="*", help="the loose PDFs to ingest (default: every loose PDF found)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="report the pending loose PDFs and exit, without loading any model or moving any file",
    )
    args = parser.parse_args()

    try:
        cfg = load_config()
        mode = cfg.get("mode")  # None -> Marker auto-selects by device
        strip_refs = bool(cfg.get("strip_references", True))
        if args.pdf:
            # Dedupe while keeping the caller's order: the same PDF named twice
            # would move on the first pass and then "fail" on the second.
            targets = list(dict.fromkeys(resolve_single_target(raw) for raw in args.pdf))
        else:
            targets = find_loose_pdfs(discover_source_roots(cfg))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if not targets:
        print("Nothing to ingest: no loose PDFs found (every paper is already in its folder).")
        return 0

    # Discovery is free; ingestion moves files. Reporting happens before the
    # engine loads so the skill can ask which papers to ingest at no cost.
    if args.list:
        print_listing(targets)
        return 0

    try:
        converter = build_converter(mode)
    except EngineError as exc:
        print(f"Environment error: {exc}", file=sys.stderr)
        return 2

    done: list[str] = []
    failed = 0
    for loose_pdf in targets:
        try:
            md_path = ingest_loose(converter, loose_pdf, strip_refs)
            done.append(md_path.parent.name)
        except Exception as exc:  # keep going; report the failure for this file only
            failed += 1
            print(f"FAILED {loose_pdf.name}: {exc}", file=sys.stderr)

    if done:
        print(f"Ingested {len(done)}: " + ", ".join(done))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
