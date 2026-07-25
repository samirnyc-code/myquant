"""Does the METHOD re-calibrate to NQ? (Samir's test, 2026-07-25)
Generate NQ WT trades with NO gap filter, recording per-trade gap + net at several
stop-mults. Then sweep gap-threshold x stop-mult on NQ TRAIN (<=2023), pick the best
train cell, and read its NQ TEST (2024+) PF. If a train-good region is ALSO test-good,
the method generalizes to NQ (non-transfer = calibration, not a fake edge). If train-good
regions are test-bad, NQ genuinely lacks the edge for this method.

  python scripts/regime_2e_nq_recalib.py
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import regime_second_entry_study as R
R.TICKD = Path(r"C:/Users/Admin/myquant/data/ticks_continuous_NQ")
from regime_second_entry_study import phase_transitions, load_day
from regime_2e_causal_check import detect_entries_causal

TICK = 0.25; PT = 20.0; COMM = 5.0; SLIP = 0.25 * PT
WT = Path(__file__).resolve().parent.parent
NQBARS = WT / "data" / "regime" / "_nq_bars_5m.parquet"
GOOD = {"09", "10", "11", "12", "13"}; FLOOR = 8 * TICK; TRAIN_END = "2023-12-31"
STOPS = [0.20, 0.30, 0.40, 0.50]
DS = WT / "data" / "regime" / "nq_recalib_dataset.csv"


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0


def gen():
    b = pd.read_parquet(NQBARS)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gmap = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b.Date.unique()); rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gmap.index:
            continue
        adr, gapv = gmap.loc[dstr, "adr10"], gmap.loc[dstr, "gap"]
        if not np.isfinite(adr):
            continue                                       # NO gap filter (record gap, filter later)
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        H, L = g["High"].values, g["Low"].values; n = len(g); g_dt = g["DateTime"].values
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception:
            continue
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]; hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
            want = "BEAR" if short else "BULL"
            if reg != want:
                continue
            lim = trig + 6 * TICK if short else trig - 6 * TICK
            seg0 = tP[jf:]; jl = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
            if not len(jl):
                continue
            jfl = jf + int(jl[0])
            if int(tbar[jfl]) - fb > 6:
                continue
            if pd.Timestamp(g_dt[min(int(tbar[jfl]), n-1)]).strftime("%H") not in GOOD:
                continue
            fill = lim; seg = tP[jfl:]; rec = {"Date": dstr, "gap": gapv}
            for m in STOPS:
                sd = max(round(m * adr / TICK) * TICK, FLOOR); stop = fill + sd if short else fill - sd
                js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                ex = stop if len(js) else seg[-1]
                rec[f"s{m}"] = round(((fill-ex) if short else (ex-fill))*PT-COMM-SLIP, 1)
            rows.append(rec)
        del tP, tbar; gc.collect()
        if (di+1) % 400 == 0:
            print(f"[{di+1}/{len(days)}] {len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    d = pd.DataFrame(rows); d.to_csv(DS, index=False); return d


d = pd.read_csv(DS) if DS.exists() else gen()
d["tr"] = d.Date <= TRAIN_END
print(f"NQ WT trades (no gap filter): {len(d)}  train {d.tr.sum()} / test {(~d.tr).sum()}\n")
GAPS = [0.45, 0.54, 0.70, 1.00, 99]
print("TRAIN PF grid (rows=stop, cols=gap<=):    [pick best TRAIN, read its TEST]")
hdr = "        " + "".join(f"g{g:>6}" for g in GAPS); print(hdr)
best = None
for m in STOPS:
    line = f"  s{m}  "
    for g in GAPS:
        x = d[d.tr & (d.gap <= g)][f"s{m}"]
        line += f"{pf(x):>7.2f}"
        if best is None or pf(x) > best[0]:
            if len(x) >= 40: best = (pf(x), m, g)
    print(line)
print("\nTEST PF grid (same cells):")
print(hdr)
for m in STOPS:
    line = f"  s{m}  "
    for g in GAPS:
        x = d[~d.tr & (d.gap <= g)][f"s{m}"]
        line += f"{pf(x):>7.2f}"
    print(line)
bm, bg = best[1], best[2]
tr = d[d.tr & (d.gap <= bg)][f"s{bm}"]; te = d[~d.tr & (d.gap <= bg)][f"s{bm}"]
print(f"\nBEST TRAIN cell: stop {bm}, gap<={bg}  -> TRAIN PF {pf(tr)} (n={len(tr)}, ${tr.sum():+,.0f})")
print(f"  its NQ TEST:  PF {pf(te)} (n={len(te)}, ${te.sum():+,.0f})  net ${tr.sum()+te.sum():+,.0f}")
print(f"VERDICT: method {'GENERALIZES to NQ (recalibrated)' if pf(te) >= 1.15 else 'does NOT hold OOS on NQ even recalibrated'}")
