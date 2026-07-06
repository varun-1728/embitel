#!/usr/bin/env bash
# Weekly competitor-intelligence job (run by cron).
# Refreshes all competitors, then builds + emails the report.
# Output is appended to data/weekly.log with a timestamp header.

cd /home/varun/embitel || exit 1

echo "===== weekly run: $(date '+%Y-%m-%d %H:%M:%S %Z') =====" >> data/weekly.log
/usr/bin/python3 main.py weekly >> data/weekly.log 2>&1
echo "" >> data/weekly.log
