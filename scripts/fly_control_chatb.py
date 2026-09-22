"""Fly control: simulate the desk stop on the 79 August fly verticals, compare stop
DECISIONS + P&L to the desk's booked values; then ±1.82pt parity perturbation.
Local only (scratchpad) — not committed. Uses wall_pnl_stops primitives + Chat A's
marketable-touch exit pricer.
"""
import sys
from pathlib import Path
ROOT = Path(r"C:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "scripts"))
import json
import pandas as pd
import wall_pnl_stops as W
W.INTERVAL, W.FILL = "1m", "mid"

FLIES = ["eodfly_p", "eodfly_c", "openfly_p", "openfly_c"]


def detect(date, short_k, right, offset=0.0, accept_mins=10):
    o = "put" if right == "P" else "call"
    opp = "call" if right == "P" else "put"
    sp = W.opt_path(date, short_k, o)
    lp = W.opt_path(date, short_k - W.WING if right == "P" else short_k + W.WING, o)
    op = W.opt_path(date, short_k, opp)
    if not sp or not lp or not op:
        return None
    se0, le0 = W._at_or_before(sp, W.ENTRY_HM), W._at_or_before(lp, W.ENTRY_HM)
    if se0 is None or le0 is None:
        return None
    credit = W._mid(se0) - W._mid(le0)
    grid = sorted(t for t in (set(sp) | set(lp) | set(op)) if W.ENTRY_HM < t <= W.TIME_STOP_HM)
    call_src = sp if right == "C" else op
    put_src = sp if right == "P" else op
    accept_secs = accept_mins * 60
    beyond_start, exit_hm, reason = None, W.TIME_STOP_HM, "time_stop"
    for t in grid:
        cm, pm = W._mid(W._at_or_before(call_src, t)), W._mid(W._at_or_before(put_src, t))
        if cm is None or pm is None:
            continue
        spot = short_k + cm - pm + offset
        beyond = spot < short_k if right == "P" else spot > short_k
        if beyond:
            if beyond_start is None:
                beyond_start = t
            if W._secs(t) - W._secs(beyond_start) >= accept_secs:
                exit_hm, reason = t, "acceptance"
                break
        else:
            beyond_start = None
    se, le = W._at_or_before(sp, exit_hm), W._at_or_before(lp, exit_hm)
    exit_cost = W._mid(se) - W._mid(le)          # combo-net (mid) exit
    pnl = (credit - exit_cost) * W.MULT - 4 * W.FEE
    return {"stopped": reason == "acceptance", "pnl": pnl}


t = pd.read_parquet(ROOT / "data/options_log/trades.parquet")
t["d"] = t.entry_dt.astype(str).str[:10]
a = t[(t.d >= "2026-08-01") & (t.d <= "2026-08-31") & t.strategy_id.isin(FLIES) & t.exit_dt.notna()]

rows = []
for _, r in a.iterrows():
    legs = r.legs if isinstance(r.legs, list) else json.loads(r.legs)
    sh = next((l for l in legs if l.get("side") == "sell"), None)
    if not sh:
        continue
    K, right = float(sh["strike"]), (sh.get("right") or "").upper()
    base = detect(r.d, K, right, 0.0)
    if base is None:
        continue
    up = detect(r.d, K, right, +1.82)
    dn = detect(r.d, K, right, -1.82)
    rows.append({
        "date": r.d, "strat": r.strategy_id, "K": K, "right": right,
        "desk_stopped": "ACCEPT" in str(r.close_reason).upper(),
        "desk_pnl": float(r.pnl),
        "bt_stopped": base["stopped"], "bt_pnl": base["pnl"],
        "up_stopped": up["stopped"] if up else base["stopped"],
        "dn_stopped": dn["stopped"] if dn else base["stopped"],
        "up_pnl": up["pnl"] if up else base["pnl"],
        "dn_pnl": dn["pnl"] if dn else base["pnl"],
    })
d = pd.DataFrame(rows)
n = len(d)
tp = int((d.desk_stopped & d.bt_stopped).sum())
fp = int((~d.desk_stopped & d.bt_stopped).sum())
fn = int((d.desk_stopped & ~d.bt_stopped).sum())
tn = int((~d.desk_stopped & ~d.bt_stopped).sum())

print(f"August fly verticals with data: {n}")
print(f"desk acceptance-stops: {int(d.desk_stopped.sum())}   backtest acceptance-stops: {int(d.bt_stopped.sum())}\n")
print("STOP-DECISION confusion (backtest vs desk):")
print(f"  true-positive (both stop)   : {tp}")
print(f"  FALSE stop (bt yes, desk no): {fp}")
print(f"  MISSED stop (bt no, desk yes): {fn}")
print(f"  true-negative (neither)     : {tn}")
print(f"  agreement: {100*(tp+tn)/n:.0f}%  ({tp+tn}/{n})")

print(f"\nP&L (fly verticals, $):  desk booked {d.desk_pnl.sum():+,.0f}   backtest {d.bt_pnl.sum():+,.0f}   diff {d.bt_pnl.sum()-d.desk_pnl.sum():+,.0f}")
st = d[d.desk_stopped | d.bt_stopped]
if len(st):
    md = (st.bt_pnl - st.desk_pnl).abs().mean()
    print(f"  on the {len(st)} stop-involved trades: median |bt-desk| ${(st.bt_pnl-st.desk_pnl).abs().median():.0f}, mean ${md:.0f}")

fp_mask = ~d.desk_stopped & d.bt_stopped
agree_mask = d.desk_stopped == d.bt_stopped
print("\nFALSE-STOP trades (bt stopped, desk did not):")
for _, r in d[~d.desk_stopped & d.bt_stopped].iterrows():
    print(f"  {r.date} {r.strat:10} {r.right} {r.K:.0f}  desk {r.desk_pnl:>7.0f}  bt {r.bt_pnl:>7.0f}  diff {r.bt_pnl-r.desk_pnl:>7.0f}")

print("\nGAP DECOMPOSITION (backtest - desk):")
print(f"  on the 5 FALSE-stop trades : {(d[fp_mask].bt_pnl - d[fp_mask].desk_pnl).sum():+,.0f}")
print(f"  on the {int(agree_mask.sum())} AGREEMENT trades : {(d[agree_mask].bt_pnl - d[agree_mask].desk_pnl).sum():+,.0f}")
print(f"    (of which {int((agree_mask & d.desk_stopped).sum())} true-pos stops: "
      f"{(d[agree_mask & d.desk_stopped].bt_pnl - d[agree_mask & d.desk_stopped].desk_pnl).sum():+,.0f}, "
      f"{int((agree_mask & ~d.desk_stopped).sum())} held: "
      f"{(d[agree_mask & ~d.desk_stopped].bt_pnl - d[agree_mask & ~d.desk_stopped].desk_pnl).sum():+,.0f})")

print("\n±1.82pt PARITY PERTURBATION (p90 feed error):")
flip_up = int((d.bt_stopped != d.up_stopped).sum())
flip_dn = int((d.bt_stopped != d.dn_stopped).sum())
print(f"  decision flips vs baseline:  +1.82pt -> {flip_up}/{n}   -1.82pt -> {flip_dn}/{n}")
print(f"  book P&L:  base {d.bt_pnl.sum():+,.0f}   +1.82 {d.up_pnl.sum():+,.0f}   -1.82 {d.dn_pnl.sum():+,.0f}")
print(f"  P&L swing across ±1.82: ${max(d.up_pnl.sum(),d.dn_pnl.sum())-min(d.up_pnl.sum(),d.dn_pnl.sum()):,.0f}")
