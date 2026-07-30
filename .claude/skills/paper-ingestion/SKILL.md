---
name: paper-ingestion
description: "Trigger: ingest new PDFs into auditable Markdown with raw page text, rendered page images, and lite extraction provenance. Never infers table structure or image content."
---

# Paper Ingestion

## Activation Contract

Accept an optional PDF path or scan `source_roots` from `papersmith.yaml`. Validate the effective configuration before creating any artifact. Run extraction with the bundled script (below); delegate to the `paper-ingestion` subagent for larger batches when isolation helps.

## How to execute

Extraction is performed by the bundled, self-contained script (PyMuPDF + PyYAML — see `requirements.txt`):

```
python3 .claude/skills/paper-ingestion/scripts/extract_pdf.py <pdf> --output-dir <source-root-parent>/normalized
```

Run it only when its effective behavior satisfies the hard rules below. Never modify source PDFs.

## Hard Rules

- Produce `normalized/<document>.md`, `normalized/<document>.manifest.json`, and `normalized/<document>-assets/`; never modify source PDFs.
- Process only PDFs without document-named Markdown. Require explicit approval for each forced re-ingestion.
- Treat forced output as one transaction across Markdown, manifest, and the entire asset directory. On failure preserve the previous complete set. On success replace the set and remove obsolete page assets from shorter reruns.
- Preserve exact raw page text, rendered page images, page numbers, source hash, configuration, confidence, and review status.
- Lite tables are not structured extraction. Even when `extract.tables` is true, retain only raw page text and rendered page images as table evidence; emit no cells, rows, columns, inferred values, or table claims.
- Keep textual captions as page-level evidence. Do not pair captions to embedded images by order. Mark each embedded image `review_required` unless a defensible spatial association is proven and recorded. Never infer image details.
- Preserve equation candidates only as exact raw text with page provenance. Do not synthesize LaTeX or claim exact equations from layout.

## Decision Gates

| Situation | Action |
| --- | --- |
| Malformed/unsupported configuration | Reject before artifact creation |
| Existing Markdown without exact approval | Return `interaction_required` |
| Forced transaction unavailable | Stop; do not risk prior artifacts |
| Low-confidence or ambiguous evidence | Mark `review_required` |

## Execution Steps

1. Load and validate `papersmith.yaml`; identify pending PDFs.
2. Report existing outputs and request exact per-PDF force approval when needed.
3. Extract only pending or explicitly approved PDFs.
4. Verify each successful artifact set is complete and internally consistent.
5. Report processed, skipped, and review-required documents.

## Output Contract

Return Markdown, manifest, and asset paths plus review-required pages. State the table mode as `lite_evidence_only`. Do not claim structured tables, reconstructed equations, caption/image association, or visual interpretation.
