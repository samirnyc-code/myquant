# Register the daily options-desk Task Scheduler jobs (S75).
# Idempotent — safe to re-run; -Force overwrites the same-named task.
# Runs as the current user, only when logged on (IB Gateway needs the session).
#
# Daily loop:
#   08:28  Gameplan       -> gameplan_YYYYMMDD.json (premarket plan from EOD levels)
#   08:26  Spot Feed      -> live.json + underlying tape, runs until ~16:20
#   08:29  Trigger Daemon -> auto-executes triggers on their condition until 16:00
#   14:28  Sim Daemon     -> (existing) the 15:59 STMR BPS decision
#   14:35  Marks Watch    -> (existing) marks open positions
#   15:15  Postmortem     -> postmortem_YYYYMMDD.json (plan vs actual, observe-only)
#
# NOTE: this reschedules "MyQuant Spot Feed" to 08:26 (all-day) so the trigger
# daemon has live spot from the open; the same feed covers the 15:59 BPS window.
# Prereq each morning: IB Gateway logged in (paper 4002).
#
# UPDATED 2026-10-25: this file had drifted from what's actually registered live (someone
# had hand-edited the real tasks to add run_at_ct.py + dual triggers without updating this
# script — found while investigating the Germany DST clock change). Re-running the OLD
# version of this file would have silently clobbered that fix back to a single, DST-unsafe
# trigger per task. Set-QTask now always registers the same dual-trigger + run_at_ct.py
# pattern as scripts/fix_dst_dual_triggers.ps1 (CT-target+6h and CT-target+7h, 1h apart,
# bracketing the twice-a-year EU/US DST mismatch — see that script's header for the full
# explanation). Re-running this file is now safe and reproduces the live DST-safe state.
#
# NOT reconciled here (left as-is, flagged only): "MyQuant Gameplan" below is a DIFFERENT,
# currently-Disabled task from the live "MyQuant Gameplan Early" (different args/log file) —
# this script does not know which one is the real current intent, so it still registers the
# old "Gameplan" name rather than guessing a merge. Likewise Levels Fetch / Gamma Scanner /
# Health Check / MQ Mine are currently Disabled live; registering (Force) will re-create them
# ENABLED — check live state before re-running this script if that's not what you want.
#
# Run:  powershell -ExecutionPolicy Bypass -File scripts\schedule_options_tasks.ps1

$repo = "C:\Users\Admin\myquant"
$py   = "$repo\.venv\Scripts\python.exe"
$pyw  = "$repo\.venv\Scripts\pythonw.exe"
$sd   = "$repo\scripts"
$runAtCt = "$sd\run_at_ct.py"

# Dual-trigger, DST-safe: CT-target+6h lands correctly during the ~1wk Oct/Nov + ~3wk March
# EU/US DST-mismatch windows, CT-target+7h lands correctly the rest of the year. Anchor on
# TODAY (not a past/future date — both can bake in the wrong UTC offset or suppress near-term
# occurrences; see scripts/fix_dst_dual_triggers.ps1 for the two ways this went wrong live).
$anchor = (Get-Date).ToString("yyyy-MM-dd")
function CtPlusHours($ctTime, $hours) {
    $hh, $mm = $ctTime.Split(":")
    ([datetime]"$anchor $hh`:$mm").AddHours($hours).ToString("HH:mm")
}

function Set-QTask($name, $script, $ctTime, $taskArgs = "") {
    $at6 = CtPlusHours $ctTime 6
    $at7 = CtPlusHours $ctTime 7
    $argline = "`"$runAtCt`" --at $ctTime -- `"$py`" `"$sd\$script`""
    if ($taskArgs) { $argline += " $taskArgs" }
    $action  = New-ScheduledTaskAction -Execute $pyw -Argument $argline -WorkingDirectory $repo
    $t1      = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At ([datetime]"$anchor $at6")
    $t2      = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At ([datetime]"$anchor $at7")
    $set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8)
    Register-ScheduledTask -TaskName $name -Action $action -Trigger @($t1, $t2) -Settings $set -Force | Out-Null
    Write-Output ("registered  {0,-26} {1} CT (triggers {2} / {3})  {4} {5}" -f $name, $ctTime, $at6, $at7, $script, $taskArgs)
}

Set-QTask "MyQuant Dashboard"      "options_dashboard_live.py" "08:25" "--host 0.0.0.0 --port 8600"
Set-QTask "MyQuant Spot Feed"      "spot_feed.py"              "08:26"
Set-QTask "MyQuant Levels Fetch"   "mq_levels_fetch.py"        "08:27"
Set-QTask "MyQuant Gameplan"       "options_gameplan.py"       "08:28"
Set-QTask "MyQuant Trigger Daemon" "options_trigger_daemon.py" "08:29" "--until 15:00"
Set-QTask "MyQuant Chain Recorder" "options_chain_recorder.py" "08:25" "--stop 15:05"
Set-QTask "MyQuant Evening Brief" "gexlog_evening.py" "19:05"
Set-QTask "MyQuant Gamma Scanner"  "options_gamma_scanner.py"  "08:35"
Set-QTask "MyQuant Health Check"   "options_healthcheck.py"    "08:40"
Set-QTask "MyQuant Marks Watch"    "options_mark.py"           "08:26" "--watch 120"
Set-QTask "MyQuant MQ Mine"        "mq_mine.py"                "07:30"
Set-QTask "MyQuant Postmortem"     "options_postmortem.py"     "15:15"
Set-QTask "MyQuant EOD Report"     "eod_report.py"             "15:20"

Write-Output ""
Write-Output "done. current MyQuant tasks:"
Get-ScheduledTask | Where-Object { $_.TaskName -like "MyQuant*" } |
    Select-Object TaskName, State | Format-Table -AutoSize
