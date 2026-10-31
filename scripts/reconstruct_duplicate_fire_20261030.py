"""Reconstruct the 2026-10-30 duplicate-fire incident on the options trigger daemon.

What happened: the trigger daemon's heartbeat went stale 3x between 08:40-08:50 CT
this morning (desk_watchdog.py's hang detector), each time triggering a kill+restart
via the 'MyQuant Trigger Daemon' scheduled task. Each restart landed inside
run_at_ct.py's +-25min "on time" window around the 08:29 CT target, so it was NOT
treated as the redundant DST dual-trigger and genuinely relaunched
options_trigger_daemon.py. Each fresh instance reloaded gameplan_20261030.json and
re-fired every trigger it still saw as not-yet-fired -> 8 of 10 setups fired 3x, one
fired 2x, one fired cleanly once. 27 trades logged for an intended 10.

This script pulls the primary sources (trades.parquet, desk_watchdog.log,
trigger_daemon_sched.log, notifications.log) and writes a dated, annotated CSV +
markdown summary — the persisted record for the incident writeup in
docs/living/duplicate_fire_incident_20261030.md.

Run: .venv/Scripts/python.exe scripts/reconstruct_duplicate_fire_20261030.py
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATE = "20261030"
DATE_ISO = "2026-10-30"
OUT_DIR = ROOT / "data" / "options_log" / "_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_day_trades() -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    df["entry_dt"] = pd.to_datetime(df["entry_dt"])
    day = df[df["entry_dt"].dt.date.astype(str) == DATE_ISO].copy()
    day = day.sort_values("entry_dt").reset_index(drop=True)
    # wave = which fire-cycle this copy belongs to, per strategy_id, in entry order
    day["wave"] = day.groupby("strategy_id").cumcount() + 1
    day["is_duplicate"] = day["wave"] > 1
    return day


def grep_log(path: Path, needle: str) -> list[str]:
    if not path.exists():
        return []
    return [ln.rstrip("\n") for ln in path.read_text(errors="replace").splitlines()
            if needle in ln and DATE_ISO in ln]


def watchdog_timeline() -> list[str]:
    """desk_watchdog.py's log() stamps with now() = dt.datetime.now(CT) (its own source,
    line 76-77) -- already Chicago time, no conversion needed."""
    lines = grep_log(ROOT / "data" / "_catalog" / "logs" / "desk_watchdog.log", "triggers:")
    out = []
    for ln in lines:
        m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) (.*)", ln)
        if not m:
            continue
        _, tstr, rest = m.groups()
        out.append(f"{tstr} CT  {rest}")
    return out


def sched_log_runs() -> list[str]:
    path = ROOT / "data" / "options_sim" / "trigger_daemon_sched.log"
    if not path.exists():
        return []
    # this file has no date column; it's a rolling tail, so just grab RUN/SKIP lines
    return [ln for ln in path.read_text(errors="replace").splitlines() if "RUN" in ln or "SKIP" in ln]


def marks_outage_timeline() -> list[str]:
    """notifications.log uses notify.py's own timestamp, which is machine-local
    (Berlin) time, NOT CT -- confirmed by cross-referencing the same restart event
    against desk_watchdog.log (CT): 2026-10-30 14:40:21 here == 08:40:20 CT there,
    a 6h offset (this week's DST-mismatch offset). Convert for the report."""
    lines = grep_log(ROOT / "data" / "options_log" / "notifications.log", "marks:")
    out = []
    for ln in lines:
        m = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\t(.*)", ln)
        if not m:
            out.append(ln)
            continue
        _, tstr, rest = m.groups()
        berlin = dt.datetime.strptime(f"{DATE_ISO} {tstr}", "%Y-%m-%d %H:%M:%S")
        ct = berlin - dt.timedelta(hours=6)
        out.append(f"{ct:%H:%M:%S} CT  {rest}")
    first = out[0] if out else None
    cap_hit = next((ln for ln in out if "RESTART CAP HIT" in ln), None)
    last = out[-1] if out else None
    return [x for x in (first, cap_hit, last) if x]


def financial_impact(day: pd.DataFrame) -> dict:
    actual_total = round(day["pnl"].sum(), 2)
    # baseline = first fire of each strategy_id (what SHOULD have been the only trade)
    baseline = day[day["wave"] == 1]
    baseline_total = round(baseline["pnl"].sum(), 2)
    dup_rows = day[day["is_duplicate"]]
    dup_total = round(dup_rows["pnl"].sum(), 2)
    return {
        "actual_total_pnl": actual_total,
        "single_run_baseline_pnl": baseline_total,
        "duplicate_rows_pnl": dup_total,
        "cost_of_bug": round(actual_total - baseline_total, 2),
        "n_total_trades": len(day),
        "n_duplicate_trades": int(day["is_duplicate"].sum()),
    }


def main():
    day = load_day_trades()
    csv_path = OUT_DIR / f"duplicate_fire_{DATE}.csv"
    day.to_csv(csv_path, index=False)

    impact = financial_impact(day)
    wd_lines = watchdog_timeline()
    sched_lines = sched_log_runs()
    marks_lines = marks_outage_timeline()

    report = []
    report.append(f"# Duplicate-fire incident reconstruction — {DATE_ISO}\n")
    report.append("## Financial impact\n")
    for k, v in impact.items():
        report.append(f"- **{k}**: {v}")
    report.append("\n## Watchdog hang/restart timeline (converted to CT)\n")
    report.extend(f"- {ln}" for ln in wd_lines)
    report.append("\n## run_at_ct.py decisions around the restart window (today's tail)\n")
    report.extend(f"- {ln}" for ln in sched_lines[-20:])
    report.append("\n## Marks pipeline outage\n")
    report.extend(f"- {ln}" for ln in marks_lines)
    report.append("\n## Why the daemon hung (sourced from desk_watchdog.py's own comment)\n")
    report.append(
        "- `scripts/desk_watchdog.py:66-68`: `trig_hb` staleness threshold (360s slow / "
        "300s fast) was tuned around a KNOWN, already-seen false-positive: `manage_open()` "
        "blocks ~2-3min quoting every leg of every open position sequentially, and on "
        "2026-09-17 this alone pushed heartbeat staleness to 191s during the 14:45 EOD "
        "close burst. The thresholds were widened to tolerate that burst, but only the "
        "EOD-side burst was named in the comment."
    )
    report.append(
        "- This morning's **entry** burst (10 fresh combo fills in a 9-minute span, "
        "08:31-08:39 CT) is the same shape of event on the open side: each fill becomes "
        "immediately eligible for `manage_open`'s exit-check 60s later, so the same "
        "sequential-leg-quoting block likely pushed heartbeat staleness past the 360s "
        "threshold -- not a crash, a legitimate-but-slow loop getting misread as HUNG. "
        "Not proven for this exact morning (no captured stdout for the killed PIDs), but "
        "it is the documented mechanism for this exact symptom and fits the timing."
    )
    report.append(f"\n## Per-trade detail\nSee `{csv_path.relative_to(ROOT)}`.\n")

    md_path = OUT_DIR / f"duplicate_fire_{DATE}_summary.md"
    md_path.write_text("\n".join(report), encoding="utf-8")

    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    print()
    print("\n".join(report))


if __name__ == "__main__":
    main()
