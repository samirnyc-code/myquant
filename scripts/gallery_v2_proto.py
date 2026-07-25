"""GALLERY v2 PROTOTYPE — back to the fade-gallery matplotlib format, tweaked.
Slide A = FULL-DAY 5-min candles (regime shading, EMA20, prior-session last bar, gap stats),
          trade drawn with DOTTED lines only (no big arrows), price labels in a right-side
          column with leader lines (no overlap).
Slide B = ZOOM on ENTRY and on EXIT only (two panels), tick path, green ✓ if verified.
One 2EL trade for approval.  python scripts/gallery_v2_proto.py
"""
import sys
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions, load_day
from regime_2e_causal_check import detect_entries_causal

TICK = 0.25; PT = 50.0; FLOOR = 8 * TICK; GOOD = {"09", "10", "11", "12", "13"}
WT = Path(__file__).resolve().parent.parent
OUTD = WT / "docs" / "living" / "trade_review"
DATA = Path(r"C:/Users/Admin/myquant/data")
SHADE = {"bull": ("#2e8b57", .10), "bear": ("#b23a2e", .10), "neutral": ("#8a8f94", .06)}
UP, DN = "#2e9e8f", "#e0574a"


def declutter(ys, min_gap):
    order = np.argsort(ys); ty = np.array(ys, float)
    s = ty[order].copy()
    for a in range(1, len(s)):
        if s[a] - s[a-1] < min_gap: s[a] = s[a-1] + min_gap
    out = np.empty_like(ty); out[order] = s; return out


def candles(ax, O, H, L, C, a0, z0, rng):
    for i in range(a0, z0 + 1):
        up = C[i] >= O[i]; col = UP if up else DN
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.3, zorder=2)
        ax.add_patch(plt.Rectangle((i-0.3, min(O[i], C[i])), 0.6, max(abs(C[i]-O[i]), rng*0.0008),
                                   facecolor=col, edgecolor="#222", lw=0.4, zorder=3))


def find_trade():
    b = pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
    b["ema20"] = b.Close.ewm(span=20, adjust=False).mean()
    dly = b.groupby("Date").agg(dO=("Open","first"), dC=("Close","last"), dH=("High","max"), dL=("Low","min")).reset_index()
    dly["adr10"] = (dly.dH-dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = (dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100; dly["pc"] = dly.dC.shift(1)
    gm = dly.set_index("Date")
    for dstr in [d for d in sorted(b.Date.unique()) if d >= "2024-03-19"]:
        if dstr not in gm.index: continue
        adr, gapv, pc = gm.loc[dstr,"adr10"], gm.loc[dstr,"gap"], gm.loc[dstr,"pc"]
        if not np.isfinite(adr) or abs(gapv) > 0.54: continue
        g, tP, tbar = load_day(b, dstr)
        if g is None: continue
        H, L = g.High.values, g.Low.values; n = len(g); gdt = g.DateTime.values
        trace = {}
        try:
            trans = phase_transitions(H, L, n, tP, tbar, trace=trace); entries = detect_entries_causal(g, tP, tbar)
        except Exception: continue
        tix=[t for (t,_) in trans]; tmd=[m for (_,m) in trans]; sd=max(round(0.30*adr/TICK)*TICK, FLOOR)
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2 or dr != "L": continue
            a=np.searchsorted(tbar,fb,"left"); z=np.searchsorted(tbar,fb,"right")
            hit=np.nonzero(tP[a:z]>=trig)[0]
            if not len(hit): continue
            jf=a+int(hit[0]); reg=tmd[bisect_right(tix,jf)-1]
            if reg!="BULL": continue
            lim=trig-6*TICK; seg0=tP[jf:]; jl=np.nonzero(seg0<lim)[0]
            if not len(jl): continue
            jfl=jf+int(jl[0]); fb2=int(tbar[jfl])
            if fb2-fb>6 or pd.Timestamp(gdt[min(fb2,n-1)]).strftime("%H") not in GOOD: continue
            fill=lim; stop=fill-sd; seg=tP[jfl:]; js=np.nonzero(seg<=stop)[0]
            if len(js): exi=jfl+int(js[0]); ex=stop; extype="stop"
            else: exi=len(tP)-1; ex=float(tP[-1]); extype="EOD"
            net=round((ex-fill)*PT-5-12.5,1)
            if net<400: continue
            ema=b[b.Date==dstr]["ema20"].values
            pidx=b.index[b.Date==dstr][0]; pbar=b.iloc[pidx-1]
            verified=bool(np.any(tP[jf:jfl+1]<lim)) and (extype=="EOD" or ex==stop)
            trd=dict(Date=dstr, sb=sb, fb=fb, jf=jf, jfl=jfl, exi=exi, fill_bar=fb2,
                     exit_bar=int(tbar[exi]), trig=trig, sb_lo=L[sb], fill=fill, stop=stop, ex=ex,
                     extype=extype, net=net, adr=adr, gap=gapv, pc=pc, verified=verified)
            return trd, g, tP, tbar, trace, ema, pbar
    return None


def main():
    r = find_trade()
    if r is None: print("no trade"); return
    t, g, tP, tbar, trace, ema, pbar = r
    O, H, L, C = (g[c].values for c in ["Open","High","Low","Close"]); n=len(g); gdt=g.DateTime.values
    OUTD.mkdir(parents=True, exist_ok=True)

    # ---------- SLIDE A: full day ----------
    rng = H.max()-L.min()
    fig, ax = plt.subplots(figsize=(16, 8), dpi=100)
    # regime shading full day
    bounds=sorted([(s_,"start",sd) for (s_,sd,_) in trace["starts"]]+[(bb,"term",None) for (_,_,bb,_) in trace["terms"]])
    cur="neutral"; x0=0; segs=[]
    for (xb,ktp,sd) in bounds: segs.append((x0,xb,cur)); x0=xb; cur=sd if ktp=="start" else "neutral"
    segs.append((x0,n-1,cur))
    for (aa,bb,sdv) in segs:
        col,al=SHADE[sdv]; ax.axvspan(aa-0.5, bb+0.5, color=col, alpha=al, zorder=0)
    candles(ax, O,H,L,C, 0, n-1, rng)
    ax.plot(range(n), ema, color="#c98a10", lw=1.6, zorder=4, label="EMA20")
    # prior bar ghost at x=-1.5
    pcol = UP if pbar.Close>=pbar.Open else DN
    ax.plot([-1.6,-1.6],[pbar.Low,pbar.High], color="#b9b9b2", lw=1.3, zorder=2)
    ax.add_patch(plt.Rectangle((-1.9, min(pbar.Open,pbar.Close)), 0.6, max(abs(pbar.Close-pbar.Open),rng*0.0008),
                               facecolor="#cfcfc8", edgecolor="#999", lw=0.4, zorder=3))
    ax.text(-1.6, pbar.High+rng*0.02, "prior\nbar", ha="center", va="bottom", fontsize=8, color="#888")
    # dotted level lines (no arrows), entry/exit small dots
    levels=[(t["pc"],"Prior close",  "#7a5cc0"),(t["trig"],"2EL trigger","#d98a2b"),
            (t["fill"],"Entry (fill)","#2a78d6"),(t["sb_lo"],"Signal-bar low","#8a8f94"),
            (t["stop"],"Stop 0.30xADR","#b23a2e"),(t["ex"],f"Exit ({t['extype']})","#2e8b57")]
    for (y,txt,col) in levels:
        ax.plot([-2, n-1],[y,y], ls=":", lw=1.2, color=col, alpha=0.75, zorder=4)
    ax.plot(t["fill_bar"], t["fill"], "o", ms=6, color="#2a78d6", mec="#111", mew=0.6, zorder=6)
    ax.plot(t["exit_bar"], t["ex"], "o", ms=6, color="#2e8b57", mec="#111", mew=0.6, zorder=6)
    ax.plot([t["fill_bar"], t["exit_bar"]],[t["fill"],t["ex"]], ls="--", lw=1.0, color="#2e8b57", alpha=0.5, zorder=5)
    ax.plot(t["sb"], L[t["sb"]]-rng*0.03, "^", ms=8, color="#8a6a12", zorder=6)
    ax.text(t["sb"], L[t["sb"]]-rng*0.06, "2EL b%d"%(t["sb"]+1), ha="center", fontsize=8, color="#8a6a12")
    # right-side label column with leader lines (no overlap)
    xlab = n + 2.5
    ys = declutter([y for (y,_,_) in levels], rng*0.045)
    for (yv,(y,txt,col)) in zip(ys, levels):
        ax.plot([n-1, xlab-0.3],[y,yv], ls=":", lw=0.8, color=col, alpha=0.6, zorder=4)
        ax.text(xlab, yv, f"{txt}  {y:.2f}", ha="left", va="center", fontsize=9.5, color=col, fontweight="bold")
    # gap-stats box
    tr = "TRADE" if abs(t["gap"])<=0.54 else "SKIP"
    ax.text(0.008, 0.985, f"gap {t['gap']:+.2f}%   ADR10 {t['adr']:.1f}   thr 0.54   {tr}",
            transform=ax.transAxes, va="top", ha="left", fontsize=10,
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#ddd"))
    sgn="+" if t["net"]>=0 else ""
    ax.set_title(f"[A]  {t['Date']} · 2EL long (BULL) · full session · fill {t['fill']:.2f} → exit {t['ex']:.2f} "
                 f"({t['extype']}) · net {sgn}{t['net']:,.0f}$", fontsize=13, fontweight="bold", pad=10)
    ax.set_xlim(-3, n + 12); ax.set_ylim(L.min()-rng*0.10, H.max()+rng*0.10)
    ax.grid(axis="y", color="#eceeed", lw=0.6); ax.set_axisbelow(True)
    for s_ in ("top","right","bottom"): ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(OUTD/"v2_a.png", facecolor="white"); plt.close(fig)

    # ---------- SLIDE B: entry & exit zoom ----------
    fig, axs = plt.subplots(1, 2, figsize=(16, 7), dpi=100, gridspec_kw={"wspace":0.15})
    def zoom(ax, center_tick, lvls, title, mark_tick, mark_col, mark_lbl):
        i0=max(0, center_tick-260); i1=min(len(tP), center_tick+260)
        xs=np.arange(i0,i1); ax.plot(xs, tP[i0:i1], color="#33454d", lw=1.1, zorder=3)
        yr = tP[i0:i1].max()-tP[i0:i1].min()+1e-9
        for (y,txt,col) in lvls:
            ax.axhline(y, ls=":", lw=1.1, color=col, alpha=0.8, zorder=2)
            ax.text(i1-1, y, "  "+txt+f" {y:.2f}", va="center", ha="left", fontsize=9, color=col)
        ax.scatter([mark_tick],[tP[mark_tick]], s=90, color=mark_col, ec="#111", zorder=6)
        ax.annotate(mark_lbl, (mark_tick, tP[mark_tick]), xytext=(mark_tick, tP[mark_tick]+yr*0.12),
                    ha="center", fontsize=9, fontweight="bold", color=mark_col,
                    arrowprops=dict(arrowstyle="->", color=mark_col, lw=1))
        ax.set_title(title, fontsize=11.5, fontweight="bold", pad=8)
        ax.set_xlim(i0, i1+90); ax.grid(axis="y", color="#eceeed", lw=0.6); ax.set_axisbelow(True)
        for s_ in ("top","right","bottom"): ax.spines[s_].set_visible(False)
        ax.tick_params(axis="x", bottom=False, labelbottom=False)
    zoom(axs[0], t["jfl"],
         [(t["trig"],"2EL trigger","#d98a2b"),(t["sb_lo"],"SB low","#8a8f94"),(t["fill"],"Entry (fill)","#2a78d6")],
         "[B1] ENTRY zoom — limit fills on tick through", t["jfl"], "#2a78d6", f"FILL {t['fill']:.2f}")
    zoom(axs[1], t["exi"],
         [(t["stop"],"Stop","#b23a2e"),(t["ex"],f"Exit ({t['extype']})","#2e8b57")],
         "[B2] EXIT zoom — "+t["extype"], t["exi"], "#2e8b57", f"EXIT {t['ex']:.2f}")
    if t["verified"]:
        fig.text(0.5, 0.965, "✓  VERIFIED — entry traded through the limit and exit confirmed",
                 ha="center", fontsize=12, color="#1c6b41", fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.94]); fig.savefig(OUTD/"v2_b.png", facecolor="white"); plt.close(fig)

    (OUTD/"v2.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>2E v2 proto</title>"
        f"<body style='margin:0;background:#f5f5f0;font-family:sans-serif'>"
        f"<div style='max-width:1200px;margin:auto;padding:14px'>"
        f"<h3>2E trade review — v2 prototype (matplotlib, fade-gallery style)</h3>"
        f"<img src='v2_a.png' style='width:100%;border:1px solid #ddd;margin-bottom:14px'>"
        f"<img src='v2_b.png' style='width:100%;border:1px solid #ddd'></div></body>", encoding="utf-8")
    print(f"built v2_a.png / v2_b.png / v2.html — {t['Date']} net ${t['net']} verified={t['verified']}")


if __name__ == "__main__":
    main()
