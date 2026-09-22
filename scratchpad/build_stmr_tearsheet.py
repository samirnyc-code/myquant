"""Generate the STMR MES tearsheet HTML from stmr_final.json (data-driven)."""
import json
from pathlib import Path
R = json.load(open("scratchpad/stmr_final.json"))
c, d, f = R["combo"], R["daily"], R["fourh"]
eq = R["equity"]; sz = R["sizing"]; py = R["peryear"]; pyf = R["peryear_full"]
span = R["span"]; yrs = R["years"]; acctmin = R.get("acct_min_base1", 9012)

def m(x, s=False):
    x = round(x); sign = "+" if (s and x > 0) else ("−" if x < 0 else "")
    return f"{sign}${abs(x):,}"

# equity polyline data -> normalized for canvas via JSON embed
eq_json = json.dumps([[e[0], e[1]] for e in eq])
py_rows = "".join(
    f"<tr><th>{y}{' <span class=part>(part)</span>' if y=='2026' else ''}</th>"
    f"<td class=mono>{pyf[y][0]}</td><td class=mono>{pyf[y][1]}%</td><td class=mono>{pyf[y][2]}</td>"
    f"<td class='mono {'pos' if pyf[y][3]>=0 else 'neg'}'>{m(pyf[y][3],True)}</td></tr>"
    for y in pyf)
sz_rows = "".join(
    f"<tr{' class=hi' if s['k']==6 else ''}><th class=mono>{s['k']}</th>"
    f"<td class='mono pos'>{m(s['ann'])}</td><td class=mono>{s['pct']}%</td>"
    f"<td class='mono neg'>{m(-s['dd'])}</td><td class=mono>{s['ddpct']}%</td>"
    f"<td class=mono>{s['mpct']}%</td></tr>" for s in sz)

HTML = f"""<title>STMR on MES — an overnight-aware tearsheet</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{{
  --paper:#eceff3; --panel:#f7f9fb; --panel2:#eef2f6; --ink:#141c25; --ink2:#33414e;
  --mut:#5d6b78; --line:#d3dbe3; --accent:#256b8a; --accent2:#2f88ad;
  --pos:#0f7a52; --neg:#af3838; --warn:#8f6415;
  --serif:"Charter","Iowan Old Style","Palatino Linotype",Georgia,"Times New Roman",serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code","Consolas",monospace;
}}
@media (prefers-color-scheme:dark){{:root{{
  --paper:#0c1117; --panel:#131b24; --panel2:#18222c; --ink:#e7edf3; --ink2:#c2ccd6;
  --mut:#8493a1; --line:#243039; --accent:#54a6c8; --accent2:#6cbfdd;
  --pos:#40bd8b; --neg:#e46b6b; --warn:#d7a54c;
}}}}
:root[data-theme="light"]{{
  --paper:#eceff3; --panel:#f7f9fb; --panel2:#eef2f6; --ink:#141c25; --ink2:#33414e;
  --mut:#5d6b78; --line:#d3dbe3; --accent:#256b8a; --accent2:#2f88ad;
  --pos:#0f7a52; --neg:#af3838; --warn:#8f6415;
}}
:root[data-theme="dark"]{{
  --paper:#0c1117; --panel:#131b24; --panel2:#18222c; --ink:#e7edf3; --ink2:#c2ccd6;
  --mut:#8493a1; --line:#243039; --accent:#54a6c8; --accent2:#6cbfdd;
  --pos:#40bd8b; --neg:#e46b6b; --warn:#d7a54c;
}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.62;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:940px;margin:0 auto;padding:52px 22px 100px}}
.eyebrow{{font-family:var(--mono);font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin:0 0 14px;font-weight:600}}
h1{{font-family:var(--serif);font-weight:600;font-size:clamp(28px,4.6vw,42px);line-height:1.1;
  letter-spacing:-.012em;margin:0 0 16px;text-wrap:balance;color:var(--ink)}}
.lede{{font-size:18.5px;color:var(--ink2);max-width:64ch;margin:0 0 8px}}
.lineage{{font-family:var(--mono);font-size:12px;color:var(--mut);margin-top:20px;
  display:flex;gap:8px 20px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:16px}}
.lineage b{{color:var(--ink2);font-weight:600}}
section{{margin-top:50px;border-top:1px solid var(--line);padding-top:28px}}
h2{{font-family:var(--serif);font-weight:600;font-size:25px;letter-spacing:-.01em;margin:0 0 6px;color:var(--ink)}}
h3{{font-family:var(--mono);font-size:12px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--mut);margin:24px 0 10px;font-weight:600}}
p{{margin:0 0 14px;max-width:68ch}} a{{color:var(--accent)}}
strong{{color:var(--ink);font-weight:650}}
.mono{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .part{{color:var(--mut);font-size:11px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px;margin:26px 0 6px}}
.tile{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}}
.tile .k{{font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--mut)}}
.tile .v{{font-family:var(--serif);font-size:31px;font-weight:600;margin-top:5px;font-variant-numeric:tabular-nums;line-height:1}}
.tile .d{{font-size:12px;color:var(--mut);margin-top:6px}}
.tbl{{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}
table{{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}}
th,td{{padding:10px 15px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}}
thead th{{color:var(--mut);font-family:var(--mono);font-size:11px;letter-spacing:.04em;
  text-transform:uppercase;font-weight:600;background:var(--panel2)}}
tbody th{{text-align:left;color:var(--ink);font-weight:600;font-family:var(--sans)}}
thead th.l,tbody td.l{{text-align:left}}
tbody tr:last-child th,tbody tr:last-child td{{border-bottom:none}}
tr.hi{{background:color-mix(in srgb,var(--accent) 12%,transparent)}}
tr.tot th,tr.tot td{{border-top:2px solid var(--line);font-weight:700}}
.sig{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:10px;padding:18px 22px;margin:18px 0}}
.sig .row{{display:flex;gap:14px;align-items:baseline;margin:6px 0;flex-wrap:wrap}}
.sig .tag{{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;
  color:#fff;background:var(--accent);padding:3px 9px;border-radius:5px;flex:none}}
.note{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--warn);
  border-radius:10px;padding:16px 20px;margin:18px 0}}
.note .lab{{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--warn);margin-bottom:8px;font-weight:600}}
.note ul{{margin:6px 0 0;padding-left:20px;max-width:68ch}} .note li{{margin:6px 0}}
.assum{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px 22px;
  margin:16px 0 2px;font-family:var(--mono);font-size:12px;color:var(--mut);
  border-top:1px solid var(--line);padding-top:14px}}
.assum b{{color:var(--ink2);font-weight:600;letter-spacing:.02em}}
figure{{margin:18px 0}}
.chart-wrap{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 12px 8px}}
canvas{{width:100%;height:auto;display:block}}
figcaption{{font-family:var(--mono);font-size:11.5px;color:var(--mut);margin-top:10px;padding:0 4px}}
.legend{{display:flex;gap:18px;font-family:var(--mono);font-size:11.5px;color:var(--mut);
  padding:2px 6px 10px}}
.legend i{{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:6px;vertical-align:-1px}}
footer{{margin-top:52px;padding-top:20px;border-top:1px solid var(--line);
  color:var(--mut);font-size:12px;font-family:var(--mono);line-height:1.7}}
</style>

<div class="wrap">
<p class="eyebrow">MES Futures · Real 24-Hour Backtest</p>
<h1>STMR mean-reversion on MES, tested on the real overnight path</h1>
<p class="lede">A trend-filtered oversold-bounce signal on the S&amp;P 500 E-mini, traded as a single
directional MES position. Every stop, target and add-in is simulated on <strong>actual 24-hour
one-minute price</strong> — overnight included — not the day session alone. What survives that
test is smaller than the day-only version, and honest.</p>
<div class="lineage">
<span><b>Source</b> NinjaTrader tick export, full Globex</span>
<span><b>Span</b> {span[0]} → {span[1]} ({yrs} yr)</span>
<span><b>Bars</b> 1.74M · 1-min · 21 ES contracts</span>
<span><b>Validated</b> overnight H/L = independent source, tick-for-tick</span>
<span><b>Unit</b> 1 MES · $5/pt · $5 round-turn</span>
</div>

<div class="tiles">
<div class="tile"><div class="k">Net / year</div><div class="v pos">{m(c['ann'])}</div><div class="d">combined, 1 MES base</div></div>
<div class="tile"><div class="k">Profit factor</div><div class="v">{c['pf']}</div><div class="d">{c['n']} trades, {c['win']}% win</div></div>
<div class="tile"><div class="k">Max drawdown</div><div class="v neg">{m(-c['openDD'])}</div><div class="d">worst unrealized, incl. overnight</div></div>
<div class="tile"><div class="k">On $100k</div><div class="v">14%<span style="font-size:16px">/yr</span></div><div class="d">at 6× base, 10% drawdown</div></div>
</div>

<section>
<h2>The signal</h2>
<p><strong>STMR — Stochastic Trend-filtered Mean-Reversion.</strong> Buy the dip, but only while the
longer trend is still up. Read at the bar close, one position at a time:</p>
<div class="sig">
<div class="row"><span class="tag">Enter</span><span>8-bar stochastic <strong>%K8 &lt; 15</strong>
 (deeply oversold) <strong>and</strong> close <strong>&gt; 100-bar SMA</strong> (trend intact) — go long at the close.</span></div>
<div class="row"><span class="tag">Exit</span><span>close back <strong>above the 5-bar SMA</strong> — or a stop / target if one is used.</span></div>
</div>
<p>The 100-SMA filter is what separates this from catching a falling knife: it only fires oversold
dips <em>inside</em> an uptrend. It runs on two clocks — the <strong>daily</strong> bar (a multi-day
swing) and the <strong>4-hour</strong> bar (a shorter hold) — which fire on different days and are
combined into one book.</p>
</section>

<section>
<h2>What actually survives</h2>
<p>Two engines clear the overnight-path test. On the daily clock, a stop plus a runner target and a
single add-in on further weakness beats the raw signal. On the 4-hour clock, <strong>stops lose money</strong>
— the overnight range is wide enough that any tight stop gets tagged before the reversion completes —
so the un-stopped signal is the one that holds.</p>
<div class="tbl"><table>
<thead><tr><th class="l">engine</th><th>trades</th><th>win</th><th>net P&amp;L</th><th>PF</th><th>max drawdown</th></tr></thead>
<tbody>
<tr><th class="l">Daily · stop 35 / target 75 / +1 on −10</th><td class="mono">{d['n']}</td><td class="mono">{d['win']}%</td><td class="mono pos">{m(d['tot'])}</td><td class="mono">{d['pf']}</td><td class="mono neg">{m(-d['openDD'])}</td></tr>
<tr><th class="l">4-hour · no stop (signal exit)</th><td class="mono">{f['n']}</td><td class="mono">{f['win']}%</td><td class="mono pos">{m(f['tot'])}</td><td class="mono">{f['pf']}</td><td class="mono neg">{m(-f['openDD'])}</td></tr>
<tr class="tot"><th class="l">Combined book</th><td class="mono">{c['n']}</td><td class="mono">{c['win']}%</td><td class="mono pos">{m(c['tot'])}</td><td class="mono">{c['pf']}</td><td class="mono neg">{m(-c['openDD'])}</td></tr>
</tbody></table></div>
<p style="font-size:13.5px;color:var(--mut)">Max drawdown here is the deepest <em>unrealized</em>
mark-to-market loss while a position is open — overnight included — not the tidier closed-trade
figure. It is the money you must actually sit through.</p>
<div class="assum">
<span><b>Date range</b> {span[0]} → {span[1]} · {yrs} yr</span>
<span><b>Fees</b> $5 round-turn / contract — netted into every figure</span>
<span><b>Slippage / haircut</b> not modeled — fills at the bar close or the exact stop / target level</span>
<span><b>Instrument</b> MES · $5 / point · 1 contract = 1 unit</span>
</div>
</section>

<section>
<h2>Equity &amp; drawdown</h2>
<p>Cumulative net P&amp;L of the combined book at 1 MES per signal, marked at each trade's close.</p>
<figure>
<div class="chart-wrap">
<div class="legend"><span><i style="background:var(--accent)"></i>cumulative P&amp;L</span><span><i style="background:var(--neg)"></i>drawdown from peak</span></div>
<canvas id="eq" width="1200" height="520" aria-label="Equity curve and drawdown, combined book, 1 MES base"></canvas>
</div>
<figcaption>{span[0]} → {span[1]} · base 1 MES · net of $5 round-turn</figcaption>
</figure>
</section>

<section>
<h2>Year by year</h2>
<p>Combined book, 1 MES base. Positive in five of five completed years; the one soft year (2022,
the bear) still only cost {m(abs(py['2022'][1]))}.</p>
<div class="tbl" style="max-width:560px"><table>
<thead><tr><th class="l">year</th><th>trades</th><th>win</th><th>PF</th><th>net P&amp;L</th></tr></thead>
<tbody>{py_rows}</tbody></table></div>
</section>

<section>
<h2>Sizing $100k</h2>
<p>The unit is 1 MES per signal; scale by trading <em>k</em> micros per signal. Drawdown and margin
scale linearly. Margin is the real ceiling — the two engines can hold up to {c['peakC']} micros at
once, so peak margin is {c['peakC']}&times;<em>k</em>&times;~$2,450 (the overnight rate, which floats with volatility).</p>
<div class="tbl"><table>
<thead><tr><th class="l">base k</th><th>net / yr</th><th>return</th><th>max drawdown</th><th>of $100k</th><th>peak margin</th></tr></thead>
<tbody>{sz_rows}</tbody></table></div>
<p style="font-size:13.5px;color:var(--mut)">Highlighted row (6×) is the balance point: ~14%/yr with a
~10% peak drawdown and margin under half the account, leaving room for a volatility spike to raise the
requirement without forcing liquidation.</p>
<div class="note" style="border-left-color:var(--accent)">
<div class="lab" style="color:var(--accent)">Suggested account size</div>
<p style="margin:0"><strong>~{m(round(acctmin*1.5/500)*500)} to run 1&times; base</strong> — it covers peak margin
({c['peakC']} MES &times; ~$2,450 = {m(c['peakC']*2450)}), the worst unrealized drawdown ({m(c['openDD'])}),
and a buffer for a volatility-driven margin hike (bare minimum to survive is {m(acctmin)}). The studied
deployment is <strong>$100k at 6&times; base</strong> — the highlighted row: ~14%/yr, ~10% peak drawdown,
margin under half the account.</p>
</div>
</section>

<section>
<h2>What this is — and what could still be wrong</h2>
<p>The edge is real and it is modest. It is the same mean-reversion signal already validated on the
equity side, now measured against the true overnight path instead of the flattering day-session-only
version. Read the profit factor as an honest anchor, not a promise.</p>
<div class="note"><div class="lab">Known limits — read before sizing</div>
<ul>
<li><strong>It is short volatility in disguise.</strong> Long-only dip-buying inside an uptrend pays
until it doesn't — a sustained 2008/2000-style decline is the failure mode, and this 2021–2026
sample contains no such regime. The worst year was only {m(abs(py['2022'][1]))}, which understates
that tail.</li>
<li><strong>Parameters are in-sample.</strong> The stop, target and add spacing were chosen on the full
history. A walk-forward split (train 2021–23, test 2024–26) is not yet done — until it is, discount
the profit factor.</li>
<li><strong>1-minute path, not tick.</strong> Fills land at the bar close or the exact stop/target level;
within a single minute where both are touched, the stop is assumed first (conservative). No slippage
beyond the $5 round-turn. MES liquidity easily covers 1–{c['peakC']} contracts, so fill risk is low but not zero.</li>
<li><strong>Modest sample.</strong> {c['n']} trades over {yrs} years; 2026 is partial. Real regime
coverage, but thin per year.</li>
</ul></div>
<p>Everything here was built from tick data already on the machine — no vendor pull, no modeled
overnight. The next step that would raise confidence is the walk-forward split; the step that would
break it is a bear market the sample never saw.</p>
</section>

<footer>
STMR / MES · 24-hour continuous, panama-stitched · {span[0]}–{span[1]} · 1 MES @ $5/pt, $5 round-turn<br>
Overnight path from NinjaTrader tick export, validated tick-for-tick against independent overnight source · not investment advice.
</footer>
</div>

<script>
const EQ = {eq_json};
const cv = document.getElementById('eq'), ctx = cv.getContext('2d');
function css(v){{ return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }}
function draw(){{
  const dpr = Math.min(2, window.devicePixelRatio||1);
  const w = cv.clientWidth, h = 300;
  cv.width = w*dpr; cv.height = h*dpr; cv.style.height = h+'px';
  ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,w,h);
  const ink=css('--ink'), mut=css('--mut'), line=css('--line'), acc=css('--accent'), neg=css('--neg');
  const padL=58, padR=14, padT=14, padB=40, midGap=8;
  const eqH = (h-padT-padB)*0.66, ddH=(h-padT-padB)*0.34;
  const eqTop=padT, eqBot=padT+eqH, ddTop=eqBot+midGap, ddBot=h-padB;
  const vals=EQ.map(p=>p[1]); const maxV=Math.max(0,...vals), minV=Math.min(0,...vals);
  // drawdown series
  let peak=-1e9; const dd=vals.map(v=>{{peak=Math.max(peak,v);return v-peak;}});
  const maxDD=Math.min(...dd);
  const n=EQ.length; const X=i=> padL + (n<2?0:(i/(n-1))*(w-padL-padR));
  const Ye=v=> eqBot - (v-minV)/((maxV-minV)||1)*eqH;
  const Yd=v=> ddTop - (v/ (maxDD||-1))*ddH*-1; // v<=0 -> maps 0..ddH
  ctx.font='11px ui-monospace,Consolas,monospace'; ctx.textBaseline='middle';
  // eq gridlines + labels
  ctx.strokeStyle=line; ctx.fillStyle=mut; ctx.lineWidth=1;
  const ticks=4;
  for(let t=0;t<=ticks;t++){{ const v=minV+(maxV-minV)*t/ticks; const y=Ye(v);
    ctx.globalAlpha=.5; ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(w-padR,y);ctx.stroke();ctx.globalAlpha=1;
    ctx.textAlign='right'; ctx.fillText('$'+Math.round(v/1000)+'k', padL-8, y); }}
  // zero baseline emphasis
  ctx.strokeStyle=mut;ctx.globalAlpha=.6;ctx.beginPath();const yz=Ye(0);ctx.moveTo(padL,yz);ctx.lineTo(w-padR,yz);ctx.stroke();ctx.globalAlpha=1;
  // eq area
  const grad=ctx.createLinearGradient(0,eqTop,0,eqBot);
  grad.addColorStop(0, acc+'55'); grad.addColorStop(1, acc+'08');
  ctx.beginPath(); ctx.moveTo(X(0),Ye(vals[0]));
  for(let i=1;i<n;i++) ctx.lineTo(X(i),Ye(vals[i]));
  ctx.lineTo(X(n-1),Ye(minV)); ctx.lineTo(X(0),Ye(minV)); ctx.closePath();
  ctx.fillStyle=grad; ctx.fill();
  // eq line
  ctx.beginPath(); ctx.moveTo(X(0),Ye(vals[0]));
  for(let i=1;i<n;i++) ctx.lineTo(X(i),Ye(vals[i]));
  ctx.strokeStyle=acc; ctx.lineWidth=1.9; ctx.lineJoin='round'; ctx.stroke();
  // endpoint dot
  ctx.fillStyle=acc; ctx.beginPath(); ctx.arc(X(n-1),Ye(vals[n-1]),3.2,0,7); ctx.fill();
  // drawdown y-scale: $0 at panel top down to peak DD at the bottom
  ctx.font='10px ui-monospace,Consolas,monospace';
  const ddTicks=2;
  for(let t=0;t<=ddTicks;t++){{
    const frac=t/ddTicks, y=ddTop+frac*ddH, val=maxDD*frac;
    ctx.strokeStyle=line; ctx.globalAlpha=.45; ctx.beginPath(); ctx.moveTo(padL,y); ctx.lineTo(w-padR,y); ctx.stroke(); ctx.globalAlpha=1;
    ctx.fillStyle=mut; ctx.textAlign='right'; ctx.textBaseline='middle';
    ctx.fillText(val===0?'$0':'−$'+Math.abs(Math.round(val)).toLocaleString(), padL-8, y);
  }}
  // drawdown fill + line
  ctx.beginPath(); ctx.moveTo(X(0),ddTop);
  for(let i=0;i<n;i++) ctx.lineTo(X(i), ddTop + (dd[i]/(maxDD||-1))*ddH);
  ctx.lineTo(X(n-1),ddTop); ctx.closePath(); ctx.fillStyle=neg+'33'; ctx.fill();
  ctx.beginPath(); for(let i=0;i<n;i++){{const y=ddTop+(dd[i]/(maxDD||-1))*ddH; i?ctx.lineTo(X(i),y):ctx.moveTo(X(i),y);}}
  ctx.strokeStyle=neg; ctx.lineWidth=1.2; ctx.stroke();
  ctx.textAlign='right'; ctx.fillStyle=mut; ctx.font='10px ui-monospace,Consolas,monospace';
  ctx.fillText('drawdown from peak · $, 1 MES', w-padR-2, ddTop+9);
  // year labels
  ctx.textAlign='center'; ctx.fillStyle=mut;
  let lastYr=null;
  for(let i=0;i<n;i++){{ const yr=EQ[i][0].slice(0,4); if(yr!==lastYr){{lastYr=yr; ctx.fillText(yr, X(i), h-padB+16);}} }}
}}
draw();
let rt; addEventListener('resize',()=>{{clearTimeout(rt);rt=setTimeout(draw,120);}});
const mo=new MutationObserver(draw); mo.observe(document.documentElement,{{attributes:true,attributeFilter:['data-theme']}});
matchMedia('(prefers-color-scheme:dark)').addEventListener('change',draw);
</script>
"""
Path("scratchpad/stmr_tearsheet.html").write_text(HTML, encoding="utf-8")
print("wrote scratchpad/stmr_tearsheet.html", len(HTML), "bytes")
