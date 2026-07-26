"""PnL of the 154 MISSED signals if taken via STOP-ENTRY at the trigger (the 6t-worse
fill the retest avoids). Same 0.30xADR stop, EOD hold, $5 RT + 1t slip. Also: does adding
them to the 573-trade retest book help or hurt? 2EL(long)+2ES(short), 5yr ES.
  python scripts/regime_2e_missed_pnl.py
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions, load_day
from regime_2e_causal_check import detect_entries_causal

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8*TICK; GOOD = {"09","10","11","12","13"}
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(s):
    s = np.asarray(s, float); gp = s[s>0].sum(); gl = -s[s<0].sum(); return round(gp/gl, 2) if gl else 0


def main():
    b = pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open","first"), dC=("Close","last"), dH=("High","max"), dL=("Low","min")).reset_index()
    dly["gap"] = ((dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100).abs()
    dly["adr10"] = (dly.dH-dly.dL).rolling(10).mean().shift(1)
    gm = dly.set_index("Date")[["gap","adr10"]]
    days = sorted(b.Date.unique()); rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index: continue
        gapv, adr = gm.loc[dstr,"gap"], gm.loc[dstr,"adr10"]
        if not np.isfinite(adr) or gapv > 0.54: continue
        g, tP, tbar = load_day(b, dstr)
        if g is None: continue
        H, L = g.High.values, g.Low.values; n = len(g); gdt = g.DateTime.values
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception: continue
        tix=[t for (t,_) in trans]; tmd=[m for (_,m) in trans]; sd=max(round(0.30*adr/TICK)*TICK, FLOOR)
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2: continue
            short = dr == "S"
            a=np.searchsorted(tbar,fb,"left"); z=np.searchsorted(tbar,fb,"right")
            hit=np.nonzero(tP[a:z]<=trig)[0] if short else np.nonzero(tP[a:z]>=trig)[0]
            if not len(hit): continue
            jf=a+int(hit[0]); reg=tmd[bisect_right(tix,jf)-1]; want="BEAR" if short else "BULL"
            if reg!=want or pd.Timestamp(gdt[min(fb,n-1)]).strftime("%H") not in GOOD: continue
            lim=trig+6*TICK if short else trig-6*TICK
            seg0=tP[jf:]; jl=np.nonzero(seg0>lim)[0] if short else np.nonzero(seg0<lim)[0]
            filled=False
            if len(jl):
                jfl=jf+int(jl[0])
                if int(tbar[jfl])-fb<=6 and pd.Timestamp(gdt[min(int(tbar[jfl]),n-1)]).strftime("%H") in GOOD: filled=True
            def sim(fill, et):
                stop=fill+sd if short else fill-sd; seg=tP[et:]
                js=np.nonzero(seg>=stop)[0] if short else np.nonzero(seg<=stop)[0]
                ex=stop if len(js) else seg[-1]
                return round(((fill-ex) if short else (ex-fill))*PT-COMM-SLIP, 1)
            stop_fill = trig+TICK if short else trig-TICK               # stop-market, 1t adverse
            stop_net = sim(stop_fill, jf)                               # every signal: stop-entry at trigger
            retest_net = sim(lim, jfl) if filled else np.nan            # only if retest fills
            rows.append((dstr, "2ES" if short else "2EL", filled, stop_net, retest_net))
        del tP, tbar; gc.collect()
        if (di+1)%400==0: print(f"[{di+1}/{len(days)}] {len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    d = pd.DataFrame(rows, columns=["Date","book","filled","stop_net","retest_net"]); d["yr"]=d.Date.str[:4]
    d.to_csv(WT/"data"/"regime"/"missed_pnl.csv", index=False)
    miss=d[~d.filled]; fill=d[d.filled]
    print(f"\nDONE {time.time()-t0:.0f}s\n")
    print("=== the 154 MISSED signals, entered via STOP at the trigger (the direct answer) ===")
    print(f"{'book':6}{'n':>5}{'net':>10}{'$/tr':>8}{'PF':>6}")
    for bk in ["2EL","2ES","ALL"]:
        x = miss if bk=="ALL" else miss[miss.book==bk]
        print(f"{bk:6}{len(x):>5}{x.stop_net.sum():>10,.0f}{x.stop_net.mean():>8.1f}{pf(x.stop_net):>6.2f}")
    print("\nper-year (missed, stop-entry):")
    for y in sorted(miss.yr.unique()):
        x=miss[miss.yr==y]; print(f"  {y}: n={len(x):3d} net {x.stop_net.sum():+7,.0f} PF {pf(x.stop_net)}")

    print("\n=== HONEST STRATEGY COMPARISON (you must choose one entry rule for ALL signals) ===")
    print(f"  A) RETEST limit (current): fills 573 at 6t-better price, MISSES 154")
    print(f"       net {fill.retest_net.sum():+,.0f}  PF {pf(fill.retest_net)}  ({len(fill)} trades)")
    print(f"  B) STOP-entry all 727 at trigger: catches the 154 runners but 573 retracers fill 6t WORSE")
    print(f"       net {d.stop_net.sum():+,.0f}  PF {pf(d.stop_net)}  ({len(d)} trades)")
    cost = fill.retest_net.sum() - fill.stop_net.sum()
    print(f"  cost of the worse fill on the 573 retracers (retest vs stop): {cost:+,.0f}")
    print(f"  gain from the 154 runners (stop-entry):                       {miss.stop_net.sum():+,.0f}")
    print(f"  => STOP-entry-all is {'BETTER' if d.stop_net.sum()>fill.retest_net.sum() else 'WORSE'} by "
          f"{d.stop_net.sum()-fill.retest_net.sum():+,.0f}")
    fill=fill.rename(columns={"stop_net":"net"})  # for the chart below

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11,5), dpi=120)
    yrs=sorted(miss.yr.unique()); nety=[miss[miss.yr==y].stop_net.sum() for y in yrs]
    ax.bar(yrs,nety,color=["#2e8b57" if v>=0 else "#b23a2e" for v in nety])
    for i,v in enumerate(nety): ax.annotate(f"${v:,.0f}\nPF {pf(miss[miss.yr==yrs[i]].stop_net)}",(i,v),textcoords="offset points",xytext=(0,4 if v>=0 else -18),ha="center",fontsize=8.5)
    ax.axhline(0,color="#333")
    ax.set_title(f"The 154 MISSED signals via stop-entry: net ${miss.stop_net.sum():+,.0f}, PF {pf(miss.stop_net)}",
                 fontweight="bold", fontsize=11)
    for s_ in ("top","right"): ax.spines[s_].set_visible(False)
    fig.tight_layout(); fig.savefig(WT/"docs"/"living"/"missed_pnl.png", facecolor="white")
    print("\nsaved docs/living/missed_pnl.png")


if __name__ == "__main__":
    main()
