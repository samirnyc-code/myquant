"""Render the S75Q findings as a self-contained HTML report for Mission Control.

Reads data/options_sim/s75q_levels.json (written by gex_levels_brooks.py) plus
the hard-coded part-1 regime numbers, and writes docs/gexlab/s75q.html.

Self-contained: no external CSS/JS/fonts, light+dark, one palette validated with
the dataviz validator (light #3564d4/#c2410c, dark #5c8ce8/#d1713a).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "options_sim" / "s75q_levels.json"
OUT = ROOT / "docs" / "gexlab" / "s75q.html"

CSS = """
:root{--bg:#fcfcfb;--card:#fff;--ink:#1a1a19;--ink2:#4a4a47;--muted:#77776f;
 --line:#e4e4de;--s1:#3564d4;--s2:#c2410c;--ok:#1a7f4b;--warn:#b45309;--bad:#b42318}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--card:#232322;--ink:#f2f2ee;
 --ink2:#c8c8c0;--muted:#95958c;--line:#35352f;--s1:#5c8ce8;--s2:#d1713a;
 --ok:#4ade80;--warn:#fbbf24;--bad:#f87171}}
:root[data-theme=dark]{--bg:#1a1a19;--card:#232322;--ink:#f2f2ee;--ink2:#c8c8c0;
 --muted:#95958c;--line:#35352f;--s1:#5c8ce8;--s2:#d1713a;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171}
:root[data-theme=light]{--bg:#fcfcfb;--card:#fff;--ink:#1a1a19;--ink2:#4a4a47;
 --muted:#77776f;--line:#e4e4de;--s1:#3564d4;--s2:#c2410c;--ok:#1a7f4b;--warn:#b45309;--bad:#b42318}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:34px 20px 90px}
h1{font-size:27px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:19px;margin:38px 0 10px;letter-spacing:-.01em}
h3{font-size:15px;margin:22px 0 6px;color:var(--ink2)}
.sub{color:var(--muted);font-size:13.5px;margin-bottom:22px}
.card{background:var(--card);border:1px solid var(--line);border-radius:11px;
 padding:17px 19px;margin:14px 0}
.verdict{border-left:3px solid var(--v,var(--muted))}
.tag{display:inline-block;font-size:11px;font-weight:650;letter-spacing:.04em;
 text-transform:uppercase;padding:2px 8px;border-radius:5px;
 background:color-mix(in srgb,var(--v,var(--muted)) 15%,transparent);color:var(--v,var(--muted))}
.v-null{--v:var(--bad)} .v-weak{--v:var(--warn)} .v-live{--v:var(--ok)}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:9px 0}
th,td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
td.num{font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}
.hero{display:flex;gap:26px;flex-wrap:wrap;margin:16px 0}
.stat{min-width:132px}
.stat b{display:block;font-size:26px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.stat span{color:var(--muted);font-size:12px}
.legend{display:flex;gap:16px;font-size:12.5px;color:var(--ink2);margin:6px 0 2px}
.sw{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:6px;vertical-align:-1px}
.note{color:var(--ink2);font-size:13.5px}
code{background:color-mix(in srgb,var(--muted) 14%,transparent);padding:1px 5px;
 border-radius:4px;font-size:12.5px}
.foot{color:var(--muted);font-size:12.5px;margin-top:34px;border-top:1px solid var(--line);padding-top:14px}
"""

JS = """
document.querySelectorAll('[data-tip]').forEach(function(el){
  el.addEventListener('mouseenter',function(e){
    var t=document.createElement('div');t.id='tt';t.textContent=el.dataset.tip;
    t.style.cssText='position:fixed;z-index:9;background:var(--card);color:var(--ink);'+
      'border:1px solid var(--line);border-radius:7px;padding:6px 9px;font-size:12.5px;'+
      'pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.16)';
    document.body.appendChild(t);
    var r=el.getBoundingClientRect();
    t.style.left=Math.min(r.left,window.innerWidth-t.offsetWidth-12)+'px';
    t.style.top=(r.top-t.offsetHeight-8)+'px';
  });
  el.addEventListener('mouseleave',function(){var t=document.getElementById('tt');if(t)t.remove()});
});
"""


def bars(groups):
    """Grouped bar chart: rejection rate, CR level vs date-shuffled placebo."""
    W, H, PL, PB, PT = 640, 250, 42, 46, 14
    gw = (W - PL - 14) / len(groups)
    plot = H - PB - PT
    s = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="CR rejection rate versus placebo">']
    for y in (0, 25, 50, 75, 100):
        yy = PT + plot * (1 - y / 100)
        s.append(f'<line x1="{PL}" x2="{W-14}" y1="{yy:.1f}" y2="{yy:.1f}" '
                 f'stroke="var(--line)" stroke-width="1"/>')
        s.append(f'<text x="{PL-9}" y="{yy+4:.1f}" text-anchor="end" fill="var(--muted)" '
                 f'font-size="11">{y}%</text>')
    yy = PT + plot * 0.5
    s.append(f'<line x1="{PL}" x2="{W-14}" y1="{yy:.1f}" y2="{yy:.1f}" '
             f'stroke="var(--muted)" stroke-width="1" stroke-dasharray="4 3"/>')
    s.append(f'<text x="{W-16}" y="{yy-6:.1f}" text-anchor="end" fill="var(--muted)" '
             f'font-size="10.5">coin-flip null</text>')
    for i, (lab, lvl, pla, n) in enumerate(groups):
        x0 = PL + i * gw
        bw = min(46, gw / 2 - 9)
        for j, (val, col, nm) in enumerate(((lvl, "var(--s1)", "CR level"),
                                            (pla, "var(--s2)", "placebo"))):
            h = plot * val
            x = x0 + gw / 2 - bw - 2 + j * (bw + 4)
            y = PT + plot - h
            s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                     f'rx="4" fill="{col}" data-tip="{nm} — {lab}: {val*100:.1f}% (n={n})"/>')
            s.append(f'<text x="{x+bw/2:.1f}" y="{y-6:.1f}" text-anchor="middle" '
                     f'fill="var(--ink2)" font-size="11.5" font-weight="600">{val*100:.0f}</text>')
        s.append(f'<text x="{x0+gw/2:.1f}" y="{H-24}" text-anchor="middle" '
                 f'fill="var(--ink)" font-size="12.5">{lab}</text>')
        s.append(f'<text x="{x0+gw/2:.1f}" y="{H-9}" text-anchor="middle" '
                 f'fill="var(--muted)" font-size="11">n={n}</text>')
    s.append("</svg>")
    return "".join(s)


def tbl(head, rows_):
    h = "".join(f"<th>{c}</th>" for c in head)
    b = "".join("<tr>" + "".join(
        f'<td class="num">{c}</td>' if i else f"<td>{c}</td>"
        for i, c in enumerate(r)) + "</tr>" for r in rows_)
    return f'<div class="scroll"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    h1, m = d["H1_cr"], d["meta"]
    t = d["H1_time"]
    g = [("all sessions", h1["level_rate"], h1["level_rate"] - h1["diff"], h1["n"])]
    for k in ("early", "late"):
        if k in t:
            g.append((f"{k} (split {t['split_at']})", t[k]["level_rate"],
                      t[k]["level_rate"] - t[k]["diff"], t[k]["n"]))

    ci = h1["ci"]
    body = f"""
<h1>S75Q — Do MenthorQ gamma levels help the Brooks method?</h1>
<div class="sub">SPX/ES · {m['start']} → {m['end']} · {m['sessions']} sessions ·
rejection = reaches L∓{int(m['R_pts'])}pts before L±{int(m['R_pts'])}pts within {m['N_bars']} bars (2h)
· <b>reaction base rates, not a backtest — no fills, no P&amp;L</b></div>

<div class="card verdict v-weak">
<span class="tag">one weak signal, three nulls</span>
<p style="margin:10px 0 0">Nine of ten tested claims are dead. The single survivor is
<b>H1: price is rejected at Call Resistance more often than at a geometrically identical
placebo level</b> — but it rests on <b>n={h1['n']} resolved touches</b> and the control design
had to be repaired twice before it ran. Treat it as a hypothesis worth one more round,
<b>not</b> an edge to size.</p>
</div>

<h2>H1 (primary, pre-registered) — CR rejection vs date-shuffled placebo</h2>
<div class="hero">
  <div class="stat"><b>{h1['level_rate']*100:.1f}%</b><span>CR rejection rate</span></div>
  <div class="stat"><b>{(h1['level_rate']-h1['diff'])*100:.1f}%</b><span>placebo rate</span></div>
  <div class="stat"><b style="color:var(--ok)">+{h1['diff']*100:.1f}pp</b><span>difference</span></div>
  <div class="stat"><b>{h1['n']}</b><span>resolved touches</span></div>
</div>
<div class="legend"><span><i class="sw" style="background:var(--s1)"></i>CR level</span>
<span><i class="sw" style="background:var(--s2)"></i>date-shuffled placebo</span></div>
{bars(g)}
<p class="note">95% session-clustered bootstrap CI on the difference:
<b>[+{ci[0]*100:.1f}pp, +{ci[1]*100:.1f}pp]</b> — excludes zero, clearing the pre-registered
bar (≥3pp, CI excluding zero). Both time halves agree in sign and rough magnitude, which is
the main reason this isn't dismissed outright.</p>

<h3>Why the placebo is the right control</h3>
<p class="note">The placebo takes the CR's <i>offset from the open</i> from a different randomly
chosen session and applies it to today's open. Same distance geometry, same session, wrong day's
gamma. If a barrier N points above the open simply tends to reject, the placebo scores the same
and the difference vanishes. It doesn't — that gap is the whole result.</p>

<h2>H1 robustness — where it gets shaky</h2>
{tbl(["VIX tercile", "CR rate", "vs placebo", "n"],
     [[k, f"{v['level_rate']*100:.1f}%", f"{v['diff']*100:+.1f}pp", v["n"]]
      for k, v in d["H1_vix"].items()])}
<p class="note">This is the weak point. The effect is carried by <b>low VIX (n={d['H1_vix'].get('low VIX',{}).get('n','–')})</b>,
essentially vanishes in mid VIX, and the high-VIX cell has n=1 and should be ignored entirely.
A real mechanism should not be this lopsided — or the sample is simply too small to split, which
is the more likely reading at n={h1['n']}.</p>

<h2>Exploratory — reported, not decision-grade</h2>

<h3>E1 · Put Support rejected from above <span class="tag v-null" style="--v:var(--bad)">null</span></h3>
<p class="note">{d['E1_ps']['level_rate']*100:.1f}% vs placebo, difference
<b>{d['E1_ps']['diff']*100:+.1f}pp</b>, 95% CI
[{d['E1_ps']['ci'][0]*100:+.1f}, {d['E1_ps']['ci'][1]*100:+.1f}]pp — spans zero, n={d['E1_ps']['n']}.
Notably the raw PS rejection rate ({d['E1_ps']['level_rate']*100:.0f}%) looks as good as CR's, but so
does its placebo. Without the control this would have read as a second edge. It isn't one.</p>

<h3>E2 · HVL as day-type divider <span class="tag" style="--v:var(--warn)">confounded</span></h3>
{tbl(["VIX tercile", "range % · open ABOVE hvl", "range % · open BELOW hvl", "n above", "n below"],
     [[k, v["above"], v["below"], v["n_above"], v["n_below"]] for k, v in d["E2_vix"].items()])}
<p class="note">Headline split looks strong ({d['E2_hvl']['open_above']['range_pct']}% vs
{d['E2_hvl']['open_below']['range_pct']}% range), but opening below HVL is concentrated in high-VIX
sessions ({d['E2_vix'].get('high VIX',{}).get('n_below','–')} of
{d['E2_hvl']['open_below']['n']}), so most of the gap is VIX composition. Within terciles a residual
survives at low/mid VIX and collapses at high VIX. Same confound that killed the regime test — do not
build on this without a proper control.</p>

<h3>E3 · Session extremes cluster near GEX 1–4 <span class="tag" style="--v:var(--bad)">null — and instructive</span></h3>
{tbl(["", "median dist (ES pts)", "mean dist"],
     [["real GEX levels", d["E3_extremes"]["median_dist_gex"], d["E3_extremes"]["mean_dist_gex"]],
      ["date-shuffled placebo", d["E3_extremes"]["median_dist_ctl"], d["E3_extremes"]["mean_dist_ctl"]]])}
<p class="note">Real levels sit {d['E3_extremes']['median_dist_gex']} pts from the session
extreme — which sounds impressive until the placebo lands at {d['E3_extremes']['median_dist_ctl']} pts.
<b>An earlier, badly-designed control put this at 11 vs 78 pts</b>, i.e. a spectacular false positive,
purely because GEX levels cluster near spot while those controls sat at the edge of the span.
Kept in the report as the clearest illustration of why the control design is the entire study.</p>

<h2>Part 1 — the regime axis (all dead)</h2>
{tbl(["claim", "test", "verdict"],
     [["MQ levels use Total GEX", "net 81%/79% exact vs total 17%/20%", "FALSE — our net formula already correct"],
      ["Four Options-Matrix regimes", "+GEX/−DEX cell has n=2 in 5 years", "it's a 3-box, not a 2×2"],
      ["−GEX/−DEX is bearish", "mean return +0.097%, 50.6% up-days", "FALSE"],
      ["GEX predicts realised range", "OOS R² 0.4490 → 0.4416 when added to VIX", "subsumed by VIX"]])}

<h2>Design repairs — logged, because they weaken the result</h2>
<p class="note">Two changes were made <b>after</b> pre-registration. Both were made before any effect
direction was visible, which is the only reason they're defensible — but they still widen the
garden of forking paths and are a reason to discount H1.</p>
<ol class="note">
<li><b>Span 1.5% → 3.0%, exclusion 15 → 12pts.</b> The original control pool collapsed to
0.72 strikes/session with 594 sessions at <i>zero</i>. Broken instrument, not a result.</li>
<li><b>Same-day grid control → date-shuffle placebo.</b> Even widened, a 12pt exclusion around ~14
published levels evacuates the near-open region where every touch happens; grid controls sat
60–140pts out and were never touched. The placebo fixed this and also killed E3's false positive.</li>
</ol>

<h2>What I'd do next — and what I would not</h2>
<p class="note"><b>Would not:</b> size anything on H1. n={h1['n']}, one repaired design,
effect concentrated in a single VIX tercile.</p>
<p class="note"><b>Would:</b> (1) widen the sample — same test on NQ/RTY, whose MQ histories are already
pulled, giving 3 quasi-independent replications rather than a bigger n on one instrument;
(2) test whether the rejection is visible in <i>order flow</i> at the level (the footprint pipeline can
do this, but currently holds one session — it needs a backfill first);
(3) only then, if it survives both, define a Brooks failed-breakout entry at CR and chart-audit
every fill before any P&amp;L is claimed.</p>

<div class="foot">Pre-registration: <code>docs/living/s75q_prereg.md</code> ·
engine <code>scripts/gex_levels_brooks.py</code> · part 1
<code>scripts/gex_net_vs_total.py</code>, <code>scripts/gex_vs_vol_baseline.py</code> ·
data <code>data/options_sim/s75q_levels.json</code>. Levels sourced from the prior session and
converted SPX→ES on the prior session's basis (no lookahead). Not a backtest.</div>
"""
    html = (f"<title>S75Q — Gamma Levels vs Brooks</title><style>{CSS}</style>"
            f'<div class="wrap">{body}</div><script>{JS}</script>')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({len(html)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
