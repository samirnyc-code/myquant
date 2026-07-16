"""MenthorQ Gamma Levels — Command Center (S75).

One local hub for the whole levels database:
  * Freshness / status for all tickers (rows, range, last EOD, staleness).
  * "Update now" button -> runs the incremental backfill (mq_levels_backfill_batch --recent).
  * Ticker switcher -> the gamma-level ladder + 5-yr history + table for any ticker,
    fetched on demand from /data/<TKR>.json (so all 13 live on one page).
  * Per-ticker CSV download.

Reads data/menthorq/<TKR>_mq_levels_history.csv (from mq_levels_backfill_batch.py).
No external deps; charts are hand-drawn SVG.

Run:
  .venv/Scripts/python.exe scripts/mq_levels_command_center.py [--port 8610] [--open]
"""
import argparse
import csv
import datetime as dt
import glob
import json
import os
import subprocess
import sys
import threading
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "menthorq"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
PULLER = ROOT / "scripts" / "mq_levels_backfill_batch.py"

LEVELS = [("cr", "Call Resistance"), ("ps", "Put Support"), ("hvl", "HVL"),
          ("cr0", "Call Resistance 0DTE"), ("ps0", "Put Support 0DTE"),
          ("hvl0", "HVL 0DTE"), ("gw0", "Gamma Wall 0DTE"),
          *[(f"gex_{i}", f"GEX {i}") for i in range(1, 11)]]
GROUPS = {"Index": ["SPX"],
          "Mag 7": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"],
          "Futures": ["ES1!", "NQ1!", "RTY1!", "CL1!", "GC1!"]}

_update_lock = threading.Lock()
_update_state = {"running": False, "log": "", "at": None}
_mq = None
_candle_cache = {}
ET = None


def files():
    return {os.path.basename(f).replace("_mq_levels_history.csv", ""): f
            for f in glob.glob(str(DATA / "*_mq_levels_history.csv"))}


def num(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def ticker_rows(tkr):
    f = DATA / f"{tkr}_mq_levels_history.csv"
    if not f.exists():
        return []
    out = []
    for r in csv.DictReader(open(f, encoding="utf-8")):
        rec = {"d": r["session_date"], "spot": num(r["spot_eod"]),
               "d1_min": num(r["d1_min"]), "d1_max": num(r["d1_max"]), "L": {}}
        for stem, _ in LEVELS:
            rec["L"][stem] = [num(r.get(stem)), num(r.get(f"{stem}_gex"))]
        out.append(rec)
    return out


def status():
    fs = files()
    marker = {}
    mf = DATA / "levels_db_status.json"
    if mf.exists():
        try:
            marker = json.loads(mf.read_text())
        except Exception:
            marker = {}
    today = dt.date.today()
    rows = []
    for grp, tks in GROUPS.items():
        for t in tks:
            f = fs.get(t)
            if not f:
                rows.append({"ticker": t, "group": grp, "n": 0, "first": None,
                             "last": None, "stale": None, "spot": False})
                continue
            data = list(csv.DictReader(open(f, encoding="utf-8")))
            last = data[-1]["session_date"] if data else None
            first = data[0]["session_date"] if data else None
            stale = None
            if last:
                stale = (today - dt.date.fromisoformat(last)).days
            has_spot = bool(data and data[-1]["spot_eod"])
            rows.append({"ticker": t, "group": grp, "n": len(data), "first": first,
                         "last": last, "stale": stale, "spot": has_spot})
    return {"tickers": rows, "marker": marker,
            "update": {"running": _update_state["running"], "at": _update_state["at"]},
            "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def run_update():
    with _update_lock:
        if _update_state["running"]:
            return
        _update_state["running"] = True
        _update_state["log"] = ""
    try:
        p = subprocess.run([str(PY), str(PULLER), "--recent", "10"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        _update_state["log"] = (p.stdout or "")[-4000:] + (p.stderr or "")[-1000:]
    except Exception as e:
        _update_state["log"] = f"update failed: {e}"
    finally:
        _update_state["running"] = False
        _update_state["at"] = dt.datetime.now().strftime("%H:%M:%S")


def get_candles(ticker, date):
    """Intraday 5m OHLC for one session (from the MQ candles endpoint), that ET date only."""
    key = (ticker, date)
    if key in _candle_cache:
        return _candle_cache[key]
    global _mq, ET
    if ET is None:
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
    if _mq is None:
        from mq_api import MQ
        _mq = MQ()
    d = dt.date.fromisoformat(date)
    end = dt.datetime(d.year, d.month, d.day, 23, 0, tzinfo=ET)
    to = int(end.astimezone(dt.timezone.utc).timestamp() * 1000)
    try:
        js = _mq.get(f"tickers/{ticker}/candles", interval="5m",
                     **{"from": to - 4 * 86400000, "to": to, "countBack": 200})
    except Exception:
        return []
    bars = []
    for b in (js if isinstance(js, list) else []):
        t = dt.datetime.fromtimestamp(b["t"] / 1000, ET)
        if t.date().isoformat() == date:
            bars.append({"hm": t.strftime("%H:%M"), "o": b["o"], "h": b["h"],
                         "l": b["l"], "c": b["c"]})
    _candle_cache[key] = bars
    return bars


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self._send(HTML, "text/html; charset=utf-8")
        if path == "/status.json":
            return self._send(json.dumps(status()))
        if path == "/update_log":
            return self._send(json.dumps({"running": _update_state["running"],
                                          "log": _update_state["log"], "at": _update_state["at"]}))
        if path.startswith("/data/"):
            t = path[len("/data/"):]
            return self._send(json.dumps({"ticker": t, "rows": ticker_rows(t),
                                          "levels": [[s, l] for s, l in LEVELS]}))
        if path == "/candles":
            from urllib.parse import parse_qs, unquote
            q = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            t = unquote(q.get("ticker", [""])[0])
            date = q.get("date", [""])[0]
            return self._send(json.dumps(get_candles(t, date) if t and date else []))
        if path.endswith(".csv"):
            f = DATA / path.lstrip("/")
            if f.exists():
                return self._send(f.read_bytes(), "text/csv",
                                  {"Content-Disposition": f'attachment; filename="{f.name}"'})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/update":
            threading.Thread(target=run_update, daemon=True).start()
            return self._send(json.dumps({"started": True}))
        self.send_response(404)
        self.end_headers()


# --------------------------------------------------------------------- HTML
HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gamma Levels · Command Center</title>
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--pos:#2a78d6;--neg:#e34948;
  --hvl:#4a3aa7;--good:#0ca30c;--warn:#fab219;--card:#fff}
@media(prefers-color-scheme:dark){:root{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
  --muted:#898781;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--pos:#3987e5;
  --neg:#e66767;--hvl:#9085e9;--card:#1f1f1e}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
header{padding:13px 20px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:650}
.wrap{max-width:1380px;margin:0 auto;padding:16px 20px 60px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;margin-bottom:16px}
.card h2{font-size:12px;margin:0 0 10px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--ink2)}
button,select,input{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--border);border-radius:8px;padding:6px 11px;cursor:pointer}
button:hover{border-color:var(--axis)}
button.primary{background:var(--pos);color:#fff;border-color:var(--pos)}
button.on{background:var(--pos);color:#fff;border-color:var(--pos)}
.status-row{display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px;vertical-align:1px}
.grid-tk{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:8px}
.tk{border:1px solid var(--border);border-radius:9px;padding:8px 10px;cursor:pointer;background:var(--card)}
.tk:hover{border-color:var(--pos)}
.tk.sel{border-color:var(--pos);box-shadow:0 0 0 1px var(--pos) inset}
.tk .t{font-weight:650;font-size:14px}
.tk .m{font-size:11px;color:var(--muted);margin-top:2px;font-variant-numeric:tabular-nums}
.glabel{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;margin:6px 0 3px}
.kpis{display:flex;gap:22px;flex-wrap:wrap;margin:2px 0 8px}
.kpi .l{font-size:11px;color:var(--muted);text-transform:uppercase}
.kpi .v{font-size:19px;font-weight:650;font-variant-numeric:tabular-nums}
.two{display:grid;grid-template-columns:minmax(420px,1fr) minmax(520px,1.35fr);gap:16px}
@media(max-width:1050px){.two{grid-template-columns:1fr}}
svg{display:block;width:100%;overflow:visible}
text{fill:var(--ink2)}.tick{fill:var(--muted);font-size:10.5px}.lvl-label{fill:var(--ink);font-size:11px}
.leg{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--ink2);margin-top:6px}
.leg i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:12.5px}
th,td{text-align:right;padding:3px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--surface)}
.tbl-wrap{max-height:320px;overflow:auto}.pos{color:var(--pos)}.neg{color:var(--neg)}
.spot-row td{border-top:2px solid var(--axis);border-bottom:2px solid var(--axis)}
.spot-pos td{color:var(--good);background:rgba(12,163,12,.08)}
.spot-neg td{color:var(--neg);background:rgba(227,73,72,.09)}
a.dl{color:var(--pos);text-decoration:none;font-size:12.5px}
#tt{position:fixed;pointer-events:none;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:6px 9px;font-size:12px;box-shadow:0 4px 14px rgba(0,0,0,.14);opacity:0;transition:opacity .08s}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--border);border-top-color:var(--pos);border-radius:50%;animation:s .7s linear infinite;vertical-align:-2px}
@keyframes s{to{transform:rotate(360deg)}}
.muted{color:var(--muted)}
.zbtn{padding:3px 9px;font-size:13px;line-height:1}
</style></head><body>
<header><h1>⬡ Gamma Levels · Command Center</h1>
  <span class="muted" id="hdr-src">MenthorQ EOD levels database</span>
  <span class="muted" style="margin-left:auto" id="hdr-gen"></span></header>
<div class="wrap">

  <div class="card">
    <h2>Data status</h2>
    <div class="status-row">
      <div><span class="dot" id="freshdot"></span><b id="freshtxt">…</b></div>
      <div class="muted" id="lastupd"></div>
      <div style="margin-left:auto"></div>
      <button class="primary" id="btn-update">↻ Update now</button>
      <span id="upd-status" class="muted"></span>
    </div>
    <div id="tickergrid" style="margin-top:12px"></div>
  </div>

  <div class="card" id="viewer" style="display:none">
    <div class="status-row" style="margin-bottom:8px">
      <h2 style="margin:0" id="v-title"></h2>
      <span style="flex:1"></span>
      <button id="prev">◀</button>
      <input type="date" id="datepick">
      <button id="next">▶</button>
      <button id="latest">Latest</button>
      <a class="dl" id="csvlink" href="#" download>⬇ CSV</a>
    </div>
    <div class="kpis" id="kpis"></div>
    <div class="glabel"><span id="ts-title">Price action + levels</span> &nbsp;
      <button id="yin" class="zbtn" title="compress axis (zoom in)">＋</button><button id="yout" class="zbtn" title="expand axis (zoom out)">－</button><button id="yfit" class="zbtn" title="fit to price">fit</button>
      <span class="muted" style="text-transform:none">· scroll to zoom · drag to pan</span>
      <span id="path-note" class="muted" style="text-transform:none"></span></div>
    <div id="ts"></div><div class="leg" id="ts-leg"></div>
    <div class="glabel" style="margin-top:12px">Levels <span id="tbl-date"></span></div>
    <div class="tbl-wrap"><table id="tbl"></table></div>
  </div>
</div>
<div id="tt"></div>
<script>
const css=k=>getComputedStyle(document.documentElement).getPropertyValue(k).trim();
const fmt=(v,d=2)=>v==null?'—':v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtG=v=>v==null?'—':(v>=0?'+':'')+Math.round(v).toLocaleString('en-US');
const tt=document.getElementById('tt');
function showTT(h,x,y){tt.innerHTML=h;tt.style.opacity=1;tt.style.left=(x+14)+'px';tt.style.top=(y+14)+'px';}
function hideTT(){tt.style.opacity=0;}
const SHORT={cr:'CR',ps:'PS',hvl:'HVL',cr0:'CR0',ps0:'PS0',hvl0:'HVL0',gw0:'GW0',
 gex_1:'G1',gex_2:'G2',gex_3:'G3',gex_4:'G4',gex_5:'G5',gex_6:'G6',gex_7:'G7',gex_8:'G8',gex_9:'G9',gex_10:'G10'};

let ST=null, TKR=null, DBROWS=[], LV=[], byd={}, cur=0, range='All', FULL={};

async function loadStatus(){
  ST=await (await fetch('/status.json')).json();
  document.getElementById('hdr-gen').textContent='refreshed '+ST.generated;
  // freshness = worst non-futures staleness (futures lag structurally)
  const tks=ST.tickers, maxStale=Math.max(...tks.filter(t=>t.n).map(t=>t.stale??0),0);
  const dot=document.getElementById('freshdot'), ft=document.getElementById('freshtxt');
  let col=css('--good'),txt='Up to date';
  if(maxStale>=5){col=css('--warn');txt='Stale — needs update';}
  if(tks.some(t=>!t.n)){col=css('--warn');txt='Some tickers missing';}
  dot.style.background=col; ft.textContent=txt+' · '+tks.filter(t=>t.n).length+'/'+tks.length+' tickers';
  const m=ST.marker||{};
  document.getElementById('lastupd').textContent=m.finished_utc?('last pull '+m.finished_utc+' ('+(m.mode||'')+', '+(m.requests||0)+' req)'):'no pull marker yet';
  // ticker grid grouped
  const groups={};tks.forEach(t=>{(groups[t.group]=groups[t.group]||[]).push(t);});
  let h='';
  for(const g of Object.keys(groups)){
    h+=`<div class="glabel">${g}</div><div class="grid-tk">`;
    for(const t of groups[g]){
      const stale=t.stale==null?'—':(t.stale+'d');
      const badge=t.n? `${t.n} · ${t.first?.slice(2)}→${t.last?.slice(2)}` : 'no data';
      h+=`<div class="tk ${t.ticker===TKR?'sel':''}" data-t="${t.ticker}">
        <div class="t">${t.ticker}${t.spot?'':' <span class="muted" style="font-size:10px">·no spot</span>'}</div>
        <div class="m">${badge}</div>
        <div class="m">last ${t.last||'—'} · ${stale} old</div></div>`;
    }
    h+='</div>';
  }
  document.getElementById('tickergrid').innerHTML=h;
  document.querySelectorAll('.tk').forEach(el=>el.onclick=()=>selectTicker(el.dataset.t));
}

async function selectTicker(t){
  if(!t) return;
  TKR=t;
  document.querySelectorAll('.tk').forEach(el=>el.classList.toggle('sel',el.dataset.t===t));
  const j=await (await fetch('/data/'+encodeURIComponent(t))).json();
  DBROWS=j.rows; LV=j.levels; FULL=Object.fromEntries(LV);
  if(!DBROWS.length){document.getElementById('viewer').style.display='none';return;}
  byd=Object.fromEntries(DBROWS.map((r,i)=>[r.d,i]));
  cur=DBROWS.length-1;
  document.getElementById('viewer').style.display='';
  document.getElementById('v-title').textContent=t+' — '+DBROWS.length+' sessions ('+DBROWS[0].d+' → '+DBROWS[DBROWS.length-1].d+')';
  document.getElementById('csvlink').href='/'+encodeURIComponent(t)+'_mq_levels_history.csv';
  document.getElementById('datepick').min=DBROWS[0].d;document.getElementById('datepick').max=DBROWS[DBROWS.length-1].d;
  await goDay();
  document.getElementById('viewer').scrollIntoView({behavior:'smooth',block:'nearest'});
}
let PATH=[], pathToken=0;
async function goDay(){
  const r=DBROWS[cur], mytok=++pathToken;
  PATH=[]; yC=null; yH=null;                    // clear stale path + refit axis to new day
  document.getElementById('path-note').textContent='loading price path…';
  render();                                   // draw levels immediately
  try{PATH=await (await fetch('/candles?ticker='+encodeURIComponent(TKR)+'&date='+r.d)).json();}
  catch(e){PATH=[];}
  if(mytok!==pathToken)return;                 // a newer day was selected; drop stale path
  document.getElementById('path-note').textContent=PATH.length?('· '+PATH.length+' 5m bars'):'· no intraday path for this day';
  render();
}

// ---- single-day levels + price path (PA-first, zoomable y-axis) ----
function tcol(stem){if(stem.indexOf('gex_')===0)return css('--muted');
  if(stem[0]==='c')return css('--pos');if(stem[0]==='p')return css('--neg');return css('--hvl');}
let yC=null,yH=null,GEO=null,_zoomInit=false,_drag=null;
function paRange(){
  const r=DBROWS[cur];
  if(PATH.length){let lo=1e18,hi=-1e18;PATH.forEach(b=>{lo=Math.min(lo,b.l);hi=Math.max(hi,b.h);});return [lo,hi];}
  if(r.spot!=null)return [r.spot*0.996,r.spot*1.004];
  const h=r.L.hvl[0]||r.L.cr[0]||100;return [h*0.99,h*1.01];
}
function drawDay(){
  const r=DBROWS[cur];
  document.getElementById('ts-title').textContent='Price action + levels · '+r.d;
  const W=1180,H=470,padL=56,padR=132,padT=14,padB=26;
  const [paLo,paHi]=paRange();
  if(yC===null){yC=(paLo+paHi)/2;yH=Math.max((paHi-paLo)/2*1.18,(paHi||1)*0.0006);}   // fit to PA
  const lo=yC-yH,hi=yC+yH;
  GEO={lo,hi,padT,padB,H};
  const y=v=>padT+(H-padT-padB)*(hi-v)/(hi-lo);
  const inView=v=>v>=lo&&v<=hi;
  const n=PATH.length, xi=i=>padL+(W-padL-padR)*((i+0.5)/(n||1));
  let svg=`<svg viewBox="0 0 ${W} ${H}" id="tssvg" style="cursor:ns-resize">`;
  for(let g=0;g<=5;g++){const v=lo+(hi-lo)*g/5,yy=y(v);svg+=`<line x1="${padL}" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="${css('--grid')}"/><text class="tick" x="${padL-6}" y="${yy+3}" text-anchor="end">${fmt(v,0)}</text>`;}
  if(n){for(let g=0;g<=5;g++){const i=Math.min(n-1,Math.round((n-1)*g/5));svg+=`<text class="tick" x="${xi(i)}" y="${H-8}" text-anchor="middle">${PATH[i].hm}</text>`;}}
  else svg+=`<text class="tick" x="${(padL+W-padR)/2}" y="${H-8}" text-anchor="middle">no intraday path for this session</text>`;
  // 1D band (clipped to view)
  if(r.d1_min!=null&&r.d1_max!=null&&r.d1_max>=lo&&r.d1_min<=hi){
    const yt=y(Math.min(hi,r.d1_max)),yb=y(Math.max(lo,r.d1_min));
    svg+=`<rect x="${padL}" y="${yt}" width="${W-padR-padL}" height="${yb-yt}" fill="${css('--hvl')}" opacity="0.07"/>`;}
  // levels IN VIEW only — merge coincident, de-collide labels, colour by type, NO gex $
  const raw=LV.map(([s,l])=>({s,l,v:r.L[s][0]})).filter(x=>x.v!=null&&inView(x.v));
  const groups={};
  for(const it of raw){const k=it.v.toFixed(2);const g=(groups[k]=groups[k]||{v:it.v,codes:[],stem:it.s,key:false});
    g.codes.push(SHORT[it.s]);if(['CR','PS','HVL','GW0','CR0','PS0'].includes(SHORT[it.s]))g.key=true;}
  const items=Object.values(groups).sort((a,b)=>b.v-a.v);
  const GAP=14;let lastY=-1e9;
  for(const g of items){
    const by=y(g.v),col=tcol(g.stem),sw=g.key?1.8:1.0;
    svg+=`<line x1="${padL}" y1="${by}" x2="${W-padR}" y2="${by}" stroke="${col}" stroke-width="${sw}" opacity="${g.key?0.95:0.45}"/>`;
    let ly=Math.max(by,lastY+GAP);lastY=ly;
    if(Math.abs(ly-by)>1.5)svg+=`<line x1="${W-padR}" y1="${by}" x2="${W-padR+5}" y2="${ly}" stroke="${css('--grid')}"/>`;
    svg+=`<text class="lvl-label" x="${W-padR+7}" y="${ly+3.5}" fill="${col}"><tspan style="font-weight:600">${g.codes.join('/')}</tspan> ${fmt(g.v,0)}</text>`;
  }
  // price candles
  const cUp=css('--good'),cDn='#9a948c',bw=Math.max((W-padL-padR)/(n||1)*0.62,1.2);
  PATH.forEach((b,i)=>{const cc=b.c>=b.o?cUp:cDn,xc=xi(i);
    svg+=`<line x1="${xc}" y1="${y(b.h)}" x2="${xc}" y2="${y(b.l)}" stroke="${cc}" stroke-width="1"/>`;
    const yo=y(b.o),yc=y(b.c);svg+=`<rect x="${(xc-bw/2).toFixed(1)}" y="${Math.min(yo,yc).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(Math.abs(yo-yc),1).toFixed(1)}" fill="${cc}" data-b="${b.hm}|${b.o}|${b.h}|${b.l}|${b.c}" class="cndl"/>`;});
  svg+=`</svg>`;
  document.getElementById('ts').innerHTML=svg;
  document.getElementById('ts-leg').innerHTML=`<span><i style="background:${css('--pos')}"></i>Call levels</span><span><i style="background:${css('--neg')}"></i>Put levels</span><span><i style="background:${css('--hvl')}"></i>HVL / Gamma Wall</span><span><i style="background:${css('--muted')}"></i>GEX walls</span><span><i style="background:${css('--good')}"></i>up</span><span><i style="background:#9a948c"></i>down</span>`;
  const svgEl=document.getElementById('tssvg');
  svgEl.addEventListener('wheel',e=>{e.preventDefault();const rc=svgEl.getBoundingClientRect();
    const pv=(e.clientY-rc.top)/rc.height*H;const curV=hi-(pv-padT)/(H-padT-padB)*(hi-lo);
    const f=e.deltaY>0?1.12:0.89;yH=Math.max(yH*f,0.02);yC=curV+(yC-curV)*f;drawDay();},{passive:false});
  svgEl.addEventListener('mousedown',e=>{_drag={y:e.clientY};});
  document.querySelectorAll('.cndl').forEach(el=>{el.addEventListener('mousemove',e=>{const p=el.dataset.b.split('|');
    showTT(`<b>${p[0]}</b><br>O ${p[1]} H ${p[2]}<br>L ${p[3]} C ${p[4]}`,e.clientX,e.clientY);});el.addEventListener('mouseleave',hideTT);});
}
function initZoom(){if(_zoomInit)return;_zoomInit=true;
  window.addEventListener('mousemove',e=>{if(!_drag||!GEO)return;const el=document.getElementById('tssvg');if(!el)return;
    const rc=el.getBoundingClientRect();const dy=e.clientY-_drag.y;_drag.y=e.clientY;
    const chartHpx=rc.height*((GEO.H-GEO.padT-GEO.padB)/GEO.H);yC+=dy*(GEO.hi-GEO.lo)/chartHpx;drawDay();});
  window.addEventListener('mouseup',()=>{_drag=null;});}
function drawKPIs(){const r=DBROWS[cur];
  const items=[...(r.spot!=null?[['Spot',fmt(r.spot)]]:[]),['Call Resistance',fmt(r.L.cr[0],0)],['Put Support',fmt(r.L.ps[0],0)],['HVL',fmt(r.L.hvl[0],0)],['Gamma Wall 0DTE',fmt(r.L.gw0[0],0)],['1D range',fmt(r.d1_min,0)+' – '+fmt(r.d1_max,0)]];
  document.getElementById('kpis').innerHTML=items.map(([l,v])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');}
function drawTable(){const r=DBROWS[cur];document.getElementById('tbl-date').textContent='· '+r.d;
  const ent=[];
  for(const [s,l] of LV){const v=r.L[s][0],g=r.L[s][1];if(v==null)continue;ent.push({name:l,v,g,spot:false});}
  let reg=null;
  if(r.spot!=null){const hvl=r.L.hvl[0];reg=hvl==null?null:(r.spot>=hvl);
    ent.push({name:'SPOT',v:r.spot,g:null,spot:true,reg});}
  ent.sort((a,b)=>b.v-a.v);   // price descending — resistance on top, support below
  let h='<tr><th>Level</th><th>Price</th><th>Signed GEX ($)</th><th>Δ vs spot</th></tr>';
  for(const e of ent){
    const d=r.spot!=null?(e.v-r.spot):null;
    const dtxt=d==null?'—':(d>=0?'+':'')+fmt(d,0);
    if(e.spot){
      const cls=e.reg==null?'spot-row':(e.reg?'spot-row spot-pos':'spot-row spot-neg');
      const tag=e.reg==null?'—':(e.reg?'▲ positive gamma':'▼ negative gamma');
      h+=`<tr class="${cls}"><td><b>▶ SPOT</b></td><td><b>${fmt(e.v,0)}</b></td><td><b>${tag}</b></td><td>0</td></tr>`;
    }else{
      h+=`<tr><td>${e.name}</td><td>${fmt(e.v,0)}</td><td class="${e.g==null?'':e.g>=0?'pos':'neg'}">${fmtG(e.g)}</td><td>${dtxt}</td></tr>`;
    }
  }
  document.getElementById('tbl').innerHTML=h;}
function render(){drawKPIs();drawDay();drawTable();document.getElementById('datepick').value=DBROWS[cur].d;}

document.getElementById('prev').onclick=()=>{if(cur>0){cur--;goDay();}};
document.getElementById('next').onclick=()=>{if(cur<DBROWS.length-1){cur++;goDay();}};
document.getElementById('latest').onclick=()=>{cur=DBROWS.length-1;goDay();};
document.getElementById('datepick').onchange=e=>{const v=e.target.value;if(byd[v]!=null){cur=byd[v];goDay();}};
document.getElementById('yin').onclick=()=>{if(yH){yH*=0.8;drawDay();}};
document.getElementById('yout').onclick=()=>{if(yH){yH*=1.25;drawDay();}};
document.getElementById('yfit').onclick=()=>{yC=null;yH=null;drawDay();};
initZoom();
window.addEventListener('keydown',e=>{if(!DBROWS.length)return;if(e.key==='ArrowLeft')document.getElementById('prev').click();if(e.key==='ArrowRight')document.getElementById('next').click();});

// update button
const btn=document.getElementById('btn-update');
btn.onclick=async()=>{btn.disabled=true;document.getElementById('upd-status').innerHTML='<span class="spin"></span> pulling recent sessions…';
  await fetch('/update',{method:'POST'});poll();};
async function poll(){const j=await (await fetch('/update_log')).json();
  if(j.running){setTimeout(poll,1500);return;}
  document.getElementById('upd-status').textContent=j.at?('updated '+j.at):'done';btn.disabled=false;
  const keep=TKR;await loadStatus();if(keep)selectTicker(keep);}

loadStatus();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8610)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Gamma Levels Command Center at {url}  (Ctrl-C to stop)")
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
