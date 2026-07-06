#!/usr/bin/env bash
# Remove the weekly report schedule installed by install_schedule.sh.
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
UNIT_DIR="$HOME/.config/systemd/user"

systemctl --user disable --now embitel-weekly.timer 2>/dev/null || true
rm -f "$UNIT_DIR/embitel-weekly.timer" "$UNIT_DIR/embitel-weekly.service"
systemctl --user daemon-reload 2>/dev/null || true
echo "Weekly schedule removed."
