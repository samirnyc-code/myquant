#!/usr/bin/env python3
"""Week-of-18-May regime page: regime tape + one section per session."""
import base64, json, pathlib, datetime as dt

import sys

_HERE = pathlib.Path(__file__).resolve().parent
SRC = _HERE.parent                       # regime_tracker/ -- JSONs and PNGs
OUT_DIR = _HERE / "out"                  # generated pages (git-ignored)
OUT_DIR.mkdir(exist_ok=True)


OUT = OUT_DIR / "es_regime_reconciled.html"
DAYS = ["20260213", "20251226", "20260519", "20260521"]

NOTES = {
 "20260213": """<b>Bar 9 now fires.</b> Bar 6's high (6966.25) never reached bar 4's 6973.75,
  so the bar collapses to the low it closed toward &mdash; restoring the b3&ndash;b4&ndash;b6
  structure and the BOS over bar 4's high at 6975.00.""",
 "20251226": """<b>One Bear, bars 21 to 53</b>, in place of five flips. Bar 16's high (7095.50)
  fails against bar 13's 7097.75, so the bullish bar keeps its high and drops its low &mdash;
  and the old bar-17 Bear, which was a break of that low, never happens.""",
 "20260519": """<b>Bear from bar 16</b> rather than a one-bar Bull at 15. Bar 13's high
  (7433.75) was the level the old bar-15 BOS broke; it fails to extend, so the bearish bar
  keeps only its low. The afternoon Bear from bar 52 is unaffected.""",
 "20260521": """<b>Unchanged: Bull still opens at bar 28.</b> Bar 21 made new ground at both
  ends &mdash; a new session low and a high 0.75 above bar 18's &mdash; so both swings stand,
  bar 21's low keeps the premature bar-23 signal suppressed, and the break of bar 23's high
  at bar 28 is the one that counts.""",
}


def tm(b, i):
    return b[i]["t"][11:16]


days = []
for s in DAYS:
    d = json.load(open(SRC / f"regime_data_es_{s}.json"))
    b = d["bars"]
    n = len(b)
    ml = sum(p["major"] for p in d["pivot_lows"])
    mh = sum(p["major"] for p in d["pivot_highs"])
    mn = len(d["pivot_lows"]) + len(d["pivot_highs"]) - ml - mh
    ev = d["events"]
    segs = d["segments"]
    ribbon, counts = [], {"Bull": 0, "Bear": 0, "Range": 0}
    for k, g in enumerate(segs):
        a = g["start"]
        z = segs[k + 1]["start"] if k + 1 < len(segs) else n
        last = min(z, n) - 1 if k + 1 == len(segs) else z
        counts[g["regime"]] += z - a
        ribbon.append(dict(
            r=g["regime"], w=(z - a) / n * 100,
            tip=f'{g["regime"]} · bar {a+1}–{last+1} · {tm(b, a)}–{tm(b, last)}'))
    days.append(dict(
        s=s, date=dt.date(int(s[:4]), int(s[4:6]), int(s[6:])), b=b, n=n, segs=segs, ev=ev,
        ribbon=ribbon, counts=counts, maj=ml + mh, mn=mn,
        nb=sum(e["kind"] == "BOS" for e in ev), nc=sum(e["kind"] == "ChoCh" for e in ev),
        o=b[0]["o"], h=max(x["h"] for x in b), l=min(x["l"] for x in b), c=b[-1]["c"],
        img=base64.b64encode((SRC / f"ms_chart_{s}.png").read_bytes()).decode()))

# --- regime tape ---
TICKS = [("09:00", 7), ("10:00", 19), ("11:00", 31), ("12:00", 43),
         ("13:00", 55), ("14:00", 67), ("15:00", 79)]
tape_rows = []
for D in days:
    cells = "".join(
        f'<span class="seg seg--{g["r"].lower()}" style="flex-basis:{g["w"]:.3f}%" '
        f'title="{g["tip"]}"></span>' for g in D["ribbon"])
    c = D["counts"]
    tape_rows.append(f'''
    <a class="row" href="#d{D["s"]}" role="listitem">
      <span class="day"><b>{D["date"]:%d %b}</b></span>
      <span class="ribbon" aria-label="Regime sequence for {D["date"]:%A}">{cells}</span>
      <span class="mix"><i class="k k--bull"></i>{c["Bull"]}<i class="k k--bear"></i>{c["Bear"]}<i class="k k--range"></i>{c["Range"]}</span>
    </a>''')
ticks = "".join(f'<span style="left:{(bar - 1) / 81 * 100:.2f}%">{t}</span>' for t, bar in TICKS)


def seg_list(D):
    b, n = D["b"], D["n"]
    out = []
    for g in D["segs"]:
        a, e = g["start"], min(g["end"], n - 1)
        out.append(f'<li><span class="reg reg--{g["regime"].lower()}">{g["regime"]}</span>'
                   f'<span class="v">{a+1}&ndash;{e+1}</span>'
                   f'<span class="t">{tm(b, a)}&ndash;{tm(b, e)}</span></li>')
    return "".join(out)


def ev_list(D):
    return "".join(
        f'<li><span class="v">b{e["i"]+1}</span>'
        f'<span class="{"choch" if e["kind"] == "ChoCh" else "bos"}">'
        f'{e["kind"]} {"&uarr;" if e["dir"] == "up" else "&darr;"}</span>'
        f'<span class="v">{e["level"]:.2f}</span></li>'
        for e in D["ev"])


sections = []
for D in days:
    sections.append(f'''
  <section class="day-sec" id="d{D["s"]}">
    <header class="dh">
      <h2>{D["date"]:%A %d %B %Y}</h2>
      <p class="meta">O {D["o"]:.2f} · H {D["h"]:.2f} · L {D["l"]:.2f} · C {D["c"]:.2f}
        <span class="sep">|</span> {D["maj"]} major / {D["mn"]} minor
        <span class="sep">|</span> {D["nb"]} BOS / {D["nc"]} ChoCh</p>
    </header>
    <p class="lede">{NOTES[D["s"]]}</p>
    <button class="shot" data-full="img{D["s"]}" aria-label="Enlarge chart for {D["date"]:%A %d %B}">
      <img id="img{D["s"]}" src="data:image/png;base64,{D["img"]}" alt="ES 5-minute regime chart, {D["date"]:%d %B %Y}">
      <span class="hint">Click to enlarge</span>
    </button>
    <div class="lists">
      <div><h3>Regimes</h3><ul class="ls">{seg_list(D)}</ul></div>
      <div><h3>Structural breaks</h3><ul class="ls ls--ev">{ev_list(D)}</ul></div>
    </div>
  </section>''')

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
.wrap{max-width:1180px;margin:0 auto;padding-block:52px 88px;padding-inline:24px}
.v,.t,.meta,.eyebrow,.day,.mix,.ticks,h3,.flag .where{font-family:"IBM Plex Mono",ui-monospace,monospace}
.eyebrow{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 13px}
h1{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:clamp(28px,4vw,40px);
 line-height:1.14;color:var(--ink);margin:0 0 14px;letter-spacing:-.01em;text-wrap:balance}
h2{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:23px;color:var(--ink);margin:0;text-wrap:balance}
.standfirst{font-size:16.5px;max-width:64ch;margin:0 0 34px}
.standfirst b,.lede b,.flag b{color:var(--ink);font-weight:600}

/* regime tape */
.tape{background:var(--surface);border:1px solid var(--rule);box-shadow:var(--shadow);
 padding:18px 20px 10px;margin:0 0 16px}
.row{display:grid;grid-template-columns:92px minmax(0,1fr) 150px;align-items:center;gap:16px;
 padding:7px 0;text-decoration:none;color:inherit}
.row:hover .day b,.row:focus-visible .day b{color:var(--ink);text-decoration:underline}
.row:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
.day{font-size:13px;color:var(--muted);white-space:nowrap}
.day b{font-weight:600;color:var(--body);margin-right:4px}
.ribbon{display:flex;height:22px;overflow:hidden;border-radius:2px;background:var(--soft)}
.seg{flex-grow:0;flex-shrink:0;height:100%;box-shadow:inset -1px 0 0 var(--surface)}
.seg--bull{background:color-mix(in srgb,var(--bull) 62%,var(--surface))}
.seg--bear{background:color-mix(in srgb,var(--bear) 62%,var(--surface))}
.seg--range{background:color-mix(in srgb,var(--range) 30%,var(--surface))}
.mix{font-size:12.5px;color:var(--body);font-variant-numeric:tabular-nums;white-space:nowrap;
 display:flex;align-items:center;gap:5px;justify-content:flex-end}
.k{display:inline-block;width:9px;height:9px;border-radius:1px;margin-left:8px}
.k--bull{background:var(--bull)}.k--bear{background:var(--bear)}.k--range{background:var(--range)}
.ticks{position:relative;height:20px;margin:2px 166px 0 108px;font-size:10.5px;color:var(--muted)}
.ticks span{position:absolute;top:2px;transform:translateX(-50%)}
.legend{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;color:var(--muted);margin:0 0 56px}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend .k{margin:0}

/* flags */
.flags{border-top:1px solid var(--rule);padding-top:26px;margin:0 0 64px}
.flags h2{margin-bottom:6px}
.flags>p{max-width:66ch;margin:0 0 18px}
.flag{display:grid;grid-template-columns:128px minmax(0,1fr);gap:6px 22px;padding:16px 0;border-top:1px solid var(--soft)}
.flag .where{font-size:13px;color:var(--ink);font-weight:600}
.flag .where small{display:block;font-weight:400;color:var(--muted);font-size:12px;margin-top:2px}
.flag p{margin:0;max-width:70ch;font-size:14.5px}
.flag p+p{margin-top:8px}
.flag .ask{color:var(--ink)}

/* day sections */
.day-sec{padding-top:40px;border-top:1px solid var(--rule);margin-bottom:24px;scroll-margin-top:16px}
.dh{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:6px 24px;margin:0 0 10px}
.meta{margin:0;font-size:12.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.sep{color:var(--rule);margin:0 4px}
.lede{max-width:70ch;margin:0 0 20px;font-size:15px}
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
.ls li{display:grid;grid-template-columns:62px 70px 1fr;gap:10px;padding:4px 0;border-bottom:1px solid var(--soft)}
.ls--ev{columns:2;column-gap:28px}
.ls--ev li{grid-template-columns:40px 84px 1fr;break-inside:avoid}
.v{font-variant-numeric:tabular-nums;color:var(--ink)}
.t{font-size:12.5px;color:var(--muted)}
.reg{font-weight:600}.reg--bull{color:var(--bull)}.reg--bear{color:var(--bear)}.reg--range{color:var(--range)}
.bos{color:var(--ink);font-weight:600}.choch{color:var(--bear);font-weight:600}

#lb{position:fixed;inset:0;background:rgba(10,8,5,.92);z-index:50;padding:22px;overflow:auto;cursor:zoom-out}
#lb img{display:block;margin:0 auto;max-width:none;width:auto}
#lb .close{position:fixed;top:calc(14px + env(safe-area-inset-top,0px));right:18px;font-family:"IBM Plex Mono",monospace;
 font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#efe9dc;background:rgba(0,0,0,.5);
 border:1px solid rgba(255,255,255,.28);padding:7px 13px;cursor:pointer}

@media (max-width:760px){
 .row{grid-template-columns:minmax(0,1fr);gap:5px}
 .mix{justify-content:flex-start}
 .mix .k:first-child{margin-left:0}
 .ticks{margin:2px 0 0}
 .flag{grid-template-columns:minmax(0,1fr)}
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

HTML = f"""<title>Outside Bars Reconciled</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>{CSS}</style>

<div class="wrap">
  <p class="eyebrow">Regime tracker &middot; ES 5-minute &middot; after the outside-bar rule</p>
  <h1>Outside Bars Reconciled</h1>
  <p class="standfirst">One rule now covers all four readings you asked for. Of the twelve
  sessions on disk these are the only ones that differ from the committed version; the
  other eight are byte-identical.</p>

  <div class="tape" role="list">{"".join(tape_rows)}
    <div class="ticks" aria-hidden="true">{ticks}</div>
  </div>
  <div class="legend">
    <span><i class="k k--bull"></i>Bull</span>
    <span><i class="k k--bear"></i>Bear</span>
    <span><i class="k k--range"></i>Range</span>
    <span>Right-hand figures are bars spent in each state</span>
  </div>

  <section class="flags">
    <h2>The rule</h2>
    <p>mywedge marks an outside bar as both a swing high and a swing low. Whether that bar
    counts as one swing or two turns on whether it <b>extended</b> the structure at both
    ends &mdash; ran past the last swing of its own kind on each side.</p>

    <div class="flag">
      <div class="where">Both ends<small>keep both</small></div>
      <div>
        <p>The bar genuinely made new ground in both directions, so both swings stand.
        <b>05-21 bar 21</b> is the case: a new session low, and a high 0.75 above bar 18's.
        Keeping its low is what stops a premature signal at bar 23.</p>
      </div>
    </div>

    <div class="flag">
      <div class="where">One end<small>keep the close side</small></div>
      <div>
        <p>The bar is one move with an overshoot attached, and collapses to the extreme it
        <b>left on</b>, from <code>bar_dir</code>. The other end never turned anything &mdash;
        it just splits the pullback around it and inverts the higher-low test.</p>
        <p><b>02-13 b6</b> and <b>05-19 b13</b> are bearish and keep their lows;
        <b>12-26 b16</b> is bullish and keeps its high. In all three the opposite end had
        failed to clear the previous swing of its own kind.</p>
      </div>
    </div>
  </section>
{"".join(sections)}
</div>

<script>{JS}</script>
"""
OUT.write_text(HTML, encoding="utf-8")
print("wrote", OUT, "%.0f KB" % (OUT.stat().st_size / 1024))
