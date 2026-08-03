#!/usr/bin/env bash
# One-command provisioning for the paper-ingestion engine (Marker, local/keyless).
# Installs the system dependency (llama.cpp) and the Python venv + requirements.
# Idempotent: safe to re-run.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SKILL_DIR/.venv"
PYTHON="${PYTHON:-python3.12}"

echo "==> paper-ingestion setup"

# 1. System dependency: llama-server (surya-ocr OCR backend). NOT a pip package.
if command -v llama-server >/dev/null 2>&1; then
  echo "  [ok] llama-server already on PATH: $(command -v llama-server)"
elif command -v brew >/dev/null 2>&1; then
  echo "  [..] installing llama.cpp (provides llama-server) via Homebrew"
  brew install llama.cpp
else
  echo "  [!!] llama-server not found and Homebrew unavailable." >&2
  echo "       Install llama.cpp manually: https://github.com/ggml-org/llama.cpp/releases" >&2
  echo "       Then set LLAMA_CPP_BINARY to its path, or put llama-server on PATH." >&2
  exit 1
fi

# 2. Python virtualenv (requires Python 3.10–3.13).
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "  [!!] $PYTHON not found. Install it (e.g. 'brew install python@3.12')" >&2
  echo "       or run with PYTHON=python3.11 ./setup.sh" >&2
  exit 1
fi
if [ ! -d "$VENV" ]; then
  echo "  [..] creating venv with $PYTHON"
  "$PYTHON" -m venv "$VENV"
fi

# 3. Python dependencies.
echo "  [..] installing Python requirements (this downloads ~2-3 GB of ML deps)"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install -r "$SKILL_DIR/requirements.txt"

echo "==> done. Ingest with:"
echo "    $VENV/bin/python $SKILL_DIR/scripts/extract_pdf.py"
