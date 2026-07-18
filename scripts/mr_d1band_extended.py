"""1D expected-move band tests on the TRIPLED sample (S73): 628 self-computed
days 2021-07..2023-12 (IV-based bands — valid under volume-proxy limitations).

A. Verify MenthorQ's published claims (their def, daily closes, no conversion):
   close < 1D Max ~85% ; close > 1D Min ~87% ; both hold ~73%.
B. Intraday first-touch fades of the bands on ES 5M (repaired bars), converting
   SPX-scale bands to ES with the per-day measured basis (Yahoo ES=F - ^GSPC).
   Same gauntlet: sweep cells+, ref stop8/tgt10, OOS 1/3.
"""
import datetime as dt
import json
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
STOPS = [3, 4, 5, 6, 8, 10]
TGTS = [6, 8, 10, 12, 15, 20]
FRIC = 1.25


def yahoo_daily(tkr, enc):
    req = urllib.request.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?range=10y&interval=1d",
        headers={"User-Agent": "Mozilla/5.0"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    return pd.DataFrame({"date": [dt.datetime.fromtimestamp(t, ET).date().isoformat()
                                  for t in r["timestamp"]],
                         tkr: q["close"]}).dropna()


def main():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_computed_SPX.csv")
    lv["date"] = lv.date.astype(str)
    lv = lv.dropna(subset=["d1_min", "d1_max"])

    # ---- A. daily-close verification of MQ's published claims ----
    spx = yahoo_daily("SPX", "%5EGSPC").rename(columns={"SPX": "close"})
    m = lv.merge(spx, on="date", how="inner")
    # band computed FROM day d's chain applies to day d+1 (forward-looking daily move)
    m["next_close"] = m.close.shift(-1)
    m = m.dropna(subset=["next_close"])
    below_max = (m.next_close < m.d1_max).mean() * 100
    above_min = (m.next_close > m.d1_min).mean() * 100
    inside = ((m.next_close < m.d1_max) & (m.next_close > m.d1_min)).mean() * 100
    print(f"A. Daily-close band verification (n={len(m)}, 2021-07..2023-12, next-day close vs band):")
    print(f"   close < 1D Max: {below_max:.1f}%   (MQ claim ~85%)")
    print(f"   close > 1D Min: {above_min:.1f}%   (MQ claim ~87%)")
    print(f"   inside band   : {inside:.1f}%   (MQ claim ~73%)")

    # ---- B. intraday first-touch fades on ES ----
    es = yahoo_daily("ES", "ES%3DF").rename(columns={"ES": "es_close"})
    basis = spx.merge(es, on="date", how="inner")
    basis["basis"] = basis.es_close - basis.close
    basis["basis_s"] = basis.basis.rolling(5, center=True, min_periods=1).median()
    bmap = dict(zip(basis.date, basis.basis_s))

    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")

    # levels of day d apply to session d+1: shift level dates forward one trading day
    lv2 = lv.sort_values("date").reset_index(drop=True)
    trade_dates = sorted(set(b.date))
    nxt = {}
    for d in lv2.date:
        later = [x for x in trade_dates if x > d]
        if later:
            nxt[d] = later[0]
    lv2["session"] = lv2.date.map(nxt)
    lv2 = lv2.dropna(subset=["session"])

    for col, kind in [("d1_max", "res"), ("d1_min", "sup")]:
        ents = []
        for r in lv2.itertuples():
            d = r.session
            if d not in bmap or not np.isfinite(getattr(r, col)):
                continue
            lvl = getattr(r, col) + bmap[d]           # SPX-scale -> ES-scale
            day = b[b.date == d].reset_index(drop=True)
            if len(day) < 10:
                continue
            H, L, Cl = day.High.values, day.Low.values, day.Close.values
            for i in range(1, len(day)):
                k = max(0, i - 3)
                ok = (np.max(Cl[k:i]) < lvl - 0.5) if kind == "res" else (np.min(Cl[k:i]) > lvl + 0.5)
                if ok and (L[i] - 1.0) <= lvl <= (H[i] + 1.0):
                    ents.append((d, day, lvl, i))
                    break

        def pnl(day, lvl, ti, s, t):
            H, L, Cl = day.High.values, day.Low.values, day.Close.values
            for j in range(ti + 1, len(day)):
                if kind == "res":
                    if H[j] >= lvl + s:
                        return -s - FRIC
                    if L[j] <= lvl - t:
                        return t - FRIC
                else:
                    if L[j] <= lvl - s:
                        return -s - FRIC
                    if H[j] >= lvl + t:
                        return t - FRIC
            raw = (lvl - Cl[-1]) if kind == "res" else (Cl[-1] - lvl)
            return raw - FRIC

        if len(ents) < 20:
            print(f"\nB. {col}: only {len(ents)} entries — skip")
            continue
        pos = sum((np.mean([pnl(day, lvl, ti, s, t) for _, day, lvl, ti in ents]) > 0)
                  for s in STOPS for t in TGTS)
        pref = np.array([pnl(day, lvl, ti, 8, 10) for _, day, lvl, ti in ents])
        dates = [d for d, *_ in ents]
        cut = sorted(dates)[int(len(dates) * 0.66)]
        isp = np.array([pnl(day, lvl, ti, 8, 10) for d, day, lvl, ti in ents if d <= cut])
        oos = np.array([pnl(day, lvl, ti, 8, 10) for d, day, lvl, ti in ents if d > cut])
        yrs = pd.Series([d[:4] for d in dates]).value_counts().sort_index()
        print(f"\nB. {col} first-touch fade ({'short' if kind == 'res' else 'long'}), "
              f"2021-07..2023-12 ES:")
        print(f"   n {len(ents)} ({dict(yrs)})  cells+ {pos}/36  "
              f"ref E ${pref.mean() * 50:+.0f} win {(pref > 0).mean() * 100:.0f}%  "
              f"total ${pref.sum() * 50:+,.0f}")
        print(f"   IS ${isp.mean() * 50:+.0f} -> OOS ${oos.mean() * 50:+.0f}")


if __name__ == "__main__":
    main()
