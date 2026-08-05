# Rebuild artifact_div_marks.html: one LARGE chart per setup, explanation directly
# under its chart (was: single 2x3 composite on top, all text below).
import base64
from pathlib import Path

SP = Path(r"c:\Users\Admin\myquant\scratchpad")

def b64(name):
    return base64.b64encode((SP / name).read_bytes()).decode()

SETUPS = [
    ("div_mark_1_0835.png",
     '1 · 08:35 2nd-entry fade <span class="chip short">SHORT</span> <span class="chip abs">ABSORPTION</span>',
     'test1 08:32 · 7609.75 · CVD 1522 &nbsp;→&nbsp; test2 08:35 · 7608.75 · CVD 2080 &nbsp;(ΔCVD +558)',
     """<p>No classic divergence — CVD <i>rose</i> into the retest. But price printed a <b>lower</b> high:
+558 net buying bought exactly nothing. Buyers pressing into gex_3 7610 / just above Friday's
VPOC 7600.5 and being absorbed. The fade worked as a rotation back to prior VPOC.</p>"""),
    ("div_mark_2_0915.png",
     '2 · 09:15 2nd-entry fade <span class="chip short">SHORT</span> <span class="chip abs">ABSORPTION — strongest of day</span>',
     'test1 09:00 · 7610.50 · CVD 2090 &nbsp;→&nbsp; test2 09:14 · 7604.75 · CVD 3448 &nbsp;(ΔCVD +1358)',
     """<p>The heaviest effort-vs-result mismatch of the session: +1358 buying while price failed
5.75 points <i>below</i> the prior high. Aggressive buyers absorbed near the gex_3 7610 test;
the market broke ~30 points within minutes. If absorption is real anywhere, it's this shape.</p>"""),
    ("div_mark_3_0923.png",
     '3 · 09:23 BOPB <span class="chip long">LONG</span> <span class="chip conf">TRAPPED SHORTS (different signature)</span>',
     'test1 09:16 · 7573.50 · CVD 1124 &nbsp;→&nbsp; test2 09:21 · 7585.25 · CVD −225 &nbsp;(ΔCVD −1349)',
     """<p>Neither divergence nor absorption: price rallied 11.75 points <i>against</i> −1349 net selling.
Sellers hitting into a rising tape — shorts trapped below the hvl0 7585 / prior-VAL 7581.5 confluence,
fueling the pullback long. A third signature class worth its own definition.</p>"""),
    ("div_mark_4_0955.png",
     '4 · 09:55 2nd-entry fade <span class="chip long">LONG</span> <span class="chip div">CLASSIC DIVERGENCE</span>',
     'test1 09:46 · 7580.75 · CVD −2750 &nbsp;→&nbsp; test2 09:52 · 7586.00 · CVD −2260 &nbsp;(ΔCVD +490)',
     """<p>Textbook bullish divergence: the second test into the hvl0 zone came with less cumulative selling.
Sellers exhausting at a level that had already held once. Price rotated back to ~7600.</p>"""),
    ("div_mark_5_1104.png",
     '5 · 11:04 BOPB <span class="chip short">SHORT</span> <span class="chip div">CLASSIC DIVERGENCE</span>',
     'test1 10:32 · 7596.50 · CVD −1764 &nbsp;→&nbsp; test2 11:09 · 7587.50 · CVD −3212 &nbsp;(ΔCVD −1448)',
     """<p>Bearish: the lower retest of the broken hvl0 area came with −1448 more net selling — flow firmly
behind the breakdown. This mark front-ran the entire afternoon leg to 7551.</p>"""),
    ("div_mark_6_1438.png",
     '6 · 14:38 2nd-entry fade <span class="chip long">LONG</span> <span class="chip abs">ABSORPTION</span>',
     'test1 14:29 · 7551.75 · CVD −2902 &nbsp;→&nbsp; test2 14:38 · 7551.00 · CVD −3556 &nbsp;(ΔCVD −654)',
     """<p>No classic divergence (CVD made a lower low too) — but −654 of fresh selling moved price only
0.75 points at the gex_1 7550 test. Sellers pressing and getting nothing: selling absorbed at the
gamma support. Price bounced ~17 points into the close.</p>"""),
]

setup_html = ""
for png, title, data, body in SETUPS:
    setup_html += f"""
<section class="setup-block">
<h2>{title}</h2>
<figure><img src="data:image/png;base64,{b64(png)}"
  alt="Price and session CVD around this setup with the two tests connected"></figure>
<div class="setup">
<p class="data num">{data}</p>
{body}
</div>
</section>
"""

HTML = """<title>ES 7/13 — CVD Divergence at the 6 Marked Setups</title>
<style>
:root{
  --paper:#f7f6f2; --ink:#20262e; --muted:#68707c; --line:#d9d6cd;
  --accent:#3b6ea5; --level:#a06a00; --good:#2e7d4f; --bad:#b03434;
  --chip-bg:#ece9e0; --card:#ffffff;
}
@media (prefers-color-scheme: dark){:root{
  --paper:#161a20; --ink:#dbe1e8; --muted:#8b95a3; --line:#2c333d;
  --accent:#7aa7d4; --level:#d4a24c; --good:#5fba8a; --bad:#e07070;
  --chip-bg:#232a33; --card:#1c2229;
}}
:root[data-theme="dark"]{
  --paper:#161a20; --ink:#dbe1e8; --muted:#8b95a3; --line:#2c333d;
  --accent:#7aa7d4; --level:#d4a24c; --good:#5fba8a; --bad:#e07070;
  --chip-bg:#232a33; --card:#1c2229;
}
:root[data-theme="light"]{
  --paper:#f7f6f2; --ink:#20262e; --muted:#68707c; --line:#d9d6cd;
  --accent:#3b6ea5; --level:#a06a00; --good:#2e7d4f; --bad:#b03434;
  --chip-bg:#ece9e0; --card:#ffffff;
}
body{background:var(--paper);color:var(--ink);
  font:16px/1.6 -apple-system,"Segoe UI",Roboto,sans-serif;margin:0;}
main{max-width:78rem;margin:0 auto;padding:2.5rem 1.25rem 4rem;}
.eyebrow{font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 .4rem;}
h1{font-family:Charter,Georgia,serif;font-size:1.9rem;line-height:1.2;margin:0 0 .4rem;text-wrap:balance;}
h2{font-family:Charter,Georgia,serif;font-size:1.35rem;margin:2.6rem 0 .7rem;}
.sub{color:var(--muted);margin:0 0 1.6rem;max-width:65ch;}
p{max-width:70ch;}
.setup-block{margin:0 0 1.2rem;}
figure{margin:.4rem 0 .9rem;border:1px solid var(--line);border-radius:6px;background:var(--card);
  padding:.6rem;overflow-x:auto;}
figure img{display:block;min-width:1000px;max-width:100%;width:100%;height:auto;}
figcaption{font-size:.8rem;color:var(--muted);padding:.5rem .3rem 0;}
.num{font-family:ui-monospace,Consolas,monospace;font-variant-numeric:tabular-nums;}
.chip{display:inline-block;font-size:.7rem;font-weight:700;letter-spacing:.05em;
  padding:.12rem .6rem;border-radius:99px;background:var(--chip-bg);}
.chip.abs{color:var(--level);} .chip.div{color:var(--good);} .chip.conf{color:var(--muted);}
.chip.short{color:var(--bad);} .chip.long{color:var(--good);}
.setup{background:var(--card);border:1px solid var(--line);border-radius:6px;
  padding:1rem 1.2rem;margin:0;max-width:none;}
.setup .data{font-size:.9rem;color:var(--muted);margin:.2rem 0 .6rem;}
.setup p{margin:.4rem 0;}
.callout{border-left:3px solid var(--level);background:var(--card);border-radius:0 6px 6px 0;
  padding:.8rem 1rem;margin:1.2rem 0;max-width:62ch;}
.callout p{margin:.3rem 0;}
.hyp{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:.9rem 1.1rem;margin:.8rem 0;max-width:65ch;}
.hyp b{color:var(--accent);}
ul{max-width:65ch;padding-left:1.2rem;} li{margin:.45rem 0;}
.foot{margin-top:2.5rem;font-size:.78rem;color:var(--muted);border-top:1px solid var(--line);padding-top:.8rem;}
</style>
<main>
<p class="eyebrow">Order-flow research · S75M · 2026-07-17</p>
<h1>CVD at the two tests of the extreme — Samir's 6 marked setups, 7/13</h1>
<p class="sub">For each hand-marked setup: <b>test&nbsp;1</b> = the prior push into the extreme,
<b>test&nbsp;2</b> = the touch at the setup. We compare session CVD (cumulative delta, from our
tick-built footprint) at the two tests. The finding: classic divergence explains only 2 of 6 —
the fades are better explained by <b>absorption</b> (effort without result). Each setup below:
the chart first, the read underneath. Colored line = classic CVD divergence at the tests;
gray line = CVD "confirmed" — which in four cases is the absorption signature, not an absence
of signal. Triangle = the mark.</p>
__SETUPS__
<h2>What this suggests</h2>
<div class="hyp"><b>Scoreboard: 2 classic divergences, 3 absorptions, 1 trapped-trader — 5 of 6 marks
carry a flow signature at the tests.</b> The eye that marked these setups appears to be reading
effort-vs-result, not momentum divergence.</div>
<div class="hyp"><b>Absorption here = pre-registered H5&nbsp;v2.</b> "Delta per point of net progress"
(S75K redefinition) is exactly what setups 1, 2 and 6 show. These 4 days are its IN-SAMPLE
calibration window only — they can never count as its test.</div>
<div class="hyp"><b>Three divergence definitions now exist</b> (trend-swing · extreme-retest ·
marks-anchored two-test). Exactly one must be pre-registered before the 5-yr run; choosing
post-hoc whichever fires at good-looking marks is how fake edges are built.</div>
<div class="hyp"><b>Missing piece — the control count.</b> We have not yet measured how often these
signatures appear at <i>unmarked</i> touches that went nowhere. Until the matched-control pass runs,
"his winners show absorption" and "absorption is everywhere" are indistinguishable.</div>

<div class="callout">
<p><b>Next steps (parked, agreed):</b></p>
<p>· Add <span class="num">delta_per_point</span>, <span class="num">two_test_dcvd</span>, and a rejection
grade as columns in the touch-episode table.</p>
<p>· Run the 4-day matched-control pass (marks vs unmarked touch episodes, same days/levels).</p>
<p>· Then the 5-yr run with the frozen definitions (abr0.35 band, day-clustered stats).</p>
</div>

<p class="foot">Data: nt8/FootprintExporter.cs tick-built footprint (validated exact vs MzPack, S75H) ·
marks from the :8630 forward-reveal tool (no-lookahead enforced) · scripts/footprint_metrics.py.
Render: scratchpad/render_div_at_marks_single.py. Companion artifact: "Prior-Session Volume Profile Read".</p>
</main>"""

out = SP / "artifact_div_marks.html"
out.write_text(HTML.replace("__SETUPS__", setup_html), encoding="utf-8")
print("wrote", out, out.stat().st_size, "bytes")
