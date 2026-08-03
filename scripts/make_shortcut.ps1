<#
Create (or refresh) the "Golden Nutrition AI" desktop shortcut. Double-click
starts the local server if needed and opens the app in its own window.

    powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1
#>
$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'Golden Nutrition AI.lnk'

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$sc.Arguments = ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' `
    -f (Join-Path $Repo 'scripts\launch_app.ps1'))
$sc.WorkingDirectory = $Repo
$ico = Join-Path $Repo 'app\static\icon.ico'
if (Test-Path $ico) { $sc.IconLocation = "$ico,0" }
$sc.Description = 'Golden Nutrition AI - the iron does not lie'
$sc.Save()
Write-Host "Shortcut created: $lnk"
