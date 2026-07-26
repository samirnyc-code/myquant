"""f2EL FADE x HVL — does the failed-2EL fade-short (our own bear-fade sleeve) fill the BELOW-HVL
(negative-gamma) slot? f2EL is a reversal, so it should live below HVL where 2E-continuation dies.
Emit f2EL fade trades (exact two_sleeves logic) on the Databento proxy 2021+, capture entry price,
classify by prior-day HVL (Samir's causal method), test below vs above HVL, per year.

f2EL: a 2EL (long 2E) that fires in a BEAR regime and FAILS 1t through the signal-bar low within
K=2 bars -> SHORT at fail-1t, stop 16t (4pt) fixed, EOD hold.

  python scripts/regime_f2el_hvl.py
Output: data/regime/f2el_hvl_20260725.csv + tables.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK; KFADE = 2; TIGHT = 16 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions as pt_old   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402
from regime_2e_tickproxy_fidelity import proxy_ticks                # noqa: E402
GOOD = {"09", "10", "11", "12", "13"}


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    m1 = pd.read_parquet(DATA / "bars" / "_db_es_1m_rth.parquet"); m1["DateTime"] = pd.to_datetime(m1["DateTime"]); m1["Date"] = m1["DateTime"].dt.date.astype(str)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = [d for d in sorted(b["Date"].unique()) if d >= "2021-01-01"]
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
        m1day = m1g[dstr]; m1day = m1day[m1day.DateTime >= g["DateTime"].values[0]]
        if len(m1day) < 30:
            continue
        H, L = g["High"].values, g["Low"].values; n = len(g)
        try:
            tP, tbar = proxy_ticks(g, m1day)
            trans = pt_old(H, L, n, tP, tbar); tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
            entries = detect_entries_causal(g, tP, tbar); g_dt = g["DateTime"].values
            for (fb, sb, dr, cnt, trig) in entries:
                if cnt != 2 or dr != "L":     # f2EL fades a failed LONG 2E
                    continue
                a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
                hit = np.nonzero(tP[a:z] >= trig)[0]
                if not len(hit):
                    continue
                jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
                if reg != "BEAR":            # fade only against a real BEAR
                    continue
                fail_px = L[sb] - TICK
                zlim = np.searchsorted(tbar, fb + KFADE + 1, "left"); segf = tP[jf:zlim]
                w = np.nonzero(segf <= fail_px)[0]
                if not len(w):
                    continue
                jx = jf + int(w[0]); fb2 = int(tbar[min(jx, len(tbar) - 1)])
                if pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H") not in GOOD:
                    continue
                fill = fail_px - TICK; stop = fill + TIGHT; seg = tP[jx:]
                js = np.nonzero(seg >= stop)[0]; ex = stop if len(js) else seg[-1]
                net = round((fill - ex) * PT - COMM - SLIP, 1)
                rows.append({"Date": dstr, "yr": int(dstr[:4]), "entry_px": round(float(fill), 2), "net": net})
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del g, m1day; gc.collect()
        if (di + 1) % 400 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    d = pd.DataFrame(rows)

    # prior-day HVL in ES frame
    esc = b.groupby("Date").agg(es_close=("Close", "last"))
    mq = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"); mq["date"] = mq["date"].astype(str)
    dd = mq[["date", "spot", "hvl"]].rename(columns={"date": "Date", "spot": "spx"}).set_index("Date").join(esc, how="inner").sort_index()
    dd["prior_hvl_es"] = (dd.hvl + (dd.es_close - dd.spx)).shift(1)
    d = d.merge(dd[["prior_hvl_es"]], left_on="Date", right_index=True, how="left")
    d = d[d.prior_hvl_es.notna()]; d["below"] = d.entry_px < d.prior_hvl_es
    d.to_csv(WT / "data" / "regime" / "f2el_hvl_20260725.csv", index=False)

    print(f"\nDONE {time.time()-t0:.0f}s  f2EL trades {len(d)} (2021+, HVL-covered)")
    print(f"  f2EL ALL         : n={len(d):4d} PF {pf(d.net):.2f} net ${d.net.sum():+,.0f} $/yr ${d.net.sum()/5.5:+,.0f}")
    print(f"  f2EL BELOW HVL   : n={len(d[d.below]):4d} PF {pf(d[d.below].net):.2f} net ${d[d.below].net.sum():+,.0f}")
    print(f"  f2EL ABOVE HVL   : n={len(d[~d.below]):4d} PF {pf(d[~d.below].net):.2f} net ${d[~d.below].net.sum():+,.0f}")
    print("\nf2EL BELOW HVL by year:")
    for y in range(2021, 2027):
        x = d[d.below & (d.yr == y)]
        if len(x): print(f"  {y}: n={len(x):3d} PF {pf(x.net):.2f} net ${x.net.sum():+,.0f}")


if __name__ == "__main__":
    main()
