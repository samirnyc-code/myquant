"""Divergence-marking tool — forward-reveal price + CVD, one bar at a time (S75M).

Companion to mark_setups.py, but for CVD divergences. Deliberately forward-only so a
mark can only use information KNOWN AT THE TIME (kills the hindsight bias: you can't
mark a divergence off a swing you can only see because price already reversed).

  * TWO panels: 5M price candles (top) + CVD candles (bottom, reconstructed from
    ES_bars Delta/MinDelta/MaxDelta — cumulative delta, session reset).
  * FORWARD REVEAL: →/Space step one bar; ← rewinds the VIEW only (reveal never shrinks).
  * MARK a divergence: click pivot A, click pivot B (both must be already revealed),
    then pick the type (1 reg-bear · 2 reg-bull · 3 hid-bear · 4 hid-bull). The line is
    drawn on BOTH panels at the same two bars; price uses the high (bear) or low (bull),
    CVD uses its close at those bars. Z = undo last.

Marks -> data/annotations/divergence_marks.csv:
  marked_at,day,a_idx,a_time,a_price,a_cvd,b_idx,b_time,b_price,b_cvd,kind,reveal_idx,note
Input: data/footprint/ES_bars.csv    Run: .venv/Scripts/python.exe scripts/mark_divergence.py [--port 8631] [--open]
"""
import argparse, csv, json, webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BARS_CSV = ROOT / "data" / "footprint" / "ES_bars.csv"
MARKS_CSV = ROOT / "data" / "annotations" / "divergence_marks.csv"
FIELDS = ["marked_at", "day", "a_idx", "a_time", "a_price", "a_cvd",
          "b_idx", "b_time", "b_price", "b_cvd", "kind", "reveal_idx", "note"]
RTH0, RTH1 = "08:30", "15:00"


def load_days():
    """{day: {bars:[[idx,hhmm,o,h,l,c,cvo,cvh,cvl,cvc],...]}}  5M RTH, CVD candles."""
    raw = {}
    with open(BARS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            day = r["BarTime"][:10]; t5 = r["BarTime"][11:16]
            if not (RTH0 <= t5 < RTH1):
                continue
            key = t5[:4] + "0" if False else t5    # placeholder; real 5-min floor below
            raw.setdefault(day, []).append(r)
    days = {}
    for day, rows in raw.items():
        rows.sort(key=lambda r: r["BarTime"])
        # 5-minute bins
        bins = {}
        for r in rows:
            hh, mm = int(r["BarTime"][11:13]), int(r["BarTime"][14:16])
            t5 = f"{hh:02d}:{(mm//5)*5:02d}"
            bins.setdefault(t5, []).append(r)
        bars = []; run = 0.0; idx = 0
        for t5 in sorted(bins):
            g = sorted(bins[t5], key=lambda r: int(r["BarIdx"]))
            o = float(g[0]["Open"]); c = float(g[-1]["Close"])
            h = max(float(x["High"]) for x in g); lo = min(float(x["Low"]) for x in g)
            cvo = run; cur = run; ch = run; cl = run
            for x in g:
                mx = float(x["MaxDelta"]); mn = float(x["MinDelta"]); dl = float(x["Delta"])
                ch = max(ch, cur + mx); cl = min(cl, cur + mn); cur += dl
            bars.append([idx, t5, o, h, lo, c, cvo, ch, cl, cur]); run = cur; idx += 1
        days[day] = {"bars": bars}
    return dict(sorted(days.items()))


def read_marks():
    if not MARKS_CSV.exists():
        return []
    with open(MARKS_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_mark(row):
    MARKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not MARKS_CSV.exists()
    with open(MARKS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def delete_last(day):
    rows = read_marks()
    for i in range(len(rows) - 1, -1, -1):
        if rows[i]["day"] == day:
            del rows[i]; break
    else:
        return False
    with open(MARKS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    return True


class Handler(BaseHTTPRequestHandler):
    days = {}

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, separators=(",", ":")).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML.replace("__DAYS__", json.dumps(list(self.days))).encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body); return
        if self.path.startswith("/api/day?d="):
            d = self.path.split("=", 1)[1]
            if d not in self.days:
                return self._json({"err": "unknown day"}, 404)
            marks = [m for m in read_marks() if m["day"] == d]
            return self._json({**self.days[d], "marks": marks})
        self._json({"err": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"err": "bad json"}, 400)
        if self.path == "/api/mark":
            day = req.get("day"); bars = {b[0]: b for b in self.days.get(day, {}).get("bars", [])}
            a, b = req.get("a_idx"), req.get("b_idx"); rv = req.get("reveal_idx")
            if a not in bars or b not in bars:
                return self._json({"err": "unknown bar"}, 400)
            if not isinstance(rv, int) or a > rv or b > rv:
                return self._json({"err": "mark beyond reveal edge rejected"}, 400)
            if req.get("kind") not in ("reg_bear", "reg_bull", "hid_bear", "hid_bull"):
                return self._json({"err": "bad kind"}, 400)
            ba, bb = bars[a], bars[b]
            hi = "bear" in req["kind"]   # bear compares HIGHs (price [3], CVD [7]); bull compares LOWs (price [4], CVD [8])
            append_mark({"marked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "day": day, "a_idx": a, "a_time": ba[1], "a_price": ba[3] if hi else ba[4], "a_cvd": ba[7] if hi else ba[8],
                         "b_idx": b, "b_time": bb[1], "b_price": bb[3] if hi else bb[4], "b_cvd": bb[7] if hi else bb[8],
                         "kind": req["kind"], "reveal_idx": rv, "note": req.get("note", "")})
            return self._json({"ok": True})
        if self.path == "/api/unmark":
            return self._json({"ok": delete_last(req.get("day"))})
        self._json({"err": "not found"}, 404)


HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Mark Divergences — forward reveal</title>
<style>
:root{--bg:#0f1115;--surf:#171a20;--ink:#e8ebf0;--mut:#8a91a0;--line:#2a3040;--up:#2e9e4f;--dn:#d64545;--sel:#3987e5;--bull:#22a45a;--bear:#d23b3b}
@media(prefers-color-scheme:light){:root{--bg:#eef0f3;--surf:#fff;--ink:#151821;--mut:#68707f;--line:#dde1e8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px system-ui,"Segoe UI",sans-serif}
header{padding:9px 14px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap;background:var(--surf)}
h1{font-size:14px;margin:0;font-weight:650}
select,button{font:inherit;color:var(--ink);background:var(--surf);border:1px solid var(--line);border-radius:8px;padding:5px 9px;cursor:pointer}
button.on{background:var(--sel);color:#fff;border-color:var(--sel)}
.pill{font-size:12px;color:var(--mut)}
#wrap{margin:8px 14px}
canvas{display:block;width:100%;background:var(--surf);border:1px solid var(--line);border-radius:10px;cursor:crosshair}
#pop{position:fixed;display:none;background:var(--surf);border:1px solid var(--line);border-radius:10px;padding:8px;box-shadow:0 8px 30px rgba(0,0,0,.5);z-index:9}
#pop button{display:block;width:190px;margin:3px 0;text-align:left}
.help{font-size:12px;color:var(--mut);margin:4px 14px}
b.k{color:var(--ink);background:var(--line);border-radius:4px;padding:0 5px;font-family:ui-monospace,monospace}
</style></head><body>
<header>
  <h1>Mark Divergences</h1>
  <select id="day"></select>
  <button id="play">▶ Play</button>
  <span class="pill" id="pos"></span>
  <span class="pill" id="cnt"></span>
  <span class="pill">click <b>A</b> then <b>B</b> → pick type · <b class="k">→</b> step · <b class="k">Space</b> play · <b class="k">Z</b> undo</span>
</header>
<div id="wrap"><canvas id="cv"></canvas></div>
<div class="help">Forward-only: you can only mark bars already revealed. Price top, CVD (session cumulative delta) bottom — both drawn as candles.</div>
<div id="pop">
  <button data-k="reg_bear">1 · Regular bearish (price HH, CVD LH → short)</button>
  <button data-k="reg_bull">2 · Regular bullish (price LL, CVD HL → long)</button>
  <button data-k="hid_bear">3 · Hidden bearish (price LH, CVD HH → cont. down)</button>
  <button data-k="hid_bull">4 · Hidden bullish (price HL, CVD LL → cont. up)</button>
</div>
<script>
const DAYS=__DAYS__; let D=null, day=null, reveal=1, marks=[], sel=[], playing=false, timer=null;
const cv=document.getElementById('cv'), ctx=cv.getContext('2d'), pop=document.getElementById('pop');
const daySel=document.getElementById('day');
DAYS.forEach(d=>{const o=document.createElement('option');o.value=o.textContent=d;daySel.appendChild(o)});
function css(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim()}
async function load(d){const r=await fetch('/api/day?d='+d);D=await r.json();day=d;reveal=1;sel=[];marks=D.marks||[];draw()}
daySel.onchange=()=>load(daySel.value);

const PADL=54,PADR=14,PADT=12,GAP=16;
function geom(){
  const W=cv.width, H=cv.height, priceH=Math.round((H-GAP)*0.62), cvdH=H-GAP-priceH-PADT;
  return {W,H,priceH,cvdH,cvdTop:PADT+priceH+GAP};
}
function draw(){
  const bars=D.bars, n=reveal, ratio=window.devicePixelRatio||1;
  const cssW=cv.parentElement.clientWidth, cssH=Math.max(520,Math.min(760,window.innerHeight-150));
  cv.style.height=cssH+'px'; cv.width=cssW*ratio; cv.height=cssH*ratio; ctx.setTransform(ratio,0,0,ratio,0,0);
  const {W,priceH,cvdH,cvdTop}=(()=>{const W=cssW,H=cssH,pH=Math.round((H-GAP)*0.62),cH=H-GAP-pH-PADT;return{W,priceH:pH,cvdH:cH,cvdTop:PADT+pH+GAP}})();
  ctx.clearRect(0,0,W,cssH);
  const vis=bars.slice(0,n); if(!vis.length)return;
  const total=bars.length;                              // fixed x-scale over the whole day
  const bw=(W-PADL-PADR)/total, cw=Math.max(1.5,bw*0.62);
  const X=i=>PADL+(i+0.5)*bw;
  // price scale (over full day so it doesn't jump as bars reveal)
  let plo=Math.min(...bars.map(b=>b[4])), phi=Math.max(...bars.map(b=>b[3])); const pp=(phi-plo)*0.05;
  const YP=v=>PADT+(1-(v-(plo-pp))/((phi+pp)-(plo-pp)))*priceH;
  let clo=Math.min(...bars.map(b=>b[8])), chi=Math.max(...bars.map(b=>b[7])); const cp=(chi-clo)*0.06||1;
  const YC=v=>cvdTop+(1-(v-(clo-cp))/((chi+cp)-(clo-cp)))*cvdH;
  const up=css('--up'),dn=css('--dn');
  // zero line for CVD
  ctx.strokeStyle=css('--line');ctx.beginPath();ctx.moveTo(PADL,YC(0));ctx.lineTo(W-PADR,YC(0));ctx.stroke();
  function candle(i,o,h,l,c,Y){const x=X(i),col=(c>=o)?up:dn;ctx.strokeStyle=col;ctx.fillStyle=col;
    ctx.beginPath();ctx.moveTo(x,Y(h));ctx.lineTo(x,Y(l));ctx.stroke();
    const a=Y(o),b=Y(c);ctx.fillRect(x-cw/2,Math.min(a,b),cw,Math.max(Math.abs(b-a),1))}
  vis.forEach(b=>{candle(b[0],b[2],b[3],b[4],b[5],YP);
                  candle(b[0],b[6],b[7],b[8],b[9],YC)});
  // labels
  ctx.fillStyle=css('--mut');ctx.font='10px system-ui';ctx.fillText('PRICE',4,PADT+10);ctx.fillText('CVD',4,cvdTop+10);
  // existing marks
  const botY=cvdTop+cvdH;
  marks.forEach(m=>drawMark(+m.a_idx,+m.b_idx,m.kind,X,YP,YC,botY));
  // pending selection
  sel.forEach(i=>{ctx.strokeStyle=css('--sel');ctx.setLineDash([4,3]);
    ctx.beginPath();ctx.moveTo(X(i),PADT);ctx.lineTo(X(i),cvdTop+cvdH);ctx.stroke();ctx.setLineDash([])});
  document.getElementById('pos').textContent=`bar ${n}/${total}  ${vis[vis.length-1][1]}`;
  document.getElementById('cnt').textContent=`${marks.length} divergences`;
  window._geom={X,YP,YC,bw,total};
}
function drawMark(ai,bi,kind,X,YP,YC,botY){
  const A=D.bars[ai],B=D.bars[bi]; const bear=kind.includes('bear');
  const col=bear?css('--bear'):css('--bull');
  const pa=bear?A[3]:A[4], pb=bear?B[3]:B[4];         // price: high(bear)/low(bull)
  const ca=bear?A[7]:A[8], cb=bear?B[7]:B[8];         // CVD:   high(bear)/low(bull) — MATCHES price
  ctx.strokeStyle=col;ctx.lineWidth=2;
  ctx.beginPath();ctx.moveTo(X(ai),YP(pa));ctx.lineTo(X(bi),YP(pb));ctx.stroke();   // price
  ctx.beginPath();ctx.moveTo(X(ai),YC(ca));ctx.lineTo(X(bi),YC(cb));ctx.stroke();   // CVD
  ctx.setLineDash([3,3]);ctx.globalAlpha=.5;                                          // aligned verticals
  [ai,bi].forEach(i=>{ctx.beginPath();ctx.moveTo(X(i),PADT);ctx.lineTo(X(i),botY);ctx.stroke()});
  ctx.globalAlpha=1;ctx.setLineDash([]);ctx.lineWidth=1;
}
function pickBar(px){const g=window._geom;if(!g)return -1;
  let i=Math.round((px-PADL)/g.bw-0.5); i=Math.max(0,Math.min(reveal-1,i));return i}
cv.addEventListener('click',e=>{
  const rect=cv.getBoundingClientRect(); const i=pickBar(e.clientX-rect.left);
  if(i<0||i>=reveal)return;
  sel.push(i); if(sel.length>2)sel.shift();
  if(sel.length===2){ showPop(e.clientX,e.clientY); }
  draw();
});
function showPop(x,y){pop.style.left=Math.min(x,window.innerWidth-210)+'px';pop.style.top=Math.min(y,window.innerHeight-180)+'px';pop.style.display='block'}
pop.querySelectorAll('button').forEach(btn=>btn.onclick=()=>saveMark(btn.dataset.k));
async function saveMark(kind){
  pop.style.display='none'; if(sel.length!==2){sel=[];return}
  const [a,b]=sel.slice().sort((x,y)=>x-y);
  const r=await fetch('/api/mark',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({day,a_idx:a,b_idx:b,kind,reveal_idx:reveal-1})});
  const j=await r.json(); if(!j.ok)alert('rejected: '+(j.err||'?'));
  const rr=await fetch('/api/day?d='+day); marks=(await rr.json()).marks||[]; sel=[]; draw();
}
function step(dn){reveal=Math.max(1,Math.min(D.bars.length,reveal+dn));draw()}
document.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight'){step(1)} else if(e.key==='ArrowLeft'){step(-1)}
  else if(e.key===' '){e.preventDefault();togglePlay()}
  else if(e.key.toLowerCase()==='z'){undo()}
  else if(pop.style.display==='block' && '1234'.includes(e.key)){
    saveMark(['reg_bear','reg_bull','hid_bear','hid_bull'][+e.key-1])}
});
function togglePlay(){playing=!playing;document.getElementById('play').classList.toggle('on',playing);
  document.getElementById('play').textContent=playing?'❚❚ Pause':'▶ Play';
  if(playing){timer=setInterval(()=>{if(reveal>=D.bars.length){togglePlay();return}step(1)},350)}else clearInterval(timer)}
document.getElementById('play').onclick=togglePlay;
async function undo(){await fetch('/api/unmark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({day})});
  const rr=await fetch('/api/day?d='+day); marks=(await rr.json()).marks||[]; draw()}
window.addEventListener('resize',()=>D&&draw());
load(DAYS[0]);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8631)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    Handler.days = load_days()
    print(f"loaded {len(Handler.days)} days: {', '.join(Handler.days)}")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}"
    print(f"divergence marker -> {url}  (Ctrl+C to stop)")
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
