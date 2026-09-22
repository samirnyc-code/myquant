"""activity_pings.py — phone pings for the day's ACTIVITY, not just its health.

Three streams the user asked for, each fired once per event (deduped, so nothing repeats):

  1. PROCESS RUNS   — every MyQuant scheduled task, when it newly completes, with its
                      exit result (0 = ok). Detected from LastRunTime deltas, so it needs
                      no change to the 22 individual scripts.
  2. SIM TRADES     — every new row in the trade log (entry) and every fill that closes
                      (exit), with structure / credit / P&L.
  3. EOD REPORT     — a one-message summary when the daily desk report lands.

Additive to alert_monitor (problems) and session_pings (milestones). Runs on the same
5-minute schedule.

    python scripts/activity_pings.py
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
STATE = ROOT / "data" / "_catalog" / "activity_pings_state.json"
NOWIN = 0x08000000

# friendly names + whether a run is worth a ping (skip the pure-plumbing ones that fire
# constantly, e.g. the watchdog every few minutes)
TASK_LABEL = {
    "MyQuant MQ Mine": "MQ full-surface mine",
    "MyQuant MQ Harvest": "MQ dashboard harvest",
    "MyQuant Levels DB": "Levels DB",
    "MyQuant Data Catalog Scan": "Data catalog scan",
    "MyQuant Gateway Login": "IB Gateway login",
    "MyQuant Gateway Ensure": "Gateway ensure (4002)",
    "MyQuant Dashboard": "Options desk server",
    "MyQuant Levels Fetch": "MQ levels fetch",
    "MyQuant Gameplan": "Premarket gameplan",
    "MyQuant Sim Daemon": "Sim daemon",
    "MyQuant Levels Engine": "Level-fade engine",
    "MyQuant Trigger Daemon": "Trigger daemon",
    "MyQuant Gamma Scanner": "Gamma scanner",
    "MyQuant Health Check": "Morning health check",
    "MyQuant Postmortem": "Daily postmortem",
    "MyQuant EOD Report": "EOD report",
    "MyQuant Levels History": "Levels history backfill",
    "MyQuant Backtest Levels": "Backtest-tile scrape",
    "MyQuant Depth Rollover": "Depth->parquet rollover",
    "MyQuant Pre-Open Verify": "Pre-open verify",
    # deliberately excluded (fire too often to be signal):
    #   Desk Watchdog / Desk Watchdog Live / Spot Feed / Marks Watch / Alert Monitor
}


def _load():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s))


def _task_runs():
    ps = ("Get-ScheduledTask | Where-Object {$_.TaskName -like 'MyQuant*'} | "
          "ForEach-Object { $i=$_|Get-ScheduledTaskInfo; [PSCustomObject]@{"
          "n=$_.TaskName; r=$i.LastTaskResult; "
          "l=(&{if($i.LastRunTime){$i.LastRunTime.ToString('o')}else{''}}) } } "
          "| ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                              "-WindowStyle", "Hidden", "-Command", ps],
                             capture_output=True, text=True, timeout=45,
                             creationflags=NOWIN).stdout.strip()
        rows = json.loads(out) if out else []
        return rows if isinstance(rows, list) else [rows]
    except Exception:
        return []


def check_tasks(tg, st):
    seen = st.setdefault("task_runs", {})
    for r in _task_runs():
        name, last, res = r.get("n"), r.get("l", ""), r.get("r")
        if name not in TASK_LABEL or not last:
            continue
        if seen.get(name) == last:      # same run as last time -> already pinged
            continue
        seen[name] = last
        # only ping runs we haven't seen AND that happened recently (avoid a burst of
        # historical "runs" on first ever execution)
        try:
            when = dt.datetime.fromisoformat(last)
            age_h = (dt.datetime.now(when.tzinfo) - when).total_seconds() / 3600
        except Exception:
            age_h = 0
        if age_h > 3:                   # stale record, don't ping - just remember it
            continue
        # "result 0" reads like failure to a human even though 0 = success. Say it plainly.
        ok = res in (0, 267009, 267011, 267014)
        if ok:
            tg.send(f"✅ {TASK_LABEL[name]} — completed OK", level="info")
        else:
            tg.send(f"⚠️ {TASK_LABEL[name]} — FAILED (exit code {res})", level="warn")


def check_trades(tg, st):
    import pandas as pd
    f = ROOT / "data" / "options_log" / "trades.parquet"
    if not f.exists():
        return
    try:
        d = pd.read_parquet(f)
    except Exception:
        return
    seen_entry = set(st.setdefault("trade_entry", []))
    seen_exit = set(st.setdefault("trade_exit", []))
    for _, r in d.iterrows():
        tid = str(r.get("trade_id"))
        if tid not in seen_entry:
            seen_entry.add(tid)
            # skip historical backfill on first run: only ping trades opened today
            edt = str(r.get("entry_dt", ""))
            if edt.startswith(dt.date.today().isoformat()):
                struct = r.get("structure", "?")
                credit = r.get("credit")
                cr = f"credit {credit:+.2f}" if credit == credit else ""
                tg.send(f"🟦 SIM ENTRY — {struct} ({tid}) {cr}", level="info")
        exited = str(r.get("exit_dt")) not in ("", "nan", "None", "NaT")
        if exited and tid not in seen_exit:
            seen_exit.add(tid)
            pnl = r.get("pnl")
            reason = r.get("close_reason", "")
            if pnl == pnl and str(r.get("exit_dt", "")).startswith(dt.date.today().isoformat()):
                emoji = "🟢" if pnl >= 0 else "🔴"
                tg.send(f"{emoji} SIM EXIT — {r.get('structure','?')} closed "
                        f"{pnl:+,.0f} ({reason}) [{tid}]",
                        level="ok" if pnl >= 0 else "warn")
    st["trade_entry"] = list(seen_entry)[-500:]
    st["trade_exit"] = list(seen_exit)[-500:]


def check_eod(tg, st):
    date = dt.date.today().strftime("%Y%m%d")
    f = ROOT / "data" / "options_sim" / f"eod_status_{date}.json"
    if not f.exists():
        return
    if st.get("eod_pinged") == date:
        return
    try:
        d = json.loads(f.read_text())
    except Exception:
        return
    st["eod_pinged"] = date
    summ = d.get("summary") or d.get("headline") or ""
    green = d.get("green"); total = d.get("total")
    counts = f" — {green}/{total} steps green" if green is not None else ""
    tg.send(f"📋 EOD desk report ready{counts}. {summ}".strip(), level="info")


def main() -> int:
    import notify_telegram as tg
    if not tg._load().get("token"):
        print("telegram not configured")
        return 2
    st = _load()
    for fn in (check_tasks, check_trades, check_eod):
        try:
            fn(tg, st)
        except Exception as e:
            print(f"{fn.__name__} error: {type(e).__name__}: {e}")
    _save(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
