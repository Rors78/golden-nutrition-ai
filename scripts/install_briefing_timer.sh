#!/usr/bin/env bash
# Install a 7:00 AM systemd *user* timer for the morning coach briefing.
# Run from the repo root: ./scripts/install_briefing_timer.sh
# Remove with: systemctl --user disable --now gna-briefing.timer
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/gna-briefing.service" <<EOF
[Unit]
Description=Golden Nutrition AI morning coach briefing

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart=$REPO/venv/bin/python $REPO/scripts/daily_briefing.py
EOF

cat > "$UNIT_DIR/gna-briefing.timer" <<EOF
[Unit]
Description=Morning coach briefing at 7:00

[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now gna-briefing.timer
echo "Installed. Next runs:"
systemctl --user list-timers gna-briefing.timer --no-pager
