# Register the daily IB Gateway auto-login (IBC) — Mon-Fri, before the market open.
# IBC (C:\IBC) logs into the paper account from C:\IBC\config.ini (credentials
# live there, OUTSIDE the repo — never committed). Gateway stays up all day; the
# 08:26 CT feed and 08:33 CT trigger daemon connect to it on port 4002.
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

$local   = CTtoLocal "08:00"                       # 08:00 CT — comfortably before the 08:26 feed
$action  = New-ScheduledTaskAction -Execute "C:\IBC\StartGateway.bat" -Argument "/INLINE" -WorkingDirectory "C:\IBC"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $local
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "MyQuant Gateway Login" -Action $action -Trigger $trigger -Settings $set -Force | Out-Null

Write-Output ("registered  MyQuant Gateway Login   Mon-Fri 08:00 CT (= {0} local)  C:\IBC\StartGateway.bat /INLINE" -f $local)
Write-Output ("next run: {0}" -f (Get-ScheduledTaskInfo -TaskName "MyQuant Gateway Login").NextRunTime)

# S75 auto-recovery: 08:20 CT VERIFY that the API port 4002 actually came up (login
# alone is NOT proof — 2026-07-16 the GUI logged in but 4002 never listened, silently
# killing the feed/daemon). gateway_ensure.py is idempotent: fast no-op if 4002 is up,
# relaunches IBC + waits if it is down. Runs before the 08:26 feed / 08:33 daemon.
$py       = "C:\Users\Admin\myquant\.venv\Scripts\python.exe"
$localEns = CTtoLocal "08:20"
$actEns   = New-ScheduledTaskAction -Execute $py -Argument "scripts\gateway_ensure.py" -WorkingDirectory "C:\Users\Admin\myquant"
$trigEns  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $localEns
Register-ScheduledTask -TaskName "MyQuant Gateway Ensure" -Action $actEns -Trigger $trigEns -Settings $set -Force | Out-Null
Write-Output ("registered  MyQuant Gateway Ensure   Mon-Fri 08:20 CT (= {0} local)  scripts\gateway_ensure.py" -f $localEns)
Write-Output ("next run: {0}" -f (Get-ScheduledTaskInfo -TaskName "MyQuant Gateway Ensure").NextRunTime)
