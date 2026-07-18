"""S75Q — two tests against MenthorQ ground truth.

TEST 1  Does MQ's CR/PS come from a NET-signed gamma profile or a TOTAL
        (unsigned) one?  We rebuild both from the ORATS chain and score each
        against MQ's published cr/ps over every overlapping session.

TEST 2  Label every session into the four Options-Matrix quadrants
        (sign of net GEX x sign of net DEX) and measure what actually
        happened next: realised range, close-to-close drift, and whether a
        prior-day-range breakout followed through.

Nothing here is a signal.  It is a base-rate table for a vendor claim.
"""
import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROF_SPAN = 0.10          # same near-spot window the slide deck uses


def chain():
    """Per-session strike profiles + aggregate GEX/DEX, from the ORATS chain."""
    rows, prof_net, prof_tot = [], {}, {}
    for f in sorted(glob.glob(str(ROOT / "data" / "orats" / "SPX" / "SPX_*.parquet"))):
        yr = pd.read_parquet(f)
        for c in ["strike", "gamma", "delta", "callOpenInterest",
                  "putOpenInterest", "dte", "spotPrice"]:
            yr[c] = pd.to_numeric(yr[c], errors="coerce")
        # identical hygiene filter to orats_levels_slides.py so the comparison
        # isolates the net-vs-total choice and nothing else
        yr = yr[(yr.dte > 1) & (yr.gamma.abs() < 0.1) & (yr.delta.abs() <= 1.01)]
        for d, g in yr.groupby("tradeDate"):
            d = str(d)[:10]
            spot = g["spotPrice"].median()
            if not np.isfinite(spot):
                continue
            net = (g.gamma * (g.callOpenInterest - g.putOpenInterest)).groupby(g.strike).sum()
            tot = (g.gamma * (g.callOpenInterest + g.putOpenInterest)).groupby(g.strike).sum()
            net, tot = net[np.isfinite(net)], tot[np.isfinite(tot)]
            if net.empty:
                continue
            lo, hi = spot * (1 - PROF_SPAN), spot * (1 + PROF_SPAN)
            prof_net[d] = net[(net.index >= lo) & (net.index <= hi)]
            prof_tot[d] = tot[(tot.index >= lo) & (tot.index <= hi)]
            # put delta = call delta - 1 (ORATS ships the call delta)
            dex = float((g.delta * g.callOpenInterest
                         + (g.delta - 1.0) * g.putOpenInterest).sum())
            rows.append({"date": d, "spot": float(spot),
                         "gex": float(net.sum()), "dex": dex})
    return pd.DataFrame(rows).set_index("date"), prof_net, prof_tot


def test1(prof_net, prof_tot, mq):
    """Score net vs total at reproducing MQ's published CR and PS strikes."""
    out = []
    for d, m in mq.iterrows():
        if d not in prof_net or not np.isfinite(m.get("cr", np.nan)):
            continue
        n, t = prof_net[d], prof_tot[d]
        if n.empty or t.empty:
            continue
        out.append({
            "date": d,
            "net_cr_err": abs(float(n.idxmax()) - m.cr),
            "net_ps_err": abs(float(n.idxmin()) - m.ps),
            # total is unsigned: its max is the biggest wall, and the best
            # available PS analogue is the largest wall below spot
            "tot_cr_err": abs(float(t.idxmax()) - m.cr),
            "tot_ps_err": abs(float(t[t.index < m.spot_eod].idxmax()) - m.ps)
            if np.isfinite(m.get("spot_eod", np.nan))
            and not t[t.index < m.spot_eod].empty else np.nan,
        })
    return pd.DataFrame(out)


def test2(agg, spx):
    """Quadrant base rates: what follows each GEX/DEX sign combination."""
    df = agg.join(spx, how="inner").sort_index()
    df["rng"] = (df.High - df.Low) / df.Close.shift(1) * 100      # realised range %
    df["ret"] = df.Close.pct_change() * 100
    df["prior_hi"], df["prior_lo"] = df.High.shift(1), df.Low.shift(1)
    # breakout = took out prior day's range; follow-through = closed beyond it
    up = df.High > df.prior_hi
    dn = df.Low < df.prior_lo
    df["bo"] = up | dn
    df["bo_ft"] = np.where(up & ~dn, df.Close > df.prior_hi,
                   np.where(dn & ~up, df.Close < df.prior_lo, np.nan))
    # regime is known at the prior close, so it must be lagged one session
    df["q"] = np.where(df.gex.shift(1) > 0,
                np.where(df.dex.shift(1) > 0, "1 +GEX/+DEX", "2 +GEX/-DEX"),
                np.where(df.dex.shift(1) > 0, "3 -GEX/+DEX", "4 -GEX/-DEX"))
    g = df.dropna(subset=["rng", "ret"]).groupby("q")
    return pd.DataFrame({
        "n": g.size(),
        "range_%": g.rng.mean().round(2),
        "ret_%": g.ret.mean().round(3),
        "up_day_%": (g.ret.apply(lambda s: (s > 0).mean()) * 100).round(1),
        "breakout_%": (g.bo.mean() * 100).round(1),
        "bo_followthru_%": (g.bo_ft.mean() * 100).round(1),
    })


def main():
    agg, prof_net, prof_tot = chain()
    mq = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
    mq["session_date"] = mq.session_date.astype(str).str[:10]
    mq = mq.set_index("session_date")

    t1 = test1(prof_net, prof_tot, mq)
    print(f"\n=== TEST 1  net vs total GEX vs MenthorQ ({len(t1)} sessions) ===")
    for c in ["net_cr_err", "tot_cr_err", "net_ps_err", "tot_ps_err"]:
        s = t1[c].dropna()
        print(f"  {c:12s}  median {s.median():7.1f}  mean {s.mean():8.1f} "
              f" exact {100 * (s == 0).mean():5.1f}%  within25 {100 * (s <= 25).mean():5.1f}%")

    spx = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
    spx["Date"] = spx.Date.astype(str).str[:10]
    spx = spx.set_index("Date")[["High", "Low", "Close"]].apply(pd.to_numeric, errors="coerce")
    print(f"\n=== TEST 2  Options-Matrix quadrant base rates ===")
    print(test2(agg, spx).to_string())

    t1.to_csv(ROOT / "data" / "options_sim" / "gex_net_vs_total.csv", index=False)


if __name__ == "__main__":
    main()
