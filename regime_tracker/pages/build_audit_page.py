#!/usr/bin/env python3
"""Generate the transition-rule audit artifact with the comparison PNGs embedded."""
import base64, pathlib, html

import sys

_HERE = pathlib.Path(__file__).resolve().parent
SRC = _HERE.parent                       # regime_tracker/ -- JSONs and PNGs
OUT_DIR = _HERE / "out"                  # generated pages (git-ignored)
OUT_DIR.mkdir(exist_ok=True)


OUT = OUT_DIR / "transition_audit.html"
CASES = [
    dict(file="compare_20260406.png", date="2026-04-06", bars=74,
         call="Bull at bar 8, then Bear at bar 45",
         note="Flat Range for the entire session before. Resolves into both directions on the same day.",
         highs=("6703.50", "6722.25", "HH"), lows=("6679.00", "6685.25", "HL"), dirn="Bull"),
    dict(file="compare_20260612.png", date="2026-06-12", bars=54,
         call="Bull at bar 31",
         note="The leg completing the pair was the LOW — the case the old rule structurally cannot catch.",
         highs=("7509.75", "7525.00", "HH"), lows=("7450.75", "7461.25", "HL"), dirn="Bull"),
    dict(file="compare_20260113.png", date="2026-01-13", bars=48,
         call="Bear at bar 34",
         note="The long afternoon decline read as Range before; a Bull pocket also appears at bars 18–23.",
         highs=("7126.25", "7125.50", "LH"), lows=("7122.00", "7113.25", "LL"), dirn="Bear"),
    dict(file="compare_20260629.png", date="2026-06-29", bars=29,
         call="Bull at bar 17",
         note="Bull start moves from bar 45 to bar 17, catching the grind up from 7455 instead of the top.",
         highs=("7467.75", "7472.50", "HH"), lows=("7409.00", "7447.75", "HL"), dirn="Bull"),
    dict(file="compare_20260213.png", date="2026-02-13", bars=27,
         call="Bear at bar 51",
         note="The whole afternoon selloff, 7008 down to 6945, sat unclassified before.",
         highs=("7008.75", "7006.75", "LH"), lows=("6995.50", "6994.50", "LL"), dirn="Bear"),
    dict(file="compare_20251226.png", date="2025-12-26", bars=21,
         call="Bear at bar 13",
         note="Bear starts at bar 13 rather than bar 32 — joining the decline at 7097, not two thirds down.",
         highs=("7105.00", "7097.75", "LH"), lows=("7086.75", "7084.00", "LL"), dirn="Bear"),
]


def b64(name):
    return base64.b64encode((SRC / name).read_bytes()).decode()


figures = []
for k, c in enumerate(CASES, 1):
    ph, lh, hdir = c["highs"]
    pl, ll, ldir = c["lows"]
    figures.append(f"""
      <figure class="case">
        <div class="case-head">
          <div class="case-id">
            <span class="case-date">{c['date']}</span>
            <span class="chip chip--{c['dirn'].lower()}">{html.escape(c['call'])}</span>
          </div>
          <div class="case-count"><span class="num">{c['bars']}</span> bars resolved</div>
        </div>
        <p class="case-note">{html.escape(c['note'])}</p>
        <div class="arith">
          <span class="arith-row">highs <b>{ph}</b> → <b>{lh}</b> <i class="tag">{hdir}</i></span>
          <span class="arith-row">lows <b>{pl}</b> → <b>{ll}</b> <i class="tag">{ldir}</i></span>
        </div>
        <button class="shot" data-full="img{k}" aria-label="Enlarge {c['date']} comparison">
          <img id="img{k}" src="data:image/png;base64,{b64(c['file'])}" alt="Before and after regime shading for {c['date']}">
          <span class="zoom-hint">Click to enlarge</span>
        </button>
      </figure>""")

HTML = f"""<title>Transition Rule Audit</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap">
<style>
  :root {{
    --paper:      #faf8f4;
    --surface:    #ffffff;
    --ink:        #17140e;
    --body:       #3c372e;
    --muted:      #77705f;
    --rule:       #e4dfd3;
    --rule-soft:  #efebe1;
    --bull:       #0f8a10;
    --bear:       #c33a3a;
    --range:      #c98500;
    --shadow:     0 1px 2px rgba(23,20,14,.05), 0 8px 24px rgba(23,20,14,.06);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --paper:      #14120e;
      --surface:    #1c1a15;
      --ink:        #f6f2e9;
      --body:       #ccc5b6;
      --muted:      #938b78;
      --rule:       #2e2b23;
      --rule-soft:  #26231c;
      --bull:       #35b436;
      --bear:       #e46a6a;
      --range:      #e2a52a;
      --shadow:     0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
    }}
  }}
  :root[data-theme="dark"] {{
    --paper:      #14120e;
    --surface:    #1c1a15;
    --ink:        #f6f2e9;
    --body:       #ccc5b6;
    --muted:      #938b78;
    --rule:       #2e2b23;
    --rule-soft:  #26231c;
    --bull:       #35b436;
    --bear:       #e46a6a;
    --range:      #e2a52a;
    --shadow:     0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--paper);
    color: var(--body);
    font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 15.5px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 56px 28px 88px; }}

  .eyebrow {{
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 11.5px; letter-spacing: .14em; text-transform: uppercase;
    color: var(--muted); margin: 0 0 14px;
  }}
  h1 {{
    font-family: "IBM Plex Serif", Georgia, serif;
    font-weight: 600; font-size: clamp(30px, 4.4vw, 44px); line-height: 1.12;
    color: var(--ink); margin: 0 0 16px; text-wrap: balance; letter-spacing: -.01em;
  }}
  .standfirst {{ font-size: 17px; max-width: 62ch; margin: 0 0 40px; color: var(--body); }}
  .standfirst b {{ color: var(--ink); font-weight: 600; }}

  .stats {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(172px, 1fr));
    gap: 1px; background: var(--rule); border: 1px solid var(--rule);
    margin: 0 0 52px;
  }}
  .stat {{ background: var(--surface); padding: 18px 20px; }}
  .stat .num {{
    display: block; font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 26px; font-weight: 600; color: var(--ink);
    font-variant-numeric: tabular-nums; line-height: 1.15;
  }}
  .stat .lbl {{ display: block; font-size: 12.5px; color: var(--muted); margin-top: 5px; }}

  h2 {{
    font-family: "IBM Plex Serif", Georgia, serif; font-weight: 600;
    font-size: 21px; color: var(--ink); margin: 0 0 6px; letter-spacing: -.005em;
  }}
  .section {{ margin: 0 0 52px; }}
  .section > p {{ max-width: 66ch; margin: 0 0 18px; }}
  .lede-rule {{ border: 0; border-top: 1px solid var(--rule); margin: 0 0 24px; }}

  .ab {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 20px; }}
  .ab-card {{ background: var(--surface); border: 1px solid var(--rule); padding: 18px 20px; }}
  .ab-card h3 {{
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11.5px;
    letter-spacing: .12em; text-transform: uppercase; color: var(--muted);
    margin: 0 0 9px; font-weight: 500;
  }}
  .ab-card p {{ margin: 0; font-size: 14.5px; }}

  table.pivots {{ border-collapse: collapse; width: 100%; max-width: 520px; margin: 4px 0 14px; }}
  table.pivots th, table.pivots td {{
    text-align: left; padding: 9px 14px 9px 0; border-bottom: 1px solid var(--rule-soft);
    font-size: 14.5px;
  }}
  table.pivots th {{
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11px;
    letter-spacing: .1em; text-transform: uppercase; color: var(--muted); font-weight: 500;
  }}
  table.pivots td.v {{
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-variant-numeric: tabular-nums;
    color: var(--ink); font-weight: 500;
  }}
  table.pivots tr.key td {{ color: var(--ink); }}
  table.pivots tr.key td.v {{ font-weight: 600; }}

  .cases {{ display: flex; flex-direction: column; gap: 44px; }}
  .case {{ margin: 0; }}
  .case-head {{
    display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
    gap: 10px 18px; padding-bottom: 9px; border-bottom: 1px solid var(--rule);
  }}
  .case-id {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px; }}
  .case-date {{
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 17px;
    font-weight: 600; color: var(--ink); font-variant-numeric: tabular-nums;
  }}
  .chip {{
    font-size: 12.5px; padding: 2.5px 10px; border: 1px solid currentColor; border-radius: 2px;
    font-weight: 500; white-space: nowrap;
  }}
  .chip--bull {{ color: var(--bull); }}
  .chip--bear {{ color: var(--bear); }}
  .case-count {{ font-size: 13px; color: var(--muted); white-space: nowrap; }}
  .case-count .num {{
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 17px;
    font-weight: 600; color: var(--ink); font-variant-numeric: tabular-nums;
  }}
  .case-note {{ margin: 12px 0 10px; max-width: 70ch; font-size: 14.5px; }}
  .arith {{ display: flex; flex-wrap: wrap; gap: 8px 26px; margin: 0 0 16px; }}
  .arith-row {{
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 13px;
    color: var(--muted); font-variant-numeric: tabular-nums;
  }}
  .arith-row b {{ color: var(--ink); font-weight: 500; }}
  .arith-row .tag {{
    font-style: normal; color: var(--range); font-weight: 600; margin-left: 3px;
  }}

  .shot {{
    display: block; width: 100%; padding: 0; border: 1px solid var(--rule);
    background: var(--surface); cursor: zoom-in; position: relative; box-shadow: var(--shadow);
  }}
  .shot img {{ display: block; width: 100%; height: auto; }}
  .zoom-hint {{
    position: absolute; right: 10px; bottom: 10px;
    font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 10.5px;
    letter-spacing: .08em; text-transform: uppercase;
    background: var(--surface); color: var(--muted);
    border: 1px solid var(--rule); padding: 4px 9px; opacity: 0; transition: opacity .18s ease;
  }}
  .shot:hover .zoom-hint, .shot:focus-visible .zoom-hint {{ opacity: 1; }}
  .shot:focus-visible {{ outline: 2px solid var(--ink); outline-offset: 3px; }}

  .repro {{ background: var(--surface); border: 1px solid var(--rule); padding: 20px 22px; }}
  .repro pre {{
    margin: 0; overflow-x: auto; font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 13px; line-height: 1.75; color: var(--ink);
  }}
  .repro .cmt {{ color: var(--muted); }}

  .caveat {{ border-left: 2px solid var(--range); padding: 2px 0 2px 16px; max-width: 68ch; }}
  .caveat p {{ margin: 0; font-size: 14.5px; }}

  #lb {{
    position: fixed; inset: 0; background: rgba(10,8,5,.92); z-index: 50;
    padding: 22px; overflow: auto; cursor: zoom-out;
  }}
  #lb img {{ display: block; margin: 0 auto; max-width: none; width: auto; }}
  #lb .close {{
    position: fixed; top: 14px; right: 18px; font-family: "IBM Plex Mono", monospace;
    font-size: 12px; letter-spacing: .1em; text-transform: uppercase;
    color: #efe9dc; background: rgba(0,0,0,.5); border: 1px solid rgba(255,255,255,.28);
    padding: 7px 13px; cursor: pointer;
  }}
  @media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
</style>

<div class="wrap">
  <p class="eyebrow">Regime tracker · rule verification</p>
  <h1>Transition Rule Audit</h1>
  <p class="standfirst">
    The transition rule lets a trading range adopt whichever HH+HL or LH+LL structure forms
    inside it, rather than waiting for a new major high or a break. To check it does real work
    and isn't tuned to one chart, the identical pipeline was run with the rule <b>off</b> and
    <b>on</b> across 200 sessions of ES 5-minute bars.
  </p>

  <div class="stats">
    <div class="stat"><span class="num">15,891</span><span class="lbl">bars scanned · 200 sessions</span></div>
    <div class="stat"><span class="num">128</span><span class="lbl">qualifying calls (≥3 bars held)</span></div>
    <div class="stat"><span class="num">10.9%</span><span class="lbl">bars moved Range → trend</span></div>
    <div class="stat"><span class="num">21 / 19</span><span class="lbl">Bull / Bear split, top 40</span></div>
  </div>

  <div class="section">
    <h2>What changed</h2>
    <hr class="lede-rule">
    <div class="ab">
      <div class="ab-card">
        <h3>Before</h3>
        <p>A trend is confirmed only by a new major high or low, or by a break of structure.
        A range whose launch low doubles as its own anchor can never produce a qualifying
        higher low, so it stays a range indefinitely — even through a 50-point one-way rally.</p>
      </div>
      <div class="ab-card">
        <h3>After</h3>
        <p>Inside a range there is no established structure to protect, so the last two pivots
        of each type are compared directly. The first clean HH+HL or LH+LL becomes the new
        state, whichever of the two legs completes it. Only pivots formed since the range
        began count.</p>
      </div>
    </div>
  </div>

  <div class="section">
    <h2>Worked example · 2026-06-12</h2>
    <hr class="lede-rule">
    <p>The range opened at bar 15. Exactly four pivots formed inside it before the call:</p>
    <table class="pivots">
      <thead><tr><th>Bar</th><th>Type</th><th>Level</th><th>Reads as</th></tr></thead>
      <tbody>
        <tr><td class="v">16</td><td>low</td><td class="v">7450.75</td><td>—</td></tr>
        <tr><td class="v">19</td><td>high</td><td class="v">7509.75</td><td>—</td></tr>
        <tr class="key"><td class="v">23</td><td>high</td><td class="v">7525.00</td><td>higher high</td></tr>
        <tr class="key"><td class="v">31</td><td>low</td><td class="v">7461.25</td><td>higher low</td></tr>
      </tbody>
    </table>
    <p>HH + HL completes at bar 31 and Bull holds to the close. The leg that completed the pair
    was the <b>low</b> — precisely the case the old rule cannot reach, since it only ever
    confirms on a new high or a break. That is why bars 15–31 sat in Range before.</p>
  </div>

  <div class="section">
    <h2>Before and after</h2>
    <hr class="lede-rule">
    <p>Same bars, same pivots, shaded by each rule. Six of the 128 calls, largest first.</p>
    <div class="cases">{''.join(figures)}
    </div>
  </div>

  <div class="section">
    <h2>Reproduce</h2>
    <hr class="lede-rule">
    <div class="repro"><pre><span class="cmt"># scan any number of sessions, prints the arithmetic behind every call</span>
python compare_transition_rule.py PARQUET --sessions 200

<span class="cmt"># render the before/after for any single date</span>
python plot_compare.py PARQUET --date 2026-06-12</pre></div>
  </div>

  <div class="section caveat">
    <p><b>One caveat.</b> The rule also produces short-lived 1–3 bar trend pockets in chop —
    visible on 2025-12-26 around bars 67 and 81. The examples above filter those out by
    requiring ≥3 bars held, but they are real, and a minimum-duration guard may be worth adding.</p>
  </div>
</div>

<script>
  const lb = document.createElement("div");
  lb.id = "lb"; lb.hidden = true;
  lb.innerHTML = '<button class="close">Close · Esc</button><img alt="">';
  document.body.appendChild(lb);
  const lbImg = lb.querySelector("img");

  document.querySelectorAll(".shot").forEach(btn => {{
    btn.addEventListener("click", () => {{
      const src = document.getElementById(btn.dataset.full);
      lbImg.src = src.src;
      lbImg.alt = src.alt;
      lb.hidden = false;
      document.body.style.overflow = "hidden";
      lb.querySelector(".close").focus();
    }});
  }});
  function closeLb() {{
    lb.hidden = true; lbImg.src = ""; document.body.style.overflow = "";
  }}
  lb.addEventListener("click", closeLb);
  document.addEventListener("keydown", e => {{ if (e.key === "Escape" && !lb.hidden) closeLb(); }});
</script>
"""

OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT}  ({OUT.stat().st_size/1024/1024:.2f} MB)")
