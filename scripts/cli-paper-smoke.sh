#!/usr/bin/env bash
# CLI paper smoke: offline init/status/ingest/dry-run/audit reusing tests/fixtures/e2e/.
# Ingest is stub-equivalent (fixture copy, no Marker/network); mirrors _stub_extract.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${1:-$(mktemp -d)}"
if [[ -z "${1:-}" ]]; then trap 'rm -rf "$WS"' EXIT; fi
export PYTHONPATH="$ROOT/src"
PY="$ROOT/.venv/bin/python"
unset KAGGLE_API_TOKEN KAGGLE_KEY KAGGLE_USERNAME KAGGLE_CONFIG_DIR 2>/dev/null || true
"$PY" -m papersmith.cli init "$WS" --title "Smoke Paper" --topic "smoke" --remote local --no-npm
"$PY" -m papersmith.cli status "$WS"
mkdir -p "$WS/guidance/reference-papers/paper"
cp "$ROOT/tests/fixtures/e2e/paper.pdf" "$WS/guidance/reference-papers/paper.pdf"
cp "$ROOT/tests/fixtures/research-concept-r01.md" "$WS/guidance/reference-papers/paper/paper.md"
printf '\x89PNG\r\n\x1a\n' > "$WS/guidance/reference-papers/paper/_page_1_Figure_1.png"
"$PY" -m papersmith.cli run smoke_and_invariants --dry-run "$WS"
"$PY" -m papersmith.cli audit "$WS" --check-drift
echo "smoke: ok ($WS)"
