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
#
# UPDATED 2026-10-25: Login and Ensure below had drifted from live — Login had no run_at_ct.py
# guard at all and was already 30min off (found while investigating the Germany DST clock
# change); Ensure's live dual-trigger had its second trigger on the wrong side. Both now use
# two triggers (CT-target+6h and CT-target+7h, 1h apart) wrapping the same run_at_ct.py guard,
# matching scripts/fix_dst_dual_triggers.ps1 — re-running this file now reproduces that fix
# instead of clobbering it back to a single DST-unsafe trigger. Watchdog is left as a single
# trigger (its own internal 05:30-08:25 CT window guard makes the exact fire time forgiving)
# and is currently Disabled live — not touched/verified further here.
#
# Run:  powershell -ExecutionPolicy Bypass -File scripts\schedule_gateway_login.ps1

$py   = "C:\Users\Admin\myquant\.venv\Scripts\python.exe"
$pyw  = "C:\Users\Admin\myquant\.venv\Scripts\pythonw.exe"
$runAtCt = "C:\Users\Admin\myquant\scripts\run_at_ct.py"
$set  = New-ScheduledTaskSettingsSet -StartWhenAvailable
$days = 'Monday','Tuesday','Wednesday','Thursday','Friday'

# Anchor on TODAY — a past/future anchor can bake in the wrong UTC offset or suppress
# near-term occurrences (both hit live; see scripts/fix_dst_dual_triggers.ps1).
$anchor = (Get-Date).ToString("yyyy-MM-dd")
function CtPlusHours($ctTime, $hours) {
    $hh, $mm = $ctTime.Split(":")
    ([datetime]"$anchor $hh`:$mm").AddHours($hours).ToString("HH:mm")
}

# 1) Gateway Login — 05:30 CT, dual-trigger + run_at_ct guard (DST-robust, see header above).
#    The action tees a log to gateway_login_sched.log. StartGateway.bat self-guards double-launch.
$at6 = CtPlusHours "05:30" 6
$at7 = CtPlusHours "05:30" 7
$loginArgs  = '/c ""' + $py + '" -u "' + $runAtCt + '" --at 05:30 -- cmd.exe /c C:\IBC\StartGateway.bat /INLINE >> "C:\Users\Admin\myquant\data\options_sim\gateway_login_sched.log" 2>&1"'
$aLogin = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $loginArgs -WorkingDirectory "C:\IBC"
$t1Login = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At ([datetime]"$anchor $at6")
$t2Login = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At ([datetime]"$anchor $at7")
Register-ScheduledTask -TaskName "MyQuant Gateway Login" -Action $aLogin -Trigger @($t1Login, $t2Login) -Settings $set -Force | Out-Null
Write-Output ("registered  MyQuant Gateway Login     Mon-Fri 05:30 CT (triggers {0} / {1})" -f $at6, $at7)

# 2) Gateway Watchdog — resident from 05:30 CT. Its internal window guard (05:30-08:25 CT)
#    makes the single trigger DST-safe; it exits the moment the gateway is truly ready.
#    (Currently Disabled live — Register-ScheduledTask -Force will re-enable it if re-run.)
$wdLocal = CtPlusHours "05:30" 7
$aWd = New-ScheduledTaskAction -Execute $pyw -Argument "scripts\gateway_watchdog.py" -WorkingDirectory "C:\Users\Admin\myquant"
$tWd = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At ([datetime]"$anchor $wdLocal")
Register-ScheduledTask -TaskName "MyQuant Gateway Watchdog" -Action $aWd -Trigger $tWd -Settings $set -Force | Out-Null
Write-Output ("registered  MyQuant Gateway Watchdog   Mon-Fri 05:30 CT (= {0} local)" -f $wdLocal)

# 3) Gateway Ensure — 08:20 CT light backstop (idempotent: no-op if 4002 up, else bring up).
#    Dual-trigger + run_at_ct guard so the exact backstop time is also DST-robust.
$ensAt6 = CtPlusHours "08:20" 6
$ensAt7 = CtPlusHours "08:20" 7
$ensArgline = "`"$runAtCt`" --at 08:20 -- `"$py`" scripts\gateway_ensure.py"
$actEns   = New-ScheduledTaskAction -Execute $pyw -Argument $ensArgline -WorkingDirectory "C:\Users\Admin\myquant"
$t1Ens  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At ([datetime]"$anchor $ensAt6")
$t2Ens  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At ([datetime]"$anchor $ensAt7")
Register-ScheduledTask -TaskName "MyQuant Gateway Ensure" -Action $actEns -Trigger @($t1Ens, $t2Ens) -Settings $set -Force | Out-Null
Write-Output ("registered  MyQuant Gateway Ensure     Mon-Fri 08:20 CT (triggers {0} / {1})" -f $ensAt6, $ensAt7)

Write-Output "`nNOTE: root-cause fix lives in C:\IBC\config.ini (outside repo): AutoRestartTime=02:00"
Write-Output ("next Login run: {0}" -f (Get-ScheduledTaskInfo -TaskName 'MyQuant Gateway Login').NextRunTime)
