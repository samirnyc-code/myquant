"""Professional options trade journal (S73) -> data/options_log/journal.json.

One record per trade_id, three sections (per pro-journal practice: plan /
execution / review are SEPARATE, and process quality is graded independently
of outcome):

  auto    — recomputed on every refresh from the pipeline's own data:
            context (spot, VIX, gamma regime, MenthorQ levels), plan snapshot
            (thesis, entry grade, POP, maxG/L, playbook exit rule), execution
            (fills, slippage, fees), lifecycle (MFE/MAE $ and R from the 5-min
            marks, time in trade), result (pnl, R-multiple = pnl/|max_loss|).
  review  — human fields, PRESERVED across refreshes: outcome_grade (process
            re-grade at exit), followed_plan, exit_reason, mistakes, lesson,
            do_differently.
  meta    — created/updated stamps.

Aggregate stats (expectancy, avg R, PF, win%, MAE/MFE averages) computed on
load. The Streamlit app renders + edits the review fields.

Refresh:  .venv/Scripts/python.exe scripts/options_journal.py
"""
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
JFILE = ROOT / "data" / "options_log" / "journal.json"
SIM = ROOT / "data" / "options_sim"
ET = ZoneInfo("America/New_York")

REVIEW_FIELDS = ["outcome_grade", "followed_plan", "exit_reason",
                 "mistakes", "lesson", "do_differently"]

EXIT_RULES = {  # playbook §s — the PLANNED exit, snapshotted into the journal
    "bps_stmr": "spot(15:59) > SMA5 -> buy back 16:00+; else settle at expiry",
    "sell_0dte_gamma": "hold to cash settlement (grid alt: 50% credit / 2x stop)",
    "condor_0dte": "hold to cash settlement",
    "straddle_0dte": "hold to close (counter-regime test)",
    "fly_gw_0dte": "hold to settlement at the pin",
    "bcs_cr_0dte": "hold to settlement",
    "bull_cs_wk": "hold to expiry or signal reversal",
    "put_cal_wk": "close at 0DTE-leg expiry",
}


def load_journal():
    if JFILE.exists():
        return json.loads(JFILE.read_text(encoding="utf-8"))
    return {}


def save_journal(j):
    JFILE.parent.mkdir(parents=True, exist_ok=True)
    JFILE.write_text(json.dumps(j, indent=1), encoding="utf-8")


def _mfe_mae(marks, trade_id, risk):
    mk = marks[marks.trade_id == trade_id] if len(marks) else pd.DataFrame()
    if not len(mk):
        return None
    u = mk.unreal_pnl.astype(float)
    mfe, mae = float(u.max()), float(u.min())
    return {"mfe": round(mfe), "mae": round(mae),
            "mfe_R": round(mfe / risk, 2) if risk else None,
            "mae_R": round(mae / risk, 2) if risk else None,
            "n_marks": int(len(mk)),
            "best_ts": mk.loc[u.idxmax(), "ts_et"], "worst_ts": mk.loc[u.idxmin(), "ts_et"]}


def refresh():
    j = load_journal()
    trades = tlog.load()
    marks = pd.read_csv(SIM / "marks.csv") if (SIM / "marks.csv").exists() else pd.DataFrame()
    mq_f = ROOT / "data" / "menthorq" / "spx_calibration.csv"
    mq = pd.read_csv(mq_f).iloc[-1].to_dict() if mq_f.exists() else {}

    for _, r in trades.iterrows():
        tid = r.trade_id
        risk = abs(float(r.max_loss)) if pd.notna(r.max_loss) else (
            float(r.collateral) if pd.notna(r.collateral) else None)
        pnl = float(r.pnl) if pd.notna(r.pnl) else None
        pop_v = r["pop"]
        auto = {
            "strategy": r.strategy_id, "structure": r.structure,
            "legs": json.loads(r.legs) if isinstance(r.legs, str) else [],
            "entry_dt": str(r.entry_dt), "exit_dt": None if pd.isna(r.exit_dt) else str(r.exit_dt),
            "dte": None if pd.isna(r.dte) else int(r.dte),
            "state": "open" if pd.isna(r.exit_dt) else "closed",
            "context": {
                "vix": None if pd.isna(r.vix) else float(r.vix),
                "vix_rank": None if pd.isna(r.vix_rank) else float(r.vix_rank),
                "er10": None if pd.isna(r.er10) else float(r.er10),
                "dow": r.dow if isinstance(r.dow, str) else None,
                "gamma_regime": ("positive (spot>HVL)" if mq and mq.get("spot", 0) > mq.get("mq_hvl", 9e9)
                                 else "negative/unknown"),
                "mq_levels": {k: mq.get(k) for k in ("mq_cr", "mq_ps", "mq_hvl", "mq_cr0",
                                                     "mq_ps0", "mq_hvl0", "mq_gw0")} if mq else None,
            },
            "plan": {
                "thesis": r.commentary if isinstance(r.commentary, str) else "",
                "entry_grade": r.grade if isinstance(r.grade, str) else None,
                "pop": None if pd.isna(pop_v) else float(pop_v),
                "max_gain": None if pd.isna(r.max_gain) else float(r.max_gain),
                "max_loss": None if pd.isna(r.max_loss) else float(r.max_loss),
                "planned_exit": EXIT_RULES.get(r.strategy_id, "per playbook"),
            },
            "execution": {
                "net_credit": None if pd.isna(r.credit) else float(r.credit),
                "fill_model": r.fill_model if isinstance(r.fill_model, str) else None,
                "slippage_vs_mid": None if pd.isna(r.slippage) else float(r.slippage),
                "collateral": None if pd.isna(r.collateral) else float(r.collateral),
            },
            "lifecycle": _mfe_mae(marks, tid, risk),
            "result": {
                "pnl": pnl, "win": None if pnl is None else pnl > 0,
                "r_multiple": None if (pnl is None or not risk) else round(pnl / risk, 2),
                "exit_cost": None if pd.isna(r.exit_cost) else float(r.exit_cost),
                "hold_days": None if pd.isna(r.hold_days) else float(r.hold_days),
            },
        }
        if tid not in j:
            j[tid] = {"auto": auto, "review": {k: "" for k in REVIEW_FIELDS},
                      "meta": {"created": dt.datetime.now(ET).isoformat(timespec="seconds")}}
        else:
            j[tid]["auto"] = auto  # review preserved
        j[tid]["meta"]["updated"] = dt.datetime.now(ET).isoformat(timespec="seconds")
    save_journal(j)
    return j


def stats(j):
    closed = [e for e in j.values() if e["auto"]["state"] == "closed"
              and e["auto"]["result"]["pnl"] is not None]
    if not closed:
        return {"closed": 0}
    pnls = [e["auto"]["result"]["pnl"] for e in closed]
    rs = [e["auto"]["result"]["r_multiple"] for e in closed if e["auto"]["result"]["r_multiple"] is not None]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    return {
        "closed": len(closed), "win_rate": round(len(wins) / len(closed), 2),
        "expectancy_$": round(sum(pnls) / len(pnls)),
        "avg_R": round(sum(rs) / len(rs), 2) if rs else None,
        "profit_factor": round(sum(wins) / -sum(losses), 2) if losses else None,
        "total_$": round(sum(pnls)),
        "avg_MAE": round(pd.Series([e["auto"]["lifecycle"]["mae"] for e in closed
                                    if e["auto"].get("lifecycle")]).mean()) if any(
            e["auto"].get("lifecycle") for e in closed) else None,
    }


if __name__ == "__main__":
    j = refresh()
    print(f"journal: {len(j)} trades -> {JFILE}")
    print(json.dumps(stats(j), indent=1))
