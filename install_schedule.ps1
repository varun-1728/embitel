# Portable installer for the automatic report schedule (Windows).
# Registers a Scheduled Task using the interval/time from config.yaml.
#
# Run in PowerShell from the project folder:
#   powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1
#
# Change the schedule by editing the `schedule:` section of config.yaml,
# then re-running this script.

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Wrapper    = Join-Path $ProjectDir "run_weekly.bat"
$TaskName   = "EmbitelWeeklyReport"

# Ask the app how to schedule (reads config.yaml).
$spec  = (python (Join-Path $ProjectDir "main.py") schedule-spec --format schtasks).Trim()
$human = (python (Join-Path $ProjectDir "main.py") schedule-spec --format human).Trim()

# spec looks like: /SC WEEKLY /D MON /ST 08:00
# Build a schtasks command. /F overwrites an existing task of the same name.
$cmd = "schtasks /Create /TN $TaskName /TR `"$Wrapper`" $spec /F"
Write-Host "Registering task: $human"
Write-Host "  $cmd"
cmd /c $cmd

# Enable catch-up so a missed run (PC off/asleep) fires after next boot/logon —
# this is the Windows equivalent of systemd's Persistent=true. Without it, a
# missed scheduled start is skipped entirely.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Set-ScheduledTask -TaskName $TaskName -Settings $settings | Out-Null
Write-Host "Catch-up enabled (StartWhenAvailable): missed runs fire after next boot/logon."

Write-Host ""
Write-Host "Installed. To STOP it later:  schtasks /Delete /TN $TaskName /F"
Write-Host "To see it:  schtasks /Query /TN $TaskName"
