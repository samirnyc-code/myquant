"""Render the CR-fade setups as 5M RTH candlestick cards + test the breakout (BO)
mirror hypothesis (S73, user request).

FADE (edge): neg prior-EOD GEX, first CR touch before 10:30 CT -> SHORT,
             stop CR+5, target CR-10.  (from mr_es_cr_fade.py)
BO (test)  : pos prior-EOD GEX, first CR touch before 10:30 CT -> LONG,
             stop CR-5, target CR+10.  (the mirror: pos-GEX mornings broke)

Output: data/options_sim/cr_setups.html — one scrollable page, self-contained SVG.
Also prints BO expectancy stats.
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STOP, TGT, FRIC = 5.0, 10.0, 1.25
CUTOFF = "10:30"
# palette (dark surface): candles up/down, levels CR/PS/HVL, entry
C = {"up": "#1baf7a", "dn": "#e34948", "cr": "#eb6834", "ps": "#1baf7a",
     "hvl": "#3987e5", "entry": "#e6e9ef", "stop": "#e34948", "tgt": "#1baf7a",
     "ink": "#e6e9ef", "mut": "#8a91a0", "grid": "#232a34", "surf": "#12151c"}


def load():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"].copy(); lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"]); b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    gi = pd.read_csv(ROOT / "data" / "menthorq" / "gex_insights_ES1.csv").sort_values("date")
    gi["date"] = gi.date.astype(str)
    return lv, b, gi


def prior_gex(d, gi):
    p = gi[gi.date < d]
    return p.iloc[-1].gex if len(p) else None


def find_trade(day, cr, direction):
    """'short' = fade the first CR touch (neg-GEX).
    'bopb' = breakout-pullback long (pos-GEX): price first CLOSES above CR+1
    (breakout), THEN pulls back to retest CR (low within 2pt of CR) -> enter long
    at CR, stop CR-STOP (failed retest), target CR+TGT. Entry must be before CUTOFF."""
    npre = int((day.hm <= CUTOFF).sum())
    H, L, Cl = day.High.values, day.Low.values, day.Close.values
    hm = day.hm.values
    is_short = direction == "short"
    if is_short:
        ti = next((i for i in range(npre) if L[i] - 1.0 <= cr <= H[i] + 1.0), None)
        if ti is None:
            return None
        entry_px, stop_px, tgt_px = cr, cr + STOP, cr - TGT
    else:  # breakout-pullback long
        bo = next((i for i in range(npre) if Cl[i] >= cr + 1.0), None)  # breakout bar
        if bo is None:
            return None
        ti = next((j for j in range(bo + 1, len(day)) if hm[j] <= CUTOFF and L[j] <= cr + 1.0), None)
        if ti is None:                # broke out but never pulled back before cutoff
            return None
        entry_px, stop_px, tgt_px = cr, cr - STOP, cr + TGT
    reason, xi = "close", len(day) - 1
    for j in range(ti + 1, len(day)):
        hit_stop = (H[j] >= stop_px) if is_short else (L[j] <= stop_px)
        hit_tgt = (L[j] <= tgt_px) if is_short else (H[j] >= tgt_px)
        if hit_stop and hit_tgt:  # same bar — assume stop first (conservative)
            reason, xi = "stop", j; break
        if hit_stop:
            reason, xi = "stop", j; break
        if hit_tgt:
            reason, xi = "target", j; break
    exit_px = {"stop": stop_px, "target": tgt_px, "close": day.Close.values[xi]}[reason]
    pnl = (entry_px - exit_px) if is_short else (exit_px - entry_px)
    return {"ti": ti, "xi": xi, "reason": reason, "entry_px": entry_px, "exit_px": exit_px,
            "stop_px": stop_px, "tgt_px": tgt_px, "pnl": pnl - FRIC,
            "entry_hm": hm[ti], "exit_hm": hm[xi]}


def svg_candles(day, cr, ps, hvl, tr, W=760, Hh=340):
    """One session as an SVG candlestick chart. Y-SCALE = THE BARS ONLY (plus the
    stop/target which sit near price) — far-away levels are drawn only if they
    fall inside the view, so 5M bar structure stays readable."""
    O, Hi, Lo, Cl = day.Open.values, day.High.values, day.Low.values, day.Close.values
    n = len(day)
    ymin = min(Lo.min(), tr["tgt_px"])
    ymax = max(Hi.max(), tr["stop_px"])
    pad = (ymax - ymin) * 0.05 or 1
    ymin, ymax = ymin - pad, ymax + pad
    ml, mr, mt, mb = 8, 54, 8, 20
    def X(i): return ml + i / max(n - 1, 1) * (W - ml - mr)
    def Y(p): return mt + (ymax - p) / (ymax - ymin) * (Hh - mt - mb)
    cw = max(2.0, (W - ml - mr) / n * 0.62)
    s = [f'<svg viewBox="0 0 {W} {Hh}" width="100%" style="display:block">']
    # gridlines + price axis (5 ticks)
    for k in range(5):
        p = ymin + (ymax - ymin) * k / 4
        y = Y(p)
        s.append(f'<line x1="{ml}" y1="{y:.0f}" x2="{W-mr}" y2="{y:.0f}" stroke="{C["grid"]}" stroke-width="1"/>')
        s.append(f'<text x="{W-mr+4}" y="{y+4:.0f}" fill="{C["mut"]}" font-size="10">{p:.0f}</text>')
    # candles
    for i in range(n):
        col = C["up"] if Cl[i] >= O[i] else C["dn"]
        x = X(i)
        s.append(f'<line x1="{x:.1f}" y1="{Y(Hi[i]):.1f}" x2="{x:.1f}" y2="{Y(Lo[i]):.1f}" stroke="{col}" stroke-width="1"/>')
        yo, yc = Y(O[i]), Y(Cl[i])
        s.append(f'<rect x="{x-cw/2:.1f}" y="{min(yo,yc):.1f}" width="{cw:.1f}" '
                 f'height="{max(abs(yc-yo),1):.1f}" fill="{col}"/>')
    # levels — only those INSIDE the visible range (CR always is; PS almost never)
    for lvl, col, lab in [(cr, C["cr"], "CR"), (ps, C["ps"], "PS"), (hvl, C["hvl"], "HVL")]:
        if np.isfinite(lvl) and ymin <= lvl <= ymax:
            y = Y(lvl)
            s.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" stroke="{col}" stroke-width="1.4" opacity="0.9"/>')
            s.append(f'<text x="{ml+2}" y="{y-3:.1f}" fill="{col}" font-size="10" font-weight="700">{lab} {lvl:.0f}</text>')
    # stop / target dashed
    for lvl, col, lab in [(tr["stop_px"], C["stop"], "STOP"), (tr["tgt_px"], C["tgt"], "TGT")]:
        y = Y(lvl)
        s.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{W-mr}" y2="{y:.1f}" stroke="{col}" stroke-width="1" stroke-dasharray="4 3" opacity="0.7"/>')
        s.append(f'<text x="{W-mr-2}" y="{y-3:.1f}" fill="{col}" font-size="9" text-anchor="end">{lab}</text>')
    # entry & exit markers
    ex, ey = X(tr["ti"]), Y(tr["entry_px"])
    s.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="none" stroke="{C["entry"]}" stroke-width="2"/>')
    s.append(f'<text x="{ex:.1f}" y="{ey-8:.1f}" fill="{C["entry"]}" font-size="9" text-anchor="middle">entry</text>')
    xx = X(tr["xi"])
    xcol = C["tgt"] if tr["reason"] == "target" else (C["stop"] if tr["reason"] == "stop" else C["mut"])
    s.append(f'<circle cx="{xx:.1f}" cy="{Y(tr["exit_px"]):.1f}" r="4.5" fill="{xcol}"/>')
    s.append('</svg>')
    return "".join(s)


def render():
    lv, bars, gi = load()
    levels = {r.date: r for r in lv.itertuples()}
    days = [d for d in sorted(set(bars.date)) if d in levels]
    fade_trades, bo_trades = [], []
    for d in days:
        day = bars[bars.date == d].reset_index(drop=True)
        if len(day) < 10 or not np.isfinite(levels[d].cr):
            continue
        cr, ps, hvl = levels[d].cr, levels[d].ps, levels[d].hvl
        g = prior_gex(d, gi)
        if g is None:
            continue
        if g < 0:
            tr = find_trade(day, cr, "short")
            if tr:
                fade_trades.append((d, day, cr, ps, hvl, g, tr))
        elif g > 0:
            tr = find_trade(day, cr, "long")
            if tr:
                bo_trades.append((d, day, cr, ps, hvl, g, tr))
    return fade_trades, bo_trades


def stats(trades):
    p = np.array([t[6]["pnl"] for t in trades])
    if not len(p):
        return {}
    return {"n": len(p), "win_pct": round((p > 0).mean() * 100, 1),
            "E_usd": round(p.mean() * 50), "total_usd": round(p.sum() * 50),
            "tgt": sum(1 for t in trades if t[6]["reason"] == "target"),
            "stp": sum(1 for t in trades if t[6]["reason"] == "stop"),
            "cls": sum(1 for t in trades if t[6]["reason"] == "close")}


def card(d, day, cr, ps, hvl, g, tr, kind):
    pnl_usd = tr["pnl"] * 50
    pc = C["up"] if pnl_usd >= 0 else C["dn"]
    rc = {"target": C["tgt"], "stop": C["stop"], "close": C["mut"]}[tr["reason"]]
    dow = dt.datetime.strptime(d, "%Y-%m-%d").strftime("%a")
    return f"""<div class="card">
      <div class="chd"><div><b>{d}</b> <span class="mut">{dow}</span>
        <span class="tag">{kind}</span></div>
        <div class="pnl" style="color:{pc}">{'+' if pnl_usd>=0 else ''}${pnl_usd:,.0f}</div></div>
      <div class="meta">prior GEX <b>{g/1e6:+.0f}M</b> · entry {tr['entry_hm']} CT @ CR {cr:.0f} ·
        exit {tr['exit_hm']} <span style="color:{rc}">[{tr['reason'].upper()}]</span> @ {tr['exit_px']:.0f} ·
        {'SHORT' if kind=='FADE' else 'LONG'} · stop {tr['stop_px']:.0f} / tgt {tr['tgt_px']:.0f}</div>
      <div class="chart" onclick="zoom(this)">{svg_candles(day, cr, ps, hvl, tr)}</div>
    </div>"""


def main():
    fade, bo = render()
    fs, bs = stats(fade), stats(bo)
    print("FADE (neg-GEX morning, short CR):", fs)
    print("BO   (pos-GEX morning, long CR): ", bs)
    # distribution + drawdown of the fade trades
    pnls = np.array([t[6]["pnl"] * 50 for t in fade])
    dates = [t[0] for t in fade]
    eq = np.cumsum(pnls)
    dd = eq - np.maximum.accumulate(eq)
    months = pd.Series([d[:7] for d in dates]).value_counts().sort_index()
    streak, worst_streak = 0, 0
    for p in pnls:
        streak = streak + 1 if p < 0 else 0
        worst_streak = max(worst_streak, streak)
    print(f"\nFADE distribution: {len(dates)} trades over {dates[0]} .. {dates[-1]}")
    print("per month:", dict(months))
    print(f"maxDD ${dd.min():,.0f}  worst losing streak {worst_streak}  "
          f"largest loss ${pnls.min():,.0f}  largest win ${pnls.max():,.0f}")
    global DIST_HTML
    DIST_HTML = (f"<div class='sum'><b>Distribution & risk</b> — {len(dates)} trades "
                 f"{dates[0]} → {dates[-1]} · per month: "
                 + " · ".join(f"{k[5:]}:{v}" for k, v in months.items())
                 + f"<br>equity maxDD <b style='color:{C['dn']}'>${dd.min():,.0f}</b> · "
                 f"worst losing streak {worst_streak} · "
                 f"largest loss ${pnls.min():,.0f} · largest win ${pnls.max():,.0f}</div>")
    (SIM := ROOT / "data" / "options_sim").mkdir(exist_ok=True)
    (SIM / "cr_setups_stats.json").write_text(json.dumps({"fade": fs, "bo": bs}, indent=1))

    fade_cards = "".join(card(*t, "FADE") for t in fade)
    bo_cards = "".join(card(*t, "BREAKOUT") for t in bo)
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>CR Setups — ES 5M</title><style>
body{{background:#0d0f14;color:{C['ink']};font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:20px}}
.wrap{{max-width:840px;margin:0 auto}} h1{{font-size:22px;margin:0 0 2px}}
h2{{font-size:16px;color:#8ab4f8;margin:26px 0 6px}}
.mut{{color:{C['mut']}}} .sum{{background:#161a22;border:1px solid #23262d;border-radius:12px;padding:14px 18px;margin:12px 0;font-size:14px}}
.card{{background:{C['surf']};border:1px solid #23262d;border-radius:12px;padding:14px 16px;margin:14px 0}}
.chd{{display:flex;justify-content:space-between;align-items:baseline}} .pnl{{font-size:20px;font-weight:800}}
.tag{{background:#23262d;border-radius:6px;padding:1px 7px;font-size:10px;letter-spacing:.1em;margin-left:6px;color:{C['mut']}}}
.meta{{color:{C['mut']};font-size:12px;margin:4px 0 8px}}
.legend{{font-size:12px;color:{C['mut']};margin:6px 0}}
.legend b{{color:{C['ink']}}} .sw{{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 3px 0 10px;vertical-align:middle}}
</style></head><body><div class="wrap">
<h1>Call-Resistance setups — ES 5-minute RTH</h1>
<div class="mut">Each card = one session. Circle = entry at CR touch (before 10:30 CT);
filled dot = exit (green target / red stop / grey close). Dashed = stop &amp; target.</div>
<div class="legend"><span class="sw" style="background:{C['cr']}"></span>Call Resistance
<span class="sw" style="background:{C['ps']}"></span>Put Support
<span class="sw" style="background:{C['hvl']}"></span>HVL
<span class="sw" style="background:{C['up']}"></span>up bar
<span class="sw" style="background:{C['dn']}"></span>down bar</div>

<div class="sum"><b>FADE edge</b> — negative prior-EOD GEX, short the first CR touch:
n {fs.get('n')}, win {fs.get('win_pct')}%, E <b style="color:{C['up']}">${fs.get('E_usd')}</b>/trade,
total ${fs.get('total_usd'):,} · target {fs.get('tgt')} / stop {fs.get('stp')} / close {fs.get('cls')}</div>
<div class="sum"><b>BREAKOUT test</b> — positive prior-EOD GEX, long the first CR touch (the mirror):
n {bs.get('n')}, win {bs.get('win_pct')}%, E <b style="color:{C['up'] if bs.get('E_usd',0)>0 else C['dn']}">${bs.get('E_usd')}</b>/trade,
total ${bs.get('total_usd'):,} · target {bs.get('tgt')} / stop {bs.get('stp')} / close {bs.get('cls')}</div>

{DIST_HTML}
<h2>FADE setups — {fs.get('n')} trades (negative-GEX mornings)</h2>
{fade_cards}
<h2>BREAKOUT setups — {bs.get('n')} trades (positive-GEX mornings) — ⚠ selection logic
crude, numbers retracted; rebuild with user</h2>
{bo_cards}
</div>
<div id="ovl" onclick="this.classList.remove('on')"><div id="ovlbox"></div></div>
<style>
.chart{{cursor:zoom-in}}
#ovl{{position:fixed;inset:0;background:rgba(4,6,10,.85);display:none;align-items:center;
justify-content:center;z-index:9;cursor:zoom-out}}
#ovl.on{{display:flex}}
#ovlbox{{width:min(1500px,97vw);background:{C['surf']};border:1px solid #2a3040;
border-radius:14px;padding:18px;animation:zi .18s ease-out}}
#ovlbox svg{{width:100%;height:auto}}
@keyframes zi{{from{{transform:scale(.55);opacity:.3}}to{{transform:scale(1);opacity:1}}}}
</style>
<script>
function zoom(el){{
  const box = document.getElementById('ovlbox');
  box.innerHTML = el.closest('.card').outerHTML;
  const c = box.querySelector('.chart'); if(c) c.onclick = null;
  document.getElementById('ovl').classList.add('on');
}}
document.addEventListener('keydown', e => {{ if(e.key === 'Escape')
  document.getElementById('ovl').classList.remove('on'); }});
</script>
</body></html>"""
    out = ROOT / "data" / "options_sim" / "cr_setups.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nwrote {out}")
    return out


if __name__ == "__main__":
    main()
