# Register the daily options-desk Task Scheduler jobs (S75).
# Idempotent — safe to re-run; -Force overwrites the same-named task.
# Runs as the current user, only when logged on (IB Gateway needs the session).
#
# Daily loop:
#   09:28  Gameplan       -> gameplan_YYYYMMDD.json (premarket plan from EOD levels)
#   09:28  Spot Feed      -> live.json + underlying tape, runs until ~16:20
#   09:33  Trigger Daemon -> auto-executes triggers on their condition until 16:00
#   15:28  Sim Daemon     -> (existing) the 15:59 STMR BPS decision
#   15:35  Marks Watch    -> (existing) marks open positions
#   16:15  Postmortem     -> postmortem_YYYYMMDD.json (plan vs actual, observe-only)
#
# NOTE: this reschedules "MyQuant Spot Feed" to 09:28 (all-day) so the trigger
# daemon has live spot from the open; the same feed covers the 15:59 BPS window.
# Prereq each morning: IB Gateway logged in (paper 4002).
#
# Run:  powershell -ExecutionPolicy Bypass -File scripts\schedule_options_tasks.ps1

$repo = "C:\Users\Admin\myquant"
$py   = "$repo\.venv\Scripts\python.exe"
$sd   = "$repo\scripts"

# Times below are given in MARKET time (US Eastern). Task Scheduler fires in the
# machine's LOCAL time, so convert ET wall-clock -> local wall-clock (DST-aware).
$etz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
function ETtoLocal($etTime) {
    $today = (Get-Date).ToString('yyyy-MM-dd')
    $etDt  = [datetime]::ParseExact("$today $etTime", "yyyy-MM-dd HH:mm", $null)
    $utc   = [System.TimeZoneInfo]::ConvertTimeToUtc($etDt, $etz)
    ([System.TimeZoneInfo]::ConvertTimeFromUtc($utc, [System.TimeZoneInfo]::Local)).ToString("HH:mm")
}

function Set-QTask($name, $script, $etTime, $taskArgs = "") {
    $local   = ETtoLocal $etTime
    $argline = "`"$sd\$script`""
    if ($taskArgs) { $argline += " $taskArgs" }
    $action  = New-ScheduledTaskAction -Execute $py -Argument $argline -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Daily -At $local
    $set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8)
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $set -Force | Out-Null
    Write-Output ("registered  {0,-26} {1} ET (= {2} local)  {3} {4}" -f $name, $etTime, $local, $script, $taskArgs)
}

Set-QTask "MyQuant Gameplan"       "options_gameplan.py"       "09:28"
Set-QTask "MyQuant Spot Feed"      "spot_feed.py"              "09:26"
Set-QTask "MyQuant Trigger Daemon" "options_trigger_daemon.py" "09:33" "--until 16:00"
Set-QTask "MyQuant Postmortem"     "options_postmortem.py"     "16:15"

Write-Output ""
Write-Output "done. current MyQuant tasks:"
Get-ScheduledTask | Where-Object { $_.TaskName -like "MyQuant*" } |
    Select-Object TaskName, State | Format-Table -AutoSize
