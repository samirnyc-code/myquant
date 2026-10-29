# Stop the MyQuant scheduled tasks from flashing a visible console window every time they
# fire (2026-10-28 — user flagged the popups interrupting other work; round 2 2026-10-29
# after the user reported popups continuing post-fix).
#
# ROUND 1 (2026-10-28) ROOT CAUSE: 10 tasks called cmd.exe directly (for shell redirection,
# >> ... 2>&1, to tee output to a log file): Chain Recorder, Deadman 0832, Evening Brief,
# Gameplan Early, Gateway Login, Live Data Backup, Shadow Stop Monitor, TD Shadow Reprice,
# Tick Trove, Trigger Daemon. Task Scheduler always shows a console for a direct cmd.exe
# action, regardless of "Hidden" task settings (that setting only affects the Task Scheduler
# UI listing, not the console).
#
# ROUND 2 (2026-10-29) ROOT CAUSE — a SECOND, distinct source, found after round 1's fix
# didn't stop all the popups: 14 more tasks use pythonw.exe (Execute, normally windowless)
# but their Arguments launch venv's CONSOLE python.exe (not pythonw.exe) as the actual
# payload via run_at_ct.py: Dashboard, Depth Rollover, EOD Report, Gameplan, Gateway Ensure,
# L1 Rollover, Levels Fetch, Marks Watch, NT8 Restart, Postmortem, Pre-Open Verify, Sim
# Daemon, Spot Feed, STMR Decision. On this machine `.venv\Scripts\python.exe` is itself a
# launcher that internally re-execs into a system-Python312 "worker" process (memory
# `daemon-is-a-process-pair`) — when that internal re-exec happens with NO console anywhere
# in its ancestry (pythonw.exe has none, and run_at_ct.py's own subprocess.run uses
# creationflags=CREATE_NO_WINDOW for its direct child), Windows must allocate a BRAND NEW
# console for the worker, which Windows 11's default-terminal-app handoff displays as a
# visible Windows Terminal window/tab — confirmed live (Sim Daemon's self-relaunch pair,
# PID 2640->12332, 2026-10-29 16:15) and reproduced + fixed in isolation (see session notes/
# handoff). Fix: route these 14 through the SAME hidden launcher as round 1 — once there's a
# real (if hidden) console anywhere in the chain, the venv-stub's internal self-relaunch just
# inherits it instead of needing a fresh allocation. Verified with a live test matching the
# exact bug shape: hidden cmd.exe -> venv python.exe -> self-relaunch -> system Python312 =
# zero new windows (vs the un-wrapped pythonw.exe path, which pops every time).
#
# (XSP-related tasks — Chain Recorder XSP, XSP Mirror, XSP Settle — were disabled and
# removed from this list 2026-10-28; XSP is a retired experiment, desk is SPX-only.)
#
# FIX: route these 12 through scripts\_sched\run_hidden.vbs (WScript.Shell.Run with window
# style 0), which launches a per-task .bat file (scripts\_sched\<slug>.bat, containing the
# exact same command the task ran before) with its console fully hidden. This stays in the
# normal interactive desktop session — unlike "run whether user is logged on or not" (Session
# 0), so GUI-dependent payloads (Gateway Login driving IBC/TWS Gateway) still work exactly as
# before; only the console chrome of the launcher itself is hidden. run_at_ct.py already
# launches its own payload with CREATE_NO_WINDOW (scripts\run_at_ct.py:99), so no other
# window was ever created beyond this top-level cmd.exe — hiding this one layer is sufficient.
#
# Each task's Trigger/Settings/Principal are left untouched — only the Action changes.
# WorkingDirectory is preserved from the original task (Gateway Login needs C:\IBC).
#
# Idempotent — safe to re-run. Run:  powershell -ExecutionPolicy Bypass -File scripts\fix_cmd_window_popups.ps1

$repo = "C:\Users\Admin\myquant"
$sched = "$repo\scripts\_sched"
$vbs = "$sched\run_hidden.vbs"
$wscript = "$env:WINDIR\System32\wscript.exe"

# name -> (bat file, working directory)
$tasks = @(
    @{ Name = "MyQuant Chain Recorder";       Bat = "chain_recorder.bat";       WorkingDir = $repo },
    @{ Name = "MyQuant Deadman 0832";         Bat = "deadman_0832.bat";         WorkingDir = $repo },
    @{ Name = "MyQuant Evening Brief";        Bat = "evening_brief.bat";        WorkingDir = $repo },
    @{ Name = "MyQuant Gameplan Early";       Bat = "gameplan_early.bat";       WorkingDir = $repo },
    @{ Name = "MyQuant Gateway Login";        Bat = "gateway_login.bat";        WorkingDir = "C:\IBC" },
    @{ Name = "MyQuant Live Data Backup";     Bat = "live_data_backup.bat";     WorkingDir = $null },
    @{ Name = "MyQuant Shadow Stop Monitor";  Bat = "shadow_stop_monitor.bat";  WorkingDir = $repo },
    @{ Name = "MyQuant TD Shadow Reprice";    Bat = "td_shadow_reprice.bat";    WorkingDir = $null },
    @{ Name = "MyQuant Tick Trove";           Bat = "tick_trove.bat";           WorkingDir = $repo },
    @{ Name = "MyQuant Trigger Daemon";       Bat = "trigger_daemon.bat";       WorkingDir = $repo },
    @{ Name = "MyQuant Dashboard";            Bat = "dashboard.bat";            WorkingDir = $repo },
    @{ Name = "MyQuant Depth Rollover";       Bat = "depth_rollover.bat";       WorkingDir = $repo },
    @{ Name = "MyQuant EOD Report";           Bat = "eod_report.bat";           WorkingDir = $repo },
    @{ Name = "MyQuant Gameplan";             Bat = "gameplan.bat";             WorkingDir = $repo },
    @{ Name = "MyQuant Gateway Ensure";       Bat = "gateway_ensure.bat";       WorkingDir = $repo },
    @{ Name = "MyQuant L1 Rollover";          Bat = "l1_rollover.bat";          WorkingDir = $repo },
    @{ Name = "MyQuant Levels Fetch";         Bat = "levels_fetch.bat";         WorkingDir = $repo },
    @{ Name = "MyQuant Marks Watch";          Bat = "marks_watch.bat";          WorkingDir = $repo },
    @{ Name = "MyQuant NT8 Restart";          Bat = "nt8_restart.bat";          WorkingDir = $repo },
    @{ Name = "MyQuant Postmortem";           Bat = "postmortem.bat";           WorkingDir = $repo },
    @{ Name = "MyQuant Pre-Open Verify";      Bat = "pre_open_verify.bat";      WorkingDir = $repo },
    @{ Name = "MyQuant Sim Daemon";           Bat = "sim_daemon.bat";           WorkingDir = $repo },
    @{ Name = "MyQuant Spot Feed";            Bat = "spot_feed.bat";            WorkingDir = $repo },
    @{ Name = "MyQuant STMR Decision";        Bat = "stmr_decision.bat";        WorkingDir = $repo }
)

foreach ($t in $tasks) {
    $batPath = "$sched\$($t.Bat)"
    if (-not (Test-Path $batPath)) {
        Write-Output ("SKIP  {0,-26} missing {1}" -f $t.Name, $batPath)
        continue
    }
    $argline = "`"$vbs`" `"$batPath`""
    if ($t.WorkingDir) {
        $action = New-ScheduledTaskAction -Execute $wscript -Argument $argline -WorkingDirectory $t.WorkingDir
    } else {
        $action = New-ScheduledTaskAction -Execute $wscript -Argument $argline
    }
    Set-ScheduledTask -TaskName $t.Name -Action $action | Out-Null
    Write-Output ("hidden-launcher  {0,-26} -> {1}" -f $t.Name, $t.Bat)
}

Write-Output "`ndone. Verify with:"
Write-Output "  Get-ScheduledTask | Where TaskName -like 'MyQuant*' | % { (`$_.Actions | select -First 1).Execute }"
