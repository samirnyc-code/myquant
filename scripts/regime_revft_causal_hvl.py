"""RevFT, MY causal frame — resolve the RevFT-shorts-below-HVL question with the SAME causal
pipeline used for 2E (not the parallel session's inherited tag). Take RevFT signal timestamps
from the raw MyReversals export (CT, matches our bars), sim entry/exit in OUR 5-min bars, and
classify by OUR prior-day HVL (price vs prior-session HVL, ES frame). Then test:
  - RevFT SHORTS below HVL (does the +$102k survive a self-computed causal tag?)
  - BASELINE: 2E with-trend shorts below HVL at EOD (is RevFT better than 'just short below HVL'?)

Sim: entry = signal-bar close; stop = signal-bar extreme +/- 1pt buffer; EOD hold or stop.
$5 RT + 1t slip. 2021+.

  python scripts/regime_revft_causal_hvl.py
Output: data/regime/revft_causal_hvl_20260725.csv + tables.
"""
import re, sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; BUF = 1.0
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
SIG = WT / "data" / "signals" / "MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
GOODH = {9, 10, 11, 12, 13}


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def parse_signals():
    rows = []
    for ln in SIG.read_text().splitlines():
        m = re.match(r'\s*\d+\s+(\w+)\s+(Long|Short)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})\s+\d+', ln)
        if m:
            typ, dr, dt, tm = m.groups()
            rows.append((pd.to_datetime(dt + " " + tm, dayfirst=True), dr, typ))
    d = pd.DataFrame(rows, columns=["sigdt", "dir", "type"])
    return d[d.sigdt.dt.year >= 2021].reset_index(drop=True)


def main():
    sig = parse_signals()
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["Date"] = b["DateTime"].dt.date.astype(str)
    bybar = {ts: i for i, ts in enumerate(b["DateTime"].values)}
    O, H, L, C = b.Open.values, b.High.values, b.Low.values, b.Close.values
    dt = b["DateTime"].values; dates = b["Date"].values
    # session end index per date
    last_idx = b.groupby("Date").apply(lambda x: x.index[-1]).to_dict()

    rows = []
    for _, s in sig.iterrows():
        ts = np.datetime64(s.sigdt)
        i = bybar.get(ts)
        if i is None or s.sigdt.hour not in GOODH:
            continue
        short = s.dir == "Short"
        entry = C[i]
        stop = (H[i] + BUF) if short else (L[i] - BUF)
        stopd = abs(stop - entry)
        if stopd < 2 * TICK:
            continue
        end = last_idx[dates[i]]
        net = None
        for j in range(i + 1, end + 1):
            if (H[j] >= stop) if short else (L[j] <= stop):
                ex = stop; net = ((entry - ex) if short else (ex - entry)) * PT - COMM - SLIP; break
        if net is None:
            ex = C[end]; net = ((entry - ex) if short else (ex - entry)) * PT - COMM - SLIP
        rows.append({"Date": dates[i], "yr": s.sigdt.year, "dir": s.dir, "type": s.type,
                     "entry_px": round(float(entry), 2), "net": round(net, 1)})
    d = pd.DataFrame(rows)

    # MY causal prior-day HVL (same as 2E)
    esc = b.groupby("Date").agg(es_close=("Close", "last"))
    mq = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"); mq["date"] = mq["date"].astype(str)
    dd = mq[["date", "spot", "hvl"]].rename(columns={"date": "Date", "spot": "spx"}).set_index("Date").join(esc, how="inner").sort_index()
    dd["prior_hvl_es"] = (dd.hvl + (dd.es_close - dd.spx)).shift(1)
    d = d.merge(dd[["prior_hvl_es"]], left_on="Date", right_index=True, how="left")
    d = d[d.prior_hvl_es.notna()]; d["below"] = d.entry_px < d.prior_hvl_es
    d.to_csv(WT / "data" / "regime" / "revft_causal_hvl_20260725.csv", index=False)

    print(f"RevFT simmed in OUR frame, MY causal HVL tag: {len(d)} trades (2021+)\n")
    print("=== RevFT SHORTS, below vs above HVL (MY causal classification) ===")
    sh = d[d.dir == "Short"]
    print(f"  below HVL: n={len(sh[sh.below]):4d} PF {pf(sh[sh.below].net):.2f} net ${sh[sh.below].net.sum():+,.0f} $/yr ${sh[sh.below].net.sum()/5.5:+,.0f}")
    print(f"  above HVL: n={len(sh[~sh.below]):4d} PF {pf(sh[~sh.below].net):.2f} net ${sh[~sh.below].net.sum():+,.0f}")
    print(f"  LONGS below HVL: n={len(d[(d.dir=='Long')&d.below]):4d} PF {pf(d[(d.dir=='Long')&d.below].net):.2f} net ${d[(d.dir=='Long')&d.below].net.sum():+,.0f}")
    print("\n  RevFT shorts below HVL by year:")
    sb = sh[sh.below]
    for y in range(2021, 2027):
        x = sb[sb.yr == y]
        if len(x): print(f"    {y}: n={len(x):3d} PF {pf(x.net):.2f} net ${x.net.sum():+,.0f}")
    print("\n  by type (shorts below HVL):")
    for t, g in sb.groupby("type"):
        print(f"    {t:8s}: n={len(g):3d} PF {pf(g.net):.2f} net ${g.net.sum():+,.0f}")

    # BASELINE: 2E with-trend shorts below HVL at EOD (is RevFT better than any-short-below-HVL?)
    e = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    e = e[(e.with_trend) & (e.dir == "S") & e.fill_hour.astype(int).isin(GOODH)].copy()
    S = np.maximum(np.round(0.30 * e.adr.values / TICK) * TICK, 8 * TICK)
    mv = np.where(e.mae_pts.values >= S, -S, e.eod_move.values); e["net"] = mv * PT - COMM - SLIP
    e = e.merge(dd[["prior_hvl_es"]], left_on="Date", right_index=True, how="left")
    e = e[(e.prior_hvl_es.notna()) & (e.yr >= 2021) & (e.entry_px < e.prior_hvl_es)]
    print(f"\n=== BASELINE: 2E with-trend SHORTS below HVL, EOD (a no-RevFT short) ===")
    print(f"  n={len(e)} PF {pf(e.net):.2f} net ${e.net.sum():+,.0f} $/yr ${e.net.sum()/5.5:+,.0f}")
    print("  -> if RevFT-short >> this, RevFT adds alpha; if ~same, it's just 'short below HVL'.")


if __name__ == "__main__":
    main()
