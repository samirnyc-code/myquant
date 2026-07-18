"""S75R — build the 1M order-flow reading report (docs/gexlab/flow1m.html).

Two complete swings of ES 1M on 2026-07-17, bar by bar: annotated BidAsk ladder,
the delta arithmetic, my read, a verdict, and what I'd expect next.

THE NEXT-BAR CALLS ARE JUDGMENT, NOT MEASUREMENT. There are no probabilities in
this document on purpose. Depth data exists for exactly one session, so any
"63% of the time" here would be a number invented from a sample of one day. Where
a pattern repeats inside the window I say so and give the bar numbers; that is
observation, not a base rate.

Images are embedded base64 so the page works from any route (the slide library's
relative-link bug is the cautionary tale).
"""
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "footprint" / "ES_1m_20260717.json"
IMG = ROOT / "docs" / "slides" / "flow-1m-20260717"
OUT = ROOT / "docs" / "gexlab" / "flow1m.html"

# tag, read, verdict, next-bar expectation
N = {
 1: ("reversal", "Recording starts here, 15 minutes into RTH, with price at 7475.00 — "
     "the low of the whole window. 8,763 lots, the second-heaviest bar of the 37, and "
     "delta only +277. The heavy prints are lower: −215 at 7479.50 on 244×29. So sellers "
     "were still hitting bids inside the bar while it closed at 87% of range.",
     "Sellers spent, buyers taking control. High volume + small net delta + close near "
     "the high is the signature of a low being built, not a low being broken.",
     "Favours continuation up, but the first pullback matters more than this bar. Watch "
     "whether a red bar can close below 7480."),
 2: ("balance", "First pause. Delta −13 on 5,903 — dead flat. High 7489.75 but the close "
     "is 7484.00, right on the low, giving back the entire push.",
     "Balance bar, no conviction either way. A failed probe up, not a reversal — nobody "
     "pressed the downside either.",
     "Coin-flip on this bar alone. In context of bar 1 I'd lean long on a reclaim of 7486."),
 3: ("trend", "The answer arrives: +627 delta, 12.4% of volume, close 7492.25 at 95% of "
     "range. Cleanest efficiency of the window so far.",
     "Initiative buying. This is what a real up-leg looks like — high delta efficiency and "
     "a close on the high.",
     "Continuation. Longs get to hold; the level to defend is now 7486."),
 4: ("trend", "+524, close at 81% of range, biggest print +158 at 7495.25 on 313×471. "
     "Buyers lifting the offer in size mid-bar.",
     "Trend intact, second consecutive initiative bar.",
     "More upside. First sign of trouble would be a close in the lower third."),
 5: ("trend", "+219 on 4,657 — the push decelerates. Range narrows to 4.75.",
     "Healthy consolidation inside a trend, not distribution. Delta stays positive.",
     "Drift up or sideways. No short signal here."),
 6: ("trend", "+229, close 57% of range. Volume flat.",
     "Neutral-to-constructive. The market is resting.",
     "Sideways; wait for the next expansion bar to pick a side."),
 7: ("trap", "First real warning. Delta is POSITIVE (+127) but the close is at 11% of "
     "range — the low. The biggest print is +120 at 7500.50, which is AT THE HIGH: 22×142. "
     "Buyers lifted 142 lots at the top tick and the bar closed 4.25 points below it.",
     "Trapped buyers. Positive delta with a close on the low means the aggressive buyers "
     "paid the high and immediately went underwater. This is the first bar of the window "
     "where flow and price disagree.",
     "In a strong trend this usually resolves as a shallow pullback, not a reversal — but "
     "it's the first crack. I'd stop adding here."),
 8: ("trend", "+274, close back at 70% of range, +112 at 7502.25 again at the high.",
     "Trap from bar 7 repaired. Buyers still willing to pay up.",
     "Continuation, but the market is now paying up for less progress."),
 9: ("trend", "+643, 12.6% efficiency, close at 93% of range. Notable: +116 at 7504.00 "
     "on 0×116 — zero sellers at that tick.",
     "Strongest bar since 3. Initiative buying with no opposition at the key tick.",
     "Continuation. Nothing here argues for a top."),
10: ("trap", "Repeat of bar 7, sharper. Delta −39, close at 6% of range — on the low — "
     "yet the biggest print is +158 at 7506.25. Buyers again bought the upper half and "
     "the bar closed at the bottom.",
     "Second buyer trap. Two in four bars now. The trend is still up but it is getting "
     "more expensive to be long.",
     "Expect a test lower. If 7503 holds this is still just churn."),
11: ("trend", "+442, close 61% of range. Volume 5,684, the heaviest since bar 4.",
     "Buyers absorb the bar-10 trap and push on. Trend re-asserts.",
     "Up, but I'd want to see a close above 7509 to trust it."),
12: ("balance", "−48 on 4,490, close mid-range. Nothing happens.",
     "Pure balance. The market is coiling under 7509.",
     "Breakout bar likely next — direction unresolved. Trade the break, not the coil."),
13: ("imbalance", "+508 and the first STACKED buy imbalance of the window: 7510.50–7511.00, "
     "three consecutive ticks where ask ≥ 3× the diagonal bid.",
     "The coil resolves up. Stacked imbalance is the strongest single piece of evidence "
     "in a footprint and it points up.",
     "Continuation. This is the highest-conviction long signal so far."),
14: ("imbalance", "+630, 14.5% efficiency — the best of the window — close at 90% of range, "
     "and a second stacked buy imbalance at 7511.25–7511.75. Eight imbalance ticks total.",
     "Textbook initiative bar. Efficiency, close location and imbalance all agree.",
     "Strong continuation. Nothing to fade."),
15: ("absorption", "+301, close at 90% of range, but the biggest print is −177 at 7512.50 "
     "on 352×175 — heavy selling at the LOW of the bar that went nowhere.",
     "Sellers tried at the bottom of the bar and were absorbed. Bullish, and the mirror "
     "image of what will happen at the highs later.",
     "Up. Sellers just proved they can't hold 7512."),
16: ("trend", "The blow-off. 10,649 lots — double the running average, top-of-hour — "
     "+713 delta, close 7521.75 at 100% of range, on the high tick.",
     "Climactic initiative buying. A close exactly on the high after a vertical 25-point "
     "run is strength, but volume like this at the top of an hour is often where the last "
     "buyer shows up.",
     "This is where I stop being a buyer. Not short — but a close on the high with 2× "
     "volume is exhaustion risk, not an entry."),
17: ("trap", "And there it is. High 7522.50 — a marginal new high above bar 16 — then "
     "delta −1,147 (−14.2%, worst of the window so far) and a close at 10% of range. "
     "8,063 lots. The biggest print is −203 at 7520.75 on 373×170.",
     "UPTHRUST. New high, massive negative delta, close on the low. Everyone who bought "
     "bar 16's close and this bar's high is trapped. This is the single clearest reversal "
     "signal in the first swing.",
     "Down or sideways. Longs from 7520+ are offside and will supply on any bounce. I'd "
     "be flat here at minimum; the aggressive trade is short with a stop above 7522.75."),
18: ("balance", "−122, close 63% of range. The biggest print flips positive: +89 at "
     "7521.00 on 265×354.",
     "Buyers defend immediately. The upthrust is not being followed through — which is "
     "itself information: this is a pullback, not a reversal.",
     "Two-sided. Wait."),
19: ("balance", "−97, close 24% of range, biggest print −119 at 7519.00 which is AT THE LOW.",
     "Sellers testing the bottom of the range but achieving nothing. Third consecutive "
     "small-delta bar.",
     "Compression. The resolution will be sharp — trade the break."),
20: ("balance", "−58, close 24%, −118 at 7518.75. Fourth flat bar in a row.",
     "The bar-17 shock has fully absorbed into balance between 7517.25 and 7522.50.",
     "Breakout imminent. Given the trend is up, I'd lean long the break of 7522.50."),
21: ("imbalance", "Resolution: +301, range expands to 8.5 points, six imbalance ticks. "
     "But note the biggest print: −179 at 7524.50 on 696×517 — the heaviest two-sided "
     "battle of the window at a single tick.",
     "Break up, confirmed by the range expansion — but 7524.50 was contested hard. That "
     "tick is now a level.",
     "Up, and the bar-20 lean was right. Watch 7524.50 on any retest."),
22: ("trend", "+498, close 75% of range, +118 at 7529.50. Clean.",
     "Trend resumed. New leg up from the balance.",
     "Continuation toward 7533."),
23: ("balance", "−368, close 35% of range. First negative bar since the break.",
     "Normal pullback in an up-leg. Delta negative but price holds mid-range.",
     "Buyable if it holds above 7525."),
24: ("balance", "+81 but the biggest print is −178 at 7527.25 on 395×217. Close at 38%.",
     "Two-sided, slight seller edge under the surface. Momentum is fading.",
     "Neutral. Second consecutive bar without upside progress."),
25: ("absorption", "−66 delta yet the close is at 85% of range. Sellers hit bids and the "
     "bar closed near its high.",
     "Bullish divergence — the same absorption signature as bar 15. Sellers are being "
     "absorbed under 7529.",
     "Up. This is a long trigger with a stop below 7524.75."),
26: ("trend", "+553, 9.3% efficiency, new high 7533.75, close at 70% of range.",
     "Bar 25's read pays. New swing high. This is the top of swing 1.",
     "Continuation — but we are now 58 points off the 08:45 low with no meaningful "
     "correction. Trail stops, don't add."),
27: ("absorption", "The bar of the window. Delta −1,312 (−20.3%, the worst) driven almost "
     "entirely by ONE tick: 7532.50 traded 1,313×280 for −1,033. A single seller dumped "
     "over 1,300 lots at one price. And yet the bar's low is only 7530.50 and it closes "
     "mid-range at 7531.75.",
     "ABSORPTION — intrabar. Someone ate 1,300 lots without letting price break. On its "
     "face that is bullish. But hold that thought.",
     "This is the genuine fork. If buyers really absorbed it, the next bar goes up. If "
     "they were merely slow, price rolls. I would NOT be long into the answer."),
28: ("trap", "The answer: −367, close at 26% of range. Price rolls straight over.",
     "The bar-27 absorption FAILED. Whoever absorbed 1,300 lots at 7532.50 is now wrong, "
     "and their exit becomes supply. This is the most useful lesson in the window: "
     "absorption is only real if the next bar confirms it.",
     "Down. The failed-absorption unwind usually runs further than people expect."),
29: ("trend", "−257, close 26% of range, biggest print −142 at 7527.00 at the LOW.",
     "Initiative selling, follow-through from the failed absorption. Sellers pressing lows.",
     "Down. First support is the bar-21 battle tick at 7524.50."),
30: ("absorption", "Swing low. Low 7525.00 — right at that 7524.50 battle level — delta "
     "−578 (−11.1%), heaviest print −173 at 7525.75 on 381×208 … and the bar closes at "
     "79% of range, at 7528.75.",
     "ABSORPTION AT THE LOW, and this one has the close to back it. Sellers pressed with "
     "conviction into a known level and finished the bar 3.75 points off the low. Compare "
     "bar 27: same negative delta, but there the close was mid-range and it failed. Here "
     "the close is near the high. That difference is the whole signal.",
     "Up. This is the cleanest long in the window: entry on the close, stop below 7525."),
31: ("imbalance", "Confirmation, emphatically: +592, 9.8% efficiency, NINE imbalance ticks "
     "— the most of any bar — range 9 points, close at 86%.",
     "The bar-30 read pays immediately. Initiative buying with the heaviest imbalance "
     "count of the window.",
     "Continuation to new highs. Trail the stop under 7529."),
32: ("trend", "−60 delta, close at 72% of range, but look at the top: 240 lots traded at "
     "the high tick and the biggest print is +174 at 7536.00 ON THE HIGH.",
     "Buyers paying up at the high again — the bar-7/bar-16 pattern. Heavy volume at the "
     "extreme with a flat delta is where up-legs go to die.",
     "Caution. I'd tighten rather than add."),
33: ("trap", "High 7539.00 — the swing high — then delta −250 and a close at 4% of range, "
     "essentially on the low. Biggest print −335 at 7537.75 on 517×182.",
     "REJECTION AT THE HIGH. Same structure as bar 17: new high, negative delta, close on "
     "the low, heavy selling into the top ticks. Second time this exact pattern marks a "
     "swing high in 37 bars.",
     "Down. Exit longs. Short with a stop above 7539.25 is the aggressive version."),
34: ("balance", "−318 but the close is at 75% of range. Biggest print −250 at 7533.00.",
     "Sellers pressing, buyers still defending mid-range. Not yet a clean break.",
     "Two-sided. Let it develop."),
35: ("trend", "−325, close at 25% of range. Sellers regain the close.",
     "Down-leg resumes after the bar-34 pause.",
     "Lower. Next reference is 7527.75."),
36: ("trend", "−360, close at 5% of range — on the low. Biggest print −95 at 7528.50, "
     "at the LOW of the bar.",
     "Initiative selling into the low, no defense visible yet.",
     "Down — but a close this pinned to the low after a 4-bar slide is where I start "
     "looking for the absorption bar rather than pressing."),
37: ("absorption", "And it arrives. Low 7527.75, delta only +41, biggest print −71 at "
     "7528.25 at the LOW — sellers still hitting bids at the bottom — and the bar closes "
     "at 80% of range, at 7531.75.",
     "ABSORPTION AT THE LOW. Third occurrence of this exact signature (bars 30, 37, and "
     "the constructive version at 15/25): sellers press the low, delta stays weak or "
     "negative, close lands in the upper quarter. The two swings in this window both "
     "ended on it.",
     "Up. Same trade as bar 30 — long the close, stop below 7527.75. This is where the "
     "window ends, and the pattern says the next leg is up."),
}

CSS = """
:root{--bg:#fcfcfb;--card:#fff;--ink:#1a1a19;--ink2:#4a4a47;--muted:#77776f;
 --line:#e4e4de;--grn:#1a7f4b;--red:#b42318;--blu:#3564d4;--amb:#b45309}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--card:#232322;--ink:#f2f2ee;
 --ink2:#c8c8c0;--muted:#95958c;--line:#35352f;--grn:#4ade80;--red:#f87171;
 --blu:#5c8ce8;--amb:#fbbf24}}
:root[data-theme=dark]{--bg:#1a1a19;--card:#232322;--ink:#f2f2ee;--ink2:#c8c8c0;
 --muted:#95958c;--line:#35352f;--grn:#4ade80;--red:#f87171;--blu:#5c8ce8;--amb:#fbbf24}
:root[data-theme=light]{--bg:#fcfcfb;--card:#fff;--ink:#1a1a19;--ink2:#4a4a47;
 --muted:#77776f;--line:#e4e4de;--grn:#1a7f4b;--red:#b42318;--blu:#3564d4;--amb:#b45309}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.62 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:34px 20px 100px}
h1{font-size:28px;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:20px;margin:40px 0 12px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13.5px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:11px;
 padding:18px 20px;margin:16px 0}
.warn{border-left:3px solid var(--amb)}
.bar{background:var(--card);border:1px solid var(--line);border-radius:12px;
 padding:18px 20px;margin:22px 0}
.bar h3{margin:0 0 4px;font-size:17px;letter-spacing:-.01em}
.ohlc{color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums;margin-bottom:12px}
img{max-width:100%;height:auto;display:block;margin:6px 0 14px;border:1px solid var(--line);
 border-radius:8px;background:#fcfcfa}
.tag{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.05em;
 text-transform:uppercase;padding:2px 8px;border-radius:5px;margin-left:8px;vertical-align:2px;
 background:color-mix(in srgb,var(--t) 16%,transparent);color:var(--t)}
.t-trend{--t:var(--blu)} .t-absorption{--t:var(--grn)} .t-trap{--t:var(--red)}
.t-imbalance{--t:var(--grn)} .t-balance{--t:var(--muted)} .t-reversal{--t:var(--amb)}
.lbl{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
 color:var(--muted);margin-top:12px}
.verdict{border-left:3px solid var(--line);padding-left:13px;margin-top:6px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}
th,td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.03em}
td{font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}
.note{color:var(--ink2);font-size:14px}
code{background:color-mix(in srgb,var(--muted) 14%,transparent);padding:1px 5px;border-radius:4px;
 font-size:12.5px}
.foot{color:var(--muted);font-size:12.5px;margin-top:38px;border-top:1px solid var(--line);
 padding-top:15px}
.toc{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.toc a{font-size:12px;text-decoration:none;color:var(--ink2);border:1px solid var(--line);
 border-radius:6px;padding:3px 8px;font-variant-numeric:tabular-nums}
.toc a:hover{border-color:var(--blu);color:var(--blu)}
"""


def b64(p):
    return base64.b64encode(p.read_bytes()).decode()


def main():
    bars = json.loads(SRC.read_text(encoding="utf-8"))
    imgs = {int(f.name.split("_")[1]): f for f in IMG.glob("bar_*.png")}

    piv = {1: "swing low 7475.00", 26: "swing HIGH 7533.75", 30: "swing LOW 7525.00",
           33: "swing HIGH 7539.00", 37: "swing LOW 7527.75"}

    toc = "".join(f'<a href="#b{b["i"]}">{b["i"]}</a>' for b in bars)
    secs = []
    for b in bars:
        tag, read, verdict, nxt = N[b["i"]]
        img = (f'<img src="data:image/png;base64,{b64(imgs[b["i"]])}" '
               f'alt="bar {b["i"]} ladder">') if b["i"] in imgs else ""
        pv = (f' <span class="tag t-reversal">{piv[b["i"]]}</span>'
              if b["i"] in piv else "")
        secs.append(f"""
<div class="bar" id="b{b['i']}">
  <h3>Bar {b['i']} · {b['time']}<span class="tag t-{tag}">{tag}</span>{pv}</h3>
  <div class="ohlc">O {b['o']:.2f} &nbsp; H {b['h']:.2f} &nbsp; L {b['l']:.2f} &nbsp;
   C {b['c']:.2f} &nbsp;·&nbsp; Δ {b['delta']:+,} ({b['eff']:+.1f}% of {b['vol']:,})
   &nbsp;·&nbsp; POC {b['poc']:.2f}<br>
   <b>IBS {b['ibs']:.2f}</b> &nbsp;·&nbsp; body {b['body_pct']:.0f}%
   &nbsp;·&nbsp; wick {b['uw_pct']:.0f}%↑/{b['lw_pct']:.0f}%↓
   &nbsp;·&nbsp; range {b.get('rng_vs_abr') or '–'}% of ABR(8)
   &nbsp;·&nbsp; RVOL {b.get('rvol8') or '–'}
   &nbsp;·&nbsp; biggest print {b['dom_share']:.1f}% of vol
   &nbsp;·&nbsp; {len(b['imb'])} imb ({b['n_imb_thin']} thin)</div>
  <div>{''.join(f'<span class="tag t-{"absorption" if "absorption-low" in t else "trap" if ("climax" in t or "absorption-high" in t) else "imbalance" if "trend" in t else "balance"}">{t}</span>' for t in b.get('tags', []))}</div>
  {img}
  <div class="lbl">Read</div><div class="note">{read}</div>
  <div class="lbl">Verdict</div><div class="note verdict">{verdict}</div>
  <div class="lbl">Next bar — judgment, not a probability</div>
  <div class="note verdict">{nxt}</div>
</div>""")

    body = f"""
<h1>Reading the tape — ES 1-minute, two complete swings</h1>
<div class="sub">Fri 2026-07-17 · bars 08:45 → 09:21 · 37 bars · true BidAsk footprint
rebuilt from {sum(b['vol'] for b in bars):,} lots of tagged prints</div>

<div class="card warn">
<b>Two things to know before you read a single bar.</b>
<p style="margin:8px 0 0">
<b>1. This does not start at the open.</b> The depth recording for 7/17 begins at
<b>08:44:16</b>, so the RTH open (08:30) and the first fourteen minutes are simply not in
the data. The first complete 1-minute bar is 08:45. Any version of this showing the open
would be fabricated.</p>
<p style="margin:8px 0 0">
<b>2. There are no probabilities in this document, deliberately.</b> Depth data exists for
exactly one session. A number like "this resolves up 64% of the time" would be invented
from a sample of one day, and would read as measurement when it is opinion. Every
next-bar call below is my read as a trader, labelled as such. Where a pattern repeats
<i>inside this window</i> I say so and name the bars — that is observation, not a base rate.</p>
</div>

<h2>Lernziele — what this exercise can and cannot teach</h2>
<div class="card">
<p style="margin:0 0 10px"><b>It is a READING exercise, not a research result.</b> That
distinction is the most important thing on this page. 37 bars containing four turns can
teach you to read a ladder fluently. It cannot tell you what works. Keeping those two
apart is the whole discipline.</p>

<p style="margin:0 0 6px"><b>What you can genuinely learn here</b></p>
<ol class="note" style="margin:0 0 10px">
<li><b>The mechanics, until they are automatic.</b> Delta is horizontal (ask−bid at one
price). Imbalance is diagonal (ask[P] vs bid[P−1]). POC is where the volume piled. IBS is
where the close sat in the range. Four numbers, and after ~20 bars you stop having to
think about them.</li>
<li><b>Which signals are noise — this is the highest-value lesson.</b> 69% of the
imbalances in this window are thin-cell artifacts, and 39% sit on a row whose delta points
the <i>other</i> way. Most footprint education sells you imbalances as a signal. On ES 1M
they are mostly measurement error at the edge of the bar.</li>
<li><b>That the information is in the DISAGREEMENT, not the level.</b> Big delta tells you
little. Big delta with a close at the wrong end of the range tells you a lot. Every turn in
this window came from that disagreement.</li>
<li><b>What a failed signal looks like, side by side with a real one.</b> Bars 27 and 30
have nearly identical negative delta. One closed mid-range and price collapsed; the other
closed at 79% and price reversed up. Same "absorption", opposite outcome. That pair is
worth more than the other 35 bars combined.</li>
</ol>

<p style="margin:0 0 6px"><b>What it cannot teach, and where the wish breaks down</b></p>
<p class="note" style="margin:0 0 10px">The stated goal — "identify what good reversal bars
look like internally" — needs <b>labelled reversals across many sessions</b>. This window
contains <b>four</b>. Any internal signature I extract from four examples is a story, not a
finding, and the metrics now on every bar (IBS, ABR%, RVOL, POC location, tail volume)
exist to make that study <i>possible later</i>, not to answer it now. Same for SBs, EBs,
continuation bars, traps, climaxes: the vocabulary is here, the sample is not. Realistically
that needs 200+ labelled turns, i.e. depth data for 30–50 sessions — an NT8 re-export, not
something derivable from what is on disk.</p>
<p class="note" style="margin:0"><b>So the honest sequence is:</b> use this to build fluency
and calibrate scepticism → hand-label turns as more depth data arrives → only then ask what
they have in common → and only then, with a control, ask whether it is tradeable.</p>
</div>

<h2>The structure</h2>
<div class="scroll"><table>
<thead><tr><th>leg</th><th>from</th><th>to</th><th>move</th><th>ended by</th></tr></thead>
<tbody>
<tr><td>up</td><td>bar 1 · 7475.00</td><td>bar 26 · 7533.75</td><td>+58.75</td>
 <td>bar 27 failed absorption → bar 28</td></tr>
<tr><td>down</td><td>bar 26 · 7533.75</td><td>bar 30 · 7525.00</td><td>−8.75</td>
 <td>bar 30 absorption at the low</td></tr>
<tr><td>up</td><td>bar 30 · 7525.00</td><td>bar 33 · 7539.00</td><td>+14.00</td>
 <td>bar 33 rejection at the high</td></tr>
<tr><td>down</td><td>bar 33 · 7539.00</td><td>bar 37 · 7527.75</td><td>−11.25</td>
 <td>bar 37 absorption at the low</td></tr>
</tbody></table></div>

<h2>What actually repeated</h2>
<div class="card">
<p style="margin:0 0 10px"><b>Every turn in this window was marked by one of two
signatures</b>, and both are about the <i>disagreement</i> between delta and close
location — not about delta itself.</p>
<p style="margin:0 0 10px"><b>Absorption at the low → up.</b> Sellers press, delta is
negative, but the bar closes in the upper ~75–80% of its range.
Bars <b>30</b> (Δ−578, close 79%) and <b>37</b> (Δ+41, close 80%) both ended down-legs.
Bars <b>15</b> and <b>25</b> are the in-trend version.</p>
<p style="margin:0 0 10px"><b>Rejection at the high → down.</b> New high, negative delta,
close in the bottom ~10% of range. Bars <b>17</b> (Δ−1,147, close 10%) and <b>33</b>
(Δ−250, close 4%) both ended up-legs.</p>
<p style="margin:0"><b>And the counter-example that teaches the most: bar 27.</b> Delta
−1,312, of which −1,033 came from <i>one tick</i> — 1,313 lots hitting the bid at 7532.50.
Price held inside the bar, which looks like textbook absorption. It closed
<b>mid-range (45%)</b>, not near the high, and the next bar rolled straight over. Absorption
with a mid-range close is not absorption; it is a seller who hasn't finished. The close
location is what separates bar 27 from bar 30.</p>
</div>

<h2>Trade ideas this window supports</h2>
<div class="card">
<p style="margin:0 0 10px"><b>1. The absorption-low long (bars 30, 37).</b> Trigger: a bar
that makes a new swing low, has non-positive delta, and closes above ~75% of its range.
Entry on the close, stop a tick under the low. Both instances here worked immediately
(bar 31 was the single strongest bar of the window; bar 37 is where the data ends).</p>
<p style="margin:0 0 10px"><b>2. The upthrust exit/short (bars 17, 33).</b> Trigger: new
swing high, negative delta, close under ~10% of range. At minimum it is an exit for longs.
As a short it needs a stop above the high and it is the lower-quality of the two.</p>
<p style="margin:0 0 10px"><b>3. Do not trade single-tick size alone (bar 27).</b> A
1,300-lot print at one price is not a signal by itself. Wait for the close, then the next
bar's confirmation. Acting on bar 27 as "absorption" would have been long into a −8.75
point leg.</p>
<p style="margin:0"><b>Honest caveat on all three:</b> this is two swings on one morning of
one session. Two instances of a pattern is an observation, not an edge. Before any of this
gets sized, it needs the same treatment as the gamma-level study — a defined trigger, a
matched control, and enough sessions to have a denominator. Depth data for more days is
the blocker, and that is an NT8 re-export, not something derivable from what's on disk.</p>
</div>

<h2>A note on imbalances at 1-minute</h2>
<div class="card note">
Diagonal imbalance ticks (ask ≥ 3× the diagonal bid, min 20 lots) are common, but
<b>stacked</b> runs of 3+ are rare on ES at this timeframe — only bars 13 and 14 produced
them in 37 bars. Volume at 1M is spread too evenly across a narrow range for 3:1 diagonals
to chain. The practical read: on ES 1M, do not wait for stacked imbalances as your trigger —
they will not come often enough. The information lives in <b>close location versus delta</b>
and in <b>single-tick outliers</b> like bar 27's 1,313.
</div>

<h2>Bar by bar</h2>
<div class="toc">{toc}</div>
{''.join(secs)}

<div class="foot">
Engine <code>scripts/flowlab_1m.py</code> · renderer <code>scripts/render_1m_bars.py</code> ·
report <code>scripts/flowlab_report.py</code> · data
<code>data/depth/ES_depth_2026-07-17.csv</code> → <code>data/footprint/ES_1m_20260717.json</code>.
BidAsk footprint: Side=A is a trade at the ask (buy), Side=B a trade at the bid (sell);
Δ = Σask − Σbid, shown per row and summed on every chart. PNGs also in
<code>docs/slides/flow-1m-20260717/</code>. Reaction reading only — no fills, no P&amp;L,
no backtest.
</div>
"""
    html = (f"<title>ES 1M order flow — two swings, 7/17</title><style>{CSS}</style>"
            f'<div class="wrap">{body}</div>')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}  ({len(html)/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
