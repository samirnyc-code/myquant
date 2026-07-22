# -*- coding: utf-8 -*-
"""Self-contained HTML: filtered vs unfiltered STMR comparison + verdict."""
import json
from pathlib import Path
ROOT = Path(r"c:\Users\Admin\myquant")
R = json.load(open(ROOT / "scratchpad" / "stmr_filtered_data.json"))
U, F = R["variants"]["unfiltered"], R["variants"]["filtered"]
INST = ["BPS 30/10", "BCS 50/30", "Call ATM"]


def money(x, s=False):
    if x is None: return "—"
    a = f"${abs(x):,.0f}"
    return f"−{a}" if x < 0 else (f"+{a}" if s else a)
def pf(x): return "—" if x is None else f"{x:.2f}"
def cls(x): return "pos" if (x or 0) > 0 else ("neg" if (x or 0) < 0 else "zero")
def delta(a, b):  # b vs a, arrow
    if a is None or b is None: return ""
    d = b - a
    if abs(d) < 0.005: return '<span class="flat">≈</span>'
    return f'<span class="{"pos" if d>0 else "neg"}">{"▲" if d>0 else "▼"}</span>'


def cmp_row(label, key, fmt, better_high=True):
    cells = ""
    for inst in INST:
        u, f = U["delta"][inst].get(key), F["delta"][inst].get(key)
        cells += f'<td>{fmt(u)}</td><td>{fmt(f)} {delta(u, f)}</td>'
    return f"<tr><th>{label}</th>{cells}</tr>"


head_inst = "".join(f'<th colspan="2">{i}</th>' for i in INST)
sub = "".join('<th>unfilt</th><th>filtered</th>' for _ in INST)
main_tbl = f"""<div class="tw"><table class="grid">
<thead><tr><th class="m" rowspan="2">metric</th>{head_inst}</tr><tr>{sub}</tr></thead><tbody>
{cmp_row('trades','n',lambda v:v)}
{cmp_row('win rate','win',lambda v:f'{v}%')}
{cmp_row('profit factor','PF',pf)}
{cmp_row('avg / trade','avg',lambda v:money(v,True))}
{cmp_row('RoC / trade','roc',lambda v:f'{v:.1f}%')}
{cmp_row('total P&amp;L','tot',lambda v:money(v,True))}
{cmp_row('max drawdown','maxDD',money)}
</tbody></table></div>"""

# BPS exit sweep comparison
ex_rows = ""
for e in ("SMA3", "SMA5", "SMA8", "SMA10"):
    u, f = U["exit"]["BPS 30/10"][e], F["exit"]["BPS 30/10"][e]
    ex_rows += (f'<tr><th>{e}</th><td>{u["n"]}</td><td>{u["win"]}%</td><td>{pf(u["PF"])}</td>'
                f'<td>{f["n"]}</td><td>{f["win"]}%</td><td>{pf(f["PF"])} {delta(u["PF"],f["PF"])}</td></tr>')
exit_tbl = f"""<div class="tw"><table class="grid"><thead>
<tr><th class="m" rowspan="2">BPS exit</th><th colspan="3">unfiltered</th><th colspan="3">filtered</th></tr>
<tr><th>n</th><th>win</th><th>PF</th><th>n</th><th>win</th><th>PF</th></tr></thead><tbody>{ex_rows}</tbody></table></div>"""

# per-year BPS
yrs = sorted(set(U["year"]) | set(F["year"]))
yr_rows = ""
for y in yrs:
    u = U["year"].get(y, {}).get("BPS 30/10"); f = F["year"].get(y, {}).get("BPS 30/10")
    uc = f'{u["n"]}&nbsp;·&nbsp;<span class="{cls(u["pnl"])}">{money(u["pnl"],True)}</span>' if u else "—"
    fc = f'{f["n"]}&nbsp;·&nbsp;<span class="{cls(f["pnl"])}">{money(f["pnl"],True)}</span>' if f else "—"
    yr_rows += f"<tr><th>{y}</th><td>{uc}</td><td>{fc}</td></tr>"
yr_tbl = f"""<div class="tw"><table class="grid"><thead><tr><th class="m">year</th>
<th>unfiltered (n · P&amp;L)</th><th>filtered (n · P&amp;L)</th></tr></thead><tbody>{yr_rows}</tbody></table></div>"""

HTML = f"""<title>STMR Signal Filter — Filtered vs Unfiltered</title>
<style>
:root{{--bg:#0b0e13;--panel:#131a23;--panel2:#1a212c;--line:#27303d;--ink:#e7ecf3;--mut:#8a97a9;
--accent:#38b2c4;--pos:#35c692;--neg:#ef5661;--warn:#e3a84a;
--serif:"Charter","Iowan Old Style",Georgia,serif;--sans:system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:ui-monospace,"SF Mono",Consolas,monospace;}}
@media(prefers-color-scheme:light){{:root{{--bg:#f5f6f8;--panel:#fff;--panel2:#eef1f5;--line:#e0e5ec;
--ink:#17202e;--mut:#5c6879;--accent:#0e8ba0;--pos:#0f8f63;--neg:#cf3a45;--warn:#b0771a;}}}}
:root[data-theme="dark"]{{--bg:#0b0e13;--panel:#131a23;--panel2:#1a212c;--line:#27303d;--ink:#e7ecf3;--mut:#8a97a9;--accent:#38b2c4;--pos:#35c692;--neg:#ef5661;}}
:root[data-theme="light"]{{--bg:#f5f6f8;--panel:#fff;--panel2:#eef1f5;--line:#e0e5ec;--ink:#17202e;--mut:#5c6879;--accent:#0e8ba0;--pos:#0f8f63;--neg:#cf3a45;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.6}}
.wrap{{max-width:960px;margin:0 auto;padding:56px 24px 90px}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}}
h1{{font-family:var(--serif);font-weight:600;font-size:clamp(28px,5vw,42px);line-height:1.1;margin:0 0 14px;text-wrap:balance}}
h2{{font-family:var(--serif);font-weight:600;font-size:25px;margin:0 0 6px}}
.lede{{font-size:18px;color:var(--mut);max-width:64ch;margin:0 0 6px}}
.meta{{font-family:var(--mono);font-size:12.5px;color:var(--mut);margin-top:16px;border-top:1px solid var(--line);padding-top:14px;display:flex;gap:16px;flex-wrap:wrap}}
section{{margin-top:46px;border-top:1px solid var(--line);padding-top:26px}}
p{{margin:0 0 14px;max-width:70ch}} strong{{color:var(--ink)}}
.verdict{{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--warn);border-radius:12px;padding:22px 26px;margin:24px 0}}
.verdict h2{{margin-top:0}} .verdict .tag{{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--warn);margin-bottom:8px}}
.tw{{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:12px;background:var(--panel)}}
table.grid{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:13.5px}}
table.grid th,table.grid td{{padding:8px 13px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}}
table.grid thead th{{color:var(--mut);font-family:var(--mono);font-size:11px;letter-spacing:.03em;text-transform:uppercase;background:var(--panel2);font-weight:600}}
table.grid tbody th{{text-align:left;font-weight:600}} table.grid th.m{{text-align:left}}
table.grid tbody tr:last-child td,table.grid tbody tr:last-child th{{border-bottom:none}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}.zero,.flat{{color:var(--mut)}}
.filter-box{{font-family:var(--mono);font-size:13px;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:12px 16px;color:var(--ink);margin:12px 0;overflow-x:auto}}
footer{{margin-top:50px;padding-top:20px;border-top:1px solid var(--line);color:var(--mut);font-size:12px;font-family:var(--mono)}}
</style>
<div class="wrap">
<p class="eyebrow">Signal Study · Filter Test</p>
<h1>Does the IBS + body filter improve the STMR trade?</h1>
<p class="lede">Testing Thomas's candle filter as an add-on to the trend-filtered stochastic
mean-reversion signal, across bull put spreads, bull call spreads and long calls on SPX options.</p>
<div class="meta"><span>{R['meta']['range']}</span><span>ES daily signal · SPX ORATS options</span>
<span>realistic fills 1.25%</span><span>close entry · SMA5 exit</span></div>

<div class="verdict"><div class="tag">Verdict</div>
<h2>The filter is redundant — it doesn't help.</h2>
<p>On top of the <strong>%K8&lt;15 &amp; Close&gt;SMA100</strong> trigger, adding
<strong>IBS&lt;40 AND a decisive body</strong> changed almost nothing: it removed only
<strong>{U['n_signals']}→{F['n_signals']}</strong> signals and left the BPS profit factor
essentially flat (<strong>{U['delta']['BPS 30/10']['PF']:.2f} → {F['delta']['BPS 30/10']['PF']:.2f}</strong>,
marginally worse). The reason is structural: <strong>days that are already deeply oversold on the
8-day stochastic almost always close weak (low IBS) with a decisive down-body</strong> — so the
filter is nearly always already satisfied, and adds no new information.</p>
<p><strong>Where it might matter:</strong> on a <em>looser</em> base signal (e.g. Thomas's raw
<code>kSignalUp&gt;0</code>, which fires more often than %K8&lt;15), the filter would prune more and
could add value. On this tighter oversold gate, it's near-redundant.</p></div>

<section><h2>The filter</h2>
<p>Added on top of the base entry, computed from the daily bar:</p>
<div class="filter-box">IBS = (Close − Low) / (High − Low) &nbsp;&lt;&nbsp; 0.40 &nbsp;&nbsp;<span style="color:var(--mut)">// closed in lower 40% of range</span><br>
AND ( |Close−Open| &gt; Range/2.7 &nbsp;OR&nbsp; |Close₋₁−Open₋₁| &gt; Range₋₁/2.5 ) &nbsp;<span style="color:var(--mut)">// decisive body, not a doji</span></div>
<p>Intent: only fade the <strong>sharp, committed sell-off that closed on its lows</strong> — which
for premium-selling also means richer implied vol. Sound logic; it just overlaps almost entirely with
"%K8 &lt; 15" here.</p></section>

<section><h2>Head to head — base config (K8&lt;15, SMA5 exit)</h2>
{main_tbl}
<p style="font-family:var(--mono);font-size:12px;color:var(--mut)">▲/▼ = filtered vs unfiltered. Note the
directional plays (BCS, long call) are <strong>unprofitable on this ES-signal window either way</strong>
— PF near 1 — which underlines how fragile the debit expressions are to the exact signal, while the BPS
edge (PF ~3.8) is robust across signal variations.</p></section>

<section><h2>BPS exit sweep — filtered vs unfiltered</h2>
{exit_tbl}
<p>Same story at every exit: the filter tracks the unfiltered line almost exactly. SMA5 remains the
sweet spot in both.</p></section>

<section><h2>Year by year — BPS</h2>
{yr_tbl}
<p>The filtered and unfiltered P&amp;L move together year to year — no year where the filter meaningfully
rescues or improves the trade.</p></section>

<section><h2>Bottom line</h2>
<p><strong>Keep the STMR signal as is.</strong> Thomas's IBS + body filter is well-reasoned and would be
a good gate on a rawer signal, but on the %K8&lt;15 oversold trigger it's already baked in — it costs a
few trades and adds nothing. If we want to sharpen entries further, the lever is the <strong>exit timing
and the instrument choice</strong> (BPS is the robust edge; the debit plays are fragile), not this
candle filter.</p></section>

<footer>STMR filter study · ES daily signal, SPX ORATS options {R['meta']['range']} ·
filter: IBS&lt;40 AND (body₀&gt;range₀/2.7 OR body₁&gt;range₁/2.5) · not investment advice.</footer>
</div>"""
(ROOT / "scratchpad" / "stmr_filter_report.html").write_text(HTML, encoding="utf-8")
print("wrote", len(HTML), "bytes")
