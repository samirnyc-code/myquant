"""VIX/SPX same-day divergence study (2026-08-05).

Question (from the 08-04 evening read): SPX closed +1.79% while VIX rose +4.04%
— "rallying with one hand, buying insurance with the other." When did this last
happen, how often does it happen, and what did SPX do next?

Event definition: SPX day return >= +1.5% AND VIX day change >= +2%.
(Also reports the looser >= +1.0% / VIX up variant for context.)

Data: ^GSPC + ^VIX daily via yfinance, 1990 -> today.
Output: data/options_sim/vix_spx_divergence_20260805.csv + printed tables.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_sim" / "vix_spx_divergence_20260805.csv"


def main():
    px = yf.download(["^GSPC", "^VIX"], start="1990-01-01", progress=False,
                     auto_adjust=False)["Close"].dropna()
    px.columns = ["SPX", "VIX"]
    r = pd.DataFrame({
        "spx_ret": px.SPX.pct_change() * 100,
        "vix_chg": px.VIX.pct_change() * 100,
    }, index=px.index).dropna()
    for h in (1, 5, 10):
        r[f"fwd{h}"] = px.SPX.pct_change(h).shift(-h) * 100

    def study(name, mask):
        ev = r[mask]
        print(f"\n=== {name}: n={len(ev)} ({len(ev)/len(r)*100:.2f}% of days) ===")
        if not len(ev):
            return ev
        print("last 10 occurrences:")
        for d, row in ev.tail(10).iterrows():
            print(f"  {d:%Y-%m-%d}  SPX {row.spx_ret:+.2f}%  VIX {row.vix_chg:+.1f}%  "
                  f"-> next1 {row.fwd1:+.2f}%  next5 {row.fwd5:+.2f}%  next10 {row.fwd10:+.2f}%")
        base = r
        print(f"{'horizon':8}{'event mean':>12}{'event med':>11}{'%pos':>7}{'baseline mean':>15}")
        for h in (1, 5, 10):
            e = ev[f"fwd{h}"].dropna()
            b = base[f"fwd{h}"].dropna()
            print(f"  next{h:<4}{e.mean():>+11.2f}%{e.median():>+10.2f}%{(e > 0).mean()*100:>6.0f}%"
                  f"{b.mean():>+14.2f}%")
        return ev

    strict = study("SPX >= +1.5% AND VIX >= +2% (today's shape)",
                   (r.spx_ret >= 1.5) & (r.vix_chg >= 2.0))
    study("looser: SPX >= +1.0% AND VIX up",
          (r.spx_ret >= 1.0) & (r.vix_chg > 0))
    strict.to_csv(OUT)
    print(f"\nevents -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
