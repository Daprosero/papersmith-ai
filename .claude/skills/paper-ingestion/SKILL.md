---
name: paper-ingestion
description: "Trigger: ingest reference PDFs into high-fidelity Markdown (LaTeX equations, Markdown tables, figures as files) using Marker, locally and keyless. One folder per paper: pdf + lean .md + figure images."
---

# Paper Ingestion

Convert each source PDF into a lean, high-fidelity Markdown file an agent can
read directly — body text in reading order, equations as LaTeX, tables as
Markdown. Each paper becomes a **self-contained folder**: `pdf + md + figure
images`. Figures are separate image files the `.md` references (loaded on demand,
not embedded), and the references/bibliography section is dropped. Runs locally
with no API keys.

## Activation Contract

Accept an optional loose PDF path, or scan `source_roots` from `papersmith.yaml`.
Validate configuration before doing any work. Extraction is performed by the
bundled script running inside the skill's dedicated virtualenv.

## Environment (one-time)

The engine (Marker + torch + surya) lives in an isolated venv so it never
pollutes system Python. A new machine is provisioned with one idempotent command:

```
./.claude/skills/paper-ingestion/setup.sh
```

`setup.sh` installs both dependency kinds a `requirements.txt` alone cannot:

- **Python deps** (`requirements.txt`): `marker-pdf`, `PyYAML`, and the ML stack
  they pull in — installed into `.venv`.
- **System binary**: `llama-server` (the surya-ocr OCR backend) via
  `brew install llama.cpp`. This is **not** a pip package, so it can never live
  in `requirements.txt` — the setup script is what makes it reproducible.

Requirements: Python 3.10–3.13 and Homebrew (for `llama.cpp`). Override the
interpreter with `PYTHON=python3.11 ./setup.sh`.

**No `.env` / no keys.** Ingestion is fully keyless — the only runtime env var,
`PYTORCH_ENABLE_MPS_FALLBACK=1` (Apple Silicon), is set by the script itself. To
point at a non-Homebrew llama.cpp, export `LLAMA_CPP_BINARY`.

## How to execute

Always invoke through the venv interpreter:

```
.claude/skills/paper-ingestion/.venv/bin/python \
  .claude/skills/paper-ingestion/scripts/extract_pdf.py [<loose-pdf>]
```

- No argument: scan every `source_roots` folder and ingest every **loose** PDF.
- `<loose-pdf>`: ingest that single loose PDF.

**Loose PDF = not yet ingested.** A PDF sitting directly in a source root is
pending; once ingested it lives inside its own `<stem>/` folder, so it is no
longer loose and is skipped. To re-ingest, delete the paper's folder (leaving the
PDF loose) and run again.

First run downloads the Surya layout/OCR models (~1–2 GB), cached thereafter.

## Output Contract

For a loose `<root>/foo.pdf`, produce `<root>/foo/` containing:

- `foo.pdf` — the source PDF, moved in.
- `foo.md` — lean Markdown: text, LaTeX equations, Markdown tables. The
  references/bibliography section is stripped. Figures are **referenced**
  (`![](_page_4_Figure_2.jpeg)`), not embedded.
- the figure image files the `.md` references, flat in the same folder.

No `normalized/`, no base64, no manifest.

## Configuration (`papersmith.yaml`)

```yaml
paper_ingestion:
  engine: marker
  mode: fast              # fast (CPU/MPS) | balanced (highest fidelity, GPU-oriented)
  strip_references: true  # drop the references/bibliography section at the end
  source_roots:
    - guidance/paper-guide
    - guidance/reference-papers
```

Add a new source root (e.g. a `data`/`database` paper describing the research
dataset) by creating the folder with its PDFs and appending one line here.

## Fidelity & Verification

This skill **interprets** content for maximum fidelity — it reconstructs
equations as LaTeX and tables as Markdown cells. That interpretation can be
wrong (a misread digit, a garbled symbol). The source PDF sits in the same
folder as the `.md`: verify anything load-bearing against it. Prefer `balanced`
mode when fidelity matters more than speed.

## Decision Gates

| Situation | Action |
| --- | --- |
| Malformed/missing configuration | Report the error; do nothing |
| Loose PDFs present | Ingest them without prompting |
| No loose PDFs (all in folders) | Report nothing to do; do not re-ingest |
| A single file fails | Report that file; continue with the rest |

## Output Reporting

On success, emit only a brief confirmation of which papers were ingested. On
error, report only the error. No config dumps, path listings, or per-page tables.
