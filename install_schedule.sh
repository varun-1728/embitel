#!/usr/bin/env bash
# Portable installer for the weekly report schedule.
# Detects this project's location automatically and installs a systemd user
# timer (Mondays 08:00, with catch-up if the machine was off).
#
# Usage:
#   ./install_schedule.sh            # default: Mondays 08:00
#   ./install_schedule.sh "Fri *-*-* 09:30:00"   # custom OnCalendar schedule
#
# Run as your normal user (NOT root). Works on any Linux box with systemd.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/run_weekly.sh"
ONCALENDAR="${1:-Mon *-*-* 08:00:00}"

UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="$UNIT_DIR/embitel-weekly.service"
TIMER="$UNIT_DIR/embitel-weekly.timer"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "ERROR: systemd (systemctl) not found on this machine."
  echo "Use the cron fallback instead — see README.md."
  exit 1
fi

chmod +x "$WRAPPER"
mkdir -p "$UNIT_DIR"

cat > "$SERVICE" <<EOF
[Unit]
Description=Embitel competitor-intelligence weekly report (refresh + email)

[Service]
Type=oneshot
ExecStart=$WRAPPER
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=Weekly Embitel competitor report — catch up if missed

[Timer]
OnCalendar=$ONCALENDAR
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
systemctl --user daemon-reload
systemctl --user enable --now embitel-weekly.timer

echo "Installed. Schedule: $ONCALENDAR"
echo "Project:  $SCRIPT_DIR"
systemctl --user list-timers embitel-weekly.timer || true
echo
echo "NOTE: catch-up runs when you next log in. For a headless/always-on box"
echo "that should run without login, also run:  sudo loginctl enable-linger $USER"
