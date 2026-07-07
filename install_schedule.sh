#!/usr/bin/env bash
# Portable installer for the automatic report schedule (Linux + systemd).
#
# The interval/time come from the `schedule:` section of config.yaml
# (default: weekly, Mondays 08:00). Edit config.yaml to change it, then re-run
# this script. You can also pass a raw systemd OnCalendar string to override:
#
#   ./install_schedule.sh                          # use config.yaml
#   ./install_schedule.sh "*-*-* 18:00:00"         # every day at 18:00
#   ./install_schedule.sh "Fri *-*-* 09:30:00"     # Fridays 09:30
#
# Run as your normal user (NOT root).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/run_weekly.sh"
PYTHON="$(command -v python3)"

# Schedule: explicit arg wins, else derive from config.yaml.
if [ "${1:-}" != "" ]; then
  ONCALENDAR="$1"
else
  ONCALENDAR="$("$PYTHON" "$SCRIPT_DIR/main.py" schedule-spec --format oncalendar)"
fi
HUMAN="$("$PYTHON" "$SCRIPT_DIR/main.py" schedule-spec --format human)"

UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="$UNIT_DIR/embitel-weekly.service"
TIMER="$UNIT_DIR/embitel-weekly.timer"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "ERROR: systemd (systemctl) not found. Use the cron fallback — see README.md."
  exit 1
fi

chmod +x "$WRAPPER"
mkdir -p "$UNIT_DIR"

cat > "$SERVICE" <<EOF
[Unit]
Description=Embitel competitor-intelligence report (refresh + email)

[Service]
Type=oneshot
ExecStart=$WRAPPER
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=Automatic Embitel competitor report — catch up if missed

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

echo "Installed. Runs: $HUMAN"
echo "  (systemd OnCalendar = $ONCALENDAR)"
echo "  Project: $SCRIPT_DIR"
echo
systemctl --user list-timers embitel-weekly.timer || true
echo
echo "To STOP it later:  ./uninstall_schedule.sh"
echo "To PAUSE it:       systemctl --user disable --now embitel-weekly.timer"
