"""Setup-marking tool — forward-reveal chart annotator (S75J/K).

The user marks great trade setups (BOPB, second-entry fades) on ES volume-bar
charts; marks feed feature discovery vs matched controls. Design locked S75K:

  * FORWARD-ONLY REVEAL — bars draw left-to-right (play / step keys); a mark can
    only be placed on an already-revealed bar. Enforced client AND server side
    (`reveal_idx` is stored with every mark so the no-lookahead property is
    auditable). Rewinding the *view* is allowed; un-revealing is not.
  * PRICE + MQ LEVELS ONLY — deliberately no delta/CVD on screen, so marks stay
    independent of the footprint features the analysis will test (anchoring).
  * LABELS — setup type (BOPB / 2nd-entry fade / other) + direction + optional
    A/B grade. 3 keystrokes per mark.
  * Day order: chronological, dates shown (user's call; noted as a limitation).

Marks append to data/annotations/marks.csv:
  marked_at,day,bar_idx,bar_time,price,setup,direction,grade,reveal_idx,note

Inputs: data/footprint/ES_bars.csv, data/menthorq/ES1!_mq_levels_history.csv
Run:    .venv/Scripts/python.exe scripts/mark_setups.py [--port 8630] [--open]
        (8590-8620 are taken by Mission Control dashboards — see launcher.py)
"""
import argparse
import csv
import json
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BARS_CSV = ROOT / "data" / "footprint" / "ES_bars.csv"
LEVELS_CSV = ROOT / "data" / "menthorq" / "ES1!_mq_levels_history.csv"
MARKS_CSV = ROOT / "data" / "annotations" / "marks.csv"
MARK_FIELDS = ["marked_at", "day", "bar_idx", "bar_time", "price",
               "setup", "direction", "grade", "reveal_idx", "note"]

LEVEL_STEMS = ["cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0",
               "d1_min", "d1_max"] + [f"gex_{i}" for i in range(1, 11)]


def load_days():
    """{day: {bars: [[idx,time,o,h,l,c],...], levels: [[price,'cr0+gw0'],...]}}"""
    days = {}
    with open(BARS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = r["BarTime"][:10]
            days.setdefault(d, {"bars": [], "levels": []})["bars"].append(
                [int(r["BarIdx"]), r["BarTime"][11:16],
                 float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])])
    with open(LEVELS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = r["session_date"]
            if d not in days:
                continue
            by_price = {}
            for stem in LEVEL_STEMS:
                v = r.get(stem)
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                by_price.setdefault(v, []).append(stem)
            lo = min(b[4] for b in days[d]["bars"]) - 15
            hi = max(b[3] for b in days[d]["bars"]) + 15
            days[d]["levels"] = sorted(
                [[p, "+".join(s)] for p, s in by_price.items() if lo <= p <= hi])
    for d in days.values():
        d["bars"].sort()
    return dict(sorted(days.items()))  # chronological (user's choice)


def read_marks():
    if not MARKS_CSV.exists():
        return []
    with open(MARKS_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_mark(row):
    MARKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new = not MARKS_CSV.exists()
    with open(MARKS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MARK_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def delete_mark(day, bar_idx, setup):
    """Remove the LAST mark matching (day, bar_idx, setup); rewrite the file."""
    rows = read_marks()
    for i in range(len(rows) - 1, -1, -1):
        r = rows[i]
        if r["day"] == day and r["bar_idx"] == str(bar_idx) and r["setup"] == setup:
            del rows[i]
            break
    else:
        return False
    with open(MARKS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MARK_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return True


class Handler(BaseHTTPRequestHandler):
    days = {}  # set in main()

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML_TMPL.replace(
                "__DAYS__", json.dumps(list(self.days), separators=(",", ":"))).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
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
            day, bi = req.get("day"), req.get("bar_idx")
            bars = {b[0]: b for b in self.days.get(day, {}).get("bars", [])}
            if bi not in bars:
                return self._json({"err": "unknown bar"}, 400)
            # no-lookahead guardrail: the marked bar must already be revealed
            if not isinstance(req.get("reveal_idx"), int) or bi > req["reveal_idx"]:
                return self._json({"err": "mark beyond reveal edge rejected"}, 400)
            if req.get("setup") not in ("bopb", "fade2", "other") \
                    or req.get("direction") not in ("long", "short"):
                return self._json({"err": "bad setup/direction"}, 400)
            append_mark({
                "marked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "day": day, "bar_idx": bi, "bar_time": f"{day} {bars[bi][1]}",
                "price": bars[bi][5], "setup": req["setup"],
                "direction": req["direction"], "grade": req.get("grade", ""),
                "reveal_idx": req["reveal_idx"], "note": req.get("note", "")})
            return self._json({"ok": True})
        if self.path == "/api/unmark":
            ok = delete_mark(req.get("day"), req.get("bar_idx"), req.get("setup"))
            return self._json({"ok": ok})
        self._json({"err": "not found"}, 404)


# ---------------------------------------------------------------- HTML template
HTML_TMPL = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mark Setups — forward reveal</title>
<style>
:root{
  --surface:#fcfcfb; --plane:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10); --card:#ffffff;
  --up:#1f8a4c; --dn:#cf3f3f; --sel:#2a78d6; --long:#1f8a4c; --short:#cf3f3f;
  --cr:#cf3f3f; --ps:#1f8a4c; --hvl:#7a3aa7; --gw:#d67f2a; --gex:#9a988f; --band:#2a78d6;
}
@media (prefers-color-scheme:dark){:root{
  --surface:#1a1a19; --plane:#0d0d0d; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#262624; --axis:#383835; --border:rgba(255,255,255,.12); --card:#1f1f1e;
  --up:#37b06a; --dn:#e66767; --sel:#3987e5;
  --cr:#e66767; --ps:#37b06a; --hvl:#9c6fd0; --gw:#e6a45c; --gex:#6f6e66; --band:#3987e5;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
header{padding:10px 16px;border-bottom:1px solid var(--border);display:flex;
  align-items:center;gap:14px;flex-wrap:wrap;background:var(--surface)}
h1{font-size:15px;margin:0;font-weight:650}
select,button,input{font:inherit;color:var(--ink);background:var(--card);
  border:1px solid var(--border);border-radius:8px;padding:5px 10px;cursor:pointer}
button.on{background:var(--sel);color:#fff;border-color:var(--sel)}
.pill{font-size:12px;color:var(--ink2)}
#stage{position:relative;margin:10px 16px}
canvas{display:block;width:100%;background:var(--surface);
  border:1px solid var(--border);border-radius:12px;cursor:crosshair}
#prompt{position:absolute;top:12px;left:14px;background:var(--card);border:1px solid var(--sel);
  border-radius:10px;padding:8px 14px;font-size:13.5px;display:none;box-shadow:0 4px 14px rgba(0,0,0,.18)}
#done{position:absolute;top:12px;right:14px;background:var(--up);color:#fff;border-radius:10px;
  padding:6px 12px;font-size:13px;display:none}
#help{margin:4px 16px 8px;color:var(--muted);font-size:12px}
#marks{margin:0 16px 40px}
#marks table{border-collapse:collapse;font-size:12.5px}
#marks td,#marks th{padding:3px 10px;border-bottom:1px solid var(--border);text-align:left}
#marks button{padding:1px 8px;font-size:11.5px}
kbd{background:var(--card);border:1px solid var(--border);border-radius:4px;
  padding:0 5px;font-size:11px;font-family:inherit}
</style></head><body>
<header>
  <h1>Mark Setups</h1>
  <select id="day"></select>
  <button id="play">▶ play</button>
  <span class="pill">speed <span id="spd"></span> bars/s</span>
  <span class="pill" id="pos"></span>
  <span class="pill" id="nmarks"></span>
  <span class="pill" style="margin-left:auto">forward-only reveal · price + MQ levels only</span>
</header>
<div id="stage">
  <canvas id="cv" height="560"></canvas>
  <div id="prompt"></div>
  <div id="done">day complete — pick the next day</div>
</div>
<div id="help">
  <kbd>space</kbd> play/pause · <kbd>→</kbd> +1 bar · <kbd>shift→</kbd> +10 ·
  <kbd>+</kbd>/<kbd>-</kbd> speed · click a revealed bar to select ·
  mark: <kbd>B</kbd> BOPB / <kbd>F</kbd> 2nd-entry fade / <kbd>O</kbd> other,
  then <kbd>L</kbd> long / <kbd>S</kbd> short, then <kbd>A</kbd>/<kbd>B</kbd> grade or
  <kbd>enter</kbd> skip · <kbd>esc</kbd> cancel · <kbd>Z</kbd> undo last mark ·
  wheel/drag to look back (view only — never reveals)
</div>
<div id="marks"></div>
<script>
const DAYS=__DAYS__;
const SETUPS={bopb:"BOPB",fade2:"2nd-entry fade",other:"other"};
const LC={cr:"--cr",cr0:"--cr",ps:"--ps",ps0:"--ps",hvl:"--hvl",hvl0:"--hvl",
          gw0:"--gw",d1_min:"--band",d1_max:"--band"};
let bars=[],levels=[],marks=[],day=null;
let reveal=0,sel=null,follow=true,playing=false,timer=null,speed=4,scroll=0;
let pending=null; // {setup, direction}
const cv=document.getElementById("cv"),ctx=cv.getContext("2d");
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const BW=7,VIEW=()=>Math.floor((cv.width/dpr-70)/BW);
let dpr=1;
function sizeCanvas(){dpr=window.devicePixelRatio||1;
  const w=cv.clientWidth;cv.width=w*dpr;cv.height=560*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);}
async function loadDay(d){
  const r=await fetch("/api/day?d="+d);const j=await r.json();
  day=d;bars=j.bars;levels=j.levels;marks=j.marks;
  reveal=Math.min(19,bars.length-1);sel=null;follow=true;scroll=0;pause();draw();table();}
function pause(){playing=false;clearInterval(timer);document.getElementById("play").textContent="▶ play";
  document.getElementById("play").classList.remove("on");}
function play(){if(reveal>=bars.length-1)return;playing=true;
  document.getElementById("play").textContent="❚❚ pause";document.getElementById("play").classList.add("on");
  clearInterval(timer);timer=setInterval(()=>{step(1);if(reveal>=bars.length-1)pause();},1000/speed);}
function step(n){reveal=Math.min(bars.length-1,reveal+n);if(follow)scroll=0;
  if(sel===null||follow)sel=null;draw();}
function xIdx(i,i0){return 60+ (i-i0)*BW; }
function draw(){
  if(!bars.length)return;
  const W=cv.width/dpr,H=560,padB=24;
  ctx.clearRect(0,0,W,H);
  const view=VIEW();
  let iEnd=Math.max(0,reveal-scroll), i0=Math.max(0,iEnd-view+1);
  const vis=bars.slice(i0,iEnd+1);
  let lo=Math.min(...vis.map(b=>b[4])),hi=Math.max(...vis.map(b=>b[3]));
  if(hi-lo<8){const m=(hi+lo)/2;lo=m-4;hi=m+4;}
  const pad=(hi-lo)*0.08;lo-=pad;hi+=pad;
  const y=p=>(hi-p)/(hi-lo)*(H-padB-10)+10;
  // gridlines
  ctx.strokeStyle=css("--grid");ctx.lineWidth=1;ctx.font="10.5px system-ui";
  ctx.fillStyle=css("--muted");
  const stepP=(hi-lo)>40?10:(hi-lo)>16?5:2;
  for(let p=Math.ceil(lo/stepP)*stepP;p<hi;p+=stepP){
    ctx.beginPath();ctx.moveTo(60,y(p));ctx.lineTo(W-8,y(p));ctx.stroke();
    ctx.fillText(p.toFixed(0),8,y(p)+3);}
  // MQ levels (in view)
  ctx.font="10px system-ui";
  for(const [p,name] of levels){
    if(p<lo||p>hi)continue;
    const stem=name.split("+")[0];
    ctx.strokeStyle=css(LC[stem]||"--gex");
    ctx.setLineDash(name.startsWith("d1_")?[2,4]:(LC[stem]?[]:[4,4]));
    ctx.lineWidth=LC[stem]&&!name.startsWith("d1_")?1.4:1;
    ctx.beginPath();ctx.moveTo(60,y(p));ctx.lineTo(W-8,y(p));ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle=css(LC[stem]||"--gex");
    ctx.fillText(name+" "+p,W-8-ctx.measureText(name+" "+p).width,y(p)-3);}
  // candles
  let lastLbl=-1;
  for(let i=i0;i<=iEnd;i++){
    const [bi,t,o,h,l,c]=bars[i],x=xIdx(i,i0);
    const up=c>=o;ctx.strokeStyle=ctx.fillStyle=css(up?"--up":"--dn");
    ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x,y(h));ctx.lineTo(x,y(l));ctx.stroke();
    const yo=y(Math.max(o,c)),yc=y(Math.min(o,c));
    ctx.fillRect(x-2.5,yo,5,Math.max(1,yc-yo));
    if(sel===i){ctx.strokeStyle=css("--sel");ctx.lineWidth=1.5;
      ctx.strokeRect(x-4.5,y(h)-4,9,y(l)-y(h)+8);}
    const mins=parseInt(t.slice(3));
    if(mins%30===0&&i-lastLbl>=6){lastLbl=i;ctx.fillStyle=css("--muted");
      ctx.font="10.5px system-ui";ctx.fillText(t,x-13,H-8);
      ctx.strokeStyle=css("--grid");ctx.beginPath();ctx.moveTo(x,10);ctx.lineTo(x,H-padB);ctx.stroke();}
  }
  // marks
  for(const m of marks){
    const i=bars.findIndex(b=>b[0]==m.bar_idx);
    if(i<i0||i>iEnd)continue;
    const x=xIdx(i,i0),b=bars[i],lng=m.direction==="long";
    ctx.fillStyle=css(lng?"--long":"--short");
    const yy=lng?y(b[4])+14:y(b[3])-14;
    ctx.beginPath();
    if(lng){ctx.moveTo(x,yy-7);ctx.lineTo(x-5,yy);ctx.lineTo(x+5,yy);}
    else{ctx.moveTo(x,yy+7);ctx.lineTo(x-5,yy);ctx.lineTo(x+5,yy);}
    ctx.closePath();ctx.fill();
    ctx.font="bold 10px system-ui";
    ctx.fillText((m.setup==="bopb"?"B":m.setup==="fade2"?"F":"O")+(m.grade||""),
                 x-6,lng?yy+16:yy-10);}
  // reveal edge
  if(scroll===0){const x=xIdx(iEnd,i0)+BW;ctx.strokeStyle=css("--axis");
    ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,10);ctx.lineTo(x,H-padB);ctx.stroke();
    ctx.setLineDash([]);}
  document.getElementById("pos").textContent=
    `bar ${reveal+1}/${bars.length} · ${bars[reveal][1]}`+(scroll?` (viewing −${scroll})`:"");
  document.getElementById("nmarks").textContent=`${marks.length} marks this day`;
  document.getElementById("done").style.display=reveal>=bars.length-1?"block":"none";
  document.getElementById("spd").textContent=speed;
}
function table(){
  const el=document.getElementById("marks");
  if(!marks.length){el.innerHTML="";return;}
  el.innerHTML="<table><tr><th>time</th><th>setup</th><th>dir</th><th>grade</th>"+
    "<th>price</th><th></th></tr>"+marks.map(m=>
    `<tr><td>${m.bar_time.slice(11)}</td><td>${SETUPS[m.setup]}</td><td>${m.direction}</td>`+
    `<td>${m.grade||"—"}</td><td>${m.price}</td>`+
    `<td><button onclick="unmark('${m.bar_idx}','${m.setup}')">✕</button></td></tr>`).join("")+
    "</table>";}
async function unmark(bi,setup){
  await fetch("/api/unmark",{method:"POST",body:JSON.stringify({day,bar_idx:+bi,setup})});
  marks=marks.filter(m=>!(m.bar_idx==bi&&m.setup===setup));draw();table();}
function promptTxt(){
  const el=document.getElementById("prompt");
  if(!pending){el.style.display="none";return;}
  const i=sel===null?reveal:sel,b=bars[i];
  el.style.display="block";
  el.innerHTML=`<b>${SETUPS[pending.setup]}</b> @ ${b[1]} (${b[5]}) — `+
    (!pending.direction?"direction? <kbd>L</kbd>ong / <kbd>S</kbd>hort":
     `${pending.direction} — grade? <kbd>A</kbd>/<kbd>B</kbd> or <kbd>enter</kbd> to skip`);}
async function commit(grade){
  const i=sel===null?reveal:sel,b=bars[i];
  const body={day,bar_idx:b[0],setup:pending.setup,direction:pending.direction,
              grade:grade||"",reveal_idx:bars[reveal][0]};
  pending=null;promptTxt();
  const r=await fetch("/api/mark",{method:"POST",body:JSON.stringify(body)});
  const j=await r.json();
  if(j.ok){marks.push({...body,bar_time:day+" "+b[1],price:b[5],
    bar_idx:String(b[0])});sel=null;draw();table();}
  else alert(j.err);}
document.addEventListener("keydown",e=>{
  const k=e.key;
  if(pending){
    if(k==="Escape"){pending=null;promptTxt();}
    else if(!pending.direction){
      if(k==="l"||k==="L"){pending.direction="long";promptTxt();}
      if(k==="s"||k==="S"){pending.direction="short";promptTxt();}}
    else{
      if(k==="a"||k==="A")commit("A");
      else if(k==="b"||k==="B")commit("B");
      else if(k==="Enter")commit("");}
    e.preventDefault();return;}
  if(k===" "){playing?pause():play();e.preventDefault();}
  else if(k==="ArrowRight"){pause();step(e.shiftKey?10:1);}
  else if(k==="+"||k==="="){speed=Math.min(20,speed+1);if(playing)play();draw();}
  else if(k==="-"){speed=Math.max(1,speed-1);if(playing)play();draw();}
  else if(k==="b"||k==="B"){pending={setup:"bopb"};promptTxt();}
  else if(k==="f"||k==="F"){pending={setup:"fade2"};promptTxt();}
  else if(k==="o"||k==="O"){pending={setup:"other"};promptTxt();}
  else if(k==="z"||k==="Z"){const m=marks[marks.length-1];
    if(m)unmark(m.bar_idx,m.setup);}
});
cv.addEventListener("click",e=>{
  const rect=cv.getBoundingClientRect(),x=e.clientX-rect.left;
  const view=VIEW(),iEnd=Math.max(0,reveal-scroll),i0=Math.max(0,iEnd-view+1);
  const i=i0+Math.round((x-60)/BW);
  if(i>=i0&&i<=iEnd){sel=(sel===i?null:i);draw();promptTxt();}});
cv.addEventListener("wheel",e=>{e.preventDefault();
  scroll=Math.max(0,Math.min(reveal,scroll+(e.deltaY>0?-10:10)));follow=scroll===0;draw();},
  {passive:false});
document.getElementById("play").onclick=()=>playing?pause():play();
const sel_d=document.getElementById("day");
for(const d of DAYS){const o=document.createElement("option");o.value=o.textContent=d;sel_d.appendChild(o);}
sel_d.onchange=()=>loadDay(sel_d.value);
window.addEventListener("resize",()=>{sizeCanvas();draw();});
sizeCanvas();loadDay(DAYS[0]);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8630)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    Handler.days = load_days()
    print(f"loaded {len(Handler.days)} sessions: {', '.join(Handler.days)}")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"marking tool at {url}")
    if a.open:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
