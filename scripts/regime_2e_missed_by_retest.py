"""How many with-trend 2E trades does the 6t-back RETEST LIMIT miss vs a STOP-ENTRY at
the trigger? A signal fires when price trades through the S61 trigger (regime-confirmed,
gap<=0.54, in window). A stop-entry fills every such signal at the trigger. The current
book instead rests a limit 6 ticks BACK and only fills if price retraces 6t within 6 bars
— signals that never retrace are MISSED. Counts 2EL(long,BULL)+2ES(short,BEAR), 5yr ES.

  python scripts/regime_2e_missed_by_retest.py
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions, load_day
from regime_2e_causal_check import detect_entries_causal

TICK = 0.25; GOOD = {"09", "10", "11", "12", "13"}
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def main():
    b = pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open","first"), dC=("Close","last"), dH=("High","max"), dL=("Low","min")).reset_index()
    dly["gap"] = ((dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100).abs()
    dly["adr10"] = (dly.dH-dly.dL).rolling(10).mean().shift(1)
    gm = dly.set_index("Date")[["gap", "adr10"]]
    days = sorted(b.Date.unique()); rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index: continue
        gapv, adr = gm.loc[dstr, "gap"], gm.loc[dstr, "adr10"]
        if not np.isfinite(adr) or gapv > 0.54: continue
        g, tP, tbar = load_day(b, dstr)
        if g is None: continue
        H, L = g.High.values, g.Low.values; n = len(g); gdt = g.DateTime.values
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception: continue
        tix = [t for (t,_) in trans]; tmd = [m for (_,m) in trans]
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2: continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:z] <= trig)[0] if short else np.nonzero(tP[a:z] >= trig)[0]
            if not len(hit): continue                     # trigger never hit in fire bar
            jf = a + int(hit[0]); reg = tmd[bisect_right(tix, jf) - 1]
            want = "BEAR" if short else "BULL"
            if reg != want: continue                        # not with-trend
            if pd.Timestamp(gdt[min(fb, n-1)]).strftime("%H") not in GOOD: continue
            # SIGNAL fired (stop-entry would fill here). Does the 6t retest fill within 6 bars?
            lim = trig + 6*TICK if short else trig - 6*TICK
            seg0 = tP[jf:]; jl = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
            filled = False
            if len(jl):
                jfl = jf + int(jl[0])
                if int(tbar[jfl]) - fb <= 6 and pd.Timestamp(gdt[min(int(tbar[jfl]), n-1)]).strftime("%H") in GOOD:
                    filled = True
            rows.append((dstr, "2ES" if short else "2EL", filled))
        del tP, tbar; gc.collect()
        if (di+1) % 300 == 0:
            print(f"[{di+1}/{len(days)}] signals={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    d = pd.DataFrame(rows, columns=["Date", "book", "filled"]); d["yr"] = d.Date.str[:4]
    d.to_csv(WT/"data"/"regime"/"missed_by_retest.csv", index=False)
    print(f"\nDONE {time.time()-t0:.0f}s\n")
    print(f"{'book':6}{'signals':>9}{'filled(6t retest)':>19}{'MISSED':>9}{'miss %':>9}")
    for bk in ["2EL", "2ES", "ALL"]:
        x = d if bk == "ALL" else d[d.book == bk]
        sig = len(x); fil = int(x.filled.sum()); mis = sig - fil
        print(f"{bk:6}{sig:>9}{fil:>19}{mis:>9}{mis/sig*100:>8.0f}%")
    print("\nper-year (signals / filled / missed):")
    for y in sorted(d.yr.unique()):
        x = d[d.yr == y]; print(f"  {y}: {len(x):4d} sig / {int(x.filled.sum()):4d} filled / {len(x)-int(x.filled.sum()):4d} missed")

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5), dpi=120)
    yrs = sorted(d.yr.unique())
    fil = [int(d[d.yr == y].filled.sum()) for y in yrs]; mis = [len(d[d.yr == y]) - f for y, f in zip(yrs, fil)]
    ax.bar(yrs, fil, label="filled (6t retest — current book)", color="#2e8b57")
    ax.bar(yrs, mis, bottom=fil, label="MISSED (never retraced 6t)", color="#b23a2e")
    for i, y in enumerate(yrs):
        ax.text(i, fil[i]+mis[i]+2, f"{mis[i]/(fil[i]+mis[i])*100:.0f}% miss", ha="center", fontsize=9)
    ax.set_title(f"With-trend 2E signals: filled by 6t retest vs missed  "
                 f"(total {len(d)} signals, {len(d)-int(d.filled.sum())} missed = "
                 f"{(len(d)-int(d.filled.sum()))/len(d)*100:.0f}%)", fontweight="bold", fontsize=11)
    ax.legend(frameon=False)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    fig.tight_layout(); fig.savefig(WT/"docs"/"living"/"missed_by_retest.png", facecolor="white")
    print("\nsaved docs/living/missed_by_retest.png")


if __name__ == "__main__":
    main()
