#!/usr/bin/env bash
set -euo pipefail

CACHEKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CACHEKIT_ROOT"
command -v uv >/dev/null || { echo "Install uv before running setup." >&2; exit 1; }
command -v npm >/dev/null || { echo "Install Node.js and npm before running setup." >&2; exit 1; }

uv sync --all-packages --all-extras
npm --prefix web install

# Explicit setup download, separate from the offline analysis engine. No weights or GPU.
uv run --no-sync hf download Qwen/Qwen3-4B-Instruct-2507 \
  tokenizer.json tokenizer_config.json config.json \
  --revision cdbee75f17c01a7cc42f958dc650907174af0554 --local-dir data/tokenizer
echo "Dependencies and pinned tokenizer are ready. No inference or fixer was started."
