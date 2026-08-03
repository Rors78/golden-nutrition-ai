<#
Launch Golden Nutrition AI: make sure the local server is running (start it
if not), then open the app in an app-style browser window.

This is what the desktop shortcut runs - create the shortcut with:
    powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1
#>
param([int]$Port = 8501)
$ErrorActionPreference = 'SilentlyContinue'

function Test-App {
    try {
        (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/state" `
            -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200
    } catch { $false }
}

if (-not (Test-App)) {
    $task = Get-ScheduledTask -TaskName 'Server' -TaskPath '\GoldenNutritionAI\' `
        -ErrorAction SilentlyContinue
    if ($task) {
        Start-ScheduledTask -TaskName 'Server' -TaskPath '\GoldenNutritionAI\'
    } else {
        # No scheduled task - start the server directly, windowless
        $repo = Split-Path -Parent $PSScriptRoot
        Start-Process -FilePath (Join-Path $repo 'venv\Scripts\pythonw.exe') `
            -ArgumentList ('"{0}"' -f (Join-Path $repo 'run.py')) `
            -WorkingDirectory $repo -WindowStyle Hidden
    }
    $deadline = (Get-Date).AddSeconds(20)
    while (-not (Test-App) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
    }
}

# App-style window (no tabs/address bar) via Chrome or Edge; default browser otherwise
$url = "http://localhost:$Port"
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LocalAppData\Google\Chrome\Application\chrome.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) {
    Start-Process $chrome "--app=$url"
} else {
    $edge = @("$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
              "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($edge) { Start-Process $edge "--app=$url" } else { Start-Process $url }
}
