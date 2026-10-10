"""recover_oct2026_real_trades.py — S134 incident recovery, v2 (supersedes
recover_oct2026_calendar_gap.py, which wrongly used the reconstructed_days.json
"desk was down" overlay for REAL trades — user correctly rejected that: these
are not reconstructed/simulated days, they're real executed trades whose
trades.parquet rows were destroyed by the 2026-10-09 git-revert incident.

This writes REAL rows into trades.parquet (not the recon overlay), rebuilt from:
  - data/options_sim/gameplan_<date>.json   — the exact legs/strikes used that day
  - data/options_sim/postmortem_<date>.json — credit/pnl/grade/outcome per trigger,
    captured live the same evening, before the loss (authoritative P&L source)

What's exactly recoverable vs approximated, per trade:
  - EOD-settled triggers (in postmortem's settled_0dte list): trade_id AND entry
    time come straight from the trade_id itself (auto_YYYYMMDD_HHMMSS, preserved
    verbatim in the archive) — exact. exit_dt = that day 16:00 (cash-settle time,
    per options_postmortem.settle_0dte). credit/pnl exact from the archive.
  - Intraday-stopped triggers (not in settled_0dte — closed same-day via the
    level-accept stop monitor): credit/pnl/grade/outcome are exact (from
    postmortem), but the precise entry/exit CLOCK TIME was never archived
    anywhere (notifications.log has no rows for these 5 dates either — also
    wiped). Entry/exit times are approximated from this desk's typical same-day
    pattern (entries ~08:32-08:38 CT, intraday stops ~08:45-09:15 CT) and each
    such row is flagged in entry_note so it's never confused with a precision
    timestamp.

Run:  .venv/Scripts/python.exe scripts/recover_oct2026_real_trades.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "data" / "options_sim"

DATES = ["2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]
FEE = 1.63
EOD_FALLBACK_ENTRY = {"eod": "08:32", "open": "08:35", "gx": "08:37"}
STOP_FALLBACK_EXIT = "09:05"  # representative — see docstring; real clock time not recoverable


def entry_bucket(tid: str) -> str:
    if tid.startswith("eod"):
        return "eod"
    if tid.startswith("open"):
        return "open"
    return "gx"


def build_rows(date_iso: str):
    d8 = date_iso.replace("-", "")
    gp_path = SIM / f"gameplan_{d8}.json"
    pm_path = SIM / f"postmortem_{d8}.json"
    if not gp_path.exists() or not pm_path.exists():
        print(f"  ! missing gameplan or postmortem for {date_iso} — skipping")
        return []

    gp = json.loads(gp_path.read_text(encoding="utf-8"))
    pm = json.loads(pm_path.read_text(encoding="utf-8"))

    legs_by_id = {}
    for tr in gp.get("triggers", []):
        s = tr.get("structure", {})
        if s.get("kind") == "vertical" and s.get("short") and s.get("long"):
            legs_by_id[tr["id"]] = (s["right"], float(s["short"]), float(s["long"]))

    settled_by_pnl = {}
    for s in pm.get("settled_0dte", []):
        settled_by_pnl.setdefault(round(s["pnl"]), []).append(s["trade_id"])

    rows = []
    for t in pm.get("triggers", []):
        tid_setup = t["id"]
        if not t.get("fired") or t.get("pnl") is None or tid_setup not in legs_by_id:
            continue
        right, short, long_ = legs_by_id[tid_setup]
        credit = float(t["credit"])
        pnl = float(t["pnl"])
        width = abs(short - long_)
        collateral = round((width - credit) * 100)

        cands = settled_by_pnl.get(round(pnl), [])
        matched_tid = cands.pop(0) if cands else None

        if matched_tid:
            hhmmss = matched_tid.split("_")[-1]
            entry_dt = f"{date_iso} {hhmmss[:2]}:{hhmmss[2:4]}"
            exit_dt = f"{date_iso} 16:00"
            fill_model, close_reason = "cash_settle", "expired"
            fees = len(["s", "l"]) * 1 * FEE  # 2 legs, 1 qty — matches settle_0dte's formula
            trade_id = matched_tid
            note = "RECOVERED (S134): row rebuilt from gameplan+postmortem archive after the " \
                   "2026-10-09 git-revert data loss; trade_id/entry time are the ORIGINAL values " \
                   "(preserved in the archive), credit/pnl exact."
        else:
            entry_dt = f"{date_iso} {EOD_FALLBACK_ENTRY[entry_bucket(tid_setup)]}"
            exit_dt = f"{date_iso} {STOP_FALLBACK_EXIT}"
            fill_model, close_reason = "paper_fill", \
                f"RECOVERED (S134): level-accepted stop, outcome={t.get('outcome','?')} " \
                "— exact clock time lost, see entry_note"
            fees = 4 * FEE
            trade_id = f"auto_{d8}_recov_{tid_setup}"
            note = "RECOVERED (S134): row rebuilt from gameplan+postmortem archive after the " \
                   "2026-10-09 git-revert data loss; credit/pnl/grade/outcome are EXACT (archived " \
                   "same evening), but entry/exit CLOCK TIME is approximated (not archived anywhere) " \
                   "— do not treat entry_dt/exit_dt as precise for this row."

        exit_cost = round(credit - (pnl + fees) / 100, 2)
        legs = [
            {"side": "buy", "right": right, "strike": long_, "expiry": d8, "qty": 1},
            {"side": "sell", "right": right, "strike": short, "expiry": d8, "qty": 1},
        ]
        rows.append({
            "trade_id": trade_id, "strategy_id": tid_setup, "source": "auto_trigger",
            "symbol": "SPXW", "entry_dt": entry_dt, "exit_dt": exit_dt, "dte": 0,
            "structure": "vertical 25pt", "legs": json.dumps(legs), "credit": credit,
            "exit_cost": exit_cost, "fill_model": fill_model, "slippage": None,
            "pnl": pnl, "roc": round(pnl / collateral, 4) if collateral else None,
            "collateral": collateral, "hold_days": 0, "win": pnl > 0,
            "vix": None, "vix_rank": None, "er10": None, "adx": None,
            "gex_regime": "unknown", "hvl_side": None, "dow": None, "event": None,
            "commentary": f"RECOVERED [{tid_setup}]: {t.get('name','')}. credit {credit:.2f}.",
            "grade": t.get("final_grade"), "max_gain": round(credit * 100),
            "max_loss": round(width * 100), "pop": None,
            "close_reason": close_reason, "entry_valid": True,
            "entry_lag_min": None, "feed_age_s": None, "entry_note": note,
        })
    return rows


def main():
    df = tlog.load()
    existing_ids = set(df.trade_id)
    all_new = []
    for date_iso in DATES:
        rows = build_rows(date_iso)
        new = [r for r in rows if r["trade_id"] not in existing_ids]
        skipped = len(rows) - len(new)
        total = round(sum(r["pnl"] for r in rows))
        print(f"  {date_iso}: {len(rows)} trades recovered (total ${total:+,}), "
              f"{skipped} already present" if skipped else
              f"  {date_iso}: {len(rows)} trades recovered, total ${total:+,}")
        all_new.extend(new)

    if not all_new:
        print("\nnothing new to write.")
        return

    df = pd.concat([df, pd.DataFrame(all_new)], ignore_index=True)
    LOG = ROOT / "data" / "options_log" / "trades.parquet"
    df.to_parquet(LOG, index=False)
    print(f"\nwrote {len(all_new)} new rows to {LOG}")

    # clean up the earlier (incorrect) recon-overlay entries for these dates
    rf = SIM / "reconstructed_days.json"
    if rf.exists():
        rec = json.loads(rf.read_text(encoding="utf-8"))
        removed = [d for d in DATES if rec.pop(d, None) is not None]
        if removed:
            rf.write_text(json.dumps(rec, indent=1), encoding="utf-8")
            print(f"removed incorrect recon-overlay entries for: {', '.join(removed)}")


if __name__ == "__main__":
    main()
