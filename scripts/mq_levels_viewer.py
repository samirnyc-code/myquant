"""Local UI for the MenthorQ gamma-levels history (S75).

Reads data/menthorq/<TKR>_mq_levels_history.csv (from mq_levels_backfill.py) and
renders a self-contained dashboard:
  * Gamma-Level Ladder for a chosen session — every wall placed on a price axis,
    a diverging bar (blue = positive GEX / call side, red = negative / put side)
    sized by |GEX|, the 1D expected-move band shaded, spot marked.
  * 5-year time series of Call Resistance / Put Support / HVL vs SPX close, with
    range presets and a click-to-inspect cursor that drives the ladder.
  * Per-session data table + CSV download.

No external deps (offline/CSP safe): data is embedded, charts are hand-drawn SVG.

Run:
  .venv/Scripts/python.exe scripts/mq_levels_viewer.py [--ticker SPX] [--port 8610]
                                                       [--build-only] [--open]
"""
import argparse
import csv
import json
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "menthorq"

LEVELS = [  # (stem, label, group)
    ("cr", "Call Resistance", "key"), ("ps", "Put Support", "key"), ("hvl", "HVL", "key"),
    ("cr0", "Call Resistance 0DTE", "zero"), ("ps0", "Put Support 0DTE", "zero"),
    ("hvl0", "HVL 0DTE", "zero"), ("gw0", "Gamma Wall 0DTE", "zero"),
    *[(f"gex_{i}", f"GEX {i}", "wall") for i in range(1, 11)],
]


def load(tkr):
    f = DATA / f"{tkr}_mq_levels_history.csv"
    if not f.exists():
        raise SystemExit(f"missing {f} — run mq_levels_backfill.py first")
    rows = list(csv.DictReader(open(f, encoding="utf-8")))

    def num(v):
        try:
            return round(float(v), 4)
        except (TypeError, ValueError):
            return None

    out = []
    for r in rows:
        spot = num(r["spot_eod"])
        rec = {"d": r["session_date"], "eod": r["eod_date"],
               "spot": spot, "spot_i": num(r["spot_intraday"]),
               "d1_min": num(r["d1_min"]), "d1_max": num(r["d1_max"]), "L": {}}

        def plaus(v):  # null implausible values (MQ placeholder 100.0 glitch days)
            if v is None or spot is None:
                return v
            return v if 0.5 * spot <= v <= 1.5 * spot else None

        for stem, label, grp in LEVELS:
            val = plaus(num(r.get(stem)))
            gex = num(r.get(f"{stem}_gex")) if val is not None else None
            rec["L"][stem] = [val, gex]
        # null the band too if degenerate
        if rec["d1_min"] is not None and spot and not (0.5 * spot <= rec["d1_min"] <= 1.5 * spot):
            rec["d1_min"] = None
        if rec["d1_max"] is not None and spot and not (0.5 * spot <= rec["d1_max"] <= 1.5 * spot):
            rec["d1_max"] = None
        out.append(rec)
    return out


def build_html(tkr, rows):
    payload = json.dumps({"ticker": tkr, "rows": rows,
                          "levels": [[s, l, g] for s, l, g in LEVELS]},
                         separators=(",", ":"))
    return HTML_TMPL.replace("__PAYLOAD__", payload).replace("__TKR__", tkr)


# ---------------------------------------------------------------- HTML template
HTML_TMPL = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TKR__ Gamma Levels — MenthorQ history</title>
<style>
:root{
  --surface:#fcfcfb; --plane:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --pos:#2a78d6; --neg:#e34948; --hvl:#4a3aa7; --mid:#f0efec;
  --good:#0ca30c; --card:#ffffff;
}
@media (prefers-color-scheme:dark){:root{
  --surface:#1a1a19; --plane:#0d0d0d; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --pos:#3987e5; --neg:#e66767; --hvl:#9085e9; --mid:#383835; --card:#1f1f1e;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
header{padding:14px 20px;border-bottom:1px solid var(--border);display:flex;
  align-items:baseline;gap:16px;flex-wrap:wrap;background:var(--surface)}
h1{font-size:17px;margin:0;font-weight:650}
.sub{color:var(--ink2);font-size:12.5px}
.wrap{max-width:1360px;margin:0 auto;padding:18px 20px 60px}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:6px 0 16px}
button,select,input{font:inherit;color:var(--ink);background:var(--card);
  border:1px solid var(--border);border-radius:8px;padding:6px 10px;cursor:pointer}
button:hover{border-color:var(--axis)}
button.on{background:var(--pos);color:#fff;border-color:var(--pos)}
.grid{display:grid;grid-template-columns:minmax(420px,1fr) minmax(520px,1.35fr);gap:18px}
@media (max-width:1050px){.grid{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.card h2{font-size:13px;margin:0 0 4px;font-weight:600;letter-spacing:.02em;text-transform:uppercase;color:var(--ink2)}
.kpis{display:flex;gap:22px;flex-wrap:wrap;margin:2px 0 10px}
.kpi .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.kpi .v{font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}
svg{display:block;width:100%;overflow:visible}
text{fill:var(--ink2)}
.tick{fill:var(--muted);font-size:10.5px}
.lvl-label{fill:var(--ink);font-size:11px}
.leg{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--ink2);margin-top:6px}
.leg i{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:12.5px}
th,td{text-align:right;padding:3px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--surface)}
.tbl-wrap{max-height:340px;overflow:auto}
.pos{color:var(--pos)}.neg{color:var(--neg)}
a.dl{color:var(--pos);text-decoration:none;font-size:12.5px}
#tt{position:fixed;pointer-events:none;background:var(--card);border:1px solid var(--border);
  border-radius:8px;padding:6px 9px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.14);opacity:0;transition:opacity .08s}
</style></head>
<body>
<header>
  <h1>__TKR__ · MenthorQ Gamma Levels</h1>
  <span class="sub" id="hdr-range"></span>
  <span class="sub" style="margin-left:auto" id="hdr-count"></span>
</header>
<div class="wrap">
  <div class="bar">
    <button id="prev">◀ Prev</button>
    <input type="date" id="datepick">
    <button id="next">Next ▶</button>
    <button id="latest">Latest</button>
    <span style="flex:1"></span>
    <a class="dl" id="csvlink" href="/__TKR___mq_levels_history.csv" download>⬇ download full CSV</a>
  </div>

  <div class="kpis" id="kpis"></div>

  <div class="grid">
    <div class="card">
      <h2>Gamma-Level Ladder <span id="ladder-date" style="color:var(--muted);text-transform:none;font-weight:400"></span></h2>
      <div id="ladder"></div>
      <div class="leg">
        <span><i style="background:var(--pos)"></i>Positive GEX (call side)</span>
        <span><i style="background:var(--neg)"></i>Negative GEX (put side)</span>
        <span><i style="background:var(--hvl);opacity:.3"></i>1D expected-move band</span>
        <span>— — spot</span>
      </div>
    </div>
    <div class="card">
      <h2>History — walls vs price</h2>
      <div class="bar" style="margin:0 0 6px">
        <span id="ranges"></span>
      </div>
      <div id="ts"></div>
      <div class="leg" id="ts-leg"></div>
    </div>
  </div>

  <div class="card" style="margin-top:18px">
    <h2>Levels — <span id="tbl-date" style="color:var(--muted);text-transform:none;font-weight:400"></span></h2>
    <div class="tbl-wrap"><table id="tbl"></table></div>
  </div>
</div>
<div id="tt"></div>
<script>
const DB = __PAYLOAD__;
const ROWS = DB.rows, LV = DB.levels;
const byd = Object.fromEntries(ROWS.map((r,i)=>[r.d,i]));
let cur = ROWS.length-1;   // selected index
let range = 'All';
const css = k=>getComputedStyle(document.documentElement).getPropertyValue(k).trim();
const fmt = (v,d=2)=> v==null?'—':v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtG = v=> v==null?'—':(v>=0?'+':'')+Math.round(v).toLocaleString('en-US');
const tt = document.getElementById('tt');
function showTT(html,x,y){tt.innerHTML=html;tt.style.opacity=1;tt.style.left=(x+14)+'px';tt.style.top=(y+14)+'px';}
function hideTT(){tt.style.opacity=0;}

document.getElementById('hdr-range').textContent = ROWS[0].d+'  →  '+ROWS[ROWS.length-1].d;
document.getElementById('hdr-count').textContent = ROWS.length.toLocaleString()+' sessions';

// ---------- Ladder ----------
const SHORT={cr:'CR',ps:'PS',hvl:'HVL',cr0:'CR0',ps0:'PS0',hvl0:'HVL0',gw0:'GW0',
  gex_1:'G1',gex_2:'G2',gex_3:'G3',gex_4:'G4',gex_5:'G5',gex_6:'G6',gex_7:'G7',gex_8:'G8',gex_9:'G9',gex_10:'G10'};
const FULL=Object.fromEntries(LV.map(([s,l])=>[s,l]));
function drawLadder(){
  const r = ROWS[cur];
  document.getElementById('ladder-date').textContent = '· '+r.d+'  (EOD '+r.eod+')';
  const W=560, H=560, padL=8, padR=8, padT=16, padB=20, cx=W*0.42;
  // collect priced levels, then GROUP by identical price so coincident walls share one row
  const raw = LV.map(([s,l,g])=>({s,l,v:r.L[s][0],gex:r.L[s][1]})).filter(x=>x.v!=null);
  const groups={};
  for(const it of raw){const k=it.v.toFixed(2);(groups[k]=groups[k]||{v:it.v,codes:[],names:[],gex:0}).codes.push(SHORT[it.s]);
    groups[k].names.push(FULL[it.s]); if(Math.abs(it.gex||0)>Math.abs(groups[k].gex))groups[k].gex=it.gex;}
  const items=Object.values(groups).sort((a,b)=>b.v-a.v);
  const prices=[...items.map(x=>x.v), r.spot, r.d1_min, r.d1_max].filter(v=>v!=null);
  let lo=Math.min(...prices), hi=Math.max(...prices); const pad=(hi-lo)*0.06||10; lo-=pad; hi+=pad;
  const y = v=> padT + (H-padT-padB) * (hi-v)/(hi-lo);
  const maxG = Math.max(...items.map(x=>Math.abs(x.gex||0)),1);
  const barMax = Math.min(cx-padL-14, W-cx-padR-150);
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img">`;
  // 1D band
  if(r.d1_min!=null&&r.d1_max!=null){
    svg+=`<rect x="${padL}" y="${y(r.d1_max)}" width="${W-padL-padR}" height="${y(r.d1_min)-y(r.d1_max)}"
      fill="${css('--hvl')}" opacity="0.10"/>`;
    svg+=`<text class="tick" x="${W-padR}" y="${y(r.d1_max)-3}" text-anchor="end">1D Max ${fmt(r.d1_max)}</text>`;
    svg+=`<text class="tick" x="${W-padR}" y="${y(r.d1_min)+11}" text-anchor="end">1D Min ${fmt(r.d1_min)}</text>`;
  }
  svg+=`<line x1="${cx}" y1="${padT}" x2="${cx}" y2="${H-padB}" stroke="${css('--axis')}"/>`;
  // de-collide label y positions (labels sit to the RIGHT of the axis, stacked)
  const GAP=14; let lastY=-1e9;
  const laid=items.map(it=>{const by=y(it.v); let ly=Math.max(by,lastY+GAP); lastY=ly; return {it,by,ly};});
  for(const {it,by,ly} of laid){
    const pos=(it.gex||0)>=0, col=pos?css('--pos'):css('--neg');
    const w=Math.abs(it.gex||0)/maxG*barMax;
    const x0 = pos?cx:cx-w;
    svg+=`<rect x="${x0}" y="${by-4}" width="${Math.max(w,0.6)}" height="8" rx="3" fill="${col}"
      data-n="${it.names.join(' / ')}" data-v="${it.v}" data-g="${it.gex==null?'':Math.round(it.gex)}" class="gbar" style="cursor:pointer"/>`;
    // connector from bar to (possibly shifted) label
    const lx=W-padR-142;
    if(Math.abs(ly-by)>1.5) svg+=`<line x1="${cx}" y1="${by}" x2="${lx-4}" y2="${ly}" stroke="${css('--grid')}" stroke-width="1"/>`;
    svg+=`<text class="lvl-label" x="${lx}" y="${ly+3.5}"><tspan style="font-weight:600">${it.codes.join('/')}</tspan> · ${fmt(it.v,0)} · <tspan fill="${col}">${fmtG(it.gex)}</tspan></text>`;
  }
  // spot
  if(r.spot!=null){
    const ys=y(r.spot);
    svg+=`<line x1="${padL}" y1="${ys}" x2="${W-padR}" y2="${ys}" stroke="${css('--ink')}" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    svg+=`<text x="${padL}" y="${ys-4}" style="fill:var(--ink);font-size:11px;font-weight:700">spot ${fmt(r.spot)}</text>`;
  }
  svg+=`</svg>`;
  const el=document.getElementById('ladder'); el.innerHTML=svg;
  el.querySelectorAll('.gbar').forEach(b=>{
    b.addEventListener('mousemove',e=>showTT(`<b>${b.dataset.n}</b><br>price ${b.dataset.v}<br>GEX ${b.dataset.g?Number(b.dataset.g).toLocaleString():'—'}`,e.clientX,e.clientY));
    b.addEventListener('mouseleave',hideTT);
  });
}

// ---------- Time series ----------
const RANGES={'1M':21,'3M':63,'6M':126,'1Y':252,'All':1e9};
function drawTS(){
  const n=Math.min(RANGES[range],ROWS.length);
  const data=ROWS.slice(ROWS.length-n);
  const W=720,H=430,padL=52,padR=54,padT=12,padB=26;
  const series=[['spot','SPX close',css('--ink'),2],['cr','Call Resistance',css('--pos'),1.6],
                ['ps','Put Support',css('--neg'),1.6],['hvl','HVL',css('--hvl'),1.6]];
  const val=(r,k)=> k==='spot'?r.spot:r.L[k][0];
  let lo=Infinity,hi=-Infinity;
  data.forEach(r=>series.forEach(([k])=>{const v=val(r,k); if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v);}}));
  const pad=(hi-lo)*0.05; lo-=pad;hi+=pad;
  const x=i=> padL+(W-padL-padR)*(i/(data.length-1||1));
  const y=v=> padT+(H-padT-padB)*(hi-v)/(hi-lo);
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" id="tssvg">`;
  // gridlines + y ticks
  for(let g=0;g<=4;g++){const v=lo+(hi-lo)*g/4, yy=y(v);
    svg+=`<line x1="${padL}" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="${css('--grid')}"/>`;
    svg+=`<text class="tick" x="${padL-6}" y="${yy+3}" text-anchor="end">${fmt(v,0)}</text>`;}
  // x ticks (5)
  for(let g=0;g<=4;g++){const i=Math.round((data.length-1)*g/4);
    svg+=`<text class="tick" x="${x(i)}" y="${H-8}" text-anchor="middle">${data[i].d}</text>`}
  // lines
  for(const [k,lab,col,sw] of series){
    let dstr='',started=false;
    data.forEach((r,i)=>{const v=val(r,k); if(v==null){return;} dstr+=(started?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)+' ';started=true;});
    svg+=`<path d="${dstr}" fill="none" stroke="${col}" stroke-width="${sw}"/>`;
    // direct label at end
    const last=[...data].reverse().find(r=>val(r,k)!=null);
    if(last){const li=data.indexOf(last);
      svg+=`<text x="${W-padR+4}" y="${y(val(last,k))+3}" style="fill:${col};font-size:10.5px;font-weight:600">${fmt(val(last,k),0)}</text>`;}
  }
  // cursor for selected date if in range
  const selI=data.findIndex(r=>r.d===ROWS[cur].d);
  if(selI>=0){svg+=`<line x1="${x(selI)}" y1="${padT}" x2="${x(selI)}" y2="${H-padB}" stroke="${css('--axis')}" stroke-dasharray="3 3"/>`;}
  // hover hit layer
  svg+=`<rect x="${padL}" y="${padT}" width="${W-padL-padR}" height="${H-padT-padB}" fill="transparent" id="tshit" style="cursor:crosshair"/>`;
  svg+=`</svg>`;
  const el=document.getElementById('ts'); el.innerHTML=svg;
  document.getElementById('ts-leg').innerHTML=series.map(([k,l,c])=>`<span><i style="background:${c}"></i>${l}</span>`).join('');
  const hit=document.getElementById('tshit');
  function pick(e){const svgEl=document.getElementById('tssvg');const pt=svgEl.getBoundingClientRect();
    const rel=(e.clientX-pt.left)/pt.width*W; let i=Math.round((rel-padL)/(W-padL-padR)*(data.length-1));
    i=Math.max(0,Math.min(data.length-1,i)); return i;}
  hit.addEventListener('mousemove',e=>{const i=pick(e);const r=data[i];
    showTT(`<b>${r.d}</b><br>spot ${fmt(r.spot,0)} · CR ${fmt(r.L.cr[0],0)} · PS ${fmt(r.L.ps[0],0)} · HVL ${fmt(r.L.hvl[0],0)}`,e.clientX,e.clientY);});
  hit.addEventListener('mouseleave',hideTT);
  hit.addEventListener('click',e=>{const i=pick(e); cur=byd[data[i].d]; render();});
}

// ---------- KPIs + table ----------
function drawKPIs(){
  const r=ROWS[cur];
  const items=[['SPX close',fmt(r.spot)],['Call Resistance',fmt(r.L.cr[0],0)],
    ['Put Support',fmt(r.L.ps[0],0)],['HVL',fmt(r.L.hvl[0],0)],
    ['Gamma Wall 0DTE',fmt(r.L.gw0[0],0)],['1D range',fmt(r.d1_min,0)+' – '+fmt(r.d1_max,0)]];
  document.getElementById('kpis').innerHTML=items.map(([l,v])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');
}
function drawTable(){
  const r=ROWS[cur];
  document.getElementById('tbl-date').textContent='· '+r.d;
  let h='<tr><th>Level</th><th>Price</th><th>Signed GEX ($)</th><th>Δ vs spot</th></tr>';
  for(const [s,l] of LV){const v=r.L[s][0],g=r.L[s][1]; if(v==null)continue;
    const d=r.spot!=null?(v-r.spot):null;
    h+=`<tr><td>${l}</td><td>${fmt(v,0)}</td><td class="${g==null?'':g>=0?'pos':'neg'}">${fmtG(g)}</td><td>${d==null?'—':(d>=0?'+':'')+fmt(d,0)}</td></tr>`;}
  document.getElementById('tbl').innerHTML=h;
}

function render(){drawKPIs();drawLadder();drawTS();drawTable();
  document.getElementById('datepick').value=ROWS[cur].d;}

// controls
document.getElementById('prev').onclick=()=>{if(cur>0){cur--;render();}};
document.getElementById('next').onclick=()=>{if(cur<ROWS.length-1){cur++;render();}};
document.getElementById('latest').onclick=()=>{cur=ROWS.length-1;render();};
document.getElementById('datepick').onchange=e=>{const v=e.target.value;
  if(byd[v]!=null){cur=byd[v];render();} else {// nearest
    const ds=ROWS.map(r=>r.d); let best=0,bd=1e9;
    ds.forEach((d,i)=>{const diff=Math.abs(new Date(d)-new Date(v)); if(diff<bd){bd=diff;best=i;}});
    cur=best;render();}};
document.getElementById('datepick').min=ROWS[0].d; document.getElementById('datepick').max=ROWS[ROWS.length-1].d;
document.getElementById('ranges').innerHTML=Object.keys(RANGES).map(k=>`<button data-r="${k}" class="rbtn ${k===range?'on':''}">${k}</button>`).join(' ');
document.querySelectorAll('.rbtn').forEach(b=>b.onclick=()=>{range=b.dataset.r;
  document.querySelectorAll('.rbtn').forEach(x=>x.classList.toggle('on',x.dataset.r===range));drawTS();});
window.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')document.getElementById('prev').click();
  if(e.key==='ArrowRight')document.getElementById('next').click();});
render();
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *a, html=b"", tkr="SPX", **k):
        self.html = html
        self.tkr = tkr
        super().__init__(*a, **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/") and self.path.endswith(".csv"):
            f = DATA / self.path.lstrip("/")
            if f.exists():
                b = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{f.name}"')
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.html)))
        self.end_headers()
        self.wfile.write(self.html)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="SPX")
    ap.add_argument("--port", type=int, default=8610)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    rows = load(args.ticker)
    html = build_html(args.ticker, rows)
    out = DATA / f"{args.ticker}_levels_viewer.html"
    out.write_text(html, encoding="utf-8")
    print(f"built {out}  ({len(rows)} sessions, {rows[0]['d']}..{rows[-1]['d']})")
    if args.build_only:
        return
    url = f"http://{args.host}:{args.port}/"
    srv = ThreadingHTTPServer((args.host, args.port),
                              partial(Handler, html=html.encode("utf-8"), tkr=args.ticker))
    print(f"serving {args.ticker} gamma-levels UI at {url}  (Ctrl-C to stop)")
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
