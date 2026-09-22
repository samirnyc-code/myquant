# -*- coding: utf-8 -*-
"""Generate the self-contained STMR report HTML from stmr_report_data.json."""
import json
from pathlib import Path

ROOT = Path(r"c:\Users\Admin\myquant")
R = json.load(open(ROOT / "scratchpad" / "stmr_report_data.json"))
M = R["meta"]
SPX, XSP = R["tickers"]["SPX"], R["tickers"]["XSP"]
ORDER = ["BPS 30/10", "BPS 40/15", "BCS 50/30", "Call ATM", "Call ITM"]
HEAD = ["BPS 30/10", "BCS 50/30", "Call ATM"]
COLOR = {"BPS 30/10": "var(--accent)", "BCS 50/30": "var(--pos)", "Call ATM": "var(--warn)"}


def money(x, sign=False):
    if x is None:
        return "—"
    s = f"${abs(x):,.0f}"
    return (f"−{s}" if x < 0 else (f"+{s}" if sign else s))


def pf(x):
    return "∞" if x is None else f"{x:.2f}"


def cls(x):
    return "pos" if (x or 0) > 0 else ("neg" if (x or 0) < 0 else "zero")


def delta_table(T):
    rows = [r for r in ORDER if r in T["delta_sweep"]]
    th = "".join(f"<th>{r}</th>" for r in rows)
    def line(key, fmt, label, color=False):
        cells = "".join(f'<td class="{cls(T["delta_sweep"][r].get(key)) if color else ""}">{fmt(T["delta_sweep"][r].get(key))}</td>' for r in rows)
        return f"<tr><th>{label}</th>{cells}</tr>"
    return f"""<div class="tbl-wrap"><table class="grid">
<thead><tr><th class="metric">metric</th>{th}</tr></thead><tbody>
{line('n', lambda v: v, 'trades')}
{line('win', lambda v: f'{v}%', 'win rate')}
{line('PF', pf, 'profit factor')}
{line('avg', lambda v: money(v, True), 'avg / trade', True)}
{line('roc', lambda v: f'{v:.1f}%', 'RoC / trade')}
{line('maxDD', lambda v: money(v), 'max drawdown')}
{line('maxRisk', lambda v: money(v), 'max single risk')}
{line('medRisk', lambda v: money(v), 'median risk')}
</tbody></table></div>"""


def exit_table(T, inst):
    ex = T["exit_sweep"][inst]; cols = list(ex)
    th = "".join(f"<th>{c}</th>" for c in cols)
    def line(key, fmt, label):
        return "<tr><th>" + label + "</th>" + "".join(f"<td>{fmt(ex[c].get(key))}</td>" for c in cols) + "</tr>"
    return f"""<div class="tbl-wrap"><table class="grid compact">
<thead><tr><th class="metric">{inst}</th>{th}</tr></thead><tbody>
{line('win', lambda v: f'{v}%', 'win rate')}
{line('PF', pf, 'profit factor')}
{line('roc', lambda v: f'{v:.1f}%', 'RoC / trade')}
{line('maxDD', lambda v: money(v), 'max drawdown')}
</tbody></table></div>"""


def fill_table(T):
    def line(inst):
        fs = T["fill_sensitivity"][inst]
        c = "".join(f'<td>{pf(fs[f].get("PF"))}</td><td class="{cls(fs[f].get("avg"))}">{money(fs[f].get("avg"), True)}</td>' for f in ("mid", "realistic", "conservative"))
        return f'<tr><th>{inst}</th><td>{fs["realistic"]["n"]}</td>{c}</tr>'
    return f"""<div class="tbl-wrap"><table class="grid">
<thead><tr><th class="metric" rowspan="2">instrument</th><th rowspan="2">n</th>
<th colspan="2">mid</th><th colspan="2">realistic 1.25%</th><th colspan="2">conservative 2.5%</th></tr>
<tr><th>PF</th><th>avg$</th><th>PF</th><th>avg$</th><th>PF</th><th>avg$</th></tr></thead>
<tbody>{''.join(line(i) for i in HEAD)}</tbody></table></div>"""


def year_table(T):
    yrs = T["per_year"]
    body = ""
    for y in sorted(yrs):
        row = yrs[y]; cells = ""
        for i in HEAD:
            if i in row:
                cells += f'<td class="num">{row[i]["n"]}</td><td class="{cls(row[i]["pnl"])}">{money(row[i]["pnl"], True)}</td>'
            else:
                cells += '<td class="num">—</td><td>—</td>'
        body += f'<tr><th>{y}</th>{cells}</tr>'
    sub = "".join('<th class="num">n</th><th>P&amp;L</th>' for _ in HEAD)
    return f"""<div class="tbl-wrap"><table class="grid compact">
<thead><tr><th class="metric" rowspan="2">year</th>{''.join(f'<th colspan="2">{i}</th>' for i in HEAD)}</tr>
<tr>{sub}</tr></thead><tbody>{body}</tbody></table></div>"""


def dd_table(T):
    names = {"baseline": "Baseline 1×", "add_weak": "Add on weakness", "add_strong": "Add on bounce"}
    head = "".join(f"<th>{n}</th>" for n in names.values())
    body = ""
    for inst in HEAD:
        dd = T["double_down"][inst]
        for mi, (mk, mn) in enumerate(names.items()):
            m = dd[mk]
            lead = f'<th class="metric" rowspan="3">{inst}</th>' if mi == 0 else ""
            body += (f'<tr>{lead}<td class="lab">{mn}</td><td>{m["n"]}</td><td>{m["win"]}%</td>'
                     f'<td>{pf(m["PF"])}</td><td class="{cls(m["tot"])}">{money(m["tot"], True)}</td>'
                     f'<td>{money(m["maxDD"])}</td><td>{money(m.get("maxConcColl"))}</td></tr>')
    return f"""<div class="tbl-wrap"><table class="grid compact">
<thead><tr><th class="metric">instrument</th><th>variant</th><th>units</th><th>win</th><th>PF</th>
<th>total P&amp;L</th><th>max DD</th><th>peak collateral</th></tr></thead><tbody>{body}</tbody></table></div>"""


def yearfrac(dstr):
    y, m, d = dstr.split("-")
    return int(y) + (int(m) - 1) / 12 + (int(d) - 1) / 365


def equity_chart(T, xmin, xmax, title):
    """Two-panel SVG: overlaid equity curves (top) + drawdown underwater (bottom)."""
    W, H = 920, 400
    L, Rp, top = 62, 14, 18
    eqH, ddH, gap = 236, 84, 26
    eq0, dd0 = top, top + eqH + gap
    series = {k: T["equity"][k] for k in HEAD if k in T["equity"]}
    alleq = [v for s in series.values() for v in s["equity"]]
    alldd = [v for s in series.values() for v in s["dd"]]
    emax, emin = max(alleq + [0]), min(alleq + [0])
    dmin = min(alldd + [0])
    espan = (emax - emin) or 1
    dspan = (0 - dmin) or 1
    def X(f): return L + (f - xmin) / ((xmax - xmin) or 1) * (W - L - Rp)
    def YE(v): return eq0 + (emax - v) / espan * eqH
    def YD(v): return dd0 + (0 - v) / dspan * ddH
    grid = ""
    for frac in [i/4 for i in range(5)]:
        v = emin + frac * espan; y = YE(v)
        grid += f'<line x1="{L}" y1="{y:.1f}" x2="{W-Rp}" y2="{y:.1f}" class="g"/>'
        grid += f'<text class="cy" x="{L-6}" y="{y+3:.1f}" text-anchor="end">{money(round(v))}</text>'
    yr0 = int(xmin) + 1
    for yr in range(yr0, int(xmax) + 1, 2 if xmax - xmin < 12 else 3):
        x = X(yr)
        grid += f'<line x1="{x:.1f}" y1="{eq0}" x2="{x:.1f}" y2="{eq0+eqH}" class="g"/>'
        grid += f'<text class="cx" x="{x:.1f}" y="{dd0+ddH+16}" text-anchor="middle">{str(yr)[2:]}</text>'
    z = YE(0)
    grid += f'<line x1="{L}" y1="{z:.1f}" x2="{W-Rp}" y2="{z:.1f}" class="axis"/>'
    grid += f'<text class="cy" x="{L-6}" y="{dd0-4:.1f}" text-anchor="end" style="fill:var(--neg)">drawdown</text>'
    grid += f'<line x1="{L}" y1="{YD(0):.1f}" x2="{W-Rp}" y2="{YD(0):.1f}" class="axis"/>'
    grid += f'<text class="cy" x="{L-6}" y="{YD(dmin)+3:.1f}" text-anchor="end">{money(round(dmin))}</text>'
    lines = ""
    for k, s in series.items():
        col = COLOR[k]
        pe = " ".join(f"{X(yearfrac(dt)):.1f},{YE(v):.1f}" for dt, v in zip(s["dates"], s["equity"]))
        lines += f'<polyline points="{pe}" fill="none" stroke="{col}" stroke-width="1.9"/>'
        pd_ = " ".join(f"{X(yearfrac(dt)):.1f},{YD(v):.1f}" for dt, v in zip(s["dates"], s["dd"]))
        lines += f'<polyline points="{pd_}" fill="none" stroke="{col}" stroke-width="1.1" opacity="0.85"/>'
    leg = ""
    for i, k in enumerate(series):
        lx = L + i * 150
        leg += f'<rect x="{lx}" y="2" width="11" height="11" rx="2" fill="{COLOR[k]}"/><text class="lg" x="{lx+16}" y="11">{k}</text>'
    return f'''<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="{title}">
<g>{leg}</g>{grid}{lines}</svg>'''


def year_chart(T):
    yrs = T["per_year"]
    data = [(int(y), yrs[y]["BPS 30/10"]["pnl"]) for y in sorted(yrs) if "BPS 30/10" in yrs[y]]
    W, Hh, pad, top = 920, 220, 44, 20
    vals = [d[1] for d in data]; vmax, vmin = max(vals + [0]), min(vals + [0]); span = (vmax - vmin) or 1
    n = len(data); bw = (W - 2 * pad) / n * 0.62
    def X(i): return pad + (i + 0.5) * (W - 2 * pad) / n
    def Y(v): return top + (vmax - v) / span * (Hh - top - 26)
    zero = Y(0); bars = ""
    for i, (yr, v) in enumerate(data):
        y0, y1 = (Y(v), zero) if v >= 0 else (zero, Y(v))
        col = "var(--pos)" if v >= 0 else "var(--neg)"
        bars += f'<rect x="{X(i)-bw/2:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{max(1,y1-y0):.1f}" fill="{col}" rx="1.5"/>'
        bars += f'<text class="cx" x="{X(i):.1f}" y="{Hh-6}" text-anchor="middle">{str(yr)[2:]}</text>'
    return f'''<svg viewBox="0 0 {W} {Hh}" class="chart" role="img" aria-label="BPS P&L by year">
<line x1="{pad}" y1="{zero:.1f}" x2="{W-pad}" y2="{zero:.1f}" class="axis"/>
<text class="cy" x="{pad-6}" y="{Y(vmax)+4:.1f}" text-anchor="end">{money(vmax)}</text>
<text class="cy" x="{pad-6}" y="{Y(vmin)+4:.1f}" text-anchor="end">{money(vmin)}</text>{bars}</svg>'''


HTML = f"""<title>STMR Options Strategy — SPX &amp; XSP Backtest</title>
<style>
:root{{--bg:#0b0e13;--panel:#131a23;--panel2:#1a212c;--line:#27303d;--ink:#e7ecf3;
--mut:#8a97a9;--accent:#38b2c4;--pos:#35c692;--neg:#ef5661;--warn:#e3a84a;
--serif:"Charter","Iowan Old Style","Palatino Linotype",Georgia,serif;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace;}}
@media (prefers-color-scheme: light){{:root{{--bg:#f5f6f8;--panel:#fff;--panel2:#eef1f5;--line:#e0e5ec;
--ink:#17202e;--mut:#5c6879;--accent:#0e8ba0;--pos:#0f8f63;--neg:#cf3a45;--warn:#b0771a;}}}}
:root[data-theme="dark"]{{--bg:#0b0e13;--panel:#131a23;--panel2:#1a212c;--line:#27303d;--ink:#e7ecf3;
--mut:#8a97a9;--accent:#38b2c4;--pos:#35c692;--neg:#ef5661;--warn:#e3a84a;}}
:root[data-theme="light"]{{--bg:#f5f6f8;--panel:#fff;--panel2:#eef1f5;--line:#e0e5ec;--ink:#17202e;
--mut:#5c6879;--accent:#0e8ba0;--pos:#0f8f63;--neg:#cf3a45;--warn:#b0771a;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1040px;margin:0 auto;padding:56px 24px 96px}}
.prose{{max-width:70ch}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}}
h1{{font-family:var(--serif);font-weight:600;font-size:clamp(30px,5vw,46px);line-height:1.08;letter-spacing:-.01em;margin:0 0 14px;text-wrap:balance}}
h2{{font-family:var(--serif);font-weight:600;font-size:27px;letter-spacing:-.01em;margin:0 0 4px;text-wrap:balance}}
h3{{font-size:14px;font-family:var(--mono);letter-spacing:.04em;text-transform:uppercase;color:var(--mut);margin:26px 0 10px}}
.lede{{font-size:19px;color:var(--mut);max-width:64ch;margin:0 0 6px}}
.meta{{font-family:var(--mono);font-size:12.5px;color:var(--mut);margin-top:18px;display:flex;gap:18px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:16px}}
section{{margin-top:52px;border-top:1px solid var(--line);padding-top:30px}}
p{{margin:0 0 14px}} a{{color:var(--accent)}} strong{{color:var(--ink);font-weight:650}}
ul{{max-width:70ch}} li{{margin:4px 0}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:26px 0 8px}}
.tile{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px}}
.tile .k{{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut)}}
.tile .v{{font-family:var(--serif);font-size:30px;font-weight:600;margin-top:4px;font-variant-numeric:tabular-nums}}
.tile .d{{font-size:12.5px;color:var(--mut);margin-top:3px}}
.tbl-wrap{{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:12px;background:var(--panel)}}
table.grid{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}}
table.grid th,table.grid td{{padding:9px 14px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}}
table.grid thead th{{color:var(--mut);font-weight:600;font-family:var(--mono);font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;background:var(--panel2)}}
table.grid tbody th{{text-align:left;color:var(--ink);font-weight:600}}
table.grid th.metric{{text-align:left}} table.grid td.num,table.grid td.lab{{color:var(--mut);text-align:left}}
table.grid tbody tr:last-child td,table.grid tbody tr:last-child th{{border-bottom:none}}
table.compact th,table.compact td{{padding:7px 12px;font-size:13.5px}}
.pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .zero{{color:var(--mut)}}
.setups{{width:100%;border-collapse:collapse;font-size:14.5px;margin:14px 0}}
.setups th,.setups td{{padding:11px 13px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
.setups thead th{{color:var(--mut);font-family:var(--mono);font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;font-weight:600}}
.setups tbody th{{font-weight:650;white-space:nowrap}}
.setups .c{{color:var(--pos);font-weight:600}} .setups .d{{color:var(--warn);font-weight:600}}
.callout{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:10px;padding:16px 20px;margin:20px 0;max-width:78ch}}
.callout.warn{{border-left-color:var(--warn)}}
.callout .lab{{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:6px}}
.callout.warn .lab{{color:var(--warn)}}
.chart{{width:100%;height:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;margin:16px 0}}
.chart .axis{{stroke:var(--mut);stroke-width:1;opacity:.5}} .chart .g{{stroke:var(--line);stroke-width:1}}
.chart .cx,.chart .cy{{fill:var(--mut);font-family:var(--mono);font-size:10.5px}}
.chart .lg{{fill:var(--ink);font-family:var(--mono);font-size:12px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:20px}} @media(max-width:720px){{.two{{grid-template-columns:1fr}}}}
.tag{{font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--mut)}}
footer{{margin-top:56px;padding-top:22px;border-top:1px solid var(--line);color:var(--mut);font-size:12.5px;font-family:var(--mono)}}
</style>

<div class="wrap">
<p class="eyebrow">Quantitative Strategy Report</p>
<h1>The Stochastic Mean-Reversion trade, tested every way that matters</h1>
<p class="lede">A trend-filtered oversold-bounce signal on the S&amp;P 500, expressed as bull put spreads,
bull call spreads and long calls — swept across strikes, exits, position-adds and realistic
transaction costs, on 19 years of SPX and 6½ years of XSP options.</p>
<div class="meta">
<span>SPX {M['spx_range']} · XSP {M['xsp_range']}</span><span>{M['n_base_entries']} base signals</span>
<span>source: ORATS EOD chains</span><span>close-entry · one at a time</span></div>

<div class="tiles">
<div class="tile"><div class="k">BPS win rate</div><div class="v">{SPX['fill_sensitivity']['BPS 30/10']['realistic']['win']}%</div><div class="d">SPX, realistic fills</div></div>
<div class="tile"><div class="k">BPS profit factor</div><div class="v">{SPX['fill_sensitivity']['BPS 30/10']['realistic']['PF']:.2f}</div><div class="d">holds {SPX['fill_sensitivity']['BPS 30/10']['conservative']['PF']:.2f} at 2× costs</div></div>
<div class="tile"><div class="k">edge vs costs</div><div class="v" style="color:var(--pos)">survives</div><div class="d">not a mid-fill mirage</div></div>
<div class="tile"><div class="k">XSP capital / trade</div><div class="v">~${XSP['delta_sweep']['BPS 30/10']['medRisk']/1000:.1f}k</div><div class="d">vs ${SPX['delta_sweep']['BPS 30/10']['medRisk']/1000:.1f}k on SPX</div></div>
</div>

<section><h2>The signal</h2><div class="prose">
<p><strong>STMR — Stochastic Trend-filtered Mean-Reversion.</strong> Buy the dip, but only when the
longer trend is still up. Two conditions, read at the daily close:</p>
<p><span class="tag">ENTER</span> &nbsp; 8-day stochastic <strong>%K8 &lt; 15</strong> (deeply oversold)
&nbsp;<strong>AND</strong>&nbsp; close <strong>&gt; the 100-day SMA</strong> (uptrend intact).<br>
<span class="tag">EXIT</span> &nbsp; close back <strong>above the 5-day SMA</strong>, else at option expiry.</p>
<p>%K8 measures where price sits inside its last 8 sessions' high–low range: 8.5 means "near the
floor." The 100-SMA trend filter is what separates this from catching a falling knife. Every trade
enters at the <strong>daily close</strong> and holds one position at a time.</p></div></section>

<section><h2>The instruments</h2>
<div class="prose"><p>The same signal, five ways. Two axes: do you get <em>paid</em> to enter (credit) or
<em>pay</em> (debit), and how much up-move do you actually need?</p></div>
<table class="setups"><thead><tr><th>setup</th><th>structure</th><th>you…</th><th>max gain</th><th>max loss</th><th>needs</th></tr></thead><tbody>
<tr><th>Short put</th><td>sell 1 put</td><td class="c">collect credit</td><td>credit</td><td>huge (→0)</td><td>price ≥ flat</td></tr>
<tr><th>Bull put spread <span class="tag">BPS</span></th><td>sell put · buy lower put</td><td class="c">credit, tail capped</td><td>credit</td><td>width − credit</td><td>price ≥ flat</td></tr>
<tr><th>Bull call spread <span class="tag">BCS</span></th><td>buy call · sell higher call</td><td class="d">pay debit, upside capped</td><td>width − debit</td><td>debit</td><td>a moderate rally</td></tr>
<tr><th>Long call</th><td>buy 1 call</td><td class="d">pay debit</td><td>unlimited</td><td>debit</td><td>a big rally</td></tr>
<tr><th>Long put</th><td>buy 1 put</td><td class="d">pay debit</td><td>large</td><td>debit</td><td>a drop — wrong side</td></tr>
</tbody></table>
<div class="prose">
<p><strong>Credit plays (short put, BPS)</strong> win from time decay and "nothing bad happening" —
high win rate, positive theta, but you post real collateral to earn a small credit. A BPS is a short
put with the tail bought back: a little less credit for a defined, capped loss.</p>
<p><strong>Debit plays (BCS, long call)</strong> win only if price actually rallies past your strike —
lower win rate, negative theta, tiny capital at risk, convex payoff. A BCS is a long call with the far
upside sold off: cheaper and capped, but far better theta and win rate than a naked call.</p></div></section>

<section><h2>Method &amp; the honest caveats</h2><div class="prose">
<p>ORATS end-of-day chains (OI + greeks). Strikes chosen by <strong>delta</strong>, not fixed
point-widths, so the spread auto-scales as the index runs 700 → 6,850. A 30-delta put ≈ 0.70 call-delta.</p>
<p>Three fill assumptions bound everything:</p>
<ul>
<li><strong>Mid</strong> — (bid+ask)/2. Optimistic ceiling.</li>
<li><strong>Realistic — 1.25% spread.</strong> Measured from our own live OPRA captures of 30-delta,
14-DTE SPX puts (median bid/ask $0.40 ≈ 1.24% of mid). Cross half the spread per leg per side.</li>
<li><strong>Conservative — 2.5%.</strong> Double, to cover the pre-2013 era and stress.</li></ul>
<p>Commissions <strong>$1.30 / contract / side</strong> throughout. Limits: EOD not the exact 16:00
causal fill; no bid/ask on disk (hence modeled haircut); XSP starts 2020; 145 signals — real regime
coverage but thin per year. Read this as a robustness map, not an optimizer.</p></div></section>

<section><h2>Does the edge survive real costs?</h2>
<div class="prose"><p>The one test that matters. If credit-selling were a mid-fill artifact it would
evaporate once you pay the spread. It doesn't.</p></div>
<h3>SPX · 2007–2026 · K8&lt;15, exit SMA5</h3>{fill_table(SPX)}
<h3>XSP · 2020–2026</h3>{fill_table(XSP)}
<div class="callout"><div class="lab">Finding</div>
BPS profit factor falls only <strong>{SPX['fill_sensitivity']['BPS 30/10']['mid']['PF']:.2f} → {SPX['fill_sensitivity']['BPS 30/10']['realistic']['PF']:.2f} → {SPX['fill_sensitivity']['BPS 30/10']['conservative']['PF']:.2f}</strong>
across mid → realistic → conservative on SPX ({XSP['fill_sensitivity']['BPS 30/10']['mid']['PF']:.2f} → {XSP['fill_sensitivity']['BPS 30/10']['realistic']['PF']:.2f} → {XSP['fill_sensitivity']['BPS 30/10']['conservative']['PF']:.2f} on XSP). The bid/ask
costs ~$50/trade — real, but the edge absorbs it. The bought plays move even less.</div></section>

<section><h2>Equity curves &amp; drawdown</h2>
<div class="prose"><p>Cumulative P&amp;L (thick, top) and running drawdown (thin, below) for all three
instruments, realistic fills. The BPS grind vs the debit plays' convex, streakier ride is visible at a glance.</p></div>
<h3>SPX · 2007–2026</h3>{equity_chart(SPX, 2007, 2026.6, 'SPX equity and drawdown')}
<h3>XSP · 2020–2026 · 1/10 the dollars</h3>{equity_chart(XSP, 2020, 2026.6, 'XSP equity and drawdown')}
</section>

<section><h2>Strikes: the instrument sweep</h2>
<div class="prose"><p>Same signal, realistic fills, five expressions. The <strong>max single risk</strong> row is the capital story.</p></div>
<h3>SPX</h3>{delta_table(SPX)}
<h3>XSP · 1/10 notional</h3>{delta_table(XSP)}
<div class="callout"><div class="lab">Read</div>
BPS is the high-win, capital-hungry grinder (one spread tied up <strong>{money(SPX['delta_sweep']['BPS 30/10']['maxRisk'])}</strong>
in 2026). The <strong>BCS is the sleeper</strong>: best return-per-dollar-risked, max risk only
<strong>{money(SPX['delta_sweep']['BCS 50/30']['maxRisk'])}</strong>. On XSP every figure divides by ~10.</div></section>

<section><h2>Exit timing — the structural split</h2>
<div class="prose"><p>Credit and debit plays want <em>opposite</em> exits — and it falls straight out of how each earns.</p></div>
<div class="two"><div><h3>BPS — wants a fast exit</h3>{exit_table(SPX,'BPS 30/10')}</div>
<div><h3>BCS — wants a slow exit</h3>{exit_table(SPX,'BCS 50/30')}</div></div>
<div class="callout"><div class="lab">Why</div>
The <strong>BPS</strong> peaks at <strong>SMA5</strong> — it harvests the fast theta snap; holding
longer re-exposes it (drawdown balloons to {money(SPX['exit_sweep']['BPS 30/10']['SMA10']['maxDD'])} by SMA10). The <strong>BCS</strong>
improves on every axis out to <strong>SMA10</strong> (RoC {SPX['exit_sweep']['BCS 50/30']['SMA5']['roc']:.1f}% → {SPX['exit_sweep']['BCS 50/30']['SMA10']['roc']:.1f}%). Sell premium → exit fast; buy premium → let it run.</div></section>

<section><h2>Year by year</h2>
<div class="prose"><p>SPX bull-put-spread P&amp;L by year — <strong>one red year in twenty</strong> (2018). The debit
plays are streakier with bigger up-tails (2020, 2026).</p></div>
{year_chart(SPX)}
<h3>Per-year detail — n &amp; P&amp;L (SPX, realistic)</h3>{year_table(SPX)}</section>

<section><h2>Fees: the XSP tax</h2>
<div class="prose"><p>XSP's small size is a double-edged sword. Survivable drawdown, but the fixed
per-contract commission becomes a punishing percentage of the tiny premiums.</p></div>
<div class="tbl-wrap"><table class="grid"><thead><tr><th class="metric">BPS 30/10, mid fill</th><th>n</th><th>PF</th><th>avg credit</th><th>fee % of credit</th></tr></thead>
<tbody>
<tr><th>SPX 2007–2026</th><td>136</td><td>4.18</td><td>$1,469</td><td>0.35%</td></tr>
<tr><th>SPX 2020–26 only</th><td>56</td><td>3.74</td><td>$2,505</td><td>0.21%</td></tr>
<tr><th>XSP 2020–2026</th><td>56</td><td>3.17</td><td>$244</td><td class="neg">2.14%</td></tr>
</tbody></table></div>
<div class="callout warn"><div class="lab">Why XSP trails SPX</div>
Two effects, ~half each. <strong>Period:</strong> restricting SPX to 2020–26 alone drops PF 4.18 → 3.74
(2020 + 2022 vol shocks). <strong>Fees:</strong> the rest (3.74 → 3.17) is commission drag — XSP credits
are 1/10 the size but the $1.30/contract fee is fixed, so it eats <strong>2.14% of credit vs 0.21%</strong>,
a 10× bite. Small contracts buy survivable size at the cost of a heavier commission tax.</div></section>

<section><h2>Double-down: averaging into weakness</h2>
<div class="prose"><p>If the day after entry goes further oversold, add a second (and third) unit at the
better price — versus adding only when the bounce confirms. Across all three instruments:</p></div>
{dd_table(SPX)}
<div class="callout warn"><div class="lab">The catch</div>
Averaging into weakness nearly <strong>doubles</strong> BPS profit
({money(SPX['double_down']['BPS 30/10']['baseline']['tot'])} → {money(SPX['double_down']['BPS 30/10']['add_weak']['tot'])}) and even raises PF, holding
the win rate — the reversion is strong enough that a worse entry still reverts. But peak concurrent
collateral jumps to <strong>{money(SPX['double_down']['BPS 30/10']['add_weak']['maxConcColl'])}</strong> (from {money(SPX['double_down']['BPS 30/10']['baseline']['maxConcColl'])}).
On a $4,500 trailing-drawdown prop account that is un-runnable at SPX size — exactly why the XSP version matters.</div></section>

<section><h2>SPX vs XSP — same edge, one-tenth the ticket</h2><div class="prose">
<p>XSP is Mini-SPX: identical cash-settled, European, Section-1256 mechanics at <strong>1/10 the
notional</strong>. Same signal, same edge — only the dollar size changes:</p>
<ul>
<li>BPS max single risk: <strong>{money(SPX['delta_sweep']['BPS 30/10']['maxRisk'])} → {money(XSP['delta_sweep']['BPS 30/10']['maxRisk'])}</strong></li>
<li>BPS max drawdown: <strong>{money(SPX['delta_sweep']['BPS 30/10']['maxDD'])} → {money(XSP['delta_sweep']['BPS 30/10']['maxDD'])}</strong></li>
<li>Double-down peak collateral: <strong>{money(SPX['double_down']['BPS 30/10']['add_weak']['maxConcColl'])} → {money(XSP['double_down']['BPS 30/10']['add_weak']['maxConcColl'])}</strong></li></ul>
<p>The trade that blows a prop drawdown limit on SPX fits comfortably on XSP — at the cost of the fee tax above.</p></div></section>

<section><h2>Best parameters per strategy</h2>
<div class="prose"><p>Distilled from the sweeps (realistic fills). Exit timing is the biggest lever,
and it splits cleanly by structure: <strong>sell premium → exit fast; buy premium → let it run.</strong></p></div>
<div class="tbl-wrap"><table class="grid">
<thead><tr><th class="metric">strategy</th><th>strikes</th><th>exit</th><th>result</th><th>note</th></tr></thead>
<tbody>
<tr><th>BPS</th><td style="text-align:left">short 30Δ / long 10Δ</td><td>SMA5</td><td>91% win · PF 3.99 · RoC 5.4%</td><td style="text-align:left">max win / PF</td></tr>
<tr><th>BPS (alt)</th><td style="text-align:left">short 40Δ / long 15Δ</td><td>SMA5</td><td>89% win · PF 3.01 · RoC 6.7%</td><td style="text-align:left">more return/$, less capital</td></tr>
<tr><th>BCS</th><td style="text-align:left">buy 50Δ / sell 30Δ</td><td>SMA10</td><td>75% win · PF 1.97 · RoC 17.4%</td><td style="text-align:left">best risk-adjusted</td></tr>
<tr><th>Long call</th><td style="text-align:left">65Δ (ITM)</td><td>SMA8–10</td><td>68% win · PF 1.65 · RoC 12.7%</td><td style="text-align:left">streaky, big drawdown</td></tr>
</tbody></table></div>
<div class="prose"><p>All at <strong>~14 DTE, K8&lt;15 entry</strong> (robust across 10–25).</p></div>
<div class="callout warn"><div class="lab">Overfitting caveat</div>
These are the best-<em>observed</em> cells on 136 trades — <strong>not best-guaranteed.</strong> Picking
the peak is overfitting. What's <em>robust</em> and worth trusting: <strong>sell premium → exit fast
(SMA5); buy premium → exit slow (SMA8–10); any sensible delta works.</strong> Marry the direction, not
the exact number.</div>
</section>

<section><h2>Verdict — and how confident to be</h2><div class="prose">
<p><strong>The STMR edge is real and cost-robust</strong> — a defined-risk BPS held ~91% win and PF ~4
across 19 years and through realistic-to-conservative fills. The BCS is the capital-efficient
directional alternative; the long call the convex, higher-variance one.</p>
<p><strong>Confidence: high on the conclusions, lower on the exact numbers.</strong> Solid: the signal
has a genuine edge (it matches the already-validated equity STMR system), the BPS survives the cost
haircut, BPS is the consistent grinder, and the fast-exit/slow-exit split is mechanical. Shaky: the
precise PF/win — ORATS <code>putValue</code> is a <strong>theoretical EOD mid, not a price you can
necessarily trade</strong>; the haircut is modeled, not observed per-trade; 145 signals with 2–11 per
year is a modest sample; and much of the dollar total comes from recent high-collateral years. The
single biggest unknown is whether EOD marks are executable at 16:00 — the live forward-sim is the only
real check. Treat PF 4 as an optimistic anchor that could be 2.5–3 in live trading.</p>
<p>Size to the drawdown you can survive, not the profit factor you can print.</p></div></section>

<footer>Generated from ORATS EOD chains · SPX {M['spx_range']}, XSP {M['xsp_range']} ·
fills mid / 1.25% / 2.5% · fees $1.30/ct/side · not investment advice.</footer>
</div>"""

(ROOT / "scratchpad" / "stmr_report.html").write_text(HTML, encoding="utf-8")
print("wrote scratchpad/stmr_report.html", len(HTML), "bytes")
