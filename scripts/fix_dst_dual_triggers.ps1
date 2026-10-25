# Fix the Berlin/Chicago DST-mismatch exposure found 2026-10-25 (the day Germany's clocks
# changed, one week before US DST ends Nov 1 2026).
#
# BACKGROUND (see scripts/run_at_ct.py and docs/living/handoff.md S122):
#   Every MyQuant task is scheduled as a FIXED Berlin local wall-clock time, picked so it
#   lands on the intended America/Chicago (CT) time. Berlin-Chicago is 7h apart almost all
#   year, but drops to 6h for ~1 week each Oct/Nov and ~3 weeks each March, because EU and
#   US flip DST on different Sundays. A task pinned to ONE Berlin trigger time is correct
#   for only one of those two offsets and silently fires an hour off (or, if wrapped in
#   run_at_ct.py with its +-25min window, silently no-ops) during the other.
#
# WHAT WAS WRONG (verified by reading the raw trigger XML via `schtasks /query /xml`):
#   - MyQuant Dashboard / Gateway Ensure / L1 Rollover already had TWO triggers, but the
#     second one was 1h EARLIER than the primary (e.g. Dashboard: 14:25 and 13:25 Berlin).
#     13:25 Berlin never maps onto 08:25 CT at any real offset (would need offset=5, which
#     never occurs) -- that second trigger was dead weight, not a DST fix.
#   - Chain Recorder, Deadman 0832, Evening Brief, Gameplan Early, Trigger Daemon, Shadow
#     Stop Monitor had only ONE trigger (correct for the current 6h-offset week, wrong by
#     1h from Nov 2 2026 onward once US DST ends and the offset reverts to 7h) -- these will
#     silently SKIP every day via run_at_ct.py's window once that happens.
#   - EOD Report, Postmortem, Spot Feed, Marks Watch had only ONE trigger AND no run_at_ct.py
#     guard at all -- from Nov 2 onward these will just RUN an hour early with zero protection.
#
# THE FIX: every task gets exactly two triggers, 1h apart, bracketing both possible offsets
# (CT target + 6h) and (CT target + 7h). Whichever one lands on the correct CT time runs
# (via run_at_ct.py's own window check); the other is a no-op. This is permanent -- it never
# needs touching again for this twice-a-year mismatch.
#
# Idempotent -- safe to re-run. Run:  powershell -ExecutionPolicy Bypass -File scripts\fix_dst_dual_triggers.ps1

$repo = "C:\Users\Admin\myquant"
$py   = "$repo\.venv\Scripts\python.exe"
$pyw  = "$repo\.venv\Scripts\pythonw.exe"
$runAtCt = "$repo\scripts\run_at_ct.py"

function Set-TwoTriggers($name, $at6, $at7, $days) {
    $t1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $at6
    $t2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $at7
    Set-ScheduledTask -TaskName $name -Trigger @($t1, $t2) | Out-Null
    Write-Output ("fixed triggers   {0,-28} {1} / {2}" -f $name, $at6, $at7)
}

function Set-ActionAndTriggers($name, $ctTime, $payloadExe, $payloadArgs, $at6, $at7, $days, $useWindow) {
    $argline = "`"$runAtCt`" --at $ctTime"
    if ($useWindow) { $argline += " --window $useWindow" }
    $argline += " -- `"$payloadExe`" $payloadArgs"
    $action = New-ScheduledTaskAction -Execute $pyw -Argument $argline -WorkingDirectory $repo
    $t1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $at6
    $t2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $at7
    Set-ScheduledTask -TaskName $name -Action $action -Trigger @($t1, $t2) | Out-Null
    Write-Output ("wrapped+fixed    {0,-28} {1} / {2}  (run_at_ct --at {3})" -f $name, $at6, $at7, $ctTime)
}

$weekdays = 'Monday','Tuesday','Wednesday','Thursday','Friday'

# --- group 1: dual-trigger tasks that had the second trigger on the WRONG side ---
Set-TwoTriggers "MyQuant Dashboard"      "14:25" "15:25" $weekdays
Set-TwoTriggers "MyQuant Gateway Ensure" "14:20" "15:20" $weekdays
Set-TwoTriggers "MyQuant L1 Rollover"    "22:05" "23:05" @('Sunday','Monday','Tuesday','Wednesday','Thursday')

# --- group 2: single-trigger, already run_at_ct-wrapped -- just add the missing second trigger ---
Set-TwoTriggers "MyQuant Chain Recorder"      "14:25" "15:25" $weekdays
Set-TwoTriggers "MyQuant Deadman 0832"        "14:32" "15:32" $weekdays
Set-TwoTriggers "MyQuant Evening Brief"       "01:05" "02:05" @('Tuesday','Wednesday','Thursday','Friday','Saturday')
Set-TwoTriggers "MyQuant Gameplan Early"      "13:05" "14:05" $weekdays
Set-TwoTriggers "MyQuant Trigger Daemon"      "14:29" "15:29" $weekdays
Set-TwoTriggers "MyQuant Shadow Stop Monitor" "14:35" "15:35" $weekdays

# --- group 3: single-trigger, NO run_at_ct guard -- wrap the action AND add the second trigger ---
Set-ActionAndTriggers "MyQuant EOD Report"  "15:20" $py  "`"$repo\scripts\eod_report.py`""        "21:20" "22:20" $weekdays
Set-ActionAndTriggers "MyQuant Postmortem"  "15:15" $py  "`"$repo\scripts\options_postmortem.py`"" "21:15" "22:15" $weekdays
Set-ActionAndTriggers "MyQuant Spot Feed"   "08:26" $py  "`"$repo\scripts\spot_feed.py`""          "14:26" "15:26" $weekdays
Set-ActionAndTriggers "MyQuant Marks Watch" "08:26" $py  "`"$repo\scripts\options_mark.py`" --watch 120" "14:26" "15:26" $weekdays

Write-Output "`ndone. Verify with:"
Write-Output "  schtasks /query /tn `"MyQuant Dashboard`" /xml   (should show 2 CalendarTriggers, 1h apart)"
