#!/usr/bin/env python3
"""Before/after page for the three sessions the outside-bar fix moved."""
import base64, json, pathlib, datetime as dt

import sys

_HERE = pathlib.Path(__file__).resolve().parent
SRC = _HERE.parent                       # regime_tracker/ -- JSONs and PNGs
OUT_DIR = _HERE / "out"                  # generated pages (git-ignored)
OUT_DIR.mkdir(exist_ok=True)


SCR = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else _HERE / "_baseline")
OUT = OUT_DIR / "es_regime_outside_bar_delta.html"
DAYS = ["20251226", "20260519", "20260521"]

NOTES = {
 "20251226": """The one that matters. The old reading whipsawed five times between bars 17
  and 53; the new one holds a single <b>Bear</b> from bar 21 all the way to bar 53. The
  trigger is bar 16, a bullish outside bar whose low (7091.75) used to enter the structure
  as its own swing &mdash; the old Bear at bar 17 was a break of that low. With the bar
  contributing only its high, the Bear waits for bar 21 to take out bar 17's low at
  7091.50, four bars later and one whipsaw fewer.""",
 "20260519": """A one-bar Bull at 15 becomes a three-bar Bear at 16. Bar 13 is a bearish
  outside bar; its high (7433.75) was the level the old bar-15 BOS broke. Keeping only the
  low means no bull setup exists there, and the move that follows is read as what it looks
  like on the chart &mdash; down. The afternoon <b>Bear</b> from bar 52 is identical either
  way.""",
 "20260521": """Bull starts five bars earlier, at 23 instead of 28. Bar 21 is the session low
  (7469.75) on a bullish outside bar, so the bar now enters the structure as its high
  (7492.00). The low is still marked major on the chart; it just no longer acts as a swing
  that splits the recovery. Two extra breaks appear at bars 77&ndash;78 in the closing
  chop.""",
}
HEADLINE = {
 "20251226": ("Five regime flips become one Bear", "bar 16"),
 "20260519": ("A one-bar Bull becomes a three-bar Bear", "bar 13"),
 "20260521": ("Bull starts five bars earlier", "bar 21"),
}


def b64(p):
    return base64.b64encode(pathlib.Path(p).read_bytes()).decode()


def segline(d, n):
    return " &rarr; ".join(
        f'<span class="reg reg--{g["regime"].lower()}">{g["regime"]}&thinsp;{g["start"]+1}</span>'
        for g in d["segments"])


sections = []
for s in DAYS:
    new = json.load(open(SRC / f"regime_data_es_{s}.json"))
    old = json.load(open(SCR / "prev" / f"regime_data_es_{s}.json"))
    n = len(new["bars"])
    date = dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    head, trigger = HEADLINE[s]
    oe = {(e["i"], e["kind"], e["dir"], e["level"]) for e in old["events"]}
    ne = {(e["i"], e["kind"], e["dir"], e["level"]) for e in new["events"]}
    gained = "".join(f'<li><span class="v">b{i+1}</span><span class="{"choch" if k=="ChoCh" else "bos"}">{k} {"&uarr;" if dr=="up" else "&darr;"}</span><span class="v">{lv:.2f}</span></li>'
                     for i, k, dr, lv in sorted(ne - oe))
    lost = "".join(f'<li><span class="v">b{i+1}</span><span class="{"choch" if k=="ChoCh" else "bos"}">{k} {"&uarr;" if dr=="up" else "&darr;"}</span><span class="v">{lv:.2f}</span></li>'
                   for i, k, dr, lv in sorted(oe - ne))
    sections.append(f'''
  <section class="day">
    <header>
      <p class="kicker">{date:%A} {date.day} {date:%B} %s trigger: {trigger}</p>
      <h2>{head}</h2>
    </header>
    <p class="lede">{NOTES[s]}</p>

    <div class="seqs">
      <div class="seq"><h3>Before</h3><p>{segline(old, n)}</p></div>
      <div class="seq seq--new"><h3>After</h3><p>{segline(new, n)}</p></div>
    </div>

    <div class="pair">
      <figure>
        <figcaption>Before</figcaption>
        <button class="shot" data-full="o{s}" aria-label="Enlarge the before chart for {date:%d %B}">
          <img id="o{s}" src="data:image/png;base64,{b64(SCR / "prev" / f"ms_chart_{s}_before.png")}" alt="Previous regime reading, {date:%d %B %Y}">
        </button>
      </figure>
      <figure>
        <figcaption>After</figcaption>
        <button class="shot" data-full="n{s}" aria-label="Enlarge the after chart for {date:%d %B}">
          <img id="n{s}" src="data:image/png;base64,{b64(SRC / f"ms_chart_{s}.png")}" alt="New regime reading, {date:%d %B %Y}">
        </button>
      </figure>
    </div>

    <div class="evs">
      <div><h3>Gained</h3><ul class="ls">{gained or '<li class="none">nothing</li>'}</ul></div>
      <div><h3>Lost</h3><ul class="ls">{lost or '<li class="none">nothing</li>'}</ul></div>
    </div>
  </section>''' % "&middot;")

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
.kicker,.v,h3,figcaption,.eyebrow,.reg{font-family:"IBM Plex Mono",ui-monospace,monospace}
.eyebrow{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 13px}
h1{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:clamp(28px,4vw,40px);
 line-height:1.14;color:var(--ink);margin:0 0 14px;letter-spacing:-.01em;text-wrap:balance}
h2{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:22px;color:var(--ink);
 margin:0;text-wrap:balance}
.standfirst{font-size:16.5px;max-width:66ch;margin:0 0 20px}
.standfirst b{color:var(--ink);font-weight:600}
.rule-note{border-left:2px solid var(--range);padding:4px 0 4px 16px;max-width:70ch;margin:0 0 52px}
.rule-note p{margin:0;font-size:14.5px}
.rule-note p+p{margin-top:8px}
.rule-note b{color:var(--ink)}
.day{border-top:1px solid var(--rule);padding-top:34px;margin-bottom:56px}
.kicker{font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
.lede{max-width:72ch;margin:12px 0 22px}
.lede b{color:var(--ink);font-weight:600}
.seqs{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1px;
 background:var(--rule);border:1px solid var(--rule);margin:0 0 24px}
.seq{background:var(--surface);padding:13px 16px}
.seq p{margin:0;font-size:13px;line-height:2}
.seq--new{background:color-mix(in srgb,var(--range) 7%,var(--surface))}
h3{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);
 font-weight:500;margin:0 0 7px}
.reg{font-weight:600;white-space:nowrap}
.reg--bull{color:var(--bull)}.reg--bear{color:var(--bear)}.reg--range{color:var(--range)}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px;margin:0 0 24px}
figure{margin:0}
figcaption{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0 0 7px}
.shot{display:block;width:100%;padding:0;border:1px solid var(--rule);background:var(--surface);
 cursor:zoom-in;box-shadow:var(--shadow)}
.shot img{display:block;width:100%;height:auto}
.shot:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
.evs{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:28px}
.ls{list-style:none;margin:0;padding:0;font-size:13.5px}
.ls li{display:grid;grid-template-columns:42px 86px 1fr;gap:10px;padding:4px 0;
 border-bottom:1px solid var(--soft)}
.ls .none{display:block;color:var(--muted);border:0;font-style:italic}
.v{font-variant-numeric:tabular-nums;color:var(--ink)}
.bos{color:var(--ink);font-weight:600}.choch{color:var(--bear);font-weight:600}
#lb{position:fixed;inset:0;background:rgba(10,8,5,.92);z-index:50;padding:22px;overflow:auto;cursor:zoom-out}
#lb img{display:block;margin:0 auto;max-width:none;width:auto}
#lb .close{position:fixed;top:calc(14px + env(safe-area-inset-top,0px));right:18px;
 font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.1em;text-transform:uppercase;
 color:#efe9dc;background:rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.28);padding:7px 13px;cursor:pointer}
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

HTML = f"""<title>Outside Bar Fix Review</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>{CSS}</style>

<div class="wrap">
  <p class="eyebrow">Regime tracker &middot; rule change review</p>
  <h1>Outside Bar Fix Review</h1>
  <p class="standfirst">The 02-13 bar 9 fix moved three other sessions. Eight of the twelve
  on disk are byte-identical &mdash; 04-06, 06-25, 06-12, 01-13, 06-29, 05-18, 05-20 and
  05-22. These three are the ones to check before committing.</p>

  <div class="rule-note">
    <p><b>The rule.</b> An outside bar contributes one swing to the structure, not two.
    mywedge marks such a bar as both a swing high and a swing low; recorded as two separate
    swings they split a single pullback in half, so a pullback that ended higher than the
    one before it gets compared against its own other half and reads as a lower low.</p>
    <p>The bar now enters the structure as the extreme it left on, taken from
    <code>bar_dir</code> &mdash; the same signal already used to order the two extremes
    within a bar. Nothing else about pivots changes: both extremes are still plotted, and
    major/minor tagging is untouched.</p>
  </div>
{"".join(sections)}
</div>

<script>{JS}</script>
"""
OUT.write_text(HTML, encoding="utf-8")
print("wrote", OUT, "%.0f KB" % (OUT.stat().st_size / 1024))
