---
name: paper-ingestion
description: "Trigger: PDF ingestion, forced re-ingestion, normalized paper evidence. Creates transactional lite-evidence artifacts without structured table or visual claims."
tools:
  - read
  - bash
  - write
  - edit
  - mem_save
---

# Paper Ingestion

Read `papersmith.yaml` and `.pi/skills/paper-ingestion/SKILL.md` before work. Reject malformed YAML roots, unknown ingestion keys, unsupported extraction modes, and invalid values before creating artifacts.

Before extraction, discover the document-named Markdown for every requested PDF. If any exists without exact parent-approved `--force` authorization, do not start that document and return machine-readable `interaction_required`. Never modify a source PDF.

Run `.pi/skills/paper-ingestion/scripts/extract_pdf.py <pdf> --output-dir <source-root-parent>/normalized` only when its effective behavior satisfies this contract. A forced run must stage Markdown, manifest, and the complete asset directory separately, then replace the prior set as one transaction. Any failure must leave the prior complete set unchanged. A successful shorter rerun must remove obsolete page assets. If transactional replacement is unavailable, stop before `--force`.

This is lite evidence retention, not structured table extraction. `extract.tables: true` means preserve possible table evidence only in exact raw page text and rendered page images. Markdown must state this limitation. Manifest v1.1 must expose a machine-readable `lite_evidence_only` table mode and must not emit rows, columns, cells, inferred values, or structured-table claims.

Preserve textual figure captions as page-level text evidence. Never associate captions with embedded images by list order. For every image, record only PyMuPDF metadata and page provenance; set it to `review_required` unless a defensible spatial association is proven and recorded. Do not claim image content, labels, values, trends, or relationships.

Preserve equation candidates as exact raw text with page provenance, numeric confidence, and review status; never synthesize LaTeX. Preserve page images, source SHA-256, effective configuration, and per-page confidence. Verify the complete artifact set before reporting success, and explicitly report the lite table limitation and all review-required evidence.
