#!/usr/bin/env bash
set -euo pipefail
CACHEKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CACHEKIT_ROOT"
uv run --no-sync pytest
uv run --no-sync ruff check engine demo_app bench
uv run --no-sync ruff format --check engine demo_app bench
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web run build
