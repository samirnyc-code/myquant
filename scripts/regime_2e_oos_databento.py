"""OOS RUN — the PHASE-gate with-trend 2E book on the Databento 1-min backfill, 2010-2026.

The tick-proxy fidelity test (regime_2e_tickproxy_fidelity.py) validated that 1-min pseudo-ticks
reproduce the tick engine (99.89% label agreement, book PF 1.35 vs 1.45, mildly pessimistic).
This runs that SAME proxy book on the Databento panama-rolled 1-min frames (built by
databento_build_continuous_1m.py, seam-checked corr 0.99987 vs our NT series on 2021-26):

  PRE-2021 (2010-06 -> 2020-12) = TRUE OUT-OF-SAMPLE — never seen by any fit/holdout.
  2021+                          = consistency check (must ~reproduce the tickproxy PROXY result).

Book: 2EL long BULL + 2ES short BEAR, retest 6t, stop 0.30xADR10 (floor 8t), gap<=0.54 skip,
h09-13, EOD hold, $5 RT + 1t slip. Bars = _db_es_5m_rth; pseudo-ticks from _db_es_1m_rth.

  python scripts/regime_2e_oos_databento.py [--limit N]
Output: data/regime/oos_databento_20260725.csv + tables + PNG.
"""
import sys, gc, time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_2e_tickproxy_fidelity import proxy_ticks, run_wt   # noqa: E402  (validated proxy book)

OUT = WT / "data" / "regime" / "oos_databento_20260725.csv"
M5 = DATA / "bars" / "_db_es_5m_rth.parquet"
M1 = DATA / "bars" / "_db_es_1m_rth.parquet"
rng = np.random.default_rng(83)


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(M5); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    m1 = pd.read_parquet(M1); m1["DateTime"] = pd.to_datetime(m1["DateTime"]); m1["Date"] = m1["DateTime"].dt.date.astype(str)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index or dstr not in m1g:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g = b[b.Date == dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g) < 30:
            continue
        m1day = m1g[dstr]
        m1day = m1day[m1day.DateTime >= g["DateTime"].values[0]]
        if len(m1day) < 30:
            continue
        try:
            tP2, tbar2 = proxy_ticks(g, m1day)
            out, _ = run_wt(g, tP2, tbar2, adr)
            for (bk, net) in out:
                rows.append((dstr, bk, net))
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del g, m1day; gc.collect()
        if (di + 1) % 400 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows, columns=["Date", "book", "net"]); df.to_csv(OUT, index=False)
    df["yr"] = df.Date.str[:4].astype(int)

    def pf(s):
        s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0

    def mdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())

    def block(e, label):
        if not len(e):
            print(f"{label:<26} (no trades)"); return
        v = e.sort_values("Date").net.values
        dds = np.array([(lambda c: (c - np.maximum.accumulate(c)).min())(np.cumsum(rng.permutation(v))) for _ in range(2000)])
        wl = e[e.book == "WT-L"]; ws = e[e.book == "WT-S"]
        print(f"{label:<26} n={len(e):5d}  net {e.net.sum():+9,.0f}  $/tr {e.net.mean():+6.1f}  "
              f"PF {pf(e.net):4.2f}  win {100*(e.net>0).mean():4.1f}%  maxDD {mdd(e):+8,.0f}  "
              f"MC-1% {np.percentile(dds,1):+8,.0f}  L {pf(wl.net)}/S {pf(ws.net)}")

    print(f"\nDONE {time.time()-t0:.0f}s   (Databento 1-min proxy book, 2010-2026)\n")
    block(df, "FULL 2010-2026")
    block(df[df.yr <= 2020], "PRE-2021 OOS (2010-20)")
    block(df[df.yr >= 2021], "2021+ (consistency)")
    print("\nPF / net / n by year:")
    yt = df.groupby("yr").agg(n=("net", "size"), net=("net", "sum"),
                              PF=("net", pf)).round({"net": 0})
    print(yt.to_string())

    fig, ax = plt.subplots(figsize=(13, 6), dpi=115)
    x = df.sort_values("Date"); eq = x.net.cumsum().values
    ax.plot(range(len(x)), eq, lw=1.6, color="#2a78d6")
    # mark the 2021 boundary (OOS | in-sample-era)
    n_oos = int((x.yr <= 2020).sum())
    ax.axvline(n_oos, color="#c0392b", lw=1.2, ls="--")
    ax.text(n_oos, ax.get_ylim()[1]*0.05, "  2021 ->", color="#c0392b", fontsize=9)
    ax.axhline(0, color="#c3c2b7", lw=1); ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title(f"2E book on Databento 1-min, 2010-2026 (OOS left of dashed) — "
                 f"full {df.net.sum():+,.0f}$ PF {pf(df.net)}  |  pre-2021 "
                 f"{df[df.yr<=2020].net.sum():+,.0f}$ PF {pf(df[df.yr<=2020].net)}", fontweight="bold", fontsize=11)
    fig.tight_layout()
    p = WT / "docs" / "living" / "oos_databento_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
