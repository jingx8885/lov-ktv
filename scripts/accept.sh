#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export UV_PROJECT_ENVIRONMENT="$ROOT/.venv"
uv sync --project "$ROOT/backend" --extra dev --frozen --quiet
PYTHONPATH="$ROOT/backend" "$ROOT/.venv/bin/python" -m pytest -q backend/tests
echo "accept: unit tests passed"
