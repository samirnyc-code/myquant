# Duplicate-fire incident reconstruction — 2026-10-30

## Financial impact

- **actual_total_pnl**: -5829.32
- **single_run_baseline_pnl**: -2507.6
- **duplicate_rows_pnl**: -3321.72
- **cost_of_bug**: -3321.72
- **n_total_trades**: 27
- **n_duplicate_trades**: 17

## Watchdog hang/restart timeline (converted to CT)

- 08:40:20 CT  triggers: killing hung pair [6772, 2764, 11912, 9340]
- 08:40:21 CT  ACTION triggers: alive but heartbeat 603s stale (HUNG â€” open positions unmanaged) â€” restarting via 'MyQuant Trigger Daemon'
- 08:40:25 CT  triggers: killing hung pair [21572, 20616, 20796, 21080]
- 08:40:25 CT  ACTION triggers: alive but heartbeat 609s stale (HUNG â€” open positions unmanaged) â€” restarting via 'MyQuant Trigger Daemon'
- 08:46:35 CT  triggers: alive but heartbeat 363s stale (HUNG â€” open positions unmanaged) â€” in cooldown (371s), waiting
- 08:46:50 CT  triggers: alive but heartbeat 363s stale (HUNG â€” open positions unmanaged) â€” in cooldown (386s), waiting
- 08:47:06 CT  triggers: alive but heartbeat 363s stale (HUNG â€” open positions unmanaged) â€” in cooldown (402s), waiting
- 08:47:24 CT  triggers: alive but heartbeat 363s stale (HUNG â€” open positions unmanaged) â€” in cooldown (419s), waiting
- 08:47:42 CT  triggers: alive but heartbeat 430s stale (HUNG â€” open positions unmanaged) â€” in cooldown (438s), waiting
- 08:47:58 CT  triggers: alive but heartbeat 430s stale (HUNG â€” open positions unmanaged) â€” in cooldown (454s), waiting
- 08:48:14 CT  triggers: alive but heartbeat 430s stale (HUNG â€” open positions unmanaged) â€” in cooldown (469s), waiting
- 08:48:31 CT  triggers: alive but heartbeat 430s stale (HUNG â€” open positions unmanaged) â€” in cooldown (487s), waiting
- 08:48:50 CT  triggers: alive but heartbeat 498s stale (HUNG â€” open positions unmanaged) â€” in cooldown (506s), waiting
- 08:49:06 CT  triggers: alive but heartbeat 498s stale (HUNG â€” open positions unmanaged) â€” in cooldown (522s), waiting
- 08:49:22 CT  triggers: alive but heartbeat 498s stale (HUNG â€” open positions unmanaged) â€” in cooldown (537s), waiting
- 08:49:39 CT  triggers: alive but heartbeat 498s stale (HUNG â€” open positions unmanaged) â€” in cooldown (555s), waiting
- 08:49:58 CT  triggers: alive but heartbeat 565s stale (HUNG â€” open positions unmanaged) â€” in cooldown (573s), waiting
- 08:50:14 CT  triggers: alive but heartbeat 581s stale (HUNG â€” open positions unmanaged) â€” in cooldown (590s), waiting
- 08:50:14 CT  triggers: alive but heartbeat 565s stale (HUNG â€” open positions unmanaged) â€” in cooldown (590s), waiting
- 08:50:32 CT  triggers: killing hung pair [2040, 11936, 4160, 3628]
- 08:50:32 CT  ACTION triggers: alive but heartbeat 565s stale (HUNG â€” open positions unmanaged) â€” restarting via 'MyQuant Trigger Daemon'
- 08:56:48 CT  triggers: alive but heartbeat 368s stale (HUNG â€” open positions unmanaged) â€” in cooldown (376s), waiting
- 08:57:04 CT  triggers: alive but heartbeat 368s stale (HUNG â€” open positions unmanaged) â€” in cooldown (393s), waiting
- 08:57:21 CT  triggers: alive but heartbeat 368s stale (HUNG â€” open positions unmanaged) â€” in cooldown (409s), waiting
- 08:57:37 CT  triggers: alive but heartbeat 368s stale (HUNG â€” open positions unmanaged) â€” in cooldown (426s), waiting
- 08:58:02 CT  triggers: alive but heartbeat 440s stale (HUNG â€” open positions unmanaged) â€” in cooldown (450s), waiting
- 08:58:18 CT  triggers: alive but heartbeat 440s stale (HUNG â€” open positions unmanaged) â€” in cooldown (467s), waiting
- 08:58:35 CT  triggers: alive but heartbeat 440s stale (HUNG â€” open positions unmanaged) â€” in cooldown (483s), waiting
- 08:58:51 CT  triggers: alive but heartbeat 440s stale (HUNG â€” open positions unmanaged) â€” in cooldown (500s), waiting
- 08:59:13 CT  triggers: alive but heartbeat 513s stale (HUNG â€” open positions unmanaged) â€” in cooldown (521s), waiting
- 08:59:30 CT  triggers: alive but heartbeat 513s stale (HUNG â€” open positions unmanaged) â€” in cooldown (539s), waiting
- 08:59:46 CT  triggers: alive but heartbeat 513s stale (HUNG â€” open positions unmanaged) â€” in cooldown (555s), waiting
- 09:00:06 CT  triggers: alive but heartbeat 513s stale (HUNG â€” open positions unmanaged) â€” in cooldown (574s), waiting

## run_at_ct.py decisions around the restart window (today's tail)

- run_at_ct: target 08:29 CT | now 08:29 CT | delta +0min | berlin-chicago 7h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:29 CT | delta +0min | berlin-chicago 7h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:29 CT | delta +0min | berlin-chicago 7h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:40 CT | delta +11min | berlin-chicago 7h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:40 CT | delta +11min | berlin-chicago 7h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:29 CT | delta +0min | berlin-chicago 6h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:29 CT | delta +0min | berlin-chicago 6h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:29 CT | delta +0min | berlin-chicago 6h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 14:50 CT | delta +381min | berlin-chicago 6h | SKIP (other trigger owns this slot)
- run_at_ct: target 08:29 CT | now 08:29 CT | delta +0min | berlin-chicago 6h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 09:10 CT | delta +42min | berlin-chicago 6h | SKIP (other trigger owns this slot)
- run_at_ct: target 08:29 CT | now 09:20 CT | delta +52min | berlin-chicago 6h | SKIP (other trigger owns this slot)
- run_at_ct: target 08:29 CT | now 09:29 CT | delta +60min | berlin-chicago 6h | SKIP (other trigger owns this slot)
- run_at_ct: target 08:29 CT | now 09:30 CT | delta +62min | berlin-chicago 6h | SKIP (other trigger owns this slot)
- run_at_ct: target 08:29 CT | now 09:40 CT | delta +72min | berlin-chicago 6h | SKIP (other trigger owns this slot)
- run_at_ct: target 08:29 CT | now 09:51 CT | delta +82min | berlin-chicago 6h | SKIP (other trigger owns this slot)
- run_at_ct: target 08:29 CT | now 08:29 CT | delta +0min | berlin-chicago 6h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:40 CT | delta +11min | berlin-chicago 6h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:40 CT | delta +11min | berlin-chicago 6h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00
- run_at_ct: target 08:29 CT | now 08:50 CT | delta +22min | berlin-chicago 6h | RUN: C:\Users\Admin\myquant\.venv\Scripts\python.exe -u C:\Users\Admin\myquant\scripts\options_trigger_daemon.py --until 15:00

## Marks pipeline outage

- 10:54:07 CT  Desk watchdog	marks: marks.csv 313s â€” restarting via 'MyQuant Marks Watch'
- 11:35:09 CT  Desk watchdog	marks: marks.csv 2772s â€” RESTART CAP HIT (5/day), manual fix needed
- 15:09:51 CT  Desk watchdog	marks: marks.csv 15659s â€” RESTART CAP HIT (5/day), manual fix needed

## Why the daemon hung (sourced from desk_watchdog.py's own comment)

- `scripts/desk_watchdog.py:66-68`: `trig_hb` staleness threshold (360s slow / 300s fast) was tuned around a KNOWN, already-seen false-positive: `manage_open()` blocks ~2-3min quoting every leg of every open position sequentially, and on 2026-09-17 this alone pushed heartbeat staleness to 191s during the 14:45 EOD close burst. The thresholds were widened to tolerate that burst, but only the EOD-side burst was named in the comment.
- This morning's **entry** burst (10 fresh combo fills in a 9-minute span, 08:31-08:39 CT) is the same shape of event on the open side: each fill becomes immediately eligible for `manage_open`'s exit-check 60s later, so the same sequential-leg-quoting block likely pushed heartbeat staleness past the 360s threshold -- not a crash, a legitimate-but-slow loop getting misread as HUNG. Not proven for this exact morning (no captured stdout for the killed PIDs), but it is the documented mechanism for this exact symptom and fits the timing.

## Per-trade detail
See `data\options_log\_analysis\duplicate_fire_20261030.csv`.
