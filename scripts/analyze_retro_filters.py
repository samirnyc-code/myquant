"""analyze_retro_filters.py — 30-day retro on the SPX 0DTE desk: exit timing + GEX filters.

Answers three questions from the recorded trade log + the per-day gexlog gameplan:
  1. EXIT TIMING — for STOPPED trades ("wall didn't hold -> cut"), did the short strike
     actually finish ITM (the stop saved money) or OTM (the stop cut a WINNER = too early)?
  2. GEX CLUES — join each trade to that day's gexlog (day_type CHOP/TREND, gamma POS/NEG,
     put/call walls, EM band, event gate) and see where the money is lost.
  3. FILTERS — backtest simple skip-rules and report the P&L delta + trades dropped.

Read-only. Saves data/options_sim/retro_{stops,byfilter}.csv. Realized (closed) trades only.
Run: .venv/Scripts/python.exe scripts/analyze_retro_filters.py
"""
from __future__ import annotations
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"


def load_gameplans():
    """date -> {day_type, gamma, putWall, callWall, em_lo, em_hi, vix, event_verdict, net_gex}."""
    out = {}
    for f in glob.glob(str(SIM / "gameplan_2026*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        gx = d.get("gexlog") or {}
        eg = d.get("event_gate") or {}
        date = d.get("date")
        if not date:
            continue
        iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        out[iso] = {
            "day_type": gx.get("day_type"), "gamma": gx.get("regime"),
            "putWall": gx.get("putWall"), "callWall": gx.get("callWall"),
            "em_lo": gx.get("emLower"), "em_hi": gx.get("emUpper"),
            "net_gex": gx.get("net_gex"), "confidence": gx.get("confidence"),
            "vix": d.get("vix"), "event_verdict": eg.get("verdict"),
            "event_day": eg.get("event_day"),
        }
    return out


def closes():
    d = pd.read_csv(SIM / "spx_daily_yahoo.csv")
    return dict(zip(d.Date, d.Close.astype(float)))


def leg_info(legs):
    """(short_strike, short_right, width) from a trade's legs list/json."""
    L = json.loads(legs) if isinstance(legs, str) else legs
    s = next((x for x in L if x["side"] == "sell"), None)
    b = next((x for x in L if x["side"] == "buy"), None)
    if not s:
        return None, None, None
    width = abs(s["strike"] - b["strike"]) if b else None
    return float(s["strike"]), s["right"], width


def main():
    d = tlog.load()
    d["pnl"] = pd.to_numeric(d["pnl"], errors="coerce")
    d["ed"] = pd.to_datetime(d["exit_dt"], errors="coerce")
    d = d[(d.ed >= "2026-08-01") & d.pnl.notna() & (d.strategy_id != "incident_orphan")].copy()
    d["day"] = d.ed.dt.strftime("%Y-%m-%d")
    gp = load_gameplans()
    cl = closes()

    # per-trade enrich
    rows = []
    for _, r in d.iterrows():
        ss, sr, w = leg_info(r.legs)
        g = gp.get(r.day, {})
        close = cl.get(r.day)
        # did the SHORT expire ITM at the day's close?
        itm = None
        if ss is not None and close is not None:
            itm = (close < ss) if sr == "P" else (close > ss)
        stopped = "ACCEPTED" in str(r.close_reason) or "wall" in str(r.close_reason)
        side = "call" if (str(r.strategy_id).endswith("_c") or "bcs" in str(r.strategy_id)) else "put"
        timing = ("EOD" if str(r.strategy_id).startswith("eod")
                  else "Open" if str(r.strategy_id).startswith("open") else "GexWall")
        # short strike vs the same-side wall
        wall = g.get("callWall") if side == "call" else g.get("putWall")
        beyond_wall = None
        if ss is not None and wall is not None:
            beyond_wall = (ss > wall) if side == "call" else (ss < wall)  # sold past the wall?
        rows.append({**r[["trade_id", "strategy_id", "day", "pnl"]].to_dict(),
                     "side": side, "timing": timing, "stopped": stopped,
                     "short": ss, "right": sr, "close": close, "short_itm_at_close": itm,
                     "day_type": g.get("day_type"), "gamma": g.get("gamma"),
                     "event_verdict": g.get("event_verdict"), "vix": g.get("vix"),
                     "beyond_wall": beyond_wall})
    t = pd.DataFrame(rows)
    print(f"trades {len(t)}  over {t.day.nunique()} days  realized ${t.pnl.sum():,.0f}\n")

    # ---- 1. EXIT TIMING: were the stops premature? ----
    st = t[t.stopped & t.short_itm_at_close.notna()]
    prem = st[~st.short_itm_at_close]     # short finished OTM => trade would have EXPIRED WORTHLESS
    just = st[st.short_itm_at_close]      # short finished ITM  => stop cut a real loser
    print("=== EXIT TIMING — were the 'wall broke -> cut' stops right? ===")
    print(f"  stopped trades analysed: {len(st)}")
    print(f"  PREMATURE (short expired OTM -> would've won if held): {len(prem)}  "
          f"realized ${prem.pnl.sum():,.0f}  (these are trades the stop turned into losses)")
    print(f"  JUSTIFIED (short expired ITM -> stop cut a real loser): {len(just)}  "
          f"realized ${just.pnl.sum():,.0f}")
    print(f"  -> if we had HELD every stopped trade to expiry instead of cutting:")
    # held-to-expiry pnl approx = keep full credit if OTM; if ITM, lose ~intrinsic (bounded by width)
    print(f"     the {len(prem)} premature ones alone cost us ${-prem.pnl.sum():,.0f} in stop losses "
          f"they'd have avoided (minus a little theta). Stops look TOO EARLY on these.\n")
    st.to_csv(SIM / "retro_stops.csv", index=False)

    # ---- 2 + 3. FILTER BACKTESTS ----
    base = t.pnl.sum()
    def impact(mask, label):
        kept = t[~mask]
        return {"filter": label, "skipped": int(mask.sum()),
                "skipped_pnl": round(t[mask].pnl.sum()), "kept_pnl": round(kept.pnl.sum()),
                "delta_vs_base": round(kept.pnl.sum() - base)}
    filters = [
        impact(t.day_type == "TREND", "skip TREND days"),
        impact(t.gamma == "NEGATIVE", "skip NEGATIVE-gamma days"),
        impact(t.event_verdict == "STAND_ASIDE", "skip STAND_ASIDE (event-gate) days"),
        impact(t.timing == "EOD", "skip the EOD book"),
        impact(t.side == "call", "skip the CALL side"),
        impact(t.beyond_wall == True, "skip shorts sold BEYOND the wall"),
        impact((t.side == "call") & (t.timing == "EOD"), "skip EOD call side"),
        impact(pd.to_numeric(t.vix, errors="coerce") > 16, "skip VIX>16 days"),
    ]
    fdf = pd.DataFrame(filters).sort_values("delta_vs_base", ascending=False)
    print("=== FILTER BACKTESTS (base realized ${:,.0f}) ===".format(base))
    print(fdf.to_string(index=False))
    fdf.to_csv(SIM / "retro_byfilter.csv", index=False)

    # ---- day_type / gamma / side breakdowns ----
    for by in ["day_type", "gamma", "side", "timing", "event_verdict"]:
        g = t.groupby(by).agg(n=("pnl", "size"), win=("pnl", lambda s: round(100*(s > 0).mean())),
                              total=("pnl", "sum")).round(0).sort_values("total")
        print(f"\n--- by {by} ---"); print(g.to_string())


if __name__ == "__main__":
    main()
