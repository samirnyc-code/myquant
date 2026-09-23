#!/usr/bin/env python3
"""One page covering every reference session: regime tape, summary, all charts.

    python pages/build_all_sessions.py [slug ...]

Reads the committed regime_data_es_<slug>.json + ms_chart_<slug>.png from the
parent directory. Unlike the per-day generators this one is content-free --
sessions come from the file list, so adding a session needs no new script.
"""
import base64, json, pathlib, sys, datetime as dt

_HERE = pathlib.Path(__file__).resolve().parent
SRC = _HERE.parent
OUT_DIR = _HERE / "out"
OUT_DIR.mkdir(exist_ok=True)
OUT = OUT_DIR / "es_regime_all_sessions.html"

TICKS = [("09:00", 7), ("10:00", 19), ("11:00", 31), ("12:00", 43),
         ("13:00", 55), ("14:00", 67), ("15:00", 79)]


def load(slug):
    d = json.load(open(SRC / f"regime_data_es_{slug}.json"))
    bars, n, segs = d["bars"], len(d["bars"]), d["segments"]
    ml = sum(p["major"] for p in d["pivot_lows"]) + sum(p["major"] for p in d["pivot_highs"])
    held = {"Bull": 0, "Bear": 0, "Range": 0}
    ribbon = []
    for k, g in enumerate(segs):
        a = g["start"]
        z = segs[k + 1]["start"] if k + 1 < len(segs) else n
        held[g["regime"]] += z - a
        ribbon.append(dict(r=g["regime"], w=(z - a) / n * 100,
                           tip=f'{g["regime"]} · bar {a + 1}–{min(z, n - 1) + 1} · '
                               f'{bars[a]["t"][11:16]}–{bars[min(z, n - 1)]["t"][11:16]}'))
    ev = d["events"]
    return dict(
        slug=slug, date=dt.date(int(slug[:4]), int(slug[4:6]), int(slug[6:])),
        bars=bars, n=n, segs=segs, ev=ev, ribbon=ribbon, held=held, maj=ml,
        minr=len(d["pivot_lows"]) + len(d["pivot_highs"]) - ml,
        bos=sum(e["kind"] == "BOS" for e in ev),
        choch=sum(e["kind"] == "ChoCh" for e in ev),
        o=bars[0]["o"], h=max(b["h"] for b in bars),
        l=min(b["l"] for b in bars), c=bars[-1]["c"],
        img=base64.b64encode((SRC / f"ms_chart_{slug}.png").read_bytes()).decode())


slugs = sys.argv[1:] or sorted(
    p.name[len("regime_data_es_"):-len(".json")]
    for p in SRC.glob("regime_data_es_*.json"))
days = [load(s) for s in slugs]

tape = "".join(
    '<a class="row" href="#d{s}"><span class="day"><b>{d:%d %b}</b> <i>{d:%y}</i></span>'
    '<span class="ribbon" aria-label="Regimes for {d:%d %B %Y}">{cells}</span>'
    '<span class="mix"><i class="k k--bull"></i>{bu}<i class="k k--bear"></i>{be}'
    '<i class="k k--range"></i>{rg}</span></a>'.format(
        s=D["slug"], d=D["date"],
        cells="".join(f'<span class="seg seg--{g["r"].lower()}" '
                      f'style="flex-basis:{g["w"]:.3f}%" title="{g["tip"]}"></span>'
                      for g in D["ribbon"]),
        bu=D["held"]["Bull"], be=D["held"]["Bear"], rg=D["held"]["Range"])
    for D in days)
ticks = "".join(f'<span style="left:{(b - 1) / 81 * 100:.2f}%">{t}</span>' for t, b in TICKS)

rows = "".join(
    '<tr><td><a href="#d{s}">{d:%d %b %y}</a></td><td class="v">{o:.2f}</td>'
    '<td class="v">{h:.2f}</td><td class="v">{l:.2f}</td><td class="v">{c:.2f}</td>'
    '<td class="v">{mj}<span class="sl">/</span>{mn}</td><td class="v">{bo}</td>'
    '<td class="v">{ch}</td><td class="shape">{sh}</td></tr>'.format(
        s=D["slug"], d=D["date"], o=D["o"], h=D["h"], l=D["l"], c=D["c"],
        mj=D["maj"], mn=D["minr"], bo=D["bos"], ch=D["choch"],
        sh=" ".join(f'<b class="reg--{g["regime"].lower()}">{g["regime"][:2]}{g["start"] + 1}</b>'
                    for g in D["segs"]))
    for D in days)

sections = "".join('''
  <section class="day-sec" id="d{s}">
    <header class="dh">
      <h2>{d:%A} {dd} {d:%B} {d:%Y}</h2>
      <p class="meta">O {o:.2f} · H {h:.2f} · L {l:.2f} · C {c:.2f}
        <span class="sep">|</span> {mj} major / {mn} minor
        <span class="sep">|</span> {bo} BOS / {ch} ChoCh</p>
    </header>
    <button class="shot" data-full="i{s}" aria-label="Enlarge the chart for {d:%d %B %Y}">
      <img id="i{s}" src="data:image/png;base64,{img}" alt="ES 5-minute regime chart, {d:%d %B %Y}">
      <span class="hint">Click to enlarge</span>
    </button>
    <div class="lists">
      <div><h3>Regimes</h3><ul class="ls">{segl}</ul></div>
      <div><h3>Structural breaks</h3><ul class="ls ls--ev">{evl}</ul></div>
    </div>
  </section>'''.format(
    s=D["slug"], d=D["date"], dd=D["date"].day, o=D["o"], h=D["h"], l=D["l"], c=D["c"],
    mj=D["maj"], mn=D["minr"], bo=D["bos"], ch=D["choch"], img=D["img"],
    segl="".join(
        '<li><span class="reg reg--{k}">{r}</span><span class="v">{a}&ndash;{b}</span>'
        '<span class="t">{t1}&ndash;{t2}</span></li>'.format(
            k=g["regime"].lower(), r=g["regime"], a=g["start"] + 1,
            b=min(g["end"], D["n"] - 1) + 1,
            t1=D["bars"][g["start"]]["t"][11:16],
            t2=D["bars"][min(g["end"], D["n"] - 1)]["t"][11:16])
        for g in D["segs"]),
    evl="".join(
        '<li><span class="v">b{i}</span><span class="{c}">{k} {ar}</span>'
        '<span class="v">{lv:.2f}</span></li>'.format(
            i=e["i"] + 1, c="choch" if e["kind"] == "ChoCh" else "bos", k=e["kind"],
            ar="&uarr;" if e["dir"] == "up" else "&darr;", lv=e["level"])
        for e in D["ev"])) for D in days)

CSS = """
:root{--paper:#faf8f4;--surface:#fff;--ink:#17140e;--body:#3c372e;--muted:#77705f;
 --rule:#e4dfd3;--soft:#efebe1;--bull:#0f8a10;--bear:#c33a3a;--range:#c98500;
 --shadow:0 1px 2px rgba(23,20,14,.05),0 8px 24px rgba(23,20,14,.06)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --paper:#14120e;--surface:#1c1a15;--ink:#f6f2e9;--body:#ccc5b6;--muted:#938b78;
 --rule:#2e2b23;--soft:#26231c;--bull:#35b436;--bear:#e46a6a;--range:#e2a52a;
 --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35)}}
:root[data-theme="dark"]{--paper:#14120e;--surface:#1c1a15;--ink:#f6f2e9;--body:#ccc5b6;
 --muted:#938b78;--rule:#2e2b23;--soft:#26231c;--bull:#35b436;--bear:#e46a6a;--range:#e2a52a;
 --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35)}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--body);
 font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:15.5px;line-height:1.6;
 -webkit-font-smoothing:antialiased}
.wrap{max-width:1240px;margin:0 auto;padding-block:52px 88px;padding-inline:24px}
.v,.t,.meta,.eyebrow,.day,.mix,.ticks,h3,.shape,th,.sl{font-family:"IBM Plex Mono",ui-monospace,monospace}
.eyebrow{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 13px}
h1{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:clamp(28px,4vw,40px);
 line-height:1.14;color:var(--ink);margin:0 0 14px;letter-spacing:-.01em;text-wrap:balance}
h2{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:22px;color:var(--ink);margin:0;text-wrap:balance}
.standfirst{font-size:16.5px;max-width:66ch;margin:0 0 32px}
.standfirst b{color:var(--ink);font-weight:600}
.tape{background:var(--surface);border:1px solid var(--rule);box-shadow:var(--shadow);
 padding:16px 20px 8px;margin:0 0 14px}
.row{display:grid;grid-template-columns:104px minmax(0,1fr) 148px;align-items:center;gap:16px;
 padding:5px 0;text-decoration:none;color:inherit}
.row:hover .day b,.row:focus-visible .day b{color:var(--ink);text-decoration:underline}
.row:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
.day{font-size:12.5px;color:var(--body);white-space:nowrap}
.day b{font-weight:600}
.day i{font-style:normal;color:var(--muted)}
.ribbon{display:flex;height:20px;overflow:hidden;border-radius:2px;background:var(--soft)}
.seg{flex-grow:0;flex-shrink:0;height:100%;box-shadow:inset -1px 0 0 var(--surface)}
.seg--bull{background:color-mix(in srgb,var(--bull) 62%,var(--surface))}
.seg--bear{background:color-mix(in srgb,var(--bear) 62%,var(--surface))}
.seg--range{background:color-mix(in srgb,var(--range) 30%,var(--surface))}
.mix{font-size:12.5px;font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--body);
 display:flex;align-items:center;gap:5px;justify-content:flex-end}
.k{display:inline-block;width:9px;height:9px;border-radius:1px;margin-left:8px}
.k--bull{background:var(--bull)}.k--bear{background:var(--bear)}.k--range{background:var(--range)}
.ticks{position:relative;height:18px;margin:2px 164px 0 120px;font-size:10.5px;color:var(--muted)}
.ticks span{position:absolute;top:2px;transform:translateX(-50%)}
.legend{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;color:var(--muted);margin:0 0 48px}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend .k{margin:0}
.tbl{overflow-x:auto;margin:0 0 20px}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:720px}
th,td{text-align:left;padding:7px 14px 7px 0;border-bottom:1px solid var(--soft);white-space:nowrap}
thead th{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:500}
td a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--rule)}
td a:hover{border-color:var(--ink)}
.v{font-variant-numeric:tabular-nums;color:var(--ink)}
.sl{color:var(--muted)}
.shape{font-size:12px;letter-spacing:.02em}
.shape b{font-weight:600;margin-right:7px}
.t{font-size:12.5px;color:var(--muted)}
.day-sec{border-top:1px solid var(--rule);padding-top:36px;margin-bottom:26px;scroll-margin-top:16px}
.dh{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:6px 24px;margin:0 0 16px}
.meta{margin:0;font-size:12.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.sep{color:var(--rule);margin:0 4px}
.shot{display:block;width:100%;padding:0;border:1px solid var(--rule);background:var(--surface);
 cursor:zoom-in;position:relative;box-shadow:var(--shadow);margin:0 0 22px}
.shot img{display:block;width:100%;height:auto}
.hint{position:absolute;right:10px;bottom:10px;font-family:"IBM Plex Mono",monospace;font-size:10.5px;
 letter-spacing:.08em;text-transform:uppercase;background:var(--surface);color:var(--muted);
 border:1px solid var(--rule);padding:4px 9px;opacity:0;transition:opacity .18s}
.shot:hover .hint,.shot:focus-visible .hint{opacity:1}
.shot:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
.lists{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr);gap:32px}
h3{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:500;
 margin:0 0 8px;padding-bottom:7px;border-bottom:1px solid var(--rule)}
.ls{list-style:none;margin:0;padding:0;font-size:13.5px}
.ls li{display:grid;grid-template-columns:62px 72px 1fr;gap:10px;padding:4px 0;border-bottom:1px solid var(--soft)}
.ls--ev{columns:2;column-gap:28px}
.ls--ev li{grid-template-columns:40px 86px 1fr;break-inside:avoid}
.reg{font-weight:600}
.reg--bull{color:var(--bull)}.reg--bear{color:var(--bear)}.reg--range{color:var(--range)}
.bos{color:var(--ink);font-weight:600}.choch{color:var(--bear);font-weight:600}
#lb{position:fixed;inset:0;background:rgba(10,8,5,.92);z-index:50;padding:22px;overflow:auto;cursor:zoom-out}
#lb img{display:block;margin:0 auto;max-width:none;width:auto}
#lb .close{position:fixed;top:calc(14px + env(safe-area-inset-top,0px));right:18px;
 font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.1em;text-transform:uppercase;
 color:#efe9dc;background:rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.28);padding:7px 13px;cursor:pointer}
@media (max-width:760px){
 .row{grid-template-columns:minmax(0,1fr);gap:4px}
 .mix{justify-content:flex-start}.mix .k:first-child{margin-left:0}
 .ticks{margin:2px 0 0}
 .lists{grid-template-columns:minmax(0,1fr)}
 .ls--ev{columns:1}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = """
const lb=document.createElement("div");lb.id="lb";lb.hidden=true;
lb.innerHTML='<button class="close">Close &middot; Esc</button><img alt="">';
document.body.appendChild(lb);const im=lb.querySelector("img");
document.querySelectorAll(".shot").forEach(function(b){b.addEventListener("click",function(){
 var s=document.getElementById(b.dataset.full);im.src=s.src;im.alt=s.alt;lb.hidden=false;
 document.body.style.overflow="hidden";lb.querySelector(".close").focus();});});
function cl(){lb.hidden=true;im.src="";document.body.style.overflow="";}
lb.addEventListener("click",cl);
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&!lb.hidden)cl();});
"""

HTML = f"""<title>ES Regime Reference Sessions</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>{CSS}</style>

<div class="wrap">
  <p class="eyebrow">Regime tracker &middot; ES 5-minute &middot; Market Structure rules</p>
  <h1>ES Regime Reference Sessions</h1>
  <p class="standfirst">All {len(days)} sessions on disk, one run of the current engine.
  Each tape row is a full session &mdash; 81 bars, 08:30 to 15:10. Click a row or a date to
  jump to its chart; click a chart to enlarge it.</p>

  <div class="tape">{tape}
    <div class="ticks" aria-hidden="true">{ticks}</div>
  </div>
  <div class="legend">
    <span><i class="k k--bull"></i>Bull</span>
    <span><i class="k k--bear"></i>Bear</span>
    <span><i class="k k--range"></i>Range</span>
    <span>Right-hand figures are bars spent in each state</span>
  </div>

  <div class="tbl">
    <table>
      <thead><tr><th>Session</th><th>Open</th><th>High</th><th>Low</th><th>Close</th>
      <th>Maj/min</th><th>BOS</th><th>ChoCh</th><th>Shape</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
{sections}
</div>

<script>{JS}</script>
"""
OUT.write_text(HTML, encoding="utf-8")
print("wrote", OUT, "%.1f MB" % (OUT.stat().st_size / 1e6))
