# Fixes for Thomas — 2026-11-05 (journal gap + screenshot reliability)

**Written:** 2026-11-05 (Samir's machine)
**For:** whichever Claude Code session Thomas opens on his own machine to apply this.
**Two independent fixes below.** Part 1 is in the `myquant` repo (Thomas has git access,
`tdeutschmann-byte`). Part 2 is in the `trade-playbook` repo, which **Thomas is NOT a git
collaborator on** — give him the file content directly (paste it in, or send the file),
don't tell him to `git pull` that repo.

---

## Part 1: Screenshot reliability fix (`myquant`, `ClaudeTrackerAddOn.cs`)

**Symptom on Thomas's machine:** screenshots only land roughly half the time.

**Root cause (verified by reading the code, not guessed):** `CaptureFromChartControl()`
calls `targetChart.GetScreenshot(ShareScreenshotType.Chart)` on the chart **window**, not on
the specific `ChartControl` that was matched/tagged. That call captures whatever **tab**
happens to be selected/visible in that window at the moment — it has no idea which
ChartControl was actually matched. Being tagged (`ClaudeTracker Chart Tag`) only proves the
right ChartControl exists somewhere in the window; it says nothing about whether its tab is
the one on screen right now. If Thomas is looking at a different tab (another instrument,
another timeframe) in the same chart window when a trade event fires, the old code silently
captured the wrong thing or got a blank render instead of failing loudly — consistent with an
intermittent, roughly-coin-flip miss rate.

**Fix:** before capturing, the code now finds the tagged chart's own tab in its window's tab
collection, force-selects it, captures, then restores whatever tab was previously showing —
so Thomas's screen isn't left on a different tab than he had open. Also logs a new warning if
it can't find the tab at all (previously silent).

### Steps

1. `git pull` in Thomas's `myquant` clone — confirm you land on commit
   `<FILL IN AFTER PUSH>` or later (commit message: "ClaudeTrackerAddOn: force-select the
   tagged chart's own tab before screenshot capture").
2. **Before copying, diff the new repo file against what's currently deployed** at
   `<Documents>\NinjaTrader 8\bin\Custom\AddOns\ClaudeTrackerAddOn.cs` — Thomas's deployed
   copy has HIS OWN per-machine consts near the top (`AccountName`, `SymbolName`,
   `TraderTag = "Thomas"`, `ExportRootFolder`). The repo copy carries Samir's values for
   those same 4 consts. **Do not blind-overwrite** — copy the new file in, then re-apply
   Thomas's 4 values on top (or patch just the `CaptureFromChartControl`/
   `FindTabItemForChartControl` methods by hand into his deployed copy if that's safer).
   Byte-diff after to confirm only the screenshot method changed plus his own 4 consts are
   intact.
3. **Tell Thomas to F5 when flat** (no open position) — needs a human in the NT8 UI.
4. This fix only helps if Thomas already completed the chart-tag step from the original
   setup (`docs/living/thomas_claudetracker_addon_setup.md` step 6 — dropping "ClaudeTracker
   Chart Tag" on his one real execution chart). If he never did that, screenshots still fall
   back to ambiguous window-title matching regardless of this fix — **check that first**
   (grep his NT8 log for `Screenshot saved (tagged chart)` vs `Screenshot saved:` with no
   "(tagged chart)" suffix, or a `tagged-chart registry AND live scan both found no` warning).
5. Verify: fire a Sim test trade, confirm `[ClaudeTrackerAddOn] Screenshot saved (tagged
   chart): ...` in his log, and open the resulting PNG to confirm it shows the right
   chart/tab.

---

## Part 2: Trade journal gap fix (`trade-playbook`, manual file copy — no git access)

**What happened on Samir's machine (same class of bug likely exists on Thomas's):**
`journal_uploader.py`'s scheduled task only triggers **at Windows logon**, retries 5 times
2 minutes apart on failure, then gives up until the next logon — no other supervision. It got
killed on Samir's machine 2026-10-30 and stayed dead for 6 days with nothing noticing.
Separately, `uploader_config.json`'s `"root"` value had been pointed at the wrong export
folder since Oct 1 (an old/retired path, not where `ClaudeTrackerAddOn.cs` actually writes) —
so even a perfectly running uploader would have found nothing new.

**Check both on Thomas's machine — do not assume either is fine without checking:**

1. **Config root mismatch** — read Thomas's own `scripts/uploader_config.json`'s `"root"`
   value, and compare it character-for-character against the `ExportRootFolder` const in
   his OWN deployed `ClaudeTrackerAddOn.cs` (`<Documents>\...\Custom\AddOns\`). They must be
   the exact same path. If they differ, his trades have likely never been reaching the
   journal at all — fix the config value to match.
2. **Is the uploader actually running right now** —
   `Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match 'journal_uploader' }`.
   If nothing, check his scheduled task (`Get-ScheduledTask` for whatever he named it —
   see his own `register_autostart.ps1` from the original Oct 14 bundle for the task name) —
   `Get-ScheduledTaskInfo` for `LastRunTime`/`LastTaskResult`. Start it with
   `Start-ScheduledTask -TaskName "<name>"` if it's not running.
3. **Install the watchdog** — new file, copy this exact content onto Thomas's machine as
   `uploader_watchdog.py` next to his `journal_uploader.py`:

   Full content: see `scripts/uploader_watchdog.py` in the `trade-playbook` repo on Samir's
   machine (commit `304ab73`, "Add watchdog for journal_uploader.py") — paste that file's
   contents directly since Thomas has no git access to this repo. Two things to adjust for
   his machine:
   - `TASK_NAME = "TradePlaybookUploader"` near the top — change to whatever his actual
     scheduled task is named if different.
   - Nothing else is machine-specific; `MYQUANT_SCRIPTS` points at the shared `notify.py`
     path and is best-effort (silently skipped if that path doesn't exist on his machine —
     check whether Thomas's `myquant` clone is at the same `C:\Users\Admin\myquant\scripts`
     path; if his Windows username differs, update that constant or just accept the
     best-effort skip).
4. **Register the recurring task** (adjust the python path and task name to match what's
   actually on his machine):

   ```powershell
   $action = New-ScheduledTaskAction -Execute "<path to his pythonw.exe>" -Argument '"<path to his trade-playbook>\scripts\uploader_watchdog.py"' -WorkingDirectory "<path to his trade-playbook>\scripts"
   $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
   $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
   $principal = New-ScheduledTaskPrincipal -UserId "<his Windows user>" -LogonType Interactive -RunLevel Limited
   Register-ScheduledTask -TaskName "MyQuant Trade Journal Uploader Watchdog" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Every 5 min: restarts journal_uploader.py if its process has died." -Force
   ```
5. Verify: `Get-ScheduledTask -TaskName "MyQuant Trade Journal Uploader Watchdog"` shows
   `Ready`/running, and `scripts/uploader_watchdog.log` (next to his `uploader_state.json`,
   under `%LOCALAPPDATA%\TradePlaybookJournal\`) shows `ok -- uploader alive` entries every
   ~5 min.

## If something looks wrong

Same standing instruction as the original setup doc: report back the exact log lines rather
than guessing at a fix blind.
