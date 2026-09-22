"""check_fees_ib.py — ask IB for the ACTUAL commission on SPX vs XSP, instead of trusting
the desk's modeled $1.30/contract. Uses whatIfOrder (a pre-trade margin/commission preview
— places NOTHING) on a 1-lot option in each, and prints IB's estimated commission so we
know the real per-contract cost and the true fee drag on the mini.

Needs the gateway UP (weekday session). On a weekend 4002 is down — run it Monday.

    python scripts/check_fees_ib.py                       # near-ATM, nearest expiry
    python scripts/check_fees_ib.py --expiry 20260824
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
sys.path.insert(0, str(ROOT / "scripts"))


def _spx_spot():
    try:
        return float(json.loads((SIM / "live.json").read_text()).get("spx") or 7680)
    except Exception:
        return 7680.0


def _nearest_expiry(ib, symbol, tclass):
    """Nearest listed expiry for the option class (so this works any day)."""
    from ib_async import Index, Stock
    try:
        und = ib.qualifyContracts(Index(symbol, "CBOE", "USD"))[0]
        params = ib.reqSecDefOptParams(und.symbol, "", und.secType, und.conId)
        exps = sorted({e for p in params if p.tradingClass == tclass for e in p.expirations})
        today = dt.date.today().strftime("%Y%m%d")
        fut = [e for e in exps if e >= today]
        return fut[0] if fut else (exps[-1] if exps else None)
    except Exception as e:
        print(f"  ({symbol} expiry lookup failed: {e})")
        return None


def _commission(ib, symbol, tclass, strike, expiry):
    from ib_async import Option, LimitOrder
    o = ib.qualifyContracts(Option(symbol, expiry, strike, "C", "SMART", tradingClass=tclass))
    if not o or not o[0].conId:
        return None, f"could not qualify {symbol} {expiry} {strike}C"
    order = LimitOrder("BUY", 1, 0.05); order.whatIf = True   # preview only — places nothing
    st = ib.whatIfOrder(o[0], order)
    try:
        c = float(st.commission)
    except Exception:
        return None, f"{symbol}: no commission in whatIf ({st})"
    return c, f"{symbol} {tclass} {strike}C {expiry}: comm ${c:.4f} " \
              f"(min ${getattr(st,'minCommission','?')}/max ${getattr(st,'maxCommission','?')} {getattr(st,'commissionCurrency','')})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expiry", default=None)
    a = ap.parse_args()
    import ib_conn
    ib = ib_conn.connect(client_id=141)
    ib.reqMarketDataType(1)
    spot = _spx_spot()
    spx_k = round(spot / 5) * 5
    xsp_k = round(spot / 10)      # XSP ~ SPX/10, $1 grid
    spx_exp = a.expiry or _nearest_expiry(ib, "SPX", "SPXW")
    xsp_exp = a.expiry or _nearest_expiry(ib, "XSP", "XSP")
    print(f"SPX spot ~{spot:.0f} | SPX {spx_k}C exp {spx_exp} | XSP {xsp_k}C exp {xsp_exp}\n")

    cs, ms = _commission(ib, "SPX", "SPXW", spx_k, spx_exp) if spx_exp else (None, "no SPX expiry")
    cx, mx = _commission(ib, "XSP", "XSP", xsp_k, xsp_exp) if xsp_exp else (None, "no XSP expiry")
    print("PER-CONTRACT COMMISSION (1-lot BUY, whatIf — nothing placed):")
    print("  " + ms)
    print("  " + mx)
    if cs and cx:
        print(f"\n  SPX ${cs:.4f}/ct   XSP ${cx:.4f}/ct   ratio XSP/SPX = {cx/cs:.2f}")
        print(f"  a 2-leg spread costs ~SPX ${2*cs:.2f}  vs  XSP ${2*cx:.2f} per round-trip leg-set")
        print("  -> the true fee drag on the mini = XSP spread-fee / (SPX P&L / 10). Real number, not modeled.")
    ib.disconnect()


if __name__ == "__main__":
    main()
