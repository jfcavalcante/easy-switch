# Install kvmsync as a Task Scheduler task (Windows equivalent of
# systemd/kvmsync.service): starts at logon, no console window,
# restarts on failure, logs to %LOCALAPPDATA%\kvmsync\kvmsync.log.
#
# Usage (from the repo root):
#   powershell -ExecutionPolicy Bypass -File windows\install-task.ps1
#   powershell -ExecutionPolicy Bypass -File windows\install-task.ps1 -Uninstall
#
# Manage it like a service:
#   Start-ScheduledTask kvmsync / Stop-ScheduledTask kvmsync
#   Get-Content $env:LOCALAPPDATA\kvmsync\kvmsync.log -Wait -Tail 50

param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$TaskName = 'kvmsync'

if ($Uninstall) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    "Task '$TaskName' removed."
    return
}

$repo = Split-Path -Parent $PSScriptRoot
$config = Join-Path $repo 'config.toml'
if (-not (Test-Path $config)) { throw "Missing $config (copy config.example.toml)." }

# Use the pythonw.exe next to the python.exe that has hidapi installed.
$python = (& python -c "import hid, sys; print(sys.executable)").Trim()
if ($LASTEXITCODE -ne 0) { throw "python with hidapi not found (pip install hidapi)." }
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'

$logDir = Join-Path $env:LOCALAPPDATA 'kvmsync'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir 'kvmsync.log'

$action = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "-m kvmsync -c `"$config`" --log-file `"$log`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

"Task '$TaskName' installed and started."
"  python: $pythonw"
"  log:    $log"
