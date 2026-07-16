# Register the daily options-desk Task Scheduler jobs (S75).
# Idempotent — safe to re-run; -Force overwrites the same-named task.
# Runs as the current user, only when logged on (IB Gateway needs the session).
#
# Daily loop:
#   08:28  Gameplan       -> gameplan_YYYYMMDD.json (premarket plan from EOD levels)
#   08:26  Spot Feed      -> live.json + underlying tape, runs until ~16:20
#   08:33  Trigger Daemon -> auto-executes triggers on their condition until 16:00
#   14:28  Sim Daemon     -> (existing) the 15:59 STMR BPS decision
#   14:35  Marks Watch    -> (existing) marks open positions
#   15:15  Postmortem     -> postmortem_YYYYMMDD.json (plan vs actual, observe-only)
#
# NOTE: this reschedules "MyQuant Spot Feed" to 08:26 (all-day) so the trigger
# daemon has live spot from the open; the same feed covers the 15:59 BPS window.
# Prereq each morning: IB Gateway logged in (paper 4002).
#
# Run:  powershell -ExecutionPolicy Bypass -File scripts\schedule_options_tasks.ps1

$repo = "C:\Users\Admin\myquant"
$py   = "$repo\.venv\Scripts\python.exe"
$sd   = "$repo\scripts"

# Times below are given in EXCHANGE time (US Central = Chicago, where Cboe/CME sit).
# Task Scheduler fires in the machine's LOCAL time, so convert CT -> local (DST-aware).
$ctz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Central Standard Time")
function CTtoLocal($ctTime) {
    $today = (Get-Date).ToString('yyyy-MM-dd')
    $ctDt  = [datetime]::ParseExact("$today $ctTime", "yyyy-MM-dd HH:mm", $null)
    $utc   = [System.TimeZoneInfo]::ConvertTimeToUtc($ctDt, $ctz)
    ([System.TimeZoneInfo]::ConvertTimeFromUtc($utc, [System.TimeZoneInfo]::Local)).ToString("HH:mm")
}

function Set-QTask($name, $script, $ctTime, $taskArgs = "") {
    $local   = CTtoLocal $ctTime
    $argline = "`"$sd\$script`""
    if ($taskArgs) { $argline += " $taskArgs" }
    $action  = New-ScheduledTaskAction -Execute $py -Argument $argline -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $local
    $set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8)
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $set -Force | Out-Null
    Write-Output ("registered  {0,-26} {1} CT (= {2} local)  {3} {4}" -f $name, $ctTime, $local, $script, $taskArgs)
}

Set-QTask "MyQuant Dashboard"      "options_dashboard_live.py" "08:25" "--host 0.0.0.0 --port 8600"
Set-QTask "MyQuant Spot Feed"      "spot_feed.py"              "08:26"
Set-QTask "MyQuant Levels Fetch"   "mq_levels_fetch.py"        "08:27"
Set-QTask "MyQuant Gameplan"       "options_gameplan.py"       "08:28"
Set-QTask "MyQuant Trigger Daemon" "options_trigger_daemon.py" "08:33" "--until 15:00"
Set-QTask "MyQuant Gamma Scanner"  "options_gamma_scanner.py"  "08:35"
Set-QTask "MyQuant Health Check"   "options_healthcheck.py"    "08:40"
Set-QTask "MyQuant Marks Watch"    "options_mark.py"           "08:26" "--watch 120"
Set-QTask "MyQuant Postmortem"     "options_postmortem.py"     "15:15"
Set-QTask "MyQuant EOD Report"     "eod_report.py"             "15:20"

Write-Output ""
Write-Output "done. current MyQuant tasks:"
Get-ScheduledTask | Where-Object { $_.TaskName -like "MyQuant*" } |
    Select-Object TaskName, State | Format-Table -AutoSize
