"""Run THE BOOK (two-sided 2E, gated to price > 20-day SMA, 0.30xADR stop, retest 6t, 09-13, EOD)
on the 1-MINUTE ES data (_continuous_1m, NT-derived) for 2021-2026 — independent cross-check vs
the real-tick run. Pseudo-ticks reconstructed from the 1-min bars drive the same phase-machine
engine; gate is entry_px > 20-day SMA of daily closes. No HVL, no options.

  python scripts/regime_2e_sma20_1m.py
Output: data/regime/book_sma20_1m_20260725.csv + tables.
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
from regime_second_entry_study import phase_transitions as pt_old   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402
from regime_2e_tickproxy_fidelity import proxy_ticks                # noqa: E402
GOOD = {"09", "10", "11", "12", "13"}


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def mdd(x):
    e = x.sort_values("Date").net.cumsum().values; return float((e - np.maximum.accumulate(e)).min())


def main():
    m1 = pd.read_parquet(DATA / "bars" / "_continuous_1m.parquet")
    m1["DateTime"] = pd.to_datetime(m1["DateTime"]); m1["Date"] = m1["DateTime"].dt.date.astype(str)
    # 5m frame (engine timeframe) resampled from the 1-min bars, per session
    m1i = m1.set_index("DateTime")
    o = m1i["Open"].resample("5min", label="left", closed="left").first()
    h = m1i["High"].resample("5min", label="left", closed="left").max()
    lo = m1i["Low"].resample("5min", label="left", closed="left").min()
    c = m1i["Close"].resample("5min", label="left", closed="left").last()
    b5 = pd.concat([o, h, lo, c], axis=1).dropna().reset_index()
    b5.columns = ["DateTime", "Open", "High", "Low", "Close"]; b5["Date"] = b5["DateTime"].dt.date.astype(str)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}

    dly = b5.groupby("Date").agg(dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min"), dO=("Open", "first")).reset_index().sort_values("Date")
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    dly["sma20"] = dly.dC.rolling(20).mean().shift(1)      # prior-day 20-day SMA (causal)
    gm = dly.set_index("Date")[["adr10", "gap", "sma20"]]

    days = sorted(b5["Date"].unique()); rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index or dstr not in m1g:
            continue
        adr, gapv, sma20 = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"], gm.loc[dstr, "sma20"]
        if not np.isfinite(adr) or gapv > 0.54 or not np.isfinite(sma20):
            continue
        g = b5[b5.Date == dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g) < 30:
            continue
        m1day = m1g[dstr]; m1day = m1day[m1day.DateTime >= g["DateTime"].values[0]]
        if len(m1day) < 30:
            continue
        H, L, n = g["High"].values, g["Low"].values, len(g)
        try:
            tP, tbar = proxy_ticks(g, m1day)
            trans = pt_old(H, L, n, tP, tbar); tr_ix = [t for (t, _) in trans]; tr_md = [mm for (_, mm) in trans]
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
                if not (lim > sma20):          # THE GATE: entry above the 20-day SMA
                    continue
                stop = lim + wide if short else lim - wide; seg = tP[jfl:]
                js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js) else seg[-1]
                net = round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)
                rows.append({"Date": dstr, "yr": int(dstr[:4]), "dir": dr, "net": net})
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del g, m1day; gc.collect()
        if (di + 1) % 300 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    d = pd.DataFrame(rows); d.to_csv(WT / "data" / "regime" / "book_sma20_1m_20260725.csv", index=False)

    def show(nm, x):
        v = x.net.values
        if not len(v): print(f"{nm}: none"); return
        top5 = np.sort(v)[::-1][:5].sum()
        yrs = " ".join(f"{y}:{pf(x[x.yr==y].net):.2f}" for y in sorted(x.yr.unique()))
        print(f"{nm}: n={len(v)} ({len(v)/5.5:.0f}/yr) PF {pf(v):.2f} net ${v.sum():+,.0f} (${v.sum()/5.5:+,.0f}/yr) "
              f"win {100*(v>0).mean():.0f}% maxDD ${mdd(x):+,.0f} top5={100*top5/v.sum():.0f}%\n   per-yr {yrs}")

    print(f"\nDONE {time.time()-t0:.0f}s  === THE BOOK on 1-MIN ES data (2021-2026) ===")
    show("2E both (>SMA20)", d)
    show("2EL long only", d[d.dir == "L"])
    show("2ES short only", d[d.dir == "S"])
    print("\ncompare: real-tick run was 2E-both PF 1.68 +$70,768 (+$12,867/yr); long-only 1.61 +$5,852/yr")


if __name__ == "__main__":
    main()
