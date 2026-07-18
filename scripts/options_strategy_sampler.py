"""Execute ONE labeled paper trade per strategy family (S73 structure test).

Purpose: prove every structure the playbook mentions executes, labels, and logs
correctly END-TO-END — BPS, iron condor, straddle, butterfly, bear call spread,
bull call debit spread, put calendar. Parameters today are deliberately loose
(user: "they don't need to follow any parameters"); each trade carries honest
commentary, a setup grade, max gain/loss from the expiry payoff, and an
IV-lognormal probability of profit (POP).

Run:  .venv/Scripts/python.exe scripts/options_strategy_sampler.py
"""
import datetime as dt
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
import options_trade_log as tlog
from ib_order_test import marketable
from options_manual_trade import qualify
from options_sim_daemon import SpotRig, get_chain, rough_spot

ET = ZoneInfo("America/New_York")
FEE = 1.30


def now():
    return dt.datetime.now(ET)


def payoff_metrics(legs, spot, iv, t_years):
    """legs: [{side, right, strike, qty, fill}] — same expiry.
    Expiry P&L grid -> max gain/loss ($) and lognormal POP."""
    grid = np.unique(np.concatenate([np.arange(spot * 0.75, spot * 1.25, 1.0),
                                     [l["strike"] for l in legs]]))

    def pnl(S):
        v = 0.0
        for l in legs:
            intr = max(0.0, (S - l["strike"]) if l["right"] == "C" else (l["strike"] - S))
            v += l["qty"] * ((l["fill"] - intr) if l["side"] == "sell" else (intr - l["fill"]))
        return v * 100

    vals = np.array([pnl(S) for S in grid])
    sig = max(iv, 0.05) * math.sqrt(max(t_years, 1e-5))
    z = (np.log(grid / spot) + sig * sig / 2) / sig
    pdf = np.exp(-z * z / 2) / (sig * grid)          # lognormal density (unnormalized ok)
    w = pdf / pdf.sum()
    pop = float(w[vals > 0].sum())
    return float(vals.max()), float(vals.min()), pop


def exec_legs(ib, ib_legs):
    """ib_legs: [(contract, action, qty)]. Fills each; returns legs w/ fill prices + IVs."""
    out, ivs = [], []
    for c, action, qty in ib_legs:
        q = ib.reqMktData(c, "", snapshot=False)
        ib.sleep(6)
        px = q.ask if action == "BUY" else q.bid
        if not (px == px and px > 0):
            raise SystemExit(f"no quote on {c.strike}{c.right} {c.lastTradeDateOrContractMonth}")
        if q.modelGreeks and q.modelGreeks.impliedVol and q.modelGreeks.impliedVol == q.modelGreeks.impliedVol:
            ivs.append(q.modelGreeks.impliedVol)
        tr = marketable(ib, c, action, qty, px)
        if tr.orderStatus.status != "Filled":
            raise SystemExit(f"leg {action} {c.strike}{c.right} not filled — resolve in Gateway")
        out.append({"side": "sell" if action == "SELL" else "buy", "right": c.right,
                    "strike": float(c.strike), "expiry": c.lastTradeDateOrContractMonth,
                    "qty": qty, "fill": float(tr.orderStatus.avgFillPrice)})
    return out, (float(np.median(ivs)) if ivs else 0.12)


def book(name, structure, legs, iv, spot, commentary, grade, multi_expiry=False):
    net = sum(l["qty"] * (l["fill"] if l["side"] == "sell" else -l["fill"]) for l in legs)
    exp_near = min(l["expiry"] for l in legs)
    dte = (dt.datetime.strptime(exp_near, "%Y%m%d").date() - now().date()).days
    if multi_expiry:
        mx_g, mx_l, pop = None, -abs(min(net, 0)) * 100 or -abs(net) * 100, None
        mx_l = -abs(net) * 100 if net < 0 else None   # debit calendar: risk = debit
    else:
        t = max((16 - now().hour) + (0 - now().minute) / 60, 0.5) / (24 * 365) if dte == 0 else dte / 365
        mx_g, mx_l, pop = payoff_metrics(legs, spot, iv, t)
    n_contracts = sum(l["qty"] for l in legs)
    tid = f"{name}_{now():%Y%m%d_%H%M}"
    tlog.append_entry({
        "trade_id": tid, "strategy_id": name, "source": "paper", "symbol": "SPXW",
        "entry_dt": now().strftime("%Y-%m-%d %H:%M"), "dte": dte, "structure": structure,
        "fill_model": "paper_fill", "legs": legs, "credit": net,
        "collateral": abs(mx_l) if mx_l else abs(net) * 100,
        "commentary": commentary, "grade": grade,
        "max_gain": mx_g, "max_loss": mx_l, "pop": round(pop, 3) if pop is not None else None,
        "dow": now().strftime("%a"),
    })
    print(f"\nLOGGED {tid}: net {'credit' if net > 0 else 'debit'} {abs(net):.2f}, "
          f"maxG {mx_g if mx_g is None else f'${mx_g:,.0f}'} maxL {mx_l if mx_l is None else f'${mx_l:,.0f}'} "
          f"POP {pop if pop is None else f'{pop:.0%}'}  [{grade}]  fees ~${2 * n_contracts * FEE:.2f}")
    return tid


def r5(x):
    return round(x / 5) * 5


def main():
    ib = ib_conn.connect()
    try:
        ib.errorEvent += lambda reqId, code, msg, *a: None  # quiet the 10090 spam
        spx, rough = rough_spot(ib)
        chain = get_chain(ib, spx)
        rig = SpotRig(ib, chain, rough)
        ib.sleep(3)
        spot = rig.spot() or rough
        S = r5(spot)
        today = now().strftime("%Y%m%d")
        exp0 = min(e for e in chain.expirations if e >= today)
        expw = sorted(e for e in chain.expirations if e > exp0)[2]     # a few days out
        exp14 = min(chain.expirations, key=lambda e: abs(
            (dt.datetime.strptime(e, "%Y%m%d").date() - now().date()).days - 14))
        print(f"parity spot {spot:.2f} (S={S})  expiries: 0DTE {exp0}, wk {expw}, 14d {exp14}")
        ib.reqMarketDataType(1)
        Q = lambda e, k, r: qualify(ib, e, k, r)

        # 1. BPS — the flagship structure, off-signal today
        # (executed 2026-07-14 via recovery snippet after the limit-band reject; rerun with --with-bps)
        if "--with-bps" in sys.argv:
            legs, iv = exec_legs(ib, [(Q(exp14, S - 95, "P"), "SELL", 1), (Q(exp14, S - 145, "P"), "BUY", 1)])
            book("bps_stmr", "bull put spread 50pt 14DTE", legs, iv, spot,
                 "Flagship BPS structure WITHOUT its STMR trigger (K8~59 at entry, not oversold; C>SMA100 ok). "
                 "Pure execution/labeling test. Expectation: theta decay while SPX holds above the short put; "
                 "high POP but NO validated edge off-signal.", "C")

        # 2. Iron condor 0DTE inside the gamma walls (BUY wings first — naked-short margin rejects)
        if "--with-condor" in sys.argv:
            legs, iv = exec_legs(ib, [(Q(exp0, S - 85, "P"), "BUY", 1), (Q(exp0, S + 80, "C"), "BUY", 1),
                                      (Q(exp0, S - 60, "P"), "SELL", 1), (Q(exp0, S + 55, "C"), "SELL", 1)])
            book("condor_0dte", "iron condor 25pt wings 0DTE", legs, iv, spot,
                 "Positive-gamma day (spot above HVL 7495) favors pinning; short strikes sit inside the "
                 "PS0 7475 / CR0 7550-7600 walls. Expectation: both sides decay to worthless by 16:00. "
                 "Playbook §2 warns condors underperform plain BPS on STMR days — but today is a pin test.", "B-")

        # 3. Long straddle 0DTE ATM
        if "--with-straddle" in sys.argv:
            legs, iv = exec_legs(ib, [(Q(exp0, S, "C"), "BUY", 1), (Q(exp0, S, "P"), "BUY", 1)])
            book("straddle_0dte", "long ATM straddle 0DTE", legs, iv, spot,
                 "Long vol on a VIX-15, positive-gamma pin day is COUNTER-regime — taken to test debit/"
                 "two-right execution. Expectation: needs a move beyond the breakevens by 16:00; unlikely; "
                 "this is the trade the regime framework says NOT to take.", "C-")

        # 4. Call butterfly pinned on the 0DTE Gamma Wall (wings first)
        if "--with-fly" in sys.argv:
            legs, iv = exec_legs(ib, [(Q(exp0, 7525, "C"), "BUY", 1), (Q(exp0, 7575, "C"), "BUY", 1),
                                      (Q(exp0, 7550, "C"), "SELL", 2)])
            book("fly_gw_0dte", "call butterfly 25pt @ GW 7550", legs, iv, spot,
             "Pin play centered EXACTLY on the MenthorQ 0DTE Gamma Wall 7550 (our IB calc: 7525 — 1 strike "
             "off). Expectation: max value if SPX settles near 7550 at 16:00; cheap defined risk. The most "
             "regime-aligned trade of the batch.", "B")

        # 5. Bear call spread at Call Resistance (wing first)
        legs, iv = exec_legs(ib, [(Q(exp0, 7625, "C"), "BUY", 1), (Q(exp0, 7600, "C"), "SELL", 1)])
        book("bcs_cr_0dte", "bear call spread 25pt @ CR 7600", legs, iv, spot,
             "Short call spread AT Call Resistance 7600 — the one level where our IB computation matched "
             "MenthorQ exactly. ~60pts OTM with hours left on a positive-gamma day. Expectation: expires "
             "worthless unless a melt-up through the wall. S66 caveat: walls hold ~50% once TOUCHED.", "B+")

        # 6. Bull call debit spread, weekly — momentum
        legs, iv = exec_legs(ib, [(Q(expw, S, "C"), "BUY", 1), (Q(expw, S + 50, "C"), "SELL", 1)])
        book("bull_cs_wk", f"bull call spread 50pt {expw}", legs, iv, spot,
             "Momentum continuation: SPX +20 today, buying the weekly 50pt call spread. No validated signal "
             "— chasing strength, which the playbook has never tested. Expectation: SPX above the long "
             "strike by expiry.", "C+")

        # 7. Put calendar — multi-expiry handling test (long leg first)
        legs, iv = exec_legs(ib, [(Q(expw, S, "P"), "BUY", 1), (Q(exp0, S, "P"), "SELL", 1)])
        book("put_cal_wk", f"put calendar {exp0}/{expw}", legs, iv, spot,
             "ATM put calendar: short 0DTE leg decays fastest; long weekly retains vega. Tests multi-expiry "
             "legs in the log (payoff/POP not defined at a single expiry — risk = net debit). Expectation: "
             "small gain if SPX sits near the strike at 16:00.", "C", multi_expiry=True)

        print("\n" + tlog.summary())
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
