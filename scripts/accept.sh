#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
PYTHONPATH=. python3 -m pytest -q
echo "accept: unit tests passed"
