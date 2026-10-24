#!/usr/bin/env bash
set -euo pipefail
CACHEKIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CACHEKIT_ROOT"
exec npm --prefix web run dev -- "$@"
