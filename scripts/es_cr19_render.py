"""Render the exact 19 ES-CR fade trades behind PF 29.3 (S73, user verification).

Replicates sim_run.py's ES 'cr' entries EXACTLY (same bars, tolerance, first
from-below touch, stop 8 / target 10, 1.25pt friction) so the charts ARE the
backtest. One scrollable page, click-to-zoom, full per-trade numbers + a table.
Output: data/options_sim/es_cr19.html
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STOP, TGT, FRIC, MULT = 8.0, 10.0, 1.25, 50
C = {"up": "#1baf7a", "dn": "#e34948", "cr": "#eb6834", "stop": "#e34948",
     "tgt": "#1baf7a", "ink": "#e6e9ef", "mut": "#8a91a0", "grid": "#232a34", "surf": "#12151c"}


def load():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"][["date", "cr"]].copy()
    lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    return lv, b


def build():
    lv, b = load()
    lm = {r.date: r.cr for r in lv.itertuples() if np.isfinite(r.cr)}
    trades = []
    for d in sorted(set(b.date)):
        if d not in lm:
            continue
        day = b[b.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        lvl = lm[d]
        tol = max(1.0 * (lvl / 7500), 0.0004 * lvl)
        H, L, Cl = day.High.values, day.Low.values, day.Close.values
        ti = None
        for i in range(1, len(day)):
            k = max(0, i - 3)
            if np.max(Cl[k:i]) < lvl - tol and (L[i] - tol) <= lvl <= (H[i] + tol):
                ti = i
                break
        if ti is None:
            continue
        reason, xi, exit_px = "close", len(day) - 1, Cl[-1]
        for j in range(ti + 1, len(day)):
            if H[j] >= lvl + STOP:
                reason, xi, exit_px = "stop", j, lvl + STOP
                break
            if L[j] <= lvl - TGT:
                reason, xi, exit_px = "target", j, lvl - TGT
                break
        pts = (lvl - exit_px) - FRIC
        trades.append({"date": d, "day": day, "cr": lvl, "ti": ti, "xi": xi,
                       "reason": reason, "exit_px": exit_px, "pts": pts,
                       "pnl": pts * MULT, "entry_hm": day.hm.values[ti],
                       "exit_hm": day.hm.values[xi]})
    return trades


def svg(t, W=760, Hh=320):
    day = t["day"]
    O, Hi, Lo, Cl = day.Open.values, day.High.values, day.Low.values, day.Close.values
    n = len(day)
    stop_px, tgt_px = t["cr"] + STOP, t["cr"] - TGT
    ymin = min(Lo.min(), tgt_px) - 2
    ymax = max(Hi.max(), stop_px) + 2
    ml, mr, mt, mb = 8, 58, 8, 20
    X = lambda i: ml + i / max(n - 1, 1) * (W - ml - mr)
    Y = lambda p: mt + (ymax - p) / (ymax - ymin) * (Hh - mt - mb)
    cw = max(2.0, (W - ml - mr) / n * 0.6)
    s = [f'<svg viewBox="0 0 {W} {Hh}" width="100%" style="display:block">']
    for k in range(5):
        p = ymin + (ymax - ymin) * k / 4
        s.append(f'<line x1="{ml}" y1="{Y(p):.0f}" x2="{W-mr}" y2="{Y(p):.0f}" stroke="{C["grid"]}"/>')
        s.append(f'<text x="{W-mr+3}" y="{Y(p)+4:.0f}" fill="{C["mut"]}" font-size="10">{p:.0f}</text>')
    for i in range(n):
        col = C["up"] if Cl[i] >= O[i] else C["dn"]
        x = X(i)
        s.append(f'<line x1="{x:.1f}" y1="{Y(Hi[i]):.1f}" x2="{x:.1f}" y2="{Y(Lo[i]):.1f}" stroke="{col}"/>')
        yo, yc = Y(O[i]), Y(Cl[i])
        s.append(f'<rect x="{x-cw/2:.1f}" y="{min(yo,yc):.1f}" width="{cw:.1f}" height="{max(abs(yc-yo),1):.1f}" fill="{col}"/>')
    for lvl, col, lab in [(t["cr"], C["cr"], "CR"), (stop_px, C["stop"], "STOP"), (tgt_px, C["tgt"], "TGT")]:
        dash = '' if lab == "CR" else 'stroke-dasharray="4 3"'
        s.append(f'<line x1="{ml}" y1="{Y(lvl):.1f}" x2="{W-mr}" y2="{Y(lvl):.1f}" stroke="{col}" stroke-width="1.4" {dash} opacity="0.9"/>')
        s.append(f'<text x="{ml+2}" y="{Y(lvl)-3:.1f}" fill="{col}" font-size="10" font-weight="700">{lab} {lvl:.0f}</text>')
    ex, ey = X(t["ti"]), Y(t["cr"])
    s.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="none" stroke="{C["ink"]}" stroke-width="2"/>')
    s.append(f'<text x="{ex:.1f}" y="{ey-8:.1f}" fill="{C["ink"]}" font-size="9" text-anchor="middle">SHORT</text>')
    xc = C["tgt"] if t["reason"] == "target" else C["stop"] if t["reason"] == "stop" else C["mut"]
    s.append(f'<circle cx="{X(t["xi"]):.1f}" cy="{Y(t["exit_px"]):.1f}" r="4.5" fill="{xc}"/>')
    s.append('</svg>')
    return "".join(s)


def main():
    tr = build()
    pnls = np.array([t["pnl"] for t in tr])
    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    pf = wins.sum() / -losses.sum() if len(losses) else float("inf")
    eq = np.cumsum(pnls)
    dd = (eq - np.maximum.accumulate(eq)).min()
    cards = ""
    for i, t in enumerate(tr, 1):
        dow = dt.datetime.strptime(t["date"], "%Y-%m-%d").strftime("%a")
        pc = C["up"] if t["pnl"] >= 0 else C["dn"]
        rc = {"target": C["tgt"], "stop": C["stop"], "close": C["mut"]}[t["reason"]]
        cards += f"""<div class="card"><div class="chd">
          <div><b>#{i} · {t['date']}</b> <span class="mut">{dow}</span></div>
          <div class="pnl" style="color:{pc}">{'+' if t['pnl']>=0 else ''}${t['pnl']:,.0f}</div></div>
          <div class="meta">SHORT CR {t['cr']:.0f} @ {t['entry_hm']} CT · exit {t['exit_hm']}
          <span style="color:{rc}">[{t['reason'].upper()}]</span> @ {t['exit_px']:.0f} ·
          {t['pts']:+.2f} pts (net 1.25 fric) · stop {t['cr']+STOP:.0f} / tgt {t['cr']-TGT:.0f}</div>
          <div class="chart" onclick="zoom(this)">{svg(t)}</div></div>"""
    rows = "".join(f"<tr><td>{i}</td><td>{t['date']}</td><td>{t['cr']:.0f}</td>"
                   f"<td>{t['entry_hm']}</td><td>{t['exit_hm']}</td><td>{t['reason']}</td>"
                   f"<td>{t['exit_px']:.0f}</td><td>{t['pts']:+.2f}</td>"
                   f"<td style='color:{C['up'] if t['pnl']>=0 else C['dn']}'>{t['pnl']:+,.0f}</td></tr>"
                   for i, t in enumerate(tr, 1))
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>ES CR — 19 trades</title><style>
body{{background:#0d0f14;color:{C['ink']};font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:20px}}
.wrap{{max-width:840px;margin:0 auto}} h1{{font-size:22px;margin:0}}
.sum{{background:#161a22;border:1px solid #2a3040;border-radius:12px;padding:16px 20px;margin:12px 0;font-size:15px}}
.sum b{{color:#5fa8ff}} .mut{{color:{C['mut']}}}
.card{{background:{C['surf']};border:1px solid #23262d;border-radius:12px;padding:14px 16px;margin:14px 0}}
.chd{{display:flex;justify-content:space-between;align-items:baseline}} .pnl{{font-size:19px;font-weight:800}}
.meta{{color:{C['mut']};font-size:12px;margin:4px 0 8px}} .chart{{cursor:zoom-in}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0}}
th,td{{padding:5px 9px;text-align:right;border-bottom:1px solid #23262d}} th{{color:{C['mut']}}} td:first-child,td:nth-child(2){{text-align:left}}
#ovl{{position:fixed;inset:0;background:rgba(4,6,10,.85);display:none;align-items:center;justify-content:center;z-index:9;cursor:zoom-out}}
#ovl.on{{display:flex}} #ovlbox{{width:min(1500px,97vw);background:{C['surf']};border:1px solid #2a3040;border-radius:14px;padding:18px}}
#ovlbox svg{{width:100%;height:auto}}
</style></head><body><div class="wrap">
<h1>ES · Call-Resistance first-touch fade · the 19 trades behind PF {pf:.1f}</h1>
<div class="mut">stop 8 / target 10 ES pts, $50/pt, 1.25pt friction · repaired continuous bars · same logic as sim_run.py</div>
<div class="sum">
n <b>{len(tr)}</b> · wins <b>{len(wins)}</b> · losses <b>{len(losses)}</b> · win% <b>{len(wins)/len(tr)*100:.1f}</b>
· PF <b>{pf:.1f}</b> · expectancy <b>${pnls.mean():+,.0f}</b>/trade · total <b>${pnls.sum():+,.0f}</b>
· maxDD <b>${dd:+,.0f}</b> · avg win <b>${wins.mean():+,.0f}</b> · avg loss <b>${losses.mean() if len(losses) else 0:+,.0f}</b>
· best <b>${pnls.max():+,.0f}</b> · worst <b>${pnls.min():+,.0f}</b></div>
<table><tr><th>#</th><th>date</th><th>CR</th><th>entry</th><th>exit</th><th>result</th><th>exit px</th><th>pts</th><th>$P&L</th></tr>{rows}</table>
<div class="mut">click any chart to enlarge · circle = short entry at CR · filled dot = exit (green target / red stop / grey close)</div>
{cards}</div>
<div id="ovl" onclick="this.classList.remove('on')"><div id="ovlbox"></div></div>
<script>
function zoom(el){{const bx=document.getElementById('ovlbox');bx.innerHTML=el.closest('.card').outerHTML;
const c=bx.querySelector('.chart');if(c)c.onclick=null;document.getElementById('ovl').classList.add('on');}}
document.addEventListener('keydown',e=>{{if(e.key=='Escape')document.getElementById('ovl').classList.remove('on');}});
</script></body></html>"""
    out = ROOT / "data" / "options_sim" / "es_cr19.html"
    out.write_text(html, encoding="utf-8")
    print(f"n={len(tr)} wins={len(wins)} losses={len(losses)} PF={pf:.2f} "
          f"total=${pnls.sum():+,.0f} maxDD=${dd:+,.0f}")
    print(f"losers: {[(t['date'], round(t['pnl'])) for t in tr if t['pnl'] < 0]}")
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
