#!/usr/bin/env bash
# Common tail of every scenario: env -> materialize -> suite -> notebook -> verify.
#   finish.sh <target> <Name> <seed>
set -euo pipefail

FORGE="$(cd "$(dirname "$0")/.." && pwd)"
CLI="$FORGE/.claude/skills/proposal-implementation/scripts/implementation_cli.py"
SCRATCH="$(cd "$(dirname "$0")" && pwd)"

TARGET="$1"; NAME="$2"; SEED="$3"

# Bind to the harness fixture so a direct invocation resolves the revision the
# same way the battery does. Under `set -e` an unresolved revision aborts the
# script at admit, and every later step reports as if it had never run.
export IMPLEMENTATION_PROPOSALS="${IMPLEMENTATION_PROPOSALS:-$FORGE/tests/fixtures}"

cd "$FORGE"
python3 "$CLI" env --target "$TARGET" >/dev/null
"$TARGET/.venv/bin/pip" install -q pytest numpy ipykernel nbconvert 2>&1 \
  | rg -v 'WARNING|consider upgrading' || true

python3 "$FORGE/.claude/skills/proposal-implementation/scripts/materialize.py" "$TARGET" "$NAME" "$SEED" "$FORGE/tests/fixtures/implementation_kit"

echo "--- admissibility (before any efficacy is measured) ---"
python3 "$CLI" admit --target "$TARGET" --name "$NAME" --revision neutral-concept-r01.md \
  | jq -c '{status, admitted: (.admitted|length), inadmissible: (.inadmissible|keys)}'

echo "--- suite ---"
(cd "$TARGET" && ./.venv/bin/python -m pytest -q 2>&1 | tail -3)

echo "--- notebook (executed) ---"
(cd "$TARGET" && ./.venv/bin/jupyter nbconvert --to notebook --execute --inplace \
   "$NAME/Notebooks/verification.ipynb" 2>&1 | rg -c 'Writing' >/dev/null \
   && echo "executed OK" || echo "NOTEBOOK FAILED")

echo "--- verify ---"
python3 "$CLI" verify --target "$TARGET" --name "$NAME" --revision neutral-concept-r01.md \
  | jq -c '{structure: .structure.status, gaps: .structure.scaffoldGaps, stale: (.structure.staleReferences|length), fidelity: .fidelity.status, invariants: (.validation.invariantTests|length), notebook: .validation.notebook}'
