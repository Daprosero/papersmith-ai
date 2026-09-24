"""Literature ingestion bridge and reference index maintenance."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..bridges.python import mapped_returncode, run_script
from ..core.exit_codes import EXECUTION_ERROR, USER_ERROR
from ..errors import ExecutionError, UserError
from . import fs


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return value or "paper"


def classify_source(source: str) -> dict[str, str]:
    """Classify local/PDF/arXiv/OpenReview inputs without network access."""
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        path = Path(source)
        if path.suffix.lower() != ".pdf":
            raise UserError("ingest source must be a PDF path or an arXiv/OpenReview/PDF URL")
        return {"kind": "file", "url": "", "slug": _slug(path.stem)}
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if "arxiv.org" in host:
        if path.startswith("/abs/"):
            identifier = path.removeprefix("/abs/")
            return {"kind": "url", "url": f"https://arxiv.org/pdf/{identifier}.pdf", "slug": _slug(identifier)}
        if path.startswith("/pdf/"):
            identifier = path.removeprefix("/pdf/")
            if not identifier.endswith(".pdf"):
                identifier += ".pdf"
            return {"kind": "url", "url": f"https://arxiv.org/pdf/{identifier}", "slug": _slug(identifier.removesuffix(".pdf"))}
    if "openreview.net" in host:
        if path.startswith("/pdf") or path.endswith(".pdf"):
            return {"kind": "url", "url": source, "slug": _slug(parsed.query or Path(path).stem)}
        if path == "/forum" and urllib.parse.parse_qs(parsed.query).get("id"):
            identifier = urllib.parse.parse_qs(parsed.query)["id"][0]
            return {"kind": "openreview", "url": source, "slug": _slug(identifier)}
    if Path(parsed.path).suffix.lower() == ".pdf":
        return {"kind": "url", "url": source, "slug": _slug(Path(parsed.path).stem)}
    raise UserError("URL must point to a PDF, arXiv /abs or /pdf route, or an OpenReview forum")


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "papersmith/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    except (OSError, urllib.error.URLError) as exc:
        raise ExecutionError(f"could not download literature source: {exc}") from exc


def _openreview_pdf(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url)
    identifier = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
    if not identifier:
        raise UserError("OpenReview forum URL has no id query parameter")
    api = f"https://api2.openreview.net/notes?id={urllib.parse.quote(identifier)}"
    request = urllib.request.Request(api, headers={"User-Agent": "papersmith/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ExecutionError(f"could not resolve OpenReview PDF: {exc}") from exc
    notes = payload.get("notes", []) if isinstance(payload, dict) else []
    if not notes:
        raise UserError(f"OpenReview note not found: {identifier}")
    content = notes[0].get("content", {})
    pdf = content.get("pdf") if isinstance(content, dict) else None
    if isinstance(pdf, dict):
        pdf = pdf.get("value")
    if not isinstance(pdf, str) or not pdf:
        raise UserError(f"OpenReview note has no PDF attachment: {identifier}")
    if pdf.startswith("http://") or pdf.startswith("https://"):
        pdf_url = pdf
    else:
        pdf_url = urllib.parse.urljoin("https://openreview.net", pdf)
    return pdf_url, _slug(identifier)


def _unique_destination(directory: Path, stem: str) -> Path:
    candidate = directory / f"{stem}.pdf"
    number = 2
    while fs.exists(candidate):
        candidate = directory / f"{stem}-{number}.pdf"
        number += 1
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _title_from_markdown(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def refresh_index(workspace: str | Path) -> dict:
    root = Path(workspace).expanduser().resolve()
    reference = root / "guidance" / "reference-papers"
    reference.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for markdown in sorted(reference.rglob("*.md")):
        if markdown.name.lower() == "readme.md":
            continue
        entries.append({
            "id": markdown.parent.name,
            "title": _title_from_markdown(markdown),
            "path": markdown.relative_to(root).as_posix(),
            "sha256": _sha256(markdown),
            "updated_at": _timestamp(),
        })
    index = {"schema": 1, "updated_at": _timestamp(), "entries": entries}
    (reference / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index


def ingest(source: str, workspace: str | Path = ".", *, ocr: bool = False) -> dict:
    root = Path(workspace).expanduser().resolve()
    if not fs.is_regular_file(root / ".papersmith" / "manifest.json"):
        raise UserError(f"not a papersmith workspace: {root}")
    classified = classify_source(source)
    reference = root / "guidance" / "reference-papers"
    reference.mkdir(parents=True, exist_ok=True)
    if classified["kind"] == "file":
        original = Path(source).expanduser().resolve()
        if not fs.is_regular_file(original):
            raise UserError(f"PDF does not exist: {original}")
        pdf = original if original.parent == reference else _unique_destination(reference, classified["slug"])
        if pdf != original:
            shutil.copyfile(original, pdf)
        source_url = None
    else:
        url = classified["url"]
        if classified["kind"] == "openreview":
            url, slug = _openreview_pdf(url)
        else:
            slug = classified["slug"]
        pdf = _unique_destination(reference, slug)
        _download(url, pdf)
        source_url = source

    args = [str(pdf.relative_to(root))]
    if ocr:
        args.extend(["--mode", "balanced"])
    result = run_script(
        root,
        "skills/paper-ingestion/scripts/extract_pdf.py",
        args,
        prefer_micromamba=True,
        timeout=3600,
    )
    code = mapped_returncode(result)
    if code:
        if result.stderr:
            print(result.stderr, end="", file=__import__("sys").stderr)
        if code == USER_ERROR:
            raise UserError("paper ingestion rejected the source or configuration")
        raise ExecutionError("paper ingestion failed")
    index = refresh_index(root)
    return {"source": source, "pdf": pdf.relative_to(root).as_posix(), "source_url": source_url, "index": index}


def register(subparsers) -> None:
    parser = subparsers.add_parser("ingest", help="ingest a PDF or literature URL")
    parser.add_argument("source", metavar="<file_or_url>")
    parser.add_argument("directory", nargs="?", default=".", metavar="<dir>")
    parser.add_argument("--ocr", action="store_true", help="use the balanced OCR-oriented extraction mode")
    parser.set_defaults(handler=run_cli)


def run_cli(args) -> int:
    print(f"Ingesting {args.source} with Marker...")
    print("Note: First-time ingestion downloads ~1.5 GB Surya model weights to ~/.cache/huggingface.")
    result = ingest(args.source, args.directory, ocr=args.ocr)
    print(f"Ingested: {result['pdf']}")
    print(f"Reference index entries: {len(result['index']['entries'])}")
    return 0

