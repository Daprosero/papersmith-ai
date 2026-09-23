#!/usr/bin/env bash
#
# Live papersmith smoke: a real workspace, a real npm install, the real engines.
#
# The hermetic counterpart (scripts/cli-paper-smoke.sh) runs offline against a
# fixture copy and needs no opt-in. This script is the opposite: it writes to a
# real workspace, runs `npm install`, and may launch one model call. It refuses
# to run unless PAPERSMITH_LIVE=1 so nobody triggers it by accident.
#
# Usage:
#   PAPERSMITH_LIVE=1 bash scripts/cli-paper-live-smoke.sh [workspace-dir]
#
# Optional legs, each opted in on top of PAPERSMITH_LIVE=1:
#   PAPERSMITH_LIVE_INGEST=/path/to/paper.pdf   run a real Marker ingest
#   PAPERSMITH_LIVE_AGENT=redactor              launch one subagent through
#                                               the claude CLI inside the
#                                               workspace (one model call)
#
# Covers every papersmith command (init upgrade status ingest deliberate
# implement run remote target audit) and every shipped skill front door.
set -euo pipefail

if [[ "${PAPERSMITH_LIVE:-}" != "1" ]]; then
  echo "refusing to run: this smoke is live (real npm install, real engines, optional model call)." >&2
  echo "opt in with: PAPERSMITH_LIVE=1 bash scripts/cli-paper-live-smoke.sh" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="${1:-$(mktemp -d)}"
if [[ -z "${1:-}" ]]; then trap 'rm -rf "$WS"' EXIT; fi

PY="${PAPERSMITH_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PS=("$PY" -m papersmith.cli)

echo "== live smoke: init (real npm install)"
"${PS[@]}" init "$WS" --title "Live Smoke" --topic "live smoke" --remote local

if [[ ! -d "$WS/node_modules/jiti" ]]; then
  echo "live smoke failed: npm install did not complete; deliberate legs cannot run" >&2
  exit 1
fi

echo "== live smoke: status / target / run / audit / upgrade"
"${PS[@]}" status "$WS"
"${PS[@]}" target list "$WS"
"${PS[@]}" target check local-workstation "$WS"
"${PS[@]}" run smoke_and_invariants --dry-run "$WS"
"${PS[@]}" audit "$WS" --check-drift
"${PS[@]}" upgrade "$WS"
"${PS[@]}" status "$WS" --json > /dev/null

echo "== live smoke: deliberate (real engine, keyless)"
"${PS[@]}" deliberate "$WS" --action init \
  --instruction "Live smoke. A real workspace carries this document through its own engine." > /dev/null
"${PS[@]}" deliberate "$WS" --action status > /dev/null

echo "== live smoke: implement (real engine against a fresh demo target)"
mkdir -p "$WS/implementations/live-demo"
printf '# Live demo target\n' > "$WS/implementations/live-demo/README.md"
git -C "$WS/implementations/live-demo" init -q
git -C "$WS/implementations/live-demo" config user.email "live-smoke@test.com"
git -C "$WS/implementations/live-demo" config user.name "live smoke"
git -C "$WS/implementations/live-demo" add -A
git -C "$WS/implementations/live-demo" commit -qm "init live demo target"
"${PS[@]}" implement "$WS" --action probe --target implementations/live-demo --name "LiveDemo" > /dev/null

echo "== live smoke: remote (read-only fold; no job folder exists yet)"
if "${PS[@]}" remote status --target "$WS/implementations/missing" \
     --entrypoint "Notebooks/a.ipynb" "$WS" > /dev/null 2>&1; then
  echo "live smoke failed: remote status accepted an unresolvable job target" >&2
  exit 1
fi

echo "== live smoke: ingest"
if [[ -n "${PAPERSMITH_LIVE_INGEST:-}" ]]; then
  "${PS[@]}" ingest "$PAPERSMITH_LIVE_INGEST" "$WS"
else
  echo "ingest leg skipped: set PAPERSMITH_LIVE_INGEST=<pdf path> to run a real Marker ingest" >&2
fi

echo "== live smoke: skill front doors (workspace copies)"
"$PY" "$WS/skills/paper-writing/scripts/paper_cli.py" scaffold --paper "$WS/paper" > /dev/null
"$PY" "$WS/skills/paper-writing/scripts/paper_cli.py" status --paper "$WS/paper" > /dev/null
node "$WS/skills/proposal-deliberation/cli.mjs" '{"operation":"STATUS"}' > /dev/null
node "$WS/skills/experimental-deliberation/cli.mjs" '{"operation":"STATUS"}' > /dev/null
"$PY" "$WS/skills/kaggle-accounts/scripts/accounts_cli.py" list > /dev/null
"$PY" "$WS/skills/paper-ingestion/scripts/extract_pdf.py" --list > /dev/null
"$PY" "$WS/skills/proposal-implementation/scripts/implementation_cli.py" --help > /dev/null
"$PY" "$WS/skills/experimental-implementation/scripts/implementation_cli.py" --help > /dev/null
"$PY" "$WS/skills/remote-execution/scripts/remote_cli.py" --help > /dev/null
"$PY" "$WS/skills/skill-audit/scripts/audit_cli.py" --help > /dev/null

echo "== live smoke: agent leg"
if [[ -n "${PAPERSMITH_LIVE_AGENT:-}" ]]; then
  if command -v claude >/dev/null 2>&1; then
    (cd "$WS" && claude --agent "$PAPERSMITH_LIVE_AGENT" -p \
      "Reply with your agent name and nothing else.")
  else
    echo "agent leg skipped: claude CLI not on PATH" >&2
  fi
else
  echo "agent leg skipped: set PAPERSMITH_LIVE_AGENT=<name> to launch one subagent through claude" >&2
fi

echo "live smoke: ok ($WS)"
