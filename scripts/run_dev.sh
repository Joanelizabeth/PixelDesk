#!/usr/bin/env sh
# Development on macOS/Linux (window mode only; screen-time monitoring is Windows-only).
cd "$(dirname "$0")/.." || exit 1
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt; }
exec .venv/bin/python main.py "$@"
