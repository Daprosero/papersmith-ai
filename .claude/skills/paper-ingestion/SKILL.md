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

Accept an optional loose PDF path, or discover the source roots from
`papersmith.yaml` and scan them. Validate configuration before doing any work.
Extraction is performed by the bundled script running inside the skill's
dedicated virtualenv.

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
  .claude/skills/paper-ingestion/scripts/extract_pdf.py [--list] [<loose-pdf>…]
```

- `--list`: report the pending loose PDFs and exit. Loads no model, moves no file.
- No argument: discover the source roots, then ingest every **loose** PDF in them.
- `<loose-pdf>…`: ingest exactly those loose PDFs.
- `--file <pdf> --into <topic>`: file one unfiled PDF into a topic folder under the
  base, creating it when new. Moves one file, converts nothing, loads no model.

## Confirmation (required)

**Never ingest without asking first.** Ingestion *moves* the user's PDFs, so
discovery and execution are two separate steps:

1. Run with `--list`. This is free — it loads no model, so asking costs nothing.
2. Report what was found: each paper's path and page count.
3. Ask the user **which papers to ingest**, as a multi-select over the listed
   PDFs. Never assume the whole batch is wanted; a PDF may be sitting in a
   source root by accident, and ingesting it displaces it.
4. Run again passing only the approved paths as arguments. If the user approves
   nothing, stop and ingest nothing.

Running with no argument ingests everything unattended and therefore skips the
user's decision — use it only when the user has explicitly asked for exactly
that. The one loose PDF case is not an exception: one paper still gets moved,
so one paper still gets confirmed.

## A PDF in the base belongs to no topic yet, and nothing files it for you

The base's children are topics. A PDF dropped in the base itself, beside those
folders rather than inside one, is pending and invisible at the same time:
discovery only promotes children, so nothing finds it and the run reports that
every paper is already in its folder.

The script reports these separately and **ingests none of them**. Converting one
where it lies would make it a topic of its own, and the next run would read that
folder as already ingested and leave it there permanently — a stray paper turned
into a permanent category, silently.

So it is a question, not a default:

1. Report each unfiled PDF with its page count, and the topics that exist now.
2. **Ask which topic it belongs in** — one of the existing ones, or a new one
   whose name the user gives. Never pick for them: the topics are the user's
   filing system and the paper's subject is not something to infer from a
   filename.
3. Run `--file <pdf> --into <topic>` with the answer. The PDF lands loose inside
   that topic, which makes it ordinary pending work.
4. Then the normal confirmation applies — filing is not ingestion, and moving a
   paper into a folder never authorizes converting it.

If the user does not want to file it, leave it. It stays reported on every run,
which is the correct end state for a decision nobody has made yet.

**Loose PDF = not yet ingested.** A PDF sitting directly in a source root is
pending; once ingested it lives inside its own `<stem>/` folder, so it is no
longer loose and is skipped. To re-ingest, delete the paper's folder (leaving the
PDF loose) and run again — that deletion is the only forced re-ingestion path,
because an existing non-empty `<stem>/` folder is refused rather than merged
into.

First run downloads the Surya layout/OCR models (~1–2 GB), cached thereafter.

## Failure Semantics

Ingestion is **transactional per paper**. Conversion runs in a staging directory
beside the paper and the PDF is moved in only once its `.md` and figures exist.
A paper that fails to convert stays **loose**, so the next run retries it — a
failure never leaves a PDF stranded in a folder with no `.md`, which the next
run would read as "already ingested".

Exit codes: `0` success or nothing to do, `1` at least one paper failed (the
rest were still ingested), `2` configuration, argument, or environment error —
nothing was touched.

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
  source_base: guidance   # source roots are discovered under here, every run
  source_roots: []        # optional: extra roots outside source_base
```

## Source Root Discovery

Source roots are **rediscovered on every run**. A folder directly under
`source_base` becomes a source root when it holds at least one loose PDF. So
adding a new category of papers (e.g. a `guidance/datasets/` folder for papers
describing the research dataset) is just: create the folder, drop the PDFs in,
run. No configuration edit.

Two boundaries make that safe:

- **A loose PDF is required.** Ingestion *moves* files. Requiring a PDF you put
  there yourself is what keeps an unrelated folder under the base from ever
  being touched.
- **Exactly one level down.** A folder nested inside a source root is never
  scanned, because a subfolder means "paper already ingested". `guidance/` itself
  is a container of roots, not a root: loose PDFs sitting directly in it are
  ignored.

A folder holding only already-ingested papers is not a new root — its PDFs are
not loose — and is correctly left alone.

`source_roots` still works for roots that live outside `source_base`; explicit
entries are added to whatever was discovered. A `source_base` that is not a
folder is a configuration error, not an empty discovery.

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
| `source_base` set to something that is not a folder | Report the error; do nothing |
| Neither `source_base` nor `source_roots` configured | Report the error; do nothing |
| A folder under `source_base` with no loose PDF | Not a source root; leave it untouched |
| Unknown `engine`/`mode`, or a value of the wrong type | Report the error before loading the engine; do nothing |
| Loose PDFs present | List them, ask which to ingest, ingest only those |
| User approves a subset | Ingest exactly the approved paths; leave the rest loose |
| User approves nothing | Stop; move no file |
| No loose PDFs (all in folders) | Report nothing to do; do not re-ingest |
| Argument that is missing, not a PDF, a directory, or already ingested | Refuse before loading the engine; move nothing |
| A paper's `<stem>/` folder already exists and is not empty | Refuse that paper; say to delete the folder to re-ingest |
| Marker not installed in the interpreter | Report it and point at `setup.sh`; move nothing |
| A single file fails | Report that file; leave it loose; continue with the rest |

## Output Reporting

On success, emit only a brief confirmation of which papers were ingested. On
error, report only the error. No config dumps, path listings, or per-page tables.

**Speak the user's language.** Everything addressed to the user — the pending
list, the confirmation question and its options, the success or error report —
goes in the language the user is writing in, not in the language of this
document. The script's own stdout stays English: it is data to read, not a
message to relay verbatim. Paths, filenames, flags, and exit codes are never
translated.
