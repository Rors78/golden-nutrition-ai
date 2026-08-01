#!/usr/bin/env bash
# Put the app on your private Tailscale network with HTTPS — the safe way to
# reach it from your phone anywhere, without exposing anything to the internet.
#
#   ./scripts/setup_remote_access.sh          (will sudo where needed)
#
# What this does:
#   1. Installs Tailscale if missing (official install script).
#   2. Brings this machine onto your tailnet (opens a browser login once).
#   3. Runs `tailscale serve` so https://<this-machine>.<tailnet>.ts.net
#      proxies to localhost:8501 — the app itself stays bound to localhost,
#      and Tailscale terminates HTTPS (which the PWA, mic, and camera need).
#
# On the phone: install the Tailscale app, log into the SAME account, then
# open the https URL printed at the end. Install the PWA from there.
set -euo pipefail

PORT="${1:-8501}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "── Installing Tailscale (needs sudo)…"
  curl -fsSL https://tailscale.com/install.sh | sudo sh
fi

if ! tailscale status >/dev/null 2>&1; then
  echo "── Logging this machine into your tailnet (a browser window will open)…"
  sudo tailscale up
fi

echo "── Serving localhost:${PORT} over HTTPS on your tailnet…"
sudo tailscale serve --bg "localhost:${PORT}"

echo
echo "── Done. Your app on the tailnet:"
tailscale serve status
echo
echo "On your phone: install Tailscale, sign into the same account, open the"
echo "https URL above, and use the browser menu → 'Install app' for the PWA."
echo "The vitals webhook URL shown in the Vitals tab works from anywhere too."
echo "Undo with: sudo tailscale serve --https=443 off"
