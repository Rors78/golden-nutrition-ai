#!/usr/bin/env bash
# Install a daily 09:00 systemd *user* timer that re-checks price watches.
# Run from the repo root: ./scripts/install_price_watch_timer.sh
# Remove with: systemctl --user disable --now gna-pricewatch.timer
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/gna-pricewatch.service" <<EOF
[Unit]
Description=Golden Nutrition AI price-watch re-check

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart=$REPO/venv/bin/python $REPO/scripts/price_watch.py
EOF

cat > "$UNIT_DIR/gna-pricewatch.timer" <<EOF
[Unit]
Description=Daily price-watch re-check at 09:00

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now gna-pricewatch.timer
echo "Installed. Next runs:"
systemctl --user list-timers gna-pricewatch.timer --no-pager
