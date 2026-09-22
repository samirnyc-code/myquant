"""td_pnl_reconstruct.py — rebuild the SPX book's P&L from ONLY ThetaData + IB-real inputs,
restate the sim's calendar P&L at REAL commissions, and produce an exact P&L BRIDGE that shows
where every dollar of the sim-vs-real difference comes from.

Prices, all from the real market:
  * ENTRY  — marketable touch at the true fill time (TD NBBO): SELL hits the BID, BUY pays the ASK.
  * EXIT (order-closed) — marketable touch to CLOSE: buy back a short at the ASK, sell a long at the BID.
  * EXIT (expired) — cash settlement: intrinsic vs the official SPX 4pm close (TD /v3/index/history/eod).
  * COMMISSIONS — IB's REAL per-execution commission (Flex). The sim modeled a flat FEE=$1.30/trade.

The bridge (each step changes ONE thing, closes to the penny):
  Sim booked  ->(+commission correction)->  Sim @ real commissions
              ->(+entry-fill diff)->(+order-exit-fill diff)->(+settlement diff)->  TD net

Scope: SPX (SPXW), Aug 6+. Read-only; writes a DATED per-trade CSV + a bridge JSON.
  .venv/Scripts/python.exe scripts/td_pnl_reconstruct.py
"""
from __future__ import annotations
import csv
import datetime as dt
import glob
import io
import json
import urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OL = ROOT / "data" / "options_log"
TD = ROOT / "data" / "thetadata"
SIM = ROOT / "data" / "options_sim"
V3 = "http://127.0.0.1:25503"
MULT = 100
SIM_FEE = 1.30                                         # sim's flat modeled commission per trade


def spx_closes(d0: str, d1: str) -> dict:
    u = f"{V3}/v3/index/history/eod?symbol=SPX&start_date={d0}&end_date={d1}&format=csv"
    rows = list(csv.DictReader(io.StringIO(urllib.request.urlopen(u, timeout=30).read().decode())))
    out = {}
    for r in rows:
        stamp = r.get("last_trade") or r.get("created") or ""
        date = stamp[:10].replace("-", "")
        if date and r.get("close"):
            out[date] = float(r["close"])
    return out


def main() -> int:
    tr = pd.read_parquet(OL / "trades.parquet")
    tr = tr[(tr.entry_dt >= "2026-08-06") & (tr.symbol == "SPXW")].copy()

    at = pd.read_csv(sorted(glob.glob(str(TD / "at_time_results_*.csv")))[-1])
    at = at[at.quote_status == "ok"].copy()
    at["k"] = list(zip(at.trade_id, at.event, at.strike.round(3), at.right.astype(str).str[:1]))
    look = {k: (float(r.bid), float(r.ask)) for k, r in zip(at.k, at.itertuples())}

    fx = pd.read_csv(sorted(glob.glob(str(OL / "ib_flex_executions_*.csv")))[-1])
    fx = fx[fx.symbol.astype(str).str.startswith("SPXW")].copy()
    fx["k"] = list(zip(fx.expiry.astype(str), fx.strike.astype(float).round(3),
                       fx.put_call.astype(str).str[:1], fx.side.astype(str).str.upper()))
    cser = pd.to_numeric(fx.commission, errors="coerce").abs()
    comm = cser.groupby(fx.k).mean().to_dict()
    comm_default = cser.median()

    exps = sorted({str(lg["expiry"]) for _, r in tr.iterrows() for lg in json.loads(r.legs)})
    SET = spx_closes(exps[0], exps[-1])
    print(f"SPX settlement closes pulled: {len(SET)} dates ({exps[0]}..{exps[-1]})")

    rows, miss = [], 0
    for _, r in tr.iterrows():
        legs = json.loads(r.legs)
        order_closed = str(r.fill_model) == "paper_fill"
        td_entry = td_exit = real_comm = 0.0
        ok = True
        for lg in legs:
            side, right = lg["side"], str(lg["right"])[:1]
            strike, expiry = float(lg["strike"]), str(lg["expiry"])
            open_act = "BUY" if side == "buy" else "SELL"
            e = look.get((r.trade_id, "entry", round(strike, 3), right))
            if not e:
                ok = False
                break
            ebid, eask = e
            td_entry += ebid if side == "sell" else -eask
            real_comm += comm.get((expiry, round(strike, 3), right, open_act), comm_default)
            if order_closed:
                x = look.get((r.trade_id, "exit", round(strike, 3), right))
                if not x:
                    ok = False
                    break
                xbid, xask = x
                td_exit += xbid if side == "buy" else -xask
                exit_act = "SELL" if side == "buy" else "BUY"
                real_comm += comm.get((expiry, round(strike, 3), right, exit_act), comm_default)
            else:
                s = SET.get(expiry)
                if s is None:
                    ok = False
                    break
                intr = max(0.0, s - strike) if right == "C" else max(0.0, strike - s)
                td_exit += intr if side == "buy" else -intr
        if not ok:
            miss += 1
            continue
        td_gross = (td_entry + td_exit) * MULT
        td_net = td_gross - real_comm
        sim_pnl = float(r.pnl)
        sim_gross = sim_pnl + SIM_FEE                              # sim modeled FEE per trade
        entry_diff = (td_entry - float(r.credit)) * MULT          # TD entry touch vs sim credit
        exit_settle_diff = (td_gross - sim_gross) - entry_diff    # order-exit fills + settlement
        rows.append({
            "trade_id": r.trade_id, "strategy": r.strategy_id,
            "closed": "order" if order_closed else "expired",
            "sim_entry": round(float(r.credit) * MULT, 2), "td_entry": round(td_entry * MULT, 2),
            "sim_gross": round(sim_gross, 2), "td_gross": round(td_gross, 2),
            "td_exit": round(td_exit * MULT, 2),
            "sim_comm": SIM_FEE, "real_comm": round(real_comm, 2),
            "sim_pnl": round(sim_pnl, 2), "td_net": round(td_net, 2),
            "sim_at_realcomm": round(sim_pnl + SIM_FEE - real_comm, 2),
            "commission_adj": round(SIM_FEE - real_comm, 2),
            "entry_fill_diff": round(entry_diff, 2),
            "exit_settle_diff": round(exit_settle_diff, 2),
            "total_diff": round(td_net - sim_pnl, 2),
        })
    d = pd.DataFrame(rows)
    stamp = dt.datetime.now().strftime("%Y%m%d")
    d.to_csv(SIM / f"td_pnl_reconstruct_{stamp}.csv", index=False)

    n = len(d)
    sim_entry, td_entry = d.sim_entry.sum(), d.td_entry.sum()
    sim_gross, td_gross = d.sim_gross.sum(), d.td_gross.sum()
    sim_exit, td_exit = sim_gross - sim_entry, d.td_exit.sum()
    sim_comm, real_comm = d.sim_comm.sum(), d.real_comm.sum()
    sim_net, td_net = d.sim_pnl.sum(), d.td_net.sum()

    # Restate the sim at REAL IB commissions FIRST, so the comparison uses the same fees on both
    # sides (commissions delta = 0) and the remaining delta is purely fills + settlement.
    sim_adj = sim_gross - real_comm                       # sim P&L at real commissions

    def dp(s, t):
        return round((t - s) / abs(s) * 100, 1) if s else 0.0
    # [label, sim, real, delta$, delta%, kind]  kind: line | subtotal | total
    compare = [
        ["Entry premium collected", sim_entry, td_entry, td_entry - sim_entry, dp(sim_entry, td_entry), "line"],
        ["Exit + settlement", sim_exit, td_exit, td_exit - sim_exit, dp(sim_exit, td_exit), "line"],
        ["Gross P&L", sim_gross, td_gross, td_gross - sim_gross, dp(sim_gross, td_gross), "subtotal"],
        ["Commissions (real IB, both sides)", -real_comm, -real_comm, 0.0, 0.0, "line"],
        ["Net P&L (at real commissions)", sim_adj, td_net, td_net - sim_adj, dp(sim_adj, td_net), "total"],
    ]
    per_trade = {
        "overstate_dollar": round((sim_adj - td_net) / n, 2),           # fills/settlement only, per trade
        "overstate_pct": round((sim_adj - td_net) / abs(td_net) * 100, 1),
        "fees_undercounted_dollar": round((real_comm - sim_comm) / n, 2),  # the separate fee restatement
    }
    (SIM / f"td_pnl_bridge_{stamp}.json").write_text(json.dumps({
        "n_trades": n, "compare": compare, "per_trade": per_trade,
        "sim_booked": round(sim_net, 2), "sim_modeled_comm": round(sim_comm, 2),
        "real_comm": round(real_comm, 2), "commission_correction": round(-(real_comm - sim_comm), 2),
        "headline": {"sim_adj": round(sim_adj, 2), "td_net": round(td_net, 2)},
        "by_exit": {k: {"n": int(len(g)), "sim_adj": round(g.sim_at_realcomm.sum(), 2),
                        "td_net": round(g.td_net.sum(), 2)} for k, g in d.groupby("closed")},
    }, indent=1), encoding="utf-8")

    print(f"\ntrades: {n}  (skipped {miss})")
    print(f"  Sim booked ${sim_net:,.0f} (modeled fees ${sim_comm:,.0f}) "
          f"-> restated at REAL fees ${real_comm:,.0f} -> ${sim_adj:,.0f}\n")
    print(f"  {'component':34} {'sim':>12} {'real(TD)':>12} {'delta$':>10} {'delta%':>8}")
    for lbl, s, t, da, dpc, _ in compare:
        print(f"  {lbl:34} ${s:>10,.0f} ${t:>10,.0f} ${da:>8,.0f} {dpc:>7.1f}%")
    print(f"\n  at real fees, sim overstates ${per_trade['overstate_dollar']}/trade "
          f"({per_trade['overstate_pct']}%) from fills/settlement; "
          f"separately, real fees are ${per_trade['fees_undercounted_dollar']}/trade above the sim's model")
    print(f"  saved -> {(SIM / f'td_pnl_reconstruct_{stamp}.csv').relative_to(ROOT)} + bridge json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
