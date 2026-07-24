"""FADE gallery v2 — EOD-hold exit + 5M context slide + TICK-PATH zoom slide per trade.

Each f2EL fade trade gets TWO slides:
  A) 5-minute context: regime shading, 2EL signal bar, trigger level, failure/entry
     level, fill, 4pt stop, dotted line to EOD/stop exit, PnL, RevFT marks.
     Written prices: 2EL trigger, entry (failure) level, fill.
  B) TICK-PATH zoom: from 2 bars before the signal bar to 1 bar after the fill,
     the actual tick price path (line), bar boundaries, and the levels — so you can
     watch price tick THROUGH the 2EL trigger (up) then THROUGH the SB low (down =
     fade fills). Confirms each trade is taken correctly, like the ES sim app.

NOTE: the fade has NO 6t pullback (that is the with-trend entry). It is a stop-entry
at the signal-bar-low failure. Exit = stop or EOD (the validated book, PF 1.36 — NOT
the opposite-flip exit which scores worse).

CAUSAL: signal-bar low from a COMPLETED bar before the fill (audited A1=100%).
  python scripts/regime_fade_gallery.py [--limit N]
Output: docs/living/fade_gallery/<id>_a.png + _b.png + index.html
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402
from gapday_alt_signals import parse_signals, SIG_REV               # noqa: E402

OUTD = WT / "docs" / "living" / "fade_gallery"
GOOD = {"09", "10", "11", "12", "13"}
KFADE = 2
SHADE = {"neutral": ("#9aa0a6", 0.10), "bull": ("#1f7a3d", 0.08), "bear": ("#b23a2e", 0.08)}


def declutter(labels, min_gap):
    """labels = list of (y, text, color). Returns (y_line, y_text, text, color) with
    text y-positions pushed apart by >= min_gap so nothing overlaps; lines stay at true y."""
    order = sorted(range(len(labels)), key=lambda i: labels[i][0])
    ys = [labels[i][0] for i in order]
    ty = list(ys)
    for a in range(1, len(ty)):
        if ty[a] - ty[a-1] < min_gap:
            ty[a] = ty[a-1] + min_gap
    out = [None]*len(labels)
    for pos, i in enumerate(order):
        out[i] = (labels[i][0], ty[pos], labels[i][1], labels[i][2])
    return out


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    for f in OUTD.glob("*.png"):
        f.unlink()
    OUTD.mkdir(parents=True, exist_ok=True)
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"),
                                dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gmap = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    try:
        rev = parse_signals(SIG_REV); rev_by = {d_: g_ for d_, g_ in rev.groupby("Date")}
    except Exception:
        rev_by = {}

    done = []; t0 = time.time(); k = 0
    for di, dstr in enumerate(days):
        if dstr not in gmap.index:
            continue
        adr, gapv = gmap.loc[dstr, "adr10"], gmap.loc[dstr, "gap"]
        if not np.isfinite(adr) or gapv > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        trace = {}
        try:
            trans = phase_transitions(H, L, n, tP, tbar, trace=trace)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True); continue
        tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
        g_dt = g["DateTime"].values
        tight = 16 * TICK
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2 or dr != "L":
                continue
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:z] >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0])
            if tr_md[bisect_right(tr_ix, jf) - 1] != "BEAR":
                continue
            fail_px = L[sb] - TICK
            zlim = np.searchsorted(tbar, fb + KFADE + 1, "left")
            w = np.nonzero(tP[jf:zlim] <= fail_px)[0]
            if not len(w):
                continue
            jx = jf + int(w[0]); fill_bar = int(tbar[jx])
            hh = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
            if hh not in GOOD or sb >= fill_bar:        # A1 causal guard
                continue
            fill = fail_px - TICK; stop = fill + tight
            seg = tP[jx:]
            js_ = np.nonzero(seg >= stop)[0]
            if len(js_):
                ex, extype = stop, "stop"; exi = jx + int(js_[0])
            else:
                ex, extype = seg[-1], "eod"; exi = len(tP) - 1
            exit_bar = int(tbar[min(exi, len(tbar) - 1)])
            net = round((fill - ex) * PT - COMM - SLIP, 1)
            trd = dict(Date=dstr, sb=sb, fb=fb, jf=jf, jx=jx, exi=exi,
                       fill_bar=fill_bar, exit_bar=exit_bar, trig=trig, sb_hi=H[sb],
                       sb_lo=L[sb], fail_px=fail_px, fill=fill, stop=stop, ex=ex,
                       extype=extype, net=net)
            render_5m(trd, g, trace, rev_by.get(dstr), k)
            render_zoom(trd, g, tP, tbar, k)
            done.append((k, dstr, net, extype)); k += 1
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] fades={k} ({time.time()-t0:.0f}s)", flush=True)

    write_index(done)
    print(f"\nrendered {k} fades (2 slides each) -> {OUTD/'index.html'}")


def render_5m(t, g, trace, rev, k):
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    a0 = max(0, t["sb"] - 6); z0 = min(n - 1, t["exit_bar"] + 6)
    rng = H[a0:z0+1].max() - L[a0:z0+1].min(); off = rng * 0.035
    fig, ax = plt.subplots(figsize=(15, 8), dpi=100)
    bounds = sorted([(s_, "start", sd) for (s_, sd, _) in trace["starts"]] +
                    [(bb, "term", None) for (_, _, bb, _) in trace["terms"]])
    cur = "neutral"; x0 = 0; segs = []
    for (xb, ktp, sd) in bounds:
        segs.append((x0, xb, cur)); x0 = xb
        cur = sd if ktp == "start" else "neutral"
    segs.append((x0, n - 1, cur))
    for (aa, bb, sdv) in segs:
        col, al = SHADE[sdv]
        ax.axvspan(max(aa, a0) - 0.5, min(bb, z0) + 0.5, color=col, alpha=al, zorder=0)
    for i in range(a0, z0 + 1):
        up = C[i] >= O[i]; col = "#2e9e8f" if up else "#e0574a"
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.5, zorder=2)
        ax.add_patch(plt.Rectangle((i - 0.3, min(O[i], C[i])), 0.6,
                                   max(abs(C[i] - O[i]), rng * 0.001),
                                   facecolor=col, edgecolor="black", lw=0.4, zorder=3))
    fb, fill, stop, exb, ex = t["fill_bar"], t["fill"], t["stop"], t["exit_bar"], t["ex"]
    # signal bar + levels (right-anchored labels, staggered to avoid overlap)
    ax.plot(t["sb"], L[t["sb"]] - off * 0.5, "^", ms=10, color="#8a6a12", zorder=6)
    ax.text(t["sb"], L[t["sb"]] - off * 1.3, "2EL sig b%d" % (t["sb"]+1), ha="center",
            fontsize=9, color="#8a6a12")
    lab = [(t["trig"], "2EL trigger  %.2f" % t["trig"], "#8a6a12", ":"),
           (t["fail_px"], "entry lvl (SB low-1t)  %.2f" % t["fail_px"], "#b23a2e", "-"),
           (fill, "FILL  %.2f" % fill, "#b23a2e", "-"),
           (stop, "stop 4pt  %.2f" % stop, "#b23a2e", ":")]
    for (y, txt, col, ls) in lab:
        ax.plot([a0 - 0.5, exb + 1], [y, y], ls=ls, lw=1.3, color=col, alpha=0.7, zorder=4)
        ax.text(a0 - 0.6, y, txt, ha="right", va="center", fontsize=9, color=col)
    ax.plot(fb, fill, "v", ms=17, color="#b23a2e", mec="black", mew=1.4, zorder=7)
    ax.plot([fb, exb], [fill, ex], ls="--", lw=1.5, color="#b23a2e", alpha=0.7, zorder=5)
    ax.plot(exb, ex, "s", ms=12, color="#b23a2e", mec="black", mew=1.2, zorder=7)
    ax.text(exb, ex + (off if ex < fill else -off), "exit %s  %.2f" % (t["extype"], ex),
            ha="center", fontsize=9, fontweight="bold", color="#b23a2e",
            va="bottom" if ex < fill else "top")
    if rev is not None:
        gd = pd.to_datetime(g["DateTime"]).values
        for r in rev.itertuples():
            idx = int(np.searchsorted(gd, np.datetime64(r.DateTime))) - 1
            if a0 <= idx <= z0:
                sh = r.Direction.lower().startswith("s")
                yy = H[idx] + off * 1.8 if sh else L[idx] - off * 1.8
                ax.text(idx, yy, "R" + ("v" if sh else "^"), ha="center", fontsize=9,
                        color="#eb6834", fontweight="bold")
    sgn = "+" if t["net"] >= 0 else ""
    ax.set_title(f"[A] f2EL fade — {t['Date']}   fill {fill:.2f} -> exit {ex:.2f} ({t['extype']})"
                 f"   net {sgn}{t['net']:,.0f}$   EOD-hold book", fontsize=12.5,
                 fontweight="bold", pad=10)
    ax.set_xlim(a0 - 2.5, z0 + 3)
    ax.set_ylim(L[a0:z0+1].min() - rng*0.13, H[a0:z0+1].max() + rng*0.13)
    ax.grid(axis="y", color="#eceeed", lw=0.6); ax.set_axisbelow(True)
    for s_ in ("top", "right", "bottom"): ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    fig.tight_layout()
    fig.savefig(OUTD / f"fade_{k:04d}_{t['Date']}_a.png", facecolor="white")
    plt.close(fig)


def render_zoom(t, g, tP, tbar, k):
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    b_from = max(0, t["sb"] - 2); b_to = min(n - 1, t["fill_bar"] + 1)
    i0 = int(np.searchsorted(tbar, b_from, "left"))
    i1 = int(np.searchsorted(tbar, b_to + 1, "left"))
    xs = np.arange(i0, i1); pxs = tP[i0:i1]
    fig, ax = plt.subplots(figsize=(15, 8), dpi=100)
    # bar-boundary bands + numbers + OHLC ghost
    for bb in range(b_from, b_to + 1):
        s = int(np.searchsorted(tbar, bb, "left")); e = int(np.searchsorted(tbar, bb + 1, "left"))
        if bb % 2 == 0:
            ax.axvspan(s, e, color="#f3f3ef", zorder=0)
        ax.text((s + e) / 2, H[b_from:b_to+1].max(), "b%d" % (bb + 1), ha="center",
                va="bottom", fontsize=9, color="#555")
        ax.plot([s, e - 1], [O[bb], O[bb]], color="#bbb", lw=0.8, zorder=1)
    # the tick path
    ax.plot(xs, pxs, color="#2a78d6", lw=1.1, zorder=3)
    ax.scatter(xs, pxs, s=6, color="#2a78d6", zorder=4)
    # levels
    for (y, txt, col) in [(t["sb_hi"], "SB high %.2f" % t["sb_hi"], "#8a6a12"),
                          (t["trig"], "2EL trigger %.2f" % t["trig"], "#8a6a12"),
                          (t["sb_lo"], "SB low %.2f" % t["sb_lo"], "#b23a2e"),
                          (t["fail_px"], "fail lvl (SBlow-1t) %.2f" % t["fail_px"], "#b23a2e"),
                          (t["fill"], "FILL %.2f" % t["fill"], "#111")]:
        ax.axhline(y, ls="--", lw=1, color=col, alpha=0.7, zorder=2)
        ax.text(i1 - 1, y, " " + txt, va="center", fontsize=9, color=col)
    # trigger tick (2EL fires) + fill tick (fade fills)
    ax.scatter([t["jf"]], [tP[t["jf"]]], s=140, marker="^", color="#8a6a12",
               ec="black", zorder=6, label="2EL triggers (tick up through trigger)")
    ax.scatter([t["jx"]], [tP[t["jx"]]], s=170, marker="v", color="#b23a2e",
               ec="black", zorder=6, label="FADE fills (ticks down through SB low)")
    ax.annotate("2EL trigger\ntick %d" % t["jf"], (t["jf"], tP[t["jf"]]),
                xytext=(t["jf"], tP[t["jf"]] + (H[b_from:b_to+1].max()-L[b_from:b_to+1].min())*0.06),
                ha="center", fontsize=9, color="#8a6a12", fontweight="bold")
    ax.annotate("FILL tick %d" % t["jx"], (t["jx"], tP[t["jx"]]),
                xytext=(t["jx"], tP[t["jx"]] - (H[b_from:b_to+1].max()-L[b_from:b_to+1].min())*0.06),
                ha="center", fontsize=9, color="#b23a2e", fontweight="bold")
    ax.set_title(f"[B] TICK PATH zoom — {t['Date']}  b{b_from+1}..b{b_to+1}  "
                 f"({len(xs)} ticks)   price ticks UP through the 2EL trigger, "
                 f"then DOWN through the SB low = fade short fills", fontsize=12,
                 fontweight="bold", pad=10)
    ax.legend(loc="lower left", fontsize=9, frameon=False)
    ax.set_xlabel("tick sequence"); ax.set_xlim(i0 - 1, i1 + int((i1-i0)*0.12))
    ax.grid(axis="y", color="#eceeed", lw=0.6); ax.set_axisbelow(True)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUTD / f"fade_{k:04d}_{t['Date']}_b.png", facecolor="white")
    plt.close(fig)


def write_index(done):
    items = ",".join(f"['fade_{k:04d}_{d}',{net:+.0f},'{ex}']" for (k, d, net, ex) in done)
    html = f"""<!doctype html><meta charset='utf-8'><title>f2EL fade gallery</title>
<style>body{{font-family:Segoe UI,Arial;margin:8px;background:#14181d;color:#eee;text-align:center}}
img{{max-width:99%;border:1px solid #444;background:#fff}}
button{{font-size:15px;padding:4px 12px;margin:0 5px}}.pos{{color:#3fae67}}.neg{{color:#d76454}}
#tab button.on{{background:#2a78d6;color:#fff}}</style>
<div style='margin:6px'><button onclick='go(-1)'>&larr; prev trade</button>
<span id='lbl'></span><button onclick='go(1)'>next trade &rarr;</button>
&nbsp;|&nbsp;<span id='tab'><button id='ta' class='on' onclick='sl(0)'>A: 5-min</button>
<button id='tb' onclick='sl(1)'>B: tick zoom</button></span>
&nbsp;|&nbsp;<button onclick='filt=0;i=0;show()'>all</button>
<button onclick='filt=1;i=0;show()'>winners</button><button onclick='filt=-1;i=0;show()'>losers</button></div>
<img id='im'><script>
var D=[{items}],i=0,filt=0,slide=0;
function vis(){{return D.map((d,j)=>j).filter(j=>filt==0||(filt>0?D[j][1]>0:D[j][1]<=0));}}
function sl(s){{slide=s;document.getElementById('ta').className=s==0?'on':'';
document.getElementById('tb').className=s==1?'on':'';show();}}
function show(){{var v=vis();if(!v.length)return;if(i>=v.length)i=0;var d=D[v[i]];
document.getElementById('im').src=d[0]+(slide==0?'_a':'_b')+'.png';
document.getElementById('lbl').innerHTML=(i+1)+'/'+v.length+'  '+d[0].slice(10)+
'  <b class='+(d[1]>=0?'pos':'neg')+'>'+(d[1]>=0?'+':'')+d[1]+'$</b> ('+d[2]+')';}}
function go(k){{var v=vis();i=(i+k+v.length)%v.length;show();}}
document.addEventListener('keydown',e=>{{if(e.key=='ArrowLeft')go(-1);if(e.key=='ArrowRight')go(1);
if(e.key=='ArrowUp'||e.key=='ArrowDown'){{sl(1-slide);e.preventDefault();}}}});
show();</script>"""
    (OUTD / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
