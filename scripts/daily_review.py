"""Daily Reflective Review (S75) — the reflection the postmortem lacks: did the day
match a gameplan scenario, how did price behave AT each level, did we over/under-trade
or bet contradictory scenarios, and which playbook structure the actual path warranted.

Deterministic scaffold (sections 1-4). The 'nugget' (section 5, the why/lesson) is
written by hand from this scaffold — kept out of code so no LLM invents lessons.

  data/options_sim/daily_review_<date>.json  (+ printed report)

Run:  .venv/Scripts/python.exe scripts/daily_review.py [YYYYMMDD]
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LOG = ROOT / "data" / "options_log"

TOUCH = 3.0      # within this many pts = a touch
REJECT = 8.0     # move away this far after touch, holding = rejection
ACCEPT_FRAC = 0.30  # fraction of post-breach samples spent beyond = acceptance

# which scenario each setup is a bet ON (for the contradiction check)
SETUP_SCENARIO = {
    "fly_gw_0dte": "A/C (pin at wall)", "sell_0dte_gamma": "C (pin/chop)",
    "cr0_fade": "A (CR holds)", "ps0_fade": "B (PS holds)",
    "straddle_0dte": "D (break/expand)", "bps_stmr": "signal",
}


def classify_level(px, level, name):
    """How did price behave at `level`? rejection / acceptance / failed_break /
    breakout_pullback / tag_only / not_tested — from the price path alone."""
    if level is None or level != level:
        return {"level": name, "value": level, "behavior": "n/a"}
    d = px - level
    touched = (d.abs() <= TOUCH)
    if not touched.any():
        side = "above" if px.iloc[-1] > level else "below"
        return {"level": name, "value": round(level, 1), "behavior": "not_tested", "close_side": side}
    ti = touched.idxmax()                       # first touch index
    approached = "above" if px.iloc[:ti + 1].mean() > level else "below"
    post = px.iloc[ti:]
    breached_up = (post > level + TOUCH).any()
    breached_dn = (post < level - TOUCH).any()
    # closed on the FAR side from where price approached = a real break
    if approached == "above":
        closed_beyond = px.iloc[-1] < level - TOUCH
    else:
        closed_beyond = px.iloc[-1] > level + TOUCH
    # acceptance: closed the far side AND spent real time beyond
    beyond = ((post > level) if approached == "below" else (post < level))
    accept = closed_beyond and beyond.mean() >= ACCEPT_FRAC
    # rejection: never held beyond, and moved back a healthy distance
    max_away_back = (level - post.min()) if approached == "above" else (post.max() - level)
    breached = breached_up if approached == "below" else breached_dn
    if accept:
        beh = "acceptance"          # broke and held → continuation
    elif breached and not closed_beyond:
        beh = "failed_break"        # poked through, closed back → fakeout/fade
    elif breached and closed_beyond:
        beh = "breakout"            # broke, closed beyond (weaker than acceptance)
    elif not breached and max_away_back >= REJECT:
        beh = "rejection"           # held, pushed away → level worked
    else:
        beh = "tag_only"            # touched, no clear resolution
    return {"level": name, "value": round(level, 1), "behavior": beh,
            "approached_from": approached, "first_touch_i": int(ti),
            "note": "absorption/aggression needs order-flow (footprint) — not visible in OHLC"}


def scenario_actual(lv, hi, lo, close):
    hvl, cr0, ps0 = lv.get("hvl"), lv.get("cr0") or lv.get("cr"), lv.get("ps0")
    if hvl and close < hvl:
        return "D", "break below HVL (closed below)"
    if cr0 and hi >= cr0 - 5:
        return "A", "reached the wall (CR0/GW0)"
    if hvl and cr0 and lo >= hvl and hi <= cr0:
        return "C", "held the pin band (HVL–CR0)"
    return "B", "faded toward support, no clean break"


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else dt.datetime.now().strftime("%Y%m%d")
    d = date
    gp = json.loads((SIM / f"gameplan_{d}.json").read_text(encoding="utf-8"))
    lv = gp["levels"]
    scen = gp.get("scenarios", [])

    tape = pd.read_csv(SIM / f"underlying_{d}.csv")
    px = tape.und.astype(float)
    hi, lo, op, close = px.max(), px.min(), px.iloc[0], px.iloc[-1]

    # 1. scenario reconciliation
    aid, adesc = scenario_actual(lv, hi, lo, close)
    mapped = {s["id"]: s for s in scen}
    had_it = aid in mapped
    rec = {"actual": aid, "actual_desc": adesc, "mapped_paths": list(mapped),
           "had_scenario": had_it,
           "open": round(op, 1), "high": round(hi, 1), "low": round(lo, 1), "close": round(close, 1)}

    # 2. level action (price-behavior taxonomy)
    levels = [("HVL", lv.get("hvl")), ("CR0", lv.get("cr0") or lv.get("cr")),
              ("PS0", lv.get("ps0")), ("GW0", lv.get("gw0")),
              ("1D_max", gp.get("d1_max")), ("1D_min", gp.get("d1_min"))]
    level_action = [classify_level(px, val, nm) for nm, val in levels]

    # 3. us vs the scenario
    trades = pd.read_parquet(LOG / "trades.parquet")
    day = trades[trades.entry_dt.astype(str).str.startswith(f"{d[:4]}-{d[4:6]}-{d[6:]}")]
    met = pd.read_csv(SIM / "trade_metrics.csv").groupby("trade_id").last() if (SIM / "trade_metrics.csv").exists() else None
    fired = []
    for _, r in day.iterrows():
        pnl = met.unreal_pnl.get(r.trade_id) if met is not None and r.trade_id in met.index else r.pnl
        fired.append({"strategy": r.strategy_id, "structure": r.structure,
                      "entry": str(r.entry_dt)[11:16], "scenario_bet": SETUP_SCENARIO.get(r.strategy_id, "?"),
                      "pnl": None if pnl != pnl else round(float(pnl))})
    bets = {f["scenario_bet"].split()[0] for f in fired if f["scenario_bet"] not in ("signal", "?")}
    contradiction = len(bets) > 1
    total = sum(f["pnl"] for f in fired if f["pnl"] is not None)
    behavior = {"n_trades": len(fired), "distinct_scenario_bets": sorted(bets),
                "contradiction": contradiction, "overtraded": len(bets) > 1,
                "day_pnl": total, "trades": fired}

    # 4. playbook counterfactual (which structures the ACTUAL path warranted)
    RIGHT = {"A": "call premium at CR0 held / call debit if breaking up",
             "B": "put credit at PS0 (support holds)",
             "C": "iron condor / both premium sells (pin)",
             "D": "directional DOWN — put debit spread or SELL call premium above; long straddle ONLY on momentum/vol-expansion"}
    counterfactual = {"actual_path": aid, "right_structure": RIGHT.get(aid, "?"),
                      "what_we_did": sorted({f["scenario_bet"] for f in fired}),
                      "aligned": any(f["scenario_bet"].startswith(aid) for f in fired)}

    review = {"date": d, "scenario": rec, "level_action": level_action,
              "behavior": behavior, "counterfactual": counterfactual}
    (SIM / f"daily_review_{d}.json").write_text(json.dumps(review, indent=2), encoding="utf-8")

    # printed report
    print(f"\n===== DAILY REFLECTIVE REVIEW — {d} =====")
    print(f"\n1. SCENARIO  actual = Path {aid} ({adesc})")
    print(f"   mapped {list(mapped)} | had it: {'YES' if had_it else 'NO'} | "
          f"O {rec['open']} H {rec['high']} L {rec['low']} C {rec['close']}")
    print("\n2. LEVEL ACTION (price-behavior; absorption needs order-flow)")
    for la in level_action:
        print(f"   {la['level']:7} {str(la.get('value')):8} -> {la['behavior']}"
              + (f"  (from {la.get('approached_from')})" if la.get("approached_from") else ""))
    print(f"\n3. US vs SCENARIO   {behavior['n_trades']} trades · day P&L ${total:,}")
    print(f"   scenario bets: {sorted(bets)}  ->  "
          f"{'⚠ CONTRADICTION / OVERTRADE' if contradiction else 'coherent'}")
    for f in fired:
        print(f"   {f['entry']} {f['strategy']:16} bet {f['scenario_bet']:18} "
              f"${f['pnl'] if f['pnl'] is not None else '?'}")
    print(f"\n4. COUNTERFACTUAL   Path {aid} warranted: {RIGHT.get(aid)}")
    print(f"   did any trade align with Path {aid}? {'YES' if counterfactual['aligned'] else 'NO'}")
    print(f"\n-> {SIM / f'daily_review_{d}.json'}")


if __name__ == "__main__":
    main()
