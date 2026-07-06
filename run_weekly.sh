#!/usr/bin/env bash
# Weekly competitor-intelligence job (run by the scheduler).
# Refreshes all competitors, then builds + emails the report.
# Portable: resolves its own location, so it works from any path / any user.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

PYTHON="$(command -v python3)"

echo "===== weekly run: $(date '+%Y-%m-%d %H:%M:%S %Z') =====" >> data/weekly.log
"$PYTHON" main.py weekly >> data/weekly.log 2>&1
echo "" >> data/weekly.log
