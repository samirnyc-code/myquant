"""1D-band 0DTE iron-condor backtest (S75) — turn the 75.7% close-in-band hit-rate
into real option P&L on OptionsDX SPX chains.

Setup per trade day T:
  bands  = MenthorQ d1_min / d1_max published at T-1 EOD (SPX_mq_levels_history.csv)
  entry  = SELL the call spread with short strike at 1D Max, SELL the put spread with
           short strike at 1D Min, wings `WING` pts out. Priced from OptionsDX
           quote_date=T-1, expire=T (1DTE ~ next-morning proxy). Sell shorts at BID,
           buy longs at ASK (conservative).
  settle = SPX close on T (intrinsic). P&L = (credit - short-spread intrinsics) x 100.
Causal: bands + entry chain both known at T-1 close; no look-ahead.
"""
import glob
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path("C:/Users/Admin/myquant")
WING = 50            # spread width (pts)
_cache = {}


def load_month(ym):
    if ym in _cache:
        return _cache[ym]
    f = ROOT / "data" / "optionsdx" / f"spx_eod_{ym}.txt"
    if not f.exists():
        _cache[ym] = None
        return None
    df = pd.read_csv(f)
    df.columns = [c.strip().strip("[]").upper() for c in df.columns]
    for c in ("QUOTE_DATE", "EXPIRE_DATE"):
        df[c] = df[c].astype(str).str.strip()
    for c in ("STRIKE", "UNDERLYING_LAST", "C_BID", "C_ASK", "P_BID", "P_ASK"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    _cache[ym] = df
    return df


def leg_price(chain, strike, col):
    r = chain[chain.STRIKE == strike]
    if not len(r):
        return None
    v = r.iloc[0][col]
    return v if v == v and v > 0 else None


def main():
    lv = pd.read_csv(ROOT / "data/menthorq/SPX_mq_levels_history.csv")
    lv = lv[["session_date", "spot_eod", "d1_min", "d1_max", "hvl"]].dropna(subset=["d1_min", "d1_max"])
    lv["session_date"] = pd.to_datetime(lv["session_date"])
    lv = lv.sort_values("session_date").reset_index(drop=True)

    trades = []
    skipped = {"no_month": 0, "no_chain": 0, "no_legs": 0, "no_settle": 0}
    for i in range(len(lv) - 1):
        entry_row, settle_row = lv.iloc[i], lv.iloc[i + 1]
        qd = entry_row.session_date            # entry EOD (bands published here)
        T = settle_row.session_date            # trade/expiry day
        qd_s, T_s = qd.strftime("%Y-%m-%d"), T.strftime("%Y-%m-%d")
        dmax, dmin = entry_row.d1_max, entry_row.d1_min
        close = settle_row.spot_eod            # SPX close on T
        if close != close:
            skipped["no_settle"] += 1
            continue
        ch = load_month(qd.strftime("%Y%m"))
        if ch is None:
            skipped["no_month"] += 1
            continue
        chain = ch[(ch.QUOTE_DATE == qd_s) & (ch.EXPIRE_DATE == T_s)]
        if not len(chain):
            skipped["no_chain"] += 1
            continue
        strikes = sorted(chain.STRIKE.dropna().unique())
        if not strikes:
            skipped["no_chain"] += 1
            continue
        # short strikes at the bands (call short >= 1D Max, put short <= 1D Min)
        sc = min((s for s in strikes if s >= dmax), default=None)
        sp = max((s for s in strikes if s <= dmin), default=None)
        if sc is None or sp is None:
            skipped["no_legs"] += 1
            continue
        lc, lp = sc + WING, sp - WING
        legs = {"sc": leg_price(chain, sc, "C_BID"), "lc": leg_price(chain, lc, "C_ASK"),
                "sp": leg_price(chain, sp, "P_BID"), "lp": leg_price(chain, lp, "P_ASK")}
        if any(v is None for v in legs.values()):
            skipped["no_legs"] += 1
            continue
        credit = legs["sc"] - legs["lc"] + legs["sp"] - legs["lp"]
        if credit <= 0:
            skipped["no_legs"] += 1
            continue
        call_intr = max(0.0, close - sc) - max(0.0, close - lc)
        put_intr = max(0.0, sp - close) - max(0.0, lp - close)
        pnl = (credit - call_intr - put_intr) * 100
        pos_gamma = bool(entry_row.spot_eod >= entry_row.hvl) if entry_row.hvl == entry_row.hvl else None
        trades.append(dict(date=T_s, close=close, dmin=dmin, dmax=dmax, sc=sc, sp=sp,
                           credit=round(credit, 2), pnl=round(pnl, 2),
                           win=pnl > 0, in_band=(dmin <= close <= dmax), pos_gamma=pos_gamma))

    if not trades:
        print("NO TRADES. skipped:", skipped)
        return
    df = pd.DataFrame(trades)
    n = len(df)
    wins = df.pnl > 0
    gross_w = df.pnl[wins].sum()
    gross_l = -df.pnl[~wins].sum()
    pf = gross_w / gross_l if gross_l else float("inf")
    print(f"=== 1D-band 0DTE iron condor (WING={WING}) ===")
    print(f"trades         : {n}   ({df.date.min()} -> {df.date.max()})")
    print(f"win rate       : {wins.mean()*100:.1f}%   (close-in-band {df.in_band.mean()*100:.1f}%)")
    print(f"total P&L      : ${df.pnl.sum():,.0f}")
    print(f"avg / trade    : ${df.pnl.mean():,.0f}    median ${df.pnl.median():,.0f}")
    print(f"avg credit     : ${df.credit.mean()*100:,.0f}   avg win ${df.pnl[wins].mean():,.0f}   avg loss ${df.pnl[~wins].mean():,.0f}")
    print(f"profit factor  : {pf:.2f}")
    print(f"worst trade    : ${df.pnl.min():,.0f}   best ${df.pnl.max():,.0f}")
    print(f"skipped        : {skipped}")
    df.to_csv(ROOT / "scratchpad" / "condor_1dband_trades.csv", index=False)

    def stats(sub, label):
        if not len(sub):
            print(f"{label:26} n=0"); return
        w = sub.pnl > 0
        gl = -sub.pnl[~w].sum()
        pf = (sub.pnl[w].sum() / gl) if gl else float("inf")
        print(f"{label:26} n={len(sub):4}  win {w.mean()*100:4.0f}%  total ${sub.pnl.sum():>9,.0f}  "
              f"avg ${sub.pnl.mean():>6,.0f}  PF {pf:.2f}")

    print("\n=== REGIME SPLIT (Option Matrix: sell condors only in +gamma) ===")
    stats(df, "ALL")
    stats(df[df.pos_gamma == True], "  +gamma (spot>=HVL)")
    stats(df[df.pos_gamma == False], "  -gamma (spot< HVL)")
    df["year"] = df.date.str[:4]
    print("\n=== BY YEAR ===")
    for y, sub in df.groupby("year"):
        stats(sub, f"  {y}")


if __name__ == "__main__":
    main()
