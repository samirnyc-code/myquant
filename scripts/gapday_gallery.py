"""GAP-DAY CHART GALLERY — every skipped gap day, cyclable with arrow keys.

Per chart: 5m RTH candles · regime shading (green BULL / red BEAR / grey NEUTRAL)
· EMA20 seeded from the PRIOR day's closes · prior RTH close line · gap stats box
(gap % and pts, direction, ADR10, gap/ADR, prior-day range, DOW) · our 1E (faint)
and 2E (bold) trigger marks · RevFT (R) and MC (C) signal marks.

Output: docs/living/gapday_gallery/<date>.png + index.html (arrow keys / buttons).
  python scripts/gapday_gallery.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402
from gapday_alt_signals import parse_signals, SIG_REV, SIG_MC, GAP_Q3  # noqa: E402

OUTD = WT_ROOT / "docs" / "living" / "gapday_gallery"
SHADE = {"neutral": ("#9aa0a6", 0.12), "bull": ("#1f7a3d", 0.10), "bear": ("#b23a2e", 0.10)}
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    OUTD.mkdir(parents=True, exist_ok=True)
    b = pd.read_parquet(DATA / "data" / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"),
                                dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["rng"] = dly.dH - dly.dL
    dly["adr10"] = dly.rng.rolling(10).mean().shift(1)
    dly["gap_pct"] = (dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100
    dly["gap_pts"] = dly.dO - dly.dC.shift(1)
    dly["prev_rng"] = dly.rng.shift(1)
    dly["prevC"] = dly.dC.shift(1)
    dmap = dly.set_index("Date")
    gap_days = sorted(dly[dly.gap_pct.abs() > GAP_Q3].Date)
    if limit:
        gap_days = gap_days[:limit]
    all_days = sorted(b.Date.unique())
    prior = {d_: all_days[i - 1] for i, d_ in enumerate(all_days) if i > 0}

    rev = parse_signals(SIG_REV); mc = parse_signals(SIG_MC)
    rev_by = {d_: g_ for d_, g_ in rev.groupby("Date")}
    mc_by = {d_: g_ for d_, g_ in mc.groupby("Date")}

    done = []; t0 = time.time()
    for di, dstr in enumerate(gap_days):
        g, tP, tbar = load_day(b, dstr)
        if g is None or dstr not in prior:
            continue
        row = dmap.loc[dstr]
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        trace = {}
        try:
            phase_transitions(H, L, n, tP, tbar, trace=trace)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        # EMA20 seeded from prior day
        gp = b[b.Date == prior[dstr]].sort_values("DateTime")
        closes = np.concatenate([gp.Close.values, C])
        a20 = 2.0 / 21.0
        ema = np.empty(len(closes)); ema[0] = closes[0]
        for i in range(1, len(closes)):
            ema[i] = a20 * closes[i] + (1 - a20) * ema[i - 1]
        ema_today = ema[len(gp):]

        vhi = max(H.max(), row.prevC); vlo = min(L.min(), row.prevC)
        rng = vhi - vlo; off = rng * 0.02
        fig, ax = plt.subplots(figsize=(19, 8), dpi=100)
        bounds = sorted([(s_, "start", sd) for (s_, sd, _) in trace["starts"]] +
                        [(b_, "term", None) for (_, _, b_, _) in trace["terms"]])
        cur = "neutral"; x0 = 0; segs = []
        for (xb, ktp, sd) in bounds:
            segs.append((x0, xb, cur)); x0 = xb
            cur = sd if ktp == "start" else "neutral"
        segs.append((x0, n - 1, cur))
        for (a2, b2, sdv) in segs:
            col, al = SHADE[sdv]
            ax.axvspan(a2 + 0.5 if a2 else -0.9, b2 + 0.5, color=col, alpha=al, zorder=0)
        for k in range(n):
            up_ = C[k] >= O[k]
            col = "#2e9e8f" if up_ else "#e0574a"
            ax.plot([k, k], [L[k], H[k]], color=col, lw=1.3, zorder=2)
            ax.add_patch(plt.Rectangle((k - 0.3, min(O[k], C[k])), 0.6,
                                       max(abs(C[k] - O[k]), rng * 0.001),
                                       facecolor=col, edgecolor="black", lw=0.35, zorder=3))
        ax.plot(range(n), ema_today, lw=1.8, color="#4a3aa7", label="EMA20 (prior-day seeded)")
        ax.axhline(row.prevC, ls="--", lw=1.3, color="#33454d")
        ax.text(n - 1, row.prevC, " prior close", va="center", fontsize=9, color="#33454d")
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt > 2:
                continue
            short = dr == "S"
            col = "#b23a2e" if short else "#1f7a3d"
            ax.plot(fb, trig, "v" if short else "^", ms=11 if cnt == 2 else 6,
                    color=col, mec="black", mew=0.8, alpha=1.0 if cnt == 2 else 0.4, zorder=6)
            if cnt == 2:
                ax.text(fb, trig + (off * 1.6 if short else -off * 1.6), "2E" + dr,
                        ha="center", fontsize=8.5, color=col, fontweight="bold")
        g_dt = pd.to_datetime(g["DateTime"]).reset_index(drop=True)
        for src, sigs, mark, colr in (("R", rev_by.get(dstr), "R", "#eb6834"),
                                      ("C", mc_by.get(dstr), "C", "#0e7c86")):
            if sigs is None:
                continue
            for t_ in sigs.itertuples():
                idx = int(np.searchsorted(g_dt.values, np.datetime64(t_.DateTime))) - 1
                if idx < 0 or idx >= n:
                    continue
                short = t_.Direction.lower().startswith("s")
                y = H[idx] + off * 2.6 if short else L[idx] - off * 2.6
                ax.text(idx, y, mark + ("↓" if short else "↑"), ha="center", fontsize=9,
                        color=colr, fontweight="bold")
        gd = "UP" if row.gap_pts > 0 else "DOWN"
        stats = (f"GAP {gd} {row.gap_pct:+.2f}%  ({row.gap_pts:+.2f} pts)\n"
                 f"ADR10 {row.adr10:.1f} pts   gap/ADR {abs(row.gap_pts)/row.adr10:.2f}\n"
                 f"prior-day range {row.prev_rng:.1f} pts\n"
                 f"{DOW[pd.Timestamp(dstr).dayofweek]}")
        ax.text(0.995, 0.02, stats, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=10.5, family="monospace",
                bbox=dict(boxstyle="round,pad=0.45", fc="white", ec="#33454d", lw=1.2))
        ax.set_title(f"{dstr}  ·  GAP {gd} {row.gap_pct:+.2f}%  ·  regime shading + EMA20 + "
                     f"1E/2E triggers + RevFT(R)/MC(C) signals", fontsize=13, fontweight="bold")
        ax.set_xlim(-1, n); ax.set_ylim(vlo - rng * 0.10, vhi + rng * 0.10)
        ax.legend(loc="upper left", fontsize=9, frameon=False)
        ax.grid(axis="y", color="#eceeed", lw=0.6); ax.set_axisbelow(True)
        for s_ in ("top", "right", "bottom"): ax.spines[s_].set_visible(False)
        ax.tick_params(axis="x", bottom=False, labelbottom=False)
        fig.tight_layout()
        fig.savefig(OUTD / f"{dstr}.png", facecolor="white")
        plt.close(fig)
        done.append((dstr, float(row.gap_pct)))
        del tP, tbar; gc.collect()
        if (di + 1) % 40 == 0:
            print(f"[{di+1}/{len(gap_days)}] ({time.time()-t0:.0f}s)", flush=True)

    items = ",".join(f"['{d_}',{gp:+.2f}]" for d_, gp in done)
    html = f"""<!doctype html><meta charset='utf-8'><title>Gap-day gallery</title>
<style>body{{font-family:Segoe UI,Arial;margin:10px;background:#14181d;color:#eee;text-align:center}}
img{{max-width:99%;border:1px solid #444;background:#fff}}
.bar{{margin:8px;font-size:15px}} button{{font-size:15px;padding:4px 14px;margin:0 6px}}</style>
<div class='bar'><button onclick='go(-1)'>&larr; prev</button>
<span id='lbl'></span>
<button onclick='go(1)'>next &rarr;</button>
&nbsp; <input id='jump' size='10' placeholder='YYYY-MM-DD'>
<button onclick='jmp()'>go</button></div>
<img id='im' src=''>
<script>
var D=[{items}],i=0;
function show(){{var d=D[i];document.getElementById('im').src=d[0]+'.png';
document.getElementById('lbl').textContent=(i+1)+' / '+D.length+'  '+d[0]+'  gap '+d[1]+'%';}}
function go(k){{i=(i+k+D.length)%D.length;show();}}
function jmp(){{var v=document.getElementById('jump').value;
for(var j=0;j<D.length;j++)if(D[j][0]==v){{i=j;break;}}show();}}
document.addEventListener('keydown',function(e){{
if(e.key=='ArrowLeft')go(-1);if(e.key=='ArrowRight')go(1);}});
show();
</script>"""
    (OUTD / "index.html").write_text(html, encoding="utf-8")
    print(f"\nDONE {time.time()-t0:.0f}s  charts={len(done)} -> {OUTD/'index.html'}")


if __name__ == "__main__":
    main()
