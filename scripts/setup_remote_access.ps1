<#
Put the app on your private Tailscale network with HTTPS - the safe way to
reach it from your phone anywhere, without exposing anything to the internet.
Windows port of setup_remote_access.sh.

    powershell -ExecutionPolicy Bypass -File scripts\setup_remote_access.ps1 [-Port 8501]

What this does:
  1. Installs Tailscale via winget if missing.
  2. Brings this machine onto your tailnet (opens a browser login once).
  3. Runs `tailscale serve` so https://<this-machine>.<tailnet>.ts.net
     proxies to localhost:8501 - the app itself stays bound to localhost,
     and Tailscale terminates HTTPS (which the PWA, mic, and camera need).

On the phone: install the Tailscale app, log into the SAME account, then
open the https URL printed at the end. Install the PWA from there.
Undo with:  tailscale serve --https=443 off
#>
param([int]$Port = 8501)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
    Write-Host '-- Installing Tailscale via winget...'
    winget install --id Tailscale.Tailscale -e `
        --accept-source-agreements --accept-package-agreements
    # Pick up the PATH the installer just wrote without a new shell
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
        throw 'Tailscale installed but not on PATH yet - open a new terminal and re-run this script.'
    }
}

tailscale status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host '-- Logging this machine into your tailnet (a browser window will open)...'
    tailscale up
}

Write-Host "-- Serving localhost:$Port over HTTPS on your tailnet..."
tailscale serve --bg "localhost:$Port"

Write-Host ''
Write-Host '-- Done. Your app on the tailnet:'
tailscale serve status
Write-Host ''
Write-Host 'On your phone: install Tailscale, sign into the same account, open the'
Write-Host "https URL above, and use the browser menu -> 'Install app' for the PWA."
Write-Host 'The vitals webhook URL shown in the Vitals tab works from anywhere too.'
Write-Host 'Undo with: tailscale serve --https=443 off'
