"""Is the fade's fixed 4pt (16t) stop really best — and should it be vol-scaled?
Samir's question (2026-07-25): a fixed stop over 5 years of changing vol seems odd.
Replicates the two_sleeves FADE-S entry EXACTLY, then from ONE entry detection per
trade computes net under many stop candidates: fixed {2..12pt} and vol-scaled
{k x ADR10}. Reports net/PF/DD/train/test/trades. Also: what is 4pt in ADR terms,
and does a vol stop beat the fixed one OUT OF SAMPLE?

  python scripts/regime_2e_fade_stop_sweep.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions, load_day       # noqa: E402
from regime_2e_causal_check import detect_entries_causal                # noqa: E402

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
GOOD = {"09", "10", "11", "12", "13"}; KFADE = 2; TRAIN_END = "2023-12-31"
FIXED = [2, 3, 4, 5, 6, 8, 10, 12]                          # points
KADR = [0.06, 0.08, 0.10, 0.12, 0.15, 0.20]                 # x ADR10
MINT = 8 * TICK                                             # vol-stop floor (2pt)


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0
def mdd(s):
    e = np.cumsum(np.asarray(s, float)); return float((e - np.maximum.accumulate(e)).min())


def main():
    limit = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else None
    b = pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open","first"), dC=("Close","last"), dH=("High","max"), dL=("Low","min")).reset_index()
    dly["adr10"] = (dly.dH-dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100).abs()
    gmap = dly.set_index("Date")[["adr10","gap"]]
    days = sorted(b.Date.unique())[:limit] if limit else sorted(b.Date.unique())

    cand = [f"fx{p}" for p in FIXED] + [f"adr{k}" for k in KADR] + ["EOD"]
    rows = []; adrs = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gmap.index:
            continue
        adr, gapv = gmap.loc[dstr,"adr10"], gmap.loc[dstr,"gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        H, L = g["High"].values, g["Low"].values; n = len(g)
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception:
            continue
        tr_ix = [t for (t,_) in trans]; tr_md = [m for (_,m) in trans]; g_dt = g["DateTime"].values
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]; hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
            if not len(hit):
                continue
            jf = a+int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf)-1]
            want = "BEAR" if short else "BULL"
            if reg == want:
                continue                                   # WT, not fade
            fade_short = not short; need = "BEAR" if fade_short else "BULL"
            if reg != need:
                continue
            sb_ext = L[sb] if fade_short else H[sb]; fail_px = sb_ext-TICK if fade_short else sb_ext+TICK
            zlim = np.searchsorted(tbar, fb+KFADE+1, "left"); segf = tP[jf:zlim]
            w = np.nonzero(segf <= fail_px)[0] if fade_short else np.nonzero(segf >= fail_px)[0]
            if not len(w):
                continue
            jx = jf+int(w[0]); fb2 = int(tbar[min(jx, len(tbar)-1)])
            if pd.Timestamp(g_dt[min(fb2, n-1)]).strftime("%H") not in GOOD:
                continue
            fill = fail_px-TICK if fade_short else fail_px+TICK
            seg = tP[jx:]
            rec = {"Date": dstr, "adr": adr, "short": fade_short}
            for p in FIXED:
                sd = p * 1.0
                stop = fill+sd if fade_short else fill-sd
                jsx = np.nonzero(seg >= stop)[0] if fade_short else np.nonzero(seg <= stop)[0]
                ex = stop if len(jsx) else seg[-1]
                rec[f"fx{p}"] = round(((fill-ex) if fade_short else (ex-fill))*PT-COMM-SLIP, 1)
            for k in KADR:
                sd = max(k*adr, MINT)
                stop = fill+sd if fade_short else fill-sd
                jsx = np.nonzero(seg >= stop)[0] if fade_short else np.nonzero(seg <= stop)[0]
                ex = stop if len(jsx) else seg[-1]
                rec[f"adr{k}"] = round(((fill-ex) if fade_short else (ex-fill))*PT-COMM-SLIP, 1)
            ex = seg[-1]
            rec["EOD"] = round(((fill-ex) if fade_short else (ex-fill))*PT-COMM-SLIP, 1)
            rows.append(rec); adrs.append(adr)
        del tP, tbar; gc.collect()
        if (di+1) % 300 == 0:
            print(f"[{di+1}/{len(days)}] fades={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    d = pd.DataFrame(rows); d["is_tr"] = d.Date <= TRAIN_END
    d.to_csv(WT/"data"/"regime"/"fade_stop_sweep_20260725.csv", index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  fade trades={len(d)}")
    print(f"4pt in ADR terms: 4pt / median ADR {np.median(adrs):.1f}pt = {4/np.median(adrs)*100:.0f}% of ADR "
          f"(range {4/np.percentile(adrs,90)*100:.0f}-{4/np.percentile(adrs,10)*100:.0f}% over 10-90pctile ADR)\n")
    for label, sub in [("FADE-S  f2EL (COMMITTED book)", d[d.short]),
                       ("FADE-L  f2ES-long (DEAD, reference)", d[~d.short]),
                       ("BOTH combined", d)]:
        print(f"\n===== {label}  (n={len(sub)}) =====")
        print(f"{'stop':10}{'net':>10}{'$/tr':>7}{'PF':>6}{'maxDD':>9}{'train|test':>13}")
        tr, te = sub[sub.is_tr], sub[~sub.is_tr]
        for c in cand:
            v = sub[c].values
            star = " <== committed 4pt" if c == "fx4" else ""
            print(f"{c:10}{v.sum():>10,.0f}{v.mean():>7.1f}{pf(v):>6.2f}{mdd(v):>9,.0f}"
                  f"   {pf(tr[c])}|{pf(te[c])}{star}")


if __name__ == "__main__":
    main()
