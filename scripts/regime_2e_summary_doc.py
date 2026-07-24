"""Builds the S83 one-document program summary: headlines -> spec at a glance ->
process -> results -> path forward -> verdict. Embeds 5 key graphics (base64).
Output: docs/artifacts/regime_2e_summary.html (+ Desktop copy).
  python scripts/regime_2e_summary_doc.py
"""
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
L = ROOT / "docs" / "living"
OUT = ROOT / "docs" / "artifacts" / "regime_2e_summary.html"


def b64(p):
    return base64.b64encode((L / p).read_bytes()).decode()


IMGS = {k: b64(v) for k, v in {
    "final": "finalspec_20260724.png",
    "battery": "validation_battery_20260724.png",
    "checks": "five_checks_20260724.png",
    "kill": "kill_rules_20260724.png",
    "fill": "fillmodel_20260724.png",
}.items()}

html = """<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ES 2E x Regime — Program Summary</title>
<style>
:root{--page:#f6f5f1;--surface:#fdfdfb;--ink:#171b20;--ink2:#575c64;--grid:#e3e2dc;
--border:rgba(20,24,29,.12);--bull:#1f7a3d;--bear:#b23a2e;--blue:#2a78d6;--teal:#0e7c86;color-scheme:light}
@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])){
--page:#0f1216;--surface:#161a20;--ink:#eeede8;--ink2:#b7bac0;--grid:#272b31;
--border:rgba(255,255,255,.12);--bull:#3fae67;--bear:#d76454;--blue:#3987e5;--teal:#2fa9b5;color-scheme:dark}}
:root[data-theme="dark"]{--page:#0f1216;--surface:#161a20;--ink:#eeede8;--ink2:#b7bac0;
--grid:#272b31;--border:rgba(255,255,255,.12);--bull:#3fae67;--bear:#d76454;--blue:#3987e5;--teal:#2fa9b5;color-scheme:dark}
:root[data-theme="light"]{--page:#f6f5f1;--surface:#fdfdfb;--ink:#171b20;--ink2:#575c64;
--grid:#e3e2dc;--border:rgba(20,24,29,.12);--bull:#1f7a3d;--bear:#b23a2e;--blue:#2a78d6;--teal:#0e7c86;color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.55 system-ui,"Segoe UI",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:36px 20px 80px}
h1{font-family:"Iowan Old Style","Palatino Linotype",Georgia,serif;font-size:clamp(28px,5vw,40px);
line-height:1.15;margin:0 0 8px;text-wrap:balance}
h2{font-family:"Iowan Old Style","Palatino Linotype",Georgia,serif;font-size:24px;margin:44px 0 8px}
h3{font-size:16px;margin:22px 0 6px}
p{max-width:72ch} .sub{color:var(--ink2);font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:22px 0}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px 14px}
.tile .v{font-size:24px;font-weight:700}.tile .l{font-size:12px;color:var(--ink2);margin-top:2px}
.pos{color:var(--bull)}.neg{color:var(--bear)}
table{border-collapse:collapse;font-size:13.5px;background:var(--surface);font-variant-numeric:tabular-nums;width:100%}
th,td{border:1px solid var(--grid);padding:6px 10px;text-align:left}
th{color:var(--ink2);font-weight:600;font-size:12px}
.tw{overflow-x:auto;margin:12px 0;border:1px solid var(--border);border-radius:6px}
figure{margin:20px 0;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px}
figure img{max-width:100%;display:block;border-radius:3px}
figcaption{font-size:13px;color:var(--ink2);padding:4px 4px 8px}
.box{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--teal);
border-radius:6px;padding:14px 20px;margin:16px 0}
.warn{border-left-color:var(--bear)}
ol,ul{max-width:74ch} li{margin:6px 0}
.k{font-weight:700}
.step{display:flex;gap:12px;margin:10px 0}
.step .n{background:var(--teal);color:#fff;border-radius:50%;min-width:26px;height:26px;
display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px}
</style>
<div class="wrap">
<p class="sub" style="text-transform:uppercase;letter-spacing:.12em;font-weight:600">
Program summary · Samir / Thomas · 2026-07-24</p>
<h1>ES Second Entries × Regime — what we built, what survived, what's next</h1>

<h2>Headlines</h2>
<ul>
<li><span class="k">The raw setup loses money.</span> Mechanical second entries: PF 0.78 across 5 years of tick data. Every regime, both directions.</li>
<li><span class="k">Execution and one day-filter turned it into a real book:</span> don't chase (limit retest), volatility-sized stop, hold to the close, skip big-gap days → <span class="k">PF 1.39 lifetime, 1.36 out-of-sample</span>, green all six years, both directions.</li>
<li><span class="k">The profit is a tail harvest:</span> the top 20 of 630 trades are ALL the profit; the top 2 are 24% of it. Missing runners kills the book — <span class="k">automation is not optional, it is the strategy.</span></li>
<li><span class="k">Sized honestly it returns ~15%/yr:</span> $70–85k per ES, plan for a −$21k drawdown and 6–18 month flat stretches.</li>
<li><span class="k">Every claim was adversarially audited:</span> two fake findings were caught and retracted (a stop-tighten fill fantasy, a bad join); the draft kill-switches were themselves backtested and replaced after they proved they'd have quit the book right before its best year.</li>
</ul>

<div class="tiles">
<div class="tile"><div class="v pos">+$82.7k</div><div class="l">5-yr net · 1 ES · all costs in</div></div>
<div class="tile"><div class="v">1.39</div><div class="l">PF (test half: 1.36)</div></div>
<div class="tile"><div class="v">630</div><div class="l">trades (~10 / month)</div></div>
<div class="tile"><div class="v">45%</div><div class="l">win rate · payoff 1.4</div></div>
<div class="tile"><div class="v neg">−$21k</div><div class="l">drawdown to size for (MC 95%)</div></div>
</div>

<h2>The system at a glance</h2>
<div class="tw"><table>
<tr><th style="width:20%">WHEN</th><td>ES, 5-minute RTH chart, day-scoped. New entries only 09:00–13:59 (session open +30min to +5h30). <span class="k">Skip the whole day if |open − prior close| &gt; 0.54%</span> (fixed constant)</td></tr>
<tr><th>SETUP</th><td>Second entry only (H2/L2 by the S61 count) — <span class="k">longs when the regime machine says BULL, shorts when BEAR</span>, judged the instant the trigger is touched. Never 1st or 3rd entries</td></tr>
<tr><th>ENTRY</th><td><span class="k">Limit 6 ticks below the trigger</span> (longs; mirror shorts). Never chase. Cancel the limit if unfilled after 30 minutes or at window end</td></tr>
<tr><th>STOP</th><td><span class="k">0.30 × average daily range (10 days)</span> from fill — about 15–16 points typically. Rounded to a tick, minimum 2 points. Never moved</td></tr>
<tr><th>EXIT</th><td><span class="k">No target. Hold to the session close</span>, or the stop. Regime flips mid-trade are ignored</td></tr>
<tr><th>POSITION</th><td>1 unit per signal, same-direction adds to 3, never long and short at once (opposite fill = reverse)</td></tr>
</table></div>

<h2>The process, briefly</h2>
<p><span class="k">1 · Base study.</span> The validated tick-driven regime machine + mechanical 2E over 1,231 sessions: a loser everywhere (PF 0.78–0.82). The regime filter alone moved nothing.</p>
<p><span class="k">2 · Find the levers.</span> Sweeps over execution, not the signal: the breakout chase cost $29 of the $32/trade deficit (retest limit fixed it); afternoon entries lost $90k (window fixed it); tight stops donated winners (volatility stop doubled the book); every profit target amputated the tail (EOD hold won its fifth straight test).</p>
<p><span class="k">3 · The filter that mattered.</span> Big-gap days break the setup — the pre-registered day-type sweep found it, and it passed four independent tests, including improving a config it was never tuned on. Its evidence is broad (183 trades averaging −$155), not a tail fluke.</p>
<p><span class="k">4 · Adversarial audit.</span> Train/test splits, parameter surfaces, year tables, Monte-Carlo, fill models, removed-subset autopsies. Two findings were exposed as artifacts and retracted; the cancel-rule's PF bump failed validation and was demoted to an operational rule; the account sizing and kill rules were corrected after failing their own backtests.</p>

<figure><img src="data:image/png;base64,__FINAL__">
<figcaption><span class="k">The committed book.</span> Equity with the out-of-sample half in orange (it earned more than the in-sample half), net by year (2022 is 37% of profits — best weather is trending markets), PF green every year, and the same book under four robustness views.</figcaption></figure>

<figure><img src="data:image/png;base64,__BATTERY__">
<figcaption><span class="k">Why the gap filter is believed.</span> Top-left: skipping ever-bigger gaps degrades smoothly — no magic threshold (0.54% was fixed by rule, not picked from this curve). Bottom-left: profit factor by year for each build stage. Bottom-right: the honest shape of the risk — trade count falls as PF rises.</figcaption></figure>

<figure><img src="data:image/png;base64,__CHECKS__">
<figcaption><span class="k">The decision checks.</span> Longs and shorts both profitable and alternating leadership (not a directional bet); the Monte-Carlo drawdown distribution that sets sizing (−$21k at the 95th percentile); all volatility regimes green; the concentration curve showing the tail carries the book.</figcaption></figure>

<h2>Results that matter</h2>
<div class="tw"><table>
<tr><th>view</th><th>n</th><th>net</th><th>$/trade</th><th>PF</th></tr>
<tr><td>Lifetime</td><td>630</td><td class="pos">+$82,712</td><td>+131</td><td>1.39</td></tr>
<tr><td>Train (2021–23)</td><td>283</td><td class="pos">+$40,772</td><td>+144</td><td>1.44</td></tr>
<tr><td><span class="k">Test (2024–26)</span></td><td>347</td><td class="pos">+$41,940</td><td>+121</td><td><span class="k">1.36</span></td></tr>
<tr><td>Without 2022</td><td>540</td><td class="pos">+$52,112</td><td>+97</td><td>1.30</td></tr>
<tr><td>Doubled slippage</td><td>630</td><td class="pos">+$74,837</td><td>+119</td><td>1.35</td></tr>
</table></div>

<div class="box warn">
<span class="k">The one risk to internalize — tail concentration.</span> Remove the best 20 trades
and the other 610 collectively lose. Miss the best 2 and PF drops 1.39 → 1.30; miss 10 → 1.11.
The trades you'd most want to cut short are exactly the ones that pay for everything.
This is why the goal is an automated NT strategy and why discretionary exits are forbidden.
</div>

<div class="tw"><table>
<tr><th>forward planning</th><th>value</th></tr>
<tr><td>Profit factor</td><td><span class="k">1.25–1.30</span> (measured OOS: 1.36)</td></tr>
<tr><td>Expectancy</td><td>+$85–105 / trade · ~10 trades/month · ≈ +$900–1,100/month per ES, lumpy</td></tr>
<tr><td>Drawdown budget</td><td>−$21k per ES (Monte-Carlo 95th); flat stretches of 6–18 months are normal</td></tr>
<tr><td>Account size</td><td><span class="k">$70–85k per ES (~15%/yr)</span> · MES: $7–8.5k per contract (+$8.6/trade, PF 1.24)</td></tr>
<tr><td>Kill switches (backtested to never fire in-sample)</td><td>DD beyond −$25k · trailing 12-mo net below −$10k · either side PF&lt;1.0 for 4 quarters</td></tr>
</table></div>

<figure><img src="data:image/png;base64,__KILL__">
<figcaption><span class="k">Kill rules earned their place.</span> The obvious rule (stop when
12-month PF dips under 1.0) would have fired six times — including four months in a row right
before the book's best stretch. The adopted rules never fire on history and exist to bound the unprecedented.</figcaption></figure>

<h2>Recommended path forward — goal: the NT8 auto-strategy</h2>
<div class="step"><div class="n">1</div><div><span class="k">Validate the port offline.</span>
The C# strategy exists (RegimeSecondEntry.cs, 4 live bugs already found and fixed). Next: compile its
decision core in a standalone harness, feed it the research tick files, and diff its signals against the
research trade list. No NinjaTrader charts involved. <span class="sub">One session.</span></div></div>
<div class="step"><div class="n">2</div><div><span class="k">Update the strategy to this exact spec</span>
(volatility stop, 6-tick retest, gap filter, 30-min cancel) and re-diff. <span class="sub">Same session.</span></div></div>
<div class="step"><div class="n">3</div><div><span class="k">MES live phase, 1 contract, fully automated.</span>
What it verifies in 2–4 months: real limit-fill rates vs the strict model, the churn body, and that the
automation truly holds to the close underwater. What it cannot verify: the tail (needs 12–18 months).
Quiet months ≠ failure; one monster ≠ confirmation.</div></div>
<div class="step"><div class="n">4</div><div><span class="k">ES on forward evidence</span> at $70–85k per
contract, kill switches armed, monthly review of the watch flags: 2026 gap-day behavior (possible filter
decay), the strong-signal-bar paper book, and the gap-day breakout side book (RevFT:BO / MicroChannel CC4
longs — promising, unvalidated).</div></div>

<h2>Verdict</h2>
<div class="box">
<p><span class="k">This is a real but conditional edge, honestly measured.</span> A tail-harvest book with
~20 effective observations, conservative fills, balanced long/short engines, and a known weather
preference (trending markets pay triple). It is not an income yet — it is one validated component
worth roughly 15%/yr on properly-sized capital, and the first system this desk has produced that
survived a full adversarial audit with its numbers intact.</p>
<p><span class="k">Build the bot, run it small, let the tail prove itself.</span> The research cannot
get more honest from here — only live fills can.</p>
</div>
<p class="sub">All scripts, trade lists and audit CSVs on branch regime/indep (~80 commits).
Full technical spec: system_spec_2E_regime_20260724.md. Deep-dive report artifact available.</p>
</div>
"""
for k, v in IMGS.items():
    html = html.replace("__" + k.upper() + "__", v)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print("wrote", OUT, f"({OUT.stat().st_size/1e6:.1f} MB)")
