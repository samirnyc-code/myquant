"""
Build the self-contained LegLab findings artifact (HTML with charts inlined as
data-URIs). Output: leglab/artifact/leglab_findings.html  (published via Artifact).
"""
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "leglab" / "outputs"
ARTDIR = ROOT / "leglab" / "artifact"
ARTDIR.mkdir(parents=True, exist_ok=True)
RUN = "20260906"


def img(name):
    b = (OUT / f"{name}_{RUN}.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode()


CHARTS = {k: img(k) for k in [
    "leg_count_vs_tim", "leg_count_by_year_16y", "leg_early_classifier",
    "leg_geometry", "leg_day_typing", "leg_structure",
    "leg_structure_stresstest", "big_es_days", "leg_scalp_by_year",
]}

# (eyebrow, title, verdict, verdict_class, chart_key, caption, [paragraphs])
FINDINGS = [
    ("Validation", "The pipeline agrees with Tim", "Confirmed", "good",
     "leg_count_vs_tim",
     "Our leg count vs Tim's published per-year chart, 0.15×ADR threshold.",
     ["Before trusting anything, we checked our engine against Tim's own numbers. "
      "Counting legs his way — track the running extreme from the open, close a leg "
      "when price reverses by more than 0.15×ADR — our results land on his published "
      "figures within <b>1.2%</b> every year.",
      "That match means the data (16 years of Databento ES 5-minute RTH bars) and the "
      "counting logic are sound, so every result that follows rests on solid ground."]),

    ("Structure", "Leg count is a stable constant", "Confirmed", "good",
     "leg_count_by_year_16y",
     "Average legs per day by year, 2010–2026. Light bars are partial years.",
     ["ES prints about <b>15 legs a day</b>, and it has for sixteen straight years — "
      "every single year sits in a narrow 14.7–16.6 band with no drift. Tim showed this "
      "for four years; it holds for a decade before his window too.",
      "The reason it stays flat is the ADR normalization: as volatility rose over the "
      "years, the threshold grew with it, so the <i>count</i> stayed put. (The size in "
      "ticks is a very different story — see the last chart.)"]),

    ("Prediction", "Early legs forecast volatility, not trend", "Null on trend", "warn",
     "leg_early_classifier",
     "Legs in the first 90 minutes vs how the rest of the day behaves.",
     ["The tempting idea — a quiet, few-legged open means a trend day — is <b>false</b>. "
      "Early leg count has essentially zero relationship with how directional the day "
      "turns out (correlation −0.03). The lone exception is a dead-quiet, one-legged "
      "morning (3% of days), which does trend 67% of the time.",
      "What early legs <i>do</i> predict is the rest of the day's <b>range</b> "
      "(correlation +0.40, and it holds even after controlling for the morning's range). "
      "A busy morning means a busy afternoon. This is the first hint of the theme that "
      "runs through everything: legs measure volatility, not direction."]),

    ("Geometry", "Legs hold their size but change speed", "Finding", "good",
     "leg_geometry",
     "Leg size by index and time of day; leg-to-leg size mean-reversion.",
     ["A leg is remarkably consistent in size (~0.32×ADR) from the open to the close. "
      "What changes is <b>speed</b>: a leg takes ~2.5 bars near the open and close but "
      "~6.7 bars at lunch — the classic midday lull, measured in leg duration.",
      "The sharpest pattern is <b>size mean-reversion</b>: after an unusually big leg, "
      "the next one is larger only 14% of the time; after a small leg, 81%. Some of that "
      "is regression to the mean, but the magnitude makes it useful for sizing targets."]),

    ("Day types", "A working taxonomy — that doesn't repeat", "Null on persistence", "warn",
     "leg_day_typing",
     "Four day types by structure; the day-to-day transition matrix.",
     ["We built the day-type classifier Tim never finished (Trend-Up 24%, Channel 28%, "
      "Range 31%, Trend-Down 16%) from directional structure, and it validates his "
      "instinct — but only halfway. Fewer legs does mean more trend <i>for up days</i> "
      "(12.6 legs); trend-<i>down</i> days are the choppiest of all (19.2 legs). Selloffs "
      "trend and whip at the same time.",
      "The catch for traders: today's type tells you almost nothing about tomorrow's — "
      "the transition matrix is flat. Day types don't cluster. Volatility, on the other "
      "hand, clearly does: a big-range day is followed by another 58.5% of the time."]),

    ("Direction", "Structure carries a real signal", "Signal", "good",
     "leg_structure",
     "Breakout-of-structure vs inside legs, and what follows each.",
     ["Finally, something directional. When a leg breaks structure (a new session "
      "high/low), the next same-direction leg breaks too <b>48%</b> of the time; after a "
      "leg that stays inside, only <b>14%</b>. And balance does not coil into a breakout "
      "— the more inside legs stack up, the <i>less</i> likely the next one breaks out. "
      "Trends persist; ranges persist.",
      "This is the one thing leg count, size, and day-typing all missed — a genuine "
      "regime-persistence signal. But before celebrating, we stress-tested it."]),

    ("Skepticism", "…but most of it is mechanical", "Partial", "warn",
     "leg_structure_stresstest",
     "The breakout edge, controlled for distance to the extreme.",
     ["After a breakout you're sitting right next to the extreme, so making a new one is "
      "cheap; deep in a range you're far from it. Once we hold that distance fixed, most "
      "of the 48%-vs-14% gap disappears — it was <b>~85% mechanical positioning</b>.",
      "A small, honest edge survives: <b>+5.4 points</b> of extra breakout probability at "
      "equal distance, consistent across every bucket. Real, but modest — the kind of "
      "thing that earns a costed backtest, not a victory lap."]),

    ("Refutation", "“Big days continue” didn't hold up", "Refuted", "bad",
     "big_es_days",
     "Next-day follow-through after big ES days, vs Tim's 85% claim.",
     ["Tim found that big ES days (range ≥3.3×ABR) get a same-direction second leg 85% of "
      "the time — from 14 days over 2021–2025. On our full 16 years, it's the <b>opposite</b>: "
      "the bigger the day, the <i>less</i> the next day continues (33% at 3.3×, below the "
      "49% base rate), and the average next-day drift runs <b>against</b> the move.",
      "ES <b>mean-reverts</b> after big days; big up days reverse hardest. His 85% was a "
      "small, recent bull-market sample. (Caveat: we tested next-day close/extreme, not "
      "his exact intraday pullback-entry rule — but the continuation premise clearly fails.)"]),

    ("Practical", "The “scalp” has grown 5×", "Use this", "good",
     "leg_scalp_by_year",
     "Average leg size (0.15×ADR) per year, in ES ticks.",
     ["Here's the finding with the most direct trading consequence. The leg <i>count</i> "
      "is constant, but a leg's <b>size in ticks has roughly quintupled</b> — from ~8 "
      "ticks (2010–2017) to ~43 ticks (2022, 2025, 2026) — as ES climbed from ~1,300 to "
      "~7,700 and volatility rose.",
      "So a fixed-tick scalp target is completely unmoored from the market: an 8-tick "
      "target was a whole leg in 2012 and is under a fifth of one now. This is the "
      "strongest case in the whole study for <b>volatility-scaled (ADR-based) targets</b> "
      "instead of fixed ticks."]),
]

SCORE = [
    ("Reproduce Tim's count", "Confirmed", "good", "matches within 1.2%"),
    ("Leg count over 16 years", "Confirmed", "good", "stable ~15/day, no drift"),
    ("Early legs → trend", "Null", "warn", "no relationship (−0.03)"),
    ("Early legs → volatility", "Signal", "good", "predicts afternoon range (+0.40)"),
    ("Leg geometry", "Finding", "good", "size mean-reverts; velocity smile"),
    ("Day-type persistence", "Null", "warn", "tomorrow independent of today"),
    ("Volatility clustering", "Signal", "good", "big day → big day 58.5%"),
    ("Structure (breakouts)", "Partial", "warn", "real edge +5.4pp, ~85% mechanical"),
    ("Big-days continuation", "Refuted", "bad", "ES mean-reverts after big days"),
    ("Scalp size in ticks", "Use this", "good", "≈5× growth → scale targets"),
]

STATS = [
    ("1.2%", "match to Tim's published counts"),
    ("~15", "legs per day, every year for 16"),
    ("+2.89", "extra legs on down days, beyond volatility"),
    ("58.5%", "chance a big-range day follows a big one"),
    ("~5×", "growth in leg size (ticks) since 2010"),
]


def chip(text, cls):
    return f'<span class="chip {cls}">{text}</span>'


def build():
    score_rows = "\n".join(
        f'<tr><td>{name}</td><td>{chip(v, c)}</td>'
        f'<td class="mono note">{note}</td></tr>'
        for name, v, c, note in SCORE)

    stat_cards = "\n".join(
        f'<div class="stat"><div class="stat-n mono">{n}</div>'
        f'<div class="stat-l">{l}</div></div>' for n, l in STATS)

    sections = []
    for eyebrow, title, verdict, vclass, key, cap, paras in FINDINGS:
        body = "\n".join(f"<p>{t}</p>" for t in paras)
        sections.append(f"""
    <section class="finding">
      <div class="f-head">
        <span class="eyebrow">{eyebrow}</span>
        {chip(verdict, vclass)}
      </div>
      <h2>{title}</h2>
      <figure>
        <div class="chart-card"><img src="{CHARTS[key]}" alt="{cap}" loading="lazy"></div>
        <figcaption>{cap}</figcaption>
      </figure>
      <div class="prose">{body}</div>
    </section>""")
    sections_html = "\n".join(sections)

    return f"""<style>
:root {{
  --bg:#f5f6f3; --surface:#ffffff; --ink:#1b2226; --muted:#59636a; --faint:#8a938f;
  --line:#e3e6e0; --accent:#0e6b6b; --accent-soft:#dcecea;
  --good:#2f7d5b; --warn:#b0702a; --bad:#b23b3b;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","SFMono-Regular",Menlo,Consolas,"Liberation Mono",monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#0e1214; --surface:#161c1f; --ink:#e9edea; --muted:#96a19c; --faint:#6f7b77;
    --line:#26302f; --accent:#57bab2; --accent-soft:#123433;
    --good:#5cbd8a; --warn:#d69657; --bad:#d76a6a;
  }}
}}
:root[data-theme="light"] {{
  --bg:#f5f6f3; --surface:#ffffff; --ink:#1b2226; --muted:#59636a; --faint:#8a938f;
  --line:#e3e6e0; --accent:#0e6b6b; --accent-soft:#dcecea;
  --good:#2f7d5b; --warn:#b0702a; --bad:#b23b3b;
}}
:root[data-theme="dark"] {{
  --bg:#0e1214; --surface:#161c1f; --ink:#e9edea; --muted:#96a19c; --faint:#6f7b77;
  --line:#26302f; --accent:#57bab2; --accent-soft:#123433;
  --good:#5cbd8a; --warn:#d69657; --bad:#d76a6a;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font-family:var(--sans); line-height:1.65; -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width:940px; margin:0 auto; padding:clamp(28px,5vw,72px) clamp(20px,4vw,40px); }}
.reading {{ max-width:680px; }}
a {{ color:var(--accent); }}

/* header */
.masthead {{ border-bottom:1px solid var(--line); padding-bottom:28px; margin-bottom:36px; }}
.brand {{ font-family:var(--mono); font-size:.78rem; letter-spacing:.22em; text-transform:uppercase;
  color:var(--accent); margin-bottom:18px; }}
h1 {{ font-family:var(--serif); font-weight:600; font-size:clamp(2.1rem,5.5vw,3.4rem);
  line-height:1.05; letter-spacing:-.01em; margin:0 0 .35em; text-wrap:balance; }}
.tagline {{ font-family:var(--serif); font-style:italic; font-size:clamp(1.05rem,2.4vw,1.35rem);
  color:var(--muted); margin:0 0 22px; max-width:640px; }}
.meta {{ display:flex; flex-wrap:wrap; gap:8px; }}
.meta span {{ font-family:var(--mono); font-size:.72rem; letter-spacing:.04em; color:var(--muted);
  border:1px solid var(--line); border-radius:999px; padding:4px 11px; }}

/* summary */
.summary {{ background:var(--surface); border:1px solid var(--line); border-radius:14px;
  padding:clamp(22px,3vw,32px); margin-bottom:40px; }}
.summary h2 {{ font-family:var(--mono); font-size:.76rem; letter-spacing:.18em; text-transform:uppercase;
  color:var(--accent); margin:0 0 16px; }}
.lede {{ font-family:var(--serif); font-size:1.15rem; line-height:1.6; margin:0 0 22px; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
.stat {{ background:var(--surface); padding:16px 18px; }}
.stat-n {{ font-size:1.7rem; font-weight:600; color:var(--accent); letter-spacing:-.02em;
  font-variant-numeric:tabular-nums; }}
.stat-l {{ font-size:.82rem; color:var(--muted); margin-top:2px; line-height:1.35; }}

/* scorecard */
.scorecard {{ margin-bottom:52px; }}
.scorecard h2, .thesis h2.blk, .next h2.blk {{ font-family:var(--serif); font-weight:600;
  font-size:1.5rem; margin:0 0 16px; }}
table {{ width:100%; border-collapse:collapse; font-size:.92rem; }}
thead th {{ font-family:var(--mono); font-size:.68rem; letter-spacing:.1em; text-transform:uppercase;
  color:var(--faint); text-align:left; padding:0 12px 10px; border-bottom:1px solid var(--line); }}
tbody td {{ padding:11px 12px; border-bottom:1px solid var(--line); vertical-align:middle; }}
tbody tr:last-child td {{ border-bottom:none; }}
td.note {{ color:var(--muted); font-size:.82rem; }}
.mono {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}

/* chips */
.chip {{ display:inline-block; font-family:var(--mono); font-size:.68rem; letter-spacing:.05em;
  text-transform:uppercase; padding:3px 10px; border-radius:999px; white-space:nowrap;
  border:1px solid transparent; }}
.chip.good {{ color:var(--good); background:color-mix(in srgb,var(--good) 12%,transparent);
  border-color:color-mix(in srgb,var(--good) 30%,transparent); }}
.chip.warn {{ color:var(--warn); background:color-mix(in srgb,var(--warn) 12%,transparent);
  border-color:color-mix(in srgb,var(--warn) 30%,transparent); }}
.chip.bad {{ color:var(--bad); background:color-mix(in srgb,var(--bad) 12%,transparent);
  border-color:color-mix(in srgb,var(--bad) 30%,transparent); }}

/* findings */
.finding {{ padding:34px 0; border-top:1px solid var(--line); }}
.f-head {{ display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:6px; }}
.eyebrow {{ font-family:var(--mono); font-size:.72rem; letter-spacing:.16em; text-transform:uppercase;
  color:var(--faint); }}
.finding h2 {{ font-family:var(--serif); font-weight:600; font-size:clamp(1.4rem,3vw,1.9rem);
  line-height:1.15; margin:0 0 20px; text-wrap:balance; }}
figure {{ margin:0 0 22px; }}
.chart-card {{ background:#ffffff; border:1px solid var(--line); border-radius:12px;
  padding:14px; overflow-x:auto; }}
.chart-card img {{ display:block; width:100%; height:auto; max-width:100%; border-radius:4px; }}
figcaption {{ font-family:var(--mono); font-size:.74rem; color:var(--faint); margin-top:10px;
  line-height:1.4; }}
.prose {{ max-width:680px; }}
.prose p {{ margin:0 0 14px; }}
.prose p:last-child {{ margin-bottom:0; }}
.prose b {{ color:var(--ink); font-weight:660; }}

/* closing blocks */
.thesis {{ margin-top:56px; padding:clamp(24px,3.5vw,40px); border-radius:16px;
  background:var(--accent-soft); border:1px solid color-mix(in srgb,var(--accent) 22%,transparent); }}
.thesis .big {{ font-family:var(--serif); font-size:clamp(1.3rem,3vw,1.7rem); line-height:1.4;
  margin:0; text-wrap:balance; }}
.thesis .big b {{ color:var(--accent); }}
.next {{ margin-top:48px; }}
.next ul {{ max-width:680px; padding-left:0; list-style:none; margin:0; }}
.next li {{ padding:12px 0 12px 26px; border-bottom:1px solid var(--line); position:relative; }}
.next li:before {{ content:"\\2192"; position:absolute; left:0; color:var(--accent); font-family:var(--mono); }}
.next li b {{ font-weight:640; }}
footer {{ margin-top:52px; padding-top:24px; border-top:1px solid var(--line);
  font-family:var(--mono); font-size:.74rem; color:var(--faint); line-height:1.6; }}
</style>

<div class="wrap">
  <header class="masthead">
    <div class="brand">LegLab &middot; a leg-structure study</div>
    <h1>What 16 years of S&amp;P&nbsp;500 futures say about leg counting</h1>
    <p class="tagline">An independent reproduction and stress-test of Tim Fairweather's
      leg-counting research &mdash; and an honest hunt for a tradeable edge.</p>
    <div class="meta">
      <span>ES futures</span><span>5-minute</span><span>RTH</span>
      <span>Jun 2010 &ndash; Jul 2026</span><span>4,145 sessions</span>
    </div>
  </header>

  <div class="summary">
    <h2>The short version</h2>
    <p class="lede">Leg count is a beautifully stable feature of the market &mdash; and, it
      turns out, a <b>volatility</b> gauge, not a direction gauge. We reproduced Tim's work
      exactly, then tested a dozen ways to trade it. Most directional ideas came up empty;
      the honest, repeatable signal in legs is how <i>much</i> a market moves, not which way.</p>
    <div class="stats">
      {stat_cards}
    </div>
  </div>

  <div class="scorecard">
    <h2>Every test, and how it landed</h2>
    <div style="overflow-x:auto">
    <table>
      <thead><tr><th>Question</th><th>Verdict</th><th>In a line</th></tr></thead>
      <tbody>
        {score_rows}
      </tbody>
    </table>
    </div>
  </div>

  {sections_html}

  <div class="thesis">
    <p class="big">The throughline: leg-based metrics forecast <b>volatility</b> &mdash;
      it clusters, it persists, and leg sizes mean-revert &mdash; but they say almost nothing
      about <b>direction</b>. Build volatility timing and position sizing on legs, not
      trend prediction.</p>
  </div>

  <div class="next">
    <h2 class="blk">What's worth doing next</h2>
    <ul>
      <li><b>Volatility-scaled targets.</b> The scalp has grown 5&times; &mdash; test
        ADR-based exits against fixed-tick targets on a live scalper.</li>
      <li><b>First breakout of the day.</b> The last untested directional idea: does the
        day's first structure break predict its close?</li>
      <li><b>Tag the trade book by leg index.</b> Do entries early in the day beat
        late, exhausted ones?</li>
      <li><b>Cost the breakout edge.</b> Turn the surviving +5.4-point structure edge into
        a pass/fail after real fills.</li>
    </ul>
  </div>

  <footer>
    Method &mdash; a leg opens at the RTH open, tracks the running extreme, and closes when
    price reverses by more than 0.15&times;ADR (average of the prior 8 daily ranges),
    measured on intrabar highs/lows; the count resets each morning. Data: Databento ES
    5-minute RTH, Jun 2010 &ndash; Jul 2026. All figures reproducible from the LegLab
    scripts. Inspired by the leg-counting work at zentradingtech.com.
  </footer>
</div>"""


STANDALONE_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="An independent 16-year reproduction and stress-test of Tim Fairweather's ES leg-counting research.">
<title>LegLab — What 16 years of ES say about leg counting</title>
</head>
<body>
"""
STANDALONE_TAIL = "\n</body>\n</html>\n"


if __name__ == "__main__":
    html = build()
    # artifact-body version (no skeleton; wrapped at publish time)
    path = ARTDIR / "leglab_findings.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path}  ({len(html)/1024:.0f} KB)")
    # standalone full-document version to send to Tim (double-click / email)
    standalone = STANDALONE_HEAD + html + STANDALONE_TAIL
    spath = ARTDIR / "leglab_for_tim.html"
    spath.write_text(standalone, encoding="utf-8")
    print(f"wrote {spath}  ({len(standalone)/1024:.0f} KB)  [standalone, send this to Tim]")
