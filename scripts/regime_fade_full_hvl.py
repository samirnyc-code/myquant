"""FADE FULL x REGIME x HVL — both f2EL (fade failed long-2E -> short) and f2ES (fade failed
short-2E -> long), recording the REGIME at fail (BULL/BEAR/NEUTRAL) and the prior-day HVL
position, so we can slice every gate: opposite-trend only (frozen spec) vs neutral-allowed vs
below/above HVL. Tests Samir's question: do fades need the opposite regime, or is NEUTRAL ok,
or is the HVL a better gate than the phase regime?

Fade logic (frozen): counter-trend 2E fails 1t through signal-bar extreme within K=2 bars ->
stop-entry -1t, 16t (4pt) fixed stop, EOD hold, gap<=0.54, h09-13. Databento proxy, 2021+.

  python scripts/regime_fade_full_hvl.py
Output: data/regime/fade_full_hvl_20260725.csv + tables.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; KFADE = 2; TIGHT = 16 * TICK
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
                if cnt != 2:
                    continue
                short = dr == "S"
                a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
                hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
                if not len(hit):
                    continue
                jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
                want = "BEAR" if short else "BULL"
                if reg == want:
                    continue                       # with-trend -> not a fade
                fade_short = not short              # f2EL: fade a failed long -> short
                sb_ext = L[sb] if fade_short else H[sb]
                fail_px = sb_ext - TICK if fade_short else sb_ext + TICK
                zlim = np.searchsorted(tbar, fb + KFADE + 1, "left"); segf = tP[jf:zlim]
                w = np.nonzero(segf <= fail_px)[0] if fade_short else np.nonzero(segf >= fail_px)[0]
                if not len(w):
                    continue
                jx = jf + int(w[0]); fb2 = int(tbar[min(jx, len(tbar) - 1)])
                if pd.Timestamp(g_dt[min(fb2, n - 1)]).strftime("%H") not in GOOD:
                    continue
                fill = fail_px - TICK if fade_short else fail_px + TICK
                stop = fill + TIGHT if fade_short else fill - TIGHT; seg = tP[jx:]
                js = np.nonzero(seg >= stop)[0] if fade_short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js) else seg[-1]
                net = round(((fill - ex) if fade_short else (ex - fill)) * PT - COMM - SLIP, 1)
                rows.append({"Date": dstr, "yr": int(dstr[:4]),
                             "fade": "f2EL" if fade_short else "f2ES", "reg": reg,
                             "entry_px": round(float(fill), 2), "net": net})
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del g, m1day; gc.collect()
        if (di + 1) % 400 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    d = pd.DataFrame(rows)

    esc = b.groupby("Date").agg(es_close=("Close", "last"))
    mq = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"); mq["date"] = mq["date"].astype(str)
    dd = mq[["date", "spot", "hvl"]].rename(columns={"date": "Date", "spot": "spx"}).set_index("Date").join(esc, how="inner").sort_index()
    dd["prior_hvl_es"] = (dd.hvl + (dd.es_close - dd.spx)).shift(1)
    d = d.merge(dd[["prior_hvl_es"]], left_on="Date", right_index=True, how="left")
    d = d[d.prior_hvl_es.notna()]; d["below"] = d.entry_px < d.prior_hvl_es
    d.to_csv(WT / "data" / "regime" / "fade_full_hvl_20260725.csv", index=False)

    def show(nm, x):
        print(f"  {nm:<34} n={len(x):4d} PF {pf(x.net):.2f} net ${x.net.sum():+8,.0f} $/yr ${x.net.sum()/5.5:+,.0f}")

    print(f"\nDONE {time.time()-t0:.0f}s  fades {len(d)} (2021+)\n")
    for fade in ("f2EL", "f2ES"):
        f = d[d.fade == fade]
        opp = "BEAR" if fade == "f2EL" else "BULL"
        print(f"===== {fade} ({'fade failed long->short' if fade=='f2EL' else 'fade failed short->long'}) =====")
        show("ALL regimes", f)
        show(f"opposite trend only ({opp})  [frozen]", f[f.reg == opp])
        show("NEUTRAL only", f[f.reg == "NEUTRAL"])
        show(f"opposite OR neutral", f[f.reg.isin([opp, "NEUTRAL"])])
        show("BELOW HVL (neg gamma)", f[f.below])
        show("ABOVE HVL (pos gamma)", f[~f.below])
        show(f"{opp} AND below-HVL", f[(f.reg == opp) & f.below])
        # per-year for the best-looking gate (opp OR neutral)
        best = f[f.reg.isin([opp, "NEUTRAL"])]
        yy = " ".join(f"{y}:{pf(best[best.yr==y].net):.2f}" for y in range(2021, 2027) if len(best[best.yr == y]))
        print(f"    opp|neutral by yr: {yy}\n")


if __name__ == "__main__":
    main()
