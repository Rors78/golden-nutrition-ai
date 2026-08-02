#!/usr/bin/env bash
# Install a Sunday 18:00 systemd *user* timer for the weekly coaching review.
# Run from the repo root: ./scripts/install_review_timer.sh
# Remove with: systemctl --user disable --now gna-review.timer
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/gna-review.service" <<EOF
[Unit]
Description=Golden Nutrition AI weekly coaching review

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart=$REPO/venv/bin/python $REPO/scripts/weekly_review.py
EOF

cat > "$UNIT_DIR/gna-review.timer" <<EOF
[Unit]
Description=Weekly coaching review on Sunday 18:00

[Timer]
OnCalendar=Sun *-*-* 18:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now gna-review.timer
echo "Installed. Next runs:"
systemctl --user list-timers gna-review.timer --no-pager
