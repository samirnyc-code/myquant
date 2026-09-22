"""flip_wyckoff_build_report.py — render tempo/outputs/wyckoff_report.json into a
self-contained HTML report. Inline SVG charts, both themes, no external assets.

    python tempo/scripts/flip_wyckoff_build_report.py           # internal edition
    python tempo/scripts/flip_wyckoff_build_report.py --share   # shareable edition
        (adds a plain-language glossary, drops internal script/branch references)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "tempo" / "outputs" / "wyckoff_report.json"
OUTHTML = ROOT / "reports" / "wyckoff_climax_report.html"
OUTSHARE = ROOT / "reports" / "wyckoff_climax_report_share.html"

HTML = r"""<title>Wyckoff Effort-vs-Result · Climax-Flip Filter</title>
<style>
:root{
  --paper:#f4f2ec; --surface:#fbfaf6; --ink:#1a1815; --ink2:#57544c; --muted:#8b877d;
  --grid:#e4e1d7; --axis:#c7c3b6; --rule:#d8d3c4;
  --accent:#1f6fd0;         /* Wyckoff / kept series */
  --base:#8b877d;           /* baseline series (muted, always labeled) */
  --good:#0a8f36; --bad:#c8382f; --ochre:#b8842a;
  --card:#fbfaf6; --border:rgba(26,24,21,0.12);
  --mono:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace;
  --sans:"Segoe UI",system-ui,-apple-system,sans-serif;
}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){
  --paper:#100f0b; --surface:#1a1915; --ink:#efece2; --ink2:#b7b2a4; --muted:#8b877d;
  --grid:#2a2822; --axis:#3a382f; --rule:#33302a;
  --accent:#4a93e8; --base:#8b877d; --good:#33b45c; --bad:#e0655c; --ochre:#d3a24e;
  --card:#1a1915; --border:rgba(239,236,226,0.13);
}}
:root[data-theme="dark"]{
  --paper:#100f0b; --surface:#1a1915; --ink:#efece2; --ink2:#b7b2a4; --muted:#8b877d;
  --grid:#2a2822; --axis:#3a382f; --rule:#33302a;
  --accent:#4a93e8; --base:#8b877d; --good:#33b45c; --bad:#e0655c; --ochre:#d3a24e;
  --card:#1a1915; --border:rgba(239,236,226,0.13);
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:48px 24px 80px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--ochre);font-weight:600}
h1{font-size:clamp(26px,4.4vw,40px);line-height:1.08;margin:.35em 0 .2em;text-wrap:balance;
  letter-spacing:-.015em;font-weight:680}
h2{font-size:22px;margin:0 0 4px;letter-spacing:-.01em;text-wrap:balance}
h3{font-size:15px;margin:0 0 2px}
.lede{font-size:17px;color:var(--ink2);max-width:66ch;margin:.4em 0 0}
.meta{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:18px;
  display:flex;gap:18px;flex-wrap:wrap}
section{margin-top:52px;scroll-margin-top:20px}
.sec-head{border-top:2px solid var(--rule);padding-top:16px;margin-bottom:22px;
  display:flex;align-items:baseline;gap:14px}
.sec-num{font-family:var(--mono);font-size:12px;color:var(--ochre);font-weight:700;
  flex:none;padding-top:3px}
.sec-desc{color:var(--ink2);font-size:14.5px;max-width:64ch;margin:2px 0 0}
p{max-width:68ch}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 8px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px 16px 14px}
.card .k{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted)}
.card .v{font-size:27px;font-weight:680;margin-top:6px;font-variant-numeric:tabular-nums;
  display:flex;align-items:baseline;gap:8px}
.card .sub{font-family:var(--mono);font-size:12px;color:var(--ink2);margin-top:3px;
  font-variant-numeric:tabular-nums}
.delta{font-family:var(--mono);font-size:13px;font-weight:600}
.up{color:var(--good)} .down{color:var(--bad)}
.chart{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:18px 18px 12px;margin-top:14px}
.chart .ctitle{font-size:14px;font-weight:620;margin-bottom:2px}
.chart .csub{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-bottom:10px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-family:var(--mono);font-size:11.5px;
  color:var(--ink2);margin-top:8px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:11px;height:11px;border-radius:3px;flex:none}
svg{display:block;width:100%;height:auto;overflow:visible}
.tick{font-family:var(--mono);font-size:10.5px;fill:var(--muted)}
.blab{font-family:var(--mono);font-size:10px;fill:var(--ink2);font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:4px}
.tblwrap{overflow-x:auto;border:1px solid var(--border);border-radius:10px;margin-top:14px}
th,td{padding:9px 12px;text-align:right;font-variant-numeric:tabular-nums;
  border-bottom:1px solid var(--grid);white-space:nowrap}
th{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);font-weight:600;background:var(--paper)}
td:first-child,th:first-child{text-align:left;font-family:var(--mono)}
tr:last-child td{border-bottom:none}
.row-hi{background:color-mix(in srgb,var(--accent) 9%,transparent)}
.badge{font-family:var(--mono);font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px;
  letter-spacing:.05em}
.b-bless{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good)}
.b-rej{background:color-mix(in srgb,var(--bad) 15%,transparent);color:var(--bad)}
.callout{border-left:3px solid var(--accent);background:color-mix(in srgb,var(--accent) 6%,transparent);
  padding:14px 18px;border-radius:0 8px 8px 0;margin:16px 0;font-size:14.5px}
.callout.warn{border-color:var(--ochre);background:color-mix(in srgb,var(--ochre) 8%,transparent)}
.callout.neg{border-color:var(--bad);background:color-mix(in srgb,var(--bad) 6%,transparent)}
.quote{font-family:var(--mono);font-size:13px;color:var(--ink2);border-left:2px solid var(--rule);
  padding-left:14px;margin:14px 0}
ul{max-width:68ch;padding-left:20px} li{margin:5px 0}
.foot{margin-top:60px;border-top:1px solid var(--rule);padding-top:16px;
  font-family:var(--mono);font-size:11.5px;color:var(--muted)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:680px){.grid2{grid-template-columns:1fr}}
b,strong{font-weight:660}
</style>

<div class="wrap">
<div class="eyebrow">Tempo climax-flip · setup filter study</div>
<h1>Wyckoff Effort&#8202;vs&#8202;Result, applied to the climax&#8209;flip</h1>
<p class="lede">Richard Wyckoff&rsquo;s century-old tape-reading gives a <b>pre-registered</b>, falsifiable
rule for which climax reversals to trust. We tested five of his signatures on the frozen climax-flip
engine with strict train/test discipline. One survived cleanly &mdash; and the full walk-forward adopts it.</p>
<div class="meta">
  <span id="asof"></span><span>source&nbsp;&middot;&nbsp;tradingwyckoff.com/en/wyckoff-method (scraped)</span>
  <span>engine&nbsp;&middot;&nbsp;tempo_engine_bars &middot; 2000&#8209;tick bars &middot; 2021&ndash;2026</span>
</div>

<!-- THESIS -->
<section>
  <div class="sec-head"><div class="sec-num">THESIS</div>
    <div><h2>Our setup is Wyckoff&rsquo;s &ldquo;Climax&rdquo; fast&#8209;reversal</h2>
    <p class="sec-desc">Villahermosa devotes a section to compressed reversals. The climax-flip &mdash; two
    adjacent opposite climax bars &mdash; is his first model, and his Law of Effort vs Result predicts
    which ones hold.</p></div></div>
  <p class="quote">&ldquo;A round-trip leg that halts the previous trend with the whole process compressed
  into a few candles. The exact reversal is usually untradable due to speed&hellip; the trade comes with
  the subsequent reading.&rdquo;</p>
  <p>The <b>three Spring types by volume</b> give the testable edge, and Wyckoff states the sign in advance:
  the reversal that happens on <b>less</b> volume than the trap (&ldquo;Spring&nbsp;#3&rdquo;) is the most
  reliable; the high-volume reversal (&ldquo;Terminal Shakeout / Spring&nbsp;#1&rdquo;) is the one that fails.
  Because our bars are fixed at 2000 ticks, <b>volume-per-bar is average trade size</b> &mdash; a clean effort
  gauge. A reversal built on smaller size than the trap = supply genuinely exhausted.</p>
</section>

<!-- HEADLINE: WALK FORWARD -->
<section>
  <div class="sec-head"><div class="sec-num">01</div>
    <div><h2>The walk-forward adopts the filter &mdash; on its own</h2>
    <p class="sec-desc">144-config grid (IBS&times;SAR&times;EB&times;RR&times;skip-H8&times;Wyckoff), in-sample
    through 2022, expanding, selection on past data only. Apples-to-apples on the S119 walk-forward-stable
    config below.</p></div></div>
  <div class="cards" id="wf-cards"></div>
  <div class="callout"><b>Under PF selection the walk-forward picks Wyckoff&nbsp;=&nbsp;ON in all four
  out-of-sample years.</b> The filter roughly doubles $/trade <em>and</em> halves max drawdown &mdash; the
  drawdown cut is the headline: it neutralises 2024, the one losing year.</div>
  <div class="grid2">
    <div class="chart"><div class="ctitle">$ / trade &middot; OOS 2023&ndash;26</div>
      <div class="csub">higher is better</div><div id="wf-dtr"></div></div>
    <div class="chart"><div class="ctitle">Max drawdown &middot; OOS 2023&ndash;26</div>
      <div class="csub">shorter bar is better</div><div id="wf-dd"></div></div>
  </div>
  <div class="tblwrap"><table id="wf-tbl"></table></div>
</section>

<!-- EQUITY -->
<section>
  <div class="sec-head"><div class="sec-num">02</div>
    <div><h2>Equity: fewer trades, smoother, and more money</h2>
    <p class="sec-desc">Base climax-flip (IBS+RR2+skip-H8) across full history, with and without the
    Terminal-Shakeout skip. Full history: <b>+$1.4k on 43% fewer trades</b>, drawdown &minus;30%, $/trade
    20.0&rarr;36.5. Over the test years alone total is ~flat while $/trade and drawdown still improve.</p></div></div>
  <div class="chart"><div class="ctitle">Cumulative net $ &middot; 2021&ndash;2026 &middot; 1 ES, gross of costs</div>
    <div class="csub">filter = skip flips where reversal-bar volume &gt; trap-bar volume &middot; base $33.6k&rarr;filtered $35.0k</div>
    <div id="eq"></div>
    <div class="legend"><span><span class="sw" style="background:var(--base)"></span>baseline</span>
      <span><span class="sw" style="background:var(--accent)"></span>Wyckoff-filtered</span></div></div>
</section>

<!-- PER YEAR -->
<section>
  <div class="sec-head"><div class="sec-num">03</div>
    <div><h2>Improves every single year</h2>
    <p class="sec-desc">$ / trade by year, base config. The filter lifts or holds all six years and
    turns 2021 and 2024 around.</p></div></div>
  <div class="chart"><div class="ctitle">$ / trade by year &middot; baseline vs Wyckoff-filtered</div>
    <div class="csub" id="py-sub"></div>
    <div id="py"></div>
    <div class="legend"><span><span class="sw" style="background:var(--base)"></span>baseline</span>
      <span><span class="sw" style="background:var(--accent)"></span>Wyckoff-filtered</span></div></div>
</section>

<!-- THE SCREEN -->
<section>
  <div class="sec-head"><div class="sec-num">04</div>
    <div><h2>The screen: five signatures, signs fixed before looking</h2>
    <p class="sec-desc">Each filter&rsquo;s direction was pre-registered from Wyckoff <em>before</em> seeing
    P&amp;L. Terciles cut on train (2021&ndash;22), applied unchanged to test (2023&ndash;26). Blessed only
    if the favoured tercile beats the disfavoured one in <b>both</b> periods.</p></div></div>
  <div class="chart"><div class="ctitle">Test-period $ / trade by tercile &middot; low &rarr; high feature value</div>
    <div class="csub">two volume-based signatures survived; the tempo-composite versions flipped out of sample</div>
    <div id="screen"></div></div>
  <div class="tblwrap"><table id="screen-tbl"></table></div>
  <p style="margin-top:14px">The survivors are both <b>volume</b> measures &mdash; exactly Wyckoff&rsquo;s framing.
  The tempo-composite analogues (which fold in bar duration) failed, and absolute effort percentile flipped
  hard out of sample. The clean signal is raw <span style="font-family:var(--mono)">vol(reversal) &lt; vol(trap)</span>.</p>
</section>

<!-- SECONDARY TEST -->
<section>
  <div class="sec-head"><div class="sec-num">05</div>
    <div><h2>The Secondary Test does <em>not</em> transplant</h2>
    <p class="sec-desc">Wyckoff&rsquo;s ST says a valid retest comes on <b>lower</b> volume. We tested the first
    post-entry bar as an in-trade confirmation. The naive sign is wrong here &mdash; and the actionable rule
    loses money.</p></div></div>
  <div class="grid2">
    <div class="chart"><div class="ctitle">Diagnostic &middot; final $ / trade by first post-entry bar</div>
      <div class="csub">pre-registered: quiet = better. Reality: loud follow-through wins (sign flips)</div>
      <div id="st-diag"></div>
      <div class="legend"><span><span class="sw" style="background:var(--base)"></span>train 21&ndash;22</span>
        <span><span class="sw" style="background:var(--accent)"></span>test 23&ndash;26</span></div></div>
    <div class="chart"><div class="ctitle">Actionable ST-scratch rule &middot; $ / trade by year</div>
      <div class="csub">exit if first bar is loud &amp; against &mdash; hurts almost every year</div>
      <div id="st-py"></div>
      <div class="legend"><span><span class="sw" style="background:var(--base)"></span>baseline</span>
        <span><span class="sw" style="background:var(--bad)"></span>ST-scratch</span></div></div>
  </div>
  <div class="callout neg"><b>Rejected.</b> Once you are already in the reversal you want the impulse leg
  (Wyckoff&rsquo;s Sign of Strength), not a quiet test &mdash; a loud post-entry bar predicts a <em>better</em>
  outcome, and scratching on it cuts winners. The ST is an <em>entry-timing</em> tool, not an in-trade filter;
  that reframe is the only open follow-up.</div>
</section>

<!-- METHOD -->
<section>
  <div class="sec-head"><div class="sec-num">NOTES</div>
    <div><h2>Method &amp; caveats</h2></div></div>
  <ul>
    <li><b>Frozen mechanics.</b> Stop 1 tick beyond the 2-bar box, one position, conservative both-in-bar&rarr;stop,
      session-end close. RR2 target. Same in every arm.</li>
    <li><b>Filter definition.</b> Skip a climax-flip entry when reversal-bar volume &gt; trap-bar volume
      (the 1.0 boundary is Wyckoff-theoretic, not fitted). In the walk-forward it composes with SAR: a filtered
      reversal still closes the old position, it just doesn&rsquo;t open the new one.</li>
    <li><b>Magnitude shrinks out of sample</b> (train edge &asymp; 2&times; test) but keeps its sign and
      monotonicity &mdash; the discipline passing, not a red flag.</li>
    <li><b>Win rate barely moves</b> (~35%). The edge is removing stop-outs, not manufacturing winners.</li>
    <li><b>Fills.</b> Reversal-bar close fills; ~1 tick slippage on ~30% of fast bars (&asymp; &minus;$4/trade)
      not yet modelled here &mdash; applies equally to both arms.</li>
    <li><b>Not yet:</b> walk-forward of the exact boundary; tick-level fill validation; NT8 indicator param.</li>
  </ul>
  <div class="foot">scripts &middot; flip_wyckoff_effort.py &nbsp;/&nbsp; flip_wf_wyckoff.py &nbsp;/&nbsp;
    flip_wyckoff_st.py &nbsp;/&nbsp; flip_wyckoff_report_data.py &nbsp;&middot;&nbsp; branch leglab &middot;
    all outputs dated in tempo/outputs/</div>
</section>
</div>

<script id="D" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('D').textContent);
document.getElementById('asof').textContent='as of '+D.as_of;
const NS='http://www.w3.org/2000/svg';
const el=(t,a={})=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const cs=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const money=v=>(v<0?'−$':'$')+Math.abs(Math.round(v)).toLocaleString();
const dtr=v=>(v<0?'−$':'+$')+Math.abs(v).toFixed(1);

/* ---- WF cards ---- */
const wf=D.wf_summary;
const base=wf.find(r=>r.row.includes('base (no wyck)'));
const wyck=wf.find(r=>r.row.includes('WF-stable + WYCK'));
const pfpick=wf.find(r=>r.row.includes('select-by-pf'));
const pct=(a,b)=>((a-b)/Math.abs(b)*100);
function card(k,v,sub,delta,dir){
  const c=`<div class="card"><div class="k">${k}</div><div class="v">${v}${delta?`<span class="delta ${dir}">${delta}</span>`:''}</div><div class="sub">${sub}</div></div>`;
  return c;}
document.getElementById('wf-cards').innerHTML=
  card('$ / trade','$'+wyck['$/trade'].toFixed(1),'base $'+base['$/trade'].toFixed(1),
       '+'+pct(wyck['$/trade'],base['$/trade']).toFixed(0)+'%','up')+
  card('Max drawdown',money(wyck.maxDD_$),'base '+money(base.maxDD_$),
       pct(Math.abs(wyck.maxDD_$),Math.abs(base.maxDD_$)).toFixed(0)+'%','up')+
  card('Profit factor',wyck.PF.toFixed(2),'base '+base.PF.toFixed(2),
       '+'+(wyck.PF-base.PF).toFixed(2),'up')+
  card('WF picks Wyckoff','4 / 4 yrs','under PF selection','','');

/* ---- generic grouped bars (two series, can be negative), direct-labeled ---- */
function groupedBars(id,cats,s1,s2,c1,c2,fmt,H=230){
  const box=document.getElementById(id);box.innerHTML='';
  const W=Math.max(box.clientWidth,320),padL=40,padR=12,padT=18,padB=42;
  const iw=W-padL-padR,ih=H-padT-padB;
  const all=[...s1,...s2],mx=Math.max(0,...all),mn=Math.min(0,...all);
  const rng=(mx-mn)||1,y=v=>padT+ih*(mx-v)/rng;
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img'});
  // zero line + gridlines
  const zeroY=y(0);
  for(let g=0;g<=4;g++){const gv=mn+rng*g/4,gy=y(gv);
    svg.appendChild(el('line',{x1:padL,x2:W-padR,y1:gy,y2:gy,stroke:cs('--grid'),'stroke-width':1}));
    const t=el('text',{x:padL-6,y:gy+3,'text-anchor':'end',class:'tick'});t.textContent=fmt(gv);svg.appendChild(t);}
  svg.appendChild(el('line',{x1:padL,x2:W-padR,y1:zeroY,y2:zeroY,stroke:cs('--axis'),'stroke-width':1.5}));
  const gw=iw/cats.length,bw=Math.min(26,gw*0.32);
  cats.forEach((c,i)=>{
    const cx=padL+gw*i+gw/2;
    [[s1[i],c1,-1],[s2[i],c2,1]].forEach(([v,col,off])=>{
      const bx=cx+off*(bw/2+1)-bw*(off<0?1:0);
      const yy=v>=0?y(v):zeroY, hh=Math.abs(zeroY-y(v));
      svg.appendChild(el('rect',{x:bx,y:yy,width:bw,height:Math.max(hh,0.5),rx:3,fill:col}));
      const lab=el('text',{x:bx+bw/2,y:v>=0?yy-4:yy+hh+11,'text-anchor':'middle',class:'blab'});
      lab.textContent=fmt(v);svg.appendChild(lab);
    });
    const t=el('text',{x:cx,y:H-padB+16,'text-anchor':'middle',class:'tick'});t.textContent=c;svg.appendChild(t);
  });
  svg.appendChild(el('title',{}));
  box.appendChild(svg);
}

/* single-series bars (one measure, one axis) */
function singleBars(id,cats,vals,cols,fmt,H=230){
  const box=document.getElementById(id);box.innerHTML='';
  const W=Math.max(box.clientWidth,300),padL=48,padR=12,padT=16,padB=34;
  const iw=W-padL-padR,ih=H-padT-padB;
  const mx=Math.max(0,...vals),mn=Math.min(0,...vals),rng=(mx-mn)||1,y=v=>padT+ih*(mx-v)/rng;
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img'});
  for(let g=0;g<=4;g++){const gv=mn+rng*g/4,gy=y(gv);
    svg.appendChild(el('line',{x1:padL,x2:W-padR,y1:gy,y2:gy,stroke:cs('--grid'),'stroke-width':1}));
    const t=el('text',{x:padL-6,y:gy+3,'text-anchor':'end',class:'tick'});t.textContent=fmt(gv);svg.appendChild(t);}
  const zeroY=y(0);
  svg.appendChild(el('line',{x1:padL,x2:W-padR,y1:zeroY,y2:zeroY,stroke:cs('--axis'),'stroke-width':1.4}));
  const gw=iw/cats.length,bw=Math.min(40,gw*0.5);
  cats.forEach((c,i)=>{const cx=padL+gw*i+gw/2,v=vals[i];
    const yy=v>=0?y(v):zeroY,hh=Math.abs(zeroY-y(v));
    svg.appendChild(el('rect',{x:cx-bw/2,y:yy,width:bw,height:Math.max(hh,0.5),rx:3,fill:cols[i]}));
    const lab=el('text',{x:cx,y:v>=0?yy-4:yy+hh+11,'text-anchor':'middle',class:'blab'});
    lab.textContent=fmt(v);svg.appendChild(lab);
    const t=el('text',{x:cx,y:H-padB+16,'text-anchor':'middle',class:'tick'});t.textContent=c;svg.appendChild(t);});
  box.appendChild(svg);
}
const wfLab={'WF select-by-pts (144-grid, wyck available)':'WF·pts',
  'WF select-by-pf (144-grid, wyck available)':'WF·pf',
  'WF-stable base (no wyck)':'base','WF-stable + WYCK':'+WYCK'};
const wfOrder=[base,wyck,wf.find(r=>r.row.includes('by-pts')),pfpick];
const wfCats=wfOrder.map(r=>wfLab[r.row]);
const wfCols=wfOrder.map(r=>r.wyck_picked>0?cs('--accent'):cs('--base'));
singleBars('wf-dtr',wfCats,wfOrder.map(r=>r['$/trade']),wfCols,v=>'$'+v.toFixed(0),240);
singleBars('wf-dd',wfCats,wfOrder.map(r=>r.maxDD_$),wfCols,v=>money(v),240);

/* WF table */
(function(){
  const rows=wf.map(r=>`<tr class="${r.row.includes('WYCK')||r.row.includes('by-pf')?'row-hi':''}">
    <td>${r.row}</td><td>${r.n}</td><td>${r.PF.toFixed(2)}</td>
    <td>$${r['$/trade'].toFixed(1)}</td><td>${money(r.maxDD_$)}</td>
    <td>${r.wyck_picked??''}</td></tr>`).join('');
  document.getElementById('wf-tbl').innerHTML=
    `<thead><tr><th>config (OOS 2023&ndash;26)</th><th>n</th><th>PF</th><th>$/tr</th><th>max&nbsp;DD</th><th>wyck picks</th></tr></thead><tbody>${rows}</tbody>`;
})();

/* ---- equity line chart (two series over calendar time) ---- */
(function(){
  const box=document.getElementById('eq');const W=Math.max(box.clientWidth,320),H=280;
  const padL=52,padR=14,padT=14,padB=26,iw=W-padL-padR,ih=H-padT-padB;
  const d0=new Date(D.equity.base_dates[0]).getTime();
  const dN=new Date(D.equity.base_dates[D.equity.base_dates.length-1]).getTime();
  const tx=ds=>padL+iw*((new Date(ds).getTime()-d0)/(dN-d0));
  const all=[...D.equity.base,...D.equity.filt],mx=Math.max(...all),mn=Math.min(...all,0);
  const rng=(mx-mn)||1,ty=v=>padT+ih*(mx-v)/rng;
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img'});
  for(let g=0;g<=4;g++){const gv=mn+rng*g/4,gy=ty(gv);
    svg.appendChild(el('line',{x1:padL,x2:W-padR,y1:gy,y2:gy,stroke:cs('--grid'),'stroke-width':1}));
    const t=el('text',{x:padL-8,y:gy+3,'text-anchor':'end',class:'tick'});t.textContent=money(gv);svg.appendChild(t);}
  svg.appendChild(el('line',{x1:padL,x2:W-padR,y1:ty(0),y2:ty(0),stroke:cs('--axis'),'stroke-width':1.3}));
  // year ticks
  [2021,2022,2023,2024,2025,2026].forEach(yr=>{const gx=tx(yr+'-01-01');
    if(gx>=padL&&gx<=W-padR){svg.appendChild(el('line',{x1:gx,x2:gx,y1:padT,y2:padT+ih,stroke:cs('--grid'),'stroke-width':1,'stroke-dasharray':'2 3'}));
    const t=el('text',{x:gx,y:H-6,'text-anchor':'middle',class:'tick'});t.textContent=yr;svg.appendChild(t);}});
  function line(vals,dates,col,w){
    let d='';for(let i=0;i<vals.length;i++){d+=(i?'L':'M')+tx(dates[i]).toFixed(1)+' '+ty(vals[i]).toFixed(1);}
    svg.appendChild(el('path',{d,fill:'none',stroke:col,'stroke-width':w,'stroke-linejoin':'round','stroke-linecap':'round'}));
    const lx=tx(dates[dates.length-1]),ly=ty(vals[vals.length-1]);
    svg.appendChild(el('circle',{cx:lx,cy:ly,r:3.5,fill:col}));
  }
  line(D.equity.base,D.equity.base_dates,cs('--base'),1.6);
  line(D.equity.filt,D.equity.filt_dates,cs('--accent'),2.2);
  box.appendChild(svg);
})();

/* ---- per year ---- */
(function(){
  const py=D.peryear;
  groupedBars('py',py.map(r=>r.year),py.map(r=>r.base_dtr),py.map(r=>r.filt_dtr),
    cs('--base'),cs('--accent'),v=>(v>=0?'$':'−$')+Math.abs(v).toFixed(0),250);
  document.getElementById('py-sub').textContent=
    'trades kept per year: '+py.map(r=>r.year+' '+Math.round(100*r.filt_n/r.base_n)+'%').join('  ·  ');
})();

/* ---- screen: test tercile $/tr for 5 filters ---- */
(function(){
  const f=D.filters;const box=document.getElementById('screen');const W=Math.max(box.clientWidth,320);
  const H=250,padL=40,padR=12,padT=16,padB=64,iw=W-padL-padR,ih=H-padT-padB;
  const vals=f.flatMap(x=>x.test),mx=Math.max(0,...vals),mn=Math.min(0,...vals);
  const rng=(mx-mn)||1,y=v=>padT+ih*(mx-v)/rng;
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img'});
  for(let g=0;g<=4;g++){const gv=mn+rng*g/4,gy=y(gv);
    svg.appendChild(el('line',{x1:padL,x2:W-padR,y1:gy,y2:gy,stroke:cs('--grid'),'stroke-width':1}));
    const t=el('text',{x:padL-6,y:gy+3,'text-anchor':'end',class:'tick'});t.textContent='$'+gv.toFixed(0);svg.appendChild(t);}
  svg.appendChild(el('line',{x1:padL,x2:W-padR,y1:y(0),y2:y(0),stroke:cs('--axis'),'stroke-width':1.4}));
  const gw=iw/f.length,bw=Math.min(15,gw*0.2);
  f.forEach((x,i)=>{
    const cx=padL+gw*i+gw/2;const bless=x.verdict==='BLESS';
    x.test.forEach((v,j)=>{
      const off=(j-1);const bx=cx+off*(bw+2)-bw/2;
      const yy=v>=0?y(v):y(0),hh=Math.abs(y(0)-y(v));
      // low tercile emphasized in accent if 'low' better, else high tercile
      const fav=(x.better==='low'&&j===0)||(x.better==='high'&&j===2);
      const col=bless?(fav?cs('--accent'):cs('--base')):(fav?cs('--bad'):cs('--base'));
      svg.appendChild(el('rect',{x:bx,y:yy,width:bw,height:Math.max(hh,0.5),rx:2.5,fill:col,
        opacity:fav?1:0.5}));
    });
    // label
    const nm=x.feat.replace('sb_','').replace('_',' ');
    const t=el('text',{x:cx,y:H-padB+16,'text-anchor':'middle',class:'tick'});t.textContent=nm;svg.appendChild(t);
    const bd=el('text',{x:cx,y:H-padB+30,'text-anchor':'middle',class:'blab'});
    bd.textContent=bless?'✓ BLESS':'✗ rej';bd.setAttribute('fill',bless?cs('--good'):cs('--bad'));
    svg.appendChild(bd);
  });
  box.appendChild(svg);
  // table
  const rows=f.map(x=>`<tr class="${x.verdict==='BLESS'?'row-hi':''}"><td>${x.feat}</td>
    <td style="text-align:left;font-family:var(--sans);white-space:normal">${x.desc}</td>
    <td>${x.better}</td>
    <td>${x.test.map(v=>(v>=0?'$':'−$')+Math.abs(v).toFixed(0)).join(' / ')}</td>
    <td><span class="badge ${x.verdict==='BLESS'?'b-bless':'b-rej'}">${x.verdict==='BLESS'?'BLESS':'reject'}</span></td></tr>`).join('');
  document.getElementById('screen-tbl').innerHTML=
    `<thead><tr><th>feature</th><th style="text-align:left">Wyckoff basis</th><th>expect</th><th>test $/tr &nbsp;T1/T2/T3</th><th>verdict</th></tr></thead><tbody>${rows}</tbody>`;
})();

/* ---- ST diagnostic (train vs test, 3 terciles) ---- */
(function(){
  const d=D.st_diag;
  const tr=d.filter(r=>r.split.startsWith('TRAIN')).map(r=>r['$/tr']);
  const te=d.filter(r=>r.split.startsWith('TEST')).map(r=>r['$/tr']);
  groupedBars('st-diag',['quiet','mid','loud'],tr,te,cs('--base'),cs('--accent'),
    v=>(v>=0?'$':'−$')+Math.abs(v).toFixed(0),220);
})();

/* ---- ST per year ---- */
(function(){
  const p=D.st_peryear;
  groupedBars('st-py',p.map(r=>r.year),p.map(r=>r.baseline_$tr),p.map(r=>r.st_scratch_$tr),
    cs('--base'),cs('--bad'),v=>(v>=0?'$':'−$')+Math.abs(v).toFixed(0),220);
})();

</script>
"""


GLOSSARY = r"""
<section>
  <div class="sec-head"><div class="sec-num">KEY</div>
    <div><h2>Reading this report</h2>
    <p class="sec-desc">Plain-language glossary of the terms used above.</p></div></div>
  <div class="tblwrap"><table>
  <thead><tr><th>term</th><th style="text-align:left">what it means</th></tr></thead>
  <tbody>
  <tr><td>climax bar</td><td style="text-align:left;font-family:var(--sans);white-space:normal">A bar with a surge of activity in the top ~5% for that time of day &mdash; a burst of buying or selling.</td></tr>
  <tr><td>climax-flip</td><td style="text-align:left;font-family:var(--sans);white-space:normal">The setup studied: two back-to-back climax bars pointing opposite ways &mdash; a &ldquo;trap&rdquo; push followed by a violent reversal. We trade the reversal.</td></tr>
  <tr><td>trap / reversal bar</td><td style="text-align:left;font-family:var(--sans);white-space:normal">First climax bar traps traders on the wrong side; the second (reversal) bar is where the entry is taken.</td></tr>
  <tr><td>$ / trade</td><td style="text-align:left;font-family:var(--sans);white-space:normal">Average profit per trade, one ES futures contract, before commissions.</td></tr>
  <tr><td>profit factor (PF)</td><td style="text-align:left;font-family:var(--sans);white-space:normal">Gross profit divided by gross loss. Above 1.0 is profitable; 1.2 means $1.20 won per $1 lost.</td></tr>
  <tr><td>max drawdown</td><td style="text-align:left;font-family:var(--sans);white-space:normal">The worst peak-to-trough drop in the running account balance &mdash; the pain you&rsquo;d have sat through.</td></tr>
  <tr><td>walk-forward</td><td style="text-align:left;font-family:var(--sans);white-space:normal">Choose all settings using only past data, then test on the next unseen year. The gold standard against curve-fitting.</td></tr>
  <tr><td>in / out of sample</td><td style="text-align:left;font-family:var(--sans);white-space:normal">In-sample (2021&ndash;22) = data used to choose rules. Out-of-sample (2023&ndash;26) = untouched data used only to judge them.</td></tr>
  <tr><td>IBS &middot; RR2</td><td style="text-align:left;font-family:var(--sans);white-space:normal">Baseline rules held fixed: a direction filter (where the bar closes in its range), and a profit target set at 2&times; the risk.</td></tr>
  <tr><td>SAR &middot; EB &middot; skip-H8</td><td style="text-align:left;font-family:var(--sans);white-space:normal">Optional rules in the settings grid: stop-and-reverse on an opposite signal; scratch on a weak next bar; skip 8&nbsp;a.m. entries. The grid lets the walk-forward pick freely among them.</td></tr>
  <tr><td>WYCK</td><td style="text-align:left;font-family:var(--sans);white-space:normal">The new Wyckoff filter tested here: skip a reversal that trades on more volume than the trap bar.</td></tr>
  </tbody></table></div>
</section>
"""


def main():
    share = "--share" in sys.argv
    data = json.loads(DATA.read_text(encoding="utf-8"))
    html = HTML.replace("__DATA__", json.dumps(data))
    out = OUTHTML
    if share:
        out = OUTSHARE
        html = html.replace("<!-- METHOD -->", GLOSSARY + "\n<!-- METHOD -->")
        html = html.replace(
            "engine&nbsp;&middot;&nbsp;tempo_engine_bars &middot; 2000&#8209;tick bars &middot; 2021&ndash;2026",
            "ES&nbsp;futures&nbsp;&middot;&nbsp;2000&#8209;tick bars &middot; 2021&ndash;2026")
        html = html.replace("the S119 walk-forward-stable", "our previously-validated best")
        html = html.replace(
            r"""scripts &middot; flip_wyckoff_effort.py &nbsp;/&nbsp; flip_wf_wyckoff.py &nbsp;/&nbsp;
    flip_wyckoff_st.py &nbsp;/&nbsp; flip_wyckoff_report_data.py &nbsp;&middot;&nbsp; branch leglab &middot;
    all outputs dated in tempo/outputs/""",
            "Fixed-rule backtest &middot; ES 2000-tick bars &middot; 2021&ndash;2026 &middot; "
            "settings chosen in-sample through 2022, judged out-of-sample 2023&ndash;26 &middot; "
            "fills modelled identically across every variant.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("wrote", out, f"({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
