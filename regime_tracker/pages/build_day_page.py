#!/usr/bin/env python3
"""Build a single-session regime artifact page."""
import base64, json, pathlib

import sys

_HERE = pathlib.Path(__file__).resolve().parent
SRC = _HERE.parent                       # regime_tracker/ -- JSONs and PNGs
OUT_DIR = _HERE / "out"                  # generated pages (git-ignored)
OUT_DIR.mkdir(exist_ok=True)


OUT = OUT_DIR / "es_regime_0625.html"
SLUG = "20260625"

d = json.load(open(SRC / f"regime_data_es_{SLUG}.json"))
bars = d["bars"]
ml = sum(1 for p in d["pivot_lows"] if p["major"])
mh = sum(1 for p in d["pivot_highs"] if p["major"])
mn = (len(d["pivot_lows"]) - ml) + (len(d["pivot_highs"]) - mh)
ev = d["events"]
nbos = sum(1 for e in ev if e["kind"] == "BOS")
nchoch = sum(1 for e in ev if e["kind"] == "ChoCh")

o = bars[0]["o"]
hi = max(b["h"] for b in bars)
lo = min(b["l"] for b in bars)
cl = bars[-1]["c"]

seg_rows = "".join(
    '<tr><td class="reg reg--{k}">{r}</td><td class="v">{a}</td><td class="v">{b}</td>'
    '<td class="t">{t1} &ndash; {t2}</td></tr>'.format(
        k=s["regime"].lower(), r=s["regime"], a=s["start"] + 1,
        b=min(s["end"], len(bars) - 1) + 1,
        t1=bars[s["start"]]["t"][11:16],
        t2=bars[min(s["end"], len(bars) - 1)]["t"][11:16])
    for s in d["segments"])

ev_rows = "".join(
    '<tr><td class="v">{i}</td><td class="{c}">{k}</td><td>{a}</td><td class="v">{lv:.2f}</td></tr>'.format(
        i=e["i"] + 1, c="choch" if e["kind"] == "ChoCh" else "bos", k=e["kind"],
        a="&uarr;" if e["dir"] == "up" else "&darr;", lv=e["level"])
    for e in ev)

img = base64.b64encode((SRC / f"ms_chart_{SLUG}.png").read_bytes()).decode()

CSS = """
 :root { --paper:#faf8f4; --surface:#fff; --ink:#17140e; --body:#3c372e; --muted:#77705f;
   --rule:#e4dfd3; --soft:#efebe1; --bull:#0f8a10; --bear:#c33a3a; --range:#c98500;
   --shadow:0 1px 2px rgba(23,20,14,.05),0 8px 24px rgba(23,20,14,.06); }
 @media (prefers-color-scheme:dark) { :root:not([data-theme="light"]) {
   --paper:#14120e; --surface:#1c1a15; --ink:#f6f2e9; --body:#ccc5b6; --muted:#938b78;
   --rule:#2e2b23; --soft:#26231c; --bull:#35b436; --bear:#e46a6a; --range:#e2a52a;
   --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35); } }
 :root[data-theme="dark"] { --paper:#14120e; --surface:#1c1a15; --ink:#f6f2e9; --body:#ccc5b6;
   --muted:#938b78; --rule:#2e2b23; --soft:#26231c; --bull:#35b436; --bear:#e46a6a;
   --range:#e2a52a; --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35); }
 *{box-sizing:border-box}
 body{margin:0;background:var(--paper);color:var(--body);
   font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:15.5px;line-height:1.6;
   -webkit-font-smoothing:antialiased}
 .wrap{max-width:1180px;margin:0 auto;padding:52px 28px 80px}
 .eyebrow{font-family:"IBM Plex Mono",monospace;font-size:11.5px;letter-spacing:.14em;
   text-transform:uppercase;color:var(--muted);margin:0 0 13px}
 h1{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:clamp(28px,4vw,40px);
   line-height:1.14;color:var(--ink);margin:0 0 14px;letter-spacing:-.01em}
 .standfirst{font-size:16.5px;max-width:62ch;margin:0 0 36px}
 .standfirst b{color:var(--ink);font-weight:600}
 .ohlc{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;
   background:var(--rule);border:1px solid var(--rule);margin:0 0 40px}
 .ohlc div{background:var(--surface);padding:14px 16px}
 .ohlc .n{display:block;font-family:"IBM Plex Mono",monospace;font-size:20px;font-weight:600;
   color:var(--ink);font-variant-numeric:tabular-nums}
 .ohlc .l{display:block;font-size:12px;color:var(--muted);margin-top:3px}
 .shot{display:block;width:100%;padding:0;border:1px solid var(--rule);background:var(--surface);
   cursor:zoom-in;position:relative;box-shadow:var(--shadow);margin:0 0 40px}
 .shot img{display:block;width:100%;height:auto}
 .hint{position:absolute;right:10px;bottom:10px;font-family:"IBM Plex Mono",monospace;
   font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;background:var(--surface);
   color:var(--muted);border:1px solid var(--rule);padding:4px 9px;opacity:0;
   transition:opacity .18s}
 .shot:hover .hint,.shot:focus-visible .hint{opacity:1}
 .shot:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
 .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:36px}
 h2{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:19px;color:var(--ink);
   margin:0 0 4px}
 hr.r{border:0;border-top:1px solid var(--rule);margin:0 0 14px}
 table{border-collapse:collapse;width:100%;font-size:14px}
 th,td{text-align:left;padding:7px 12px 7px 0;border-bottom:1px solid var(--soft)}
 thead th{font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.1em;
   text-transform:uppercase;color:var(--muted);font-weight:500}
 td.v{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;color:var(--ink)}
 td.t{font-family:"IBM Plex Mono",monospace;font-size:13px;color:var(--muted)}
 td.reg{font-weight:600}
 .reg--bull{color:var(--bull)} .reg--bear{color:var(--bear)} .reg--range{color:var(--range)}
 td.bos{color:var(--ink);font-weight:600} td.choch{color:var(--bear);font-weight:600}
 .note{border-left:2px solid var(--range);padding:2px 0 2px 16px;max-width:70ch;margin-top:40px}
 .note p{margin:0;font-size:14.5px}
 #lb{position:fixed;inset:0;background:rgba(10,8,5,.92);z-index:50;padding:22px;overflow:auto;
   cursor:zoom-out}
 #lb img{display:block;margin:0 auto;max-width:none;width:auto}
 #lb .close{position:fixed;top:14px;right:18px;font-family:"IBM Plex Mono",monospace;
   font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#efe9dc;
   background:rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.28);padding:7px 13px;
   cursor:pointer}
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

HTML = f"""<title>ES Regime 25 June 2026</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>{CSS}</style>

<div class="wrap">
  <p class="eyebrow">Regime tracker &middot; ES 5-minute &middot; BOS / ChoCh</p>
  <h1>ES Regime 25 June 2026</h1>
  <p class="standfirst">A distribution session: opened near the high, gave a short morning
  uptrend, then spent the middle of the day in one <b>Bear</b> structure down to 7390.50.
  The afternoon recovery stalled and rolled into a second Bear leg from bar 69.</p>

  <div class="ohlc">
    <div><span class="n">{o:.2f}</span><span class="l">open</span></div>
    <div><span class="n">{hi:.2f}</span><span class="l">high</span></div>
    <div><span class="n">{lo:.2f}</span><span class="l">low</span></div>
    <div><span class="n">{cl:.2f}</span><span class="l">close</span></div>
    <div><span class="n">{ml+mh} / {mn}</span><span class="l">majors / minors</span></div>
    <div><span class="n">{nbos} / {nchoch}</span><span class="l">BOS / ChoCh</span></div>
  </div>

  <button class="shot" data-full="big" aria-label="Enlarge chart">
    <img id="big" src="data:image/png;base64,{img}" alt="ES regime chart for 25 June 2026">
    <span class="hint">Click to enlarge</span>
  </button>

  <div class="cols">
    <section>
      <h2>Regimes</h2><hr class="r">
      <table><thead><tr><th>State</th><th>From</th><th>To</th><th>Time</th></tr></thead>
      <tbody>{seg_rows}</tbody></table>
    </section>
    <section>
      <h2>Structural breaks</h2><hr class="r">
      <table><thead><tr><th>Bar</th><th>Event</th><th>Dir</th><th>Level</th></tr></thead>
      <tbody>{ev_rows}</tbody></table>
    </section>
  </div>

  <div class="note">
    <p>The main Bear structure survives the whole 11:00&ndash;11:30 bounce to 7460 &mdash; that
    never took out the relevant lower high, so no ChoCh fired.</p>
    <p style="margin-top:10px">The <b>bar 69</b> entry is the setup the document draws: a high at
    bar 60 (7456.75), its low at bar 64 (7422.25), then a lower high at bar 65 (7439.50) &mdash;
    and the BOS breaks bar 64's low, not whatever swing happened last. Bar 67's low of 7422.75
    fails to break 7422.25, so it stays a minor pivot and does not reset the setup.</p>
  </div>
</div>

<script>{JS}</script>
"""

OUT.write_text(HTML, encoding="utf-8")
print("wrote", OUT, "%.0f KB" % (OUT.stat().st_size / 1024))
