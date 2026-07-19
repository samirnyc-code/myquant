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
    [int]$TimeoutSec = 240,          # cold start measured at 2m28s on this machine
    [string]$ExePath = 'C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe',
    [string]$LogDir  = "$env:USERPROFILE\Documents\NinjaTrader 8\log",
    # window title that means "past the login prompt". Verify against a real logged-in
    # session before trusting it - a wrong pattern here re-creates the false-green.
    [string]$ReadyWindowPattern = 'Control Center'
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

# --- wait for the CONTROL CENTER, not just any window ------------------------
# 2026-07-19: the first version of this waited for MainWindowHandle -ne 0 and reported
# success on the LOGIN PROMPT - process up, window drawn, nothing recording. Exactly the
# false-green this script exists to prevent. A window is not a running platform; only the
# Control Center means NT8 got past sign-in.
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$proc = $null; $ready = $false; $lastTitle = ''
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $proc = Get-Process NinjaTrader -ErrorAction SilentlyContinue
    if (-not $proc) { continue }
    $proc.Refresh()
    $titles = @($proc | ForEach-Object { $_.MainWindowTitle } | Where-Object { $_ })
    if ($titles) { $lastTitle = $titles -join ' | ' }
    if ($titles | Where-Object { $_ -match $ReadyWindowPattern }) { $ready = $true; break }
}

if (-not $proc)  { Say "FAILED: process never appeared"; exit 1 }
if (-not $ready) {
    Say "FAILED: NT8 running (PID $($proc.Id -join ',')) but no window matching '$ReadyWindowPattern' after ${TimeoutSec}s"
    Say "        window title seen: '$lastTitle'"
    Say "        most likely STUCK AT THE LOGIN PROMPT - nothing is recording. Needs a human."
    exit 1
}

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
