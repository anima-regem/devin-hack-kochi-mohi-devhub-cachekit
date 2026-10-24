#!/usr/bin/env bash
set -euo pipefail
CACHEKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CACHEKIT_ROOT"
exec uv run --no-sync uvicorn cachekit.api:app --host 127.0.0.1 \
  --port "${CACHEKIT_API_PORT:-8000}" "$@"
