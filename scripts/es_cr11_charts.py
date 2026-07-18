"""The 11 ES-CR touch trades — charts + proper $ breakdown + GEX regime (S73).
Corrected logic: open below CR, virgin first touch (High>=CR), fill AT CR,
stop CR+8 / target CR-10. ES = $50/pt. Shows entry/exit on 5m candles, the
per-trade $ math (gross/friction/net) and prior-EOD Net GEX (regime)."""
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STOP, TGT, FRIC, PT = 8.0, 10.0, 1.25, 50
C = {"up": "#1baf7a", "dn": "#e34948", "cr": "#eb6834", "stop": "#e34948",
     "tgt": "#1baf7a", "ink": "#e8ebf0", "mut": "#7d8697", "grid": "#232833", "surf": "#12151c"}


def main():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"][["date", "cr", "hvl"]].dropna(subset=["cr"]); lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"]); b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    gi = pd.read_csv(ROOT / "data" / "menthorq" / "gex_insights_ES1.csv").sort_values("date")
    gi["date"] = gi.date.astype(str)
    lm = {r.date: r.cr for r in lv.itertuples()}

    trades = []
    for d in sorted(set(b.date)):
        if d not in lm:
            continue
        day = b[b.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        lvl = lm[d]; H, L, Cl, O, hm = day.High.values, day.Low.values, day.Close.values, day.Open.values, day.hm.values
        if O[0] >= lvl:
            continue
        ti = None
        for i in range(1, len(day)):
            if H[i] >= lvl and np.max(H[:i]) < lvl:
                ti = i; break
        if ti is None:
            continue
        sp, tp = lvl + STOP, lvl - TGT
        reason, xi, exit_px = "close", len(day) - 1, Cl[-1]
        for j in range(ti + 1, len(day)):
            if H[j] >= sp:
                reason, xi, exit_px = "stop", j, sp; break
            if L[j] <= tp:
                reason, xi, exit_px = "target", j, tp; break
        gross = lvl - exit_px
        prior = gi[gi.date < d]
        gex = prior.iloc[-1].gex if len(prior) else np.nan
        trades.append(dict(date=d, day=day, cr=lvl, ti=ti, xi=xi, reason=reason,
                           exit_px=exit_px, gross_pts=gross, gross_usd=gross * PT,
                           fric_usd=FRIC * PT, net_usd=(gross - FRIC) * PT,
                           entry_hm=hm[ti], exit_hm=hm[xi], gex=gex))

    def svg(t, W=720, Hh=300):
        day = t["day"]; O, Hi, Lo, Cl = day.Open.values, day.High.values, day.Low.values, day.Close.values
        n = len(day); sp, tp = t["cr"] + STOP, t["cr"] - TGT
        ymin, ymax = min(Lo.min(), tp) - 2, max(Hi.max(), sp) + 2
        ml, mr, mt, mb = 8, 56, 8, 18
        X = lambda i: ml + i / max(n - 1, 1) * (W - ml - mr)
        Y = lambda p: mt + (ymax - p) / (ymax - ymin) * (Hh - mt - mb)
        cw = max(2.0, (W - ml - mr) / n * 0.6)
        s = [f'<svg viewBox="0 0 {W} {Hh}" width="100%">']
        for k in range(5):
            p = ymin + (ymax - ymin) * k / 4
            s.append(f'<line x1="{ml}" y1="{Y(p):.0f}" x2="{W-mr}" y2="{Y(p):.0f}" stroke="{C["grid"]}"/>')
            s.append(f'<text x="{W-mr+3}" y="{Y(p)+4:.0f}" fill="{C["mut"]}" font-size="10">{p:.0f}</text>')
        for i in range(n):
            col = C["up"] if Cl[i] >= O[i] else C["dn"]; x = X(i)
            s.append(f'<line x1="{x:.1f}" y1="{Y(Hi[i]):.1f}" x2="{x:.1f}" y2="{Y(Lo[i]):.1f}" stroke="{col}"/>')
            yo, yc = Y(O[i]), Y(Cl[i])
            s.append(f'<rect x="{x-cw/2:.1f}" y="{min(yo,yc):.1f}" width="{cw:.1f}" height="{max(abs(yc-yo),1):.1f}" fill="{col}"/>')
        for lvl2, col, lab in [(t["cr"], C["cr"], "CR (short)"), (sp, C["stop"], "stop"), (tp, C["tgt"], "target")]:
            dash = '' if 'CR' in lab else 'stroke-dasharray="4 3"'
            s.append(f'<line x1="{ml}" y1="{Y(lvl2):.1f}" x2="{W-mr}" y2="{Y(lvl2):.1f}" stroke="{col}" stroke-width="1.4" {dash} opacity=".9"/>')
            s.append(f'<text x="{ml+2}" y="{Y(lvl2)-3:.1f}" fill="{col}" font-size="10" font-weight="700">{lab} {lvl2:.0f}</text>')
        ex, ey = X(t["ti"]), Y(t["cr"])
        s.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="none" stroke="{C["ink"]}" stroke-width="2"/>')
        s.append(f'<text x="{ex:.1f}" y="{ey-9:.1f}" fill="{C["ink"]}" font-size="9" text-anchor="middle">SHORT {t["cr"]:.0f}</text>')
        xc = C["tgt"] if t["reason"] == "target" else C["stop"] if t["reason"] == "stop" else C["mut"]
        s.append(f'<circle cx="{X(t["xi"]):.1f}" cy="{Y(t["exit_px"]):.1f}" r="5" fill="{xc}"/>')
        s.append(f'<text x="{X(t["xi"]):.1f}" y="{Y(t["exit_px"])+16:.1f}" fill="{xc}" font-size="9" text-anchor="middle">{t["reason"]} {t["exit_px"]:.0f}</text>')
        s.append('</svg>'); return "".join(s)

    net = sum(t["net_usd"] for t in trades)
    wins = [t for t in trades if t["net_usd"] > 0]
    gwin = sum(t["net_usd"] for t in wins); gloss = -sum(t["net_usd"] for t in trades if t["net_usd"] < 0)
    pf = gwin / gloss if gloss else float("inf")
    neg = sum(1 for t in trades if t["gex"] < 0)
    cards = ""
    for i, t in enumerate(trades, 1):
        pc = C["up"] if t["net_usd"] >= 0 else C["dn"]
        reg = "NEG γ" if t["gex"] < 0 else "POS γ"
        regc = C["dn"] if t["gex"] < 0 else C["up"]
        cards += f"""<div class="card"><div class="chd">
          <div><b>#{i} · {t['date']}</b> <span class="reg" style="background:{regc}22;color:{regc}">{reg} ({t['gex']/1e6:+.0f}M)</span></div>
          <div class="pnl" style="color:{pc}">{'+' if t['net_usd']>=0 else '−'}${abs(t['net_usd']):,.0f}</div></div>
          <div class="brk">SHORT 1 ES @ CR {t['cr']:.0f} ({t['entry_hm']}) → {t['reason']} @ {t['exit_px']:.0f} ({t['exit_hm']})
          · gross {t['gross_pts']:+.2f}pt × $50 = {'+' if t['gross_usd']>=0 else '−'}${abs(t['gross_usd']):,.0f}
          − $62 fees = <b style="color:{pc}">{'+' if t['net_usd']>=0 else '−'}${abs(t['net_usd']):,.0f} net</b></div>
          {svg(t)}</div>"""
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>ES CR — 11 trades</title><style>
body{{background:#0b0d12;color:{C['ink']};font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;padding:22px}}
.wrap{{max-width:820px;margin:0 auto}} h1{{font-size:21px;margin:0}}
.sum{{background:#12151c;border:1px solid #232833;border-radius:12px;padding:16px 20px;margin:12px 0}}
.sum b{{color:#5b9bff}} .mut{{color:{C['mut']}}}
.card{{background:{C['surf']};border:1px solid #232833;border-radius:12px;padding:14px 16px;margin:14px 0}}
.chd{{display:flex;justify-content:space-between;align-items:baseline}} .pnl{{font-size:19px;font-weight:800}}
.reg{{font-size:10px;padding:2px 8px;border-radius:6px;font-weight:700;margin-left:6px}}
.brk{{color:{C['mut']};font-size:12.5px;margin:5px 0 8px}} .brk b{{font-size:13px}}
svg{{width:100%;height:auto;display:block}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}} th,td{{padding:5px 9px;text-align:right;border-bottom:1px solid #232833}} th{{color:{C['mut']}}} td:first-child{{text-align:left}}
</style></head><body><div class="wrap">
<h1>ES · Call-Resistance touch-fade · the 11 trades, $ breakdown + regime</h1>
<div class="mut">Corrected logic: open below CR · virgin first touch (High≥CR) · SHORT 1 ES at CR · stop CR+8 / target CR−10 · $50/pt · $62 RT fees</div>
<div class="sum">
{len(trades)} trades · {len(wins)} win / {len(trades)-len(wins)} loss ({len(wins)/len(trades)*100:.0f}%)
· PF <b>{pf:.2f}</b> · net <b style="color:{C['up'] if net>=0 else C['dn']}">{'+' if net>=0 else '−'}${abs(net):,.0f}</b>
· neg-gamma days: <b>{neg}/{len(trades)}</b> · avg net/trade ${net/len(trades):+,.0f}
<br><span class="mut">honest caveat: n=11, one year, up-trending sample — real trades but NOT a validated edge.</span></div>
{cards}</div></body></html>"""
    out = ROOT / "data" / "options_sim" / "es_cr11.html"
    out.write_text(html, encoding="utf-8")
    print(f"{len(trades)} trades, net ${net:+,.0f}, PF {pf:.2f}, neg-gamma {neg}/{len(trades)}")
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
