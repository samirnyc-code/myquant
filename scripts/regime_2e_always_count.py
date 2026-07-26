"""ALWAYS-COUNT experiment (Samir, 2026-07-26): the S61 counter zeros the 2E count in the
OPPOSITE regime (shorts reset in BULL @regime_2e_causal_check.py:133-134, longs reset in BEAR
@:155-156) and on every regime flip. So a 2E signal only counts once structure/regime allows —
the f2EL fade seed can appear "late". This runs a variant that counts BOTH directions' second
entries CONTINUOUSLY (regime-independent), still classifies book vs fade by the phase machine at
the fill, and compares P&L head-to-head with the baseline counter. NOTHING in the live engine is
changed — this is a read-only comparison.

  python scripts/regime_2e_always_count.py [--limit N] [--from 2021-01-01]
Output: data/regime/always_count_compare_YYYYMMDD.csv + stdout table.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
KFADE = 2; FADE_STOP = 4.0
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day     # noqa: E402
from regime_2e_causal_check import detect_entries_causal              # noqa: E402
GOOD = {9, 10, 11, 12, 13}


def detect_entries_always(g, tP, tbar):
    """detect_entries_causal with 2E counting DECOUPLED from regime: both directions' counts
    accumulate on structure only (no opposite-regime zeroing, no reset on regime flip). Pivot
    detection is byte-identical to the baseline; only the entry-counting loop differs."""
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)

    def tick_slice(i):
        return np.searchsorted(tbar, i, "left"), np.searchsorted(tbar, i, "right")

    def ob_cont_first(i, up):
        a, z = tick_slice(i); s = tP[a:z]
        if up:
            c_ = np.nonzero(s > H[i - 1])[0]; k_ = np.nonzero(s < L[i - 1])[0]
        else:
            c_ = np.nonzero(s < L[i - 1])[0]; k_ = np.nonzero(s > H[i - 1])[0]
        return (c_[0] if len(c_) else np.inf) < (k_[0] if len(k_) else np.inf)

    piv = []
    d = 1 if H[1] >= H[0] else -1
    ext_i = 0; pj = 0
    for i in range(1, n):
        if H[i] < H[i - 1] and L[i] > L[i - 1]:
            continue
        if H[i] > H[i - 1] and L[i] < L[i - 1]:
            up = (d == 1); cf = ob_cont_first(i, up)
            if up:
                if cf:
                    if H[i] >= H[ext_i]: ext_i = i
                    piv.append((ext_i, H[ext_i], "H", i)); d = -1; ext_i = i
                else:
                    piv.append((ext_i, H[ext_i], "H", i)); piv.append((i, L[i], "L", i)); d = 1; ext_i = i
            else:
                if cf:
                    if L[i] <= L[ext_i]: ext_i = i
                    piv.append((ext_i, L[ext_i], "L", i)); d = 1; ext_i = i
                else:
                    piv.append((ext_i, L[ext_i], "L", i)); piv.append((i, H[i], "H", i)); d = -1; ext_i = i
            pj = i; continue
        if d == 1:
            if H[i] >= H[ext_i]: ext_i = i
            if L[i] < L[pj]:
                piv.append((ext_i, H[ext_i], "H", i)); d = -1; ext_i = i
        else:
            if L[i] <= L[ext_i]: ext_i = i
            if H[i] > H[pj]:
                piv.append((ext_i, L[ext_i], "L", i)); d = 1; ext_i = i
        pj = i
    piv.append((ext_i, H[ext_i] if d == 1 else L[ext_i], "H" if d == 1 else "L", n - 1))

    # ---- entry counting: CONTINUOUS in both directions (no regime gating/reset) ----
    entries = []
    ecS = 0; refS = None; refSb = None; orgS = None
    ecL = 0; refLo = None; refLb = None; orgL = None
    for i in range(1, n):
        is_ob = H[i] > H[i - 1] and L[i] < L[i - 1]
        # SHORT second-entry (fires on break below the short reference)
        if refS is not None and L[i] < refS - TICK / 2:
            ecS += 1
            entries.append((i, refSb, "S", min(ecS, 3), refS - TICK))
            refS = None; refSb = None
            if is_ob and H[i] > H[i - 1]:
                refS = L[i]; refSb = i
            if orgS is not None and L[i] < orgS - TICK / 2:
                ecS = 0; orgS = None
        elif orgS is not None and L[i] < orgS - TICK / 2:
            ecS = 0; orgS = None
        if is_ob:
            if orgS is None: orgS = L[i]
            refS = L[i]; refSb = i
        elif H[i] > H[i - 1] or L[i] >= L[i - 1] - TICK / 2:
            if refS is None and orgS is None: orgS = L[i - 1]
            refS = L[i]; refSb = i
        # LONG second-entry (fires on break above the long reference)
        if refLo is not None and H[i] > refLo + TICK / 2:
            ecL += 1
            entries.append((i, refLb, "L", min(ecL, 3), refLo + TICK))
            refLo = None; refLb = None
            if is_ob and L[i] < L[i - 1]:
                refLo = H[i]; refLb = i
            if orgL is not None and H[i] > orgL + TICK / 2:
                ecL = 0; orgL = None
        elif orgL is not None and H[i] > orgL + TICK / 2:
            ecL = 0; orgL = None
        if is_ob:
            if orgL is None: orgL = H[i]
            refLo = H[i]; refLb = i
        elif L[i] < L[i - 1] or H[i] <= H[i - 1] + TICK / 2:
            if refLo is None and orgL is None: orgL = H[i - 1]
            refLo = H[i]; refLb = i
    return entries


def sim(entries, g, tP, tbar, tr_ix, tr_md, adr, gapv):
    """Book (WT 2E, 6t retest, 0.30xADR, EOD) + fade (stop-entry, 4pt, EOD). 09-13, gap<=0.54."""
    H, L = g["High"].values, g["Low"].values; n = len(g); g_dt = g["DateTime"].values
    wide = max(round(0.30 * adr / TICK) * TICK, FLOOR)
    okgap = (not np.isfinite(gapv)) or (abs(gapv) <= 0.54)
    book, fade = [], []
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt != 2:
            continue
        short = dr == "S"; want = "BEAR" if short else "BULL"
        a = np.searchsorted(tbar, fb, "left"); zz = np.searchsorted(tbar, fb, "right")
        hit = np.nonzero(tP[a:zz] <= trig)[0] if short else np.nonzero(tP[a:zz] >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
        if reg == want:                                       # ---- with-trend book ----
            lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP[jf:]
            jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
            if not len(jl):
                continue
            jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
            if fb2 - fb > 6:
                continue
            if int(pd.Timestamp(g_dt[min(fb2, n - 1)]).hour) not in GOOD or not okgap:
                continue
            stop = lim + wide if short else lim - wide; segp = tP[jfl:]
            js = np.nonzero(segp >= stop)[0] if short else np.nonzero(segp <= stop)[0]
            ex = stop if len(js) else segp[-1]
            book.append(round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1))
        else:                                                  # ---- fade ----
            fade_short = not short; need = "BEAR" if fade_short else "BULL"
            if reg != need:
                continue
            sb_ext = L[sb] if fade_short else H[sb]
            fail_px = sb_ext - TICK if fade_short else sb_ext + TICK
            zlim = np.searchsorted(tbar, fb + KFADE + 1, "left"); segf = tP[jf:zlim]
            w = np.nonzero(segf <= fail_px)[0] if fade_short else np.nonzero(segf >= fail_px)[0]
            if not len(w):
                continue
            jx = jf + int(w[0]); fb2 = int(tbar[min(jx, len(tbar) - 1)])
            if int(pd.Timestamp(g_dt[min(fb2, n - 1)]).hour) not in GOOD or not okgap:
                continue
            fill = fail_px - TICK if fade_short else fail_px + TICK
            stop = fill + FADE_STOP if fade_short else fill - FADE_STOP; seg2 = tP[jx:]
            jsx = np.nonzero(seg2 >= stop)[0] if fade_short else np.nonzero(seg2 <= stop)[0]
            ex = stop if len(jsx) else seg2[-1]
            if fade_short:                                    # only f2EL (fade-short) is the committed book
                fade.append(round((fill - ex) * PT - COMM - SLIP, 1))
    return book, fade


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum(); return round(gp / gl, 2) if gl else 0.0


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    frm = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2021-01-01"
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100)
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = [d for d in sorted(b.Date.unique()) if d >= frm]
    if limit:
        days = days[:limit]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr):
            continue
        gd = load_day(b, dstr)
        if gd[0] is None:
            continue
        g, tP, tbar = gd; H, L = g["High"].values, g["Low"].values; n = len(g)
        try:
            trans = phase_transitions(H, L, n, tP, tbar)
            e_base = detect_entries_causal(g, tP, tbar)
            e_all = detect_entries_always(g, tP, tbar)
        except Exception:
            continue
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        bb, fb_ = sim(e_base, g, tP, tbar, tr_ix, tr_md, adr, gapv)
        ba, fa = sim(e_all, g, tP, tbar, tr_ix, tr_md, adr, gapv)
        rows.append({"Date": dstr,
                     "base_book_n": len(bb), "base_book_net": sum(bb), "base_fade_n": len(fb_), "base_fade_net": sum(fb_),
                     "all_book_n": len(ba), "all_book_net": sum(ba), "all_fade_n": len(fa), "all_fade_net": sum(fa)})
        del tP, tbar; gc.collect()
        if (di + 1) % 300 == 0:
            print(f"[{di+1}/{len(days)}] {time.time()-t0:.0f}s", flush=True)
    d = pd.DataFrame(rows)
    stamp = "".join(c for c in frm if c.isdigit())
    d.to_csv(WT / "data" / "regime" / f"always_count_compare_{stamp}.csv", index=False)
    yrs = (pd.to_datetime(d.Date).max() - pd.to_datetime(d.Date).min()).days / 365.25

    def blk(name, npar, netpar):
        # reconstruct trade-level vectors is overkill; summarize from daily sums for net/PF-approx
        return npar.sum(), netpar.sum()

    print(f"\nDONE {time.time()-t0:.0f}s  days={len(d)}  span={yrs:.1f}yr  (from {frm})\n")
    print(f"{'book':22}{'trades':>8}{'net':>12}{'$/yr':>10}")
    for lbl, ncol, netcol in [("WITH-TREND  baseline", "base_book_n", "base_book_net"),
                              ("WITH-TREND  always  ", "all_book_n", "all_book_net"),
                              ("FADE f2EL   baseline", "base_fade_n", "base_fade_net"),
                              ("FADE f2EL   always  ", "all_fade_n", "all_fade_net")]:
        N, NET = int(d[ncol].sum()), d[netcol].sum()
        print(f"{lbl:22}{N:>8}{NET:>+12,.0f}{NET/yrs:>+10,.0f}")
    print("\n(trade-count deltas show how many MORE 2E signals continuous counting surfaces)")
    print(f"  with-trend: {int(d.all_book_n.sum()-d.base_book_n.sum()):+d} trades, "
          f"${d.all_book_net.sum()-d.base_book_net.sum():+,.0f} net")
    print(f"  fade f2EL : {int(d.all_fade_n.sum()-d.base_fade_n.sum()):+d} trades, "
          f"${d.all_fade_net.sum()-d.base_fade_net.sum():+,.0f} net")


if __name__ == "__main__":
    main()
