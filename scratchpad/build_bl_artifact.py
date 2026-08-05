# -*- coding: utf-8 -*-
"""Build the Blind Spots dossier — emits a publish body (for the Artifact tool) and a
standalone HTML for Mission Control's docs/artifacts/ library."""
import base64, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
chart_b64 = base64.b64encode((ROOT/"scratchpad"/"bl_worked_example_20260709.png").read_bytes()).decode()
CHART = f"data:image/png;base64,{chart_b64}"

TITLE = "<title>Blind Spots — Reverse-Engineered &amp; Edge-Tested</title>"

STYLE = """<style>
:root{
  --bg:#f3f5f8; --panel:#ffffff; --ink:#151b23; --muted:#586675; --faint:#8894a3;
  --line:#e0e6ee; --line2:#eef2f6; --accent:#a9741a; --accent-soft:#a9741a1a;
  --good:#2f7d5b; --good-bg:#2f7d5b16; --bad:#b23b3b; --bad-bg:#b23b3b14;
  --warn:#9a6b1f; --warn-bg:#9a6b1f16;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0d1014; --panel:#151a21; --ink:#e6edf4; --muted:#9aa7b5; --faint:#697585;
    --line:#232b35; --line2:#1b222b; --accent:#e0a63c; --accent-soft:#e0a63c1c;
    --good:#4cc08a; --good-bg:#4cc08a16; --bad:#e2726a; --bad-bg:#e2726a16;
    --warn:#d9a441; --warn-bg:#d9a44116;
  }
}
:root[data-theme="light"]{
  --bg:#f3f5f8;--panel:#fff;--ink:#151b23;--muted:#586675;--faint:#8894a3;--line:#e0e6ee;--line2:#eef2f6;
  --accent:#a9741a;--accent-soft:#a9741a1a;--good:#2f7d5b;--good-bg:#2f7d5b16;--bad:#b23b3b;--bad-bg:#b23b3b14;--warn:#9a6b1f;--warn-bg:#9a6b1f16;
}
:root[data-theme="dark"]{
  --bg:#0d1014;--panel:#151a21;--ink:#e6edf4;--muted:#9aa7b5;--faint:#697585;--line:#232b35;--line2:#1b222b;
  --accent:#e0a63c;--accent-soft:#e0a63c1c;--good:#4cc08a;--good-bg:#4cc08a16;--bad:#e2726a;--bad-bg:#e2726a16;--warn:#d9a441;--warn-bg:#d9a44116;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.62 var(--sans);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{max-width:900px;margin:0 auto;padding:0 22px 96px}
.prose{max-width:660px}
.eyebrow{font:600 11.5px/1 var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--accent)}
h1{font-size:clamp(30px,5vw,46px);line-height:1.04;letter-spacing:-.022em;margin:.32em 0 0;
  text-wrap:balance;font-weight:760}
h2{font-size:24px;letter-spacing:-.015em;margin:0 0 2px;font-weight:720;text-wrap:balance}
h3{font-size:15px;margin:0 0 6px;font-weight:680;letter-spacing:-.01em}
p{margin:12px 0}
a{color:var(--accent)}
.lead{font-size:19px;line-height:1.55;color:var(--ink);margin:20px 0 0;max-width:640px}
.muted{color:var(--muted)}
hr{border:0;border-top:1px solid var(--line);margin:0}

/* header band */
header{padding:64px 0 34px;border-bottom:1px solid var(--line)}
.kicker{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font:500 12.5px/1 var(--mono);color:var(--faint)}
.dot{width:4px;height:4px;border-radius:50%;background:var(--faint)}

/* section rhythm */
section{padding:44px 0;border-bottom:1px solid var(--line)}
.sec-head{display:flex;gap:14px;align-items:baseline;margin-bottom:20px}
.sec-n{font:600 12px/1 var(--mono);color:var(--accent);padding-top:4px;min-width:26px}

/* scoreboard */
.board{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:30px}
@media(max-width:720px){.board{grid-template-columns:1fr}}
.q{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:16px 16px 15px;
  display:flex;flex-direction:column;gap:9px}
.q .ql{font:600 11px/1.3 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--faint)}
.q .qv{font-size:15px;font-weight:680;line-height:1.3}
.q .qs{font-size:13px;color:var(--muted);line-height:1.45;margin-top:auto}
.chip{align-self:flex-start;font:700 11px/1 var(--mono);letter-spacing:.04em;padding:5px 9px;border-radius:6px}
.chip.g{color:var(--good);background:var(--good-bg)}
.chip.b{color:var(--bad);background:var(--bad-bg)}
.chip.w{color:var(--warn);background:var(--warn-bg)}

/* verdict badges inline */
.badge{display:inline-flex;align-items:center;gap:6px;font:700 11px/1 var(--mono);
  padding:4px 8px;border-radius:5px;vertical-align:middle}
.badge.g{color:var(--good);background:var(--good-bg)}
.badge.b{color:var(--bad);background:var(--bad-bg)}
.badge.w{color:var(--warn);background:var(--warn-bg)}

/* tables */
.tbl{width:100%;border-collapse:collapse;font:13.5px/1.4 var(--sans);margin:8px 0}
.tbl.mono td:not(:first-child),.tbl.mono th:not(:first-child){font-family:var(--mono);
  font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.tbl th{font:600 11px/1.3 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--faint);
  text-align:left;padding:8px 12px;border-bottom:1px solid var(--line)}
.tbl th:not(:first-child){text-align:right}
.tbl td{padding:9px 12px;border-bottom:1px solid var(--line2)}
.tbl tr:last-child td{border-bottom:0}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.res-b{color:var(--bad);font-weight:650}
.res-g{color:var(--good);font-weight:650}

/* figure */
figure{margin:26px 0 6px}
figure img{width:100%;height:auto;border:1px solid var(--line);border-radius:12px;display:block;background:#fff}
figcaption{font-size:13px;color:var(--muted);margin-top:11px;line-height:1.5;max-width:660px}

/* callouts */
.note{border-left:3px solid var(--accent);background:var(--accent-soft);border-radius:0 10px 10px 0;
  padding:14px 18px;margin:22px 0;font-size:14.5px}
.note.warn{border-color:var(--warn);background:var(--warn-bg)}
.note b{font-weight:700}
.note .nl{font:700 10.5px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--accent);
  display:block;margin-bottom:6px}
.note.warn .nl{color:var(--warn)}

/* key-value formula */
.formula{font-family:var(--mono);font-size:15px;background:var(--panel);border:1px solid var(--line);
  border-radius:10px;padding:16px 18px;margin:18px 0;overflow-x:auto;color:var(--ink);
  font-variant-numeric:tabular-nums}
.formula .c{color:var(--accent)}

/* family pills */
.fams{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.fam{border:1px solid var(--line);border-radius:9px;padding:9px 13px;background:var(--panel);
  font:13px/1.3 var(--mono)}
.fam b{color:var(--accent)}

ul.clean{margin:12px 0;padding-left:20px}
ul.clean li{margin:7px 0}
.foot{padding:36px 0 0;color:var(--faint);font:12.5px/1.6 var(--mono)}
.foot a{color:var(--muted)}
</style>"""

BODY = f"""
<div class="wrap">
<header>
  <div class="kicker"><span>MENTHORQ RESEARCH</span><span class="dot"></span><span>ES / NQ · S&amp;P complex</span>
    <span class="dot"></span><span>200 sessions · 2025-09-30 → 2026-07-17</span></div>
  <p class="eyebrow" style="margin-top:22px">Investigation</p>
  <h1>Blind Spots: reverse-engineered, then edge-tested.</h1>
  <p class="lead">We captured 200 days of MenthorQ Blind Spot levels, tried to derive their formula,
    and tested whether they actually work as trading levels. Two of the three questions have hard,
    powered answers — and both are the answer nobody wants.</p>
</header>

<div class="board">
  <div class="q"><span class="ql">What are they?</span><span class="chip w">EXPLAINED</span>
    <span class="qv">Cross-asset option "walls," projected onto your chart.</span>
    <span class="qs">Price zones where the options market on correlated assets is stacked. Real, and located near genuine option structure.</span></div>
  <div class="q"><span class="ql">Can we calculate them?</span><span class="chip b">NO</span>
    <span class="qv">The exact numbers are unreconstructable from what MenthorQ publishes.</span>
    <span class="qs">Computed upstream from a continuous per-strike source. Cross-instrument links solved exactly; the seed itself resists every method.</span></div>
  <div class="q"><span class="ql">Do they work?</span><span class="chip b">NO EDGE</span>
    <span class="qv">No measurable intraday reaction edge over random levels.</span>
    <span class="qs">688 touches, ES+NQ, hard null: 47% reject vs 47% for random. Gamma-stacked ones aren't special either.</span></div>
</div>

<section>
  <div class="sec-head"><span class="sec-n">01</span><div>
    <h2>What a blind spot actually is</h2></div></div>
  <div class="prose">
  <p>When you trade ES, the thing that pushes price isn't only ES's own options — it's the whole
    correlated complex: SPY, QQQ, the big tech names, VIX. Large option positions there create
    hedging <b>walls</b> where dealers must buy or sell, and that pressure spills into ES. Watching ten
    charts to see them all is impossible, so MenthorQ collapses them into one set of levels — BL1 to
    BL10 — drawn on your chart.</p>
  <p>The number isn't strength. It's <b>how many correlated assets overlap</b> at that price: BL1 is the
    most crowded zone. In plain terms:</p>
  </div>
  <div class="note"><span class="nl">The one-line definition</span>
    A blind spot is <b>a price where the options market on correlated assets is stacked to defend or
    reject</b> — a spot you couldn't see by watching your own chart alone.</div>
</section>

<section>
  <div class="sec-head"><span class="sec-n">02</span><div>
    <h2>A day in the life &mdash; 2026-07-09</h2></div></div>
  <div class="prose">
  <p>Real ES data. The purple lines are that morning's ten blind spots; the orange dotted lines are ES's
    own gamma levels. Watch the two shaded zones.</p></div>
  <figure>
    <img src="{CHART}" alt="ES 5-minute chart for 2026-07-09 with blind spot levels and gamma levels overlaid, showing price bounded between two clusters">
    <figcaption><b>Top zone (~7600):</b> BL1 7599.51 sits exactly on Call Resistance 7600 and Gamma Wall
      7600 — a triple stack. Price rallied to 7595 and stopped cold. <b>Bottom zone (~7520):</b> BL5/BL6
      cluster on HVL 7520; the low was 7529.5 and bounced. The whole day traded inside the box.</figcaption>
  </figure>
  <div class="note warn"><span class="nl">Honest caveat</span>
    <b>This day was cherry-picked.</b> I scanned for a clean reaction to make the concept vivid — it's real,
    but it is <b>not representative</b>. The systematic test in §04 shows days like this happen about as
    often at random levels. Keep this chart as an illustration of the <i>idea</i>, not evidence that it works.</div>
</section>

<section>
  <div class="sec-head"><span class="sec-n">03</span><div>
    <h2>Can we calculate them? Half yes, half no.</h2></div></div>

  <div class="prose">
  <p><b>The half that cracked.</b> Across all 200 days, every instrument's blind spots are the
    <i>same numbers</i>, rescaled by one live price ratio — an exact identity, not a correlation:</p></div>
  <div class="formula">ES.bl<span class="c">&#8341;</span> = SPX.bl<span class="c">&#8341;</span> &times; (ES_price / SPX_price)
    &nbsp;&nbsp;&rarr;&nbsp; residual <span class="c">0.003&nbsp;pt</span>, all 200 days, every level</div>
  <div class="prose"><p>So the 19 instruments collapse to just <b>five independent underlyings</b>. Solve
    the cash index and the whole family falls out to the penny:</p></div>
  <div class="fams">
    <div class="fam">S&amp;P &nbsp;<b>ES = SPX = SPY</b></div>
    <div class="fam">Nasdaq &nbsp;<b>NQ = NDX = QQQ</b></div>
    <div class="fam">Russell &nbsp;<b>RTY = RUT = IWM</b></div>
    <div class="fam">then <b>YM · GC · CL</b> + each Mag-7 name, standalone</div>
  </div>
  <p class="muted" style="max-width:640px;font-size:14.5px">The cash index/ETF is primary; the future is
    derived — the ES/SPX ratio just drifts with the futures basis toward expiry.</p>

  <div class="prose"><p style="margin-top:26px"><b>The half that resisted everything.</b> The seed numbers
    themselves — SPX's ten — can't be rebuilt from MenthorQ's published levels. Five independent attacks,
    all beating a null, all failing:</p></div>
  <div class="scroll"><table class="tbl mono">
    <thead><tr><th>Attack</th><th>Result</th><th>Verdict</th></tr></thead>
    <tbody>
    <tr><td>Exact fingerprint (decimals)</td><td>cents are uniform &rarr; continuous source</td><td class="res-b">REFUTED</td></tr>
    <tr><td>Machine learning (740 features)</td><td>worse than a fixed-offset baseline OOS</td><td class="res-b">REFUTED</td></tr>
    <tr><td>Overlap-clustering (the "V2" story)</td><td>overlap-rank predicts nothing (&#961;&#8776;0)</td><td class="res-b">REFUTED</td></tr>
    <tr><td>Sector-ETF hypothesis</td><td>vanishes under day-shuffle; no lift vs SPY/QQQ</td><td class="res-b">REFUTED</td></tr>
    <tr><td>Per-strike gamma surface (live)</td><td>BLs don't sit on its features either</td><td class="res-b">REFUTED</td></tr>
    </tbody>
  </table></div>
  <div class="note"><span class="nl">What survives</span>
    Blind spots do sit measurably <b>near</b> real cross-asset option structure (Call Resistance, Put
    Support, HVL, Gamma Wall) &mdash; confirmed at <b>z = +6.9</b> against a strict day-shuffle null. Their
    <i>location</i> is real. What we can't do is reproduce the exact figure; it's cooked from a continuous
    per-strike quantity MenthorQ never exposes historically.</div>
</section>

<section>
  <div class="sec-head"><span class="sec-n">04</span><div>
    <h2>Do they work? The powered test.</h2></div></div>
  <div class="prose">
  <p>The real question. Test: when price first touches a blind spot, does it <b>react</b> (bounce/reject)
    more than at an arbitrary level in the same zone? Two instruments, 1-minute bars, 380 sessions, 688
    touches, and a <b>hard null</b> &mdash; random levels drawn from the same price band.</p></div>
  <div class="scroll"><table class="tbl mono">
    <thead><tr><th>Test</th><th>Blind spots</th><th>Random null</th><th>Edge</th></tr></thead>
    <tbody>
    <tr><td>Reject on touch (rest of day)</td><td>47.1%</td><td>47.0%</td><td class="res-b">none · z+0.1</td></tr>
    <tr><td>Reject on touch (20-min window)</td><td>51.9%</td><td>51.5%</td><td class="res-b">none · z+0.2</td></tr>
    <tr><td>Gamma-stacked BL react harder <span class="muted">(MQ's key claim)</span></td><td>52.6%</td><td>51.7%</td><td class="res-b">none · z+0.2</td></tr>
    <tr><td>Reaction magnitude</td><td>&mdash;</td><td>&mdash;</td><td class="res-b">none · z&#8722;0.6</td></tr>
    <tr><td>Day range inside BL envelope</td><td>70%</td><td>97%<span class="muted"> naive band</span></td><td class="res-b">worse</td></tr>
    <tr><td>Day high/low lands on a BL</td><td>22&ndash;30%</td><td>25%</td><td class="res-b">none · z&#8722;1.0</td></tr>
    </tbody>
  </table></div>
  <p style="font-size:17px;font-weight:640;margin-top:20px;max-width:640px">As a mechanical support/resistance
    level, blind spots show <span class="res-b">no measurable edge</span> on ES or NQ — and gamma-stacked
    ones are no different.</p>
  <div class="prose"><p>This doesn't contradict §03. The levels genuinely sit near option structure — but
    "a level exists in the options data" is not the same as "price reverses there in a way you can harvest."
    The location is real; the tradeable reaction is not.</p></div>
</section>

<section>
  <div class="sec-head"><span class="sec-n">05</span><div>
    <h2>What this doesn't rule out</h2></div></div>
  <div class="prose">
  <ul class="clean">
    <li><b>Mechanical use only.</b> This tests touch&rarr;fade. It can't capture a discretionary trader who
      combines a blind spot with their own directional read, wicks, and timing — how MenthorQ actually
      teaches them ("wait for the 2nd or 3rd test"), as one confirmation among several.</li>
    <li><b>Intraday reaction only.</b> Not tested as profit <i>targets</i>, nor as swing / multi-day levels.</li>
    <li><b>A deliberately harsh null.</b> "Better than <i>any</i> level in the same band" is a high bar —
      many classic support/resistance levels would fail it too.</li>
  </ul>
  <p>The fair next tests: blind spots as <b>targets</b> rather than entries, conditioned on <b>trend
    regime</b>, or combined with a directional signal instead of blind fades. That's where a tool like this
    earns its keep, if it does anywhere.</p></div>
</section>

<section style="border-bottom:0">
  <div class="sec-head"><span class="sec-n">&#8214;</span><div>
    <h2>Bottom line</h2></div></div>
  <div class="prose">
  <p style="font-size:18px;line-height:1.6">Blind spots are a <b>real map of where the options market on the
    S&amp;P complex is positioned</b> — we proved the levels track genuine structure, and that SPX seeds the
    entire family exactly. But you <b>can't compute them</b> from public data, and as standalone trading
    levels they carry <b>no measurable mechanical edge</b>. Use them as context, not as a trigger — and
    don't pay the reaction any more respect than a coin flip has earned.</p>
  </div>
  <div class="foot">
    <hr style="margin:0 0 20px">
    Pipeline: <span style="color:var(--muted)">mq_blindspots_backfill.py</span> · captured daily via
    <span style="color:var(--muted)">mq_mine.py</span> · 19 tickers &times; 200 sessions on disk.<br>
    Studies: bl_confluence_200d · bl_edge_study · bl_formula_* (5-agent run). MenthorQ research, 2026-07-20.
  </div>
</section>
</div>
"""

publish = TITLE + STYLE + BODY
(ROOT/"scratchpad"/"bl_artifact_publish.html").write_text(publish, encoding="utf-8")

standalone = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
  '<meta name="viewport" content="width=device-width,initial-scale=1">'
  + TITLE + STYLE + '</head><body>' + BODY + '</body></html>')
out = ROOT/"docs"/"artifacts"/"blind_spots_reverse_engineered_edge_tested.html"
out.write_text(standalone, encoding="utf-8")
print("publish:", (ROOT/'scratchpad'/'bl_artifact_publish.html').stat().st_size//1024, "KB")
print("standalone:", out, out.stat().st_size//1024, "KB")
