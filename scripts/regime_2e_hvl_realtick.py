"""TEST 1 — confirm the HVL-gated two-sided 2E book on REAL NT ticks (2021-26), not the proxy.
With-trend 2E (both sides), 0.30xADR stop, 09-13, EOD hold; capture entry price; classify by
prior-day HVL (causal, ES frame). Compare above-HVL vs below-HVL on real ticks.

  python scripts/regime_2e_hvl_realtick.py
Output: data/regime/hvl_2e_realtick_20260725.csv + table.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions as pt_old, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal                      # noqa: E402
GOOD = {"09", "10", "11", "12", "13"}


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index().sort_values("Date")
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = [d for d in sorted(b["Date"].unique()) if d >= "2021-01-01"]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        H, L, n = g["High"].values, g["Low"].values, len(g)
        try:
            trans = pt_old(H, L, n, tP, tbar); tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
            entries = detect_entries_causal(g, tP, tbar); g_dt = g["DateTime"].values
            wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
            for (fb, sb, dr, cnt, trig) in entries:
                if cnt != 2:
                    continue
                short = dr == "S"; want = "BEAR" if short else "BULL"
                a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
                hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
                if not len(hit):
                    continue
                jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
                if reg != want:
                    continue
                lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP[jf:]
                jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
                if not len(jl):
                    continue
                jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
                if fb2 - fb > 6 or pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H") not in GOOD:
                    continue
                stop = lim + wide if short else lim - wide; seg = tP[jfl:]
                js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js) else seg[-1]
                net = round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)
                rows.append({"Date": dstr, "yr": int(dstr[:4]), "dir": dr, "entry_px": round(float(lim), 2), "net": net})
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del tP, tbar; gc.collect()
        if (di + 1) % 300 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    d = pd.DataFrame(rows)
    esc = b.groupby("Date").agg(es_close=("Close", "last"))
    mq = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"); mq["date"] = mq["date"].astype(str)
    dd = mq[["date", "spot", "hvl"]].rename(columns={"date": "Date", "spot": "spx"}).set_index("Date").join(esc, how="inner").sort_index()
    dd["prior_hvl_es"] = (dd.hvl + (dd.es_close - dd.spx)).shift(1)
    d = d.merge(dd[["prior_hvl_es"]], left_on="Date", right_index=True, how="left")
    d = d[d.prior_hvl_es.notna()]; d["above"] = d.entry_px > d.prior_hvl_es
    d.to_csv(WT / "data" / "regime" / "hvl_2e_realtick_20260725.csv", index=False)

    def mdd(x):
        e = x.sort_values("Date").net.cumsum(); return float((e - e.cummax()).min())
    print(f"\nDONE {time.time()-t0:.0f}s  REAL-TICK HVL-gated 2E (2021+), {len(d)} trades")
    for nm, x in (("ABOVE HVL (traded)", d[d.above]), ("below HVL", d[~d.above]), ("ALL", d)):
        print(f"  {nm:<18} n={len(x):4d} PF {pf(x.net):.2f} net ${x.net.sum():+8,.0f} $/yr ${x.net.sum()/5.5:+,.0f} maxDD ${mdd(x):+,.0f}")
    ab = d[d.above]
    print(f"  above-HVL L: PF {pf(ab[ab.dir=='L'].net):.2f} ${ab[ab.dir=='L'].net.sum():+,.0f}  |  S: PF {pf(ab[ab.dir=='S'].net):.2f} ${ab[ab.dir=='S'].net.sum():+,.0f}")
    print("  above-HVL by year:", {y: (len(ab[ab.yr==y]), pf(ab[ab.yr==y].net)) for y in range(2021, 2027)})


if __name__ == "__main__":
    main()
