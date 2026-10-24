#!/usr/bin/env bash
set -euo pipefail
CACHEKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CACHEKIT_ROOT"
CACHEKIT_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
CACHEKIT_INPUT_DIR="data/quickstart/$CACHEKIT_RUN_ID"
CACHEKIT_REPORT="eval_results/quickstart/$CACHEKIT_RUN_ID/report.json"
if [[ -e "$CACHEKIT_INPUT_DIR" || -e "$CACHEKIT_REPORT" ]]; then
  echo "This run directory already exists; retry with a new timestamp." >&2
  exit 1
fi
uv run --no-sync python -m demo_app.traffic --users 6 --seed 42 --out "$CACHEKIT_INPUT_DIR"
uv run --no-sync cachekit analyze "$CACHEKIT_INPUT_DIR/requests_before.jsonl" \
  --tokenizer data/tokenizer --out "$CACHEKIT_REPORT"
echo "Saved a fresh synthetic CPU simulation: $CACHEKIT_REPORT"
echo "No GPU, real fixer session, measured speedup or quality pass is claimed."
