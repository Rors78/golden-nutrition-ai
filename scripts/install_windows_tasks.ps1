<#
Install the Golden Nutrition AI scheduled jobs on Windows - parity with the
systemd user timers used on Linux:

    Backup       03:30 daily       scripts/backup_data.py     (14 snapshots kept)
    Briefing     07:00 daily       scripts/daily_briefing.py  (morning coach push)
    PriceWatch   09:00 daily       scripts/price_watch.py     (deal drop alerts)
    Sentinel     12:00 daily       scripts/sentinel.py        (alerts only on trouble)
    WeeklyReview 18:00 Sundays     scripts/weekly_review.py   (coaching review push)

Usage (from anywhere):
    powershell -ExecutionPolicy Bypass -File scripts\install_windows_tasks.ps1
    ... -StartAtLogon      also start the app server at every logon
    ... -Uninstall         remove every GoldenNutritionAI task

Inspect afterwards with:  Get-ScheduledTask -TaskPath \GoldenNutritionAI\
#>
param(
    [switch]$StartAtLogon,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Repo 'venv\Scripts\python.exe'
$TaskPath = '\GoldenNutritionAI\'

$jobs = @(
    @{ Name = 'Backup';     Script = 'scripts\backup_data.py';    At = '03:30' },
    @{ Name = 'Briefing';   Script = 'scripts\daily_briefing.py'; At = '07:00' },
    @{ Name = 'PriceWatch'; Script = 'scripts\price_watch.py';    At = '09:00' },
    @{ Name = 'Sentinel';   Script = 'scripts\sentinel.py';       At = '12:00' }
)

if ($Uninstall) {
    foreach ($name in @('Backup', 'Briefing', 'PriceWatch', 'Sentinel', 'WeeklyReview', 'Server')) {
        try {
            Unregister-ScheduledTask -TaskName $name -TaskPath $TaskPath -Confirm:$false -ErrorAction Stop
            Write-Host "Removed $TaskPath$name"
        } catch {}
    }
    Write-Host 'Done.'
    exit 0
}

if (-not (Test-Path $Python)) {
    throw ("venv python not found at $Python - create it first:`n" +
           '    python -m venv venv; venv\Scripts\pip install -r requirements.txt')
}

# -StartWhenAvailable = run late if the machine was asleep/off at the trigger
# time (parity with systemd Persistent=true).
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

foreach ($j in $jobs) {
    $action = New-ScheduledTaskAction -Execute $Python `
        -Argument ('"{0}"' -f (Join-Path $Repo $j.Script)) `
        -WorkingDirectory $Repo
    $trigger = New-ScheduledTaskTrigger -Daily -At $j.At
    Register-ScheduledTask -TaskName $j.Name -TaskPath $TaskPath `
        -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Installed $TaskPath$($j.Name) - daily at $($j.At)"
}

$action = New-ScheduledTaskAction -Execute $Python `
    -Argument ('"{0}"' -f (Join-Path $Repo 'scripts\weekly_review.py')) `
    -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '18:00'
Register-ScheduledTask -TaskName 'WeeklyReview' -TaskPath $TaskPath `
    -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Installed ${TaskPath}WeeklyReview - Sundays at 18:00"

if ($StartAtLogon) {
    $action = New-ScheduledTaskAction -Execute $Python `
        -Argument ('"{0}"' -f (Join-Path $Repo 'run.py')) `
        -WorkingDirectory $Repo
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $srvSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero)   # no time limit: it's a server
    Register-ScheduledTask -TaskName 'Server' -TaskPath $TaskPath `
        -Action $action -Trigger $trigger -Settings $srvSettings -Force | Out-Null
    Write-Host "Installed ${TaskPath}Server - app on http://localhost:8501 at every logon"
}

Write-Host 'All set. Inspect with: Get-ScheduledTask -TaskPath \GoldenNutritionAI\'
