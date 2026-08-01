#!/usr/bin/env bash
# Install a nightly (03:30) systemd *user* timer that snapshots the data file.
# Run from the repo root: ./scripts/install_backup_timer.sh
# Remove with: systemctl --user disable --now gna-backup.timer
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/gna-backup.service" <<EOF
[Unit]
Description=Golden Nutrition AI nightly data backup

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart=$REPO/venv/bin/python $REPO/scripts/backup_data.py
EOF

cat > "$UNIT_DIR/gna-backup.timer" <<EOF
[Unit]
Description=Nightly nutrition data backup at 03:30

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now gna-backup.timer
echo "Installed. Next runs:"
systemctl --user list-timers gna-backup.timer --no-pager
