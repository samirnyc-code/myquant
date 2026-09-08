"""td_pnl_reconstruct.py — rebuild the SPX book's P&L using ONLY ThetaData + IB-real inputs,
and compare it to the sim's booked P&L.

Every price comes from the real market:
  * ENTRY  — the marketable touch at our true fill time (TD NBBO): SELL hits the BID, BUY pays
             the ASK. (Our actual fills validated at ~this touch — median position 0.)
  * EXIT (order-closed legs) — the marketable touch to CLOSE at the true exit time: close a
             short by BUYing the ASK, close a long by SELLing the BID.
  * EXIT (expired legs) — cash settlement at the official SPXW close: intrinsic vs the SPX 4pm
             index close (ThetaData /v3/index/history/eod). Short pays intrinsic, long receives it.
  * COMMISSIONS — IB's REAL per-execution commission (IB Flex), not the sim's modeled ~$0.65/leg.

Scope: SPX (SPXW) only, from the events/at_time date range (Aug 6+). Read-only; writes a DATED CSV.
  .venv/Scripts/python.exe scripts/td_pnl_reconstruct.py
"""
from __future__ import annotations
import datetime as dt
import glob
import json
import urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OL = ROOT / "data" / "options_log"
TD = ROOT / "data" / "thetadata"
SIM = ROOT / "data" / "options_sim"
V3 = "http://127.0.0.1:25503"
MULT = 100                                            # SPX option multiplier


def spx_closes(d0: str, d1: str) -> dict:
    """SPX 4pm index close per date (the SPXW PM settlement basis), from ThetaData."""
    u = (f"{V3}/v3/index/history/eod?symbol=SPX&start_date={d0}&end_date={d1}&format=csv")
    rows = list(__import__("csv").DictReader(
        __import__("io").StringIO(urllib.request.urlopen(u, timeout=30).read().decode())))
    out = {}
    for r in rows:
        stamp = r.get("last_trade") or r.get("created") or ""
        date = stamp[:10].replace("-", "")
        c = r.get("close")
        if date and c:
            out[date] = float(c)
    return out


def main() -> int:
    tr = pd.read_parquet(OL / "trades.parquet")
    tr = tr[(tr.entry_dt >= "2026-08-06") & (tr.symbol == "SPXW")].copy()

    at = pd.read_csv(sorted(glob.glob(str(TD / "at_time_results_*.csv")))[-1])
    at = at[at.quote_status == "ok"].copy()
    at["k"] = list(zip(at.trade_id, at.event, at.strike.round(3), at.right.astype(str).str[:1]))
    look = {k: (float(r.bid), float(r.ask)) for k, r in zip(at.k, at.itertuples())}

    # real per-execution commissions from IB Flex, keyed by contract+action (mean, abs)
    fx = pd.read_csv(sorted(glob.glob(str(OL / "ib_flex_executions_*.csv")))[-1])
    fx = fx[fx.symbol.astype(str).str.startswith("SPXW")].copy()
    fx["k"] = list(zip(fx.expiry.astype(str), fx.strike.astype(float).round(3),
                       fx.put_call.astype(str).str[:1], fx.side.astype(str).str.upper()))
    comm = pd.to_numeric(fx.commission, errors="coerce").abs().groupby(fx.k).mean().to_dict()
    comm_default = pd.to_numeric(fx.commission, errors="coerce").abs().median()

    exps = sorted({str(lg["expiry"]) for _, r in tr.iterrows() for lg in json.loads(r.legs)})
    SET = spx_closes(exps[0], exps[-1])
    print(f"SPX settlement closes pulled: {len(SET)} dates ({exps[0]}..{exps[-1]})")

    rows, miss = [], 0
    for _, r in tr.iterrows():
        legs = json.loads(r.legs)
        order_closed = str(r.fill_model) == "paper_fill"
        pnl_td = commission = 0.0
        ok = True
        for lg in legs:
            side = lg["side"]           # buy / sell
            right = str(lg["right"])[:1]
            strike = float(lg["strike"])
            expiry = str(lg["expiry"])
            open_act = "BUY" if side == "buy" else "SELL"
            # ENTRY at the marketable touch
            e = look.get((r.trade_id, "entry", round(strike, 3), right))
            if not e:
                ok = False
                break
            ebid, eask = e
            entry_cf = ebid if side == "sell" else -eask          # sell hits bid / buy pays ask
            commission += comm.get((expiry, round(strike, 3), right, open_act), comm_default)
            # EXIT
            if order_closed:
                x = look.get((r.trade_id, "exit", round(strike, 3), right))
                if not x:
                    ok = False
                    break
                xbid, xask = x
                exit_cf = xbid if side == "buy" else -xask        # sell long at bid / buy back short at ask
                exit_act = "SELL" if side == "buy" else "BUY"
                commission += comm.get((expiry, round(strike, 3), right, exit_act), comm_default)
            else:                                                 # expired -> cash settlement
                s = SET.get(expiry)
                if s is None:
                    ok = False
                    break
                intr = max(0.0, s - strike) if right == "C" else max(0.0, strike - s)
                exit_cf = intr if side == "buy" else -intr        # long receives / short pays intrinsic
            pnl_td += (entry_cf + exit_cf) * MULT
        if not ok:
            miss += 1
            continue
        pnl_td_net = pnl_td - commission
        rows.append({"trade_id": r.trade_id, "strategy": r.strategy_id,
                     "closed": "order" if order_closed else "expired",
                     "pnl_sim": round(r.pnl, 2), "pnl_td_gross": round(pnl_td, 2),
                     "commission_real": round(commission, 2), "pnl_td_net": round(pnl_td_net, 2),
                     "diff_vs_sim": round(pnl_td_net - r.pnl, 2)})
    d = pd.DataFrame(rows)
    out = SIM / f"td_pnl_reconstruct_{dt.datetime.now():%Y%m%d}.csv"
    d.to_csv(out, index=False)

    print(f"\ntrades reconstructed: {len(d)}  (skipped {miss} missing a fill quote)")
    print(f"  SIM booked P&L .............. ${d.pnl_sim.sum():>12,.2f}")
    print(f"  TD gross P&L (real fills) ... ${d.pnl_td_gross.sum():>12,.2f}")
    print(f"  real commissions ........... ${d.commission_real.sum():>12,.2f}")
    print(f"  TD NET P&L ................. ${d.pnl_td_net.sum():>12,.2f}")
    print(f"  vs sim (net - sim) ......... ${d.diff_vs_sim.sum():>12,.2f}")
    print("\n  by exit type:")
    for kind, g in d.groupby("closed"):
        print(f"    {kind:8} n={len(g):3}  sim=${g.pnl_sim.sum():>10,.0f}  "
              f"td_net=${g.pnl_td_net.sum():>10,.0f}  diff=${g.diff_vs_sim.sum():>9,.0f}")
    print(f"\nsaved -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
