# Register the daily IB Gateway auto-login + readiness watchdog — Mon-Fri, before the open.
# IBC (C:\IBC) logs into the paper account from C:\IBC\config.ini (credentials live there,
# OUTSIDE the repo — never committed). Gateway stays up all day; the 08:26 CT feed and
# 08:29 CT trigger daemon connect to it on port 4002.
#
# S103 (2026-08-10) — the Monday cold-auth hang fix. That day the weekend-expired IBC
# autorestart token forced a FULL authentication that hung ~85 min (07:30->08:56 CT), so
# the feed was dead straight through the 08:30 open and every premium setup was missed.
# Three-part schedule fix (root cause = C:\IBC\config.ini AutoRestartTime=02:00, set
# manually there since config.ini is outside the repo):
#   1. Gateway Login moved 07:30 -> 05:30 CT  — a cold auth now has ~3h buffer before open.
#   2. Gateway Watchdog (NEW) 05:30-08:25 CT  — verifies REAL auth (managed accounts, not
#      just port 4002) and force-restarts a gateway stuck >8 min; launches it if down.
#   3. Gateway Ensure 08:20 CT kept as a light backstop (idempotent port bring-up).
#
# Idempotent — safe to re-run. Runs only when the user is logged on (Gateway is a GUI app).
# Run:  powershell -ExecutionPolicy Bypass -File scripts\schedule_gateway_login.ps1

$ctz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Central Standard Time")
function CTtoLocal($ctTime) {
    $today = (Get-Date).ToString('yyyy-MM-dd')
    $ctDt  = [datetime]::ParseExact("$today $ctTime", "yyyy-MM-dd HH:mm", $null)
    $utc   = [System.TimeZoneInfo]::ConvertTimeToUtc($ctDt, $ctz)
    ([System.TimeZoneInfo]::ConvertTimeFromUtc($utc, [System.TimeZoneInfo]::Local)).ToString("HH:mm")
}

$py   = "C:\Users\Admin\myquant\.venv\Scripts\python.exe"
$pyw  = "C:\Users\Admin\myquant\.venv\Scripts\pythonw.exe"
$set  = New-ScheduledTaskSettingsSet -StartWhenAvailable
$days = 'Monday','Tuesday','Wednesday','Thursday','Friday'

# 1) Gateway Login — 05:30 CT. run_at_ct guards the true Chicago time (DST-robust) and the
#    action tees a log to gateway_login_sched.log. StartGateway.bat self-guards double-launch.
$loginLocal = CTtoLocal "05:30"
$loginArgs  = '/c ""' + $py + '" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 05:30 -- cmd.exe /c C:\IBC\StartGateway.bat /INLINE >> "C:\Users\Admin\myquant\data\options_sim\gateway_login_sched.log" 2>&1"'
$aLogin = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $loginArgs
$tLogin = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $loginLocal
Register-ScheduledTask -TaskName "MyQuant Gateway Login" -Action $aLogin -Trigger $tLogin -Settings $set -Force | Out-Null
Write-Output ("registered  MyQuant Gateway Login     Mon-Fri 05:30 CT (= {0} local)" -f $loginLocal)

# 2) Gateway Watchdog — resident from 05:30 CT. Its internal window guard (05:30-08:25 CT)
#    makes the single trigger DST-safe; it exits the moment the gateway is truly ready.
$wdLocal = CTtoLocal "05:30"
$aWd = New-ScheduledTaskAction -Execute $pyw -Argument "scripts\gateway_watchdog.py" -WorkingDirectory "C:\Users\Admin\myquant"
$tWd = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $wdLocal
Register-ScheduledTask -TaskName "MyQuant Gateway Watchdog" -Action $aWd -Trigger $tWd -Settings $set -Force | Out-Null
Write-Output ("registered  MyQuant Gateway Watchdog   Mon-Fri 05:30 CT (= {0} local)" -f $wdLocal)

# 3) Gateway Ensure — 08:20 CT light backstop (idempotent: no-op if 4002 up, else bring up).
$localEns = CTtoLocal "08:20"
$actEns   = New-ScheduledTaskAction -Execute $py -Argument "scripts\gateway_ensure.py" -WorkingDirectory "C:\Users\Admin\myquant"
$trigEns  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $localEns
Register-ScheduledTask -TaskName "MyQuant Gateway Ensure" -Action $actEns -Trigger $trigEns -Settings $set -Force | Out-Null
Write-Output ("registered  MyQuant Gateway Ensure     Mon-Fri 08:20 CT (= {0} local)" -f $localEns)

Write-Output "`nNOTE: root-cause fix lives in C:\IBC\config.ini (outside repo): AutoRestartTime=02:00"
Write-Output ("next Login run: {0}" -f (Get-ScheduledTaskInfo -TaskName 'MyQuant Gateway Login').NextRunTime)
