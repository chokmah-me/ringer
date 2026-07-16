#Requires -Version 7.0
<#
.SYNOPSIS
  Install or update twice-weekly Task Scheduler jobs for ModelMixBrief.

.DESCRIPTION
  Creates two schtasks (Tue + Fri 09:00 by default) that run Invoke-ModelMixBrief.ps1
  under the current user when logged on (/IT — uses User env + Grok/Claude auth).

.PARAMETER Time
  HH:mm 24h local time. Default 09:00

.PARAMETER Uninstall
  Remove the scheduled tasks instead of installing.
#>
[CmdletBinding()]
param(
    [string] $Time = '09:00',
    [switch] $Uninstall
)

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot
$InvokeScript = Join-Path $ScriptDir 'Invoke-ModelMixBrief.ps1'
if (-not (Test-Path $InvokeScript)) {
    throw "Missing $InvokeScript"
}

$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$tr = '"{0}" -NoProfile -ExecutionPolicy Bypass -File "{1}"' -f $pwsh, $InvokeScript

$tasks = @(
    @{ Name = 'Ringer\ModelMixRefresh-Tue'; Day = 'TUE' },
    @{ Name = 'Ringer\ModelMixRefresh-Fri'; Day = 'FRI' }
)

if ($Uninstall) {
    foreach ($t in $tasks) {
        Write-Host "Deleting $($t.Name)..."
        schtasks /Delete /TN $t.Name /F 2>$null | Out-Null
    }
    Write-Host "Uninstalled."
    return
}

foreach ($t in $tasks) {
    Write-Host "Creating $($t.Name) at $Time $($t.Day)..."
    # Remove if exists so recreate is clean
    schtasks /Delete /TN $t.Name /F 2>$null | Out-Null
    # /IT = interactive only when user is logged on (OAuth-friendly)
    # /RL LIMITED = standard user rights
    $args = @(
        '/Create'
        '/TN', $t.Name
        '/TR', $tr
        '/SC', 'WEEKLY'
        '/D', $t.Day
        '/ST', $Time
        '/RL', 'LIMITED'
        '/F'
        '/IT'
    )
    $out = & schtasks @args 2>&1 | Out-String
    Write-Host $out
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks failed for $($t.Name): $out"
    }
}

Write-Host ""
Write-Host "Installed. Query:"
schtasks /Query /TN 'Ringer\ModelMixRefresh-Tue' /FO LIST /V | Select-String -Pattern 'Task Name|Next Run|Status|Task To Run|Schedule'
schtasks /Query /TN 'Ringer\ModelMixRefresh-Fri' /FO LIST /V | Select-String -Pattern 'Task Name|Next Run|Status|Task To Run|Schedule'
Write-Host ""
Write-Host "Manual run:  schtasks /Run /TN `"Ringer\ModelMixRefresh-Tue`""
Write-Host "Or:          & `"$InvokeScript`""
Write-Host "Outputs:     $env:USERPROFILE\.ringer\model-mix\latest.md"
