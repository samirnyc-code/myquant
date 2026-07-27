"""NEGATIVE-GAMMA stop/target sweep (Samir, 2026-07-27): below-SMA20 is a trend-ACCELERATION
regime; the book's 0.30xADR-stop + EOD-hold is a vol-harvest shape that may be wrong there.
Sweep stop (xADR) x target (R-multiple, or EOD, or TRAIL) on the with-trend 2E entries that fill
BELOW prior-day SMA20 (negative gamma), 2021+ Databento proxy. First-touch ordered exits. Split
by direction. Above-SMA20 shown for contrast. Book unchanged — read-only search.

  python scripts/regime_2e_neggamma_sweep.py [--limit N]
Output: data/regime/neggamma_sweep_YYYYMMDD.csv + stdout grids.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions as pt_old      # noqa: E402
from regime_2e_causal_check import detect_entries_causal               # noqa: E402
from regime_2e_tickproxy_fidelity import proxy_ticks                   # noqa: E402

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
GOOD = {9, 10, 11, 12, 13}
SA = [0.15, 0.20, 0.30, 0.50, 0.75, 1.0]                 # stop = k x ADR10
TR = [None, 1.0, 1.5, 2.0, 3.0, 4.0, "trail"]            # target = R-multiple of stop / EOD / trailing-stop


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum(); return round(gp / gl, 2) if gl else 0.0


def exit_net(seg, fill, short, stop_pts, tgt):
    """First-touch ordered exit. tgt None=EOD, float=R-multiple target, 'trail'=trailing stop by stop_pts."""
    stop = fill + stop_pts if short else fill - stop_pts
    if tgt == "trail":
        # trailing stop: peak-favorable minus stop_pts (short: trough+stop_pts)
        if short:
            trough = np.minimum.accumulate(seg); tstop = trough + stop_pts
            hit = np.nonzero(seg >= tstop)[0]
        else:
            peak = np.maximum.accumulate(seg); tstop = peak - stop_pts
            hit = np.nonzero(seg <= tstop)[0]
        ex = seg[hit[0]] if len(hit) else seg[-1]
        return ((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP
    js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
    si = js[0] if len(js) else np.inf
    if tgt is None:
        ex = stop if si < np.inf else seg[-1]
    else:
        tgtp = fill - tgt * stop_pts if short else fill + tgt * stop_pts
        jt = np.nonzero(seg <= tgtp)[0] if short else np.nonzero(seg >= tgtp)[0]
        ti = jt[0] if len(jt) else np.inf
        if si == np.inf and ti == np.inf:
            ex = seg[-1]
        elif ti <= si:
            ex = tgtp
        else:
            ex = stop
    return ((fill - ex) if short else (ex - fill)) * PT - COMM - SLIP


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b.DateTime.dt.date.astype(str)
    m1 = pd.read_parquet(DATA / "bars" / "_db_es_1m_rth.parquet"); m1["DateTime"] = pd.to_datetime(m1["DateTime"]); m1["Date"] = m1.DateTime.dt.date.astype(str)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}
    dly = b.groupby("Date").agg(dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index().sort_values("Date").reset_index(drop=True)
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["sma20"] = dly.dC.rolling(20).mean().shift(1)
    gm = dly.set_index("Date")
    days = [d for d in sorted(b.Date.unique()) if d >= "2021-01-01"]
    if limit:
        days = days[:limit]
    # accumulators: rows[(subset,dir,sa,tr)] -> list of net
    rows = {}
    def acc(key, v): rows.setdefault(key, []).append(v)
    t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index or dstr not in m1g:
            continue
        row = gm.loc[dstr]; adr, sma = row.adr10, row.sma20
        if not np.isfinite(adr) or not np.isfinite(sma):
            continue
        g = b[b.Date == dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g) < 30:
            continue
        m1d = m1g[dstr]; m1d = m1d[m1d.DateTime >= g.DateTime.values[0]]
        if len(m1d) < 30:
            continue
        H, L = g.High.values, g.Low.values; n = len(g); g_dt = g.DateTime.values
        tP, tbar = proxy_ticks(g, m1d)
        trans = pt_old(H, L, n, tP, tbar); tr_ix = [t for (t, _) in trans]; tr_md = [mm for (_, mm) in trans]
        for (fb, sb, dr, cnt, trig) in detect_entries_causal(g, tP, tbar):
            if cnt != 2:
                continue
            short = dr == "S"; want = "BEAR" if short else "BULL"
            a = np.searchsorted(tbar, fb, "left"); zz = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:zz] <= trig)[0] if short else np.nonzero(tP[a:zz] >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
            if reg != want:
                continue                                  # with-trend only
            lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP[jf:]
            jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
            if not len(jl):
                continue
            jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
            if fb2 - fb > 6 or int(pd.Timestamp(g_dt[min(fb2, n - 1)]).hour) not in GOOD:
                continue
            subset = "below" if lim < sma else "above"     # gamma side at the fill price
            seg = tP[jfl:]
            for sa in SA:
                sp = max(sa * adr, FLOOR)
                for tr in TR:
                    acc((subset, dr, sa, tr), exit_net(seg, lim, short, sp, tr))
        del tP, tbar; gc.collect()
        if (di + 1) % 300 == 0:
            print(f"[{di+1}/{len(days)}] {time.time()-t0:.0f}s", flush=True)

    yrs = 5.5
    out = []
    def grid(subset, dr, title):
        print(f"\n===== {title}  (stop k*ADR down, target across) =====")
        hdr = "stop\\tgt " + "".join(f"{('EOD' if t is None else ('TRAIL' if t=='trail' else str(t)+'R')):>12}" for t in TR)
        print(hdr)
        for sa in SA:
            cells = []
            for tr in TR:
                v = rows.get((subset, dr, sa, tr), [])
                if v:
                    va = np.asarray(v, float)
                    cells.append(f"{pf(va):.2f}/{va.sum()/yrs:+5.0f}")
                    out.append({"subset": subset, "dir": dr, "stop_adr": sa, "target": ("EOD" if tr is None else tr), "n": len(v), "pf": pf(va), "net": va.sum(), "per_yr": va.sum() / yrs})
                else:
                    cells.append("-")
            print(f"{sa:>7} " + "".join(f"{c:>12}" for c in cells))
        # n per stop row (target-independent count)
        anytr = rows.get((subset, dr, SA[0], TR[0]), [])
        print(f"(cells = PF / $per-yr;  n≈{sum(len(rows.get((subset,dr,sa,TR[0]),[])) for sa in [SA[0]])} per side)")

    for dr, nm in (("L", "2EL long"), ("S", "2ES short")):
        grid("below", dr, f"BELOW SMA20 (NEG GAMMA) — {nm}")
    for dr, nm in (("L", "2EL long"), ("S", "2ES short")):
        grid("above", dr, f"ABOVE SMA20 (pos gamma) — {nm}  [contrast]")
    pd.DataFrame(out).to_csv(WT / "data" / "regime" / "neggamma_sweep_20260727.csv", index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  saved data/regime/neggamma_sweep_20260727.csv")


if __name__ == "__main__":
    main()
