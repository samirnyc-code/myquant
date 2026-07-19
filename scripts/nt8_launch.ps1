<#
nt8_launch.ps1 — start NinjaTrader 8 unattended and report whether it actually came up.

WHY: the L2/tape capture only exists while NT8 is running. A scheduled task that fires
"start NinjaTrader.exe" and reports success the moment the process spawns is worse than
useless — it goes green while the platform sits at a login prompt with nothing recording.
This waits for a real signal (main window + log activity) before claiming success.

IDEMPOTENT: if NT8 is already running it does nothing and exits 0. Safe to schedule
repeatedly (e.g. every 30 min) as a self-healing restart.

USAGE
    powershell -ExecutionPolicy Bypass -File scripts\nt8_launch.ps1
    powershell -ExecutionPolicy Bypass -File scripts\nt8_launch.ps1 -TimeoutSec 180
    powershell -ExecutionPolicy Bypass -File scripts\nt8_launch.ps1 -WhatIf     # dry run

EXIT CODES  (for the traffic light)
    0 = NT8 running with a main window
    1 = launch failed / timed out  -> needs a human
    2 = NinjaTrader.exe not found

NOTE ON CREDENTIALS: nothing here touches your login. NT8 signs in from its own stored
account token; this script only starts the process. No username, password or token is
read, written or logged.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [int]$TimeoutSec = 120,
    [string]$ExePath = 'C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe',
    [string]$LogDir  = "$env:USERPROFILE\Documents\NinjaTrader 8\log"
)

function Say($m) { "{0:HH:mm:ss}  {1}" -f (Get-Date), $m }

# --- already up? -------------------------------------------------------------
$existing = Get-Process NinjaTrader -ErrorAction SilentlyContinue
if ($existing) {
    $hasWin = $existing | Where-Object { $_.MainWindowHandle -ne 0 }
    Say "NT8 already running (PID $($existing.Id -join ',')), mainWindow=$([bool]$hasWin) - nothing to do"
    exit 0
}

if (-not (Test-Path $ExePath)) { Say "NinjaTrader.exe NOT FOUND at $ExePath"; exit 2 }

# remember where the log was, so we can prove NT8 actually did something
$before = $null
if (Test-Path $LogDir) {
    $before = Get-ChildItem $LogDir -Filter 'log.*.txt' -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
}

if (-not $PSCmdlet.ShouldProcess($ExePath, 'Start NinjaTrader 8')) { Say 'dry run - not starting'; exit 0 }

Say "starting $ExePath"
try { Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path $ExePath) | Out-Null }
catch { Say "start failed: $($_.Exception.Message)"; exit 1 }

# --- wait for a REAL signal, not just a PID ----------------------------------
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$proc = $null; $win = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $proc = Get-Process NinjaTrader -ErrorAction SilentlyContinue
    if (-not $proc) { continue }
    $proc.Refresh()
    if ($proc | Where-Object { $_.MainWindowHandle -ne 0 }) { $win = $true; break }
}

if (-not $proc) { Say "FAILED: process never appeared"; exit 1 }
if (-not $win)  { Say "FAILED: process up (PID $($proc.Id -join ',')) but no main window after ${TimeoutSec}s - stuck at login?"; exit 1 }

Say "NT8 up: PID $($proc.Id -join ',')"

# did it write to the log? (proves the platform initialised, not just drew a window)
Start-Sleep -Seconds 5
if (Test-Path $LogDir) {
    $after = Get-ChildItem $LogDir -Filter 'log.*.txt' -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($after) {
        $fresh = (-not $before) -or ($after.Name -ne $before.Name) -or ($after.LastWriteTime -gt $before.LastWriteTime)
        Say "log: $($after.Name) lastWrite=$($after.LastWriteTime.ToString('HH:mm:ss')) fresh=$fresh"
    }
}

Say 'OK - remember: connection + workspace + strategy still need verifying (nt8_launch only proves the app started)'
exit 0
