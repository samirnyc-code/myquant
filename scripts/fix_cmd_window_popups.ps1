# Stop the MyQuant scheduled tasks from flashing a visible cmd.exe console window
# every time they fire (2026-10-28 — user flagged the popups interrupting other work).
#
# ROOT CAUSE: most MyQuant tasks already use pythonw.exe (Execute, windowless by design).
# 10 tasks instead call cmd.exe directly so they can use shell redirection (>> ... 2>&1)
# to tee output to a log file: Chain Recorder, Deadman 0832, Evening Brief, Gameplan Early,
# Gateway Login, Live Data Backup, Shadow Stop Monitor, TD Shadow Reprice, Tick Trove,
# Trigger Daemon. Task Scheduler always shows a console window for a direct cmd.exe action,
# regardless of "Hidden" task settings (that setting only affects the Task Scheduler UI
# listing, not the console).
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
    @{ Name = "MyQuant Trigger Daemon";       Bat = "trigger_daemon.bat";       WorkingDir = $repo }
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
