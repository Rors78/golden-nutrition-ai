#!/usr/bin/env bash
# Install a daily 12:00 systemd *user* timer for the sentinel (alerts only
# when something needs attention). Run from the repo root:
#     ./scripts/install_sentinel_timer.sh
# Remove with: systemctl --user disable --now gna-sentinel.timer
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/gna-sentinel.service" <<EOF
[Unit]
Description=Golden Nutrition AI sentinel checks

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart=$REPO/venv/bin/python $REPO/scripts/sentinel.py
EOF

cat > "$UNIT_DIR/gna-sentinel.timer" <<EOF
[Unit]
Description=Daily sentinel checks at 12:00

[Timer]
OnCalendar=*-*-* 12:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now gna-sentinel.timer
echo "Installed. Next runs:"
systemctl --user list-timers gna-sentinel.timer --no-pager
