#!/usr/bin/env python3
"""Build the Market Structure model artifact with the six session charts embedded."""
import base64, json, pathlib, html

import sys

_HERE = pathlib.Path(__file__).resolve().parent
SRC = _HERE.parent                       # regime_tracker/ -- JSONs and PNGs
OUT_DIR = _HERE / "out"                  # generated pages (git-ignored)
OUT_DIR.mkdir(exist_ok=True)


OUT = OUT_DIR / "market_structure.html"
DAYS = [
    ("2026-02-13", "20260213", "Checked bar-for-bar against a hand-marked chart. Bull 12–43, ChoCh at bar 43 off the 6994.00 higher low, then Bear to the close — the ChoCh and the BOS chain both land where they were marked by hand."),
    ("2026-04-06", "20260406", "Three separate Bull legs with Range between them. Bar 23 no longer reads Bear — no pullback high had formed between the last low and the break, so no lower high existed to confirm one."),
    ("2026-06-12", "20260612", "Bull now starts at bar 43, not 39: at 39 the last swing was still a high, so the leg was simply running and no higher low had been put in."),
    ("2026-01-13", "20260113", "Bear 33–77 — the afternoon decline read as one structure, each new low a BOS, no ChoCh until the closing bounce."),
    ("2026-06-29", "20260629", "The cleanest trend of the six: Bull from bar 17 to the close on seven BOS, no ChoCh all session."),
    ("2025-12-26", "20251226", "Chop, and the model says so — five ChoCh, nothing holding more than six bars, Range between every leg."),
]


def stats(slug):
    d = json.load(open(SRC / f"regime_data_es_{slug}.json"))
    ml = sum(1 for p in d["pivot_lows"] if p["major"])
    mh = sum(1 for p in d["pivot_highs"] if p["major"])
    mn = (len(d["pivot_lows"]) - ml) + (len(d["pivot_highs"]) - mh)
    ev = d.get("events", [])
    segs = d["segments"]
    bars = d["bars"]
    line = " · ".join(
        f"{s['regime']} {s['start']+1}–{min(s['end'], len(bars)-1)+1}" for s in segs
    )
    return dict(majors=ml + mh, minors=mn, bos=sum(1 for e in ev if e["kind"] == "BOS"),
                choch=sum(1 for e in ev if e["kind"] == "ChoCh"), line=line)


def b64(name):
    return base64.b64encode((SRC / name).read_bytes()).decode()


figs = []
for date, slug, note in DAYS:
    s = stats(slug)
    figs.append(f"""
      <figure class="day">
        <div class="day-head">
          <span class="day-date">{date}</span>
          <span class="day-meta">{s['majors']} majors · {s['minors']} minors · {s['bos']} BOS · {s['choch']} ChoCh</span>
        </div>
        <p class="day-seq">{html.escape(s['line'])}</p>
        <p class="day-note">{html.escape(note)}</p>
        <button class="shot" data-full="i{slug}" aria-label="Enlarge {date}">
          <img id="i{slug}" src="data:image/png;base64,{b64(f'ms_chart_{slug}.png')}" alt="Regime chart for {date}">
          <span class="hint">Click to enlarge</span>
        </button>
      </figure>""")

HTML = f"""<title>BOS and ChoCh Model</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>
  :root {{
    --paper:#faf8f4; --surface:#fff; --ink:#17140e; --body:#3c372e; --muted:#77705f;
    --rule:#e4dfd3; --soft:#efebe1; --bull:#0f8a10; --bear:#c33a3a; --range:#c98500;
    --shadow:0 1px 2px rgba(23,20,14,.05),0 8px 24px rgba(23,20,14,.06);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --paper:#14120e; --surface:#1c1a15; --ink:#f6f2e9; --body:#ccc5b6; --muted:#938b78;
      --rule:#2e2b23; --soft:#26231c; --bull:#35b436; --bear:#e46a6a; --range:#e2a52a;
      --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
    }}
  }}
  :root[data-theme="dark"] {{
    --paper:#14120e; --surface:#1c1a15; --ink:#f6f2e9; --body:#ccc5b6; --muted:#938b78;
    --rule:#2e2b23; --soft:#26231c; --bull:#35b436; --bear:#e46a6a; --range:#e2a52a;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--body);
    font-family:"IBM Plex Sans",system-ui,sans-serif; font-size:15.5px; line-height:1.6;
    -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:56px 28px 88px; }}
  .eyebrow {{ font-family:"IBM Plex Mono",monospace; font-size:11.5px; letter-spacing:.14em;
    text-transform:uppercase; color:var(--muted); margin:0 0 14px; }}
  h1 {{ font-family:"IBM Plex Serif",Georgia,serif; font-weight:600;
    font-size:clamp(30px,4.4vw,44px); line-height:1.12; color:var(--ink);
    margin:0 0 16px; text-wrap:balance; letter-spacing:-.01em; }}
  .standfirst {{ font-size:17px; max-width:64ch; margin:0 0 44px; }}
  .standfirst b {{ color:var(--ink); font-weight:600; }}
  h2 {{ font-family:"IBM Plex Serif",Georgia,serif; font-weight:600; font-size:21px;
    color:var(--ink); margin:0 0 6px; }}
  .section {{ margin:0 0 52px; }}
  .section > p {{ max-width:68ch; margin:0 0 18px; }}
  hr.r {{ border:0; border-top:1px solid var(--rule); margin:0 0 22px; }}

  table.rules {{ border-collapse:collapse; width:100%; max-width:720px; }}
  table.rules th, table.rules td {{ text-align:left; padding:11px 16px 11px 0;
    border-bottom:1px solid var(--soft); font-size:14.5px; vertical-align:top; }}
  table.rules thead th {{ font-family:"IBM Plex Mono",monospace; font-size:10.5px;
    letter-spacing:.1em; text-transform:uppercase; color:var(--muted); font-weight:500; }}
  table.rules td.state {{ font-family:"IBM Plex Mono",monospace; font-weight:600;
    color:var(--ink); }}
  .bos {{ color:var(--ink); font-weight:600; }}
  .choch {{ color:var(--bear); font-weight:600; }}
  .arrow {{ color:var(--muted); }}

  .days {{ display:flex; flex-direction:column; gap:44px; }}
  .day {{ margin:0; }}
  .day-head {{ display:flex; flex-wrap:wrap; align-items:baseline; justify-content:space-between;
    gap:8px 18px; padding-bottom:9px; border-bottom:1px solid var(--rule); }}
  .day-date {{ font-family:"IBM Plex Mono",monospace; font-size:17px; font-weight:600;
    color:var(--ink); font-variant-numeric:tabular-nums; }}
  .day-meta {{ font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--muted);
    font-variant-numeric:tabular-nums; }}
  .day-seq {{ font-family:"IBM Plex Mono",monospace; font-size:12.5px; color:var(--muted);
    margin:11px 0 6px; font-variant-numeric:tabular-nums; overflow-x:auto; }}
  .day-note {{ margin:0 0 15px; max-width:72ch; font-size:14.5px; }}
  .shot {{ display:block; width:100%; padding:0; border:1px solid var(--rule);
    background:var(--surface); cursor:zoom-in; position:relative; box-shadow:var(--shadow); }}
  .shot img {{ display:block; width:100%; height:auto; }}
  .hint {{ position:absolute; right:10px; bottom:10px; font-family:"IBM Plex Mono",monospace;
    font-size:10.5px; letter-spacing:.08em; text-transform:uppercase; background:var(--surface);
    color:var(--muted); border:1px solid var(--rule); padding:4px 9px; opacity:0;
    transition:opacity .18s ease; }}
  .shot:hover .hint, .shot:focus-visible .hint {{ opacity:1; }}
  .shot:focus-visible {{ outline:2px solid var(--ink); outline-offset:3px; }}

  .note {{ border-left:2px solid var(--range); padding:2px 0 2px 16px; max-width:70ch; }}
  .note p {{ margin:0 0 10px; font-size:14.5px; }}
  .note p:last-child {{ margin-bottom:0; }}

  #lb {{ position:fixed; inset:0; background:rgba(10,8,5,.92); z-index:50; padding:22px;
    overflow:auto; cursor:zoom-out; }}
  #lb img {{ display:block; margin:0 auto; max-width:none; width:auto; }}
  #lb .close {{ position:fixed; top:14px; right:18px; font-family:"IBM Plex Mono",monospace;
    font-size:12px; letter-spacing:.1em; text-transform:uppercase; color:#efe9dc;
    background:rgba(0,0,0,.5); border:1px solid rgba(255,255,255,.28); padding:7px 13px;
    cursor:pointer; }}
  @media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; }} }}
</style>

<div class="wrap">
  <p class="eyebrow">Regime tracker · model rebuild</p>
  <h1>BOS and ChoCh Model</h1>
  <p class="standfirst">
    The classifier now follows <b>Market Structure.pdf</b>. Everything turns on one word in it —
    <b>relevant</b> — and what is relevant depends on the state. A session opens in a trading
    range, and every change of character returns to one.
  </p>

  <div class="section">
    <h2>The rules</h2>
    <hr class="r">
    <table class="rules">
      <thead><tr><th>State</th><th>Break above relevant high</th><th>Break below relevant low</th></tr></thead>
      <tbody>
        <tr><td class="state">Range</td>
            <td><span class="bos">BOS</span> <span class="arrow">→</span> Bull</td>
            <td><span class="bos">BOS</span> <span class="arrow">→</span> Bear</td></tr>
        <tr><td class="state">Bull</td>
            <td><span class="bos">BOS</span> <span class="arrow">→</span> stays Bull</td>
            <td><span class="choch">ChoCh</span> <span class="arrow">→</span> Range</td></tr>
        <tr><td class="state">Bear</td>
            <td><span class="choch">ChoCh</span> <span class="arrow">→</span> Range</td>
            <td><span class="bos">BOS</span> <span class="arrow">→</span> stays Bear</td></tr>
      </tbody>
    </table>
    <p style="margin-top:18px">
      BOS is a <b>continuation</b> signal — taking out the last high in an uptrend confirms the
      trend is healthy rather than ending it. Only a ChoCh ends a trend, and a range can only
      become a trend through a BOS. Breaks are measured on raw bar prices, so a plain
      continuation bar that never becomes a pivot itself still counts.
    </p>
  </div>

  <div class="section">
    <h2>Which pivots count</h2>
    <hr class="r">
    <p>
      A range only turns when the <b>pullback is actually there</b>. To turn up, the last
      completed swing must be the low that will serve as the higher low, and the break clears
      the high standing before it. If the last swing is still a high, the leg is merely running
      on — there is no new structure, however far price travels.
    </p>
    <p>
      In a trend, the relevant level in the trend's own direction is the top of the last
      <b>completed</b> leg. Straight after a BOS the trend is mid-leg and has no relevant level
      at all: the leg's extreme is still being made, and only the pullback that ends it promotes
      that extreme. So exactly one BOS fires per leg, and because each leg tops beyond the last,
      the relevant high in an uptrend is the trend's extreme — it ratchets and never retreats.
    </p>
    <p>
      The <b>majors</b> are the levels the structure is actually read from: each leg top, and
      each pullback promoted to the relevant higher low or lower high by a BOS. Everything else
      is a minor wiggle inside a leg. Across these six sessions that lands at <b>4–14 majors
      against 27–32 minors</b> — the document's proportions, sparse numbered pivots with the
      noise between them.
    </p>
    <p>
      Both halves were learned the hard way against hand-marked charts. Treating the relevant
      high as the last small swing rather than the last completed leg had price re-breaking it
      almost every bar — 21–36 BOS a session. And without the pullback requirement, a break
      could start a trend with no counter-swing behind it at all: a Bear called on 04-06 at bar
      23 with no lower high, a Bull on 06-12 at bar 39 with no higher low.
    </p>
  </div>

  <div class="section">
    <h2>Six sessions</h2>
    <hr class="r">
    <p>Grey solid marks a BOS, red dashed a ChoCh, each drawn from the major pivot that set the
    level across to the bar that broke it. Only breaks that move the state are marked —
    continuation BOS fire on almost every leg and would bury the chart.</p>
    <div class="days">{''.join(figs)}
    </div>
  </div>

  <div class="section note">
    <p><b>Exiting a range needs both halves.</b> A break alone is not a trend. Leaving Range
    upward requires the higher low to already be in place, and downward the lower high — exactly
    as the document's downtrend diagram shows, where breaking below pivot 2 only confirms the
    downtrend because pivot 3 is a lower high than pivot 1. Without that gate a session could be
    called Bear on its second bar, off a single low and no high at all.</p>
    <p><b>Open item.</b> On 02-13 a second ChoCh near bar 76 is marked by hand but not produced
    here. Bar 75 is an outside bar closing bearish, so it plausibly traded above bar 74 first and
    then below — putting in a lower high and a lower low within the one bar. Intrabar ordering on
    outside bars is inferred from the bar's direction, and this case is parked for now.</p>
  </div>
</div>

<script>
  const lb=document.createElement("div"); lb.id="lb"; lb.hidden=true;
  lb.innerHTML='<button class="close">Close · Esc</button><img alt="">';
  document.body.appendChild(lb);
  const im=lb.querySelector("img");
  document.querySelectorAll(".shot").forEach(b=>b.addEventListener("click",()=>{{
    const s=document.getElementById(b.dataset.full);
    im.src=s.src; im.alt=s.alt; lb.hidden=false;
    document.body.style.overflow="hidden"; lb.querySelector(".close").focus();
  }}));
  function close(){{ lb.hidden=true; im.src=""; document.body.style.overflow=""; }}
  lb.addEventListener("click",close);
  document.addEventListener("keydown",e=>{{ if(e.key==="Escape"&&!lb.hidden) close(); }});
</script>
"""

OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT}  ({OUT.stat().st_size/1024/1024:.2f} MB)")
