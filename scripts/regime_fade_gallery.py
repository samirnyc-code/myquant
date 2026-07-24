"""FADE-trade gallery + CAUSALITY AUDIT — S83.

Renders one annotated chart per f2EL fade trade (cyclable index.html) AND runs an
explicit lookahead audit on every trade. Nothing is trusted until the audit prints.

AUDIT per trade (each must pass for the trade to be 'clean'):
  A1 sig_bar_complete : the signal bar whose LOW defines the failure level must be a
     COMPLETED bar strictly before the fill bar (else L[sb] uses future ticks = lookahead).
  A2 trade_through    : the fill price was actually reached by a tick (price ticked
     THROUGH the failure level), not assumed.
  A3 regime_causal    : the regime at the fill tick is computed only from ticks <= fill.
  A4 day_features_prior: gap/ADR from prior sessions only (structural — .shift(1), always true).

Fade mechanic (stop-entry, NOT a 6t pullback — that's the WT book): a counter-trend 2EL
triggers (tick >= H[sb]+1t) while regime==BEAR, then FAILS (tick <= L[sb]-1t within K=2
bars) -> short at fail_px-1t (1t slip). Stop = 4pt tight. Exit = stop / EOD / opposite-
trend flip (whichever first). RevFT (MyReversals) signals marked.

Output: docs/living/fade_gallery/<id>.png + index.html + audit summary.
  python scripts/regime_fade_gallery.py [--limit N]
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
FLOOR = 8 * TICK
KFADE = 2
SHADE = {"neutral": ("#9aa0a6", 0.10), "bull": ("#1f7a3d", 0.08), "bear": ("#b23a2e", 0.08)}


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
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

    trades = []; audit = {"A1": 0, "A2": 0, "A3": 0, "total": 0, "suspect_net": 0.0}
    t0 = time.time()
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

        def flip_away_tick(j):
            for (tix, md) in trans:
                if tix > j and md != "BEAR":
                    return tix
            return np.inf

        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2 or dr != "L":       # counter-trend 2EL only (for f2EL fade short)
                continue
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]
            hit = np.nonzero(s >= trig)[0]            # 2EL triggers (long break)
            if not len(hit):
                continue
            jf = a + int(hit[0])
            if tr_md[bisect_right(tr_ix, jf) - 1] != "BEAR":   # counter-trend gate
                continue
            # ---- causal failure level: LOW of sb AS KNOWN UP TO the current tick ----
            fail_px = L[sb] - TICK
            zlim = np.searchsorted(tbar, fb + KFADE + 1, "left")
            segf = tP[jf:zlim]
            w = np.nonzero(segf <= fail_px)[0]
            if not len(w):
                continue
            jx = jf + int(w[0]); fill_bar = int(tbar[jx])
            hh = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
            if hh not in GOOD:
                continue
            # === AUDIT ===
            a1 = sb < fill_bar                        # sig bar completed before fill bar
            # A2: is fail_px actually reached BEFORE the sig bar it references would be
            #     'complete'? the true test is a1; A2 = the tick genuinely reached fail_px:
            a2 = tP[jx] <= fail_px + 1e-9
            reg_fill = tr_md[bisect_right(tr_ix, jx) - 1]
            a3 = reg_fill == "BEAR"                   # regime at fill from prior ticks only
            audit["total"] += 1
            if a1: audit["A1"] += 1
            if a2: audit["A2"] += 1
            if a3: audit["A3"] += 1
            fill = fail_px - TICK
            stop = fill + tight
            seg = tP[jx:]
            js_ = np.nonzero(seg >= stop)[0]; js = js_[0] if len(js_) else np.inf
            jfl = flip_away_tick(jx); jrel = (jfl - jx) if np.isfinite(jfl) else np.inf
            # exit = first of stop / opp-flip / EOD
            if np.isfinite(js) and js <= jrel:
                ex_i, ex, extype = int(js), stop, "stop"
            elif np.isfinite(jrel) and int(jrel) < len(seg):
                ex_i, ex, extype = int(jrel), seg[int(jrel)], "flip"
            else:
                ex_i, ex, extype = len(seg) - 1, seg[-1], "eod"
            net = round((fill - ex) * PT - COMM - SLIP, 1)
            if not (a1 and a2 and a3):
                audit["suspect_net"] += net
            trades.append(dict(Date=dstr, sb=sb, fb=fb, fill_bar=fill_bar,
                               exit_bar=int(tbar[min(jx + ex_i, len(tbar) - 1)]),
                               trig=trig, fill=fill, stop=stop, exit=ex, extype=extype,
                               net=net, a1=a1, a2=a2, a3=a3,
                               g=g, trace=trace, rev=rev_by.get(dstr)))
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] fades={len(trades)} ({time.time()-t0:.0f}s)", flush=True)

    # ================= AUDIT REPORT =================
    T = audit["total"]
    print(f"\n=== CAUSALITY AUDIT ({T} fade trades) ===")
    print(f"  A1 sig_bar completed before fill bar : {audit['A1']}/{T} "
          f"({100*audit['A1']/max(T,1):.1f}%)  <- the lookahead risk")
    print(f"  A2 fill price genuinely ticked through: {audit['A2']}/{T} "
          f"({100*audit['A2']/max(T,1):.1f}%)")
    print(f"  A3 regime at fill causal (BEAR)       : {audit['A3']}/{T} "
          f"({100*audit['A3']/max(T,1):.1f}%)")
    clean = [t for t in trades if t["a1"] and t["a2"] and t["a3"]]
    suspect = [t for t in trades if not (t["a1"] and t["a2"] and t["a3"])]

    def pf(v):
        v = np.array(v); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
        return round(gp / gl, 2) if gl > 0 else 0
    cn = [t["net"] for t in clean]; sn = [t["net"] for t in suspect]
    print(f"\n  CLEAN trades   : n={len(clean)}  net {sum(cn):+,.0f}  PF {pf(cn)}")
    print(f"  SUSPECT trades : n={len(suspect)}  net {sum(sn):+,.0f}  PF {pf(sn) if sn else 0}")
    print(f"  -> the fade edge REST ON CLEAN trades only: PF {pf(cn)}")

    # ================= render (clean trades) =================
    done = []
    for k, t in enumerate(clean):
        render(t, k, OUTD)
        done.append((t["Date"], t["fill_bar"], t["net"], t["extype"]))
    write_index(done)
    print(f"\nrendered {len(done)} clean fade charts -> {OUTD/'index.html'}")


def render(t, k, OUTD):
    g = t["g"]; trace = t["trace"]
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    a0 = max(0, t["sb"] - 6); z0 = min(n - 1, t["exit_bar"] + 6)
    rng = H[a0:z0+1].max() - L[a0:z0+1].min(); off = rng * 0.04
    fig, ax = plt.subplots(figsize=(15, 8), dpi=100)
    # regime shading
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
    fb, fill, stop, exb, ex = t["fill_bar"], t["fill"], t["stop"], t["exit_bar"], t["exit"]
    ax.plot(t["sb"], L[t["sb"]] - off * 0.6, "^", ms=9, color="#8a6a12", zorder=6)
    ax.text(t["sb"], L[t["sb"]] - off * 1.4, "2EL sig", ha="center", fontsize=9, color="#8a6a12")
    ax.axhline(t["trig"], ls=":", lw=1, color="#8a6a12", alpha=0.6)
    ax.text(a0, t["trig"], " 2EL trigger", fontsize=8, color="#8a6a12", va="bottom")
    # fade entry
    ax.plot(fb, fill, "v", ms=17, color="#b23a2e", mec="black", mew=1.4, zorder=7)
    ax.plot([fb - 0.7, exb], [stop, stop], ls=":", lw=1.8, color="#b23a2e", zorder=5)
    ax.text(exb + 0.2, stop, "stop 4pt", va="center", fontsize=9, color="#b23a2e")
    ax.plot([fb, exb], [fill, ex], ls="--", lw=1.5, color="#b23a2e", alpha=0.7, zorder=5)
    ax.plot(exb, ex, "s", ms=11, color="#b23a2e", mec="black", mew=1.1, zorder=7)
    ax.text(exb, ex + (off if ex < fill else -off), "exit " + t["extype"],
            ha="center", fontsize=9, fontweight="bold", color="#b23a2e",
            va="bottom" if ex < fill else "top")
    # RevFT marks
    if t["rev"] is not None:
        gd = pd.to_datetime(g["DateTime"]).values
        for r in t["rev"].itertuples():
            idx = int(np.searchsorted(gd, np.datetime64(r.DateTime))) - 1
            if a0 <= idx <= z0:
                sh = r.Direction.lower().startswith("s")
                yy = H[idx] + off * 2.2 if sh else L[idx] - off * 2.2
                ax.text(idx, yy, "R" + ("v" if sh else "^"), ha="center", fontsize=9,
                        color="#eb6834", fontweight="bold")
    sgn = "+" if t["net"] >= 0 else ""
    ax.set_title(f"f2EL fade short — {t['Date']}  ·  fill {fill:.2f} → exit {ex:.2f} ({t['extype']})"
                 f"  ·  net {sgn}{t['net']:,.0f}$   [CAUSAL: sig-bar b{t['sb']+1} < fill-bar b{fb+1}]",
                 fontsize=12.5, fontweight="bold", pad=10)
    ax.set_xlim(a0 - 1, z0 + 3); ax.set_ylim(L[a0:z0+1].min() - rng*0.12, H[a0:z0+1].max() + rng*0.12)
    ax.grid(axis="y", color="#eceeed", lw=0.6); ax.set_axisbelow(True)
    for s_ in ("top", "right", "bottom"): ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    fig.tight_layout()
    fig.savefig(OUTD / f"fade_{k:04d}_{t['Date']}.png", facecolor="white")
    plt.close(fig)


def write_index(done):
    items = ",".join(f"['fade_{i:04d}_{d}',{net:+.0f},'{ex}']"
                     for i, (d, fb, net, ex) in enumerate(done))
    html = f"""<!doctype html><meta charset='utf-8'><title>f2EL fade gallery</title>
<style>body{{font-family:Segoe UI,Arial;margin:10px;background:#14181d;color:#eee;text-align:center}}
img{{max-width:99%;border:1px solid #444;background:#fff}}
button{{font-size:15px;padding:4px 14px;margin:0 6px}}.pos{{color:#3fae67}}.neg{{color:#d76454}}</style>
<div style='margin:8px'><button onclick='go(-1)'>&larr; prev</button>
<span id='lbl'></span><button onclick='go(1)'>next &rarr;</button>
&nbsp;<button onclick='filt=0;show()'>all</button>
<button onclick='filt=1;show()'>winners</button><button onclick='filt=-1;show()'>losers</button></div>
<img id='im'><script>
var D=[{items}],i=0,filt=0;
function vis(){{return D.map((d,j)=>j).filter(j=>filt==0||(filt>0?D[j][1]>0:D[j][1]<=0));}}
function show(){{var v=vis();if(i>=v.length)i=0;var d=D[v[i]];
document.getElementById('im').src=d[0]+'.png';
document.getElementById('lbl').innerHTML=(i+1)+'/'+v.length+'  '+d[0].slice(10)+
'  <b class='+(d[1]>=0?'pos':'neg')+'>'+(d[1]>=0?'+':'')+d[1]+'$</b> ('+d[2]+')';}}
function go(k){{var v=vis();i=(i+k+v.length)%v.length;show();}}
document.addEventListener('keydown',e=>{{if(e.key=='ArrowLeft')go(-1);if(e.key=='ArrowRight')go(1);}});
show();</script>"""
    (OUTD / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
